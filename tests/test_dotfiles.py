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
Test case for dotfiles special processing.
Transpiled from Perl t/dotfiles.t
"""

import os

import pytest

from testutil import (
    new_Stow,
    new_compat_Stow,
    make_path,
    make_file,
    make_link,
    stow_module,
)
adjust_dotfile = stow_module.adjust_dotfile
unadjust_dotfile = stow_module.unadjust_dotfile


class TestAdjustDotfile:
    """Tests for adjust_dotfile() utility function."""

    @pytest.mark.parametrize("input_val,expected", [
        ('file', 'file'),
        ('dot-', 'dot-'),
        ('dot-.', 'dot-.'),
        ('dot-file', '.file'),
    ])
    def test_adjust_dotfile(self, input_val, expected):
        assert adjust_dotfile(input_val) == expected


class TestUnadjustDotfile:
    """Tests for unadjust_dotfile() utility function."""

    @pytest.mark.parametrize("input_val,expected", [
        ('file', 'file'),
        ('.', '.'),
        ('..', '..'),
        ('.file', 'dot-file'),
    ])
    def test_unadjust_dotfile(self, input_val, expected):
        assert unadjust_dotfile(input_val) == expected


class TestStowDotfiles:
    """Tests for stowing with dotfiles mode."""

    def test_stow_dot_foo_as_dotfoo(self, stow_test_env):
        """stow dot-foo as .foo"""
        stow = new_Stow(dir='../stow', dotfiles=1)
        make_path('../stow/dotfiles')
        make_file('../stow/dotfiles/dot-foo')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('.foo')
        assert os.readlink('.foo') == '../stow/dotfiles/dot-foo'

    def test_stow_dot_foo_without_dotfiles_enabled(self, stow_test_env):
        """stow dot-foo as dot-foo without --dotfile enabled"""
        stow = new_Stow(dir='../stow', dotfiles=0)
        make_path('../stow/dotfiles')
        make_file('../stow/dotfiles/dot-foo')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('dot-foo')
        assert os.readlink('dot-foo') == '../stow/dotfiles/dot-foo'

    def test_stow_dot_emacs_dir_as_dotemacs(self, stow_test_env):
        """stow dot-emacs dir as .emacs"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-emacs')
        make_file('../stow/dotfiles/dot-emacs/init.el')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('.emacs')
        assert os.readlink('.emacs') == '../stow/dotfiles/dot-emacs'

    def test_stow_dot_dir_when_target_dir_exists(self, stow_test_env):
        """stow dir marked with 'dot' prefix when directory exists in target"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-emacs.d')
        make_file('../stow/dotfiles/dot-emacs.d/init.el')
        make_path('.emacs.d')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('.emacs.d/init.el')
        assert os.readlink('.emacs.d/init.el') == '../../stow/dotfiles/dot-emacs.d/init.el'

    def test_stow_dot_dir_when_target_dir_exists_2_levels(self, stow_test_env):
        """stow dir marked with 'dot' prefix when directory exists in target (2 levels)"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-emacs.d/dot-emacs.d')
        make_file('../stow/dotfiles/dot-emacs.d/dot-emacs.d/init.el')
        make_path('.emacs.d')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('.emacs.d/.emacs.d')
        assert os.readlink('.emacs.d/.emacs.d') == '../../stow/dotfiles/dot-emacs.d/dot-emacs.d'

    def test_stow_dot_dir_nested_2_levels(self, stow_test_env):
        """stow dir marked with 'dot' prefix when directory exists in target (nested 2 levels)"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-one/dot-two')
        make_file('../stow/dotfiles/dot-one/dot-two/three')
        make_path('.one/.two')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('./.one/.two/three')
        assert os.readlink('./.one/.two/three') == '../../../stow/dotfiles/dot-one/dot-two/three'

    def test_dot_dash_should_not_expand(self, stow_test_env):
        """dot-. should not have that part expanded."""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles')
        make_file('../stow/dotfiles/dot-')

        make_path('../stow/dotfiles/dot-.')
        make_file('../stow/dotfiles/dot-./foo')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('dot-')
        assert os.readlink('dot-') == '../stow/dotfiles/dot-'

        assert os.path.islink('dot-.')
        assert os.readlink('dot-.') == '../stow/dotfiles/dot-.'

    def test_stow_dot_gitignore_not_ignored_by_default(self, stow_test_env):
        """when stowing, dot-gitignore is not ignored by default"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_file('../stow/dotfiles/dot-gitignore')

        stow.plan_stow('dotfiles')
        stow.process_tasks()

        assert os.path.islink('.gitignore')
        assert os.readlink('.gitignore') == '../stow/dotfiles/dot-gitignore'


class TestUnstowDotfiles:
    """Tests for unstowing with dotfiles mode."""

    def test_unstow_bar_from_dot_bar(self, stow_test_env):
        """unstow .bar from dot-bar"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles')
        make_file('../stow/dotfiles/dot-bar')
        make_link('.bar', '../stow/dotfiles/dot-bar')

        stow.plan_unstow('dotfiles')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0
        assert os.path.isfile('../stow/dotfiles/dot-bar')
        assert not os.path.exists('.bar')

    def test_unstow_dot_emacs_d_init_el(self, stow_test_env):
        """unstow dot-emacs.d/init.el when .emacs.d/init.el in target"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-emacs.d')
        make_file('../stow/dotfiles/dot-emacs.d/init.el')
        make_path('.emacs.d')
        make_link('.emacs.d/init.el', '../../stow/dotfiles/dot-emacs.d/init.el')

        stow.plan_unstow('dotfiles')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0
        assert os.path.isfile('../stow/dotfiles/dot-emacs.d/init.el')
        assert not os.path.exists('.emacs.d/init.el')
        assert os.path.isdir('.emacs.d/')

    def test_unstow_dot_emacs_d_init_el_compat_mode(self, stow_test_env):
        """unstow dot-emacs.d/init.el in --compat mode"""
        stow = new_compat_Stow(dir='../stow', dotfiles=1)

        make_path('../stow/dotfiles/dot-emacs.d')
        make_file('../stow/dotfiles/dot-emacs.d/init.el')
        make_path('.emacs.d')
        make_link('.emacs.d/init.el', '../../stow/dotfiles/dot-emacs.d/init.el')

        stow.plan_unstow('dotfiles')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0
        assert os.path.isfile('../stow/dotfiles/dot-emacs.d/init.el')
        assert not os.path.exists('.emacs.d/init.el')
        assert os.path.isdir('.emacs.d/')

    def test_unstow_dot_gitignore_not_ignored_by_default(self, stow_test_env):
        """when unstowing, dot-gitignore is not ignored by default"""
        stow = new_Stow(dir='../stow', dotfiles=1)

        make_file('../stow/dotfiles/dot-gitignore')
        if not os.path.exists('.gitignore'):
            make_link('.gitignore', '../stow/dotfiles/dot-gitignore')

        stow.plan_unstow('dotfiles')
        stow.process_tasks()

        assert not os.path.exists('.gitignore')
