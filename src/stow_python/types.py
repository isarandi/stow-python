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
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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


class Operation(Enum):
    """High-level stow operations."""

    STOW = "stow"
    UNSTOW = "unstow"
    RESTOW = "restow"


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


@dataclass
class StowOptions:
    """
    Configuration options for a Stow instance.

    Attributes:
        dir: The stow directory containing packages
        target: The target directory where symlinks are created
        verbose: Verbosity level (0-5)
        simulate: If True, don't make filesystem changes
        compat: Use legacy algorithm for unstowing
        dotfiles: Enable dot-prefix handling for dotfiles
        adopt: Import existing files into stow package
        no_folding: Disable tree folding optimization
        paranoid: Enable extra safety checks
        test_mode: Test mode (output to stdout instead of stderr)
        ignore: Patterns to ignore during stowing
        defer: Patterns to defer (skip if already stowed elsewhere)
        override: Patterns to force stow (replace existing stow)
    """

    dir: str
    target: str
    verbose: int = 0
    simulate: bool = False
    compat: bool = False
    dotfiles: bool = False
    adopt: bool = False
    no_folding: bool = False
    paranoid: bool = False
    test_mode: bool = False
    ignore: list[re.Pattern] = field(default_factory=list)
    defer: list[re.Pattern] = field(default_factory=list)
    override: list[re.Pattern] = field(default_factory=list)

    @classmethod
    def from_dict(cls, opts: dict) -> StowOptions:
        """Create from dict, handling key name conversions."""
        opts = dict(opts)  # Don't modify the original

        # Handle 'no-folding' -> no_folding conversion
        if "no-folding" in opts:
            opts["no_folding"] = opts.pop("no-folding")

        # Handle conflicts option (stored as conflicts in dict, not used in dataclass)
        opts.pop("conflicts", None)

        return cls(**opts)


@dataclass
class StowedPathResult:
    """
    Result of find_stowed_path() - identifies ownership of a symlink.

    This replaces the 3-tuple (pkg_path_from_cwd, stow_path, package)
    returned by find_stowed_path().
    """

    pkg_path_from_cwd: str
    stow_path: str
    package: str

    @property
    def is_found(self) -> bool:
        """Return True if a stowed path was found."""
        return bool(self.pkg_path_from_cwd)

    def __bool__(self) -> bool:
        return self.is_found

    def __iter__(self):
        """For backward compatibility with tuple unpacking."""
        return iter((self.pkg_path_from_cwd, self.stow_path, self.package))


@dataclass
class ConflictTracker:
    """
    Tracks conflicts discovered during stow/unstow planning.

    Conflicts are organized by action (stow/unstow) and package name.
    """

    _conflicts: dict = field(default_factory=dict)
    _count: int = 0

    def add(self, action: str, package: str, message: str) -> None:
        """Record a conflict."""
        self._conflicts.setdefault(action, {}).setdefault(package, []).append(message)
        self._count += 1

    @property
    def count(self) -> int:
        """Return the total number of conflicts."""
        return self._count

    def get_all(self) -> dict:
        """Return conflicts as a nested dict."""
        return self._conflicts

    def __bool__(self) -> bool:
        return self._count > 0

    def __contains__(self, action: str) -> bool:
        return action in self._conflicts

    def __getitem__(self, action: str) -> dict:
        return self._conflicts.get(action, {})
