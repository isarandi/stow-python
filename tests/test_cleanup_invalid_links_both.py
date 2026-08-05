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
Oracle tests for cleanup_invalid_links behavior.

These tests verify that Perl and Python stow handle invalid/orphaned
symlinks identically during stow/unstow operations.
"""

import errno
import os

from conftest import (
    assert_stow_match,
    check_link,
    check_not_exists,
    run_both_tests,
)


class TestCleanupInvalidLinksBoth:
    """Oracle tests for cleanup_invalid_links behavior."""

    def test_nothing_to_clean_in_simple_tree(self, stow_env):
        """Nothing to clean in a simple tree - both should leave valid link."""
        stow_env.create_package("pkg1", {"bin1/file1": "content"})

        def setup():
            # Create folded symlink (as if previously stowed)
            stow_env.create_target_link("bin1", "../stow/pkg1/bin1")

        def check(env):
            # Link should still be there
            check_link(env, "bin1", "../stow/pkg1/bin1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg1"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_cleanup_orphaned_owned_link(self, stow_env):
        """Cleanup orphaned stow-owned link during restow."""
        stow_env.create_package("pkg2", {"bin2/file2a": "content"})

        def setup():
            # Create directory with valid and orphaned links
            stow_env.create_target_dir("bin2")
            stow_env.create_target_link("bin2/file2a", "../../stow/pkg2/bin2/file2a")
            # Orphaned link pointing into same package but to non-existent file
            orphan_path = os.path.join(stow_env.target_dir, "bin2", "file2b")
            os.symlink("../../stow/pkg2/bin2/file2b", orphan_path)

        def check(env):
            # Valid link should remain
            check_link(env, "bin2/file2a", "../../stow/pkg2/bin2/file2a")
            # Orphaned link should be cleaned up
            check_not_exists(env, "bin2/file2b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg2"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_dont_cleanup_bad_link_not_owned_by_stow(self, stow_env):
        """Don't cleanup bad links not pointing into stow directory."""
        stow_env.create_package("pkg3", {"bin3/file3a": "content"})

        def setup():
            stow_env.create_target_dir("bin3")
            stow_env.create_target_link("bin3/file3a", "../../stow/pkg3/bin3/file3a")
            # Bad link NOT owned by stow (points outside stow dir)
            orphan_path = os.path.join(stow_env.target_dir, "bin3", "file3b")
            os.symlink("../../empty", orphan_path)

        def check(env):
            check_link(env, "bin3/file3a", "../../stow/pkg3/bin3/file3a")
            # Non-stow link should NOT be cleaned up
            check_link(env, "bin3/file3b", "../../empty")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg3"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_dont_cleanup_valid_link_not_owned_by_stow(self, stow_env):
        """Don't cleanup valid links not owned by stow."""
        stow_env.create_package("pkg4", {"bin4/file4a": "content"})

        def setup():
            stow_env.create_target_dir("bin4")
            stow_env.create_target_link("bin4/file4a", "../../stow/pkg4/bin4/file4a")
            # Valid non-stow link
            stow_env.create_target_file("unowned", "content")
            stow_env.create_target_link("bin4/file4b", "../unowned")

        def check(env):
            check_link(env, "bin4/file4a", "../../stow/pkg4/bin4/file4a")
            # Non-stow link should NOT be touched
            check_link(env, "bin4/file4b", "../unowned")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg4"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_foreign_link_to_zero_aborts_cleanup(self, stow_env):
        """cleanup_invalid_links() calls readlink() directly, so its error
        for a link pointing at "0" has neither a colon nor the errno text.
        The abort leaves the package's own links in place."""
        stow_env.create_package("pkg5", {"a.txt": "content a", "b.txt": "content b"})

        def setup():
            stow_env.create_target_link("a.txt", "../stow/pkg5/a.txt")
            stow_env.create_target_link("b.txt", "../stow/pkg5/b.txt")
            stow_env.create_target_link("x", "0")

        rc, stdout, stderr, state = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "-D", "pkg5"], setup
        )
        assert rc == errno.ENOENT
        assert stdout == ""
        assert stderr == "stow: ERROR: Could not read link x\n"
        assert set(state) == {"a.txt", "b.txt", "x"}

    def test_dont_cleanup_dangling_link_owned_by_package_zero(self, stow_env):
        """A package named "0" is false to Perl's ownership test, so a
        dangling link into it is not recognised as stow's and survives the
        clean-up that removes nothing and reports nothing."""
        stow_env.create_package("0", {"bin6/keep": "content"})
        stow_env.create_package("pkg6", {"bin6/file6": "content"})

        def setup():
            stow_env.create_target_dir("bin6")
            stow_env.create_target_link("bin6/gone", "../../stow/0/bin6/gone")
            stow_env.create_target_link("bin6/file6", "../../stow/pkg6/bin6/file6")

        def check(env):
            check_link(env, "bin6/gone", "../../stow/0/bin6/gone")
            check_not_exists(env, "bin6/file6")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg6"],
            setup,
            check,
            compare_fs_ops=True,
        )
