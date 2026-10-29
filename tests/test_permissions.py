"""
Regression tests for audit finding 5: capture data is sensitive
(unencrypted arbitrary highlighted text), so files must be created
owner-only rather than inheriting the process umask.
"""

import os
import stat

import pytest

from highlight_scraper.storage import CaptureStore


@pytest.mark.skipif(not hasattr(os, "chmod"), reason="POSIX-only permission semantics")
def test_capture_database_created_owner_only(tmp_path):
    store = CaptureStore(tmp_path / "captures.db")

    mode = stat.S_IMODE(os.stat(store.db_path).st_mode)
    assert mode == 0o600, "the capture database must be created 0600, not umask-derived"

    data_dir_mode = stat.S_IMODE(os.stat(store.db_path.parent).st_mode)
    assert data_dir_mode == 0o700, "the app-owned data directory must be 0700"

    store.close()


@pytest.mark.skipif(not hasattr(os, "chmod"), reason="POSIX-only permission semantics")
def test_capture_database_tightened_on_existing_store(tmp_path):
    """A DB created by an older version (mode 0644) must be tightened when
    a new CaptureStore opens it — not just for freshly created files."""
    db = tmp_path / "captures.db"
    probe = CaptureStore(db)  # let the tool create a valid store first
    probe.close()
    os.chmod(db, 0o644)

    store = CaptureStore(db)

    mode = stat.S_IMODE(os.stat(db).st_mode)
    assert mode == 0o600, "pre-existing stores must be re-tightened to 0600"
    store.close()
