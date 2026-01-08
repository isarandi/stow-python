# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Type definitions for stow-python.

This module contains enums and dataclasses that define the core data
structures used throughout stow-python.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union


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


class StowConflictError(StowError):
    """Error raised when stow operations would cause conflicts.

    Attributes:
        conflicts: Dict mapping package names to lists of conflict messages
    """

    def __init__(self, message: str, conflicts: dict[str, list[str]]):
        self.conflicts = conflicts
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


Task = Union[LinkTask, DirTask, MoveTask]


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

    default_regexp: Optional[re.Pattern]
    local_regexp: Optional[re.Pattern]


class StowConfig:
    """Configuration for stow operations."""

    def __init__(
        self,
        dir: str = ".",
        target: Optional[str] = None,
        dotfiles: bool = False,
        adopt: bool = False,
        no_folding: bool = False,
        simulate: bool = False,
        verbose: int = 0,
        compat: bool = False,
        ignore: tuple[re.Pattern, ...] = (),
        defer: tuple[re.Pattern, ...] = (),
        override: tuple[re.Pattern, ...] = (),
    ):
        import os

        self.dir = dir
        self.target: str = (
            target if target else (os.path.dirname(dir.rstrip("/")) or ".")
        )
        self.dotfiles = dotfiles
        self.adopt = adopt
        self.no_folding = no_folding
        self.simulate = simulate
        self.verbose = verbose
        self.compat = compat
        self.ignore = ignore
        self.defer = defer
        self.override = override


@dataclass
class StowResult:
    """Result of a stow/unstow/restow operation."""

    success: bool
    conflicts: dict[str, list[str]]  # Empty if success
    tasks: list[Task]  # Tasks that were (or would be) performed
