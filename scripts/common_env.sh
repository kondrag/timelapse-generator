#!/usr/bin/bash

# Common environment variables for timelapse scripts

# Logging (override via environment for testing)
: ${LOGFILE:=/tmp/timelapse.log}

# Directories
: ${TIMELAPSE_DIR:=/var/local/timelapse}
: ${WEEWX_DIR:=/tmp/weewx}
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

# Date variables
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
ARCHIVE_DIR=${TIMELAPSE_DIR}/${TODAY}

# Path settings
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin

# Logging helper
log() {
    echo "$(date '+%a %b %d %H:%M:%S %Z %Y') - $*" >> "$LOGFILE"
}

# Report count and chronological bounds (filenames embed YYYYMMDDhhmmss) of the
# jpgs in a directory. First/last reveal whether an image window is complete.
jpg_stats() {
    local DIR=$1
    local COUNT FIRST LAST
    COUNT=$(ls -1 "$DIR"/*.jpg 2>/dev/null | wc -l)
    FIRST=$(ls -1 "$DIR"/*.jpg 2>/dev/null | head -1)
    LAST=$(ls -1 "$DIR"/*.jpg 2>/dev/null | tail -1)
    echo "count=$COUNT first=${FIRST:-NONE} last=${LAST:-NONE}"
}

# Rotate $LOGFILE to a name unique per user+pid so concurrent midnight
# invocations can never collide or overwrite each other's history. If we
# lose the race and the live log survives (foreign-owned on sticky /tmp),
# append a separator instead of truncating the other instance's entries.
rotate_log() {
    local ROTATED="${LOGFILE}.$(date +%Y%m%d_%H%M%S).$(id -un).$$"
    if ${MV_CMD:-mv} "$LOGFILE" "$ROTATED" 2>/dev/null; then
        echo "Initialize logs for $(date)" > "$LOGFILE"
    elif [ -e "$LOGFILE" ]; then
        {
            echo ""
            echo "=== log continued by $(id -un) at $(date) after losing rotation race ==="
        } >> "$LOGFILE" 2>/dev/null || true
    else
        echo "Initialize logs for $(date)" > "$LOGFILE"
    fi
    chmod 666 "$LOGFILE" 2>/dev/null || true
}

# Schedule $2 via `at` for $1 (HH:MM), then verify the job actually appears
# in the at queue. The unexplained Sep 7 kill left no jobs scheduled and no
# trace; this turns that failure mode into a loud ERROR plus an alert mail.
schedule_and_verify() {
    local WHEN=$1 CMD=$2
    { echo "$CMD" | ${AT_CMD:-at} "$WHEN" 2>&1; } >> "$LOGFILE"
    # atq lists only the invoking user's jobs (root sees all); the user
    # anchor is unnecessary and times never collide across the 5-min offsets
    if ${ATQ_CMD:-atq} 2>/dev/null | grep -Eq "[0-9] ${WHEN}:[0-9]{2} "; then
        log "at-job '$CMD' at $WHEN confirmed in at queue"
        return 0
    fi
    log "ERROR: at-job '$CMD' at $WHEN NOT confirmed in at queue - scheduling failed"
    echo "setup_schedule.sh ($(id -un)): at-job '$CMD' at $WHEN was NOT found in the at queue after scheduling. Check atq and /tmp/timelapse.log. ($(date))" \
        | ${MAIL_CMD:-mail} -s "timelapse: at-job scheduling failed" "${MAIL_TO:-greg}" 2>/dev/null || true
    return 1
}
