"""
session_manager.py — ties the raw selection watcher to storage, source
attribution, a privacy exclude-list/pause switch, and highlight-merging.

This is what cli.py, gui.py, and tray.py all build on top of, instead
of each one wrapping SelectionWatcher separately. That way the filtering
rules (exclude list, minimum length, pause, merge window) only have to
be correct in one place.

Merging: dragging a mouse selection fires many intermediate
selection-changed events, not one. Without merging, every one of those
becomes its own row. If the new text is a superset/subset of the last
capture and it happens within merge_window_seconds, we update that row
in place instead of inserting a new one.

0.4.0 additions:
  - _capture_count tracked for auto-export trigger
  - auto-export: every N captures, export to a Markdown file
    (configured via config keys: auto_export_every, auto_export_path)
"""

import threading
import time
from pathlib import Path

from highlight_scraper.source_info import get_active_window_info
from highlight_scraper.storage import CaptureStore
from highlight_scraper.watcher_core import SelectionWatcher


def _looks_like_extension(old_text: str, new_text: str) -> bool:
    """True if new_text is the same highlight just grown or shrunk, not a new one."""
    if not old_text or not new_text:
        return False
    return old_text in new_text or new_text in old_text


class CaptureSession:
    def __init__(self, db_path, session_name: str, config: dict):
        self.session_name = session_name
        self.config = config
        self.store = CaptureStore(db_path)
        self.paused = False
        self.listeners = []  # callables(Capture) -> None, for UI updates
        self._lock = threading.Lock()
        self._last_text = None
        self._last_capture_time = 0.0

        # 0.4.0 — auto-export counter
        self._capture_count = 0

        self.watcher = SelectionWatcher(
            on_change=self._handle,
            poll_interval=config.get("poll_interval", 0.3),
        )

    def start(self):
        self.watcher.start()

    def stop(self):
        self.watcher.stop()
        self.store.close()

    def toggle_pause(self) -> bool:
        with self._lock:
            self.paused = not self.paused
        return self.paused

    def tag_last(self, tag: str):
        return self.store.set_tag_for_last(tag, session=self.session_name)

    def _handle(self, text: str):
        if self.paused:
            return

        if len(text.strip()) < self.config.get("min_length", 0):
            return

        window, app = get_active_window_info()

        excluded = self.config.get("excluded_apps", [])
        if app and any(pattern.lower() in app.lower() for pattern in excluded):
            return

        now = time.time()
        merge_window = self.config.get("merge_window_seconds", 2.0)
        with self._lock:
            is_extension = (
                self._last_text is not None
                and now - self._last_capture_time <= merge_window
                and _looks_like_extension(self._last_text, text)
            )
            self._last_text = text
            self._last_capture_time = now

        if is_extension:
            row = self.store.update_text_for_last(text, session=self.session_name)
        else:
            row = self.store.add_capture(
                text=text, session=self.session_name,
                source_window=window, source_app=app,
            )

        if row is None:
            return  # broken merge — don't crash capture

        # 0.4.0 — increment counter and trigger auto-export if configured
        self._capture_count += 1
        self._maybe_auto_export()

        for callback in list(self.listeners):
            try:
                callback(row)
            except Exception:
                pass  # a broken UI listener shouldn't take down capture

    # ── 0.4.0: auto-export ───────────────────────────────────────────────────

    def _maybe_auto_export(self) -> None:
        """
        If auto_export_every is set in config and the capture count is a
        multiple of that number, export the current session to Markdown.

        Config keys:
            auto_export_every  int   Number of captures between exports.
                                     0 or missing = disabled.
            auto_export_path   str   Output file path. Supports ~ expansion.
                                     Default: ~/highlights_<session>.md
        """
        every = self.config.get("auto_export_every", 0)
        if not every or every <= 0:
            return
        if self._capture_count % every != 0:
            return

        # Import here to avoid circular imports at module load time
        from highlight_scraper import export as exporters

        raw_path = self.config.get(
            "auto_export_path",
            str(Path.home() / f"highlights_{self.session_name}.md"),
        )
        out_path = str(Path(raw_path).expanduser())

        try:
            exporters.export_markdown(self.store, self.session_name, out_path)
        except Exception:
            pass  # auto-export failure must never interrupt capture
