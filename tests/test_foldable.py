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
Testing foldable()
"""

import pytest

from testutil import new_Stow, make_path, make_file, make_link


@pytest.fixture
def stow(stow_test_env):
    """Create a Stow instance for testing."""
    return new_Stow(dir='../stow')


def test_foldable_simple_tree(stow):
    """Can fold a simple tree."""
    make_path('../stow/pkg1/bin1')
    make_file('../stow/pkg1/bin1/file1')
    make_path('bin1')
    make_link('bin1/file1', '../../stow/pkg1/bin1/file1')

    assert stow.foldable('bin1') == '../stow/pkg1/bin1'


def test_foldable_empty_directory(stow):
    """Can't fold an empty directory."""
    make_path('../stow/pkg2/bin2')
    make_file('../stow/pkg2/bin2/file2')
    make_path('bin2')

    assert stow.foldable('bin2') == ''


def test_foldable_dir_with_non_link(stow):
    """Can't fold if dir contains a non-link."""
    make_path('../stow/pkg3/bin3')
    make_file('../stow/pkg3/bin3/file3')
    make_path('bin3')
    make_link('bin3/file3', '../../stow/pkg3/bin3/file3')
    make_file('bin3/non-link')

    assert stow.foldable('bin3') == ''


def test_foldable_links_to_different_dirs(stow):
    """Can't fold if links point to different directories."""
    make_path('bin4')
    make_path('../stow/pkg4a/bin4')
    make_file('../stow/pkg4a/bin4/file4a')
    make_link('bin4/file4a', '../../stow/pkg4a/bin4/file4a')
    make_path('../stow/pkg4b/bin4')
    make_file('../stow/pkg4b/bin4/file4b')
    make_link('bin4/file4b', '../../stow/pkg4b/bin4/file4b')

    assert stow.foldable('bin4') == ''
