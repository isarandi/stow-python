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
Testing parent()
"""

from testutil import parent


def test_no_leading_or_trailing_slash():
    """no leading or trailing /"""
    assert parent('a/b/c') == 'a/b'


def test_leading_slash():
    """leading /"""
    assert parent('/a/b/c') == '/a/b'


def test_trailing_slash():
    """trailing /"""
    assert parent('a/b/c/') == 'a/b'


def test_multiple_slashes():
    """multiple /"""
    assert parent('/////a///b///c///') == '/a/b'


def test_empty_parent():
    """empty parent"""
    assert parent('a') == ''
