# highlight-scraper

Watches text you highlight with your mouse — no Ctrl+C needed — and logs it
to a local SQLite database, tagged with a session name and which app the text
came from. Three front ends: CLI, desktop GUI, and system tray icon.

Built for researchers, writers, and power users who highlight text constantly
and want a searchable record without changing how they work.

---

## What It Does

- **Captures the X11 PRIMARY selection** — anything you highlight is saved instantly, no keypress required
- **SQLite storage** — every capture is stored locally at `~/.local/share/highlight_scraper/captures.db`
- **Session-based** — group captures by session name for later export and filtering
- **Source attribution** — logs which app and window the highlight came from (X11 only)
- **Tags** — mark captures as `important`, `question`, or `followup` via CLI or hotkeys
- **Export** — Markdown, CSV, or JSON
- **Three front ends** — CLI, tkinter GUI, system tray icon — all running on the same engine
- **Click-and-hold-to-paste** — accessibility gesture, X11 only, optional
- **Ctrl+Alt+1/2/3 tag hotkeys** — optional, requires `pynput`
- **Merge-on-extension** — extending a highlight within 2 seconds updates the existing row rather than creating a duplicate
- **Excluded apps** — password managers and other sensitive apps are blocked from capture by default

---

## Requirements

| Requirement | Platform | Notes |
|---|---|---|
| Python 3.9+ | All | |
| `xclip`, `python3-xlib`, `xdotool` | X11 | For event-driven capture and source attribution |
| `wl-clipboard` | Wayland | For capture; paste/hotkey features are X11 only |
| `python3-tk` | Linux | GUI front end only |
| `pynput` | Optional | Paste-on-hold and tag hotkeys |
| `pystray`, `pillow` | Optional | Tray icon front end |

Linux (X11 or Wayland). No Windows or macOS support — PRIMARY selection
is an X11/Wayland concept with no equivalent on other platforms.

---

## Installation

```bash
git clone https://github.com/BleedingCodes/highlight-scraper.git
cd highlight-scraper
./install.sh
```

`install.sh` detects X11 vs Wayland, installs system packages via apt, and
pip-installs the package with all optional extras. Safe to re-run.

**Manual install:**

```bash
# X11
sudo apt install xclip python3-xlib xdotool python3-dev python3-tk build-essential

# Wayland
sudo apt install wl-clipboard python3-dev python3-tk build-essential

# Package with all optional extras
python3 -m pip install -e '.[all]' --break-system-packages
```

Plain capture works without `pynput`, `pystray`, and `pillow` — you just
won't have paste-on-hold, tag hotkeys, or the tray icon.

---

## Quick Start

**CLI**
```bash
highlight-scraper start --session "research-2026-09-11" --with-tags
# highlight text while you read — every highlight is saved automatically
highlight-scraper tag important
highlight-scraper stop
highlight-scraper sessions
highlight-scraper export --format md --session "research-2026-09-11" --out notes.md
```

**GUI**
```bash
highlight-scraper-gui
```
Type a session name, click Start, highlight text. Captures appear live in the
recent-captures list. Tag buttons and export dialog built in.

**Tray**
```bash
highlight-scraper-tray
```
Right-click the icon: Start / Pause / Stop / Open data folder / Quit. Best for
always-on capture without a visible window.

---

## Command Reference

| Command | Flags | What It Does |
|---|---|---|
| `start` | `--session NAME`, `--with-paste`, `--with-tags` | Begin a capture session |
| `stop` | — | End the running session |
| `status` | — | Show running status and session name; auto-heals stale PID files |
| `tag TAGNAME` | — | Tag the most recent capture |
| `sessions` | — | List all sessions with capture count and timestamps |
| `export` | `--format md\|csv\|json`, `--out PATH`, `--session NAME` | Export captures to a file |

---

## Config File

Auto-created at `~/.config/highlight_scraper/config.json` on first run.

| Key | Default | Meaning |
|---|---|---|
| `poll_interval` | `0.3` | Seconds between checks (polling fallback only) |
| `hold_seconds` | `0.45` | Hold duration for click-and-hold-to-paste |
| `min_length` | `3` | Highlights shorter than this are ignored |
| `merge_window_seconds` | `2.0` | Extending a highlight within this window updates the existing row |
| `excluded_apps` | password managers | App name substrings — matches are never stored |
| `db_path` | `~/.local/share/highlight_scraper/captures.db` | SQLite database location |

---

## Project Structure

```
highlight-scraper/
├── src/highlight_scraper/
│   ├── watcher_core.py     # X11/Wayland selection watcher, backend detection
│   ├── session_manager.py  # Central engine — filtering, merging, storage coordination
│   ├── storage.py          # SQLite capture store
│   ├── source_info.py      # Active app/window detection (X11 only)
│   ├── export.py           # Markdown, CSV, JSON export
│   ├── config.py           # Config file load/save
│   ├── paste_on_hold.py    # Click-and-hold-to-paste gesture
│   ├── hotkeys.py          # Ctrl+Alt+1/2/3 tag hotkeys
│   ├── cli.py              # CLI front end
│   ├── gui.py              # tkinter GUI front end
│   └── tray.py             # System tray front end
├── tests/                  # 29 pytest tests
├── install.sh              # One-command setup
├── conftest.py             # Lets pytest find the package without installing
├── pyproject.toml
├── CHANGELOG.md
├── LICENSE
└── README.md
```

Three front ends, one shared engine. All filtering, merging, and storage
logic lives in `session_manager.py` — change it once, it applies everywhere.

---

## Running Tests

```bash
pip install pytest --break-system-packages
pytest
```

29 tests covering config defaults and merging, the storage layer, all three
export formats, session manager filtering rules, and excluded-app blocking.
Works right after cloning — `conftest.py` puts `src/` on the path without
needing to run `install.sh` first.

---

## Known Limits

- Source attribution (which app/window) is **X11 only** — Wayland gets `None`, capture still works
- **Browser URLs are never captured** — only the window title
- **Paste-on-hold and tag hotkeys are X11 only** — Wayland blocks global input listening
- **Wayland event-loop path is unverified on a live Wayland session** — X11 path has been verified end-to-end on Linux Mint/Cinnamon
- **Linux only** — PRIMARY selection has no equivalent on Windows or macOS

---

## Built by MainbyteLabs

Python tooling for electronics labs, hardware shops, and Linux-based tech teams.

[MainbyteLabs](https://github.com/MR-MainbyteLabs) ·
[LinkedIn](https://linkedin.com/in/michael-rivera-c0ding) ·
mr.mainbytelabs@gmail.com

---

## License

MIT License — see `LICENSE`.
