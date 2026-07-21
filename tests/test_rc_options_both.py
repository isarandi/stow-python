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
Black-box oracle tests for .stowrc file handling.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results

Based on Perl t/rc_options.t
"""

import os

from conftest import (
    check_link,
    run_both_tests,
)


class TestRcOptionsBoth:
    """Test .stowrc handling - black-box comparison of both implementations."""

    def test_home_stowrc_paths(self, stow_env):
        """Test that ~/.stowrc --dir and --target are used."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        # Create ~/.stowrc with dir and target
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={stow_env.target_dir}\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        # Note: run from stow_dir (where .stowrc -d points)
        # The stowrc provides --dir and --target, so just pass package name
        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowrc_defer_option(self, stow_env):
        """Test --defer in .stowrc."""
        stow_env.create_package("pkg1", {"man/file": "first"})
        stow_env.create_package("pkg2", {"man/file": "second"})

        # Create ~/.stowrc with defer
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={stow_env.target_dir}\n")
            f.write("--defer=man\n")

        def setup():
            stow_env.create_target_dir("man")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # pkg1's file should remain (pkg2 deferred via rc)
            check_link(env, "man/file", "../../stow/pkg1/man/file")

        run_both_tests(
            stow_env,
            ["pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_stowrc_ignore_option(self, stow_env):
        """Test --ignore in .stowrc."""
        stow_env.create_package(
            "pkg",
            {
                "bin/keep": "keep",
                "bin/skip.bak": "skip",
            },
        )

        # Create ~/.stowrc with ignore
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={stow_env.target_dir}\n")
            f.write("--ignore=\\.bak\n")

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            check_link(env, "bin/keep", "../../stow/pkg/bin/keep")
            assert not os.path.exists(os.path.join(env.target_dir, "bin", "skip.bak"))

        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_cwd_stowrc_overrides_home(self, stow_env):
        """Test that .stowrc in cwd overrides ~/.stowrc."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        # Create ~/.stowrc with wrong target
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write("--target=/nonexistent/should/be/overridden\n")

        # Create .stowrc in stow_dir (cwd) with correct target
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write(f"--target={stow_env.target_dir}\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_cli_overrides_stowrc(self, stow_env):
        """Test that CLI options override .stowrc."""
        stow_env.create_package("pkg", {"file": "content"})

        # Wrong target in stowrc
        wrong_target = os.path.join(stow_env.tmpdir, "wrong_target")
        os.makedirs(wrong_target)
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={wrong_target}\n")

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        # CLI --target should override stowrc
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowrc_with_verbose(self, stow_env):
        """Test verbose option in .stowrc."""
        stow_env.create_package("pkg", {"file": "content"})

        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={stow_env.target_dir}\n")
            f.write("-v\n")

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_nonword_brace_expansion_stays_literal(self, stow_env):
        """A ${...} whose braces contain non-word characters (e.g. the
        shell-ism ${VAR-default}) is NOT expanded by either side: Perl's
        rc expansion regex only accepts [\\w\\s]+ between the braces, and
        Python replicates that. With a directory literally named
        '${TQZ-x}' as the target, both implementations stow into it."""
        import shutil

        from conftest import assert_stow_match

        stow_env.create_package("pkg", {"file": "content"})
        literal_target = os.path.join(stow_env.tmpdir, "${TQZ-x}")

        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target={literal_target}\n")

        def setup():
            shutil.rmtree(literal_target, ignore_errors=True)
            os.makedirs(literal_target)

        assert_stow_match(stow_env, ["pkg"], setup)
        assert os.path.islink(os.path.join(literal_target, "file"))
