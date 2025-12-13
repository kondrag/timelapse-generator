#!/usr/bin/bash

LOGFILE=/var/log/timelapse.log
FTP_PUB=/srv/ftp/pub
TIMELAPSE_DIR=/var/local/timelapse
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
PROCESS_DIR=${TIMELAPSE_DIR}/${TODAY}
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

echo "===== Starting timelapse processing at $(date) =====" >> $LOGFILE

 "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE

echo "Removing directories older than 21 days from $TIMELAPSE_DIR" >> $LOGFILE
find $TIMELAPSE_DIR -type d -mtime +21 -print -exec rm -rf {} + >> $LOGFILE

cd $FTP_PUB

echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
echo "Moving JPG images to ${PROCESS_DIR} directory..." >> $LOGFILE

mkdir $PROCESS_DIR
mv AuroraCam*.jpg $PROCESS_DIR

echo "Changing to $TODAY directory" >> $LOGFILE
cd $PROCESS_DIR

echo "Working directory is now $(pwd)" >> $LOGFILE
echo "There are $(ls -1 | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE

latest=$(ls -t *.jpg | head -n 1)
echo "Removing latest image: $latest" >> $LOGFILE
rm -f $latest
echo "There are $(ls -1 *.jpg | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE

echo "$(date) - Creating timelapse 360p video..." >> $LOGFILE
nice -n 19 ffmpeg -threads 4 -framerate 60 -pattern_type glob -i "*.jpg" -c:v libx264 -threads 4 -preset veryfast -vf scale=640:360 -pix_fmt yuv420p AuroraCam_${TODAY}_360p.mp4
RETVAL="${?}"

echo "ffmpeg 360p return value: $RETVAL" >> $LOGFILE

if [ "${RETVAL}" = "0" ]; then
  echo "$(date) - Linking 360p video to weewx"
  cp -v "AuroraCam_${TODAY}_360p.mp4" "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.mp4" >> $LOGFILE
fi

echo "$(date) - Creating timelapse 1080p video..." >> $LOGFILE
nice -n 19 ffmpeg -threads 3 -framerate 60 -pattern_type glob -i "*.jpg" -c:v libx264 -threads 3 -preset medium -vf scale=1920:1080 -pix_fmt yuv420p AuroraCam_${TODAY}_1080p.mp4
RETVAL="${RETVAL}${?}"

#echo "$(date) - Creating timelapse 1440p video..." >> $LOGFILE
#nice -n 19 ffmpeg -threads 3 -framerate 30 -pattern_type glob -i "*.jpg" -c:v libx264 -threads 3 -preset medium -vf scale=2560:1440 -pix_fmt yuv420p AuroraCam_${TODAY}_1440p.mp4
#RETVAL="${RETVAL}${?}"

echo "ffmpeg return values: $RETVAL" >> $LOGFILE

wget -v https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json -O "k-index_${TODAY}.json" >> $LOGFILE
wget -v https://services.swpc.noaa.gov/images/swx-overview-large.gif -O "SpaceWeather_${TODAY}.gif" >> $LOGFILE
cp -v "SpaceWeather_${TODAY}.gif" "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_${DAY}.gif" >> $LOGFILE

if [ "${RETVAL}" != "00" ]; then
  echo "$(date) - Error creating timelapse: Error $RETVAL" >> $LOGFILE
  exit 1
fi

echo "$(date) - Timelapse video created successfully." >> $LOGFILE
ls -al *.mp4 >> $LOGFILE

#echo "Uploading video to YouTube..." >> $LOGFILE
#youtube_upload
#test $? -eq 0 || echo "Error uploading to YouTube" && exit 1

echo "Removing JPG files" >> $LOGFILE
rm AuroraCam*.jpg
echo "There are $(ls -1 | wc -l) files in $(pwd)." >> $LOGFILE
