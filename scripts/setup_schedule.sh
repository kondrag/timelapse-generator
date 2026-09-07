#!/usr/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "${SCRIPT_DIR}/common_env.sh"

usage() {
    echo "Usage: $0 {images|timelapse}"
    exit 1
}

if [ -z "$1" ]; then
    usage
fi

OPTION=$1

# python3-astral Debian package must be installed for system python
DAWN=$(python3 ${SCRIPT_DIR}/sun.py --dawn)
DUSK=$(python3 ${SCRIPT_DIR}/sun.py --dusk)

OFFSET_MINUTES=5
DAWN_PLUS_OFFSET=$(date -d "$DAWN today + $OFFSET_MINUTES minutes" +%H:%M)
DUSK_PLUS_OFFSET=$(date -d "$DUSK today + $OFFSET_MINUTES minutes" +%H:%M)

# rotate to a unique timestamped+user+pid name; race-safe (see common_env.sh)
rotate_log

log "=== setup_schedule.sh invoked by $(id -un) with option '$OPTION' ==="
log "local time: $(date), UTC: $(date -u), TZ: $(date +%Z)"
log "Dawn is $DAWN"
log "Dawn plus $OFFSET_MINUTES minutes is $DAWN_PLUS_OFFSET"
log "Dusk is $DUSK"
log "Dusk plus $OFFSET_MINUTES minutes is $DUSK_PLUS_OFFSET"

warn_if_passed() {
    local TARGET=$1 LABEL=$2 NOW
    NOW=$(date +%H:%M)
    if [[ "$NOW" > "$TARGET" ]]; then
        log "WARNING: $LABEL ($TARGET) has already passed today ($(date +%H:%M)) - at will schedule it for TOMORROW"
    fi
}

if [ "$OPTION" == "images" ]; then
    warn_if_passed "$DAWN" "dawn"
    log "scheduling: move_ftp_images.sh night at $DAWN"
    schedule_and_verify "$DAWN" "${SCRIPT_DIR}/move_ftp_images.sh night"
    warn_if_passed "$DUSK" "dusk"
    log "scheduling: move_ftp_images.sh day at $DUSK"
    schedule_and_verify "$DUSK" "${SCRIPT_DIR}/move_ftp_images.sh day"
elif [ "$OPTION" == "timelapse" ]; then
    warn_if_passed "$DAWN_PLUS_OFFSET" "dawn+offset"
    log "scheduling: timelapse.sh night at $DAWN_PLUS_OFFSET"
    schedule_and_verify "$DAWN_PLUS_OFFSET" "${SCRIPT_DIR}/timelapse.sh night"
    warn_if_passed "$DUSK_PLUS_OFFSET" "dusk+offset"
    log "scheduling: timelapse.sh day at $DUSK_PLUS_OFFSET"
    schedule_and_verify "$DUSK_PLUS_OFFSET" "${SCRIPT_DIR}/timelapse.sh day"
else
    usage
fi

log "at queue for user $(id -un) after scheduling (other users' jobs are hidden):"
atq >> $LOGFILE 2>&1
