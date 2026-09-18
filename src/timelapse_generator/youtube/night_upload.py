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
        if not force:
            record = _state_record(
                date, "failed", effective_threshold, error=f"bad_kp_data: {exc}"
            )
            save_state(state_file, {**state, date_key: record})
            return NightUploadResult(status="failed", error=f"bad_kp_data: {exc}")
        logger.warning(f"Forced upload for {date} proceeds despite bad Kp data: {exc}")
        series = []

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
            record = _state_record(
                date, "skipped_low_kp", effective_threshold, max_kp=max_kp
            )
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
        record = _state_record(
            date, "failed", effective_threshold, max_kp=max_kp, error=str(exc)
        )
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
