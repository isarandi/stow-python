# Layer 5: Extreme/Stress Tests Implementation Plan

This document outlines the implementation plan for Docker-based extreme/stress tests as specified in `docs/TESTING.md`.

## Overview

Extreme tests validate stow behavior under unusual or hostile conditions that could damage a development environment. They MUST run in isolated Docker containers to protect the host system.

## Goals

1. Verify graceful handling of filesystem edge cases
2. Test resource exhaustion scenarios
3. Validate behavior under race conditions and interruption
4. Ensure no corruption of existing state under adverse conditions
5. Compare Python behavior against Perl where applicable

## Docker Environment Design

### Base Dockerfile

```dockerfile
# tests/Dockerfile.extreme
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    perl \
    make \
    strace \
    procps \
    fuse \
    && rm -rf /var/lib/apt/lists/*

# Install Python test dependencies
RUN pip install --no-cache-dir pytest pytest-timeout hypothesis

# Create mount points for special filesystems
RUN mkdir -p /small-disk /readonly-disk /no-inodes

# Create non-root user for permission tests
RUN useradd -m testuser

WORKDIR /code
COPY . .

# Build stow binaries
RUN python scripts/build_single_file.py

# Download Perl stow for oracle comparison
RUN cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh

# Default: run extreme tests with timeout protection
CMD ["pytest", "tests/test_extreme.py", "-v", "--timeout=60"]
```

### Docker Compose for Complex Scenarios

```yaml
# tests/docker-compose.extreme.yml
version: '3.8'

services:
  extreme-tests:
    build:
      context: ..
      dockerfile: tests/Dockerfile.extreme
    # Tmpfs mounts for disk-full and inode tests
    tmpfs:
      - /small-disk:size=1M,mode=1777
      - /no-inodes:size=10M,nr_inodes=10,mode=1777
    # Read-only mount for permission tests
    volumes:
      - readonly_vol:/readonly-disk:ro
    # Capabilities for some tests
    cap_add:
      - SYS_PTRACE  # For strace-based tests
    # Resource limits to prevent runaway tests
    mem_limit: 512m
    pids_limit: 1000

volumes:
  readonly_vol:
```

## Test Organization

### File Structure

```
tests/
  test_extreme.py          # Main extreme test file
  extreme/
    __init__.py
    conftest.py            # Extreme-specific fixtures
    test_filesystem.py     # Filesystem limit tests
    test_symlinks.py       # Symlink edge cases
    test_resources.py      # Resource exhaustion
    test_race.py           # Race conditions
    test_signals.py        # Signal handling
    test_unicode.py        # Unicode/encoding
    test_scale.py          # Large-scale tests
```

### Pytest Markers

Add to `conftest.py`:

```python
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "extreme: marks tests requiring Docker isolation (deselect with '-m \"not extreme\"')"
    )
    config.addinivalue_line(
        "markers",
        "slow: marks tests taking >10 seconds"
    )
    config.addinivalue_line(
        "markers",
        "destructive: tests that may corrupt filesystem state"
    )
```

### Environment Detection

Tests should auto-skip when not in Docker:

```python
# tests/extreme/conftest.py
import os
import pytest

def is_in_docker():
    """Detect if running inside Docker container."""
    # Check for .dockerenv file
    if os.path.exists('/.dockerenv'):
        return True
    # Check cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        return False

@pytest.fixture(autouse=True)
def require_docker():
    """Skip extreme tests when not in Docker."""
    if not is_in_docker():
        pytest.skip("Extreme tests require Docker environment")
```

## Test Categories: Priority and Implementation

### Priority 1: High Value, Easy to Implement

These tests catch real-world bugs with minimal implementation effort.

#### 1.1 Disk Full During Operation

**Why:** Users hit disk full regularly. Stow should fail gracefully without corrupting state.

**Implementation:**
```python
@pytest.fixture
def small_disk(tmp_path):
    """Create a tiny tmpfs for disk-full tests."""
    # The Docker container mounts /small-disk as 1MB tmpfs
    small_path = Path("/small-disk") / f"test_{os.getpid()}"
    small_path.mkdir(exist_ok=True)
    yield small_path
    shutil.rmtree(small_path, ignore_errors=True)

@pytest.mark.extreme
def test_disk_full_during_stow(small_disk):
    """Stow should fail gracefully when disk fills up."""
    stow_dir = small_disk / "stow"
    target_dir = small_disk / "target"
    stow_dir.mkdir()
    target_dir.mkdir()

    # Create package with enough files to exhaust disk
    pkg_dir = stow_dir / "bigpkg"
    pkg_dir.mkdir()
    for i in range(100):
        (pkg_dir / f"file{i}.txt").write_text("x" * 10000)

    # Stow should fail with OSError, not corrupt anything
    result = subprocess.run(
        [sys.executable, PYTHON_STOW, "-t", str(target_dir), "bigpkg"],
        cwd=str(stow_dir),
        capture_output=True
    )

    # Should fail (non-zero exit)
    assert result.returncode != 0
    # Error message should be helpful
    assert b"No space left" in result.stderr or b"ENOSPC" in result.stderr
    # No partial symlinks should remain
    # (depends on implementation - may have partial state)
```

#### 1.2 Maximum Filename Length

**Why:** Common edge case, especially with generated package names.

**Implementation:**
```python
import os

@pytest.mark.extreme
def test_max_filename_length(stow_env):
    """Test stowing files at maximum filename length (255 bytes)."""
    max_name = "a" * 255

    stow_env.create_package("pkg", {
        max_name: "content"
    })

    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
    assert rc == 0

    # Verify link exists
    target_link = os.path.join(stow_env.target_dir, max_name)
    assert os.path.islink(target_link)

@pytest.mark.extreme
def test_filename_too_long(stow_env):
    """Test behavior with filename exceeding limit."""
    # Can't actually create this on most filesystems
    # Instead, test error handling if somehow encountered
    pass
```

#### 1.3 Symlink Loops

**Why:** Symlink loops can cause infinite recursion. Stow must detect them.

**Implementation:**
```python
@pytest.mark.extreme
def test_symlink_loop_in_target(stow_env):
    """Stow should handle symlink loops in target directory."""
    target = stow_env.target_dir

    # Create loop: a -> b -> a
    os.symlink("b", os.path.join(target, "a"))
    os.symlink("a", os.path.join(target, "b"))

    stow_env.create_package("pkg", {"c/file": "content"})

    # Should not hang or crash
    rc, stdout, stderr = stow_env.run_python_stow(
        ["-t", target, "pkg"],
        timeout=10
    )
    # Either succeeds (loop is in unrelated path) or fails gracefully
    # Must not hang

@pytest.mark.extreme
def test_symlink_loop_in_package(stow_env):
    """Symlink loop inside a package should be detected."""
    pkg_dir = os.path.join(stow_env.stow_dir, "badpkg")
    os.makedirs(pkg_dir)

    # Create loop inside package
    os.symlink("b", os.path.join(pkg_dir, "a"))
    os.symlink("a", os.path.join(pkg_dir, "b"))

    rc, stdout, stderr = stow_env.run_python_stow(
        ["-t", stow_env.target_dir, "badpkg"],
        timeout=10
    )
    # Should fail gracefully, not hang
```

#### 1.4 Broken Symlinks

**Why:** Very common in practice. Unstow of partially removed packages, etc.

**Implementation:**
```python
@pytest.mark.extreme
def test_broken_symlink_in_target(stow_env):
    """Stow should handle broken symlinks in target."""
    target = stow_env.target_dir

    # Create broken symlink
    os.symlink("/nonexistent/path", os.path.join(target, "broken"))

    stow_env.create_package("pkg", {"file": "content"})

    rc, stdout, stderr = stow_env.run_python_stow(["-t", target, "pkg"])
    # Should succeed (broken link is unrelated)
    assert rc == 0

@pytest.mark.extreme
def test_stow_package_with_broken_symlink(stow_env):
    """Package containing broken symlink should stow correctly."""
    pkg_dir = os.path.join(stow_env.stow_dir, "pkg")
    os.makedirs(pkg_dir)

    # Package contains a broken symlink (intentional)
    os.symlink("nonexistent", os.path.join(pkg_dir, "broken_link"))

    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])

    # Should stow the broken symlink as-is
    assert rc == 0
    link = os.path.join(stow_env.target_dir, "broken_link")
    assert os.path.islink(link)
    # The symlink target is relative to the package, so read through stow link
```

### Priority 2: Medium Value, Moderate Effort

#### 2.1 Unicode Filenames

**Why:** International users, emoji in paths becoming common.

**Implementation:**
```python
UNICODE_NAMES = [
    "cafe\u0301",           # NFD: cafe + combining acute accent
    "caf\u00e9",            # NFC: e-acute
    "\u4e2d\u6587",         # Chinese
    "\u0645\u0644\u0641",   # Arabic (RTL)
    "\U0001F4C1",           # Folder emoji
    "a\u200bb",             # Zero-width space
    "a\u0000b",             # Embedded null (should reject!)
]

@pytest.mark.extreme
@pytest.mark.parametrize("name", UNICODE_NAMES)
def test_unicode_filenames(stow_env, name):
    """Test stowing files with various unicode names."""
    if "\x00" in name:
        # Null byte should be rejected
        with pytest.raises(Exception):
            stow_env.create_package("pkg", {name: "content"})
        return

    stow_env.create_package("pkg", {name: "content"})
    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
    assert rc == 0

@pytest.mark.extreme
def test_unicode_normalization_mismatch(stow_env):
    """NFC vs NFD normalization edge case."""
    # Create with NFD
    nfd_name = "cafe\u0301"  # e + combining accent
    stow_env.create_package("pkg", {nfd_name: "content"})

    # Stow
    stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])

    # Create target file with NFC
    nfc_name = "caf\u00e9"  # precomposed
    # On some filesystems these are the SAME file, on others different
    # Test should verify consistent behavior either way
```

#### 2.2 Maximum Path Length

**Why:** Deep nesting can exceed PATH_MAX (4096 on Linux).

**Implementation:**
```python
@pytest.mark.extreme
@pytest.mark.slow
def test_maximum_path_length(stow_env):
    """Test paths approaching PATH_MAX (4096 bytes)."""
    # Build deep path: 4096 / 256 = ~16 levels with max-length components
    pkg_dir = os.path.join(stow_env.stow_dir, "pkg")
    current = pkg_dir

    # Create ~15 levels of 250-char directories
    for i in range(15):
        component = f"d{i:02d}_" + "x" * 245
        current = os.path.join(current, component)

    os.makedirs(current)

    # Create file at the end
    filepath = os.path.join(current, "file.txt")
    with open(filepath, "w") as f:
        f.write("content")

    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])

    # Either succeeds or fails gracefully with ENAMETOOLONG
    if rc != 0:
        assert b"name too long" in stderr.lower() or b"ENAMETOOLONG" in stderr
```

#### 2.3 Many Files in Single Directory

**Why:** Some users have thousands of dotfiles.

**Implementation:**
```python
@pytest.mark.extreme
@pytest.mark.slow
def test_100k_files(stow_env):
    """Test stowing 100,000 files."""
    pkg_dir = os.path.join(stow_env.stow_dir, "bigpkg")
    os.makedirs(pkg_dir)

    # Create 100k empty files (fast)
    for i in range(100_000):
        open(os.path.join(pkg_dir, f"file{i:06d}"), "w").close()

    import time
    start = time.time()
    rc, stdout, stderr = stow_env.run_python_stow(
        ["-t", stow_env.target_dir, "bigpkg"],
        timeout=300  # 5 minute timeout
    )
    elapsed = time.time() - start

    assert rc == 0

    # Verify all links created
    links = os.listdir(stow_env.target_dir)
    assert len(links) == 100_000

    # Performance check: should complete in reasonable time
    # (baseline: ~30 seconds on modern hardware)
    print(f"100k files stowed in {elapsed:.1f}s")
```

### Priority 3: Important but Complex

#### 3.1 Race Conditions

**Why:** Concurrent file modifications during stow can cause inconsistencies.

**Implementation:**
```python
import threading
import random

@pytest.mark.extreme
def test_file_deleted_during_planning(stow_env):
    """Test behavior when target file deleted between plan and execute."""
    stow_env.create_package("pkg", {"dir/file": "content"})
    stow_env.create_target_dir("dir")
    stow_env.create_target_file("dir/existing", "old")

    # Race: delete file while stow runs
    deleted = threading.Event()

    def delete_during_stow():
        # Wait a bit for stow to start planning
        import time
        time.sleep(0.1)
        try:
            os.unlink(os.path.join(stow_env.target_dir, "dir/existing"))
            deleted.set()
        except:
            pass

    t = threading.Thread(target=delete_during_stow)
    t.start()

    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
    t.join()

    # Should either succeed or fail gracefully
    # Must not crash or corrupt state

@pytest.mark.extreme
def test_concurrent_stow_operations(stow_env):
    """Two stow processes running simultaneously."""
    stow_env.create_package("pkg1", {"shared/file1": "content1"})
    stow_env.create_package("pkg2", {"shared/file2": "content2"})

    import subprocess

    # Start both stow processes
    p1 = subprocess.Popen(
        [sys.executable, PYTHON_STOW, "-t", stow_env.target_dir, "pkg1"],
        cwd=stow_env.stow_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    p2 = subprocess.Popen(
        [sys.executable, PYTHON_STOW, "-t", stow_env.target_dir, "pkg2"],
        cwd=stow_env.stow_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    p1.wait()
    p2.wait()

    # At least one should succeed, neither should crash
    assert p1.returncode == 0 or p2.returncode == 0

    # Verify no corruption
    target = stow_env.target_dir
    shared = os.path.join(target, "shared")
    assert os.path.isdir(shared) or os.path.islink(shared)
```

#### 3.2 Signal Handling

**Why:** Users press Ctrl+C. Stow should not leave corrupted state.

**Implementation:**
```python
import signal

@pytest.mark.extreme
def test_sigint_during_execution(stow_env):
    """SIGINT during execution should not corrupt state."""
    # Create large package to have time window for signal
    pkg_dir = os.path.join(stow_env.stow_dir, "pkg")
    os.makedirs(pkg_dir)
    for i in range(1000):
        open(os.path.join(pkg_dir, f"file{i}"), "w").close()

    p = subprocess.Popen(
        [sys.executable, PYTHON_STOW, "-t", stow_env.target_dir, "pkg"],
        cwd=stow_env.stow_dir
    )

    # Send SIGINT after brief delay
    import time
    time.sleep(0.05)
    p.send_signal(signal.SIGINT)
    p.wait()

    # May have created some links, may not
    # Key: existing symlinks should be valid
    for name in os.listdir(stow_env.target_dir):
        path = os.path.join(stow_env.target_dir, name)
        if os.path.islink(path):
            # Link should point to valid target
            target = os.readlink(path)
            # Should be relative path into stow dir
            assert target.startswith("../stow/") or target.startswith("stow/")

@pytest.mark.extreme
def test_sigterm_during_planning(stow_env):
    """SIGTERM during planning should make no changes."""
    stow_env.create_package("pkg", {"file": "content"})

    # Get initial state
    initial_state = stow_env.get_filesystem_state()

    p = subprocess.Popen(
        [sys.executable, PYTHON_STOW, "-n", "-t", stow_env.target_dir, "pkg"],
        cwd=stow_env.stow_dir
    )

    # Immediate SIGTERM during planning
    p.send_signal(signal.SIGTERM)
    p.wait()

    # No changes should have been made
    final_state = stow_env.get_filesystem_state()
    assert initial_state == final_state
```

#### 3.3 Permission Errors

**Why:** Users run stow as wrong user, or on permission-restricted directories.

**Implementation:**
```python
@pytest.mark.extreme
def test_readonly_target(stow_env):
    """Stow to read-only target should fail gracefully."""
    stow_env.create_package("pkg", {"file": "content"})

    # Make target read-only
    os.chmod(stow_env.target_dir, 0o555)

    try:
        rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])

        assert rc != 0
        assert b"Permission denied" in stderr or b"EACCES" in stderr
    finally:
        os.chmod(stow_env.target_dir, 0o755)

@pytest.mark.extreme
def test_unreadable_package(stow_env):
    """Stow unreadable package should fail gracefully."""
    pkg_dir = os.path.join(stow_env.stow_dir, "pkg")
    os.makedirs(pkg_dir)
    with open(os.path.join(pkg_dir, "file"), "w") as f:
        f.write("content")

    # Make package unreadable
    os.chmod(pkg_dir, 0o000)

    try:
        rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert rc != 0
    finally:
        os.chmod(pkg_dir, 0o755)
```

### Priority 4: Comprehensive but Lower Urgency

#### 4.1 Special Characters in Paths

```python
SPECIAL_NAMES = [
    "file with spaces",
    "file\twith\ttabs",
    "file'with'quotes",
    'file"with"doublequotes',
    "file\\with\\backslashes",
    "file\nwith\nnewlines",  # Known Perl bug, document difference
    "file*with*stars",
    "file?with?questions",
    "file[with]brackets",
]

@pytest.mark.extreme
@pytest.mark.parametrize("name", SPECIAL_NAMES)
def test_special_chars_in_filename(stow_env, name):
    """Test filenames with shell-special characters."""
    if "\n" in name:
        # Known difference - document in perl-differences.md
        pytest.skip("Newlines in filenames: known Perl bug")

    stow_env.create_package("pkg", {name: "content"})
    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
    assert rc == 0
```

#### 4.2 Symlink to Special Files

```python
@pytest.mark.extreme
def test_symlink_to_devnull(stow_env):
    """Package with symlink to /dev/null."""
    pkg_dir = os.path.join(stow_env.stow_dir, "pkg")
    os.makedirs(pkg_dir)
    os.symlink("/dev/null", os.path.join(pkg_dir, "null"))

    rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])

    # Should stow the symlink
    assert rc == 0
    link = os.path.join(stow_env.target_dir, "null")
    assert os.path.islink(link)
```

#### 4.3 Large Scale

```python
@pytest.mark.extreme
@pytest.mark.slow
def test_1000_packages(stow_env):
    """Test stowing 1000 packages."""
    for i in range(1000):
        stow_env.create_package(f"pkg{i:04d}", {f"file{i}": f"content{i}"})

    pkg_names = [f"pkg{i:04d}" for i in range(1000)]

    rc, stdout, stderr = stow_env.run_python_stow(
        ["-t", stow_env.target_dir] + pkg_names,
        timeout=600
    )

    assert rc == 0
    # All files should be stowed
    assert len(os.listdir(stow_env.target_dir)) == 1000
```

## Timeout Handling

All extreme tests should have timeout protection to prevent hangs:

```python
# In tests/extreme/conftest.py
import pytest

@pytest.fixture(autouse=True)
def extreme_timeout(request):
    """Default timeout for extreme tests."""
    # Get marker timeout or default to 60 seconds
    marker = request.node.get_closest_marker("timeout")
    if marker is None:
        # Add default timeout
        request.node.add_marker(pytest.mark.timeout(60))
```

Also use pytest-timeout plugin:
```bash
pytest tests/test_extreme.py --timeout=60 --timeout-method=signal
```

## CI Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/extreme-tests.yml
name: Extreme Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  # Manual trigger
  workflow_dispatch:

jobs:
  extreme-tests:
    name: Extreme Tests (Docker)
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -f tests/Dockerfile.extreme -t stow-extreme .

      - name: Run extreme tests
        run: |
          docker run --rm \
            --tmpfs /small-disk:size=1M \
            --tmpfs /no-inodes:size=10M,nr_inodes=10 \
            --cap-add SYS_PTRACE \
            --memory 512m \
            --pids-limit 1000 \
            stow-extreme \
            pytest tests/test_extreme.py -v --timeout=120 --junitxml=/tmp/results.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: extreme-test-results
          path: /tmp/results.xml
```

### Running Locally

```bash
# Build container
docker build -f tests/Dockerfile.extreme -t stow-extreme .

# Run all extreme tests
docker run --rm \
    --tmpfs /small-disk:size=1M \
    stow-extreme

# Run specific test
docker run --rm \
    --tmpfs /small-disk:size=1M \
    stow-extreme \
    pytest tests/test_extreme.py::test_disk_full_during_stow -v

# Interactive debugging
docker run -it --rm \
    --tmpfs /small-disk:size=1M \
    stow-extreme \
    /bin/bash
```

## Implementation Order

Recommended implementation sequence:

### Phase 1: Infrastructure (Week 1)
1. Create `tests/Dockerfile.extreme`
2. Add `tests/extreme/conftest.py` with Docker detection, fixtures
3. Add pytest markers to main `conftest.py`
4. Create `.github/workflows/extreme-tests.yml`
5. Add basic smoke test to verify infrastructure works

### Phase 2: High-Value Tests (Week 2)
1. Disk full during stow/unstow
2. Maximum filename length
3. Symlink loops (in target and package)
4. Broken symlinks
5. Basic unicode filenames

### Phase 3: Medium-Value Tests (Week 3)
1. Maximum path length
2. 100k files test
3. Unicode edge cases (NFD/NFC, RTL, zero-width)
4. Special characters in paths
5. Permission denied scenarios

### Phase 4: Complex Tests (Week 4)
1. Race conditions (file deleted during planning)
2. Concurrent stow operations
3. Signal handling (SIGINT, SIGTERM)
4. Read-only filesystem
5. Out of inodes

### Phase 5: Scale and Polish (Week 5)
1. 1000 packages test
2. Restow of large package set
3. Performance benchmarks
4. Oracle comparison for applicable tests
5. Documentation updates

## Oracle Comparison Strategy

For tests where behavior comparison with Perl stow is meaningful:

```python
@pytest.mark.extreme
def test_symlink_loop_oracle(stow_env):
    """Compare Python and Perl handling of symlink loops."""
    # Create identical scenario for both
    def setup():
        os.symlink("b", os.path.join(stow_env.target_dir, "a"))
        os.symlink("a", os.path.join(stow_env.target_dir, "b"))

    stow_env.create_package("pkg", {"file": "content"})

    # Run both with timeout
    setup()
    perl_rc, perl_out, perl_err = stow_env.run_perl_stow(
        ["-t", stow_env.target_dir, "pkg"],
        timeout=10
    )

    stow_env.reset_target()
    setup()
    python_rc, python_out, python_err = stow_env.run_python_stow(
        ["-t", stow_env.target_dir, "pkg"],
        timeout=10
    )

    # Document any differences in behavior
    if perl_rc != python_rc:
        # Add to perl-differences.md if intentional
        pass
```

## Success Criteria

The extreme test suite is complete when:

1. All Priority 1 and 2 tests pass consistently
2. CI runs extreme tests on every PR
3. No test takes more than 2 minutes
4. Docker container builds in under 5 minutes
5. Local developers can run `./run-extreme-tests.sh` easily
6. Documentation covers all known edge case behaviors
7. Any Python/Perl differences are documented

## Open Questions

1. **Filesystem-specific tests:** Should we test ext4 vs btrfs vs ZFS behavior differences? (Probably out of scope)

2. **macOS support:** Should extreme tests run on macOS (case-insensitive HFS+)? Requires different container strategy.

3. **Windows:** Out of scope for now, but worth noting that symlink behavior differs significantly.

4. **Fuzz testing:** Should we add AFL or libFuzzer-based testing? Could catch edge cases we haven't thought of.
