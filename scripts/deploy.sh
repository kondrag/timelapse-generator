#!/usr/bin/env bash
# Deploy timelapse scripts to /opt/timelapse/scripts and apply FTP ACLs.
# Run manually: sudo scripts/deploy.sh
# Nothing here schedules jobs or rotates logs.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
DEST_DIR=${DEST_DIR:-/opt/timelapse/scripts}
FTP_DIR=${FTP_DIR:-/srv/ftp/aurora}
SETFACL_CMD=${SETFACL_CMD:-setfacl}
CRONTAB_CMD=${CRONTAB_CMD:-crontab}
ACL_USER=${ACL_USER:-greg}

if [ "$DEST_DIR" = "/opt/timelapse/scripts" ] && [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: deploying to $DEST_DIR requires root (run: sudo scripts/deploy.sh)" >&2
    exit 1
fi

mkdir -p "$DEST_DIR" || { echo "ERROR: cannot create $DEST_DIR" >&2; exit 1; }

if [ "$SCRIPT_DIR" -ef "$DEST_DIR" ]; then
    echo "== $DEST_DIR is linked to this workspace; skipping copy =="
else
    echo "== copying scripts to $DEST_DIR =="
    for f in "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/sun.py "$SCRIPT_DIR"/requirements.txt; do
        [ -e "$f" ] || continue
        [ "$(basename "$f")" = "deploy.sh" ] && continue
        cp -p "$f" "$DEST_DIR/" || { echo "ERROR: copy failed: $f" >&2; exit 1; }
        echo "  installed: $(basename "$f")"
    done
fi

echo "== applying ACLs on $FTP_DIR =="
# Directory + default ACL so future uploads inherit access for ACL_USER.
"$SETFACL_CMD" -m "u:${ACL_USER}:rwx,d:u:${ACL_USER}:rwx" "$FTP_DIR" || {
    echo "ERROR: dir ACL failed on $FTP_DIR" >&2
    exit 1
}
# One-time recursive pass so existing ftp-owned files become readable.
"$SETFACL_CMD" -R -m "u:${ACL_USER}:rw" "$FTP_DIR" || {
    echo "ERROR: recursive ACL failed on $FTP_DIR" >&2
    exit 1
}
echo "  ok: ${ACL_USER} can read/move images"

echo "== crontab entries referencing timelapse =="
"$CRONTAB_CMD" -l 2>/dev/null | grep -i timelapse || echo "  (none found in this crontab)"

echo "== pending at jobs =="
atq 2>/dev/null || true

echo "deploy complete."
