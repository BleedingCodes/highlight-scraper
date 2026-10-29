"""
Tests for the small, pure-logic pieces of watcher_core.py that don't
need a real display server. The backend selection/event-loop code
itself needs a live X11 or Wayland session to test meaningfully — see
README.md's "Known limits" section for that gap.
"""

import sys
import time
from types import ModuleType

import pytest

from highlight_scraper import watcher_core
from highlight_scraper.watcher_core import SelectionWatcher, is_wayland


@pytest.fixture
def x11_session(monkeypatch):
    """Force the X11 (non-Wayland) backend-selection path, with Xlib treated
    as importable (fake modules shadow any real installation)."""
    monkeypatch.setattr(watcher_core, "is_wayland", lambda: False)
    monkeypatch.setitem(sys.modules, "Xlib", ModuleType("Xlib"))
    monkeypatch.setitem(sys.modules, "Xlib.display", ModuleType("Xlib.display"))
    monkeypatch.setitem(sys.modules, "Xlib.ext", ModuleType("Xlib.ext"))
    monkeypatch.setitem(sys.modules, "Xlib.ext.xfixes", ModuleType("Xlib.ext.xfixes"))


def test_xfixes_backend_requires_xclip(x11_session, monkeypatch):
    """Regression for audit finding 8: with python-xlib available but xclip
    missing, the Xfixes backend used to be selected while every capture
    read silently returned ''. Backend selection must raise instead."""
    monkeypatch.setattr(watcher_core.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="xclip"):
        SelectionWatcher(on_change=lambda text: None)._pick_backend()


def test_xfixes_backend_selected_when_xlib_and_xclip_available(x11_session, monkeypatch):
    monkeypatch.setattr(watcher_core.shutil, "which",
                        lambda name: "/usr/bin/xclip" if name == "xclip" else None)

    run_fn, name = SelectionWatcher(on_change=lambda text: None)._pick_backend()

    assert "Xfixes" in name, "xlib + xclip must select the event-driven backend"
    assert run_fn.__name__ == "_run_x11"


def test_polling_backend_selected_without_xlib(x11_session, monkeypatch):
    # Force the Xlib import to fail even though real Xlib is installed:
    # a value of None in sys.modules makes `import Xlib...` raise ImportError.
    import sys
    for name in ("Xlib", "Xlib.display", "Xlib.ext", "Xlib.ext.xfixes"):
        monkeypatch.setitem(sys.modules, name, None)

    monkeypatch.setattr(watcher_core.shutil, "which",
                        lambda name: "/usr/bin/xclip" if name == "xclip" else None)

    _, name = SelectionWatcher(on_change=lambda text: None)._pick_backend()

    assert "polling" in name, "xlib missing + xclip present must select the polling fallback"


def test_capture_loop_survives_a_broken_iteration(monkeypatch):
    """Regression for audit finding 11: an exception mid-loop (e.g. a
    UnicodeDecodeError from a hostile clipboard, or a bug in on_change)
    used to silently kill the daemon thread — capture stopped while the
    app still said 'Running'. The loop must cage the exception and keep
    capturing."""
    received = []
    watcher = SelectionWatcher(on_change=received.append, poll_interval=0.02)

    calls = []

    def flaky_reader():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated decode failure")
        return f"capture #{len(calls)}"

    monkeypatch.setattr(SelectionWatcher, "_read_primary_xclip",
                        staticmethod(flaky_reader))
    # Force the polling backend so no live X/Wayland server is involved:
    # the test runs the real polling loop, whose per-iteration cage is
    # finding 11's fix (the Xfixes/Wayland loop bodies use the same cage).
    monkeypatch.setattr(SelectionWatcher, "_pick_backend",
                        lambda self: (self._run_x11_polling, "test-polling"))

    watcher.start()
    try:
        for _ in range(200):  # up to ~2 s — generous on slow machines
            if received:
                break
            time.sleep(0.01)
    finally:
        watcher.stop()

    assert len(received) >= 1, \
        "capture must continue after a broken iteration, not die silently"
    assert watcher._thread is not None
    watcher._thread.join(timeout=0.1)
    assert not watcher._thread.is_alive(), "stop() must still terminate the thread"


def test_is_wayland_true_when_wayland_display_set(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert is_wayland() is True


def test_is_wayland_true_when_session_type_is_wayland(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert is_wayland() is True


def test_is_wayland_false_on_plain_x11(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert is_wayland() is False


def test_is_wayland_session_type_is_case_insensitive(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "WAYLAND")
    assert is_wayland() is True
