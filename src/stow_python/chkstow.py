# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""chkstow - Check stow target directory for problems."""

from __future__ import annotations

import os
import re
import stat
import sys
from collections.abc import Iterator
from enum import Enum, auto


class Mode(Enum):
    BAD_LINKS = auto()
    ALIENS = auto()
    LIST = auto()


DEFAULT_TARGET = os.environ.get("STOW_DIR", "/usr/local/")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) == 1:
        usage()

    target, mode = parse_args(sys.argv[1:])

    match mode:
        case Mode.BAD_LINKS:
            for path in find_bad_links(target):
                print(f"Bogus link: {path}")
        case Mode.ALIENS:
            for path in find_aliens(target):
                print(f"Unstowed file: {path}")
        case Mode.LIST:
            for pkg in list_packages(target):
                print(pkg)


def parse_args(args: list[str]) -> tuple[str, Mode]:
    """Parse arguments, return (target, mode)."""
    target = DEFAULT_TARGET
    mode = Mode.BAD_LINKS

    i = 0
    while i < len(args):
        arg = args[i]
        match arg:
            case "-b" | "--badlinks":
                mode = Mode.BAD_LINKS
            case "-a" | "--aliens":
                mode = Mode.ALIENS
            case "-l" | "--list":
                mode = Mode.LIST
            case "-t" | "--target" if i + 1 < len(args):
                i += 1
                target = args[i]
            case _ if arg.startswith("--target="):
                target = arg.removeprefix("--target=")
            case _:
                usage()
        i += 1

    return target, mode


def usage() -> None:
    """Print usage message and exit."""
    print(f"""\
USAGE: chkstow [options]

Options:
    -t DIR, --target=DIR  Set the target directory to DIR
                          (default is {DEFAULT_TARGET})
    -b, --badlinks        Report symlinks that point to non-existent files
    -a, --aliens          Report non-symlinks in the target directory
    -l, --list            List packages in the target directory

--badlinks is the default mode.""")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


def find_bad_links(target: str) -> Iterator[str]:
    """Yield broken symlinks in target."""
    yield from _walk_target(target, _bad_links_wanted)


def find_aliens(target: str) -> Iterator[str]:
    """Yield files that are neither symlinks nor directories."""
    yield from _walk_target(target, _aliens_wanted)


def list_packages(target: str) -> list[str]:
    """Return sorted list of packages stowed in target."""
    packages: set[str] = set()
    for dest in _walk_target(target, _list_wanted):
        dest = re.sub(r"^(?:\.\./)+stow/", "", dest)
        dest = re.sub(r"/.*", "", dest)
        packages.add(dest)

    return sorted(packages - {"", ".."})


def _bad_links_wanted(entry: str, full_path: str, is_link: bool) -> str | None:
    """Perl: -l && !-e && print"""
    # Perl's -l uses cached stat from File::Find, so no extra lstat
    # Perl's !-e does stat to check if target exists
    if is_link and not os.path.exists(entry):
        return full_path
    return None


def _aliens_wanted(entry: str, full_path: str, is_link: bool) -> str | None:
    """Perl: !-l && !-d && print"""
    # Perl short-circuits: if -l is true, -d is not evaluated
    if is_link:
        return None
    # For non-links, Perl's -d does stat
    is_dir = os.path.isdir(entry)
    if not is_dir:
        return full_path
    return None


def _list_wanted(entry: str, full_path: str, is_link: bool) -> str | None:
    """Perl: -l && readlink"""
    if is_link:
        return os.readlink(entry)
    return None


def _walk_target(target: str, wanted) -> Iterator[str]:
    """Walk target directory, calling wanted callback for each entry.

    Matches Perl's File::Find behavior with chdir and relative paths.
    wanted(entry, full_path) is called with cwd set to entry's directory.
    """
    # File::Find saves cwd at start and returns to it at end
    start_cwd = os.getcwd()
    # Perl lstats the initial target twice
    os.lstat(target)
    os.lstat(target)

    # Track depth for multi-level chdir back
    final_depth = 0
    for result, result_depth in _file_find_chdir(target, "", wanted, depth=1):
        final_depth = result_depth
        if result is not None:
            yield result

    # Final chdir back to saved cwd (Perl uses absolute path from getcwd)
    if final_depth > 0:
        os.chdir(start_cwd)


def _file_find_chdir(target: str, prefix: str, wanted, depth: int = 1) -> Iterator[tuple[str, int]]:
    """Recursive File::Find-like walker using chdir and relative paths.

    Matches Perl's File::Find syscall pattern exactly:
    - open(".") to read current directory
    - stat .stow/.notstowed (preprocess)
    - For each entry: lstat to get type
      - If link: lstat again + readlink in wanted
      - If dir: just lstat (second lstat happens before chdir)
      - If file: lstat again + call wanted
    - Recurse into subdirs with lstat before each chdir
    - Multi-level chdir back (Perl optimization)

    Yields (result, depth_after) tuples. depth_after indicates how deep we are
    after processing, so caller can do multi-level chdir.
    """
    # File::Find calls wanted on the root directory only (depth 1)
    if depth == 1:
        dir_full_path = target + "/" + prefix if prefix else target
        wanted(".", dir_full_path, False)  # "." is not a symlink

    # Open and read current directory entries (Perl uses ".")
    try:
        entries = os.listdir(".")
    except OSError:
        return

    # preprocess: stat .stow and .notstowed (Perl's -e test)
    if _path_exists(".stow") or _path_exists(".notstowed"):
        # Perl outputs $File::Find::dir which is the full path from start
        skip_path = target + "/" + prefix if prefix else target
        print(f"skipping {skip_path}", file=sys.stderr)
        return

    # Process entries - Perl handles links immediately, defers dirs
    subdirs = []
    for entry in entries:
        try:
            st = os.lstat(entry)
        except OSError:
            continue

        is_dir = stat.S_ISDIR(st.st_mode)
        is_link = stat.S_ISLNK(st.st_mode)

        # Build full path (Perl's $File::Find::name)
        full_path = os.path.join(prefix, entry) if prefix else entry
        full_path = target + "/" + full_path

        if is_dir:
            # Dirs: just collect for later recursion
            subdirs.append((entry, full_path))
        else:
            # Files and symlinks: second lstat + wanted
            os.lstat(entry)
            result = wanted(entry, full_path, is_link)
            if result is not None:
                yield result, depth

    # Recurse into subdirectories with chdir
    # Track depth so we can do multi-level chdir back like Perl
    current_depth = depth
    for subdir, subdir_full_path in subdirs:
        # If we're deeper than expected, chdir back first
        if current_depth > depth:
            os.chdir("/".join([".."] * (current_depth - depth)))
            current_depth = depth

        os.lstat(subdir)  # Second lstat happens here, before chdir
        # Call wanted for dirs - generates stat for -d test
        wanted(subdir, subdir_full_path, False)
        os.chdir(subdir)
        current_depth += 1
        new_prefix = os.path.join(prefix, subdir) if prefix else subdir

        for result, result_depth in _file_find_chdir(target, new_prefix, wanted, current_depth):
            yield result, result_depth
            current_depth = result_depth

    # After all subdirs, return current depth for parent to handle chdir
    if current_depth > depth:
        # We're still deep from last recursion, parent will handle chdir
        pass
    # Yield a sentinel to communicate final depth (None result)
    yield None, current_depth


def _path_exists(path: str) -> bool:
    """Check if path exists using stat (like Perl's -e)."""
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
