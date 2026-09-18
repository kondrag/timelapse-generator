"""Tests for automatic night high-res YouTube uploads."""

from pathlib import Path

from timelapse_generator.config.settings import (
    NightUploadSettings,
    Settings,
    settings,
)


def test_night_upload_defaults():
    cfg = NightUploadSettings()
    assert cfg.enabled is True
    assert cfg.kp_threshold == 4.0
    assert cfg.archive_dir == Path("/var/local/timelapse")
    assert cfg.state_file == Path(
        "~/.local/state/timelapse-generator/night_uploads.json"
    )
    assert (cfg.latitude, cfg.longitude) == (45.1666, -90.8076)
    assert cfg.timezone == "America/Chicago"


def test_settings_parse_night_upload_section():
    s = Settings(
        **{"youtube": {"night_upload": {"enabled": False, "kp_threshold": 5.5}}}
    )
    assert s.youtube.night_upload.enabled is False
    assert s.youtube.night_upload.kp_threshold == 5.5


def test_repo_config_yaml_has_night_upload():
    s = Settings.from_file(Path(__file__).parents[1] / "config.yaml")
    assert s.youtube.night_upload.enabled is True
    assert s.youtube.night_upload.kp_threshold == 4.0
    assert str(s.youtube.night_upload.archive_dir) == "/var/local/timelapse"
    assert (
        str(s.youtube.night_upload.state_file)
        == "~/.local/state/timelapse-generator/night_uploads.json"
    )
    assert (s.youtube.night_upload.latitude, s.youtube.night_upload.longitude) == (
        45.1666,
        -90.8076,
    )
    assert s.youtube.night_upload.timezone == "America/Chicago"
