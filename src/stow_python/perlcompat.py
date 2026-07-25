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
Emulations of the Perl library behavior GNU Stow depends on.

Perl stow splits .stowrc lines with Text::ParseWords, parses its command
line with Getopt::Long, and hands user-supplied patterns to Perl's own
regexp engine. What those libraries do is not stow's own logic, so it
lives here rather than in the ports of `bin/stow` and `Stow.pm`: nothing
in this module knows what a package or a target directory is.

The names are free of the leading underscore because they are imported
across modules; the module itself is package-internal and appears in no
public export list.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Text::ParseWords
# ---------------------------------------------------------------------------

# The alternation mirrors the parse_line() pattern in Text::ParseWords 3.31:
# a double-quoted segment, a single-quoted segment, or an unquoted segment
# followed by a delimiter (end of string, whitespace, or a quote starting the
# next segment). Perl uses atomic groups (?>...) purely as a stack guard;
# the match language is identical without them.
PARSE_LINE_RE = re.compile(
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
        m = PARSE_LINE_RE.match(line)
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


# ---------------------------------------------------------------------------
# Getopt::Long
# ---------------------------------------------------------------------------


class OptionError(Exception):
    """One Getopt::Long option diagnostic.

    Getopt::Long warns about a bad option, counts it and carries on
    scanning, so every problem on the command line is reported before the
    single usage exit at the end; raising this instead of exiting on the
    spot is what reproduces that.
    """


def find_long_option(
    name: str, specs: Sequence[tuple[tuple[str, ...], str]], allow_abbrev: bool
) -> tuple[str, str, str] | None:
    """Resolve a long option name like Getopt::Long's find_option.

    An exact name/alias match wins; otherwise a unique prefix resolves via
    auto_abbrev. A prefix matching several options raises OptionError.
    The option table `specs` pairs each option's names - the first being
    the primary one - with its value type.
    Returns (matched_name, primary_name, value_type) — matched_name is the
    name as resolved (alias as given, or the full name a prefix expanded
    to), which is what error messages use — or None if unknown.
    """
    for names, vtype in specs:
        if name in names:
            return name, names[0], vtype
    if not allow_abbrev or not name:
        return None
    hits = []
    for names, vtype in specs:
        matched = [nm for nm in names if nm.startswith(name)]
        if matched:
            hits.append((matched, names[0], vtype))
    if not hits:
        return None
    if len(hits) > 1:
        all_matched = sorted(nm for matched, _, _ in hits for nm in matched)
        raise OptionError(f"Option {name} is ambiguous ({', '.join(all_matched)})")
    matched, primary, vtype = hits[0]
    return matched[0], primary, vtype


# Getopt::Long's PAT_INT: an optional sign, then underscores and digits.
# This is the whole grammar a --verbose/-v value has to satisfy, which is
# why int() alone will not do: it would accept " 5" (Perl rejects it) and
# reject "_4" and "3_0" (Perl accepts both).
GETOPT_INT_RE = re.compile(r"[-+]?_*[0-9][0-9_]*")


def parse_optint_value(value: str) -> int | None:
    """Read an attached --verbose=N value like Getopt::Long does.

    Returns None if the value is not a legal integer for the option, which
    Getopt::Long reports and counts as an error. Underscores are stripped
    from a fully matching value, so --verbose=3_0 sets level 30.
    """
    if not GETOPT_INT_RE.fullmatch(value):
        return None
    return int(value.replace("_", ""))


def take_bundled_optint(rest: str) -> tuple[int, int] | None:
    """Take a -v value off the front of a short-option bundle.

    Returns (value, characters consumed), or None when the bundle simply
    continues with more option letters (`-vx` is -v -x). Getopt::Long
    numifies the matched text here instead of stripping underscores as
    the attached long form does, so -v3_0 is level 3 and -v_4 is level 0.
    """
    m = GETOPT_INT_RE.match(rest)
    if not m:
        return None
    digits = re.match(r"[-+]?[0-9]+", m.group())
    return (int(digits.group()) if digits else 0), m.end()


# ---------------------------------------------------------------------------
# Perl regexp semantics
# ---------------------------------------------------------------------------

# A POSIX bracket class inside a bracket expression: [[:alpha:]] is a
# character class to Perl and the set [[:alph] plus a literal ] to Python's
# re, so it compiles in both engines with different meanings. A bare
# [:alpha:] OUTSIDE brackets denotes the same character set in both and is
# deliberately not matched here.
POSIX_CLASS_RE = re.compile(r"\[\^?[^\]]*\[:[a-z]+:\]")

POSIX_CLASS_HINT = (
    "POSIX character classes ([[:alpha:]]) are not supported; "
    "use Python re syntax such as [A-Za-z]"
)

# A leading global flag group, legal at the start of a pattern in both
# engines. Only the flags whose Python spelling agrees with re.ASCII are
# listed; (?u) and (?L) would contradict it and are left to fail as the
# malformed patterns they are here.
LEADING_FLAGS_RE = re.compile(r"\A\(\?([aimsx]+)\)")

INLINE_FLAGS = {
    "a": re.ASCII,
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
}


def compile_user_regexp(source: str, flags: int = 0) -> re.Pattern[str]:
    """Compile a user-supplied regexp with Perl stow's character semantics.

    re.ASCII makes \\w, \\d and \\s match the same characters as Perl's,
    which runs its engine over undecoded bytes (Stow.pm has no `use utf8`).
    Bracket expressions such as [[] draw a FutureWarning from re although
    both engines match them identically and Perl prints nothing, so that
    one warning is suppressed rather than leaked onto stderr.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return re.compile(source, flags | re.ASCII)


def hoist_leading_flags(pattern: str) -> tuple[str, int]:
    """Split a leading global flag group off a pattern, as compile flags.

    Both implementations wrap the user's pattern in an anchoring group,
    which pushes a leading (?i) off position 0 - where Perl still honors
    it but Python's re rejects it. Hoisting the group into the compile
    flags restores the meaning it has in both dialects; the anchors it
    then also covers contain no letters, so nothing else changes.
    """
    m = LEADING_FLAGS_RE.match(pattern)
    if not m:
        return pattern, 0
    flags = 0
    for letter in m.group(1):
        flags |= INLINE_FLAGS[letter]
    return pattern[m.end() :], flags


def scope_leading_flags(pattern: str) -> str:
    """Rewrite a leading (?i) group as the scoped (?i:...) form.

    Ignore-file patterns are joined into one alternation, where a leading
    flag group could not be hoisted for one alternative alone. Perl leaks
    such a flag into every following alternative; scoping it to the
    pattern that carries it is the reading users expect (see
    docs/perl-differences.md #28).
    """
    m = LEADING_FLAGS_RE.match(pattern)
    if not m:
        return pattern
    return f"(?{m.group(1)}:{pattern[m.end() :]})"
