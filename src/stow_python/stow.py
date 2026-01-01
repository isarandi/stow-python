# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Stow class - manage farms of symbolic links.

This module contains the core Stow class that handles planning and
executing stow/unstow operations.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Optional

from stow_python.types import Task, TaskAction, TaskType
from stow_python.util import (
    error,
    internal_error,
    debug,
    set_debug_level,
    set_test_mode,
    join_paths,
    parent,
    canon_path,
    restore_cwd,
    adjust_dotfile,
    unadjust_dotfile,
    is_a_directory,
)

LOCAL_IGNORE_FILE = ".stow-local-ignore"
GLOBAL_IGNORE_FILE = ".stow-global-ignore"

# These are the default options for each Stow instance.
DEFAULT_OPTIONS = {
    "conflicts": 0,
    "simulate": 0,
    "verbose": 0,
    "paranoid": 0,
    "compat": 0,
    "test_mode": 0,
    "dotfiles": 0,
    "adopt": 0,
    "no-folding": 0,
    "ignore": [],
    "override": [],
    "defer": [],
}

# Memoization cache for ignore file regexps
_ignore_file_regexps: dict = {}


class Stow:
    """
    Stow class - manage farms of symbolic links.

    Required options:
        dir - the stow directory
        target - the target directory

    N.B. This sets the current working directory to the target directory.
    """

    def __init__(self, **opts):
        self.action_count = 0

        # Check required arguments
        for required_arg in ("dir", "target"):
            if required_arg not in opts:
                raise ValueError(
                    f"Stow.__init__() called without '{required_arg}' parameter"
                )
            setattr(self, required_arg, opts.pop(required_arg))

        # Set options with defaults
        # Note: 'ignore', 'defer', 'override' are stored with underscore prefix
        # to avoid conflict with methods of the same name
        for opt, default in DEFAULT_OPTIONS.items():
            if opt in ("ignore", "defer", "override"):
                attr_name = "_" + opt
            else:
                attr_name = opt.replace("-", "_")

            if opt in opts:
                setattr(self, attr_name, opts.pop(opt))
            else:
                # Deep copy lists to avoid sharing between instances
                if isinstance(default, list):
                    setattr(self, attr_name, list(default))
                else:
                    setattr(self, attr_name, default)

        if opts:
            raise ValueError(
                f"Stow.__init__() called with unrecognised parameter(s): {', '.join(opts.keys())}"
            )

        # Compile defer/override/ignore patterns into regex objects
        self._defer = [re.compile(p) for p in self._defer]
        self._override = [re.compile(p) for p in self._override]
        self._ignore = [re.compile(p) for p in self._ignore]

        set_debug_level(self.get_verbosity())
        set_test_mode(self.test_mode)
        self.set_stow_dir()
        self.init_state()

    def get_verbosity(self) -> int:
        if not self.test_mode:
            return self.verbose

        test_verbose = os.environ.get("TEST_VERBOSE", "")
        if not test_verbose:
            return 0

        try:
            return int(test_verbose)
        except ValueError:
            return 3

    def set_stow_dir(self, dir_path: Optional[str] = None) -> None:
        """
        Set a new stow directory.

        If dir_path is omitted, uses the value of the 'dir' parameter
        passed to the constructor.
        """
        if dir_path is not None:
            self.dir = dir_path

        stow_dir = canon_path(self.dir)
        target = canon_path(self.target)

        self.stow_path = os.path.relpath(stow_dir, target)

        debug(2, 0, f"stow dir is {stow_dir}")
        debug(2, 0, f"stow dir path relative to target {target} is {self.stow_path}")

    def init_state(self) -> None:
        """Initialize internal state structures."""
        self.conflicts: dict = {}
        self.conflict_count = 0

        self.pkgs_to_stow: list[str] = []
        self.pkgs_to_delete: list[str] = []

        # Task queue: list of Task objects
        self.tasks: list[Task] = []

        # Maps from path to task for quick lookup
        self.dir_task_for: dict[str, Task] = {}
        self.link_task_for: dict[str, Task] = {}

    def plan_unstow(self, *packages: str) -> None:
        """Plan which symlink/directory creation/removal tasks need to be executed
        in order to unstow the given packages. Any potential conflicts are then
        accessible via get_conflicts()."""
        if not packages:
            return

        debug(2, 0, f"Planning unstow of: {' '.join(packages)} ...")

        def do_unstow():
            for package in packages:
                pkg_path = join_paths(self.stow_path, package)
                if not is_a_directory(pkg_path):
                    error(
                        f"The stow directory {self.stow_path} does not contain package {package}"
                    )
                debug(2, 0, f"Planning unstow of package {package}...")
                self.unstow_contents(package, ".", ".")
                debug(2, 0, f"Planning unstow of package {package}... done")
                self.action_count += 1

        self.within_target_do(do_unstow)

    def plan_stow(self, *packages: str) -> None:
        """Plan which symlink/directory creation/removal tasks need to be executed
        in order to stow the given packages. Any potential conflicts are then
        accessible via get_conflicts()."""
        if not packages:
            return

        debug(2, 0, f"Planning stow of: {' '.join(packages)} ...")

        def do_stow():
            for package in packages:
                pkg_path = join_paths(self.stow_path, package)
                if not is_a_directory(pkg_path):
                    error(
                        f"The stow directory {self.stow_path} does not contain package {package}"
                    )
                debug(2, 0, f"Planning stow of package {package}...")
                self.stow_contents(self.stow_path, package, ".", ".")
                debug(2, 0, f"Planning stow of package {package}... done")
                self.action_count += 1

        self.within_target_do(do_stow)

    def within_target_do(self, code) -> None:
        """Execute code within target directory, preserving cwd.

        This is done to ensure that the consumer of the Stow interface doesn't
        have to worry about (a) what their cwd is, and (b) that their cwd
        might change."""
        cwd = os.getcwd()
        try:
            os.chdir(self.target)
        except OSError as e:
            error(f"Cannot chdir to target tree: {self.target} ({e})")

        debug(3, 0, f"cwd now {self.target}")
        code()
        restore_cwd(cwd)
        debug(3, 0, f"cwd restored to {cwd}")

    def stow_contents(
        self, stow_path: str, package: str, pkg_subdir: str, target_subdir: str
    ) -> None:
        """Stow the contents of the given directory.

        Args:
            stow_path: Relative path from current (i.e. target) directory to
                       the stow dir containing the package to be stowed.
            package: The package whose contents are being stowed.
            pkg_subdir: Subdirectory of the installation image in the package
                        directory which needs stowing as a symlink.
            target_subdir: Subdirectory of the target directory.

        Note: stow_node() and stow_contents() are mutually recursive."""
        if self.should_skip_target(pkg_subdir):
            return

        cwd = os.getcwd()
        msg = f"Stowing contents of {stow_path} / {package} / {pkg_subdir} (cwd={cwd})"

        # Replace $HOME with ~ for readability
        home = os.environ.get("HOME", "")
        if home:
            msg = msg.replace(home + "/", "~/")
            msg = msg.replace(home, "~")

        debug(3, 0, msg)
        debug(4, 1, f"target subdir is {target_subdir}")

        pkg_path_from_cwd = join_paths(stow_path, package, pkg_subdir)

        if not self.is_a_node(target_subdir):
            error(f"stow_contents() called with non-directory target: {target_subdir}")

        try:
            listing = os.listdir(pkg_path_from_cwd)
        except OSError as e:
            error(f"cannot read directory: {pkg_path_from_cwd} ({e})")

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            package_node_path = join_paths(pkg_subdir, node)
            target_node = node
            target_node_path = join_paths(target_subdir, target_node)

            if self.ignore(stow_path, package, target_node_path):
                continue

            if self.dotfiles:
                adjusted = adjust_dotfile(node)
                if adjusted != node:
                    debug(4, 1, f"Adjusting: {node} => {adjusted}")
                    target_node = adjusted
                    target_node_path = join_paths(target_subdir, target_node)

            self.stow_node(stow_path, package, package_node_path, target_node_path)

    def stow_node(
        self, stow_path: str, package: str, pkg_subpath: str, target_subpath: str
    ) -> None:
        """Stow the given node.

        Note: stow_node() and stow_contents() are mutually recursive."""
        debug(3, 0, f"Stowing entry {stow_path} / {package} / {pkg_subpath}")

        # Calculate the path to the package directory or sub-directory
        # whose contents need to be stowed, relative to the current
        # (target directory).
        pkg_path_from_cwd = join_paths(stow_path, package, pkg_subpath)

        # Don't try to stow absolute symlinks (they can't be unstowed)
        if os.path.islink(pkg_path_from_cwd):
            link_dest = self.read_a_link(pkg_path_from_cwd)
            if link_dest.startswith("/"):
                self.conflict(
                    "stow",
                    package,
                    f"source is an absolute symlink {pkg_path_from_cwd} => {link_dest}",
                )
                debug(3, 0, "Absolute symlinks cannot be unstowed")
                return

        # How many directories deep are we?
        level = pkg_subpath.count("/")
        debug(2, 1, f"level of {pkg_subpath} is {level}")

        # Calculate the destination of the symlink which would need to be
        # installed within this directory in the absence of folding.
        link_dest = join_paths("../" * level, pkg_path_from_cwd)
        debug(4, 1, f"link destination {link_dest}")

        # Does the target already exist?
        if self.is_a_link(target_subpath):
            existing_link_dest = self.read_a_link(target_subpath)
            if not existing_link_dest:
                error(f"Could not read link: {target_subpath}")

            debug(
                4,
                1,
                f"Evaluate existing link: {target_subpath} => {existing_link_dest}",
            )

            # Does it point to a node under any stow directory?
            existing_pkg_path_from_cwd, existing_stow_path, existing_package = (
                self.find_stowed_path(target_subpath, existing_link_dest)
            )

            if not existing_pkg_path_from_cwd:
                self.conflict(
                    "stow",
                    package,
                    f"existing target is not owned by stow: {target_subpath}",
                )
                return

            # Does the existing target_subpath actually point to anything?
            if self.is_a_node(existing_pkg_path_from_cwd):
                if existing_link_dest == link_dest:
                    debug(
                        2,
                        0,
                        f"--- Skipping {target_subpath} as it already points to {link_dest}",
                    )
                elif self.defer(target_subpath):
                    debug(2, 0, f"--- Deferring installation of: {target_subpath}")
                elif self.override(target_subpath):
                    debug(2, 0, f"--- Overriding installation of: {target_subpath}")
                    self.do_unlink(target_subpath)
                    self.do_link(link_dest, target_subpath)
                elif self.is_a_dir(
                    join_paths(parent(target_subpath), existing_link_dest)
                ) and self.is_a_dir(join_paths(parent(target_subpath), link_dest)):
                    # If the existing link points to a directory,
                    # and the proposed new link points to a directory,
                    # then we can unfold (split open) the tree at that point
                    debug(
                        2,
                        0,
                        f"--- Unfolding {target_subpath} which was already owned by {existing_package}",
                    )
                    self.do_unlink(target_subpath)
                    self.do_mkdir(target_subpath)
                    self.stow_contents(
                        existing_stow_path,
                        existing_package,
                        pkg_subpath,
                        target_subpath,
                    )
                    self.stow_contents(
                        self.stow_path, package, pkg_subpath, target_subpath
                    )
                else:
                    self.conflict(
                        "stow",
                        package,
                        f"existing target is stowed to a different package: {target_subpath} => {existing_link_dest}",
                    )
            else:
                # The existing link is invalid, so replace it with a good link
                debug(2, 0, f"--- replacing invalid link: {target_subpath}")
                self.do_unlink(target_subpath)
                self.do_link(link_dest, target_subpath)

        elif self.is_a_node(target_subpath):
            debug(4, 1, f"Evaluate existing node: {target_subpath}")
            if self.is_a_dir(target_subpath):
                if not os.path.isdir(pkg_path_from_cwd):
                    self.conflict(
                        "stow",
                        package,
                        f"cannot stow non-directory {pkg_path_from_cwd} over existing directory target {target_subpath}",
                    )
                else:
                    self.stow_contents(
                        self.stow_path, package, pkg_subpath, target_subpath
                    )
            else:
                # If we're here, target_subpath is not a current or
                # planned directory.
                if self.adopt:
                    if os.path.isdir(pkg_path_from_cwd):
                        self.conflict(
                            "stow",
                            package,
                            f"cannot stow directory {pkg_path_from_cwd} over existing non-directory target {target_subpath}",
                        )
                    else:
                        self.do_mv(target_subpath, pkg_path_from_cwd)
                        self.do_link(link_dest, target_subpath)
                else:
                    self.conflict(
                        "stow",
                        package,
                        f"cannot stow {pkg_path_from_cwd} over existing target {target_subpath} "
                        f"since neither a link nor a directory and --adopt not specified",
                    )

        elif (
            self.no_folding
            and os.path.isdir(pkg_path_from_cwd)
            and not os.path.islink(pkg_path_from_cwd)
        ):
            self.do_mkdir(target_subpath)
            self.stow_contents(self.stow_path, package, pkg_subpath, target_subpath)
        else:
            self.do_link(link_dest, target_subpath)

    def should_skip_target(self, target: str) -> bool:
        """Determine whether target is a stow directory which should not be altered."""
        if target == self.stow_path:
            print(
                f"WARNING: skipping target which was current stow directory {target}",
                file=sys.stderr,
            )
            return True

        if self.marked_stow_dir(target):
            print(f"WARNING: skipping marked Stow directory {target}", file=sys.stderr)
            return True

        nonstow_file = join_paths(target, ".nonstow")
        if os.path.exists(nonstow_file):
            print(f"WARNING: skipping protected directory {target}", file=sys.stderr)
            return True

        debug(4, 1, f"{target} not protected; shouldn't skip")
        return False

    def marked_stow_dir(self, dir_path: str) -> bool:
        """Check if directory contains .stow marker file."""
        stow_file = join_paths(dir_path, ".stow")
        if os.path.exists(stow_file):
            debug(5, 5, f"> {dir_path} contained .stow")
            return True
        return False

    def unstow_contents(
        self, package: str, pkg_subdir: str, target_subdir: str
    ) -> None:
        """Unstow the contents of the given directory.

        Note: unstow_node() and unstow_contents() are mutually recursive.
        Here we traverse the package tree, rather than the target tree."""
        if self.should_skip_target(target_subdir):
            return

        cwd = os.getcwd()
        compat_str = ", compat" if self.compat else ""
        msg = f"Unstowing contents of {self.stow_path} / {package} / {pkg_subdir} (cwd={cwd}{compat_str})"

        home = os.environ.get("HOME", "")
        if home:
            msg = msg.replace(home + "/", "~/")

        debug(3, 0, msg)
        debug(4, 1, f"target subdir is {target_subdir}")

        # Calculate the path to the package directory or sub-directory
        # whose contents need to be unstowed, relative to the current
        # (target directory).
        pkg_path_from_cwd = join_paths(self.stow_path, package, pkg_subdir)

        if self.compat:
            # In compat mode we traverse the target tree not the source tree,
            # so we're unstowing the contents of /target/foo, there's no
            # guarantee that the corresponding /stow/mypkg/foo exists.
            if not os.path.isdir(target_subdir):
                error(
                    f"unstow_contents() in compat mode called with non-directory target: {target_subdir}"
                )
        else:
            # We traverse the package installation image tree not the
            # target tree, so pkg_path_from_cwd must exist.
            if not os.path.isdir(pkg_path_from_cwd):
                error(
                    f"unstow_contents() called with non-directory path: {pkg_path_from_cwd}"
                )
            # When called at the top level, target_subdir should exist. And
            # unstow_node() should only call this via mutual recursion if
            # target_subdir exists.
            if not self.is_a_node(target_subdir):
                error(f"unstow_contents() called with invalid target: {target_subdir}")

        dir_to_read = target_subdir if self.compat else pkg_path_from_cwd
        try:
            listing = os.listdir(dir_to_read)
        except OSError as e:
            error(f"cannot read directory: {dir_to_read} ({e})")

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            package_node = node
            target_node = node
            target_node_path = join_paths(target_subdir, target_node)

            if self.ignore(self.stow_path, package, target_node_path):
                continue

            if self.dotfiles:
                if self.compat:
                    adjusted = unadjust_dotfile(node)
                    if adjusted != node:
                        debug(4, 1, f"Reverse adjusting: {node} => {adjusted}")
                        package_node = adjusted
                else:
                    adjusted = adjust_dotfile(node)
                    if adjusted != node:
                        debug(4, 1, f"Adjusting: {node} => {adjusted}")
                        target_node = adjusted
                        target_node_path = join_paths(target_subdir, target_node)

            package_node_path = join_paths(pkg_subdir, package_node)
            self.unstow_node(package, package_node_path, target_node_path)

        if not self.compat and os.path.isdir(target_subdir):
            self.cleanup_invalid_links(target_subdir)

    def unstow_node(self, package: str, pkg_subpath: str, target_subpath: str) -> None:
        """Unstow the given node.

        Note: unstow_node() and unstow_contents() are mutually recursive."""
        debug(3, 0, f"Unstowing entry from target: {target_subpath}")
        debug(4, 1, f"Package entry: {self.stow_path} / {package} / {pkg_subpath}")

        # Does the target exist?
        if self.is_a_link(target_subpath):
            self.unstow_link_node(package, pkg_subpath, target_subpath)
        elif os.path.isdir(target_subpath):
            self.unstow_contents(package, pkg_subpath, target_subpath)
            # This action may have made the parent directory foldable
            parent_in_pkg = self.foldable(target_subpath)
            if parent_in_pkg:
                self.fold_tree(target_subpath, parent_in_pkg)
        elif os.path.exists(target_subpath):
            debug(2, 1, f"{target_subpath} doesn't need to be unstowed")
        else:
            debug(2, 1, f"{target_subpath} did not exist to be unstowed")

    def unstow_link_node(
        self, package: str, pkg_subpath: str, target_subpath: str
    ) -> None:
        debug(4, 2, f"Evaluate existing link: {target_subpath}")

        # Where is the link pointing?
        link_dest = self.read_a_link(target_subpath)
        if not link_dest:
            error(f"Could not read link: {target_subpath}")

        if link_dest.startswith("/"):
            print(
                f"Ignoring an absolute symlink: {target_subpath} => {link_dest}",
                file=sys.stderr,
            )
            return

        # Does it point to a node under any stow directory?
        existing_pkg_path_from_cwd, existing_stow_path, existing_package = (
            self.find_stowed_path(target_subpath, link_dest)
        )

        if not existing_pkg_path_from_cwd:
            # The user is unstowing the package, so they don't want links to it.
            # Therefore we should allow them to have a link pointing elsewhere
            # which would conflict with the package if they were stowing it.
            debug(5, 3, f"Ignoring unowned link {target_subpath} => {link_dest}")
            return

        pkg_path_from_cwd = join_paths(self.stow_path, package, pkg_subpath)

        # Does the existing target_subpath actually point to anything?
        if os.path.exists(existing_pkg_path_from_cwd):
            if existing_pkg_path_from_cwd == pkg_path_from_cwd:
                # It points to the package we're unstowing, so unstow the link.
                self.do_unlink(target_subpath)
            else:
                debug(5, 3, f"Ignoring link {target_subpath} => {link_dest}")
        else:
            debug(
                2,
                0,
                f"--- removing invalid link into a stow directory: {pkg_path_from_cwd}",
            )
            self.do_unlink(target_subpath)

    def link_owned_by_package(self, target_subpath: str, link_dest: str) -> str:
        """Determine whether the given link points to a member of a stowed package."""
        _, _, package = self.find_stowed_path(target_subpath, link_dest)
        return package

    def find_stowed_path(
        self, target_subpath: str, link_dest: str
    ) -> tuple[str, str, str]:
        """
        Determine whether the given symlink within the target directory
        is a stowed path pointing to a member of a package under the stow dir.

        Returns (pkg_path_from_cwd, stow_path, package) or ('', '', '').
        """
        if link_dest.startswith("/"):
            return ("", "", "")

        debug(4, 2, f"find_stowed_path(target={target_subpath}; source={link_dest})")
        pkg_path_from_cwd = join_paths(parent(target_subpath), link_dest)
        debug(4, 3, f"is symlink destination {pkg_path_from_cwd} owned by stow?")

        package, pkg_subpath = self.link_dest_within_stow_dir(pkg_path_from_cwd)
        if package:
            debug(
                4,
                3,
                f"yes - package {package} in {self.stow_path} may contain {pkg_subpath}",
            )
            return (pkg_path_from_cwd, self.stow_path, package)

        stow_path, ext_package = self.find_containing_marked_stow_dir(pkg_path_from_cwd)
        if stow_path:
            debug(
                5,
                5,
                f"yes - {stow_path} in {pkg_path_from_cwd} was marked as a stow dir; package={ext_package}",
            )
            return (pkg_path_from_cwd, stow_path, ext_package)

        return ("", "", "")

    def link_dest_within_stow_dir(self, link_dest: str) -> tuple[str, str]:
        """Detect whether symlink destination is within current stow dir."""
        debug(4, 4, f"common prefix? link_dest={link_dest}; stow_path={self.stow_path}")

        prefix = self.stow_path + "/"
        if not link_dest.startswith(prefix):
            debug(4, 3, f"no - {link_dest} not under {self.stow_path}")
            return ("", "")

        remaining = link_dest[len(prefix) :]
        debug(4, 4, f"remaining after removing {self.stow_path}: {remaining}")

        parts = remaining.split("/")
        package = parts[0] if parts else ""
        pkg_subpath = "/".join(parts[1:]) if len(parts) > 1 else ""
        return (package, pkg_subpath)

    def find_containing_marked_stow_dir(
        self, pkg_path_from_cwd: str
    ) -> tuple[str, str]:
        """Detect whether path is within a marked stow directory."""
        segments = [s for s in pkg_path_from_cwd.split("/") if s]

        for last_segment in range(len(segments)):
            path_so_far = "/".join(segments[: last_segment + 1])
            debug(5, 5, f"is {path_so_far} marked stow dir?")
            if self.marked_stow_dir(path_so_far):
                if last_segment == len(segments) - 1:
                    internal_error("find_stowed_path() called directly on stow dir")

                package = segments[last_segment + 1]
                return (path_so_far, package)

        return ("", "")

    def cleanup_invalid_links(self, dir_path: str) -> None:
        """Clean up orphaned links that may block folding."""
        cwd = os.getcwd()
        debug(2, 0, f"Cleaning up any invalid links in {dir_path} (pwd={cwd})")

        if not os.path.isdir(dir_path):
            internal_error(
                f"cleanup_invalid_links() called with a non-directory: {dir_path}"
            )

        try:
            listing = os.listdir(dir_path)
        except OSError as e:
            error(f"cannot read directory: {dir_path} ({e})")

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            node_path = join_paths(dir_path, node)

            if not os.path.islink(node_path):
                continue

            debug(4, 1, f"Checking validity of link {node_path}")

            if node_path in self.link_task_for:
                task = self.link_task_for[node_path]
                if task.action != TaskAction.REMOVE:
                    print(
                        f"Unexpected action {task.action.value} scheduled for {node_path}; skipping clean-up",
                        file=sys.stderr,
                    )
                else:
                    debug(4, 2, f"{node_path} scheduled for removal; skipping clean-up")
                continue

            try:
                link_dest = os.readlink(node_path)
            except OSError:
                error(f"Could not read link {node_path}")

            target_subpath = join_paths(dir_path, link_dest)
            debug(4, 2, f"join {dir_path} {link_dest}")

            if os.path.exists(target_subpath):
                debug(
                    4,
                    2,
                    f"Link target {link_dest} exists at {target_subpath}; skipping clean up",
                )
                continue
            else:
                debug(
                    4, 2, f"Link target {link_dest} doesn't exist at {target_subpath}"
                )

            debug(
                3,
                1,
                f"Checking whether valid link {node_path} -> {link_dest} is owned by stow",
            )

            owner = self.link_owned_by_package(node_path, link_dest)
            if owner:
                debug(
                    2,
                    0,
                    f"--- removing link owned by {owner}: {node_path} => {join_paths(dir_path, link_dest)}",
                )
                self.do_unlink(node_path)

    def foldable(self, target_subdir: str) -> str:
        """
        Determine whether a tree can be folded.

        Returns path to the parent dir iff the tree can be safely folded.
        """
        debug(3, 2, f"Is {target_subdir} foldable?")

        if self.no_folding:
            debug(3, 3, "Not foldable because --no-folding enabled")
            return ""

        try:
            listing = os.listdir(target_subdir)
        except OSError as e:
            error(f'Cannot read directory "{target_subdir}" ({e})\n')

        parent_in_pkg = ""

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            target_node_path = join_paths(target_subdir, node)

            if not self.is_a_node(target_node_path):
                continue

            if not self.is_a_link(target_node_path):
                debug(3, 3, f"Not foldable because {target_node_path} not a link")
                return ""

            link_dest = self.read_a_link(target_node_path)
            if not link_dest:
                error(f"Could not read link {target_node_path}")

            new_parent = parent(link_dest)
            if parent_in_pkg == "":
                parent_in_pkg = new_parent
            elif parent_in_pkg != new_parent:
                debug(
                    3,
                    3,
                    f"Not foldable because {target_subdir} contains links to entries in both {parent_in_pkg} and {new_parent}",
                )
                return ""

        if not parent_in_pkg:
            debug(3, 3, f"Not foldable because {target_subdir} contains no links")
            return ""

        if parent_in_pkg.startswith("../"):
            parent_in_pkg = parent_in_pkg[3:]

        if self.link_owned_by_package(target_subdir, parent_in_pkg):
            debug(3, 3, f"{target_subdir} is foldable")
            return parent_in_pkg
        else:
            debug(3, 3, f"{target_subdir} is not foldable")
            return ""

    def fold_tree(self, target_subdir: str, pkg_subpath: str) -> None:
        """Fold the given tree."""
        debug(3, 0, f"--- Folding tree: {target_subdir} => {pkg_subpath}")

        try:
            listing = os.listdir(target_subdir)
        except OSError as e:
            error(f'Cannot read directory "{target_subdir}" ({e})\n')

        for node in sorted(listing):
            if node in (".", ".."):
                continue
            node_path = join_paths(target_subdir, node)
            if not self.is_a_node(node_path):
                continue
            self.do_unlink(node_path)

        self.do_rmdir(target_subdir)
        self.do_link(pkg_subpath, target_subdir)

    def conflict(self, action: str, package: str, message: str) -> None:
        """Handle conflicts in stow operations."""
        debug(2, 0, f"CONFLICT when {action}ing {package}: {message}")

        self.conflicts.setdefault(action, {}).setdefault(package, []).append(message)
        self.conflict_count += 1

    def get_conflicts(self) -> dict:
        """Returns a nested dict of all potential conflicts discovered."""
        return self.conflicts

    def get_conflict_count(self) -> int:
        """Returns the number of conflicts found."""
        return self.conflict_count

    def get_tasks(self) -> list[Task]:
        """Returns a list of all pending tasks."""
        return self.tasks

    def get_action_count(self) -> int:
        """Returns the number of actions planned for this Stow instance."""
        return self.action_count

    def ignore(self, stow_path: str, package: str, target: str) -> bool:
        """Determine if the given path matches a regex in our ignore list."""
        if not target:
            internal_error("Stow.ignore() called with empty target")

        for suffix in self.ignore_list:
            if suffix.search(target):
                debug(4, 1, f"Ignoring path {target} due to --ignore={suffix.pattern}")
                return True

        package_dir = join_paths(stow_path, package)
        path_regexp, segment_regexp = self.get_ignore_regexps(package_dir)

        if path_regexp is not None:
            debug(5, 2, f"Ignore list regexp for paths:    /{path_regexp.pattern}/")
        else:
            debug(5, 2, "Ignore list regexp for paths:    none")

        if segment_regexp is not None:
            debug(5, 2, f"Ignore list regexp for segments: /{segment_regexp.pattern}/")
        else:
            debug(5, 2, "Ignore list regexp for segments: none")

        if path_regexp is not None and path_regexp.search("/" + target):
            debug(4, 1, f"Ignoring path /{target}")
            return True

        basename = target.rsplit("/", 1)[-1]
        if segment_regexp is not None and segment_regexp.search(basename):
            debug(4, 1, f"Ignoring path segment {basename}")
            return True

        debug(5, 1, f"Not ignoring {target}")
        return False

    @property
    def ignore_list(self) -> list:
        return getattr(self, "_ignore", [])

    @ignore_list.setter
    def ignore_list(self, value):
        self._ignore = value

    def get_ignore_regexps(self, dir_path: str) -> tuple:
        """Get ignore regexps for the given package directory."""
        local_stow_ignore = join_paths(dir_path, LOCAL_IGNORE_FILE)
        home = os.environ.get("HOME", "")
        global_stow_ignore = join_paths(home, GLOBAL_IGNORE_FILE) if home else ""

        for file_path in (local_stow_ignore, global_stow_ignore):
            if file_path and os.path.exists(file_path):
                debug(5, 1, f"Using ignore file: {file_path}")
                return self.get_ignore_regexps_from_file(file_path)
            else:
                debug(5, 1, f"{file_path} didn't exist")

        debug(4, 1, "Using built-in ignore list")
        return self.get_default_global_ignore_regexps()

    def get_ignore_regexps_from_file(self, file_path: str) -> tuple:
        """Get ignore regexps from a file, with memoization."""
        if file_path in _ignore_file_regexps:
            debug(4, 2, f"Using memoized regexps from {file_path}")
            return _ignore_file_regexps[file_path]

        try:
            with open(file_path, "r") as f:
                regexps = self.get_ignore_regexps_from_fh(f)
        except IOError as e:
            debug(4, 2, f"Failed to open {file_path}: {e}")
            return (None, None)

        _ignore_file_regexps[file_path] = regexps
        return regexps

    def invalidate_memoized_regexp(self, file_path: str) -> None:
        """Invalidate memoized regexp for a file."""
        if file_path in _ignore_file_regexps:
            debug(4, 2, f"Invalidated memoized regexp for {file_path}")
            del _ignore_file_regexps[file_path]
        else:
            debug(2, 1, f"WARNING: no memoized regexp for {file_path} to invalidate")

    def get_ignore_regexps_from_fh(self, fh) -> tuple:
        """Parse ignore patterns from a file handle."""
        regexps = {}

        for line in fh:
            line = line.strip()

            if line.startswith("#") or len(line) == 0:
                continue

            line = re.sub(r"\s+#.+", "", line)
            line = line.replace("\\#", "#")

            regexps[line] = regexps.get(line, 0) + 1

        local_ignore_pattern = "^/" + re.escape(LOCAL_IGNORE_FILE) + "$"
        regexps[local_ignore_pattern] = regexps.get(local_ignore_pattern, 0) + 1

        return self.compile_ignore_regexps(regexps)

    def compile_ignore_regexps(self, regexps: dict) -> tuple:
        """Compile ignore patterns into path and segment regexps."""
        segment_regexps = []
        path_regexps = []

        for regexp in regexps.keys():
            if "/" not in regexp:
                segment_regexps.append(regexp)
            else:
                path_regexps.append(regexp)

        segment_regexp = None
        path_regexp = None

        if segment_regexps:
            combined = "|".join(segment_regexps)
            segment_regexp = self.compile_regexp(f"^({combined})$")

        if path_regexps:
            combined = "|".join(path_regexps)
            path_regexp = self.compile_regexp(f"(^|/)({combined})(/|$)")

        return (path_regexp, segment_regexp)

    def compile_regexp(self, regexp: str):
        """Compile a single regexp pattern."""
        try:
            return re.compile(regexp)
        except re.error as e:
            raise RuntimeError(f"Failed to compile regexp: {e}")

    def get_default_global_ignore_regexps(self) -> tuple:
        """Get default global ignore regexps."""
        default_patterns = """
# Comments and blank lines are allowed.

RCS
.+,v

CVS
\\.\\#.+       # CVS conflict files / emacs lock files
\\.cvsignore

\\.svn
_darcs
\\.hg

\\.git
\\.gitignore
\\.gitmodules

.+~          # emacs backup files
\\#.*\\#       # emacs autosave files

^/README.*
^/LICENSE.*
^/COPYING
"""
        regexps = {}
        for line in default_patterns.strip().split("\n"):
            line = line.strip()
            if line.startswith("#") or len(line) == 0:
                continue
            line = re.sub(r"\s+#.+", "", line)
            line = line.replace("\\#", "#")
            regexps[line] = regexps.get(line, 0) + 1

        local_ignore_pattern = "^/" + re.escape(LOCAL_IGNORE_FILE) + "$"
        regexps[local_ignore_pattern] = regexps.get(local_ignore_pattern, 0) + 1

        return self.compile_ignore_regexps(regexps)

    def defer(self, path: str) -> bool:
        """Determine if the given path matches a regex in our defer list."""
        for prefix in self.defer_list:
            if prefix.search(path):
                return True
        return False

    @property
    def defer_list(self) -> list:
        return getattr(self, "_defer", [])

    @defer_list.setter
    def defer_list(self, value):
        self._defer = value

    def override(self, path: str) -> bool:
        """Determine if the given path matches a regex in our override list."""
        for regex in self.override_list:
            if regex.search(path):
                return True
        return False

    @property
    def override_list(self) -> list:
        return getattr(self, "_override", [])

    @override_list.setter
    def override_list(self, value):
        self._override = value

    def process_tasks(self) -> None:
        """Process each task in the tasks list."""
        debug(2, 0, "Processing tasks...")

        # Strip out all tasks with a skip action
        self.tasks = [t for t in self.tasks if t.action != TaskAction.SKIP]

        if not self.tasks:
            return

        def do_process():
            for task in self.tasks:
                self.process_task(task)

        self.within_target_do(do_process)

        debug(2, 0, "Processing tasks... done")

    def process_task(self, task: Task) -> None:
        """Process a single task using pattern matching."""
        match (task.action, task.type):
            case (TaskAction.CREATE, TaskType.DIR):
                try:
                    os.mkdir(task.path, 0o777)
                except OSError as e:
                    error(f"Could not create directory: {task.path} ({e})")

            case (TaskAction.CREATE, TaskType.LINK):
                try:
                    os.symlink(task.source, task.path)
                except OSError as e:
                    error(
                        f"Could not create symlink: {task.path} => {task.source} ({e})"
                    )

            case (TaskAction.REMOVE, TaskType.DIR):
                try:
                    os.rmdir(task.path)
                except OSError as e:
                    error(f"Could not remove directory: {task.path} ({e})")

            case (TaskAction.REMOVE, TaskType.LINK):
                try:
                    os.unlink(task.path)
                except OSError as e:
                    error(f"Could not remove link: {task.path} ({e})")

            case (TaskAction.MOVE, TaskType.FILE):
                try:
                    shutil.move(task.path, task.dest)
                except (IOError, OSError) as e:
                    error(f"Could not move {task.path} -> {task.dest} ({e})")

            case _:
                internal_error(f"bad task action: {task.action.value}")

    def link_task_action(self, path: str) -> str:
        """Finds the link task action for the given path, if there is one."""
        if path not in self.link_task_for:
            debug(4, 4, f"| link_task_action({path}): no task")
            return ""

        action = self.link_task_for[path].action
        if action not in (TaskAction.REMOVE, TaskAction.CREATE):
            internal_error(f"bad task action: {action.value}")

        debug(
            4,
            1,
            f"link_task_action({path}): link task exists with action {action.value}",
        )
        return action.value

    def dir_task_action(self, path: str) -> str:
        """Finds the dir task action for the given path, if there is one."""
        if path not in self.dir_task_for:
            debug(4, 4, f"| dir_task_action({path}): no task")
            return ""

        action = self.dir_task_for[path].action
        if action not in (TaskAction.REMOVE, TaskAction.CREATE):
            internal_error(f"bad task action: {action.value}")

        debug(
            4,
            4,
            f"| dir_task_action({path}): dir task exists with action {action.value}",
        )
        return action.value

    def parent_link_scheduled_for_removal(self, target_path: str) -> bool:
        """Determine whether the given path or any parent is a link scheduled for removal."""
        prefix = ""
        for part in target_path.split("/"):
            if not part:
                continue
            prefix = join_paths(prefix, part)
            debug(
                5,
                4,
                f"| parent_link_scheduled_for_removal({target_path}): prefix {prefix}",
            )
            if (
                prefix in self.link_task_for
                and self.link_task_for[prefix].action == TaskAction.REMOVE
            ):
                debug(
                    4,
                    4,
                    f"| parent_link_scheduled_for_removal({target_path}): link scheduled for removal",
                )
                return True

        debug(
            4, 4, f"| parent_link_scheduled_for_removal({target_path}): returning false"
        )
        return False

    def is_a_link(self, target_path: str) -> bool:
        """Determine if the given path is a current or planned link."""
        debug(4, 2, f"is_a_link({target_path})")

        action = self.link_task_action(target_path)
        match action:
            case "remove":
                debug(
                    4, 2, f"is_a_link({target_path}): returning 0 (remove action found)"
                )
                return False
            case "create":
                debug(
                    4, 2, f"is_a_link({target_path}): returning 1 (create action found)"
                )
                return True

        if os.path.islink(target_path):
            debug(4, 2, f"is_a_link({target_path}): is a real link")
            return not self.parent_link_scheduled_for_removal(target_path)

        debug(4, 2, f"is_a_link({target_path}): returning 0")
        return False

    def is_a_dir(self, target_path: str) -> bool:
        """Determine if the given path is a current or planned directory."""
        debug(4, 1, f"is_a_dir({target_path})")

        action = self.dir_task_action(target_path)
        match action:
            case "remove":
                return False
            case "create":
                return True

        if self.parent_link_scheduled_for_removal(target_path):
            return False

        if os.path.isdir(target_path):
            debug(4, 1, f"is_a_dir({target_path}): real dir")
            return True

        debug(4, 1, f"is_a_dir({target_path}): returning false")
        return False

    def is_a_node(self, target_path: str) -> bool:
        """Determine whether the given path is a current or planned node."""
        debug(4, 4, f"| Checking whether {target_path} is a current/planned node")

        laction = self.link_task_action(target_path)
        daction = self.dir_task_action(target_path)

        # Use pattern matching for the truth table
        match (laction, daction):
            case ("remove", "remove"):
                internal_error(f"removing link and dir: {target_path}")
                return False
            case ("remove", "create"):
                # Unfolding: link removal before dir creation
                return True
            case ("remove", ""):
                return False
            case ("create", "remove"):
                # Folding: dir removal before link creation
                return True
            case ("create", "create"):
                internal_error(f"creating link and dir: {target_path}")
                return True
            case ("create", _):
                return True
            case ("", "remove"):
                return False
            case ("", "create"):
                return True
            case ("", ""):
                pass  # Fall through to filesystem check

        if self.parent_link_scheduled_for_removal(target_path):
            return False

        if os.path.exists(target_path) or os.path.islink(target_path):
            debug(4, 3, f"| is_a_node({target_path}): really exists")
            return True

        debug(4, 3, f"| is_a_node({target_path}): returning false")
        return False

    def read_a_link(self, link: str) -> str:
        """Return the destination of a current or planned link."""
        action = self.link_task_action(link)
        if action:
            debug(4, 2, f"read_a_link({link}): task exists with action {action}")

            if action == "create":
                return self.link_task_for[link].source
            elif action == "remove":
                internal_error(
                    f"read_a_link() passed a path that is scheduled for removal: {link}"
                )

        elif os.path.islink(link):
            debug(4, 2, f"read_a_link({link}): is a real link")
            try:
                return os.readlink(link)
            except OSError as e:
                error(f"Could not read link: {link} ({e})")

        internal_error(f"read_a_link() passed a non-link path: {link}")

    def do_link(self, link_dest: str, link_src: str) -> None:
        """Wrap 'link' operation for later processing."""
        if link_src in self.dir_task_for:
            task_ref = self.dir_task_for[link_src]

            if task_ref.action == TaskAction.CREATE:
                if task_ref.type == TaskType.DIR:
                    internal_error(
                        f"new link ({link_src} => {link_dest}) clashes with planned new directory"
                    )
            elif task_ref.action == TaskAction.REMOVE:
                pass  # May need to remove a directory before creating a link
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        if link_src in self.link_task_for:
            task_ref = self.link_task_for[link_src]

            if task_ref.action == TaskAction.CREATE:
                if task_ref.source != link_dest:
                    internal_error(
                        f"new link clashes with planned new link: {task_ref.path} => {task_ref.source}"
                    )
                else:
                    debug(
                        1,
                        0,
                        f"LINK: {link_src} => {link_dest} (duplicates previous action)",
                    )
                    return

            elif task_ref.action == TaskAction.REMOVE:
                if task_ref.source == link_dest:
                    debug(
                        1,
                        0,
                        f"LINK: {link_src} => {link_dest} (reverts previous action)",
                    )
                    self.link_task_for[link_src].action = TaskAction.SKIP
                    del self.link_task_for[link_src]
                    return
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        debug(1, 0, f"LINK: {link_src} => {link_dest}")
        task = Task(
            action=TaskAction.CREATE,
            type=TaskType.LINK,
            path=link_src,
            source=link_dest,
        )
        self.tasks.append(task)
        self.link_task_for[link_src] = task

    def do_unlink(self, file_path: str) -> None:
        """Wrap 'unlink' operation for later processing."""
        if file_path in self.link_task_for:
            task_ref = self.link_task_for[file_path]

            if task_ref.action == TaskAction.REMOVE:
                debug(1, 0, f"UNLINK: {file_path} (duplicates previous action)")
                return
            elif task_ref.action == TaskAction.CREATE:
                debug(1, 0, f"UNLINK: {file_path} (reverts previous action)")
                self.link_task_for[file_path].action = TaskAction.SKIP
                del self.link_task_for[file_path]
                return
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        if (
            file_path in self.dir_task_for
            and self.dir_task_for[file_path].action == TaskAction.CREATE
        ):
            internal_error(
                f"new unlink operation clashes with planned operation: {self.dir_task_for[file_path].action.value} dir {file_path}"
            )

        debug(1, 0, f"UNLINK: {file_path}")

        try:
            source = os.readlink(file_path)
        except OSError as e:
            error(f"could not readlink {file_path} ({e})")

        task = Task(
            action=TaskAction.REMOVE,
            type=TaskType.LINK,
            path=file_path,
            source=source,
        )
        self.tasks.append(task)
        self.link_task_for[file_path] = task

    def do_mkdir(self, dir_path: str) -> None:
        """Wrap 'mkdir' operation."""
        if dir_path in self.link_task_for:
            task_ref = self.link_task_for[dir_path]

            if task_ref.action == TaskAction.CREATE:
                internal_error(
                    f"new dir clashes with planned new link ({task_ref.path} => {task_ref.source})"
                )
            elif task_ref.action == TaskAction.REMOVE:
                pass  # May need to remove a link before creating a directory
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        if dir_path in self.dir_task_for:
            task_ref = self.dir_task_for[dir_path]

            if task_ref.action == TaskAction.CREATE:
                debug(1, 0, f"MKDIR: {dir_path} (duplicates previous action)")
                return
            elif task_ref.action == TaskAction.REMOVE:
                debug(1, 0, f"MKDIR: {dir_path} (reverts previous action)")
                self.dir_task_for[dir_path].action = TaskAction.SKIP
                del self.dir_task_for[dir_path]
                return
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        debug(1, 0, f"MKDIR: {dir_path}")
        task = Task(
            action=TaskAction.CREATE,
            type=TaskType.DIR,
            path=dir_path,
        )
        self.tasks.append(task)
        self.dir_task_for[dir_path] = task

    def do_rmdir(self, dir_path: str) -> None:
        """Wrap 'rmdir' operation."""
        if dir_path in self.link_task_for:
            task_ref = self.link_task_for[dir_path]
            internal_error(
                f"rmdir clashes with planned operation: {task_ref.action.value} link {task_ref.path} => {task_ref.source}"
            )

        if dir_path in self.dir_task_for:
            task_ref = self.dir_task_for[dir_path]

            if task_ref.action == TaskAction.REMOVE:
                debug(1, 0, f"RMDIR {dir_path} (duplicates previous action)")
                return
            elif task_ref.action == TaskAction.CREATE:
                debug(1, 0, f"MKDIR {dir_path} (reverts previous action)")
                self.dir_task_for[dir_path].action = TaskAction.SKIP
                del self.dir_task_for[dir_path]
                return
            else:
                internal_error(f"bad task action: {task_ref.action.value}")

        debug(1, 0, f"RMDIR {dir_path}")
        task = Task(
            action=TaskAction.REMOVE,
            type=TaskType.DIR,
            path=dir_path,
            source="",
        )
        self.tasks.append(task)
        self.dir_task_for[dir_path] = task

    def do_mv(self, src: str, dst: str) -> None:
        """Wrap 'move' operation for later processing."""
        if src in self.link_task_for:
            task_ref = self.link_task_for[src]
            internal_error(
                f"do_mv: pre-existing link task for {src}; action: {task_ref.action.value}, source: {task_ref.source}"
            )
        elif src in self.dir_task_for:
            task_ref = self.dir_task_for[src]
            internal_error(
                f"do_mv: pre-existing dir task for {src}?! action: {task_ref.action.value}"
            )

        debug(1, 0, f"MV: {src} -> {dst}")

        task = Task(
            action=TaskAction.MOVE,
            type=TaskType.FILE,
            path=src,
            dest=dst,
        )
        self.tasks.append(task)
