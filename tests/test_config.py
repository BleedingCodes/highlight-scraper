"""
Tests for config.py: defaults get created on first load, and loading an
older/partial config file merges in any new default keys without losing
what the user already changed.
"""

from highlight_scraper import config


def _point_config_at(monkeypatch, tmp_path):
    cfg_dir = tmp_path / ".config" / "highlight_scraper"
    cfg_path = cfg_dir / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    return cfg_path


def test_load_config_creates_file_with_defaults(tmp_path, monkeypatch):
    cfg_path = _point_config_at(monkeypatch, tmp_path)
    assert not cfg_path.exists()

    cfg = config.load_config()

    assert cfg_path.exists()
    for key in config.DEFAULTS:
        assert key in cfg


def test_load_config_preserves_user_edits_and_adds_new_keys(tmp_path, monkeypatch):
    cfg_path = _point_config_at(monkeypatch, tmp_path)
    cfg_path.parent.mkdir(parents=True)
    # Simulate an older config on disk that's missing a newer default key
    # and has a user-customized value for an existing one.
    partial = {k: v for k, v in config.DEFAULTS.items() if k != "min_length"}
    partial["hold_seconds"] = 0.9  # the user's own customization
    import json
    cfg_path.write_text(json.dumps(partial))

    cfg = config.load_config()

    assert cfg["hold_seconds"] == 0.9, "user's customized value must survive a reload"
    assert cfg["min_length"] == config.DEFAULTS["min_length"], "missing keys should be backfilled"


def test_load_config_does_not_overwrite_corrupt_file_with_defaults(tmp_path, monkeypatch, capsys):
    """Regression for audit finding 4: a corrupt (e.g. hand-edited, torn
    write) config used to be silently replaced with pure defaults, wiping
    the user's privacy exclude list. The corrupt file must be preserved,
    backed up, and defaults used only in memory."""
    cfg_path = _point_config_at(monkeypatch, tmp_path)
    cfg_path.parent.mkdir(parents=True)
    corrupt_text = '{\n "excluded_apps": ["mybank"],\n "min_length": 10,\n'  # syntax error
    cfg_path.write_text(corrupt_text)

    cfg = config.load_config()

    # file on disk untouched
    assert cfg_path.read_text() == corrupt_text, "a corrupt config must not be overwritten"
    # a timestamped backup exists
    backups = list(cfg_path.parent.glob("config.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == corrupt_text
    # defaults are served in memory, and the user is warned
    assert cfg["min_length"] == config.DEFAULTS["min_length"]
    assert "corrupt" in capsys.readouterr().err.lower()
    # excluded_apps falls back to the default list (mybank is NOT auto-added)
    assert cfg["excluded_apps"] == config.DEFAULTS["excluded_apps"]


def test_load_config_handles_non_object_json(tmp_path, monkeypatch, capsys):
    """Regression for reviewer finding N2: valid-but-non-object JSON (e.g.
    `["not","a","dict"]`) used to crash load_config with a TypeError and
    take every front end down at startup. Treat it as corrupt."""
    cfg_path = _point_config_at(monkeypatch, tmp_path)
    cfg_path.parent.mkdir(parents=True)
    bad_text = '["not", "a", "dict"]'
    cfg_path.write_text(bad_text)

    cfg = config.load_config()  # must not raise

    assert cfg["min_length"] == config.DEFAULTS["min_length"]
    assert cfg_path.read_text() == bad_text, "the non-object file must not be overwritten"
    assert "corrupt" in capsys.readouterr().err.lower()
    assert len(list(cfg_path.parent.glob("config.json.corrupt-*"))) == 1
