"""
Oracle-based tests comparing Python stow vs Perl stow.

Each test creates a scenario, runs both implementations, and verifies
they produce identical results (return code, stdout, stderr, filesystem).
"""

from __future__ import print_function

import os

from conftest import assert_stow_match


class TestBasicStow:
    """Basic stow operations."""

    def test_stow_simple_package(self, stow_env):
        """Stow a simple package with a few files."""
        stow_env.create_package('mypkg', {
            'bin/hello': '#!/bin/bash\necho hello\n',
            'lib/mylib.so': 'library content',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_stow_empty_package(self, stow_env):
        """Stow an empty package."""
        stow_env.create_package('empty', {})

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'empty'])

    def test_stow_single_file(self, stow_env):
        """Stow a package with just one file."""
        stow_env.create_package('single', {
            'bin/program': 'content',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'single'])

    def test_stow_deep_hierarchy(self, stow_env):
        """Stow a package with deep directory hierarchy."""
        stow_env.create_package('deep', {
            'share/doc/deep/examples/config/settings.txt': 'settings',
            'share/doc/deep/README': 'readme',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'deep'])

    def test_stow_multiple_packages(self, stow_env):
        """Stow multiple packages at once."""
        stow_env.create_package('pkg1', {
            'bin/prog1': 'prog1',
        })
        stow_env.create_package('pkg2', {
            'bin/prog2': 'prog2',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'pkg1', 'pkg2'])


class TestUnstow:
    """Unstow operations."""

    def test_unstow_simple(self, stow_env):
        """Unstow a previously stowed package."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
            'lib/mylib.so': 'lib',
        })

        # First stow it
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'mypkg'])

        # Then test unstow
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-D', 'mypkg'])

    def test_unstow_not_stowed(self, stow_env):
        """Unstow a package that was never stowed."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-D', 'mypkg'])


class TestRestow:
    """Restow operations."""

    def test_restow_simple(self, stow_env):
        """Restow a package (unstow then stow)."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        # First stow it
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'mypkg'])

        # Then restow
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-R', 'mypkg'])


class TestConflicts:
    """Conflict detection and handling."""

    def test_conflict_existing_file(self, stow_env):
        """Conflict when target file already exists."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'from package',
        })
        stow_env.create_target_file('bin/hello', 'existing file')

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_conflict_existing_dir_vs_file(self, stow_env):
        """Conflict when package has file but target has directory."""
        stow_env.create_package('mypkg', {
            'bin': 'this is a file not a dir',  # File named 'bin'
        })
        stow_env.create_target_dir('bin')
        stow_env.create_target_file('bin/existing', 'existing')

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_conflict_two_packages_same_file(self, stow_env):
        """Conflict when two packages have the same file."""
        stow_env.create_package('pkg1', {
            'bin/hello': 'from pkg1',
        })
        stow_env.create_package('pkg2', {
            'bin/hello': 'from pkg2',
        })

        # Stow first package
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'pkg1'])

        # Try to stow second - should conflict
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'pkg2'])


class TestAdopt:
    """Adopt option tests."""

    def test_adopt_existing_file(self, stow_env):
        """Adopt an existing file into the package."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'from package',
        })
        stow_env.create_target_file('bin/hello', 'existing content')

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '--adopt', 'mypkg'])


class TestDotfiles:
    """Dotfiles support tests."""

    def test_dotfiles_basic(self, stow_env):
        """Stow with --dotfiles converts dot-X to .X."""
        stow_env.create_package('dotpkg', {
            'dot-bashrc': 'bashrc content',
            'dot-config/app/settings': 'settings',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '--dotfiles', 'dotpkg'])

    def test_dotfiles_without_flag(self, stow_env):
        """Without --dotfiles, dot-X stays as dot-X."""
        stow_env.create_package('dotpkg', {
            'dot-bashrc': 'bashrc content',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'dotpkg'])

    def test_dotfiles_unstow(self, stow_env):
        """Unstow with --dotfiles."""
        stow_env.create_package('dotpkg', {
            'dot-bashrc': 'bashrc content',
        })

        # First stow with dotfiles
        stow_env.run_perl_stow(['-t', stow_env.target_dir, '--dotfiles', 'dotpkg'])

        # Then unstow
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '--dotfiles', '-D', 'dotpkg'])


class TestIgnore:
    """Ignore patterns."""

    def test_ignore_pattern(self, stow_env):
        """Files matching ignore pattern should be skipped."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
            'bin/hello.bak': 'backup',
            'README.md': 'readme',
        })

        assert_stow_match(stow_env, [
            '-t', stow_env.target_dir,
            '--ignore=\\.bak$',
            '--ignore=README',
            'mypkg'
        ])

    def test_ignore_git(self, stow_env):
        """Default ignore patterns should skip .git."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
            '.git/config': 'git config',
            '.gitignore': 'ignore patterns',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])


class TestDeferOverride:
    """Defer and override patterns."""

    def test_defer_pattern(self, stow_env):
        """Defer should skip stowing if already stowed elsewhere."""
        stow_env.create_package('pkg1', {
            'bin/hello': 'from pkg1',
        })
        stow_env.create_package('pkg2', {
            'bin/hello': 'from pkg2',
        })

        # Stow first package
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'pkg1'])

        # Stow second with defer - should not conflict
        assert_stow_match(stow_env, [
            '-t', stow_env.target_dir,
            '--defer=bin',
            'pkg2'
        ])

    def test_override_pattern(self, stow_env):
        """Override should replace existing stowed link."""
        stow_env.create_package('pkg1', {
            'bin/hello': 'from pkg1',
        })
        stow_env.create_package('pkg2', {
            'bin/hello': 'from pkg2',
        })

        # Stow first package
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'pkg1'])

        # Stow second with override
        assert_stow_match(stow_env, [
            '-t', stow_env.target_dir,
            '--override=bin',
            'pkg2'
        ])


class TestSimulate:
    """Simulate (dry-run) mode."""

    def test_simulate_no_changes(self, stow_env):
        """Simulate mode should not modify filesystem."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-n', 'mypkg'])


class TestVerbose:
    """Verbose output."""

    def test_verbose_level_1(self, stow_env):
        """Verbose level 1 output."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-v', 'mypkg'])

    def test_verbose_level_2(self, stow_env):
        """Verbose level 2 output."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-v', '-v', 'mypkg'])

    def test_verbose_explicit(self, stow_env):
        """Explicit verbose level."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '--verbose=3', 'mypkg'])


class TestTreeFolding:
    """Tree folding and unfolding."""

    def test_tree_folding(self, stow_env):
        """Directory should be replaced with symlink when possible."""
        stow_env.create_package('mypkg', {
            'share/mypkg/file1': 'file1',
            'share/mypkg/file2': 'file2',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_tree_unfolding(self, stow_env):
        """Symlink should be replaced with directory when needed."""
        stow_env.create_package('pkg1', {
            'share/common/file1': 'from pkg1',
        })
        stow_env.create_package('pkg2', {
            'share/common/file2': 'from pkg2',
        })

        # Stow first - should create symlink to share
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'pkg1'])

        # Stow second - should unfold and create individual links
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'pkg2'])

    def test_no_folding(self, stow_env):
        """--no-folding should create individual links."""
        stow_env.create_package('mypkg', {
            'share/mypkg/file1': 'file1',
            'share/mypkg/file2': 'file2',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '--no-folding', 'mypkg'])


class TestEnvironment:
    """Environment variable handling."""

    def test_stow_dir_env(self, stow_env):
        """STOW_DIR environment variable."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        # Run from target dir, using STOW_DIR env var
        assert_stow_match(
            stow_env,
            ['-t', stow_env.target_dir, 'mypkg'],
            env={'STOW_DIR': stow_env.stow_dir}
        )


class TestEdgeCases:
    """Edge cases and special scenarios."""

    def test_symlink_in_package(self, stow_env):
        """Package containing a relative symlink."""
        pkg_dir = os.path.join(stow_env.stow_dir, 'linkpkg')
        os.makedirs(os.path.join(pkg_dir, 'bin'))

        # Create a real file and a symlink to it
        with open(os.path.join(pkg_dir, 'bin', 'real'), 'w') as f:
            f.write('real file')
        os.symlink('real', os.path.join(pkg_dir, 'bin', 'alias'))

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'linkpkg'])

    def test_absolute_symlink_in_package(self, stow_env):
        """Package containing an absolute symlink should conflict."""
        pkg_dir = os.path.join(stow_env.stow_dir, 'abspkg')
        os.makedirs(os.path.join(pkg_dir, 'bin'))

        # Create an absolute symlink
        os.symlink('/usr/bin/true', os.path.join(pkg_dir, 'bin', 'absolute'))

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'abspkg'])

    def test_stow_dir_marker(self, stow_env):
        """Stow should skip directories with .stow marker."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        # Create .stow marker in a target subdirectory
        stow_env.create_target_dir('otherstow')
        stow_env.create_target_file('otherstow/.stow', '')

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_nonstow_marker(self, stow_env):
        """Stow should skip directories with .nonstow marker."""
        stow_env.create_package('mypkg', {
            'protected/file': 'should not stow',
            'bin/hello': 'hello',
        })

        # Create .nonstow marker
        stow_env.create_target_dir('protected')
        stow_env.create_target_file('protected/.nonstow', '')

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg'])

    def test_package_with_trailing_slash(self, stow_env):
        """Package name with trailing slash."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'mypkg/'])

    def test_nonexistent_package(self, stow_env):
        """Trying to stow nonexistent package."""
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, 'nonexistent'])


class TestHelpVersion:
    """Help and version output."""

    def test_help(self, stow_env):
        """--help output."""
        assert_stow_match(stow_env, ['--help'])

    def test_version(self, stow_env):
        """--version output."""
        assert_stow_match(stow_env, ['--version'])

    def test_no_packages(self, stow_env):
        """Error when no packages specified."""
        assert_stow_match(stow_env, ['-t', stow_env.target_dir])


class TestCompat:
    """Compat mode tests."""

    def test_compat_unstow(self, stow_env):
        """Unstow with --compat flag."""
        stow_env.create_package('mypkg', {
            'bin/hello': 'hello',
        })

        # First stow
        stow_env.run_perl_stow(['-t', stow_env.target_dir, 'mypkg'])

        # Unstow with compat
        assert_stow_match(stow_env, ['-t', stow_env.target_dir, '-p', '-D', 'mypkg'])
