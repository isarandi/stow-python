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
Testing cleanup_invalid_links()
"""

from testutil import (
    new_Stow, make_path, make_file, make_link,
    make_invalid_link
)


class TestCleanupInvalidLinks:
    """Tests for cleanup_invalid_links() method."""

    def test_nothing_to_clean_in_simple_tree(self, stow_test_env):
        """Nothing to clean in a simple tree."""
        make_path('../stow/pkg1/bin1')
        make_file('../stow/pkg1/bin1/file1')
        make_link('bin1', '../stow/pkg1/bin1')

        stow = new_Stow()
        stow.cleanup_invalid_links('./')

        assert len(stow.get_tasks()) == 0, 'nothing to clean'

    def test_cleanup_orphaned_owned_link_in_simple_tree(self, stow_test_env):
        """Cleanup an orphaned owned link in a simple tree."""
        make_path('bin2')
        make_path('../stow/pkg2/bin2')
        make_file('../stow/pkg2/bin2/file2a')
        make_link('bin2/file2a', '../../stow/pkg2/bin2/file2a')
        make_invalid_link('bin2/file2b', '../../stow/pkg2/bin2/file2b')

        stow = new_Stow()
        stow.cleanup_invalid_links('bin2')

        assert stow.get_conflict_count() == 0, 'no conflicts cleaning up bad link'
        assert len(stow.get_tasks()) == 1, 'one task cleaning up bad link'
        assert stow.link_task_action('bin2/file2b') == 'remove', 'removal task for bad link'

    def test_dont_cleanup_bad_link_not_owned_by_stow(self, stow_test_env):
        """Don't cleanup a bad link not owned by stow."""
        make_path('bin3')
        make_path('../stow/pkg3/bin3')
        make_file('../stow/pkg3/bin3/file3a')
        make_link('bin3/file3a', '../../stow/pkg3/bin3/file3a')
        make_invalid_link('bin3/file3b', '../../empty')

        stow = new_Stow()
        stow.cleanup_invalid_links('bin3')

        assert stow.get_conflict_count() == 0, \
            'no conflicts cleaning up bad link not owned by stow'
        assert len(stow.get_tasks()) == 0, 'no tasks cleaning up bad link not owned by stow'

    def test_dont_cleanup_valid_link_in_target_not_owned_by_stow(self, stow_test_env):
        """Don't cleanup a valid link in the target not owned by stow."""
        make_path('bin4')
        make_path('../stow/pkg4/bin4')
        make_file('../stow/pkg4/bin4/file3a')
        make_link('bin4/file3a', '../../stow/pkg4/bin4/file3a')
        make_file("unowned")
        make_link('bin4/file3b', '../unowned')

        stow = new_Stow()
        stow.cleanup_invalid_links('bin4')

        assert stow.get_conflict_count() == 0, \
            'no conflicts cleaning up bad link not owned by stow'
        assert len(stow.get_tasks()) == 0, 'no tasks cleaning up bad link not owned by stow'
