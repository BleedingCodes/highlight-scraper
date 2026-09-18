"""
paste_on_hold.py — assistive "click-and-hold to paste" gesture.

Left-click on a text field and hold still (don't drag) for ~0.45s, then
release. That gesture pastes the current PRIMARY selection — whatever
you last highlighted with the mouse, anywhere — into that field.

How: it synthesizes an X11 middle-click at the same spot. Middle-click-
pastes-PRIMARY is a native, built-in X11 behavior; this module just gives
you a way to trigger it with a left-click-hold instead of a working
middle button.

Telling a "hold to paste" apart from a normal click-drag text selection:
    - if the pointer moves more than MOVE_TOLERANCE_PX px while the
      button is down, that's a drag/selection — ignored.
    - if it stays still for at least HOLD_SECONDS before release, that's
      a paste trigger.

X11 only. On Wayland, global mouse listening generally does not work
without extra OS-level permissions (reading raw input devices via
python-evdev, which needs root or `input` group membership) — see the
bottom of this file for what that path would look like if you need it.

Requires: pip install pynput --break-system-packages
          (pulls in python-xlib automatically on Linux)

Run standalone:
    python3 -m highlight_scraper.paste_on_hold
Or import ClickHoldPaste and call .start() / .stop() from the GUI or CLI.
"""

import math
import time

from highlight_scraper.watcher_core import is_wayland

HOLD_SECONDS = 0.45        # how long to hold still before it counts as "hold"
MOVE_TOLERANCE_PX = 4      # movement allowed before it's treated as a drag


class ClickHoldPaste:
    def __init__(self, hold_seconds: float = HOLD_SECONDS,
                 move_tolerance: int = MOVE_TOLERANCE_PX, on_paste=None):
        self.hold_seconds = hold_seconds
        self.move_tolerance = move_tolerance
        self.on_paste = on_paste  # optional callback(x, y), fired on every paste
        self._press_time = None
        self._press_pos = None
        self._listener = None
        self._mouse_ctrl = None
        self.warning = None

    def start(self):
        if is_wayland():
            self.warning = (
                "Wayland detected — global mouse listening usually doesn't "
                "work here without extra permissions. See the note at the "
                "bottom of paste_on_hold.py."
            )

        from pynput import mouse
        self._mouse_ctrl = mouse.Controller()
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        from pynput.mouse import Button
        if button != Button.left:
            return

        if pressed:
            self._press_time = time.time()
            self._press_pos = (x, y)
            return

        if self._press_time is None:
            return

        held = time.time() - self._press_time
        px, py = self._press_pos
        moved = math.hypot(x - px, y - py)
        self._press_time = None

        if held >= self.hold_seconds and moved <= self.move_tolerance:
            self._paste_at(x, y)

    def _paste_at(self, x, y):
        from pynput.mouse import Button
        time.sleep(0.05)  # let the real click finish focusing the field first
        self._mouse_ctrl.position = (x, y)
        self._mouse_ctrl.click(Button.middle)
        if self.on_paste:
            self.on_paste(x, y)


def main():
    print(f"Click and hold (don't drag) on a text field for "
          f"{HOLD_SECONDS}s, then release, to paste. Ctrl+C to quit.")
    chp = ClickHoldPaste(on_paste=lambda x, y: print(f"Pasted at ({x}, {y})", flush=True))
    chp.start()
    if chp.warning:
        print(chp.warning)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        chp.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# Wayland path, if you need it later:
#
# Listening: pynput can't see global clicks under Wayland. The workaround is
# reading the mouse's raw device file directly with `python-evdev`
# (bypasses the compositor entirely, works under both X11 and Wayland), e.g.:
#     from evdev import InputDevice, categorize, ecodes
#     dev = InputDevice('/dev/input/eventX')   # find yours: `sudo libinput list-devices`
# This needs your user in the `input` group (or root) — a permissions step,
# not a code change.
#
# Injecting the paste: `xdotool` doesn't work on native Wayland windows.
# Use `ydotool` instead (needs the `ydotoold` daemon running):
#     ydotool click 0xC2   # middle button down+up — verify the button code
#                           # against `ydotool click --help` on your system
# or `wtype` for keyboard-based paste (Ctrl+V) on wlroots-based compositors.
# ---------------------------------------------------------------------------
