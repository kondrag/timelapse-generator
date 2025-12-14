#!/usr/bin/bash

# Definition of global variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"

# Resolution settings
LOW_RES="720x404"
HIGH_RES="2560x1440"

# Setup logging and path
echo "===== Starting timelapse processing for $1 at $(date) =====" >> $LOGFILE
echo "PATH is $PATH" >> $LOGFILE
echo "TIMELAPSE_DIR is $TIMELAPSE_DIR" >> $LOGFILE
echo "Updated PATH is $PATH" >> $LOGFILE


cleanup_old_dirs() {
    echo "Removing directories older than 30 days from $TIMELAPSE_DIR" >> $LOGFILE
    find $TIMELAPSE_DIR -type d -mtime +30 -print -exec rm -rf {} + >> $LOGFILE
}

generate_timelapse() {
    local QUALITY=$1
    local RESOLUTION=$2
    local INPUT_DIR=$3
    local OUTPUT_FILENAME=$4
    echo "$(date) - generate_timelapse() called with: QUALITY=$QUALITY, RESOLUTION=$RESOLUTION, INPUT_DIR=$INPUT_DIR, OUTPUT_FILENAME=$OUTPUT_FILENAME" >> $LOGFILE
    
    echo "$(date) - Creating timelapse ${RESOLUTION} video..." >> $LOGFILE
    TIMELAPSE_GENERATOR_DIR="${SCRIPT_DIR}/../." 
    cd "${TIMELAPSE_GENERATOR_DIR}" || { echo "Failed to cd to ${TIMELAPSE_GENERATOR_DIR}" >> $LOGFILE; exit 1; }
    
    OUTPUT_FILE=${INPUT_DIR}/${OUTPUT_FILENAME}
    echo "$(date) - Running timelapse generator with options: -q ${QUALITY} --resolution ${RESOLUTION} --fps 60 $INPUT_DIR ${OUTPUT_FILE}" >> $LOGFILE
    
    uv run timelapse generate -q ${QUALITY} --resolution ${RESOLUTION} --fps 60 $INPUT_DIR "${OUTPUT_FILE}" --yes >> $LOGFILE 2>&1

    echo "${OUTPUT_FILE}"

    return $?
}

process_day() {
    local SUBDIR="day"
    local PROCESS_DIR=${ARCHIVE_DIR}/${SUBDIR}
    local VIDEO_FILENAME="CloudCam_${TODAY}_${LOW_RES}.mp4"
    
    # Generate Low Res Video
    local VIDEO_PATH=$(generate_timelapse "medium" "${LOW_RES}" "${PROCESS_DIR}" "${VIDEO_FILENAME}")
    local RETVAL=$?
    echo "$(date) VIDEO_PATH is $VIDEO_PATH" >> $LOGFILE
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
    #rm -rf $PROCESS_DIR
}

process_night() {
    cleanup_old_dirs
    local SUBDIR="night"
    local PROCESS_DIR=${ARCHIVE_DIR}/${SUBDIR}
    local LOW_RES_FILENAME="AuroraCam_${TODAY}_${LOW_RES}.mp4"
    local HIGH_RES_FILENAME="AuroraCam_${TODAY}_${HIGH_RES}.mp4"
    
    # Generate Low Res
    local VIDEO_PATH_LOW=$(generate_timelapse "medium" "${LOW_RES}" "${PROCESS_DIR}" "${LOW_RES_FILENAME}")
    local RETVAL_LOW=$?
    echo "$(date) VIDEO_PATH is $VIDEO_PATH" >> $LOGFILE
    echo "$(date) - Nighttime ${LOW_RES} video creation return value: $RETVAL_LOW" >> $LOGFILE
    exit 0

    echo "Finding midnight thumbnail image..." >> $LOGFILE
    local THUMBNAIL=$(ls ${PROCESS_DIR}/AuroraCam_00_$(date +%Y%m%d)*.jpg 2>/dev/null | sort | head -1)
    echo "Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE

    if [ "${RETVAL_LOW}" = "0" ]; then
        echo "$(date) - Copying ${LOW_RES} video to weewx" >> $LOGFILE
        # Move low res output to full path location if generate_timelapse output it to local dir (it currently outputs to PWD which is /opt/timelapse-generator when running uv run)
        # Note: uv run command uses $OUTPUT_FILENAME relative to PWD.
        # Let's assume files are in /opt/timelapse-generator because of cd.
        
        cp -v "${VIDEO_PATH_LOW}" "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.mp4" >> $LOGFILE
        
        if [ -f "$THUMBNAIL" ]; then
            echo "Resizing thumbnail to ${LOW_RES}..." >> $LOGFILE
            convert "${THUMBNAIL}" -resize ${LOW_RES} "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY}.thumbnail.jpg"
            echo "Thumbnail creation return value: $?" >> $LOGFILE 
        fi
    fi

    # Generate High Res
    local VIDEO_PATH_HIGH=$(generate_timelapse "high" "${HIGH_RES}" "${PROCESS_DIR}" "${HIGH_RES_FILENAME}")
    local RETVAL_HIGH=$?
    
    local RETVAL="${RETVAL_LOW}${RETVAL_HIGH}"
    echo "Timelapse generation return values: $RETVAL" >> $LOGFILE
    echo "$(date) - Nighttime timelapse videos created successfully." >> $LOGFILE
    # Files are in /opt/timelapse-generator
    ls -al ${PROCESS_DIR}/*.mp4 >> $LOGFILE
    echo "$(date) - Moving videos to archive dir $ARCHIVE_DIR" >> $LOGFILE
    mv -v ${VIDEO_PATH_LOW} ${VIDEO_PATH_HIGH} $ARCHIVE_DIR >> $LOGFILE

    echo "Removing processing dir $PROCESS_DIR" >> $LOGFILE
    #rm -rf $PROCESS_DIR
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
