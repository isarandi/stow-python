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

"""chkstow - Check stow target directory for problems."""

from __future__ import annotations

import os
import re
import signal
import stat
import sys
from collections.abc import Iterator
from enum import Enum, auto


class Mode(Enum):
    BAD_LINKS = auto()
    ALIENS = auto()
    LIST = auto()


def default_target() -> str:
    """Default target directory: $STOW_DIR, else /usr/local/.

    "or" (not a default argument) so an empty STOW_DIR also falls back.
    Deliberately NOT like Perl chkstow's `$ENV{STOW_DIR} ||` fallback,
    which also treats the string "0" as false: here STOW_DIR=0 names a
    real directory, consistent with Perl stow's own `length` check.
    See docs/perl-differences.md. A function (not a module constant) so
    the environment is read when parsing starts, not at import time.
    """
    return os.environ.get("STOW_DIR") or "/usr/local/"


# Option table mirroring Perl chkstow's GetOptions() spec
# ('b|badlinks', 'a|aliens', 'l|list', 't|target=s') under Getopt::Long's
# DEFAULT configuration, which differs from the one stow's parser
# emulates: long names match case-insensitively, "+" works as an option
# prefix (getopt_compat), and there is no short-option bundling. A None
# mode marks the value-taking target option.
_OPTION_SPECS: tuple[tuple[tuple[str, ...], Mode | None], ...] = (
    (("b", "badlinks"), Mode.BAD_LINKS),
    (("a", "aliens"), Mode.ALIENS),
    (("l", "list"), Mode.LIST),
    (("t", "target"), None),
)


def main() -> None:
    """Main entry point."""
    configure_standard_streams()

    if len(sys.argv) == 1:
        usage()

    target, mode = parse_args(sys.argv[1:])

    if mode == Mode.BAD_LINKS:
        for path in find_bad_links(target):
            print(f"Bogus link: {path}")
    elif mode == Mode.ALIENS:
        for path in find_aliens(target):
            print(f"Unstowed file: {path}")
    elif mode == Mode.LIST:
        for pkg in list_packages(target):
            print(pkg)


def configure_standard_streams() -> None:
    """Make the standard streams behave the way Perl chkstow's do.

    A report about a tree is worthless if it stops at the first name that
    is not valid UTF-8: Perl writes undecoded bytes and lists the whole
    tree, so surrogateescape reproduces those bytes exactly instead of
    raising UnicodeEncodeError mid-report. Restoring the default SIGPIPE
    action matches Perl for `chkstow -a | head`.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="surrogateescape")
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def parse_args(args: list[str]) -> tuple[str, Mode]:
    """Parse arguments like Perl chkstow's GetOptions() call.

    Returns (target, mode). A bad option warns on stderr exactly like
    Getopt::Long, and after the remaining arguments have been checked ends
    in usage(), mirroring Perl's `GetOptions(...) or usage()`. Non-option
    arguments are skipped: Perl chkstow leaves them in @ARGV and never
    reads them. POSIXLY_CORRECT disables abbreviation and "+" prefixes
    and stops option processing at the first non-option argument
    (require_order).
    """
    target = default_target()
    mode = Mode.BAD_LINKS
    posixly_correct = "POSIXLY_CORRECT" in os.environ
    ok = True

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            break
        long_form = arg.startswith("--")
        if long_form:
            name = arg[2:]
        elif len(arg) > 1 and arg.startswith("-"):
            name = arg[1:]
        elif arg.startswith("+") and not posixly_correct:
            # getopt_compat accepts "+" as an option prefix, so a bare "+"
            # is an option whose name is missing
            if len(arg) == 1:
                print("Missing option after +", file=sys.stderr)
                ok = False
                i += 1
                continue
            name = arg[1:]
        else:
            if posixly_correct:
                break
            i += 1
            continue

        attached: str | None = None
        # Without getopt_compat (i.e. under POSIXLY_CORRECT) Getopt::Long
        # splits an attached value off after "--" only, so "-t=DIR" is the
        # unknown option "t=DIR" rather than --target=DIR
        if (
            (long_form or not posixly_correct)
            and "=" in name
            and not name.startswith("=")
        ):
            name, attached = name.split("=", 1)

        spec = _find_option(name, allow_abbrev=not posixly_correct)
        if spec is None:
            print(f"Unknown option: {name.lower()}", file=sys.stderr)
            ok = False
        else:
            canonical, spec_mode = spec
            if spec_mode is not None:
                if attached is not None:
                    print(
                        f"Option {canonical} does not take an argument", file=sys.stderr
                    )
                    ok = False
                else:
                    mode = spec_mode
            elif attached:
                target = attached
            elif attached is None and i + 1 < len(args):
                i += 1
                target = args[i]
            else:
                # An attached but empty value ("--target=") is no value at
                # all to Getopt::Long, exactly like a missing one
                print(f"Option {canonical} requires an argument", file=sys.stderr)
                ok = False
        i += 1

    if not ok:
        usage()

    return target, mode


def _find_option(name: str, allow_abbrev: bool) -> tuple[str, Mode | None] | None:
    """Resolve an option name like Getopt::Long's default find_option: an
    exact match on a name or alias wins, else a unique prefix resolves,
    both case-insensitively. Returns (canonical name, mode), or None if
    the option is unknown. (No prefix is ambiguous between two of
    chkstow's specs, so unlike stow's parser there is no ambiguity error
    path.) The canonical name is what Getopt::Long's diagnostics quote:
    the lower-cased spelling of an exact name or alias, and the expanded
    name of an abbreviation ("--badl=1" complains about "badlinks").
    """
    folded = name.lower()
    for names, mode in _OPTION_SPECS:
        if folded in names:
            return folded, mode
    if not allow_abbrev or not folded:
        return None
    hits = [
        (next(n for n in names if n.startswith(folded)), mode)
        for names, mode in _OPTION_SPECS
        if any(n.startswith(folded) for n in names)
    ]
    return hits[0] if len(hits) == 1 else None


def usage() -> None:
    """Print usage message and exit."""
    print(f"""\
USAGE: chkstow [options]

Options:
    -t DIR, --target=DIR  Set the target directory to DIR
                          (default is {default_target()})
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

    # Byte order, like Perl's sort: a package name that is not valid UTF-8
    # would otherwise be listed at a different position
    return sorted(packages - {"", ".."}, key=os.fsencode)


def _walk_target(target: str) -> Iterator[str]:
    """Walk target directory, yielding file and symlink paths.

    Follows Perl File::Find's edge behaviors: one trailing slash is
    stripped off the top-level argument, an unstattable target warns
    "Can't stat ..." on stderr and checks nothing, a target that is not a
    directory is checked once itself, named "./x" when given as a bare
    relative name, and a directory that cannot be entered or read is
    reported and skipped rather than silently passed over. One deliberate
    divergence: a symlink to a directory is followed and its contents
    checked, where Perl checks only the symlink itself once — see
    docs/perl-differences.md.
    """
    if target != "/":
        target = target.removesuffix("/")

    try:
        st: os.stat_result | None = os.lstat(target)
    except OSError as e:
        print(f"Can't stat {target}: {e.strerror}", file=sys.stderr)
        return

    if st is not None and stat.S_ISLNK(st.st_mode):
        try:
            st = os.stat(target)
        except OSError:
            st = None  # Dangling symlink: check it as a single entry

    if st is None or not stat.S_ISDIR(st.st_mode):
        yield target if "/" in target else "./" + target
        return

    # File::Find skips the chdir for a top item of "." and goes straight
    # to the opendir, so the failure it reports there is a different one
    if target != os.curdir:
        error = _cannot_enter(target)
        if error is not None:
            print(f"Can't cd to {target}: {error.strerror}", file=sys.stderr)
            return

    for dirpath, dirnames, filenames in os.walk(target, onerror=_report_opendir_error):
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

        # File::Find chdirs into every directory before listing it, so a
        # readable but unsearchable one (mode 444) is reported and its
        # contents are never seen; os.walk would happily enumerate it.
        for dirname in list(dirnames):
            path = os.path.join(dirpath, dirname)
            if os.path.islink(path):
                continue
            error = _cannot_enter(path)
            if error is not None:
                print(
                    f"Can't cd to ({dirpath}/) {dirname}: {error.strerror}",
                    file=sys.stderr,
                )
                dirnames.remove(dirname)


def _cannot_enter(path: str) -> OSError | None:
    """Return the error a chdir into path would fail with, else None.

    Statting "<path>/." needs exactly the search permission chdir needs,
    so this answers File::Find's question without moving the process out
    of the directory the walk's relative paths are resolved against.
    """
    try:
        os.stat(os.path.join(path, os.curdir))
    except OSError as e:
        return e
    return None


def _report_opendir_error(error: OSError) -> None:
    """os.walk error handler: a directory that could be entered but not
    listed, which is where File::Find's opendir fails."""
    print(f"Can't opendir({error.filename}): {error.strerror}", file=sys.stderr)


if __name__ == "__main__":
    main()
