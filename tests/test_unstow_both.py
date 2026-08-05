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
Black-box oracle tests for unstow operations.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results (with and without -n)

Based on Perl t/unstow.t
"""

import errno
import os

from conftest import (
    assert_stow_match,
    check_dir,
    check_link,
    check_not_exists,
    run_both_tests,
)


class TestUnstowBoth:
    """Test unstow operations - black-box comparison of both implementations."""

    def test_unstow_simple_tree_minimally(self, stow_env):
        """Unstow a simple tree minimally."""
        stow_env.create_package("pkg1", {"bin1/file1": "content"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            check_not_exists(env, "bin1")
            assert os.path.isfile(os.path.join(env.stow_dir, "pkg1/bin1/file1"))

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg1"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unstow_from_existing_directory(self, stow_env):
        """Unstow a simple tree from an existing directory."""
        stow_env.create_package("pkg2", {"lib2/file2": "content"})

        def setup():
            stow_env.create_target_dir("lib2")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg2"])

        def check(env):
            check_not_exists(env, "lib2/file2")
            check_dir(env, "lib2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_fold_tree_after_unstowing(self, stow_env):
        """Fold tree after unstowing."""
        stow_env.create_package("pkg3a", {"bin3/file3a": "content a"})
        stow_env.create_package("pkg3b", {"bin3/file3b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3a"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3b"])

        def check(env):
            check_link(env, "bin3", "../stow/pkg3a/bin3")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg3b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unstow_link_owned_by_different_package(self, stow_env):
        """Unstowing pkg when link is owned by different package."""
        stow_env.create_package("pkg6a", {"bin6/file6": "content a"})
        stow_env.create_package("pkg6b", {"bin6/file6": "content b"})

        def setup():
            # Manually create link pointing to pkg6a (emulate prior stow)
            stow_env.create_target_dir("bin6")
            stow_env.create_target_link("bin6/file6", "../../stow/pkg6a/bin6/file6")

        def check(env):
            # Original test checks planner doesn't touch links from other pkgs
            # With -n (simulate), link should be unchanged
            check_link(env, "bin6/file6", "../../stow/pkg6a/bin6/file6")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg6b"],
            setup,
            check,
            check_on_simulate=True,  # Original test was planning-only
            compare_fs_ops=True,
        )

    def test_unstow_directories_named_0(self, stow_env):
        """Unstowing directories named 0."""
        stow_env.create_package("pkg8a", {"0/file8a": "content a"})
        stow_env.create_package("pkg8b", {"0/file8b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg8a"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg8b"])

        def check(env):
            check_link(env, "0", "../stow/pkg8a/0")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg8b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unstow_with_ignore_pattern(self, stow_env):
        """Ignore temp files when unstowing."""
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
            stow_env.run_perl_stow(
                ["-t", stow_env.target_dir, "--ignore=~", "--ignore=\\.#.*", "pkg"]
            )

        def check(env):
            check_not_exists(env, "man/man1/file.1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=~", "--ignore=\\.#.*", "-D", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unstow_never_stowed_package(self, stow_env):
        """Unstow a package that was never stowed."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass  # No setup - package never stowed

        def check(env):
            check_not_exists(env, "bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_restow_operation(self, stow_env):
        """Restow operation (unstow + stow)."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unreadable_target_subdir_is_fatal(self, stow_env):
        """A target subdirectory that cannot be read while unstowing in
        compat mode is fatal, and the exit status is the errno of the
        syscall that failed."""
        stow_env.create_package("pkgperm", {"bin/file": "content"})
        locked = os.path.join(stow_env.target_dir, "bin")

        def setup():
            os.makedirs(locked)
            os.symlink("../../stow/pkgperm/bin/file", os.path.join(locked, "file"))
            os.chmod(locked, 0o000)

        results = []
        for run in (stow_env.run_perl_stow, stow_env.run_python_stow):
            if os.path.exists(locked):
                os.chmod(locked, 0o755)
            stow_env.reset_target()
            setup()
            try:
                results.append(run(["-t", stow_env.target_dir, "-D", "-p", "pkgperm"]))
            finally:
                os.chmod(locked, 0o755)

        assert results[0] == results[1]
        rc, stdout, stderr = results[0]
        assert rc == errno.EACCES
        assert stdout == ""
        assert stderr == "stow: ERROR: cannot read directory: bin (Permission denied)\n"

    def test_unstow_over_target_link_to_zero_is_fatal(self, stow_env):
        """Reading a target link whose destination is "0" fails the same way
        during unstow, so the whole operation aborts instead of silently
        doing nothing."""
        stow_env.create_package("pkgz2", {"link": "content"})

        def setup():
            stow_env.create_target_link("link", "0")

        rc, stdout, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "-D", "pkgz2"], setup
        )
        assert rc == errno.ENOENT
        assert stdout == ""
        assert stderr == (
            "stow: ERROR: Could not read link: link (No such file or directory)\n"
        )
