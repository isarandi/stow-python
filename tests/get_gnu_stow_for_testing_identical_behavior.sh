#!/bin/bash
#
# This file is part of GNU Stow.
#
# GNU Stow is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GNU Stow is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.
# Download and build Perl source of the original GNU Stow for oracle testing
# Pinned to the version used for the Python port

set -e
set -o pipefail

VERSION="2.4.1"
# ftpmirror.gnu.org redirects to a community mirror chosen per request, and
# an unhealthy one answers with a short error page instead of the tarball.
# ftp.gnu.org is the canonical fallback for that case.
MIRROR_URL="https://ftpmirror.gnu.org/stow/stow-${VERSION}.tar.gz"
CANONICAL_URL="https://ftp.gnu.org/gnu/stow/stow-${VERSION}.tar.gz"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="${SCRIPT_DIR}/gnu_stow_for_testing"
TARBALL="${DEST_DIR}/stow-${VERSION}.tar.gz"

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"

# Download to a file and verify it before unpacking: piping straight into tar
# hides a failed transfer as an unhelpful "Unrecognized archive format".
# --fail turns an HTTP error page into a non-zero exit instead of a 166-byte
# "tarball", and the retries cover a mirror that is merely slow or flaky.
download() {
    curl --fail --location --silent --show-error \
        --retry 3 --retry-delay 2 --retry-connrefused \
        --output "$TARBALL" "$1"
}

if ! download "$MIRROR_URL"; then
    echo "Mirror failed, falling back to ${CANONICAL_URL}" >&2
    download "$CANONICAL_URL"
fi

if ! tar tzf "$TARBALL" >/dev/null 2>&1; then
    echo "Downloaded file is not a valid gzip archive:" >&2
    ls -l "$TARBALL" >&2
    exit 1
fi

tar xz -C "$DEST_DIR" --strip-components=1 -f "$TARBALL"
rm -f "$TARBALL"

# Build stow (generates bin/stow, lib/Stow.pm, etc. from .in templates)
cd "$DEST_DIR"
./configure --prefix="$DEST_DIR/install" >/dev/null
make bin/stow bin/chkstow lib/Stow.pm lib/Stow/Util.pm >/dev/null

# Fix the lib path in bin/stow to use the local lib directory instead of install
# The generated bin/stow has 'use lib "...install/share/perl/..."' which doesn't exist
# after just 'make' (without 'make install'). Point it to the local lib/ instead.
sed -i 's|use lib "[^"]*";|use lib "'"$DEST_DIR"'/lib";|' bin/stow bin/chkstow

echo "Perl stow ${VERSION} built in ${DEST_DIR}"
