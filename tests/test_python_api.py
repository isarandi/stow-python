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
Tests for the public Python API: stow(), unstow(), restow().

These test the library interface as documented in __init__.py,
not the CLI or internal _Stower class.
"""

import os
import re

import pytest

from stow_python import stow, unstow, restow, StowConfig, StowResult, StowError
from stow_python.types import LinkTask, DirTask, MoveTask


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """Create a test environment for API tests."""
    stow_dir = tmp_path / "stow"
    target_dir = tmp_path / "target"
    stow_dir.mkdir()
    target_dir.mkdir()

    # Set HOME to avoid global ignore file interference
    monkeypatch.setenv("HOME", str(tmp_path))

    return {
        "stow_dir": str(stow_dir),
        "target_dir": str(target_dir),
        "tmp_path": tmp_path,
    }


def create_package(stow_dir, name, files):
    """Create a package with given files."""
    pkg_dir = os.path.join(stow_dir, name)
    os.makedirs(pkg_dir, exist_ok=True)
    for path, content in files.items():
        full_path = os.path.join(pkg_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)


class TestStowBasic:
    """Test basic stow() functionality."""

    def test_stow_single_package(self, api_env):
        """Stow a single package creates expected symlinks."""
        create_package(api_env["stow_dir"], "pkg1", {"bin/hello": "#!/bin/sh\necho hi"})

        result = stow("pkg1", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert result.success
        assert result.conflicts == {}
        link = os.path.join(api_env["target_dir"], "bin")
        assert os.path.islink(link)
        assert os.readlink(link) == "../stow/pkg1/bin"

    def test_stow_multiple_packages(self, api_env):
        """Stow multiple packages at once."""
        create_package(api_env["stow_dir"], "pkg1", {"bin/cmd1": "content1"})
        create_package(api_env["stow_dir"], "pkg2", {"lib/lib1": "content2"})

        result = stow(
            "pkg1", "pkg2", dir=api_env["stow_dir"], target=api_env["target_dir"]
        )

        assert result.success
        assert os.path.islink(os.path.join(api_env["target_dir"], "bin"))
        assert os.path.islink(os.path.join(api_env["target_dir"], "lib"))

    def test_stow_returns_tasks(self, api_env):
        """Stow result includes performed tasks."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        result = stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert result.success
        assert len(result.tasks) > 0
        assert any(isinstance(t, LinkTask) for t in result.tasks)


class TestUnstowBasic:
    """Test basic unstow() functionality."""

    def test_unstow_removes_symlinks(self, api_env):
        """Unstow removes symlinks created by stow."""
        create_package(api_env["stow_dir"], "pkg", {"bin/hello": "content"})

        # First stow
        stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])
        assert os.path.islink(os.path.join(api_env["target_dir"], "bin"))

        # Then unstow
        result = unstow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert result.success
        assert not os.path.exists(os.path.join(api_env["target_dir"], "bin"))

    def test_unstow_never_stowed(self, api_env):
        """Unstow package that was never stowed succeeds (no-op)."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        result = unstow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert result.success
        assert result.conflicts == {}


class TestRestowBasic:
    """Test basic restow() functionality."""

    def test_restow_refreshes_package(self, api_env):
        """Restow unstows then stows package."""
        create_package(api_env["stow_dir"], "pkg", {"file1": "content1"})

        # Initial stow
        stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        # Add new file to package
        with open(os.path.join(api_env["stow_dir"], "pkg", "file2"), "w") as f:
            f.write("content2")

        # Restow
        result = restow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert result.success
        # Both files are top-level package entries, so each is stowed as
        # its own symlink into the package
        target_file1 = os.path.join(api_env["target_dir"], "file1")
        assert os.path.islink(target_file1)
        assert os.readlink(target_file1) == "../stow/pkg/file1"
        target_file2 = os.path.join(api_env["target_dir"], "file2")
        assert os.path.islink(target_file2)
        assert os.readlink(target_file2) == "../stow/pkg/file2"


class TestStowConfig:
    """Test StowConfig usage."""

    def test_config_reuse(self, api_env):
        """StowConfig can be reused for multiple operations."""
        create_package(api_env["stow_dir"], "pkg1", {"bin/cmd1": "content1"})
        create_package(api_env["stow_dir"], "pkg2", {"lib/lib1": "content2"})

        config = StowConfig(dir=api_env["stow_dir"], target=api_env["target_dir"])

        result1 = stow("pkg1", config=config)
        result2 = stow("pkg2", config=config)

        assert result1.success
        assert result2.success
        assert os.path.islink(os.path.join(api_env["target_dir"], "bin"))
        assert os.path.islink(os.path.join(api_env["target_dir"], "lib"))

    def test_config_override_with_kwargs(self, api_env):
        """kwargs override config fields."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        config = StowConfig(dir=api_env["stow_dir"], target=api_env["target_dir"])

        # Override simulate=True
        result = stow("pkg", config=config, simulate=True)

        assert result.success
        assert len(result.tasks) > 0
        # But no actual symlink created (simulation)
        assert not os.path.exists(os.path.join(api_env["target_dir"], "file"))


class TestSimulateMode:
    """Test simulate (dry-run) mode."""

    def test_simulate_returns_planned_tasks(self, api_env):
        """Simulate mode returns tasks without executing."""
        create_package(api_env["stow_dir"], "pkg", {"bin/hello": "content"})

        result = stow(
            "pkg", dir=api_env["stow_dir"], target=api_env["target_dir"], simulate=True
        )

        assert result.success
        assert len(result.tasks) > 0
        # No actual changes
        assert not os.path.exists(os.path.join(api_env["target_dir"], "bin"))

    def test_simulate_detects_conflicts(self, api_env):
        """Simulate mode detects conflicts without modifying filesystem."""
        create_package(api_env["stow_dir"], "pkg", {"file": "package content"})
        # Create conflicting file in target
        target_file = os.path.join(api_env["target_dir"], "file")
        with open(target_file, "w") as f:
            f.write("existing content")

        result = stow(
            "pkg", dir=api_env["stow_dir"], target=api_env["target_dir"], simulate=True
        )

        assert not result.success
        assert "pkg" in result.conflicts
        # Original file unchanged
        with open(target_file) as f:
            assert f.read() == "existing content"

    def test_simulate_excludes_skipped_tasks(self, api_env):
        """Simulated tasks match what a real run would perform.

        Restowing an already-stowed package plans a remove+create pair
        that planning then reverts (marks skipped). Reverted tasks are
        never executed, so simulate mode must exclude them from
        result.tasks just like a real run does."""
        create_package(api_env["stow_dir"], "pkg", {"bin/hello": "content"})
        stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        simulated = restow(
            "pkg", dir=api_env["stow_dir"], target=api_env["target_dir"], simulate=True
        )
        real = restow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert simulated.success and real.success
        assert simulated.tasks == real.tasks
        assert not any(t.skipped for t in simulated.tasks)
        assert not any(t.skipped for t in real.tasks)
        # For this scenario everything cancels out: nothing to perform
        assert simulated.tasks == []


class TestConflictHandling:
    """Test conflict detection and reporting."""

    def test_conflict_with_existing_file(self, api_env):
        """Stow reports conflict when target file exists."""
        create_package(api_env["stow_dir"], "pkg", {"file": "package content"})
        # Create conflicting file
        target_file = os.path.join(api_env["target_dir"], "file")
        with open(target_file, "w") as f:
            f.write("existing content")

        result = stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert not result.success
        assert "pkg" in result.conflicts
        assert len(result.conflicts["pkg"]) > 0

    def test_no_changes_on_conflict(self, api_env):
        """No filesystem changes when conflicts exist."""
        create_package(
            api_env["stow_dir"], "pkg", {"dir/file1": "c1", "dir/file2": "c2"}
        )
        # Create conflicting file
        os.makedirs(os.path.join(api_env["target_dir"], "dir"))
        target_file = os.path.join(api_env["target_dir"], "dir", "file1")
        with open(target_file, "w") as f:
            f.write("existing")

        result = stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert not result.success
        # file2 should NOT be stowed either (all-or-nothing)
        assert not os.path.islink(os.path.join(api_env["target_dir"], "dir", "file2"))


class TestDotfilesMode:
    """Test dotfiles handling."""

    def test_dotfiles_transforms_names(self, api_env):
        """Dotfiles mode converts dot- prefix to . in target."""
        create_package(api_env["stow_dir"], "dotpkg", {"dot-bashrc": "# bashrc"})

        result = stow(
            "dotpkg",
            dir=api_env["stow_dir"],
            target=api_env["target_dir"],
            dotfiles=True,
        )

        assert result.success
        # Should create .bashrc, not dot-bashrc
        assert os.path.islink(os.path.join(api_env["target_dir"], ".bashrc"))
        assert not os.path.exists(os.path.join(api_env["target_dir"], "dot-bashrc"))


class TestNoFoldingMode:
    """Test no-folding mode."""

    def test_no_folding_creates_directories(self, api_env):
        """No-folding mode creates real directories instead of dir symlinks."""
        create_package(api_env["stow_dir"], "pkg", {"dir/file": "content"})

        result = stow(
            "pkg",
            dir=api_env["stow_dir"],
            target=api_env["target_dir"],
            no_folding=True,
        )

        assert result.success
        # dir should be a real directory, not a symlink
        target_dir = os.path.join(api_env["target_dir"], "dir")
        assert os.path.isdir(target_dir)
        assert not os.path.islink(target_dir)
        # file inside should be a symlink
        assert os.path.islink(os.path.join(target_dir, "file"))


class TestAdoptMode:
    """Test adopt mode."""

    def test_adopt_moves_existing_file(self, api_env):
        """Adopt mode moves existing target file into package."""
        create_package(api_env["stow_dir"], "pkg", {"file": "package version"})
        # Create file in target with different content
        target_file = os.path.join(api_env["target_dir"], "file")
        with open(target_file, "w") as f:
            f.write("target version")

        result = stow(
            "pkg", dir=api_env["stow_dir"], target=api_env["target_dir"], adopt=True
        )

        assert result.success
        # Target should now be symlink
        assert os.path.islink(target_file)
        # Package file should have target content (adopted)
        pkg_file = os.path.join(api_env["stow_dir"], "pkg", "file")
        with open(pkg_file) as f:
            assert f.read() == "target version"


class TestErrorHandling:
    """Test error conditions."""

    def test_nonexistent_package_raises(self, api_env):
        """Stowing nonexistent package raises StowError."""
        with pytest.raises(StowError):
            stow("nonexistent", dir=api_env["stow_dir"], target=api_env["target_dir"])

    def test_empty_package_name_raises(self, api_env):
        """Empty package name raises StowError."""
        with pytest.raises(StowError):
            stow("", dir=api_env["stow_dir"], target=api_env["target_dir"])


class TestStowResult:
    """Test StowResult structure."""

    def test_result_has_expected_fields(self, api_env):
        """StowResult has success, conflicts, and tasks fields."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        result = stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        assert isinstance(result, StowResult)
        assert hasattr(result, "success")
        assert hasattr(result, "conflicts")
        assert hasattr(result, "tasks")
        assert isinstance(result.success, bool)
        assert isinstance(result.conflicts, dict)
        assert isinstance(result.tasks, list)

    def test_tasks_are_typed(self, api_env):
        """Tasks in result are proper Task types."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        result = stow("pkg", dir=api_env["stow_dir"], target=api_env["target_dir"])

        for task in result.tasks:
            assert isinstance(task, (LinkTask, DirTask, MoveTask))


class TestLibraryRobustness:
    """Pin the library-API hardening: kwargs validation, string patterns,
    per-operation ignore caching, and deep-tree traversal."""

    def test_unknown_kwarg_rejected(self, api_env):
        """A typo'd option name must raise, not silently change behavior."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        with pytest.raises(TypeError, match="adpot"):
            stow(
                "pkg",
                dir=api_env["stow_dir"],
                target=api_env["target_dir"],
                adpot=True,
            )

    def test_pattern_strings_accepted_and_anchored(self, api_env):
        """ignore takes raw pattern strings, end-anchored like the CLI."""
        create_package(api_env["stow_dir"], "pkg", {"notes.txt": "x", "txt.notes": "y"})

        result = stow(
            "pkg",
            dir=api_env["stow_dir"],
            target=api_env["target_dir"],
            ignore=[r"\.txt"],
        )

        assert result.success
        assert not os.path.lexists(os.path.join(api_env["target_dir"], "notes.txt"))
        assert os.path.islink(os.path.join(api_env["target_dir"], "txt.notes"))

    def test_compiled_pattern_rejected(self, api_env):
        """Pre-compiled patterns are rejected: anchoring is applied in core."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        with pytest.raises(TypeError, match="regex strings"):
            stow(
                "pkg",
                dir=api_env["stow_dir"],
                target=api_env["target_dir"],
                ignore=[re.compile("file")],
            )

    def test_malformed_pattern_raises_stow_error(self, api_env):
        """A malformed pattern raises StowError, not re.error."""
        create_package(api_env["stow_dir"], "pkg", {"file": "content"})

        with pytest.raises(StowError, match="Failed to compile regexp"):
            stow(
                "pkg",
                dir=api_env["stow_dir"],
                target=api_env["target_dir"],
                ignore=["foo("],
            )

    def test_ignore_file_cache_is_per_operation(self, tmp_path, monkeypatch):
        """Sequential operations on different trees with the same relative
        layout must each read their own .stow-local-ignore file."""
        monkeypatch.setenv("HOME", str(tmp_path))
        for name, ignored in (("a", "keepme"), ("b", "unrelated")):
            root = tmp_path / name
            (root / "stow" / "pkg").mkdir(parents=True)
            (root / "target").mkdir()
            (root / "stow" / "pkg" / ".stow-local-ignore").write_text(ignored + "\n")
            (root / "stow" / "pkg" / "keepme").write_text("x")

        result_a = stow(
            "pkg",
            dir=str(tmp_path / "a" / "stow"),
            target=str(tmp_path / "a" / "target"),
        )
        result_b = stow(
            "pkg",
            dir=str(tmp_path / "b" / "stow"),
            target=str(tmp_path / "b" / "target"),
        )

        assert result_a.success and result_b.success
        # Tree a ignores keepme; tree b must NOT inherit a's cached patterns
        assert not os.path.lexists(tmp_path / "a" / "target" / "keepme")
        assert os.path.islink(tmp_path / "b" / "target" / "keepme")

    def test_deep_tree_stow_and_unstow(self, tmp_path, monkeypatch):
        """A tree hundreds of levels deep must not hit the interpreter
        recursion limit (the planner runs on an explicit job stack)."""
        monkeypatch.setenv("HOME", str(tmp_path))
        stow_dir = tmp_path / "stow"
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Bound the depth by the platform's PATH_MAX (Linux ~4096, macOS
        # 1024). The longest string built here is the symlink destination,
        # which spends about five bytes per level: "../" climbing back out
        # plus "d/" descending into the package. Linux keeps the full 600;
        # the floor assertion below stops the test from silently decaying
        # into a shallow one if the budget ever collapses.
        try:
            path_max = os.pathconf(str(tmp_path), "PC_PATH_MAX")
        except (AttributeError, OSError, ValueError):
            path_max = 1024
        prefix = max(len(str(stow_dir / "pkg")), len(str(target_dir)))
        depth = min(600, (path_max - prefix - 32) // 5)
        assert depth > 100, f"depth {depth} too shallow to exercise the job stack"

        rel = "/".join(["d"] * depth)
        deep_dir = os.path.join(str(stow_dir / "pkg"), rel)
        os.makedirs(deep_dir)
        with open(os.path.join(deep_dir, "leaf"), "w") as f:
            f.write("x")

        result = stow("pkg", dir=str(stow_dir), target=str(target_dir), no_folding=True)
        assert result.success
        leaf = os.path.join(str(target_dir), rel, "leaf")
        assert os.path.islink(leaf)

        result = unstow("pkg", dir=str(stow_dir), target=str(target_dir))
        assert result.success
        assert not os.path.lexists(leaf)
