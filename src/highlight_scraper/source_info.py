"""
source_info.py — best-effort "what app/window was this highlighted in".

X11: uses xdotool. Returns (window_title, app_name).
Wayland (0.4.0): reads /proc/<focused_pid>/cmdline via the compositor's
  focused-window mechanism. Compositor-specific helpers are tried in order:
    1. hyprctl  (Hyprland)
    2. swaymsg  (Sway / i3-on-Wayland)
    3. kdotool  (KDE Plasma Wayland, if installed)
  Falls back gracefully to (None, None) on any failure — capture always
  works, attribution is just blank when nothing is available.

We deliberately do NOT attempt to extract browser URLs. Getting the real
URL of the active tab needs cooperation from the browser (an extension or
its remote-debugging port) — a window title alone doesn't reliably contain
it, and guessing from the title is more likely to mislead than help.

Install (X11):     sudo apt install xdotool
Install (Wayland): hyprctl / swaymsg / kdotool are compositor built-ins;
                   no separate install needed on those compositors.
"""

import json
import shutil
import subprocess

from highlight_scraper.watcher_core import is_wayland

_have_xdotool  = shutil.which("xdotool")  is not None
_have_hyprctl  = shutil.which("hyprctl")  is not None
_have_swaymsg  = shutil.which("swaymsg")  is not None
_have_kdotool  = shutil.which("kdotool")  is not None


def get_active_window_info() -> tuple[str | None, str | None]:
    """
    Returns (window_title, app_name).
    Either or both may be None — never raises.
    """
    if is_wayland():
        return _get_wayland_window_info()
    if not _have_xdotool:
        return None, None
    return _run_xdotool("getwindowname"), _run_xdotool("getwindowclassname")


# ── X11 ──────────────────────────────────────────────────────────────────────

def _run_xdotool(subcommand: str) -> str | None:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", subcommand],
            capture_output=True, text=True, timeout=1,
        )
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ── Wayland ───────────────────────────────────────────────────────────────────

def _get_wayland_window_info() -> tuple[str | None, str | None]:
    """
    Try each Wayland compositor helper in order, return the first that works.
    Falls back to (None, None) if none are available or all fail.
    """
    if _have_hyprctl:
        result = _hyprland_active_window()
        if result != (None, None):
            return result

    if _have_swaymsg:
        result = _sway_active_window()
        if result != (None, None):
            return result

    if _have_kdotool:
        result = _kde_active_window()
        if result != (None, None):
            return result

    return None, None


def _hyprland_active_window() -> tuple[str | None, str | None]:
    """
    Hyprland: `hyprctl activewindow -j` returns JSON with 'title' and 'class'.
    'class' is the app/WM_CLASS — equivalent to xdotool getwindowclassname.
    """
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=1,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        data = json.loads(result.stdout)
        title = data.get("title") or None
        app   = data.get("class") or None
        return title, app
    except (subprocess.TimeoutExpired, FileNotFoundError,
            json.JSONDecodeError, KeyError):
        return None, None


def _sway_active_window() -> tuple[str | None, str | None]:
    """
    Sway / i3-on-Wayland: `swaymsg -t get_tree` returns a JSON tree.
    Walk it to find the focused node.
    """
    try:
        result = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        tree = json.loads(result.stdout)
        node = _sway_find_focused(tree)
        if node is None:
            return None, None
        title = node.get("name") or None
        app   = (node.get("app_id")
                 or (node.get("window_properties") or {}).get("class")
                 or None)
        return title, app
    except (subprocess.TimeoutExpired, FileNotFoundError,
            json.JSONDecodeError, KeyError):
        return None, None


def _sway_find_focused(node: dict) -> dict | None:
    """Recursively walk the sway tree to find the focused leaf node."""
    if node.get("focused") and node.get("type") in ("con", "floating_con"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        result = _sway_find_focused(child)
        if result:
            return result
    return None


def _kde_active_window() -> tuple[str | None, str | None]:
    """
    KDE Plasma Wayland: kdotool getactivewindow then getwindowname /
    getwindowclassname — same interface as xdotool but Wayland-native.
    """
    try:
        wid_result = subprocess.run(
            ["kdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1,
        )
        wid = wid_result.stdout.strip()
        if not wid:
            return None, None

        def _kdo(sub: str) -> str | None:
            r = subprocess.run(
                ["kdotool", sub, wid],
                capture_output=True, text=True, timeout=1,
            )
            return r.stdout.strip() or None

        return _kdo("getwindowname"), _kdo("getwindowclassname")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, None
