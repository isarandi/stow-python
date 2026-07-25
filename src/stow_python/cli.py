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
Command-line interface for stow-python.

This module contains the CLI functions including argument parsing,
configuration file handling, and the main entry point.
"""

from __future__ import annotations
import itertools
import os
import pwd
import re
import signal
import sys
import traceback
from dataclasses import dataclass, field
from typing import NoReturn
from collections.abc import Sequence

from stow_python.perlcompat import (
    OptionError,
    find_long_option,
    parse_optint_value,
    perl_shellwords,
    take_bundled_optint,
)
from stow_python.stow import _Stower, _compile_option_pattern
from stow_python.types import StowError, StowInternalError, StowCLIError, StowConfig
from stow_python.util import VERSION, PROGRAM_NAME, parent


# Perl derives its program name from $0 (bin/stow:469-470), so a renamed
# copy or a symlink identifies itself under that name in the usage banner,
# the SYNOPSIS line and --version. The "stow: ERROR:" prefix is NOT
# derived - Perl hardcodes it in Stow::Util (lib/Stow/Util.pm:45) - which
# is why library code keeps using PROGRAM_NAME.
_program_name = PROGRAM_NAME

# Option table mirroring Perl stow's GetOptions() specification. Long
# options resolve by exact name (or alias) first, then by unique prefix
# like Getopt::Long's auto_abbrev, which POSIXLY_CORRECT disables.
# Value types: "flag" (no value), "optint" (optional attached integer,
# like 'verbose|v:i'), "string" (mandatory value, like 'dir|d=s').
_OPTION_SPECS: list[tuple[tuple[str, ...], str]] = [
    (("verbose", "v"), "optint"),
    (("help", "h"), "flag"),
    (("simulate", "n", "no"), "flag"),
    (("version", "V"), "flag"),
    (("compat", "p"), "flag"),
    (("dir", "d"), "string"),
    (("target", "t"), "string"),
    (("adopt",), "flag"),
    (("no-folding",), "flag"),
    (("dotfiles",), "flag"),
    (("ignore",), "string"),
    (("override",), "string"),
    (("defer",), "string"),
    (("D", "delete"), "flag"),
    (("S", "stow"), "flag"),
    (("R", "restow"), "flag"),
]


def main() -> None:
    """Main entry point for stow command."""
    global _program_name
    _program_name = os.path.basename(sys.argv[0])

    configure_standard_streams()
    try:
        _main()
    except StowInternalError as e:
        print(
            f"\n{PROGRAM_NAME}: INTERNAL ERROR: {e.message}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        print(
            "This _is_ a bug. Please submit a bug report so we can fix it! :-)",
            file=sys.stderr,
        )
        print(
            "See https://github.com/isarandi/stow-python for how to do this.",
            file=sys.stderr,
        )
        sys.exit(e.errno)
    except StowCLIError as e:
        print(e.message, file=sys.stderr)
        sys.exit(e.errno)
    except StowError as e:
        print(f"{PROGRAM_NAME}: ERROR: {e.message}", file=sys.stderr)
        sys.exit(e.errno)


def configure_standard_streams() -> None:
    """Make the standard streams behave the way Perl stow's do.

    Perl writes undecoded bytes, so a file name that is not valid UTF-8
    reaches the terminal byte for byte; Python's defaults would render it
    as escape text on stderr and raise UnicodeEncodeError on stdout.
    surrogateescape round-trips exactly the bytes the filesystem gave us.

    Restoring the default SIGPIPE action likewise matches Perl: piping
    output into a program that exits early (`stow --help | head`) then
    ends the process on the signal instead of printing a BrokenPipeError
    traceback. Only the entry points do this - a library caller's process
    is none of our business.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="surrogateescape")
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def _main() -> None:
    """Main implementation (can raise StowError)."""
    options, pkgs_to_unstow, pkgs_to_stow = process_options()

    # Build StowConfig from parsed options
    config = StowConfig(
        dir=options.get("dir", "."),
        target=options.get("target") or "",
        dotfiles=options.get("dotfiles", False),
        adopt=options.get("adopt", False),
        no_folding=options.get("no-folding", False),
        simulate=options.get("simulate", False),
        verbose=options.get("verbose", 0),
        compat=options.get("compat", False),
        ignore=tuple(options.get("ignore", [])),
        defer=tuple(options.get("defer", [])),
        override=tuple(options.get("override", [])),
    )

    stower = _Stower(config)
    stower.plan_unstow(pkgs_to_unstow)
    stower.plan_stow(pkgs_to_stow)

    if stower.conflicts:
        for package in sorted(stower.conflicts.keys()):
            print(
                f"WARNING! stowing {package} would cause conflicts:",
                file=sys.stderr,
            )
            for message in sorted(stower.conflicts[package]):
                print(f"  * {message}", file=sys.stderr)
        print("All operations aborted.", file=sys.stderr)
        sys.exit(1)
    else:
        if config.simulate:
            print(
                "WARNING: in simulation mode so not modifying filesystem.",
                file=sys.stderr,
            )
            return

        stower.process_tasks()


def process_options() -> tuple[dict, list[str], list[str]]:
    """Parse and process command line and .stowrc file options.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    cli_options, pkgs_to_unstow, pkgs_to_stow = parse_cli_options(sys.argv[1:])
    rc_options, _, _ = get_config_file_options()

    # Merge .stowrc and command line options
    options = dict(rc_options)
    for option, cli_value in cli_options.items():
        rc_value = rc_options.get(option)

        if isinstance(cli_value, list) and rc_value is not None:
            options[option] = list(rc_value) + list(cli_value)
        else:
            options[option] = cli_value

    sanitize_path_options(options)

    # Perl strips trailing slashes from package names (s{/+$}{} on the
    # aliased loop variable), so "stow pkg/" behaves exactly like "stow pkg"
    pkgs_to_unstow = [_strip_trailing_slashes(p) for p in pkgs_to_unstow]
    pkgs_to_stow = [_strip_trailing_slashes(p) for p in pkgs_to_stow]
    check_packages(pkgs_to_stow, pkgs_to_unstow)

    return (options, pkgs_to_unstow, pkgs_to_stow)


def parse_cli_options(args: Sequence[str]) -> tuple[dict, list[str], list[str]]:
    """Parse command line options.

    One left-to-right pass over the arguments, each of which is a "--"
    terminator, a long option, the deprecated +n, a package name, or a
    bundle of short options. Every arm hands the scan state to a helper
    that may consume further arguments by advancing the state's index.

    Perl scans the WHOLE argument list first and only then acts on what
    it found: `GetOptions(...) or usage('')`, then --help, then --version
    (bin/stow:614-624). So a bad option anywhere on the line beats an
    earlier --help, and --help beats --version.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    # POSIXLY_CORRECT disables the + option prefix and long-option
    # abbreviation in Perl's Getopt::Long. It would also enable
    # require_order, but Perl stow's explicit 'permute' config overrides
    # that, so packages and options may be interleaved either way.
    posixly_correct = "POSIXLY_CORRECT" in os.environ

    state = _ScanState(args=args)
    while state.i < len(args):
        arg = args[state.i]

        if arg == "--":
            _take_rest_as_packages(state)
            break

        elif arg.startswith("--"):
            _scan_long_option(state, arg, allow_abbrev=not posixly_correct)

        # Support +n for simulate (backwards compat with Perl's Getopt::Long)
        # POSIXLY_CORRECT disables + prefix support
        elif arg == "+n" and not posixly_correct:
            print("Warning: +n is deprecated, use -n instead", file=sys.stderr)
            state.options["simulate"] = True

        # Package argument (including "-" which is a valid package name)
        # Also matches +n when POSIXLY_CORRECT (+ not recognized as option prefix)
        elif not arg.startswith("-") or arg == "-":
            _add_package(state, arg)

        else:
            _scan_bundled_options(state, arg)

        state.i += 1

    if state.had_option_error:
        show_usage_and_exit(exit_code=1)
    if state.want_help:
        show_usage_and_exit()
    if state.want_version:
        show_version_and_exit()

    return (state.options, state.pkgs_to_unstow, state.pkgs_to_stow)


@dataclass
class _ScanState:
    """Everything one scan over an argument list builds up and looks at.

    `i` is the position of the argument being scanned; a helper that
    consumes the following argument as an option value advances `i`
    itself, and the scan loop then steps past the last one consumed.

    A bad option is diagnosed on stderr where it is met and recorded in
    `had_option_error`, so that the scan reaches every later argument
    before the usage exit, exactly as Getopt::Long does.
    """

    args: Sequence[str]
    i: int = 0
    action: str = "stow"
    options: dict = field(default_factory=dict)
    pkgs_to_unstow: list[str] = field(default_factory=list)
    pkgs_to_stow: list[str] = field(default_factory=list)
    had_option_error: bool = False
    want_help: bool = False
    want_version: bool = False


def _take_rest_as_packages(state: _ScanState) -> None:
    """Take every argument after a "--" terminator as a package name.

    POSIX says the terminator ends option processing, so a package may be
    named there even if it starts with "-". (Perl stow silently DISCARDS
    the arguments after "--" because Getopt::Long leaves them in @ARGV
    unread; that is clearly unintended, so we diverge deliberately - see
    docs/perl-differences.md.)
    """
    for pkg in state.args[state.i + 1 :]:
        _add_package(state, pkg)


def _add_package(state: _ScanState, pkg: str) -> None:
    """Queue a package for the action the preceding -S/-D/-R selected."""
    if state.action == "restow":
        state.pkgs_to_unstow.append(pkg)
        state.pkgs_to_stow.append(pkg)
    elif state.action == "unstow":
        state.pkgs_to_unstow.append(pkg)
    else:
        state.pkgs_to_stow.append(pkg)


def _scan_long_option(state: _ScanState, arg: str, allow_abbrev: bool) -> None:
    """Resolve one --option argument and apply it."""
    name = arg[2:]
    attached: str | None = None
    # Getopt::Long only splits at "=" when at least one name
    # character precedes it ("--=x" is the unknown option "=x")
    if "=" in name and not name.startswith("="):
        name, attached = name.split("=", 1)
    try:
        resolved = find_long_option(name, _OPTION_SPECS, allow_abbrev)
        if resolved is None:
            raise OptionError(f"Unknown option: {name}")
        given_name, primary, vtype = resolved
        _apply_long_option(state, given_name, primary, vtype, attached)
    except OptionError as e:
        print(e, file=sys.stderr)
        state.had_option_error = True


def _apply_long_option(
    state: _ScanState,
    given_name: str,
    primary: str,
    vtype: str,
    attached: str | None,
) -> None:
    """Apply one resolved long option according to the value it takes."""
    if vtype == "string":
        _apply_string_option(state, given_name, primary, attached)
    elif vtype == "optint":
        _apply_optint_option(state, attached)
    else:
        _apply_flag_option(state, given_name, primary, attached)


def _apply_string_option(
    state: _ScanState, given_name: str, primary: str, attached: str | None
) -> None:
    """Apply a long option that requires a value, consuming the following
    argument as that value where Getopt::Long would.

    An empty attached value ("--ignore=") is rejected like Getopt::Long
    rejects it: an empty regex or path is never what the user meant, and
    an empty --ignore pattern would silently match every file. An empty
    SEPARATE argument (--dir "") is accepted, also like Getopt::Long.
    """
    if attached:
        value = attached
    elif attached is None and state.i + 1 < len(state.args):
        state.i += 1
        value = state.args[state.i]
    else:
        raise OptionError(f"Option {given_name} requires an argument")

    if primary in ("ignore", "defer", "override"):
        _validate_option_regex(value, primary)
        state.options.setdefault(primary, []).append(value)
    else:  # dir, target
        state.options[primary] = value


def _apply_optint_option(state: _ScanState, attached: str | None) -> None:
    """Apply --verbose, which takes an optional ATTACHED value only;
    unlike Perl it never consumes the next command-line argument (see
    docs/perl-differences.md)."""
    if not attached:
        state.options["verbose"] = state.options.get("verbose", 0) + 1
        return

    level = parse_optint_value(attached)
    if level is None:
        # Abort like Perl instead of silently proceeding with a default
        # level and modifying the filesystem
        raise OptionError(
            f'Value "{attached}" invalid for option verbose (number expected)'
        )
    state.options["verbose"] = level


def _apply_flag_option(
    state: _ScanState, given_name: str, primary: str, attached: str | None
) -> None:
    """Apply a long option that takes no value."""
    if attached is not None:
        raise OptionError(f"Option {given_name} does not take an argument")

    if primary == "simulate":
        state.options["simulate"] = True
    elif primary == "compat":
        state.options["compat"] = True
    elif primary in ("adopt", "no-folding", "dotfiles"):
        state.options[primary] = True
    elif primary == "D":
        state.action = "unstow"
    elif primary == "S":
        state.action = "stow"
    elif primary == "R":
        state.action = "restow"
    elif primary == "help":
        state.want_help = True
    else:  # version
        state.want_version = True


def _validate_option_regex(pattern: str, option: str) -> None:
    """Reject a malformed --ignore/--defer/--override pattern up front.

    Anchoring and compilation happen in the core (_compile_option_pattern);
    validating here turns a malformed pattern into a clean usage error, not
    a traceback. Note that Perl-only regex syntax (e.g. \\Q...\\E) is not
    supported and also ends up here.
    """
    try:
        _compile_option_pattern(pattern, option)
    except StowError as e:
        show_usage_and_exit(e.message)


def _scan_bundled_options(state: _ScanState, arg: str) -> None:
    """Apply a bundle of short options: -xyz is parsed as -x -y -z.

    A value-taking option (d, t) at the end of a bundle consumes the next
    command-line argument, so `-nt DIR` works like `-n -t DIR`.
    """
    chars = arg[1:]
    pos = 0

    while pos < len(chars):
        char = chars[pos]
        rest = chars[pos + 1 :]

        if char == "n":
            state.options["simulate"] = True
        elif char == "p":
            state.options["compat"] = True
        elif char == "v":
            pos += _apply_bundled_verbose(state, rest)
        elif char == "S":
            state.action = "stow"
        elif char == "D":
            state.action = "unstow"
        elif char == "R":
            state.action = "restow"
        elif char == "h":
            state.want_help = True
        elif char == "V":
            state.want_version = True
        elif char in ("d", "t") and rest:
            state.options["dir" if char == "d" else "target"] = rest
            pos += len(rest)
        elif char in ("d", "t"):
            _take_next_arg_as_path(state, char)
        else:
            # Like Perl, report every unknown letter and keep processing
            # the rest of the bundle before the fatal usage exit
            print(f"Unknown option: {char}", file=sys.stderr)
            state.had_option_error = True
        pos += 1


def _apply_bundled_verbose(state: _ScanState, rest: str) -> int:
    """Apply a -v inside a bundle, with the value attached to it if any.

    Returns how many characters of the bundle that value took up, which
    is zero when the bundle just continues with more option letters.
    """
    taken = take_bundled_optint(rest)
    if taken is None:
        state.options["verbose"] = state.options.get("verbose", 0) + 1
        return 0
    state.options["verbose"], consumed = taken
    return consumed


def _take_next_arg_as_path(state: _ScanState, char: str) -> None:
    """Take the argument following the bundle as the value of a -d/-t
    ending it, like tar -xf FILE or ssh -p PORT."""
    if state.i + 1 < len(state.args):
        state.i += 1
        state.options["dir" if char == "d" else "target"] = state.args[state.i]
    else:
        print(f"Option {char} requires an argument", file=sys.stderr)
        state.had_option_error = True


def _strip_trailing_slashes(package: str) -> str:
    """Perl's s{/+$}{} on a package name.

    Perl's "$" - and Python's - also matches just before a final newline,
    so a package directory literally named "a\\n" is still recognized when
    shell completion writes it as "a/\\n".
    """
    return re.sub(r"/+$", "", package)


def sanitize_path_options(options: dict) -> None:
    """Validate and set defaults for dir and target options."""
    if "dir" not in options:
        stow_dir_env = os.environ.get("STOW_DIR")
        options["dir"] = stow_dir_env if stow_dir_env else os.getcwd()

    if not os.path.isdir(options["dir"]):
        show_usage_and_exit(
            f"{_program_name}: --dir value '{options['dir']}' is not a valid directory\n"
        )

    if "target" in options:
        if not os.path.isdir(options["target"]):
            show_usage_and_exit(
                f"{_program_name}: --target value '{options['target']}' is not a valid directory\n"
            )
    else:
        target = parent(options["dir"])
        options["target"] = target if target else "."


def check_packages(pkgs_to_stow: Sequence[str], pkgs_to_unstow: Sequence[str]) -> None:
    """Validate package names."""
    if not pkgs_to_stow and not pkgs_to_unstow:
        show_usage_and_exit(f"{_program_name}: No packages to stow or unstow\n")

    for package in itertools.chain(pkgs_to_stow, pkgs_to_unstow):
        if "/" in package:
            raise StowError("Slashes are not permitted in package names")


def get_config_file_options() -> tuple[dict, list[str], list[str]]:
    """Search for default settings in any .stowrc files.

    Returns: (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)
    """
    defaults: list[str] = []
    stowrc_candidate_paths = [".stowrc"]

    home = os.environ.get("HOME")
    if home is not None:
        # Perl tests defined($ENV{HOME}) and interpolates, so HOME="" makes
        # it probe "/.stowrc" rather than skipping the home candidate
        stowrc_candidate_paths.insert(0, f"{home}/.stowrc")

    for file_path in stowrc_candidate_paths:
        try:
            # Byte-transparent, "\n"-delimited records, exactly as Perl
            # reads the file: a non-UTF-8 byte must not abort the run, and
            # a bare CR inside a quoted value must not split the line
            with open(file_path, errors="surrogateescape", newline="\n") as f:
                for line in f:
                    # Parse like Perl's shellwords so .stowrc files
                    # written for GNU Stow behave identically; chomp
                    # removes the one newline and nothing else
                    defaults.extend(perl_shellwords(line.removesuffix("\n")))
        except IsADirectoryError as e:
            raise StowCLIError(f"Could not open {file_path} for reading") from e
        except OSError:
            # Missing or unreadable (EACCES, ELOOP, EIO, ...): skip the
            # file silently, like Perl's -r probe failing
            continue

    rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow = parse_cli_options(defaults)

    if "target" in rc_options:
        rc_options["target"] = expand_filepath(rc_options["target"], "--target option")
    if "dir" in rc_options:
        rc_options["dir"] = expand_filepath(rc_options["dir"], "--dir option")

    return (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)


def expand_filepath(path: str, source: str) -> str:
    """Expand environment variables and tilde in file paths."""
    path = expand_environment_variables(path, source)
    path = expand_tilde_to_homedir(path)
    return path


def expand_environment_variables(path: str, source: str) -> str:
    """Expand environment variables in path.

    Replace non-escaped $VAR and ${VAR} with os.environ[VAR].
    """

    def replace_var(match):
        var = match.group(1)
        try:
            return os.environ[var]
        except KeyError as e:
            raise StowCLIError(
                f"{source} references undefined environment variable ${var}; aborting!"
            ) from e

    # Braced form: Perl stow only expands ${NAME} when the braces contain
    # word/space characters ([\w\s]+), so shell-isms like ${VAR:-default}
    # stay literal instead of being looked up (and failing) as a variable
    # named "VAR:-default". re.ASCII keeps \w and \s to the characters
    # Perl's match over undecoded bytes sees, so "$BASE" followed by a
    # non-ASCII letter still ends the variable name at BASE.
    path = re.sub(r"(?<!\\)\$\{([\w\s]+)}", replace_var, path, flags=re.ASCII)
    path = re.sub(r"(?<!\\)\$(\w+)", replace_var, path, flags=re.ASCII)
    path = path.replace("\\$", "$")

    return path


def expand_tilde_to_homedir(path: str) -> str:
    """Expand tilde to user's home directory path.

    Like Perl stow's expand_tilde, in the same order: a bare leading ~ or
    ~username is expanded first, then every escaped tilde (\\~) anywhere
    in the path is unescaped. A leading \\~ therefore stays a literal ~
    (the expansion step matches only a bare leading ~), and later \\~
    sequences do not suppress expansion of the leading ~. An unknown
    ~username leaves the path unchanged rather than mangling it (see
    docs/perl-differences.md #21).
    """
    if path.startswith("~"):
        # Split ~username/rest into parts
        tilde_part, slash, rest = path.partition("/")
        username = tilde_part.removeprefix("~")

        if username:
            home = get_homedir_from_passwd(username=username)
        else:
            home = (
                os.environ.get("HOME")
                or os.environ.get("LOGDIR")
                or get_homedir_from_passwd()
            )

        if home:
            path = home + slash + rest

    return path.replace("\\~", "~")


def get_homedir_from_passwd(
    username: str | None = None, uid: int | None = None
) -> str | None:
    try:
        if username is not None:
            return pwd.getpwnam(username).pw_dir
        if uid is not None:
            return pwd.getpwuid(uid).pw_dir
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None


def show_usage_and_exit(
    msg: str | None = None, exit_code: int | None = None
) -> NoReturn:
    """Print program usage message and exit."""
    if msg:
        print(msg, file=sys.stderr)

    print(f"""{_program_name} (GNU Stow) version {VERSION}

Stow-Python is a Python reimplementation of GNU Stow.
Original GNU Stow by Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others.

SYNOPSIS:

    {_program_name} [OPTION ...] [-D|-S|-R] PACKAGE ... [-D|-S|-R] PACKAGE ...

OPTIONS:

    -d DIR, --dir=DIR     Set stow dir to DIR (default is current dir)
    -t DIR, --target=DIR  Set target to DIR (default is parent of stow dir)

    -S, --stow            Stow the package names that follow this option
    -D, --delete          Unstow the package names that follow this option
    -R, --restow          Restow (like stow -D followed by stow -S)

    --ignore=REGEX        Ignore files ending in this Perl regex
    --defer=REGEX         Don't stow files beginning with this Perl regex
                          if the file is already stowed to another package
    --override=REGEX      Force stowing files beginning with this Perl regex
                          if the file is already stowed to another package
    --adopt               (Use with care!)  Import existing files into stow package
                          from target.  Please read docs before using.
    --dotfiles            Enables special handling for dotfiles that are
                          Stow packages that start with "dot-" and not "."
    -p, --compat          Use legacy algorithm for unstowing

    -n, --no, --simulate  Do not actually make any filesystem changes
    -v, --verbose[=N]     Increase verbosity (levels are from 0 to 5;
                            -v or --verbose adds 1; --verbose=N sets level)
    -V, --version         Show stow version number
    -h, --help            Show this help

GNU Stow home page: <http://www.gnu.org/software/stow/>
Report deviations from GNU Stow: <https://github.com/isarandi/stow-python/issues>""")

    if exit_code is not None:
        sys.exit(exit_code)
    elif msg:
        sys.exit(1)
    else:
        sys.exit(0)


def show_version_and_exit() -> NoReturn:
    """Print version and exit."""
    # Byte-identical to Perl stow's --version output so that scripts
    # matching on "GNU Stow" keep working
    print(f"{_program_name} (GNU Stow) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
