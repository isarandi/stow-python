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

        Returns a dict mapping paths to:
        - 'dir' for directories
        - 'file:<content>' for files
        - 'link:<dest>' for symlinks
        """
        state = {}
        for root, dirs, files in os.walk(self.target_dir, followlinks=False):
            rel_root = os.path.relpath(root, self.target_dir)
            if rel_root == ".":
                rel_root = ""

            for d in sorted(dirs):
                path = os.path.join(rel_root, d) if rel_root else d
                full_path = os.path.join(root, d)
                if os.path.islink(full_path):
                    state[path] = "link:" + os.readlink(full_path)
                else:
                    state[path] = "dir"

            for f in sorted(files):
                path = os.path.join(rel_root, f) if rel_root else f
                full_path = os.path.join(root, f)
                if os.path.islink(full_path):
                    state[path] = "link:" + os.readlink(full_path)
                else:
                    with open(full_path, "r") as fh:
                        state[path] = "file:" + fh.read()

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


def assert_stow_match(stow_env, args, env=None, ignore_stderr_whitespace=False):
    """
    Run both Perl and Python stow with the same args and assert they match.

    Compares:
    - Return code
    - stdout
    - stderr
    - Filesystem state after execution
    """
    # Run Perl stow
    stow_env.reset_target()
    # Restore initial state would be needed for complex tests
    perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_stow(args, env)
    perl_state = stow_env.get_filesystem_state()

    # Reset and run Python stow
    stow_env.reset_target()
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


def assert_chkstow_match(stow_env, args, env=None):
    """
    Run both Perl and Python chkstow with the same args and assert they match.

    Compares:
    - Return code
    - stdout
    - stderr
    """
    perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_chkstow(args, env)
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
