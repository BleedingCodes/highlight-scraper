"""
watcher_core.py — shared engine for the mouse-highlight scraper.

Both cli.py and gui.py import this. It picks the best available way to
watch the PRIMARY selection (the text you highlight with the mouse — no
Ctrl+C needed) and calls your callback every time it changes.

Backend priority:
    X11:
        1. Xfixes — the X server pushes us an event the instant the
           selection owner changes. No polling loop at all. Verified
           working end-to-end against a live X server (Linux Mint/
           Cinnamon, X11) on 2026-09-11 — see the comment in
           _run_x11_xfixes for why the call looks slightly unusual
           (python-xlib exposes it as a free function on this build,
           not a bound Window method).
        2. xclip polling — automatic fallback if python-xlib/Xfixes
           isn't available, or if the Xfixes call fails for any reason
           (a different python-xlib version binding things differently,
           say — the fallback exists so that's a degraded experience,
           not a crash).
    Wayland:
        1. `wl-paste --watch` — the compositor invokes our helper
           command every time the selection changes. Push-based, not
           polling, even though it's a subprocess rather than an
           in-process event.
        2. `wl-paste` polling — fallback if wl-clipboard is too old to
           support --watch.

Install notes:
    sudo apt install xclip           # X11 fallback + used to read text
    sudo apt install python3-xlib    # X11 event-driven mode (best)
    sudo apt install wl-clipboard    # Wayland (provides wl-paste)
"""

import os
import shutil
import subprocess
import threading
import time


def is_wayland() -> bool:
    """True if this session is Wayland, not X11."""
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class SelectionWatcher:
    """
    Watches the PRIMARY selection in a background thread and calls
    on_change(text) whenever it changes to something new and non-empty.

    Usage:
        watcher = SelectionWatcher(on_change=my_function)
        watcher.start()
        print(watcher.backend_name)   # what it's actually using
        ...
        watcher.stop()
    """

    def __init__(self, on_change, poll_interval: float = 0.3):
        self.on_change = on_change
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread = None
        self.backend_name = "not started"

    def start(self):
        run_fn, name = self._pick_backend()
        self.backend_name = name
        self._stop_event.clear()
        self._thread = threading.Thread(target=run_fn, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    # ---- backend selection -------------------------------------------------

    def _pick_backend(self):
        if is_wayland():
            if shutil.which("wl-paste"):
                return self._run_wayland, "Wayland (wl-paste --watch, event-driven)"
            raise RuntimeError(
                "Wayland detected but wl-clipboard isn't installed.\n"
                "Install it with: sudo apt install wl-clipboard"
            )

        # X11
        try:
            import Xlib.display  # noqa: F401
            from Xlib.ext import xfixes  # noqa: F401
            return self._run_x11, "X11 (Xfixes, event-driven)"
        except ImportError:
            if shutil.which("xclip"):
                return self._run_x11_polling, "X11 (xclip polling — python3-xlib not installed)"
            raise RuntimeError(
                "Neither python3-xlib nor xclip is available.\n"
                "Install one with: sudo apt install python3-xlib   (best)\n"
                "             or:  sudo apt install xclip          (fallback)"
            )

    # ---- X11: event-driven via Xfixes, with automatic fallback -------------

    def _run_x11(self):
        try:
            self._run_x11_xfixes()
        except Exception as e:
            print(f"[watcher] Event-driven X11 mode failed ({e}); "
                  f"falling back to polling.", flush=True)
            self.backend_name = "X11 (xclip polling — Xfixes failed at runtime)"
            self._run_x11_polling()

    def _run_x11_xfixes(self):
        from Xlib import display
        from Xlib.ext import xfixes

        d = display.Display()
        if not d.has_extension("XFIXES"):
            raise RuntimeError("X server does not support the XFIXES extension")
        d.xfixes_query_version()

        root = d.screen().root
        # Ask the X server to notify us whenever PRIMARY gets a new owner
        # (i.e. someone just finished highlighting something new).
        #
        # select_selection_input is a free function in python-xlib, not a
        # bound Window method (this python-xlib build's xfixes.init() only
        # binds the cursor calls onto Window — confirmed by introspecting
        # dir(xfixes) and dir(root) on real hardware). It was written to be
        # called as `self.xfixes_select_selection_input(...)`, so we call
        # it unbound and pass root as `self` (it only needs root's
        # `.display` attribute) and again as the `window` argument whose
        # selection ownership we're watching. Verified working end-to-end
        # against a live X server (Linux Mint/Cinnamon, X11) on 2026-09-11.
        xfixes.select_selection_input(
            root, root,
            d.get_atom("PRIMARY"),
            xfixes.XFixesSetSelectionOwnerNotifyMask,
        )
        d.flush()

        last_seen = ""
        while not self._stop_event.is_set():
            if d.pending_events():
                d.next_event()  # we only registered for one kind of event
                text = self._read_primary_xclip()
                if text and text != last_seen:
                    last_seen = text
                    self.on_change(text)
            else:
                time.sleep(0.05)  # just yielding the CPU, not polling content

    @staticmethod
    def _read_primary_xclip() -> str:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "primary", "-o"],
                capture_output=True, text=True, timeout=1,
            )
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    # ---- X11: plain polling fallback ---------------------------------------

    def _run_x11_polling(self):
        last_seen = ""
        while not self._stop_event.is_set():
            text = self._read_primary_xclip()
            if text and text != last_seen:
                last_seen = text
                self.on_change(text)
            time.sleep(self.poll_interval)

    # ---- Wayland: event-driven via wl-paste --watch ------------------------

    def _run_wayland(self):
        SEP = "\x1e"  # ASCII "record separator" — splits one change from the next
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--type", "text", "--primary", "--watch",
                 "sh", "-c", f"cat; printf '{SEP}'"],
                stdout=subprocess.PIPE, text=True,
            )
        except FileNotFoundError:
            self._run_wayland_polling()
            return

        buf = ""
        try:
            while not self._stop_event.is_set():
                chunk = proc.stdout.read(1)
                if chunk == "":
                    break  # wl-paste exited — likely --watch unsupported
                if chunk == SEP:
                    if buf:
                        self.on_change(buf)
                    buf = ""
                else:
                    buf += chunk
        finally:
            proc.terminate()

        # wl-paste --watch exited (not a missing binary — that's caught above).
        # Most likely cause: an older wl-clipboard that doesn't support --watch.
        # Fall back to polling so capture continues rather than silently dying.
        if not self._stop_event.is_set():
            print("[watcher] wl-paste --watch exited; falling back to polling.", flush=True)
            self.backend_name = "Wayland (wl-paste polling — --watch unsupported)"
            self._run_wayland_polling()

    # ---- Wayland: plain polling fallback ------------------------------------

    def _run_wayland_polling(self):
        last_seen = ""
        while not self._stop_event.is_set():
            try:
                result = subprocess.run(
                    ["wl-paste", "--type", "text", "--primary", "--no-newline"],
                    capture_output=True, text=True, timeout=1,
                )
                text = result.stdout
            except (FileNotFoundError, subprocess.TimeoutExpired):
                text = ""
            if text and text != last_seen:
                last_seen = text
                self.on_change(text)
            time.sleep(self.poll_interval)
