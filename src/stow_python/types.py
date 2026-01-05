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
from typing import Optional


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


class StowProgrammingError(StowError):
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


class TaskAction(Enum):
    """Actions that can be performed on filesystem nodes."""

    CREATE = "create"
    REMOVE = "remove"
    SKIP = "skip"
    MOVE = "move"


class TaskType(Enum):
    """Types of filesystem nodes that tasks operate on."""

    LINK = "link"
    DIR = "dir"
    FILE = "file"


@dataclass(slots=True)
class Task:
    """
    A deferred filesystem operation.

    Tasks are queued during the planning phase and executed only after
    all potential conflicts have been assessed.
    """

    action: TaskAction
    type: TaskType
    path: str
    source: Optional[str] = None  # For links: the symlink destination
    dest: Optional[str] = None  # For moves: the destination path


@dataclass(slots=True, frozen=True)
class StowedPath:
    """Result of find_stowed_path - identifies ownership of a symlink."""

    path: str
    stow_dir: str
    package: str


@dataclass(slots=True, frozen=True)
class PackageSubpath:
    """A path within a package (package name + subpath within it)."""

    package: str
    subpath: str


@dataclass(slots=True, frozen=True)
class MarkedStowDir:
    """A marked stow directory and the package within it."""

    stow_dir: str
    package: str


@dataclass(slots=True, frozen=True)
class IgnorePatterns:
    """Compiled ignore patterns from stow ignore files."""

    default_regexp: re.Pattern | None
    local_regexp: re.Pattern | None


@dataclass(frozen=True)
class StowConfig:
    """Immutable configuration for stow operations."""

    dir: str = "."
    target: str | None = None  # Default: parent of dir
    dotfiles: bool = False
    adopt: bool = False
    no_folding: bool = False
    simulate: bool = False
    verbose: int = 0
    compat: bool = False
    ignore: tuple[re.Pattern, ...] = ()
    defer: tuple[re.Pattern, ...] = ()
    override: tuple[re.Pattern, ...] = ()


@dataclass
class StowResult:
    """Result of a stow/unstow/restow operation."""

    success: bool
    conflicts: dict[str, list[str]]  # Empty if success
    tasks: list[Task]  # Tasks that were (or would be) performed
