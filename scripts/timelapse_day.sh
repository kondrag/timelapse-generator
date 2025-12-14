#!/usr/bin/bash

LOGFILE=/var/log/timelapse.log
FTP_DIR=/srv/ftp/pub/aurora
TIMELAPSE_DIR=/var/local/timelapse/
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
ARCHIVE_DIR=${TIMELAPSE_DIR}/${TODAY}
PROCESS_DIR=${ARCHIVE_DIR}/day
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

echo "===== Starting daylight timelapse processing at $(date) =====" >> $LOGFILE

echo "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE

cd $FTP_DIR

echo "There are $(ls -1 *.jpg | wc -l) daylight images in $(pwd)" >> $LOGFILE
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

echo "$(date) - Creating timelapse video..." >> $LOGFILE
cd /opt/timelapse-generator
RESOLUTION="720x480"
VIDEO_FILENAME="CloudCam_${TODAY}_${RESOLUTION}.mp4"
VIDEO_DAY_FILENAME="CloudCam_${DAY}.mp4"
uv run timelapse generate -q medium --resolution ${RESOLUTION} --framerate 60 $PROCESS_DIR $VIDEO_FILENAME
RETVAL="${?}"

echo "$(date) timelapse video creation return value: $RETVAL" >> $LOGFILE

echo "$(date) Finding noon thumbnail image..." >> $LOGFILE
THUMBNAIL=$(find . -name "AuroraCam_00_$(date +%Y%m%d)*.jpg" -newermt "$(date +%Y-%m-%d) 12:00" -type f | sort | head -1)
echo "$(date) Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

if [ "${RETVAL}" = "0" ]; then
  echo "$(date) - Daylight Timelapse video created successfully." >> $LOGFILE
  ls -al *.mp4 >> $LOGFILE
  echo "$(date) - Copying daylight video to weewx" >> $LOGFILE
  cp -v "$VIDEO_FILENAME" "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.mp4" >> $LOGFILE

  echo "$(date) Resizing thumbnail to ${RESOLUTION}..." >> $LOGFILE
  convert "${THUMBNAIL}" -resize ${RESOLUTION} "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.thumbnail.jpg"
  RETVAL="${?}"
  echo "$(date) thumbnail creation return value: $RETVAL" >> $LOGFILE

  echo "$(date) - Moving daylight video to archive" >> $LOGFILE
  mv -v "$VIDEO_FILENAME" $ARCHIVE_DIR >> $LOGFILE
else
  echo "$(date) - Error creating daylight timelapse: Error $RETVAL" >> $LOGFILE
fi

echo "Removing daylight JPG files" >> $LOGFILE
rm -rf $PROCESS_DIR
