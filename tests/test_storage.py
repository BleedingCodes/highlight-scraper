"""
Tests for storage.py's CaptureStore: the actual database layer everything
else depends on. If these break, nothing else can be trusted.
"""

from highlight_scraper.storage import CaptureStore


def _store(tmp_path):
    return CaptureStore(tmp_path / "captures.db")


def test_add_capture_returns_and_persists_a_row(tmp_path):
    store = _store(tmp_path)
    row = store.add_capture("hello world", session="s1",
                             source_window="Term", source_app="xterm")

    assert row.id is not None
    assert row.text == "hello world"
    assert row.tag is None

    fetched = store.query(session="s1")
    assert len(fetched) == 1
    assert fetched[0].id == row.id
    store.close()


def test_set_tag_for_last_only_touches_most_recent(tmp_path):
    store = _store(tmp_path)
    first = store.add_capture("first", session="s1")
    second = store.add_capture("second", session="s1")

    tagged_id = store.set_tag_for_last("important", session="s1")

    assert tagged_id == second.id
    rows = {r.id: r for r in store.query(session="s1")}
    assert rows[second.id].tag == "important"
    assert rows[first.id].tag is None
    store.close()


def test_set_tag_for_last_is_scoped_per_session(tmp_path):
    store = _store(tmp_path)
    store.add_capture("in session A", session="A")
    b_row = store.add_capture("in session B", session="B")

    # Tagging "the last capture in session A" should not touch session B's
    # row even though it's the most recent capture overall.
    tagged_id = store.set_tag_for_last("flag", session="A")
    row_a = store.query(session="A")[0]
    row_b = store.query(session="B")[0]

    assert row_a.tag == "flag"
    assert row_b.tag is None
    assert row_b.id == b_row.id
    store.close()


def test_set_tag_for_last_returns_none_when_nothing_to_tag(tmp_path):
    store = _store(tmp_path)
    assert store.set_tag_for_last("x", session="empty-session") is None
    store.close()


def test_update_text_for_last_preserves_source_and_tag(tmp_path):
    store = _store(tmp_path)
    store.add_capture("The transformer", session="s1",
                       source_window="paper.pdf", source_app="okular")
    store.set_tag_for_last("key-finding", session="s1")

    updated = store.update_text_for_last("The transformer architecture", session="s1")

    assert updated is not None
    assert updated.text == "The transformer architecture"
    assert updated.tag == "key-finding", "extending a highlight must not lose its tag"
    assert updated.source_app == "okular"

    rows = store.query(session="s1")
    assert len(rows) == 1, "the extension should update the row in place, not add a new one"
    store.close()


def test_sessions_lists_counts_and_time_range(tmp_path):
    store = _store(tmp_path)
    store.add_capture("a", session="proj1")
    store.add_capture("b", session="proj1")
    store.add_capture("c", session="proj2")

    sessions = {name: count for name, count, _, _ in store.sessions()}

    assert sessions["proj1"] == 2
    assert sessions["proj2"] == 1
    store.close()


def test_query_limit_and_ordering(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.add_capture(f"item {i}", session="s1")

    rows = store.query(session="s1", limit=2)

    assert len(rows) == 2
    assert rows[0].text == "item 4", "query() returns newest first"
    store.close()
