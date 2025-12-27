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
Test unstowing packages - Python port of t/unstow.t
"""

import os
import sys
import pytest
import re

# Python 2/3 compatible StringIO and redirect_stderr
if sys.version_info[0] >= 3:
    from io import StringIO
    from contextlib import redirect_stderr
else:
    from StringIO import StringIO
    import contextlib

    @contextlib.contextmanager
    def redirect_stderr(new_stderr):
        old_stderr = sys.stderr
        sys.stderr = new_stderr
        try:
            yield
        finally:
            sys.stderr = old_stderr

from testutil import (
    init_test_dirs, new_Stow, new_compat_Stow,
    make_path, make_file, make_link, make_invalid_link,
    remove_dir, is_nonexistent_path, is_dir_not_symlink,
    canon_path,
)


def check_protected_dirs_skipped(stderr, dirs=None):
    """
    Verify that warnings are emitted for skipping marked Stow directories.

    In compat mode, Stow should warn when it encounters other Stow directories
    (like stow2) that should be skipped.
    """
    if dirs is None:
        dirs = ['stow', 'stow2']
    for dir_name in dirs:
        assert re.search(
            r'WARNING.*skipping marked Stow directory %s' % re.escape(dir_name),
            stderr
        ), "Should warn when skipping marked directory %s" % dir_name


# Store the repo directory for later use
REPO = os.getcwd()


def init_stow2():
    """Create an alternate stow directory as subdir of target."""
    make_path('stow2')
    make_file('stow2/.stow')


UNOWNED_DIRS = ['unowned-dir', '.unowned-dir', 'dot-unowned-dir']


def create_unowned_files():
    """
    Make things harder for Stow to figure out, by adding
    a bunch of alien files unrelated to Stow.
    """
    for dir_ in ['.'] + UNOWNED_DIRS:
        for subdir in ['.'] + UNOWNED_DIRS:
            path = os.path.join(dir_, subdir)
            make_path(path)
            make_file(os.path.join(path, 'unowned'))
            make_file(os.path.join(path, '.unowned'))
            make_file(os.path.join(path, 'dot-unowned'))


def run_subtests(name, test_func, abs_test_dir, setup_func=None, setup_opts=None,
                 check_compat_stderr=None):
    """
    Run a subtest twice: with compat off then on, in parallel test trees.

    Parameters:
        name: test name
        test_func: callable taking (stow, test_dir) or (stow, test_dir, stderr_capture)
        abs_test_dir: absolute path to test directory from stow_test_env fixture
        setup_func: optional callable taking test_dir and returning opts dict
        setup_opts: optional dict of options to pass to Stow constructor
        check_compat_stderr: optional callable taking stderr string for compat mode verification
    """
    # Derive test_dir and compat_test_dir from abs_test_dir
    test_dir = abs_test_dir
    compat_test_dir = abs_test_dir + '-compat'
    compat_abs_test_dir = init_test_dirs(compat_test_dir)

    # Non-compat mode
    os.environ['HOME'] = test_dir
    os.chdir(os.path.join(test_dir, 'target'))
    create_unowned_files()

    if setup_func:
        opts = setup_func(test_dir)
    elif setup_opts:
        opts = setup_opts.copy()
    else:
        opts = {}

    if opts.get('dir'):
        make_path(opts['dir'])

    stow = new_Stow(**opts)
    test_func(stow, test_dir)

    # Compat mode - capture stderr for verification
    os.environ['HOME'] = compat_abs_test_dir
    os.chdir(os.path.join(compat_test_dir, 'target'))
    create_unowned_files()

    if setup_func:
        opts = setup_func(compat_test_dir)
    elif setup_opts:
        opts = setup_opts.copy()
    else:
        opts = {}

    if opts.get('dir'):
        make_path(opts['dir'])

    stow = new_compat_Stow(**opts)

    # Capture stderr during compat mode test
    stderr_capture = StringIO()
    with redirect_stderr(stderr_capture):
        test_func(stow, compat_test_dir)

    # If a compat stderr check function is provided, run it
    if check_compat_stderr:
        check_compat_stderr(stderr_capture.getvalue())


class TestUnstowSimpleTree:
    """Test unstowing a simple tree minimally."""

    def test_unstow_simple_tree(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('../stow/pkg1/bin1')
            make_file('../stow/pkg1/bin1/file1')
            make_link('bin1', '../stow/pkg1/bin1')

            stow.plan_unstow('pkg1')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile('../stow/pkg1/bin1/file1')
            assert not os.path.exists('bin1'), 'unstow a simple tree'

        run_subtests("unstow a simple tree minimally", test_func, stow_test_env)


class TestUnstowFromExistingDir:
    """Test unstowing a simple tree from an existing directory."""

    def test_unstow_from_existing_dir(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('lib2')
            make_path('../stow/pkg2/lib2')
            make_file('../stow/pkg2/lib2/file2')
            make_link('lib2/file2', '../../stow/pkg2/lib2/file2')

            stow.plan_unstow('pkg2')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile('../stow/pkg2/lib2/file2')
            assert os.path.isdir('lib2'), 'unstow simple tree from a pre-existing directory'

        run_subtests("unstow a simple tree from an existing directory", test_func, stow_test_env)


class TestFoldTreeAfterUnstowing:
    """Test fold tree after unstowing."""

    def test_fold_tree_after_unstowing(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('bin3')

            make_path('../stow/pkg3a/bin3')
            make_file('../stow/pkg3a/bin3/file3a')
            make_link('bin3/file3a', '../../stow/pkg3a/bin3/file3a')  # emulate stow

            make_path('../stow/pkg3b/bin3')
            make_file('../stow/pkg3b/bin3/file3b')
            make_link('bin3/file3b', '../../stow/pkg3b/bin3/file3b')  # emulate stow

            stow.plan_unstow('pkg3b')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.islink('bin3')
            assert os.readlink('bin3') == '../stow/pkg3a/bin3', 'fold tree after unstowing'

        run_subtests("fold tree after unstowing", test_func, stow_test_env)


class TestInvalidLinkOwnedByStow:
    """Test existing link is owned by stow but is invalid so it gets removed anyway."""

    def test_invalid_link_owned_by_stow(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('bin4')
            make_path('../stow/pkg4/bin4')
            make_file('../stow/pkg4/bin4/file4')
            make_invalid_link('bin4/file4', '../../stow/pkg4/bin4/does-not-exist')

            stow.plan_unstow('pkg4')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert not os.path.exists('bin4/file4'), 'remove invalid link owned by stow'

        run_subtests(
            "existing link is owned by stow but is invalid so it gets removed anyway",
            test_func, stow_test_env)


class TestInvalidLinkNotOwnedByStow:
    """Test existing invalid link is not owned by stow."""

    def test_invalid_link_not_owned_by_stow(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('../stow/pkg5/bin5')
            make_invalid_link('bin5', '../not-stow')

            stow.plan_unstow('pkg5')
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.islink('bin5'), 'invalid link not removed'
            assert os.readlink('bin5') == '../not-stow', 'invalid link not changed'

        run_subtests("Existing invalid link is not owned by stow", test_func, stow_test_env)


class TestLinkPointsToDifferentPackage:
    """Test target already exists, is owned by stow, but points to a different package."""

    def test_link_points_to_different_package(self, stow_test_env):
        def test_func(stow, test_dir):
            make_path('bin6')
            make_path('../stow/pkg6a/bin6')
            make_file('../stow/pkg6a/bin6/file6')
            make_link('bin6/file6', '../../stow/pkg6a/bin6/file6')

            make_path('../stow/pkg6b/bin6')
            make_file('../stow/pkg6b/bin6/file6')

            stow.plan_unstow('pkg6b')
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.islink('bin6/file6')
            assert os.readlink('bin6/file6') == '../../stow/pkg6a/bin6/file6', \
                'ignore existing link that points to a different package'

        run_subtests(
            "Target already exists, is owned by stow, but points to a different package",
            test_func, stow_test_env)


class TestDontUnlinkUnderStowDir:
    """Test don't unlink anything under the stow directory."""

    def test_dont_unlink_under_stow_dir(self, stow_test_env):
        def setup_func(test_dir):
            make_path('stow')
            return {'dir': 'stow'}

        def test_func(stow, test_dir):
            # Emulate stowing into ourself (bizarre corner case or accident):
            make_path('stow/pkg7a/stow/pkg7b')
            make_file('stow/pkg7a/stow/pkg7b/file7b')
            # Make a package be a link to a package of the same name inside another package.
            make_link('stow/pkg7b', '../stow/pkg7a/stow/pkg7b')

            stow.plan_unstow('pkg7b')
            assert len(stow.get_tasks()) == 0, 'no tasks to process when unstowing pkg7b'
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.islink('stow/pkg7b')
            assert os.readlink('stow/pkg7b') == '../stow/pkg7a/stow/pkg7b', \
                "don't unlink any nodes under the stow directory"

        def check_stderr(stderr):
            # In compat mode, there should be a warning about skipping the stow directory
            assert re.search(
                r'WARNING.*skipping target which was current stow directory stow',
                stderr
            ), "Should warn when unstowing from current stow directory"

        run_subtests("Don't unlink anything under the stow directory", test_func, stow_test_env,
                     setup_func=setup_func, check_compat_stderr=check_stderr)


class TestDontUnlinkUnderAnotherStowDir:
    """Test don't unlink any nodes under another stow directory."""

    def test_dont_unlink_under_another_stow_dir(self, stow_test_env):
        def setup_func(test_dir):
            make_path('stow')
            return {'dir': 'stow'}

        def test_func(stow, test_dir):
            init_stow2()
            # emulate stowing into ourself (bizarre corner case or accident)
            make_path('stow/pkg8a/stow2/pkg8b')
            make_file('stow/pkg8a/stow2/pkg8b/file8b')
            make_link('stow2/pkg8b', '../stow/pkg8a/stow2/pkg8b')

            stow.plan_unstow('pkg8a')
            assert len(stow.get_tasks()) == 0, 'no tasks to process when unstowing pkg8a'
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.islink('stow2/pkg8b')
            assert os.readlink('stow2/pkg8b') == '../stow/pkg8a/stow2/pkg8b', \
                "don't unlink any nodes under another stow directory"

        def check_stderr(stderr):
            # In compat mode, should warn about skipping marked Stow directory stow2
            assert re.search(
                r'WARNING.*skipping marked Stow directory stow2',
                stderr
            ), "Should warn when skipping marked Stow directory stow2"

        run_subtests(
            "Don't unlink any nodes under another stow directory", test_func, stow_test_env,
            setup_func=setup_func, check_compat_stderr=check_stderr)


class TestOverridingAlreadyStowedDocumentation:
    """Test overriding already stowed documentation."""

    def test_overriding_already_stowed_documentation(self, stow_test_env):
        def test_func(stow, test_dir):
            make_file('stow/.stow')
            init_stow2()
            make_path('../stow/pkg9a/man9/man1')
            make_file('../stow/pkg9a/man9/man1/file9.1')
            make_path('man9/man1')
            make_link('man9/man1/file9.1', '../../../stow/pkg9a/man9/man1/file9.1')  # emulate stow

            make_path('../stow/pkg9b/man9/man1')
            make_file('../stow/pkg9b/man9/man1/file9.1')
            stow.plan_unstow('pkg9b')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert not os.path.islink('man9/man1/file9.1'), \
                'overriding existing documentation files'

        def check_stderr(stderr):
            # In compat mode, should warn about skipping protected directories
            check_protected_dirs_skipped(stderr)

        run_subtests("overriding already stowed documentation", test_func, stow_test_env,
                     setup_opts={'override': ['man9', 'info9']}, check_compat_stderr=check_stderr)


class TestDeferringToAlreadyStowedDocumentation:
    """Test deferring to already stowed documentation."""

    def test_deferring_to_already_stowed_documentation(self, stow_test_env):
        def test_func(stow, test_dir):
            init_stow2()
            make_path('../stow/pkg10a/man10/man1')
            make_file('../stow/pkg10a/man10/man1/file10a.1')
            make_path('man10/man1')
            make_link('man10/man1/file10a.1', '../../../stow/pkg10a/man10/man1/file10a.1')

            # need this to block folding
            make_path('../stow/pkg10b/man10/man1')
            make_file('../stow/pkg10b/man10/man1/file10b.1')
            make_link('man10/man1/file10b.1', '../../../stow/pkg10b/man10/man1/file10b.1')

            make_path('../stow/pkg10c/man10/man1')
            make_file('../stow/pkg10c/man10/man1/file10a.1')
            stow.plan_unstow('pkg10c')
            assert len(stow.get_tasks()) == 0, 'no tasks to process when unstowing pkg10c'
            assert stow.get_conflict_count() == 0, 'conflict count'
            link_target = '../../../stow/pkg10a/man10/man1/file10a.1'
            assert os.readlink('man10/man1/file10a.1') == link_target, \
                'defer to existing documentation files'

        def check_stderr(stderr):
            # In compat mode, should warn about skipping protected directories
            check_protected_dirs_skipped(stderr)

        run_subtests("deferring to already stowed documentation", test_func, stow_test_env,
                     setup_opts={'defer': ['man10', 'info10']}, check_compat_stderr=check_stderr)


class TestIgnoreTempFiles:
    """Test ignore temp files."""

    def test_ignore_temp_files(self, stow_test_env):
        def test_func(stow, test_dir):
            init_stow2()
            make_path('../stow/pkg12/man12/man1')
            make_file('../stow/pkg12/man12/man1/file12.1')
            make_file('../stow/pkg12/man12/man1/file12.1~')
            make_file('../stow/pkg12/man12/man1/.#file12.1')
            make_path('man12/man1')
            make_link('man12/man1/file12.1', '../../../stow/pkg12/man12/man1/file12.1')

            stow.plan_unstow('pkg12')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert not os.path.exists('man12/man1/file12.1'), 'man12/man1/file12.1 was unstowed'

        def check_stderr(stderr):
            # In compat mode, should warn about skipping protected directories
            check_protected_dirs_skipped(stderr)

        run_subtests("Ignore temp files", test_func, stow_test_env,
                     setup_opts={'ignore': ['~', r'\.#.*']}, check_compat_stderr=check_stderr)


class TestUnstowAlreadyUnstowed:
    """Test unstow an already unstowed package."""

    def test_unstow_already_unstowed(self, stow_test_env):
        def test_func(stow, test_dir):
            # Create protected stow directories (matching Perl's shared state from prior tests)
            init_stow2()
            make_file('stow/.stow')
            # Create pkg12 in stow directory (no symlinks in target)
            # This package exists but has nothing stowed
            make_path('../stow/pkg12/man12/man1')
            make_file('../stow/pkg12/man12/man1/file12.1')
            stow.plan_unstow('pkg12')
            assert len(stow.get_tasks()) == 0, 'no tasks to process when unstowing pkg12'
            assert stow.get_conflict_count() == 0, 'conflict count'

        def check_stderr(stderr):
            # In compat mode, should warn about skipping protected directories
            check_protected_dirs_skipped(stderr)

        run_subtests("Unstow an already unstowed package", test_func, stow_test_env,
                     check_compat_stderr=check_stderr)


class TestUnstowNeverStowed:
    """Test unstow a never stowed package."""

    def test_unstow_never_stowed(self, stow_test_env):
        def test_func(stow, test_dir):
            # Create pkg12 in stow directory first
            make_path('../stow/pkg12/man12/man1')
            make_file('../stow/pkg12/man12/man1/file12.1')

            # Remove and recreate target directory to test with empty target
            # We need to cd out before removing, then cd back after recreating
            target_path = os.path.abspath(stow.target) if stow.target != '.' else os.getcwd()
            parent_path = os.path.dirname(target_path)
            os.chdir(parent_path)
            try:
                remove_dir(target_path)
            except Exception:
                pass
            if not os.path.exists(target_path):
                os.mkdir(target_path)
            os.chdir(target_path)

            stow.plan_unstow('pkg12')
            assert len(stow.get_tasks()) == 0, \
                'no tasks to process when unstowing pkg12 which was never stowed'
            assert stow.get_conflict_count() == 0, 'conflict count'

        run_subtests("Unstow a never stowed package", test_func, stow_test_env)


class TestUnstowingWithRealFiles:
    """Test unstowing when target contains real files shouldn't be an issue."""

    def test_unstowing_with_real_files(self, stow_test_env):
        def test_func(stow, test_dir):
            # Create pkg12 in stow directory first
            make_path('../stow/pkg12/man12/man1')
            make_file('../stow/pkg12/man12/man1/file12.1')

            # Test both a file which do / don't overlap with the package
            make_path('man12/man1')
            make_file('man12/man1/alien')
            make_file('man12/man1/file12.1')

            stow.plan_unstow('pkg12')
            assert len(stow.get_tasks()) == 0, \
                'no tasks to process when unstowing pkg12 for third time'
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile('man12/man1/alien'), 'alien untouched'
            assert os.path.isfile('man12/man1/file12.1'), \
                'file overlapping with pkg untouched'

        run_subtests(
            "Unstowing when target contains real files shouldn't be an issue",
            test_func, stow_test_env)


class TestUnstowWhenCwdIsntTarget:
    """Test unstow a simple tree minimally when cwd isn't target."""

    def test_unstow_when_cwd_isnt_target(self, stow_test_env):
        def setup_func(test_dir):
            os.chdir(REPO)
            return {
                'dir': os.path.join(test_dir, 'stow'),
                'target': os.path.join(test_dir, 'target')
            }

        def test_func(stow, test_dir):
            make_path(os.path.join(test_dir, 'stow/pkg13/bin13'))
            make_file(os.path.join(test_dir, 'stow/pkg13/bin13/file13'))
            make_link(os.path.join(test_dir, 'target/bin13'), '../stow/pkg13/bin13')

            stow.plan_unstow('pkg13')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile(os.path.join(test_dir, 'stow/pkg13/bin13/file13')), \
                'package file untouched'
            assert not os.path.exists(os.path.join(test_dir, 'target/bin13')), 'bin13/ unstowed'

        run_subtests(
            "unstow a simple tree minimally when cwd isn't target",
            test_func, stow_test_env, setup_func=setup_func)


class TestUnstowWithAbsoluteStowDir:
    """Test unstow a simple tree minimally with absolute stow dir when cwd isn't target."""

    def test_unstow_with_absolute_stow_dir(self, stow_test_env):
        def setup_func(test_dir):
            os.chdir(REPO)
            return {
                'dir': canon_path(os.path.join(test_dir, 'stow')),
                'target': os.path.join(test_dir, 'target')
            }

        def test_func(stow, test_dir):
            make_path(os.path.join(test_dir, 'stow/pkg14/bin14'))
            make_file(os.path.join(test_dir, 'stow/pkg14/bin14/file14'))
            make_link(os.path.join(test_dir, 'target/bin14'), '../stow/pkg14/bin14')

            stow.plan_unstow('pkg14')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile(os.path.join(test_dir, 'stow/pkg14/bin14/file14'))
            assert not os.path.exists(os.path.join(test_dir, 'target/bin14')), \
                'unstow a simple tree with absolute stow dir'

        run_subtests("unstow a simple tree minimally with absolute stow dir when cwd isn't target",
                     test_func, stow_test_env, setup_func=setup_func)


class TestUnstowWithAbsoluteStowAndTargetDirs:
    """Test unstow a simple tree with absolute stow AND target dirs."""

    def test_unstow_with_absolute_stow_and_target_dirs(self, stow_test_env):
        def setup_func(test_dir):
            os.chdir(REPO)
            return {
                'dir': canon_path(os.path.join(test_dir, 'stow')),
                'target': canon_path(os.path.join(test_dir, 'target'))
            }

        def test_func(stow, test_dir):
            make_path(os.path.join(test_dir, 'stow/pkg15/bin15'))
            make_file(os.path.join(test_dir, 'stow/pkg15/bin15/file15'))
            make_link(os.path.join(test_dir, 'target/bin15'), '../stow/pkg15/bin15')

            stow.plan_unstow('pkg15')
            stow.process_tasks()
            assert stow.get_conflict_count() == 0, 'conflict count'
            assert os.path.isfile(os.path.join(test_dir, 'stow/pkg15/bin15/file15'))
            assert not os.path.exists(os.path.join(test_dir, 'target/bin15')), \
                'unstow a simple tree with absolute stow and target dirs'

        run_subtests(
            "unstow a simple tree minimally with absolute stow AND target dirs "
            "when cwd isn't target",
            test_func, stow_test_env, setup_func=setup_func)


def create_and_stow_pkg(id_, pkg):
    """Helper to create and stow a package for no-folding tests."""
    stow_pkg = '../stow/%s-%s' % (id_, pkg)
    make_path(stow_pkg)
    make_file('%s/%s-file-%s' % (stow_pkg, id_, pkg))

    # create a shallow hierarchy specific to this package and stow via folding
    make_path('%s/%s-%s-only-folded' % (stow_pkg, id_, pkg))
    make_file('%s/%s-%s-only-folded/file-%s' % (stow_pkg, id_, pkg, pkg))
    make_link('%s-%s-only-folded' % (id_, pkg), '%s/%s-%s-only-folded' % (stow_pkg, id_, pkg))

    # create a deeper hierarchy specific to this package and stow via folding
    make_path('%s/%s-%s-only-folded2/subdir' % (stow_pkg, id_, pkg))
    make_file('%s/%s-%s-only-folded2/subdir/file-%s' % (stow_pkg, id_, pkg, pkg))
    make_link('%s-%s-only-folded2' % (id_, pkg), '%s/%s-%s-only-folded2' % (stow_pkg, id_, pkg))

    # create a shallow hierarchy specific to this package and stow without folding
    make_path('%s/%s-%s-only-unfolded' % (stow_pkg, id_, pkg))
    make_file('%s/%s-%s-only-unfolded/file-%s' % (stow_pkg, id_, pkg, pkg))
    make_path('%s-%s-only-unfolded' % (id_, pkg))
    make_link('%s-%s-only-unfolded/file-%s' % (id_, pkg, pkg),
              '../%s/%s-%s-only-unfolded/file-%s' % (stow_pkg, id_, pkg, pkg))

    # create a deeper hierarchy specific to this package and stow without folding
    make_path('%s/%s-%s-only-unfolded2/subdir' % (stow_pkg, id_, pkg))
    make_file('%s/%s-%s-only-unfolded2/subdir/file-%s' % (stow_pkg, id_, pkg, pkg))
    make_path('%s-%s-only-unfolded2/subdir' % (id_, pkg))
    make_link('%s-%s-only-unfolded2/subdir/file-%s' % (id_, pkg, pkg),
              '../../%s/%s-%s-only-unfolded2/subdir/file-%s' % (stow_pkg, id_, pkg, pkg))

    # create a shallow shared hierarchy which this package uses, and stow its
    # contents without folding
    make_path('%s/%s-shared' % (stow_pkg, id_))
    make_file('%s/%s-shared/file-%s' % (stow_pkg, id_, pkg))
    make_path('%s-shared' % id_)
    make_link('%s-shared/file-%s' % (id_, pkg), '../%s/%s-shared/file-%s' % (stow_pkg, id_, pkg))

    # create a deeper shared hierarchy which this package uses, and stow its
    # contents without folding
    make_path('%s/%s-shared2/subdir' % (stow_pkg, id_))
    make_file('%s/%s-shared2/file-%s' % (stow_pkg, id_, pkg))
    make_file('%s/%s-shared2/subdir/file-%s' % (stow_pkg, id_, pkg))
    make_path('%s-shared2/subdir' % id_)
    make_link('%s-shared2/file-%s' % (id_, pkg), '../%s/%s-shared2/file-%s' % (stow_pkg, id_, pkg))
    make_link('%s-shared2/subdir/file-%s' % (id_, pkg),
              '../../%s/%s-shared2/subdir/file-%s' % (stow_pkg, id_, pkg))


class TestNoFolding:
    """Test unstow a tree with no-folding enabled - no refolding should take place."""

    def test_no_folding(self, stow_test_env):
        for pkg in ['a', 'b']:
            create_and_stow_pkg('no-folding', pkg)

        stow = new_Stow(**{'no-folding': True})
        stow.plan_unstow('no-folding-b')
        assert stow.get_conflict_count() == 0, 'no conflicts with --no-folding'

        stow.process_tasks()

        is_nonexistent_path('no-folding-b-only-folded')
        is_nonexistent_path('no-folding-b-only-folded2')
        is_nonexistent_path('no-folding-b-only-unfolded/file-b')
        is_nonexistent_path('no-folding-b-only-unfolded2/subdir/file-b')
        is_dir_not_symlink('no-folding-shared')
        is_dir_not_symlink('no-folding-shared2')
        is_dir_not_symlink('no-folding-shared2/subdir')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
