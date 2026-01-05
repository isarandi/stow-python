"""
Oracle-based tests comparing Python chkstow vs Perl chkstow.

Each test creates a scenario, runs both implementations, and verifies
they produce identical results (return code, stdout, stderr).
"""

from __future__ import print_function

import os

from conftest import assert_chkstow_match


class TestChkstowListPackages:
    """Tests for -l/--list mode."""

    def test_list_single_package(self, stow_env):
        """List a single stowed package."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_list_multiple_packages(self, stow_env):
        """List multiple stowed packages in sorted order."""
        stow_env.create_package("zeta", {"bin/zeta": "zeta"})
        stow_env.create_package("alpha", {"bin/alpha": "alpha"})
        stow_env.create_package("beta", {"lib/beta": "beta"})

        stow_env.run_perl_stow(["-t", stow_env.target_dir, "alpha", "beta", "zeta"])

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_list_empty_target(self, stow_env):
        """No output when target is empty."""
        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_list_with_tree_folding(self, stow_env):
        """List packages with tree-folded directories."""
        stow_env.create_package(
            "mypkg",
            {
                "share/mypkg/file1": "f1",
                "share/mypkg/file2": "f2",
            },
        )
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_list_deep_hierarchy(self, stow_env):
        """List packages from deep symlinks."""
        stow_env.create_package(
            "deep",
            {"share/doc/deep/examples/config.txt": "config"},
        )
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "deep"])

        assert_chkstow_match(stow_env, ["--list", "-t", stow_env.target_dir])


class TestChkstowBadLinks:
    """Tests for -b/--badlinks mode (default)."""

    def test_no_bad_links(self, stow_env):
        """No output when all symlinks are valid."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-b", "-t", stow_env.target_dir])

    def test_detect_bad_link(self, stow_env):
        """Detect a broken symlink."""
        stow_env.create_target_dir("bin")
        os.symlink("nonexistent", os.path.join(stow_env.target_dir, "bin", "broken"))

        assert_chkstow_match(stow_env, ["-b", "-t", stow_env.target_dir])

    def test_detect_multiple_bad_links(self, stow_env):
        """Detect multiple broken symlinks."""
        stow_env.create_target_dir("bin")
        stow_env.create_target_dir("lib")
        os.symlink("missing1", os.path.join(stow_env.target_dir, "bin", "broken1"))
        os.symlink("missing2", os.path.join(stow_env.target_dir, "lib", "broken2"))

        assert_chkstow_match(stow_env, ["--badlinks", "-t", stow_env.target_dir])

    def test_default_mode_is_badlinks(self, stow_env):
        """Default mode without -b/-a/-l is badlinks."""
        stow_env.create_target_dir("bin")
        os.symlink("nonexistent", os.path.join(stow_env.target_dir, "bin", "broken"))

        assert_chkstow_match(stow_env, ["-t", stow_env.target_dir])

    def test_mixed_valid_and_broken(self, stow_env):
        """Only report broken links, not valid ones."""
        stow_env.create_package("mypkg", {"bin/valid": "valid"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        # Add a broken link alongside the valid one
        os.symlink("nonexistent", os.path.join(stow_env.target_dir, "bin", "broken"))

        assert_chkstow_match(stow_env, ["-b", "-t", stow_env.target_dir])


class TestChkstowAliens:
    """Tests for -a/--aliens mode."""

    def test_no_aliens(self, stow_env):
        """No output when all files are symlinks or directories."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-a", "-t", stow_env.target_dir])

    def test_detect_alien_file(self, stow_env):
        """Detect a non-symlink file (alien)."""
        stow_env.create_target_file("bin/alien", "alien content")

        assert_chkstow_match(stow_env, ["-a", "-t", stow_env.target_dir])

    def test_detect_multiple_aliens(self, stow_env):
        """Detect multiple alien files."""
        stow_env.create_target_file("bin/alien1", "content1")
        stow_env.create_target_file("lib/alien2", "content2")

        assert_chkstow_match(stow_env, ["--aliens", "-t", stow_env.target_dir])

    def test_mixed_symlinks_and_aliens(self, stow_env):
        """Only report aliens, not symlinks."""
        stow_env.create_package("mypkg", {"bin/valid": "valid"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        # Add an alien file alongside the symlink
        stow_env.create_target_file("bin/alien", "alien")

        assert_chkstow_match(stow_env, ["-a", "-t", stow_env.target_dir])


class TestChkstowSkipDirs:
    """Tests for skipping .stow and .notstowed directories."""

    def test_skip_stow_dir(self, stow_env):
        """Skip directories with .stow marker, print warning to stderr."""
        stow_env.create_target_dir("stow")
        stow_env.create_target_file("stow/.stow", "")
        stow_env.create_target_file("stow/pkg/bin/hello", "hello")

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_skip_notstowed_dir(self, stow_env):
        """Skip directories with .notstowed marker."""
        stow_env.create_target_dir("protected")
        stow_env.create_target_file("protected/.notstowed", "")
        stow_env.create_target_file("protected/alien", "should be skipped")

        # Without the .notstowed marker, this would report an alien
        assert_chkstow_match(stow_env, ["-a", "-t", stow_env.target_dir])

    def test_skip_nested_stow_dir(self, stow_env):
        """Skip nested .stow directories."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        # Create a nested stow dir in target
        stow_env.create_target_dir("otherstow")
        stow_env.create_target_file("otherstow/.stow", "")

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])


class TestChkstowTargetOption:
    """Tests for -t/--target option."""

    def test_target_short_option(self, stow_env):
        """Use -t to specify target directory."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-l", "-t", stow_env.target_dir])

    def test_target_long_option(self, stow_env):
        """Use --target= to specify target directory."""
        stow_env.create_package("mypkg", {"bin/hello": "hello"})
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "mypkg"])

        assert_chkstow_match(stow_env, ["-l", "--target=" + stow_env.target_dir])
