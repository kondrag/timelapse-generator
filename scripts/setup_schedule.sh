#!/usr/bin/bash

SCRIPT_DIR=$(dirname -- "${BASH_SOURCE[0]}")
source "${SCRIPT_DIR}/venv/bin/activate"

DAWN=$(python ${SCRIPT_DIR}/sun.py --dawn)
DUSK=$(python ${SCRIPT_DIR}/sun.py --dusk)

echo "Dawn is $DAWN"
echo "Dusk is $DUSK"

at $DAWN < ${SCRIPT_DIR}/timelapse_night.sh
at $DUSK < ${SCRIPT_DIR}/timelapse_day.sh

