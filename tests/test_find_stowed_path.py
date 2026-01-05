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
Testing Stow.find_stowed_path()
"""

from testutil import new_Stow, make_path, make_file, cd
import testutil


class TestFindStowedPath:
    """Tests for find_stowed_path method."""

    def test_find_link_to_stowed_path_with_relative_target(self, stow_test_env):
        """Find link to a stowed path with relative target."""
        # This is a relative path, unlike ABS_TEST_DIR below.
        target = testutil.TEST_DIR + "/target"

        stow = new_Stow(dir=testutil.TEST_DIR + "/stow", target=target)
        result = stow._find_stowed_path("a/b/c", "../../../stow/a/b/c")
        assert result.path == "../stow/a/b/c", "path"
        assert result.stow_dir == "../stow", "stow path"
        assert result.package == "a", "package"

    def test_find_link_to_stowed_path(self, stow_test_env):
        """Find link to a stowed path."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        result = stow._find_stowed_path("a/b/c", "../../../stow/a/b/c")
        assert result.path == "../stow/a/b/c", "path from target directory"
        assert result.stow_dir == "../stow", "stow path from target directory"
        assert result.package == "a", "from target directory"

    def test_find_link_to_alien_path_not_owned_by_stow(self, stow_test_env):
        """Find link to alien path not owned by Stow."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        result = stow._find_stowed_path("a/b/c", "../../alien")
        assert result is None, "alien is not stowed"

    def test_second_stow_dir_still_alien_without_dot_stow(self, stow_test_env):
        """Second stow dir still alien without .stow file."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        # Make a second stow directory within the target directory
        make_path("stow2")

        # This second stow directory is still "alien" until we put a .stow file in it
        result = stow._find_stowed_path("a/b/c", "../../stow2/a/b/c")
        assert result is None, "stow2 not a stow dir yet"

    def test_dot_stow_makes_second_stow_dir_owned_by_stow(self, stow_test_env):
        """.stow makes second stow dir owned by Stow."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        # Make stow2 a secondary stow directory
        make_path("stow2")
        make_file("stow2/.stow")

        result = stow._find_stowed_path("a/b/c", "../../stow2/a/b/c")
        assert result.path == "stow2/a/b/c", "path"
        assert result.stow_dir == "stow2", "stow path"
        assert result.package == "a", "detect alternate stow directory"

    def test_relative_symlink_pointing_to_target_dir(self, stow_test_env):
        """Relative symlink pointing to target dir."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        # Technically the target dir is not owned by Stow, since
        # Stow won't touch the target dir itself, only its contents.
        result = stow._find_stowed_path("a/b/c", "../../..")
        assert result is None, "corner case - link points to target dir"

    def test_relative_symlink_pointing_to_parent_of_target_dir(self, stow_test_env):
        """Relative symlink pointing to parent of target dir."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        result = stow._find_stowed_path("a/b/c", "../../../..")
        assert result is None, "corner case - link points to parent of target dir"

    def test_unowned_symlink_pointing_to_absolute_path_inside_target(
        self, stow_test_env
    ):
        """Unowned symlink pointing to absolute path inside target."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        result = stow._find_stowed_path("a/b/c", testutil.ABS_TEST_DIR + "/target/d")
        assert result is None, "symlink unowned by Stow points to absolute path"

    def test_unowned_symlink_pointing_to_absolute_path_outside_target(
        self, stow_test_env
    ):
        """Unowned symlink pointing to absolute path outside target."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        result = stow._find_stowed_path("a/b/c", "/dev/null")
        assert result is None, "symlink unowned by Stow points to absolute path"

    def test_stow2_becomes_primary_stow_directory(self, stow_test_env):
        """stow2 becomes the primary stow directory."""
        stow = new_Stow(
            dir=testutil.ABS_TEST_DIR + "/stow",
            target=testutil.ABS_TEST_DIR + "/target",
        )
        cd(testutil.ABS_TEST_DIR + "/target")

        # Make stow2 directory with .stow marker
        make_path("stow2")
        make_file("stow2/.stow")

        # Now make stow2 the primary stow directory
        stow.stow_dir = testutil.ABS_TEST_DIR + "/target/stow2"

        result = stow._find_stowed_path("a/b/c", "../../stow2/a/b/c")
        assert result.path == "stow2/a/b/c", "path in stow2"
        assert result.stow_dir == "stow2", "stow path for stow2"
        assert result.package == "a", "stow2 is subdir of target directory"
