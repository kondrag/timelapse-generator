#!/usr/bin/bash

# Definition of global variables
LOGFILE=/var/log/timelapse.log
FTP_DIR=/srv/ftp/aurora
TIMELAPSE_DIR=/var/local/timelapse
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
ARCHIVE_DIR=${TIMELAPSE_DIR}/${TODAY}
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

# Resolution settings
LOW_RES="720x480"
HIGH_RES="2560x1440"

# Setup logging and path
echo "===== Starting timelapse processing for $1 at $(date) =====" >> $LOGFILE
echo "PATH is $PATH" >> $LOGFILE
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
echo "Updated PATH is $PATH" >> $LOGFILE


cleanup_old_dirs() {
    echo "Removing directories older than 21 days from $TIMELAPSE_DIR" >> $LOGFILE
    find $TIMELAPSE_DIR -type d -mtime +21 -print -exec rm -rf {} + >> $LOGFILE
}

prepare_files() {
    local SUBDIR=$1
    local PROCESS_DIR=${ARCHIVE_DIR}/${SUBDIR}

    cd $FTP_DIR || { echo "Failed to cd to $FTP_DIR" >> $LOGFILE; exit 1; }

    echo "There are $(ls -1 *.jpg 2>/dev/null | wc -l) images in $(pwd)" >> $LOGFILE
    echo "Moving JPG images to ${PROCESS_DIR} directory..." >> $LOGFILE

    mkdir -p $PROCESS_DIR
    mv AuroraCam*.jpg $PROCESS_DIR 2>/dev/null

    echo "Changing to $PROCESS_DIR" >> $LOGFILE
    cd $PROCESS_DIR || { echo "Failed to cd to $PROCESS_DIR" >> $LOGFILE; exit 1; }

    echo "Working directory is now $(pwd)" >> $LOGFILE
    echo "There are $(ls -1 | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE

    latest=$(ls -t *.jpg 2>/dev/null | head -n 1)
    if [ -n "$latest" ]; then
        echo "Removing latest image: $latest" >> $LOGFILE
        rm -f $latest
    fi
    echo "There are $(ls -1 *.jpg 2>/dev/null | wc -l) images for the timelapse video in $(pwd)." >> $LOGFILE
    
    echo "$PROCESS_DIR"
}

generate_timelapse() {
    local QUALITY=$1
    local RESOLUTION=$2
    local OUTPUT_FILENAME=$3
    local INPUT_DIR=$4
    
    echo "$(date) - Creating timelapse ${RESOLUTION} video..." >> $LOGFILE
    cd /opt/timelapse-generator || { echo "Failed to cd to /opt/timelapse-generator" >> $LOGFILE; exit 1; }
    
    uv run timelapse generate -q ${QUALITY} --resolution ${RESOLUTION} --framerate 60 $INPUT_DIR $OUTPUT_FILENAME
    return $?
}

process_day() {
    local PROCESS_DIR=$(prepare_files "day")
    local VIDEO_FILENAME="CloudCam_${TODAY}_${LOW_RES}.mp4"
    local VIDEO_PATH="/opt/timelapse-generator/${VIDEO_FILENAME}"
    
    # Generate Low Res Video
    generate_timelapse "medium" "${LOW_RES}" "${VIDEO_FILENAME}" "${PROCESS_DIR}"
    local RETVAL=$?
    echo "$(date) timelapse video creation return value: $RETVAL" >> $LOGFILE
    
    echo "$(date) Finding noon thumbnail image..." >> $LOGFILE
    local THUMBNAIL=$(find ${PROCESS_DIR} -name "AuroraCam_00_$(date +%Y%m%d)*.jpg" -newermt "$(date +%Y-%m-%d) 12:00" -type f | sort | head -1)
    echo "$(date) Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

    if [ "${RETVAL}" = "0" ]; then
        echo "$(date) - Daylight Timelapse video created successfully." >> $LOGFILE
        ls -al "${VIDEO_PATH}" >> $LOGFILE
        
        echo "$(date) - Copying daylight video to weewx" >> $LOGFILE
        cp -v "${VIDEO_PATH}" "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.mp4" >> $LOGFILE

        if [ -f "$THUMBNAIL" ]; then
            echo "$(date) Resizing thumbnail to ${LOW_RES}..." >> $LOGFILE
            convert "${THUMBNAIL}" -resize ${LOW_RES} "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY}.thumbnail.jpg"
            echo "$(date) thumbnail creation return value: $?" >> $LOGFILE
        else
            echo "$(date) No thumbnail found." >> $LOGFILE
        fi

        echo "$(date) - Moving daylight video to archive" >> $LOGFILE
        mv -v "${VIDEO_PATH}" $ARCHIVE_DIR >> $LOGFILE
    else
        echo "$(date) - Error creating daylight timelapse: Error $RETVAL" >> $LOGFILE
    fi

    echo "Removing daylight JPG files and process dir" >> $LOGFILE
    rm -rf $PROCESS_DIR
}

process_night() {
    cleanup_old_dirs
    local PROCESS_DIR=$(prepare_files "night")
    local LOW_RES_FILENAME="AuroraCam_${TODAY}_${LOW_RES}.mp4"
    local HIGH_RES_FILENAME="AuroraCam_${TODAY}_${HIGH_RES}.mp4"
    
    # Generate Low Res
    generate_timelapse "medium" "${LOW_RES}" "${LOW_RES_FILENAME}" "${PROCESS_DIR}"
    local RETVAL_LOW=$?
    echo "$(date) - Nighttime ${LOW_RES} video creation return value: $RETVAL_LOW" >> $LOGFILE

    echo "Finding midnight thumbnail image..." >> $LOGFILE
    local THUMBNAIL=$(ls ${PROCESS_DIR}/AuroraCam_00_$(date +%Y%m%d)*.jpg 2>/dev/null | sort | head -1)
    echo "Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

    if [ "${RETVAL_LOW}" = "0" ]; then
        echo "$(date) - Copying ${LOW_RES} video to weewx" >> $LOGFILE
        # Move low res output to full path location if generate_timelapse output it to local dir (it currently outputs to PWD which is /opt/timelapse-generator when running uv run)
        # Note: uv run command uses $OUTPUT_FILENAME relative to PWD.
        # Let's assume files are in /opt/timelapse-generator because of cd.
        
        cp -v "/opt/timelapse-generator/${LOW_RES_FILENAME}" "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.mp4" >> $LOGFILE
        
        if [ -f "$THUMBNAIL" ]; then
            echo "Resizing thumbnail to ${LOW_RES}..." >> $LOGFILE
            convert "${THUMBNAIL}" -resize ${LOW_RES} "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.thumbnail.jpg"
            echo "Thumbnail creation return value: $?" >> $LOGFILE 
        fi
    fi

    # Generate High Res
    generate_timelapse "high" "${HIGH_RES}" "${HIGH_RES_FILENAME}" "${PROCESS_DIR}"
    local RETVAL_HIGH=$?
    
    local RETVAL="${RETVAL_LOW}${RETVAL_HIGH}"
    echo "Timelapse generation return values: $RETVAL" >> $LOGFILE

    # NOAA Data
    wget -v https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json -O "${ARCHIVE_DIR}/k-index_${TODAY}.json" >> $LOGFILE
    wget -v https://services.swpc.noaa.gov/images/swx-overview-large.gif -O "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" >> $LOGFILE
    cp -v "${ARCHIVE_DIR}/SpaceWeather_${TODAY}.gif" "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_${DAY}.gif" >> $LOGFILE

    if [ "${RETVAL}" != "00" ]; then
      echo "$(date) - Error creating timelapse: Error $RETVAL" >> $LOGFILE
      exit 1
    fi

    echo "$(date) - Nighttime timelapse videos created successfully." >> $LOGFILE
    # Files are in /opt/timelapse-generator
    ls -al /opt/timelapse-generator/*.mp4 >> $LOGFILE
    echo "$(date) - Moving videos to archive dir $ARCHIVE_DIR" >> $LOGFILE
    mv -v /opt/timelapse-generator/*.mp4 $ARCHIVE_DIR >> $LOGFILE

    echo "Removing processing dir $PROCESS_DIR" >> $LOGFILE
    rm -rf $PROCESS_DIR
}

usage() {
    echo "Usage: $0 {day|night}"
    exit 1
}

case "$1" in
    day)
        process_day
        ;;
    night)
        process_night
        ;;
    *)
        usage
        ;;
esac
