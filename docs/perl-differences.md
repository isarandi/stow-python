# Known Differences from GNU Stow (Perl)

This document catalogues every known behavioral difference between
stow-python and GNU Stow 2.4.1 (Perl). The differences were discovered
through property-based testing with Hypothesis, side-by-side CLI probing
against the Perl executable, and a subroutine-by-subroutine comparison of
the two codebases (see [correspondence-map.md](correspondence-map.md)).
Every behavioral entry is pinned by a test asserting both the Perl and
the Python behavior, so silent drift on either side fails the suite; the
purely syscall-level entries are enforced by the strace comparison layer
that runs in every oracle scenario.

Entry numbers are stable identifiers: they are cited from code comments,
tests and the correspondence map. When a difference is eliminated, its
entry is removed and its number retired rather than reused, so the
numbering may have gaps.

## 2. Package Names Starting with `-` + Non-ASCII Bytes

**Example:** Package named `-\x80` (dash followed by byte 0x80)

| Implementation | Behavior |
|----------------|----------|
| Perl | Prints one "Unknown option" line per BYTE of the unknown sequence |
| Python | Prints one "Unknown option" line per CHARACTER |

**Result:** Both report every unknown flag in the bundle and fail with exit
code 1, but for non-ASCII characters Perl prints one error line per UTF-8
byte while Python prints one per character (e.g. two lines vs one for `é`).

**Cause:** Perl processes the option bundle as bytes; Python as decoded
characters.

## 3. Newline in Path Breaks Perl's Ignore Check

**Example:** Directory named `\n` (literal newline) containing file `backup~`

| Implementation | Behavior |
|----------------|----------|
| Perl | Prints warnings about newline in filename, but ignore check fails silently; creates symlink for file that should be ignored |
| Python | Correctly ignores `backup~` per default `.+~` pattern |

**Result:** Perl creates symlink, Python doesn't.

**Cause:** Perl bug - the `lstat`/`stat` warnings about newlines cause the ignore pattern matching to malfunction.

**Note:** This is a Perl bug that we intentionally do not replicate.

## 4. Newline Warning Messages

**Example:** Any path containing newline character

| Implementation | Behavior |
|----------------|----------|
| Perl | Prints `Unsuccessful lstat on filename containing newline` warnings to stderr |
| Python | No warnings, handles newlines silently |

**Result:** Different stderr output.

**Cause:** Perl's `-w` warnings about newlines in filenames; Python's `os.lstat()` handles them without complaint.

**Same class, same treatment:** Perl's `Deep recursion on subroutine
"Stow::stow_contents"` warnings (two lines at a nesting depth of 99 or
more, one-shot per subroutine, exit status unaffected) and its
`Argument "_4" isn't numeric` warning from Getopt::Long on `-v_4` are
interpreter noise we do not reproduce either. The job-stack planner has no
recursion depth to warn about, and the verbosity level it ends up with is
Perl's (see #10).

## 5. `+` Prefix for Options Not Supported (except `+n`)

**Example:** `stow +v pkg` or `stow +verbose pkg`

| Implementation | Behavior |
|----------------|----------|
| Perl | Treats `+` as equivalent to `-` for options (deprecated Getopt::Long `getopt_compat` mode) |
| Python | Treats `+pkg` as a package name |

**Result:** Perl parses `+v` as `-v` (verbose mode); Python stows package `+v`.

**Cause:** Perl's Getopt::Long has a deprecated `getopt_compat` feature that treats `+` as an option prefix. This behavior is complex (partial long option matching, different handling for different characters) and rarely used, so we don't fully support it.

**Exception:** `+n` is supported as equivalent to `-n` (simulate/dry-run mode) for backwards compatibility, with an added deprecation warning — see #22.

**Note:** Use `-` for options. This entry is about `stow`; `chkstow`'s
Perl parser uses Getopt::Long's *default* configuration, and the Python
chkstow reproduces that configuration fully (including `+` prefixes,
case-insensitive long options, and unique-prefix abbreviation), so there
is no divergence for chkstow.

## 6. Empty Package Name Rejected

**Example:** `stow ''` or `stow "" pkg`

| Implementation | Behavior |
|----------------|----------|
| Perl | Interprets empty string as "current directory" (`.`), stows the ENTIRE stow directory contents including all packages and the `.stow` marker. Exits with code 0 (success). |
| Python | Rejects with error: "Package name cannot be empty" |

**Result:** Perl silently creates a broken state; Python fails fast with a clear error.

**Cause:** Perl's handling of empty package name causes it to treat the stow directory itself as a package, creating symlinks for everything inside it—including other packages and internal markers. This is clearly unintended and dangerous behavior.

**Note:** This is a Perl bug that we intentionally do not replicate. Rejecting empty package names is a safety improvement.

## 7. RC File Checking Syscall

**Example:** Checking `.stowrc` files

| Implementation | Behavior |
|----------------|----------|
| Perl | Uses `stat` syscall (via `-r` test) then `open` |
| Python | Uses `open` directly, catches exceptions |

**Result:** Identical behavior - file is read or skipped. Different syscalls in strace output.

**Note:** This is a deliberate simplification. The Pythonic approach is cleaner and behaviorally equivalent. For syscall-exact matching, see the `bug4bug` branch.

## 8. lstat Before unlink (Perl Safety Check)

**Example:** Removing a symlink during task execution

| Implementation | Behavior |
|----------------|----------|
| Perl | Calls `lstat()` before `unlink()` to check if target is a directory |
| Python | Calls `unlink()` directly |

**Result:** Identical behavior on all modern systems. One extra syscall in Perl's strace output.

**Cause:** Perl's built-in `unlink` function (in `doio.c`) includes a safety check to prevent root from accidentally deleting directories:

```c
else {  /* don't let root wipe out directories without -U */
    if (PerlLIO_lstat(s, &statbuf) < 0)
        tot--;
    else if (S_ISDIR(statbuf.st_mode)) {
        SETERRNO(EISDIR, SS_NOPRIV);
        tot--;
    }
    else {
        UNLINK(s);
    }
}
```

**Why we don't match this:**

On modern Linux (since kernel 2.1.132, released 1998), the kernel returns `EISDIR` when attempting to `unlink()` a directory, even for root. This makes Perl's application-level check redundant.

The only systems where Perl's check provides additional safety are:
- **Solaris**: Allows root to unlink directories (dangerous, corrupts filesystem)
- **OpenBSD**: May allow root to unlink directories on some filesystems

For this to matter in stow, ALL of these conditions must be met:
1. Running as root
2. On Solaris or OpenBSD with permissive filesystem
3. A race condition replaces a symlink with a directory between planning and execution

This is an extremely unlikely scenario. The check is legacy protection for ancient/non-Linux systems and we intentionally do not replicate it.

## 9. chkstow Directory Traversal Order

**Example:** Running `chkstow -l` to list packages

| Implementation | Behavior |
|----------------|----------|
| Perl | Uses `File::Find` with specific traversal order |
| Python | Uses `os.walk()` with different traversal order |

**Result:** Identical output (sorted package list), but different syscall sequences.

**Cause:** Perl's `File::Find` and Python's `os.walk()` traverse directory trees in different orders. The final output is sorted so results match, but the underlying stat/lstat/readdir syscalls occur in different sequences.

**Why we don't match this:**

1. **chkstow is read-only** - it doesn't modify the filesystem, so syscall order doesn't affect behavior
2. **Output order coincides** - only `-l` output is explicitly sorted (by both implementations); `-b`/`-a` print in traversal order, and the orders File::Find and os.walk() produce coincide for the tree shapes involved (files of a directory before its subdirectories' contents) - asserted by the oracle tests, which compare stdout byte-for-byte
3. **No practical benefit** - matching traversal order would require reimplementing `File::Find`'s quirks with no user-visible improvement

**Testing implication:** Oracle tests for chkstow compare only return code, stdout, and stderr - not filesystem operations via strace. The output matching is sufficient to verify behavioral equivalence.

**One ordering caveat:** the `Can't cd to (<parent>/) <dir>` warning for a
directory that cannot be entered (#18) is emitted when the parent is
listed, whereas File::Find emits it when that directory's turn comes. With
several unenterable directories at different depths the warnings can
therefore appear in a different order on stderr; the set of warnings, the
report on stdout and the exit code are the same.

## 10. `-v N` Value Gobbling Not Supported

Long-option abbreviation IS supported, matching Getopt::Long's auto_abbrev:
any unique prefix resolves (`--sim`, `--tar`, `--verb`), every alias works in
long form (`--R`, `--n`, `--t DIR`), an ambiguous prefix is a fatal
`Option de is ambiguous (defer, delete)` error, and POSIXLY_CORRECT disables
abbreviation — all identical to Perl. Likewise, a mandatory-value option with
an empty attached value (`--ignore=`) or no value at all (`stow pkg --target`)
fails with `Option X requires an argument` exactly like Getopt::Long.

The one Getopt::Long behavior we deliberately do not reproduce:
**`-v N` / `--verbose N` value gobbling**. Perl's `verbose|v:+` spec
consumes a following integer argument in the short and the long form
alike (`stow -v 2 pkg` and `stow --verbose 2 pkg` both set level 2); we
treat `2` as a package name and fail loudly. The failure is a clear
error with a nonzero exit code — never silent misbehavior — but this is
the most likely real-world script breakage when switching from Perl:
use the attached forms `-v2` / `--verbose=2`, which behave identically
in both implementations. The bundled form `-nt DIR` / `-nd DIR`
(a value option ending a short-option bundle taking the next argument) IS
supported, since it matches universal Unix conventions (`tar -xf FILE`).
Both the short and the long space-separated form are pinned by
`test_verbose_value_gobbling` in `tests/test_divergence_pinning_both.py`.

## 11. `--` Terminator: Packages, Not Discarded

Perl's Getopt::Long consumes `--` and leaves the remaining arguments in `@ARGV`, which stow never reads — so everything after `--` is *silently discarded* and stow reports "No packages to stow or unstow". That is clearly unintended. We implement the standard POSIX behavior: arguments after `--` are package names, which also makes packages with leading dashes usable (`stow -- -my-pkg`).

## 12. Invalid Option Values Abort Cleanly

- `--verbose=xyz` aborts with `Value "xyz" invalid for option verbose (number expected)` before any filesystem modification (Perl does the same).
- A malformed `--ignore`/`--defer`/`--override` regex (e.g. `foo(`) or a malformed pattern in an ignore file produces a clean `Failed to compile regexp` error with exit 1. Perl aborts too, but with different wording and codes: for a malformed CLI regex it dies with the raw interpreter message (`Unmatched ( in regex; marked by <-- HERE in m/( <-- HERE foo()\z/ at <path-to-stow> line N.`, exit 1); for a malformed ignore-file pattern it dies with `Failed to compile regexp: Unmatched ( in regex; ...` and exit 255 (`$!`-derived, see #13). Both cases are pinned with both sides asserted (`test_malformed_regex_fails_cleanly`, `test_malformed_ignore_file_regex_fails_cleanly` in `tests/test_cli_options_both.py`). Perl-only regex syntax such as `\Q...\E` is not supported and fails the same clean way, whereas Perl warns `Unrecognized escape` and proceeds. A POSIX bracket class (`[[:alpha:]]`) is rejected through the same path, with a fix-it hint, rather than being silently misread — see #28, which describes the regex dialect boundary in full.

## 13. Exit Codes on Fatal Errors

Perl's `die` exits with `$!` — the errno left over from the *last failed
syscall*, which is accidental: `stow a/b` ("Slashes are not permitted...")
exits 2 if no `.stowrc` exists (ENOENT from probing it) but 255 when the
last rc-file probe succeeded and `$!` is clean. We use intentional, stable
exit codes instead: where the fatal error IS a failed filesystem check, its
errno is used (missing package → 2 ENOENT; package path exists but is a
plain file → 20 ENOTDIR, byte-identical stderr to Perl); CLI usage errors
exit 1. Scripts should test for nonzero rather than specific values.

Pinned by `TestExitCodeAndWarningDivergences` in
`tests/test_divergence_pinning_both.py`: `a/b` → Perl 2 / 255 (without /
with a readable `./.stowrc`) vs Python 1; package-is-a-file → Perl 2 vs
Python 20 with identical stderr on both planners; `.stowrc`-is-a-directory
→ Perl 21 vs Python 1 (see #20).

Further cases that follow the same rule without their own pins: a
malformed ignore-file regex → Perl 255 (`$!` clean after `die`) vs
Python 1 (pinned in `tests/test_cli_options_both.py`, see #12); a
`.stowrc` referencing an undefined environment variable → byte-identical
stderr (`... references undefined environment variable $VAR; aborting!`)
but Perl exits with a leftover errno (typically 2/ENOENT from rc-file
probing) vs Python 1; a deleted working directory → byte-identical
`stow: ERROR: Your current directory  seems to have vanished` (the doubled
space is Perl's, from interpolating an undefined path) but Perl exits 2
and Python 1; an unreadable directory → `(Permission denied)` on both,
Perl exiting 13 and Python 1.

Two stdout failure modes are also worth recording here. `stow --help |
head` now behaves like Perl on both sides — the default `SIGPIPE`
disposition is restored at the CLI entry points, so the process dies on
the signal (shell status 141) instead of printing a `BrokenPipeError`
traceback. An unwritable stdout still differs: `stow --version >
/dev/full` makes Perl print `Unable to flush stdout: No space left on
device` and exit 1, while Python reports
`Exception ignored in: <_io.TextIOWrapper ...> OSError: [Errno 28]` and
exits 120. Both say the write failed and neither touches the filesystem.

## 14. Refolding Ignores Perl's `foldable('')` Bug

When unstowing makes a directory foldable, Perl's `foldable()` initializes its tracking variable to the empty string, and a foreign symlink whose destination has no slash (e.g. `a -> b`) is mistaken for "no parent seen yet". As a result Perl can fold the directory and **delete a user's unrelated symlink**. We treat such a directory as not foldable, preserving the user's link. This is a deliberate safety divergence from a data-loss bug.

## 15. chkstow Follows a Symlinked Target

Perl's File::Find does not descend through a top-level symlink argument, so `chkstow -t <symlink-to-dir>` silently checks nothing and exits 0 — an "all clear" from a diagnostic tool that inspected nothing. We follow the explicitly given target (and only that; symlinks *inside* the tree are still not descended). Covered by a pinning test asserting both behaviors.

## 16. chkstow with `STOW_DIR=0`

**Example:** `STOW_DIR=0 chkstow -b` (a stow/target directory literally named `0`)

| Implementation | Behavior |
|----------------|----------|
| Perl | `$ENV{STOW_DIR} \|\| '/usr/local/'` treats the string `"0"` as false, so chkstow silently scans `/usr/local/` instead |
| Python | `STOW_DIR=0` names the real directory `0` and is honored |

**Result:** Perl's chkstow reports on `/usr/local/`; Python's reports on `./0`.

**Cause:** Perl truthiness treats `"0"` as false. Perl's own `stow` uses
`length $ENV{STOW_DIR}` and handles `0` correctly, so upstream is internally
inconsistent here; we side with stow's semantics for both tools. A diagnostic
silently inspecting a completely different tree is the worse failure mode.
Covered by a pinning test asserting both behaviors.

## 17. Help Text Additions

`stow --version` output is byte-identical to Perl's (`stow (GNU Stow) version
2.4.1`). The `--help`/usage text keeps the same header, synopsis and option
descriptions, but adds two attribution lines (naming this as a Python
reimplementation and crediting the original GNU Stow authors) and points bug
reports at this project's issue tracker instead of the GNU addresses. The
oracle test harness normalizes exactly these known lines and nothing else.

Like Perl, the name in the banner, the SYNOPSIS line and the `--version`
output comes from `argv[0]`, so a renamed copy or a symlink identifies
itself under that name. The `stow: ERROR:` and `stow: INTERNAL ERROR:`
prefixes are hardcoded in both implementations (`Stow/Util.pm:45`).

The internal-error banner is redirected the same way as the help text: it
reads `See https://github.com/isarandi/stow-python for how to do this.`
where Perl names `http://www.gnu.org/software/stow/`, since a bug in this
implementation is not a GNU Stow bug. The block around it also has a
different shape — Perl appends `Carp::longmess()` on the message line and
leaves two blank lines before `This _is_ a bug`, while we start the
traceback on its own line and leave one — but the frame contents are
inherently uncomparable anyway.

## 18. chkstow "Can't stat" Warning Format

For an unstattable target, Perl's File::Find warns
`Can't stat <target>: No such file or directory` and Perl's `warn` appends
` at <path-to-chkstow> line N.` — the script's own install path and line
number, an artifact of the Perl runtime with no meaning here. Python prints
the same first line and nothing more. Both exit 0 having reported nothing.
Pinned by a test asserting both formats.

The same suffix, and the same treatment, applies to the other File::Find
diagnostics we reproduce: `Can't cd to <target>: <error>` for a top-level
target that cannot be entered, `Can't cd to (<parent>/) <dir>: <error>`
for a subdirectory that cannot be entered (mode 000 or a readable but
unsearchable mode 444, whose contents File::Find never sees either), and
`Can't opendir(<dir>): <error>` for one that can be entered but not
listed. In every case the message text matches byte for byte, the affected
subtree is skipped on both sides, and only Perl's ` at <script> line N.`
suffix is missing. Pinned by `test_chkstow_cannot_enter_directory_warning`
in `tests/test_divergence_pinning_both.py`.

## 19. Perl Runtime Warning Noise with HOME Unset

With `HOME` unset, Perl prints `Use of uninitialized value` warnings on an
otherwise successful run (the `$ENV{HOME}` tildification and global-ignore
path construction interpolate an undefined value); the run still succeeds.
Python is silent and succeeds. Same class as #4: interpreter warning noise
we do not reproduce. Pinned by a test asserting Perl's warnings and
Python's silence with identical tree results.

With `HOME` set to the *empty* string Perl emits no warnings at all, but
the `-v3` "Unstowing contents of" line is mangled: the tildification
substitution interpolates the empty value, so the pattern degenerates to
`/` and every slash in the line is replaced, giving
`Unstowing contents of ..~/stow ~/ p1 ~/ . (cwd=~/var~/tmp~/...)`. We
guard on a non-empty `HOME` and print the clean line. Everything else
about an empty `HOME` matches, including the `/.stowrc` probe it produces.

The same warning-noise class appears when chkstow runs from a *deleted
working directory* with a directory target: Perl's File::Find records the
working directory as undefined, completes the whole scan, and then fails
to return to it — two `Use of uninitialized value ... File/Find.pm`
warning lines followed by `Can't cd to : No such file or directory` (the
vanished directory interpolated as the empty string) and exit 2. We
produce the same report, the same `Can't cd to :` line and the same
exit 2, without the two warning lines. Pinned by
`test_deleted_working_directory` in `tests/test_chkstow_both.py`.

## 20. `.stowrc` Is a Directory

Perl's `open('<', ...)` on a directory *succeeds*; the subsequent read
fails, and the pending handle error only surfaces at `close()`, so Perl
dies with the misleading `Could not close open file: <path>` and exit 21
(EISDIR via `$!`). Python's `open()` fails up front, producing the
truthful `Could not open <path> for reading` with exit 1 (see #13).
Pinned by a test asserting both messages and codes.

## 21. `~unknownuser` in `.stowrc` Paths

For `--target=~nosuchuser/t` in an rc file, Perl substitutes the unknown
user's home directory as the EMPTY string (with an uninitialized-value
warning), silently mangling the path to `/t`. Python leaves the path
literal. Both then fail on a nonexistent directory, but the error names
different paths — and if a directory literally named `~nosuchuser/t`
exists, Python uses it while Perl never can. A path that mangles itself
is the worse failure mode. Pinned by a test asserting both behaviors.

## 22. `+n` Prints a Deprecation Warning

Perl's getopt_compat consumes `+n` silently. Python supports `+n` as the
one `+`-form (the exception documented in #5) but prepends a single
stderr line `Warning: +n is deprecated, use -n instead` to steer scripts
toward the portable spelling. Pinned by a test asserting Perl's silence
and Python's exact warning line.

## 23. `-v5` Ignore-List Regexp Lines Are Unmatchable

At verbosity 5 both implementations print their compiled default-ignore
regexps. Perl stringifies compiled patterns as `(?^:...)` and its hash
iteration order randomizes the alternation per process — two consecutive
Perl runs already differ — while Python prints its own stable format.
These two lines are therefore inherently uncomparable. Every OTHER
verbosity 4-5 debug line is byte-identical (task-action lines, join_paths
traces including "After .. removal", marked-stow-dir prefix joins), which
is pinned by a test that strips exactly these two lines from both sides
and asserts the remaining `-v5` stderr equal.

A third line in the same family is the `-v4`
`Ignoring path X due to --ignore=<pattern>` trace: Perl interpolates the
compiled `qr`, which stringifies as `(?^:(foo.*)\z)`, while we print the
pattern we compiled, `(foo.*)\Z`. Same decision to ignore, different
spelling of the regexp that caused it.

One further cosmetic caveat in this area: Perl interpolates `$ENV{HOME}`
into the `-v3` tildification substitution as a raw regex, so a HOME
containing regex metacharacters misbehaves in Perl; Python escapes it.
For any normal HOME the output is byte-identical.

## 24. `--verbose=xyz` Wording Depends on the System Getopt::Long

The diagnostic for a non-numeric verbosity comes from Perl's Getopt::Long
module, not from Stow, and its wording changed upstream:

| Getopt::Long | Message |
|--------------|---------|
| 2.54 and earlier | `Value "xyz" invalid for option verbose (number expected)` |
| 2.55 and later | `Value "xyz" invalid for option verbose (integer number expected)` |

Perl stow therefore prints different text depending only on which Perl is
installed — Debian/Ubuntu currently ship 2.54, while a Homebrew or
otherwise recent Perl ships 2.58. No single fixed string can match every
installation, so we emit the 2.54 wording (the widely deployed one, and
the one our pinned tests assert). Both spellings mean the same thing, the
exit code is 1 either way, and neither implementation touches the
filesystem.

Because the difference tracks the local Perl rather than Stow's behavior,
the oracle harness canonicalizes the newer spelling onto the older one
(`normalize_getopt_long_wording` in `tests/conftest.py`), anchored to the
complete message so it cannot hide a missing or differently-worded
diagnostic.

## 25. Perl's String `"0"` Is False

Perl has no separate boolean type, and the one-character string `"0"` is
false in every boolean context. GNU Stow tests names, `readlink` results,
path components and environment values for truth throughout, so anything
literally named `0` takes the "absent" or "failed" branch. We treat `"0"`
as the ordinary value it is. This generalizes #16, which records the same
defect in `chkstow`'s `STOW_DIR` handling.

| Where | Perl | Python |
|-------|------|--------|
| `readlink` returns `0` (`Stow.pm:2103`) | "Could not read link", aborting the whole run (exit 255) and doing nothing | stows or unstows the link like any other |
| the package owning a directory's remaining links is named `0` (`Stow.pm:1313`) | the directory is "not foldable" and stays a real directory | the directory is folded back into a symlink |
| the parent of the stow dir is `0` (`bin/stow:644`) | the default target becomes `.` | the default target is the directory named `0` |
| `~0` in an rc-file path (`bin/stow:776`) | the captured user name is false, so `~0` expands like a bare `~` | `0` is looked up as a user name, and the path stays literal |
| `HOME=0` or `LOGDIR=0` (`bin/stow:778`) | falls through to the next candidate, ending at the passwd entry | `0` names the home directory and is used |

**Result:** For a name that is exactly `0`, Perl silently takes a
different branch. In the `readlink` cases it aborts a run that has nothing
wrong with it (a foreign `z -> 0` anywhere in the target is enough to stop
an unstow); in the `foldable` case its own `-v5` trace contradicts itself,
printing `yes - package 0 in ../stow may contain bin` immediately followed
by `bin is not foldable`.

**Note:** This is a Perl bug we intentionally do not replicate. Renaming
the package, link destination or directory makes both implementations
agree. One consequence worth stating: because we do not take Perl's early
"contains no links" exit in `foldable()`, a layout in which a directory's
links point at a *marked* stow directory named `0` reaches the shared
`find_stowed_path() called directly on stow dir` internal error that Perl
reaches for every other name — Perl's falsiness merely happens to shield
that one spelling.

**Pinned by:** `TestZeroIsFalseInPerl` in
`tests/test_divergence_pinning_both.py`, covering the symlink destination,
the package name, `--dir 0/sub`, `~0` and `HOME=0`.

## 26. `%` in a Path or Package Name Garbles Perl's Own Messages

Perl's `error()` is
`die "$ProgramName: ERROR: " . sprintf($format, @args) . "\n"`
(`Stow/Util.pm:64`), and all but one of its 23 call sites pass a single,
already-interpolated string with no arguments. A `%` that came from a
package name or a path is therefore consumed as a `sprintf` conversion:
`stow 'a%%b'` makes Perl report `does not contain package a%b`, and
`stow 'pkg%s-x'` makes it report `package pkg-x` plus a
`Missing argument in sprintf` warning. We store and print the message
verbatim, so the name in the diagnostic is the name the user typed.

**Result:** Same exit status and same filesystem outcome; only Perl's
message is corrupted. The same applies to every other fatal message that
interpolates a path, including `Could not create directory:`,
`canon_path: cannot chdir to ...` and
`Your current directory ... seems to have vanished`.

**Note:** This is a Perl bug we intentionally do not replicate — an error
message that misnames the offending path is actively misleading.

**Pinned by:** `test_percent_in_package_name_garbles_perl_message` in
`tests/test_divergence_pinning_both.py`.

## 27. The Working Directory Is Restored When a Run Dies

Perl's `within_target_do` (`Stow.pm:352-361`) chdirs into the target, runs
the planning or execution phase, and only then restores the previous
directory — with no `eval` around the call, so a fatal error skips the
restore entirely and the process dies inside the target. We use a
`try`/`finally`, so the caller's working directory is always restored.

**Result:** On a fatal error our run makes one extra `chdir` syscall and,
at `-v3` and above, prints one extra `cwd restored to <dir>` line after
the `cwd now <target>` line. Successful runs are identical.

**Note:** Deliberate. Leaving the process in a different directory than it
started in matters for the library API, where a failed `stow()` call must
not silently relocate its caller; the cost is one line of debug output on
a path that is aborting anyway.

**Pinned by:** `test_cwd_restored_on_fatal_error` in
`tests/test_divergence_pinning_both.py`.

## 28. Regex Dialect: Python `re`, With Guardrails

`--ignore`, `--defer`, `--override` and ignore-file patterns are compiled
with Python's `re`, not Perl's engine. The two dialects agree on
everything stow's documentation shows, and the remaining gaps are handled
so that a pattern never silently means something different:

- **Byte-mode character classes are reproduced.** `Stow.pm` has no
  `use utf8`, so Perl matches over undecoded bytes and `\w`, `\d`, `\s`
  cover ASCII only. We compile user patterns with `re.ASCII`, so `\w+`
  matches the same names in both.
- **POSIX bracket classes are rejected loudly.** `[[:alpha:]]` is a
  character class to Perl and the set `[[:alph]` followed by a literal `]`
  to Python. Because that compiles in both engines with different
  meanings, we refuse it: `Failed to compile regexp: POSIX character
  classes ([[:alpha:]]) are not supported; use Python re syntax such as
  [A-Za-z]`, exit 1, nothing touched. Perl accepts it and quietly ignores
  (or overrides) a different set of files. A bare `[:alpha:]` *outside* a
  bracket expression means the same set in both dialects and is accepted.
- **A leading global flag group is honored.** Both implementations wrap
  the user's pattern in an anchoring group, which pushes a leading `(?i)`
  off position 0 where Python's `re` would reject it; we hoist it into the
  compile flags instead, so `--ignore='(?i)man'` and a `(?i)man` line in
  an ignore file behave exactly as in Perl. Ignore-file patterns are
  joined into one alternation, where the flag is scoped to its own
  alternative (`(?i:man)`); Perl leaks it into every alternative that
  follows, which is a bug nobody relies on.
- **What remains different:** a pattern that counts characters rather than
  classifying them. `^.....$` counts five bytes in Perl and five
  characters in Python, so it matches a five-byte name such as `caf\xc3\xa9`
  only in Perl. Perl-only syntax (`\Q...\E`, `(?{...})`) is not supported
  and fails with the same clean `Failed to compile regexp` error (#12).

**Pinned by:** `test_posix_character_class_rejected_not_misread` and
`test_byte_vs_character_counting_in_pattern` in
`tests/test_divergence_pinning_both.py`.

## 29. `join_paths` Collapses `..` Even After a `..`-Prefixed Name

Perl removes `X/..` pairs with
`1 while $result =~ s,(^|/)(?!\.\.)[^/]+/\.\.(/|$),$1,;`
(`Stow/Util.pm:192`). The lookahead inspects only the next two characters,
so a component whose *name* starts with `..` — `..d`, `...`, `..bak` —
blocks the removal and the path never collapses. We use
`os.path.normpath`, which collapses it correctly.

**Example:** a package containing `..d/f1`, stowed into a target that
already has a real `..d` directory.

| Implementation | Behavior |
|----------------|----------|
| Perl | Fails to recognize the symlink it created itself: a second `stow` reports `existing target is not owned by stow: ..d/f1` (exit 1), and unstowing refuses to remove it |
| Python | Recognizes its own link; restow is idempotent (exit 0) and unstow removes it |

The same recognition failure surfaces in conflict wording when a *second*
package contains the same `..`-prefixed path: both implementations abort
with exit 1, but Perl's conflict bullet says
`existing target is not owned by stow: ..d/f1` while ours correctly names
the owner: `existing target is stowed to a different package: ..d/f1 =>
../../stow/pkg1/..d/f1`. Perl may also report the conflict at a shallower
path than we do — it stops at the folded directory it cannot recognize,
while we descend into it and report the conflicting files within. And
because `bin/stow` sorts each warning's conflict messages
lexicographically, the different wording also changes the order in which
the bullets print.

**Note:** This is a Perl bug we intentionally do not replicate — an
implementation that cannot recognize its own symlinks cannot manage them.
A related quirk of the same regex is not replicated either: Perl's `$`
anchor matches before a trailing newline, so a component literally named
`..<LF>` cancels the preceding one (`join_paths('a', "..\n")` is `"\n"` in
Perl and `a/..\n` here). Exit codes and streams are identical there; only
the resulting tree differs.

**Pinned by:** `test_dotdot_prefixed_directory_collapse` in
`tests/test_divergence_pinning_both.py`.

---

## Syscall Normalization (Not a Behavioral Difference)

When comparing strace output between Perl and Python stow, you may see different syscall names for functionally identical operations:

| Python | Perl | Notes |
|--------|------|-------|
| `stat(path)` | `newfstatat(AT_FDCWD, path, ..., 0)` | Same operation, different glibc entry point |
| `lstat(path)` | `newfstatat(AT_FDCWD, path, ..., AT_SYMLINK_NOFOLLOW)` | Same operation |
| `open(path)` | `openat(AT_FDCWD, path)` | Same operation |

**Why this happens:**

Both Perl and Python link to the **same glibc** on a given system, but they call different glibc wrapper functions based on which headers they were compiled against:

- Python (CPython) uses `__xstat64` → makes `stat` syscall
- Perl uses `stat64@GLIBC_2.33` → glibc internally implements this as `newfstatat(AT_FDCWD, ...)`

The `*at()` syscalls (`newfstatat`, `openat`, etc.) with `AT_FDCWD` as the directory file descriptor are **semantically identical** to their non-`at` counterparts. They return the same data and have the same effects.

**Important distinctions:**

1. Only `*at()` syscalls with `AT_FDCWD` are equivalent. If the first argument is a real file descriptor (e.g., `newfstatat(3, path)`), it's a different operation that resolves `path` relative to that fd, not the current working directory.

2. For `newfstatat`/`fstatat`, the `AT_SYMLINK_NOFOLLOW` flag determines whether it acts as `stat` or `lstat`:
   - Without `AT_SYMLINK_NOFOLLOW`: equivalent to `stat` (follows symlinks)
   - With `AT_SYMLINK_NOFOLLOW`: equivalent to `lstat` (doesn't follow symlinks)

**Impact:** None. This is purely an implementation detail of how the language runtimes interface with glibc. The test code in `tests/conftest.py` normalizes these syscall names, checking both `AT_FDCWD` and `AT_SYMLINK_NOFOLLOW` flags to correctly distinguish `stat` from `lstat`.

**Path-spelling differences with the same effect.** Two more come from
`join_paths` and cost at most one extra probe:

- When every component of a joined path cancels out, Perl's
  `File::Spec->canonpath('')` is `''` and splitting it yields no segments,
  so its marked-stow-dir loop never runs; `os.path.normpath('a/..')` is
  `.`, which is then treated as one real segment. A link destination that
  cancels back to the top-level target therefore costs us one extra
  `stat(".stow")` and a handful of extra `-v5` lines. The return value is
  the same on both sides.
- `canonpath` collapses every run of slashes, while `os.path.normpath`
  preserves a leading `//` (the POSIX rule), so with `HOME=//home/u` the
  `-v5` join trace and the `Using ignore file:` line print
  `//home/u/.stow-global-ignore` where Perl prints `/home/u/...`. The two
  spellings name the same file.

---

## Testing Implications

The hypothesis-based oracle tests (`tests/test_oracle_hypothesis.py`) filter out these edge cases:

- Path components cannot be `.` or `..` (invalid filesystem entries)
- Package names that would be parsed as options are not directly tested
- Empty package names are filtered out (min_size=1 for package name strategy)
- Names ending with `~` are filtered (default ignore pattern, Perl bug with newlines)
- A package named `.stowrc` is filtered: the runs use the stow dir as their
  working directory, so it would make `./.stowrc` a directory — divergence
  #20, already pinned by its own test
- A package named `0` (#25) and path components starting with `..` (#29)
  are NOT filtered — the strategies deliberately inject them at a fixed
  rate (one package set in ten gets a `0` package, one path in twenty a
  `..`-prefixed component) so every run exercises these corners — and a
  resulting mismatch is accepted only when it matches the documented
  divergence's exact signature (`_matches_documented_divergence` in
  `tests/test_oracle_hypothesis.py`); any other mismatch still fails. The
  one exception is the verbose-output property, which assumes both
  triggers away because #25 and #29 alter the verbose trace itself with
  no tight signature to check against

These filters ensure the oracle tests focus on behavioral equivalence for realistic inputs rather than obscure edge cases where Perl has bugs or undefined behavior.

---

## Edge Case Behaviors We DO Match

Some Perl behaviors are edge cases but provide real value, so we replicate them.

### NFS-Robust Move (File::Copy::move)

Perl's `File::Copy::move` function includes a workaround for an NFS edge case: when `rename()` succeeds on the server but the acknowledgment is lost, the client sees an error even though the operation completed.

Perl handles this by:
1. Pre-stat source and destination before rename
2. If rename "fails", check if source disappeared and destination has expected size
3. If so, consider it a success

We replicate this in `stow_python/util.py:move()` because without it, a lost NFS ACK during `--adopt` would cause:
- An error message (confusing)
- Inconsistent state (file moved, symlink not created)
- Need for manual recovery

**No data loss** would occur (the user's file content is preserved in the package), but the operation would abort partway through. The NFS check prevents this annoyance on flaky network filesystems.

**Relevant code:** `src/stow_python/util.py` - `move()` function
