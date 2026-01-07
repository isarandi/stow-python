"""
Hypothesis-based oracle tests for stow and chkstow.

Uses property-based testing to generate random scenarios and verify
Python and Perl implementations produce identical results.
"""

from __future__ import print_function

import os
import tempfile

from hypothesis import given, settings, assume, strategies as st

from conftest import StowTestEnv, assert_stow_match, assert_stow_match_with_fs_ops, assert_chkstow_match


def try_create_packages(env, packages):
    """Try to create packages, return False if filesystem conflicts occur."""
    try:
        for pkg_name, files in packages.items():
            env.create_package(pkg_name, files)
        return True
    except (OSError, IOError):
        return False


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for package names
# Exclude: empty, null, slash, and names starting with - or + (confused with CLI options)
# See docs/perl-differences.md for details on option parsing differences
name_st = st.text(
    min_size=1,
    max_size=12,
).filter(lambda x: "\0" not in x and "/" not in x and not x.startswith("-") and not x.startswith("+"))

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

    for i in range(num_files):
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
# Chkstow hypothesis tests
# =============================================================================


class TestChkstowHypothesis:
    """Hypothesis-based tests for chkstow."""

    @settings(max_examples=50)
    @given(packages=package_set_st(max_packages=4))
    def test_list_packages_random(self, packages):
        """List packages matches for random package structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            assert_chkstow_match(env, ["-l", "-t", env.target_dir])

    @settings(max_examples=50)
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

    @settings(max_examples=50)
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

    @settings(max_examples=30)
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

    @settings(max_examples=50)
    @given(packages=package_set_st(max_packages=3))
    def test_stow_random_packages(self, packages):
        """Stow random package structures with strace comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            assert_stow_match_with_fs_ops(env, ["-t", env.target_dir] + pkg_names)

    @settings(max_examples=50)
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
            assert_stow_match_with_fs_ops(
                env, ["-t", env.target_dir, "-D"] + pkg_names, setup
            )

    @settings(max_examples=50)
    @given(packages=package_set_st(max_packages=3))
    def test_restow_random_packages(self, packages):
        """Restow random package structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())

            # First stow
            env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            # Then test restow
            assert_stow_match(env, ["-t", env.target_dir, "-R"] + pkg_names)

    @settings(max_examples=30)
    @given(files=file_tree_st(max_depth=3, max_files=8))
    def test_stow_no_folding_random(self, files):
        """Stow with --no-folding creates individual links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("pkg", files)

            assert_stow_match(env, ["-t", env.target_dir, "--no-folding", "pkg"])

    @settings(max_examples=30)
    @given(
        pkg1_files=file_tree_st(max_depth=2, max_files=4),
        pkg2_files=file_tree_st(max_depth=2, max_files=4),
    )
    def test_tree_unfolding_random(self, pkg1_files, pkg2_files):
        """Stowing second package triggers tree unfolding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("pkg1", pkg1_files)
            env.create_package("pkg2", pkg2_files)

            # Stow first package
            env.run_perl_stow(["-t", env.target_dir, "pkg1"])

            # Stow second - may trigger unfolding
            assert_stow_match(env, ["-t", env.target_dir, "pkg2"])


class TestStowDotfilesHypothesis:
    """Hypothesis-based tests for dotfiles mode."""

    @settings(max_examples=30)
    @given(files=dotfiles_tree_st(max_files=5))
    def test_dotfiles_stow_random(self, files):
        """Stow with --dotfiles converts dot-X to .X."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("dotpkg", files)

            assert_stow_match(env, ["-t", env.target_dir, "--dotfiles", "dotpkg"])

    @settings(max_examples=30)
    @given(files=dotfiles_tree_st(max_files=5))
    def test_dotfiles_unstow_random(self, files):
        """Unstow with --dotfiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("dotpkg", files)

            # First stow
            env.run_perl_stow(["-t", env.target_dir, "--dotfiles", "dotpkg"])

            # Then unstow
            assert_stow_match(env, ["-t", env.target_dir, "--dotfiles", "-D", "dotpkg"])


class TestStowConflictsHypothesis:
    """Hypothesis-based tests for conflict scenarios."""

    @settings(max_examples=30)
    @given(
        pkg_files=file_tree_st(max_depth=2, max_files=5),
        conflict_idx=st.integers(min_value=0, max_value=4),
    )
    def test_conflict_existing_file_random(self, pkg_files, conflict_idx):
        """Conflict when target file already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("pkg", pkg_files)

            # Create a conflicting file at one of the package paths
            paths = list(pkg_files.keys())
            if paths:
                conflict_path = paths[conflict_idx % len(paths)]
                env.create_target_file(conflict_path, "existing content")

            assert_stow_match(env, ["-t", env.target_dir, "pkg"])

    @settings(max_examples=30)
    @given(
        pkg_files=file_tree_st(max_depth=2, max_files=5),
        conflict_idx=st.integers(min_value=0, max_value=4),
    )
    def test_adopt_existing_file_random(self, pkg_files, conflict_idx):
        """Adopt existing files into the package with strace comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            env.create_package("pkg", pkg_files)

            # Create a conflicting file at one of the package paths
            paths = list(pkg_files.keys())

            def setup():
                if paths:
                    conflict_path = paths[conflict_idx % len(paths)]
                    env.create_target_file(conflict_path, "to be adopted")

            assert_stow_match_with_fs_ops(
                env, ["-t", env.target_dir, "--adopt", "pkg"], setup
            )


class TestStowVerboseHypothesis:
    """Hypothesis-based tests for verbose output."""

    @settings(max_examples=20)
    @given(
        packages=package_set_st(max_packages=2),
        verbose_level=st.integers(min_value=1, max_value=3),
    )
    def test_verbose_random(self, packages, verbose_level):
        """Verbose output matches at various levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))

            pkg_names = list(packages.keys())
            # Use --verbose=N to avoid ambiguity with numeric package names
            # (Perl's -v can consume following number as its argument)
            assert_stow_match(
                env, ["-t", env.target_dir, f"--verbose={verbose_level}"] + pkg_names
            )
