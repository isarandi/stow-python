# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
stow-python - Python implementation of GNU Stow

This package provides a Pythonic implementation of GNU Stow,
a symlink farm manager.
"""

from stow_python.types import Task, TaskAction, TaskType, Operation, StowOptions
from stow_python.util import (
    error,
    internal_error,
    debug,
    set_debug_level,
    set_test_mode,
    join_paths,
    parent,
    canon_path,
    restore_cwd,
    adjust_dotfile,
    unadjust_dotfile,
    is_a_directory,
)
from stow_python.stow import Stow
from stow_python.cli import main

__version__ = "2.4.1"
__all__ = [
    "Stow",
    "Task",
    "TaskAction",
    "TaskType",
    "Operation",
    "StowOptions",
    "main",
    "error",
    "internal_error",
    "debug",
    "set_debug_level",
    "set_test_mode",
    "join_paths",
    "parent",
    "canon_path",
    "restore_cwd",
    "adjust_dotfile",
    "unadjust_dotfile",
    "is_a_directory",
]
