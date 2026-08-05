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
import pwd
import shutil
import subprocess
import sys

import pytest

from conftest import (
    PERL_LIB,
    PERL_STOW,
    PYTHON_STOW,
    assert_stow_match,
    assert_stow_match_raw,
    assert_stow_match_with_fs_ops,
    check_dir,
    check_link,
    check_not_exists,
    normalize_newline_warnings,
    normalize_stow_output,
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
            [f"--dir={stow_env.stow_dir}", f"--target={stow_env.target_dir}", "--stow", "pkg"],
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
            ["-t", stow_env.target_dir, "-D", "pkg_delete", "-S", "pkg_stow", "-R", "pkg_restow"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_plus_prefix_simulate(self, stow_env):
        """Test + prefix for options (Perl's getopt_compat mode).

        POSIXLY_CORRECT disables + prefix in Perl's Getopt::Long.
        This test verifies both implementations match under both settings.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            # +n means simulate, so nothing should be created
            check_not_exists(env, "file")

        # +n is equivalent to -n (simulate mode)
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "+n", "pkg"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=False,
        )

    def test_plus_prefix_verbose(self, stow_env):
        """Test +verbose option (Perl's getopt_compat mode).

        Without POSIXLY_CORRECT, +verbose is equivalent to --verbose and the
        package gets stowed. With POSIXLY_CORRECT set, Getopt::Long disables
        the + prefix entirely, so +verbose is taken as a (nonexistent)
        package name and nothing is stowed.
        """
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        def check_posixly(env):
            # +verbose was treated as a package name: no link was made
            check_not_exists(env, "file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "+verbose", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
            check_func_posixly=check_posixly,
        )

    def test_plus_prefix_value_options(self, stow_env):
        """+t/+ignore take a space-separated value (Getopt::Long getopt_compat).

        With POSIXLY_CORRECT set, the + forms are all read as package names,
        no target is set, and nothing lands in the test target dir.
        """
        stow_env.create_package("pkg", {"file": "content", "ignoreme": "x"})

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")
            check_not_exists(env, "ignoreme")

        def check_posixly(env):
            check_not_exists(env, "file")
            check_not_exists(env, "ignoreme")

        run_both_tests(
            stow_env,
            ["+t", stow_env.target_dir, "+ignore", "ignoreme", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
            check_func_posixly=check_posixly,
        )

    def test_verbose_level_as_next_argument(self, stow_env):
        """-v 2 consumes a following integer argument as the verbosity level."""
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "file", "../stow/pkg/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-v", "2", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_bundled_short_option_with_value_argument(self, stow_env):
        """A value option ending a bundle takes the next argument: -St DIR."""
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

    def test_double_dash_discards_remaining_arguments(self, stow_env):
        """Arguments after -- are left in @ARGV and ignored by Perl stow."""
        stow_env.create_package("pkg", {"file": "content"})

        def setup():
            pass

        def check(env):
            # pkg came after --, so it was never stowed
            check_not_exists(env, "file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

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

    def test_malformed_regex_option_warns_then_usage(self, stow_env):
        """A pattern the regex engine rejects is a Getopt::Long handler
        failure: one warning line on stderr, the usage message on stdout,
        exit status 1, nothing stowed. Only the engine's wording of the
        complaint differs between Perl and Python."""
        stow_env.create_package("pkg", {"file": "content"})

        for option in ("--ignore=foo(", "--override=foo(", "--defer=foo("):
            args = ["-t", stow_env.target_dir, option, "pkg"]

            stow_env.reset_target()
            perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_stow(args)
            check_not_exists(stow_env, "file")

            stow_env.reset_target()
            python_rc, python_stdout, python_stderr = stow_env.run_python_stow(args)
            check_not_exists(stow_env, "file")

            assert perl_rc == python_rc == 1
            assert normalize_stow_output(python_stdout) == perl_stdout
            assert "SYNOPSIS:" in perl_stdout
            assert len(perl_stderr.splitlines()) == 1
            assert len(python_stderr.splitlines()) == 1

    def test_inline_flag_regex_option(self, stow_env):
        """Perl accepts a leading inline flag group in these patterns and
        applies it to the whole pattern."""
        stow_env.create_package("pkgi", {"MAN/f": "content", "man/g": "content"})

        def setup():
            pass

        def check(env):
            check_not_exists(env, "MAN")
            check_not_exists(env, "man")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=(?i)MAN", "pkgi"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_dir_whose_parent_is_zero_targets_cwd(self, stow_env):
        """The default target is Perl's parent($dir) || '.', so a stow dir
        whose parent is the string "0" targets the current directory. The
        link destination still carries the "0/" prefix."""
        pkg_root = os.path.join(stow_env.stow_dir, "0", "sub", "pkg")
        link = os.path.join(stow_env.stow_dir, "file.txt")

        def run_once(run, args, env):
            shutil.rmtree(os.path.join(stow_env.stow_dir, "0"), ignore_errors=True)
            if os.path.islink(link):
                os.unlink(link)
            os.makedirs(pkg_root)
            with open(os.path.join(pkg_root, "file.txt"), "w") as fh:
                fh.write("content")
            rc, stdout, stderr = run(args, env)
            dest = os.readlink(link) if os.path.islink(link) else None
            return rc, stdout, stderr, dest

        for args, env in (
            (["--dir", "0/sub", "pkg"], None),
            (["pkg"], {"STOW_DIR": "0/sub"}),
        ):
            perl = run_once(stow_env.run_perl_stow, args, env)
            python = run_once(stow_env.run_python_stow, args, env)
            assert perl == python
            assert perl == (0, "", "", "0/sub/pkg/file.txt")

    def test_home_of_zero_falls_through_to_logdir(self, stow_env):
        """Perl expands a bare ~ via $ENV{HOME} || $ENV{LOGDIR} || the passwd
        entry, and the string "0" is false at every step of that chain."""
        stow_env.create_package("pkgl", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as fh:
            fh.write("--target=~\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkgl/bin")

        run_both_tests(
            stow_env,
            ["pkgl"],
            setup,
            check,
            compare_fs_ops=True,
            env_vars={"HOME": "0", "LOGDIR": stow_env.target_dir},
        )

    def test_home_and_logdir_of_zero_fall_through_to_passwd(self, stow_env):
        """With both false, the chain ends at the passwd home directory,
        which is what the rejected target path is built from."""
        stow_env.create_package("pkgp", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as fh:
            fh.write("--target=~/no-such-directory-for-stow-python\n")

        def setup():
            pass

        rc, stdout, stderr, state = assert_stow_match(
            stow_env, ["pkgp"], setup, env={"HOME": "0", "LOGDIR": "0"}
        )
        assert rc == 1
        assert "SYNOPSIS:" in stdout
        assert stderr == (
            "stow: --target value '%s/no-such-directory-for-stow-python'"
            " is not a valid directory\n\n" % pwd.getpwuid(os.getuid()).pw_dir
        )
        assert state == {}

    def test_tilde_user_zero_takes_the_bare_tilde_branch(self, stow_env):
        """Perl tests the captured username for truth, so "~0/..." is not a
        lookup of user "0" but a bare tilde: it expands to $HOME."""
        stow_env.create_package("pkgt", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as fh:
            fh.write("--target=~0/target\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkgt/bin")

        run_both_tests(
            stow_env,
            ["pkgt"],
            setup,
            check,
            compare_fs_ops=True,
            env_vars={"HOME": stow_env.tmpdir},
        )

    def test_empty_home_probes_root_stowrc(self, stow_env):
        """Perl tests HOME with defined(), not for truth, so an empty HOME
        still contributes a candidate .stowrc — the literal path
        "/.stowrc"."""
        if shutil.which("strace") is None:
            pytest.skip("strace not available")

        stow_env.create_package("pkgh", {"bin/file": "content"})

        def setup():
            pass

        _, _, _, _, perl_ops, python_ops = assert_stow_match_with_fs_ops(
            stow_env, ["-t", stow_env.target_dir, "pkgh"], setup, env={"HOME": ""}
        )
        probed = [op for op in perl_ops if op["paths"][0] == "/.stowrc"]
        assert probed, "Perl probes the literal path /.stowrc"
        assert [op for op in python_ops if op["paths"][0] == "/.stowrc"] == probed

    def test_unknown_tilde_user_expands_to_nothing(self, stow_env):
        """getpwnam() failing leaves undef, which Perl substitutes as the
        empty string after warning, so "~nosuchuser/t" becomes "/t"."""
        stow_env.create_package("pkgu", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as fh:
            fh.write("--target=~nosuchuser-xyzzy/t\n")

        def setup():
            pass

        rc, stdout, stderr, state = assert_stow_match(
            stow_env, ["pkgu"], setup, env={"HOME": stow_env.tmpdir}
        )
        assert rc == 1
        assert "SYNOPSIS:" in stdout
        assert stderr == (
            "Use of uninitialized value in substitution iterator\n"
            "stow: --target value '/t' is not a valid directory\n\n"
        )
        assert state == {}

    def test_verbose_trace_shape(self, stow_env):
        """The -v5 trace is compared line for line, apart from the two
        ignore-list regexp lines that quote the regex engine. It pins the
        two task-action lines, which Perl writes at different indents and
        with different wording, and the join_paths trace that every stow
        dir prefix candidate goes through."""
        stow_env.create_package("pkgv1", {"bin/one": "content", "bin/sub/two": "c"})
        stow_env.create_package("pkgv2", {"bin/three": "content"})
        stow_env.create_package("pkgvm", {"f.txt": "content"})

        def setup_unfold():
            stow_env.create_target_link("bin", "../stow/pkgv1/bin")

        def setup_marked():
            stow_env.create_target_file("a/b/.stow", "")
            stow_env.create_target_file("a/b/pkg2/f.txt", "content")
            stow_env.create_target_link("f.txt", "a/b/pkg2/f.txt")

        cases = (
            (
                setup_unfold,
                ["-t", stow_env.target_dir, "-v5", "pkgv2"],
                [
                    "    link_task_action(bin): link task exists with action remove",
                    "                | dir_task_action(bin): dir task exists with"
                    " action create",
                ],
            ),
            (
                setup_marked,
                ["-t", stow_env.target_dir, "-v5", "-D", "pkgvm"],
                [
                    "                    | Joining: a",
                    "                    | Final join: a",
                    "                    | Joining: a b",
                    "                    | Final join: a/b",
                ],
            ),
        )

        for setup, args, expected in cases:
            traces = []
            for run, unbrand in (
                (stow_env.run_perl_stow, lambda text: text),
                (stow_env.run_python_stow, normalize_stow_output),
            ):
                stow_env.reset_target()
                setup()
                rc, stdout, stderr = run(args)
                assert rc == 0
                assert stdout == ""
                traces.append(
                    [
                        line
                        for line in unbrand(stderr).splitlines()
                        if "Ignore list regexp for" not in line
                    ]
                )

            assert traces[0] == traces[1]
            for line in expected:
                assert line in traces[0]

    def test_trailing_slash_before_a_newline_is_stripped(self, stow_env):
        """Perl deletes trailing slashes with s{/+$}{}, and $ matches
        before a trailing newline, so "a/\\n" becomes the usable package
        name "a\\n". The substitution writes back through the foreach
        alias, so the trace names the stripped package too."""
        stow_env.create_package("a\n", {"file1": "content"})
        stow_env.create_package("a", {"plainfile": "content"})

        for given, package, member in (
            ("a/\n", "a\n", "file1"),
            ("a//", "a", "plainfile"),
        ):
            def setup():
                pass

            def check(env, package=package, member=member):
                check_link(env, member, "../stow/%s/%s" % (package, member))

            run_both_tests(
                stow_env,
                ["-t", stow_env.target_dir, "-v3", given],
                setup,
                check,
                check_on_simulate=False,
            )

    def test_newline_directory_value_warns_before_the_error(self, stow_env):
        """--dir and --target are checked with Perl's -d, which is a stat,
        so a failing one on a value ending in a newline warns first."""
        stow_env.create_package("pkgnl", {"file": "content"})

        for option, label in (("--target", "--target"), ("--dir", "--dir")):
            value = "nosuchdir/\n"

            def setup():
                pass

            rc, stdout, stderr, state = assert_stow_match(
                stow_env, [option + "=" + value, "pkgnl"], setup
            )
            assert rc == 1
            assert "SYNOPSIS:" in stdout
            assert stderr == (
                "Unsuccessful stat on filename containing newline\n"
                "stow: %s value '%s' is not a valid directory\n\n" % (label, value)
            )

    def test_help_beats_version_and_errors_beat_both(self, stow_env):
        """Perl checks $options{help} before $options{version}, and both
        only after GetOptions has returned — so an option error wins over
        either, with the usage message on stdout and status 1."""
        stow_env.create_package("pkghv", {"file": "content"})

        def setup():
            pass

        for args, expect_rc, expect_stderr in (
            (["--version", "--help", "pkghv"], 0, ""),
            (["--help", "--version", "pkghv"], 0, ""),
            (["--help", "--bogus"], 1, "Unknown option: bogus\n"),
            (["--version", "--bogus"], 1, "Unknown option: bogus\n"),
            (["-V", "--bogus"], 1, "Unknown option: bogus\n"),
            (["-h", "--bogus"], 1, "Unknown option: bogus\n"),
        ):
            rc, stdout, stderr, _ = assert_stow_match(stow_env, args, setup)
            assert rc == expect_rc
            assert "SYNOPSIS:" in stdout
            assert stderr == expect_stderr

    def test_every_bad_option_is_reported(self, stow_env):
        """GetOptions parses the whole argument list before returning
        false, so each bad option gets its own complaint."""
        stow_env.create_package("pkgbad", {"file": "content"})

        def setup():
            pass

        for args, expect_stderr in (
            (
                ["--bogus", "--alsobad", "--third", "pkgbad"],
                "Unknown option: bogus\n"
                "Unknown option: alsobad\n"
                "Unknown option: third\n",
            ),
            (
                ["--bogus", "--dir"],
                "Unknown option: bogus\nOption dir requires an argument\n",
            ),
            (["-x", "-y", "pkgbad"], "Unknown option: x\nUnknown option: y\n"),
            (
                ["--de", "x", "--bogus", "pkgbad"],
                "Option de is ambiguous (defer, delete)\nUnknown option: bogus\n",
            ),
            (
                ["--adopt=1", "--bogus", "pkgbad"],
                "Option adopt does not take an argument\nUnknown option: bogus\n",
            ),
            (
                ["--verbose=zz", "--bogus", "pkgbad"],
                'Value "zz" invalid for option verbose (number expected)\n'
                "Unknown option: bogus\n",
            ),
        ):
            rc, stdout, stderr, _ = assert_stow_match(stow_env, args, setup)
            assert rc == 1
            assert "SYNOPSIS:" in stdout
            assert stderr == expect_stderr

    def test_verbose_value_grammar_allows_underscores(self, stow_env):
        """Getopt::Long's integer pattern lets underscores separate (and
        precede) the digits. A value in its own argument has them deleted
        before the number is read; one bundled onto the option does not,
        so Perl's numeric conversion stops at the first underscore and
        warns."""
        stow_env.create_package("pkgvg", {"file": "content"})

        def setup():
            pass

        for args, expect_level, expect_warning in (
            (["--verbose=1_0"], 10, False),
            (["--verbose=_5"], 5, False),
            (["--verbose=1__0"], 10, False),
            (["--verbose=1_"], 1, False),
            (["--verbose=+_3"], 3, False),
            (["--verbose=-_3"], -3, False),
            (["--verbose", "1_0"], 10, False),
            (["-v", "1_0"], 10, False),
            (["-v_2"], 0, True),
            (["-v1_0"], 1, True),
        ):
            run_args = args + ["-t", stow_env.target_dir, "-n", "pkgvg"]
            traces = []
            for run, unbrand in (
                (stow_env.run_perl_stow, lambda text: text),
                (stow_env.run_python_stow, normalize_stow_output),
            ):
                stow_env.reset_target()
                setup()
                rc, stdout, stderr = run(run_args)
                assert rc == 0
                assert stdout == ""
                # The alternation order inside the ignore-list regexps is
                # Perl's hash order, which nothing can reproduce
                traces.append([
                    line
                    for line in normalize_newline_warnings(unbrand(stderr)).splitlines()
                    if "Ignore list regexp for" not in line
                ])

            assert traces[0] == traces[1]
            lines = traces[0]
            if expect_warning:
                value = args[0][2:]
                assert lines[0] == (
                    'Argument "%s" isn\'t numeric in addition (+)' % value
                )
                lines = lines[1:]
            # Level 1 is the first that prints the planned link, and the
            # higher levels only add to what the lower ones printed
            assert ("LINK: file => ../stow/pkgvg/file" in lines) == (
                expect_level >= 1
            )
            assert (len(lines) > 3) == (expect_level >= 3)

    def test_program_name_comes_from_argv_zero(self, stow_env):
        """The name in the version, usage and option-error lines is the
        basename of $0; only the ERROR: prefix stays the hardcoded
        "stow"."""
        if PERL_STOW is None:
            pytest.skip("Perl stow not found")

        renamed_perl = os.path.join(stow_env.tmpdir, "renamed-stow")
        shutil.copy(PERL_STOW, renamed_perl)
        renamed_python = os.path.join(stow_env.tmpdir, "renamed-py-stow")
        shutil.copy(PYTHON_STOW, renamed_python)

        for path, name, unbrand in (
            (renamed_perl, "renamed-stow", lambda text: text),
            (renamed_python, "renamed-py-stow", normalize_stow_output),
        ):
            run_env = os.environ.copy()
            run_env["STOW_DIR"] = stow_env.stow_dir
            if path is renamed_perl and PERL_LIB:
                run_env["PERL5LIB"] = PERL_LIB
            command = [path] if path is renamed_perl else [sys.executable, path]

            for args, expected_stdout, expected_stderr in (
                (["--version"], "%s (GNU Stow) version 2.4.1\n" % name, ""),
                ([], None, "%s: No packages to stow or unstow\n\n" % name),
                (
                    ["--target=/nosuchdir/zz", "pkg"],
                    None,
                    "%s: --target value '/nosuchdir/zz'"
                    " is not a valid directory\n\n" % name,
                ),
            ):
                proc = subprocess.Popen(
                    command + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=stow_env.stow_dir,
                    env=run_env,
                )
                stdout, stderr = proc.communicate()
                stdout = unbrand(stdout.decode())
                assert stderr.decode() == expected_stderr
                if expected_stdout is None:
                    assert stdout.startswith("%s (GNU Stow) version 2.4.1\n" % name)
                    assert "    %s [OPTION ...]" % name in stdout
                else:
                    assert stdout == expected_stdout

    def test_stdout_failures_are_reported_like_perl(self, stow_env):
        """Perl flushes stdout on the way out and complains when that
        fails, and leaves SIGPIPE at its default so a reader that has gone
        away kills the process by signal."""
        if PERL_STOW is None:
            pytest.skip("Perl stow not found")

        for path, prefix in (
            (PERL_STOW, "perl -I%s " % PERL_LIB if PERL_LIB else ""),
            (PYTHON_STOW, "%s " % sys.executable),
        ):
            for redirection, expected in (
                ("> /dev/full", (1, "Unable to flush stdout: No space left on device\n")),
                (">&-", (1, "Unable to flush stdout: Bad file descriptor\n")),
            ):
                proc = subprocess.Popen(
                    ["bash", "-c", "%s%s --version %s" % (prefix, path, redirection)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = proc.communicate()
                assert (proc.returncode, stderr.decode()) == expected

            proc = subprocess.Popen(
                ["bash", "-c",
                 "{ %s%s --help; echo RC=${?} >&2; } | { exit 0; }" % (prefix, path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            assert stderr.decode() == "RC=141\n"

    def test_stowrc_variable_names_are_ascii_words(self, stow_env):
        """Perl reads .stowrc as bytes, so a variable name stops at the
        first byte outside [A-Za-z0-9_] and a "$" followed by none of them
        is not a variable at all. The braced form takes word and space
        characters only, so "${TQZ-x}" stays literal."""
        stow_env.create_package("pkgev", {"file": "content"})
        rc_path = os.path.join(stow_env.stow_dir, ".stowrc")

        for record, expected_target in (
            (b"--target=$TQZBASE\xc3\xa9\n", b"nosuch\xc3\xa9"),
            (b"--target=$\xc3\x9cnicode\n", b"$\xc3\x9cnicode"),
            (b"--target=${TQZ-x}\n", b"${TQZ-x}"),
        ):
            with open(rc_path, "wb") as fh:
                fh.write(record)

            def setup():
                pass

            rc, stdout, stderr = assert_stow_match_raw(
                stow_env,
                ["pkgev"],
                setup,
                env={"TQZBASE": "nosuch", "HOME": stow_env.tmpdir},
            )
            assert rc == 1
            assert b"SYNOPSIS:" in stdout
            assert stderr == (
                b"stow: --target value '" + expected_target
                + b"' is not a valid directory\n\n"
            )

        os.unlink(rc_path)
