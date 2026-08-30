#!/usr/bin/bash

# Common environment variables for timelapse scripts

# Logging
LOGFILE=/tmp/timelapse.log

# Directories
TIMELAPSE_DIR=/var/local/timelapse
WEEWX_DIR=/tmp/weewx
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
