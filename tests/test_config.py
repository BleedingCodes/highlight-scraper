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
