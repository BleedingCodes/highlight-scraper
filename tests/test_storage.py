"""
Tests for the small, pure-logic pieces of watcher_core.py that don't
need a real display server. The backend selection/event-loop code
itself needs a live X11 or Wayland session to test meaningfully — see
README.md's "Known limits" section for that gap.
"""

from highlight_scraper.watcher_core import is_wayland


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
