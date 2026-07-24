# Known Differences from GNU Stow (Perl)

This document catalogues behavioral differences between stow-python and GNU Stow 2.4.1 (Perl).
These are edge cases discovered through property-based testing with Hypothesis.

## 1. Package Names Starting with `--` (Long Option Style) — Resolved, Now Matches

**Example:** Package named `--o=0`

| Implementation | Behavior |
|----------------|----------|
| Perl | Getopt::Long consumes `--o=0` as an unknown-but-valued option, then reports "No packages to stow or unstow" (exit 1). Under `POSIXLY_CORRECT`, reports "Unknown option: o" (exit 1). |
| Python | Identical: "No packages to stow or unstow" (exit 1), or "Unknown option: o" under `POSIXLY_CORRECT`. |

**Result:** No longer a divergence. The Getopt::Long emulation now reproduces
Perl's `--option=value` handling exactly, so both implementations produce the
same message and exit code.

**Pinned by:** an equality test
(`test_package_named_double_dash_o_matches` in `tests/test_cli_options_both.py`)
that asserts both implementations match in default and `POSIXLY_CORRECT` modes.

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

**Note:** This is a deliberate simplification. The Pythonic approach is cleaner and behaviorally equivalent. For syscall-exact matching, see the `pythonic-bug4bug` branch.

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
- A malformed `--ignore`/`--defer`/`--override` regex (e.g. `foo(`) or a malformed pattern in an ignore file produces a clean `Failed to compile regexp` error with exit 1. Perl aborts too, but with different wording and codes: for a malformed CLI regex it dies with the raw interpreter message (`Unmatched ( in regex; marked by <-- HERE in m/( <-- HERE foo()\z/ at <path-to-stow> line N.`, exit 1); for a malformed ignore-file pattern it dies with `Failed to compile regexp: Unmatched ( in regex; ...` and exit 255 (`$!`-derived, see #13). Both cases are pinned with both sides asserted (`test_malformed_regex_fails_cleanly`, `test_malformed_ignore_file_regex_fails_cleanly` in `tests/test_cli_options_both.py`). Perl-only regex syntax such as `\Q...\E` is not supported and fails the same clean way, whereas Perl warns `Unrecognized escape` and proceeds.

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
probing) vs Python 1.

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

## 18. chkstow "Can't stat" Warning Format

For an unstattable target, Perl's File::Find warns
`Can't stat <target>: No such file or directory` and Perl's `warn` appends
` at <path-to-chkstow> line N.` — the script's own install path and line
number, an artifact of the Perl runtime with no meaning here. Python prints
the same first line and nothing more. Both exit 0 having reported nothing.
Pinned by a test asserting both formats.

## 19. Perl Runtime Warning Noise with HOME Unset

With `HOME` unset, Perl prints `Use of uninitialized value` warnings on an
otherwise successful run (the `$ENV{HOME}` tildification and global-ignore
path construction interpolate an undefined value); the run still succeeds.
Python is silent and succeeds. Same class as #4: interpreter warning noise
we do not reproduce. Pinned by a test asserting Perl's warnings and
Python's silence with identical tree results.

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

One further cosmetic caveat in this area: Perl interpolates `$ENV{HOME}`
into the `-v3` tildification substitution as a raw regex, so a HOME
containing regex metacharacters misbehaves in Perl; Python escapes it.
For any normal HOME the output is byte-identical.

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

---

## Testing Implications

The hypothesis-based oracle tests (`tests/test_oracle_hypothesis.py`) filter out these edge cases:

- Path components cannot be `.` or `..` (invalid filesystem entries)
- Package names that would be parsed as options are not directly tested
- Empty package names are filtered out (min_size=1 for package name strategy)
- Names ending with `~` are filtered (default ignore pattern, Perl bug with newlines)

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
