"""
Regression tests for audit finding 7: `stop` used to send SIGTERM to
whatever PID happens to sit in the pid file — including a recycled pid
now owned by an unrelated process. Commands must verify the pid is a
running highlight-scraper daemon (its /proc cmdline contains this CLI's
'-m highlight_scraper.cli' argv pair) before signaling anything.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from highlight_scraper import cli

pytestmark = pytest.mark.skipif(
    not Path("/proc/self/cmdline").exists(), reason="/proc required (Linux)"
)


def _spawn_child(argv_markers=()):
    """Spawn a throwaway processes: a plain python child by default, or one
    whose cmdline carries the daemon's permissive argv markers (so the
    identity helper matches it without starting a real daemon)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(20)", *argv_markers],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def child():
    procs = []

    def _add(argv_markers=()):
        proc = _spawn_child(argv_markers)
        procs.append(proc)
        return proc

    yield _add

    for proc in procs:
        proc.kill()
        proc.wait()


def _point_pid_file_at(monkeypatch, tmp_path, pid):
    pid_file = tmp_path / "pid"
    pid_file.write_text(json.dumps({"pid": pid, "session": "test-session"}))
    monkeypatch.setattr(cli, "PID_FILE", pid_file)
    return pid_file


def test_identity_helper_matches_daemon_argv(child):
    ours = child(argv_markers=("-m", "highlight_scraper.cli"))
    plain = child()
    try:
        assert cli._pid_is_scraper(ours.pid) is True
        assert cli._pid_is_scraper(plain.pid) is False, \
            "an arbitrary same-user process must not look like our daemon"
    finally:
        ours.kill(); ours.wait()
        plain.kill(); plain.wait()


def test_stop_refuses_to_signal_a_recycled_pid(tmp_path, monkeypatch, child, capsys):
    """The reproduced failure mode: a pid file whose pid now belongs to an
    unrelated process must NOT be signaled."""
    proc = child()
    _point_pid_file_at(monkeypatch, tmp_path, proc.pid)

    cli.cmd_stop(None)

    assert proc.poll() is None, \
        "a foreign process must never be SIGTERMed by 'stop'"
    assert "not a highlight-scraper process" in capsys.readouterr().out
    assert not cli.PID_FILE.exists(), "the stale/foreign pid file must be removed"


def test_stop_signals_a_verified_daemon_pid(tmp_path, monkeypatch, child, capsys):
    """Positive control: the normal flow still terminates the daemon."""
    proc = child(argv_markers=("-m", "highlight_scraper.cli", "_run"))
    _point_pid_file_at(monkeypatch, tmp_path, proc.pid)

    cli.cmd_stop(None)
    proc.wait(timeout=5)

    assert proc.returncode != 0, "the (marked) child must have been terminated"
    assert "Stopped." in capsys.readouterr().out
    assert not cli.PID_FILE.exists()


def test_status_reports_a_recycled_pid_as_not_running(tmp_path, monkeypatch, child, capsys):
    proc = child()
    _point_pid_file_at(monkeypatch, tmp_path, proc.pid)

    cli.cmd_status(None)

    out = capsys.readouterr().out
    assert out.startswith("Not running"), \
        "a pid we cannot verify as ours must not be reported as our daemon"
    assert "not a highlight-scraper process" in out
    assert cli.PID_FILE.exists(), "status reports only; healing happens on next start"


# ── audit finding 10: corrupt pid file must not crash every command ────────

@pytest.mark.parametrize("garbage", ["{truncated", "[]", "not json"])
def test_corrupt_pid_file_is_healed_not_fatal(tmp_path, monkeypatch, capsys, garbage):
    pid_file = _point_pid_file_at(monkeypatch, tmp_path, 6666)
    pid_file.write_text(garbage)

    cli.cmd_status(None)      # must not raise
    out = capsys.readouterr()
    assert "Corrupt pid file" in out.out and "Not running." in out.out
    assert not pid_file.exists(), "the corrupt file must be removed (self-heal)"

    _point_pid_file_at(monkeypatch, tmp_path, 6666).write_text(garbage)
    cli.cmd_stop(None)        # must not raise
    out = capsys.readouterr()
    assert "Corrupt pid file" in out.out
    assert not cli.PID_FILE.exists()

    _point_pid_file_at(monkeypatch, tmp_path, 6666).write_text(garbage)
    cli._running_session_name()  # used by `tag` — must not raise


# ── audit finding 10: session-name validation ───────────────────────────────

@pytest.mark.parametrize("bad", ["sub/dirname", "a\\b", "nul\0char", "", "  "])
def test_invalid_session_names_are_rejected_with_clean_message(monkeypatch, capsys, bad):
    with pytest.raises(SystemExit) as excinfo:
        cli._validate_session_name(bad)

    assert excinfo.value.code == 1
    assert "invalid session name" in capsys.readouterr().err


def test_valid_session_names_pass():
    for name in ("research-2026-09-11", "lab session", "20261028_194759"):
        assert cli._validate_session_name(name) == name


def test_start_rejects_bad_session_before_spawning(tmp_path, monkeypatch, capsys):
    """The full reproduced failure: `start --session sub/dirname` used to
    raise FileNotFoundError out of the log-file open with a traceback."""
    class _NoSpawn:
        def __getattr__(self, name):
            raise AssertionError(
                "subprocess must not be used with an invalid session name")

    monkeypatch.setattr(cli, "PID_FILE", tmp_path / "pid")
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli, "subprocess", _NoSpawn())  # spawn must never happen

    args = type("A", (), {"session": "sub/dirname",
                          "with_paste": False, "with_tags": False})()
    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_start(args)

    assert excinfo.value.code == 1
    assert "invalid session name" in capsys.readouterr().err

