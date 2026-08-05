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
    assert_stow_match,
    assert_stow_match_with_fs_ops,
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
        # Don't compare fs_ops - RC file handling has known syscall differences
        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=False,
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
            compare_fs_ops=False,
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
            compare_fs_ops=False,
        )

    def test_cwd_stowrc_overrides_home(self, stow_env):
        """Test that .stowrc in cwd overrides ~/.stowrc."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        # Create ~/.stowrc with wrong target
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write(f"--target=/nonexistent/should/be/overridden\n")

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
            compare_fs_ops=False,
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
            compare_fs_ops=False,
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
            compare_fs_ops=False,
        )

    def test_stowrc_with_non_utf8_bytes(self, stow_env):
        """A .stowrc holding non-UTF-8 bytes is read like Perl reads bytes."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "wb") as f:
            f.write(b"-d " + stow_env.stow_dir.encode() + b"\n")
            f.write(b"--target=" + stow_env.target_dir.encode() + b"\n")
            f.write(b"--ignore=\xff\n")

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
            compare_fs_ops=False,
        )

    def test_stowrc_brace_without_variable_name_stays_literal(self, stow_env):
        """A brace group that is not a bare variable name is left as it is."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write("--target=${TQZ-x}\n")

        def setup():
            pass

        # ${TQZ-x} is not a variable reference, so it survives expansion and
        # is reported verbatim as the invalid directory it is
        run_both_tests(
            stow_env,
            ["pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

    def test_home_of_zero_falls_through_to_logdir(self, stow_env):
        """A HOME of "0" is false, so ~ expands from LOGDIR instead.

        Perl picks the home directory with
        $ENV{HOME} || $ENV{LOGDIR} || (getpwuid($<))[7].
        """
        stow_env.create_package("pkg", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write("--target ~\n")

        def setup():
            pass

        _rc, _stdout, _stderr, state = assert_stow_match(
            stow_env,
            ["pkg"],
            setup,
            env={"HOME": "0", "LOGDIR": stow_env.target_dir},
        )
        assert state["bin"] == ("link", "../stow/pkg/bin")

    def test_tilde_user_named_zero_takes_bare_tilde_branch(self, stow_env):
        """~0 expands from HOME, because the captured name "0" is false.

        Perl chooses between (getpwnam($1))[7] and the HOME chain with
        "$1 ? ... : ...", so a user name of "0" never reaches getpwnam.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write("--target ~0\n")

        def setup():
            pass

        _rc, _stdout, _stderr, state = assert_stow_match(
            stow_env, ["pkg"], setup, env={"HOME": stow_env.target_dir}
        )
        assert state["bin"] == ("link", "../stow/pkg/bin")

    def test_empty_home_still_probes_root_stowrc(self, stow_env):
        """An empty but set HOME is still interpolated into "$HOME/.stowrc".

        Perl guards that probe with defined($ENV{HOME}), so it looks for
        "/.stowrc" rather than skipping the home config entirely. Only the
        syscall trace shows it.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        assert_stow_match_with_fs_ops(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            env={"HOME": ""},
        )

    def test_tilde_unknown_user_expands_to_empty(self, stow_env):
        """~nosuchuser expands to nothing, after a warning.

        Perl's getpwnam returns the empty list for an unknown user, so the
        substitution interpolates an undefined value.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write("--target ~nosuchuser-xyzzy/t\n")

        def setup():
            pass

        rc, _stdout, stderr, _state = assert_stow_match(stow_env, ["pkg"], setup)
        assert rc == 1
        assert stderr.startswith(
            "Use of uninitialized value in substitution iterator\n"
            "stow: --target value '/t' is not a valid directory\n"
        )
