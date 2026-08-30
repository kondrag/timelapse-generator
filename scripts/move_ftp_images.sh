#!/usr/bin/bash

usage() {
    echo "Usage: $0 {day|night}"
    exit 1
}

if [ "$1" != "day" ] && [ "$1" != "night" ]; then
    usage
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"
FTP_DIR=/srv/ftp/aurora
PROCESS_DIR="${ARCHIVE_DIR}/${1}"
USER=greg

echo "===== $(date) - Moving $1 images to $PROCESS_DIR =====" >> $LOGFILE

log "PATH is $PATH"

cd $FTP_DIR || { log "ERROR: cannot cd to $FTP_DIR, aborting image move"; exit 1; }
mkdir -p $PROCESS_DIR
chown -R $USER:$USER $ARCHIVE_DIR
chmod -R 0755 $ARCHIVE_DIR

log "FTP_DIR before move: $(jpg_stats $FTP_DIR)"
if [ "$(ls -1 $FTP_DIR/*.jpg 2>/dev/null | wc -l)" -eq 0 ]; then
    log "WARNING: no JPG images found in $FTP_DIR - the camera may be offline or images were already moved"
fi
log "Moving JPG images..."
START=$SECONDS
mv *.jpg $PROCESS_DIR 2>> $LOGFILE
log "move completed in $((SECONDS - START))s"
log "FTP_DIR after move: $(jpg_stats $FTP_DIR)"

cd $PROCESS_DIR || { log "ERROR: cannot cd to $PROCESS_DIR"; exit 1; }
log "PROCESS_DIR after move: $(jpg_stats $PROCESS_DIR)"
chown -R $USER:$USER $PROCESS_DIR
find $PROCESS_DIR -type f -exec chmod 644 {} +
log "PROCESS_DIR ownership and permissions fixed"
