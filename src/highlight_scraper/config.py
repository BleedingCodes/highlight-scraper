"""
config.py — simple JSON settings file, created with sensible defaults
the first time anything asks for it.

Location: ~/.config/highlight_scraper/config.json

excluded_apps: a highlight is skipped (never stored) if the active
window's app name contains any of these strings, case-insensitive.
This is the privacy guard — extend it with anything you don't want
silently logged (password managers, banking apps, etc.).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "highlight_scraper"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "poll_interval": 0.3,
    "hold_seconds": 0.45,
    "preview_chars": 300,
    "min_length": 3,
    "merge_window_seconds": 2.0,
    "excluded_apps": [
        "keepassxc", "keepass", "bitwarden", "1password",
        "gnome-keyring", "seahorse",
    ],
    # Privacy fail-closed: when no app attribution is available we cannot
    # prove a highlight is NOT from an excluded app, so it is skipped.
    # Set to false to keep capturing even when attribution is unavailable
    # (e.g. GNOME Wayland) — see README "Known Limits".
    "exclude_unattributed_apps": True,
    "db_path": str(Path.home() / ".local" / "share" / "highlight_scraper" / "captures.db"),
}


def _handle_corrupt_config() -> None:
    """A corrupt/unreadable config must never be silently replaced with
    defaults (it may hold the user's privacy exclude list). Back it up,
    warn loudly, and run on defaults until the user intervenes."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG_PATH.with_name(f"config.json.corrupt-{ts}")
    backed_up = None
    try:
        backup.write_bytes(CONFIG_PATH.read_bytes())
        backed_up = backup
    except OSError:
        pass  # the warning below still tells the user the file was untouched
    print(
        f"WARNING: {CONFIG_PATH} is corrupt or unreadable — it was NOT "
        f"overwritten; running with defaults."
        + (f" A backup of the corrupt file is at: {backed_up}" if backed_up else ""),
        file=sys.stderr,
    )


def load_config() -> dict:
    corrupt = False
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                # valid JSON but not an object (e.g. a bare list) —
                # {**DEFAULTS, **data} would crash on it; treat as corrupt
                corrupt = True
        except (json.JSONDecodeError, OSError):
            corrupt = True
        if corrupt:
            _handle_corrupt_config()
            loaded = {}
    else:
        loaded = {}

    merged = {**DEFAULTS, **loaded}
    if not corrupt and merged != loaded:
        save_config(merged)  # persist any newly-introduced default keys
    return merged


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)  # atomic — an interrupted save can't corrupt the file
