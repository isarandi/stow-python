# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Utility functions for stow-python.

This module contains general-purpose utilities used throughout stow-python,
including error handling, debugging, and path manipulation.
"""

from __future__ import annotations

import errno as errno_module
import os
import re
import stat
import sys
import traceback

VERSION = "2.4.1"
PROGRAM_NAME = "stow"

# Track the last errno from filesystem operations.
# This mimics Perl's $! behavior where file test operators set errno.
_last_errno = 0

# Debug level and test mode are module-level state
_debug_level = 0
_test_mode = False


def error(format_str: str, *args) -> None:
    """
    Output an error message and exit.

    Mimics Perl's die() behavior: if errno ($!) is non-zero,
    the exit code is the errno value. Otherwise exits with 255.
    """
    global _last_errno
    msg = format_str % args if args else format_str
    print(f"{PROGRAM_NAME}: ERROR: {msg}", file=sys.stderr)

    # Perl's die() uses $! as exit code if non-zero, otherwise 255
    if _last_errno != 0:
        exit_code = _last_errno
        _last_errno = 0  # Reset after use
    else:
        exit_code = 255
    sys.exit(exit_code)


def internal_error(message: str, *args) -> None:
    """Output internal error message with stack trace and exit."""
    error_msg = message % args if args else message
    stack = traceback.format_stack()
    stacktrace = "".join(stack[:-1])

    print(
        f"\n{PROGRAM_NAME}: INTERNAL ERROR: {error_msg}\n{stacktrace}", file=sys.stderr
    )
    print(
        "This _is_ a bug. Please submit a bug report so we can fix it! :-)",
        file=sys.stderr,
    )
    print(
        "See https://github.com/isarandi/stow-python for how to do this.",
        file=sys.stderr,
    )
    sys.exit(1)


def is_a_directory(path: str) -> bool:
    """
    Check if path is a directory, setting errno like Perl's -d operator.

    Returns True if path is a directory, False otherwise.
    Sets _last_errno to the errno if the stat fails.
    """
    global _last_errno
    try:
        stat_result = os.stat(path)
        if stat.S_ISDIR(stat_result.st_mode):
            _last_errno = 0
            return True
        else:
            _last_errno = errno_module.ENOTDIR
            return False
    except OSError as e:
        _last_errno = e.errno
        return False


def set_debug_level(level: int) -> None:
    """Set verbosity level for debug()."""
    global _debug_level
    _debug_level = level


def get_debug_level() -> int:
    """Get current debug level."""
    return _debug_level


def set_test_mode(on_or_off: bool) -> None:
    """Set test mode on or off."""
    global _test_mode
    _test_mode = bool(on_or_off)


def get_test_mode() -> bool:
    """Get current test mode."""
    return _test_mode


def debug(level: int, *args) -> None:
    """
    Log to STDERR based on debug_level setting.

    Verbosity rules:
        0: errors only
        >= 1: print operations: LINK/UNLINK/MKDIR/RMDIR/MV
        >= 2: print operation exceptions (skipping, deferring, overriding)
        >= 3: print trace detail: stow/unstow/package/contents/node
        >= 4: debug helper routines
        >= 5: debug ignore lists

    Supports two calling conventions for backwards compatibility:
        debug(level, msg)
        debug(level, indent_level, msg)
    """
    # Handle backwards-compatible calling conventions
    if len(args) >= 2 and isinstance(args[0], int):
        indent_level = args[0]
        msg = args[1]
    elif len(args) >= 1:
        indent_level = 0
        msg = args[0]
    else:
        return

    if _debug_level >= level:
        indent = "    " * indent_level
        if _test_mode:
            print(f"# {indent}{msg}")
        else:
            print(f"{indent}{msg}", file=sys.stderr)


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

        # Apply canonpath-like normalization
        part = _canonpath(part)

        if part.startswith("/"):
            result = part  # absolute path, ignore all previous parts
        else:
            if result and result != "/":
                result += "/"
            result += part

        debug(7, 6, f"| Join now: {result}")

    debug(6, 5, f"| Joined: {result}")

    # Need this to remove any initial ./
    result = _canonpath(result)

    # Remove foo/.. patterns where foo is not ..
    while True:
        new_result = re.sub(r"(^|/)(?!\.\.)[^/]+/\.\.(/|$)", r"\1", result)
        if new_result == result:
            break
        result = new_result

    debug(6, 5, f"| After .. removal: {result}")

    result = _canonpath(result)
    debug(5, 5, f"| Final join: {result}")

    return result


def _canonpath(path: str) -> str:
    """
    Clean up a path by removing redundant separators and up-level references.

    Mimics Perl's File::Spec->canonpath() behavior.
    Does NOT resolve symlinks or check if path exists.
    """
    if not path:
        return path

    # Remove duplicate slashes
    path = re.sub(r"/+", "/", path)

    # Remove trailing slash (unless it's just "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # Remove leading ./ (but not just ".")
    path = re.sub(r"^\./", "", path)

    # Remove /. at the end
    path = re.sub(r"/\.$", "", path)

    # Remove /./ in the middle
    path = re.sub(r"/\./", "/", path)

    # If we ended up with empty string, return '.'
    if not path:
        path = "."

    return path


def parent(*path_parts: str) -> str:
    """
    Find the parent of the given path.

    Mimics Perl: split m{/+}, $path; pop @elts; join '/', @elts
    """
    path = "/".join(path_parts)

    # Split on one or more slashes
    elts = re.split(r"/+", path)

    # Perl's split drops trailing empty strings
    while elts and elts[-1] == "":
        elts.pop()

    if elts:
        elts.pop()

    return "/".join(elts)


def canon_path(path: str) -> str:
    """
    Find absolute canonical path of given path.

    Uses chdir() to resolve symlinks and relative paths.
    """
    cwd = os.getcwd()
    try:
        os.chdir(path)
    except OSError:
        error(f"canon_path: cannot chdir to {path} from {cwd}")

    canon = os.getcwd()
    restore_cwd(cwd)
    return canon


def restore_cwd(prev: str) -> None:
    """
    Restore previous working directory.

    Dies if directory no longer exists.
    """
    try:
        os.chdir(prev)
    except OSError:
        error(f"Your current directory {prev} seems to have vanished")


def adjust_dotfile(pkg_node: str) -> str:
    """
    Convert dot-X to .X for dotfiles mode.

    Used when stowing with --dotfiles flag.
    Only transforms 'dot-X' to '.X' when X starts with a non-dot character.
    """
    match = re.match(r"^dot-([^.])", pkg_node)
    if match:
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
