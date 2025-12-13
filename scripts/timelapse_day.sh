#!/usr/bin/bash

LOGFILE=/var/log/timelapse.log
FTP_PUB=/srv/ftp/pub
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

cd $FTP_PUB

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
nice -n 19 ffmpeg -threads 4 -framerate 60 -pattern_type glob -i "*.jpg" -c:v libx264 -threads 4 -preset veryfast -vf scale=640:360 -pix_fmt yuv420p CloudCam_${TODAY}_360p.mp4
RETVAL="${?}"

echo "$(date) ffmpeg video creation return value: $RETVAL" >> $LOGFILE

echo "$(date) Finding noon thumbnail image..." >> $LOGFILE
THUMBNAIL=$(find . -name "AuroraCam_00_$(date +%Y%m%d)*.jpg" -newermt "$(date +%Y-%m-%d) 12:00" -type f | sort | head -1)
echo "$(date) Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

if [ "${RETVAL}" = "0" ]; then
  echo "$(date) - Daylight Timelapse video created successfully." >> $LOGFILE
  ls -al *.mp4 >> $LOGFILE
  echo "$(date) - Copying daylight video to weewx" >> $LOGFILE
  cp -v "CloudCam_${TODAY}_360p.mp4" "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.mp4" >> $LOGFILE

  echo "$(date) Resizing thumbnail to 640x360..." >> $LOGFILE
  convert "${THUMBNAIL}" -resize 640x360 "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.thumbnail.jpg"
  RETVAL="${?}"
  echo "$(date) ffmpeg 360p thumbnail creation return value: $RETVAL" >> $LOGFILE

  echo "$(date) - Moving daylight video to archive" >> $LOGFILE
  mv -v "CloudCam_${TODAY}_360p.mp4" $ARCHIVE_DIR >> $LOGFILE
else
  echo "$(date) - Error creating daylight timelapse: Error $RETVAL" >> $LOGFILE
fi

echo "Removing daylight JPG files" >> $LOGFILE
rm -rf $PROCESS_DIR
