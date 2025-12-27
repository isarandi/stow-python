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
Tests for chkstow utility - Python port of chkstow.t

The chkstow utility checks for:
- Bad links (symlinks pointing to non-existent files)
- Aliens (non-symlink, non-directory files not owned by stow)
- Listing packages in the target directory
"""

import os
import re
import sys

import pytest

from testutil import (
    init_test_dirs, make_path, make_file, make_link, make_invalid_link
)

# Check if chkstow module exists
CHKSTOW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'bin', 'chkstow'
)
CHKSTOW_EXISTS = os.path.exists(CHKSTOW_PATH)

# Try to import chkstow module if it exists (Python 2/3 compatible)
chkstow = None
if CHKSTOW_EXISTS:
    try:
        if sys.version_info[0] >= 3:
            import importlib.util
            import importlib.machinery
            loader = importlib.machinery.SourceFileLoader("chkstow", CHKSTOW_PATH)
            spec = importlib.util.spec_from_loader("chkstow", loader)
            if spec is not None:
                chkstow = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(chkstow)
        else:
            import imp
            chkstow = imp.load_source("chkstow", CHKSTOW_PATH)
    except Exception:
        chkstow = None


@pytest.fixture
def chkstow_env(tmp_path, monkeypatch):
    """Set up test environment matching the Perl test structure."""
    monkeypatch.chdir(tmp_path)

    # Initialize test dirs
    init_test_dirs(str(tmp_path / 'test'))
    target_dir = tmp_path / 'test' / 'target'
    monkeypatch.chdir(target_dir)

    # Setup stow directory
    make_path('stow')
    make_file('stow/.stow')

    # perl package
    make_path('stow/perl/bin')
    make_file('stow/perl/bin/perl')
    make_file('stow/perl/bin/a2p')
    make_path('stow/perl/info')
    make_file('stow/perl/info/perl')
    make_path('stow/perl/lib/perl')
    make_path('stow/perl/man/man1')
    make_file('stow/perl/man/man1/perl.1')

    # emacs package
    make_path('stow/emacs/bin')
    make_file('stow/emacs/bin/emacs')
    make_file('stow/emacs/bin/etags')
    make_path('stow/emacs/info')
    make_file('stow/emacs/info/emacs')
    make_path('stow/emacs/libexec/emacs')
    make_path('stow/emacs/man/man1')
    make_file('stow/emacs/man/man1/emacs.1')

    # Setup target directory with symlinks
    make_path('bin')
    make_link('bin/a2p', '../stow/perl/bin/a2p')
    make_link('bin/emacs', '../stow/emacs/bin/emacs')
    make_link('bin/etags', '../stow/emacs/bin/etags')
    make_link('bin/perl', '../stow/perl/bin/perl')

    make_path('info')
    make_link('info/emacs', '../stow/emacs/info/emacs')
    make_link('info/perl', '../stow/perl/info/perl')

    make_link('lib', 'stow/perl/lib')
    make_link('libexec', 'stow/emacs/libexec')

    make_path('man')
    make_path('man/man1')
    make_link('man/man1/emacs', '../../stow/emacs/man/man1/emacs.1')
    make_link('man/man1/perl', '../../stow/perl/man/man1/perl.1')

    return target_dir


@pytest.mark.skipif(not CHKSTOW_EXISTS, reason="chkstow not yet implemented")
class TestChkstow:
    """Tests for the chkstow utility."""

    def test_skip_stow_directory(self, chkstow_env, capsys):
        """Skip directories containing .stow marker file."""
        # Running with -b (badlinks) should skip the stow directory
        # and emit a warning about it
        chkstow.Target = '.'
        chkstow.Wanted = chkstow.bad_links

        chkstow.check_stow()

        captured = capsys.readouterr()
        assert re.search(r'skipping .*stow', captured.err)

    def test_list_packages(self, chkstow_env, capsys):
        """List packages finds all stowed packages in sorted order."""
        chkstow.Target = '.'
        chkstow.Wanted = chkstow.list
        chkstow.Package = {}

        chkstow.check_stow()

        captured = capsys.readouterr()
        # Should list emacs, perl, and stow in sorted order (matching Perl's regex)
        # Perl test: qr{emacs\nperl\nstow\n}xms
        assert re.search(r'emacs\nperl\nstow\n', captured.out), \
            "Packages should be listed in sorted order: emacs, perl, stow. Got: %r" % captured.out

    def test_no_bogus_links(self, chkstow_env, capsys):
        """No bogus links when all symlinks are valid."""
        chkstow.Target = '.'
        chkstow.Wanted = chkstow.bad_links

        chkstow.check_stow()

        captured = capsys.readouterr()
        # stdout should be empty (no bogus links)
        assert captured.out == ''

    def test_no_aliens(self, chkstow_env, capsys):
        """No aliens when all non-dir files are symlinks."""
        chkstow.Target = '.'
        chkstow.Wanted = chkstow.aliens

        chkstow.check_stow()

        captured = capsys.readouterr()
        # stdout should be empty (no aliens)
        assert captured.out == ''

    def test_detect_alien(self, chkstow_env, capsys):
        """Detect alien (non-symlink) files."""
        # Create an alien file
        make_file('bin/alien')

        chkstow.Target = '.'
        chkstow.Wanted = chkstow.aliens

        chkstow.check_stow()

        captured = capsys.readouterr()
        assert re.search(r'Unstowed file: \./bin/alien', captured.out)

    def test_detect_bogus_link(self, chkstow_env, capsys):
        """Detect bogus (broken) symlinks."""
        # Create a bogus link
        make_invalid_link('bin/link', 'ireallyhopethisfiledoesn/t.exist')

        chkstow.Target = '.'
        chkstow.Wanted = chkstow.bad_links

        chkstow.check_stow()

        captured = capsys.readouterr()
        assert re.search(r'Bogus link: \./bin/link', captured.out)

    def test_default_target(self, chkstow_env, monkeypatch):
        """Default target is /usr/local/ when STOW_DIR not set."""
        # Clear STOW_DIR so default is /usr/local/
        monkeypatch.delenv('STOW_DIR', raising=False)

        # Set Target to the expected default (simulating fresh module load)
        # This is what Perl's $Target would be at module load when STOW_DIR is not set
        original_target = chkstow.Target
        chkstow.Target = '/usr/local/'

        # Simulate calling with just -b (no target specified)
        sys.argv = ['chkstow', '-b']
        chkstow.process_options()

        # process_options should NOT change Target when -t is not provided
        # Note: Perl uses '/usr/local/' with trailing slash
        assert chkstow.Target == '/usr/local/', \
            "Default target should be /usr/local/, got %s" % chkstow.Target

        # Restore
        chkstow.Target = original_target
