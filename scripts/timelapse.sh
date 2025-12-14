#!/usr/bin/bash

# Definition of global variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"

# Resolution settings
LOW_RES="640x360"
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

generate_timelapse_ffmpeg() {
    local PRESET=$1
    local RESOLUTION=$2
    local INPUT_DIR=$3
    local OUTPUT_FILENAME=$4
    local OUTPUT_FILEPATH="${INPUT_DIR}/${OUTPUT_FILENAME}"

    echo "$(date) - Creating timelapse video with ffmpeg..." >> $LOGFILE
    #pushd "$PWD"
    #cd "$INPUT_DIR"
    nice -n 19 ffmpeg -threads 4 -framerate 60 -pattern_type glob -i "${INPUT_DIR}/*.jpg" -c:v libx264 -threads 4 -preset ${PRESET} -vf scale=${RESOLUTION/x/:} -pix_fmt yuv420p "$OUTPUT_FILEPATH"
    RETVAL="${?}"
    echo "$(date) - timelapse video creation return value: $RETVAL" >> $LOGFILE
    #   popd

    echo "${OUTPUT_FILEPATH}"

    return $RETVAL
}

generate_timelapse() {
    local QUALITY=$1
    local RESOLUTION=$2
    local INPUT_DIR=$3
    local OUTPUT_FILENAME=$4
    echo "$(date) - generate_timelapse() called with: QUALITY=$QUALITY, RESOLUTION=$RESOLUTION, INPUT_DIR=$INPUT_DIR, OUTPUT_FILENAME=$OUTPUT_FILENAME" >> $LOGFILE
    
    echo "$(date) - Creating timelapse ${RESOLUTION} video..." >> $LOGFILE
    TIMELAPSE_GENERATOR_DIR="${SCRIPT_DIR}/../."
    # We cd to the input dir so the output filename is relative. This is a workaround for an issue where
    # the timelapse generator fails when using absolute paths for the output file.
    cd "${INPUT_DIR}" || { echo "Failed to cd to ${INPUT_DIR}" >> $LOGFILE; exit 1; }
    
    # We need to run uv from the project dir, so we use the absolute path to uv/project if needed,
    # or better, just rely on uv finding the project. But wait, TIMELAPSE_GENERATOR_DIR is where the project is.
    # So we should cd to TIMELAPSE_GENERATOR_DIR to run uv, but then the output file path is relative to THAT?
    # The user says "works when output is relative filename".
    # If we run from TIMELAPSE_GENERATOR_DIR, then relative path "OUTPUT_FILENAME" would put it in likely the wrong place unless we use full path.
    # But full path fails.
    # So we must run FROM the directory where we want the file to be, OR passed a relative path like "data/output.mp4".
    
    # Strategy:
    # 1. cd to the directory where we want output (INPUT_DIR, since OUTPUT_FILE is inside it)
    # 2. Run uv run --project <PROJECT_DIR> ... with just filename.
    
    PROJECT_DIR=$(readlink -f "${TIMELAPSE_GENERATOR_DIR}")
    
    # Export config path so the app finds it even when running from data dir
    export TIMELAPSE_CONFIG="${PROJECT_DIR}/config.yaml"
    
    cd "${INPUT_DIR}" || { echo "Failed to cd to ${INPUT_DIR}" >> $LOGFILE; exit 1; }
    
    echo "$(date) - Running timelapse generator from ${INPUT_DIR}" >> $LOGFILE
    uv run --project "${PROJECT_DIR}" timelapse generate --backend ffmpegcv -q ${QUALITY} --resolution ${RESOLUTION} --fps 60 . "${OUTPUT_FILENAME}" --yes --no-progress >> $LOGFILE 2>&1
    RESULT=$?

    echo "${INPUT_DIR}/${OUTPUT_FILENAME}"

    return $RESULT
}

process_day() {
    local SUBDIR="day"
    local PROCESS_DIR=${ARCHIVE_DIR}/${SUBDIR}
    local VIDEO_FILENAME="CloudCam_${TODAY}_${LOW_RES}.mp4"
    
    # Generate Low Res Video
    local VIDEO_PATH=$(generate_timelapse_ffmpeg "veryfast" "${LOW_RES}" "${PROCESS_DIR}" "${VIDEO_FILENAME}")
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
    local VIDEO_PATH_LOW=$(generate_timelapse_ffmpeg "low" "${LOW_RES}" "${PROCESS_DIR}" "${LOW_RES_FILENAME}")
    local RETVAL_LOW=$?
    echo "$(date) VIDEO_PATH_LOW is $VIDEO_PATH_LOW" >> $LOGFILE
    echo "$(date) - Nighttime ${LOW_RES} video creation return value: $RETVAL_LOW" >> $LOGFILE

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
    local VIDEO_PATH_HIGH=$(generate_timelapse_ffmpeg "medium" "${HIGH_RES}" "${PROCESS_DIR}" "${HIGH_RES_FILENAME}")
    local RETVAL_HIGH=$?
    echo "$(date) VIDEO_PATH_HIGH is $VIDEO_PATH_HIGH" >> $LOGFILE
    
    local RETVAL="${RETVAL_LOW}${RETVAL_HIGH}"
    echo "Timelapse generation return values: $RETVAL" >> $LOGFILE
    echo "$(date) - Nighttime timelapse videos created successfully." >> $LOGFILE
    # Files are in /opt/timelapse-generator
    ls -al ${PROCESS_DIR}/*.mp4 >> $LOGFILE
    echo "$(date) - Moving ${VIDEO_PATH_LOW} and ${VIDEO_PATH_HIGH} to archive dir $ARCHIVE_DIR" >> $LOGFILE
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
