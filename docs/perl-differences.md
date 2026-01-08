# Known Differences from GNU Stow (Perl)

This document catalogues behavioral differences between stow-python and GNU Stow 2.4.1 (Perl).
These are edge cases discovered through property-based testing with Hypothesis.

## 1. Package Names Starting with `--` (Long Option Style)

**Example:** Package named `--o=0`

| Implementation | Behavior |
|----------------|----------|
| Perl | Getopt::Long silently consumes `--o=0` as unknown option with empty value, then reports "No packages to stow" |
| Python | Reports "Unknown option: o=0" |

**Result:** Both fail with exit code 1, but different error messages.

**Cause:** Getopt::Long has special handling for `--option=value` syntax that our manual parser doesn't replicate.

## 2. Package Names Starting with `-` + Non-ASCII Bytes

**Example:** Package named `-\x80` (dash followed by byte 0x80)

| Implementation | Behavior |
|----------------|----------|
| Perl | Prints "Unknown option" twice (interprets multi-byte sequence as separate characters) |
| Python | Prints "Unknown option: \x80" once |

**Result:** Both fail, but Perl prints two error lines, Python prints one.

**Cause:** Perl's character-by-character option parsing vs Python's string handling of non-ASCII bytes.

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

**Exception:** `+n` is supported as equivalent to `-n` (simulate/dry-run mode) for backwards compatibility.

**Note:** Use `-` for options.

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
2. **Output is sorted** - the visible result (package list, bad links, aliens) is always sorted alphabetically
3. **No practical benefit** - matching traversal order would require reimplementing `File::Find`'s quirks with no user-visible improvement

**Testing implication:** Oracle tests for chkstow compare only return code, stdout, and stderr - not filesystem operations via strace. The output matching is sufficient to verify behavioral equivalence.

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
