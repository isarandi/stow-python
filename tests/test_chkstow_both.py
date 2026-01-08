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
Oracle tests for chkstow - comparing Perl and Python implementations.

These tests run chkstow CLI on both implementations and verify identical:
- Return codes
- stdout output
- stderr output
- Filesystem operations (via strace)
"""

import os
import pytest

from conftest import assert_chkstow_match, assert_chkstow_match_with_fs_ops


@pytest.fixture
def chkstow_env(stow_env):
    """Set up test environment for chkstow tests."""
    # Create stow directory marker
    stow_env.create_target_dir("stow")
    stow_marker = os.path.join(stow_env.target_dir, "stow", ".stow")
    with open(stow_marker, "w") as f:
        pass

    # Create perl package
    for path in ["stow/perl/bin", "stow/perl/info", "stow/perl/lib/perl",
                 "stow/perl/man/man1"]:
        stow_env.create_target_dir(path)
    for path, content in [
        ("stow/perl/bin/perl", "perl"),
        ("stow/perl/bin/a2p", "a2p"),
        ("stow/perl/info/perl", "info"),
        ("stow/perl/man/man1/perl.1", "man"),
    ]:
        stow_env.create_target_file(path, content)

    # Create emacs package
    for path in ["stow/emacs/bin", "stow/emacs/info", "stow/emacs/libexec/emacs",
                 "stow/emacs/man/man1"]:
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

    Note: Strace comparison not used for chkstow - it's read-only and
    directory traversal order can legitimately differ. Output matching
    is sufficient.
    """

    def test_list_packages(self, chkstow_env):
        """List packages mode should produce identical output."""
        assert_chkstow_match(chkstow_env, ["-l", "-t", "."])

    def test_no_bogus_links(self, chkstow_env):
        """Bad links check with no bad links."""
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])

    def test_no_aliens(self, chkstow_env):
        """Aliens check with no aliens."""
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])

    def test_detect_alien(self, chkstow_env):
        """Aliens check should detect non-symlink files identically."""
        chkstow_env.create_target_file("bin/alien", "alien file")
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])

    def test_detect_bogus_link(self, chkstow_env):
        """Bad links check should detect broken symlinks identically."""
        bad_link = os.path.join(chkstow_env.target_dir, "bin", "broken")
        os.symlink("../../stow/nonexistent/bin/broken", bad_link)
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])


class TestChkstowSyscalls:
    """Oracle tests comparing syscall traces between Perl and Python chkstow."""

    def test_list_packages_syscalls(self, chkstow_env):
        """List packages mode should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-l", "-t", "."])

    def test_badlinks_syscalls(self, chkstow_env):
        """Bad links check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-b", "-t", "."])

    def test_aliens_syscalls(self, chkstow_env):
        """Aliens check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-a", "-t", "."])
