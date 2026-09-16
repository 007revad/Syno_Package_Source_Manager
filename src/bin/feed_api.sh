#!/bin/bash
# Wrapper around the official SYNO.Core.Package.Feed API. Run via sudo as
# root (synowebapi itself requires root regardless of method - confirmed:
# "sudo -u SourceManager synowebapi ..." gives Permission denied).
#
# DSM expects the "list" param as a JSON-encoded STRING (i.e. the value is
# itself a string containing escaped JSON), not a raw JSON array/object -
# confirmed by decoding DSM's own browser requests. A raw array/object
# value fails with error 120 ("list"/"type") even though --help's usage
# text implies key=json_value should just work.
#
# Usage:
#   feed_api.sh list
#   feed_api.sh add "<name>" "<feed_url>"
#   feed_api.sh delete "<feed_url>" ["<feed_url2>" ...]
#----------------------------------------------------------

PKG_NAME="SourceManager"
PKG_ROOT="/var/packages/${PKG_NAME}"
BIN_DIR="${PKG_ROOT}/target/bin"
SCRIPT="${BIN_DIR}/feed_api.sh"

# Get DSM major version
dsm=$(/usr/syno/bin/synogetkeyvalue /etc.defaults/VERSION majorversion)
if [[ $dsm -ge 7 ]]; then
    VAR_DIR="${PKG_ROOT}/var"
else
    VAR_DIR="${PKG_ROOT}/etc"
fi

FEEDS_FILE="${VAR_DIR}/feeds"
LOG_FILE="${VAR_DIR}/sourcemanager.log"
API_LOG_FILE="${VAR_DIR}/api.log"

# ---------------------------------------------------------------------
# Self-heal file ownership.
#
# bin/ is locked to 555 by postinst, which blocks create/delete/rename
# of files inside them - but postinst runs as SourceManager, not root
# (confirmed 2026-08-15), so it can never chown anything. Every file 
# under bin/ therefore starts out still owned by SourceManager. An owner
# can always chmod u+w their own file regardless of the containing 
# directory's permissions, then overwrite its content in place - confirmed
# exploitable against feed_api.sh on DS218 2026-08-15 despite bin/ being 555.
#
# Since this script always runs as root (invoked only via
# sourcemanager-helper's setuid), it closes that gap on every single
# invocation: chown root:root + re-lock any file that's still
# SourceManager-owned. Cheap enough to run unconditionally rather than
# caching a "did we already do this" flag - a handful of stat calls.
#
# Targets are found by globbing bin/ directly. Since both directories 
# are 555 (no new files can be created), globbing what's actually on 
# disk covers every possible overwrite target without trusting content
# that could be the attack itself.
#
# LIMITATION: This cannot protect this script (feed_api.sh)
# itself if it's been replaced before this code runs, the replacement
# executes instead and this check never fires - self-heal logic in the
# original file doesn't help once the original file is gone. This is
# a narrow, accepted gap: the window between postinst completing and
# the first invocation of this script (which happens automatically on
# first page load via getstate). Everything this function iterates
# over is fully self-healing from that point forward; this file itself
# is the one exception.
self_heal() {
    local f owner
    for f in "$BIN_DIR"/*.sh "$BIN_DIR"/*.py "$0"; do
        [[ -f "$f" ]] || continue
        owner="$(stat -c '%U' "$f" 2>/dev/null)"
        if [[ "$owner" != "root" ]]; then
            chown root:root "$f" 2>/dev/null
            chmod 555 "$f" 2>/dev/null
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] SourceManager: self-heal secured $f (was owned by $owner)" \
                >> "${API_LOG_FILE}" 2>/dev/null
        fi
    done

    # feeds is data, not code - root still writes it on every
    # save. 600 rather than 555: no group/other bits at all, since
    # root bypasses the mode entirely and the only thing left to
    # control is whether SourceManager can read config values.
    if [[ -f "$FEEDS_FILE" ]]; then
        owner="$(stat -c '%U' "$FEEDS_FILE" 2>/dev/null)"
        if [[ "$owner" != "root" ]]; then
            chown root:root "$FEEDS_FILE" 2>/dev/null
            chmod 600 "$FEEDS_FILE" 2>/dev/null
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] SourceManager: self-heal secured $FEEDS_FILE (was owned by $owner)" \
                >> "${API_LOG_FILE}" 2>/dev/null
        fi
    fi

    # Remove leftover sudoers rule from the pre-setuid-helper design.
    # No longer independently exploitable once the scripts above are
    # root-owned 555 (a NOPASSWD entry pointing at a script the
    # invoking user can't write to isn't itself an escalation path),
    # but it's unnecessary attack surface left behind on an in-place
    # upgrade of an old install, and worth clearing rather than
    # leaving as an inert-but-present entry. Only root can delete
    # anything under /etc/sudoers.d/, so - same as the ownership
    # fixes above - this only works from here, whether invoked via
    # the helper (DSM7) or directly (DSM6).
    SUDOERS_FILE="/etc/sudoers.d/${PKG_NAME}"
    if [[ -f "$SUDOERS_FILE" ]]; then
        rm -f "$SUDOERS_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SourceManager: self-heal removed leftover sudoers file $SUDOERS_FILE" \
            >> "${API_LOG_FILE}" 2>/dev/null
    fi
}

self_heal

ACTION="$1"
shift

# Get DSM major version - DSM 7 needs -s, DSM 6 must NOT have -s
dsm=$(/usr/syno/bin/synogetkeyvalue /etc.defaults/VERSION majorversion)
if [[ "$dsm" -ge 7 ]]; then
    WEBAPI_FLAG="-s"
else
    WEBAPI_FLAG=""
fi

case "$ACTION" in
list)
    synowebapi "$WEBAPI_FLAG" --exec api=SYNO.Core.Package.Feed method=list version=1
    ;;

add)
    NAME="$1"
    FEED="$2"
    if [ -z "$NAME" ] || [ -z "$FEED" ]; then
        echo '{"success":false,"error":{"message":"add requires a name and a feed url"}}' >&2
        exit 1
    fi
    LIST_PARAM=$(python3 -c "
import json, sys
obj = {'name': sys.argv[1], 'feed': sys.argv[2]}
print(json.dumps(json.dumps(obj)))
" "$NAME" "$FEED")
    synowebapi "$WEBAPI_FLAG" --exec api=SYNO.Core.Package.Feed method=add version=1 list="${LIST_PARAM}"
    ;;

delete)
    if [ "$#" -eq 0 ]; then
        echo '{"success":false,"error":{"message":"delete requires at least one feed url"}}' >&2
        exit 1
    fi
    LIST_PARAM=$(python3 -c "
import json, sys
print(json.dumps(json.dumps(sys.argv[1:])))
" "$@")
    synowebapi "$WEBAPI_FLAG" --exec api=SYNO.Core.Package.Feed method=delete version=1 list="${LIST_PARAM}"
    ;;

*)
    echo '{"success":false,"error":{"message":"Unknown action"}}' >&2
    exit 1
    ;;
esac
