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
import re
import subprocess
import sys

# Path to the stow script
STOW_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin', 'stow')


def run_stow(*args):
    """
    Run the stow script with given arguments.

    Returns: (returncode, stdout, stderr)
    """
    cmd = [sys.executable, STOW_SCRIPT] + list(args)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    return (
        proc.returncode,
        stdout.decode('utf-8', errors='replace'),
        stderr.decode('utf-8', errors='replace')
    )


class TestCLI:
    """Black-box CLI tests."""

    def test_help_returns_zero_exit_code(self):
        """--help should return 0 exit code."""
        returncode, stdout, stderr = run_stow('--help')
        assert returncode == 0, "--help should return 0 exit code"

    def test_unrecognised_option_returns_one_exit_code(self):
        """Unrecognised option should return 1 exit code."""
        returncode, stdout, stderr = run_stow('--foo')
        assert returncode == 1, "unrecognised option should return 1 exit code"

    def test_unrecognised_option_is_listed_in_error(self):
        """Unrecognised option should be listed in error message."""
        returncode, stdout, stderr = run_stow('--foo')
        # Combine stdout and stderr since error could go to either
        output = stdout + stderr
        # Perl's Getopt::Long outputs option name without dashes
        assert re.search(r'^Unknown option: foo$', output, re.MULTILINE), \
            "unrecognised option should be listed"
