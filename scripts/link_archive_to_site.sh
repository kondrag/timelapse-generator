#!/usr/bin/bash

# Restore the 7-day rolling media window in the weewx staging directory
# (/tmp/weewx/aurora) from the persistent timelapse archive
# (/var/local/timelapse/<YYYYMMDD>/). /tmp is wiped on reboot; the archive
# is not. Run from cron every 5 minutes (as greg; /tmp/weewx/aurora is
# weewx:weewx 775 and greg is in the weewx group).
#
# Also stages a 35-day date-named tree (d/<YYYYMMDD> -> archive dir) for
# the Timelapses calendar page, which the skin scanner reads under the
# same /cam alias, plus five *_latest.* links refreshed every run for
# the gallery's "Latest" card.
#
# Safety: a destination file is ONLY replaced when absent. The daily
# pipeline publishes with `cp` BEFORE archiving with `mv`, so an existing
# destination is always the pipeline's own real file — linking under it
# would let that cp write through into the archive original.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd )"
source "${SCRIPT_DIR}/common_env.sh"

mkdir -p "${WEEWX_TIMELAPSE_DIR}" 2>/dev/null || {
    log "link_archive: cannot create ${WEEWX_TIMELAPSE_DIR}"
    exit 1
}

NOW_EPOCH=$(date +%s)

# link_if_absent <archive_src> <staged_dest> <min_age_seconds>
link_if_absent() {
    local SRC=$1 DEST=$2 MIN_AGE=${3:-0}
    [ -e "${SRC}" ] || return 0          # nothing archived for this day
    [ -e "${DEST}" ] && return 0         # pipeline's real file, or link already live
    if [ "${MIN_AGE}" -gt 0 ]; then
        # Skip freshly published files still inside the cp-then-mv window.
        local AGE=$(( NOW_EPOCH - $(stat -c %Y "${SRC}") ))
        [ "${AGE}" -lt "${MIN_AGE}" ] && return 0
    fi
    ln -sfn "${SRC}" "${DEST}" && log "link_archive: linked ${DEST} -> ${SRC}"
}

# synth_thumb_if_missing <Cam> <YYYYMMDD> <archive_dir>
# Days published before thumbnails were archived (and any reboot gap) have
# no <Cam>_<D>.thumbnail.jpg. Synthesize one from the archived 640x360
# video's first frame so the gallery card gets a real image; it then links
# like any other archived file.
synth_thumb_if_missing() {
    local CAM=$1 D=$2 ARC=$3
    local VID="${ARC}/${CAM}_${D}_640x360.mp4"
    local THB="${ARC}/${CAM}_${D}.thumbnail.jpg"
    [ -e "${THB}" ] && return 0
    [ -e "${VID}" ] || return 0
    # Grab the midpoint frame — a more representative sample than the
    # first frame (night videos start near-dark, day videos at dawn).
    local MID
    MID=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${VID}" 2>/dev/null \
          | awk '{ printf "%.2f", $1 / 2 }')
    [ -n "${MID}" ] || MID=0.5
    if ffmpeg -loglevel error -y -ss "${MID}" -i "${VID}" -frames:v 1 "${THB}"; then
        # Inherit the video's mtime: the thumbnail is as old as its source
        # frame, and this also satisfies the today-file age gate above.
        touch -r "${VID}" "${THB}"
        log "link_archive: synthesized ${THB}"
    else
        rm -f "${THB}"
        log "link_archive: ffmpeg failed for ${THB}"
    fi
}

for OFFSET in 6 5 4 3 2 1 0; do
    D=$(date -d "-${OFFSET} days" +%Y%m%d)
    DAY_NAME=$(date -d "-${OFFSET} days" +%A)
    ARC="${TIMELAPSE_DIR}/${D}"

    # Today (offset 0): only files archived more than 2 hours ago, well
    # clear of the publish race. Past days publish unconditionally.
    MIN_AGE=0
    [ "${OFFSET}" -eq 0 ] && MIN_AGE=$(( 2 * 3600 ))

    synth_thumb_if_missing AuroraCam "${D}" "${ARC}"
    synth_thumb_if_missing CloudCam  "${D}" "${ARC}"

    link_if_absent "${ARC}/AuroraCam_${D}_640x360.mp4"      "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY_NAME}.mp4"           "${MIN_AGE}"
    link_if_absent "${ARC}/AuroraCam_${D}.thumbnail.jpg"    "${WEEWX_TIMELAPSE_DIR}/AuroraCam_${DAY_NAME}.thumbnail.jpg" "${MIN_AGE}"
    link_if_absent "${ARC}/CloudCam_${D}_640x360.mp4"       "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY_NAME}.mp4"            "${MIN_AGE}"
    link_if_absent "${ARC}/CloudCam_${D}.thumbnail.jpg"     "${WEEWX_TIMELAPSE_DIR}/CloudCam_${DAY_NAME}.thumbnail.jpg"  "${MIN_AGE}"
    link_if_absent "${ARC}/SpaceWeather_${D}.gif"           "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_${DAY_NAME}.gif"        "${MIN_AGE}"
done

# Date-named tree for the Timelapses calendar: d/<YYYYMMDD> -> archive dir.
# No today-age gate needed here: nothing writes *through* these links (the
# pipeline only publishes weekday-named real files at the staging root),
# and the skin scanner lists a day's media only once the completed files
# have been mv'd to the top of the archive dir.
DATE_LINK_DIR="${WEEWX_TIMELAPSE_DIR}/d"
mkdir -p "${DATE_LINK_DIR}" 2>/dev/null || {
    log "link_archive: cannot create ${DATE_LINK_DIR}"
    exit 1
}

for OFFSET in $(seq 34 -1 0); do
    D=$(date -d "-${OFFSET} days" +%Y%m%d)
    ARC="${TIMELAPSE_DIR}/${D}"
    [ -d "${ARC}" ] && ln -sfn "${ARC}" "${DATE_LINK_DIR}/${D}"
done

# link_latest <DEST> <SRC_PATTERN>
# Refreshed EVERY run (unlike link_if_absent): walks back through the
# archive until a day carries the asset, then points <DEST> at it. The
# gallery's "Latest" card reads these instead of the weekday-named
# rotation, which gilman-aurora-archive requires to stay backfill-only.
# The *_latest.* names are staged only by this script, so there is never
# a real pipeline file to protect, and no today-age gate is needed (the
# cp-then-mv publish means an archive path exists only once complete).
link_latest() {
    local DEST=$1 PAT=$2 OFFSET D SRC
    for OFFSET in $(seq 0 49); do
        D=$(date -d "-${OFFSET} days" +%Y%m%d)
        SRC=$(printf "${PAT}" "${D}" "${D}")
        if [ -e "${SRC}" ]; then
            ln -sfn "${SRC}" "${DEST}" \
                && log "link_archive: latest ${DEST} -> ${SRC}"
            return 0
        fi
    done
    log "link_archive: latest ${DEST}: no archive match"
}

link_latest "${WEEWX_TIMELAPSE_DIR}/AuroraCam_latest.mp4"           "${TIMELAPSE_DIR}/%s/AuroraCam_%s_640x360.mp4"
link_latest "${WEEWX_TIMELAPSE_DIR}/AuroraCam_latest.thumbnail.jpg" "${TIMELAPSE_DIR}/%s/AuroraCam_%s.thumbnail.jpg"
link_latest "${WEEWX_TIMELAPSE_DIR}/CloudCam_latest.mp4"            "${TIMELAPSE_DIR}/%s/CloudCam_%s_640x360.mp4"
link_latest "${WEEWX_TIMELAPSE_DIR}/CloudCam_latest.thumbnail.jpg"  "${TIMELAPSE_DIR}/%s/CloudCam_%s.thumbnail.jpg"
link_latest "${WEEWX_TIMELAPSE_DIR}/SpaceWeather_latest.gif"        "${TIMELAPSE_DIR}/%s/SpaceWeather_%s.gif"

# Prune day-name media symlinks whose archive target has rotated away.
shopt -s nullglob
for LINK in "${WEEWX_TIMELAPSE_DIR}"/AuroraCam_*.mp4 \
            "${WEEWX_TIMELAPSE_DIR}"/AuroraCam_*.thumbnail.jpg \
            "${WEEWX_TIMELAPSE_DIR}"/CloudCam_*.mp4 \
            "${WEEWX_TIMELAPSE_DIR}"/CloudCam_*.thumbnail.jpg \
            "${WEEWX_TIMELAPSE_DIR}"/SpaceWeather_*.gif \
            "${DATE_LINK_DIR}"/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]; do
    [ -L "${LINK}" ] || continue
    [ -e "${LINK}" ] || { rm -f "${LINK}" && log "link_archive: pruned broken ${LINK}"; }
done

exit 0
