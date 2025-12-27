#!/bin/bash
# Download and build Perl source of the original GNU Stow for oracle testing
# Pinned to the version used for the Python port

set -e

VERSION="2.4.1"
URL="https://ftpmirror.gnu.org/stow/stow-${VERSION}.tar.gz"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="${SCRIPT_DIR}/gnu_stow_for_testing"

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
curl -L "$URL" | tar xz -C "$DEST_DIR" --strip-components=1

# Build stow (generates bin/stow, lib/Stow.pm, etc. from .in templates)
cd "$DEST_DIR"
./configure --prefix="$DEST_DIR/install" >/dev/null
make bin/stow bin/chkstow lib/Stow.pm lib/Stow/Util.pm >/dev/null

echo "Perl stow ${VERSION} built in ${DEST_DIR}"
