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
FEED_API_SCRIPT="${BIN_DIR}/feed_api.sh"

# SCRIPT_DIR resolves to wherever api.cgi itself is running from, so
# feeds_list (shipped alongside index.html/main.js/api.cgi in the ui
# folder) is found without hard-coding a package path.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FEEDS_LIST_FILE="${SCRIPT_DIR}/feeds_list"

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

# Reconciles MASTER_FILE against the live DSM feed list. Handles feeds
# added/renamed/re-pointed directly in Package Center > Settings, so
# the master copy (and its enabled/disabled memory) doesn't drift out
# of sync with reality. Best-effort: if the live read fails (e.g.
# sudoers not set up yet), falls back to whatever the master file
# already has rather than blocking the UI.
reconcile_master_file() {
    python3 -c "
import json, os, subprocess

master_file = '${MASTER_FILE}'
feed_api = '${FEED_API_SCRIPT}'

try:
    with open(master_file) as f:
        master = json.load(f)
except Exception:
    master = []

proc = subprocess.run(['sudo', '-n', feed_api, 'list'], capture_output=True, text=True)
try:
    listing = json.loads(proc.stdout)
except Exception:
    listing = {'success': False}

if proc.returncode != 0 or not listing.get('success'):
    # Can't reach the live list right now - leave master file untouched.
    raise SystemExit(0)

live_items = listing.get('data', {}).get('items', [])

updated = list(master)
consumed = set()

for live in live_items:
    lf, ln = live['feed'], live['name']

    # Match by feed URL first (DSM's real unique key).
    idx = next((i for i, m in enumerate(updated)
                if i not in consumed and m.get('feed') == lf), None)
    if idx is not None:
        if updated[idx].get('name') != ln:
            updated[idx]['name'] = ln  # name changed in Package Center
        updated[idx]['enabled'] = True
        consumed.add(idx)
        continue

    # No URL match - if the name matches an existing entry, treat this
    # as that same source having its URL changed rather than a new one.
    idx = next((i for i, m in enumerate(updated)
                if i not in consumed and m.get('name') == ln), None)
    if idx is not None:
        updated[idx]['feed'] = lf  # URL changed in Package Center
        updated[idx]['enabled'] = True
        consumed.add(idx)
        continue

    # Genuinely new source, added directly in Package Center.
    updated.append({'feed': lf, 'name': ln, 'enabled': True})
    consumed.add(len(updated) - 1)

# Anything still marked enabled that we didn't see live must have been
# removed directly in Package Center - drop it to disabled so it's
# remembered (re-enable-able) rather than silently wrong, and so a
# future Save doesn't resurrect it by mistake.
for i, m in enumerate(updated):
    if i not in consumed and m.get('enabled', True):
        m['enabled'] = False

if updated != master:
    with open(master_file, 'w') as f:
        json.dump(updated, f, indent=2)
    os.chmod(master_file, 0o644)
" 2>>"${LOG_FILE}"
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
    reconcile_master_file
    if [ -f "$MASTER_FILE" ]; then
        DATA="$(cat "$MASTER_FILE")"
        json_response true "Feeds loaded" "${DATA}"
    else
        json_response false "No feeds file found on this NAS" "[]"
    fi
    ;;

catalog)
    # Returns the bundled feeds_list, filtered to entries that are
    # actually relevant to add right now:
    #  - dsmver:"6" entries dropped on DSM 7+
    #  - dsmver:"7" entries dropped on DSM <7
    #  - entries whose feed URL already exists in MASTER_FILE (i.e.
    #    already known to this package, enabled or not)
    if [ ! -f "$FEEDS_LIST_FILE" ]; then
        log "[ERROR] Bundled feeds_list not found at ${FEEDS_LIST_FILE}"
        json_response false "Bundled feeds_list not found" "[]"
        exit 0
    fi

    # DSM major version, read from the standard Synology VERSION file
    # (sourced rather than parsed, so no extra tooling is required).
    DSM_MAJOR=""
    if [ -f /etc.defaults/VERSION ]; then
        DSM_MAJOR="$(. /etc.defaults/VERSION 2>/dev/null; echo "$majorversion")"
    fi
    log "catalog: detected DSM majorversion='${DSM_MAJOR}'"

    RESULT_JSON=$(DSM_MAJOR="${DSM_MAJOR}" FEEDS_LIST_FILE="${FEEDS_LIST_FILE}" MASTER_FILE="${MASTER_FILE}" python3 -c "
import json, os

def to_int(s):
    try:
        return int(s)
    except Exception:
        return None

def normalize_feed(url):
    # Trailing-slash-insensitive comparison - the same feed is often
    # listed with and without one (e.g. 'nas' vs 'nas/') depending on
    # source.
    return (url or '').strip().rstrip('/')

dsm_major = to_int(os.environ.get('DSM_MAJOR', ''))

with open(os.environ['FEEDS_LIST_FILE']) as f:
    catalog = json.load(f)

existing_feeds = set()
master_file = os.environ.get('MASTER_FILE', '')
if master_file and os.path.exists(master_file):
    with open(master_file) as f:
        existing_feeds = {normalize_feed(m.get('feed')) for m in json.load(f)}

available = []
for entry in catalog:
    dsmver = entry.get('dsmver')
    if dsmver == '6' and (dsm_major is None or dsm_major >= 7):
        continue
    if dsmver == '7' and (dsm_major is not None and dsm_major < 7):
        continue
    if normalize_feed(entry.get('feed')) in existing_feeds:
        continue
    available.append(entry)

print(json.dumps(available))
" 2>>"${LOG_FILE}")

    if [ -z "$RESULT_JSON" ]; then
        log "[ERROR] catalog filtering produced no output"
        json_response false "Failed to build available source list" ""
    else
        json_response true "Available sources loaded" "${RESULT_JSON}"
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

    # Validate the incoming JSON and write the full master copy (with
    # enabled flags - DSM itself has no "disabled" concept, so this is
    # the only place that state is remembered).
    if ! echo "$RAW_DATA" | python3 -c "
import json, sys
data = json.load(sys.stdin)
with open('${TMP_MASTER}', 'w') as f:
    json.dump(data, f, indent=2)
" 2>>"${LOG_FILE}"; then
        log "[ERROR] Failed to parse/write incoming feeds data"
        json_response false "Invalid feeds data" ""
        exit 0
    fi

    mv "${TMP_MASTER}" "${MASTER_FILE}"
    chmod 644 "${MASTER_FILE}"
    log "Master feeds file updated: ${MASTER_FILE}"

    # Reconcile the live DSM feed list (via the official
    # SYNO.Core.Package.Feed API, root-run through feed_api.sh + sudo)
    # against the enabled entries from the master copy.
    RESULT_JSON=$(echo "$RAW_DATA" | python3 -c "
import json, subprocess, sys

feed_api = '${FEED_API_SCRIPT}'

data = json.load(sys.stdin)
target_enabled = {e['feed']: e['name'] for e in data if e.get('enabled', True)}

def run(*args):
    proc = subprocess.run(
        ['sudo', '-n', feed_api, *args],
        capture_output=True, text=True
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {'success': False, 'error': {'message': proc.stderr.strip() or 'no output'}}

rc, listing = run('list')
if rc != 0 or not listing.get('success'):
    print(json.dumps({
        'success': False,
        'message': 'Saved locally, but could not read the live feed list (sudoers grant likely missing). See set_package_permissions.md'
    }))
    sys.exit(0)

current_feeds = {item['feed'] for item in listing.get('data', {}).get('items', [])}

to_delete = [f for f in current_feeds if f not in target_enabled]
to_add = [(name, feed) for feed, name in target_enabled.items() if feed not in current_feeds]

errors = []

if to_delete:
    rc, res = run('delete', *to_delete)
    if rc != 0 or not res.get('success'):
        errors.append('delete failed: ' + json.dumps(res.get('error', res)))

for name, feed in to_add:
    rc, res = run('add', name, feed)
    if rc != 0 or not res.get('success'):
        errors.append(f'add failed for {name!r}: ' + json.dumps(res.get('error', res)))

if errors:
    print(json.dumps({'success': False, 'message': 'Feeds saved locally, but DSM rejected some changes: ' + '; '.join(errors)}))
else:
    changed = len(to_delete) + len(to_add)
    msg = 'Feeds saved' if changed else 'Feeds saved (no source changes needed)'
    print(json.dumps({'success': True, 'message': msg}))
" 2>>"${LOG_FILE}")

    if [ -z "$RESULT_JSON" ]; then
        log "[ERROR] feed reconciliation produced no output"
        json_response false "Saved locally, but the live feed sync failed unexpectedly. Check api.log" ""
    else
        log "Live feed reconciliation result: ${RESULT_JSON}"
        echo "$RESULT_JSON"
    fi
    ;;

*)
    log "[ERROR] Invalid action: ${ACTION}"
    json_response false "Invalid action: ${ACTION}" ""
    ;;
esac

exit 0
