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
Type definitions for stow-python.

This module contains enums and dataclasses that define the core data
structures used throughout stow-python.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Union


class StowError(Exception):
    """Base exception for stow operation errors.

    Attributes:
        message: Error description
        errno: Exit code (for CLI compatibility)
    """

    def __init__(self, message: str, errno: int = 1):
        self.message = message
        self.errno = errno
        super().__init__(message)


class StowInternalError(StowError):
    """Internal error indicating a bug in stow."""

    def __init__(self, message: str):
        super().__init__(message, errno=1)


class StowCLIError(StowError):
    """CLI error - printed without program name prefix."""

    pass


class Action(Enum):
    """Actions for link/directory tasks."""

    CREATE = "create"
    REMOVE = "remove"


@dataclass
class LinkTask:
    """Create or remove a symlink."""

    action: Action
    path: str
    source: str
    skipped: bool = False


@dataclass
class DirTask:
    """Create or remove a directory."""

    action: Action
    path: str
    skipped: bool = False


@dataclass
class MoveTask:
    """Move a file."""

    path: str
    dest: str
    skipped: bool = False


# typing.Union rather than the | operator: the aliases are evaluated at
# runtime, and runtime unions of classes need Python 3.10
Task = Union[LinkTask, DirTask, MoveTask]


@dataclass(frozen=True)
class StowScanJob:
    """Planner job: list a package directory and visit its entries."""

    stow_path: str
    package: str
    pkg_subdir: str
    target_subdir: str


@dataclass(frozen=True)
class StowNodeJob:
    """Planner job: run per-entry checks and stow one node."""

    stow_path: str
    package: str
    pkg_subdir: str
    target_subdir: str
    node: str


@dataclass(frozen=True)
class UnstowScanJob:
    """Planner job: list a directory and visit its entries for unstowing."""

    package: str
    pkg_subdir: str
    target_subdir: str


@dataclass(frozen=True)
class UnstowNodeJob:
    """Planner job: run per-entry checks and unstow one node."""

    package: str
    pkg_subdir: str
    target_subdir: str
    node: str


@dataclass(frozen=True)
class FoldJob:
    """Planner job: fold a directory once its subtree has been unstowed."""

    target_subdir: str


@dataclass(frozen=True)
class CleanupJob:
    """Planner job: clean invalid links after a directory's entries are done."""

    target_subdir: str


StowJob = Union[StowScanJob, StowNodeJob]
UnstowJob = Union[UnstowScanJob, UnstowNodeJob, FoldJob, CleanupJob]


@dataclass(frozen=True)
class StowedPath:
    """Result of find_stowed_path - identifies ownership of a symlink."""

    path: str
    stow_dir: str
    package: str


@dataclass(frozen=True)
class PackageSubpath:
    """A path within a package (package name + subpath within it)."""

    package: str
    subpath: str


@dataclass(frozen=True)
class MarkedStowDir:
    """A marked stow directory and the package within it."""

    stow_dir: str
    package: str


@dataclass(frozen=True)
class IgnorePatterns:
    """Compiled ignore patterns from stow ignore files."""

    default_regexp: re.Pattern[str] | None
    local_regexp: re.Pattern[str] | None


@dataclass(frozen=True)
class StowConfig:
    """Configuration for stow operations.

    ignore/defer/override are regex pattern STRINGS as the user would pass
    them on the command line; anchoring (--ignore matches at the end of a
    path, --defer/--override at the start) and compilation happen inside
    the stower, so library callers and the CLI get identical semantics.

    An empty target (the default; None is tolerated too) is replaced by
    the parent of the stow dir.
    """

    dir: str = "."
    target: str = ""
    dotfiles: bool = False
    adopt: bool = False
    no_folding: bool = False
    simulate: bool = False
    verbose: int = 0
    compat: bool = False
    ignore: tuple[str, ...] = ()
    defer: tuple[str, ...] = ()
    override: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target:
            derived = os.path.dirname(self.dir.rstrip("/")) or "."
            object.__setattr__(self, "target", derived)


@dataclass
class StowResult:
    """Result of a stow/unstow/restow operation.

    tasks holds the filesystem changes that were performed, or in simulate
    mode would have been performed; tasks that were planned but then
    reverted during planning are excluded in both cases.
    """

    success: bool
    conflicts: dict[str, list[str]]  # Empty if success
    tasks: list[Task]  # Tasks that were (or would be) performed
