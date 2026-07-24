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

from conftest import assert_chkstow_match


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
    with open(stow_marker, "w"):
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
        assert re.search(r"emacs\nperl\nstow\n", stdout), (
            f"Expected package list, got: {stdout}"
        )

    def test_no_bogus_links(self, chkstow_env):
        r"""Bad links check with no bad links.

        Perl: stdout_like qr{\A\z} (empty)
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert stdout.strip() == "", f"Expected empty stdout, got: {stdout}"

    def test_no_aliens(self, chkstow_env):
        r"""Aliens check with no aliens.

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
        assert re.search(r"Unstowed file: \./bin/alien", stdout), (
            f"Expected alien detection, got: {stdout}"
        )

    def test_detect_bogus_link(self, chkstow_env):
        """Bad links check with broken symlink.

        Perl: stdout_like qr{Bogus link: ./bin/link}
        """
        bad_link = os.path.join(chkstow_env.target_dir, "bin", "link")
        os.symlink("ireallyhopethisfiledoesn/t.exist", bad_link)
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, stdout, _ = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"Bogus link: \./bin/link", stdout), (
            f"Expected bogus link detection, got: {stdout}"
        )

    def test_skip_stow_directories(self, chkstow_env):
        """Skip directories containing .stow marker.

        Perl: stderr_like qr{skipping .*stow.*}
        """
        assert_chkstow_match(chkstow_env, ["-b", "-t", "."])
        _, _, stderr = chkstow_env.run_python_chkstow(["-b", "-t", "."])
        assert re.search(r"skipping.*stow", stderr, re.IGNORECASE), (
            f"Expected skip warning, got stderr: {stderr}"
        )


class TestChkstowSymlinkTarget:
    """Pin the intentional divergence for a symlinked target directory.

    Perl's File::Find does not descend through a top-level symlink, so
    "chkstow -t <symlink>" silently checks nothing and reports all clear —
    a footgun for a diagnostic tool. We deliberately follow the explicit
    top-level target instead (interior symlinks are still not followed).
    See docs/perl-differences.md.
    """

    def test_symlinked_target_is_followed(self, chkstow_env):
        real = os.path.join(chkstow_env.tmpdir, "realtarget")
        os.makedirs(real)
        with open(os.path.join(real, "alien"), "w") as f:
            f.write("x")
        link = os.path.join(chkstow_env.tmpdir, "linktarget")
        os.symlink("realtarget", link)

        # Python reports the alien file inside the symlinked target
        rc, stdout, stderr = chkstow_env.run_python_chkstow(["-a", "-t", link])
        assert rc == 0
        assert "Unstowed file:" in stdout and "alien" in stdout

        # Perl silently reports nothing
        rc, stdout, stderr = chkstow_env.run_perl_chkstow(["-a", "-t", link])
        assert rc == 0
        assert stdout.strip() == ""


class TestChkstowGetoptLongBoth:
    """chkstow's option parser reproduces Getopt::Long's DEFAULT
    configuration (unlike stow's parser): case-insensitive long options,
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

    def test_plus_prefix_getopt_compat(self, stow_env):
        self._make_bogus_link(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["+b", "-t", "."])
        assert rc == 0 and "Bogus link:" in stdout

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

    def test_file_target_checked_as_single_entry(self, stow_env):
        """File::Find semantics for a non-directory target: the file
        itself is checked once, named './x' for a bare relative name."""
        stow_env.create_target_file("plainfile", "y")
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-t", "plainfile", "-a"])
        assert rc == 0
        assert stdout == "Unstowed file: ./plainfile\n"
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-t", "./plainfile", "-a"])
        assert stdout == "Unstowed file: ./plainfile\n"

    def test_empty_attached_target_value_rejected(self, stow_env):
        """'t|target=s' makes Getopt::Long treat an attached but empty
        value as no value at all, so nothing is scanned."""
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "--target="])
        assert rc == 0
        assert "Option target requires an argument" in stderr
        assert "USAGE:" in stdout
        assert "Bogus link:" not in stdout

    def test_bare_plus_is_an_option_without_a_name(self, stow_env):
        """getopt_compat accepts '+' as an option prefix, so a lone '+' is
        an option whose name is missing and the scan never runs."""
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["+", "-b", "-t", "."])
        assert rc == 0
        assert "Missing option after +" in stderr
        assert "Bogus link:" not in stdout

    def test_diagnostics_name_the_canonical_option(self, stow_env):
        """Getopt::Long lower-cases and prefix-expands the option before
        warning about it, so '--FOO' is 'foo' and '--badl=1' is
        'badlinks'."""
        self._make_bogus_link(stow_env)
        for args, expected in (
            (["--FOO"], "Unknown option: foo"),
            (["--badl=1"], "Option badlinks does not take an argument"),
            (["--targ"], "Option target requires an argument"),
            (["-b=1"], "Option b does not take an argument"),
        ):
            rc, stdout, stderr = assert_chkstow_match(stow_env, args)
            assert rc == 0
            assert expected in stderr, f"{args}: {stderr!r}"

    def test_posixly_correct_does_not_split_single_dash_options(self, stow_env):
        """Without getopt_compat, Getopt::Long splits an attached value off
        after '--' only, so '-t=DIR' is one unknown option and no scan
        happens."""
        self._make_bogus_link(stow_env)
        env = {"POSIXLY_CORRECT": "1"}
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-t=.", "-b"], env=env)
        assert rc == 0
        assert "Unknown option: t=." in stderr
        assert "Bogus link:" not in stdout
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b=1"], env=env)
        assert "Unknown option: b=1" in stderr

    def test_trailing_slash_stripped_from_top_level_target(self, stow_env):
        """File::Find removes one trailing slash from the top item, so
        '-t sub/' reports 'skipping sub' and '-t sub//' reports
        'skipping sub/'."""
        stow_env.create_target_dir("sub/inner")
        with open(os.path.join(stow_env.target_dir, "sub", ".stow"), "w"):
            pass
        rc, _, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "sub/"])
        assert rc == 0 and stderr == "skipping sub\n"
        rc, _, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "sub//"])
        assert stderr == "skipping sub/\n"

    def test_non_utf8_names_are_reported_byte_for_byte(self, stow_env):
        """A name that is not valid UTF-8 must be written out as the bytes
        it is, in Perl's byte sort order, instead of truncating the report
        with an encoding error."""
        target = os.fsencode(stow_env.target_dir)
        os.symlink(b"nowhere", os.path.join(target, b"aaa_broken"))
        os.symlink(b"nowhere", os.path.join(target, b"bad\xff\xfename"))
        os.symlink(b"nowhere", os.path.join(target, b"zzz_broken"))

        rc, stdout, _ = assert_chkstow_match(stow_env, ["-b", "-t", "."])
        assert rc == 0
        assert stdout.count("Bogus link:") == 3, repr(stdout)

    def test_package_list_is_sorted_in_byte_order(self, stow_env):
        """Perl's sort compares raw bytes, so an invalid byte sorts before
        a valid multi-byte character."""
        target = os.fsencode(stow_env.target_dir)
        os.symlink(b"../../stow/pkg1/file", os.path.join(target, b"a1"))
        os.symlink(b"\x80z", os.path.join(target, b"b1"))
        os.symlink("éw".encode(), os.path.join(target, b"b2"))

        rc, stdout, _ = assert_chkstow_match(stow_env, ["-l", "-t", "."])
        assert rc == 0
        assert len(stdout.splitlines()) == 3, repr(stdout)
