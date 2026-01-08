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

from conftest import run_both_tests, check_link, check_not_exists, check_dir


class TestStowDotfilesBoth:
    """Tests for stowing with dotfiles mode - black-box comparison of both implementations."""

    def test_stow_dot_foo_as_dotfoo(self, stow_env):
        """stow dot-foo as .foo

        Perl: is(readlink('.foo'), '../stow/dotfiles/dot-foo')
        """
        stow_env.create_package("dotfiles", {"dot-foo": "foo content"})

        def setup():
            pass

        def check(env):
            check_link(env, ".foo", "../stow/dotfiles/dot-foo")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_foo_without_dotfiles_enabled(self, stow_env):
        """stow dot-foo as dot-foo without --dotfiles enabled

        Perl: is(readlink('dot-foo'), '../stow/dotfiles/dot-foo')
        """
        stow_env.create_package("dotfiles", {"dot-foo": "foo content"})

        def setup():
            pass

        def check(env):
            check_link(env, "dot-foo", "../stow/dotfiles/dot-foo")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_emacs_dir_as_dotemacs(self, stow_env):
        """stow dot-emacs dir as .emacs

        Perl: is(readlink('.emacs'), '../stow/dotfiles/dot-emacs')
        """
        stow_env.create_package("dotfiles", {"dot-emacs/init.el": "emacs init"})

        def setup():
            pass

        def check(env):
            check_link(env, ".emacs", "../stow/dotfiles/dot-emacs")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_dir_when_target_dir_exists(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target

        Perl: is(readlink('.emacs.d/init.el'), '../../stow/dotfiles/dot-emacs.d/init.el')
        """
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})

        def setup():
            stow_env.create_target_dir(".emacs.d")

        def check(env):
            check_link(env, ".emacs.d/init.el", "../../stow/dotfiles/dot-emacs.d/init.el")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_dir_when_target_dir_exists_2_levels(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target (2 levels)

        Perl: is(readlink('.emacs.d/.emacs.d'), '../../stow/dotfiles/dot-emacs.d/dot-emacs.d')
        """
        stow_env.create_package(
            "dotfiles", {"dot-emacs.d/dot-emacs.d/init.el": "nested init"}
        )

        def setup():
            stow_env.create_target_dir(".emacs.d")

        def check(env):
            check_link(env, ".emacs.d/.emacs.d", "../../stow/dotfiles/dot-emacs.d/dot-emacs.d")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_dir_nested_2_levels(self, stow_env):
        """stow dir marked with 'dot' prefix when directory exists in target (nested 2 levels)

        Perl: is(readlink('./.one/.two/three'), '../../../stow/dotfiles/dot-one/dot-two/three')
        """
        stow_env.create_package("dotfiles", {"dot-one/dot-two/three": "content"})

        def setup():
            stow_env.create_target_dir(".one/.two")

        def check(env):
            check_link(env, ".one/.two/three", "../../../stow/dotfiles/dot-one/dot-two/three")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_dot_dash_should_not_expand(self, stow_env):
        """dot-. should not have that part expanded.

        Perl:
          is(readlink('dot-'), '../stow/dotfiles/dot-')
          is(readlink('dot-.'), '../stow/dotfiles/dot-.')
        """
        stow_env.create_package(
            "dotfiles",
            {
                "dot-": "dot dash content",
                "dot-./foo": "foo content",
            },
        )

        def setup():
            pass

        def check(env):
            check_link(env, "dot-", "../stow/dotfiles/dot-")
            check_link(env, "dot-.", "../stow/dotfiles/dot-.")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_stow_dot_gitignore_not_ignored_by_default(self, stow_env):
        """when stowing, dot-gitignore is not ignored by default

        Perl: is(readlink('.gitignore'), '../stow/dotfiles/dot-gitignore')
        """
        stow_env.create_package("dotfiles", {"dot-gitignore": "*.pyc\n"})

        def setup():
            pass

        def check(env):
            check_link(env, ".gitignore", "../stow/dotfiles/dot-gitignore")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )


class TestUnstowDotfilesBoth:
    """Tests for unstowing with dotfiles mode - black-box comparison of both implementations."""

    def test_unstow_bar_from_dot_bar(self, stow_env):
        """unstow .bar from dot-bar

        Perl:
          ok(-f '../stow/dotfiles/dot-bar', 'package file untouched')
          ok(! -e '.bar' => '.bar was unstowed')
        """
        stow_env.create_package("dotfiles", {"dot-bar": "bar content"})

        def setup():
            # Pre-create the link as if already stowed
            stow_env.create_target_link(".bar", "../stow/dotfiles/dot-bar")

        def check(env):
            check_not_exists(env, ".bar")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_unstow_dot_emacs_d_init_el(self, stow_env):
        """unstow dot-emacs.d/init.el when .emacs.d/init.el in target

        Perl:
          ok(! -e '.emacs.d/init.el', '.emacs.d/init.el unstowed')
          ok(-d '.emacs.d/' => '.emacs.d left behind')
        """
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})

        def setup():
            stow_env.create_target_dir(".emacs.d")
            stow_env.create_target_link(".emacs.d/init.el", "../../stow/dotfiles/dot-emacs.d/init.el")

        def check(env):
            check_not_exists(env, ".emacs.d/init.el")
            check_dir(env, ".emacs.d")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_unstow_dot_emacs_d_init_el_compat_mode(self, stow_env):
        """unstow dot-emacs.d/init.el in --compat mode

        Perl:
          ok(! -e '.emacs.d/init.el', '.emacs.d/init.el unstowed')
          ok(-d '.emacs.d/' => '.emacs.d left behind')
        """
        stow_env.create_package("dotfiles", {"dot-emacs.d/init.el": "emacs init"})

        def setup():
            stow_env.create_target_dir(".emacs.d")
            stow_env.create_target_link(".emacs.d/init.el", "../../stow/dotfiles/dot-emacs.d/init.el")

        def check(env):
            check_not_exists(env, ".emacs.d/init.el")
            check_dir(env, ".emacs.d")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "--compat", "-D", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_unstow_dot_gitignore_not_ignored_by_default(self, stow_env):
        """when unstowing, dot-gitignore is not ignored by default

        Perl: ok(! -e ('.gitignore') => "dot-gitignore shouldn't have been ignored")
        """
        stow_env.create_package("dotfiles", {"dot-gitignore": "*.pyc\n"})

        def setup():
            stow_env.create_target_link(".gitignore", "../stow/dotfiles/dot-gitignore")

        def check(env):
            check_not_exists(env, ".gitignore")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "-D", "dotfiles"],
            setup,
            check,
            compare_fs_ops=True,
        )
