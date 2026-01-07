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
Black-box oracle tests for dotfiles special processing.
Tests both Perl and Python implementations via CLI.

Based on Perl t/dotfiles.t - integration tests only.
Unit tests for adjust_dotfile/unadjust_dotfile remain in test_dotfiles.py.
"""

from conftest import assert_stow_match_with_fs_ops


class TestStowDotfilesBoth:
    """Tests for stowing with dotfiles mode - black-box comparison of both implementations."""

    def test_stow_dot_foo_as_dotfoo(self, stow_env):
        """stow dot-foo as .foo"""
        stow_env.create_package("dotfiles", {"dot-foo": "foo content"})

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_stow_dot_foo_without_dotfiles_enabled(self, stow_env):
        """stow dot-foo as dot-foo without --dotfiles enabled"""
        stow_env.create_package("dotfiles", {"dot-foo": "foo content"})

        # Without --dotfiles flag
        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "dotfiles"])

    def test_stow_dot_emacs_dir_as_dotemacs(self, stow_env):
        """stow dot-emacs dir as .emacs"""
        stow_env.create_package("dotfiles", {"dot-emacs/init.el": "emacs init"})

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_stow_dot_dir_when_target_dir_exists(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target"""
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})
        stow_env.create_target_dir(".emacs.d")

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_stow_dot_dir_when_target_dir_exists_2_levels(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target (2 levels)"""
        stow_env.create_package(
            "dotfiles", {"dot-emacs.d/dot-emacs.d/init.el": "nested init"}
        )
        stow_env.create_target_dir(".emacs.d")

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_stow_dot_dir_nested_2_levels(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target (nested 2 levels)"""
        stow_env.create_package("dotfiles", {"dot-one/dot-two/three": "content"})
        stow_env.create_target_dir(".one/.two")

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_dot_dash_should_not_expand(self, stow_env):
        """dot-. should not have that part expanded."""
        stow_env.create_package(
            "dotfiles",
            {
                "dot-": "dot dash content",
                "dot-./foo": "foo content",
            },
        )

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

    def test_stow_dot_gitignore_not_ignored_by_default(self, stow_env):
        """when stowing, dot-gitignore is not ignored by default"""
        stow_env.create_package("dotfiles", {"dot-gitignore": "*.pyc\n"})

        assert_stow_match_with_fs_ops(stow_env, ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])


class TestUnstowDotfilesBoth:
    """Tests for unstowing with dotfiles mode - black-box comparison of both implementations."""

    def test_unstow_bar_from_dot_bar(self, stow_env):
        """unstow .bar from dot-bar"""
        stow_env.create_package("dotfiles", {"dot-bar": "bar content"})

        # First stow with Perl (sets up initial state for both runs)
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

        # Then test unstow
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"]
        )

    def test_unstow_dot_emacs_d_init_el(self, stow_env):
        """unstow dot-emacs.d/init.el when .emacs.d/init.el in target"""
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})
        stow_env.create_target_dir(".emacs.d")

        # First stow
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

        # Then test unstow
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"]
        )

    def test_unstow_dot_emacs_d_init_el_compat_mode(self, stow_env):
        """unstow dot-emacs.d/init.el in --compat mode"""
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})
        stow_env.create_target_dir(".emacs.d")

        # First stow
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

        # Then test unstow with --compat
        assert_stow_match_with_fs_ops(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "--compat", "-D", "dotfiles"],
        )

    def test_unstow_dot_gitignore_not_ignored_by_default(self, stow_env):
        """when unstowing, dot-gitignore is not ignored by default"""
        stow_env.create_package("dotfiles", {"dot-gitignore": "*.pyc\n"})

        # First stow
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "--dotfiles", "dotfiles"])

        # Then test unstow
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"]
        )