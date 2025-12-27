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
Utilities shared by test scripts - Python port of testutil.pm
"""

from __future__ import print_function

import os
import shutil
import sys

# Import from the single-file stow script in bin/
# Use types.ModuleType for Python 2.7 compatibility (no importlib.util)
import types
_stow_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'stow')
stow_module = types.ModuleType('stow_module')
stow_module.__file__ = _stow_path
with open(_stow_path) as _f:
    exec(compile(_f.read(), _stow_path, 'exec'), stow_module.__dict__)
sys.modules['stow_module'] = stow_module

Stow = stow_module.Stow
parent = stow_module.parent
canon_path = stow_module.canon_path
join_paths = stow_module.join_paths

TEST_DIR = 'tmp-testing-trees'
ABS_TEST_DIR = os.path.abspath(TEST_DIR)
_original_cwd = None


def init_test_dirs(test_dir=None):
    """
    Initialize test directories.
    Returns the absolute path to the test directory.

    If test_dir is provided (e.g., from pytest's tmp_path), use that.
    Otherwise use the default TEST_DIR.
    """
    global TEST_DIR, ABS_TEST_DIR, _original_cwd

    # Save original cwd for restoration
    _original_cwd = os.getcwd()

    if test_dir is None:
        test_dir = TEST_DIR
        abs_test_dir = os.path.abspath(test_dir)
    else:
        # Handle pathlib.Path from pytest's tmp_path
        abs_test_dir = (str(test_dir) if hasattr(test_dir, '__fspath__')
                        else os.path.abspath(test_dir))
        test_dir = abs_test_dir

    ABS_TEST_DIR = abs_test_dir
    TEST_DIR = test_dir

    # Create subdirectories for tests
    for subdir in ("target", "stow", "run_from", "stow directory"):
        path = os.path.join(abs_test_dir, subdir)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path)

    # Don't let user's ~/.stow-global-ignore affect test results
    os.environ['HOME'] = abs_test_dir

    return abs_test_dir


def cleanup_test_dirs():
    """Restore original working directory after test."""
    global _original_cwd
    if _original_cwd is not None:
        try:
            os.chdir(_original_cwd)
        except OSError:
            pass
        _original_cwd = None


def new_Stow(**opts):
    """
    Create a new Stow instance with test defaults.
    These default paths assume that execution will be triggered from
    within the target directory.
    """
    if 'dir' not in opts:
        opts['dir'] = '../stow'
    if 'target' not in opts:
        opts['target'] = '.'
    opts['test_mode'] = 1

    try:
        stow = Stow(**opts)
    except Exception as e:
        raise RuntimeError("Error while trying to instantiate new Stow(%s): %s" % (opts, e))

    return stow


def new_compat_Stow(**opts):
    """Create a new Stow instance with compat mode enabled."""
    opts['compat'] = 1
    return new_Stow(**opts)


def make_path(path):
    """Create directory and all parent directories."""
    if not os.path.exists(path):
        os.makedirs(path)


def make_link(link_src, link_dest, invalid=False):
    """
    Safely create a link.

    Parameters:
        link_src: path to the link
        link_dest: where the new link should point
        invalid: True iff link_dest refers to non-existent file
    """
    if os.path.islink(link_src):
        old_source = os.readlink(link_src)
        if old_source != link_dest:
            raise RuntimeError("%s already exists but points elsewhere" % link_src)
        return  # Link already exists and points to correct destination

    if os.path.exists(link_src):
        raise RuntimeError("%s already exists and is not a link" % link_src)

    abs_target = os.path.abspath(link_src)
    link_src_container = os.path.dirname(abs_target)
    abs_source = os.path.normpath(os.path.join(link_src_container, link_dest))

    if os.path.exists(abs_source):
        if invalid:
            raise RuntimeError("Won't make invalid link pointing to existing %s" % abs_target)
    else:
        if not invalid:
            raise RuntimeError("Won't make link pointing to non-existent %s" % abs_source)

    os.symlink(link_dest, link_src)


def make_invalid_link(target, source):
    """Safely create an invalid link (pointing to non-existent target)."""
    make_link(target, source, invalid=True)


def make_file(path, contents=None):
    """
    Create a file, optionally with contents.

    Parameters:
        path: path to the file
        contents: optional contents to write
    """
    if os.path.exists(path) and not os.path.isfile(path):
        raise RuntimeError("a non-file already exists at %s" % path)

    # Create parent directories if needed
    parent_dir = os.path.dirname(path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    with open(path, 'w') as f:
        if contents is not None:
            f.write(contents)


def setup_global_ignore(contents):
    """Set up global ignore file with given contents."""
    global_ignore_file = join_paths(os.environ['HOME'], stow_module.GLOBAL_IGNORE_FILE)
    make_file(global_ignore_file, contents)
    return global_ignore_file


def setup_package_ignore(package_path, contents):
    """Set up package-local ignore file with given contents."""
    package_ignore_file = join_paths(package_path, stow_module.LOCAL_IGNORE_FILE)
    make_file(package_ignore_file, contents)
    return package_ignore_file


def remove_link(path):
    """Remove an existing symbolic link."""
    if not os.path.islink(path):
        raise RuntimeError("remove_link() called with a non-link: %s" % path)
    os.unlink(path)


def remove_file(path):
    """Remove an existing empty file."""
    if os.path.getsize(path) > 0:
        raise RuntimeError("file at %s is non-empty" % path)
    os.unlink(path)


def remove_dir(dir_path):
    """
    Safely remove a tree of test files.
    Recursively removes directories containing softlinks and empty files.
    """
    if not os.path.isdir(dir_path):
        raise RuntimeError("%s is not a directory" % dir_path)

    for node in os.listdir(dir_path):
        if node in ('.', '..'):
            continue

        path = os.path.join(dir_path, node)

        if os.path.islink(path):
            os.unlink(path)
        elif (os.path.isfile(path)
              and (os.path.getsize(path) == 0 or node == stow_module.LOCAL_IGNORE_FILE)):
            os.unlink(path)
        elif os.path.isdir(path):
            remove_dir(path)
        else:
            raise RuntimeError("%s is not a link, directory, or empty file" % path)

    os.rmdir(dir_path)


def cd(dir_path):
    """Wrapper around chdir."""
    try:
        os.chdir(dir_path)
    except OSError as e:
        raise RuntimeError("Failed to chdir(%s): %s" % (dir_path, e))


def cat_file(file_path):
    """Return file contents."""
    with open(file_path, 'r') as f:
        return f.read()


# Assertion helpers for pytest
def is_link(path, dest):
    """Assert path is a symlink pointing to dest."""
    assert os.path.islink(path), "%s should be symlink" % path
    assert os.readlink(path) == dest, "%s symlinks to %s" % (path, dest)


def is_dir_not_symlink(path):
    """Assert path is a directory not a symlink."""
    assert not os.path.islink(path), "%s should not be symlink" % path
    assert os.path.isdir(path), "%s should be a directory" % path


def is_nonexistent_path(path):
    """Assert path does not exist."""
    assert not os.path.islink(path), "%s should not be symlink" % path
    assert not os.path.exists(path), "%s should not exist" % path
