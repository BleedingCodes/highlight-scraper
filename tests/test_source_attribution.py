"""
Regression guards for the X11 app-attribution fix (source_info._x11_app_class).

xdotool has no `getwindowclassname` subcommand, so the old
`_run_xdotool("getwindowclassname")` call always returned None on X11.
With the 0.4.2 fail-closed privacy guard, an unattributed capture with a
non-empty exclude list is skipped — so broken attribution previously
meant zero captures on any machine with a standard exclude list.

These tests monkeypatch subprocess.run inside source_info so they run
identically on machines without a live X server.
"""

from __future__ import annotations

import subprocess
import types

import pytest

from highlight_scraper import source_info


class _FakeResult:
    """Minimal subprocess.CompletedProcess stand-in."""

    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


@pytest.fixture()
def fake_processes(monkeypatch):
    """Queue of (match_words, result) consulted in order; None result => raise."""
    calls: list[list[str]] = []
    queue: list[tuple[tuple[str, ...], object]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        for words, result in queue:
            if all(w in argv for w in words):
                queue.remove((words, result))
                if result is None:
                    raise subprocess.TimeoutExpired(argv, 1)
                return result
        raise AssertionError(f"unexpected subprocess call: {argv}")

    monkeypatch.setattr(source_info.subprocess, "run", fake_run)
    monkeypatch.setattr(source_info, "_have_xprop", True)

    holder = types.SimpleNamespace(queue=queue, calls=calls)
    return holder


_QUEUE = ((("getactivewindow"),), None)  # placeholder to keep flake quiet


def test_parses_class_from_wm_class_pair(fake_processes):
    fake_processes.queue.append(
        ((("getactivewindow"),), _FakeResult("1234\n")))
    fake_processes.queue.append(
        ((("xprop"),), _FakeResult('WM_CLASS = "gnome-terminal-server", "Gnome-terminal"\n')))
    # xprop returns the pair; the second string is the class
    assert source_info._x11_app_class() == "Gnome-terminal"


def test_single_string_wm_class_falls_back_to_first(fake_processes):
    fake_processes.queue.append(((("getactivewindow"),), _FakeResult("1234\n")))
    fake_processes.queue.append(
        ((("xprop"),), _FakeResult('WM_CLASS = "myapp"\n')))
    assert source_info._x11_app_class() == "myapp"


def test_returns_none_when_xprop_reported_no_window(fake_processes):
    fake_processes.queue.append(((("getactivewindow"),), _FakeResult("\n")))
    assert source_info._x11_app_class() is None


def test_returns_none_when_xprop_fails(fake_processes):
    fake_processes.queue.append(((("getactivewindow"),), _FakeResult("1234\n")))
    # nonzero rc from xprop => None, never raises
    fake_processes.queue.append(
        ((("xprop"),), _FakeResult("", returncode=1)))
    assert source_info._x11_app_class() is None


def test_returns_none_when_calls_time_out(fake_processes):
    fake_processes.queue.append(((("getactivewindow"),), None))  # raises
    assert source_info._x11_app_class() is None


def test_returns_none_without_xprop(monkeypatch):
    monkeypatch.setattr(source_info, "_have_xprop", False)
    assert source_info._x11_app_class() is None
