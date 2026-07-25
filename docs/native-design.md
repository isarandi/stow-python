# If Stow had been born in Python

A thought experiment with a practical purpose. Imagine the alternative
universe where GNU Stow was written in Python from the start: someone sits
down with only the feature description — manage farms of symlinks, stow and
unstow packages into a target tree, fold and unfold directories, handle
dotfiles, honor ignore lists — and writes it as an ordinary Python developer
would, using the standard library and its defaults. Much of what fills this
codebase today would simply not exist, because it exists only to make Python
*look like Perl*.

This document inventories that code: the places where we pay lines,
complexity and maintenance purely for behavioral compatibility, where the
natural Python behavior would have been a perfectly reasonable design for
the stow *task*. It is the complement of
[perl-differences.md](perl-differences.md): that file records where we
deliberately *differ* from Perl; this one records where we deliberately
*conform* at a cost.

**Status: none of this is actionable now.** The compatibility is worth its
price today — users have `.stowrc` files, ignore lists, scripts that parse
output and test exit codes, all shaped by decades of the Perl behavior, and
"drop-in replacement" is this project's entire claim. But a future major
version, past the migration era, could shed most of it. Keeping the
inventory current keeps that option open and the costs visible.

The core algorithm is *not* on this list. Folding and unfolding, ownership
detection, conflict handling, `--adopt`, dotfiles, deferral and override —
that is Stow's actual design, as sensible in Python as in Perl. What follows
is the wrapping, not the gift.

---

## 1. The Getopt::Long emulation

**Where:** `perlcompat.py` (value grammar, option resolution),
`cli.py` (the scanner: bundling, abbreviation, `POSIXLY_CORRECT`,
error-collection ordering), chkstow's separate default-config parser.

**What it costs:** several hundred lines emulating a Perl module's habits —
the `[-+]?_*[0-9][0-9_]*` integer grammar with its different numification
for bundled versus attached values, unique-prefix abbreviation with
Perl-worded ambiguity errors, per-character bundle diagnostics, the
scan-everything-then-act precedence of errors over `--help` over
`--version`, the deprecated `+n`.

**The native version:** `argparse` plus a small custom layer for the one
genuinely Stow-specific feature — `-S`/`-D`/`-R` switching the action for
the package names that follow. Everything else is table-driven library
behavior. Users would lose `-nt DIR`-style bundling quirks, underscore
integers and Perl's exact diagnostics; they would gain standard `--help`
formatting and standard conventions.

## 2. The shellwords port

**Where:** `perlcompat.py: perl_shellwords` for `.stowrc` parsing.

**What it costs:** a faithful port of `Text::ParseWords` 3.31, including
backslash-in-single-quotes subtleties and the drop-the-whole-line behavior
on an unmatched quote.

**The native version:** `shlex.split()`. Existing `.stowrc` files with
escaped patterns (`--ignore="\.git"`) parse differently — which is exactly
why the port exists today.

## 3. The regex dialect boundary

**Where:** `perlcompat.py` regexp helpers; `re.ASCII` on every
user-supplied pattern; POSIX-class detection with a fix-it error; hoisting
of leading `(?i)` groups (perl-differences.md #28).

**What it costs:** a guardrail layer whose only purpose is that `\w` and
`\d` match what Perl's byte-mode classes match, and that Perl-only syntax
fails loudly instead of silently meaning something else.

**The native version:** patterns are Python regexes, Unicode semantics,
documented as such, no translation or detection layer. `café` matches `\w+`
because of course it does.

## 4. Byte-transparent I/O and byte-order sorting

**Where:** `surrogateescape` reconfiguration of stdout/stderr at the entry
points; ignore files and `.stowrc` opened with `errors="surrogateescape"`
and `newline="\n"`; ASCII-only whitespace stripping; `key=os.fsencode` on
every directory-listing sort; chkstow's package sort.

**What it costs:** deliberate avoidance of Python's text model so that
non-UTF-8 filenames round-trip and sort exactly as Perl's byte strings do.

**The native version:** default text handling and plain `sorted()`. Part of
this family is genuinely good engineering regardless (not crashing on weird
bytes); the byte-*ordering* and `\n`-only record parsing are pure parity.

## 5. Perl's error surfaces, reproduced

**Where:** `e.strerror` interpolation shaped to Perl's `$!` messages; the
doubled space in `Your current directory  seems to have vanished` (an
artifact of Perl interpolating an undefined variable, reproduced byte for
byte); Perl's trailing-newline-producing message in `_foldable`; the
`$`-matches-before-final-newline emulations (trailing-slash stripping of
package names, the `.`/`..` dotfile guard); the exact conflict and warning
strings.

**What it costs:** dozens of small decisions bent toward another language's
formatting accidents.

**The native version:** ordinary exception messages; none of the
newline-anchor mimicry. Output-parsing scripts are the reason it stays.

## 6. The chdir-based engine

**Where:** `within_dir`, `canon_path`, the whole planner running with the
process chdir'd into the target; the `process_lock` serializing library
calls; relative link computation depending on the working directory.

**What it costs:** process-global state, a threading caveat documented in
the architecture notes, and a re-entrant lock — all because Perl stow
chdirs and its syscall sequence (which our strace-level tests pin) follows
from that.

**The native version:** pure-path computation with `pathlib`/`os.path
.relpath` against absolute paths, no cwd mutation, a thread-safe library
for free. This is the single deepest simplification available.

## 7. File::Find's habits in chkstow

**Where:** `_walk_target`'s enterability probing (`stat(path/.)`), the
`Can't cd to (parent/) name` and `Can't opendir(...)` warning formats, the
single trailing-slash strip of the top argument, checking a non-directory
target once under the name `./x`.

**The native version:** `os.walk` with an `onerror` handler and messages
written for humans.

## 8. Perl truthiness and definedness distinctions

**Where:** `STOW_DIR` tested by length (so `STOW_DIR=0` names a real
directory); `HOME` tested with a defined-check (so `HOME=""` probes
`/.stowrc`); the ignore-file open-failure deliberately *not* memoized
because Perl's memo assignment sits after its early return.

**The native version:** ordinary Python truthiness and an ordinary cache.
Some of these (the `"0"` family) are places we already refused to copy
Perl's bugs — but the defined-versus-truthy shadings we do copy cost real
reading effort per site.

## 9. The verbosity theater

**Where:** the logging machinery shaped to emit Perl's exact `-v0`–`-v5`
lines — four-space indent ladders, `| ` prefixes, the `$HOME`→`~`
tildification including Perl's own internal inconsistency between the stow
and unstow paths, memoized-regexps trace lines, join-path traces.

**What it costs:** the debug stream is a byte-exact reproduction of another
program's internal narration; several fixes in this repo's history exist
only to keep single `-v4`/`-v5` lines identical.

**The native version:** structured, greppable logging at levels chosen for
the Python implementation's own shape.

---

## What dropping all this would look like

Roughly: `perlcompat.py` deleted; `cli.py` at a fraction of its size on
argparse; the engine free of cwd mutation and thread-safe; text handling on
Python defaults; messages written fresh. The suite would shrink with it —
the byte-exactness layers and many divergence pins exist to police exactly
the surfaces listed above. What would remain is the part that was always
the point: the planner, the task system, the ownership model, and the
oracle discipline of testing behavior against a specification rather than
against habit.

The migration-era rule stands until then: externally visible behavior is
matched unless Perl's is indefensible, because compatibility is a promise
to existing users, not an aesthetic. This document is the ledger of what
that promise costs.
