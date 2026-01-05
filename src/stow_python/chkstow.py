# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""chkstow - Check stow target directory for problems."""

from __future__ import annotations

import os
import re
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
    for path in _walk_target(target):
        if os.path.islink(path) and not os.path.exists(path):
            yield path


def find_aliens(target: str) -> Iterator[str]:
    """Yield files that are neither symlinks nor directories."""
    for path in _walk_target(target):
        if not os.path.islink(path) and not os.path.isdir(path):
            yield path


def list_packages(target: str) -> list[str]:
    """Return sorted list of packages stowed in target."""
    packages: set[str] = set()
    for path in _walk_target(target):
        if os.path.islink(path):
            dest = os.readlink(path)
            dest = re.sub(r"^(?:\.\./)+stow/", "", dest)
            dest = re.sub(r"/.*", "", dest)
            packages.add(dest)

    return sorted(packages - {"", ".."})


def _walk_target(target: str) -> Iterator[str]:
    """Walk target directory, yielding file and symlink paths."""
    for dirpath, dirnames, filenames in os.walk(target):
        if os.path.exists(os.path.join(dirpath, ".stow")) or os.path.exists(
            os.path.join(dirpath, ".notstowed")
        ):
            print(f"skipping {dirpath}", file=sys.stderr)
            dirnames.clear()
            continue

        for filename in filenames:
            yield os.path.join(dirpath, filename)

        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.islink(path):
                yield path


if __name__ == "__main__":
    main()
