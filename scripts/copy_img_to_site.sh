#!/usr/bin/bash

# Copy the latest image from the FTP directory to the site directory
# and resize it to 1280x720
# Usage: $0 <camera_name> <site_name>

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <camera_name> <site_name>"
    exit 1
fi


CAMERA_NAME="$1"
SITE_NAME="$2"
FTP_DIR="/srv/ftp/$CAMERA_NAME"
WEEWX_DIR="/tmp/weewx"
SITE_DIR="$WEEWX_DIR/$SITE_NAME"

cd $FTP_DIR
latest=$(ls -t *.jpg | head -n 2 | tail -n 1)

RETVAL=$?

if [ "$RETVAL" = "0" ]; then
    convert "$latest" -resize "1280x720" "$SITE_DIR/latest.jpg"
fi
