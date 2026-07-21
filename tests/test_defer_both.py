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
Black-box oracle tests for defer and override handling.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results

Based on Perl t/defer.t and defer/override tests in t/stow.t
"""

from conftest import (
    check_link,
    run_both_tests,
)


class TestDeferBoth:
    """Test defer pattern handling - black-box comparison of both implementations."""

    def test_defer_to_existing(self, stow_env):
        """Defer to already stowed package."""
        stow_env.create_package("pkg1", {"man/man1/file.1": "first"})
        stow_env.create_package("pkg2", {"man/man1/file.1": "second"})

        def setup():
            stow_env.create_target_dir("man/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # pkg1's file should remain (pkg2 deferred)
            check_link(env, "man/man1/file.1", "../../../stow/pkg1/man/man1/file.1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_defer_multiple_patterns(self, stow_env):
        """Defer with multiple patterns."""
        stow_env.create_package("pkg1", {"lib/file": "first", "share/file": "first"})
        stow_env.create_package("pkg2", {"lib/file": "second", "share/file": "second"})

        def setup():
            stow_env.create_target_dir("lib")
            stow_env.create_target_dir("share")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # Both should defer to pkg1
            check_link(env, "lib/file", "../../stow/pkg1/lib/file")
            check_link(env, "share/file", "../../stow/pkg1/share/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=lib", "--defer=share", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_defer_no_match(self, stow_env):
        """Defer pattern that doesn't match should still stow."""
        stow_env.create_package("pkg1", {"bin/file": "first"})
        stow_env.create_package("pkg2", {"bin/file": "second"})

        def setup():
            stow_env.create_target_dir("bin")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # bin doesn't match defer=man, so conflict should occur
            # (test verifies both implementations handle this the same)
            pass

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )


class TestOverrideBoth:
    """Test override pattern handling - black-box comparison of both implementations."""

    def test_override_existing(self, stow_env):
        """Override already stowed package."""
        stow_env.create_package("pkg1", {"man/man1/file.1": "old"})
        stow_env.create_package("pkg2", {"man/man1/file.1": "new"})

        def setup():
            stow_env.create_target_dir("man/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # pkg2's file should replace pkg1's
            check_link(env, "man/man1/file.1", "../../../stow/pkg2/man/man1/file.1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=man", "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_override_multiple_patterns(self, stow_env):
        """Override with multiple patterns."""
        stow_env.create_package("pkg1", {"lib/file": "old", "info/file": "old"})
        stow_env.create_package("pkg2", {"lib/file": "new", "info/file": "new"})

        def setup():
            stow_env.create_target_dir("lib")
            stow_env.create_target_dir("info")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # Both should be overridden by pkg2
            check_link(env, "lib/file", "../../stow/pkg2/lib/file")
            check_link(env, "info/file", "../../stow/pkg2/info/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=lib", "--override=info", "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_override_no_match(self, stow_env):
        """Override pattern that doesn't match should cause conflict."""
        stow_env.create_package("pkg1", {"bin/file": "first"})
        stow_env.create_package("pkg2", {"bin/file": "second"})

        def setup():
            stow_env.create_target_dir("bin")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # bin doesn't match override=man, so pkg1's link remains
            check_link(env, "bin/file", "../../stow/pkg1/bin/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=man", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )


class TestDeferOverrideCombined:
    """Test defer and override together."""

    def test_defer_and_override_together(self, stow_env):
        """Use both defer and override in same operation."""
        stow_env.create_package("pkg1", {"man/file": "old man", "lib/file": "old lib"})
        stow_env.create_package("pkg2", {"man/file": "new man", "lib/file": "new lib"})

        def setup():
            stow_env.create_target_dir("man")
            stow_env.create_target_dir("lib")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # man should defer (keep pkg1), lib should override (use pkg2)
            check_link(env, "man/file", "../../stow/pkg1/man/file")
            check_link(env, "lib/file", "../../stow/pkg2/lib/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man", "--override=lib", "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )


class TestDeferOverrideRegexEdgeCases:
    """Test complex regex patterns in defer/override, not just simple strings."""

    def test_defer_with_regex_character_class(self, stow_env):
        """Defer with regex character class pattern."""
        stow_env.create_package(
            "pkg1",
            {
                "man1/file": "first",
                "man2/file": "first",
                "bin/file": "first",
            },
        )
        stow_env.create_package(
            "pkg2",
            {
                "man1/file": "second",
                "man2/file": "second",
                "bin/file": "second",
            },
        )

        def setup():
            stow_env.create_target_dir("man1")
            stow_env.create_target_dir("man2")
            stow_env.create_target_dir("bin")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # man1 and man2 should defer, bin should conflict
            check_link(env, "man1/file", "../../stow/pkg1/man1/file")
            check_link(env, "man2/file", "../../stow/pkg1/man2/file")
            # bin doesn't match man[12], so conflict (pkg1 remains)
            check_link(env, "bin/file", "../../stow/pkg1/bin/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man[12]", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_override_with_regex_alternation(self, stow_env):
        """Override with regex alternation pattern."""
        stow_env.create_package(
            "pkg1",
            {
                "lib/file": "old",
                "lib64/file": "old",
                "share/file": "old",
            },
        )
        stow_env.create_package(
            "pkg2",
            {
                "lib/file": "new",
                "lib64/file": "new",
                "share/file": "new",
            },
        )

        def setup():
            stow_env.create_target_dir("lib")
            stow_env.create_target_dir("lib64")
            stow_env.create_target_dir("share")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        # Just use oracle comparison - let the Perl vs Python comparison verify behavior
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=lib(64)?", "pkg2"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_defer_with_anchor_start(self, stow_env):
        """Defer with anchor pattern (start of path)."""
        stow_env.create_package(
            "pkg1",
            {
                "usr/share/man/file": "first",
                "share/man/file": "first",
            },
        )
        stow_env.create_package(
            "pkg2",
            {
                "usr/share/man/file": "second",
                "share/man/file": "second",
            },
        )

        def setup():
            stow_env.create_target_dir("usr/share/man")
            stow_env.create_target_dir("share/man")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # ^share matches share but not usr/share
            check_link(env, "share/man/file", "../../../stow/pkg1/share/man/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=^share", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_override_with_wildcard_and_quantifier(self, stow_env):
        """Override with .* wildcard and quantifiers."""
        stow_env.create_package(
            "pkg1",
            {
                "local/bin/file": "old",
                "local/lib/file": "old",
                "system/bin/file": "old",
            },
        )
        stow_env.create_package(
            "pkg2",
            {
                "local/bin/file": "new",
                "local/lib/file": "new",
                "system/bin/file": "new",
            },
        )

        def setup():
            stow_env.create_target_dir("local/bin")
            stow_env.create_target_dir("local/lib")
            stow_env.create_target_dir("system/bin")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        # Just use oracle comparison - let the Perl vs Python comparison verify behavior
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=local/.*", "pkg2"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_defer_with_extension_pattern(self, stow_env):
        """Defer pattern matching file extensions in path."""
        stow_env.create_package(
            "pkg1",
            {
                "share/doc/file": "first",
                "share/man/file": "first",
            },
        )
        stow_env.create_package(
            "pkg2",
            {
                "share/doc/file": "second",
                "share/man/file": "second",
            },
        )

        def setup():
            stow_env.create_target_dir("share/doc")
            stow_env.create_target_dir("share/man")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1"])

        def check(env):
            # share/(doc|man) matches both
            check_link(env, "share/doc/file", "../../../stow/pkg1/share/doc/file")
            check_link(env, "share/man/file", "../../../stow/pkg1/share/man/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=share/(doc|man)", "pkg2"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )


class TestPackageUpgradeScenarios:
    """Test package upgrade scenarios using override to replace old versions."""

    def test_upgrade_package_version_override(self, stow_env):
        """Upgrade package: override old version with new version of same package."""
        # Simulate two versions of the same package
        stow_env.create_package(
            "app-1.0",
            {
                "bin/app": "version 1.0",
                "lib/libapp.so": "lib 1.0",
                "share/app/config": "config 1.0",
            },
        )
        stow_env.create_package(
            "app-2.0",
            {
                "bin/app": "version 2.0",
                "lib/libapp.so": "lib 2.0",
                "share/app/config": "config 2.0",
                "share/app/newfeature": "new in 2.0",
            },
        )

        def setup():
            stow_env.create_target_dir("bin")
            stow_env.create_target_dir("lib")
            stow_env.create_target_dir("share/app")
            # Old version already installed
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "app-1.0"])

        def check(env):
            # All paths should now point to 2.0
            check_link(env, "bin/app", "../../stow/app-2.0/bin/app")
            check_link(env, "lib/libapp.so", "../../stow/app-2.0/lib/libapp.so")
            check_link(
                env, "share/app/config", "../../../stow/app-2.0/share/app/config"
            )
            check_link(
                env,
                "share/app/newfeature",
                "../../../stow/app-2.0/share/app/newfeature",
            )

        # Override all paths to allow upgrade
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=.*", "app-2.0"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_upgrade_with_restow(self, stow_env):
        """Upgrade using unstow old + stow new (restow pattern)."""
        stow_env.create_package(
            "pkg-old",
            {
                "bin/cmd": "old",
                "lib/lib.so": "old",
            },
        )
        stow_env.create_package(
            "pkg-new",
            {
                "bin/cmd": "new",
                "lib/lib.so": "new",
                "lib/extra.so": "extra",
            },
        )

        def setup():
            stow_env.create_target_dir("bin")
            stow_env.create_target_dir("lib")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg-old"])

        def check(env):
            # New package should be stowed
            check_link(env, "bin/cmd", "../../stow/pkg-new/bin/cmd")
            check_link(env, "lib/lib.so", "../../stow/pkg-new/lib/lib.so")
            check_link(env, "lib/extra.so", "../../stow/pkg-new/lib/extra.so")

        # Unstow old, stow new in one command
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "-D", "pkg-old", "-S", "pkg-new"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_upgrade_selective_override(self, stow_env):
        """Upgrade with selective override - only upgrade specific paths."""
        stow_env.create_package(
            "app-1.0",
            {
                "bin/app": "1.0 binary",
                "etc/app.conf": "1.0 config",
            },
        )
        stow_env.create_package(
            "app-2.0",
            {
                "bin/app": "2.0 binary",
                "etc/app.conf": "2.0 config",
            },
        )

        def setup():
            stow_env.create_target_dir("bin")
            stow_env.create_target_dir("etc")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "app-1.0"])

        def check(env):
            # bin should be upgraded (override matches)
            check_link(env, "bin/app", "../../stow/app-2.0/bin/app")
            # etc should defer (keep old config)
            check_link(env, "etc/app.conf", "../../stow/app-1.0/etc/app.conf")

        # Override bin, defer etc (preserve user config)
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=bin", "--defer=etc", "app-2.0"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )
