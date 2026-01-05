# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Utility functions for stow-python.

This module contains general-purpose utilities used throughout stow-python,
including error handling, debugging, and path manipulation.
"""

from __future__ import annotations

from contextlib import contextmanager
import errno as errno_module
import logging
import os
import re
import stat
import sys

from stow_python.types import StowError

VERSION = "2.4.1"
PROGRAM_NAME = "stow"

# --- Logging setup ---


class _VerbosityFilter(logging.Filter):
    """Filter that checks message level against current verbosity setting."""

    def __init__(self):
        super().__init__()
        self.verbosity = 0

    def filter(self, record: logging.LogRecord) -> bool:
        return self.verbosity >= getattr(record, "stow_level", 0)


class _IndentFormatter(logging.Formatter):
    """Formatter that outputs just the indented message, nothing else."""

    def format(self, record: logging.LogRecord) -> str:
        indent = "    " * getattr(record, "indent", 0)
        return f"{indent}{record.getMessage()}"


_verbosity_filter = _VerbosityFilter()
_logger = logging.getLogger("stow")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_IndentFormatter())
_handler.addFilter(_verbosity_filter)
_logger.addHandler(_handler)


def require_directory(path: str, msg: str) -> None:
    """Raise StowError if path is not a directory."""
    try:
        stat_result = os.stat(path)
        if not stat.S_ISDIR(stat_result.st_mode):
            raise StowError(msg, errno=errno_module.ENOTDIR)
    except OSError as e:
        raise StowError(msg, errno=e.errno) from e


def set_debug_level(level: int) -> None:
    """Set verbosity level for debug()."""
    _verbosity_filter.verbosity = level


def debug(level: int, indent: int, msg: str) -> None:
    """
    Log to STDERR based on debug_level setting.

    Verbosity rules:
        0: errors only
        >= 1: print operations: LINK/UNLINK/MKDIR/RMDIR/MV
        >= 2: print operation exceptions (skipping, deferring, overriding)
        >= 3: print trace detail: stow/unstow/package/contents/node
        >= 4: debug helper routines
        >= 5: debug ignore lists
    """
    _logger.debug(msg, extra={"stow_level": level, "indent": indent})


def join_paths(*paths: str) -> str:
    """
    Concatenate given paths with normalization.

    Factors out redundant path elements: '//' => '/', 'a/b/../c' => 'a/c'.
    This behavior is deliberately different from canon_path() because
    join_paths() is used to calculate relative paths that may not exist yet.
    """
    debug(5, 5, f"| Joining: {' '.join(paths)}")
    result = ""

    for part in paths:
        if not part:
            continue

        part = os.path.normpath(part)

        if part.startswith("/"):
            result = part  # absolute path, ignore all previous parts
        else:
            if result and result != "/":
                result += "/"
            result += part

        debug(7, 6, f"| Join now: {result}")

    debug(6, 5, f"| Joined: {result}")

    result = os.path.normpath(result)
    debug(5, 5, f"| Final join: {result}")

    return result


def parent(*path_parts: str) -> str:
    """Find the parent of the given path."""
    path = re.sub(r"/+", "/", "/".join(path_parts)).rstrip("/")
    result = os.path.dirname(path)
    return "" if result == "/" else result


def canon_path(path: str) -> str:
    """
    Find absolute canonical path of given path.

    Uses chdir() to resolve symlinks and relative paths.
    """
    cwd = os.getcwd()
    try:
        os.chdir(path)
    except OSError as e:
        raise StowError(f"canon_path: cannot chdir to {path} from {cwd}") from e

    canon = os.getcwd()
    restore_cwd(cwd)
    return canon


def restore_cwd(prev: str) -> None:
    """
    Restore previous working directory.

    Raises StowError if directory no longer exists.
    """
    try:
        os.chdir(prev)
    except OSError as e:
        raise StowError(f"Your current directory {prev} seems to have vanished") from e


@contextmanager
def within_dir(path: str, name: str = "directory"):
    """Context manager to execute code within a directory, preserving cwd."""
    cwd = os.getcwd()
    try:
        os.chdir(path)
    except OSError as e:
        raise StowError(f"Cannot chdir to {name}: {path} ({e})") from e

    debug(3, 0, f"cwd now {path}")
    try:
        yield
    finally:
        restore_cwd(cwd)
        debug(3, 0, f"cwd restored to {cwd}")


def adjust_dotfile(pkg_node: str) -> str:
    """
    Convert dot-X to .X for dotfiles mode.

    Used when stowing with --dotfiles flag.
    Only transforms 'dot-X' to '.X' when X is non-empty and starts with a non-dot character.
    """
    if (
        len(pkg_node) > 4
        and pkg_node.startswith("dot-")
        and not pkg_node.startswith("dot-.")
    ):
        return "." + pkg_node[4:]
    return pkg_node


def unadjust_dotfile(target_node: str) -> str:
    """
    Reverse operation: .X to dot-X

    Used during unstow with --compat and --dotfiles.
    """
    if target_node in (".", ".."):
        return target_node

    if target_node.startswith("."):
        return "dot-" + target_node[1:]

    return target_node
