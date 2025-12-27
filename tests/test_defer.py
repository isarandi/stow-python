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
Testing defer()
"""

from testutil import new_Stow


def test_defer_simple_success(stow_test_env):
    """Simple success: path matches defer pattern."""
    stow = new_Stow(defer=['man'])
    assert stow.defer('man/man1/file.1')


def test_defer_simple_failure(stow_test_env):
    """Simple failure: path does not match defer pattern."""
    stow = new_Stow(defer=['lib'])
    assert not stow.defer('man/man1/file.1')


def test_defer_complex_success(stow_test_env):
    """Complex success: path matches one of multiple defer patterns."""
    stow = new_Stow(defer=['lib', 'man', 'share'])
    assert stow.defer('man/man1/file.1')


def test_defer_complex_failure(stow_test_env):
    """Complex failure: path does not match any of multiple defer patterns."""
    stow = new_Stow(defer=['lib', 'man', 'share'])
    assert not stow.defer('bin/file')
