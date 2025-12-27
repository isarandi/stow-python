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
Testing examples from the documentation.
Python port of t/examples.t
"""

import os

from testutil import (
    new_Stow, make_path, make_file,
    is_dir_not_symlink
)


def setup_perl_package():
    """Set up fake perl package to stow."""
    make_path('stow/perl/bin')
    make_file('stow/perl/bin/perl')
    make_file('stow/perl/bin/a2p')
    make_path('stow/perl/info')
    make_file('stow/perl/info/perl')
    make_path('stow/perl/lib/perl')
    make_path('stow/perl/man/man1')
    make_file('stow/perl/man/man1/perl.1')


def setup_emacs_package():
    """Set up fake emacs package to stow."""
    make_path('stow/emacs/bin')
    make_file('stow/emacs/bin/emacs')
    make_file('stow/emacs/bin/etags')
    make_path('stow/emacs/info')
    make_file('stow/emacs/info/emacs')
    make_path('stow/emacs/libexec/emacs')
    make_path('stow/emacs/man/man1')
    make_file('stow/emacs/man/man1/emacs.1')


class TestDocumentationExamples:
    """Tests based on examples from the documentation."""

    def test_stow_perl_into_empty_target(self, stow_test_env):
        """Stow perl into an empty target."""
        setup_perl_package()

        stow = new_Stow(dir='stow')
        stow.plan_stow('perl')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0
        assert os.path.islink('bin')
        assert os.path.islink('info')
        assert os.path.islink('lib')
        assert os.path.islink('man')
        assert os.readlink('bin') == 'stow/perl/bin'
        assert os.readlink('info') == 'stow/perl/info'
        assert os.readlink('lib') == 'stow/perl/lib'
        assert os.readlink('man') == 'stow/perl/man'

    def test_stow_perl_into_nonempty_target(self, stow_test_env):
        """Stow perl into a non-empty target."""
        setup_perl_package()

        # Create pre-existing directories in target
        make_path('bin')
        make_path('lib')
        make_path('man/man1')

        stow = new_Stow(dir='stow')
        stow.plan_stow('perl')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0
        # Directories should remain directories (not folded to symlinks)
        is_dir_not_symlink('bin')
        is_dir_not_symlink('lib')
        is_dir_not_symlink('man')
        is_dir_not_symlink('man/man1')
        # info didn't exist, so it should be a symlink
        assert os.path.islink('info')
        # Individual files should be symlinks
        assert os.path.islink('bin/perl')
        assert os.path.islink('bin/a2p')
        assert os.path.islink('lib/perl')
        assert os.path.islink('man/man1/perl.1')
        # Check symlink targets
        assert os.readlink('info') == 'stow/perl/info'
        assert os.readlink('bin/perl') == '../stow/perl/bin/perl'
        assert os.readlink('bin/a2p') == '../stow/perl/bin/a2p'
        assert os.readlink('lib/perl') == '../stow/perl/lib/perl'
        assert os.readlink('man/man1/perl.1') == '../../stow/perl/man/man1/perl.1'

    def test_stow_perl_then_emacs_into_empty_target(self, stow_test_env):
        """Install perl into an empty target and then install emacs."""
        setup_perl_package()
        setup_emacs_package()

        stow = new_Stow(dir='stow')
        stow.plan_stow('perl', 'emacs')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0

        # bin should be a directory (unfolded due to both packages)
        is_dir_not_symlink('bin')
        assert os.path.islink('bin/perl')
        assert os.path.islink('bin/emacs')
        assert os.path.islink('bin/a2p')
        assert os.path.islink('bin/etags')
        assert os.readlink('bin/perl') == '../stow/perl/bin/perl'
        assert os.readlink('bin/a2p') == '../stow/perl/bin/a2p'
        assert os.readlink('bin/emacs') == '../stow/emacs/bin/emacs'
        assert os.readlink('bin/etags') == '../stow/emacs/bin/etags'

        # info should be a directory (unfolded due to both packages)
        is_dir_not_symlink('info')
        assert os.path.islink('info/perl')
        assert os.path.islink('info/emacs')
        assert os.readlink('info/perl') == '../stow/perl/info/perl'
        assert os.readlink('info/emacs') == '../stow/emacs/info/emacs'

        # man should be a directory (unfolded due to both packages)
        is_dir_not_symlink('man')
        is_dir_not_symlink('man/man1')
        assert os.path.islink('man/man1/perl.1')
        assert os.path.islink('man/man1/emacs.1')
        assert os.readlink('man/man1/perl.1') == '../../stow/perl/man/man1/perl.1'
        assert os.readlink('man/man1/emacs.1') == '../../stow/emacs/man/man1/emacs.1'

        # lib only in perl, libexec only in emacs - should be symlinks
        assert os.path.islink('lib')
        assert os.path.islink('libexec')
        assert os.readlink('lib') == 'stow/perl/lib'
        assert os.readlink('libexec') == 'stow/emacs/libexec'

    def test_bug1_stowing_empty_dirs(self, stow_test_env):
        """
        BUG 1: Empty directory handling.

        1. Stow a package with an empty directory
        2. Stow another package with the same directory but non empty
        3. Unstow the second package

        The original empty directory should remain.
        Behavior is the same as if the empty directory had nothing to do with stow.
        """
        make_path('stow/pkg1a/bin1')
        make_path('stow/pkg1b/bin1')
        make_file('stow/pkg1b/bin1/file1b')

        stow = new_Stow(dir='stow')
        stow.plan_stow('pkg1a', 'pkg1b')
        stow.plan_unstow('pkg1b')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0, 'no conflicts stowing empty dirs'
        assert os.path.isdir('bin1'), 'bug 1: stowing empty dirs - directory should remain'

    def test_bug2_split_tree_folding_symlinks_from_different_stow_dirs(self, stow_test_env):
        """
        BUG 2: Split open tree-folding symlinks pointing inside different stow
        directories.
        """
        # Set up two separate stow directories
        make_path('stow2a/pkg2a/bin2')
        make_file('stow2a/pkg2a/bin2/file2a')
        make_file('stow2a/.stow')
        make_path('stow2b/pkg2b/bin2')
        make_file('stow2b/pkg2b/bin2/file2b')
        make_file('stow2b/.stow')

        stow = new_Stow(dir='stow2a')
        stow.plan_stow('pkg2a')
        stow.set_stow_dir('stow2b')
        stow.plan_stow('pkg2b')
        stow.process_tasks()

        assert stow.get_conflict_count() == 0, 'no conflicts splitting tree-folding symlinks'
        assert os.path.isdir('bin2'), 'tree got split by packages from multiple stow directories'
        assert os.path.isfile('bin2/file2a'), 'file from 1st stow dir'
        assert os.path.isfile('bin2/file2b'), 'file from 2nd stow dir'
