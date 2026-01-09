#!/usr/bin/env python
#
# This file is part of GNU Stow.
#
# GNU Stow is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GNU Stow is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.

"""
Black-box oracle tests for chkstow - comparing Perl and Python implementations.

Perl t/chkstow.t tests (7 scenarios):
1. -b: Skip directories containing .stow (stderr check)
2. -l: List packages → stdout_like "emacs\nperl\nstow\n"
3. -b: No bogus links → stdout empty
4. -a: No aliens → stdout empty
5. -a with alien file → stdout_like "Unstowed file: ./bin/alien"
6. -b with bogus link → stdout_like "Bogus link: ./bin/link"
7. Default target is /usr/local

These tests verify Perl vs Python match and check expected output patterns.
Syscall comparison tests verify identical File::Find traversal behavior.
"""

import os
import pytest
import re

from conftest import assert_chkstow_match, assert_chkstow_match_with_fs_ops


@pytest.fixture
def chkstow_env(stow_env):
    """Set up test environment for chkstow tests.

    Matches Perl t/chkstow.t setup:
    - stow/.stow marker
    - stow/perl package with bin/perl, bin/a2p, info/perl, lib/perl, man/man1/perl.1
    - stow/emacs package with bin/emacs, bin/etags, info/emacs, libexec/emacs, man/man1/emacs.1
    - Target with stowed symlinks
    """
    # Create stow directory marker
    stow_env.create_target_dir("stow")
    stow_marker = os.path.join(stow_env.target_dir, "stow", ".stow")
    with open(stow_marker, "w") as f:
        pass

    # Create perl package
    for path in [
        "stow/perl/bin",
        "stow/perl/info",
        "stow/perl/lib/perl",
        "stow/perl/man/man1",
    ]:
        stow_env.create_target_dir(path)
    for path, content in [
        ("stow/perl/bin/perl", "perl"),
        ("stow/perl/bin/a2p", "a2p"),
        ("stow/perl/info/perl", "info"),
        ("stow/perl/man/man1/perl.1", "man"),
    ]:
        stow_env.create_target_file(path, content)

    # Create emacs package
    for path in [
        "stow/emacs/bin",
        "stow/emacs/info",
        "stow/emacs/libexec/emacs",
        "stow/emacs/man/man1",
    ]:
        stow_env.create_target_dir(path)
    for path, content in [
        ("stow/emacs/bin/emacs", "emacs"),
        ("stow/emacs/bin/etags", "etags"),
        ("stow/emacs/info/emacs", "info"),
        ("stow/emacs/man/man1/emacs.1", "man"),
    ]:
        stow_env.create_target_file(path, content)

    # Create stowed symlinks
    stow_env.create_target_dir("bin")
    stow_env.create_target_link("bin/a2p", "../stow/perl/bin/a2p")
    stow_env.create_target_link("bin/emacs", "../stow/emacs/bin/emacs")
    stow_env.create_target_link("bin/etags", "../stow/emacs/bin/etags")
    stow_env.create_target_link("bin/perl", "../stow/perl/bin/perl")

    stow_env.create_target_dir("info")
    stow_env.create_target_link("info/emacs", "../stow/emacs/info/emacs")
    stow_env.create_target_link("info/perl", "../stow/perl/info/perl")

    stow_env.create_target_link("lib", "stow/perl/lib")
    stow_env.create_target_link("libexec", "stow/emacs/libexec")

    stow_env.create_target_dir("man")
    stow_env.create_target_dir("man/man1")
    stow_env.create_target_link("man/man1/emacs", "../../stow/emacs/man/man1/emacs.1")
    stow_env.create_target_link("man/man1/perl", "../../stow/perl/man/man1/perl.1")

    return stow_env


class TestChkstowBoth:
    """Oracle tests comparing Perl and Python chkstow.

    Strace comparison not used for chkstow - it's read-only and directory
    traversal order can legitimately differ. Output matching is sufficient.
    """

    def test_list_packages(self, chkstow_env):
        """List packages mode.

        Perl: stdout_like qr{emacs\nperl\nstow\n}
        """
        assert_chkstow_match(chkstow_env, ["-l", "-t", "."])
        # Additional check: verify expected packages listed
        _, stdout, _ = chkstow_env.run_python_chkstow(["-l", "-t", "."])
        assert re.search(r"emacs\nperl\nstow\n", stdout), f"Expected package list, got: {stdout}"

    def test_no_bogus_links(self, chkstow_env):
        r"""Bad links check with no bad links.

        Perl: stdout_like qr{\A\z} (empty)
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert stdout.strip() == "", f"Expected empty stdout, got: {stdout}"

    def test_no_aliens(self, chkstow_env):
        r"""Aliens check with no aliens.

        Perl: stdout_like qr{\A\z} (empty)
        """
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-a", "-t", "."])
        assert stdout.strip() == "", f"Expected empty stdout, got: {stdout}"

    def test_detect_alien(self, chkstow_env):
        """Aliens check with alien file.

        Perl: stdout_like qr{Unstowed file: ./bin/alien}
        """
        chkstow_env.create_target_file("bin/alien", "alien file")
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-a", "-t", "."])
        assert re.search(r"Unstowed file: \./bin/alien", stdout), f"Expected alien detection, got: {stdout}"

    def test_detect_bogus_link(self, chkstow_env):
        """Bad links check with broken symlink.

        Perl: stdout_like qr{Bogus link: ./bin/link}
        """
        bad_link = os.path.join(chkstow_env.target_dir, "bin", "link")
        os.symlink("ireallyhopethisfiledoesn/t.exist", bad_link)
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"Bogus link: \./bin/link", stdout), f"Expected bogus link detection, got: {stdout}"

    def test_skip_stow_directories(self, chkstow_env):
        """Skip directories containing .stow marker.

        Perl: stderr_like qr{skipping .*stow.*}
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, _, stderr = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"skipping.*stow", stderr, re.IGNORECASE), f"Expected skip warning, got stderr: {stderr}"


class TestChkstowSyscalls:
    """Oracle tests comparing syscall traces between Perl and Python chkstow.

    Verifies that the Python implementation uses the same File::Find-like
    traversal pattern as Perl, including:
    - chdir-based directory walking
    - Same lstat/stat patterns
    - Same order of operations
    """

    def test_list_packages_syscalls(self, chkstow_env):
        """List packages mode should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-l", "-t", "."])

    def test_badlinks_syscalls(self, chkstow_env):
        """Bad links check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-b", "-t", "."])

    def test_aliens_syscalls(self, chkstow_env):
        """Aliens check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-a", "-t", "."])
