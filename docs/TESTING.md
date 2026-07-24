# Testing Strategy

> **Note:** This document describes the planned testing approach. Not all layers are fully implemented yet.

This document outlines the testing approach for Stow-Python, aiming for bulletproof reliability suitable for GNU adoption.

## Testing Layers

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: Extreme/Stress Tests (Docker)                 │
│  - Disk full, 100k files, long paths, symlink loops     │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Property-Based Oracle Tests (Hypothesis)      │
│  - Random inputs, compare Python vs Perl                │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Scenario Oracle Tests                         │
│  - Real-world scenarios, verify identical behavior      │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Integration Tests                             │
│  - CLI invocation, filesystem effects                   │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Unit Tests                                    │
│  - Individual functions, edge cases                     │
└─────────────────────────────────────────────────────────┘
```

## Layer 1: Unit Tests

Test individual functions in isolation.

**Location:** `tests/test_*.py` (non-oracle tests)

### Coverage Areas

- Path utilities (`join_paths`, `parent`, `canon_path`)
- Dotfile adjustment (`adjust_dotfile`, `unadjust_dotfile`)
- Ignore pattern compilation and matching
- Task creation and manipulation
- Conflict detection logic
- Tree folding/unfolding decisions

## Layer 2: Integration Tests

Test CLI and library as black boxes.

**Location:** `tests/test_cli.py`, `tests/test_stow.py`, `tests/test_unstow.py`

### Coverage Areas

- Argument parsing (short, long, bundled options)
- RC file loading (`~/.stowrc`, `.stowrc`)
- Error message formatting
- Exit codes
- Filesystem state after operations

## Layer 3: Scenario Oracle Tests

Run identical scenarios on both Python and Perl, compare everything.

**Location:** `tests/test_oracle.py`, `tests/test_oracle_chkstow.py`

### What We Compare

1. **Return code** - Must be identical
2. **stdout** - Must be identical
3. **stderr** - Must be identical (modulo documented differences)
4. **Filesystem state** - Full recursive comparison:
   - Directory tree structure (which dirs exist)
   - Regular files (existence and contents)
   - Symlinks (existence and target path)
   - What's missing (files/dirs that were removed)
   - File types (symlink vs file vs directory at each path)
   - Permissions/mode bits
   - Ownership (uid/gid)

   **Intentionally NOT compared** (may differ):
   - mtime/atime/ctime (timestamps)
   - inode numbers

### Comparison guarantees and caveats

Precisely what the oracle comparison does and does not guarantee:

- **Output comparison** (stdout and stderr) is byte-exact modulo
  exactly two documented normalizations:
  1. Stow-Python branding lines are rewritten (program name/version
     lines differ between the two implementations by design).
  2. Perl's newline-in-filename warnings are filtered from both sides.
  Output is decoded with `errors="surrogateescape"`, so undecodable
  bytes survive decoding losslessly and the comparison is
  byte-faithful.
- **Tree-state snapshot** covers entry types, file content bytes,
  symlink destinations, permissions, and ownership — but NOT mtimes
  (the two runs create their trees at different times, so absolute
  mtimes are incomparable by construction) and NOT xattrs.
- **Syscall comparison** checks syscall name, path arguments, results,
  and order — but not `open()` flag arguments or `mkdir()` mode
  arguments. Interpreter-level differences (e.g. `O_CLOEXEC`) would
  drown the signal there; the tree-state comparison covers the effects
  of those arguments.
- On machines without strace, all non-syscall comparison layers still
  run and only the syscall layer is (loudly) skipped. CI hard-requires
  strace on Linux.

### Real-World Scenarios to Test

#### Dotfiles Management
```
□ Stow package with nested .config/app/ structure
□ Multiple packages sharing .config/ (tree unfolding)
□ --dotfiles with dot-config/app/settings.json
□ Stow from ~/dotfiles to ~ (parent target)
□ Selective stow (some packages, not all)
```

#### Conflict Handling
```
□ Pre-existing plain file at target
□ Pre-existing directory where symlink needed
□ Pre-existing symlink pointing elsewhere (not stow-owned)
□ Pre-existing symlink owned by different package
□ --adopt moving existing file into package
□ --adopt with directory structures
```

#### Tree Folding
```
□ Single package gets folded symlink
□ Second package triggers unfold
□ Unstow re-folds when possible
□ --no-folding creates individual symlinks
□ Nested folding (dir inside folded dir)
```

#### Defer/Override
```
□ --defer skips already-stowed paths
□ --override replaces already-stowed paths
□ Regex patterns in defer/override
□ Multiple --defer and --override flags
□ Package upgrade scenario (override old version)
```

#### Ignore Patterns
```
□ .stow-local-ignore in package
□ .stow-global-ignore in stow dir
□ Default ignore patterns (RCS, CVS, .git, etc.)
□ Anchored patterns (^/README.*)
□ Emacs backup files (.~, #*#)
□ Negation patterns
```

#### Multiple Stow Directories
```
□ Two stow dirs sharing target
□ Unfold symlink owned by other stow dir
□ .stow marker file detection
```

#### chkstow Diagnostics
```
□ List packages (-l)
□ Detect broken symlinks (-b)
□ Detect alien files (-a)
□ Skip .stow directories
□ Nested stow directories
```

## Layer 4: Property-Based Oracle Tests

Generate random inputs with Hypothesis, verify Python matches Perl.

**Location:** `tests/test_oracle_hypothesis.py`

### Strategies

- Random filesystem trees, with file, directory, and package names
  drawn from restricted alphabets
- Operations: stow, unstow-after-stow, and restow
- Options exercised one at a time: `verbose`, `dotfiles`,
  `no-folding`, `adopt`

Not currently generated: random symlink targets, random ignore
patterns, and random option combinations.

### Filters (Documented Exclusions)

The name alphabets exclude, by construction:
- NUL bytes and `/`
- Names starting with `-` or `+`
- The path components `.` and `..`
- Names ending in `~`

## Layer 5: Extreme/Stress Tests (planned)

**⚠️ WARNING: Run in Docker/VM only - may damage host filesystem**

**Status:** Not yet implemented. The detailed implementation plan,
including the Docker environment, is in
[EXTREME_TESTS_PLAN.md](EXTREME_TESTS_PLAN.md). The scenario lists
below summarize what it will cover.

### Filesystem Limits

```
□ Maximum filename length (255 bytes on most filesystems)
□ Maximum path length (4096 bytes on Linux)
□ Filename with all printable characters
□ Filename with unicode (emoji, RTL, zero-width)
□ 100,000+ files in single directory
□ 10,000+ nested directory levels (up to fs limit)
□ Very deep package structure
□ Very wide package structure (1000 siblings)
```

### Symlink Edge Cases

```
□ Symlink loop (a -> b -> a)
□ Long symlink chain (a -> b -> c -> ... -> z)
□ Symlink to self
□ Symlink target at max path length
□ Broken symlink (target doesn't exist)
□ Symlink to special files (/dev/null, /proc/*)
□ Relative symlink with many ../
□ Absolute symlink in package (known limitation)
```

### Resource Exhaustion

```
□ Disk full during stow (simulate with small tmpfs)
□ Disk full during unstow
□ Out of inodes
□ Permission denied mid-operation
□ Read-only filesystem
□ File locked by another process
```

### Race Conditions

```
□ File deleted between plan and execute
□ File created between plan and execute
□ Directory replaced with file
□ Symlink target changed
□ Concurrent stow operations
```

### Signal Handling / Interruption

**Note:** Neither Perl stow nor Python stow has signal handling or rollback.
Both use a two-phase approach (plan, then execute), but if killed during
execution, partial filesystem state remains. This is a known limitation
of both implementations.

```
□ SIGTERM during planning phase → safe, no changes made
□ SIGTERM during execution phase → partial state (both Perl and Python)
□ SIGINT (Ctrl+C) behavior
□ Verify no corruption of existing symlinks on interrupt
```

### Special Characters in Paths

```
□ Spaces in package names
□ Quotes in filenames
□ Backslashes in filenames
□ Newlines in filenames (Perl has bugs here)
□ Null bytes (should reject)
□ Control characters
□ Unicode normalization (NFC vs NFD)
```

### Large Scale

```
□ 1000 packages
□ 100,000 files across packages
□ 10GB total file size (symlinks only, but planning)
□ Restow of large package set
```

## Selecting Test Subsets

No pytest markers are registered (`pytest.ini_options` defines only
`testpaths` and `python_files`); subsets are selected by test file
path instead:

```bash
pytest tests/ --ignore=tests/test_oracle_hypothesis.py   # skip the slow property-based tests
pytest tests/test_oracle.py tests/test_oracle_chkstow.py # only the scenario oracle tests
pytest tests/test_stow_both.py                           # a single oracle test file
```

## Coverage Goals

| Category | Target |
|----------|--------|
| Line coverage | >90% |
| Branch coverage | >85% |
| Oracle scenarios | 100+ |
| Hypothesis examples | 1000+/test |

To measure the current line coverage, run:

```bash
pytest --cov=stow_python tests/
```

## Continuous Integration

The workflow is `.github/workflows/ci.yml`, with five jobs:

- **download-stow**: builds the Perl GNU Stow oracle via
  `tests/get_gnu_stow_for_testing_identical_behavior.sh` (cached) and
  uploads it as an artifact for the test jobs.
- **test**: matrix over Python 3.10-3.14 on Ubuntu; installs the
  package under test, fetches the oracle artifact, ensures strace is
  available, and runs the full test suite.
- **test-macos**: single-version run on macOS, without strace.
- **lint**: `ruff check`, `ruff format --check` (ruff 0.14.10) and
  mypy 1.19.1.
- **docs**: validates `docs/stow.texi` with makeinfo.

## Adding New Tests

1. **Identify the scenario** - Real bug report? Edge case? Stress test?
2. **Choose the layer** - Unit, integration, oracle, or extreme?
3. **Write Perl test first** (if oracle) - Verify Perl behavior
4. **Write Python test** - Mirror the scenario
5. **Run both** - `assert_stow_match()` for oracle tests
6. **Document** - If it reveals a difference, add to `perl-differences.md`

## Known Test Gaps

Areas needing more coverage:

- [ ] Multiple stow directories (complex scenarios)
- [ ] defer/override regex edge cases
- [ ] Partial failures and rollback behavior
- [ ] Signal handling (Ctrl+C during operation)
- [ ] Locale/encoding edge cases
- [ ] Filesystem-specific behavior (ext4 vs btrfs vs ZFS)
- [ ] Case-insensitive filesystems (macOS)
- [ ] Windows compatibility (future)

## References

- [GNU Stow Manual](https://www.gnu.org/software/stow/manual/stow.html)
- [GNU Stow Issues](https://github.com/aspiers/stow/issues) - Real bug reports
- [Dotfiles tutorials](https://systemcrafters.net/managing-your-dotfiles/using-gnu-stow/) - Real usage patterns
- [perl-differences.md](perl-differences.md) - Documented behavioral differences