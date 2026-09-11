"""
storage.py — SQLite-backed capture store.

WAL mode is turned on so the background capture process can keep
writing while a separate `cli.py tag` / `cli.py export` invocation (a
different process) reads or updates the same file at the same time.
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    session TEXT NOT NULL,
    source_window TEXT,
    source_app TEXT,
    tag TEXT
);
"""


@dataclass
class Capture:
    id: int
    text: str
    captured_at: str
    session: str
    source_window: str
    source_app: str
    tag: str


class CaptureStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()

    def add_capture(self, text, session, source_window=None, source_app=None) -> Capture:
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO captures (text, captured_at, session, source_window, source_app) "
                "VALUES (?, ?, ?, ?, ?)",
                (text, ts, session, source_window, source_app),
            )
            self.conn.commit()
            row_id = cur.lastrowid
        return Capture(row_id, text, ts, session, source_window, source_app, None)

    def update_text_for_last(self, text: str, session: str = None):
        """
        Overwrite the text (and refresh captured_at) of the most recent
        capture, leaving its source/tag alone. Used to merge a highlight
        that's just being extended or shrunk — you dragged further, or
        backed up — into the SAME row instead of inserting a new one per
        pixel of drag. Returns the updated Capture, or None if there was
        nothing to update.
        """
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            if session:
                cur = self.conn.execute(
                    "SELECT id, session, source_window, source_app, tag "
                    "FROM captures WHERE session=? ORDER BY id DESC LIMIT 1",
                    (session,),
                )
            else:
                cur = self.conn.execute(
                    "SELECT id, session, source_window, source_app, tag "
                    "FROM captures ORDER BY id DESC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            row_id, row_session, source_window, source_app, tag = row
            self.conn.execute(
                "UPDATE captures SET text=?, captured_at=? WHERE id=?",
                (text, ts, row_id),
            )
            self.conn.commit()
        return Capture(row_id, text, ts, row_session, source_window, source_app, tag)

    def set_tag_for_last(self, tag: str, session: str = None):
        """Tag the most recent capture (optionally restricted to one session).
        Returns the row id tagged, or None if there was nothing to tag."""
        with self._lock:
            if session:
                cur = self.conn.execute(
                    "SELECT id FROM captures WHERE session=? ORDER BY id DESC LIMIT 1",
                    (session,),
                )
            else:
                cur = self.conn.execute("SELECT id FROM captures ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                return None
            self.conn.execute("UPDATE captures SET tag=? WHERE id=?", (tag, row[0]))
            self.conn.commit()
            return row[0]

    def query(self, session: str = None, limit: int = 200):
        sql = ("SELECT id, text, captured_at, session, source_window, source_app, tag "
               "FROM captures")
        params = []
        if session:
            sql += " WHERE session=?"
            params.append(session)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cur = self.conn.execute(sql, params)
        return [Capture(*row) for row in cur.fetchall()]

    def sessions(self):
        """Returns (name, count, first_timestamp, last_timestamp) per session,
        most recently active first."""
        cur = self.conn.execute(
            "SELECT session, COUNT(*), MIN(captured_at), MAX(captured_at) "
            "FROM captures GROUP BY session ORDER BY MAX(captured_at) DESC"
        )
        return cur.fetchall()

    def close(self):
        self.conn.close()
