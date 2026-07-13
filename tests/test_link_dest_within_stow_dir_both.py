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
Black-box oracle tests for link ownership detection (link_dest_within_stow_dir).

The Perl t/link_dest_within_stow_dir.t unit-tests the internal method that
determines if a symlink points into the stow directory (owned by stow)
or elsewhere (not owned). It tests these scenarios:

1. "../stow/pkg/dir/file" with relative stow dir → (pkg, dir/file)
2. "../stow/pkg/dir/subdir/file" with relative stow dir → (pkg, dir/subdir/file)
3. "../stow/pkg/dir/file" with absolute stow dir → (pkg, dir/file)
4. "../stow/pkg/dir/subdir/file" with absolute stow dir → (pkg, dir/subdir/file)
5. "./alien" → ("", "") - link to target, not owned
6. "../alien" → ("", "") - link outside, not owned

These CLI tests exercise the same logic by pre-creating symlinks and
observing behavior:
- Owned link → restow succeeds
- Not-owned link → conflict reported
"""

import os

from conftest import run_both_tests, check_link


class TestLinkDestWithinStowDirBoth:
    """Oracle tests for link ownership detection via CLI behavior."""

    def test_link_to_stow_pkg_top_level_is_owned(self, stow_env):
        """Link ../stow/pkg/dir/file is recognized as owned by pkg.

        Perl: "../stow/pkg/dir/file" → (pkg, dir/file)
        Observable: restow succeeds, link preserved.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../../stow/pkg/dir/file")

        def check(env):
            check_link(env, "dir/file", "../../stow/pkg/dir/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_link_to_stow_pkg_second_level_is_owned(self, stow_env):
        """Link ../stow/pkg/dir/subdir/file is recognized as owned.

        Perl: "../stow/pkg/dir/subdir/file" → (pkg, dir/subdir/file)
        Observable: restow succeeds, link preserved.
        """
        stow_env.create_package("pkg", {"dir/subdir/file": "content"})

        def setup():
            stow_env.create_target_dir("dir/subdir")
            stow_env.create_target_link(
                "dir/subdir/file", "../../../stow/pkg/dir/subdir/file"
            )

        def check(env):
            check_link(env, "dir/subdir/file", "../../../stow/pkg/dir/subdir/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_link_to_target_is_not_owned(self, stow_env):
        """Link ./alien (pointing within target) is NOT owned by stow.

        Perl: "./alien" → ("", "")
        Observable: stow reports conflict, link unchanged.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            stow_env.create_target_file("alien", "alien content")
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../alien")

        def check(env):
            # Conflict reported, link unchanged
            check_link(env, "dir/file", "../alien")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_link_outside_target_and_stow_is_not_owned(self, stow_env):
        """Link ../alien (outside target and stow) is NOT owned.

        Perl: "../alien" → ("", "")
        Observable: stow reports conflict, link unchanged.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            alien_path = os.path.join(stow_env.tmpdir, "alien")
            with open(alien_path, "w") as f:
                f.write("alien outside")
            stow_env.create_target_link("file", "../alien")

        def check(env):
            # Conflict reported, link unchanged
            check_link(env, "file", "../alien")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            compare_fs_ops=True,
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

        def check(env):
            # Conflict reported, link unchanged (still points to pkg1)
            check_link(env, "bin", "../stow/pkg1/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg2"],
            setup,
            check,
            compare_fs_ops=True,
        )

    def test_absolute_stow_dir_link_recognized(self, stow_env):
        """With absolute stow dir, relative link still recognized as owned.

        Perl tests 3-4: absolute stow dir with "../stow/pkg/..." links
        Observable: restow succeeds, link preserved.
        """
        stow_env.create_package("pkg", {"dir/file": "content"})

        def setup():
            stow_env.create_target_dir("dir")
            stow_env.create_target_link("dir/file", "../../stow/pkg/dir/file")

        def check(env):
            check_link(env, "dir/file", "../../stow/pkg/dir/file")

        abs_stow_dir = os.path.abspath(stow_env.stow_dir)
        run_both_tests(
            stow_env,
            ["-d", abs_stow_dir, "-t", stow_env.target_dir, "-R", "pkg"],
            setup,
            check,
            compare_fs_ops=True,
        )
