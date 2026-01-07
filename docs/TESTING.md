# Testing Strategy

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

- Random package names (filtered for CLI safety)
- Random directory structures (depth, breadth)
- Random file contents
- Random symlink targets
- Random ignore patterns
- Random option combinations

### Filters (Documented Differences)

See `docs/perl-differences.md` for edge cases we intentionally filter:
- Package names starting with `-` or `+`
- Path components `.` or `..`
- Newlines in paths (Perl bug)

## Layer 5: Extreme/Stress Tests

**⚠️ WARNING: Run in Docker/VM only - may damage host filesystem**

**Location:** `tests/test_extreme.py` (Docker-only)

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

## Docker Test Environment

For extreme tests that could damage the host:

```dockerfile
# tests/Dockerfile.extreme
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    perl \
    stow \
    && rm -rf /var/lib/apt/lists/*

# Create small tmpfs for disk-full tests
RUN mkdir /small-disk

WORKDIR /code
COPY . .

# Run with: --tmpfs /small-disk:size=1M
CMD ["pytest", "tests/test_extreme.py", "-v"]
```

Run extreme tests:
```bash
docker build -f tests/Dockerfile.extreme -t stow-extreme .
docker run --rm \
    --tmpfs /small-disk:size=1M \
    stow-extreme
```

## Test Markers

```python
# In conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "extreme: marks tests requiring Docker")
    config.addinivalue_line("markers", "oracle: marks tests comparing to Perl")

# Usage:
@pytest.mark.extreme
def test_hundred_thousand_files():
    ...

@pytest.mark.slow
def test_deep_nesting():
    ...
```

Run specific test categories:
```bash
pytest tests/ -m "not extreme"           # Skip extreme tests
pytest tests/ -m "oracle"                 # Only oracle tests
pytest tests/ -m "extreme" --docker      # Extreme in Docker
```

## Coverage Goals

| Category | Target | Current |
|----------|--------|---------|
| Line coverage | >90% | ~71% |
| Branch coverage | >85% | TBD |
| Oracle scenarios | 100+ | ~50 |
| Hypothesis examples | 1000+/test | 100 |

## Continuous Integration

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    strategy:
      matrix:
        python: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - run: pytest tests/ -m "not extreme and not slow"

  oracle-tests:
    steps:
      - run: ./tests/get_gnu_stow_for_testing.sh
      - run: pytest tests/ -m "oracle"

  extreme-tests:
    steps:
      - run: docker build -f tests/Dockerfile.extreme -t stow-extreme .
      - run: docker run --rm --tmpfs /small-disk:size=1M stow-extreme
```

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