"""
Regression tests for audit finding 9 (parent prints "Started" even when
the daemon dies at birth) and reviewer finding N3 (--with-tags without
pynput used to kill the daemon with a traceback after the false success).
Both run against cmd_start's new early-exit liveness check with a fake
Popen — no real daemon is spawned.
"""

import json

import pytest

from highlight_scraper import cli


class _FakeProc:
    def __init__(self, poll_result=None):
        self.pid = 4242
        self._poll_result = poll_result

    def poll(self):
        return self._poll_result


class _FakeArgs:
    session = None
    with_paste = False
    with_tags = False


def _run_cmd_start(monkeypatch, tmp_path, proc):
    monkeypatch.setattr(cli, "PID_FILE", tmp_path / ".highlight_scraper.pid")
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: proc)
    # avoid touching the user's real home dir for the log file
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    cli.cmd_start(_FakeArgs())
    return cli.PID_FILE


def test_start_reports_failure_when_daemon_dies_immediately(tmp_path, monkeypatch, capsys):
    """Regression for finding 9: an instantly-dead child must produce an
    error and exit status 1 — never a false 'Started'."""
    with pytest.raises(SystemExit) as excinfo:
        _run_cmd_start(monkeypatch, tmp_path, _FakeProc(poll_result=1))

    assert excinfo.value.code == 1
    out = capsys.readouterr()
    assert "Started" not in out.out
    assert "exited immediately" in out.err
    assert not cli.PID_FILE.exists(), "the stale pid file of a dead daemon must be removed"


def test_start_reports_success_for_live_daemon(tmp_path, monkeypatch, capsys):
    pid_file = _run_cmd_start(monkeypatch, tmp_path, _FakeProc(poll_result=None))

    out = capsys.readouterr()
    assert "Started (pid=4242)" in out.out
    assert pid_file.exists()
    info = json.loads(pid_file.read_text())
    assert info["pid"] == 4242 and isinstance(info["session"], str) and info["session"]


def test_start_treats_any_immediate_exit_as_failure(tmp_path, monkeypatch, capsys):
    """cmd_run_foreground exits 0 after a caught RuntimeError (missing
    backend), so a clean exit within the liveness window is still failure."""
    with pytest.raises(SystemExit) as excinfo:
        _run_cmd_start(monkeypatch, tmp_path, _FakeProc(poll_result=0))

    assert excinfo.value.code == 1
    assert "Started" not in capsys.readouterr().out
    assert not cli.PID_FILE.exists()
