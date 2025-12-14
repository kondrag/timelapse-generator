#!/usr/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
TIMELAPSE_DIR=$(dirname -- "${SCRIPT_DIR}")
source "${TIMELAPSE_DIR}/venv/bin/activate"

DAWN=$(python3 ${SCRIPT_DIR}/sun.py --dawn)
DUSK=$(python3 ${SCRIPT_DIR}/sun.py --dusk)

echo "Dawn is $DAWN"
echo "Dusk is $DUSK"

echo "${SCRIPT_DIR}/move_ftp_images.sh night" | at $DAWN
echo "${SCRIPT_DIR}/move_ftp_images.sh day" | at $DUSK
