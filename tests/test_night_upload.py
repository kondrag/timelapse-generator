"""Tests for automatic night high-res YouTube uploads."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from timelapse_generator.config.settings import (
    NightUploadSettings,
    Settings,
    settings,
)
from timelapse_generator.youtube.night_upload import (
    KpDataError,
    find_night_video,
    load_kp_series,
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


NOAA_SAMPLE = [
    ["time_tag", "Kp", "a_running", "station_count"],
    ["2026-09-06 00:00:00.000", "1.33", "6", "8"],
    ["2026-09-06 03:00:00.000", "2.67", "12", "8"],
]


def test_find_night_video_returns_expected_path(tmp_path):
    day_dir = tmp_path / "20260916"
    day_dir.mkdir()
    video = day_dir / "AuroraCam_20260916_2560x1440.mp4"
    video.write_bytes(b"x")
    assert find_night_video(date(2026, 9, 16), tmp_path) == video


def test_find_night_video_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_night_video(date(2026, 9, 16), tmp_path)


def test_find_night_video_empty_file_raises(tmp_path):
    day_dir = tmp_path / "20260916"
    day_dir.mkdir()
    (day_dir / "AuroraCam_20260916_2560x1440.mp4").write_bytes(b"")
    with pytest.raises(FileNotFoundError):
        find_night_video(date(2026, 9, 16), tmp_path)


def test_load_kp_series_parses_noaa_format(tmp_path):
    p = tmp_path / "k-index_20260906.json"
    p.write_text(json.dumps(NOAA_SAMPLE))
    series = load_kp_series(p)
    assert series == [
        (datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc), 1.33),
        (datetime(2026, 9, 6, 3, 0, tzinfo=timezone.utc), 2.67),
    ]


def test_load_kp_series_missing_file_raises(tmp_path):
    with pytest.raises(KpDataError):
        load_kp_series(tmp_path / "nope.json")


def test_load_kp_series_corrupt_json_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text("{not json")
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_short_file_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps([["time_tag", "Kp", "a_running", "station_count"]]))
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_non_numeric_kp_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(
        json.dumps(
            [
                ["time_tag", "Kp", "a_running", "station_count"],
                ["2026-09-06 00:00:00.000", "quiet", "6", "8"],
            ]
        )
    )
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_bad_timestamp_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(
        json.dumps(
            [
                ["time_tag", "Kp", "a_running", "station_count"],
                ["2026-09-06T00:00:00Z", "2.0", "6", "8"],
            ]
        )
    )
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_short_row_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(
        json.dumps(
            [
                ["time_tag", "Kp", "a_running", "station_count"],
                ["2026-09-06 00:00:00.000"],
            ]
        )
    )
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_bad_header_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(
        json.dumps([["timestamp", "value"], ["2026-09-06 00:00:00.000", "2.0"]])
    )
    with pytest.raises(KpDataError):
        load_kp_series(p)
