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
Black-box oracle tests for advanced stow scenarios.
Tests both Perl and Python implementations via CLI, verifying:
1. Both implementations produce identical results

These tests cover Layer 3 scenario gaps:
- Stow from ~/dotfiles to ~ (parent target)
- --adopt with directory structures
- Multiple stow directories sharing target
- Unfold symlink owned by other stow dir
"""

import os
import shutil

import pytest

from conftest import (
    StowTestEnv,
    assert_stow_match,
    check_dir,
    check_file,
    check_link,
    check_not_exists,
    run_both_tests,
    makedirs_exist_ok,
)


class TestStowDirChildOfTarget:
    """Test stowing when stow dir is a child of target dir (e.g., ~/dotfiles to ~)."""

    def test_stow_from_child_dir_to_parent_target(self, stow_env):
        """Stow from ~/dotfiles to ~ (stow dir is child of target dir).

        This is a common dotfiles setup: ~/dotfiles contains packages that
        should be stowed to ~ (the parent directory).
        Simulated by putting stow dir inside target dir.
        """
        # Create a nested structure: target/dotfiles/pkg/file
        dotfiles_dir = os.path.join(stow_env.target_dir, "dotfiles")
        pkg_dir = os.path.join(dotfiles_dir, "pkg")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "myfile"), "w") as f:
            f.write("content")

        # Update the env to use the nested dotfiles as stow dir
        original_stow_dir = stow_env.stow_dir
        stow_env.stow_dir = dotfiles_dir

        def setup():
            # Reset just the expected file
            file_path = os.path.join(stow_env.target_dir, "myfile")
            if os.path.islink(file_path) or os.path.exists(file_path):
                os.remove(file_path)
            # Recreate the dotfiles directory structure if it was cleared
            if not os.path.exists(pkg_dir):
                os.makedirs(pkg_dir)
                with open(os.path.join(pkg_dir, "myfile"), "w") as f:
                    f.write("content")

        # Just use oracle comparison - no specific check
        run_both_tests(
            stow_env,
            ["-d", dotfiles_dir, "-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=None,
            compare_fs_ops=True,
        )

        # Restore
        stow_env.stow_dir = original_stow_dir

    def test_stow_from_child_dir_with_subdirs(self, stow_env):
        """Stow from child stow dir with nested directories."""
        # Create a nested structure: target/dotfiles/vim/.vim/plugin/settings.vim
        dotfiles_dir = os.path.join(stow_env.target_dir, "dotfiles")
        pkg_dir = os.path.join(dotfiles_dir, "vim")
        config_dir = os.path.join(pkg_dir, ".vim", "plugin")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "settings.vim"), "w") as f:
            f.write("vim settings")

        original_stow_dir = stow_env.stow_dir
        stow_env.stow_dir = dotfiles_dir

        def setup():
            vim_path = os.path.join(stow_env.target_dir, ".vim")
            if os.path.islink(vim_path):
                os.remove(vim_path)
            elif os.path.isdir(vim_path):
                shutil.rmtree(vim_path)
            # Recreate if needed
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
                with open(os.path.join(config_dir, "settings.vim"), "w") as f:
                    f.write("vim settings")

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-d", dotfiles_dir, "-t", stow_env.target_dir, "vim"],
            setup,
            check_func=None,
            compare_fs_ops=True,
        )

        stow_env.stow_dir = original_stow_dir


class TestAdoptDirectoryStructures:
    """Test --adopt with directory structures, not just single files."""

    def test_adopt_entire_directory_tree(self, stow_env):
        """Adopt when there's an existing directory tree, not just a single file."""
        # Package has directory structure
        stow_env.create_package(
            "pkg",
            {
                "config/app/settings.conf": "package settings",
                "config/app/theme.conf": "package theme",
            },
        )

        def setup():
            # Target has matching structure with different content
            stow_env.create_target_file("config/app/settings.conf", "target settings")
            stow_env.create_target_file("config/app/theme.conf", "target theme")
            # Restore package files for each run
            pkg_dir = os.path.join(stow_env.stow_dir, "pkg", "config", "app")
            with open(os.path.join(pkg_dir, "settings.conf"), "w") as f:
                f.write("package settings")
            with open(os.path.join(pkg_dir, "theme.conf"), "w") as f:
                f.write("package theme")

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--adopt", "pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_adopt_partial_directory_overlap(self, stow_env):
        """Adopt with partial overlap - some files exist, some don't."""
        stow_env.create_package(
            "pkg",
            {
                "dir/existing.txt": "package existing",
                "dir/new.txt": "package new",
            },
        )

        def setup():
            # Only one file exists in target
            stow_env.create_target_file("dir/existing.txt", "target existing")
            # Ensure new.txt doesn't exist
            new_path = os.path.join(stow_env.target_dir, "dir", "new.txt")
            if os.path.exists(new_path):
                os.remove(new_path)
            # Restore package files
            pkg_dir = os.path.join(stow_env.stow_dir, "pkg", "dir")
            with open(os.path.join(pkg_dir, "existing.txt"), "w") as f:
                f.write("package existing")
            with open(os.path.join(pkg_dir, "new.txt"), "w") as f:
                f.write("package new")

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--adopt", "pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )


class TestMultipleStowDirs:
    """Test multiple stow directories sharing the same target."""

    def test_two_stow_dirs_same_target(self, stow_env):
        """Two separate stow dirs both stowing to same target directory."""
        # Create a second stow directory
        stow_dir2 = os.path.join(stow_env.tmpdir, "stow2")
        os.makedirs(stow_dir2)

        # Create packages in both stow dirs
        stow_env.create_package("pkg1", {"bin/cmd1": "command 1"})

        pkg2_dir = os.path.join(stow_dir2, "pkg2")
        os.makedirs(os.path.join(pkg2_dir, "bin"))
        with open(os.path.join(pkg2_dir, "bin", "cmd2"), "w") as f:
            f.write("command 2")

        def setup():
            # First stow pkg1 from stow_dir1
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-d", stow_dir2, "-t", stow_env.target_dir, "pkg2"],
            setup,
            check_func=None,
            compare_fs_ops=True,
        )

    def test_unstow_from_one_stow_dir_preserves_other(self, stow_env):
        """Unstowing from one stow dir preserves links from another."""
        # Create a second stow directory
        stow_dir2 = os.path.join(stow_env.tmpdir, "stow2")
        os.makedirs(stow_dir2)

        # Create packages in both stow dirs
        stow_env.create_package("pkg1", {"lib/lib1.so": "library 1"})

        pkg2_dir = os.path.join(stow_dir2, "pkg2")
        os.makedirs(os.path.join(pkg2_dir, "lib"))
        with open(os.path.join(pkg2_dir, "lib", "lib2.so"), "w") as f:
            f.write("library 2")

        def setup():
            # Stow both packages
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])
            stow_env.run_perl_stow(["-d", stow_dir2, "-t", stow_env.target_dir, "pkg2"])

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg1"],
            setup,
            check_func=None,
            compare_fs_ops=True,
        )


class TestUnfoldFromOtherStowDir:
    """Test unfolding symlink owned by another stow directory."""

    def test_unfold_link_from_other_stow_dir(self, stow_env):
        """Second stow dir needs to unfold a link created by first stow dir."""
        # Create a second stow directory
        stow_dir2 = os.path.join(stow_env.tmpdir, "stow2")
        os.makedirs(stow_dir2)

        # pkg1 in stow1: share/app/file1
        stow_env.create_package("pkg1", {"share/app/file1": "file 1"})

        # pkg2 in stow2: share/app/file2
        pkg2_dir = os.path.join(stow_dir2, "pkg2")
        os.makedirs(os.path.join(pkg2_dir, "share", "app"))
        with open(os.path.join(pkg2_dir, "share", "app", "file2"), "w") as f:
            f.write("file 2")

        def setup():
            # Stow pkg1 from stow1 (creates folded link share -> stow/pkg1/share)
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        # Just use oracle comparison
        run_both_tests(
            stow_env,
            ["-d", stow_dir2, "-t", stow_env.target_dir, "pkg2"],
            setup,
            check_func=None,
            compare_fs_ops=True,
        )
