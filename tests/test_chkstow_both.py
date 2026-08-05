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


class TestChkstowTargetDirectoryBoth:
    """The scan is rooted in the --target directory, not in the process's
    current directory.

    Every other scenario in this file runs with the process directory
    equal to the target and passes "-t .", which cannot tell the two
    apart. These point -t at a subdirectory whose contents differ from
    the process directory's, so entries reported from the wrong tree —
    or entries of the right tree gone missing — show up immediately.
    """

    def _split_trees(self, stow_env):
        """Decoys in the process directory, the real entries under scan/."""
        stow_env.create_package("pkg", {"file": "content"})
        stow_env.create_target_file("alien_in_cwd", "cwd")
        stow_env.create_target_link("dangling_in_cwd", "../stow/decoy/file")
        stow_env.create_target_dir("scan")
        stow_env.create_target_file("scan/alien_in_target", "target")
        stow_env.create_target_link("scan/dangling_in_target", "nowhere")
        stow_env.create_target_link("scan/stowed", "../../stow/pkg/file")

    def test_aliens_come_from_the_target(self, stow_env):
        self._split_trees(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien_in_target\n"
        assert stderr == ""

    def test_bogus_links_come_from_the_target(self, stow_env):
        self._split_trees(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/dangling_in_target\n"
        assert stderr == ""

    def test_list_packages_come_from_the_target(self, stow_env):
        """The process directory's dangling link would contribute the
        package name "nowhere"; only scan/'s links may be read."""
        self._split_trees(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-l", "-t", "scan"])
        assert rc == 0
        assert stdout == "nowhere\npkg\n"
        assert stderr == ""

    def test_absolute_target_scans_that_directory(self, stow_env):
        self._split_trees(stow_env)
        scan_dir = os.path.join(stow_env.target_dir, "scan")
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-a", "-t", scan_dir])
        assert rc == 0
        assert stdout == f"Unstowed file: {scan_dir}/alien_in_target\n"

    def test_stow_marker_probe_uses_the_target(self, stow_env):
        """The .stow/.notstowed probe is a property of the directory being
        scanned: a marker in the process directory must not silence the
        scan, and a marker inside the target subtree skips that subtree
        under its target-relative name."""
        self._split_trees(stow_env)
        stow_env.create_target_file(".stow", "")
        stow_env.create_target_dir("scan/sub")
        stow_env.create_target_file("scan/sub/.notstowed", "")
        stow_env.create_target_file("scan/sub/alien_below_marker", "hidden")
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien_in_target\n"
        assert stderr == "skipping scan/sub\n"


class TestChkstowUnreadableDirectoriesBoth:
    """File::Find warns and carries on when a directory denies access.

    A directory it cannot chdir into produces
    "Can't cd to (<parent>/) <dir>: <reason>" on stderr; one it can enter
    but not read produces "Can't opendir(<dir>): <reason>", naming the
    directory's own path from the start of the walk. Either way the
    subtree is skipped, the rest of the tree is still reported, and the
    exit code stays 0.
    """

    def setup_method(self, method):
        self.locked = []
        if os.geteuid() == 0:
            pytest.skip("running as root: permission bits do not block access")

    def teardown_method(self, method):
        for path in self.locked:
            os.chmod(path, 0o755)

    def _lock(self, stow_env, rel_path, mode):
        full_path = os.path.join(stow_env.target_dir, rel_path)
        self.locked.append(full_path)
        os.chmod(full_path, mode)

    def _tree_with_locked_dir(self, stow_env, mode):
        stow_env.create_target_dir("scan/locked")
        stow_env.create_target_link("scan/locked/hidden", "nowhere")
        stow_env.create_target_file("scan/alien", "alien")
        stow_env.create_target_link("scan/dangling", "nowhere")
        self._lock(stow_env, "scan/locked", mode)

    def test_unenterable_dir_warns_and_aliens_continue(self, stow_env):
        self._tree_with_locked_dir(stow_env, 0o000)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien\n"
        assert stderr == "Can't cd to (scan/) locked: Permission denied\n"

    def test_unenterable_dir_warns_and_badlinks_continue(self, stow_env):
        self._tree_with_locked_dir(stow_env, 0o000)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/dangling\n"
        assert stderr == "Can't cd to (scan/) locked: Permission denied\n"

    def test_readable_but_unsearchable_dir_is_not_entered(self, stow_env):
        """Mode 444 lists but cannot be chdir'd into, so its contents are
        never examined."""
        self._tree_with_locked_dir(stow_env, 0o444)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien\n"
        assert stderr == "Can't cd to (scan/) locked: Permission denied\n"

    def test_nested_unenterable_dir_names_its_own_parent(self, stow_env):
        stow_env.create_target_dir("scan/mid/locked")
        stow_env.create_target_link("scan/mid/dangling", "nowhere")
        self._lock(stow_env, "scan/mid/locked", 0o000)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/mid/dangling\n"
        assert stderr == "Can't cd to (scan/mid/) locked: Permission denied\n"

    def test_unenterable_target_warns_without_parentheses(self, stow_env):
        """The top-level target is entered by name, so its failure uses
        File::Find's plain "Can't cd to <dir>" form."""
        stow_env.create_target_dir("scan")
        stow_env.create_target_link("dangling_in_cwd", "nowhere")
        self._lock(stow_env, "scan", 0o000)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't cd to scan: Permission denied\n"

    def test_unreadable_but_searchable_dir_warns_and_aliens_continue(self, stow_env):
        """Mode 111 is entered successfully and fails at the read, which
        is a different warning from the one a failed chdir gives."""
        self._tree_with_locked_dir(stow_env, 0o111)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien\n"
        assert stderr == "Can't opendir(scan/locked): Permission denied\n"

    def test_unreadable_but_searchable_dir_warns_and_badlinks_continue(self, stow_env):
        self._tree_with_locked_dir(stow_env, 0o111)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/dangling\n"
        assert stderr == "Can't opendir(scan/locked): Permission denied\n"

    def test_nested_unreadable_dir_names_its_own_path(self, stow_env):
        """The opendir warning names the directory that could not be
        read, not its parent as the chdir warning does."""
        stow_env.create_target_dir("scan/mid/locked")
        stow_env.create_target_link("scan/mid/dangling", "nowhere")
        self._lock(stow_env, "scan/mid/locked", 0o111)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/mid/dangling\n"
        assert stderr == "Can't opendir(scan/mid/locked): Permission denied\n"

    def test_unreadable_target_warns_under_its_own_name(self, stow_env):
        stow_env.create_target_dir("scan")
        stow_env.create_target_link("scan/dangling", "nowhere")
        self._lock(stow_env, "scan", 0o111)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't opendir(scan): Permission denied\n"

    def test_unreadable_dir_in_list_mode(self, stow_env):
        self._tree_with_locked_dir(stow_env, 0o111)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-l", "-t", "scan"])
        assert rc == 0
        assert stdout == "nowhere\n"
        assert stderr == "Can't opendir(scan/locked): Permission denied\n"


class TestChkstowTrailingSlashBoth:
    """File::Find drops exactly one trailing slash from its top item.

    The shortened form is what prefixes every reported name and what the
    "Can't stat" and "skipping" messages spell, while the lstat that
    decides whether the target is a directory still sees the argument as
    it was given.
    """

    def _tree(self, stow_env):
        stow_env.create_target_dir("scan/sub")
        stow_env.create_target_file("scan/alien", "alien")
        stow_env.create_target_file("scan/sub/alien_below", "alien")
        stow_env.create_target_link("scan/dangling", "nowhere")
        stow_env.create_target_file("plainfile", "plain")
        stow_env.create_target_link("linktodir", "scan")

    def test_one_trailing_slash_is_dropped_from_reported_names(self, stow_env):
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan/"])
        assert rc == 0
        assert stdout == (
            "Unstowed file: scan/alien\nUnstowed file: scan/sub/alien_below\n"
        )
        assert stderr == ""

    def test_only_one_trailing_slash_is_dropped(self, stow_env):
        """"scan//" keeps a slash, and the reported names keep it too."""
        self._tree(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-a", "-t", "scan//"])
        assert rc == 0
        assert stdout == (
            "Unstowed file: scan//alien\nUnstowed file: scan//sub/alien_below\n"
        )

    def test_dot_slash_target_reads_as_dot(self, stow_env):
        """Shortened to ".", the target is the directory the process is
        already in, which File::Find enters by not moving at all."""
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "./"])
        assert rc == 0
        assert stdout == (
            "Unstowed file: ./plainfile\n"
            "Unstowed file: ./scan/alien\n"
            "Unstowed file: ./scan/sub/alien_below\n"
        )
        assert stderr == ""

    def test_missing_target_warning_uses_the_shortened_name(self, stow_env):
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "nosuchdir/"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't stat nosuchdir: No such file or directory\n"

    def test_file_target_with_slash_fails_the_stat(self, stow_env):
        """The lstat sees "plainfile/" and reports ENOTDIR, but the
        warning names the shortened path."""
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "plainfile/"])
        assert rc == 0
        assert stdout == ""
        assert stderr == "Can't stat plainfile: Not a directory\n"

    def test_symlink_to_directory_is_descended_only_with_the_slash(self, stow_env):
        """Without the slash the lstat sees a symlink, which File::Find
        does not descend; with it the lstat resolves to the directory."""
        self._tree(stow_env)
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-a", "-t", "linktodir"])
        assert rc == 0
        assert stdout == ""
        rc, stdout, _ = assert_chkstow_match(stow_env, ["-a", "-t", "linktodir/"])
        assert rc == 0
        assert stdout == (
            "Unstowed file: linktodir/alien\n"
            "Unstowed file: linktodir/sub/alien_below\n"
        )

    def test_skip_marker_message_uses_the_shortened_name(self, stow_env):
        self._tree(stow_env)
        stow_env.create_target_file("scan/sub/.stow", "")
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan/"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien\n"
        assert stderr == "skipping scan/sub\n"

    def test_package_list_is_unaffected_by_the_slash(self, stow_env):
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-l", "-t", "scan/"])
        assert rc == 0
        assert stdout == "nowhere\n"
        assert stderr == ""


class TestChkstowNonUtf8NamesBoth:
    """File names are bytes, and the reports pass them through unchanged.

    Perl neither decodes nor validates them, so a name that is not valid
    UTF-8 is printed as the bytes it is and sorted by byte value. The
    names below are written as the surrogate escapes Python decodes those
    bytes into: "\\udc80" is the byte 0x80, "\\udcff" is 0xff.
    """

    RAW_80 = "\udc80"
    RAW_FF = "\udcff"

    def _tree(self, stow_env):
        stow_env.create_target_dir("scan")
        for name in [self.RAW_80 + "z", "éw", "ascii", "Zupper", self.RAW_FF]:
            stow_env.create_target_file("scan/" + name, "alien")
        stow_env.create_target_dir("scan/" + self.RAW_80 + "dir")
        stow_env.create_target_file(
            "scan/" + self.RAW_80 + "dir/inner" + self.RAW_FF, "alien"
        )

    def test_aliens_report_the_raw_bytes(self, stow_env):
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stderr == ""
        assert sorted(stdout.splitlines()) == sorted(
            [
                "Unstowed file: scan/" + self.RAW_80 + "z",
                "Unstowed file: scan/éw",
                "Unstowed file: scan/ascii",
                "Unstowed file: scan/Zupper",
                "Unstowed file: scan/" + self.RAW_FF,
                "Unstowed file: scan/" + self.RAW_80 + "dir/inner" + self.RAW_FF,
            ]
        )

    def test_bogus_links_report_the_raw_bytes(self, stow_env):
        stow_env.create_target_dir("scan")
        stow_env.create_target_link("scan/" + self.RAW_80 + "link", "nowhere")
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-b", "-t", "scan"])
        assert rc == 0
        assert stdout == "Bogus link: scan/" + self.RAW_80 + "link\n"
        assert stderr == ""

    def test_package_list_sorts_by_byte_value(self, stow_env):
        """Perl's sort compares bytes: 0x80 comes before the 0xc3 that
        starts the UTF-8 encoding of "é", which comparing decoded code
        points would reverse. Case is likewise a byte comparison, so
        "Mpkg" precedes "mpkg"."""
        stow_env.create_target_dir("scan")
        for name, pkg in [
            ("l1", self.RAW_80 + "z"),
            ("l2", "éw"),
            ("l3", "Mpkg"),
            ("l4", "mpkg"),
            ("l5", self.RAW_FF + "q"),
        ]:
            stow_env.create_target_link("scan/" + name, "../stow/" + pkg + "/file")
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-l", "-t", "scan"])
        assert rc == 0
        assert stdout == (
            "Mpkg\nmpkg\n" + self.RAW_80 + "z\néw\n" + self.RAW_FF + "q\n"
        )
        assert stderr == ""

    def test_warnings_carry_the_raw_bytes(self, stow_env):
        """The skip message and the "Can't stat" warning go through the
        same byte-transparent path as the reports."""
        stow_env.create_target_dir("scan/" + self.RAW_80 + "dir")
        stow_env.create_target_file("scan/" + self.RAW_80 + "dir/.stow", "")
        stow_env.create_target_file("scan/alien", "alien")
        rc, stdout, stderr = assert_chkstow_match(stow_env, ["-a", "-t", "scan"])
        assert rc == 0
        assert stdout == "Unstowed file: scan/alien\n"
        assert stderr == "skipping scan/" + self.RAW_80 + "dir\n"

        rc, stdout, stderr = assert_chkstow_match(
            stow_env, ["-a", "-t", self.RAW_80 + "nosuch"]
        )
        assert rc == 0
        assert stdout == ""
        assert stderr == (
            "Can't stat " + self.RAW_80 + "nosuch: No such file or directory\n"
        )

    def test_raw_bytes_survive_a_non_utf8_locale(self, stow_env):
        """Neither implementation interprets the names, so the C locale
        changes nothing about what is printed."""
        self._tree(stow_env)
        rc, stdout, stderr = assert_chkstow_match(
            stow_env, ["-a", "-t", "scan"], env={"LC_ALL": "C", "LANG": "C"}
        )
        assert rc == 0
        assert stderr == ""
        assert ("Unstowed file: scan/" + self.RAW_80 + "z") in stdout.splitlines()
