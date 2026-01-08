# Perl Compatibility Notes

This is the `pythonic-bug4bug` branch, which achieves syscall-level exact matching with GNU Stow 2.4.1 (Perl).

**No behavioral differences.** All known Perl behaviors are replicated, including edge cases and arguable bugs.

## Syscall Name Normalization

Python and Perl make the same filesystem operations but use different syscall names due to glibc internals:

| Python | Perl | Notes |
|--------|------|-------|
| `stat(path)` | `newfstatat(AT_FDCWD, path, ..., 0)` | Same operation |
| `lstat(path)` | `newfstatat(AT_FDCWD, path, ..., AT_SYMLINK_NOFOLLOW)` | Same operation |
| `open(path)` | `openat(AT_FDCWD, path)` | Same operation |

Both link to the same glibc but call different wrapper functions. The test suite normalizes these.

---

## Quirks We Match

These are Perl behaviors that are edge cases or arguably bugs, but we replicate them for exact compatibility.

### Byte-Level CLI Parsing

Perl's Getopt::Long parses command-line arguments byte-by-byte, which leads to quirky behavior with unusual inputs. We replicate this exactly:

- **`--o=0` style package names**: If you try to stow a package literally named `--o=0`, Perl's Getopt::Long silently consumes it as an unknown option with an empty value, then complains "No packages to stow". We do the same.
- **Non-ASCII bytes after `-`**: A package named `-\x80` (dash followed by byte 0x80) gets parsed character-by-character, printing "Unknown option" twice. We match this byte-level iteration.
- **Bundled options**: `-npvS` is parsed exactly as Perl does, including edge cases with attached values like `-d/path` or `-v3`.

### Newline Warnings

When Perl's `-w` warnings are enabled (as they are in stow), any `stat` or `lstat` on a path containing a newline prints `Unsuccessful stat on filename containing newline` to stderr. This is a Perl runtime warning, not stow code. We emit identical warnings using Python's `warnings` module.

### Empty Package Names

Running `stow ''` (empty string as package name) causes Perl to interpret it as the current directory, which means it tries to stow the entire stow directory contents - including all other packages and the `.stow` marker file. This is almost certainly not what anyone wants, but we replicate it.

### Newline in Path Breaks Ignore Check

When a directory path contains a newline character, Perl's ignore pattern matching silently malfunctions. A file like `backup~` that should be ignored by the default `.+~` pattern gets symlinked anyway. This happens because the newline warning disrupts the pattern matching logic. We replicate this bug.

### lstat Before unlink

Perl's built-in `unlink` function (in `doio.c`) includes a safety check for root users on ancient Unix systems that allowed root to delete directories with `unlink`. Before removing a file, Perl does an `lstat` to verify it's not a directory. On modern Linux this is redundant (the kernel returns EISDIR), but Perl still does it, and so do we.

### RC File Stat Check

Before reading `.stowrc` configuration files, Perl checks if the file is readable using the `-r` test, which translates to a `stat` syscall. Only then does it `open` the file. The Pythonic approach would be to just try opening and catch exceptions, but we match Perl's two-step check.

### File::Find Traversal Pattern

The `chkstow` utility walks directory trees to find packages, bad links, and alien files. Perl's `File::Find` module has a specific traversal pattern:
- It `chdir`s into directories rather than using absolute paths
- When backtracking multiple levels, it uses `chdir("../..")` rather than multiple `chdir("..")` calls
- It performs `lstat`, `readlink`, and `open` calls in a specific order

We replicate this exactly, including the multi-level chdir optimization.

### NFS-Robust Move

When using `--adopt` to move a file into the stow package, the `rename()` syscall might "fail" even though it succeeded - this happens on NFS when the server completes the operation but the acknowledgment is lost. Perl's `File::Copy::move` handles this by checking if the source file disappeared and the destination has the expected size. We implement the same check.

---

## Testing

The test suite runs both implementations under strace and compares:
- Return codes
- Stdout/stderr output
- Filesystem operations (same syscalls in same order)

Property-based tests with Hypothesis generate random package structures to find edge cases.
