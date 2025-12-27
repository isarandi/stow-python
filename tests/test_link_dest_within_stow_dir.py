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
Testing Stow.link_dest_within_stow_dir()
"""

import testutil
from testutil import new_Stow


class TestLinkDestWithinStowDir:
    """Tests for link_dest_within_stow_dir() method."""

    def test_relative_stow_dir_link_to_top_level_package_file(self, stow_test_env):
        """Relative stow dir, link to top-level package file."""
        # This is a relative path, unlike ABS_TEST_DIR
        stow = new_Stow(dir=testutil.TEST_DIR + "/stow", target=testutil.TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("../stow/pkg/dir/file")
        assert package == "pkg", "package"
        assert path == "dir/file", "path"

    def test_relative_stow_dir_link_to_second_level_package_file(self, stow_test_env):
        """Relative stow dir, link to second-level package file."""
        stow = new_Stow(dir=testutil.TEST_DIR + "/stow", target=testutil.TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("../stow/pkg/dir/subdir/file")
        assert package == "pkg", "package"
        assert path == "dir/subdir/file", "path"

    def test_absolute_stow_dir_link_to_top_level_package_file(self, stow_test_env):
        """Absolute stow dir, link to top-level package file."""
        # This is an absolute path, unlike TEST_DIR
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow", target=testutil.ABS_TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("../stow/pkg/dir/file")
        assert package == "pkg", "package"
        assert path == "dir/file", "path"

    def test_absolute_stow_dir_link_to_second_level_package_file(self, stow_test_env):
        """Absolute stow dir, link to second-level package file."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow", target=testutil.ABS_TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("../stow/pkg/dir/subdir/file")
        assert package == "pkg", "package"
        assert path == "dir/subdir/file", "path"

    def test_link_to_path_in_target(self, stow_test_env):
        """Link to path in target.

        Links with destination in the target are not pointing within
        the stow dir, so they're not owned by stow.
        """
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow", target=testutil.ABS_TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("./alien")
        assert path == "", "alien is in target, so path is empty"
        assert package == "", "alien is in target, so package is empty"

    def test_link_to_path_outside_target_and_stow_dir(self, stow_test_env):
        """Link to path outside target and stow dir."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow", target=testutil.ABS_TEST_DIR + "/target")

        package, path = stow.link_dest_within_stow_dir("../alien")
        assert path == "", "alien is outside, so path is empty"
        assert package == "", "alien is outside, so package is empty"
