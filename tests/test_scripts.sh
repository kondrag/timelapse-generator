#!/usr/bin/env bash
# Test harness for the timelapse shell scripts.
# Run: bash tests/test_scripts.sh  (from repo root)

set -u
cd "$(dirname "$0")/.."

PASS=0
FAIL=0

check() {
    local DESC=$1 EXPECTED=$2 ACTUAL=$3
    if [ "$EXPECTED" = "$ACTUAL" ]; then
        PASS=$((PASS + 1))
        echo "ok   - $DESC"
    else
        FAIL=$((FAIL + 1))
        echo "FAIL - $DESC"
        echo "       expected: $EXPECTED"
        echo "       actual:   $ACTUAL"
    fi
}

sandbox() {
    SBX=$(mktemp -d)
}

trap 'rm -rf "${SBX:-}"' EXIT

# ---------------------------------------------------------------- overrides

test_env_overrides_respected() {
    sandbox
    local OUT
    OUT=$(LOGFILE="$SBX/log" TIMELAPSE_DIR="$SBX/tl" WEEWX_DIR="$SBX/wx" \
        bash -c 'source scripts/common_env.sh; echo "$LOGFILE|$TIMELAPSE_DIR|$WEEWX_TIMELAPSE_DIR"')
    check "env overrides respected" "$SBX/log|$SBX/tl|$SBX/wx/aurora" "$OUT"
}

test_env_defaults_untouched() {
    sandbox
    local OUT
    OUT=$(bash -c 'source scripts/common_env.sh; echo "$LOGFILE|$TIMELAPSE_DIR"')
    check "defaults unchanged" "/tmp/timelapse.log|/var/local/timelapse" "$OUT"
}

test_env_overrides_reach_archive_dir() {
    sandbox
    local OUT
    OUT=$(LOGFILE="$SBX/log" TIMELAPSE_DIR="$SBX/tl" \
        bash -c 'source scripts/common_env.sh; echo "$ARCHIVE_DIR"')
    check "ARCHIVE_DIR derives from overridden TIMELAPSE_DIR" "$SBX/tl/$(date +%Y%m%d)" "$OUT"
}

# ---------------------------------------------------------------- self_heal_move.sh
# Fixture dates are fixed so sun.py output is deterministic:
#   Sep 6 2026 dusk=20:36  Sep 7 2026 dawn=05:26  Sep 7 2026 dusk=20:34
# Night window: [20260906203600, 20260907052659]
# Day window:   [20260907052700, 20260907203459]

mk_img() {
    : > "$1"
}

run_heal() {
    FTP_DIR="$SBX/ftp" TIMELAPSE_DIR="$SBX/tl" LOGFILE="$SBX/log" \
        bash scripts/self_heal_move.sh "$@" >>"$SBX/out" 2>&1
}

test_self_heal_moves_only_matching_files() {
    sandbox
    mkdir -p "$SBX/ftp"
    mk_img "$SBX/ftp/AuroraCam_00_20260906203500.jpg"  # before dusk - stays
    mk_img "$SBX/ftp/AuroraCam_00_20260906203600.jpg"  # dusk - night
    mk_img "$SBX/ftp/AuroraCam_00_20260907052658.jpg"  # last night frame - night
    mk_img "$SBX/ftp/AuroraCam_00_20260907052700.jpg"  # first day frame - stays
    run_heal night --date 2026-09-07
    local NIGHT FTPLEFT
    NIGHT=$(ls -1 "$SBX/tl/20260907/night" 2>/dev/null | wc -l)
    FTPLEFT=$(ls -1 "$SBX/ftp" | wc -l)
    check "night self-heal moves only window files" "2|2" "$NIGHT|$FTPLEFT"
}

test_self_heal_noop_when_archive_has_files() {
    sandbox
    mkdir -p "$SBX/ftp" "$SBX/tl/20260907/night"
    mk_img "$SBX/ftp/AuroraCam_00_20260906203600.jpg"
    mk_img "$SBX/tl/20260907/night/AuroraCam_00_20260906210000.jpg"
    run_heal night --date 2026-09-07
    local NIGHT FTPLEFT
    NIGHT=$(ls -1 "$SBX/tl/20260907/night" | wc -l)
    FTPLEFT=$(ls -1 "$SBX/ftp" | wc -l)
    check "no move when archive window already has images" "1|1" "$NIGHT|$FTPLEFT"
}

test_self_heal_noop_when_no_matching_files() {
    sandbox
    mkdir -p "$SBX/ftp"
    mk_img "$SBX/ftp/AuroraCam_00_20260907052700.jpg"  # day frame, not night
    run_heal night --date 2026-09-07
    local NIGHTDIR
    NIGHTDIR=$(ls -1 "$SBX/tl/20260907" 2>/dev/null | wc -l)
    check "no move and no window dir when nothing matches" "0" "$NIGHTDIR"
}

test_self_heal_day_window() {
    sandbox
    mkdir -p "$SBX/ftp"
    mk_img "$SBX/ftp/AuroraCam_00_20260907052700.jpg"  # first day frame - day
    mk_img "$SBX/ftp/AuroraCam_00_20260907203300.jpg"  # before dusk - day
    mk_img "$SBX/ftp/AuroraCam_00_20260907203400.jpg"  # dusk - day
    mk_img "$SBX/ftp/AuroraCam_00_20260907203500.jpg"  # after dusk - stays
    run_heal day --date 2026-09-07
    local DAY FTPLEFT
    DAY=$(ls -1 "$SBX/tl/20260907/day" 2>/dev/null | wc -l)
    FTPLEFT=$(ls -1 "$SBX/ftp" | wc -l)
    check "day self-heal moves only window files" "3|1" "$DAY|$FTPLEFT"
}

test_self_heal_logs_to_logfile() {
    sandbox
    mkdir -p "$SBX/ftp"
    mk_img "$SBX/ftp/AuroraCam_00_20260906203600.jpg"
    run_heal night --date 2026-09-07
    grep -q 'SELF-HEAL' "$SBX/log"
    check "self-heal writes SELF-HEAL tagged lines to log" "0" "$?"
}

test_self_heal_usage_error() {
    sandbox
    run_heal bogus
    check "invalid window arg exits nonzero" "1" "$?"
}

# ---------------------------------------------------------------- rotate_log

test_rotation_moves_old_log() {
    sandbox
    echo hello > "$SBX/log"
    LOGFILE="$SBX/log" bash -c 'source scripts/common_env.sh; rotate_log'
    local ROTATED INIT
    ROTATED=$(cat "$SBX"/log.* 2>/dev/null)
    INIT=$(head -1 "$SBX/log")
    case "$INIT" in
        Initialize*) INIT=Initialize ;;
    esac
    check "rotation archives old log and reinits" "hello|Initialize" "$ROTATED|$INIT"
}

test_rotation_unique_names() {
    sandbox
    echo one > "$SBX/log"
    LOGFILE="$SBX/log" bash -c 'source scripts/common_env.sh; rotate_log'
    echo two > "$SBX/log"
    LOGFILE="$SBX/log" bash -c 'source scripts/common_env.sh; rotate_log'
    local COUNT
    COUNT=$(ls -1 "$SBX"/log.* 2>/dev/null | wc -l)
    check "two rotations leave two distinct files" "2" "$COUNT"
}

test_rotation_preserves_log_when_mv_fails() {
    sandbox
    echo PRECIOUS > "$SBX/log"
    LOGFILE="$SBX/log" MV_CMD=false bash -c 'source scripts/common_env.sh; rotate_log'
    local ROTATED SURVIVES
    ROTATED=$(ls -1 "$SBX"/log.* 2>/dev/null | wc -l)
    if grep -q PRECIOUS "$SBX/log"; then SURVIVES=yes; else SURVIVES=no; fi
    check "losing rotation race appends instead of truncating" "0|yes" "$ROTATED|$SURVIVES"
}

# ---------------------------------------------------------------- schedule_and_verify

test_schedule_verify_confirms_job() {
    sandbox
    mkdir -p "$SBX/ftp"
    local ATQ_LINE="999	Mon Sep 7 20:34:00 2026 a $(id -un)"
    LOGFILE="$SBX/log" AT_CMD="echo at-fake" ATQ_CMD="echo $ATQ_LINE" \
        bash -c 'source scripts/common_env.sh; schedule_and_verify 20:34 "/opt/timelapse/scripts/move_ftp_images.sh day"'
    check "at-job confirmed when atq lists it" "0" "$?"
}

test_schedule_verify_missing_job_alerts() {
    sandbox
    mkdir -p "$SBX/ftp"
    printf '#!/bin/bash\necho "$@" >> "$MAILBOX"\n' >"$SBX/fakemail"
    chmod +x "$SBX/fakemail"
    export MAILBOX="$SBX/mailbox"
    LOGFILE="$SBX/log" AT_CMD="echo at-fake" ATQ_CMD=true MAIL_CMD="$SBX/fakemail" \
        bash -c 'source scripts/common_env.sh; schedule_and_verify 20:34 "/opt/timelapse/scripts/move_ftp_images.sh day"'
    local RC=$?
    local ERRLOG MAILED
    grep -q 'ERROR' "$SBX/log" && ERRLOG=yes || ERRLOG=no
    grep -q 'scheduling failed' "$MAILBOX" 2>/dev/null && MAILED=yes || MAILED=no
    check "missing at-job logs ERROR, mails, exits 1" "1|yes|yes" "$RC|$ERRLOG|$MAILED"
    unset MAILBOX
}

# ---------------------------------------------------------------- fetch_spaceweather.sh

test_fetch_spaceweather_creates_archive_dir() {
    sandbox
    LOGFILE="$SBX/log" TIMELAPSE_DIR="$SBX/tl" WEEWX_DIR="$SBX/wx" \
        WGET_CMD="echo wget-fake" \
        bash scripts/fetch_spaceweather.sh >>"$SBX/out" 2>&1
    local EXISTS
    [ -d "$SBX/tl/$(date +%Y%m%d)" ] && EXISTS=yes || EXISTS=no
    check "fetch creates missing ARCHIVE_DIR" "yes" "$EXISTS"
}

# ---------------------------------------------------------------- timelapse.sh
# Uses fake ffmpeg/ffprobe/convert on PATH plus dynamic sun.py windows so the
# tests are runnable on any date. Fixture jpgs must be NON-empty (the encoder
# quarantines zero-byte files).

win_bounds() {
    local YD TD DUSK_Y DAWN DUSK BASE
    YD=$(date -d yesterday +%F)
    TD=$(date +%F)
    DUSK_Y=$(python3 scripts/sun.py --date "$YD" --dusk)
    DAWN=$(python3 scripts/sun.py --dawn)
    DUSK=$(python3 scripts/sun.py --dusk)
    NIGHT_LO_E=$(date -d "$YD $DUSK_Y" +%s)
    NIGHT_HI_E=$(( $(date -d "$TD $DAWN" +%s) + 59 ))
    DAY_LO_E=$(( $(date -d "$TD $DAWN" +%s) + 60 ))
    DAY_HI_E=$(( $(date -d "$TD $DUSK" +%s) + 59 ))
}

ts() { date -d "@$1" +%Y%m%d%H%M%S; }

mk_jpg() {  # mk_jpg <dir> <epoch-seconds>
    printf 'JPGDATA' > "$1/AuroraCam_00_$(ts "$2").jpg"
}

mk_fakebin() {  # mk_fakebin [fail|probe-fail]  - ffmpeg fails when "fail" given;
    #               "probe-fail" fails ONLY vaapi probes (args contain lavfi)
    FAKEBIN=$SBX/fakebin
    mkdir -p "$FAKEBIN"
    if [ "${1:-}" = "fail" ]; then
        printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "${FFMPEG_LOG:-/dev/null}"\nexit 1\n' > "$FAKEBIN/ffmpeg"
    elif [ "${1:-}" = "probe-fail" ]; then
        cat > "$FAKEBIN/ffmpeg" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "${FFMPEG_LOG:-/dev/null}"
case "$*" in *lavfi*) exit 1;; esac
OUT="${@: -1}"
printf X > "$OUT"
exit 0
EOF
    else
        printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "${FFMPEG_LOG:-/dev/null}"\nOUT="${@: -1}"\nprintf X > "$OUT"\nexit 0\n' > "$FAKEBIN/ffmpeg"
    fi
    cat > "$FAKEBIN/ffprobe" <<'EOF'
#!/bin/bash
LAST="${@: -1}"
DIR=$(dirname "$LAST")
case "$*" in
    *duration*) echo 100.0 ;;
    *) ls -1 "$DIR"/*.jpg 2>/dev/null | wc -l ;;
esac
EOF
    printf '#!/bin/bash\nprintf X > "${@: -1}"\n' > "$FAKEBIN/convert"
    chmod +x "$FAKEBIN"/*
}

run_timelapse() {
    PATH="$FAKEBIN:$PATH" FTP_DIR="$SBX/ftp" TIMELAPSE_DIR="$SBX/tl" \
        LOGFILE="$SBX/log" WEEWX_DIR="$SBX/wx" WGET_CMD="echo wget-fake" \
        bash scripts/timelapse.sh "$@" >>"$SBX/out" 2>&1
}

test_timelapse_night_self_heal_hookup() {
    sandbox
    win_bounds
    mk_fakebin
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" $((NIGHT_LO_E - 60))   # before dusk - stays in FTP
    mk_jpg "$SBX/ftp" "$NIGHT_LO_E"          # dusk - night
    mk_jpg "$SBX/ftp" "$NIGHT_HI_E"          # last night frame - night
    mk_jpg "$SBX/ftp" $((NIGHT_HI_E + 60))   # first day frame - stays in FTP
    run_timelapse night
    local TODAY=$(/bin/date +%Y%m%d) DAY=$(/bin/date +%A)
    local MP4S HEALED FTPLEFT
    MP4S=$(ls -1 "$SBX/tl/$TODAY"/*.mp4 2>/dev/null | wc -l)
    grep -q 'SELF-HEAL' "$SBX/log" && HEALED=yes || HEALED=no
    FTPLEFT=$(ls -1 "$SBX/ftp" | wc -l)
    check "night run self-heals, encodes both, archives, keeps strays" \
        "2|yes|2|$([ -f "$SBX/wx/aurora/AuroraCam_${DAY}.mp4" ] && echo v)" \
        "$MP4S|$HEALED|$FTPLEFT|$([ -f "$SBX/wx/aurora/AuroraCam_${DAY}.mp4" ] && echo v)"
}

test_timelapse_day_self_heal_hookup() {
    sandbox
    win_bounds
    mk_fakebin
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" $((DAY_LO_E - 60))     # still night - stays in FTP
    mk_jpg "$SBX/ftp" "$DAY_LO_E"            # first day frame
    mk_jpg "$SBX/ftp" $((NIGHT_HI_E + 3660)) # midday (thumbnail candidate)
    mk_jpg "$SBX/ftp" "$DAY_HI_E"            # last day frame
    run_timelapse day
    local TODAY=$(/bin/date +%Y%m%d) DAY=$(/bin/date +%A)
    local MP4S HEALED FTPLEFT
    MP4S=$(ls -1 "$SBX/tl/$TODAY"/*.mp4 2>/dev/null | wc -l)
    grep -q 'SELF-HEAL' "$SBX/log" && HEALED=yes || HEALED=no
    FTPLEFT=$(ls -1 "$SBX/ftp" | wc -l)
    check "day run self-heals, encodes, archives, keeps strays" \
        "1|yes|1|$([ -f "$SBX/wx/aurora/CloudCam_${DAY}.mp4" ] && echo v)" \
        "$MP4S|$HEALED|$FTPLEFT|$([ -f "$SBX/wx/aurora/CloudCam_${DAY}.mp4" ] && echo v)"
}

test_timelapse_night_failure_guards() {
    sandbox
    mk_fakebin fail
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora" "$SBX/tl/$(/bin/date +%Y%m%d)/night"
    mk_jpg "$SBX/tl/$(/bin/date +%Y%m%d)/night" "$(( $(date -d '12 hours ago' +%s) ))"
    run_timelapse night
    local TODAY=$(/bin/date +%Y%m%d)
    local KEPT MVNOISE EMPTYTHUMB
    [ -d "$SBX/tl/$TODAY/night" ] && KEPT=yes || KEPT=no
    grep -q '^mv: ' "$SBX/log" && MVNOISE=yes || MVNOISE=no
    grep -q 'Using  as thumbnail' "$SBX/log" && EMPTYTHUMB=yes || EMPTYTHUMB=no
    check "failed encode keeps dir, no bogus mv, no empty-thumb log" \
        "yes|no|no" "$KEPT|$MVNOISE|$EMPTYTHUMB"
}

test_timelapse_uses_vaapi_when_available() {
    sandbox
    win_bounds
    mk_fakebin
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" "$NIGHT_LO_E"
    mk_jpg "$SBX/ftp" "$NIGHT_HI_E"
    local FFMPEG_LOG=$SBX/ffmpeg.args
    export FFMPEG_LOG
    run_timelapse night
    local VHW VDEV VUP NOSW BACKEND
    grep -q 'h264_vaapi' "$FFMPEG_LOG" && VHW=y || VHW=n
    grep -q 'vaapi_device' "$FFMPEG_LOG" && VDEV=y || VDEV=n
    grep -q 'hwupload' "$FFMPEG_LOG" && VUP=y || VUP=n
    grep -q 'libx264' "$FFMPEG_LOG" && NOSW=y || NOSW=n
    grep -q 'encoder backend: vaapi' "$SBX/log" && BACKEND=y || BACKEND=n
    check "vaapi backend chosen when probe succeeds" \
        "y|y|y|n|y" "$VHW|$VDEV|$VUP|$NOSW|$BACKEND"
}

test_vaapi_qp_configurable() {
    sandbox
    win_bounds
    mk_fakebin
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" "$NIGHT_LO_E"
    mk_jpg "$SBX/ftp" "$NIGHT_HI_E"
    local FFMPEG_LOG=$SBX/ffmpeg.args
    export FFMPEG_LOG
    run_timelapse night
    local QP27 NO23
    grep -q -- '-qp 27' "$FFMPEG_LOG" && QP27=y || QP27=n
    grep -q -- '-qp 23' "$FFMPEG_LOG" && NO23=y || NO23=n
    check "vaapi default qp is 27" "y|n" "$QP27|$NO23"

    sandbox
    win_bounds
    mk_fakebin
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" "$NIGHT_LO_E"
    mk_jpg "$SBX/ftp" "$NIGHT_HI_E"
    FFMPEG_LOG=$SBX/ffmpeg.args
    export FFMPEG_LOG
    VAAPI_QP=30 run_timelapse night
    grep -q -- '-qp 30' "$FFMPEG_LOG" && QP27=y || QP27=n
    check "vaapi qp overridable via VAAPI_QP" "y" "$QP27"
}

test_timelapse_falls_back_to_libx264_when_probe_fails() {
    sandbox
    win_bounds
    mk_fakebin probe-fail
    mkdir -p "$SBX/ftp" "$SBX/wx/aurora"
    mk_jpg "$SBX/ftp" "$NIGHT_LO_E"
    mk_jpg "$SBX/ftp" "$NIGHT_HI_E"
    local FFMPEG_LOG=$SBX/ffmpeg.args
    export FFMPEG_LOG
    run_timelapse night
    local SW BACKEND MP4S
    grep -q 'libx264' "$FFMPEG_LOG" && SW=y || SW=n
    grep -q 'encoder backend: libx264' "$SBX/log" && BACKEND=y || BACKEND=n
    MP4S=$(ls -1 "$SBX/tl/$(/bin/date +%Y%m%d)"/*.mp4 2>/dev/null | wc -l)
    check "libx264 fallback when vaapi probe fails, encode still succeeds" \
        "y|y|2" "$SW|$BACKEND|$MP4S"
}

# ---------------------------------------------------------------- deploy.sh

test_deploy_copies_scripts_and_applies_acls() {
    sandbox
    mkdir -p "$SBX/ftp" "$SBX/opt"
    printf 'JPG' > "$SBX/ftp/AuroraCam_00_20260907093000.jpg"
    cat > "$SBX/fakesetfacl" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$ACL_LOG"
exit 0
EOF
    chmod +x "$SBX/fakesetfacl"
    cat > "$SBX/fakecrontab" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-l" ]; then
    echo "0 0 * * * /opt/timelapse/scripts/setup_schedule.sh images"
    exit 0
fi
exit 1
EOF
    chmod +x "$SBX/fakecrontab"
    local OUT RC
    local ACL_LOG=$SBX/acl.log
    export ACL_LOG
    OUT=$(DEST_DIR="$SBX/opt" FTP_DIR="$SBX/ftp" \
        SETFACL_CMD="$SBX/fakesetfacl" \
        CRONTAB_CMD="$SBX/fakecrontab" \
        bash scripts/deploy.sh 2>&1); RC=$?
    local NFILES SETUP_EXEC HEAL_EXEC ACLDIR ACLRECURS CRONSTATUS
    NFILES=$(ls -1 "$SBX/opt" | wc -l)
    [ -x "$SBX/opt/setup_schedule.sh" ] && SETUP_EXEC=x || SETUP_EXEC=-
    [ -x "$SBX/opt/self_heal_move.sh" ] && HEAL_EXEC=x || HEAL_EXEC=-
    grep -q -- '-m u:greg:rwx,d:u:greg:rwx' "$SBX/acl.log" && ACLDIR=y || ACLDIR=n
    grep -q -- "-m u:greg:rw $SBX/ftp/AuroraCam_00_20260907093000.jpg" "$SBX/acl.log" \
        && ACLFILE=y || ACLFILE=n
    grep -q -- '-R' "$SBX/acl.log" && ACLRECURS=y || ACLRECURS=n
    grep -q 'setup_schedule.sh images' <<<"$OUT" && CRONSTATUS=y || CRONSTATUS=n
    check "deploy copies 9 files +x, dir+file ACLs, no recursive dir clobber, prints cron status" \
        "0|9|x|x|y|y|n|y" "$RC|$NFILES|$SETUP_EXEC|$HEAL_EXEC|$ACLDIR|$ACLFILE|$ACLRECURS|$CRONSTATUS"
}

test_deploy_skips_copy_when_dest_symlinks_to_source() {
    sandbox
    mkdir -p "$SBX/ftp"
    printf 'JPG' > "$SBX/ftp/AuroraCam_00_20260907093000.jpg"
    cat > "$SBX/fakesetfacl" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$ACL_LOG"
exit 0
EOF
    chmod +x "$SBX/fakesetfacl"
    ln -s "$(pwd)/scripts" "$SBX/dest"
    local OUT RC SKIPPED ACLDIR
    local ACL_LOG=$SBX/acl.log
    export ACL_LOG
    OUT=$(DEST_DIR="$SBX/dest" FTP_DIR="$SBX/ftp" \
        SETFACL_CMD="$SBX/fakesetfacl" CRONTAB_CMD=true \
        bash scripts/deploy.sh 2>&1); RC=$?
    grep -q 'linked' <<<"$OUT" && SKIPPED=y || SKIPPED=n
    grep -q -- '-m u:greg:rwx,d:u:greg:rwx' "$SBX/acl.log" && ACLDIR=y || ACLDIR=n
    check "deploy detects symlinked dest, skips copy, still applies ACLs" \
        "0|y|y" "$RC|$SKIPPED|$ACLDIR"
}

test_deploy_refuses_default_dest_without_root() {
    sandbox
    local OUT RC REFUSED FAILED
    OUT=$(bash scripts/deploy.sh 2>&1); RC=$?
    [ "$RC" -ne 0 ] && FAILED=y || FAILED=n
    grep -qi 'root' <<<"$OUT" && REFUSED=y || REFUSED=n
    check "deploy refuses default dest as non-root" "y|y" "$FAILED|$REFUSED"
}

# ---------------------------------------------------------------- run

for fn in $(declare -F | awk '{print $3}' | grep '^test_'); do
    "$fn"
done

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
