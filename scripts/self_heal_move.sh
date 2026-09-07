#!/usr/bin/env bash
# Self-heal safety net: if the scheduled move job never ran, move
# window-matching images from the FTP dir into the archive before encoding.
# Windows come from filename timestamps (AuroraCam_00_YYYYMMDDHHMMSS.jpg):
#   night: yesterday dusk .. today dawn+59s
#   day:   today dawn+60s .. today dusk+59s

usage() {
    echo "Usage: $0 {day|night} [--date YYYY-MM-DD]"
    exit 1
}

WINDOW="${1:-}"
shift || true
DATE_REF=$(date +%Y-%m-%d)
if [ "${1:-}" = "--date" ] && [ -n "${2:-}" ]; then
    DATE_REF=$2
fi
[ "$WINDOW" = "day" ] || [ "$WINDOW" = "night" ] || usage

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"
: "${FTP_DIR:=/srv/ftp/aurora}"

# Recompute date-derived vars so --date overrides propagate.
TODAY=${DATE_REF//-/}
ARCHIVE_DIR=$TIMELAPSE_DIR/$TODAY
PROCESS_DIR=$ARCHIVE_DIR/$WINDOW

YESTERDAY=$(date -d "$DATE_REF - 1 day" +%Y-%m-%d)
DUSK_YESTERDAY=$(python3 "$SCRIPT_DIR/sun.py" --dusk --date "$YESTERDAY")
DAWN_TODAY=$(python3 "$SCRIPT_DIR/sun.py" --dawn --date "$DATE_REF")
DUSK_TODAY=$(python3 "$SCRIPT_DIR/sun.py" --dusk --date "$DATE_REF")

plus_secs() { # $1=YYYY-MM-DD $2=HH:MM $3=seconds -> YYYYMMDDHHMMSS
    local base
    base=$(date -d "$1 $2" +%s)
    date -d "@$((base + $3))" +%Y%m%d%H%M%S
}

case $WINDOW in
    night)
        LO=$(plus_secs "$YESTERDAY" "$DUSK_YESTERDAY" 0)
        HI=$(plus_secs "$DATE_REF" "$DAWN_TODAY" 59)
        ;;
    day)
        LO=$(plus_secs "$DATE_REF" "$DAWN_TODAY" 60)
        HI=$(plus_secs "$DATE_REF" "$DUSK_TODAY" 59)
        ;;
esac

if [ "$(ls -1 "$PROCESS_DIR"/*.jpg 2>/dev/null | wc -l)" -gt 0 ]; then
    log "SELF-HEAL: $WINDOW window already has images in $PROCESS_DIR - nothing to do"
    exit 0
fi

if [ ! -d "$FTP_DIR" ]; then
    log "SELF-HEAL: $FTP_DIR does not exist - nothing to do"
    exit 0
fi

MATCHES=()
for f in "$FTP_DIR"/AuroraCam_*.jpg; do
    [ -e "$f" ] || continue
    ts=$(basename "$f" | grep -o '[0-9]\{14\}' | head -1)
    [ -n "$ts" ] || continue
    if (( 10#$ts >= 10#$LO && 10#$ts <= 10#$HI )); then
        MATCHES+=("$f")
    fi
done

if [ "${#MATCHES[@]}" -eq 0 ]; then
    log "SELF-HEAL: no $WINDOW-window images ($LO..$HI) in $FTP_DIR - nothing to do"
    exit 0
fi

log "SELF-HEAL: $WINDOW move job apparently missed - recovering ${#MATCHES[@]} images ($LO..$HI)"
mkdir -p "$PROCESS_DIR"
START=$SECONDS
mv "${MATCHES[@]}" "$PROCESS_DIR" 2>>$LOGFILE || {
    log "SELF-HEAL: ERROR: mv into $PROCESS_DIR failed"
    exit 1
}
log "SELF-HEAL: move completed in $((SECONDS - START))s"
log "SELF-HEAL: PROCESS_DIR after move: $(jpg_stats "$PROCESS_DIR")"
log "SELF-HEAL: FTP_DIR after move: $(jpg_stats "$FTP_DIR")"

if [ "$(id -u)" = "0" ]; then
    chown -R greg:greg "$ARCHIVE_DIR"
    find "$PROCESS_DIR" -type f -exec chmod 644 {} +
    log "SELF-HEAL: ownership and permissions fixed (ran as root)"
fi

exit 0
