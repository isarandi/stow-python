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
Black-box oracle tests for chkstow - comparing Perl and Python implementations.

Perl t/chkstow.t tests (7 scenarios):
1. -b: Skip directories containing .stow (stderr check)
2. -l: List packages → stdout_like "emacs\nperl\nstow\n"
3. -b: No bogus links → stdout empty
4. -a: No aliens → stdout empty
5. -a with alien file → stdout_like "Unstowed file: ./bin/alien"
6. -b with bogus link → stdout_like "Bogus link: ./bin/link"
7. Default target is /usr/local

These tests verify Perl vs Python match and check expected output patterns.
Note: chkstow is read-only with no simulate mode, so we don't use run_both_tests.
"""

import os
import pytest
import re

from conftest import assert_chkstow_match, assert_chkstow_match_with_fs_ops


@pytest.fixture
def chkstow_env(stow_env):
    """Set up test environment for chkstow tests.

    Matches Perl t/chkstow.t setup:
    - stow/.stow marker
    - stow/perl package with bin/perl, bin/a2p, info/perl, lib/perl, man/man1/perl.1
    - stow/emacs package with bin/emacs, bin/etags, info/emacs, libexec/emacs, man/man1/emacs.1
    - Target with stowed symlinks
    """
    # Create stow directory marker
    stow_env.create_target_dir("stow")
    stow_marker = os.path.join(stow_env.target_dir, "stow", ".stow")
    with open(stow_marker, "w") as f:
        pass

    # Create perl package
    for path in [
        "stow/perl/bin",
        "stow/perl/info",
        "stow/perl/lib/perl",
        "stow/perl/man/man1",
    ]:
        stow_env.create_target_dir(path)
    for path, content in [
        ("stow/perl/bin/perl", "perl"),
        ("stow/perl/bin/a2p", "a2p"),
        ("stow/perl/info/perl", "info"),
        ("stow/perl/man/man1/perl.1", "man"),
    ]:
        stow_env.create_target_file(path, content)

    # Create emacs package
    for path in [
        "stow/emacs/bin",
        "stow/emacs/info",
        "stow/emacs/libexec/emacs",
        "stow/emacs/man/man1",
    ]:
        stow_env.create_target_dir(path)
    for path, content in [
        ("stow/emacs/bin/emacs", "emacs"),
        ("stow/emacs/bin/etags", "etags"),
        ("stow/emacs/info/emacs", "info"),
        ("stow/emacs/man/man1/emacs.1", "man"),
    ]:
        stow_env.create_target_file(path, content)

    # Create stowed symlinks
    stow_env.create_target_dir("bin")
    stow_env.create_target_link("bin/a2p", "../stow/perl/bin/a2p")
    stow_env.create_target_link("bin/emacs", "../stow/emacs/bin/emacs")
    stow_env.create_target_link("bin/etags", "../stow/emacs/bin/etags")
    stow_env.create_target_link("bin/perl", "../stow/perl/bin/perl")

    stow_env.create_target_dir("info")
    stow_env.create_target_link("info/emacs", "../stow/emacs/info/emacs")
    stow_env.create_target_link("info/perl", "../stow/perl/info/perl")

    stow_env.create_target_link("lib", "stow/perl/lib")
    stow_env.create_target_link("libexec", "stow/emacs/libexec")

    stow_env.create_target_dir("man")
    stow_env.create_target_dir("man/man1")
    stow_env.create_target_link("man/man1/emacs", "../../stow/emacs/man/man1/emacs.1")
    stow_env.create_target_link("man/man1/perl", "../../stow/perl/man/man1/perl.1")

    return stow_env


class TestChkstowBoth:
    """Oracle tests comparing Perl and Python chkstow.

    Strace comparison not used for chkstow - it's read-only and directory
    traversal order can legitimately differ. Output matching is sufficient.
    """

    def test_list_packages(self, chkstow_env):
        """List packages mode.

        Perl: stdout_like qr{emacs\nperl\nstow\n}
        """
        assert_chkstow_match(chkstow_env, ["-l", "-t", "."])
        # Additional check: verify expected packages listed
        _, stdout, _ = chkstow_env.run_python_chkstow(["-l", "-t", "."])
        assert re.search(r"emacs\nperl\nstow\n", stdout), f"Expected package list, got: {stdout}"

    def test_no_bogus_links(self, chkstow_env):
        """Bad links check with no bad links.

        Perl: stdout_like qr{\A\z} (empty)
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert stdout.strip() == "", f"Expected empty stdout, got: {stdout}"

    def test_no_aliens(self, chkstow_env):
        """Aliens check with no aliens.

        Perl: stdout_like qr{\A\z} (empty)
        """
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-a", "-t", "."])
        assert stdout.strip() == "", f"Expected empty stdout, got: {stdout}"

    def test_detect_alien(self, chkstow_env):
        """Aliens check with alien file.

        Perl: stdout_like qr{Unstowed file: ./bin/alien}
        """
        chkstow_env.create_target_file("bin/alien", "alien file")
        assert_chkstow_match(chkstow_env, ["-a", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-a", "-t", "."])
        assert re.search(r"Unstowed file: \./bin/alien", stdout), f"Expected alien detection, got: {stdout}"

    def test_detect_bogus_link(self, chkstow_env):
        """Bad links check with broken symlink.

        Perl: stdout_like qr{Bogus link: ./bin/link}
        """
        bad_link = os.path.join(chkstow_env.target_dir, "bin", "link")
        os.symlink("ireallyhopethisfiledoesn/t.exist", bad_link)
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"Bogus link: \./bin/link", stdout), f"Expected bogus link detection, got: {stdout}"

    def test_skip_stow_directories(self, chkstow_env):
        """Skip directories containing .stow marker.

        Perl: stderr_like qr{skipping .*stow.*}
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, _, stderr = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"skipping.*stow", stderr, re.IGNORECASE), f"Expected skip warning, got stderr: {stderr}"


class TestChkstowSyscalls:
    """Oracle tests comparing syscall traces between Perl and Python chkstow."""

    def test_list_packages_syscalls(self, chkstow_env):
        """List packages mode should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-l", "-t", "."])

    def test_badlinks_syscalls(self, chkstow_env):
        """Bad links check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-b", "-t", "."])

    def test_aliens_syscalls(self, chkstow_env):
        """Aliens check should produce identical syscalls."""
        assert_chkstow_match_with_fs_ops(chkstow_env, ["-a", "-t", "."])


class TestChkstowGetoptLongBoth:
    """chkstow's option parser reproduces Getopt::Long's DEFAULT
    configuration (unlike stow's): case-insensitive long options,
    unique-prefix abbreviation, '+' option prefixes, and stderr warnings
    for bad options followed by usage on stdout with exit 0. Everything
    here is asserted equal against the Perl oracle.
    """

    def _make_bogus_link(self, stow_env):
        stow_env.create_target_link("bogus", "nonexistent-dest")

    def test_abbreviated_and_case_insensitive_long_options(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["--bad", "-t", "."])
        assert rc == 0 and "Bogus link:" in stdout
        rc, stdout, _ = assert_chkstow_match(stow_env, ["--tar", ".", "-b"])
        assert "Bogus link:" in stdout
        rc, stdout, _ = assert_chkstow_match(stow_env, ["--BADLINKS", "-t", "."])
        assert "Bogus link:" in stdout
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-B", "-t", "."])
        assert "Bogus link:" in stdout

    def test_plus_prefix_getopt_compat(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["+b", "-t", "."])
        assert rc == 0 and "Bogus link:" in stdout

    def test_single_dash_equals_value(self, stow_env):
        """Getopt::Long accepts -t=DIR (name t, value DIR) but treats
        -tDIR as the unknown option 'tDIR' — no bundling."""
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-t=.", "-b"])
        assert rc == 0 and "Bogus link:" in stdout
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-t.", "-b"])
        assert rc == 0
        assert "Unknown option: t." in stderr
        assert "USAGE:" in stdout

    def test_unknown_option_warns_then_usage(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-x", "-t", "."])
        assert rc == 0
        assert "Unknown option: x" in stderr
        assert "USAGE:" in stdout

    def test_missing_option_value_warns_then_usage(self, stow_env):
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t"])
        assert rc == 0
        assert "requires an argument" in stderr
        assert "USAGE:" in stdout

    def test_flag_with_attached_value_rejected(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["--badlinks=1", "-t", "."])
        assert rc == 0
        assert "USAGE:" in stdout

    def test_non_option_arguments_ignored(self, stow_env):
        """Perl chkstow leaves non-option args in @ARGV and never reads
        them; the scan still runs on the -t target."""
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["foo", "-b", "-t", "."])
        assert rc == 0 and "Bogus link:" in stdout

    def test_posixly_correct_disables_abbreviation(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(
            stow_env, ["--bad", "-t", "."], env={"POSIXLY_CORRECT": "1"}
        )
        assert rc == 0
        assert "Unknown option: bad" in stderr
        assert "USAGE:" in stdout

    def test_posixly_correct_disables_plus_and_stops_at_non_option(self, stow_env):
        """Under POSIXLY_CORRECT, '+b' is not an option: it becomes the
        first non-option argument, require_order stops parsing there, and
        the scan runs on the default target in badlinks mode. STOW_DIR
        points the default at the local tree, never /usr/local."""
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(
            stow_env, ["+b"], env={"POSIXLY_CORRECT": "1", "STOW_DIR": "."}
        )
        assert rc == 0 and "Bogus link:" in stdout

    def test_nonexistent_target_warns_cant_stat(self, stow_env):
        """File::Find warns "Can't stat ..." and checks nothing; the
        harness strips only Perl's " at <script> line N." suffix, so the
        message itself is compared."""
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-t", "nosuchdir", "-b"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't stat nosuchdir: No such file or directory\n"
