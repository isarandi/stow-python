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
Testing ignore lists.
"""

import os
import tempfile

import pytest

from testutil import (
    new_Stow, make_path, make_file,
    setup_global_ignore, setup_package_ignore,
    stow_module, join_paths,
)
LOCAL_IGNORE_FILE = stow_module.LOCAL_IGNORE_FILE
GLOBAL_IGNORE_FILE = stow_module.GLOBAL_IGNORE_FILE


def check_ignores(stow, stow_path, package, context, tests):
    """
    Test whether paths are correctly ignored or not.

    Parameters:
        stow: Stow instance
        stow_path: path to stow directory
        package: package name
        context: description for error messages
        tests: list of (path, should_ignore) tuples
    """
    for path, should_ignore in tests:
        not_str = '' if should_ignore else ' not'
        was_ignored = stow.ignore(stow_path, package, path)
        assert was_ignored == should_ignore, "Should%s ignore %s %s" % (not_str, path, context)


def check_local_ignore_list_always_ignored_at_top_level(stow, stow_path, package, context):
    """Local ignore file should always be ignored at top level but not in subdirs."""
    check_ignores(stow, stow_path, package, context, [
        (LOCAL_IGNORE_FILE, True),
        ("subdir/" + LOCAL_IGNORE_FILE, False),
    ])


def check_built_in_list(stow, stow_path, package, context, expect_ignores):
    """Test built-in ignore patterns."""
    # Test CVS, .cvsignore, #autosave# patterns
    for ignored in ['CVS', '.cvsignore', '#autosave#']:
        for path in [ignored, "foo/bar/" + ignored]:
            suffix = path + ".suffix"
            # Create prefix version: 'CVS' -> 'prefix.CVS', 'foo/bar/CVS' -> 'foo/bar/prefix.CVS'
            parts = path.rsplit('/', 1)
            if len(parts) == 2:
                prefix = parts[0] + "/prefix." + parts[1]
            else:
                prefix = "prefix." + parts[0]

            check_ignores(stow, stow_path, package, context, [
                (path, expect_ignores),
                (prefix, False),
                (suffix, False),
            ])

    # The pattern catching lock files allows suffixes but not prefixes
    for ignored in ['.#lock-file']:
        for path in [ignored, "foo/bar/" + ignored]:
            suffix = path + ".suffix"
            parts = path.rsplit('/', 1)
            if len(parts) == 2:
                prefix = parts[0] + "/prefix." + parts[1]
            else:
                prefix = "prefix." + parts[0]

            check_ignores(stow, stow_path, package, context, [
                (path, expect_ignores),
                (prefix, False),
                (suffix, expect_ignores),
            ])


def check_user_global_list(stow, stow_path, package, context, expect_ignores):
    """Test user's global ignore patterns."""
    for path_prefix in ['', 'foo/bar/']:
        check_ignores(stow, stow_path, package, context, [
            (path_prefix + "exact", expect_ignores),
            (path_prefix + "0exact", False),
            (path_prefix + "exact1", False),
            (path_prefix + "0exact1", False),
            (path_prefix + "substring", False),
            (path_prefix + "0substring", False),
            (path_prefix + "substring1", False),
            (path_prefix + "0substring1", expect_ignores),
        ])


def do_setup_user_global_list():
    """Set up user's global ignore list in a temp home directory."""
    os.environ['HOME'] = tempfile.mkdtemp()
    setup_global_ignore("""\
exact
.+substring.+ # here's a comment
.+\\.extension
myprefix.+       #hi mum
""")


def do_setup_package_local_list(stow, stow_path, package, contents):
    """Set up package-local ignore list."""
    package_path = join_paths(stow_path, package)
    make_path(package_path)
    package_ignore = setup_package_ignore(package_path, contents)
    stow.invalidate_memoized_regexp(package_ignore)
    return package_ignore


class TestIgnoreBuiltInList:
    """Test built-in ignore list (no user global list)."""

    def test_local_ignore_always_ignored_at_top_level(self, stow_test_env):
        stow = new_Stow()
        stow_path = '../stow'
        package = 'non-existent-package'
        context = "when using built-in list"
        check_local_ignore_list_always_ignored_at_top_level(stow, stow_path, package, context)

    def test_built_in_patterns(self, stow_test_env):
        stow = new_Stow()
        stow_path = '../stow'
        package = 'non-existent-package'
        context = "when using built-in list"
        check_built_in_list(stow, stow_path, package, context, expect_ignores=True)


class TestIgnoreUserGlobalList:
    """Test ~/.stow-global-ignore."""

    @pytest.fixture(autouse=True)
    def setup_global_list(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        do_setup_user_global_list()
        self.package = 'non-existent-package'
        self.context = "when using ~/" + GLOBAL_IGNORE_FILE

    def test_local_ignore_always_ignored_at_top_level(self):
        check_local_ignore_list_always_ignored_at_top_level(
            self.stow, self.stow_path, self.package, self.context)

    def test_built_in_patterns_disabled(self):
        check_built_in_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_user_global_patterns(self):
        check_user_global_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=True)


class TestIgnoreEmptyPackageLocalList:
    """Test empty package-local .stow-local-ignore."""

    @pytest.fixture(autouse=True)
    def setup_empty_local_list(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        do_setup_user_global_list()
        self.package = 'ignorepkg'
        self.local_ignore = do_setup_package_local_list(
            self.stow, self.stow_path, self.package, "")
        self.context = "when using empty " + self.local_ignore

    def test_local_ignore_always_ignored_at_top_level(self):
        check_local_ignore_list_always_ignored_at_top_level(
            self.stow, self.stow_path, self.package, self.context)

    def test_built_in_patterns_disabled(self):
        check_built_in_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_user_global_patterns_disabled(self):
        check_user_global_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_nothing_ignored(self):
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ('random', False),
            ('foo2/bar', False),
            ('foo2/bars', False),
            ('foo2/bar/random', False),
            ('foo2/bazqux', False),
            ('xfoo2/bazqux', False),
        ])


class TestIgnorePackageLocalSegmentRegexps:
    """Test package-local .stow-local-ignore with only path segment regexps."""

    @pytest.fixture(autouse=True)
    def setup_local_list(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        do_setup_user_global_list()
        self.package = 'ignorepkg'
        self.local_ignore = do_setup_package_local_list(
            self.stow, self.stow_path, self.package, "random\n")
        self.context = "when using %s with only path segment regexps" % self.local_ignore

    def test_local_ignore_always_ignored_at_top_level(self):
        check_local_ignore_list_always_ignored_at_top_level(
            self.stow, self.stow_path, self.package, self.context)

    def test_built_in_patterns_disabled(self):
        check_built_in_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_user_global_patterns_disabled(self):
        check_user_global_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_segment_pattern_matches(self):
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ('random', True),
            ('foo2/bar', False),
            ('foo2/bars', False),
            ('foo2/bar/random', True),
            ('foo2/bazqux', False),
            ('xfoo2/bazqux', False),
        ])


class TestIgnorePackageLocalFullPathRegexps:
    """Test package-local .stow-local-ignore with only full path regexps."""

    @pytest.fixture(autouse=True)
    def setup_local_list(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        do_setup_user_global_list()
        self.package = 'ignorepkg'
        self.local_ignore = do_setup_package_local_list(
            self.stow, self.stow_path, self.package, "foo2/bar\n")
        self.context = "when using %s with only full path regexps" % self.local_ignore

    def test_local_ignore_always_ignored_at_top_level(self):
        check_local_ignore_list_always_ignored_at_top_level(
            self.stow, self.stow_path, self.package, self.context)

    def test_built_in_patterns_disabled(self):
        check_built_in_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_user_global_patterns_disabled(self):
        check_user_global_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_full_path_pattern_matches(self):
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ('random', False),
            ('foo2/bar', True),
            ('foo2/bars', False),
            ('foo2/bar/random', True),
            ('foo2/bazqux', False),
            ('xfoo2/bazqux', False),
        ])


class TestIgnorePackageLocalMixedRegexps:
    """Test package-local .stow-local-ignore with a mixture of regexps."""

    @pytest.fixture(autouse=True)
    def setup_local_list(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        do_setup_user_global_list()
        self.package = 'ignorepkg'
        self.local_ignore = do_setup_package_local_list(
            self.stow, self.stow_path, self.package, """\
foo2/bar
random
foo2/baz.+
""")
        self.context = "when using %s with mixture of regexps" % self.local_ignore

    def test_local_ignore_always_ignored_at_top_level(self):
        check_local_ignore_list_always_ignored_at_top_level(
            self.stow, self.stow_path, self.package, self.context)

    def test_built_in_patterns_disabled(self):
        check_built_in_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_user_global_patterns_disabled(self):
        check_user_global_list(
            self.stow, self.stow_path, self.package, self.context, expect_ignores=False)

    def test_mixed_pattern_matches(self):
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ('random', True),
            ('foo2/bar', True),
            ('foo2/bars', False),
            ('foo2/bar/random', True),
            ('foo2/bazqux', True),
            ('xfoo2/bazqux', False),
        ])


class TestIgnoreExamplesFromManual:
    """Test examples from the manual."""

    @pytest.fixture(autouse=True)
    def setup_env(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        self.package = 'ignorepkg'
        self.context = "(example from manual)"

    @pytest.mark.parametrize("regex", [
        'bazqux',
        'baz.*',
        '.*qux',
        'bar/.*x',
        '^/foo/.*qux',
    ])
    def test_patterns_that_match(self, regex):
        do_setup_package_local_list(self.stow, self.stow_path, self.package, regex + "\n")
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ("foo/bar/bazqux", True),
        ])

    @pytest.mark.parametrize("regex", [
        'bar',
        'baz',
        'qux',
        'o/bar/b',
    ])
    def test_patterns_that_dont_match(self, regex):
        do_setup_package_local_list(self.stow, self.stow_path, self.package, regex + "\n")
        check_ignores(self.stow, self.stow_path, self.package, self.context, [
            ("foo/bar/bazqux", False),
        ])


class TestIgnoreInvalidRegexp:
    """Test handling of invalid regular expressions."""

    @pytest.fixture(autouse=True)
    def setup_env(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        self.package = 'ignorepkg'

    def test_invalid_segment_regexp(self):
        context = "Invalid segment regexp in list"
        contents = """\
this one's ok
this one isn't|*!
but this one is
"""
        do_setup_package_local_list(self.stow, self.stow_path, self.package, contents)
        with pytest.raises(Exception, match=r"Failed to compile regexp"):
            check_ignores(self.stow, self.stow_path, self.package, context, [
                ("foo/bar/bazqux", True),
            ])

    def test_invalid_full_path_regexp(self):
        context = "Invalid full path regexp in list"
        contents = """\
this one's ok
this/one isn't|*!
but this one is
"""
        do_setup_package_local_list(self.stow, self.stow_path, self.package, contents)
        with pytest.raises(Exception, match=r"Failed to compile regexp"):
            check_ignores(self.stow, self.stow_path, self.package, context, [
                ("foo/bar/bazqux", True),
            ])


class TestIgnoreViaStow:
    """Test that ignore patterns work during actual stow operations."""

    @pytest.fixture(autouse=True)
    def setup_env(self, stow_test_env):
        self.stow = new_Stow()
        self.stow_path = '../stow'
        self.package = 'pkg1'

    def test_top_dir_ignored(self):
        make_path("%s/%s/foo/bar" % (self.stow_path, self.package))
        make_file("%s/%s/foo/bar/baz" % (self.stow_path, self.package))
        do_setup_package_local_list(self.stow, self.stow_path, self.package, 'foo')
        self.stow.plan_stow(self.package)
        assert len(self.stow.get_tasks()) == 0, 'top dir ignored'
        assert self.stow.get_conflict_count() == 0, 'top dir ignored, no conflicts'

    @pytest.mark.parametrize("ignore_pattern", [
        'bar',
        'foo/bar',
        '/foo/bar',
        '^/foo/bar',
        '^/fo.+ar',
    ])
    def test_bar_ignored(self, ignore_pattern):
        make_path("%s/%s/foo/bar" % (self.stow_path, self.package))
        make_file("%s/%s/foo/bar/baz" % (self.stow_path, self.package))
        make_path("foo")
        do_setup_package_local_list(self.stow, self.stow_path, self.package, ignore_pattern)
        self.stow.plan_stow(self.package)
        assert len(self.stow.get_tasks()) == 0, "bar ignored via %s" % ignore_pattern
        assert self.stow.get_conflict_count() == 0, 'bar ignored, no conflicts'

    def test_qux_stowed_bar_ignored(self):
        make_path("%s/%s/foo/bar" % (self.stow_path, self.package))
        make_file("%s/%s/foo/bar/baz" % (self.stow_path, self.package))
        make_path("foo")
        # Use '^/fo.+ar' pattern to match Perl test - this is the last pattern
        # tested in the parametrized test_bar_ignored, and the Perl test
        # continues from that state
        do_setup_package_local_list(self.stow, self.stow_path, self.package, '^/fo.+ar')
        make_file("%s/%s/foo/qux" % (self.stow_path, self.package))
        self.stow.plan_stow(self.package)
        self.stow.process_tasks()
        assert self.stow.get_conflict_count() == 0, 'no conflicts stowing qux'
        assert not os.path.exists("foo/bar"), "bar ignore prevented stow"
        assert os.path.islink("foo/qux"), "qux not ignored and stowed"
        assert os.readlink("foo/qux") == "../%s/%s/foo/qux" % (self.stow_path, self.package), \
            "qux stowed correctly"
