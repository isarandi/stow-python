# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

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
    StowConflictError,
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
    "StowConflictError",
    "StowCLIError",
    "__version__",
    "main",
]
