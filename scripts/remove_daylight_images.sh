#!/usr/bin/bash

LOGFILE=/var/log/timelapse.log
FTP_PUB=/srv/ftp/pub
TIMELAPSE_DIR=/var/local/timelapse
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
PROCESS_DIR=${TIMELAPSE_DIR}/${TODAY}
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

echo "===== Removing daylight images at $(date) =====" >> $LOGFILE

echo "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE

cd $FTP_PUB

echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
echo "Removing JPG images..." >> $LOGFILE
rm -f AuroraCam*.jpg
echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
