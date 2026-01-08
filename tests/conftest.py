"""
Pytest configuration for oracle-based stow tests.

These tests compare the Python stow implementation against the Perl stow
as an oracle. Both must produce identical:
- Return codes
- stdout output
- stderr output
- Filesystem effects
"""

from __future__ import print_function

import errno
import os
import shutil
import subprocess
import sys

import pytest


def which(cmd):
    """Python 2 compatible shutil.which."""
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full_path = os.path.join(path, cmd)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None


def makedirs_exist_ok(path):
    """Python 2 compatible os.makedirs with exist_ok=True."""
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


# Paths
EXACT_PYSTOW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_STOW = os.path.join(EXACT_PYSTOW_DIR, "bin", "stow")
PYTHON_CHKSTOW = os.path.join(EXACT_PYSTOW_DIR, "bin", "chkstow")

# Find Perl stow - look in tests/gnu_stow_for_testing/
# (downloaded via scripts/get_gnu_stow_for_testing_identical_behavior.sh)
# Pinned to version 2.4.1 used for the Python port
PERL_STOW_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gnu_stow_for_testing"
)
PERL_STOW = os.path.join(PERL_STOW_DIR, "bin", "stow")
PERL_CHKSTOW = os.path.join(PERL_STOW_DIR, "bin", "chkstow")
PERL_LIB = os.path.join(PERL_STOW_DIR, "lib")

if not os.path.exists(PERL_STOW):
    # Fallback to system stow
    PERL_STOW = which("stow")
    PERL_CHKSTOW = which("chkstow")
    PERL_LIB = None


class StowTestEnv:
    """Test environment for running stow commands."""

    def __init__(self, tmpdir):
        self.tmpdir = str(tmpdir)
        self.stow_dir = os.path.join(self.tmpdir, "stow")
        self.target_dir = os.path.join(self.tmpdir, "target")
        os.makedirs(self.stow_dir)
        os.makedirs(self.target_dir)
        # Isolate from user's ~/.stow-global-ignore
        os.environ["HOME"] = self.tmpdir

    def create_package(self, name, files):
        """
        Create a package in the stow directory.

        files: dict mapping relative paths to content (or None for directories)
        """
        pkg_dir = os.path.join(self.stow_dir, name)
        makedirs_exist_ok(pkg_dir)

        for path, content in files.items():
            full_path = os.path.join(pkg_dir, path)
            parent = os.path.dirname(full_path)
            if parent:
                makedirs_exist_ok(parent)

            if content is None:
                # Directory
                makedirs_exist_ok(full_path)
            else:
                # File
                with open(full_path, "w") as f:
                    f.write(content)

    def create_target_file(self, path, content):
        """Create a file in the target directory."""
        full_path = os.path.join(self.target_dir, path)
        parent = os.path.dirname(full_path)
        if parent:
            makedirs_exist_ok(parent)
        with open(full_path, "w") as f:
            f.write(content)

    def create_target_dir(self, path):
        """Create a directory in the target directory."""
        full_path = os.path.join(self.target_dir, path)
        makedirs_exist_ok(full_path)

    def create_target_link(self, path, dest):
        """Create a symlink in the target directory."""
        full_path = os.path.join(self.target_dir, path)
        parent = os.path.dirname(full_path)
        if parent:
            makedirs_exist_ok(parent)
        os.symlink(dest, full_path)

    def get_filesystem_state(self):
        """
        Get a snapshot of the target directory state.

        Returns a dict mapping paths to tuples:
        - ('dir', mode, uid, gid) for directories
        - ('file', content, mode, uid, gid) for files
        - ('link', target) for symlinks (perms not checked, usually 0o777)
        """
        state = {}
        for root, dirs, files in os.walk(self.target_dir, followlinks=False):
            rel_root = os.path.relpath(root, self.target_dir)
            if rel_root == ".":
                rel_root = ""

            for d in sorted(dirs):
                path = os.path.join(rel_root, d) if rel_root else d
                full_path = os.path.join(root, d)
                st = os.lstat(full_path)
                if os.path.islink(full_path):
                    state[path] = ("link", os.readlink(full_path))
                else:
                    state[path] = ("dir", st.st_mode, st.st_uid, st.st_gid)

            for f in sorted(files):
                path = os.path.join(rel_root, f) if rel_root else f
                full_path = os.path.join(root, f)
                st = os.lstat(full_path)
                if os.path.islink(full_path):
                    state[path] = ("link", os.readlink(full_path))
                else:
                    with open(full_path, "r") as fh:
                        state[path] = ("file", fh.read(), st.st_mode, st.st_uid, st.st_gid)

        return state

    def run_perl_stow(self, args, env=None):
        """Run Perl stow and return (returncode, stdout, stderr)."""
        if PERL_STOW is None:
            pytest.skip("Perl stow not found")

        cmd = [PERL_STOW] + list(args)

        run_env = os.environ.copy()
        run_env["STOW_DIR"] = self.stow_dir
        if PERL_LIB:
            run_env["PERL5LIB"] = PERL_LIB
        if env:
            run_env.update(env)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.stow_dir,
            env=run_env,
        )
        stdout, stderr = proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        return proc.returncode, stdout_str, stderr_str

    def run_python_stow(self, args, env=None):
        """Run Python stow and return (returncode, stdout, stderr)."""
        cmd = [sys.executable, PYTHON_STOW] + list(args)

        run_env = os.environ.copy()
        run_env["STOW_DIR"] = self.stow_dir
        if env:
            run_env.update(env)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.stow_dir,
            env=run_env,
        )
        stdout, stderr = proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        return proc.returncode, stdout_str, stderr_str

    def run_perl_chkstow(self, args, env=None):
        """Run Perl chkstow and return (returncode, stdout, stderr)."""
        if PERL_CHKSTOW is None:
            pytest.skip("Perl chkstow not found")

        cmd = ["perl", PERL_CHKSTOW] + list(args)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.target_dir,
            env=run_env,
        )
        stdout, stderr = proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        return proc.returncode, stdout_str, stderr_str

    def run_python_chkstow(self, args, env=None):
        """Run Python chkstow and return (returncode, stdout, stderr)."""
        cmd = [sys.executable, PYTHON_CHKSTOW] + list(args)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.target_dir,
            env=run_env,
        )
        stdout, stderr = proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        return proc.returncode, stdout_str, stderr_str

    def reset_target(self):
        """Reset target directory to empty state."""
        shutil.rmtree(self.target_dir)
        os.makedirs(self.target_dir)


@pytest.fixture
def stow_env(tmp_path):
    """Create a fresh stow test environment."""
    return StowTestEnv(tmp_path)


def normalize_stow_output(text):
    """
    Normalize Stow-Python output to match GNU Stow for oracle comparison.

    This allows the Python reimplementation to have its own branding while
    still passing oracle tests that compare behavior.
    """
    # Normalize version/help header
    text = text.replace("(Stow-Python)", "(GNU Stow)")

    # Remove the extra description lines added in Stow-Python
    text = text.replace(
        "\nStow-Python is a Python reimplementation of GNU Stow.\n"
        "Original GNU Stow by Bob Glickstein, Guillaume Morin, "
        "Kahlil Hodgson, Adam Spiers, and others.\n",
        "",
    )

    # Normalize footer URLs
    text = text.replace(
        "GNU Stow home page: <http://www.gnu.org/software/stow/>\n"
        "Report deviations from GNU Stow: "
        "<https://github.com/isarandi/stow-python/issues>",
        "Report bugs to: bug-stow@gnu.org\n"
        "Stow home page: <http://www.gnu.org/software/stow/>\n"
        "General help using GNU software: <http://www.gnu.org/gethelp/>",
    )

    return text


def normalize_newline_warnings(text):
    """
    Filter out Perl/Python warnings about newlines in filenames.

    These warnings come from stat/lstat internals, not stow logic,
    and trigger in different code paths between Perl and Python.
    """
    import re

    # Filter warnings about newlines in filenames
    # e.g., "Unsuccessful lstat on filename containing newline at ... line N."
    text = re.sub(
        r"Unsuccessful (?:l?stat) on filename containing newline at [^\n]+ line \d+\.\n",
        "",
        text,
    )

    return text


def assert_stow_match(stow_env, args, setup_func=None, env=None, ignore_stderr_whitespace=False):
    """
    Run both Perl and Python stow with the same args and assert they match.

    Compares:
    - Return code
    - stdout
    - stderr
    - Filesystem state after execution

    Args:
        stow_env: StowTestEnv instance
        args: command line arguments
        setup_func: optional callable to set up target state after reset
        env: optional environment variables
        ignore_stderr_whitespace: if True, ignore whitespace differences in stderr
    """
    # Run Perl stow
    stow_env.reset_target()
    if setup_func:
        setup_func()
    perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_stow(args, env)
    perl_state = stow_env.get_filesystem_state()

    # Reset and run Python stow
    stow_env.reset_target()
    if setup_func:
        setup_func()
    python_rc, python_stdout, python_stderr = stow_env.run_python_stow(args, env)
    python_state = stow_env.get_filesystem_state()

    # Normalize Python output to match Perl branding for comparison
    python_stdout = normalize_stow_output(python_stdout)
    python_stderr = normalize_stow_output(python_stderr)

    # Filter out newline warnings from both (these trigger inconsistently)
    perl_stderr = normalize_newline_warnings(perl_stderr)
    python_stderr = normalize_newline_warnings(python_stderr)

    # Compare return codes
    assert perl_rc == python_rc, (
        "Return code mismatch: Perl=%d, Python=%d\nPerl stderr: %s\nPython stderr: %s"
        % (perl_rc, python_rc, perl_stderr, python_stderr)
    )

    # Compare stdout
    assert perl_stdout == python_stdout, "stdout mismatch:\nPerl: %r\nPython: %r" % (
        perl_stdout,
        python_stdout,
    )

    # Compare stderr (optionally ignoring whitespace differences)
    if ignore_stderr_whitespace:
        perl_stderr_normalized = " ".join(perl_stderr.split())
        python_stderr_normalized = " ".join(python_stderr.split())
        assert perl_stderr_normalized == python_stderr_normalized, (
            "stderr mismatch:\nPerl: %r\nPython: %r" % (perl_stderr, python_stderr)
        )
    else:
        assert perl_stderr == python_stderr, (
            "stderr mismatch:\nPerl: %r\nPython: %r" % (perl_stderr, python_stderr)
        )

    # Compare filesystem state
    assert perl_state == python_state, (
        "Filesystem state mismatch:\nPerl: %s\nPython: %s" % (perl_state, python_state)
    )

    return perl_rc, perl_stdout, perl_stderr, perl_state


def assert_chkstow_match(stow_env, args, setup_func=None, env=None):
    """
    Run both Perl and Python chkstow with the same args and assert they match.

    Compares:
    - Return code
    - stdout
    - stderr

    Args:
        stow_env: StowTestEnv instance
        args: command line arguments
        setup_func: optional callable to set up target state before each run
        env: optional environment variables
    """
    if setup_func:
        setup_func()
    perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_chkstow(args, env)

    if setup_func:
        setup_func()
    python_rc, python_stdout, python_stderr = stow_env.run_python_chkstow(args, env)

    # Compare return codes
    assert perl_rc == python_rc, (
        "Return code mismatch: Perl=%d, Python=%d\nPerl stderr: %s\nPython stderr: %s"
        % (perl_rc, python_rc, perl_stderr, python_stderr)
    )

    # Compare stdout
    assert perl_stdout == python_stdout, "stdout mismatch:\nPerl: %r\nPython: %r" % (
        perl_stdout,
        python_stdout,
    )

    # Compare stderr
    assert perl_stderr == python_stderr, "stderr mismatch:\nPerl: %r\nPython: %r" % (
        perl_stderr,
        python_stderr,
    )

    return perl_rc, perl_stdout, perl_stderr


def assert_chkstow_match_with_fs_ops(stow_env, args, setup_func=None, env=None):
    """
    Run both Perl and Python chkstow, comparing outputs AND filesystem operations.

    Captures strace output for both and compares read operations (stat, lstat, etc.).
    """
    import tempfile

    # Check if strace is available
    if shutil.which('strace') is None:
        return assert_chkstow_match(stow_env, args, setup_func, env)

    tmpdir = stow_env.tmpdir

    # Run Perl chkstow with strace
    if setup_func:
        setup_func()

    perl_cmd = ["perl", PERL_CHKSTOW] + list(args)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    with tempfile.NamedTemporaryFile(mode='w', suffix='_perl_strace.txt', delete=False) as f:
        perl_strace_file = f.name

    perl_rc, perl_stdout, perl_stderr = run_with_strace(
        perl_cmd, stow_env.target_dir, run_env, perl_strace_file
    )
    perl_ops = parse_strace_output(perl_strace_file, tmpdir=tmpdir)

    # Run Python chkstow with strace
    if setup_func:
        setup_func()

    python_cmd = [sys.executable, PYTHON_CHKSTOW] + list(args)
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    with tempfile.NamedTemporaryFile(mode='w', suffix='_python_strace.txt', delete=False) as f:
        python_strace_file = f.name

    python_rc, python_stdout, python_stderr = run_with_strace(
        python_cmd, stow_env.target_dir, run_env, python_strace_file
    )
    python_ops = parse_strace_output(python_strace_file, tmpdir=tmpdir)

    # Clean up strace files
    try:
        os.unlink(perl_strace_file)
        os.unlink(python_strace_file)
    except Exception:
        pass

    # Compare return codes
    assert perl_rc == python_rc, (
        f"Return code mismatch: Perl={perl_rc}, Python={python_rc}\n"
        f"Perl stderr: {perl_stderr}\nPython stderr: {python_stderr}"
    )

    # Compare stdout
    assert perl_stdout == python_stdout, (
        f"stdout mismatch:\nPerl: {perl_stdout!r}\nPython: {python_stdout!r}"
    )

    # Compare stderr
    assert perl_stderr == python_stderr, (
        f"stderr mismatch:\nPerl: {perl_stderr!r}\nPython: {python_stderr!r}"
    )

    # Compare filesystem operations
    syscall_diffs = find_syscall_diffs(perl_ops, python_ops)
    assert not syscall_diffs, (
        f"Filesystem operation differences!\n"
        f"Perl ({len(perl_ops)} ops) vs Python ({len(python_ops)} ops):\n"
        f"{syscall_diffs}\n\n"
        f"Full diff:\n{diff_fs_ops(perl_ops, python_ops)}"
    )

    return perl_rc, perl_stdout, perl_stderr, perl_ops, python_ops


# ============================================================================
# Fixtures for transpiled unit tests (from stow-2.4.1/t/*.t)
# ============================================================================


@pytest.fixture
def stow_test_env(tmp_path):
    """
    Provide isolated test environment for transpiled unit tests.

    Creates test directories in pytest's tmp_path and changes to target dir.
    Restores original cwd after test.
    """
    from testutil import init_test_dirs, cleanup_test_dirs, cd

    original_cwd = os.getcwd()

    # Initialize test dirs in the isolated tmp_path
    abs_test_dir = init_test_dirs(tmp_path)

    # Change to target directory (most tests expect this)
    target_dir = os.path.join(abs_test_dir, "target")
    cd(target_dir)

    yield abs_test_dir

    # Restore original cwd
    try:
        os.chdir(original_cwd)
    except OSError:
        pass
    cleanup_test_dirs()


# ============================================================================
# Shared assertion helpers for _both oracle tests
# ============================================================================


def check_link(env, path, expected_target):
    """Check that path is a symlink pointing to expected_target."""
    full_path = os.path.join(env.target_dir, path)
    assert os.path.islink(full_path), f"{path} should be a symlink"
    actual = os.readlink(full_path)
    assert actual == expected_target, f"{path}: expected {expected_target}, got {actual}"


def check_dir(env, path):
    """Check that path is a real directory (not a symlink)."""
    full_path = os.path.join(env.target_dir, path)
    assert os.path.isdir(full_path), f"{path} should be a directory"
    assert not os.path.islink(full_path), f"{path} should not be a symlink"


def check_not_exists(env, path):
    """Check that path does not exist (including broken symlinks)."""
    full_path = os.path.join(env.target_dir, path)
    assert not os.path.exists(full_path) and not os.path.islink(full_path), (
        f"{path} should not exist"
    )


def check_file(env, path):
    """Check that path is a regular file (not a symlink)."""
    full_path = os.path.join(env.target_dir, path)
    assert os.path.isfile(full_path), f"{path} should be a file"
    assert not os.path.islink(full_path), f"{path} should not be a symlink"


def run_perl_and_check(env, args, check_func):
    """Run Perl stow and verify assertions."""
    env.run_perl_stow(args)
    check_func(env)
    return env.get_filesystem_state()


def run_python_and_check(env, args, check_func):
    """Run Python stow and verify assertions."""
    env.run_python_stow(args)
    check_func(env)
    return env.get_filesystem_state()


def run_both_tests(env, args, setup_func, check_func=None, check_on_simulate=False,
                   compare_fs_ops=False):
    """
    Run comprehensive oracle test with both execute and simulate modes.

    1. Runs behavioral assertions (if check_func provided) on the appropriate mode
    2. Asserts Perl vs Python match for BOTH modes (-n and without -n)
    3. Optionally compares filesystem operations via strace

    Args:
        env: StowTestEnv instance
        args: base arguments (without -n flag)
        setup_func: callable to set up test state (called before each run)
        check_func: optional callable for behavioral assertions
        check_on_simulate: if True, run check_func on simulate mode; else on execute
        compare_fs_ops: if True, capture and compare filesystem operations
    """
    # Determine args for both modes
    args_execute = list(args)
    args_simulate = ["-n"] + list(args)

    # Run behavioral checks on appropriate mode
    if check_func:
        check_args = args_simulate if check_on_simulate else args_execute

        env.reset_target()
        setup_func()
        run_perl_and_check(env, check_args, check_func)

        env.reset_target()
        setup_func()
        run_python_and_check(env, check_args, check_func)

    # Assert Perl vs Python match for BOTH modes
    # Pass setup_func to assert functions - they handle reset+setup internally
    assert_stow_match(env, args_simulate, setup_func)

    if compare_fs_ops:
        assert_stow_match_with_fs_ops(env, args_execute, setup_func)
    else:
        assert_stow_match(env, args_execute, setup_func)


def is_stow_relevant_path(path):
    """Check if path is relevant to stow operations (not interpreter/system loading)."""
    # Filter out Python interpreter paths (site-packages, pycache, etc.)
    if '.local/lib/python' in path or '__pycache__' in path:
        return False
    # Relative paths are stow operations (../stow/pkg, bin1, etc.)
    if not path.startswith('/'):
        return True
    # Paths under /tmp are test directories
    if path.startswith('/tmp'):
        return True
    # User's stow config files
    if path.endswith(('.stowrc', '.stow-global-ignore')):
        return True
    return False


# Syscalls that are functionally equivalent but may differ between Perl and Python
# due to different glibc wrapper functions used at compile time.
# See docs/perl-differences.md for details.

# *at syscalls with AT_FDCWD are equivalent to their non-at counterparts
# e.g., newfstatat(AT_FDCWD, path, ..., 0) == stat(path)
# BUT: newfstatat with AT_SYMLINK_NOFOLLOW flag is lstat, not stat!
AT_FDCWD_SYSCALLS = {
    'openat': 'open',
    'linkat': 'link',
    'unlinkat': 'unlink',
    'mkdirat': 'mkdir',
    'readlinkat': 'readlink',
    'symlinkat': 'symlink',
    'renameat': 'rename',
    'faccessat': 'access',
    'faccessat2': 'access',
}

# fstatat/newfstatat can be either stat or lstat depending on AT_SYMLINK_NOFOLLOW flag
FSTATAT_SYSCALLS = {'newfstatat', 'fstatat', 'fstatat64'}

# These are just renamed versions (no AT_FDCWD check needed)
RENAMED_SYSCALLS = {
    'stat64': 'stat',
    'lstat64': 'lstat',
    'fstat64': 'fstat',
}


def _normalize_syscall(syscall, line):
    """
    Normalize syscall names to canonical form for comparison.

    For *at syscalls, only normalize if AT_FDCWD is the first argument.
    This ensures we don't incorrectly equate newfstatat(3, path) with stat(path).

    For fstatat/newfstatat, also check AT_SYMLINK_NOFOLLOW flag:
    - With AT_SYMLINK_NOFOLLOW: equivalent to lstat
    - Without: equivalent to stat
    """
    # Simple renames (no argument check needed)
    if syscall in RENAMED_SYSCALLS:
        return RENAMED_SYSCALLS[syscall]

    # fstatat/newfstatat - check AT_FDCWD and AT_SYMLINK_NOFOLLOW
    if syscall in FSTATAT_SYSCALLS:
        if 'AT_FDCWD' in line:
            # AT_SYMLINK_NOFOLLOW means lstat (don't follow symlinks)
            if 'AT_SYMLINK_NOFOLLOW' in line:
                return 'lstat'
            else:
                return 'stat'
        return syscall

    # Other *at syscalls - only normalize if AT_FDCWD
    if syscall in AT_FDCWD_SYSCALLS:
        # Check if first argument is AT_FDCWD
        # Line looks like: "openat(AT_FDCWD, "/path", ..."
        if 'AT_FDCWD' in line:
            return AT_FDCWD_SYSCALLS[syscall]

    return syscall


def parse_strace_output(strace_file, tmpdir=None, filter_relevant=True):
    """
    Parse strace output to extract all filesystem operations with full details.

    Returns list of dicts with keys:
        - syscall: normalized syscall name
        - paths: list of paths involved
        - result: return value (int or error string)
        - raw: original line (for debugging)

    Args:
        strace_file: path to strace output file
        tmpdir: if provided, make paths relative to this for comparison
        filter_relevant: if True, keep only stow-relevant paths
    """
    two_path_syscalls = {'symlink', 'rename', 'link', 'linkat'}
    ops = []

    try:
        with open(strace_file, 'r') as f:
            for line in f:
                # Skip lines without syscall pattern
                paren_pos = line.find('(')
                if paren_pos == -1:
                    continue

                # Extract syscall name
                before_paren = line[:paren_pos].strip()
                if ' ' in before_paren:
                    syscall = before_paren.split()[-1]
                else:
                    syscall = before_paren

                # Normalize equivalent syscalls (see docs/perl-differences.md)
                syscall = _normalize_syscall(syscall, line)

                # Extract all quoted strings (paths)
                paths = []
                pos = 0
                while True:
                    quote_start = line.find('"', pos)
                    if quote_start == -1:
                        break
                    quote_end = line.find('"', quote_start + 1)
                    if quote_end == -1:
                        break
                    path = line[quote_start + 1:quote_end]
                    paths.append(path)
                    pos = quote_end + 1

                if not paths:
                    continue

                # Filter by path relevance (check first path only - that's the operation target)
                if filter_relevant:
                    if not is_stow_relevant_path(paths[0]):
                        continue

                # Make paths relative to tmpdir for comparison
                if tmpdir:
                    paths = [
                        p[len(tmpdir):].lstrip('/') if p.startswith(tmpdir) else p
                        for p in paths
                    ]

                # Extract return value
                eq_pos = line.rfind(' = ')
                result = None
                if eq_pos != -1:
                    result_str = line[eq_pos + 3:].strip()
                    # Parse result: could be int, -1 ERRNO, or other
                    if result_str.startswith('-1'):
                        # Error case: "-1 ENOENT (No such file or directory)"
                        parts = result_str.split()
                        if len(parts) >= 2:
                            result = parts[1]  # e.g., "ENOENT"
                        else:
                            result = -1
                    else:
                        # Success: try to parse as int
                        try:
                            result = int(result_str.split()[0])
                        except (ValueError, IndexError):
                            result = result_str

                ops.append({
                    'syscall': syscall,
                    'paths': tuple(paths),
                    'result': result,
                })

    except Exception:
        pass

    return ops


def format_fs_ops(ops, limit=50):
    """Format filesystem operations for readable diff output."""
    lines = []
    for i, op in enumerate(ops[:limit]):
        paths_str = ', '.join(op['paths'])
        result_str = f" -> {op['result']}" if op['result'] is not None else ""
        lines.append(f"  {i+1:3d}. {op['syscall']}({paths_str}){result_str}")
    if len(ops) > limit:
        lines.append(f"  ... and {len(ops) - limit} more")
    return '\n'.join(lines)


def find_syscall_diffs(perl_ops, python_ops):
    """Find syscall differences between Perl and Python.

    Returns a string describing differences, or empty string if all match.
    """
    if len(perl_ops) != len(python_ops):
        return f"Operation count mismatch: Perl {len(perl_ops)} vs Python {len(python_ops)}"

    diffs = []
    for i, (perl_op, python_op) in enumerate(zip(perl_ops, python_ops)):
        if perl_op != python_op:
            diffs.append(
                f"  {i+1}. Perl: {perl_op['syscall']}({', '.join(perl_op['paths'])}) -> {perl_op['result']}\n"
                f"      Python: {python_op['syscall']}({', '.join(python_op['paths'])}) -> {python_op['result']}"
            )

    return '\n'.join(diffs)


def diff_fs_ops(perl_ops, python_ops):
    """Generate a readable diff of filesystem operations."""
    lines = []
    max_len = max(len(perl_ops), len(python_ops))

    for i in range(min(max_len, 80)):
        perl_op = perl_ops[i] if i < len(perl_ops) else None
        python_op = python_ops[i] if i < len(python_ops) else None

        if perl_op == python_op:
            p = perl_op
            lines.append(f"  {i+1:3d}. {p['syscall']}({', '.join(p['paths'])})")
        else:
            if perl_op:
                p = perl_op
                lines.append(f"P {i+1:3d}. {p['syscall']}({', '.join(p['paths'])}) -> {p['result']}")
            if python_op:
                p = python_op
                lines.append(f"Y {i+1:3d}. {p['syscall']}({', '.join(p['paths'])}) -> {p['result']}")

    if max_len > 30:
        lines.append(f"  ... ({max_len - 30} more ops)")

    return '\n'.join(lines)


def run_with_strace(cmd, cwd, env, strace_output_file):
    """Run a command under strace, capturing filesystem operations."""
    strace_cmd = [
        'strace', '-f', '-o', strace_output_file,
        # Capture all syscalls that take a filename argument.
        # This is strace's built-in %file class - comprehensive and excludes
        # syscalls like read/write that show buffer contents instead of paths.
        '-e', 'trace=%file'
    ] + cmd

    proc = subprocess.Popen(
        strace_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    stdout, stderr = proc.communicate()
    return proc.returncode, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')


def assert_stow_match_with_fs_ops(stow_env, args, setup_func=None, env=None):
    """
    Run both Perl and Python stow, comparing outputs AND filesystem operations.

    Captures strace output for both and compares STRICTLY:
    - Return code, stdout, stderr, filesystem state
    - Filesystem operations: syscall names, paths, results, ORDER

    Any difference fails the test. Approved differences must be documented
    in docs/perl-differences.md.
    """
    import tempfile

    # Check if strace is available
    if shutil.which('strace') is None:
        # Fall back to regular comparison if strace not available
        return assert_stow_match(stow_env, args, env)

    tmpdir = stow_env.tmpdir

    # Run Perl stow with strace
    stow_env.reset_target()
    if setup_func:
        setup_func()

    perl_cmd = [PERL_STOW] + list(args)
    run_env = os.environ.copy()
    run_env["STOW_DIR"] = stow_env.stow_dir
    if PERL_LIB:
        run_env["PERL5LIB"] = PERL_LIB
    if env:
        run_env.update(env)

    with tempfile.NamedTemporaryFile(mode='w', suffix='_perl_strace.txt', delete=False) as f:
        perl_strace_file = f.name

    perl_rc, perl_stdout, perl_stderr = run_with_strace(
        perl_cmd, stow_env.stow_dir, run_env, perl_strace_file
    )
    perl_state = stow_env.get_filesystem_state()
    perl_ops = parse_strace_output(perl_strace_file, tmpdir=tmpdir)

    # Run Python stow with strace
    stow_env.reset_target()
    if setup_func:
        setup_func()

    python_cmd = [sys.executable, PYTHON_STOW] + list(args)
    run_env = os.environ.copy()
    run_env["STOW_DIR"] = stow_env.stow_dir
    if env:
        run_env.update(env)

    with tempfile.NamedTemporaryFile(mode='w', suffix='_python_strace.txt', delete=False) as f:
        python_strace_file = f.name

    python_rc, python_stdout, python_stderr = run_with_strace(
        python_cmd, stow_env.stow_dir, run_env, python_strace_file
    )
    python_state = stow_env.get_filesystem_state()
    python_ops = parse_strace_output(python_strace_file, tmpdir=tmpdir)

    # Clean up strace files
    try:
        os.unlink(perl_strace_file)
        os.unlink(python_strace_file)
    except Exception:
        pass

    # Normalize outputs
    python_stdout = normalize_stow_output(python_stdout)
    python_stderr = normalize_stow_output(python_stderr)
    perl_stderr = normalize_newline_warnings(perl_stderr)
    python_stderr = normalize_newline_warnings(python_stderr)

    # Compare return codes
    assert perl_rc == python_rc, (
        f"Return code mismatch: Perl={perl_rc}, Python={python_rc}\n"
        f"Perl stderr: {perl_stderr}\nPython stderr: {python_stderr}"
    )

    # Compare stdout
    assert perl_stdout == python_stdout, (
        f"stdout mismatch:\nPerl: {perl_stdout!r}\nPython: {python_stdout!r}"
    )

    # Compare stderr
    assert perl_stderr == python_stderr, (
        f"stderr mismatch:\nPerl: {perl_stderr!r}\nPython: {python_stderr!r}"
    )

    # Compare filesystem state
    assert perl_state == python_state, (
        f"Filesystem state mismatch:\nPerl: {perl_state}\nPython: {python_state}"
    )

    # Compare filesystem operations
    syscall_diffs = find_syscall_diffs(perl_ops, python_ops)
    assert not syscall_diffs, (
        f"Filesystem operation differences!\n"
        f"Perl ({len(perl_ops)} ops) vs Python ({len(python_ops)} ops):\n"
        f"{syscall_diffs}\n\n"
        f"Full diff:\n{diff_fs_ops(perl_ops, python_ops)}"
    )

    return perl_rc, perl_stdout, perl_stderr, perl_state, perl_ops, python_ops
