"""
source_info.py — best-effort "what app/window was this highlighted in".

X11 only, via xdotool. On Wayland, or if xdotool isn't installed, this
returns (None, None) rather than failing — capture still works, you
just lose the source attribution.

We deliberately do NOT attempt to extract browser URLs. Getting the
real URL of the active tab needs cooperation from the browser (an
extension, or its remote-debugging port) — a window title alone doesn't
reliably contain it, and guessing from the title is more likely to
mislead you than help. That's a separate, larger piece of work if you
ever want it.

Install: sudo apt install xdotool
"""

import shutil
import subprocess

from highlight_scraper.watcher_core import is_wayland

_have_xdotool = shutil.which("xdotool") is not None


def get_active_window_info():
    """Returns (window_title, app_name). Either (or both) may be None."""
    if is_wayland() or not _have_xdotool:
        return None, None

    return _run_xdotool("getwindowname"), _run_xdotool("getwindowclassname")


def _run_xdotool(subcommand: str):
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", subcommand],
            capture_output=True, text=True, timeout=1,
        )
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
