#!/usr/bin/bash

# Definition of global variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "${SCRIPT_DIR}/common_env.sh"

# Resolution settings
LOW_RES="640x360"
HIGH_RES="2560x1440"

# Setup logging and path
log "===== Starting timelapse processing for $1 ====="
log "PATH is $PATH"
log "TIMELAPSE_DIR is $TIMELAPSE_DIR"


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
    local INPUT_COUNT DURATION FRAMES

    local BAD_DIR="${INPUT_DIR}/bad_frames"
    local BAD_LIST
    BAD_LIST=$(find "${INPUT_DIR}" -maxdepth 1 -type f -name '*.jpg' \( ! -readable -o -size 0 \) 2>/dev/null)
    if [ -n "${BAD_LIST}" ]; then
        local BAD_COUNT TOTAL_COUNT
        BAD_COUNT=$(printf '%s\n' "${BAD_LIST}" | wc -l)
        TOTAL_COUNT=$(find "${INPUT_DIR}" -maxdepth 1 -type f -name '*.jpg' 2>/dev/null | wc -l)
        if [ "${BAD_COUNT}" -ge "${TOTAL_COUNT}" ]; then
            log "ERROR: all ${TOTAL_COUNT} input image(s) in ${INPUT_DIR} are unreadable/empty - this is a file ownership/permission problem, NOT quarantining. Aborting."
            echo "${OUTPUT_FILEPATH}"
            return 1
        fi
        log "ERROR: ${BAD_COUNT} bad input image(s) (empty or unreadable) in ${INPUT_DIR}; quarantining to ${BAD_DIR}"
        log "bad image samples: $(printf '%s\n' "${BAD_LIST}" | head -3)"
        mkdir -p "${BAD_DIR}"
        printf '%s\n' "${BAD_LIST}" | xargs -d '\n' mv -t "${BAD_DIR}" --
    fi

    INPUT_COUNT=$(ls -1 "${INPUT_DIR}"/*.jpg 2>/dev/null | wc -l)
    log "input images: $(jpg_stats "${INPUT_DIR}")"
    if [ "$INPUT_COUNT" -eq 0 ]; then
        log "ERROR: no JPG images in ${INPUT_DIR} - nothing to encode"
        echo "${OUTPUT_FILEPATH}"
        return 1
    fi
    log "expected video duration at 60 fps: $(awk "BEGIN{printf \"%.1f\", ${INPUT_COUNT}/60}")s"
    log "disk space available for output: $(df --output=avail -h "${INPUT_DIR}" 2>/dev/null | tail -1)"

    log "$(date) - Creating timelapse video with ffmpeg..."
    nice -n 19 ffmpeg -threads 4 -framerate 60 -pattern_type glob -i "${INPUT_DIR}/*.jpg" -c:v libx264 -threads 4 -preset ${PRESET} -vf scale=${RESOLUTION/x/:} -pix_fmt yuv420p "$OUTPUT_FILEPATH" >> $LOGFILE 2>&1
    RETVAL="${?}"
    log "$(date) - timelapse video creation return value: $RETVAL"

    if [ "$RETVAL" -eq 0 ]; then
        DURATION=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUTPUT_FILEPATH" 2>/dev/null)
        FRAMES=$(ffprobe -v error -select_streams v -show_entries stream=nb_frames -of default=nw=1:nk=1 "$OUTPUT_FILEPATH" 2>/dev/null)
        log "output video: duration=${DURATION}s frames=${FRAMES} (input images: ${INPUT_COUNT})"
        if [ -n "$FRAMES" ] && [ "$FRAMES" -ne "$INPUT_COUNT" ]; then
            log "ERROR: output frames=${FRAMES} != input images=${INPUT_COUNT} - video truncated"
            RETVAL=1
        fi
    fi

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

    log "expected day window: dawn $(python3 ${SCRIPT_DIR}/sun.py --dawn 2>/dev/null || echo '?') to dusk $(python3 ${SCRIPT_DIR}/sun.py --dusk 2>/dev/null || echo '?')"

    # If the scheduled move job never ran, recover today's images ourselves
    ${SCRIPT_DIR}/self_heal_move.sh day

    # Generate Low Res Video
    local VIDEO_PATH RETVAL
    VIDEO_PATH=$(generate_timelapse_ffmpeg "veryfast" "${LOW_RES}" "${PROCESS_DIR}" "${VIDEO_FILENAME}")
    RETVAL=$?
    echo "$(date) VIDEO_PATH is $VIDEO_PATH" >> $LOGFILE
    echo "$(date) timelapse video creation return value: $RETVAL" >> $LOGFILE
    
    echo "$(date) Finding noon thumbnail image..." >> $LOGFILE
    local THUMBNAIL=$(find ${PROCESS_DIR} -name "AuroraCam_00_$(date +%Y%m%d)*.jpg" -newermt "$(date +%Y-%m-%d) 12:00" -type f -not -path "*/bad_frames/*" | sort | head -1)
    if [ -n "$THUMBNAIL" ]; then
        echo "$(date) Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE
    else
        echo "$(date) No thumbnail found." >> $LOGFILE
    fi

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

    if [ "${RETVAL}" = "0" ]; then
        log "Removing daylight JPG files and process dir"
        rm -rf $PROCESS_DIR
    else
        log "ERROR: day timelapse failed - keeping $PROCESS_DIR for inspection/retry"
    fi
}

process_night() {
    cleanup_old_dirs
    local SUBDIR="night"
    local PROCESS_DIR=${ARCHIVE_DIR}/${SUBDIR}
    local LOW_RES_FILENAME="AuroraCam_${TODAY}_${LOW_RES}.mp4"
    local HIGH_RES_FILENAME="AuroraCam_${TODAY}_${HIGH_RES}.mp4"

    log "expected night window: dusk $(python3 ${SCRIPT_DIR}/sun.py --dusk 2>/dev/null || echo '?') yesterday to dawn $(python3 ${SCRIPT_DIR}/sun.py --dawn 2>/dev/null || echo '?') today"

    # If the scheduled move job never ran, recover last night's images ourselves
    ${SCRIPT_DIR}/self_heal_move.sh night

    # Generate Low Res
    local VIDEO_PATH_LOW RETVAL_LOW
    VIDEO_PATH_LOW=$(generate_timelapse_ffmpeg "veryfast" "${LOW_RES}" "${PROCESS_DIR}" "${LOW_RES_FILENAME}")
    RETVAL_LOW=$?
    echo "$(date) VIDEO_PATH_LOW is $VIDEO_PATH_LOW" >> $LOGFILE
    echo "$(date) - Nighttime ${LOW_RES} video creation return value: $RETVAL_LOW" >> $LOGFILE

    echo "Finding midnight thumbnail image..." >> $LOGFILE
    local THUMBNAIL=$(ls ${PROCESS_DIR}/AuroraCam_00_$(date +%Y%m%d)*.jpg 2>/dev/null | sort | head -1)
    if [ -n "$THUMBNAIL" ]; then
        echo "Using ${THUMBNAIL} as thumbnail image" >> $LOGFILE
    else
        echo "No thumbnail found." >> $LOGFILE
    fi

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

    # download spaceweather
    ${SCRIPT_DIR}/fetch_spaceweather.sh

    # Generate High Res
    local VIDEO_PATH_HIGH RETVAL_HIGH
    VIDEO_PATH_HIGH=$(generate_timelapse_ffmpeg "medium" "${HIGH_RES}" "${PROCESS_DIR}" "${HIGH_RES_FILENAME}")
    RETVAL_HIGH=$?
    echo "$(date) VIDEO_PATH_HIGH is $VIDEO_PATH_HIGH" >> $LOGFILE
    
    log "Timelapse generation return values: LOW=$RETVAL_LOW HIGH=$RETVAL_HIGH"
    if [ "$RETVAL_LOW" -eq 0 ] && [ "$RETVAL_HIGH" -eq 0 ]; then
        log "$(date) - Nighttime timelapse videos created successfully."
    else
        log "$(date) - ERROR: nighttime timelapse incomplete (LOW=$RETVAL_LOW HIGH=$RETVAL_HIGH)"
    fi

    local VF MOVED=0
    for VF in "${VIDEO_PATH_LOW}" "${VIDEO_PATH_HIGH}"; do
        if [ -f "${VF}" ]; then
            ls -al "${VF}" >> $LOGFILE 2>&1
            mv -v "${VF}" $ARCHIVE_DIR >> $LOGFILE 2>&1
            MOVED=1
        fi
    done
    if [ "$MOVED" -eq 0 ]; then
        log "no completed videos to move to $ARCHIVE_DIR"
    fi

    if [ "$RETVAL_LOW" -eq 0 ] && [ "$RETVAL_HIGH" -eq 0 ]; then
        log "Removing processing dir $PROCESS_DIR"
        rm -rf $PROCESS_DIR
    else
        log "ERROR: night timelapse failed - keeping $PROCESS_DIR for inspection/retry"
    fi
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
