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
Test processing of .stowrc file - Python port of t/rc_options.t

These tests use white-box testing by directly calling internal functions
and verifying the parsed option values, matching the Perl tests.
"""

import errno
import os
import sys

import pytest

from testutil import init_test_dirs, make_file

# Import the stow script as a module (Python 2/3 compatible)
STOW_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin', 'stow')
if sys.version_info[0] >= 3:
    import importlib.util
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("stow_module", STOW_SCRIPT)
    spec = importlib.util.spec_from_loader("stow_module", loader)
    stow_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stow_module)
else:
    import imp
    stow_module = imp.load_source("stow_module", STOW_SCRIPT)

# Import functions from stow module for white-box testing
parse_options = stow_module.parse_options
process_options = stow_module.process_options
get_config_file_options = stow_module.get_config_file_options
expand_environment = stow_module.expand_environment
expand_tilde = stow_module.expand_tilde
expand_filepath = stow_module.expand_filepath


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Set up test environment for RC option testing."""
    # Initialize test directories
    test_dir = str(tmp_path / 'test')
    abs_test_dir = init_test_dirs(test_dir)

    # Set HOME to test directory
    monkeypatch.setenv('HOME', abs_test_dir)

    # Change to run_from directory (like Perl tests)
    run_from = os.path.join(abs_test_dir, 'run_from')
    try:
        os.makedirs(run_from)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    monkeypatch.chdir(run_from)

    yield {
        'test_dir': test_dir,
        'abs_test_dir': abs_test_dir,
        'stow_dir': os.path.join(abs_test_dir, 'stow'),
        'target_dir': os.path.join(abs_test_dir, 'target'),
        'run_from': run_from,
        'cwd_rc_file': '.stowrc',
        'home_rc_file': os.path.join(abs_test_dir, '.stowrc'),
    }


# =========== RC Loading Tests ===========
# Basic parsing and loading rc file tests.
# ========================================


class TestNoStowrcFile:
    """Test behavior when no .stowrc file exists."""

    def test_default_target_with_no_stowrc(self, test_env, monkeypatch):
        """Default --target with no .stowrc should be parent of cwd."""
        # Delete HOME and STOW_DIR to test defaults
        monkeypatch.delenv('HOME', raising=False)
        monkeypatch.delenv('STOW_DIR', raising=False)
        # Also ensure no .stowrc in cwd
        cwd_rc = os.path.join(test_env['run_from'], '.stowrc')
        if os.path.exists(cwd_rc):
            os.remove(cwd_rc)
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        options, pkgs_to_delete, pkgs_to_stow = process_options()

        # Default target is parent of cwd
        assert options.get('target') == test_env['abs_test_dir'], \
            "default --target with no .stowrc, got %s" % options.get('target')
        # Default dir is cwd
        assert options.get('dir') == test_env['run_from'], \
            "default -d with no .stowrc, got %s" % options.get('dir')


class TestCwdStowrcRelativePaths:
    """Test .stowrc file in cwd with relative paths."""

    def test_relative_paths_from_cwd_stowrc(self, test_env, monkeypatch):
        """Relative paths in $PWD/.stowrc should be used."""
        # Delete HOME so only cwd stowrc is used
        monkeypatch.delenv('HOME', raising=False)
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(test_env['cwd_rc_file'], """\
-d ../stow
--target ../target
""")
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('target') == '../target', \
            "relative --target from $PWD/.stowrc"
        assert options.get('dir') == '../stow', \
            "relative -d from $PWD/.stowrc"


class TestCwdStowrcAbsolutePaths:
    """Test .stowrc file in cwd with absolute paths."""

    def test_absolute_paths_from_cwd_stowrc(self, test_env, monkeypatch):
        """Absolute paths in $PWD/.stowrc should be used."""
        monkeypatch.delenv('HOME', raising=False)
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(
            test_env['cwd_rc_file'],
            "-d %s/stow\n--target %s/target\n" % (
                test_env['abs_test_dir'], test_env['abs_test_dir']))
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('target') == "%s/target" % test_env['abs_test_dir'], \
            "absolute --target from $PWD/.stowrc"
        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "absolute -d from $PWD/.stowrc"


class TestHomeStowrcRelativePaths:
    """Test ~/.stowrc file with relative paths."""

    def test_relative_paths_from_home_stowrc(self, test_env, monkeypatch):
        """Relative paths in $HOME/.stowrc should be used."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(test_env['home_rc_file'], """\
-d ../stow
--target ../target
""")
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('target') == '../target', \
            "--target from $HOME/.stowrc"
        assert options.get('dir') == '../stow', \
            "-d ../stow from $HOME/.stowrc"


class TestHomeStowrcAbsolutePaths:
    """Test ~/.stowrc file with absolute paths."""

    def test_absolute_paths_from_home_stowrc(self, test_env, monkeypatch):
        """Absolute paths in $HOME/.stowrc should be used."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(
            test_env['home_rc_file'],
            "-d %s/stow\n--target %s/target\n" % (
                test_env['abs_test_dir'], test_env['abs_test_dir']))
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('target') == "%s/target" % test_env['abs_test_dir'], \
            "--target from $HOME/.stowrc"
        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "-d %s/stow from $HOME/.stowrc" % test_env['abs_test_dir']


class TestStowrcPathsWithSpaces:
    """Test ~/.stowrc with paths containing spaces."""

    def test_paths_with_spaces_in_stowrc(self, test_env, monkeypatch):
        """Paths with spaces should be properly quoted and handled."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(
            test_env['home_rc_file'],
            '-d "%s/stow directory"\n--target "%s/target"\n' % (
                test_env['abs_test_dir'], test_env['abs_test_dir']))
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('dir') == "%s/stow directory" % test_env['abs_test_dir'], \
            "-d from $HOME/.stowrc with spaces"


class TestCwdOverridesHomeStowrc:
    """Test that $PWD/.stowrc overrides $HOME/.stowrc."""

    def test_cwd_stowrc_overrides_home_stowrc(self, test_env, monkeypatch):
        """Options in $PWD/.stowrc should override $HOME/.stowrc."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(
            test_env['home_rc_file'],
            "-d %s/stow-will-be-overridden\n"
            "--target %s/target-will-be-overridden\n--defer=info\n" % (
                test_env['abs_test_dir'], test_env['abs_test_dir']))
        make_file(
            test_env['cwd_rc_file'],
            "-d %s/stow\n--target %s/target\n--defer=man\n" % (
                test_env['abs_test_dir'], test_env['abs_test_dir']))
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('target') == "%s/target" % test_env['abs_test_dir'], \
            "--target overridden by $PWD/.stowrc"
        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "-d overridden by $PWD/.stowrc"

        # Defer options should be merged (both info and man)
        assert 'defer' in options, 'defer option should be set'
        assert len(options['defer']) == 2, 'should have 2 defer patterns'
        # First pattern from home rc (info), second from cwd rc (man)
        assert options['defer'][0].match('info'), 'defer[0] should match info'
        assert options['defer'][1].match('man'), 'defer[1] should match man'


class TestCliOverridesStowrc:
    """Test that CLI options override .stowrc options."""

    def test_cli_overwrites_scalar_rc_option(self, test_env, monkeypatch):
        """CLI options should overwrite conflicting .stowrc options."""
        stow_dir = '%s/stow' % test_env['abs_test_dir']
        monkeypatch.setattr(sys, 'argv', ['stow', '-d', stow_dir, 'dummy'])

        make_file(test_env['home_rc_file'], "-d bad/path\n")
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "cli overwrite scalar rc option"


class TestDeferOptionMerging:
    """Test that list options like --defer are merged from rc and CLI."""

    def test_defer_options_merge(self, test_env, monkeypatch):
        """--defer from .stowrc and CLI should be merged."""
        monkeypatch.setattr(sys, 'argv', ['stow', '--defer=man', 'dummy'])

        make_file(test_env['home_rc_file'], "--defer=info\n")
        options, pkgs_to_delete, pkgs_to_stow = process_options()

        # Both defer options should be present
        assert 'defer' in options, 'defer option should be set'
        assert len(options['defer']) == 2, 'should have 2 defer patterns'
        assert options['defer'][0].match('info'), 'defer[0] should match info'
        assert options['defer'][1].match('man'), 'defer[1] should match man'


# ======== Filepath Expansion Tests ========
# Test proper filepath expansion in rc file.
# ==========================================


class TestExpandEnvironment:
    """Test environment variable expansion function."""

    def test_expand_home(self, test_env):
        """$HOME should be expanded."""
        result = expand_environment('$HOME/stow', '--dir option')
        assert result == "%s/stow" % test_env['abs_test_dir'], 'expand $HOME'

    def test_expand_braced_home(self, test_env):
        """${HOME} should be expanded."""
        result = expand_environment('${HOME}/stow', '--dir option')
        assert result == "%s/stow" % test_env['abs_test_dir'], 'expand ${HOME}'

    def test_undefined_var_error(self, test_env, monkeypatch):
        """Undefined environment variable should cause error."""
        monkeypatch.delenv('UNDEFINED', raising=False)

        with pytest.raises(SystemExit):
            expand_environment('$UNDEFINED', '--foo option')

    def test_undefined_braced_var_error(self, test_env, monkeypatch):
        """Undefined ${VAR} should cause error."""
        monkeypatch.delenv('UNDEFINED', raising=False)

        with pytest.raises(SystemExit):
            expand_environment('${UNDEFINED}', '--foo option')

    def test_expand_var_with_underscore(self, test_env, monkeypatch):
        """Environment variable with underscore should expand correctly."""
        monkeypatch.setenv('WITH_UNDERSCORE', 'test string')

        result = expand_environment('${WITH_UNDERSCORE}', '--dir option')
        assert result == 'test string', 'expand ${WITH_UNDERSCORE}'

    def test_escaped_dollar_not_expanded(self, test_env):
        """Escaped $ should not be expanded."""
        result = expand_environment('\\$HOME/stow', '--dir option')
        assert result == '$HOME/stow', 'expand \\$HOME'


class TestExpandTilde:
    """Test tilde (~) expansion."""

    def test_tilde_expansion_to_home(self, test_env):
        """~ should be expanded to $HOME."""
        result = expand_tilde('~/path')
        assert result == "%s/path" % test_env['abs_test_dir'], 'tilde expansion to $HOME'

    def test_middle_tilde_not_expanded(self, test_env):
        """~ in middle of path should not be expanded."""
        result = expand_tilde('/path/~/here')
        assert result == '/path/~/here', 'middle ~ not expanded'

    def test_escaped_tilde(self, test_env):
        """Escaped tilde should not be expanded."""
        result = expand_tilde('\\~/path')
        assert result == '~/path', 'escaped tilde'


class TestExpansionInRcFile:
    """Test that expansion is applied correctly in .stowrc files."""

    def test_env_expansion_applied_to_dir_and_target(self, test_env, monkeypatch):
        """Environment variables should be expanded in --dir and --target."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        # Note: Perl uses <<'HERE' (raw heredoc) so \\$FOO\\$ is literal in file
        # In Python, we need \\\\ to write \\ to the file
        make_file(test_env['home_rc_file'], """\
--dir=$HOME/stow
--target="$HOME/dir with space in/file with space in"
--ignore=\\\\$FOO\\\\$
--defer="foo\\\\b.*bar"
--defer="\\\\.jpg$"
--override=\\\\.png$
--override=bin|man
--ignore='perllocal\\\\.pod'
--ignore='\\\\.packlist'
--ignore='\\\\.bs'
""")
        options, pkgs_to_delete, pkgs_to_stow = get_config_file_options()

        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "apply environment expansion on --dir"
        expected_target = "%s/dir with space in/file with space in" % (
            test_env['abs_test_dir'])
        assert options.get('target') == expected_target, \
            "apply environment expansion on --target"

        # Ignore patterns should have escaped $ converted to literal $
        assert 'ignore' in options, 'ignore option should be set'
        # Check that $FOO$ is literal (backslash removed)
        assert any(r.search('$FOO$') for r in options['ignore']), \
            'environment expansion not applied on --ignore but backslash removed'

        # Defer patterns should be present
        assert 'defer' in options, 'defer option should be set'
        assert len(options['defer']) == 2, 'should have 2 defer patterns'

        # Override patterns should be present
        assert 'override' in options, 'override option should be set'
        assert len(options['override']) == 2, 'should have 2 override patterns'

    def test_tilde_expansion_applied_correctly(self, test_env, monkeypatch):
        """Tilde should be expanded in --dir/--target but not patterns."""
        monkeypatch.setattr(sys, 'argv', ['stow', 'dummy'])

        make_file(test_env['home_rc_file'], """\
--dir=~/stow
--target=~/stow
--ignore=~/stow
--defer=~/stow
--override=~/stow
""")
        options, pkgs_to_delete, pkgs_to_stow = get_config_file_options()

        assert options.get('dir') == "%s/stow" % test_env['abs_test_dir'], \
            "apply tilde expansion on $HOME/.stowrc --dir"
        assert options.get('target') == "%s/stow" % test_env['abs_test_dir'], \
            "apply tilde expansion on $HOME/.stowrc --target"

        # Tilde should NOT be expanded in pattern options
        assert 'ignore' in options, 'ignore option should be set'
        assert options['ignore'][0].search('~/stow'), \
            "tilde expansion not applied on --ignore"

        assert 'defer' in options, 'defer option should be set'
        assert options['defer'][0].match('~/stow'), \
            "tilde expansion not applied on --defer"

        assert 'override' in options, 'override option should be set'
        assert options['override'][0].match('~/stow'), \
            "tilde expansion not applied on --override"
