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
Test CLI interface via subprocess - Python port of t/cli.t

These are black-box tests that invoke the stow script as a subprocess
and check return codes and output.
"""

from __future__ import print_function

import os
import pwd
import re
import subprocess
import sys

import pytest

from stow_python import cli
from stow_python.cli import get_homedir_from_passwd, perl_shellwords
from stow_python.types import StowInternalError

# Path to the stow script
STOW_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bin", "stow")


def run_stow(*args):
    """
    Run the stow script with given arguments.

    Returns: (returncode, stdout, stderr)
    """
    cmd = [sys.executable, STOW_SCRIPT] + list(args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


class TestCLI:
    """Black-box CLI tests."""

    def test_help_returns_zero_exit_code(self):
        """--help should return 0 exit code."""
        returncode, stdout, stderr = run_stow("--help")
        assert returncode == 0, "--help should return 0 exit code"

    def test_unrecognised_option_returns_one_exit_code(self):
        """Unrecognised option should return 1 exit code."""
        returncode, stdout, stderr = run_stow("--foo")
        assert returncode == 1, "unrecognised option should return 1 exit code"

    def test_unrecognised_option_is_listed_in_error(self):
        """Unrecognised option should be listed in error message."""
        returncode, stdout, stderr = run_stow("--foo")
        # Combine stdout and stderr since error could go to either
        output = stdout + stderr
        # Perl's Getopt::Long outputs option name without dashes
        assert re.search(r"^Unknown option: foo$", output, re.MULTILINE), (
            "unrecognised option should be listed"
        )


class TestPerlShellwords:
    """Edge cases of the Text::ParseWords::shellwords() port used for .stowrc.

    Expected outputs verified against Perl's Text::ParseWords 3.31."""

    def test_double_quoted_backslash_escape(self):
        # Inside double quotes, backslash escapes ANY character: \X -> X
        assert perl_shellwords('--ignore="\\.git"') == ["--ignore=.git"]

    def test_single_quoted_backslash_is_literal(self):
        # Inside single quotes, backslash is copied literally
        assert perl_shellwords("--ignore='\\.git'") == ["--ignore=\\.git"]

    def test_backslash_does_not_close_single_quote(self):
        # \' spans two characters while scanning, so it cannot end the quote
        assert perl_shellwords("'a\\'b'") == ["a\\'b"]

    def test_empty_quoted_words_kept(self):
        assert perl_shellwords("\"\" ''") == ["", ""]

    def test_unmatched_quote_drops_whole_line(self):
        assert perl_shellwords('foo "bar') == []

    def test_trailing_lone_backslash_drops_whole_line(self):
        assert perl_shellwords("foo \\") == []
        assert perl_shellwords("foo\\") == []

    def test_words_split_on_any_whitespace(self):
        assert perl_shellwords("one two\tthree   four") == [
            "one",
            "two",
            "three",
            "four",
        ]

    def test_quoted_segment_adjacent_to_unquoted_text(self):
        # Adjacent quoted and unquoted segments form a single word
        assert perl_shellwords('a"b c"d') == ["ab cd"]


class TestGetHomedirFromPasswd:
    """Passwd database lookups used by tilde expansion."""

    def test_current_uid_lookup_returns_string_path(self):
        home = get_homedir_from_passwd()
        assert isinstance(home, str)
        assert home == pwd.getpwuid(os.getuid()).pw_dir

    def test_unknown_username_returns_none(self):
        assert get_homedir_from_passwd(username="no_such_user_xyzzy_042") is None

    def test_explicit_uid_lookup(self):
        home = get_homedir_from_passwd(uid=os.getuid())
        assert home == pwd.getpwuid(os.getuid()).pw_dir


class TestInternalErrorHandler:
    """main() must format StowInternalError with the bug-report banner."""

    def test_internal_error_formatting(self, monkeypatch, capsys):
        def boom():
            raise StowInternalError("boom")

        monkeypatch.setattr(cli, "_main", boom)

        with pytest.raises(SystemExit) as excinfo:
            cli.main()

        assert excinfo.value.code == 1
        stderr = capsys.readouterr().err
        assert "INTERNAL ERROR: boom" in stderr
        assert (
            "This _is_ a bug. Please submit a bug report so we can fix it! :-)"
            in stderr
        )
        assert (
            "See https://github.com/isarandi/stow-python for how to do this." in stderr
        )


class TestReleaseIdentification:
    """RELEASE is the only runtime channel identifying a stow-python
    release (--version stays byte-identical to GNU Stow), so it must
    agree with the packaging metadata and reach the built artifact."""

    def test_release_matches_pyproject(self):
        pyproject_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "pyproject.toml"
        )
        with open(pyproject_path) as f:
            content = f.read()
        m = re.search(r'(?m)^version = "([^"]+)"$', content)
        assert m, "version not found in pyproject.toml"
        from stow_python.util import RELEASE, VERSION

        assert RELEASE == m.group(1)
        assert RELEASE.startswith(VERSION)

    def test_release_stamped_into_artifact(self):
        from stow_python.util import RELEASE

        with open(STOW_SCRIPT) as f:
            header = f.read(2048)
        assert f"stow-python release {RELEASE}" in header
