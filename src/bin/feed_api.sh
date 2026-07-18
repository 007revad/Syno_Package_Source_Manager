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

ACTION="$1"
shift

case "$ACTION" in
list)
    synowebapi -s --exec api=SYNO.Core.Package.Feed method=list version=1
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
    synowebapi -s --exec api=SYNO.Core.Package.Feed method=add version=1 list="${LIST_PARAM}"
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
    synowebapi -s --exec api=SYNO.Core.Package.Feed method=delete version=1 list="${LIST_PARAM}"
    ;;

*)
    echo '{"success":false,"error":{"message":"Unknown action"}}' >&2
    exit 1
    ;;
esac
