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

---

## Testing Implications

The hypothesis-based oracle tests (`tests/test_oracle_hypothesis.py`) filter out these edge cases:

- Path components cannot be `.` or `..` (invalid filesystem entries)
- Package names that would be parsed as options are not directly tested
- Empty package names are filtered out (min_size=1 for package name strategy)
- Names ending with `~` are filtered (default ignore pattern, Perl bug with newlines)

These filters ensure the oracle tests focus on behavioral equivalence for realistic inputs rather than obscure edge cases where Perl has bugs or undefined behavior.
