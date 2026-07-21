# Stow-Python - manage farms of symbolic links
# Python reimplementation of GNU Stow, and a derivative work of it.
#
# Copyright (C) 1993, 1994, 1995, 1996 by Bob Glickstein
# Copyright (C) 2000, 2001 Guillaume Morin
# Copyright (C) 2007 Kahlil Hodgson
# Copyright (C) 2011 Adam Spiers
# Copyright (C) 2025, 2026 Istvan Sarandi
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Stow-Python is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Stow-Python is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.

"""
stow-python - Python implementation of GNU Stow

This package provides a Pythonic implementation of GNU Stow,
a symlink farm manager.

Basic usage::

    from stow_python import stow, unstow, restow

    # Stow packages
    result = stow("emacs", "vim", dir="./stow", target="/home/user")
    if result.conflicts:
        print("Conflicts:", result.conflicts)

    # Unstow packages
    result = unstow("vim", dir="./stow", target="/home/user")

    # Restow (unstow + stow) after updating package
    result = restow("emacs", dir="./stow", target="/home/user")

With configuration reuse::

    from stow_python import stow, StowConfig

    config = StowConfig(dir="./stow", target="/home/user", dotfiles=True)
    stow("pkg1", config=config)
    stow("pkg2", config=config)

Simulation mode::

    result = stow("pkg", dir="./stow", target="/home/user", simulate=True)
    print("Would perform:", result.tasks)
"""

from stow_python.stow import stow, unstow, restow
from stow_python.types import (
    StowConfig,
    StowResult,
    StowError,
    StowInternalError,
    StowCLIError,
)
from stow_python.util import VERSION as __version__

# CLI entry point
from stow_python.cli import main

__all__ = [
    "stow",
    "unstow",
    "restow",
    "StowConfig",
    "StowResult",
    "StowError",
    "StowInternalError",
    "StowCLIError",
    "__version__",
    "main",
]
