#!/usr/bin/bash

FTP_DIR=/srv/ftp/pub
WEEWX_DIR=/tmp/weewx/aurora

mkdir -p $WEEWX_DIR
cd $FTP_DIR
latest=$(ls -t *.jpg | head -n 2 | tail -n 1)

RETVAL=$?

if [ "$RETVAL" = "0" ]; then
    convert "$latest" -resize "1280x720" "$WEEWX_DIR/snapshot.jpg"
fi
