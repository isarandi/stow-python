# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Utility functions for stow-python.

This module contains general-purpose utilities used throughout stow-python,
including error handling, debugging, and path manipulation.
"""

from __future__ import annotations

from contextlib import contextmanager
import errno as errno_module
import logging
import os
import re
import stat
import sys

from stow_python.types import StowError

VERSION = "2.4.1"
PROGRAM_NAME = "stow"

# --- Logging setup ---


class _VerbosityFilter(logging.Filter):
    """Filter that checks message level against current verbosity setting."""

    def __init__(self):
        super().__init__()
        self.verbosity = 0

    def filter(self, record: logging.LogRecord) -> bool:
        return self.verbosity >= getattr(record, "stow_level", 0)


class _IndentFormatter(logging.Formatter):
    """Formatter that outputs just the indented message, nothing else."""

    def format(self, record: logging.LogRecord) -> str:
        indent = "    " * getattr(record, "indent", 0)
        return f"{indent}{record.getMessage()}"


_verbosity_filter = _VerbosityFilter()
_logger = logging.getLogger("stow")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_IndentFormatter())
_handler.addFilter(_verbosity_filter)
_logger.addHandler(_handler)


# Perl's $!: the errno left behind by the most recent failed syscall.
# die() exits with it when it is set, which is where stow's fatal exit
# codes come from, so every place a syscall can fail records it here.
_last_errno = 0


def record_errno(err: int | None) -> None:
    """Remember the errno of a failed syscall, the way Perl leaves $! set."""
    global _last_errno
    if err:
        _last_errno = err


def last_errno() -> int:
    """The errno of the last failed syscall, 0 if none has failed."""
    return _last_errno


def last_errno_message() -> str:
    """Perl's $! as a string: the message, or empty when no call has failed."""
    return os.strerror(_last_errno) if _last_errno else ""


def sorted_by_bytes(names) -> list[str]:
    """Perl's `sort readdir`: directory entries compare as byte strings.

    Names come off readdir as bytes and cmp orders them by byte value, so
    "\\x80raw" sorts after "zzz" and before "\\xffraw". Python's own string
    order is by code point, which puts every multi-byte character in a
    different place, and surrogate escapes for undecodable bytes in a place
    of their own again.
    """
    return sorted(names, key=os.fsencode)


def perl_true(value: str | None) -> bool:
    """Perl's truth test, under which the STRING "0" is false.

    Stow guards a lot of paths and package names with a plain Perl boolean
    test, so a path component or package literally named "0" takes the
    false branch there. Every guard that mirrors such a test goes through
    this, not through Python's own truthiness.
    """
    return bool(value) and value != "0"


# Perl's sprintf, which error() and internal_error() run their message
# through. A '%' in a path or package name therefore reaches sprintf as a
# conversion, and Perl's behaviour for a conversion with no argument left
# (substitute undef, warn) is part of the output stow produces.
_SPRINTF_SPEC = re.compile(
    r"%(\d+\$)?([-+ 0#]*)(v?)(\*|\d+)?(?:\.(\*|\d*))?(hh|ll|h|l|L|q|z|j|t)?(.?)", re.S
)

# Conversions taking an integer, whose C formatting prints nothing at all
# for a zero value with an explicit precision of zero.
_SPRINTF_INTEGER = "diuoxXbB"

# Conversions that take an argument, mapped to the value Perl's undef
# turns into for them.
_SPRINTF_UNDEF = {
    "s": "",
    "c": 0,
    "d": 0,
    "i": 0,
    "u": 0,
    "o": 0,
    "x": 0,
    "X": 0,
    "b": 0,
    "B": 0,
    "e": 0.0,
    "E": 0.0,
    "f": 0.0,
    "F": 0.0,
    "g": 0.0,
    "G": 0.0,
    "a": 0.0,
    "A": 0.0,
}


def perl_sprintf(fmt: str, *args) -> str:
    """Format like Perl's sprintf, warning on stderr as Perl does.

    Perl warns "Missing argument in sprintf" for a conversion with no
    argument left and formats undef; an unknown conversion stays in the
    output literally and warns "Invalid conversion in sprintf". The
    warnings go out before the message that is being formatted, as they do
    in Perl. Perl's warnings name the Perl source location; ours name the
    running script.
    """
    result: list[str] = []
    remaining = list(args)
    pos = 0

    while True:
        start = fmt.find("%", pos)
        if start < 0:
            result.append(fmt[pos:])
            break
        result.append(fmt[pos:start])

        match = _SPRINTF_SPEC.match(fmt, start)
        index, flags, vector, width, precision, size, conv = match.groups()
        pos = match.end()

        if conv == "%" and not vector:
            # A percent conversion still honours a field width
            result.append(_sprintf_pad("%", flags, width if width != "*" else None))
            continue

        # Only the long size modifiers mean anything to a float
        if (
            conv not in _SPRINTF_UNDEF
            or (size in ("h", "hh", "z", "j", "t") and conv in "eEfFgGaA")
            or (vector and conv == "%")
        ):
            # Perl quotes everything it consumed, and only calls it an end
            # of string when the format stopped right after the percent.
            _sprintf_warn(
                "Invalid conversion in sprintf: end of string"
                if match.group() == "%"
                else f'Invalid conversion in sprintf: "{_quote_conversion(match.group())}"'
            )
            if vector and conv == "%":
                # The percent stays available to start the next conversion
                result.append(match.group()[:-1])
                pos = match.end() - 1
            else:
                result.append(match.group())
            continue

        # However many arguments one conversion is short of, Perl warns
        # about it once.
        warned: list[bool] = []

        if conv in "oxXbBcs":
            # A sign has no meaning for these, so C ignores the flags
            flags = flags.replace("+", "").replace(" ", "")

        spec = "%" + flags
        resolved_width = width
        if width == "*":
            resolved_width = str(_sprintf_next(remaining, 0, warned))
        if resolved_width:
            spec += resolved_width
        resolved_precision = precision
        if precision is not None:
            if precision == "*":
                resolved_precision = str(_sprintf_next(remaining, 0, warned))
            spec += "." + resolved_precision

        value = _sprintf_next(remaining, _SPRINTF_UNDEF[conv], warned)
        if vector:
            # Perl's %vd formats each character of the string as a number
            result.append(
                ".".join(
                    perl_sprintf("%" + conv, ord(char)) for char in str(value or "")
                )
            )
            continue
        if conv in ("u", "i"):
            conv = "d"
        if (
            conv in _SPRINTF_INTEGER
            and precision is not None
            and not int(resolved_precision or 0)
            and not int(value)
        ):
            # C prints no digits for a zero value at precision zero, but
            # the sign a flag asked for is still there
            sign = "+" if "+" in flags else " " if " " in flags else ""
            result.append(_sprintf_pad(sign, flags, resolved_width))
        elif conv in ("b", "B"):
            # Python has no binary conversion in %-formatting
            digits = format(int(value), "b")
            if resolved_precision:
                digits = digits.rjust(int(resolved_precision), "0")
            result.append(_sprintf_pad(digits, flags, resolved_width))
        elif conv == "c":
            result.append(_sprintf_pad(chr(int(value)), flags, resolved_width))
        elif conv in ("a", "A"):
            # Hexadecimal float, which Python only spells via float.hex()
            text = re.sub(r"\.0*p", "p", float(value).hex())
            result.append(_sprintf_pad(text.upper() if conv == "A" else text, flags, resolved_width))
        elif conv in ("x", "X", "o") and "#" in flags and not int(value):
            # C prints no 0x/0 prefix for a zero value
            result.append((spec.replace("#", "", 1) + conv) % value)
        else:
            result.append((spec + conv) % value)

    return "".join(result)


def _sprintf_pad(text: str, flags: str, width: str | None) -> str:
    """Pad a preformatted conversion to its field width, as C does."""
    if not width or len(text) >= int(width):
        return text
    if "-" in flags:
        return text.ljust(int(width))
    return text.rjust(int(width), "0" if "0" in flags else " ")


def _sprintf_next(remaining: list, undef, warned: list):
    """Take the next argument, or Perl's undef with its warning."""
    if remaining:
        return remaining.pop(0)
    if not warned:
        warned.append(True)
        _sprintf_warn("Missing argument in sprintf")
    return undef


def _quote_conversion(text: str) -> str:
    """Escape a conversion the way Perl quotes it in its sprintf warning.

    Perl prints a character of the offending conversion as itself only
    when it is printable ASCII, and otherwise as a three-digit octal
    escape of its first byte.
    """
    pieces = []
    for char in text:
        if " " <= char <= "~":
            pieces.append(char)
        else:
            first_byte = char.encode("utf-8", errors="surrogateescape")[0]
            pieces.append("\\%03o" % first_byte)
    return "".join(pieces)


def _sprintf_warn(message: str) -> None:
    """Perl's warn from within sprintf, with its source location."""
    print(f"{message} at {sys.argv[0]} line {_SPRINTF_WARN_LINE}.", file=sys.stderr)


# Perl's warning names the sprintf call inside Stow::Util::error(), at
# line 64 of Stow/Util.pm. Nothing here corresponds to that location, so
# the warnings keep the line number and name the running script.
_SPRINTF_WARN_LINE = 64


def warn_uninitialized(context: str, line: int) -> None:
    """Perl's "Use of uninitialized value" warning for an undef in an expression.

    Perl names the Perl source location; ours keeps Perl's line number and
    names the running script, as the sprintf warnings do.
    """
    print(
        f"Use of uninitialized value {context} at {sys.argv[0]} line {line}.",
        file=sys.stderr,
    )


def undef_action_eq(task_ref, action, line: int) -> bool:
    """Perl's `$task_ref->{action} eq '...'` when task_ref may be undef.

    Dereferencing undef in rvalue context yields undef, and comparing
    undef with `eq` warns "Use of uninitialized value in string eq" and
    is false; `line` is the Perl source line the warning names.
    """
    if task_ref is None:
        warn_uninitialized("in string eq", line)
        return False
    return task_ref.action == action


# Line of the "| Joining: @paths" interpolation in Stow/Util.pm, which is
# where an undef path warns.
_JOIN_PATHS_WARN_LINE = 171


# Perl's stat/lstat builtins warn "Unsuccessful (l)stat on filename
# containing newline" when the syscall FAILS on a path whose name ENDS with
# a newline (the you-forgot-to-chomp heuristic in pp_sys.c — a newline in
# the middle does not warn, nor does a successful call). Every file test
# (-l, -d, -e, ...) goes through stat/lstat, so all stat-family calls in
# stow code must use these wrappers to reproduce the warnings.

def _warn_unsuccessful(path: str, syscall: str) -> None:
    """Print Perl's warning for a failed stat/lstat on a newline path."""
    if path.endswith("\n"):
        print(f"Unsuccessful {syscall} on filename containing newline", file=sys.stderr)


def lstat_with_newline_warning(path: str) -> os.stat_result:
    """os.lstat with Perl's unsuccessful-on-newline warning."""
    try:
        return os.lstat(path)
    except OSError as e:
        record_errno(e.errno)
        _warn_unsuccessful(path, "lstat")
        raise


def stat_with_newline_warning(path: str) -> os.stat_result:
    """os.stat with Perl's unsuccessful-on-newline warning."""
    try:
        return os.stat(path)
    except OSError as e:
        record_errno(e.errno)
        _warn_unsuccessful(path, "stat")
        raise


def islink_with_newline_warning(path: str) -> bool:
    """os.path.islink (one lstat) with Perl's newline warning."""
    try:
        st = os.lstat(path)
    except (OSError, ValueError) as e:
        record_errno(getattr(e, "errno", None))
        _warn_unsuccessful(path, "lstat")
        return False
    return stat.S_ISLNK(st.st_mode)


def isdir_with_newline_warning(path: str) -> bool:
    """os.path.isdir (one stat) with Perl's newline warning."""
    try:
        st = os.stat(path)
    except (OSError, ValueError) as e:
        record_errno(getattr(e, "errno", None))
        _warn_unsuccessful(path, "stat")
        return False
    return stat.S_ISDIR(st.st_mode)


def exists_with_newline_warning(path: str) -> bool:
    """os.path.exists (one stat) with Perl's newline warning."""
    try:
        os.stat(path)
    except (OSError, ValueError) as e:
        record_errno(getattr(e, "errno", None))
        _warn_unsuccessful(path, "stat")
        return False
    return True


# A Perl inline flag group, in the forms Python can also express as a
# scoped group: "(?i)", "(?-x)", "(?im-sx)".
_INLINE_FLAG_GROUP = re.compile(r"\(\?[aimsux]*(?:-[imsx]+)?\)")


def scope_inline_flags(pattern: str) -> str:
    """Rewrite Perl's inline flag groups as the scoped groups Python needs.

    Perl lets "(?i)" appear anywhere, applying from there to the end of
    the enclosing group (across alternations); Python only accepts such a
    group at the very start of a whole pattern. Turning "(?i)rest" into
    "(?i:rest)" — with the scope closed exactly where the enclosing group
    ends — compiles under Python and matches what Perl means.

    Patterns without an inline flag group come back untouched.
    """
    if not _INLINE_FLAG_GROUP.search(pattern):
        return pattern

    result: list[str] = []
    # Number of flag scopes opened inside the group at each nesting level
    pending = [0]
    i = 0
    n = len(pattern)

    while i < n:
        char = pattern[i]

        if char == "\\" and i + 1 < n:
            result.append(pattern[i : i + 2])
            i += 2
            continue

        if char == "[":
            # A character class: parentheses inside it are literal
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            result.append(pattern[i : j + 1])
            i = j + 1
            continue

        if char == "(":
            match = _INLINE_FLAG_GROUP.match(pattern, i)
            if match:
                result.append(match.group()[:-1] + ":")
                pending[-1] += 1
                i = match.end()
                continue
            pending.append(0)
            result.append(char)
            i += 1
            continue

        if char == ")":
            result.append(")" * pending.pop() if len(pending) > 1 else "")
            result.append(char)
            i += 1
            continue

        result.append(char)
        i += 1

    result.append(")" * sum(pending))
    return "".join(result)


def require_directory(path: str, msg: str) -> None:
    """Raise StowError if path is not a directory."""
    try:
        stat_result = os.stat(path)
        if not stat.S_ISDIR(stat_result.st_mode):
            raise StowError(msg, errno=errno_module.ENOTDIR)
    except OSError as e:
        record_errno(e.errno)
        raise StowError(msg, errno=e.errno) from e


def set_debug_level(level: int) -> None:
    """Set verbosity level for debug()."""
    _verbosity_filter.verbosity = level


def get_debug_level() -> int:
    """Get current verbosity level."""
    return _verbosity_filter.verbosity


def debug(level: int, indent: int, msg: str) -> None:
    """
    Log to STDERR based on debug_level setting.

    Verbosity rules:
        0: errors only
        >= 1: print operations: LINK/UNLINK/MKDIR/RMDIR/MV
        >= 2: print operation exceptions (skipping, deferring, overriding)
        >= 3: print trace detail: stow/unstow/package/contents/node
        >= 4: debug helper routines
        >= 5: debug ignore lists
    """
    _logger.debug(msg, extra={"stow_level": level, "indent": indent})


def canonpath(path: str) -> str:
    """
    Mimic Perl's File::Spec::Unix->canonpath() exactly.

    Normalizes a path by removing redundant separators and dot components,
    but does NOT resolve '..' in the middle of paths (unlike os.path.normpath).

    Transformations applied (in order):
        xx////xx   -> xx/xx      (collapse multiple slashes)
        xx/././xx  -> xx/xx      (remove /. sequences)
        ./xx       -> xx         (remove leading ./)
        /../../xx  -> /xx        (collapse leading /.. sequences)
        /..        -> /          (collapse /.. at end)
        xx/        -> xx         (remove trailing slash)

    This matches Perl's behavior where '/a/b/../c' stays as '/a/b/../c',
    NOT resolved to '/a/c' like Python's os.path.normpath would do.
    """
    if not path:
        return path

    # xx////xx -> xx/xx (collapse multiple slashes)
    path = re.sub(r'/{2,}', '/', path)

    # xx/././xx -> xx/xx and trailing /. -> / (remove /. sequences)
    # Perl: s{(?:/\.)+(?:/|\z)}{/}g
    # \Z (absolute end) matches Perl's \z; the previous lookahead form with $
    # dropped "/." to "" instead of "/" and would misfire before a trailing
    # newline in the path.
    path = re.sub(r'(?:/\.)+(?:/|\Z)', '/', path)

    # ./xx -> xx (remove leading ./, but preserve standalone ".")
    # Perl: s|^(?:\./)+||s unless $path eq "./"
    if path != "./":
        path = re.sub(r'^(?:\./)+', '', path)

    # /../../xx -> /xx (collapse leading /.. after root)
    # Perl: s|^/(?:\.\./)+|/|
    path = re.sub(r'^/(?:\.\./)+', '/', path)

    # /.. -> / (just /.. becomes /)
    # Perl source says s|^/\.\.$|/|, but the XS implementation that actually
    # runs (PathTools' canonpath) compares the whole string, so "/..\n" is
    # NOT rewritten. Match the XS behavior, which is what Stow really calls.
    if path == '/..':
        path = '/'

    # xx/ -> xx (remove trailing slash, but preserve standalone "/")
    # Perl: s|/\z|| unless $path eq "/"
    if path != '/' and path.endswith('/'):
        path = path[:-1]

    # If we ended up with empty string, return empty (Perl returns undef/empty)
    return path


def join_paths(*paths: str | None) -> str:
    """
    Concatenate given paths with Perl-compatible normalization.

    Matches Perl's Stow::Util::join_paths() exactly:
    1. Applies canonpath() to each part and the result
    2. Removes 'foo/..' pairs (but NOT '../..')

    For example:
        join_paths('a/b', '../c') -> 'a/c'      (foo/.. resolved)
        join_paths('a', '../../b') -> '../b'    (only one .. resolved)

    A None part stands for Perl's undef: interpolating it into the trace
    message warns, and the join itself skips it.
    """
    # Perl builds this message whatever the verbosity, so an undef path
    # warns even when the trace is not printed
    debug(5, 5, f"| Joining: {_interpolate_paths(paths)}")
    result = ""

    for part in paths:
        if not part:
            continue

        part = canonpath(part)

        if part.startswith("/"):
            result = part  # absolute path, ignore all previous parts
        else:
            if result and result != "/":
                result += "/"
            result += part

        debug(7, 6, f"| Join now: {result}")

    debug(6, 5, f"| Joined: {result}")

    # Need this to remove any initial ./
    result = canonpath(result)

    # Remove foo/.. pairs (but not ../..)
    # Perl: 1 while $result =~ s,(^|/)(?!\.\.)[^/]+/\.\.(/|$),$1,;
    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'(^|/)(?!\.\.)[^/]+/\.\.(/|$)', r'\1', result)
    debug(6, 5, f"| After .. removal: {result}")

    result = canonpath(result)
    debug(5, 5, f"| Final join: {result}")

    return result


def _interpolate_paths(paths: tuple) -> str:
    """Perl's "@paths" interpolation, warning about each undef element."""
    pieces = []
    for index, part in enumerate(paths):
        if part is None:
            warn_uninitialized(
                f"$paths[{index}] in join or string", _JOIN_PATHS_WARN_LINE
            )
            part = ""
        pieces.append(part)
    return " ".join(pieces)


def parent(*path_parts: str) -> str:
    """Find the parent of the given path."""
    path = re.sub(r"/+", "/", "/".join(path_parts)).rstrip("/")
    result = os.path.dirname(path)
    return "" if result == "/" else result


def canon_path(path: str) -> str:
    """
    Find absolute canonical path of given path.

    Uses chdir() to resolve symlinks and relative paths.
    """
    cwd = os.getcwd()
    try:
        os.chdir(path)
    except OSError as e:
        record_errno(e.errno)
        raise StowError(f"canon_path: cannot chdir to {path} from {cwd}") from e

    canon = os.getcwd()
    restore_cwd(cwd)
    return canon


def restore_cwd(prev: str) -> None:
    """
    Restore previous working directory.

    Raises StowError if directory no longer exists.
    """
    try:
        os.chdir(prev)
    except OSError as e:
        record_errno(e.errno)
        raise StowError(f"Your current directory {prev} seems to have vanished") from e


@contextmanager
def within_dir(path: str, name: str = "directory"):
    """Context manager to execute code within a directory, preserving cwd."""
    cwd = os.getcwd()
    try:
        os.chdir(path)
    except OSError as e:
        record_errno(e.errno)
        raise StowError(f"Cannot chdir to {name}: {path} ({e.strerror})") from e

    debug(3, 0, f"cwd now {path}")
    try:
        yield
    finally:
        restore_cwd(cwd)
        debug(3, 0, f"cwd restored to {cwd}")


def adjust_dotfile(pkg_node: str) -> str:
    """
    Convert dot-X to .X for dotfiles mode.

    Used when stowing with --dotfiles flag.
    Only transforms 'dot-X' to '.X' when X is non-empty and starts with a non-dot character.
    """
    if (
        len(pkg_node) > 4
        and pkg_node.startswith("dot-")
        and not pkg_node.startswith("dot-.")
    ):
        return "." + pkg_node[4:]
    return pkg_node


_DOT_ENTRY = re.compile(r"\.\.?\n?\Z")


def unadjust_dotfile(target_node: str) -> str:
    """
    Reverse operation: .X to dot-X

    Used during unstow with --compat and --dotfiles.
    """
    # Perl's /^\.\.?$/, whose $ also matches before one trailing newline, so
    # the entries ".\n" and "..\n" take the guard too
    if _DOT_ENTRY.match(target_node):
        return target_node

    if target_node.startswith("."):
        return "dot-" + target_node[1:]

    return target_node


def move(src: str, dst: str) -> None:
    """
    Move a file from src to dst, with NFS robustness.

    Matches Perl's File::Copy::move behavior for robustness on NFS:
    When rename() fails on NFS due to a lost server ACK, the rename
    may have actually succeeded. We detect this by pre-stat'ing the
    source and checking if post-failure the source is gone and the
    destination has the expected size.

    Falls back to copy+delete for cross-filesystem moves.
    """
    import shutil

    # Handle moving into a directory (like Perl's File::Copy::move)
    # This also produces the same stat syscall as Perl's -d check
    if os.path.isdir(dst) and not os.path.isdir(src):
        dst = os.path.join(dst, os.path.basename(src))

    # Pre-stat for NFS robustness (like Perl's File::Copy::move)
    try:
        dst_stat = os.stat(dst)
    except OSError:
        dst_stat = None

    try:
        src_size = os.stat(src).st_size
    except OSError:
        src_size = None

    # Try rename first (same-filesystem move)
    try:
        os.rename(src, dst)
        return
    except OSError:
        pass

    # NFS workaround: check if rename succeeded despite error
    # This happens when the NFS server ACK is lost but the rename completed
    if src_size is not None:
        src_exists = os.path.exists(src)
        if not src_exists:
            try:
                new_dst_stat = os.stat(dst)
                if new_dst_stat.st_size == src_size:
                    # Rename actually succeeded
                    return
            except OSError:
                pass

    # Fall back to copy+delete for cross-filesystem moves
    shutil.copy2(src, dst)
    os.unlink(src)
