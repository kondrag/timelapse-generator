"""Tests for automatic night high-res YouTube uploads."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from timelapse_generator.config.settings import (
    NightUploadSettings,
    Settings,
    settings,
)
from timelapse_generator.youtube import night_upload
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


from timelapse_generator.youtube.night_upload import max_kp_in_window, night_window


def test_night_window_september_ground_truth():
    # Ground truth from tests/test_sun.py: nautical dusk 2026-09-06 was 20:36
    # and nautical dawn 2026-09-07 was 05:26 America/Chicago (CDT = UTC-5).
    start, end = night_window(date(2026, 9, 7))
    assert start.tzinfo == timezone.utc and end.tzinfo == timezone.utc
    assert (start.hour, start.minute) == (1, 36)
    assert start.day == 7  # dusk on 9/6 20:36 CDT is already 9/7 in UTC
    assert (end.hour, end.minute) == (10, 26)
    assert start < end


def test_night_window_winter_longer_than_summer():
    summer_start, summer_end = night_window(date(2026, 6, 21))
    winter_start, winter_end = night_window(date(2026, 12, 21))
    assert (winter_end - winter_start) > (summer_end - summer_start)


def test_night_window_covers_dst_spring_forward():
    # US DST 2026 starts Sunday 2026-03-08. The window for date 3/8 runs from
    # dusk on 3/7 (CST, UTC-6) to dawn on 3/8 (CDT, UTC-5). night_window returns
    # UTC, so offsets are asserted after converting back to local time.
    start, end = night_window(date(2026, 3, 8))
    local = ZoneInfo("America/Chicago")
    assert start.astimezone(local).utcoffset() == timedelta(hours=-6)
    assert end.astimezone(local).utcoffset() == timedelta(hours=-5)
    assert start < end


def test_night_window_honors_observer_overrides():
    start_default, end_default = night_window(date(2026, 9, 7))
    start_far, _ = night_window(
        date(2026, 9, 7), latitude=-41.3, longitude=174.8, tz_name="Pacific/Auckland"
    )
    assert start_far != start_default  # a different observer sees a different night


def test_max_kp_in_window_inclusive_edges():
    window = (
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
    )
    series = [
        (datetime(2026, 9, 7, 9, 59, tzinfo=timezone.utc), 9.0),  # just outside
        (datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc), 3.0),  # at start
        (datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc), 2.5),
        (datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc), 4.0),  # at end
        (datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc), 1.0),  # just outside
    ]
    assert max_kp_in_window(series, window) == 4.0


def test_max_kp_in_window_no_samples_returns_none():
    window = (
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
    )
    assert max_kp_in_window([], window) is None
    assert (
        max_kp_in_window(
            [(datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc), 5.0)], window
        )
        is None
    )


from timelapse_generator.youtube.night_upload import (
    NightUploadResult,
    load_state,
    save_state,
)


def test_load_state_missing_file_returns_empty(tmp_path):
    assert load_state(tmp_path / "state.json") == {}


def test_state_roundtrip(tmp_path):
    state_file = tmp_path / "nested" / "state.json"
    state = {"20260916": {"status": "uploaded", "video_id": "abc123"}}
    save_state(state_file, state)
    assert load_state(state_file) == state


def test_save_state_is_atomic_no_temp_leftovers(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, {})
    save_state(state_file, {"20260916": {"status": "failed"}})
    assert list(tmp_path.iterdir()) == [state_file]


def test_state_record_shape():
    record = night_upload._state_record(
        date(2026, 9, 16), "uploaded", 4.0, max_kp=5.33, video_id="abc", url="u"
    )
    assert record["status"] == "uploaded"
    assert record["video_id"] == "abc"
    assert record["url"] == "u"
    assert record["max_kp"] == 5.33
    assert record["threshold"] == 4.0
    assert record["error"] is None
    assert datetime.fromisoformat(record["timestamp"]).utcoffset() is not None


def test_night_upload_result_defaults():
    r = NightUploadResult(status="no_op")
    assert r.status == "no_op"
    assert r.max_kp is None
    assert r.video_id is None
    assert r.url is None
    assert r.error is None
    assert r.reason is None
    assert r.metadata is None


from timelapse_generator.youtube.night_upload import upload_night_for_date

DAY = date(2026, 9, 16)
DATE_KEY = "20260916"
# The nautical window for 2026-09-16 is ~01:52-10:40 UTC; 06:00 UTC is inside.
IN_WINDOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
OUT_OF_WINDOW = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)


class FakeUploader:
    upload_calls = []

    def __init__(self):
        pass

    def upload_video(self, **kwargs):
        FakeUploader.upload_calls.append(kwargs)
        return {
            "video_id": "abc123",
            "video_url": "https://www.youtube.com/watch?v=abc123",
        }


class FailingUploader(FakeUploader):
    def upload_video(self, **kwargs):
        raise RuntimeError("quotaExceeded")


@pytest.fixture
def configured(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    state_file = tmp_path / "state" / "night_uploads.json"
    monkeypatch.setattr(
        settings.youtube,
        "night_upload",
        NightUploadSettings(archive_dir=archive, state_file=state_file),
    )
    FakeUploader.upload_calls = []
    return archive, state_file


def make_archive(archive, day=DAY, samples=None, kp_bytes=None):
    day_dir = archive / day.strftime("%Y%m%d")
    day_dir.mkdir(parents=True)
    video = day_dir / f"AuroraCam_{day.strftime('%Y%m%d')}_2560x1440.mp4"
    video.write_bytes(b"fake video bytes")
    rows = [["time_tag", "Kp", "a_running", "station_count"]]
    for when, kp in (
        samples if samples is not None else [(IN_WINDOW, 5.33), (OUT_OF_WINDOW, 1.0)]
    ):
        rows.append([when.strftime("%Y-%m-%d %H:%M:%S.%f"), str(kp), "8", "8"])
    (day_dir / f"k-index_{day.strftime('%Y%m%d')}.json").write_text(
        kp_bytes or json.dumps(rows)
    )
    return video


def test_qualified_upload_records_uploaded(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive)
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    result = upload_night_for_date(DAY)

    assert result.status == "uploaded"
    assert result.max_kp == 5.33
    assert result.video_id == "abc123"
    assert result.url == "https://www.youtube.com/watch?v=abc123"
    assert len(FakeUploader.upload_calls) == 1
    call = FakeUploader.upload_calls[0]
    assert call["privacy_status"] == "private"
    assert "Kp" in call["title"]
    entry = load_state(state_file)[DATE_KEY]
    assert entry["status"] == "uploaded"
    assert entry["max_kp"] == 5.33
    assert entry["threshold"] == 4.0
    assert entry["error"] is None


def test_second_run_is_already_done(configured, monkeypatch):
    archive, _ = configured
    make_archive(archive)
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    first = upload_night_for_date(DAY)
    second = upload_night_for_date(DAY)

    assert first.status == "uploaded"
    assert second.status == "already_done"
    assert second.reason == "uploaded"
    assert len(FakeUploader.upload_calls) == 1  # never uploaded twice


def test_low_kp_skips_then_force_uploads(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive, samples=[(IN_WINDOW, 2.67), (OUT_OF_WINDOW, 1.0)])
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    skipped = upload_night_for_date(DAY)
    assert skipped.status == "skipped_low_kp"
    assert skipped.max_kp == 2.67
    assert load_state(state_file)[DATE_KEY]["status"] == "skipped_low_kp"

    rerun = upload_night_for_date(DAY)
    assert rerun.status == "already_done"
    assert rerun.reason == "already_skipped_low_kp"
    assert len(FakeUploader.upload_calls) == 0

    forced = upload_night_for_date(DAY, force=True)
    assert forced.status == "uploaded"
    assert len(FakeUploader.upload_calls) == 1


def test_no_samples_in_window_is_skipped_with_null_kp(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive, samples=[(OUT_OF_WINDOW, 5.33)])
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    result = upload_night_for_date(DAY)

    assert result.status == "skipped_low_kp"
    assert result.max_kp is None
    entry = load_state(state_file)[DATE_KEY]
    assert entry["status"] == "skipped_low_kp"
    assert entry["max_kp"] is None


def test_threshold_override(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive, samples=[(IN_WINDOW, 4.5)])
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    assert upload_night_for_date(DAY, threshold=5.0).status == "skipped_low_kp"
    state_file.unlink()  # fresh state: threshold re-evaluates without a skip record
    assert upload_night_for_date(DAY, threshold=4.0).status == "uploaded"


def test_missing_video_is_quiet_no_op(configured):
    archive, state_file = configured
    result = upload_night_for_date(DAY)
    assert result.status == "no_op"
    assert result.reason == "missing_video"
    assert not state_file.exists()


def test_missing_kp_json_is_quiet_no_op(configured):
    archive, state_file = configured
    day_dir = archive / DATE_KEY
    day_dir.mkdir(parents=True)
    (day_dir / f"AuroraCam_{DATE_KEY}_2560x1440.mp4").write_bytes(b"v")
    result = upload_night_for_date(DAY)
    assert result.status == "no_op"
    assert result.reason == "missing_kp"
    assert not state_file.exists()


def test_malformed_kp_fails_then_force_uploads(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive, kp_bytes=json.dumps([["time_tag", "Kp"], ["oops"]]))
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    failed = upload_night_for_date(DAY)
    assert failed.status == "failed"
    assert failed.error.startswith("bad_kp_data:")
    assert load_state(state_file)[DATE_KEY]["status"] == "failed"

    forced = upload_night_for_date(DAY, force=True)
    assert forced.status == "uploaded"
    assert load_state(state_file)[DATE_KEY]["status"] == "uploaded"


def test_upload_error_records_failed(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive)
    monkeypatch.setattr(night_upload, "YouTubeUploader", FailingUploader)

    result = upload_night_for_date(DAY)

    assert result.status == "failed"
    assert "quotaExceeded" in result.error
    entry = load_state(state_file)[DATE_KEY]
    assert entry["status"] == "failed"
    assert "quotaExceeded" in entry["error"]


def test_dry_run_qualified_mutates_nothing(configured, monkeypatch):
    archive, state_file = configured
    video = make_archive(archive)
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    result = upload_night_for_date(DAY, dry_run=True)

    assert result.status == "dry_run"
    assert result.max_kp == 5.33
    assert result.metadata["title"].startswith("Aurora Timelapse - September 16, 2026")
    assert result.metadata["privacy_status"] == "private"
    assert not state_file.exists()
    assert len(FakeUploader.upload_calls) == 0
    assert video.exists()


def test_disabled_returns_disabled(configured, monkeypatch):
    archive, state_file = configured
    make_archive(archive)
    monkeypatch.setattr(
        settings.youtube,
        "night_upload",
        NightUploadSettings(archive_dir=archive, state_file=state_file, enabled=False),
    )
    result = upload_night_for_date(DAY)
    assert result.status == "disabled"


from click.testing import CliRunner

from timelapse_generator import cli as cli_module
from timelapse_generator.cli import cli as cli_group
from timelapse_generator.youtube.night_upload import parse_date_arg


def test_parse_date_arg_variants():
    assert parse_date_arg(None) == datetime.now().astimezone().date()
    assert parse_date_arg("20260916") == date(2026, 9, 16)
    assert parse_date_arg("2026-09-16") == date(2026, 9, 16)
    with pytest.raises(ValueError):
        parse_date_arg("09/16/2026")
    with pytest.raises(ValueError):
        parse_date_arg("2026091")


def test_cli_uploaded_exit_zero(monkeypatch):
    captured = {}

    def fake(date, dry_run=False, force=False, threshold=None):
        captured.update(date=date, dry_run=dry_run, force=force, threshold=threshold)
        return NightUploadResult(
            status="uploaded",
            max_kp=5.33,
            video_id="abc",
            url="https://www.youtube.com/watch?v=abc",
        )

    monkeypatch.setattr(cli_module, "upload_night_for_date", fake)
    result = CliRunner().invoke(cli_group, ["upload-night", "20260916"])
    assert result.exit_code == 0, result.output
    assert captured["date"] == date(2026, 9, 16)
    assert captured["dry_run"] is False
    assert "abc" in result.output


def test_cli_flags_forwarded(monkeypatch):
    captured = {}

    def fake(date, dry_run=False, force=False, threshold=None):
        captured.update(date=date, dry_run=dry_run, force=force, threshold=threshold)
        return NightUploadResult(status="uploaded")

    monkeypatch.setattr(cli_module, "upload_night_for_date", fake)
    result = CliRunner().invoke(
        cli_group,
        ["upload-night", "2026-09-16", "--dry-run", "--force", "--threshold", "5.5"],
    )
    assert result.exit_code == 0, result.output
    assert captured == {
        "date": date(2026, 9, 16),
        "dry_run": True,
        "force": True,
        "threshold": 5.5,
    }


def test_cli_failed_exits_one(monkeypatch):
    def fake(date, dry_run=False, force=False, threshold=None):
        return NightUploadResult(status="failed", error="boom")

    monkeypatch.setattr(cli_module, "upload_night_for_date", fake)
    result = CliRunner().invoke(cli_group, ["upload-night"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_cli_invalid_date_exits_one():
    result = CliRunner().invoke(cli_group, ["upload-night", "garbage"])
    assert result.exit_code == 1


def test_cli_no_op_and_skipped_exit_zero(monkeypatch):
    cases = [
        (NightUploadResult(status="no_op", reason="missing_video"), "retry"),
        (NightUploadResult(status="skipped_low_kp", max_kp=2.0), "below threshold"),
        (NightUploadResult(status="disabled"), "disabled"),
        (
            NightUploadResult(status="already_done", reason="uploaded"),
            "Already handled",
        ),
    ]
    for stub, needle in cases:
        monkeypatch.setattr(cli_module, "upload_night_for_date", lambda *a, **k: stub)
        result = CliRunner().invoke(cli_group, ["upload-night", "20260916"])
        assert result.exit_code == 0, result.output
        assert needle.lower() in result.output.lower()


def test_cli_dry_run_prints_decision(monkeypatch):
    def fake(date, dry_run=False, force=False, threshold=None):
        assert dry_run is True
        return NightUploadResult(
            status="dry_run",
            max_kp=5.33,
            metadata={
                "title": "Aurora Timelapse - September 16, 2026 (Kp 5.33)",
                "description": "desc",
                "tags": ["timelapse", "aurora"],
                "privacy_status": "private",
            },
        )

    monkeypatch.setattr(cli_module, "upload_night_for_date", fake)
    result = CliRunner().invoke(cli_group, ["upload-night", "20260916", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would upload" in result.output.lower()
    assert "Aurora Timelapse - September 16, 2026" in result.output
    assert "private" in result.output.lower()
