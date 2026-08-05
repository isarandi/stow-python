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

from conftest import (
    assert_chkstow_match,
    assert_chkstow_match_raw,
    assert_chkstow_match_with_fs_ops,
)


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


class TestChkstowNonUTF8Bytes:
    """Filenames are byte strings: names that are not valid UTF-8 reach
    stdout unchanged, and packages sort by their bytes, whatever the
    locale claims.
    """

    UTF8_ENV = {"LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}

    def _make_tree(self, stow_env):
        target = stow_env.target_dir.encode()
        os.makedirs(os.path.join(target, b"bin"))
        with open(os.path.join(target, b"bad\xff\xfename"), "wb") as f:
            f.write(b"x")
        os.symlink(b"nowhere\xff", os.path.join(target, b"bin/broken\xfelink"))
        # b'\x80z' sorts before b'\xc3\xa9w' by bytes, after it by code point
        for pkg in (b"\x80z", b"\xc3\xa9w"):
            os.makedirs(os.path.join(target, b"stow/" + pkg + b"/bin"))
            with open(os.path.join(target, b"stow/" + pkg + b"/bin/f"), "wb") as f:
                f.write(b"f")
            os.symlink(
                b"../stow/" + pkg + b"/bin/f",
                os.path.join(target, b"bin/" + pkg),
            )
        open(os.path.join(target, b"stow/.stow"), "wb").close()

    def test_bogus_link_with_non_utf8_name(self, stow_env):
        self._make_tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match_raw(
            stow_env, ["-b", "-t", "."], env=self.UTF8_ENV
        )
        assert rc == 0
        assert stdout == b"Bogus link: ./bin/broken\xfelink\n"
        assert stderr == b"skipping ./stow\n"

    def test_alien_with_non_utf8_name(self, stow_env):
        self._make_tree(stow_env)
        rc, stdout, _ = assert_chkstow_match_raw(
            stow_env, ["-a", "-t", "."], env=self.UTF8_ENV
        )
        assert rc == 0
        assert stdout == b"Unstowed file: ./bad\xff\xfename\n"

    def test_package_list_sorts_by_bytes(self, stow_env):
        self._make_tree(stow_env)
        rc, stdout, _ = assert_chkstow_match_raw(
            stow_env, ["-l", "-t", "."], env=self.UTF8_ENV
        )
        assert rc == 0
        assert stdout == b"nowhere\xff\n\x80z\n\xc3\xa9w\n"

    def test_non_utf8_names_from_another_cwd(self, stow_env):
        self._make_tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match_raw(
            stow_env,
            ["-b", "-t", "../target"],
            env=self.UTF8_ENV,
            cwd=stow_env.stow_dir,
        )
        assert rc == 0
        assert stdout == b"Bogus link: ../target/bin/broken\xfelink\n"


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

    def test_walks_target_not_cwd(self, stow_env):
        """File::Find chdirs into the target, so what gets scanned is the
        target tree even when chkstow is invoked from elsewhere. The decoys
        planted in the invocation directory must never show up, and the
        reported paths keep the target spelling from the command line."""
        # Decoys in the directory chkstow is invoked from
        os.symlink("nowhere-decoy", os.path.join(stow_env.stow_dir, "decoy-broken"))
        stow_env.create_target_dir("../stow/decoypkg")
        with open(os.path.join(stow_env.stow_dir, "decoy-alien"), "w") as f:
            f.write("decoy")

        # Real content in the target
        stow_env.create_target_file("stow/pkg/bin/real", "real")
        stow_env.create_target_file("alien", "alien")
        stow_env.create_target_link("bin/stowed", "../stow/pkg/bin/real")
        stow_env.create_target_link("bin/broken", "nowhere-real")

        for mode, expected in (
            ("-b", ["Bogus link: ../target/bin/broken"]),
            (
                "-a",
                [
                    "Unstowed file: ../target/alien",
                    "Unstowed file: ../target/stow/pkg/bin/real",
                ],
            ),
            # list mode readlinks every link, bogus ones included
            ("-l", ["nowhere-real", "pkg"]),
        ):
            rc, stdout, stderr = assert_chkstow_match(
                stow_env, [mode, "-t", "../target"], cwd=stow_env.stow_dir
            )
            assert rc == 0
            assert stderr == ""
            assert "decoy" not in stdout
            assert sorted(stdout.splitlines()) == expected

    def test_walks_target_not_cwd_absolute(self, stow_env):
        """Same walk with an absolute target."""
        with open(os.path.join(stow_env.stow_dir, "decoy-alien"), "w") as f:
            f.write("decoy")
        stow_env.create_target_file("alien", "alien")

        rc, stdout, _ = assert_chkstow_match(
            stow_env, ["-a", "-t", stow_env.target_dir], cwd=stow_env.stow_dir
        )
        assert rc == 0
        assert stdout == "Unstowed file: %s/alien\n" % stow_env.target_dir

    def test_walks_target_not_cwd_syscalls(self, stow_env):
        """The chdir-driven walk of a target outside the cwd must issue the
        same syscalls as File::Find's."""
        stow_env.create_target_file("bin/real", "real")
        stow_env.create_target_link("bin/broken", "nowhere-real")
        assert_chkstow_match_with_fs_ops(
            stow_env, ["-b", "-t", "../target"], cwd=stow_env.stow_dir
        )

    def test_trailing_slash_target(self, stow_env):
        """File::Find strips ONE trailing slash off the target argument, so
        a doubled slash survives into the reported paths."""
        stow_env.create_target_link("bin/broken", "nowhere")
        rc, stdout, _ = assert_chkstow_match(
            stow_env, ["-b", "-t", "../target/"], cwd=stow_env.stow_dir
        )
        assert stdout == "Bogus link: ../target/bin/broken\n"
        rc, stdout, _ = assert_chkstow_match(
            stow_env, ["-b", "-t", "../target//"], cwd=stow_env.stow_dir
        )
        assert stdout == "Bogus link: ../target//bin/broken\n"
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-b", "-t", "./"])
        assert stdout == "Bogus link: ./bin/broken\n"

    def test_unreadable_subdir_warns_and_continues(self, stow_env):
        """A subdirectory that cannot be entered warns with the parent in
        parentheses; the rest of the tree is still scanned and rc stays 0."""
        stow_env.create_target_link("bin/broken", "nowhere")
        stow_env.create_target_file("alien", "alien")
        locked = os.path.join(stow_env.target_dir, "bin")
        os.chmod(locked, 0o000)
        try:
            rc, stdout, stderr = assert_chkstow_match(
                stow_env, ["-a", "-t", "../target"], cwd=stow_env.stow_dir
            )
        finally:
            os.chmod(locked, 0o755)
        assert rc == 0
        assert stdout == "Unstowed file: ../target/alien\n"
        assert stderr == "Can't cd to (../target/) bin: Permission denied\n"

    def test_unreadable_target_warns_without_parentheses(self, stow_env):
        """A top-level target that cannot be entered warns without the
        parenthesised parent, and nothing is scanned."""
        stow_env.create_target_file("alien", "alien")
        os.chmod(stow_env.target_dir, 0o000)
        try:
            rc, stdout, stderr = assert_chkstow_match(
                stow_env, ["-a", "-t", "../target"], cwd=stow_env.stow_dir
            )
        finally:
            os.chmod(stow_env.target_dir, 0o755)
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't cd to ../target: Permission denied\n"

    def test_unlistable_subdir_warns_cant_opendir(self, stow_env):
        """A subdirectory that can be entered but not read warns from
        opendir, naming the directory's full path."""
        stow_env.create_target_link("bin/broken", "nowhere")
        locked = os.path.join(stow_env.target_dir, "bin")
        os.chmod(locked, 0o111)
        try:
            rc, stdout, stderr = assert_chkstow_match(
                stow_env, ["-b", "-t", "../target"], cwd=stow_env.stow_dir
            )
        finally:
            os.chmod(locked, 0o755)
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't opendir(../target/bin): Permission denied\n"

    def test_nonexistent_target_warns_cant_stat(self, stow_env):
        """File::Find warns "Can't stat ..." and checks nothing; the
        harness strips only Perl's " at <script> line N." suffix, so the
        message itself is compared."""
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-t", "nosuchdir", "-b"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't stat nosuchdir: No such file or directory\n"

    def test_empty_attached_value_is_a_missing_argument(self, stow_env):
        """Getopt::Long counts an empty attached value as no value at all,
        so "--target=" reports a missing argument and nothing is scanned.
        The complaint names the expanded, lowercased option."""
        self._make_bogus_link(stow_env)
        for args, name in ((["--target="], "target"), (["-t="], "t")):
            rc, stdout, stderr = assert_chkstow_match(stow_env, args + ["-l"])
            assert rc == 0
            assert stderr == "Option %s requires an argument\n" % name
            assert "USAGE:" in stdout
            assert "Bogus link:" not in stdout

    def test_posixly_correct_keeps_equals_in_short_option_names(self, stow_env):
        """The "=" of a value splits off under a short prefix only while
        getopt_compat is on, which POSIXLY_CORRECT turns off — the whole
        "t=x" is then an unknown option name."""
        self._make_bogus_link(stow_env)
        for args, message in (
            (["-t=x"], "Unknown option: t=x\n"),
            (["-b=1"], "Unknown option: b=1\n"),
        ):
            rc, stdout, stderr = assert_chkstow_match(
                stow_env, args, env={"POSIXLY_CORRECT": "1", "STOW_DIR": "."}
            )
            assert rc == 0
            assert stderr == message
            assert "USAGE:" in stdout

    def test_bare_plus_is_a_missing_option(self, stow_env):
        """A prefix with no name behind it is a missing option, not an
        unknown one, and nothing is scanned."""
        self._make_bogus_link(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["+", "-l"])
        assert rc == 0
        assert stderr == "Missing option after +\n"
        assert "USAGE:" in stdout
        assert stdout.startswith("USAGE:")

    def test_diagnostics_name_the_canonical_option(self, stow_env):
        """Getopt::Long lowercases and prefix-expands the option name
        before it complains about a known one, and reports an unknown one
        by the name the lookup gave up on — lowercased by auto_abbrev, and
        left alone when POSIXLY_CORRECT has disabled it."""
        self._make_bogus_link(stow_env)
        for args, env, message in (
            (["--FOO"], None, "Unknown option: foo\n"),
            (["--badl=1"], None, "Option badlinks does not take an argument\n"),
            (["--targ"], None, "Option target requires an argument\n"),
            (["-T"], None, "Option t requires an argument\n"),
            (
                ["--FOO"],
                {"POSIXLY_CORRECT": "1", "STOW_DIR": "."},
                "Unknown option: FOO\n",
            ),
            (
                ["--BADL"],
                {"POSIXLY_CORRECT": "1", "STOW_DIR": "."},
                "Unknown option: BADL\n",
            ),
        ):
            rc, stdout, stderr = assert_chkstow_match(stow_env, args, env=env)
            assert rc == 0
            assert stderr == message
            assert "USAGE:" in stdout
