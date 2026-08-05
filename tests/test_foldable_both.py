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

import os

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

    def test_tree_owned_by_package_zero_is_not_foldable(self, stow_env):
        """foldable() folds only if the common parent is owned by a package,
        and a package named "0" is false to Perl's test, so the directory
        stays unfolded."""
        stow_env.create_package("0", {"bin5/file5a": "content a"})
        stow_env.create_package("pkg5b", {"bin5/file5b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "0"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg5b"])

        def check(env):
            check_dir(env, "bin5")
            check_link(env, "bin5/file5a", "../../stow/0/bin5/file5a")
            check_not_exists(env, "bin5/file5b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg5b"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_links_into_package_subdir_zero_count_as_no_links(self, stow_env):
        """A common parent of "0" is false, so foldable() reports that the
        directory contains no links and returns before asking who owns it —
        which is what keeps it from walking into a stow dir named "0"."""
        stow_env.create_package("pkg6", {"bin6/0/x": "content"})

        def setup():
            stow_env.create_target_dir("0")
            with open(os.path.join(stow_env.target_dir, "0", ".stow"), "w"):
                pass
            stow_env.create_target_dir("bin6")
            stow_env.create_target_link("bin6/0", "../../stow/pkg6/bin6/0")
            stow_env.create_target_link("bin6/f", "0/x")

        def check(env):
            check_dir(env, "bin6")
            check_not_exists(env, "bin6/0")
            check_link(env, "bin6/f", "0/x")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg6"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_first_link_without_directory_part_does_not_fix_the_parent(self, stow_env):
        """foldable() seeds the common parent with the empty string and
        re-tests for that exact value, so a first link whose destination has
        no directory part leaves the next link to set it instead of being
        compared against it."""
        stow_env.create_package("pkg7", {"bin7/file7": "content"})

        def setup():
            stow_env.create_target_file("elsewhere/f", "content")
            stow_env.create_target_dir("bin7")
            stow_env.create_target_link("bin7/file7", "../../stow/pkg7/bin7/file7")
            # a resolves through x, whose own destination names a directory
            stow_env.create_target_link("bin7/a", "x")
            stow_env.create_target_link("bin7/x", "../elsewhere/f")

        traces = []
        for run in (stow_env.run_perl_stow, stow_env.run_python_stow):
            stow_env.reset_target()
            setup()
            rc, stdout, stderr = run(["-t", stow_env.target_dir, "-v3", "-D", "pkg7"])
            assert rc == 0
            assert stdout == ""
            traces.append(stderr)
            check_dir(stow_env, "bin7")
            check_link(stow_env, "bin7/a", "x")
            check_not_exists(stow_env, "bin7/file7")

        assert traces[0] == traces[1]
        assert "            bin7 is not foldable\n" in traces[0]
