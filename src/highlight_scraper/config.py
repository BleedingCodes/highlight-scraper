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
    "db_path": str(Path.home() / ".local" / "share" / "highlight_scraper" / "captures.db"),
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    merged = {**DEFAULTS, **data}
    if merged != data:
        save_config(merged)  # persist any newly-introduced default keys
    return merged


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
