"""
Tests for export.py: the three output formats a researcher actually
hands to someone else, so they'd better be right.
"""

import csv
import json

import pytest

from highlight_scraper import export as exporters
from highlight_scraper.storage import CaptureStore


def _seeded_store(tmp_path):
    store = CaptureStore(tmp_path / "captures.db")
    store.add_capture("First finding", session="proj", source_window="p1", source_app="okular")
    second = store.add_capture("Second finding", session="proj", source_window="p1", source_app="okular")
    store.set_tag_for_last("important", session="proj")
    return store, second


def test_export_markdown_includes_text_source_and_tag(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.md"

    exporters.export_markdown(store, "proj", out)
    content = out.read_text()

    assert "First finding" in content
    assert "Second finding" in content
    assert "important" in content
    assert "okular" in content
    store.close()


def test_export_csv_has_correct_header_and_row_count(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.csv"

    exporters.export_csv(store, "proj", out)

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["id", "captured_at", "session", "source_app", "source_window", "tag", "text"]
    assert len(rows) == 3  # header + 2 captures
    store.close()


def test_export_json_round_trips_all_fields(tmp_path):
    store, second = _seeded_store(tmp_path)
    out = tmp_path / "out.json"

    exporters.export_json(store, "proj", out)
    data = json.loads(out.read_text())

    assert len(data) == 2
    tagged = next(row for row in data if row["id"] == second.id)
    assert tagged["tag"] == "important"
    assert tagged["text"] == "Second finding"
    store.close()


def test_export_with_no_session_covers_all_sessions(tmp_path):
    store = CaptureStore(tmp_path / "captures.db")
    store.add_capture("from A", session="A")
    store.add_capture("from B", session="B")
    out = tmp_path / "all.json"

    exporters.export_json(store, None, out)
    data = json.loads(out.read_text())

    assert {row["session"] for row in data} == {"A", "B"}
    store.close()


# --- overwrite guard tests ---

def test_export_markdown_refuses_to_overwrite_by_default(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("existing content")

    with pytest.raises(FileExistsError):
        exporters.export_markdown(store, "proj", out)

    assert out.read_text() == "existing content"
    store.close()


def test_export_csv_refuses_to_overwrite_by_default(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.csv"
    out.write_text("existing content")

    with pytest.raises(FileExistsError):
        exporters.export_csv(store, "proj", out)

    assert out.read_text() == "existing content"
    store.close()


def test_export_json_refuses_to_overwrite_by_default(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.json"
    out.write_text("existing content")

    with pytest.raises(FileExistsError):
        exporters.export_json(store, "proj", out)

    assert out.read_text() == "existing content"
    store.close()


def test_export_markdown_force_overwrites(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("old content")

    exporters.export_markdown(store, "proj", out, force=True)

    content = out.read_text()
    assert "First finding" in content
    assert "old content" not in content
    store.close()


def test_export_json_force_overwrites(tmp_path):
    store, _ = _seeded_store(tmp_path)
    out = tmp_path / "out.json"
    out.write_text("old content")

    exporters.export_json(store, "proj", out, force=True)

    data = json.loads(out.read_text())
    assert len(data) == 2
    store.close()
