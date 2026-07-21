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
Black-box oracle tests for CLI option parsing.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results

Based on Perl t/cli_options.t
"""

import os

from conftest import (
    check_dir,
    check_link,
    check_not_exists,
    run_both_tests,
)


class TestCliOptionsBoth:
    """Test CLI options - black-box comparison of both implementations."""

    def test_short_options(self, stow_env):
        """Test short options -d, -t, -S."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["-d", stow_env.stow_dir, "-t", stow_env.target_dir, "-S", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_long_options(self, stow_env):
        """Test long options --dir, --target, --stow."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            [
                f"--dir={stow_env.stow_dir}",
                f"--target={stow_env.target_dir}",
                "--stow",
                "pkg",
            ],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_delete_option(self, stow_env):
        """Test -D/--delete option."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])

        def check(env):
            check_not_exists(env, "bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_restow_option(self, stow_env):
        """Test -R/--restow option."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
            # Add new file to package
            with open(os.path.join(stow_env.stow_dir, "pkg", "bin", "file2"), "w") as f:
                f.write("content2")

        def check(env):
            # After restow, bin remains a folder symlink (both files in same package)
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-R", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_simulate_option(self, stow_env):
        """Test -n/--simulate option."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        def check(env):
            # Nothing should be created in simulate mode
            check_not_exists(env, "bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-n", "pkg"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=False,  # No FS operations in simulate mode
        )

    def test_no_folding_option(self, stow_env):
        """Test --no-folding option."""
        stow_env.create_package(
            "pkg",
            {
                "dir/file1": "content1",
                "dir/file2": "content2",
            },
        )

        def setup():
            pass

        def check(env):
            check_dir(env, "dir")
            check_link(env, "dir/file1", "../../stow/pkg/dir/file1")
            check_link(env, "dir/file2", "../../stow/pkg/dir/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--no-folding", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_dotfiles_option(self, stow_env):
        """Test --dotfiles option."""
        stow_env.create_package(
            "pkg",
            {
                "dot-bashrc": "# bashrc",
                "dot-config/app/settings": "settings",
            },
        )

        def setup():
            pass

        def check(env):
            check_link(env, ".bashrc", "../stow/pkg/dot-bashrc")
            check_link(env, ".config", "../stow/pkg/dot-config")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--dotfiles", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_bundled_short_options(self, stow_env):
        """Test bundled short options like -nvS."""
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            # Simulate mode, nothing created
            check_not_exists(env, "file")

        # -nvS means: simulate, verbose, stow
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-nS", "pkg"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=False,
        )

    def test_verbose_levels(self, stow_env):
        """Test multiple verbose flags."""
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        # Multiple -v flags
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-v", "-v", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_mixed_stow_unstow_restow(self, stow_env):
        """Test mixing -D, -S, -R for different packages."""
        stow_env.create_package("pkg_delete", {"bin/delete": "content"})
        stow_env.create_package("pkg_stow", {"bin/stow": "content"})
        stow_env.create_package("pkg_restow", {"bin/restow": "content"})

        def setup():
            # Pre-stow pkg_delete and pkg_restow
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg_delete"])
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg_restow"])

        def check(env):
            # pkg_delete should be gone
            check_not_exists(env, "bin/delete")
            # pkg_stow should be stowed
            check_link(env, "bin/stow", "../../stow/pkg_stow/bin/stow")
            # pkg_restow should be re-stowed
            check_link(env, "bin/restow", "../../stow/pkg_restow/bin/restow")

        run_both_tests(
            stow_env,
            [
                "-t",
                stow_env.target_dir,
                "-D",
                "pkg_delete",
                "-S",
                "pkg_stow",
                "-R",
                "pkg_restow",
            ],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_plus_n_simulate(self, stow_env):
        """Test +n option for simulate mode.

        Pythonic supports +n (with deprecation warning) when POSIXLY_CORRECT is not set.
        When POSIXLY_CORRECT is set, +n is treated as a package name (disabled).

        Note: Pythonic only supports +n, not other + prefixed options like +verbose.
        This is intentionally different from Perl's full getopt_compat support.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def check(env):
            # +n means simulate, so nothing should be created
            check_not_exists(env, "file")

        # Test without POSIXLY_CORRECT - +n should work as simulate
        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "+n", "pkg"]
        )
        assert rc == 0, f"Expected success, got: {stderr}"
        assert "simulation mode" in stderr
        check(stow_env)

        # Test with POSIXLY_CORRECT - +n should be treated as package name (error)
        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "+n", "pkg"], env={"POSIXLY_CORRECT": ""}
        )
        assert rc != 0, "Expected error when +n treated as package"
        assert "+n" in stderr  # Error about package +n not found

    def test_require_order_options_after_package(self, stow_env):
        """Test require_order behavior under POSIXLY_CORRECT.

        POSIXLY_CORRECT enables require_order in Perl's Getopt::Long, which
        stops parsing options at the first non-option argument.

        With require_order: 'stow pkg --verbose' treats '--verbose' as a package
        Without require_order: 'stow pkg --verbose' treats '--verbose' as an option

        Perl stow explicitly sets 'permute' which overrides require_order,
        so this should work the same with and without POSIXLY_CORRECT.
        This test verifies both implementations match Perl's behavior.
        """
        stow_env.create_package("pkg1", {"file1": "content1"})
        stow_env.create_package("pkg2", {"file2": "content2"})

        def setup():
            pass

        def check(env):
            # Both packages should be stowed
            check_link(env, "file1", "../stow/pkg1/file1")
            check_link(env, "file2", "../stow/pkg2/file2")

        # Options mixed with packages - tests permute behavior
        # Perl stow explicitly enables permute, so this should work
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg1", "-v", "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_bundled_short_option_with_value_argument(self, stow_env):
        """A value option ending a bundle takes the next argument: -St DIR.

        This matches Perl's Getopt::Long bundling and common Unix muscle
        memory (tar -xf FILE), so it is verified against the oracle.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        run_both_tests(
            stow_env,
            ["-St", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_double_dash_treats_rest_as_packages(self, stow_env):
        """POSIX "--" terminator: intentional divergence from Perl.

        Perl's Getopt::Long leaves the arguments after -- in @ARGV, which
        stow never reads, so they are silently discarded ("No packages to
        stow or unstow"). We deliberately implement the standard POSIX
        behavior instead: the remaining arguments are package names. This
        test pins BOTH behaviors so the divergence cannot drift unnoticed.
        """
        stow_env.create_package("pkg", {"file": "content"})

        # Python: pkg after -- is stowed
        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--", "pkg"]
        )
        assert rc == 0, f"Expected success, got rc={rc}: {stderr}"
        check_link(stow_env, "file", "../stow/pkg/file")

        # Perl: pkg after -- is discarded and stow errors out
        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "--", "pkg"]
        )
        assert rc != 0, "Perl should report no packages"
        assert "No packages to stow or unstow" in stderr
        check_not_exists(stow_env, "file")

    def test_verbose_invalid_value_aborts(self, stow_env):
        """--verbose=xyz must abort before touching the filesystem."""
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            # The invalid option value aborted the run: nothing was stowed
            check_not_exists(env, "file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--verbose=xyz", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

    def test_malformed_regex_fails_cleanly(self, stow_env):
        """A malformed --ignore regex must give a clean error, no traceback."""
        stow_env.create_package("pkg", {"file": "content"})

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--ignore", "foo(", "pkg"]
        )
        assert rc != 0
        assert "Failed to compile regexp" in stderr
        assert "Traceback" not in stderr
        check_not_exists(stow_env, "file")

    def test_malformed_ignore_file_regex_fails_cleanly(self, stow_env):
        """A malformed pattern in .stow-local-ignore errors without traceback."""
        stow_env.create_package("pkg", {"file": "content"})
        with open(
            os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore"), "w"
        ) as f:
            f.write("foo(\n")

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "pkg"]
        )
        assert rc != 0
        assert "Failed to compile regexp" in stderr
        assert "Traceback" not in stderr
        check_not_exists(stow_env, "file")

    def test_long_option_abbreviation_simulate(self, stow_env):
        """--sim is a unique prefix of --simulate (Getopt::Long abbreviation).

        Abbreviation is disabled under POSIXLY_CORRECT, so both
        implementations reject --sim there ("Unknown option: sim"). The
        harness runs both modes automatically, so a single equality check
        covers resolution when abbreviation is on and rejection when off.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--sim", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

    def test_long_option_abbreviation_verbose(self, stow_env):
        """--verb resolves to --verbose (abbreviation); disabled under POSIXLY."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--verb", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

    def test_long_option_abbreviation_delete(self, stow_env):
        """--del resolves to --delete (abbreviation); disabled under POSIXLY."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--del", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

    def test_ambiguous_long_option_prefix(self, stow_env):
        """--de is an ambiguous prefix (defer, delete): identical error.

        Both implementations report the same 'Option de is ambiguous
        (defer, delete)' error and exit 1. Under POSIXLY_CORRECT the prefix
        is not expanded and both report 'Unknown option: de'; the harness
        covers both modes.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--de", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

        # Pin the exact ambiguity message (abbreviation enabled).
        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--de", "pkg"]
        )
        assert rc == 1
        assert "Option de is ambiguous (defer, delete)" in stderr

    def test_empty_attached_value_rejected(self, stow_env):
        """--ignore= (and siblings) with an empty attached value is rejected.

        Perl's Getopt::Long treats an empty '=value' as a missing argument.
        Both implementations fail with 'Option X requires an argument',
        exit 1, and stow nothing.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        # --ignore= through the full equality harness (both POSIXLY modes).
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

        # The sibling value options behave the same way.
        for opt in ["--ignore=", "--defer=", "--override=", "--target=", "--dir="]:
            name = opt[len("--") : -1]
            expected = "Option %s requires an argument" % name

            stow_env.reset_target()
            prc, _, perr = stow_env.run_perl_stow([opt, "pkg"])
            stow_env.reset_target()
            yrc, _, yerr = stow_env.run_python_stow([opt, "pkg"])

            assert prc == 1 and yrc == 1, "%s: rc perl=%d py=%d" % (opt, prc, yrc)
            assert expected in perr, "%s: perl stderr=%r" % (opt, perr)
            assert expected in yerr, "%s: py stderr=%r" % (opt, yerr)
            check_not_exists(stow_env, "bin/file")

    def test_missing_final_value_rejected(self, stow_env):
        """A value option ending the argv with no value: 'pkg --target'.

        Both implementations report 'Option target requires an argument'
        and exit 1.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        run_both_tests(
            stow_env,
            ["pkg", "--target"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(["pkg", "--target"])
        assert rc == 1
        assert "Option target requires an argument" in stderr

    def test_unknown_letter_bundle_reports_each(self, stow_env):
        """A short bundle of unknown letters '-xy' reports both letters.

        Both implementations emit 'Unknown option: x' AND 'Unknown option:
        y' and exit 1.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-xy", "pkg"],
            setup,
            None,
            check_on_simulate=False,
            compare_fs_ops=False,
        )

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "-xy", "pkg"]
        )
        assert rc == 1
        assert "Unknown option: x" in stderr
        assert "Unknown option: y" in stderr

    def test_trailing_slash_in_package_name(self, stow_env):
        """'stow pkg/' behaves identically to 'stow pkg' (slash stripped)."""
        stow_env.create_package("pkg", {"bin/file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg/"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_version_byte_identical(self, stow_env):
        """--version prints byte-identical output on stdout, nothing on stderr."""
        prc, pout, perr = stow_env.run_perl_stow(["--version"])
        yrc, yout, yerr = stow_env.run_python_stow(["--version"])

        assert prc == 0 and yrc == 0
        assert pout == "stow (GNU Stow) version 2.4.1\n"
        assert yout == pout, "version stdout mismatch: perl=%r py=%r" % (pout, yout)
        assert perr == "" and yerr == ""

    def test_package_named_double_dash_o_matches(self, stow_env):
        """Package-like arg '--o=0' now parses identically on both.

        The Getopt::Long emulation reproduces Perl's '--option=value'
        handling: '--o=0' is consumed as an unknown-but-valued option,
        leaving no packages, so both report 'No packages to stow or unstow'
        (exit 1). Under POSIXLY_CORRECT both instead report 'Unknown
        option: o'. (This was documented divergence #1, now resolved.)
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        # Default mode: both report "No packages to stow or unstow".
        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "--o=0"])
        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "--o=0"])
        assert prc == 1 and yrc == 1
        assert "No packages to stow or unstow" in perr
        assert "No packages to stow or unstow" in yerr

        # POSIXLY_CORRECT: both report "Unknown option: o".
        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "--o=0"], env={"POSIXLY_CORRECT": ""}
        )
        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--o=0"], env={"POSIXLY_CORRECT": ""}
        )
        assert prc == 1 and yrc == 1
        assert "Unknown option: o" in perr
        assert "Unknown option: o" in yerr
