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


DAWN=$(python3 ${SCRIPT_DIR}/sun.py --dawn)
DUSK=$(python3 ${SCRIPT_DIR}/sun.py --dusk)

OFFSET_MINUTES=5
DAWN_PLUS_OFFSET=$(date -d "$DAWN today + $OFFSET_MINUTES minutes" +%H:%M)
DUSK_PLUS_OFFSET=$(date -d "$DUSK today + $OFFSET_MINUTES minutes" +%H:%M)

# clear logs and write new values
mv $LOGFILE $LOGFILE.old
echo "Initialize logs for $(date)" > $LOGFILE
echo "Dawn is $DAWN" >> $LOGFILE
echo "Dawn plus $OFFSET_MINUTES minutes is $DAWN_PLUS_OFFSET" >> $LOGFILE
echo "Dusk is $DUSK" >> $LOGFILE
echo "Dusk plus $OFFSET_MINUTES minutes is $DUSK_PLUS_OFFSET" >> $LOGFILE

if [ "$OPTION" == "images" ]; then
    echo "${SCRIPT_DIR}/move_ftp_images.sh night" | at $DAWN
    echo "${SCRIPT_DIR}/move_ftp_images.sh day" | at $DUSK
elif [ "$OPTION" == "timelapse" ]; then
    echo "${SCRIPT_DIR}/timelapse.sh night" | at $DAWN_PLUS_OFFSET
    echo "${SCRIPT_DIR}/timelapse.sh day" | at $DUSK_PLUS_OFFSET
else
    usage
fi
