# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

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
import stat
import sys
import traceback
from typing import Optional, Sequence

from stow_python.stow import _Stower
from stow_python.types import StowError, StowInternalError, StowCLIError, StowConfig
from stow_python.util import VERSION, PROGRAM_NAME, parent


# Getopt::Long's optional-integer test for 'verbose|v:+' values. Perl anchors
# with $, which also matches before one trailing newline, so "2\n" counts.
_OPTIONAL_INT_RE = re.compile(r"[+-]?[0-9]+\n?\Z")

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
        line = line[m.end():]

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
    return pieces  # all remaining entries are strings


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
        target=options.get("target"),
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

    Perl's Getopt::Long iterates byte-by-byte, not character-by-character.
    We re-encode to bytes to match this behavior for multi-byte characters.

    A value-taking option (d, t) at the END of a bundle consumes the next
    command-line argument, so `-nd DIR` works like `-n -d DIR`. A bare
    trailing v consumes a following integer argument (`-nv 4`), matching
    Getopt::Long's 'verbose|v:+' optional-value behavior.

    Returns (action, next_arg_index, has_any_unknown_options,
    should_show_help, should_show_version).
    """
    has_any_unknown_options = False
    should_show_help = False
    should_show_version = False

    # Convert to bytes to iterate byte-by-byte like Perl
    char_bytes = args[arg_index][1:].encode('utf-8', errors='surrogateescape')
    i = 0

    while i < len(char_bytes):
        byte = char_bytes[i]
        char = chr(byte) if byte < 128 else char_bytes[i:i+1].decode('latin-1')
        rest_bytes = char_bytes[i + 1:]
        rest = rest_bytes.decode('utf-8', errors='surrogateescape')

        if char == "n":
            options["simulate"] = True
        elif char == "p":
            options["compat"] = True
        elif char == "v" and (m := re.match(r"\d+", rest)):
            options["verbose"] = int(m.group())
            # Skip bytes for matched digits
            i += len(m.group().encode('utf-8'))
        elif char == "v":
            if not rest and arg_index + 1 < len(args) and _OPTIONAL_INT_RE.match(args[arg_index + 1]):
                arg_index += 1
                options["verbose"] = int(args[arg_index])
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
            i += len(rest_bytes)  # Skip remaining bytes
        elif char in ("d", "t"):
            # Last byte of the bundle: the value is the next argument
            if arg_index + 1 < len(args):
                arg_index += 1
                options["dir" if char == "d" else "target"] = args[arg_index]
            else:
                show_usage_and_exit(f"Option {char} requires an argument")
        else:
            # Output raw byte like Perl does
            sys.stderr.buffer.write(b"Unknown option: " + bytes([byte]) + b"\n")
            sys.stderr.buffer.flush()
            has_any_unknown_options = True
            # Perl continues processing all bytes, printing each unknown
        i += 1

    return action, arg_index, has_any_unknown_options, should_show_help, should_show_version


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
    check_packages(pkgs_to_unstow, pkgs_to_stow)

    return (options, pkgs_to_unstow, pkgs_to_stow)


# Getopt::Long option specification, in bin/stow's GetOptions() order.
# Each entry: (names with the primary name first, value type).
# Value types: "flag", "optint" ('verbose|v:+'), "string" ('=s').
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


def _find_long_option(name: str, allow_abbrev: bool):
    """Resolve a long option name like Getopt::Long's find_option.

    An exact name/alias match wins; otherwise a unique prefix resolves via
    auto_abbrev (which POSIXLY_CORRECT disables, hence allow_abbrev). A
    prefix matching several options is a fatal ambiguity error. Returns
    (matched_name, primary_name, value_type) — matched_name is the name as
    resolved (alias as given, or the full name a prefix expanded to), which
    is what Getopt::Long uses in error messages — or None if unknown.
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
        show_usage_and_exit(
            f"Option {name} is ambiguous ({', '.join(all_matched)})"
        )
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

    # POSIXLY_CORRECT changes Getopt::Long behavior:
    # - Disables + prefix for options (getopt_compat)
    # - Disables long-option abbreviation (auto_abbrev)
    # - Would enable require_order, BUT Perl stow explicitly sets
    #   config('permute') which overrides that, so we DON'T implement
    #   require_order here.
    posixly_correct = "POSIXLY_CORRECT" in os.environ

    i = 0

    def apply_option(given_name: str, primary: str, vtype: str,
                     attached: Optional[str]) -> None:
        """Apply one resolved long/+ option, consuming a following argument
        as its value where Getopt::Long would."""
        nonlocal i, action
        if vtype == "string":
            # Getopt::Long rejects an EMPTY attached value ("--dir=") as a
            # missing argument, though an empty separate argument
            # (-d "") is accepted.
            if attached:
                value = attached
            elif attached is None and i + 1 < len(args):
                i += 1
                value = args[i]
            else:
                show_usage_and_exit(f"Option {given_name} requires an argument")
            if primary == "dir":
                options["dir"] = value
            elif primary == "target":
                options["target"] = value
            elif primary == "ignore":
                options.setdefault("ignore", []).append(re.compile(rf"({value})\Z"))
            elif primary == "override":
                options.setdefault("override", []).append(re.compile(rf"\A({value})"))
            elif primary == "defer":
                options.setdefault("defer", []).append(re.compile(rf"\A({value})"))
        elif vtype == "optint":
            # 'verbose|v:+': an attached or following integer sets the
            # level, an empty attached value or anything else increments.
            if attached is not None:
                if attached == "":
                    options["verbose"] = options.get("verbose", 0) + 1
                elif _OPTIONAL_INT_RE.match(attached):
                    options["verbose"] = int(attached)
                else:
                    show_usage_and_exit(
                        f'Value "{attached}" invalid for option verbose (number expected)'
                    )
            elif i + 1 < len(args) and _OPTIONAL_INT_RE.match(args[i + 1]):
                i += 1
                options["verbose"] = int(args[i])
            else:
                options["verbose"] = options.get("verbose", 0) + 1
        else:
            if attached is not None:
                show_usage_and_exit(
                    f"Option {given_name} does not take an argument"
                )
            if primary == "simulate":
                options["simulate"] = True
            elif primary == "compat":
                options["compat"] = True
            elif primary == "adopt":
                options["adopt"] = True
            elif primary == "no-folding":
                options["no-folding"] = True
            elif primary == "dotfiles":
                options["dotfiles"] = True
            elif primary == "D":
                action = "unstow"
            elif primary == "S":
                action = "stow"
            elif primary == "R":
                action = "restow"
            elif primary == "help":
                show_usage_and_exit()
            elif primary == "version":
                show_version_and_exit()

    while i < len(args):
        arg = args[i]

        # Getopt::Long: "--" ends option processing and leaves the remaining
        # arguments in @ARGV, which Perl stow never looks at again — so
        # everything after "--" is silently DISCARDED, not treated as
        # packages ("stow -- pkg" yields "No packages to stow or unstow").
        if arg == "--":
            break

        elif arg.startswith("--"):
            name = arg[2:]
            attached = None
            # Getopt::Long only splits at "=" when at least one name
            # character precedes it ("--=x" is the unknown option "=x")
            if "=" in name and not name.startswith("="):
                name, attached = name.split("=", 1)
            resolved = _find_long_option(name, allow_abbrev=not posixly_correct)
            if resolved is None:
                show_usage_and_exit(f"Unknown option: {name}")
            given_name, primary, vtype = resolved
            apply_option(given_name, primary, vtype, attached)

        # Support + prefix (Perl's Getopt::Long getopt_compat mode).
        # Same name resolution as --, but "=" values are NOT recognized:
        # "+target=x" fails to resolve and reports its first byte.
        # POSIXLY_CORRECT disables + prefix support entirely.
        elif arg.startswith("+") and not posixly_correct:
            if arg == "+":
                show_usage_and_exit("Missing option after +")
            opt = arg[1:]
            resolved = _find_long_option(opt, allow_abbrev=True)
            if resolved is None:
                # Unknown + option: report first BYTE only (Perl behavior)
                first_byte = opt.encode('utf-8', errors='surrogateescape')[0:1]
                sys.stderr.buffer.write(b"Unknown option: " + first_byte + b"\n")
                sys.stderr.buffer.flush()
                show_usage_and_exit(exit_code=1)
            given_name, primary, vtype = resolved
            apply_option(given_name, primary, vtype, None)

        # Package argument (including "-" which is a valid package name).
        # Also matches +foo when POSIXLY_CORRECT (+ not an option prefix).
        elif not arg.startswith("-") or arg == "-":
            # Perl stow explicitly sets config('permute') which overrides
            # POSIXLY_CORRECT's require_order default. So we always permute
            # (continue parsing options after package arguments).
            if action == "restow":
                pkgs_to_unstow.append(arg)
                pkgs_to_stow.append(arg)
            elif action == "unstow":
                pkgs_to_unstow.append(arg)
            else:
                pkgs_to_stow.append(arg)

        else:
            # Bundled short options: -xyz is parsed as -x -y -z
            action, i, has_any_unknown_options, should_show_help, should_show_version = (
                _parse_bundled_options(args, i, options, action)
            )
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
        show_usage_and_exit(f"{PROGRAM_NAME}: --dir value '{options['dir']}' is not a valid directory\n")

    if "target" in options:
        if not os.path.isdir(options["target"]):
            show_usage_and_exit(f"{PROGRAM_NAME}: --target value '{options['target']}' is not a valid directory\n")
    else:
        target = parent(options["dir"])
        options["target"] = target if target else "."


def check_packages(pkgs_to_stow: Sequence[str], pkgs_to_unstow: Sequence[str]) -> None:
    """Validate package names."""
    if not pkgs_to_stow and not pkgs_to_unstow:
        show_usage_and_exit(f"{PROGRAM_NAME}: No packages to stow or unstow\n")

    for package in itertools.chain(pkgs_to_stow, pkgs_to_unstow):
        package = package.rstrip("/")
        if "/" in package:
            # Perl dies here and exits with $!, the errno of the last failed
            # syscall — in the normal flow that is ENOENT (2) from probing a
            # nonexistent .stowrc just before. (If a .stowrc exists, Perl
            # exits 255 instead; see docs/perl-differences.md.)
            raise StowError("Slashes are not permitted in package names", errno=2)


def _is_readable_by_effective_uid(st: os.stat_result) -> bool:
    """Check if a file is readable by the effective UID, like Perl's -r test.

    This mirrors Perl's -r operator which checks readability based on
    the stat structure's mode bits and the effective UID/GID.
    """
    mode = st.st_mode
    euid = os.geteuid()
    egid = os.getegid()

    # Root can read anything
    if euid == 0:
        return True

    # Check owner permission
    if st.st_uid == euid:
        return bool(mode & stat.S_IRUSR)

    # Check group permission
    if st.st_gid == egid or st.st_gid in os.getgroups():
        return bool(mode & stat.S_IRGRP)

    # Check other permission
    return bool(mode & stat.S_IROTH)


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
        # Check readability like Perl's -r test: stat and check mode bits
        try:
            st = os.stat(file_path)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            raise StowCLIError(f"Could not open {file_path} for reading")
        if not _is_readable_by_effective_uid(st):
            continue
        # File exists and is readable, now open it
        try:
            # newline="\n" splits lines exactly like Perl's <$FILE> (on \n
            # only, no \r translation); removesuffix matches chomp.
            with open(file_path, "r", newline="\n") as f:
                for line in f:
                    defaults.extend(perl_shellwords(line.removesuffix("\n")))
        except IOError:
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

    path = re.sub(r"(?<!\\)\$\{([^}]+)}", replace_var, path)
    path = re.sub(r"(?<!\\)\$(\w+)", replace_var, path)
    path = path.replace("\\$", "$")

    return path


def expand_tilde_to_homedir(path: str) -> str:
    """Expand tilde to user's home directory path.

    Same order as Perl's expand_tilde: the bare leading ~/~username is
    expanded first, then every escaped tilde (\\~) anywhere in the path
    is unescaped (s/\\\\~/~/g), so a later \\~ does not suppress
    expansion of the leading ~.
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


def get_homedir_from_passwd(username: str | None = None, uid: int | None = None) -> str | None:
    try:
        if username is not None:
            return pwd.getpwnam(username).pw_dir
        if uid is not None:
            return pwd.getpwuid(uid).pw_dir
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None


def show_usage_and_exit(msg: str | None = None, exit_code: int | None = None) -> None:
    """Print program usage message and exit."""
    if msg:
        print(msg, file=sys.stderr)

    print(f"""{PROGRAM_NAME} (Stow-Python) version {VERSION}

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


def show_version_and_exit() -> None:
    """Print version and exit."""
    print(f"{PROGRAM_NAME} (Stow-Python) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
