# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Core stow operations - manage farms of symbolic links.

This module provides the public API for stowing and unstowing packages,
as well as the internal _Stower class that handles planning and execution.
"""

from __future__ import annotations

import functools
import os
import re
import sys
from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

from stow_python.types import (
    Action,
    Task,
    LinkTask,
    DirTask,
    MoveTask,
    StowError,
    StowInternalError,
    StowedPath,
    PackageSubpath,
    MarkedStowDir,
    IgnorePatterns,
    StowConfig,
    StowResult,
    StowJob,
    StowScanJob,
    StowNodeJob,
    UnstowJob,
    UnstowScanJob,
    UnstowNodeJob,
    FoldJob,
    CleanupJob,
)
from stow_python.util import (
    debug,
    get_debug_level,
    set_debug_level,
    join_paths,
    parent,
    canon_path,
    adjust_dotfile,
    unadjust_dotfile,
    require_directory,
    within_dir,
    move,
    process_lock,
)

LOCAL_IGNORE_FILE = ".stow-local-ignore"
GLOBAL_IGNORE_FILE = ".stow-global-ignore"


# =============================================================================
# Public API
# =============================================================================


def stow(
    *package_names: str,
    config: Optional[StowConfig] = None,
    **kwargs,
) -> StowResult:
    """Stow packages into target directory.

    Args:
        *package_names: Names of packages to stow (in stow dir)
        config: Optional StowConfig for configuration
        **kwargs: Override config fields (dir, target, dotfiles, etc.)

    Returns:
        StowResult with success status, conflicts (if any), and tasks performed
    """
    cfg = _make_config(config, **kwargs)
    stower = _Stower(cfg)
    stower.plan_stow(list(package_names))
    return stower.execute()


def unstow(
    *package_names: str,
    config: Optional[StowConfig] = None,
    **kwargs,
) -> StowResult:
    """Unstow packages from target directory.

    Args:
        *package_names: Names of packages to unstow
        config: Optional StowConfig for configuration
        **kwargs: Override config fields (dir, target, dotfiles, etc.)

    Returns:
        StowResult with success status, conflicts (if any), and tasks performed
    """
    cfg = _make_config(config, **kwargs)
    stower = _Stower(cfg)
    stower.plan_unstow(list(package_names))
    return stower.execute()


def restow(
    *package_names: str,
    config: Optional[StowConfig] = None,
    **kwargs,
) -> StowResult:
    """Restow packages (unstow then stow).

    Useful after updating package contents.

    Args:
        *package_names: Names of packages to restow
        config: Optional StowConfig for configuration
        **kwargs: Override config fields (dir, target, dotfiles, etc.)

    Returns:
        StowResult with success status, conflicts (if any), and tasks performed
    """
    cfg = _make_config(config, **kwargs)
    stower = _Stower(cfg)
    stower.plan_unstow(list(package_names))
    stower.plan_stow(list(package_names))
    return stower.execute()


def _make_config(config: Optional[StowConfig], **kwargs) -> StowConfig:
    """Create a StowConfig from optional base config and overrides."""
    if config is None:
        merged = StowConfig(
            dir=kwargs.pop("dir", "."),
            target=kwargs.pop("target", None),
            dotfiles=kwargs.pop("dotfiles", False),
            adopt=kwargs.pop("adopt", False),
            no_folding=kwargs.pop("no_folding", False),
            simulate=kwargs.pop("simulate", False),
            verbose=kwargs.pop("verbose", 0),
            compat=kwargs.pop("compat", False),
            ignore=tuple(kwargs.pop("ignore", ())),
            defer=tuple(kwargs.pop("defer", ())),
            override=tuple(kwargs.pop("override", ())),
        )
    elif kwargs:
        # Merge base config with overrides
        merged = StowConfig(
            dir=kwargs.pop("dir", config.dir),
            target=kwargs.pop("target", config.target),
            dotfiles=kwargs.pop("dotfiles", config.dotfiles),
            adopt=kwargs.pop("adopt", config.adopt),
            no_folding=kwargs.pop("no_folding", config.no_folding),
            simulate=kwargs.pop("simulate", config.simulate),
            verbose=kwargs.pop("verbose", config.verbose),
            compat=kwargs.pop("compat", config.compat),
            ignore=tuple(kwargs.pop("ignore", config.ignore)),
            defer=tuple(kwargs.pop("defer", config.defer)),
            override=tuple(kwargs.pop("override", config.override)),
        )
    else:
        return config

    if kwargs:
        # A typo'd option name (e.g. adpot=True) must not silently change
        # behavior, especially for safety-relevant flags like adopt/simulate
        raise TypeError(
            f"unexpected configuration option(s): {', '.join(sorted(kwargs))}"
        )
    return merged


# =============================================================================
# Internal Stower class
# =============================================================================


class _Stower:
    """
    Internal class that manages state during stow/unstow planning and execution.

    This class is used internally by the module-level stow(), unstow(), restow()
    functions and by the CLI. It handles planning operations and executing them.
    """

    def __init__(self, config: StowConfig):
        self.c = config

        # Pre-compiled CLI patterns
        self._ignore_pats = list(config.ignore)
        self._defer_pats = list(config.defer)
        self._override_pats = list(config.override)



        with self._session():
            # Compute stow_path (relative path from target to stow dir)
            stow_dir_abs = canon_path(config.dir)
            target_abs = canon_path(config.target)
            self.stow_path = os.path.relpath(stow_dir_abs, target_abs)
            debug(2, 0, f"stow dir is {stow_dir_abs}")
            debug(
                2,
                0,
                f"stow dir path relative to target {target_abs} is {self.stow_path}",
            )

        # State
        self.conflicts: dict[str, list[str]] = {}
        self.tasks: list[Task] = []
        self.dir_task_for: dict[str, DirTask] = {}
        self.link_task_for: dict[str, LinkTask] = {}

    @contextmanager
    def _session(self) -> Iterator[None]:
        """Serialize a planning/execution phase and scope verbosity to it.

        Phases chdir into the target tree and route debug() through a
        process-wide verbosity level, so concurrent stow operations in one
        process must not interleave. Callers that change the working
        directory concurrently with a running operation are still on their
        own (see docs/architecture.md).
        """
        with process_lock:
            prev_verbosity = get_debug_level()
            set_debug_level(self.c.verbose)
            try:
                yield
            finally:
                set_debug_level(prev_verbosity)

    def plan_stow(self, packages: Sequence[str]) -> None:
        """Plan stow operations for the given packages."""
        if not packages:
            return

        for package in packages:
            if not package:
                raise StowError("Package name cannot be empty")

        with self._session():
            debug(2, 0, f"Planning stow of: {' '.join(packages)} ...")
            with within_dir(self.c.target, "target tree"):
                for package in packages:
                    pkg_path = join_paths(self.stow_path, package)
                    require_directory(
                        pkg_path,
                        f"The stow directory {self.stow_path} does not contain package {package}",
                    )
                    debug(2, 0, f"Planning stow of package {package}...")
                    self.stow_contents(self.stow_path, package, ".", ".")
                    debug(2, 0, f"Planning stow of package {package}... done")

    def plan_unstow(self, packages: Sequence[str]) -> None:
        """Plan unstow operations for the given packages."""
        if not packages:
            return

        for package in packages:
            if not package:
                raise StowError("Package name cannot be empty")

        with self._session():
            debug(2, 0, f"Planning unstow of: {' '.join(packages)} ...")
            with within_dir(self.c.target, "target tree"):
                for package in packages:
                    pkg_path = join_paths(self.stow_path, package)
                    require_directory(
                        pkg_path,
                        f"The stow directory {self.stow_path} does not contain package {package}",
                    )
                    debug(2, 0, f"Planning unstow of package {package}...")
                    self.unstow_contents(package, ".", ".")
                    debug(2, 0, f"Planning unstow of package {package}... done")

    def execute(self) -> StowResult:
        """Execute planned tasks and return result.

        Returns StowResult with success=False if there were conflicts,
        or success=True with the list of executed tasks.
        """
        if self.conflicts:
            return StowResult(
                success=False,
                conflicts=dict(self.conflicts),
                tasks=[],
            )

        if self.c.simulate:
            return StowResult(
                success=True,
                conflicts={},
                tasks=list(self.tasks),
            )

        self.process_tasks()
        return StowResult(
            success=True,
            conflicts={},
            tasks=list(self.tasks),
        )

    def process_tasks(self) -> None:
        """Process each task in the tasks list."""
        with self._session():
            debug(2, 0, "Processing tasks...")

            # Strip out all tasks with a skip action
            self.tasks = [t for t in self.tasks if not t.skipped]

            if not self.tasks:
                return

            with within_dir(self.c.target, "target tree"):
                for task in self.tasks:
                    self._process_task(task)

            debug(2, 0, "Processing tasks... done")

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

        The descent (scan a directory, visit each of its entries, which may
        scan subdirectories in turn) runs on an explicit job stack rather
        than by recursion, so arbitrarily deep trees cannot hit the
        interpreter recursion limit. Jobs execute in exactly the order the
        recursive formulation would."""
        jobs: list[StowJob] = [
            StowScanJob(stow_path, package, pkg_subdir, target_subdir)
        ]
        while jobs:
            job = jobs.pop()
            if isinstance(job, StowScanJob):
                self._stow_scan_dir(
                    job.stow_path, job.package, job.pkg_subdir, job.target_subdir, jobs
                )
            else:
                self._stow_visit_node(
                    job.stow_path,
                    job.package,
                    job.pkg_subdir,
                    job.target_subdir,
                    job.node,
                    jobs,
                )

    def _stow_scan_dir(
        self,
        stow_path: str,
        package: str,
        pkg_subdir: str,
        target_subdir: str,
        jobs: list[StowJob],
    ) -> None:
        """List one package directory and queue a visit for each entry."""
        if self._should_skip_target(pkg_subdir):
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

        if not self._is_a_node(target_subdir):
            raise StowError(
                f"stow_contents() called with non-directory target: {target_subdir}"
            )

        try:
            listing = os.listdir(pkg_path_from_cwd)
        except OSError as e:
            raise StowError(
                f"cannot read directory: {pkg_path_from_cwd} ({e.strerror})", errno=2
            ) from e

        # Pushed in reverse so that popping visits entries in sorted order
        for node in sorted(listing, reverse=True):
            jobs.append(
                StowNodeJob(stow_path, package, pkg_subdir, target_subdir, node)
            )

    def _stow_visit_node(
        self,
        stow_path: str,
        package: str,
        pkg_subdir: str,
        target_subdir: str,
        node: str,
        jobs: list[StowJob],
    ) -> None:
        """Run the per-entry ignore/dotfiles checks, then stow the node."""
        if node in (".", ".."):
            return

        package_node_path = join_paths(pkg_subdir, node)
        target_node = node
        target_node_path = join_paths(target_subdir, target_node)

        if self._should_ignore(stow_path, package, target_node_path):
            return

        if self.c.dotfiles:
            adjusted = adjust_dotfile(node)
            if adjusted != node:
                debug(4, 1, f"Adjusting: {node} => {adjusted}")
                target_node = adjusted
                target_node_path = join_paths(target_subdir, target_node)

        self._stow_node(stow_path, package, package_node_path, target_node_path, jobs)

    def _stow_node(
        self,
        stow_path: str,
        package: str,
        pkg_subpath: str,
        target_subpath: str,
        jobs: list[StowJob],
    ) -> None:
        """Stow the given node, queueing subdirectory scans onto the job stack."""
        debug(3, 0, f"Stowing entry {stow_path} / {package} / {pkg_subpath}")

        # Calculate the path to the package directory or sub-directory
        # whose contents need to be stowed, relative to the current
        # (target directory).
        pkg_path_from_cwd = join_paths(stow_path, package, pkg_subpath)

        # Don't try to stow absolute symlinks (they can't be unstowed)
        if os.path.islink(pkg_path_from_cwd):
            link_dest = self._read_a_link(pkg_path_from_cwd)
            if link_dest.startswith("/"):
                self._record_conflict(
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
        if self._is_a_link(target_subpath):
            self._stow_node_for_existing_link(
                stow_path, package, pkg_subpath, target_subpath, link_dest, jobs
            )
        elif self._is_a_node(target_subpath):
            self._stow_node_for_existing_node(
                package, pkg_subpath, target_subpath, pkg_path_from_cwd, link_dest, jobs
            )
        elif (
            self.c.no_folding
            and os.path.isdir(pkg_path_from_cwd)
            and not os.path.islink(pkg_path_from_cwd)
        ):
            self._do_mkdir(target_subpath)
            jobs.append(
                StowScanJob(self.stow_path, package, pkg_subpath, target_subpath)
            )
        else:
            self._do_link(link_dest, target_subpath)

    def _stow_node_for_existing_link(
        self,
        stow_path: str,
        package: str,
        pkg_subpath: str,
        target_subpath: str,
        link_dest: str,
        jobs: list[StowJob],
    ) -> None:
        """Handle stowing when target is an existing link."""
        existing_link_dest = self._read_a_link(target_subpath)
        if not existing_link_dest:
            raise StowError(f"Could not read link: {target_subpath}")

        debug(4, 1, f"Evaluate existing link: {target_subpath} => {existing_link_dest}")

        # Does it point to a node under any stow directory?
        stowed = self._find_stowed_path(target_subpath, existing_link_dest)

        if not stowed:
            self._record_conflict(
                package,
                f"existing target is not owned by stow: {target_subpath}",
            )
            return

        # Does the existing target_subpath actually point to anything?
        if self._is_a_node(stowed.path):
            if existing_link_dest == link_dest:
                debug(
                    2,
                    0,
                    f"--- Skipping {target_subpath} as it already points to {link_dest}",
                )
            elif self._should_defer(target_subpath):
                debug(2, 0, f"--- Deferring installation of: {target_subpath}")
            elif self._should_override(target_subpath):
                debug(2, 0, f"--- Overriding installation of: {target_subpath}")
                self._do_unlink(target_subpath)
                self._do_link(link_dest, target_subpath)
            elif self._is_a_dir(
                join_paths(parent(target_subpath), existing_link_dest)
            ) and self._is_a_dir(join_paths(parent(target_subpath), link_dest)):
                # If the existing link points to a directory,
                # and the proposed new link points to a directory,
                # then we can unfold (split open) the tree at that point
                debug(
                    2,
                    0,
                    f"--- Unfolding {target_subpath} which was already owned by {stowed.package}",
                )
                self._do_unlink(target_subpath)
                self._do_mkdir(target_subpath)
                # Pushed in reverse: the previously stowed package's
                # contents are scanned before this package's
                jobs.append(
                    StowScanJob(self.stow_path, package, pkg_subpath, target_subpath)
                )
                jobs.append(
                    StowScanJob(
                        stowed.stow_dir, stowed.package, pkg_subpath, target_subpath
                    )
                )
            else:
                self._record_conflict(
                    package,
                    f"existing target is stowed to a different package: {target_subpath} => {existing_link_dest}",
                )
        else:
            # The existing link is invalid, so replace it with a good link
            debug(2, 0, f"--- replacing invalid link: {target_subpath}")
            self._do_unlink(target_subpath)
            self._do_link(link_dest, target_subpath)

    def _stow_node_for_existing_node(
        self,
        package: str,
        pkg_subpath: str,
        target_subpath: str,
        pkg_path_from_cwd: str,
        link_dest: str,
        jobs: list[StowJob],
    ) -> None:
        """Handle stowing when target is an existing node (not a link)."""
        debug(4, 1, f"Evaluate existing node: {target_subpath}")
        if self._is_a_dir(target_subpath):
            if not os.path.isdir(pkg_path_from_cwd):
                self._record_conflict(
                    package,
                    f"cannot stow non-directory {pkg_path_from_cwd} over existing directory target {target_subpath}",
                )
            else:
                jobs.append(
                    StowScanJob(self.stow_path, package, pkg_subpath, target_subpath)
                )
        else:
            # target_subpath is not a current or planned directory
            if self.c.adopt:
                if os.path.isdir(pkg_path_from_cwd):
                    self._record_conflict(
                        package,
                        f"cannot stow directory {pkg_path_from_cwd} over existing non-directory target {target_subpath}",
                    )
                else:
                    self._do_mv(target_subpath, pkg_path_from_cwd)
                    self._do_link(link_dest, target_subpath)
            else:
                self._record_conflict(
                    package,
                    f"cannot stow {pkg_path_from_cwd} over existing target {target_subpath} "
                    f"since neither a link nor a directory and --adopt not specified",
                )

    def unstow_contents(
        self, package: str, pkg_subdir: str, target_subdir: str
    ) -> None:
        """Unstow the contents of the given directory.

        Here we traverse the package tree, rather than the target tree
        (except in compat mode). Like stow_contents(), the descent runs on
        an explicit job stack in exactly the recursive order; the "fold"
        and "cleanup" jobs run after the corresponding subtree completes,
        mirroring the work the recursive formulation does after each
        nested call returns."""
        jobs: list[UnstowJob] = [UnstowScanJob(package, pkg_subdir, target_subdir)]
        while jobs:
            job = jobs.pop()
            if isinstance(job, UnstowScanJob):
                self._unstow_scan_dir(
                    job.package, job.pkg_subdir, job.target_subdir, jobs
                )
            elif isinstance(job, UnstowNodeJob):
                self._unstow_visit_node(
                    job.package, job.pkg_subdir, job.target_subdir, job.node, jobs
                )
            elif isinstance(job, FoldJob):
                self._fold_if_foldable(job.target_subdir)
            else:
                if os.path.isdir(job.target_subdir):
                    self._cleanup_invalid_links(job.target_subdir)

    def _unstow_scan_dir(
        self, package: str, pkg_subdir: str, target_subdir: str, jobs: list[UnstowJob]
    ) -> None:
        """List one directory and queue a visit for each entry."""
        if self._should_skip_target(target_subdir):
            return

        cwd = os.getcwd()
        compat_str = ", compat" if self.c.compat else ""
        msg = f"Unstowing contents of {self.stow_path} / {package} / {pkg_subdir} (cwd={cwd}{compat_str})"

        home = os.environ.get("HOME")
        if home:
            msg = msg.replace(home + "/", "~/")

        debug(3, 0, msg)
        debug(4, 1, f"target subdir is {target_subdir}")

        # Calculate the path to the package directory or sub-directory
        # whose contents need to be unstowed, relative to the current
        # (target directory).
        pkg_path_from_cwd = join_paths(self.stow_path, package, pkg_subdir)

        if self.c.compat:
            # In compat mode we traverse the target tree not the source tree,
            # so we're unstowing the contents of /target/foo, there's no
            # guarantee that the corresponding /stow/mypkg/foo exists.
            if not os.path.isdir(target_subdir):
                raise StowError(
                    f"unstow_contents() in compat mode called with non-directory target: {target_subdir}"
                )
        else:
            # We traverse the package installation image tree not the
            # target tree, so pkg_path_from_cwd must exist.
            if not os.path.isdir(pkg_path_from_cwd):
                raise StowError(
                    f"unstow_contents() called with non-directory path: {pkg_path_from_cwd}"
                )
            # When called at the top level, target_subdir should exist. And
            # unstow_node() should only call this via mutual recursion if
            # target_subdir exists.
            if not self._is_a_node(target_subdir):
                raise StowError(
                    f"unstow_contents() called with invalid target: {target_subdir}"
                )

        dir_to_read = target_subdir if self.c.compat else pkg_path_from_cwd
        try:
            listing = os.listdir(dir_to_read)
        except OSError as e:
            raise StowError(
                f"cannot read directory: {dir_to_read} ({e.strerror})", errno=2
            ) from e

        # Pushed first so it pops last: clean-up runs after all of this
        # directory's entries (and their subtrees) have been processed
        if not self.c.compat:
            jobs.append(CleanupJob(target_subdir))
        # Pushed in reverse so that popping visits entries in sorted order
        for node in sorted(listing, reverse=True):
            jobs.append(UnstowNodeJob(package, pkg_subdir, target_subdir, node))

    def _unstow_visit_node(
        self,
        package: str,
        pkg_subdir: str,
        target_subdir: str,
        node: str,
        jobs: list[UnstowJob],
    ) -> None:
        """Run the per-entry ignore/dotfiles checks, then unstow the node."""
        if node in (".", ".."):
            return

        package_node = node
        target_node = node
        target_node_path = join_paths(target_subdir, target_node)

        if self._should_ignore(self.stow_path, package, target_node_path):
            return

        if self.c.dotfiles:
            if self.c.compat:
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
        self._unstow_node(package, package_node_path, target_node_path, jobs)

    def _unstow_node(
        self, package: str, pkg_subpath: str, target_subpath: str, jobs: list[UnstowJob]
    ) -> None:
        """Unstow the given node, queueing subdirectory scans onto the job stack."""
        debug(3, 0, f"Unstowing entry from target: {target_subpath}")
        debug(4, 1, f"Package entry: {self.stow_path} / {package} / {pkg_subpath}")

        # Does the target exist?
        if self._is_a_link(target_subpath):
            self._unstow_link_node(package, pkg_subpath, target_subpath)
        elif os.path.isdir(target_subpath):
            # The fold check runs only after the subtree scan completes,
            # since unstowing the contents may make the directory foldable
            jobs.append(FoldJob(target_subpath))
            jobs.append(UnstowScanJob(package, pkg_subpath, target_subpath))
        elif os.path.exists(target_subpath):
            debug(2, 1, f"{target_subpath} doesn't need to be unstowed")
        else:
            debug(2, 1, f"{target_subpath} did not exist to be unstowed")

    def _fold_if_foldable(self, target_subdir: str) -> None:
        """Fold the directory if unstowing its contents made that possible."""
        parent_in_pkg = self._foldable(target_subdir)
        if parent_in_pkg:
            self._fold_tree(target_subdir, parent_in_pkg)

    def _unstow_link_node(
        self, package: str, pkg_subpath: str, target_subpath: str
    ) -> None:
        debug(4, 2, f"Evaluate existing link: {target_subpath}")

        # Where is the link pointing?
        link_dest = self._read_a_link(target_subpath)
        if not link_dest:
            raise StowError(f"Could not read link: {target_subpath}")

        if link_dest.startswith("/"):
            print(
                f"Ignoring an absolute symlink: {target_subpath} => {link_dest}",
                file=sys.stderr,
            )
            return

        # Does it point to a node under any stow directory?
        stowed = self._find_stowed_path(target_subpath, link_dest)

        if not stowed:
            # The user is unstowing the package, so they don't want links to it.
            # Therefore we should allow them to have a link pointing elsewhere
            # which would conflict with the package if they were stowing it.
            debug(5, 3, f"Ignoring unowned link {target_subpath} => {link_dest}")
            return

        pkg_path_from_cwd = join_paths(self.stow_path, package, pkg_subpath)

        # Does the existing target_subpath actually point to anything?
        if os.path.exists(stowed.path):
            if stowed.path == pkg_path_from_cwd:
                # It points to the package we're unstowing, so unstow the link.
                self._do_unlink(target_subpath)
            else:
                debug(5, 3, f"Ignoring link {target_subpath} => {link_dest}")
        else:
            debug(
                2,
                0,
                f"--- removing invalid link into a stow directory: {pkg_path_from_cwd}",
            )
            self._do_unlink(target_subpath)

    def _cleanup_invalid_links(self, dir_path: str) -> None:
        """Clean up orphaned links that may block folding."""
        cwd = os.getcwd()
        debug(2, 0, f"Cleaning up any invalid links in {dir_path} (pwd={cwd})")

        if not os.path.isdir(dir_path):
            raise StowInternalError(
                f"cleanup_invalid_links() called with a non-directory: {dir_path}"
            )

        try:
            listing = os.listdir(dir_path)
        except OSError as e:
            raise StowError(
                f"cannot read directory: {dir_path} ({e.strerror})", errno=2
            ) from e

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            node_path = join_paths(dir_path, node)

            if not os.path.islink(node_path):
                continue

            debug(4, 1, f"Checking validity of link {node_path}")

            if node_path in self.link_task_for:
                task = self.link_task_for[node_path]
                if task.action != Action.REMOVE:
                    print(
                        f"Unexpected action {task.action.value} scheduled for {node_path}; skipping clean-up",
                        file=sys.stderr,
                    )
                else:
                    debug(4, 2, f"{node_path} scheduled for removal; skipping clean-up")
                continue

            try:
                link_dest = os.readlink(node_path)
            except OSError as e:
                raise StowError(f"Could not read link {node_path}") from e

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

            owner = self._get_owning_package(node_path, link_dest)
            if owner:
                debug(
                    2,
                    0,
                    f"--- removing link owned by {owner}: {node_path} => {join_paths(dir_path, link_dest)}",
                )
                self._do_unlink(node_path)

    def _foldable(self, target_subdir: str) -> Optional[str]:
        """
        Determine whether a tree can be folded.

        Returns path to the parent dir iff the tree can be safely folded.
        """
        debug(3, 2, f"Is {target_subdir} foldable?")

        if self.c.no_folding:
            debug(3, 3, "Not foldable because --no-folding enabled")
            return None

        try:
            listing = os.listdir(target_subdir)
        except OSError as e:
            raise StowError(f'Cannot read directory "{target_subdir}" ({e})') from e

        parent_in_pkg = None

        for node in sorted(listing):
            if node in (".", ".."):
                continue

            target_node_path = join_paths(target_subdir, node)

            if not self._is_a_node(target_node_path):
                continue

            if not self._is_a_link(target_node_path):
                debug(3, 3, f"Not foldable because {target_node_path} not a link")
                return None

            link_dest = self._read_a_link(target_node_path)
            if not link_dest:
                raise StowError(f"Could not read link {target_node_path}")

            new_parent = parent(link_dest)
            if parent_in_pkg is None:
                parent_in_pkg = new_parent
            elif parent_in_pkg != new_parent:
                debug(
                    3,
                    3,
                    f"Not foldable because {target_subdir} contains links to entries in both {parent_in_pkg} and {new_parent}",
                )
                return None

        if not parent_in_pkg:
            debug(3, 3, f"Not foldable because {target_subdir} contains no links")
            return None

        parent_in_pkg = parent_in_pkg.removeprefix("../")

        if self._get_owning_package(target_subdir, parent_in_pkg):
            debug(3, 3, f"{target_subdir} is foldable")
            return parent_in_pkg
        else:
            debug(3, 3, f"{target_subdir} is not foldable")
            return None

    def _fold_tree(self, target_subdir: str, pkg_subpath: str) -> None:
        """Fold the given tree."""
        debug(3, 0, f"--- Folding tree: {target_subdir} => {pkg_subpath}")

        try:
            listing = os.listdir(target_subdir)
        except OSError as e:
            raise StowError(f'Cannot read directory "{target_subdir}" ({e})') from e

        for node in sorted(listing):
            if node in (".", ".."):
                continue
            node_path = join_paths(target_subdir, node)
            if self._is_a_node(node_path):
                self._do_unlink(node_path)

        self._do_rmdir(target_subdir)
        self._do_link(pkg_subpath, target_subdir)

    def _process_task(self, task: Task) -> None:
        """Process a single task."""
        if isinstance(task, DirTask):
            if task.action == Action.CREATE:
                try:
                    os.mkdir(task.path, 0o777)
                except OSError as e:
                    raise StowError(
                        f"Could not create directory: {task.path} ({e})"
                    ) from e
            else:  # Action.REMOVE
                try:
                    os.rmdir(task.path)
                except OSError as e:
                    raise StowError(
                        f"Could not remove directory: {task.path} ({e})"
                    ) from e

        elif isinstance(task, LinkTask):
            if task.action == Action.CREATE:
                try:
                    os.symlink(task.source, task.path)
                except OSError as e:
                    raise StowError(
                        f"Could not create symlink: {task.path} => {task.source} ({e})"
                    ) from e
            else:  # Action.REMOVE
                try:
                    os.unlink(task.path)
                except OSError as e:
                    raise StowError(f"Could not remove link: {task.path} ({e})") from e

        elif isinstance(task, MoveTask):
            try:
                move(task.path, task.dest)
            except (IOError, OSError) as e:
                raise StowError(
                    f"Could not move {task.path} -> {task.dest} ({e})"
                ) from e

    def _record_conflict(self, package: str, message: str) -> None:
        """Handle conflicts in stow operations."""
        debug(2, 0, f"CONFLICT when stowing {package}: {message}")
        self.conflicts.setdefault(package, []).append(message)

    def _should_ignore(self, stow_path: str, package: str, target: str) -> bool:
        """Determine if the given path matches a regex in our ignore list."""
        if not target:
            raise StowInternalError("Stow.ignore() called with empty target")

        for suffix in self._ignore_pats:
            if suffix.search(target):
                debug(4, 1, f"Ignoring path {target} due to --ignore={suffix.pattern}")
                return True

        package_dir = join_paths(stow_path, package)
        patterns = self._get_ignore_regexps(package_dir)

        if patterns.default_regexp is not None:
            debug(
                5,
                2,
                f"Ignore list regexp for paths:    /{patterns.default_regexp.pattern}/",
            )
        else:
            debug(5, 2, "Ignore list regexp for paths:    none")

        if patterns.local_regexp is not None:
            debug(
                5,
                2,
                f"Ignore list regexp for segments: /{patterns.local_regexp.pattern}/",
            )
        else:
            debug(5, 2, "Ignore list regexp for segments: none")

        if patterns.default_regexp is not None and patterns.default_regexp.search(
            "/" + target
        ):
            debug(4, 1, f"Ignoring path /{target}")
            return True

        basename = os.path.basename(target)
        if patterns.local_regexp is not None and patterns.local_regexp.search(basename):
            debug(4, 1, f"Ignoring path segment {basename}")
            return True

        debug(5, 1, f"Not ignoring {target}")
        return False

    def _get_ignore_regexps(self, dir_path: str) -> IgnorePatterns:
        """Get ignore regexps for the given package directory."""
        local_stow_ignore = join_paths(dir_path, LOCAL_IGNORE_FILE)
        home = os.environ.get("HOME", "")
        global_stow_ignore = join_paths(home, GLOBAL_IGNORE_FILE)

        for file_path in (local_stow_ignore, global_stow_ignore):
            if os.path.exists(file_path):
                debug(5, 1, f"Using ignore file: {file_path}")
                if file_path not in self._ignore_file_cache:
                    self._ignore_file_cache[file_path] = _read_ignore_file(file_path)
                return self._ignore_file_cache[file_path]
            else:
                debug(5, 1, f"{file_path} didn't exist")

        debug(4, 1, "Using built-in ignore list")
        return _get_default_global_ignore_regexps()

    def _should_defer(self, path: str) -> bool:
        """Determine if the given path matches a regex in our defer list."""
        return any(prefix.search(path) for prefix in self._defer_pats)

    def _should_override(self, path: str) -> bool:
        """Determine if the given path matches a regex in our override list."""
        return any(regex.search(path) for regex in self._override_pats)

    def _should_skip_target(self, target: str) -> bool:
        """Determine whether target is a stow directory which should not be altered."""
        if target == self.stow_path:
            print(
                f"WARNING: skipping target which was current stow directory {target}",
                file=sys.stderr,
            )
            return True

        if self._is_marked_stow_dir(target):
            print(f"WARNING: skipping marked Stow directory {target}", file=sys.stderr)
            return True

        if os.path.exists(join_paths(target, ".nonstow")):
            print(f"WARNING: skipping protected directory {target}", file=sys.stderr)
            return True

        debug(4, 1, f"{target} not protected; shouldn't skip")
        return False

    def _is_marked_stow_dir(self, dir_path: str) -> bool:
        """Check if directory contains .stow marker file."""
        if os.path.exists(join_paths(dir_path, ".stow")):
            debug(5, 5, f"> {dir_path} contained .stow")
            return True
        return False

    def _get_owning_package(self, target_subpath: str, link_dest: str) -> Optional[str]:
        """Determine whether the given link points to a member of a stowed package."""
        stowed = self._find_stowed_path(target_subpath, link_dest)
        return stowed.package if stowed else None

    def _find_stowed_path(
        self, target_subpath: str, link_dest: str
    ) -> Optional[StowedPath]:
        """
        Determine whether the given symlink within the target directory
        is a stowed path pointing to a member of a package under the stow dir.

        Returns StowedPath or None if not found.
        """
        if link_dest.startswith("/"):
            return None

        debug(4, 2, f"find_stowed_path(target={target_subpath}; source={link_dest})")
        pkg_path_from_cwd = join_paths(parent(target_subpath), link_dest)
        debug(4, 3, f"is symlink destination {pkg_path_from_cwd} owned by stow?")

        pkg_loc = self._parse_link_dest_as_package_subpath(pkg_path_from_cwd)
        if pkg_loc:
            debug(
                4,
                3,
                f"yes - package {pkg_loc.package} in {self.stow_path} may contain {pkg_loc.subpath}",
            )
            return StowedPath(pkg_path_from_cwd, self.stow_path, pkg_loc.package)

        marked = self._find_containing_marked_stow_dir(pkg_path_from_cwd)
        if marked:
            debug(
                5,
                5,
                f"yes - {marked.stow_dir} in {pkg_path_from_cwd} was marked as a stow dir; package={marked.package}",
            )
            return StowedPath(pkg_path_from_cwd, marked.stow_dir, marked.package)

        return None

    def _parse_link_dest_as_package_subpath(
        self, link_dest: str
    ) -> Optional[PackageSubpath]:
        """Detect whether symlink destination is within current stow dir."""
        debug(4, 4, f"common prefix? link_dest={link_dest}; stow_path={self.stow_path}")

        prefix = self.stow_path + "/"
        if not link_dest.startswith(prefix):
            debug(4, 3, f"no - {link_dest} not under {self.stow_path}")
            return None

        remaining = link_dest.removeprefix(prefix)
        debug(4, 4, f"remaining after removing {self.stow_path}: {remaining}")

        package, _, subpath = remaining.partition("/")
        return PackageSubpath(package, subpath)

    def _find_containing_marked_stow_dir(
        self, pkg_path_from_cwd: str
    ) -> Optional[MarkedStowDir]:
        """Detect whether path is within a marked stow directory."""
        segments = [s for s in pkg_path_from_cwd.split("/") if s]

        for last_segment in range(len(segments)):
            path_so_far = "/".join(segments[: last_segment + 1])
            debug(5, 5, f"is {path_so_far} marked stow dir?")
            if self._is_marked_stow_dir(path_so_far):
                if last_segment == len(segments) - 1:
                    raise StowInternalError(
                        "find_stowed_path() called directly on stow dir"
                    )

                package = segments[last_segment + 1]
                return MarkedStowDir(path_so_far, package)

        return None

    def _get_link_task_action(self, path: str) -> Optional[Action]:
        """Finds the link task action for the given path, if there is one."""
        if path not in self.link_task_for:
            debug(4, 4, f"| link_task_action({path}): no task")
            return None
        action = self.link_task_for[path].action
        debug(
            4, 4, f"| link_task_action({path}): task exists with action {action.value}"
        )
        return action

    def _get_dir_task_action(self, path: str) -> Optional[Action]:
        """Finds the dir task action for the given path, if there is one."""
        if path not in self.dir_task_for:
            debug(4, 4, f"| dir_task_action({path}): no task")
            return None
        action = self.dir_task_for[path].action
        debug(
            4, 4, f"| dir_task_action({path}): task exists with action {action.value}"
        )
        return action

    def _is_parent_link_scheduled_for_removal(self, target_path: str) -> bool:
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
                and self.link_task_for[prefix].action == Action.REMOVE
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

    def _is_a_link(self, target_path: str) -> bool:
        """Determine if the given path is a current or planned link."""
        debug(4, 2, f"is_a_link({target_path})")

        link_action = self._get_link_task_action(target_path)
        if link_action == Action.REMOVE:
            debug(4, 2, f"is_a_link({target_path}): returning 0 (remove action found)")
            return False
        elif link_action == Action.CREATE:
            debug(4, 2, f"is_a_link({target_path}): returning 1 (create action found)")
            return True

        if os.path.islink(target_path):
            debug(4, 2, f"is_a_link({target_path}): is a real link")
            return not self._is_parent_link_scheduled_for_removal(target_path)

        debug(4, 2, f"is_a_link({target_path}): returning 0")
        return False

    def _is_a_dir(self, target_path: str) -> bool:
        """Determine if the given path is a current or planned directory."""
        debug(4, 1, f"is_a_dir({target_path})")

        dir_action = self._get_dir_task_action(target_path)
        if dir_action == Action.REMOVE:
            return False
        elif dir_action == Action.CREATE:
            return True

        if self._is_parent_link_scheduled_for_removal(target_path):
            return False

        if os.path.isdir(target_path):
            debug(4, 1, f"is_a_dir({target_path}): real dir")
            return True

        debug(4, 1, f"is_a_dir({target_path}): returning false")
        return False

    def _is_a_node(self, target_path: str) -> bool:
        """Determine whether the given path is a current or planned node."""
        debug(4, 4, f"| Checking whether {target_path} is a current/planned node")

        laction = self._get_link_task_action(target_path)
        daction = self._get_dir_task_action(target_path)

        # Truth table for link/dir task actions
        if laction == Action.REMOVE and daction == Action.REMOVE:
            raise StowInternalError(f"removing link and dir: {target_path}")
        elif laction == Action.REMOVE and daction == Action.CREATE:
            # Unfolding: link removal happens before dir creation.
            return True
        elif laction == Action.REMOVE and daction is None:
            return False
        elif laction == Action.CREATE and daction == Action.REMOVE:
            # Folding: dir removal happens before link creation.
            return True
        elif laction == Action.CREATE and daction == Action.CREATE:
            raise StowInternalError(f"creating link and dir: {target_path}")
        elif laction == Action.CREATE:
            return True
        elif laction is None and daction == Action.REMOVE:
            return False
        elif laction is None and daction == Action.CREATE:
            return True
        # else: laction is None and daction is None - fall through to filesystem check

        if self._is_parent_link_scheduled_for_removal(target_path):
            return False

        if os.path.exists(target_path):
            debug(4, 3, f"| is_a_node({target_path}): really exists")
            return True

        debug(4, 3, f"| is_a_node({target_path}): returning false")
        return False

    def _read_a_link(self, link: str) -> str:
        """Return the destination of a current or planned link."""
        action = self._get_link_task_action(link)
        if action:
            debug(4, 2, f"read_a_link({link}): task exists with action {action.value}")

            if action == Action.CREATE:
                return self.link_task_for[link].source
            elif action == Action.REMOVE:
                raise StowInternalError(
                    f"read_a_link() passed a path that is scheduled for removal: {link}"
                )

        elif os.path.islink(link):
            debug(4, 2, f"read_a_link({link}): is a real link")
            try:
                return os.readlink(link)
            except OSError as e:
                raise StowError(f"Could not read link: {link} ({e})") from e

        raise StowInternalError(f"read_a_link() passed a non-link path: {link}")

    def _do_link(self, link_dest: str, link_src: str) -> None:
        """Wrap 'link' operation for later processing."""
        if link_src in self.dir_task_for:
            dir_task = self.dir_task_for[link_src]
            if dir_task.action == Action.CREATE:
                raise StowInternalError(
                    f"new link ({link_src} => {link_dest}) clashes with planned new directory"
                )
            # Action.REMOVE is ok - may need to remove a directory before creating a link

        if link_src in self.link_task_for:
            link_task = self.link_task_for[link_src]

            if link_task.action == Action.CREATE:
                if link_task.source != link_dest:
                    raise StowInternalError(
                        f"new link clashes with planned new link: {link_task.path} => {link_task.source}"
                    )
                else:
                    debug(
                        1,
                        0,
                        f"LINK: {link_src} => {link_dest} (duplicates previous action)",
                    )
                    return

            elif link_task.action == Action.REMOVE:
                if link_task.source == link_dest:
                    debug(
                        1,
                        0,
                        f"LINK: {link_src} => {link_dest} (reverts previous action)",
                    )
                    link_task.skipped = True
                    del self.link_task_for[link_src]
                    return

        debug(1, 0, f"LINK: {link_src} => {link_dest}")
        task = LinkTask(
            action=Action.CREATE,
            path=link_src,
            source=link_dest,
        )
        self.tasks.append(task)
        self.link_task_for[link_src] = task

    def _do_unlink(self, file_path: str) -> None:
        """Wrap 'unlink' operation for later processing."""
        if file_path in self.link_task_for:
            link_task = self.link_task_for[file_path]

            if link_task.action == Action.REMOVE:
                debug(1, 0, f"UNLINK: {file_path} (duplicates previous action)")
                return
            elif link_task.action == Action.CREATE:
                debug(1, 0, f"UNLINK: {file_path} (reverts previous action)")
                link_task.skipped = True
                del self.link_task_for[file_path]
                return

        if (
            file_path in self.dir_task_for
            and self.dir_task_for[file_path].action == Action.CREATE
        ):
            raise StowInternalError(
                f"new unlink operation clashes with planned operation: {self.dir_task_for[file_path].action.value} dir {file_path}"
            )

        debug(1, 0, f"UNLINK: {file_path}")

        try:
            source = os.readlink(file_path)
        except OSError as e:
            raise StowError(f"could not readlink {file_path} ({e})") from e

        task = LinkTask(
            action=Action.REMOVE,
            path=file_path,
            source=source,
        )
        self.tasks.append(task)
        self.link_task_for[file_path] = task

    def _do_mkdir(self, dir_path: str) -> None:
        """Wrap 'mkdir' operation."""
        if dir_path in self.link_task_for:
            link_task = self.link_task_for[dir_path]
            if link_task.action == Action.CREATE:
                raise StowInternalError(
                    f"new dir clashes with planned new link ({link_task.path} => {link_task.source})"
                )
            # Action.REMOVE is ok - may need to remove a link before creating a directory

        if dir_path in self.dir_task_for:
            dir_task = self.dir_task_for[dir_path]

            if dir_task.action == Action.CREATE:
                debug(1, 0, f"MKDIR: {dir_path} (duplicates previous action)")
                return
            elif dir_task.action == Action.REMOVE:
                debug(1, 0, f"MKDIR: {dir_path} (reverts previous action)")
                dir_task.skipped = True
                del self.dir_task_for[dir_path]
                return

        debug(1, 0, f"MKDIR: {dir_path}")
        task = DirTask(
            action=Action.CREATE,
            path=dir_path,
        )
        self.tasks.append(task)
        self.dir_task_for[dir_path] = task

    def _do_rmdir(self, dir_path: str) -> None:
        """Wrap 'rmdir' operation."""
        if dir_path in self.link_task_for:
            link_task = self.link_task_for[dir_path]
            raise StowInternalError(
                f"rmdir clashes with planned operation: {link_task.action.value} link {link_task.path} => {link_task.source}"
            )

        if dir_path in self.dir_task_for:
            dir_task = self.dir_task_for[dir_path]

            if dir_task.action == Action.REMOVE:
                debug(1, 0, f"RMDIR {dir_path} (duplicates previous action)")
                return
            elif dir_task.action == Action.CREATE:
                debug(1, 0, f"MKDIR {dir_path} (reverts previous action)")
                dir_task.skipped = True
                del self.dir_task_for[dir_path]
                return

        debug(1, 0, f"RMDIR {dir_path}")
        task = DirTask(
            action=Action.REMOVE,
            path=dir_path,
        )
        self.tasks.append(task)
        self.dir_task_for[dir_path] = task

    def _do_mv(self, src: str, dst: str) -> None:
        """Wrap 'move' operation for later processing."""
        if src in self.link_task_for:
            link_task = self.link_task_for[src]
            raise StowInternalError(
                f"do_mv: pre-existing link task for {src}; action: {link_task.action.value}, source: {link_task.source}"
            )
        elif src in self.dir_task_for:
            dir_task = self.dir_task_for[src]
            raise StowInternalError(
                f"do_mv: pre-existing dir task for {src}?! action: {dir_task.action.value}"
            )

        debug(1, 0, f"MV: {src} -> {dst}")

        task = MoveTask(
            path=src,
            dest=dst,
        )
        self.tasks.append(task)


# =============================================================================
# Module-level helper functions
# =============================================================================


def _read_ignore_file(file_path: str) -> IgnorePatterns:
    """Read and parse ignore file, returning compiled regexps.

    Caching lives in _Stower._ignore_file_cache, per stower instance:
    file_path is relative to the target directory, so a cross-instance
    cache could hand one tree's patterns to an operation on another."""
    try:
        with open(file_path, "r") as f:
            patterns: set[str] = set()
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                line = re.sub(r"\s+#.+", "", line)
                line = line.replace("\\#", "#")
                patterns.add(line)

            # Always ignore the local ignore file itself
            patterns.add("^/" + re.escape(LOCAL_IGNORE_FILE) + "$")
            return _compile_ignore_patterns(patterns)
    except IOError:
        return IgnorePatterns(None, None)


def _compile_ignore_patterns(patterns: set[str]) -> IgnorePatterns:
    """Compile ignore patterns into path and segment regexps."""
    segment_patterns = [p for p in patterns if "/" not in p]
    path_patterns = [p for p in patterns if "/" in p]

    segment_regexp = None
    path_regexp = None

    try:
        if segment_patterns:
            combined = "|".join(segment_patterns)
            segment_regexp = re.compile(f"^({combined})$")

        if path_patterns:
            combined = "|".join(path_patterns)
            path_regexp = re.compile(f"(^|/)({combined})(/|$)")
    except re.error as e:
        # StowError produces a clean "stow: ERROR: ..." message instead of
        # a traceback when an ignore file contains a malformed pattern
        raise StowError(f"Failed to compile regexp: {e}")

    return IgnorePatterns(path_regexp, segment_regexp)


@functools.lru_cache(maxsize=1)
def _get_default_global_ignore_regexps() -> IgnorePatterns:
    """Get default global ignore regexps (cached)."""
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
    patterns: set[str] = set()
    for line in default_patterns.strip().split("\n"):
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        line = re.sub(r"\s+#.+", "", line)
        line = line.replace("\\#", "#")
        patterns.add(line)

    patterns.add("^/" + re.escape(LOCAL_IGNORE_FILE) + "$")
    return _compile_ignore_patterns(patterns)
