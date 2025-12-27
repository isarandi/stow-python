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
Test stowing packages - Python port of stow.t
"""

import os
import re

from testutil import (
    new_Stow, make_path, make_file, make_link,
    make_invalid_link, cd, cat_file, is_link, is_dir_not_symlink,
    canon_path,
)


class TestStow:
    """Test stowing packages."""

    def test_stow_simple_tree_minimally(self, stow_test_env):
        """Stow a simple tree minimally."""
        stow = new_Stow(dir='../stow')

        make_path('../stow/pkg1/bin1')
        make_file('../stow/pkg1/bin1/file1')

        stow.plan_stow('pkg1')
        stow.process_tasks()
        assert stow.get_conflicts() == {}, 'no conflicts with minimal stow'
        is_link('bin1', '../stow/pkg1/bin1')

    def test_stow_simple_tree_into_existing_directory(self, stow_test_env):
        """Stow a simple tree into an existing directory."""
        stow = new_Stow()

        make_path('../stow/pkg2/lib2')
        make_file('../stow/pkg2/lib2/file2')
        make_path('lib2')

        stow.plan_stow('pkg2')
        stow.process_tasks()
        is_link('lib2/file2', '../../stow/pkg2/lib2/file2')

    def test_unfold_existing_tree(self, stow_test_env):
        """Unfold existing tree."""
        stow = new_Stow()

        make_path('../stow/pkg3a/bin3')
        make_file('../stow/pkg3a/bin3/file3a')
        make_link('bin3', '../stow/pkg3a/bin3')  # emulate stow

        make_path('../stow/pkg3b/bin3')
        make_file('../stow/pkg3b/bin3/file3b')

        stow.plan_stow('pkg3b')
        stow.process_tasks()
        assert os.path.isdir('bin3')
        is_link('bin3/file3a', '../../stow/pkg3a/bin3/file3a')
        is_link('bin3/file3b', '../../stow/pkg3b/bin3/file3b')

    def test_package_dir_conflicts_with_existing_non_dir(self, stow_test_env):
        """Package dir 'bin4' conflicts with existing non-dir so can't unfold."""
        stow = new_Stow()

        make_file('bin4')  # this is a file but named like a directory
        make_path('../stow/pkg4/bin4')
        make_file('../stow/pkg4/bin4/file4')

        stow.plan_stow('pkg4')
        conflicts = stow.get_conflicts()
        assert stow.get_conflict_count() == 1
        assert re.search(
            r'cannot stow ../stow/pkg4/bin4 over existing target bin4 since neither '
            r'a link nor a directory and --adopt not specified',
            conflicts['stow']['pkg4'][0]
        ), 'link to new dir bin4 conflicts with existing non-directory'

    def test_package_dir_conflicts_with_existing_non_dir_even_with_adopt(
            self, stow_test_env):
        """Package dir 'bin4a' conflicts with non-dir so can't unfold even with --adopt."""
        stow = new_Stow(adopt=True)

        make_file('bin4a')  # this is a file but named like a directory
        make_path('../stow/pkg4a/bin4a')
        make_file('../stow/pkg4a/bin4a/file4a')

        stow.plan_stow('pkg4a')
        conflicts = stow.get_conflicts()
        assert stow.get_conflict_count() == 1
        assert re.search(
            r'cannot stow directory ../stow/pkg4a/bin4a over existing non-directory target bin4a',
            conflicts['stow']['pkg4a'][0]
        ), 'link to new dir bin4a conflicts with existing non-directory'

    def test_package_files_conflict_with_existing_files(self, stow_test_env):
        """Package files 'file4b' and 'bin4b' conflict with existing files."""
        stow = new_Stow()

        # Populate target
        make_file('file4b', 'file4b - version originally in target')
        make_path('bin4b')
        make_file('bin4b/file4b', 'bin4b/file4b - version originally in target')

        # Populate stow package
        make_path('../stow/pkg4b')
        make_file('../stow/pkg4b/file4b', 'file4b - version originally in stow package')
        make_path('../stow/pkg4b/bin4b')
        make_file('../stow/pkg4b/bin4b/file4b',
                  'bin4b/file4b - version originally in stow package')

        stow.plan_stow('pkg4b')
        conflicts = stow.get_conflicts()
        assert stow.get_conflict_count() == 2, 'conflict per file'
        for i, target in enumerate(['bin4b/file4b', 'file4b']):
            assert re.search(
                r'cannot stow ../stow/pkg4b/%s over existing target %s since neither '
                r'a link nor a directory and --adopt not specified' % (target, target),
                conflicts['stow']['pkg4b'][i]
            ), 'link to file4b conflicts with existing non-directory'

    def test_package_files_conflict_with_existing_directories(self, stow_test_env):
        """Package files 'file4d' conflicts with existing directories."""
        stow = new_Stow()

        # Populate target
        make_path('file4d')  # this is a directory but named like a file to create the conflict
        make_path('bin4d/file4d')  # same here

        # Populate stow package
        make_path('../stow/pkg4d')
        make_file('../stow/pkg4d/file4d', 'file4d - version originally in stow package')
        make_path('../stow/pkg4d/bin4d')
        make_file('../stow/pkg4d/bin4d/file4d',
                  'bin4d/file4d - version originally in stow package')

        stow.plan_stow('pkg4d')
        conflicts = stow.get_conflicts()
        assert stow.get_conflict_count() == 2, 'conflict per file'
        for i, target in enumerate(['bin4d/file4d', 'file4d']):
            assert re.search(
                r'cannot stow non-directory ../stow/pkg4d/%s over existing directory '
                r'target %s' % (target, target),
                conflicts['stow']['pkg4d'][i]
            ), 'link to file4d conflicts with existing non-directory'

    def test_package_files_can_adopt_existing_versions(self, stow_test_env):
        """Package files 'file4c' and 'bin4c' can adopt existing versions."""
        stow = new_Stow(adopt=True)

        # Populate target
        make_file('file4c', "file4c - version originally in target\n")
        make_path('bin4c')
        make_file('bin4c/file4c', "bin4c/file4c - version originally in target\n")

        # Populate stow package
        make_path('../stow/pkg4c')
        make_file('../stow/pkg4c/file4c', "file4c - version originally in stow package\n")
        make_path('../stow/pkg4c/bin4c')
        make_file('../stow/pkg4c/bin4c/file4c',
                  "bin4c/file4c - version originally in stow package\n")

        stow.plan_stow('pkg4c')
        assert stow.get_conflict_count() == 0, 'no conflicts with --adopt'
        assert len(stow.get_tasks()) == 4, 'two tasks per file'
        stow.process_tasks()
        for file in ['file4c', 'bin4c/file4c']:
            assert os.path.islink(file), "%s turned into a symlink" % file
            prefix = '' if '/' not in file else '../'
            expected_link = prefix + '../stow/pkg4c/' + file
            is_link(file, expected_link)
            assert cat_file(file) == "%s - version originally in target\n" % file, \
                "%s has right contents" % file

    def test_target_already_exists_but_not_owned_by_stow(self, stow_test_env):
        """Target already exists but is not owned by stow."""
        stow = new_Stow()

        make_path('bin5')
        make_invalid_link('bin5/file5', '../../empty')
        make_path('../stow/pkg5/bin5/file5')

        stow.plan_stow('pkg5')
        conflicts = stow.get_conflicts()
        assert re.search(r'not owned by stow', conflicts['stow']['pkg5'][-1]), \
            'target already exists but is not owned by stow'

    def test_replace_existing_but_invalid_target(self, stow_test_env):
        """Replace existing but invalid target."""
        stow = new_Stow()

        make_invalid_link('file6', '../stow/path-does-not-exist')
        make_path('../stow/pkg6')
        make_file('../stow/pkg6/file6')

        stow.plan_stow('pkg6')
        stow.process_tasks()
        is_link('file6', '../stow/pkg6/file6')

    def test_target_exists_owned_by_stow_but_points_to_non_directory(self, stow_test_env):
        """Target already exists, is owned by stow, but points to a non-directory."""
        stow = new_Stow()

        make_path('bin7')
        make_path('../stow/pkg7a/bin7')
        make_file('../stow/pkg7a/bin7/node7')
        make_link('bin7/node7', '../../stow/pkg7a/bin7/node7')
        make_path('../stow/pkg7b/bin7/node7')
        make_file('../stow/pkg7b/bin7/node7/file7')

        stow.plan_stow('pkg7b')
        conflicts = stow.get_conflicts()
        assert re.search(
            r'existing target is stowed to a different package',
            conflicts['stow']['pkg7b'][-1]
        ), 'link to new dir conflicts with existing stowed non-directory'

    def test_stowing_directories_named_0(self, stow_test_env):
        """Stowing directories named 0."""
        stow = new_Stow()

        make_path('../stow/pkg8a/0')
        make_file('../stow/pkg8a/0/file8a')
        make_link('0', '../stow/pkg8a/0')  # emulate stow

        make_path('../stow/pkg8b/0')
        make_file('../stow/pkg8b/0/file8b')

        stow.plan_stow('pkg8b')
        stow.process_tasks()
        assert stow.get_conflict_count() == 0
        assert os.path.isdir('0')
        is_link('0/file8a', '../../stow/pkg8a/0/file8a')
        is_link('0/file8b', '../../stow/pkg8b/0/file8b')

    def test_overriding_already_stowed_documentation(self, stow_test_env):
        """Overriding already stowed documentation."""
        stow = new_Stow(override=['man9', 'info9'])

        make_path('../stow/pkg9a/man9/man1')
        make_file('../stow/pkg9a/man9/man1/file9.1')
        make_path('man9/man1')
        make_link('man9/man1/file9.1', '../../../stow/pkg9a/man9/man1/file9.1')  # emulate stow

        make_path('../stow/pkg9b/man9/man1')
        make_file('../stow/pkg9b/man9/man1/file9.1')

        stow.plan_stow('pkg9b')
        stow.process_tasks()
        assert stow.get_conflict_count() == 0
        is_link('man9/man1/file9.1', '../../../stow/pkg9b/man9/man1/file9.1')

    def test_deferring_to_already_stowed_documentation(self, stow_test_env):
        """Deferring to already stowed documentation."""
        stow = new_Stow(defer=['man10', 'info10'])

        make_path('../stow/pkg10a/man10/man1')
        make_file('../stow/pkg10a/man10/man1/file10.1')
        make_path('man10/man1')
        # emulate stow
        make_link('man10/man1/file10.1', '../../../stow/pkg10a/man10/man1/file10.1')

        make_path('../stow/pkg10b/man10/man1')
        make_file('../stow/pkg10b/man10/man1/file10.1')

        stow.plan_stow('pkg10b')
        assert len(stow.get_tasks()) == 0, 'no tasks to process'
        assert stow.get_conflict_count() == 0
        is_link('man10/man1/file10.1', '../../../stow/pkg10a/man10/man1/file10.1')

    def test_ignore_temp_files(self, stow_test_env):
        """Ignore temp files."""
        stow = new_Stow(ignore=['~', r'\.#.*'])

        make_path('../stow/pkg11/man11/man1')
        make_file('../stow/pkg11/man11/man1/file11.1')
        make_file('../stow/pkg11/man11/man1/file11.1~')
        make_file('../stow/pkg11/man11/man1/.#file11.1')
        make_path('man11/man1')

        stow.plan_stow('pkg11')
        stow.process_tasks()
        assert stow.get_conflict_count() == 0
        is_link('man11/man1/file11.1', '../../../stow/pkg11/man11/man1/file11.1')
        assert not os.path.exists('man11/man1/file11.1~')
        assert not os.path.exists('man11/man1/.#file11.1')

    def test_stowing_links_library_files(self, stow_test_env):
        """Stowing links library files."""
        stow = new_Stow()

        make_path('../stow/pkg12/lib12/')
        make_file('../stow/pkg12/lib12/lib.so.1')
        make_link('../stow/pkg12/lib12/lib.so', 'lib.so.1')

        make_path('lib12/')

        stow.plan_stow('pkg12')
        stow.process_tasks()
        assert stow.get_conflict_count() == 0
        is_link('lib12/lib.so.1', '../../stow/pkg12/lib12/lib.so.1')
        is_link('lib12/lib.so', '../../stow/pkg12/lib12/lib.so')

    def test_unfolding_to_stow_links_to_library_files(self, stow_test_env):
        """Unfolding to stow links to library files."""
        stow = new_Stow()

        make_path('../stow/pkg13a/lib13/')
        make_file('../stow/pkg13a/lib13/liba.so.1')
        make_link('../stow/pkg13a/lib13/liba.so', 'liba.so.1')
        make_link('lib13', '../stow/pkg13a/lib13')

        make_path('../stow/pkg13b/lib13/')
        make_file('../stow/pkg13b/lib13/libb.so.1')
        make_link('../stow/pkg13b/lib13/libb.so', 'libb.so.1')

        stow.plan_stow('pkg13b')
        stow.process_tasks()
        assert stow.get_conflict_count() == 0
        is_link('lib13/liba.so.1', '../../stow/pkg13a/lib13/liba.so.1')
        is_link('lib13/liba.so', '../../stow/pkg13a/lib13/liba.so')
        is_link('lib13/libb.so.1', '../../stow/pkg13b/lib13/libb.so.1')
        is_link('lib13/libb.so', '../../stow/pkg13b/lib13/libb.so')

    def test_stowing_to_stow_dir_should_fail(self, stow_test_env, capsys):
        """Stowing to stow dir should fail."""
        make_path('stow')
        stow = new_Stow(dir='stow')

        make_path('stow/pkg14/stow/pkg15')
        make_file('stow/pkg14/stow/pkg15/node15')

        stow.plan_stow('pkg14')
        # Check for warning in stderr - must match the specific warning message
        captured = capsys.readouterr()
        assert re.search(
            r'WARNING.*skipping target which was current stow directory stow',
            captured.err
        ), "stowing to stow dir should give warning about skipping stow directory"

        assert len(stow.get_tasks()) == 0, 'no tasks to process'
        assert stow.get_conflict_count() == 0
        assert not os.path.islink('stow/pkg15'), "stowing to stow dir should fail"

    def test_stow_simple_tree_minimally_when_cwd_not_target(self, stow_test_env):
        """Stow a simple tree minimally when cwd isn't target."""
        test_dir = stow_test_env
        cd('../..')
        stow = new_Stow(dir=os.path.join(test_dir, 'stow'),
                        target=os.path.join(test_dir, 'target'))

        make_path(os.path.join(test_dir, 'stow/pkg16/bin16'))
        make_file(os.path.join(test_dir, 'stow/pkg16/bin16/file16'))

        stow.plan_stow('pkg16')
        stow.process_tasks()
        assert stow.get_conflicts() == {}, 'no conflicts with minimal stow'
        is_link(os.path.join(test_dir, 'target/bin16'), '../stow/pkg16/bin16')

    def test_stow_simple_tree_minimally_to_absolute_stow_dir(self, stow_test_env):
        """Stow a simple tree minimally to absolute stow dir when cwd isn't."""
        test_dir = stow_test_env
        stow = new_Stow(dir=canon_path(os.path.join(test_dir, 'stow')),
                        target=os.path.join(test_dir, 'target'))

        make_path(os.path.join(test_dir, 'stow/pkg17/bin17'))
        make_file(os.path.join(test_dir, 'stow/pkg17/bin17/file17'))

        stow.plan_stow('pkg17')
        stow.process_tasks()
        assert stow.get_conflicts() == {}, 'no conflicts with minimal stow'
        is_link(os.path.join(test_dir, 'target/bin17'), '../stow/pkg17/bin17')

    def test_stow_simple_tree_minimally_with_absolute_stow_and_target_dirs(self, stow_test_env):
        """Stow a simple tree minimally with absolute stow AND target dirs."""
        test_dir = stow_test_env
        stow = new_Stow(dir=canon_path(os.path.join(test_dir, 'stow')),
                        target=canon_path(os.path.join(test_dir, 'target')))

        make_path(os.path.join(test_dir, 'stow/pkg18/bin18'))
        make_file(os.path.join(test_dir, 'stow/pkg18/bin18/file18'))

        stow.plan_stow('pkg18')
        stow.process_tasks()
        assert stow.get_conflicts() == {}, 'no conflicts with minimal stow'
        is_link(os.path.join(test_dir, 'target/bin18'), '../stow/pkg18/bin18')

    def test_stow_tree_with_no_folding_enabled(self, stow_test_env):
        """Stow a tree with no-folding enabled."""
        test_dir = stow_test_env
        cd(os.path.join(test_dir, 'target'))

        def create_pkg(id_prefix, pkg):
            stow_pkg = "../stow/%s-%s" % (id_prefix, pkg)
            make_path(stow_pkg)
            make_file("%s/%s-file-%s" % (stow_pkg, id_prefix, pkg))

            # create a shallow hierarchy specific to this package which isn't
            # yet stowed
            make_path("%s/%s-%s-only-new" % (stow_pkg, id_prefix, pkg))
            make_file("%s/%s-%s-only-new/%s-file-%s" % (stow_pkg, id_prefix, pkg, id_prefix, pkg))

            # create a deeper hierarchy specific to this package which isn't
            # yet stowed
            make_path("%s/%s-%s-only-new2/subdir" % (stow_pkg, id_prefix, pkg))
            make_file("%s/%s-%s-only-new2/subdir/%s-file-%s" % (
                stow_pkg, id_prefix, pkg, id_prefix, pkg))
            make_link("%s/%s-%s-only-new2/current" % (stow_pkg, id_prefix, pkg), "subdir")

            # create a hierarchy specific to this package which is already
            # stowed via a folded tree
            make_path("%s/%s-%s-only-old" % (stow_pkg, id_prefix, pkg))
            make_link("%s-%s-only-old" % (id_prefix, pkg),
                      "%s/%s-%s-only-old" % (stow_pkg, id_prefix, pkg))
            make_file("%s/%s-%s-only-old/%s-file-%s" % (stow_pkg, id_prefix, pkg, id_prefix, pkg))

            # create a shared hierarchy which this package uses
            make_path("%s/%s-shared" % (stow_pkg, id_prefix))
            make_file("%s/%s-shared/%s-file-%s" % (stow_pkg, id_prefix, id_prefix, pkg))

            # create a partially shared hierarchy which this package uses
            make_path("%s/%s-shared2/subdir-%s" % (stow_pkg, id_prefix, pkg))
            make_file("%s/%s-shared2/%s-file-%s" % (stow_pkg, id_prefix, id_prefix, pkg))
            make_file("%s/%s-shared2/subdir-%s/%s-file-%s" % (
                stow_pkg, id_prefix, pkg, id_prefix, pkg))

        def check_no_folding(pkg):
            stow_pkg = "../stow/no-folding-%s" % pkg
            is_link("no-folding-file-%s" % pkg, "%s/no-folding-file-%s" % (stow_pkg, pkg))

            # check existing folded tree is untouched
            is_link("no-folding-%s-only-old" % pkg, "%s/no-folding-%s-only-old" % (stow_pkg, pkg))

            # check newly stowed shallow tree is not folded
            is_dir_not_symlink("no-folding-%s-only-new" % pkg)
            is_link("no-folding-%s-only-new/no-folding-file-%s" % (pkg, pkg),
                    "../%s/no-folding-%s-only-new/no-folding-file-%s" % (stow_pkg, pkg, pkg))

            # check newly stowed deeper tree is not folded
            is_dir_not_symlink("no-folding-%s-only-new2" % pkg)
            is_dir_not_symlink("no-folding-%s-only-new2/subdir" % pkg)
            is_link("no-folding-%s-only-new2/subdir/no-folding-file-%s" % (pkg, pkg),
                    "../../%s/no-folding-%s-only-new2/subdir/no-folding-file-%s" % (
                        stow_pkg, pkg, pkg))
            is_link("no-folding-%s-only-new2/current" % pkg,
                    "../%s/no-folding-%s-only-new2/current" % (stow_pkg, pkg))

            # check shared tree is not folded. first time round this will be
            # newly stowed.
            is_dir_not_symlink('no-folding-shared')
            is_link("no-folding-shared/no-folding-file-%s" % pkg,
                    "../%s/no-folding-shared/no-folding-file-%s" % (stow_pkg, pkg))

            # check partially shared tree is not folded. first time round this
            # will be newly stowed.
            is_dir_not_symlink('no-folding-shared2')
            is_link("no-folding-shared2/no-folding-file-%s" % pkg,
                    "../%s/no-folding-shared2/no-folding-file-%s" % (stow_pkg, pkg))

        for pkg in ['a', 'b']:
            create_pkg('no-folding', pkg)

        stow = new_Stow(**{'no-folding': True})
        stow.plan_stow('no-folding-a')
        assert stow.get_conflicts() == {}, 'no conflicts with --no-folding'
        tasks = stow.get_tasks()
        assert len(tasks) == 13, "6 dirs, 7 links"
        stow.process_tasks()

        check_no_folding('a')

        stow = new_Stow(**{'no-folding': True})
        stow.plan_stow('no-folding-b')
        assert stow.get_conflicts() == {}, 'no conflicts with --no-folding'
        tasks = stow.get_tasks()
        assert len(tasks) == 11, '4 dirs, 7 links'
        stow.process_tasks()

        check_no_folding('a')
        check_no_folding('b')
