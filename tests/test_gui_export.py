"""
Regression tests for audit finding 6: the GUI export path used to call
the exporter without force=True, so choosing an existing file in the Tk
save dialog (which already confirms the overwrite) aborted with an
unhandled FileExistsError. The core write path is now module-level and
always passes force=True — testable without a real Tk root.
"""

import json

from highlight_scraper import gui
from highlight_scraper.storage import CaptureStore


def _store_with_captures(tmp_path):
    store = CaptureStore(tmp_path / "captures.db")
    store.add_capture("first", session="gui-session", source_app="app-a")
    store.add_capture("second", session="gui-session", source_app="app-a")
    return store


def test_export_to_writes_markdown(tmp_path):
    store = _store_with_captures(tmp_path)
    out = tmp_path / "out.md"

    gui._export_to(store, "gui-session", str(out))

    content = out.read_text()
    assert "first" in content and "second" in content
    store.close()


def test_export_to_replaces_an_existing_file(tmp_path):
    """The core fix: the exporter must not raise FileExistsError for an
    existing target — the save dialog already obtained the user's OK."""
    store = _store_with_captures(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("old export from yesterday")

    gui._export_to(store, "gui-session", str(out))  # must not raise

    content = out.read_text()
    assert "old export from yesterday" not in content
    assert "second" in content
    store.close()


def test_export_to_respects_extension(tmp_path):
    store = _store_with_captures(tmp_path)
    out = tmp_path / "out.json"

    gui._export_to(store, "gui-session", str(out))

    data = json.loads(out.read_text())
    assert len(data) == 2, "the .json extension must select the JSON exporter"
    store.close()
