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
Oracle tests for link ownership detection (link_dest_within_stow_dir).

The Perl t/link_dest_within_stow_dir.t tests the internal method that
determines if a symlink points into the stow directory (owned by stow)
or elsewhere (not owned).

These tests exercise the same logic via CLI by pre-creating symlinks
and observing whether stow treats them as owned (no conflict, restow ok)
or not owned (conflict reported).

Perl test scenarios:
1. "../stow/pkg/dir/file" → owned (package=pkg, path=dir/file)
2. "../stow/pkg/dir/subdir/file" → owned (package=pkg, path=dir/subdir/file)
3. "./alien" → not owned (points within target)
4. "../alien" → not owned (points outside target and stow)
"""

import os

from conftest import assert_stow_match_with_fs_ops


class TestLinkDestWithinStowDirBoth:
    """Oracle tests for link ownership detection via CLI behavior."""

    def test_link_to_stow_pkg_top_level_is_owned(self, stow_env):
        """Link ../stow/pkg/dir/file is recognized as owned by pkg.

        Corresponds to Perl: "../stow/pkg/dir/file" → (pkg, dir/file)
        Observable: restow succeeds without conflict.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            # Pre-create the symlink as if already stowed
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../../stow/pkg/dir/file")

        # Restow should recognize link as owned - no conflict, success
        # Also compare filesystem operations via strace
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "-R", "pkg"], setup
        )

    def test_link_to_stow_pkg_second_level_is_owned(self, stow_env):
        """Link ../stow/pkg/dir/subdir/file is recognized as owned.

        Corresponds to Perl: "../stow/pkg/dir/subdir/file" → (pkg, dir/subdir/file)
        """
        stow_env.create_package("pkg", {"dir/subdir/file": "content"})

        def setup():
            stow_env.create_target_dir("dir/subdir")
            stow_env.create_target_link("dir/subdir/file",
                                        "../../../stow/pkg/dir/subdir/file")

        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "-R", "pkg"], setup
        )

    def test_link_to_target_is_not_owned(self, stow_env):
        """Link ./alien (pointing within target) is NOT owned by stow.

        Corresponds to Perl: "./alien" → ("", "")
        Observable: stow reports conflict.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            # Create alien file in target and link pointing to it
            stow_env.create_target_file("alien", "alien content")
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../alien")

        # Stow should see link as not-owned → conflict
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "pkg"], setup
        )

    def test_link_outside_target_and_stow_is_not_owned(self, stow_env):
        """Link ../alien (outside target and stow) is NOT owned.

        Corresponds to Perl: "../alien" → ("", "")
        Observable: stow reports conflict.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            # Create link pointing outside (to parent of target)
            # Since target is inside tmpdir, ../alien would be in tmpdir
            alien_path = os.path.join(stow_env.tmpdir, "alien")
            with open(alien_path, "w") as f:
                f.write("alien outside")
            stow_env.create_target_link("file", "../alien")

        # Stow should see link as not-owned → conflict
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "pkg"], setup
        )

    def test_link_to_different_package_is_owned_but_conflicts(self, stow_env):
        """Link to different stow package is owned but causes conflict.

        The link IS recognized as owned by stow (points into stow dir),
        but since it's a different package, stow reports conflict.
        """
        stow_env.create_package("pkg1", {"bin/tool": "pkg1 content"})
        stow_env.create_package("pkg2", {"bin/tool": "pkg2 content"})

        def setup():
            # Pre-stow pkg1
            stow_env.create_target_link("bin", "../stow/pkg1/bin")

        # Stowing pkg2 should conflict (link owned by different package)
        assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "pkg2"], setup
        )

    def test_absolute_stow_dir_link_recognized(self, stow_env):
        """With absolute stow dir, relative link still recognized as owned.

        Tests that ownership detection works regardless of whether stow
        dir was specified as relative or absolute path.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../../stow/pkg/dir/file")

        # Use absolute path for stow dir
        abs_stow_dir = os.path.abspath(stow_env.stow_dir)
        assert_stow_match_with_fs_ops(
            stow_env,
            ["-d", abs_stow_dir, "-t", stow_env.target_dir, "-R", "pkg"],
            setup,
        )
