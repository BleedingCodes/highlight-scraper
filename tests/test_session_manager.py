"""
Tests for session_manager.py: the filtering rules every front end
(cli.py, gui.py, tray.py) relies on. The privacy exclude-list test in
particular is not a nice-to-have — it's what stops this tool from
silently logging your password manager.

These call session._handle() directly rather than session.start(),
because start() launches the real X11/Wayland watcher — not available
in a test environment, and not what these tests are about anyway.
"""

import highlight_scraper.session_manager as session_manager
from highlight_scraper.session_manager import CaptureSession


def _session(tmp_path, **config_overrides):
    config = {
        "min_length": 3,
        "excluded_apps": ["keepassxc", "bitwarden"],
        "merge_window_seconds": 2.0,
        **config_overrides,
    }
    return CaptureSession(tmp_path / "captures.db", "test-session", config)


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_min_length_filter_skips_short_highlights(tmp_path):
    session = _session(tmp_path, min_length=5)
    received = []
    session.listeners.append(received.append)

    session._handle("hi")

    assert received == []
    session.store.close()


def test_normal_highlight_is_captured(tmp_path):
    session = _session(tmp_path)
    received = []
    session.listeners.append(received.append)

    session._handle("A real highlighted sentence.")

    assert len(received) == 1
    assert received[0].text == "A real highlighted sentence."
    session.store.close()


def test_excluded_app_privacy_filter_blocks_capture(tmp_path, monkeypatch):
    session = _session(tmp_path, excluded_apps=["keepassxc"])
    received = []
    session.listeners.append(received.append)

    monkeypatch.setattr(session_manager, "get_active_window_info",
                         lambda: ("Vault - KeePassXC", "keepassxc"))

    session._handle("my secret password is hunter2")

    assert received == [], "a highlight from an excluded app must never be stored or emitted"
    assert session.store.query(session="test-session") == []
    session.store.close()


def test_excluded_app_match_is_case_insensitive(tmp_path, monkeypatch):
    session = _session(tmp_path, excluded_apps=["keepassxc"])
    monkeypatch.setattr(session_manager, "get_active_window_info",
                         lambda: ("Vault", "KeePassXC"))

    session._handle("should still be blocked")

    assert session.store.query(session="test-session") == []
    session.store.close()


def test_pause_blocks_capture_until_resumed(tmp_path):
    session = _session(tmp_path)
    received = []
    session.listeners.append(received.append)

    assert session.toggle_pause() is True
    session._handle("should be ignored while paused")
    assert received == []

    assert session.toggle_pause() is False
    session._handle("should be captured now")
    assert len(received) == 1
    session.store.close()


def test_tag_last_via_session(tmp_path):
    session = _session(tmp_path)
    session._handle("something worth tagging")

    row_id = session.tag_last("important")

    assert row_id is not None
    assert session.store.query(session="test-session")[0].tag == "important"
    session.store.close()


def test_extending_a_highlight_merges_into_one_row(tmp_path, monkeypatch):
    session = _session(tmp_path)
    clock = _FakeClock()
    monkeypatch.setattr(session_manager.time, "time", clock.time)

    session._handle("The transformer")
    clock.advance(0.5)  # well within the merge window
    session._handle("The transformer architecture")

    rows = session.store.query(session="test-session")
    assert len(rows) == 1, "extending the same highlight should update one row, not add another"
    assert rows[0].text == "The transformer architecture"
    session.store.close()


def test_shrinking_a_highlight_also_merges(tmp_path, monkeypatch):
    session = _session(tmp_path)
    clock = _FakeClock()
    monkeypatch.setattr(session_manager.time, "time", clock.time)

    session._handle("The transformer architecture eschews recurrence")
    clock.advance(0.5)
    session._handle("The transformer architecture")  # backed up the drag

    rows = session.store.query(session="test-session")
    assert len(rows) == 1
    assert rows[0].text == "The transformer architecture"
    session.store.close()


def test_unrelated_highlight_after_merge_window_is_a_new_row(tmp_path, monkeypatch):
    session = _session(tmp_path)
    clock = _FakeClock()
    monkeypatch.setattr(session_manager.time, "time", clock.time)

    session._handle("First sentence entirely.")
    clock.advance(5.0)  # past the 2s merge window
    session._handle("A totally different sentence.")

    rows = session.store.query(session="test-session")
    assert len(rows) == 2
    session.store.close()


def test_unrelated_highlight_within_window_is_still_a_new_row(tmp_path, monkeypatch):
    """Being within the time window isn't enough on its own — the text
    also has to actually look like an extension of the previous one."""
    session = _session(tmp_path)
    clock = _FakeClock()
    monkeypatch.setattr(session_manager.time, "time", clock.time)

    session._handle("The transformer architecture")
    clock.advance(0.2)
    session._handle("A completely unrelated sentence about cats.")

    rows = session.store.query(session="test-session")
    assert len(rows) == 2
    session.store.close()


def test_merged_capture_preserves_existing_tag(tmp_path, monkeypatch):
    session = _session(tmp_path)
    clock = _FakeClock()
    monkeypatch.setattr(session_manager.time, "time", clock.time)

    session._handle("The transformer")
    session.tag_last("key-finding")
    clock.advance(0.3)
    session._handle("The transformer architecture eschews recurrence")

    rows = session.store.query(session="test-session")
    assert len(rows) == 1
    assert rows[0].tag == "key-finding", "extending a tagged highlight must not drop the tag"
    session.store.close()


def test_broken_listener_does_not_break_capture(tmp_path):
    session = _session(tmp_path)

    def bad_listener(row):
        raise RuntimeError("a UI bug")

    good_received = []
    session.listeners.append(bad_listener)
    session.listeners.append(good_received.append)

    session._handle("this should still get captured")

    assert len(good_received) == 1
    assert len(session.store.query(session="test-session")) == 1
    session.store.close()
