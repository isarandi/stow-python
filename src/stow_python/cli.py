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
import sys
import traceback
from typing import NoReturn, Optional, Sequence

from stow_python.stow import _Stower, _compile_option_pattern
from stow_python.types import StowError, StowInternalError, StowCLIError, StowConfig
from stow_python.util import VERSION, PROGRAM_NAME, parent


# The alternation mirrors the parse_line() pattern in Text::ParseWords 3.31:
# a double-quoted segment, a single-quoted segment, or an unquoted segment
# followed by a delimiter (end of string, whitespace, or a quote starting the
# next segment). Perl uses atomic groups (?>...) purely as a stack guard;
# the match language is identical without them.
_PARSE_LINE_RE = re.compile(
    r'(")([^\\"]*(?:\\.[^\\"]*)*)"'
    r"|(')([^\\']*(?:\\.[^\\']*)*)'"
    r'|((?:\\.|[^\\"\'])*?)(\Z|\s+|(?!^)(?=["\']))',
    re.S,
)


def perl_shellwords(line: str) -> list[str]:
    """
    Parse a line using Perl's Text::ParseWords::shellwords() semantics,
    i.e. parse_line('\\s+', 0, $line) after stripping leading whitespace.

    Faithful port of Text::ParseWords 3.31. Behaviors that differ from
    Python's shlex.split():
    - In double quotes, backslash escapes ANY character: \\X -> X
    - In single quotes, backslash is copied literally, but \\X still spans
      two characters while scanning, so \\' does not close the quote
    - Empty quoted words ("" or '') are kept
    - A line that fails to parse (unmatched quote, trailing lone backslash)
      yields no words at all: parse_line returns an empty list, so the
      whole line is dropped
    - Words are delimited by any whitespace (\\s+), not just space/tab

    This matters for .stowrc files with regex patterns like:
        --ignore="\\.git"
    Perl parses this as: --ignore=.git  (backslash consumed)
    """
    line = re.sub(r"^\s+", "", line)
    pieces: list[Optional[str]] = []
    word: Optional[str] = None

    while line:
        m = _PARSE_LINE_RE.match(line)
        if m is None:
            # Unmatched quote or trailing backslash: parse_line returns ()
            return []
        dq, dq_text, sq, sq_text, unquoted, delim = m.groups()
        quote = dq if dq is not None else sq

        # Perl: return() unless defined($quote) || length($unquoted) || length($delim)
        if quote is None and not unquoted and not delim:
            return []

        if quote is not None:
            quoted = dq_text if dq is not None else sq_text
            # Backslash unescaping happens only inside double quotes
            if quote == '"':
                quoted = re.sub(r"\\(.)", r"\1", quoted, flags=re.S)
            segment = quoted
        else:
            segment = re.sub(r"\\(.)", r"\1", unquoted, flags=re.S)

        word = ("" if word is None else word) + segment
        line = line[m.end() :]

        # \Z and lookahead delimiters are zero-width: only real whitespace
        # ends the word here; end-of-string is handled just below.
        if delim:
            pieces.append(word)
            word = None
        if not line:
            pieces.append(word)

    # shellwords() pops a trailing undef left by a line ending in whitespace
    if pieces and pieces[-1] is None:
        pieces.pop()
    # A None can only ever be the trailing element popped above
    return [w for w in pieces if w is not None]


def main() -> None:
    """Main entry point for stow command."""
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


def _parse_bundled_options(
    args: Sequence[str], arg_index: int, options: dict, action: str
) -> tuple[str, int, bool, bool, bool]:
    """Parse bundled short options like -npvS at args[arg_index].

    A value-taking option (d, t) at the end of a bundle consumes the next
    command-line argument, so `-nt DIR` works like `-n -t DIR`.

    Returns (action, next_arg_index, has_any_unknown_options,
    should_show_help, should_show_version).
    """
    has_any_unknown_options = False
    should_show_help = False
    should_show_version = False
    chars = args[arg_index][1:]
    i = 0

    while i < len(chars):
        char = chars[i]
        rest = chars[i + 1 :]

        if char == "n":
            options["simulate"] = True
        elif char == "p":
            options["compat"] = True
        elif char == "v":
            m = re.match(r"\d+", rest)
            if m:
                options["verbose"] = int(m.group())
                i += len(m.group())
            else:
                options["verbose"] = options.get("verbose", 0) + 1
        elif char == "S":
            action = "stow"
        elif char == "D":
            action = "unstow"
        elif char == "R":
            action = "restow"
        elif char == "h":
            should_show_help = True
        elif char == "V":
            should_show_version = True
        elif char in ("d", "t") and rest:
            options["dir" if char == "d" else "target"] = rest
            i += len(rest)
        elif char in ("d", "t"):
            # Last character of the bundle: take the next argument as the
            # value, like tar -xf FILE or ssh -p PORT
            if arg_index + 1 < len(args):
                arg_index += 1
                options["dir" if char == "d" else "target"] = args[arg_index]
            else:
                show_usage_and_exit(f"Option {char} requires an argument")
        else:
            # Like Perl, report every unknown letter and keep processing
            # the rest of the bundle before the fatal usage exit
            print(f"Unknown option: {char}", file=sys.stderr)
            has_any_unknown_options = True
        i += 1

    return (
        action,
        arg_index,
        has_any_unknown_options,
        should_show_help,
        should_show_version,
    )


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
    pkgs_to_unstow = [p.rstrip("/") for p in pkgs_to_unstow]
    pkgs_to_stow = [p.rstrip("/") for p in pkgs_to_stow]
    check_packages(pkgs_to_stow, pkgs_to_unstow)

    return (options, pkgs_to_unstow, pkgs_to_stow)


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


# Option table mirroring Perl stow's GetOptions() specification. Long
# options resolve by exact name (or alias) first, then by unique prefix
# like Getopt::Long's auto_abbrev, which POSIXLY_CORRECT disables.
# Value types: "flag" (no value), "optint" (optional attached integer,
# like 'verbose|v:i'), "string" (mandatory value, like 'dir|d=s').
_OPTION_SPECS = [
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


def _find_long_option(name: str, allow_abbrev: bool) -> Optional[tuple[str, str, str]]:
    """Resolve a long option name like Getopt::Long's find_option.

    An exact name/alias match wins; otherwise a unique prefix resolves via
    auto_abbrev. A prefix matching several options is a fatal ambiguity
    error. Returns (matched_name, primary_name, value_type) — matched_name
    is the name as resolved (alias as given, or the full name a prefix
    expanded to), which is what error messages use — or None if unknown.
    """
    for names, vtype in _OPTION_SPECS:
        if name in names:
            return name, names[0], vtype
    if not allow_abbrev or not name:
        return None
    hits = []
    for names, vtype in _OPTION_SPECS:
        matched = [nm for nm in names if nm.startswith(name)]
        if matched:
            hits.append((matched, names[0], vtype))
    if not hits:
        return None
    if len(hits) > 1:
        all_matched = sorted(nm for matched, _, _ in hits for nm in matched)
        show_usage_and_exit(f"Option {name} is ambiguous ({', '.join(all_matched)})")
    matched, primary, vtype = hits[0]
    return matched[0], primary, vtype


def parse_cli_options(args: Sequence[str]) -> tuple[dict, list[str], list[str]]:
    """Parse command line options.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    options: dict = {}
    pkgs_to_unstow: list[str] = []
    pkgs_to_stow: list[str] = []
    action = "stow"

    # POSIXLY_CORRECT disables the + option prefix and long-option
    # abbreviation in Perl's Getopt::Long. It would also enable
    # require_order, but Perl stow's explicit 'permute' config overrides
    # that, so packages and options may be interleaved either way.
    posixly_correct = "POSIXLY_CORRECT" in os.environ

    i = 0

    def add_package(pkg: str) -> None:
        if action == "restow":
            pkgs_to_unstow.append(pkg)
            pkgs_to_stow.append(pkg)
        elif action == "unstow":
            pkgs_to_unstow.append(pkg)
        else:
            pkgs_to_stow.append(pkg)

    def apply_long_option(
        given_name: str, primary: str, vtype: str, attached: Optional[str]
    ) -> None:
        """Apply one resolved long option, consuming the following argument
        as its value where Getopt::Long would."""
        nonlocal i, action
        if vtype == "string":
            # An empty attached value ("--ignore=") is rejected like
            # Getopt::Long rejects it: an empty regex or path is never
            # what the user meant, and an empty --ignore pattern would
            # silently match every file. An empty SEPARATE argument
            # (--dir "") is accepted, also like Getopt::Long.
            if attached:
                value = attached
            elif attached is None and i + 1 < len(args):
                i += 1
                value = args[i]
            else:
                show_usage_and_exit(f"Option {given_name} requires an argument")
            if primary in ("ignore", "defer", "override"):
                _validate_option_regex(value, primary)
                options.setdefault(primary, []).append(value)
            else:  # dir, target
                options[primary] = value
        elif vtype == "optint":
            # --verbose takes an optional ATTACHED value only; unlike
            # Perl it never consumes the next command-line argument
            # (see docs/perl-differences.md)
            if not attached:
                options["verbose"] = options.get("verbose", 0) + 1
            else:
                try:
                    options["verbose"] = int(attached)
                except ValueError:
                    # Abort like Perl instead of silently proceeding with
                    # a default level and modifying the filesystem
                    show_usage_and_exit(
                        f'Value "{attached}" invalid for option verbose (number expected)'
                    )
        else:  # flag
            if attached is not None:
                show_usage_and_exit(f"Option {given_name} does not take an argument")
            if primary == "simulate":
                options["simulate"] = True
            elif primary == "compat":
                options["compat"] = True
            elif primary in ("adopt", "no-folding", "dotfiles"):
                options[primary] = True
            elif primary == "D":
                action = "unstow"
            elif primary == "S":
                action = "stow"
            elif primary == "R":
                action = "restow"
            elif primary == "help":
                show_usage_and_exit()
            else:  # version
                show_version_and_exit()

    while i < len(args):
        arg = args[i]

        # POSIX "--" terminator: everything after it is a package name,
        # even if it starts with "-". (Perl stow silently DISCARDS the
        # arguments after "--" because Getopt::Long leaves them in @ARGV
        # unread; that is clearly unintended, so we diverge deliberately —
        # see docs/perl-differences.md.)
        if arg == "--":
            for pkg in args[i + 1 :]:
                add_package(pkg)
            break

        elif arg.startswith("--"):
            name = arg[2:]
            attached: Optional[str] = None
            # Getopt::Long only splits at "=" when at least one name
            # character precedes it ("--=x" is the unknown option "=x")
            if "=" in name and not name.startswith("="):
                name, attached = name.split("=", 1)
            resolved = _find_long_option(name, allow_abbrev=not posixly_correct)
            if resolved is None:
                show_usage_and_exit(f"Unknown option: {name}")
            given_name, primary, vtype = resolved
            apply_long_option(given_name, primary, vtype, attached)

        # Support +n for simulate (backwards compat with Perl's Getopt::Long)
        # POSIXLY_CORRECT disables + prefix support
        elif arg == "+n" and not posixly_correct:
            print("Warning: +n is deprecated, use -n instead", file=sys.stderr)
            options["simulate"] = True

        # Package argument (including "-" which is a valid package name)
        # Also matches +n when POSIXLY_CORRECT (+ not recognized as option prefix)
        elif not arg.startswith("-") or arg == "-":
            add_package(arg)

        else:
            # Bundled short options: -xyz is parsed as -x -y -z
            (
                action,
                i,
                has_any_unknown_options,
                should_show_help,
                should_show_version,
            ) = _parse_bundled_options(args, i, options, action)
            if has_any_unknown_options:
                show_usage_and_exit(exit_code=1)
            if should_show_help:
                show_usage_and_exit()
            if should_show_version:
                show_version_and_exit()

        i += 1

    return (options, pkgs_to_unstow, pkgs_to_stow)


def sanitize_path_options(options: dict) -> None:
    """Validate and set defaults for dir and target options."""
    if "dir" not in options:
        stow_dir_env = os.environ.get("STOW_DIR")
        options["dir"] = stow_dir_env if stow_dir_env else os.getcwd()

    if not os.path.isdir(options["dir"]):
        show_usage_and_exit(
            f"{PROGRAM_NAME}: --dir value '{options['dir']}' is not a valid directory\n"
        )

    if "target" in options:
        if not os.path.isdir(options["target"]):
            show_usage_and_exit(
                f"{PROGRAM_NAME}: --target value '{options['target']}' is not a valid directory\n"
            )
    else:
        target = parent(options["dir"])
        options["target"] = target if target else "."


def check_packages(pkgs_to_stow: Sequence[str], pkgs_to_unstow: Sequence[str]) -> None:
    """Validate package names."""
    if not pkgs_to_stow and not pkgs_to_unstow:
        show_usage_and_exit(f"{PROGRAM_NAME}: No packages to stow or unstow\n")

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
    if home:
        stowrc_candidate_paths.insert(0, os.path.join(home, ".stowrc"))

    for file_path in stowrc_candidate_paths:
        try:
            with open(file_path, "r") as f:
                for line in f:
                    # Parse like Perl's shellwords so .stowrc files
                    # written for GNU Stow behave identically
                    defaults.extend(perl_shellwords(line.rstrip("\n\r")))
        except (FileNotFoundError, PermissionError):
            continue  # Skip missing or unreadable files
        except IsADirectoryError:
            raise StowCLIError(f"Could not open {file_path} for reading")

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
        except KeyError:
            raise StowCLIError(
                f"{source} references undefined environment variable ${var}; aborting!"
            )

    # Braced form: Perl stow only expands ${NAME} when the braces contain
    # word/space characters ([\w\s]+), so shell-isms like ${VAR:-default}
    # stay literal instead of being looked up (and failing) as a variable
    # named "VAR:-default".
    path = re.sub(r"(?<!\\)\$\{([\w\s]+)}", replace_var, path)
    path = re.sub(r"(?<!\\)\$(\w+)", replace_var, path)
    path = path.replace("\\$", "$")

    return path


def expand_tilde_to_homedir(path: str) -> str:
    """Expand tilde to user's home directory path."""
    if "\\~" in path:
        return path.replace("\\~", "~")

    if not path.startswith("~"):
        return path

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

    if not home:
        return path
    return home + slash + rest


def get_homedir_from_passwd(
    username: Optional[str] = None, uid: Optional[int] = None
) -> Optional[str]:
    try:
        if username is not None:
            return pwd.getpwnam(username).pw_dir
        if uid is not None:
            return pwd.getpwuid(uid).pw_dir
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None


def show_usage_and_exit(
    msg: Optional[str] = None, exit_code: Optional[int] = None
) -> NoReturn:
    """Print program usage message and exit."""
    if msg:
        print(msg, file=sys.stderr)

    print(f"""{PROGRAM_NAME} (GNU Stow) version {VERSION}

Stow-Python is a Python reimplementation of GNU Stow.
Original GNU Stow by Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others.

SYNOPSIS:

    {PROGRAM_NAME} [OPTION ...] [-D|-S|-R] PACKAGE ... [-D|-S|-R] PACKAGE ...

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
    print(f"{PROGRAM_NAME} (GNU Stow) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
