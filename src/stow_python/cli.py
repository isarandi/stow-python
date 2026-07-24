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
from typing import NoReturn
from collections.abc import Sequence

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
    pieces: list[str | None] = []
    word: str | None = None

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


# Perl derives its program name from $0 (bin/stow:469-470), so a renamed
# copy or a symlink identifies itself under that name in the usage banner,
# the SYNOPSIS line and --version. The "stow: ERROR:" prefix is NOT
# derived - Perl hardcodes it in Stow::Util (lib/Stow/Util.pm:45) - which
# is why library code keeps using PROGRAM_NAME.
_program_name = PROGRAM_NAME


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


def _parse_bundled_options(
    args: Sequence[str], arg_index: int, options: dict, action: str
) -> tuple[str, int, bool, bool, bool]:
    """Parse bundled short options like -npvS at args[arg_index].

    A value-taking option (d, t) at the end of a bundle consumes the next
    command-line argument, so `-nt DIR` works like `-n -t DIR`.

    Returns (action, next_arg_index, had_option_error, should_show_help,
    should_show_version).
    """
    had_option_error = False
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
            taken = _take_bundled_optint(rest)
            if taken is None:
                options["verbose"] = options.get("verbose", 0) + 1
            else:
                options["verbose"], consumed = taken
                i += consumed
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
                print(f"Option {char} requires an argument", file=sys.stderr)
                had_option_error = True
        else:
            # Like Perl, report every unknown letter and keep processing
            # the rest of the bundle before the fatal usage exit
            print(f"Unknown option: {char}", file=sys.stderr)
            had_option_error = True
        i += 1

    return (
        action,
        arg_index,
        had_option_error,
        should_show_help,
        should_show_version,
    )


# Getopt::Long's PAT_INT: an optional sign, then underscores and digits.
# This is the whole grammar a --verbose/-v value has to satisfy, which is
# why int() alone will not do: it would accept " 5" (Perl rejects it) and
# reject "_4" and "3_0" (Perl accepts both).
_GETOPT_INT_RE = re.compile(r"[-+]?_*[0-9][0-9_]*")


def _parse_optint_value(value: str) -> int | None:
    """Read an attached --verbose=N value like Getopt::Long does.

    Returns None if the value is not a legal integer for the option, which
    Getopt::Long reports and counts as an error. Underscores are stripped
    from a fully matching value, so --verbose=3_0 sets level 30.
    """
    if not _GETOPT_INT_RE.fullmatch(value):
        return None
    return int(value.replace("_", ""))


def _take_bundled_optint(rest: str) -> tuple[int, int] | None:
    """Take a -v value off the front of a short-option bundle.

    Returns (value, characters consumed), or None when the bundle simply
    continues with more option letters (`-vx` is -v -x). Getopt::Long
    numifies the matched text here instead of stripping underscores as
    the attached long form does, so -v3_0 is level 3 and -v_4 is level 0.
    """
    m = _GETOPT_INT_RE.match(rest)
    if not m:
        return None
    digits = re.match(r"[-+]?[0-9]+", m.group())
    return (int(digits.group()) if digits else 0), m.end()


def _strip_trailing_slashes(package: str) -> str:
    """Perl's s{/+$}{} on a package name.

    Perl's "$" - and Python's - also matches just before a final newline,
    so a package directory literally named "a\\n" is still recognized when
    shell completion writes it as "a/\\n".
    """
    return re.sub(r"/+$", "", package)


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


class _OptionError(Exception):
    """One Getopt::Long option diagnostic.

    Getopt::Long warns about a bad option, counts it and carries on
    scanning, so every problem on the command line is reported before the
    single usage exit at the end; raising this instead of exiting on the
    spot is what reproduces that.
    """


def _find_long_option(name: str, allow_abbrev: bool) -> tuple[str, str, str] | None:
    """Resolve a long option name like Getopt::Long's find_option.

    An exact name/alias match wins; otherwise a unique prefix resolves via
    auto_abbrev. A prefix matching several options raises _OptionError.
    Returns (matched_name, primary_name, value_type) — matched_name is the
    name as resolved (alias as given, or the full name a prefix expanded
    to), which is what error messages use — or None if unknown.
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
        raise _OptionError(f"Option {name} is ambiguous ({', '.join(all_matched)})")
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

    # Perl scans the WHOLE argument list first and only then acts on what
    # it found: `GetOptions(...) or usage('')`, then --help, then
    # --version (bin/stow:614-624). So a bad option anywhere on the line
    # beats an earlier --help, and --help beats --version.
    had_option_error = False
    want_help = False
    want_version = False

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
        given_name: str, primary: str, vtype: str, attached: str | None
    ) -> None:
        """Apply one resolved long option, consuming the following argument
        as its value where Getopt::Long would."""
        nonlocal i, action, want_help, want_version
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
                raise _OptionError(f"Option {given_name} requires an argument")
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
                level = _parse_optint_value(attached)
                if level is None:
                    # Abort like Perl instead of silently proceeding with
                    # a default level and modifying the filesystem
                    raise _OptionError(
                        f'Value "{attached}" invalid for option verbose (number expected)'
                    )
                options["verbose"] = level
        else:  # flag
            if attached is not None:
                raise _OptionError(f"Option {given_name} does not take an argument")
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
                want_help = True
            else:  # version
                want_version = True

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
            attached: str | None = None
            # Getopt::Long only splits at "=" when at least one name
            # character precedes it ("--=x" is the unknown option "=x")
            if "=" in name and not name.startswith("="):
                name, attached = name.split("=", 1)
            try:
                resolved = _find_long_option(name, allow_abbrev=not posixly_correct)
                if resolved is None:
                    raise _OptionError(f"Unknown option: {name}")
                given_name, primary, vtype = resolved
                apply_long_option(given_name, primary, vtype, attached)
            except _OptionError as e:
                print(e, file=sys.stderr)
                had_option_error = True

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
                bundle_error,
                bundle_help,
                bundle_version,
            ) = _parse_bundled_options(args, i, options, action)
            had_option_error = had_option_error or bundle_error
            want_help = want_help or bundle_help
            want_version = want_version or bundle_version

        i += 1

    if had_option_error:
        show_usage_and_exit(exit_code=1)
    if want_help:
        show_usage_and_exit()
    if want_version:
        show_version_and_exit()

    return (options, pkgs_to_unstow, pkgs_to_stow)


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
