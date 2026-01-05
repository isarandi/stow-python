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
"""

import os
import re

import pytest

from testutil import init_test_dirs, make_path, make_file, make_link, make_invalid_link

# Check if chkstow module exists
CHKSTOW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "bin", "chkstow"
)
CHKSTOW_EXISTS = os.path.exists(CHKSTOW_PATH)

# Try to import chkstow module if it exists
chkstow = None
if CHKSTOW_EXISTS:
    try:
        import importlib.util
        import importlib.machinery

        loader = importlib.machinery.SourceFileLoader("chkstow", CHKSTOW_PATH)
        spec = importlib.util.spec_from_loader("chkstow", loader)
        if spec is not None:
            chkstow = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(chkstow)
    except Exception:
        chkstow = None


@pytest.fixture
def chkstow_env(tmp_path, monkeypatch):
    """Set up test environment matching the Perl test structure."""
    monkeypatch.chdir(tmp_path)

    # Initialize test dirs
    init_test_dirs(str(tmp_path / "test"))
    target_dir = tmp_path / "test" / "target"
    monkeypatch.chdir(target_dir)

    # Setup stow directory
    make_path("stow")
    make_file("stow/.stow")

    # perl package
    make_path("stow/perl/bin")
    make_file("stow/perl/bin/perl")
    make_file("stow/perl/bin/a2p")
    make_path("stow/perl/info")
    make_file("stow/perl/info/perl")
    make_path("stow/perl/lib/perl")
    make_path("stow/perl/man/man1")
    make_file("stow/perl/man/man1/perl.1")

    # emacs package
    make_path("stow/emacs/bin")
    make_file("stow/emacs/bin/emacs")
    make_file("stow/emacs/bin/etags")
    make_path("stow/emacs/info")
    make_file("stow/emacs/info/emacs")
    make_path("stow/emacs/libexec/emacs")
    make_path("stow/emacs/man/man1")
    make_file("stow/emacs/man/man1/emacs.1")

    # Setup target directory with symlinks
    make_path("bin")
    make_link("bin/a2p", "../stow/perl/bin/a2p")
    make_link("bin/emacs", "../stow/emacs/bin/emacs")
    make_link("bin/etags", "../stow/emacs/bin/etags")
    make_link("bin/perl", "../stow/perl/bin/perl")

    make_path("info")
    make_link("info/emacs", "../stow/emacs/info/emacs")
    make_link("info/perl", "../stow/perl/info/perl")

    make_link("lib", "stow/perl/lib")
    make_link("libexec", "stow/emacs/libexec")

    make_path("man")
    make_path("man/man1")
    make_link("man/man1/emacs", "../../stow/emacs/man/man1/emacs.1")
    make_link("man/man1/perl", "../../stow/perl/man/man1/perl.1")

    return target_dir


@pytest.mark.skipif(not CHKSTOW_EXISTS, reason="chkstow not yet implemented")
class TestChkstow:
    """Tests for the chkstow utility."""

    def test_skip_stow_directory(self, chkstow_env, capsys):
        """Skip directories containing .stow marker file."""
        list(chkstow.find_bad_links("."))

        captured = capsys.readouterr()
        assert re.search(r"skipping .*stow", captured.err)

    def test_list_packages(self, chkstow_env):
        """List packages finds all stowed packages in sorted order."""
        packages = chkstow.list_packages(".")

        assert packages == ["emacs", "perl", "stow"]

    def test_no_bogus_links(self, chkstow_env):
        """No bogus links when all symlinks are valid."""
        bad_links = list(chkstow.find_bad_links("."))

        assert bad_links == []

    def test_no_aliens(self, chkstow_env):
        """No aliens when all non-dir files are symlinks."""
        aliens = list(chkstow.find_aliens("."))

        assert aliens == []

    def test_detect_alien(self, chkstow_env):
        """Detect alien (non-symlink) files."""
        make_file("bin/alien")

        aliens = list(chkstow.find_aliens("."))

        assert any("bin/alien" in a for a in aliens)

    def test_detect_bogus_link(self, chkstow_env):
        """Detect bogus (broken) symlinks."""
        make_invalid_link("bin/link", "ireallyhopethisfiledoesn/t.exist")

        bad_links = list(chkstow.find_bad_links("."))

        assert any("bin/link" in b for b in bad_links)

    def test_default_target(self, chkstow_env):
        """parse_args returns DEFAULT_TARGET when no -t specified."""
        target, mode = chkstow.parse_args(["-b"])

        assert target == chkstow.DEFAULT_TARGET
        assert mode == chkstow.Mode.BAD_LINKS
