# Night YouTube Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically upload `AuroraCam_<date>_2560x1440.mp4` to YouTube when the night's max Kp >= 4.0, via a 30-minute cron poll plus a manual `timelapse upload-night` CLI command.

**Architecture:** New module `src/timelapse_generator/youtube/night_upload.py` implements the decision pipeline (find video, parse sibling NOAA Kp JSON, compute the nautical night window with astral, gate on max Kp, persist per-date state, delegate to the existing `YouTubeUploader`). A new Click subcommand `upload-night` wraps the orchestrator; a new `scripts/upload_night_cron.sh` polls it under `flock`. Config lives in a new `youtube.night_upload` settings section.

**Tech Stack:** Python >=3.9, pydantic v2 (settings), astral (nautical twilight), click (CLI), pytest (unittest-style functions, `uv run pytest`), bash + flock (cron wrapper). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-17-night-youtube-upload-design.md` (read it first; this plan argues from it).

## Global Constraints

- Python `>=3.9`; no new runtime dependencies (astral, click, pydantic, jinja2 already in `pyproject.toml`).
- Run tests from the repo root with `uv run pytest <args>` (the suite has `--cov` in `addopts`; that works as-is).
- Match existing style: double-quote docstrings, `from ..config.settings import settings` singleton pattern, `get_logger(__name__)`, black line-length 88. Do not reformat existing files.
- State date keys are `YYYYMMDD` strings (e.g. `"20260916"`), matching archive dir names.
- The state file must live OUTSIDE `/var/local/timelapse` (archive dirs are deleted after 30 days).
- Videos uploaded only from `<archive_dir>/<YYYYMMDD>/AuroraCam_<YYYYMMDD>_2560x1440.mp4` — never low-res or CloudCam files.
- Never upload the same date twice: `uploaded` state is never overridden, even by `--force`.
- Exit codes: 0 = uploaded / skipped / clean no-op / dry-run of a qualified or skipped decision; 1 = failure (bad Kp data, upload error, invalid DATE argument, disabled is exit 0).
- NOAA time format: `%Y-%m-%d %H:%M:%S.%f`, UTC. Kp values are decimal strings like `"4.67"`.
- Config defaults: Gilman, WI observer — latitude `45.1666`, longitude `-90.8076`, timezone `America/Chicago`; threshold `4.0`; archive dir `/var/local/timelapse`; state file `~/.local/state/timelapse-generator/night_uploads.json`.

---

### Task 1: Config — `youtube.night_upload` settings section

**Files:**
- Modify: `src/timelapse_generator/config/settings.py` (add `NightUploadSettings` class before `YouTubeSettings`; add field to `YouTubeSettings`)
- Modify: `config.yaml` (add `night_upload:` block under `youtube:`)
- Create: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: existing `Settings`/`YouTubeSettings` pydantic models in `src/timelapse_generator/config/settings.py`.
- Produces: `NightUploadSettings` (pydantic BaseModel) with fields `enabled: bool = True`, `kp_threshold: float = 4.0`, `archive_dir: Path = Path("/var/local/timelapse")`, `state_file: Path = Path("~/.local/state/timelapse-generator/night_uploads.json")`, `latitude: float = 45.1666`, `longitude: float = -90.8076`, `timezone: str = "America/Chicago"`. Accessible everywhere as `settings.youtube.night_upload`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_night_upload.py`:

```python
"""Tests for automatic night high-res YouTube uploads."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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
    assert cfg.state_file == Path("~/.local/state/timelapse-generator/night_uploads.json")
    assert (cfg.latitude, cfg.longitude) == (45.1666, -90.8076)
    assert cfg.timezone == "America/Chicago"


def test_settings_parse_night_upload_section():
    s = Settings(**{"youtube": {"night_upload": {"enabled": False, "kp_threshold": 5.5}}})
    assert s.youtube.night_upload.enabled is False
    assert s.youtube.night_upload.kp_threshold == 5.5


def test_repo_config_yaml_has_night_upload():
    s = Settings.from_file(Path(__file__).parents[1] / "config.yaml")
    assert s.youtube.night_upload.enabled is True
    assert s.youtube.night_upload.kp_threshold == 4.0
    assert str(s.youtube.night_upload.archive_dir) == "/var/local/timelapse"
    assert str(s.youtube.night_upload.state_file) == "~/.local/state/timelapse-generator/night_uploads.json"
    assert (s.youtube.night_upload.latitude, s.youtube.night_upload.longitude) == (45.1666, -90.8076)
    assert s.youtube.night_upload.timezone == "America/Chicago"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'NightUploadSettings'`

- [ ] **Step 3: Add the settings models**

In `src/timelapse_generator/config/settings.py`, insert this class immediately BEFORE `class YouTubeSettings(BaseModel):`:

```python
class NightUploadSettings(BaseModel):
    """Automatic nightly high-res YouTube upload settings."""

    enabled: bool = Field(default=True, description="Enable automatic night uploads")
    kp_threshold: float = Field(
        default=4.0,
        ge=0.0,
        le=9.0,
        description="Minimum max-Kp required during the night window",
    )
    archive_dir: Path = Field(
        default=Path("/var/local/timelapse"),
        description="Timelapse archive root containing <YYYYMMDD> directories",
    )
    state_file: Path = Field(
        default=Path("~/.local/state/timelapse-generator/night_uploads.json"),
        description="Per-date upload state JSON (expanded at use)",
    )
    latitude: float = Field(default=45.1666, ge=-90.0, le=90.0, description="Observer latitude")
    longitude: float = Field(default=-90.8076, ge=-180.0, le=180.0, description="Observer longitude")
    timezone: str = Field(default="America/Chicago", description="Observer IANA timezone name")
```

Inside `class YouTubeSettings(BaseModel):`, add this field after `tags`:

```python
    night_upload: NightUploadSettings = Field(
        default_factory=NightUploadSettings,
        description="Automatic night upload settings",
    )
```

- [ ] **Step 4: Update config.yaml**

In `config.yaml`, inside the `youtube:` section (keys are alphabetical in this file), add the `night_upload:` block between `category_id:` and `privacy_status:`:

```yaml
youtube:
  category_id: '22'
  night_upload:
    archive_dir: /var/local/timelapse
    enabled: true
    kp_threshold: 4.0
    latitude: 45.1666
    longitude: -90.8076
    state_file: ~/.local/state/timelapse-generator/night_uploads.json
    timezone: America/Chicago
  privacy_status: private
  tags:
  - timelapse
  - astrophotography
  - night sky
  upload_enabled: false
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/timelapse_generator/config/settings.py config.yaml tests/test_night_upload.py
git commit -m "Add youtube.night_upload config section"
```

---

### Task 2: Archive inputs — `find_night_video` and `load_kp_series`

**Files:**
- Create: `src/timelapse_generator/youtube/night_upload.py`
- Modify: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `class KpDataError(Exception)` — Kp data missing/short/malformed.
  - `find_night_video(date: date, archive_dir: Path) -> Path` — raises `FileNotFoundError` when absent or empty.
  - `load_kp_series(path: Path) -> list[tuple[datetime, float]]` — raises `KpDataError` on missing/unreadable/short/malformed data; timestamps are UTC-aware.
  - Module constants `HIGH_RES_SUFFIX = "_2560x1440.mp4"` and `NOAA_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"` (used by later tasks/tests).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_night_upload.py`:

```python
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
    p.write_text(json.dumps([
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-09-06 00:00:00.000", "quiet", "6", "8"],
    ]))
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_bad_timestamp_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps([
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-09-06T00:00:00Z", "2.0", "6", "8"],
    ]))
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_short_row_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps([
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-09-06 00:00:00.000"],
    ]))
    with pytest.raises(KpDataError):
        load_kp_series(p)


def test_load_kp_series_bad_header_raises(tmp_path):
    p = tmp_path / "k.json"
    p.write_text(json.dumps([["timestamp", "value"], ["2026-09-06 00:00:00.000", "2.0"]]))
    with pytest.raises(KpDataError):
        load_kp_series(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'KpDataError'`

- [ ] **Step 3: Create the module with the input functions**

Create `src/timelapse_generator/youtube/night_upload.py`:

```python
"""Automatic upload of nightly high-res timelapses, gated on Kp index.

Implements the decision pipeline from
docs/superpowers/specs/2026-09-17-night-youtube-upload-design.md: find the
night high-res video, gate on the max Kp index inside the nautical night
window, persist per-date state, and delegate the upload to YouTubeUploader.
"""

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astral import Depression, LocationInfo
from astral.sun import sun

from ..config.settings import settings
from ..utils.logging import get_logger
from .metadata import MetadataManager
from .uploader import YouTubeUploader

logger = get_logger(__name__)

HIGH_RES_SUFFIX = "_2560x1440.mp4"
NOAA_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


class KpDataError(Exception):
    """Kp index data is missing, truncated, or malformed."""


def find_night_video(date: date, archive_dir: Path) -> Path:
    """Return the night high-res video path for date, or raise FileNotFoundError.

    The video reaches the archive via mv within one filesystem (atomic), so a
    partially-written file cannot be observed; existence + non-zero size is
    sufficient.
    """
    video = (
        Path(archive_dir)
        / date.strftime("%Y%m%d")
        / f"AuroraCam_{date.strftime('%Y%m%d')}{HIGH_RES_SUFFIX}"
    )
    if not video.exists() or video.stat().st_size == 0:
        raise FileNotFoundError(f"Night high-res video not found: {video}")
    return video


def load_kp_series(path: Path) -> List[Tuple[datetime, float]]:
    """Parse a NOAA planetary K index product file into (utc_time, kp) pairs.

    Element 0 is the header row ["time_tag", "Kp", "a_running", "station_count"];
    subsequent rows carry UTC timestamps formatted %Y-%m-%d %H:%M:%S.%f and
    decimal Kp values. Raises KpDataError on missing/short/malformed data.
    """
    try:
        rows = json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise KpDataError(f"Kp file not found: {path}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise KpDataError(f"unreadable Kp file {path}: {exc}") from exc

    if not isinstance(rows, list) or len(rows) < 2:
        raise KpDataError(f"Kp file {path} is not a JSON array with a header and samples")

    header = rows[0]
    if not (isinstance(header, list) and "time_tag" in header and "Kp" in header):
        raise KpDataError(f"Kp file {path} has unexpected header row: {header!r}")

    series: List[Tuple[datetime, float]] = []
    for row in rows[1:]:
        if not isinstance(row, list) or len(row) < 2:
            raise KpDataError(f"Kp file {path} has short row: {row!r}")
        try:
            when = datetime.strptime(str(row[0]), NOAA_TIME_FORMAT).replace(tzinfo=timezone.utc)
            kp = float(row[1])
        except (ValueError, TypeError) as exc:
            raise KpDataError(f"Kp file {path} has malformed row {row!r}: {exc}") from exc
        series.append((when, kp))
    return series
```

Note: the imports of `dataclass`, `timedelta`, `LocationInfo`, `Depression`, `sun`, `settings`, `MetadataManager`, and `YouTubeUploader` are used by Tasks 3-5; if your linter complains before then, leave them in place — they will all be used by the end of Task 5.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS (3 settings + 11 input tests; only new tests matter)

- [ ] **Step 5: Commit**

```bash
git add src/timelapse_generator/youtube/night_upload.py tests/test_night_upload.py
git commit -m "Add night video discovery and NOAA Kp parsing"
```

---

### Task 3: Window math — `night_window` and `max_kp_in_window`

**Files:**
- Modify: `src/timelapse_generator/youtube/night_upload.py` (append functions)
- Modify: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: nothing from other tasks (uses astral directly, mirroring `scripts/sun.py`).
- Produces:
  - `night_window(date: date, latitude: float = 45.1666, longitude: float = -90.8076, tz_name: str = "America/Chicago") -> tuple[datetime, datetime]` — nautical dusk (D-1) and dawn (D) as UTC-aware datetimes, `(start, end)` with `start < end`.
  - `max_kp_in_window(series: list[tuple[datetime, float]], window: tuple[datetime, datetime]) -> Optional[float]` — max Kp among samples with `window[0] <= time <= window[1]` (inclusive both ends); `None` when no samples fall inside.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_night_upload.py`:

```python
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
    # dusk on 3/7 (CST, UTC-6) to dawn on 3/8 (CDT, UTC-5).
    start, end = night_window(date(2026, 3, 8))
    assert start.utcoffset() == timedelta(hours=-6)
    assert end.utcoffset() == timedelta(hours=-5)
    assert start < end


def test_night_window_honors_observer_overrides():
    start_default, end_default = night_window(date(2026, 9, 7))
    start_far, _ = night_window(date(2026, 9, 7), latitude=-41.3, longitude=174.8, tz_name="Pacific/Auckland")
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
    assert max_kp_in_window(
        [(datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc), 5.0)], window
    ) is None
```

(Adjust the import line if Task 2's imports already cover part of it; the tests must import `max_kp_in_window` and `night_window` from `timelapse_generator.youtube.night_upload`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'night_window'`

- [ ] **Step 3: Implement the window functions**

Append to `src/timelapse_generator/youtube/night_upload.py` (after `load_kp_series`):

```python
def night_window(
    date: date,
    latitude: float = 45.1666,
    longitude: float = -90.8076,
    tz_name: str = "America/Chicago",
) -> Tuple[datetime, datetime]:
    """Nautical dusk on date-1 through nautical dawn on date, as UTC datetimes.

    Mirrors scripts/sun.py: same Depression.NAUTICAL and observer convention.
    """
    location = LocationInfo("Observer", "", timezone=tz_name, latitude=latitude, longitude=longitude)
    dusk = sun(
        location.observer,
        date=date - timedelta(days=1),
        tzinfo=location.timezone,
        dawn_dusk_depression=Depression.NAUTICAL,
    )["dusk"]
    dawn = sun(
        location.observer,
        date=date,
        tzinfo=location.timezone,
        dawn_dusk_depression=Depression.NAUTICAL,
    )["dawn"]
    return dusk.astimezone(timezone.utc), dawn.astimezone(timezone.utc)


def max_kp_in_window(
    series: List[Tuple[datetime, float]],
    window: Tuple[datetime, datetime],
) -> Optional[float]:
    """Max Kp among samples with window_start <= time <= window_end; None if none."""
    start, end = window
    inside = [kp for when, kp in series if start <= when <= end]
    return max(inside) if inside else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS (all, including the new window tests)

- [ ] **Step 5: Commit**

```bash
git add src/timelapse_generator/youtube/night_upload.py tests/test_night_upload.py
git commit -m "Add nautical night window and Kp window max"
```

---

### Task 4: State store — `NightUploadResult`, `load_state`, `save_state`

**Files:**
- Modify: `src/timelapse_generator/youtube/night_upload.py` (append)
- Modify: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `@dataclass NightUploadResult` with fields `status: str` (one of `uploaded`, `skipped_low_kp`, `failed`, `already_done`, `no_op`, `dry_run`, `disabled`), `max_kp: Optional[float] = None`, `video_id: Optional[str] = None`, `url: Optional[str] = None`, `error: Optional[str] = None`, `reason: Optional[str] = None`, `metadata: Optional[dict] = None`.
  - `load_state(state_file: Path) -> Dict[str, Dict[str, Any]]` — `{}` when the file does not exist; a corrupt file raises `json.JSONDecodeError` (loud failure, avoids accidental re-uploads).
  - `save_state(state_file: Path, state: Dict[str, Dict[str, Any]]) -> None` — atomic (temp file + `os.replace`), creates parent dirs.
  - `_state_record(date, status, threshold, max_kp=None, video_id=None, url=None, error=None) -> Dict[str, Any]` — the per-date JSON entry shape from the spec: keys `status`, `video_id`, `url`, `max_kp`, `threshold`, `error`, `timestamp` (ISO 8601 with local offset).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_night_upload.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'NightUploadResult'`

- [ ] **Step 3: Implement the state store**

Append to `src/timelapse_generator/youtube/night_upload.py`:

```python
@dataclass
class NightUploadResult:
    """Outcome of one upload_night_for_date run."""

    status: str  # uploaded|skipped_low_kp|failed|already_done|no_op|dry_run|disabled
    max_kp: Optional[float] = None
    video_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    metadata: Optional[dict] = None


def load_state(state_file: Path) -> Dict[str, Dict[str, Any]]:
    """Load the per-date upload state; {} when absent. Corrupt JSON raises."""
    try:
        return json.loads(Path(state_file).read_text())
    except FileNotFoundError:
        return {}


def save_state(state_file: Path, state: Dict[str, Dict[str, Any]]) -> None:
    """Atomically persist the state (temp file + os.replace)."""
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.parent / f".{state_file.name}.tmp"
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, state_file)


def _state_record(
    date: date,
    status: str,
    threshold: float,
    max_kp: Optional[float] = None,
    video_id: Optional[str] = None,
    url: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one per-date state entry (spec JSON shape)."""
    return {
        "status": status,
        "video_id": video_id,
        "url": url,
        "max_kp": max_kp,
        "threshold": threshold,
        "error": error,
        "timestamp": datetime.now().astimezone().isoformat(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/timelapse_generator/youtube/night_upload.py tests/test_night_upload.py
git commit -m "Add atomic per-date night upload state store"
```

---

### Task 5: Orchestrator — `upload_night_for_date`

**Files:**
- Modify: `src/timelapse_generator/youtube/night_upload.py` (append)
- Modify: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: `find_night_video`, `load_kp_series`, `KpDataError`, `night_window`, `max_kp_in_window`, `NightUploadResult`, `load_state`, `save_state`, `_state_record` (Tasks 2-4); `settings.youtube.night_upload` (Task 1); `MetadataManager.generate_metadata(video_file, kp_index, date, ...)` from `youtube/metadata.py` (a `date=` kwarg flows through `**kwargs` and overrides the mtime-derived date in the template context); `YouTubeUploader.upload_video(video_file, title, description, tags, privacy_status, category_id) -> {"video_id", "video_url", ...}` from `youtube/uploader.py`.
- Produces: `upload_night_for_date(date: date, dry_run: bool = False, force: bool = False, threshold: Optional[float] = None) -> NightUploadResult` — the single entry point used by the CLI (Task 6).
- Behavior contract (from the spec's Data Flow):
  1. `enabled` false → `disabled` (no side effects).
  2. State says `uploaded` → `already_done` (never overridden, even by `--force`); `skipped_low_kp` without `--force` → `already_done`.
  3. Video missing → `no_op` (reason `missing_video`); Kp JSON missing → `no_op` (reason `missing_kp`); no state written.
  4. Malformed Kp JSON → `failed` with `error` starting `bad_kp_data:`; `--force` overrides and proceeds.
  5. `max_kp is None or max_kp < threshold` without `--force` → `skipped_low_kp` recorded (`max_kp: null` when no samples in window).
  6. Qualified → metadata via `MetadataManager` with `kp_index=max_kp` and `date=<date at midnight>`; upload via `YouTubeUploader`; record `uploaded` with video id/url. Any exception from uploader construction/upload → `failed` recorded.
  7. `dry_run=True` never uploads and never mutates state; a qualified decision returns `dry_run` with `metadata` populated. Dry-run of a failing condition (bad Kp data) returns `failed` without recording.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_night_upload.py`:

```python
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
        return {"video_id": "abc123", "video_url": "https://www.youtube.com/watch?v=abc123"}


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
    for when, kp in (samples if samples is not None else [(IN_WINDOW, 5.33), (OUT_OF_WINDOW, 1.0)]):
        rows.append([when.strftime("%Y-%m-%d %H:%M:%S.%f"), str(kp), "8", "8"])
    (day_dir / f"k-index_{day.strftime('%Y%m%d')}.json").write_text(kp_bytes or json.dumps(rows))
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
    archive, _ = configured
    make_archive(archive, samples=[(IN_WINDOW, 4.5)])
    monkeypatch.setattr(night_upload, "YouTubeUploader", FakeUploader)

    assert upload_night_for_date(DAY, threshold=5.0).status == "skipped_low_kp"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'upload_night_for_date'`

- [ ] **Step 3: Implement the orchestrator**

Append to `src/timelapse_generator/youtube/night_upload.py`:

```python
def upload_night_for_date(
    date: date,
    dry_run: bool = False,
    force: bool = False,
    threshold: Optional[float] = None,
) -> NightUploadResult:
    """Run the full night-upload decision for one date (spec Data Flow)."""
    cfg = settings.youtube.night_upload
    if not cfg.enabled:
        return NightUploadResult(status="disabled")

    date_key = date.strftime("%Y%m%d")
    state_file = cfg.state_file.expanduser()
    archive_dir = Path(cfg.archive_dir)

    state = load_state(state_file)
    entry = state.get(date_key)
    if entry and entry.get("status") == "uploaded":
        return NightUploadResult(
            status="already_done",
            reason="uploaded",
            video_id=entry.get("video_id"),
            url=entry.get("url"),
        )
    if entry and entry.get("status") == "skipped_low_kp" and not force:
        return NightUploadResult(
            status="already_done",
            reason="already_skipped_low_kp",
            max_kp=entry.get("max_kp"),
        )

    effective_threshold = threshold if threshold is not None else cfg.kp_threshold

    try:
        video = find_night_video(date, archive_dir)
    except FileNotFoundError:
        return NightUploadResult(status="no_op", reason="missing_video")

    kp_path = archive_dir / date_key / f"k-index_{date_key}.json"
    if not kp_path.exists():
        return NightUploadResult(status="no_op", reason="missing_kp")

    try:
        series = load_kp_series(kp_path)
    except KpDataError as exc:
        if dry_run:
            return NightUploadResult(status="failed", error=f"bad_kp_data: {exc}")
        record = _state_record(date, "failed", effective_threshold, error=f"bad_kp_data: {exc}")
        save_state(state_file, {**state, date_key: record})
        return NightUploadResult(status="failed", error=f"bad_kp_data: {exc}")

    window = night_window(
        date,
        latitude=cfg.latitude,
        longitude=cfg.longitude,
        tz_name=cfg.timezone,
    )
    max_kp = max_kp_in_window(series, window)
    logger.info(f"Night window for {date}: {window}, max Kp in window: {max_kp}")

    if not force and (max_kp is None or max_kp < effective_threshold):
        if not dry_run:
            record = _state_record(date, "skipped_low_kp", effective_threshold, max_kp=max_kp)
            save_state(state_file, {**state, date_key: record})
        return NightUploadResult(status="skipped_low_kp", max_kp=max_kp)

    metadata = MetadataManager().generate_metadata(
        video_file=video,
        kp_index=max_kp,
        date=datetime.combine(date, datetime.min.time()),
    )

    if dry_run:
        return NightUploadResult(status="dry_run", max_kp=max_kp, metadata=metadata)

    try:
        uploader = YouTubeUploader()
        upload_result = uploader.upload_video(
            video_file=video,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            privacy_status=metadata["privacy_status"],
            category_id=metadata["category_id"],
        )
    except Exception as exc:
        logger.error(f"Night upload failed for {date}: {exc}")
        record = _state_record(date, "failed", effective_threshold, max_kp=max_kp, error=str(exc))
        save_state(state_file, {**state, date_key: record})
        return NightUploadResult(status="failed", max_kp=max_kp, error=str(exc))

    record = _state_record(
        date,
        "uploaded",
        effective_threshold,
        max_kp=max_kp,
        video_id=upload_result["video_id"],
        url=upload_result["video_url"],
    )
    save_state(state_file, {**state, date_key: record})
    return NightUploadResult(
        status="uploaded",
        max_kp=max_kp,
        video_id=upload_result["video_id"],
        url=upload_result["video_url"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS (all, including the 12 orchestrator scenarios)

If the `date=` kwarg does not override the template date (title shows the file mtime date instead), check that `MetadataManager.generate_metadata` merges `**kwargs` AFTER the fixed context keys — it does (`context = {..., **kwargs}` in `youtube/metadata.py`).

- [ ] **Step 5: Commit**

```bash
git add src/timelapse_generator/youtube/night_upload.py tests/test_night_upload.py
git commit -m "Add upload_night_for_date orchestrator with Kp gate and state machine"
```

---

### Task 6: CLI — `timelapse upload-night`

**Files:**
- Modify: `src/timelapse_generator/cli.py` (add import + new command before `def main():`)
- Modify: `src/timelapse_generator/youtube/night_upload.py` (add `parse_date_arg`)
- Modify: `tests/test_night_upload.py`

**Interfaces:**
- Consumes: `upload_night_for_date` (Task 5), `NightUploadResult` (Task 4).
- Produces:
  - `parse_date_arg(value: Optional[str]) -> date` in `night_upload.py` — `None` → today (local); `"YYYYMMDD"` (8 digits) → `strptime`; otherwise ISO `YYYY-MM-DD`; anything else raises `ValueError`.
  - Click command `upload-night [DATE] [--dry-run] [--force] [--threshold FLOAT]` in `cli.py`. Exit 0 for `disabled`/`no_op`/`already_done`/`skipped_low_kp`/`dry_run`/`uploaded`; exit 1 for `failed` and for an invalid DATE. `--dry-run` prints the decision incl. would-be title/description/tags/privacy without uploading or mutating state. `--force` forwards to the orchestrator; `--threshold` overrides config.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_night_upload.py`:

```python
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
            status="uploaded", max_kp=5.33, video_id="abc",
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
        (NightUploadResult(status="already_done", reason="uploaded"), "Already handled"),
    ]
    for stub, needle in cases:
        monkeypatch.setattr(
            cli_module, "upload_night_for_date", lambda *a, **k: stub
        )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_date_arg'` (and the CLI has no `upload-night` command)

- [ ] **Step 3: Add `parse_date_arg` to night_upload.py**

Append to `src/timelapse_generator/youtube/night_upload.py`:

```python
def parse_date_arg(value: Optional[str]) -> date:
    """Parse a CLI date argument: None=today, YYYYMMDD, or YYYY-MM-DD."""
    if value is None:
        return datetime.now().astimezone().date()
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"invalid DATE {value!r}: use YYYYMMDD or YYYY-MM-DD") from None
```

- [ ] **Step 4: Add the CLI command**

In `src/timelapse_generator/cli.py`, extend the existing import block — change:

```python
from .youtube.uploader import YouTubeUploader
from .youtube.metadata import MetadataManager
```

to:

```python
from .youtube.uploader import YouTubeUploader
from .youtube.metadata import MetadataManager
from .youtube.night_upload import parse_date_arg, upload_night_for_date
```

Then insert this command immediately BEFORE `def main():`:

```python
@cli.command(name='upload-night')
@click.argument('date', required=False, type=str)
@click.option('--dry-run', is_flag=True, help='Show the decision without uploading or updating state')
@click.option('--force', is_flag=True, help='Bypass the Kp gate and a prior skipped_low_kp state')
@click.option('--threshold', type=float, default=None, help='Override the configured Kp threshold')
def upload_night(date, dry_run, force, threshold):
    """Upload the night high-res AuroraCam video for DATE (YYYYMMDD or YYYY-MM-DD, default today)."""
    try:
        target = parse_date_arg(date)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    result = upload_night_for_date(target, dry_run=dry_run, force=force, threshold=threshold)

    if result.status == "disabled":
        click.echo("Night uploads are disabled (youtube.night_upload.enabled=false).")
        return
    if result.status == "no_op":
        click.echo(f"Nothing to do for {target:%Y-%m-%d} ({result.reason}); a later poll will retry.")
        return
    if result.status == "already_done":
        detail = result.url or f"previously skipped (max Kp {result.max_kp})"
        click.echo(f"Already handled {target:%Y-%m-%d}: {detail}")
        return
    if result.status == "skipped_low_kp":
        observed = "no samples in window" if result.max_kp is None else f"max Kp {result.max_kp}"
        click.echo(f"⏭️  Skipped {target:%Y-%m-%d}: {observed} below threshold.")
        return
    if result.status == "dry_run":
        click.echo(f"🔍 Dry run for {target:%Y-%m-%d}: would upload")
        click.echo(f"Max Kp in window: {result.max_kp}")
        click.echo(f"Title: {result.metadata['title']}")
        click.echo(f"Description: {result.metadata['description']}")
        click.echo(f"Tags: {', '.join(result.metadata['tags'])}")
        click.echo(f"Privacy: {result.metadata['privacy_status']}")
        return
    if result.status == "failed":
        click.echo(f"❌ Upload failed for {target:%Y-%m-%d}: {result.error}")
        sys.exit(1)

    click.echo(f"✅ Uploaded {target:%Y-%m-%d}: {result.url} (max Kp {result.max_kp})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_night_upload.py -v`
Expected: PASS (all, including the 7 CLI tests)

- [ ] **Step 6: Run the full suite to check for regressions**

Run: `uv run pytest -q`
Expected: PASS (existing tests unaffected)

- [ ] **Step 7: Commit**

```bash
git add src/timelapse_generator/cli.py src/timelapse_generator/youtube/night_upload.py tests/test_night_upload.py
git commit -m "Add upload-night CLI command"
```

---

### Task 7: Cron wrapper, README, manual acceptance

**Files:**
- Create: `scripts/upload_night_cron.sh` (executable)
- Modify: `README.md` (new subsection under `## YouTube Setup`, after `### 2. Configure Authentication`)

**Interfaces:**
- Consumes: the `timelapse upload-night` command (Task 6); `scripts/common_env.sh` (`LOGFILE`, `log()`); `uv` on PATH.
- Produces: `scripts/upload_night_cron.sh` — safe to run every 30 minutes from cron; skips when another run holds the lock; appends all output to `$LOGFILE` (default `/tmp/timelapse.log`). Exit code mirrors the CLI (0 clean, 1 failure).

- [ ] **Step 1: Create the cron wrapper**

Create `scripts/upload_night_cron.sh`:

```bash
#!/usr/bin/bash
#
# Poll for new night high-res timelapses and upload qualified ones to YouTube.
# Scheduled every 30 minutes via cron; a cheap no-op when nothing is pending
# (missing video/Kp file) or when youtube.night_upload.enabled is false.

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

# Shared logging conventions (LOGFILE, log())
. "${SCRIPT_DIR}/common_env.sh"

# One upload at a time: a 1440p upload can outlast the 30-minute poll.
LOCK_FILE=/tmp/timelapse_upload_night.lock
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    log "upload_night_cron: another upload-night run holds the lock; skipping"
    exit 0
fi

log "upload_night_cron: starting"
cd "${REPO_DIR}" && uv run timelapse upload-night >> "$LOGFILE" 2>&1
RC=$?
log "upload_night_cron: finished rc=${RC}"
exit $RC
```

Make it executable and syntax-check it:

```bash
chmod +x scripts/upload_night_cron.sh
bash -n scripts/upload_night_cron.sh
```

Expected: `bash -n` exits 0 silently.

- [ ] **Step 2: Smoke-test the wrapper locally**

```bash
LOGFILE=/tmp/opencode/upload_night_smoke.log scripts/upload_night_cron.sh; echo "rc=$?"
```

Expected: `rc=0` (no qualifying video present → CLI no-ops). The log contains `upload_night_cron: starting` and `finished rc=0` (plus the CLI's own "Nothing to do" line). Note: if a real qualifying video + Kp file exist in the archive for today, this would attempt a real upload — in that case pass an old date via a direct CLI dry-run instead (`uv run timelapse upload-night --dry-run 20260916`) and skip this smoke test.

- [ ] **Step 3: Document in README.md**

In `README.md`, insert this subsection immediately AFTER the `### 2. Configure Authentication` section (i.e. right before `## Video Backends`):

```markdown
### 3. Automatic Night Uploads

`AuroraCam_<date>_2560x1440.mp4` videos are uploaded to YouTube automatically
when the planetary Kp index reached 4.0 at some point during the night window
(nautical dusk the evening before through nautical dawn, Gilman WI):

```bash
# One-off / manual (any date, YYYYMMDD or YYYY-MM-DD)
uv run timelapse upload-night 20260916
uv run timelapse upload-night --dry-run          # decide, don't upload
uv run timelapse upload-night --force 20260916   # bypass the Kp gate

# Install the 30-minute poll (as the user that owns the archive)
crontab -e
# */30 * * * * /path/to/timelapse-generator/scripts/upload_night_cron.sh
```

The first run must happen interactively once so the OAuth browser flow can
complete; the token is then cached at
`~/.cache/timelapse_generator/youtube_token.json` and refreshed headlessly by
later runs. Per-date state lives in
`~/.local/state/timelapse-generator/night_uploads.json`: uploaded videos are
never uploaded twice, Kp-skipped dates need `--force`, and failed uploads are
retried by the next poll. Set `youtube.night_upload.enabled: false` in
`config.yaml` to turn the poll into a no-op.
```

- [ ] **Step 4: Full suite + lint pass**

Run: `uv run pytest -q && uv run black --check src/timelapse_generator/youtube/night_upload.py src/timelapse_generator/cli.py src/timelapse_generator/config/settings.py tests/test_night_upload.py`

Expected: all tests pass; `black --check` reports no reformatting needed (run `black` on the same paths if it does, then re-run tests and amend into the files before committing).

- [ ] **Step 5: Manual acceptance (interactive, on the host)**

1. `uv run timelapse upload-night --dry-run <an existing archive date>` — expect the decision printout (window, max Kp, title/desc/tags/privacy) and exit 0, with no new entries in `~/.local/state/timelapse-generator/night_uploads.json`.
2. `uv run timelapse upload-night --force <same date>` — expect a private upload, a `uploaded` state entry, and the video visible as Private on the channel. Verify a second plain run prints "Already handled" without re-uploading.
3. Add the crontab line from the README (`crontab -e`) and confirm the next poll appends a `finished rc=0` line to `/tmp/timelapse.log`.

If YouTube credentials are not yet set up on this machine, do steps 1 and 3 now and leave step 2 for the first interactive session with `youtube_credentials.json` in place.

- [ ] **Step 6: Commit**

```bash
git add scripts/upload_night_cron.sh README.md
git commit -m "Add upload-night cron poll wrapper and docs"
```
