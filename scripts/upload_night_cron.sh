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
