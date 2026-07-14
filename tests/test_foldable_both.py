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
Oracle tests for tree folding behavior.

These tests verify that Perl and Python stow fold/unfold directory trees
identically. Tree folding creates a single symlink for an entire directory
when possible, rather than individual symlinks for each file.
"""

from conftest import (
    check_link,
    check_dir,
    check_not_exists,
    run_both_tests,
)


class TestFoldableBoth:
    """Oracle tests for tree folding behavior."""

    def test_foldable_simple_tree(self, stow_env):
        """Unstowing second package folds tree back to single symlink."""
        # pkg1a and pkg1b both contribute to bin1
        stow_env.create_package("pkg1a", {"bin1/file1a": "content a"})
        stow_env.create_package("pkg1b", {"bin1/file1b": "content b"})

        def setup():
            # First stow pkg1a (creates folded symlink)
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1a"])
            # Then stow pkg1b (unfolds into directory with individual links)
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1b"])

        def check(env):
            # After unstowing pkg1b, should fold back to single symlink
            check_link(env, "bin1", "../stow/pkg1a/bin1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg1b"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_not_foldable_empty_directory(self, stow_env):
        """Empty directory can't be folded."""
        stow_env.create_package("pkg2", {"bin2/file2": "content"})

        def setup():
            # Create empty directory (not from stow)
            stow_env.create_target_dir("bin2")

        def check(env):
            # Stow creates individual links, doesn't fold
            check_dir(env, "bin2")
            check_link(env, "bin2/file2", "../../stow/pkg2/bin2/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg2"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_not_foldable_with_non_link(self, stow_env):
        """Directory with non-link file can't be folded."""
        stow_env.create_package("pkg3a", {"bin3/file3": "content"})
        stow_env.create_package("pkg3b", {"bin3/file3b": "content b"})

        def setup():
            # Stow first package
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3a"])
            # Stow second package (unfolds)
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3b"])
            # Add a non-link file
            stow_env.create_target_file("bin3/non-link", "alien content")

        def check(env):
            # After unstowing pkg3b, can't fold because of non-link file
            check_dir(env, "bin3")
            check_link(env, "bin3/file3", "../../stow/pkg3a/bin3/file3")
            check_not_exists(env, "bin3/file3b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg3b"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_not_foldable_links_to_different_dirs(self, stow_env):
        """Directory with links to different package dirs can't be folded."""
        stow_env.create_package("pkg4a", {"bin4/file4a": "content a"})
        stow_env.create_package("pkg4b", {"bin4/file4b": "content b"})
        stow_env.create_package("pkg4c", {"bin4/file4c": "content c"})

        def setup():
            # Stow all three packages (creates unfolded directory)
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg4a"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg4b"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg4c"])

        def check(env):
            # After unstowing pkg4c, still can't fold (two different packages)
            check_dir(env, "bin4")
            check_link(env, "bin4/file4a", "../../stow/pkg4a/bin4/file4a")
            check_link(env, "bin4/file4b", "../../stow/pkg4b/bin4/file4b")
            check_not_exists(env, "bin4/file4c")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg4c"],
            setup,
            check,
            compare_fs_ops=True,
        )
