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
        raise KpDataError(
            f"Kp file {path} is not a JSON array with a header and samples"
        )

    header = rows[0]
    if not (isinstance(header, list) and "time_tag" in header and "Kp" in header):
        raise KpDataError(f"Kp file {path} has unexpected header row: {header!r}")

    series: List[Tuple[datetime, float]] = []
    for row in rows[1:]:
        if not isinstance(row, list) or len(row) < 2:
            raise KpDataError(f"Kp file {path} has short row: {row!r}")
        try:
            when = datetime.strptime(str(row[0]), NOAA_TIME_FORMAT).replace(
                tzinfo=timezone.utc
            )
            kp = float(row[1])
        except (ValueError, TypeError) as exc:
            raise KpDataError(
                f"Kp file {path} has malformed row {row!r}: {exc}"
            ) from exc
        series.append((when, kp))
    return series


def night_window(
    date: date,
    latitude: float = 45.1666,
    longitude: float = -90.8076,
    tz_name: str = "America/Chicago",
) -> Tuple[datetime, datetime]:
    """Nautical dusk on date-1 through nautical dawn on date, as UTC datetimes.

    Mirrors scripts/sun.py: same Depression.NAUTICAL and observer convention.
    """
    location = LocationInfo(
        "Observer", "", timezone=tz_name, latitude=latitude, longitude=longitude
    )
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
