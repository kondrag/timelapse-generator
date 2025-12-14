#!/usr/bin/bash

usage() {
    echo "Usage: $0 {day|night}"
    exit 1
}

if [ "$1" != "day" ] && [ "$1" != "night" ]; then
    usage
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"
FTP_DIR=/srv/ftp/aurora
PROCESS_DIR="${ARCHIVE_DIR}/${1}"
USER=greg

echo "===== $(date) - Moving $1 images to $PROCESS_DIR =====" >> $LOGFILE

echo "PATH is $PATH" >> $LOGFILE
echo "PATH is $PATH" >> $LOGFILE
echo "Updated PATH is $PATH" >> $LOGFILE

cd $FTP_DIR
mkdir -p $PROCESS_DIR
chown -R $USER:$USER $ARCHIVE_DIR
chmod -R 0755 $ARCHIVE_DIR

echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
echo "Moving JPG images..." >> $LOGFILE
mv *.jpg $PROCESS_DIR
echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE

cd $PROCESS_DIR
echo "There are $(ls -1 *.jpg | wc -l) images in $(pwd)" >> $LOGFILE
chown $USER:$USER *.jpg
chmod 644 *.jpg
