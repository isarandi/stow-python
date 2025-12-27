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
Test CLI option processing - Python port of t/cli_options.t

These tests use white-box testing by directly calling internal functions
and verifying the parsed option values, matching the Perl tests.
"""

import os
import sys

import pytest

from testutil import init_test_dirs

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


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Set up test environment for CLI option testing."""
    # Initialize test directories
    test_dir = str(tmp_path / 'test')
    abs_test_dir = init_test_dirs(test_dir)

    # Set HOME to test directory
    monkeypatch.setenv('HOME', abs_test_dir)

    # Change to target directory (like Perl tests)
    os.chdir(os.path.join(abs_test_dir, 'target'))

    return {
        'test_dir': test_dir,
        'abs_test_dir': abs_test_dir,
        'stow_dir': os.path.join(abs_test_dir, 'stow'),
        'target_dir': os.path.join(abs_test_dir, 'target'),
    }


class TestBasicOptionParsing:
    """Test basic CLI option parsing - corresponds to Perl tests 1-4."""

    def test_verbose_and_dir_options(self, test_env):
        """Test -v and -d options are parsed correctly."""
        args = ['-v', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # Test 1: verbose option
        assert options.get('verbose') == 1, 'verbose option should be 1'

        # Test 2: stow dir option
        assert options.get('dir') == test_env['stow_dir'], 'stow dir option'

        # Test 4: default to stow (package in stow list)
        assert pkgs_to_stow == ['dummy'], 'default to stow'


class TestMixedPackageOptions:
    """Test mixed -D/-S/-R package options - corresponds to Perl tests 5-6."""

    def test_mixed_delete_stow_restow(self, test_env):
        """Test that -D/-S/-R correctly categorize packages."""
        args = [
            '-v',
            '-D', 'd1', 'd2',
            '-S', 's1',
            '-R', 'r1',
            '-D', 'd3',
            '-S', 's2', 's3',
            '-R', 'r2'
        ]
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # Test 5: mixed deletes - note -R adds to both lists
        # Expected: d1, d2, r1, d3, r2
        assert pkgs_to_delete == ['d1', 'd2', 'r1', 'd3', 'r2'], 'mixed deletes'

        # Test 6: mixed stows
        # Expected: s1, r1, s2, s3, r2
        assert pkgs_to_stow == ['s1', 'r1', 's2', 's3', 'r2'], 'mixed stows'


class TestDeferOption:
    """Test --defer option regex compilation - corresponds to Perl test 7."""

    def test_defer_compiles_to_regex(self, test_env):
        """Test that --defer values are compiled to start-anchored regexes."""
        args = ['--defer=man', '--defer=info', 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # Verify defer patterns are compiled regexes anchored at start
        assert 'defer' in options, 'defer option should be set'
        assert len(options['defer']) == 2, 'should have 2 defer patterns'

        # Check that patterns are start-anchored (\A)
        for i, expected_pattern in enumerate(['man', 'info']):
            regex = options['defer'][i]
            # Should match at start of string
            msg = 'defer[%d] should match "%s"' % (i, expected_pattern)
            assert regex.match(expected_pattern), msg
            msg = 'defer[%d] should match "%s/foo"' % (i, expected_pattern)
            assert regex.match(expected_pattern + '/foo'), msg
            # Should not match in middle
            msg = 'defer[%d] should not match "x%s"' % (i, expected_pattern)
            assert not regex.match('x' + expected_pattern), msg


class TestOverrideOption:
    """Test --override option regex compilation - corresponds to Perl test 8."""

    def test_override_compiles_to_regex(self, test_env):
        """Test that --override values are compiled to start-anchored regexes."""
        args = ['--override=man', '--override=info', 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # Verify override patterns are compiled regexes anchored at start
        assert 'override' in options, 'override option should be set'
        assert len(options['override']) == 2, 'should have 2 override patterns'

        # Check that patterns are start-anchored (\A)
        for i, expected_pattern in enumerate(['man', 'info']):
            regex = options['override'][i]
            # Should match at start of string
            msg = 'override[%d] should match "%s"' % (i, expected_pattern)
            assert regex.match(expected_pattern), msg
            # Should not match in middle
            msg = 'override[%d] should not match "x%s"' % (i, expected_pattern)
            assert not regex.match('x' + expected_pattern), msg


class TestIgnoreOption:
    """Test --ignore option regex compilation - corresponds to Perl test 9."""

    def test_ignore_compiles_to_regex(self, test_env):
        """Test that --ignore values are compiled to end-anchored regexes."""
        args = ['--ignore=~', '--ignore=\\.#.*', 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # Verify ignore patterns are compiled regexes anchored at end
        assert 'ignore' in options, 'ignore option should be set'
        assert len(options['ignore']) == 2, 'should have 2 ignore patterns'

        # Check first pattern (~) - should match at end
        tilde_regex = options['ignore'][0]
        assert tilde_regex.search('file~'), 'ignore[0] should match "file~"'
        assert not tilde_regex.search('~file'), 'ignore[0] should not match "~file"'

        # Check second pattern (.#.*) - should match at end
        lock_regex = options['ignore'][1]
        assert lock_regex.search('.#file'), 'ignore[1] should match ".#file"'
        assert lock_regex.search('.#file.lock'), 'ignore[1] should match ".#file.lock"'


class TestNoHomeExpansion:
    """Test that $HOME is not expanded in paths - corresponds to Perl test 10."""

    def test_dollar_home_not_expanded(self, test_env, tmp_path):
        """Test that $HOME in target path is used literally."""
        # Create a directory with literal $HOME in the name
        dollar_home_dir = tmp_path / '$HOME'
        dollar_home_dir.mkdir()

        args = ['--target=' + str(dollar_home_dir), '-d', test_env['stow_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        # The path should be literal, not expanded
        assert options['target'] == str(dollar_home_dir), 'no expansion of $HOME in CLI args'


class TestSimulateOption:
    """Test -n/--simulate option."""

    def test_simulate_option(self, test_env):
        """Test -n sets simulate mode."""
        args = ['-n', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('simulate') == 1, 'simulate option should be set'


class TestCompatOption:
    """Test -p/--compat option."""

    def test_compat_option(self, test_env):
        """Test -p sets compat mode."""
        args = ['-p', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('compat') == 1, 'compat option should be set'


class TestNoFoldingOption:
    """Test --no-folding option."""

    def test_no_folding_option(self, test_env):
        """Test --no-folding sets no-folding mode."""
        args = ['--no-folding', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('no-folding') == 1, 'no-folding option should be set'


class TestAdoptOption:
    """Test --adopt option."""

    def test_adopt_option(self, test_env):
        """Test --adopt sets adopt mode."""
        args = ['--adopt', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('adopt') == 1, 'adopt option should be set'


class TestDotfilesOption:
    """Test --dotfiles option."""

    def test_dotfiles_option(self, test_env):
        """Test --dotfiles sets dotfiles mode."""
        args = ['--dotfiles', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('dotfiles') == 1, 'dotfiles option should be set'


class TestVerboseLevels:
    """Test verbose level accumulation."""

    def test_verbose_levels(self, test_env):
        """Test that multiple -v flags accumulate."""
        args = ['-v', '-v', '-v', '-d', test_env['stow_dir'],
                '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('verbose') == 3, 'multiple -v should accumulate'

    def test_verbose_with_value(self, test_env):
        """Test --verbose=N sets specific level."""
        args = ['--verbose=5', '-d', test_env['stow_dir'], '-t', test_env['target_dir'], 'dummy']
        options, pkgs_to_delete, pkgs_to_stow = parse_options(args)

        assert options.get('verbose') == 5, '--verbose=5 should set level to 5'
