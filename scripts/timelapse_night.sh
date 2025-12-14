#!/usr/bin/bash

LOGFILE=/var/log/timelapse.log
FTP_DIR=/srv/ftp/pub/aurora
TIMELAPSE_DIR=/var/local/timelapse
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
ARCHIVE_DIR=${TIMELAPSE_DIR}/${TODAY}
PROCESS_DIR=${ARCHIVE_DIR}/night
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

echo "===== Starting nighttime timelapse processing at $(date) =====" >> $LOGFILE

 "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE

echo "Removing directories older than 21 days from $TIMELAPSE_DIR" >> $LOGFILE
find $TIMELAPSE_DIR -type d -mtime +21 -print -exec rm -rf {} + >> $LOGFILE

cd $FTP_DIR

echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
echo "Moving JPG images to ${PROCESS_DIR} directory..." >> $LOGFILE

mkdir -p $PROCESS_DIR
mv AuroraCam*.jpg $PROCESS_DIR

echo "Changing to $TODAY directory" >> $LOGFILE
cd $PROCESS_DIR

echo "Working directory is now $(pwd)" >> $LOGFILE
echo "There are $(ls -1 | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE

latest=$(ls -t *.jpg | head -n 1)
echo "Removing latest image: $latest" >> $LOGFILE
rm -f $latest
echo "There are $(ls -1 *.jpg | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE

echo "$(date) - Creating nighttime timelapse 720x480 video..." >> $LOGFILE
cd /opt/timelapse-generator
LOW_RES="720x480"
LOW_RES_FILENAME="AuroraCam_${TODAY}_${LOW_RES}.mp4"
uv run timelapse generate -q medium --resolution ${LOW_RES} --framerate 60 $PROCESS_DIR $LOW_RES_FILENAME
RETVAL_LOW=$?

echo "$(date) - Nighttime ${LOW_RES} video creation return value: $RETVAL_LOW" >> $LOGFILE

echo "Finding midnight thumbnail image..." >> $LOGFILE
THUMBNAIL=$(ls ${PROCESS_DIR}/AuroraCam_00_$(date +%Y%m%d)*.jpg 2>/dev/null | sort | head -1)
echo "Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

if [ "${RETVAL_LOW}" = "0" ]; then
  echo "$(date) - Copying ${LOW_RES} video to weewx" >> $LOGFILE
  cp -v "$LOW_RES_FILENAME" "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.mp4" >> $LOGFILE
  echo "Resizing thumbnail to ${LOW_RES}..." >> $LOGFILE
  convert "${THUMBNAIL}" -resize ${LOW_RES} "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.thumbnail.jpg"
  RETVAL_THUMB="${?}"
  echo "Thumbnail creation return value: $RETVAL_THUMB" >> $LOGFILE 
fi

echo "$(date) - Creating nighttime timelapse 2560x1440 video..." >> $LOGFILE
HIGH_RES="2560x1440"
HIGH_RES_FILENAME="AuroraCam_${TODAY}_${HIGH_RES}.mp4"
uv run timelapse generate -q high --resolution ${HIGH_RES} --framerate 60 $PROCESS_DIR $HIGH_RES_FILENAME
RETVAL_HIGH=$?

RETVAL="${RETVAL_LOW}${RETVAL_HIGH}"

echo "Timelapse generation return values: $RETVAL" >> $LOGFILE

wget -v https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json -O "${ARCHIVE_DIR}/k-index_${TODAY}.json" >> $LOGFILE
wget -v https://services.swpc.noaa.gov/images/swx-overview-large.gif -O "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" >> $LOGFILE
cp -v "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_${DAY}.gif" >> $LOGFILE

if [ "${RETVAL}" != "00" ]; then
  echo "$(date) - Error creating timelapse: Error $RETVAL" >> $LOGFILE
  exit 1
fi

echo "$(date) - Nighttime timelapse videos created successfully." >> $LOGFILE
ls -al *.mp4 >> $LOGFILE
echo "$(date) - Moving videos to archive dir $ARCHIVE_DIR" >> $LOGFILE
mv -v *.mp4 $ARCHIVE_DIR >> $LOGFILE

#echo "Uploading video to YouTube..." >> $LOGFILE
#youtube_upload
#test $? -eq 0 || echo "Error uploading to YouTube" && exit 1

echo "Removing processing dir $PROCESS_DIR" >> $LOGFILE
rm -rf $PROCESS_DIR
