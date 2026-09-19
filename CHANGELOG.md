# Changelog

## 0.4.1 — export overwrite guard

- **export.py** — all three exporters (Markdown, CSV, JSON) now refuse to
  overwrite an existing file by default. Attempting to export to a path that
  already exists raises `FileExistsError` with a clear message.
  Pass `force=True` in the API (or `--force` on the CLI) to allow the overwrite.
- **cli.py** — `export` subcommand gains a `--force` flag. Without it,
  the command exits with an error and a clear message if the output file exists.
  The existing file is never modified on a refused export.
- **tests/test_export.py** — five new tests covering the overwrite guard:
  all three formats block silent overwrite by default, all three verify the
  existing file is untouched on refusal, and two formats verify `force=True`
  allows the overwrite.



## 0.4.0 — Four program-level improvements

All four changes are to the program itself, not the GUI skin.

- **storage.py** — `delete_capture(row_id)`: permanently deletes one
  capture by id. Thread-safe; safe to call while a session is running.
  Returns True if a row was deleted, False if the id didn't exist.

- **storage.py** — `search(query, session, limit)`: case-insensitive
  substring search across all capture text bodies. Optionally restricted
  to one session. Returns a list of Capture dataclass instances,
  most recent first.

- **source_info.py** — Wayland source attribution: `get_active_window_info()`
  now attempts to return (window_title, app_name) on Wayland instead of
  always returning (None, None). Three compositor helpers tried in order:
  Hyprland (`hyprctl activewindow -j`), Sway/i3 (`swaymsg -t get_tree`),
  KDE Plasma Wayland (`kdotool`). Falls back gracefully to (None, None)
  if none are available — capture is never interrupted.

- **session_manager.py** — Auto-export: after every N captures
  (configured via `auto_export_every` in config.json, default 0 = off),
  the current session is automatically exported to a Markdown file at
  `auto_export_path`. Export failures are silently swallowed — they never
  interrupt capture.

- **gui.py** — Search bar added to the capture list header. Filters the
  visible list in real time as you type; searches the current active
  session when live, or the selected browse session when reviewing history.
  ✕ button clears the search and restores the normal view.

- **gui.py** — Per-row delete wired up: the right-click "Delete last
  capture" menu item now works. Shows a confirmation dialog with a preview
  of the text before deleting. Was stubbed in 0.3.5.

- **gui.py** — Settings panel expanded: auto-export controls added
  (every-N spinbox + file path entry with browse button). Panel height
  increased to 460px to accommodate new section.

## 0.3.5 — GUI redesign: MainbyteLabs theme + five feature improvements

- **gui.py** — Full visual redesign: MainbyteLabs dark palette (`#0D0D0D`
  background, `#00FF41` green accent, monospace typography throughout).
  Uses `ttkthemes` (`equilux` base) with manual style overrides applied
  via `ttk.Style`; falls back to plain `tk.Tk()` gracefully if
  `ttkthemes` is not installed.
- **gui.py** — Session history browser: combobox lists all past sessions
  from `store.sessions()`. Selecting one renders its captures in the
  preview list. Includes Refresh and Export buttons scoped to the
  selected session — no active capture session required.
- **gui.py** — Per-capture right-click context menu on the capture list:
  Copy text, Tag as important/question/followup, Delete last (Delete
  is stubbed with a clear "not implemented" message pending a
  `storage.py` per-row delete addition).
- **gui.py** — Live capture counter and elapsed session time displayed
  in the status bar right side (`N captures  HH:MM:SS`), updating on
  the existing 100ms drain loop.
- **gui.py** — Custom tag input field: text entry + Tag button alongside
  the three quick-tag buttons. Accepts Enter key. Clears on apply.
- **gui.py** — Settings panel (gear button, top right): configures
  entries shown in list, preview characters, min capture length, and
  merge window seconds. Writes back to `config.json` via `save_config()`
  on Save & Close. Changes apply immediately to the preview.

## 0.3.4 — four logic bugs fixed (QA pass)

- **watcher_core.py** — Wayland `_run_wayland()`: when `wl-paste --watch` exits
  for any reason other than the binary being missing (e.g., an older `wl-clipboard`
  that doesn't support `--watch`), the watcher thread was silently exiting instead
  of falling back to polling. Fixed: after the `--watch` loop exits and the stop
  event is not set, the method now logs a message and calls `_run_wayland_polling()`
  so capture continues.
- **gui.py** — `stop()`: the Export button was never disabled on stop, and
  `self.session` was never cleared. After stopping, Export was callable on a
  closed store. Fixed: `export_btn` is now disabled on stop, and `self.session`
  is set to `None` so the guard in `export()` works as intended.
- **pyproject.toml** — `requires-python = ">=3.9"` was missing. pip would attempt
  installation on any Python version. Added.
- **cli.py** — `cmd_tag`, `cmd_sessions`, `cmd_export`: `store.close()` was not
  called if an exception was raised mid-operation, leaving the SQLite connection
  and WAL files open. Wrapped all three in `try/finally`.

## 0.3.3 — GUI needs python3-tk, which install.sh never installed

Confirmed on real hardware: after 0.3.2 fixed the pip/evdev bugs, the
package installed cleanly, `highlight-scraper start` worked, but
`highlight-scraper-gui` failed with `ModuleNotFoundError: No module
named 'tkinter'`.

- `tkinter` isn't part of Python's standard library on Debian/Ubuntu —
  it ships as the separate `python3-tk` apt package, and a venv doesn't
  get it just by existing (a venv shares the base interpreter's stdlib,
  but `tkinter` was never in it to share). `install.sh` never installed
  it. Added `python3-tk` to both the X11 and Wayland package lists, and
  to the manual-install instructions in the README.
- The CLI and tray front ends don't need `tkinter` — only
  `highlight-scraper-gui` does, which is why `start`/`status`/etc. all
  worked fine before this fix.

## 0.3.2 — install.sh actually installs, on a real machine

Both bugs below only showed up running `install.sh` on real hardware —
this sandbox's network restrictions meant I'd never actually run it end
to end before shipping it. Fixed against the real error output:

- `install.sh` called a bare `pip`, which doesn't exist on Mint (only
  `pip3`/`python3 -m pip` do). Switched every pip invocation to
  `python3 -m pip`, which works regardless of what's aliased and
  whether or not you're inside a venv.
- `pynput` pulls in `evdev` as a Linux dependency, which compiles a C
  extension against `Python.h`. `install.sh` never installed the
  package that provides it. Added `python3-dev` and `build-essential`
  to the apt install list.
- Also quoted `.[all]` in the pip call so the shell doesn't try to
  glob-expand the brackets under stricter shell settings.

## 0.3.1 — the Xfixes backend is now actually verified

- Fixed `watcher_core.py`'s `_run_x11_xfixes()`: the registration call was
  `root.xfixes_select_selection_input(...)`, a method that doesn't exist on
  this python-xlib build — it silently threw and every session fell back to
  polling. Found and fixed by having the person running it install
  `python3-xlib`/`xclip`, run a standalone reproduction script, and
  introspect the actual installed library (`dir(xfixes)`,
  `inspect.signature`) to find the real call: `xfixes.select_selection_input`
  is a free function, not a bound Window method, on this python-xlib
  version — called as `xfixes.select_selection_input(root, root, PRIMARY,
  mask)`.
- Confirmed working end-to-end against a live X server (Linux Mint/Cinnamon,
  X11): two independent highlight-and-capture rounds, both correct.
- This is the one thing every earlier version of this README flagged as
  "written from documented patterns, never run against a live X server."
  It's no longer a caveat — it was wrong on the first try, exactly the kind
  of bug that caveat existed to warn about, and it's now fixed and verified
  rather than just asserted.

## 0.3.0 — packaging and reliability

- Restructured into a real pip-installable package (`src/highlight_scraper/`,
  `pyproject.toml`, console scripts `highlight-scraper` / `highlight-scraper-gui`
  / `highlight-scraper-tray`) instead of a folder of scripts you `cd` into.
- Added a real pytest suite (`tests/`) covering config, storage, export, and
  session-manager logic — 29 tests, all passing. This is the actual gap between
  "the AI ran some manual asserts once" and software you can trust after a change.
- Added highlight-merging: dragging a mouse selection fires many intermediate
  selection-changed events. Previously each one became its own database row.
  Now, if a new highlight is an extension/shrink of the last one within
  `merge_window_seconds` (default 2s), it updates that row in place instead —
  tags and source attribution on the original are preserved.
- `start` now detects and self-heals a stale PID file (process crashed without
  cleaning up) instead of permanently refusing to start until a manual `stop`.
- Added `install.sh`: detects X11/Wayland, installs the right system packages,
  installs the Python package with extras, in one command.
- Added `LICENSE` (MIT) and this changelog.

## 0.2.0 — SQLite, sessions, tags, tray

- Replaced the flat per-project JSONL file with one SQLite database, rows
  tagged by session name — supports cross-session queries and a `sessions`
  listing that JSONL-per-folder couldn't.
- Added a privacy exclude-list: highlights from configured apps (password
  managers by default) are never stored.
- Added `cli.py tag`, `sessions`, `export --format md|csv|json`.
- Added `tray.py`, a system tray front end.
- Added `hotkeys.py`: Ctrl+Alt+1/2/3 to tag the last capture without switching
  windows.
- Source-window attribution switched from raw X11/EWMH calls to `xdotool`.

## 0.1.0 — first working version

- `watcher_core.py`: watches the X11 PRIMARY selection (Xfixes event-driven,
  falling back to xclip polling), with a Wayland path via `wl-paste --watch`.
- `paste_on_hold.py`: left-click-and-hold to paste the current selection —
  an accessibility gesture standing in for a working middle-click.
- CLI and GUI front ends, flat text-file log.
