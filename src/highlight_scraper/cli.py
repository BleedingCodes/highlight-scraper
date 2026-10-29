#!/usr/bin/env python3
"""
cli.py — command-line front end for the research highlight capture tool.

    highlight-scraper start [--session NAME] [--with-paste] [--with-tags]
    highlight-scraper stop
    highlight-scraper status
    highlight-scraper tag TAGNAME
    highlight-scraper sessions
    highlight-scraper export --format md|csv|json --out PATH [--session NAME] [--force]

All captures go into one SQLite database (~/.local/share/highlight_scraper/
captures.db by default — see config.py), tagged with a session name so you
can run several research efforts and keep them apart, or query across all
of them. See README.md for the full reference and how to extend this.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from highlight_scraper.config import load_config
from highlight_scraper.session_manager import CaptureSession
from highlight_scraper.storage import CaptureStore
from highlight_scraper import export as exporters

PID_FILE = Path.home() / ".highlight_scraper.pid"

EXPORTERS = {
    "md": exporters.export_markdown,
    "csv": exporters.export_csv,
    "json": exporters.export_json,
}


def _running_session_name():
    info = _read_pid_file()
    if info is None:
        return None
    return info.get("session")


def _validate_session_name(name: str) -> str:
    """Reject session names that cannot be embedded safely in the log
    filename (audit finding 10: a '/' used to crash cmd_start with an
    unhandled FileNotFoundError traceback)."""
    if not name or not name.strip() or any(c in name for c in ("/", "\\", "\0")):
        print(f"Error: invalid session name {name!r} — it may not contain "
              "'/', '\\', or null characters.", file=sys.stderr)
        sys.exit(1)
    return name


def _read_pid_file():
    """Parsed pid-file dict, or None after removing an unreadable/corrupt
    file — a truncated or hand-edited pid file used to raise
    JSONDecodeError out of every command, blocking start/status/stop/tag
    until it was removed by hand (audit finding 10). Valid-JSON-but-not-an
   -object content (e.g. `[]`) counts as corrupt too (the pid-file
    counterpart of config finding N2)."""
    try:
        info = json.loads(PID_FILE.read_text())
    except (OSError, ValueError):
        pass
    else:
        if isinstance(info, dict):
            return info
    print("Corrupt pid file — removing it.")
    PID_FILE.unlink(missing_ok=True)
    return None


def _pid_is_alive(pid: int) -> bool:
    """True if a process with this pid exists (whether or not it's ours)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone/something we can't signal
    return True


def _pid_is_scraper(pid: int) -> bool:
    """True only if this pid is a running highlight-scraper daemon: its
    /proc/<pid>/cmdline must contain this CLI's own '-m highlight_scraper.cli'
    argv pair. Without this identity check, a recycled pid (daemon crashed
    and its pid got reused by e.g. a browser) would be SIGTERMed by
    'stop' (audit finding 7)."""
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return b"-m" in argv and b"highlight_scraper.cli" in argv


def cmd_start(args):
    info = _read_pid_file() if PID_FILE.exists() else None
    if info is not None:
        pid = info.get("pid", -1)
        if _pid_is_alive(pid) and _pid_is_scraper(pid):
            print("Already running. Run 'stop' first.")
            sys.exit(1)
        print(f"Found a stale pid file (process {pid} is not a running "
              f"highlight-scraper daemon — it likely crashed, or the pid "
              f"was recycled). Cleaning it up and starting fresh.")
        PID_FILE.unlink(missing_ok=True)

    session_name = _validate_session_name(args.session or datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_path = Path.home() / f".highlight_scraper_{session_name}.log"

    cmd = [sys.executable, "-m", "highlight_scraper.cli", "_run", "--session", session_name]
    if args.with_paste:
        cmd.append("--with-paste")
    if args.with_tags:
        cmd.append("--with-tags")

    log_fh = open(log_path, "w")
    try:
        os.fchmod(log_fh.fileno(), 0o600)  # log holds raw capture text (finding 5)
    except OSError:
        pass  # non-POSIX or exotic mount — best effort, capture still works
    proc = subprocess.Popen(
        cmd, stdout=log_fh, stderr=subprocess.STDOUT,
        start_new_session=True,  # detach so it survives this shell exiting
    )
    log_fh.close()  # child keeps its own handle to the file

    PID_FILE.write_text(json.dumps({"pid": proc.pid, "session": session_name}))
    try:
        PID_FILE.chmod(0o600)
    except OSError:
        pass

    # Give the child a moment to fail. The daemon dies within milliseconds
    # in the common birth-failure cases (missing backend, unreadable config,
    # missing optional dependency) — any early exit means capture did not
    # start, and reporting "Started" then was misleading (finding 9; the
    # --with-tags/no-pynput case is reviewer finding N3).
    time.sleep(0.5)
    rc = proc.poll()
    if rc is not None:
        PID_FILE.unlink(missing_ok=True)
        print(f"ERROR: the daemon exited immediately (exit code {rc}). "
              "Capture did not start.", file=sys.stderr)
        print(f"Backend/errors log: {log_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Started (pid={proc.pid}), session: {session_name}")
    print(f"Database: {load_config()['db_path']}")
    print(f"Backend/errors log: {log_path}")
    if args.with_paste:
        print("Click-and-hold-to-paste: ON")
    if args.with_tags:
        print("Tag hotkeys: ON (Ctrl+Alt+1/2/3 -> important/question/followup)")
    print("Run 'highlight-scraper stop' to end.")


def cmd_stop(args):
    info = _read_pid_file() if PID_FILE.exists() else None
    if info is None:
        print("Not running.")
        return
    pid = info.get("pid", -1)
    try:
        if _pid_is_alive(pid) and not _pid_is_scraper(pid):
            # PID reuse: that pid belongs to some unrelated process now.
            # Never signal it — treat the pid file as stale instead.
            print(f"PID file points at pid {pid}, which is not a "
                  "highlight-scraper process (the pid was likely recycled). "
                  "Not signaling it; removed the stale pid file.")
            return  # finally-block below removes the file
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped. Session '{info['session']}' saved.")
    except ProcessLookupError:
        print("Process was already gone (stale pid file removed).")
    finally:
        PID_FILE.unlink(missing_ok=True)


def cmd_status(args):
    info = _read_pid_file() if PID_FILE.exists() else None
    if info is None:
        print("Not running.")
        return
    pid = info.get("pid", -1)
    if not _pid_is_alive(pid):
        print("Not running (stale pid file — will be cleaned up on next 'start').")
        return
    if not _pid_is_scraper(pid):
        print(f"Not running (pid file points at pid {pid}, which is not a "
              "highlight-scraper process — the pid was likely recycled; "
              "will be cleaned up on next 'start').")
        return
    print(f"Running (pid={info['pid']}), session: {info['session']}")


def cmd_tag(args):
    config = load_config()
    store = CaptureStore(config["db_path"])
    try:
        session = args.session or _running_session_name()  # None = tag the last capture overall
        row_id = store.set_tag_for_last(args.tag, session=session)
    finally:
        store.close()
    if row_id is None:
        scope = f"session '{session}'" if session else "any session"
        print(f"No captures found in {scope}.")
    else:
        print(f"Tagged capture #{row_id} as: {args.tag}")


def cmd_sessions(args):
    config = load_config()
    store = CaptureStore(config["db_path"])
    try:
        rows = store.sessions()
    finally:
        store.close()
    if not rows:
        print("No captures yet.")
        return
    for name, count, first_ts, last_ts in rows:
        print(f"{name:30s}  {count:5d} captures   {first_ts} .. {last_ts}")


def cmd_export(args):
    config = load_config()
    store = CaptureStore(config["db_path"])
    try:
        exporter = EXPORTERS[args.format]
        try:
            exporter(store, args.session, args.out, force=args.force)
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    finally:
        store.close()
    print(f"Exported ({args.format}): {args.out}")


def cmd_run_foreground(args):
    """Internal — this is what actually runs in the background process."""
    config = load_config()
    session = CaptureSession(config["db_path"], args.session, config)
    session.listeners.append(
        lambda row: print(
            f"[{row.captured_at}] ({row.source_app or 'unknown'}) {row.text}"
            + (f"  [{row.tag}]" if row.tag else ""),
            flush=True,
        )
    )

    try:
        session.start()
    except RuntimeError as e:
        print(f"Error: {e}", flush=True)
        return
    print(f"Backend: {session.watcher.backend_name}", flush=True)

    paste_helper = None
    if args.with_paste:
        from highlight_scraper.paste_on_hold import ClickHoldPaste
        paste_helper = ClickHoldPaste(hold_seconds=config.get("hold_seconds", 0.45))
        paste_helper.start()
        print(paste_helper.warning or "Click-and-hold-to-paste: listening", flush=True)

    tag_hotkeys = None
    if args.with_tags:
        try:
            from highlight_scraper.hotkeys import TagHotkeys
        except ImportError as e:
            # pynput is an optional dependency; a missing one must degrade
            # to capture-without-hotkeys, not kill the daemon (reviewer
            # finding N3: this used to die with ModuleNotFoundError after
            # the parent CLI had already printed "Started").
            print(f"Tag hotkeys unavailable ({e}) — capture continues. "
                  "Install pynput, or drop --with-tags.", flush=True)
        else:
            tag_hotkeys = TagHotkeys(on_tag=session.tag_last)
            tag_hotkeys.start()
            print("Tag hotkeys: listening (Ctrl+Alt+1/2/3)", flush=True)

    stop_flag = {"set": False}

    def handle_term(signum, frame):
        stop_flag["set"] = True

    signal.signal(signal.SIGTERM, handle_term)

    try:
        while not stop_flag["set"]:
            time.sleep(0.2)
    finally:
        session.stop()
        if paste_helper:
            paste_helper.stop()
        if tag_hotkeys:
            tag_hotkeys.stop()


def main():
    parser = argparse.ArgumentParser(description="Research highlight capture tool (CLI)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start watching in the background")
    p_start.add_argument("--session", help="Session name (default: a timestamp)")
    p_start.add_argument("--with-paste", action="store_true",
                          help="Also enable click-and-hold-to-paste (see paste_on_hold.py)")
    p_start.add_argument("--with-tags", action="store_true",
                          help="Also enable Ctrl+Alt+1/2/3 tag hotkeys (see hotkeys.py)")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="Stop watching")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="Check if it's running")
    p_status.set_defaults(func=cmd_status)

    p_tag = sub.add_parser("tag", help="Tag the most recent capture")
    p_tag.add_argument("tag", help="Tag text, e.g. 'important' or 'follow-up'")
    p_tag.add_argument("--session", default=None,
                        help="Defaults to the currently running session, else the last capture overall")
    p_tag.set_defaults(func=cmd_tag)

    p_sessions = sub.add_parser("sessions", help="List every session, count, and time range")
    p_sessions.set_defaults(func=cmd_sessions)

    p_export = sub.add_parser("export", help="Write captures to a Markdown/CSV/JSON file")
    p_export.add_argument("--format", choices=["md", "csv", "json"], required=True)
    p_export.add_argument("--out", required=True, help="Output file path")
    p_export.add_argument("--session", default=None, help="Omit to export all sessions")
    p_export.add_argument("--force", action="store_true",
                           help="Overwrite the output file if it already exists")
    p_export.set_defaults(func=cmd_export)

    p_run = sub.add_parser("_run", help=argparse.SUPPRESS)  # internal use only
    p_run.add_argument("--session", required=True)
    p_run.add_argument("--with-paste", action="store_true")
    p_run.add_argument("--with-tags", action="store_true")
    p_run.set_defaults(func=cmd_run_foreground)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
