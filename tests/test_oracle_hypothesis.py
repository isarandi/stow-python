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
Hypothesis-based oracle tests for stow and chkstow.

Uses property-based testing to generate random scenarios and verify
Python and Perl implementations produce identical results.
"""

import os
import sys
import tempfile
from collections import Counter

from hypothesis import (
    currently_in_test_context,
    event,
    given,
    settings,
    assume,
    strategies as st,
    HealthCheck,
)

from conftest import (
    StowTestEnv,
    assert_stow_match,
    assert_stow_match_with_fs_ops,
    assert_chkstow_match,
    normalize_getopt_long_wording,
    normalize_newline_warnings,
    normalize_stow_output,
)

# Oracle tests spawn subprocesses (Perl + Python), so disable per-example deadline
# to avoid flaky failures on slower systems
_SUPPRESSED_HEALTH_CHECKS = [HealthCheck.too_slow]

# macOS refuses filenames that Linux accepts: its filesystems reject
# unassigned and ill-formed Unicode, so a share of the generated examples
# cannot exist there and is assumed away by try_create_packages() in the
# test bodies. Only that platform needs the filter health check relaxed;
# on Linux it stays armed, so genuine over-filtering still fails the suite.
if sys.platform == "darwin":
    _SUPPRESSED_HEALTH_CHECKS.append(HealthCheck.filter_too_much)

ORACLE_SETTINGS = dict(deadline=None, suppress_health_check=_SUPPRESSED_HEALTH_CHECKS)


def try_create_packages(env, packages):
    """Try to create packages, return False if filesystem conflicts occur."""
    try:
        for pkg_name, files in packages.items():
            env.create_package(pkg_name, files)
        return True
    except OSError:
        return False


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for package names
# Exclude: empty, null, slash, and names starting with - or + (confused with CLI options)
# Also exclude ".stowrc": the runs use the stow dir as their working
# directory, so a package of that name makes ./.stowrc a DIRECTORY, which
# is documented divergence #20 (Perl's open() of a directory succeeds and
# fails at close with exit 21; ours fails up front with exit 1). That
# divergence is pinned by test_stowrc_is_a_directory in
# tests/test_divergence_pinning_both.py, so generating it here would only
# rediscover it at random.
# A package named "0" and path components starting with ".." ARE drawn:
# they trigger documented divergences #25 and #29, whose expected shape the
# comparison itself recognizes (see _matches_documented_divergence below).
# See docs/perl-differences.md for details on option parsing differences
name_st = st.text(
    min_size=1,
    max_size=12,
).filter(
    lambda x: "\0" not in x
    and "/" not in x
    and not x.startswith("-")
    and not x.startswith("+")
    and x != ".stowrc"
)

# Strategy for file content
content_st = st.text(max_size=100)

# Strategy for relative path components (must be non-empty for valid paths)
# Exclude:
#   - null, slash: invalid in filenames
#   - "." and "..": special directory entries
#   - names ending with ~: ignored by default patterns, and Perl has a bug
#     where ignore check fails for paths containing newlines (see docs/perl-differences.md)
path_component_st = st.text(
    min_size=1,
    max_size=8,
).filter(
    lambda x: "\0" not in x
    and "/" not in x
    and x not in (".", "..")
    and not x.endswith("~")
)


@st.composite
def file_tree_st(draw, max_depth=3, max_files=10):
    """Generate a random file tree as {path: content} dict.

    Ensures no path conflicts (e.g., 'a' as file and 'a/b' as file).
    """
    num_files = draw(st.integers(min_value=1, max_value=max_files))
    files = {}
    used_dirs = set()  # Track directories to avoid file/dir conflicts

    for _ in range(num_files):
        depth = draw(st.integers(min_value=1, max_value=max_depth))
        components = draw(
            st.lists(path_component_st, min_size=depth, max_size=depth, unique=True)
        )
        if components:
            # One path in twenty gains a ".."-prefixed leading component,
            # the documented-divergence #29 trigger, for the same reason
            if draw(st.integers(min_value=0, max_value=19)) == 0:
                components[0] = ".." + components[0]
            path = "/".join(components)

            # Skip if this path is already a directory prefix
            if path in used_dirs:
                continue

            # Skip if any prefix of this path is already a file
            prefixes = ["/".join(components[:i]) for i in range(1, len(components))]
            if any(p in files for p in prefixes):
                continue

            # Mark all prefixes as directories
            used_dirs.update(prefixes)

            content = draw(content_st)
            files[path] = content

    return files if files else {"file": "content"}


@st.composite
def package_set_st(draw, max_packages=4):
    """Generate a set of packages with random file trees.

    Each package is tested independently to avoid conflicts between package names
    and file paths across packages.
    """
    num_packages = draw(st.integers(min_value=1, max_value=max_packages))
    names = draw(
        st.lists(name_st, min_size=num_packages, max_size=num_packages, unique=True)
    )
    # One draw in ten swaps a name for "0", the documented-divergence #25
    # trigger, so the divergence classifier is exercised routinely rather
    # than only when random text happens to produce that exact string.
    if draw(st.integers(min_value=0, max_value=9)) == 0 and "0" not in names:
        names[-1] = "0"
    packages = {}
    for name in names:
        packages[name] = draw(file_tree_st(max_depth=2, max_files=5))
    return packages


@st.composite
def single_package_st(draw):
    """Generate a single package with name and file tree."""
    name = draw(name_st)
    files = draw(file_tree_st(max_depth=2, max_files=5))
    return {name: files}


@st.composite
def dotfiles_tree_st(draw, max_files=5):
    """Generate a file tree with dot- prefixed names.

    Ensures no path conflicts (e.g., 'a' as file and 'a/b' as file).
    """
    num_files = draw(st.integers(min_value=1, max_value=max_files))
    files = {}
    used_dirs = set()

    for _ in range(num_files):
        # Mix of dot- prefixed and regular names
        if draw(st.booleans()):
            name = "dot-" + draw(path_component_st)
        else:
            name = draw(path_component_st)

        # Optionally add subdirectory
        if draw(st.booleans()):
            subdir = draw(path_component_st)
            path = f"{name}/{subdir}"
            # Check for conflicts
            if name in files:
                continue
            used_dirs.add(name)
        else:
            path = name
            # Check for conflicts
            if path in used_dirs:
                continue

        files[path] = draw(content_st)

    return files if files else {"dot-file": "content"}


# =============================================================================
# Documented-divergence recognition
# =============================================================================
#
# The random inputs may contain triggers of documented divergences: a package
# named "0" (perl-differences.md #25, Perl's string-"0" falsiness) or a path
# component starting with ".." (#29, Perl's join_paths collapse regexp). Those
# inputs are deliberately still generated - excluding them would also exclude
# their interactions with every other feature - and a resulting mismatch is
# accepted only when it matches the pinned signature of the documented
# divergence. Anything else stays a failure: this exploration exists to find
# UNdocumented differences.


def _note_accepted(label):
    """Record an accepted divergence for hypothesis statistics when inside a
    test; the classifier also runs standalone (e.g. from a repro script)."""
    if currently_in_test_context():
        event("accepted " + label)


def _dot_adjusted(component):
    """The target-side spelling of a component under --dotfiles."""
    if (
        component.startswith("dot-")
        and len(component) > 4
        and not component[4:].startswith(".")
    ):
        return "." + component[4:]
    return component


def _divergence_triggers(packages):
    """Which documented-divergence triggers the drawn input contains."""
    has_zero_package = "0" in packages
    has_dotdot_component = False
    for files in packages.values():
        for path in files:
            for component in path.split("/"):
                for spelling in (component, _dot_adjusted(component)):
                    if spelling.startswith(".."):
                        has_dotdot_component = True
    return has_zero_package, has_dotdot_component


def _has_dotdot_component(path):
    return any(c.startswith("..") for c in path.split("/"))


def _capture_side(env, args, setup_func, runner):
    """One implementation's run: (rc, stdout, stderr, pre_state, post_state)."""
    env.reset_target()
    if setup_func:
        setup_func()
    pre_state = env.get_filesystem_state()
    rc, out, err = runner(args)
    return rc, out, err, pre_state, env.get_filesystem_state()


_NOT_OWNED_MSG = "existing target is not owned by stow: "
_DIFF_PKG_MSG = "existing target is stowed to a different package: "


def _parse_conflict_warnings(err):
    """Parse conflict stderr into (header, message multiset) blocks.

    Returns None when err has any other structure. A message can span
    lines (drawn names may contain newlines), so messages are cut on the
    "\\n  * " delimiter rather than parsed line by line.
    """
    prefix = "WARNING! "
    suffix = "All operations aborted.\n"
    if not err.startswith(prefix) or not err.endswith(suffix):
        return None
    chunks = err[len(prefix) : -len(suffix)].split("\nWARNING! ")
    blocks = []
    for i, chunk in enumerate(chunks):
        if i < len(chunks) - 1:
            chunk += "\n"  # restore the newline the split consumed
        header, sep, body = chunk.partition(" would cause conflicts:\n")
        if not sep or not body.startswith("  * ") or not body.endswith("\n"):
            return None
        blocks.append((header, Counter(body[4:-1].split("\n  * "))))
    return blocks


def _matches_documented_divergence(env, args, setup_func, packages):
    """Re-run both sides and test the mismatch against the documented shapes.

    Accepted shapes, each requiring its trigger in the drawn input:

    - #25 leftover: identical exit status and streams; entries existing only
      on the Perl side, each an (emptied) directory or a link into package
      "0" - Perl cannot recognize that package as an owner, so it skips the
      unlink/fold/cleanup work we perform.
    - #29 leftover: as above, with every Perl-only entry under a
      ..-prefixed component - Perl cannot recognize its own links there.
    - conflict-abort (#25 or #29): Perl reports its own links as "existing
      target is not owned by stow" and aborts ALL operations (its tree is
      byte-identical to the pre-command state) with exit 1, while we
      proceed with exit 0. Every conflict bullet must name a path whose
      pre-command state implicates the trigger: a link into package "0",
      or a path with a ..-prefixed component.
    - conflict-degradation (#25 or #29): both sides abort with exit 1 and
      unchanged trees, but where we name the owning package ("existing
      target is stowed to a different package: Q => D"), Perl reports
      "existing target is not owned by stow: P" - the same recognition
      failure surfacing in the conflict wording. Q must equal P or descend
      from it: Perl stops at the folded dir it cannot recognize while we
      descend and report the files within, so one Perl message can cover
      several of ours, and a Perl path we handled cleanly may have no
      counterpart (then it must implicate the trigger on its own, like a
      conflict-abort bullet). Every degradation must implicate its
      trigger: P with a ..-prefixed component, or D inside package "0".
      Both sides sort each warning's messages lexicographically (bin/stow
      does `sort @{ $conflicts{...} }`), so the wording change also
      reorders them; messages are therefore compared per warning block as
      multisets. A message can span lines when a drawn name contains a
      newline, so conflict stderr is parsed on message delimiters, not
      line by line (_parse_conflict_warnings).
    """
    has_zero, has_dotdot = _divergence_triggers(packages)
    if not (has_zero or has_dotdot):
        return False

    prc, pout, perr, ppre, ppost = _capture_side(
        env, args, setup_func, env.run_perl_stow
    )
    yrc, yout, yerr, ypre, ypost = _capture_side(
        env, args, setup_func, env.run_python_stow
    )
    yout = normalize_stow_output(yout)
    yerr = normalize_stow_output(yerr)
    perr = normalize_getopt_long_wording(normalize_newline_warnings(perr))
    yerr = normalize_getopt_long_wording(normalize_newline_warnings(yerr))

    only_perl = {k: v for k, v in ppost.items() if k not in ypost}
    only_py = {k for k in ypost if k not in ppost}
    differing = {k for k in ppost.keys() & ypost.keys() if ppost[k] != ypost[k]}

    def is_package_zero_artifact(entry):
        if entry[0] == "dir":
            return True
        return entry[0] == "link" and "0" in entry[1].split("/")

    # Leftover shapes: streams and exit status agree, Perl merely kept more.
    if (
        (prc, pout, perr) == (yrc, yout, yerr)
        and only_perl
        and not only_py
        and not differing
    ):
        if has_zero and all(is_package_zero_artifact(v) for v in only_perl.values()):
            _note_accepted("documented divergence #25 (leftover)")
            return True
        if has_dotdot and all(_has_dotdot_component(k) for k in only_perl):
            _note_accepted("documented divergence #29 (leftover)")
            return True

    def bullet_implicates_trigger(path):
        if has_dotdot and _has_dotdot_component(path):
            return True
        if has_zero:
            entry = ppre.get(os.path.join("target", path))
            return (
                entry is not None and entry[0] == "link" and "0" in entry[1].split("/")
            )
        return False

    # Conflict-abort shape: Perl plans, sees the un-ownable link, aborts all.
    if prc == 1 and yrc == 0 and pout == yout == "" and yerr == "" and ppost == ppre:
        pblocks = _parse_conflict_warnings(perr)

        if pblocks is not None:
            messages = [m for _h, msgs in pblocks for m in msgs.elements()]
            paths = [
                m[len(_NOT_OWNED_MSG) :]
                for m in messages
                if m.startswith(_NOT_OWNED_MSG)
            ]
            if (
                paths
                and len(paths) == len(messages)
                and all(bullet_implicates_trigger(p) for p in paths)
            ):
                _note_accepted("documented divergence #25/#29 (conflict abort)")
                return True

    # Conflict-degradation shape: both sides abort, but where we name the
    # owning package, Perl reports its unrecognizable link as unowned.
    if (
        prc == 1
        and yrc == 1
        and pout == yout
        and ppost == ppre
        and ypost == ypre
        and ppre == ypre
    ):

        def degradation_anchor(body, ppaths):
            """The Perl not-owned path that "Q => D" in `body` extends.

            Q may contain " => " itself, so every split point is tried; a
            candidate anchors when Q equals a Perl path P or descends from
            it (Perl reports the unrecognizable folded dir, we report the
            files within), and P or D implicates a trigger.
            """
            i = body.find(" => ")
            while i >= 0:
                q, dest = body[:i], body[i + 4 :]
                for p in ppaths:
                    if (q == p or q.startswith(p + "/")) and (
                        (has_dotdot and _has_dotdot_component(p))
                        or (has_zero and "0" in dest.split("/"))
                    ):
                        return p
                i = body.find(" => ", i + 1)
            return None

        def count_degraded():
            """Degraded-message count, or -1 if any block fails to match."""
            pblocks = _parse_conflict_warnings(perr)
            yblocks = _parse_conflict_warnings(yerr)
            if pblocks is None or yblocks is None or len(pblocks) != len(yblocks):
                return -1
            degraded = 0
            for (phead, pmsgs), (yhead, ymsgs) in zip(pblocks, yblocks):
                if phead != yhead:
                    return -1
                common = pmsgs & ymsgs
                ppaths = []
                for pmsg in (pmsgs - common).elements():
                    if not pmsg.startswith(_NOT_OWNED_MSG):
                        return -1
                    ppaths.append(pmsg[len(_NOT_OWNED_MSG) :])
                anchored = set()
                for ymsg in (ymsgs - common).elements():
                    if not ymsg.startswith(_DIFF_PKG_MSG):
                        return -1
                    hit = degradation_anchor(ymsg[len(_DIFF_PKG_MSG) :], ppaths)
                    if hit is None:
                        return -1
                    anchored.add(hit)
                    degraded += 1
                # A Perl path may have no counterpart of ours at all (we
                # handled that subtree cleanly); it must then implicate the
                # trigger on its own, like the conflict-abort bullets.
                for path in ppaths:
                    if path not in anchored:
                        if not bullet_implicates_trigger(path):
                            return -1
                        degraded += 1
            return degraded

        if count_degraded() > 0:
            _note_accepted("documented divergence #25/#29 (conflict degradation)")
            return True

    return False


def assert_match_or_documented(
    env, args, packages, setup_func=None, matcher=assert_stow_match
):
    """assert_stow_match, accepting only documented-divergence mismatches."""
    try:
        matcher(env, args, setup_func)
    except AssertionError:
        if not _matches_documented_divergence(env, args, setup_func, packages):
            raise


# =============================================================================
# Chkstow hypothesis tests
# =============================================================================


class TestChkstowHypothesis:
    """Hypothesis-based tests for chkstow."""

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(packages=package_set_st(max_packages=4))
    def test_list_packages_random(self, packages):
        """List packages matches for random package structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            assert_chkstow_match(env, ["-l", "-t", env.target_dir])

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(
        num_broken=st.integers(min_value=1, max_value=5),
        num_valid=st.integers(min_value=0, max_value=3),
    )
    def test_bad_links_random(self, num_broken, num_valid):
        """Detect broken symlinks in random configurations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_target_dir("bin")

            # Create some valid symlinks via stowing
            if num_valid > 0:
                files = {f"bin/valid{i}": f"content{i}" for i in range(num_valid)}
                env.create_package("validpkg", files)
                env.run_perl_stow(["-t", env.target_dir, "validpkg"])

            # Create broken symlinks
            for i in range(num_broken):
                os.symlink(
                    f"nonexistent{i}",
                    os.path.join(env.target_dir, "bin", f"broken{i}"),
                )

            assert_chkstow_match(env, ["-b", "-t", env.target_dir])

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(
        num_aliens=st.integers(min_value=1, max_value=5),
        num_symlinks=st.integers(min_value=0, max_value=3),
    )
    def test_aliens_random(self, num_aliens, num_symlinks):
        """Detect alien files in random configurations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)

            # Create some symlinks via stowing
            if num_symlinks > 0:
                files = {f"bin/prog{i}": f"content{i}" for i in range(num_symlinks)}
                env.create_package("pkg", files)
                env.run_perl_stow(["-t", env.target_dir, "pkg"])

            # Create alien files
            for i in range(num_aliens):
                env.create_target_file(f"bin/alien{i}", f"alien content {i}")

            assert_chkstow_match(env, ["-a", "-t", env.target_dir])

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(
        packages=package_set_st(max_packages=3),
        has_stow_marker=st.booleans(),
        has_notstowed_marker=st.booleans(),
    )
    def test_skip_markers_random(self, packages, has_stow_marker, has_notstowed_marker):
        """Skip directories with .stow or .notstowed markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            # Add marker directories
            if has_stow_marker:
                env.create_target_dir("otherstow")
                env.create_target_file("otherstow/.stow", "")

            if has_notstowed_marker:
                env.create_target_dir("protected")
                env.create_target_file("protected/.notstowed", "")
                env.create_target_file("protected/alien", "should be skipped")

            assert_chkstow_match(env, ["-l", "-t", env.target_dir])


# =============================================================================
# Stow hypothesis tests
# =============================================================================


class TestStowHypothesis:
    """Hypothesis-based tests for stow."""

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(packages=package_set_st(max_packages=3))
    def test_stow_random_packages(self, packages):
        """Stow random package structures with strace comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            assert_match_or_documented(
                env,
                ["-t", env.target_dir] + pkg_names,
                packages,
                matcher=assert_stow_match_with_fs_ops,
            )

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(packages=package_set_st(max_packages=3))
    def test_unstow_random_packages(self, packages):
        """Unstow random package structures with strace comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())

            def setup():
                env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            # Test unstow with strace comparison
            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "-D"] + pkg_names,
                packages,
                setup,
                matcher=assert_stow_match_with_fs_ops,
            )

    @settings(max_examples=50, **ORACLE_SETTINGS)
    @given(packages=package_set_st(max_packages=3))
    def test_restow_random_packages(self, packages):
        """Restow random package structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())

            def setup():
                # First stow
                env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            # Then test restow
            assert_match_or_documented(
                env, ["-t", env.target_dir, "-R"] + pkg_names, packages, setup
            )

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(files=file_tree_st(max_depth=3, max_files=8))
    def test_stow_no_folding_random(self, files):
        """Stow with --no-folding creates individual links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"pkg": files}))

            assert_match_or_documented(
                env, ["-t", env.target_dir, "--no-folding", "pkg"], {"pkg": files}
            )

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(
        pkg1_files=file_tree_st(max_depth=2, max_files=4),
        pkg2_files=file_tree_st(max_depth=2, max_files=4),
    )
    def test_tree_unfolding_random(self, pkg1_files, pkg2_files):
        """Stowing second package triggers tree unfolding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"pkg1": pkg1_files, "pkg2": pkg2_files}))

            def setup():
                # Stow first package
                env.run_perl_stow(["-t", env.target_dir, "pkg1"])

            # Stow second - may trigger unfolding
            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "pkg2"],
                {"pkg1": pkg1_files, "pkg2": pkg2_files},
                setup,
            )


class TestStowDotfilesHypothesis:
    """Hypothesis-based tests for dotfiles mode."""

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(files=dotfiles_tree_st(max_files=5))
    def test_dotfiles_stow_random(self, files):
        """Stow with --dotfiles converts dot-X to .X."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"dotpkg": files}))

            assert_match_or_documented(
                env, ["-t", env.target_dir, "--dotfiles", "dotpkg"], {"dotpkg": files}
            )

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(files=dotfiles_tree_st(max_files=5))
    def test_dotfiles_unstow_random(self, files):
        """Unstow with --dotfiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"dotpkg": files}))

            def setup():
                # First stow
                env.run_perl_stow(["-t", env.target_dir, "--dotfiles", "dotpkg"])

            # Then unstow
            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "--dotfiles", "-D", "dotpkg"],
                {"dotpkg": files},
                setup,
            )


class TestStowConflictsHypothesis:
    """Hypothesis-based tests for conflict scenarios."""

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(
        pkg_files=file_tree_st(max_depth=2, max_files=5),
        conflict_idx=st.integers(min_value=0, max_value=4),
    )
    def test_conflict_existing_file_random(self, pkg_files, conflict_idx):
        """Conflict when target file already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"pkg": pkg_files}))

            # Create a conflicting file at one of the package paths
            paths = list(pkg_files.keys())
            if paths:
                conflict_path = paths[conflict_idx % len(paths)]
                env.create_target_file(conflict_path, "existing content")

            assert_match_or_documented(
                env, ["-t", env.target_dir, "pkg"], {"pkg": pkg_files}
            )

    @settings(max_examples=30, **ORACLE_SETTINGS)
    @given(
        pkg_files=file_tree_st(max_depth=2, max_files=5),
        conflict_idx=st.integers(min_value=0, max_value=4),
    )
    def test_adopt_existing_file_random(self, pkg_files, conflict_idx):
        """Adopt existing files into the package with strace comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            # Confirm up front that the generated names are representable on
            # this filesystem; setup() recreates the package for each run
            assume(try_create_packages(env, {"pkg": pkg_files}))

            # Create a conflicting file at one of the package paths
            paths = list(pkg_files.keys())

            def setup():
                # Recreate the package per run: --adopt mutates it (moves
                # the target file into it), and the Perl run's mutation
                # must not become the Python run's starting state.
                env.create_package("pkg", pkg_files)
                if paths:
                    conflict_path = paths[conflict_idx % len(paths)]
                    env.create_target_file(conflict_path, "to be adopted")

            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "--adopt", "pkg"],
                {"pkg": pkg_files},
                setup,
                matcher=assert_stow_match_with_fs_ops,
            )


class TestStowVerboseHypothesis:
    """Hypothesis-based tests for verbose output."""

    @settings(max_examples=20, **ORACLE_SETTINGS)
    @given(
        packages=package_set_st(max_packages=2),
        verbose_level=st.integers(min_value=1, max_value=3),
    )
    def test_verbose_random(self, packages, verbose_level):
        """Verbose output matches at various levels."""
        # Divergences #25 and #29 alter the verbose trace itself (ownership
        # and folding decisions are narrated differently), which has no
        # tight signature to classify - so this one property assumes the
        # triggers away; the non-verbose properties draw them freely.
        has_zero, has_dotdot = _divergence_triggers(packages)
        assume(not has_zero and not has_dotdot)
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            # Use --verbose=N to avoid ambiguity with numeric package names
            # (Perl's -v can consume following number as its argument)
            assert_stow_match(
                env, ["-t", env.target_dir, f"--verbose={verbose_level}"] + pkg_names
            )
