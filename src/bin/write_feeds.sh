#!/bin/bash
# Writes a validated feeds JSON file into place as root.
# This script is meant to be invoked via sudo (see set_package_permissions.md)
# and does nothing except copy a temp file over the real feeds file.
#
# Usage: write_feeds.sh <source_tmp_file> <destination_file>

set -e

SRC="$1"
DEST="$2"

if [ -z "$SRC" ] || [ -z "$DEST" ]; then
    echo "Usage: $0 <source_tmp_file> <destination_file>" >&2
    exit 1
fi

if [ ! -f "$SRC" ]; then
    echo "Source file not found: $SRC" >&2
    exit 1
fi

# Only ever allow writing to the one path this package manages.
if [ "$DEST" != "/usr/syno/etc/packages/feeds" ]; then
    echo "Refusing to write to unexpected destination: $DEST" >&2
    exit 1
fi

cp "$SRC" "$DEST"
chmod 644 "$DEST"
