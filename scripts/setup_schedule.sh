#!/usr/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "${SCRIPT_DIR}/common_env.sh"

DAWN=$(python3 ${SCRIPT_DIR}/sun.py --dawn)
DUSK=$(python3 ${SCRIPT_DIR}/sun.py --dusk)

# clear logs and write new values
mv $LOGFILE $LOGFILE.old
echo "Initialize logs for $(date)" > $LOGFILE
echo "Dawn is $DAWN" >> $LOGFILE
echo "Dusk is $DUSK" >> $LOGFILE

echo "${SCRIPT_DIR}/move_ftp_images.sh night" | at $DAWN
echo "${SCRIPT_DIR}/move_ftp_images.sh day" | at $DUSK
