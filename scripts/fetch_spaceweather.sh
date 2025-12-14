#!/usr/bin/bash

# Definition of global variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"

echo "===== Fetching Space Weather Data at $(date) =====" >> $LOGFILE

# NOAA Data
echo "Fetching NOAA planetary K-index..." >> $LOGFILE
wget -v https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json -O "${ARCHIVE_DIR}/k-index_${TODAY}.json" >> $LOGFILE
echo "Fetching NOAA Space Weather Overview..." >> $LOGFILE
wget -v https://services.swpc.noaa.gov/images/swx-overview-large.gif -O "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" >> $LOGFILE

echo "Copying Space Weather GIF to weewx directory..." >> $LOGFILE
cp -v "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_${DAY}.gif" >> $LOGFILE

echo "===== Space Weather Data Fetch Complete at $(date) =====" >> $LOGFILE
