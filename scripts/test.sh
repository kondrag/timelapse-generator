#!/usr/bin/bash

echo "Starting timelapse at $(date)"

FTP_PUB=/srv/ftp/pub
cd $FTP_PUB

YESTERDAY=$(date -d "yesterday 13:00" -I)
TODAY=$(date +%Y%m%d)
#mkdir $TODAY
#mv *.jpg $TODAY

cd $TODAY

NUMFILES=$(ls -1 | wc -l)
echo "There are ${NUMFILES} images for the timelapse video."


echo "$(date) - Creating timelapse 360p video..."
time ffmpeg -threads 2 -framerate 30 -pattern_type glob -i "*.jpg" -c:v libx264 -preset veryfast -vf scale=640:360 -pix_fmt yuv420p AuroraCam_${TODAY}_360p.mp4
echo $?
#echo "$(date) - Creating timelapse 1080p video..."
#time ffmpeg -framerate 30 -pattern_type glob -i '*.jpg' -c:v libx264 -preset medium -vf scale=1920:1080 -pix_fmt yuv420p AuroraCam_${DATESTRING}_1080p.mp4
#echo $?

test $? -eq 0 || echo "$(date) - Error creating timelapse" && exit 1

echo "$(date) - Timelapse video created successfully."

