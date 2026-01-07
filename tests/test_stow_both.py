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
Black-box oracle tests for stow operations.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results (with and without -n)

Based on Perl t/stow.t
"""

import os

from conftest import (
    assert_stow_match,
    check_dir,
    check_link,
    check_not_exists,
    run_both_tests,
)


class TestStowBoth:
    """Test stow operations - black-box comparison of both implementations."""

    def test_stow_simple_tree_minimally(self, stow_env):
        """Stow a simple tree minimally."""
        stow_env.create_package("pkg1", {"bin1/file1": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "bin1", "../stow/pkg1/bin1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg1"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stow_simple_tree_into_existing_directory(self, stow_env):
        """Stow a simple tree into an existing directory."""
        stow_env.create_package("pkg2", {"lib2/file2": "content"})

        def setup():
            stow_env.create_target_dir("lib2")

        def check(env):
            check_link(env, "lib2/file2", "../../stow/pkg2/lib2/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unfold_existing_tree(self, stow_env):
        """Unfold existing tree when stowing second package."""
        stow_env.create_package("pkg3a", {"bin3/file3a": "content a"})
        stow_env.create_package("pkg3b", {"bin3/file3b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3a"])

        def check(env):
            check_dir(env, "bin3")
            check_link(env, "bin3/file3a", "../../stow/pkg3a/bin3/file3a")
            check_link(env, "bin3/file3b", "../../stow/pkg3b/bin3/file3b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg3b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowing_directories_named_0(self, stow_env):
        """Stowing directories named 0."""
        stow_env.create_package("pkg8a", {"0/file8a": "content a"})
        stow_env.create_package("pkg8b", {"0/file8b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg8a"])

        def check(env):
            check_dir(env, "0")
            check_link(env, "0/file8a", "../../stow/pkg8a/0/file8a")
            check_link(env, "0/file8b", "../../stow/pkg8b/0/file8b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg8b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stow_with_no_folding(self, stow_env):
        """Stow with --no-folding creates individual links."""
        stow_env.create_package(
            "pkg",
            {
                "bin/file1": "content1",
                "bin/file2": "content2",
            },
        )

        def setup():
            pass

        def check(env):
            check_dir(env, "bin")
            check_link(env, "bin/file1", "../../stow/pkg/bin/file1")
            check_link(env, "bin/file2", "../../stow/pkg/bin/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--no-folding", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowing_links_to_library_files(self, stow_env):
        """Stowing package with symlinks (like lib.so -> lib.so.1)."""
        pkg_dir = os.path.join(stow_env.stow_dir, "pkg12", "lib12")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "lib.so.1"), "w") as f:
            f.write("library")
        os.symlink("lib.so.1", os.path.join(pkg_dir, "lib.so"))

        def setup():
            stow_env.create_target_dir("lib12")

        def check(env):
            check_link(env, "lib12/lib.so.1", "../../stow/pkg12/lib12/lib.so.1")
            check_link(env, "lib12/lib.so", "../../stow/pkg12/lib12/lib.so")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg12"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_conflict_existing_file(self, stow_env):
        """Conflict when target file already exists."""
        stow_env.create_package("pkg", {"bin/file": "package content"})

        def setup():
            stow_env.create_target_file("bin/file", "existing content")

        def check(env):
            # File should still be the original, not a symlink
            full_path = os.path.join(env.target_dir, "bin/file")
            assert os.path.isfile(full_path), "bin/file should exist"
            assert not os.path.islink(full_path), "bin/file should not be a symlink"

        # For conflicts, check on simulate (planning detects conflict)
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_adopt_existing_file(self, stow_env):
        """Adopt existing files into the package."""
        stow_env.create_package("pkg", {"file": "package version"})

        def setup():
            stow_env.create_target_file("file", "target version")
            # Restore package file to original state for each run
            with open(os.path.join(stow_env.stow_dir, "pkg", "file"), "w") as f:
                f.write("package version")

        def check(env):
            full_path = os.path.join(env.target_dir, "file")
            assert os.path.islink(full_path), "file should be a symlink after adopt"
            pkg_file = os.path.join(env.stow_dir, "pkg", "file")
            with open(pkg_file) as f:
                content = f.read()
            assert content == "target version", "package file should have adopted content"

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--adopt", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_pattern(self, stow_env):
        """Ignore files matching pattern."""
        stow_env.create_package(
            "pkg",
            {
                "man/man1/file.1": "content",
                "man/man1/file.1~": "backup",
                "man/man1/.#file.1": "emacs temp",
            },
        )

        def setup():
            stow_env.create_target_dir("man/man1")

        def check(env):
            check_link(env, "man/man1/file.1", "../../../stow/pkg/man/man1/file.1")
            check_not_exists(env, "man/man1/file.1~")
            check_not_exists(env, "man/man1/.#file.1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=~", "--ignore=\\.#.*", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_override_already_stowed(self, stow_env):
        """Override already stowed paths."""
        stow_env.create_package("pkg9a", {"man9/man1/file9.1": "old"})
        stow_env.create_package("pkg9b", {"man9/man1/file9.1": "new"})

        def setup():
            stow_env.create_target_dir("man9/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg9a"])

        def check(env):
            check_link(
                env, "man9/man1/file9.1", "../../../stow/pkg9b/man9/man1/file9.1"
            )

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=man9", "pkg9b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_defer_to_already_stowed(self, stow_env):
        """Defer to already stowed paths."""
        stow_env.create_package("pkg10a", {"man10/man1/file10.1": "first"})
        stow_env.create_package("pkg10b", {"man10/man1/file10.1": "second"})

        def setup():
            stow_env.create_target_dir("man10/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg10a"])

        def check(env):
            check_link(
                env, "man10/man1/file10.1", "../../../stow/pkg10a/man10/man1/file10.1"
            )

        # Defer is a planning decision, check on simulate
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man10", "pkg10b"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )
