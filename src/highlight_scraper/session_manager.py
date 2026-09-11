"""
session_manager.py — ties the raw selection watcher to storage, source
attribution, a privacy exclude-list/pause switch, and highlight-merging.

This is what cli.py, gui.py, and tray.py all build on top of, instead
of each one wrapping SelectionWatcher separately. That way the
filtering rules (exclude list, minimum length, pause, merge window)
only have to be correct in one place — three copies of the same
filtering logic is exactly the kind of thing that quietly drifts out
of sync over time.

Merging: dragging a mouse selection fires many intermediate
selection-changed events, not one — "highlight a sentence" looks like
"highlight 'The', then 'The tr', then 'The transformer', ..." to
watcher_core. Without merging, every one of those becomes its own row.
If the new text is a superset/subset of the last capture (you extended
or backed up the same drag) and it happens within merge_window_seconds,
we update that row in place instead of inserting a new one.
"""

import threading
import time

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
            return  # shouldn't happen, but a broken merge shouldn't crash capture

        for callback in list(self.listeners):
            try:
                callback(row)
            except Exception:
                pass  # a broken UI listener shouldn't be able to take down capture
