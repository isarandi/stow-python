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

# Fix the lib path in bin/stow to use the local lib directory instead of install
# The generated bin/stow has 'use lib "...install/share/perl/..."' which doesn't exist
# after just 'make' (without 'make install'). Point it to the local lib/ instead.
sed -i 's|use lib "[^"]*";|use lib "'"$DEST_DIR"'/lib";|' bin/stow bin/chkstow

echo "Perl stow ${VERSION} built in ${DEST_DIR}"
