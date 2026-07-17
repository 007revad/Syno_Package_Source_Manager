#!/bin/bash
#----------------------------------------------------------
# Package Source Manager API - CGI API
#----------------------------------------------------------

# --------- 1. Common variables and path calculations -------------

PKG_NAME="SourceManager"
PKG_ROOT="/var/packages/${PKG_NAME}"
PKG_VERSION=$(synopkg version "$PKG_NAME")
TARGET_DIR="${PKG_ROOT}/target"
BIN_DIR="${TARGET_DIR}/bin"
LOG_DIR="${PKG_ROOT}/var"
LOG_FILE="${LOG_DIR}/api.log"

LIVE_FILE="/usr/syno/etc/packages/feeds"
MASTER_FILE="${LOG_DIR}/feeds"
WRITE_SCRIPT="${BIN_DIR}/write_feeds.sh"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"
chmod 644 "${LOG_FILE}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "${LOG_FILE}"
}

# --------- 2. HTTP header output --------------------------------

echo "Content-Type: application/json; charset=utf-8"
echo "Access-Control-Allow-Origin: *"
echo "Access-Control-Allow-Methods: GET, POST"
echo "Access-Control-Allow-Headers: Content-Type"
echo "" # Header/body separator blank line

# --------- 3. Parsing URL-encoded parameters --------------------

urldecode() { : "${*//+/ }"; echo -e "${_//%/\\x}"; }
declare -A PARAM
parse_kv() {
    local kv_pair key val
    IFS='&' read -ra kv_pair <<< "$1"
    for pair in "${kv_pair[@]}"; do
        IFS='=' read -r key val <<< "${pair}"
        key="$(urldecode "${key}")"
        val="$(urldecode "${val}")"
        PARAM["${key}"]="${val}"
    done
}

case "$REQUEST_METHOD" in
POST)
    CONTENT_LENGTH=${CONTENT_LENGTH:-0}
    if [ "$CONTENT_LENGTH" -gt 0 ]; then
        read -r -n "$CONTENT_LENGTH" POST_DATA
    else
        POST_DATA=""
    fi
    parse_kv "${POST_DATA}"
    ;;
GET)
    parse_kv "${QUERY_STRING}"
    ;;
*)
    log "Unsupported METHOD: ${REQUEST_METHOD}"
    echo '{"success":false,"message":"Unsupported METHOD","result":null}'
    exit 0
    ;;
esac

ACTION="${PARAM[action]}"
log "Request: ACTION=${ACTION}"

# --------- 4. JSON utility functions -----------------------------

json_escape() {
    echo "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

json_response() {
    local ok="$1" msg="$2" data="$3"
    local msg_json
    msg_json=$(echo "$msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')
    if [ -z "$data" ]; then
        echo "{\"success\":$ok, \"message\":$msg_json, \"result\":null}"
    else
        echo "{\"success\":$ok, \"message\":$msg_json, \"result\":$data}"
    fi
}

# Bootstraps MASTER_FILE from LIVE_FILE if it doesn't exist yet
# (belt-and-braces alongside postinst, in case api.cgi runs first)
ensure_master_file() {
    if [ ! -f "$MASTER_FILE" ] && [ -f "$LIVE_FILE" ]; then
        python3 -c "
import json
with open('$LIVE_FILE') as f:
    data = json.load(f)
for entry in data:
    entry['enabled'] = True
with open('$MASTER_FILE', 'w') as f:
    json.dump(data, f, indent=2)
" 2>>"${LOG_FILE}"
        chmod 644 "$MASTER_FILE" 2>/dev/null
    fi
}

# --------- 5. Action processing ---------------------------------

case "${ACTION}" in
init)
    log "----------------------------------------"
    log "Web UI opened/refreshed"
    echo '{"success":true,"message":"init"}'
    ;;

list)
    ensure_master_file
    if [ -f "$MASTER_FILE" ]; then
        DATA="$(cat "$MASTER_FILE")"
        json_response true "Feeds loaded" "${DATA}"
    else
        json_response false "No feeds file found on this NAS" "[]"
    fi
    ;;

save)
    # PARAM[data] is expected to be a JSON array of
    # {"feed":"...","name":"...","enabled":true|false}
    RAW_DATA="${PARAM[data]}"

    if [ -z "$RAW_DATA" ]; then
        json_response false "No data supplied" ""
        exit 0
    fi

    TMP_MASTER="${LOG_DIR}/feeds.tmp"
    TMP_LIVE="${LOG_DIR}/feeds_live.tmp"

    # Validate the incoming JSON, write the full master copy (with
    # enabled flags), and build the live-file copy (enabled entries
    # only, original two-key schema: feed + name).
    if ! echo "$RAW_DATA" | python3 -c "
import json, sys

data = json.load(sys.stdin)

with open('${TMP_MASTER}', 'w') as f:
    json.dump(data, f, indent=2)

live = [{'feed': e['feed'], 'name': e['name']} for e in data if e.get('enabled', True)]
with open('${TMP_LIVE}', 'w') as f:
    json.dump(live, f)
" 2>>"${LOG_FILE}"; then
        log "[ERROR] Failed to parse/write incoming feeds data"
        json_response false "Invalid feeds data" ""
        exit 0
    fi

    # Master file is package-owned, write it directly.
    mv "${TMP_MASTER}" "${MASTER_FILE}"
    chmod 644 "${MASTER_FILE}"
    log "Master feeds file updated: ${MASTER_FILE}"

    # Live file is root-owned. Requires the sudoers grant described in
    # set_package_permissions.md. If that hasn't been set up yet this
    # will fail, which we report back rather than silently ignoring.
    if sudo -n "${WRITE_SCRIPT}" "${TMP_LIVE}" "${LIVE_FILE}" 2>>"${LOG_FILE}"; then
        rm -f "${TMP_LIVE}"
        log "Live feeds file updated: ${LIVE_FILE}"
        json_response true "Feeds saved" ""
    else
        log "[ERROR] Failed to write live feeds file, sudoers grant likely missing"
        json_response false "Saved locally, but couldn't update the live feeds file. See set_package_permissions.md" ""
    fi
    ;;

*)
    log "[ERROR] Invalid action: ${ACTION}"
    json_response false "Invalid action: ${ACTION}" ""
    ;;
esac

exit 0
