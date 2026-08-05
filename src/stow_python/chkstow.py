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


# Perl: $ENV{STOW_DIR} || '/usr/local/' — Perl truthiness makes both the
# empty string and "0" fall back to the default, not just an unset variable.
_stow_dir_env = os.environ.get("STOW_DIR")
DEFAULT_TARGET = "/usr/local/" if _stow_dir_env in (None, "", "0") else _stow_dir_env

# Perl: $File::Find::current_dir, i.e. File::Spec->curdir
_CURRENT_DIR = "."


def main() -> None:
    """Main entry point."""
    _make_streams_byte_transparent()

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


def _make_streams_byte_transparent() -> None:
    """Let filenames reach the streams as the raw bytes Perl prints.

    Filenames are decoded with surrogateescape, so encoding the output
    with the same error handler puts the original bytes back on the wire
    whatever the locale says.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="surrogateescape")


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
    target = DEFAULT_TARGET
    mode = Mode.BAD_LINKS
    posixly_correct = "POSIXLY_CORRECT" in os.environ
    ok = True

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            break
        if arg.startswith("--"):
            starter, name = "--", arg[2:]
            long_prefix = True
        elif arg.startswith("-") and arg != "-":
            starter, name = "-", arg[1:]
            long_prefix = False
        elif arg.startswith("+") and not posixly_correct:
            starter, name = "+", arg[1:]
            long_prefix = False
        else:
            if posixly_correct:
                break
            i += 1
            continue

        # An "=" separates the value only under a long prefix, or under a
        # short one while getopt_compat is on, which POSIXLY_CORRECT turns
        # off — "-t=x" is then the unknown option "t=x". At least one name
        # character has to precede it, so "--=x" is the option "=x".
        attached: str | None = None
        equals = name.find("=", 1)
        if (long_prefix or not posixly_correct) and equals > 0:
            name, attached = name[:equals], name[equals + 1 :]

        given, spec = _find_option(name, allow_abbrev=not posixly_correct)
        if spec is None:
            # A prefix with nothing behind it is not an unknown option but
            # a missing one; only "+" gets that far, since "-" alone is a
            # non-option argument and "--" ends the options
            if given:
                print(f"Unknown option: {given}", file=sys.stderr)
            else:
                print(f"Missing option after {starter}", file=sys.stderr)
            ok = False
        else:
            _, spec_mode = spec
            if spec_mode is not None:
                if attached is not None:
                    print(f"Option {given} does not take an argument", file=sys.stderr)
                    ok = False
                else:
                    mode = spec_mode
            elif attached:
                target = attached
            elif attached is None and i + 1 < len(args):
                i += 1
                target = args[i]
            else:
                # An empty attached value counts as no argument at all
                print(f"Option {given} requires an argument", file=sys.stderr)
                ok = False
        i += 1

    if not ok:
        usage()

    return target, mode


def _find_option(
    name: str, allow_abbrev: bool
) -> tuple[str, tuple[tuple[str, ...], Mode | None] | None]:
    """Resolve an option name like Getopt::Long's default find_option.

    An exact match on a name or alias wins, else a unique prefix resolves,
    both case-insensitively. Returns (name_for_messages, spec), with the
    spec None when the option is unknown. Getopt::Long names a known option
    by the lowercased, prefix-expanded name it resolved to, and an unknown
    one by the name as it stood when the lookup gave up — which
    auto_abbrev has already lowercased and POSIXLY_CORRECT has not. (No
    prefix is ambiguous between two of chkstow's specs, so there is no
    ambiguity error path.)
    """
    given = name.lower() if allow_abbrev else name
    folded = name.lower()
    for spec in _OPTION_SPECS:
        if folded in spec[0]:
            return folded, spec
    if not allow_abbrev or not folded:
        return given, None
    hits = [
        (n, spec)
        for spec in _OPTION_SPECS
        for n in spec[0]
        if n.startswith(folded)
    ]
    if len(hits) != 1:
        return given, None
    expanded, spec = hits[0]
    return expanded, spec


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

    # Perl sorts the package names as byte strings
    return sorted(packages - {"", ".."}, key=os.fsencode)


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
    wanted(entry, full_path) is called with cwd set to entry's directory,
    so the walk happens inside the target tree, not inside the cwd stow
    was started from. The paths handed to wanted() keep the target
    spelling as given on the command line.
    """
    # File::Find saves cwd at start and returns to it at end
    start_cwd = os.getcwd()
    try:
        st = os.lstat(target)
    except OSError as e:
        # File::Find warns and checks nothing. Perl's warn appends its
        # " at <script> line N." source location, which the test harness
        # normalizes away like the other Perl warning locations.
        print(f"Can't stat {target}: {e.strerror}", file=sys.stderr)
        os.chdir(start_cwd)
        return

    # File::Find strips ONE trailing slash from the top-level argument
    # unless the argument is the root directory, so "-t dir/" reports
    # "dir/x" while "-t dir//" reports "dir//x".
    if target.endswith("/") and not _is_root(target):
        target = target[:-1]

    # File::Find does NOT descend a top-level argument that is not a
    # directory (note: a symlink to a directory is still a symlink here).
    # It chdirs to the argument's parent, lstats the basename again, calls
    # wanted() on it once, and chdirs back. $File::Find::name is "./x" for
    # a bare relative name, the argument as given otherwise. So e.g.
    # "chkstow -a -t <symlink>" silently checks nothing inside the link.
    if not stat.S_ISDIR(st.st_mode):
        dirname, basename = os.path.split(target)
        if dirname:
            full_name = target
            os.chdir(dirname + "/")
        else:
            full_name = "./" + target
            os.chdir("./")
        st = os.lstat(basename)
        result = wanted(basename, full_name, stat.S_ISLNK(st.st_mode))
        if result is not None:
            yield result
        os.chdir(start_cwd)
        return

    # File::Find's _find_dir chdirs into the top directory before reading
    # it; "." is already the cwd, so it is left alone. A failed chdir
    # warns without the parenthesised parent that deeper failures carry,
    # and checks nothing.
    if target != _CURRENT_DIR:
        try:
            os.chdir(target)
        except OSError as e:
            print(f"Can't cd to {target}: {e.strerror}", file=sys.stderr)
            os.chdir(start_cwd)
            return

    for result, _result_depth in _file_find_chdir(target, wanted, depth=1):
        if result is not None:
            yield result

    # Final chdir back to saved cwd (Perl uses absolute path from getcwd)
    os.chdir(start_cwd)


def _file_find_chdir(dir_name: str, wanted, depth: int = 1) -> Iterator[tuple[str, int]]:
    """Recursive File::Find-like walker using chdir and relative paths.

    The cwd is the directory being read; dir_name is that directory's path
    as File::Find spells it ($File::Find::dir), which is what the entries'
    names are built from.

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
    # File::Find calls wanted on the root directory only (depth 1); deeper
    # directories get their call from the loop below, before descending.
    if depth == 1:
        st = os.lstat(_CURRENT_DIR)
        wanted(_CURRENT_DIR, dir_name, stat.S_ISLNK(st.st_mode))

    # Entry names hang off the directory path, which only ends in a slash
    # of its own when it is the root directory.
    dir_pref = dir_name if _is_root(dir_name) else dir_name + "/"

    # Open and read current directory entries (Perl uses ".")
    try:
        entries = os.listdir(".")
    except OSError as e:
        print(f"Can't opendir({dir_name}): {e.strerror}", file=sys.stderr)
        return

    # preprocess: stat .stow and .notstowed (Perl's -e test)
    if _path_exists(".stow") or _path_exists(".notstowed"):
        # Perl outputs $File::Find::dir which is the full path from start
        print(f"skipping {dir_name}", file=sys.stderr)
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
        full_path = dir_pref + entry

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
        try:
            os.chdir(subdir)
        except OSError as e:
            # File::Find names the parent in parentheses here, printing it
            # empty when the parent is the root directory.
            parent_in_msg = "" if _is_root(dir_name) else dir_name
            print(
                f"Can't cd to ({parent_in_msg}/) {subdir}: {e.strerror}",
                file=sys.stderr,
            )
            continue
        current_depth += 1

        for result, result_depth in _file_find_chdir(subdir_full_path, wanted, current_depth):
            yield result, result_depth
            current_depth = result_depth

    # After all subdirs, return current depth for parent to handle chdir
    if current_depth > depth:
        # We're still deep from last recursion, parent will handle chdir
        pass
    # Yield a sentinel to communicate final depth (None result)
    yield None, current_depth


def _is_root(path: str) -> bool:
    """Perl File::Find's _is_root: the Unix root directory, nothing else."""
    return path == "/"


def _path_exists(path: str) -> bool:
    """Check if path exists using stat (like Perl's -e)."""
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
