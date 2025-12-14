#!/usr/bin/bash

usage() {
    echo "Usage: $0 {day|night}"
    exit 1
}

if [ "$1" != "day" ] && [ "$1" != "night" ]; then
    usage
fi

LOGFILE=/var/log/timelapse.log
FTP_DIR=/srv/ftp/aurora
TIMELAPSE_DIR=/var/local/timelapse
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
PROCESS_DIR="${TIMELAPSE_DIR}/${TODAY}/${1}"
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora
USER=www-data

echo "===== $(date) - Moving $1 images to $PROCESS_DIR =====" >> $LOGFILE

echo "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE

cd $FTP_DIR
mkdir -p $PROCESS_DIR
chown $USER:$USER $PROCESS_DIR

echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
echo "Moving JPG images..." >> $LOGFILE
mv *.jpg $PROCESS_DIR
echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE

cd $PROCESS_DIR
echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
chown $USER:$USER *.jpg
chmod 664 *.jpg
