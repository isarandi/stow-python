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


# Perl's stat/lstat builtins warn "Unsuccessful (l)stat on filename
# containing newline" when the syscall FAILS on a path whose name ENDS with
# a newline (the you-forgot-to-chomp heuristic in pp_sys.c — a newline in
# the middle does not warn, nor does a successful call). Every file test
# (-l, -d, -e, ...) goes through stat/lstat, so all stat-family calls in
# stow code must use these wrappers to reproduce the warnings.

def _warn_unsuccessful(path: str, syscall: str) -> None:
    """Print Perl's warning for a failed stat/lstat on a newline path."""
    if path.endswith("\n"):
        print(f"Unsuccessful {syscall} on filename containing newline", file=sys.stderr)


def lstat_with_newline_warning(path: str) -> os.stat_result:
    """os.lstat with Perl's unsuccessful-on-newline warning."""
    try:
        return os.lstat(path)
    except OSError:
        _warn_unsuccessful(path, "lstat")
        raise


def stat_with_newline_warning(path: str) -> os.stat_result:
    """os.stat with Perl's unsuccessful-on-newline warning."""
    try:
        return os.stat(path)
    except OSError:
        _warn_unsuccessful(path, "stat")
        raise


def islink_with_newline_warning(path: str) -> bool:
    """os.path.islink (one lstat) with Perl's newline warning."""
    try:
        st = os.lstat(path)
    except (OSError, ValueError):
        _warn_unsuccessful(path, "lstat")
        return False
    return stat.S_ISLNK(st.st_mode)


def isdir_with_newline_warning(path: str) -> bool:
    """os.path.isdir (one stat) with Perl's newline warning."""
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        _warn_unsuccessful(path, "stat")
        return False
    return stat.S_ISDIR(st.st_mode)


def exists_with_newline_warning(path: str) -> bool:
    """os.path.exists (one stat) with Perl's newline warning."""
    try:
        os.stat(path)
    except (OSError, ValueError):
        _warn_unsuccessful(path, "stat")
        return False
    return True


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


def get_debug_level() -> int:
    """Get current verbosity level."""
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


def canonpath(path: str) -> str:
    """
    Mimic Perl's File::Spec::Unix->canonpath() exactly.

    Normalizes a path by removing redundant separators and dot components,
    but does NOT resolve '..' in the middle of paths (unlike os.path.normpath).

    Transformations applied (in order):
        xx////xx   -> xx/xx      (collapse multiple slashes)
        xx/././xx  -> xx/xx      (remove /. sequences)
        ./xx       -> xx         (remove leading ./)
        /../../xx  -> /xx        (collapse leading /.. sequences)
        /..        -> /          (collapse /.. at end)
        xx/        -> xx         (remove trailing slash)

    This matches Perl's behavior where '/a/b/../c' stays as '/a/b/../c',
    NOT resolved to '/a/c' like Python's os.path.normpath would do.
    """
    if not path:
        return path

    # xx////xx -> xx/xx (collapse multiple slashes)
    path = re.sub(r'/{2,}', '/', path)

    # xx/././xx -> xx/xx and trailing /. -> / (remove /. sequences)
    # Perl: s{(?:/\.)+(?:/|\z)}{/}g
    # \Z (absolute end) matches Perl's \z; the previous lookahead form with $
    # dropped "/." to "" instead of "/" and would misfire before a trailing
    # newline in the path.
    path = re.sub(r'(?:/\.)+(?:/|\Z)', '/', path)

    # ./xx -> xx (remove leading ./, but preserve standalone ".")
    # Perl: s|^(?:\./)+||s unless $path eq "./"
    if path != "./":
        path = re.sub(r'^(?:\./)+', '', path)

    # /../../xx -> /xx (collapse leading /.. after root)
    # Perl: s|^/(?:\.\./)+|/|
    path = re.sub(r'^/(?:\.\./)+', '/', path)

    # /.. -> / (just /.. becomes /)
    # Perl source says s|^/\.\.$|/|, but the XS implementation that actually
    # runs (PathTools' canonpath) compares the whole string, so "/..\n" is
    # NOT rewritten. Match the XS behavior, which is what Stow really calls.
    if path == '/..':
        path = '/'

    # xx/ -> xx (remove trailing slash, but preserve standalone "/")
    # Perl: s|/\z|| unless $path eq "/"
    if path != '/' and path.endswith('/'):
        path = path[:-1]

    # If we ended up with empty string, return empty (Perl returns undef/empty)
    return path


def join_paths(*paths: str) -> str:
    """
    Concatenate given paths with Perl-compatible normalization.

    Matches Perl's Stow::Util::join_paths() exactly:
    1. Applies canonpath() to each part and the result
    2. Removes 'foo/..' pairs (but NOT '../..')

    For example:
        join_paths('a/b', '../c') -> 'a/c'      (foo/.. resolved)
        join_paths('a', '../../b') -> '../b'    (only one .. resolved)
    """
    debug(5, 5, f"| Joining: {' '.join(paths)}")
    result = ""

    for part in paths:
        if not part:
            continue

        part = canonpath(part)

        if part.startswith("/"):
            result = part  # absolute path, ignore all previous parts
        else:
            if result and result != "/":
                result += "/"
            result += part

        debug(7, 6, f"| Join now: {result}")

    debug(6, 5, f"| Joined: {result}")

    # Need this to remove any initial ./
    result = canonpath(result)

    # Remove foo/.. pairs (but not ../..)
    # Perl: 1 while $result =~ s,(^|/)(?!\.\.)[^/]+/\.\.(/|$),$1,;
    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'(^|/)(?!\.\.)[^/]+/\.\.(/|$)', r'\1', result)
    debug(6, 5, f"| After .. removal: {result}")

    result = canonpath(result)
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

    # Pre-stat for NFS robustness (like Perl's File::Copy::move)
    try:
        dst_stat = os.stat(dst)
    except OSError:
        dst_stat = None

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

    # NFS workaround: check if rename succeeded despite error
    # This happens when the NFS server ACK is lost but the rename completed
    if src_size is not None:
        src_exists = os.path.exists(src)
        if not src_exists:
            try:
                new_dst_stat = os.stat(dst)
                if new_dst_stat.st_size == src_size:
                    # Rename actually succeeded
                    return
            except OSError:
                pass

    # Fall back to copy+delete for cross-filesystem moves
    shutil.copy2(src, dst)
    os.unlink(src)
