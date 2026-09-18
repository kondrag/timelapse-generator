# Design: Automatic YouTube Upload of Night High-Res Timelapses

**Date:** 2026-09-17
**Status:** Approved design (pending implementation plan)
**Repo:** timelapse-generator

## Summary

Automatically upload the nightly high-resolution aurora timelapse
(`AuroraCam_<date>_2560x1440.mp4`) to YouTube, gated on space weather: the
video is uploaded only when the planetary Kp index reached at least 4.0 at
some point during that night's imaging window. A periodic cron poll detects
new videos and triggers uploads; the same code path is exposed as a manual
CLI command for on-demand uploads. Existing YouTube upload machinery
(`YouTubeUploader`) is reused, not duplicated.

## Requirements

- Upload only `AuroraCam_<YYYYMMDD>_2560x1440.mp4` night videos from
  `/var/local/timelapse/<YYYYMMDD>/`. Never upload low-res or CloudCam (day)
  videos.
- Gate each upload on Kp: parse the sibling `k-index_<YYYYMMDD>.json` (NOAA
  `noaa-planetary-k-index.json` product fetched by
  `scripts/fetch_spaceweather.sh`), keep only samples whose `time_tag` falls
  inside the night window for that date, and upload only if the maximum Kp in
  that window is >= 4.0.
- The night window for date D is nautical dusk on D-1 through nautical dawn
  on D, in local time (America/Chicago, observer at Gilman, WI), converted to
  UTC for comparison against NOAA `time_tag` values.
- Privacy status: private. No custom thumbnail (YouTube auto-selects frames).
- Never upload the same video twice: persist per-date upload state.
- Failed uploads are retried automatically by later polls; Kp-skipped videos
  are never auto-retried but can be forced manually.
- Support manual invocation for any date, with a dry-run mode.

## Non-Goals

- No upload of day (CloudCam) or low-resolution videos.
- No custom thumbnails, playlists, or caption handling.
- No new standalone project; all work stays in timelapse-generator.
- No change to video generation or archive retention behavior.

## Components

### 1. `src/timelapse_generator/youtube/night_upload.py` (new module)

- `find_night_video(date) -> Path`: returns
  `<archive_dir>/<YYYYMMDD>/AuroraCam_<YYYYMMDD>_2560x1440.mp4` if it exists
  (size > 0), else raises `FileNotFoundError`. The video reaches the archive
  via `mv` within one filesystem (atomic), so partially-written files cannot
  be observed; the existence + size check is sufficient.
- `load_kp_series(path) -> list[tuple[datetime, float]]`: parses the NOAA
  product format — element 0 is the header row
  `["time_tag", "Kp", "a_running", "station_count"]`; subsequent rows carry
  UTC timestamps formatted `%Y-%m-%d %H:%M:%S.%f` and decimal Kp values.
  Raises `KpDataError` on a missing/short/malformed file.
- `night_window(date) -> tuple[datetime, datetime]`: nautical dusk on D-1 and
  nautical dawn on D computed with `astral` (same `Depression.NAUTICAL` and
  observer as `scripts/sun.py`), localized to `America/Chicago`, returned as
  UTC-aware datetimes.
- `max_kp_in_window(series, window) -> Optional[float]`: maximum Kp among
  samples whose UTC `time_tag` lies within `[window_start, window_end]`;
  `None` when no samples fall inside the window.
- `upload_night_for_date(date, dry_run, force, threshold) -> NightUploadResult`:
  orchestrator. Loads config, consults and updates the state file, evaluates
  the gate, and (when qualified) delegates to `YouTubeUploader.upload_video`.
- State file: `~/.local/state/timelapse-generator/night_uploads.json`
  (overridable via config). Archive directories are deleted after 30 days, so
  state must live outside `/var/local/timelapse`. Structure:

  ```json
  {
    "20260916": {
      "status": "uploaded",
      "video_id": "abc123",
      "url": "https://www.youtube.com/watch?v=abc123",
      "max_kp": 5.33,
      "threshold": 4.0,
      "error": null,
      "timestamp": "2026-09-17T07:05:11-05:00"
    }
  }
  ```

  Statuses: `uploaded`, `skipped_low_kp`, `failed`. Writes are atomic
  (temporary file + `os.replace`).

### 2. CLI: `timelapse upload-night`

Added to `src/timelapse_generator/cli.py`:

```
timelapse upload-night [DATE] [--dry-run] [--force] [--threshold FLOAT]
```

- `DATE` (optional, `YYYYMMDD` or `YYYY-MM-DD`): defaults to today.
- `--dry-run`: prints the decision (video found, window, max Kp, would-be
  title/description/tags/privacy) without uploading or mutating state.
- `--force`: bypasses the Kp gate and overrides a prior `skipped_low_kp`
  state. `failed` entries are always eligible for retry, with or without
  `--force`.
- `--threshold`: overrides `youtube.night_upload.kp_threshold` from config.
- Exit codes: 0 = uploaded, skipped, or clean no-op; 1 = failure (bad data,
  upload error). Dry-run of a qualified upload also exits 0.
- The cron poll and manual invocations use this same command.

### 3. `scripts/upload_night_cron.sh` (new)

- Sources `scripts/common_env.sh` for logging conventions.
- Guards against concurrent runs with `flock -n` on a lock file (a 1440p
  upload can outlast the poll interval).
- Runs `uv run --project <repo> timelapse upload-night >> $LOGFILE 2>&1`.
- Scheduled by a crontab entry: `*/30 * * * * .../upload_night_cron.sh`.
  A recurring poll (rather than an `at`-chained one-shot) also catches
  videos that appear after `timelapse.sh night` failures and re-runs.
  Installation is documented in the README; the poll is a cheap no-op when
  there is nothing to upload.

### 4. Config additions (`config.yaml`, `youtube:` section)

```yaml
youtube:
  night_upload:
    enabled: true
    kp_threshold: 4.0
    archive_dir: /var/local/timelapse
    state_file: ~/.local/state/timelapse-generator/night_uploads.json
    latitude: 45.1666
    longitude: -90.8076
    timezone: America/Chicago
```

Defaults match the existing Gilman, WI observer and current deployment
paths. `enabled: false` makes the cron wrapper exit cleanly without touching
anything else (useful while OAuth is not yet set up on a machine).

## Data Flow (each poll or manual run)

1. If `youtube.night_upload.enabled` is false → exit 0.
2. Load state for the target date. If status is `uploaded` or
   `skipped_low_kp` (and not `--force`) → done.
3. `find_night_video(date)` → missing → clean no-op (video may not be
   generated yet; a later poll retries).
4. `load_kp_series(k-index_<date>.json)` → missing → clean no-op (fetch may
   have failed; file could still appear). Malformed → record `failed`
   (reason `bad_kp_data`) so polls stop re-parsing; `--force` overrides.
5. `night_window(date)`; `max_kp_in_window(series, window)`. Empty window
   overlap → treat as below threshold (record `skipped_low_kp`, `max_kp`
   null).
6. If `max_kp >= threshold` or `--force`:
   - Build metadata via the existing Jinja templates, passing
     `kp_index=max_kp` so the title/description include it
     (e.g. "Aurora Timelapse - September 16, 2026 (Kp 5.33)"); tags and
     category from existing `youtube:` config; `privacy_status` from config
     (default `private`).
   - Upload through `YouTubeUploader` (token cache/refresh, resumable
     chunks, built-in retries).
   - Record `uploaded` with video id/url.
7. Else record `skipped_low_kp` with the observed `max_kp`.

## Error Handling

| Condition | Behavior |
|---|---|
| Video not present | Quiet no-op; retried by next poll |
| Kp JSON not present | Quiet no-op; retried by next poll |
| Kp JSON malformed | `failed` (`bad_kp_data`); `--force` overrides |
| No Kp samples in window | `skipped_low_kp` (`max_kp: null`) |
| Auth error (token refresh fails, needs browser) | `failed`; logged; cron retries; first-time auth must be done via a manual `upload-night --dry-run`/forced run on an interactive session |
| Upload `HttpError` after built-in retries | `failed`; retried next poll |
| Quota exceeded | `failed`; retried next poll (failed inserts consume no upload quota) |
| Concurrent cron + manual run | `flock -n` in cron wrapper; manual run waits/reports busy |

## Testing

pytest (following existing `tests/` patterns and mocking conventions):

- `night_window`: known dates (e.g. 2026-06-21 vs 2026-12-21) produce
  expected UTC window bounds; DST spring/fall transitions handled.
- `load_kp_series`: happy path with real-format fixture (header row + rows),
  short file, non-numeric Kp, missing file → `KpDataError`.
- `max_kp_in_window`: boundary inclusivity at window edges, no samples in
  window, all-samples-outside.
- `upload_night_for_date` state machine with a mocked `YouTubeUploader`:
  first upload, second run no-op, `skipped_low_kp` blocked then allowed via
  `--force`, `failed` retried, `--dry-run` mutates nothing, malformed JSON
  marks `failed`.
- CLI: argument parsing, exit codes, `--dry-run` output.

Manual acceptance check on the host: `timelapse upload-night --dry-run` for
an existing archive date, then a forced upload of one video with `--force`
and private visibility verified on the channel.
