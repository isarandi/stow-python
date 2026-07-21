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
import threading

from stow_python.types import StowError

VERSION = "2.4.1"
PROGRAM_NAME = "stow"

# Planning and execution chdir into the target tree (mirroring Perl stow's
# syscall sequence), which is process-global state; this lock serializes
# concurrent stow operations within one process. Re-entrant so that nested
# phases of one operation can each take it.
process_lock = threading.RLock()

# --- Logging setup ---
#
# The "stow" logger gets its handler at import time with propagate=False.
# This is deliberate: the debug() stream must reach stderr in Perl-stow's
# exact format even for pure library use (Perl's Stow.pm prints the same
# way), and must never be reformatted by an embedding application's root
# logger config. Embedders who want the output elsewhere can replace the
# handlers on logging.getLogger("stow").


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
        raise StowError(msg, errno=e.errno or 1) from e


def set_debug_level(level: int) -> None:
    """Set verbosity level for debug()."""
    _verbosity_filter.verbosity = level


def get_debug_level() -> int:
    """Return the current verbosity level for debug()."""
    return _verbosity_filter.verbosity


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

    # normpath() covers both of Perl's steps here (canonpath plus the
    # explicit foo/.. removal loop), so the intermediate debug line shows
    # the same value as the final one.
    result = os.path.normpath(result)
    debug(6, 5, f"| After .. removal: {result}")
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


def move(src: str, dst: str) -> None:
    """
    Move a file from src to dst, with NFS robustness.

    Matches Perl's File::Copy::move behavior for robustness on NFS:
    When rename() fails on NFS due to a lost server ACK, the rename
    may have actually succeeded. We detect this by pre-stat'ing the
    source and checking if post-failure the source is gone and the
    destination has the expected size.

    Falls back to copy+delete for cross-filesystem moves.
    """
    import shutil

    # Handle moving into a directory (like Perl's File::Copy::move)
    # This also produces the same stat syscall as Perl's -d check
    if os.path.isdir(dst) and not os.path.isdir(src):
        dst = os.path.join(dst, os.path.basename(src))

    # Pre-stat both files for NFS robustness (matches Perl's File::Copy::move)
    try:
        dst_stat = os.stat(dst)
        dst_size, dst_mtime = dst_stat.st_size, dst_stat.st_mtime
    except OSError:
        dst_size, dst_mtime = None, None

    try:
        src_size = os.stat(src).st_size
    except OSError:
        src_size = None

    # Try rename first (same-filesystem move)
    try:
        os.rename(src, dst)
        return
    except OSError:
        pass

    # NFS workaround: rename may succeed but return error due to lost ACK.
    # Detect this by checking if src is gone and dst has the expected content.
    if src_size is not None and not os.path.exists(src):
        try:
            new_stat = os.stat(dst)
            new_size, new_mtime = new_stat.st_size, new_stat.st_mtime
            # Rename succeeded if: dst didn't exist before, OR size/mtime changed
            dst_changed = (
                dst_size is None or new_size != dst_size or new_mtime != dst_mtime
            )
            if dst_changed and new_size == src_size:
                return
        except OSError:
            pass

    # Fall back to copy+delete for cross-filesystem moves
    shutil.copy2(src, dst)
    os.unlink(src)
