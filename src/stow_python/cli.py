# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Command-line interface for stow-python.

This module contains the CLI functions including argument parsing,
configuration file handling, and the main entry point.
"""

from __future__ import annotations
import errno as errno_module
import os
import pwd
import re
import signal
import stat
import sys
import traceback
from typing import Optional, Sequence

from stow_python.stow import _Stower
from stow_python.types import (
    PerlRegexp,
    StowError,
    StowInternalError,
    StowCLIError,
    StowConfig,
)
from stow_python.util import (
    VERSION,
    PROGRAM_NAME,
    isdir_with_newline_warning,
    last_errno,
    parent,
    perl_sprintf,
    perl_true,
    record_errno,
    scope_inline_flags,
    sorted_by_bytes,
    warn_uninitialized,
)


# Getopt::Long's PAT_INT, the grammar of a 'verbose|v:+' value: underscores
# may separate (and precede) the digits. Perl anchors with $, which also
# matches before one trailing newline, so "2\n" counts.
_OPTIONAL_INT_RE = re.compile(r"[-+]?_*[0-9][0-9_]*\n?\Z")

# The same grammar where it is bundled onto the option: what it matches is
# the value and whatever follows starts the next option.
_BUNDLED_INT = re.compile(r"[-+]?_*[0-9][0-9_]*")

# The leading part of a string Perl's numeric conversion actually reads.
_LEADING_NUMBER = re.compile(r"[-+]?[0-9]+")

# Line of the addition in Getopt::Long's FindOption that converts a bundled
# option's value, which is where a value with underscores warns. Perl names
# its own source; ours keeps the line number and names the running script.
_GETOPT_NUMERIC_LINE = 1238

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
    # Perl leaves SIGPIPE at its default disposition, so writing to a pipe
    # nobody reads any more kills the process by signal (status 141);
    # Python ignores it and raises BrokenPipeError instead.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    # Filenames are decoded with surrogateescape, so encoding the output
    # with the same error handler puts the original bytes back on the wire
    # the way Perl prints them, whatever the locale says.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="surrogateescape")

    # Perl has no recursion limit of its own, so a deep tree walks as far
    # as the filesystem allows; Python's default limit would stop the
    # mutually recursive planning routines first.
    sys.setrecursionlimit(100000)

    status = 0
    try:
        _main()
    except SystemExit as e:
        status = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except StowInternalError as e:
        # The stack trace follows the message on the same line and two
        # blank lines separate it from the closing note, as Perl's
        # Carp::longmess output does.
        sys.stderr.write(
            f"\n{PROGRAM_NAME}: INTERNAL ERROR: "
            f"{perl_sprintf(e.message, *e.format_args)}"
            f"{traceback.format_exc()}\n\n"
            "This _is_ a bug. Please submit a bug report so we can fix it! :-)\n"
            "See https://github.com/isarandi/stow-python for how to do this.\n"
        )
        status = _exit_status(e)
    except StowCLIError as e:
        print(e.message, file=sys.stderr)
        status = _exit_status(e)
    except StowError as e:
        print(
            f"{PROGRAM_NAME}: ERROR: {perl_sprintf(e.message, *e.format_args)}",
            file=sys.stderr,
        )
        status = _exit_status(e)

    _flush_stdout()
    sys.exit(status)


def _flush_stdout() -> None:
    """Flush stdout on the way out, complaining as Perl does when it fails.

    A closed stdout leaves Python with no stream object at all, which is
    the same EBADF Perl's flush runs into. Reporting it and leaving through
    os._exit keeps the interpreter from retrying the doomed flush and
    printing an ignored-exception notice on top of the message.
    """
    try:
        if sys.stdout is None:
            raise OSError(errno_module.EBADF, os.strerror(errno_module.EBADF))
        sys.stdout.flush()
    except OSError as e:
        print(f"Unable to flush stdout: {e.strerror}", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)


def _exit_status(error: StowError) -> int:
    """The status Perl's die() exits with: $! when a syscall has failed."""
    if error.errno is not None:
        return error.errno
    return last_errno() or 1


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
        for package in sorted_by_bytes(stower.conflicts.keys()):
            print(
                f"WARNING! stowing {package} would cause conflicts:",
                file=sys.stderr,
            )
            for message in sorted_by_bytes(stower.conflicts[package]):
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


def _warn_option(message: str) -> None:
    """Getopt::Long's complaint about one option, on stderr.

    Every one of these only tallies an error and lets parsing continue, so
    a command line with several bad options reports every one of them.
    """
    print(message, file=sys.stderr)


def _perl_numify(text: str) -> int:
    """Perl's "0 + $text", warning about a string that is not fully numeric.

    Getopt::Long converts a value bundled onto a short option without
    deleting the underscores its integer pattern let through, so "-v1_0"
    reads as 1 and warns; a value in its own argument is cleaned first and
    reads as 10. Perl's warning names Getopt/Long.pm; ours keeps the line
    number and names the running script.
    """
    match = _LEADING_NUMBER.match(text)
    if match is None or match.end() != len(text):
        print(
            f'Argument "{text}" isn\'t numeric in addition (+) '
            f"at {sys.argv[0]} line {_GETOPT_NUMERIC_LINE}.",
            file=sys.stderr,
        )
    return int(match.group()) if match else 0


def _verbose_value(text: str) -> int:
    """A 'verbose|v:+' value that arrived in its own argument.

    Getopt::Long deletes the underscores its integer pattern allows before
    reading the number, so "1_0" is 10 and "_5" is 5.
    """
    return int(text.replace("_", ""))


def _parse_bundled_options(
    args: Sequence[str], arg_index: int, options: dict, action: str
) -> tuple[str, int, bool]:
    """Parse bundled short options like -npvS at args[arg_index].

    Perl's Getopt::Long iterates byte-by-byte, not character-by-character.
    We re-encode to bytes to match this behavior for multi-byte characters.

    A value-taking option (d, t) at the END of a bundle consumes the next
    command-line argument, so `-nd DIR` works like `-n -d DIR`. A bare
    trailing v consumes a following integer argument (`-nv 4`), matching
    Getopt::Long's 'verbose|v:+' optional-value behavior.

    Returns (action, next_arg_index, had_error).
    """
    had_error = False

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
        elif char == "v" and (m := _BUNDLED_INT.match(rest)):
            options["verbose"] = _perl_numify(m.group())
            # Skip bytes for the matched value
            i += len(m.group().encode('utf-8', errors='surrogateescape'))
        elif char == "v":
            if not rest and arg_index + 1 < len(args) and _OPTIONAL_INT_RE.match(args[arg_index + 1]):
                arg_index += 1
                options["verbose"] = _verbose_value(args[arg_index])
            else:
                options["verbose"] = options.get("verbose", 0) + 1
        elif char == "S":
            action = "stow"
        elif char == "D":
            action = "unstow"
        elif char == "R":
            action = "restow"
        elif char == "h":
            options["help"] = True
        elif char == "V":
            options["version"] = True
        elif char in ("d", "t") and rest:
            options["dir" if char == "d" else "target"] = rest
            i += len(rest_bytes)  # Skip remaining bytes
        elif char in ("d", "t"):
            # Last byte of the bundle: the value is the next argument
            if arg_index + 1 < len(args):
                arg_index += 1
                options["dir" if char == "d" else "target"] = args[arg_index]
            else:
                _warn_option(f"Option {char} requires an argument")
                had_error = True
        else:
            # Name the raw byte, as Perl does
            _warn_option(
                "Unknown option: "
                + char_bytes[i : i + 1].decode("utf-8", errors="surrogateescape")
            )
            had_error = True
            # Perl continues processing all bytes, printing each unknown
        i += 1

    return action, arg_index, had_error


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


class _AmbiguousOption(Exception):
    """A prefix that resolves to more than one option."""


def _find_long_option(name: str, allow_abbrev: bool):
    """Resolve a long option name like Getopt::Long's find_option.

    An exact name/alias match wins; otherwise a unique prefix resolves via
    auto_abbrev (which POSIXLY_CORRECT disables, hence allow_abbrev). A
    prefix matching several options raises _AmbiguousOption. Returns
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
        raise _AmbiguousOption(
            f"Option {name} is ambiguous ({', '.join(all_matched)})"
        )
    matched, primary, vtype = hits[0]
    return matched[0], primary, vtype


def _compile_option_regexp(python_text: str, perl_text: str) -> PerlRegexp | None:
    """Compile a --ignore/--override/--defer pattern.

    Perl compiles these inside Getopt::Long option handlers, and a handler
    that dies only warns and tallies an error there, so the pattern is
    dropped and parsing goes on. The wording of the complaint comes from
    the regex engine, so it differs from Perl's; None marks the failure.
    """
    try:
        return PerlRegexp(re.compile(scope_inline_flags(python_text)), perl_text)
    except re.error as e:
        _warn_option(str(e))
        return None


def parse_cli_options(args: Sequence[str]) -> tuple[dict, list[str], list[str]]:
    """Parse command line options the way GetOptionsFromArray does.

    The whole argument list is parsed before anything is acted upon: every
    bad option only prints its complaint and tallies an error, so all of
    them are reported. A tallied error then ends in the usage message and
    status 1 — ahead of --help and --version, which Perl checks only after
    GetOptions has returned, and in that order.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    options: dict = {}
    pkgs_to_unstow: list[str] = []
    pkgs_to_stow: list[str] = []
    action = "stow"
    error = False

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
        nonlocal i, action, error
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
                _warn_option(f"Option {given_name} requires an argument")
                error = True
                return
            if primary == "dir":
                options["dir"] = value
            elif primary == "target":
                options["target"] = value
            else:
                if primary == "ignore":
                    compiled = _compile_option_regexp(rf"({value})\Z", rf"({value})\z")
                else:
                    compiled = _compile_option_regexp(rf"\A({value})", rf"\A({value})")
                if compiled is None:
                    error = True
                else:
                    options.setdefault(primary, []).append(compiled)
        elif vtype == "optint":
            # 'verbose|v:+': an attached or following integer sets the
            # level, an empty attached value or anything else increments.
            if attached is not None:
                if attached == "":
                    options["verbose"] = options.get("verbose", 0) + 1
                elif _OPTIONAL_INT_RE.match(attached):
                    options["verbose"] = _verbose_value(attached)
                else:
                    _warn_option(
                        f'Value "{attached}" invalid for option verbose (number expected)'
                    )
                    error = True
            elif i + 1 < len(args) and _OPTIONAL_INT_RE.match(args[i + 1]):
                i += 1
                options["verbose"] = _verbose_value(args[i])
            else:
                options["verbose"] = options.get("verbose", 0) + 1
        else:
            if attached is not None:
                _warn_option(f"Option {given_name} does not take an argument")
                error = True
                return
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
                options["help"] = True
            elif primary == "version":
                options["version"] = True

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
            # Getopt::Long splits at the first "=" that has at least one
            # name character in front of it, so "--=x=y" is the unknown
            # option "=x" with the value "y"
            equals = name.find("=", 1)
            if equals > 0:
                name, attached = name[:equals], name[equals + 1 :]
            try:
                resolved = _find_long_option(name, allow_abbrev=not posixly_correct)
            except _AmbiguousOption as e:
                _warn_option(str(e))
                error = True
                resolved = None
                name = None
            if resolved is None:
                if name is not None:
                    _warn_option(f"Unknown option: {name}")
                    error = True
            else:
                given_name, primary, vtype = resolved
                apply_option(given_name, primary, vtype, attached)

        # Support + prefix (Perl's Getopt::Long getopt_compat mode).
        # Same name resolution as --, but "=" values are NOT recognized:
        # "+target=x" fails to resolve and reports its first byte.
        # POSIXLY_CORRECT disables + prefix support entirely.
        elif arg.startswith("+") and not posixly_correct:
            if arg == "+":
                _warn_option("Missing option after +")
                error = True
                i += 1
                continue
            opt = arg[1:]
            try:
                resolved = _find_long_option(opt, allow_abbrev=True)
            except _AmbiguousOption as e:
                _warn_option(str(e))
                error = True
                resolved = None
                opt = None
            if resolved is None:
                if opt is not None:
                    # Unknown + option: report first BYTE only (Perl behavior)
                    first_byte = opt.encode("utf-8", errors="surrogateescape")[0:1]
                    _warn_option(
                        "Unknown option: "
                        + first_byte.decode("utf-8", errors="surrogateescape")
                    )
                    error = True
            else:
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
            action, i, had_error = _parse_bundled_options(args, i, options, action)
            error = error or had_error

        i += 1

    # GetOptions returning false lands in Perl's `or usage('')`: the usage
    # message on stdout and status 1, with no message line of its own
    if error:
        show_usage_and_exit(exit_code=1)

    if options.get("help"):
        show_usage_and_exit()
    if options.get("version"):
        show_version_and_exit()

    return (options, pkgs_to_unstow, pkgs_to_stow)

def sanitize_path_options(options: dict) -> None:
    """Validate and set defaults for dir and target options."""
    if "dir" not in options:
        stow_dir_env = os.environ.get("STOW_DIR")
        options["dir"] = stow_dir_env if stow_dir_env else os.getcwd()

    # Perl's -d is a stat, so a failing one on a path that ends in a
    # newline warns before the invalid-directory message
    if not isdir_with_newline_warning(options["dir"]):
        show_usage_and_exit(
            f"{_program_name()}: --dir value '{options['dir']}' is not a valid directory\n"
        )

    if "target" in options:
        if not isdir_with_newline_warning(options["target"]):
            show_usage_and_exit(
                f"{_program_name()}: --target value '{options['target']}' is not a valid directory\n"
            )
    else:
        # Perl's "parent($dir) || '.'", under which a parent of "0" is false
        target = parent(options["dir"])
        options["target"] = target if perl_true(target) else "."


# Perl's s{/+$}{} on a package name. The $ also matches before one trailing
# newline, so "a/\n" loses its slash and stays a usable package name.
_TRAILING_SLASHES = re.compile(r"/+(?=\n?\Z)")


def check_packages(pkgs_to_stow: list[str], pkgs_to_unstow: list[str]) -> None:
    """Validate package names, stripping trailing slashes from them.

    Perl loops over the arrays with a foreach alias, so the substitution
    that deletes the trailing slashes writes back into the lists the rest
    of the run works from.
    """
    if not pkgs_to_stow and not pkgs_to_unstow:
        show_usage_and_exit(f"{_program_name()}: No packages to stow or unstow\n")

    for packages in (pkgs_to_stow, pkgs_to_unstow):
        for index, package in enumerate(packages):
            package = _TRAILING_SLASHES.sub("", package, count=1)
            packages[index] = package
            if "/" in package:
                # Perl dies here and exits with $!, the errno of the last
                # failed syscall — in the normal flow that is ENOENT (2)
                # from probing a nonexistent .stowrc just before. (If a
                # .stowrc exists, Perl exits 255 instead; see
                # docs/perl-differences.md.)
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

    # Perl tests HOME with defined(), so an empty HOME still contributes a
    # candidate — the literal path "/.stowrc"
    home = os.environ.get("HOME")
    if home is not None:
        stowrc_candidate_paths.insert(0, f"{home}/.stowrc")

    for file_path in stowrc_candidate_paths:
        # Check readability like Perl's -r test: stat and check mode bits
        try:
            st = os.stat(file_path)
        except OSError as e:
            # Perl's -r is a stat, and a failed one leaves $! set for
            # whatever dies later
            record_errno(e.errno)
            continue
        # Perl's -r is only an access test: a readable DIRECTORY passes it
        # and reaches the open
        if not _is_readable_by_effective_uid(st):
            continue
        # File exists and is readable, now open it
        try:
            # newline="\n" splits lines exactly like Perl's <$FILE> (on \n
            # only, no \r translation); removesuffix matches chomp.
            # surrogateescape keeps bytes that are not valid in the locale
            # encoding, which Perl passes through untouched.
            with open(file_path, "r", errors="surrogateescape", newline="\n") as f:
                for line in f:
                    defaults.extend(perl_shellwords(line.removesuffix("\n")))
        except OSError as e:
            record_errno(e.errno)
            if e.errno == errno_module.EISDIR:
                # Perl's open succeeds on a directory; the read then fails
                # with EISDIR (setting $!), the loop reads nothing, and
                # close reports the pending error - a bare die exiting
                # with $!
                raise StowCLIError(f"Could not close open file: {file_path}")
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


# Perl reads the rc file as bytes, so \w and \s there are the ASCII classes
# only: a variable name stops at the first byte outside [A-Za-z0-9_], and a
# "$" not followed by one of those is not a variable at all. The braced form
# accepts exactly what Perl's (?:\w|\s)+ does, so "${TQZ-x}" stays literal.
_BRACED_VARIABLE = re.compile(r"(?<!\\)\$\{((?:\w|\s)+)\}", re.ASCII)
_BARE_VARIABLE = re.compile(r"(?<!\\)\$(\w+)", re.ASCII)


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

    path = _BRACED_VARIABLE.sub(replace_var, path)
    path = _BARE_VARIABLE.sub(replace_var, path)
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

        # Perl tests the captured username for truth, so "~0/..." takes the
        # bare-tilde branch, as does every step of the HOME/LOGDIR chain
        if perl_true(username):
            home = get_homedir_from_passwd(username=username)
        else:
            home = os.environ.get("HOME")
            if not perl_true(home):
                home = os.environ.get("LOGDIR")
            if not perl_true(home):
                home = get_homedir_from_passwd()

        if home is None:
            # Perl substitutes undef as the empty string, warning as it does
            warn_uninitialized("in substitution iterator", _EXPAND_TILDE_LINE)
            home = ""

        path = home + slash + rest

    return path.replace("\\~", "~")


# Line of the tilde substitution in stow's expand_tilde(), which is where
# an unknown user or a missing home directory warns.
_EXPAND_TILDE_LINE = 775


def get_homedir_from_passwd(username: str | None = None, uid: int | None = None) -> str | None:
    try:
        if username is not None:
            return pwd.getpwnam(username).pw_dir
        if uid is not None:
            return pwd.getpwuid(uid).pw_dir
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None


def _program_name() -> str:
    """Perl's $ProgramName in bin/stow: $0 with everything up to the last
    slash removed. Perl's . does not match a newline, so the substitution
    only reaches the last slash on the first line. The $ProgramName that
    prefixes ERROR: and INTERNAL ERROR: is a different one, hardcoded to
    "stow" in Stow::Util.
    """
    return re.sub(r".*/", "", sys.argv[0], count=1)


def show_usage_and_exit(msg: str | None = None, exit_code: int | None = None) -> None:
    """Print program usage message and exit."""
    if msg:
        print(msg, file=sys.stderr)

    program_name = _program_name()
    print(f"""{program_name} (Stow-Python) version {VERSION}

Stow-Python is a Python reimplementation of GNU Stow.
Original GNU Stow by Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others.

SYNOPSIS:

    {program_name} [OPTION ...] [-D|-S|-R] PACKAGE ... [-D|-S|-R] PACKAGE ...

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
    print(f"{_program_name()} (Stow-Python) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
