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
Black-box oracle tests for ignore pattern handling.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results

Based on Perl t/ignore.t
"""

import os

from conftest import (
    check_link,
    check_not_exists,
    run_both_tests,
)


class TestIgnoreBoth:
    """Test ignore pattern handling - black-box comparison of both implementations."""

    def test_ignore_cli_pattern(self, stow_env):
        """Test --ignore CLI option filters files."""
        stow_env.create_package(
            "pkg",
            {
                "bin/file": "content",
                "bin/file~": "backup",
                "bin/.#file": "emacs temp",
            },
        )

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            check_link(env, "bin/file", "../../stow/pkg/bin/file")
            check_not_exists(env, "bin/file~")
            check_not_exists(env, "bin/.#file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=~", "--ignore=\\.#.*", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_multiple_patterns(self, stow_env):
        """Test multiple --ignore patterns."""
        stow_env.create_package(
            "pkg",
            {
                "dir/keep.txt": "keep",
                "dir/skip.bak": "skip1",
                "dir/skip.tmp": "skip2",
                "dir/also_skip~": "skip3",
            },
        )

        def setup():
            stow_env.create_target_dir("dir")

        def check(env):
            check_link(env, "dir/keep.txt", "../../stow/pkg/dir/keep.txt")
            check_not_exists(env, "dir/skip.bak")
            check_not_exists(env, "dir/skip.tmp")
            check_not_exists(env, "dir/also_skip~")

        run_both_tests(
            stow_env,
            [
                "-t",
                stow_env.target_dir,
                "--ignore=\\.bak",
                "--ignore=\\.tmp",
                "--ignore=~",
                "pkg",
            ],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_local_file(self, stow_env):
        """Test .stow-local-ignore file in package."""
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "bin"))
        with open(os.path.join(pkg_path, "bin", "keep"), "w") as f:
            f.write("keep")
        with open(os.path.join(pkg_path, "bin", "ignore_me"), "w") as f:
            f.write("ignore")
        # Create local ignore file
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("ignore_me\n")

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            check_link(env, "bin/keep", "../../stow/pkg/bin/keep")
            check_not_exists(env, "bin/ignore_me")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_global_file(self, stow_env):
        """Test ~/.stow-global-ignore file."""
        stow_env.create_package(
            "pkg",
            {
                "bin/keep": "keep",
                "bin/global_ignored": "ignore",
            },
        )
        # Create global ignore file in HOME (which is set to tmpdir)
        with open(os.path.join(stow_env.tmpdir, ".stow-global-ignore"), "w") as f:
            f.write("global_ignored\n")

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            check_link(env, "bin/keep", "../../stow/pkg/bin/keep")
            check_not_exists(env, "bin/global_ignored")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_local_ignore_overrides_global(self, stow_env):
        """Test that local ignore file completely replaces global."""
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "bin"))
        with open(os.path.join(pkg_path, "bin", "from_global"), "w") as f:
            f.write("content")
        with open(os.path.join(pkg_path, "bin", "from_local"), "w") as f:
            f.write("content")
        with open(os.path.join(pkg_path, "bin", "keep"), "w") as f:
            f.write("keep")

        # Global would ignore from_global
        with open(os.path.join(stow_env.tmpdir, ".stow-global-ignore"), "w") as f:
            f.write("from_global\n")

        # Local ignores from_local (and replaces global)
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("from_local\n")

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            # from_global should be stowed (local replaced global)
            check_link(env, "bin/from_global", "../../stow/pkg/bin/from_global")
            # from_local should be ignored
            check_not_exists(env, "bin/from_local")
            check_link(env, "bin/keep", "../../stow/pkg/bin/keep")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_entire_directory(self, stow_env):
        """Test ignoring entire directory via pattern."""
        stow_env.create_package(
            "pkg",
            {
                "keep/file": "keep",
                "skipdir/file": "skip",
            },
        )

        def setup():
            pass

        def check(env):
            check_link(env, "keep", "../stow/pkg/keep")
            check_not_exists(env, "skipdir")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=skipdir", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_regex_pattern(self, stow_env):
        """Test regex pattern in ignore."""
        stow_env.create_package(
            "pkg",
            {
                "file.txt": "keep",
                "file.log": "skip",
                "data.log": "skip",
                "readme": "keep",
            },
        )

        def setup():
            pass

        def check(env):
            # Non-matching files are stowed as individual top-level links;
            # the .log files are ignored and never appear in the target
            check_link(env, "file.txt", "../stow/pkg/file.txt")
            check_link(env, "readme", "../stow/pkg/readme")
            check_not_exists(env, "file.log")
            check_not_exists(env, "data.log")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=\\.log$", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )


class TestAnchoredIgnorePatterns:
    """Test anchored ignore patterns (^/ prefix) that anchor to package root."""

    def test_anchored_pattern_at_package_root(self, stow_env):
        """Test ^/README.* anchored pattern only matches at package root.

        Pattern ^/README.* should only ignore README files at the package
        root level, not README files in subdirectories.
        """
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "doc"))
        os.makedirs(os.path.join(pkg_path, "bin"))
        # README at root - should be ignored
        with open(os.path.join(pkg_path, "README.md"), "w") as f:
            f.write("root readme")
        # README in subdir - should NOT be ignored (anchored pattern)
        with open(os.path.join(pkg_path, "doc", "README.md"), "w") as f:
            f.write("doc readme")
        with open(os.path.join(pkg_path, "bin", "cmd"), "w") as f:
            f.write("command")
        # Create local ignore with anchored pattern
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("^/README\\..*\n")

        def setup():
            pass

        def check(env):
            # Root README should be ignored (anchored match)
            check_not_exists(env, "README.md")
            # bin should be stowed
            check_link(env, "bin", "../stow/pkg/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_anchored_pattern_with_subdirectory(self, stow_env):
        """Test anchored pattern that specifies subdirectory path."""
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "share", "doc"))
        os.makedirs(os.path.join(pkg_path, "lib"))
        # File at anchored path - should be ignored
        with open(os.path.join(pkg_path, "share", "doc", "LICENSE"), "w") as f:
            f.write("license")
        # Same filename at different path - should be stowed
        with open(os.path.join(pkg_path, "lib", "LICENSE"), "w") as f:
            f.write("lib license")
        # Create local ignore with anchored subdirectory pattern
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("^/share/doc/LICENSE\n")

        def setup():
            pass

        def check(env):
            # lib/LICENSE should be stowed
            check_link(env, "lib", "../stow/pkg/lib")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unanchored_pattern_matches_anywhere(self, stow_env):
        """Test that unanchored pattern matches at any level."""
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "dir1"))
        os.makedirs(os.path.join(pkg_path, "dir2", "subdir"))
        # backup files at various levels - all should be ignored
        with open(os.path.join(pkg_path, "file.bak"), "w") as f:
            f.write("root backup")
        with open(os.path.join(pkg_path, "dir1", "data.bak"), "w") as f:
            f.write("dir1 backup")
        with open(os.path.join(pkg_path, "dir2", "subdir", "test.bak"), "w") as f:
            f.write("nested backup")
        with open(os.path.join(pkg_path, "dir1", "keep.txt"), "w") as f:
            f.write("keep this")
        # Create local ignore with unanchored pattern
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("\\.bak$\n")

        def setup():
            stow_env.create_target_dir("dir1")
            stow_env.create_target_dir("dir2/subdir")

        # Just use oracle comparison - let the Perl vs Python comparison verify behavior
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )


class TestNegationIgnorePatterns:
    """Test negation patterns that un-ignore previously ignored files."""

    def test_negation_pattern_basic(self, stow_env):
        """Test basic negation pattern to un-ignore a file.

        First pattern ignores all .txt files, negation brings back specific one.
        Note: Stow may or may not support negation patterns - this test just
        verifies both implementations behave identically.
        """
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "doc"))
        with open(os.path.join(pkg_path, "doc", "skip.txt"), "w") as f:
            f.write("skip")
        with open(os.path.join(pkg_path, "doc", "important.txt"), "w") as f:
            f.write("important")
        with open(os.path.join(pkg_path, "doc", "other.txt"), "w") as f:
            f.write("other")
        # Ignore all .txt, then negate for important.txt
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("\\.txt$\n")
            f.write("!important\\.txt$\n")

        def setup():
            stow_env.create_target_dir("doc")

        # Just use oracle comparison - let the Perl vs Python comparison verify behavior
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_negation_pattern_directory(self, stow_env):
        """Test negation pattern for directories."""
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "cache", "keep"))
        os.makedirs(os.path.join(pkg_path, "cache", "temp"))
        with open(os.path.join(pkg_path, "cache", "keep", "file"), "w") as f:
            f.write("keep")
        with open(os.path.join(pkg_path, "cache", "temp", "file"), "w") as f:
            f.write("temp")
        with open(os.path.join(pkg_path, "main.conf"), "w") as f:
            f.write("config")
        # Ignore cache, then negate cache/keep
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("^/cache\n")
            f.write("!^/cache/keep\n")

        def setup():
            pass

        def check(env):
            # main.conf should be stowed
            check_link(env, "main.conf", "../stow/pkg/main.conf")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_negation_order_matters(self, stow_env):
        """Test that order of patterns and negations matters.

        Note: Stow may or may not support negation patterns - this test just
        verifies both implementations behave identically.
        """
        pkg_path = os.path.join(stow_env.stow_dir, "pkg")
        os.makedirs(os.path.join(pkg_path, "bin"))
        with open(os.path.join(pkg_path, "bin", "script.sh"), "w") as f:
            f.write("script")
        with open(os.path.join(pkg_path, "bin", "test.sh"), "w") as f:
            f.write("test")
        with open(os.path.join(pkg_path, "bin", "helper.py"), "w") as f:
            f.write("helper")
        # Negate first, then ignore - negation should have no effect
        with open(os.path.join(pkg_path, ".stow-local-ignore"), "w") as f:
            f.write("!test\\.sh$\n")  # This negation comes first - has no effect
            f.write("\\.sh$\n")  # This ignores all .sh files

        def setup():
            stow_env.create_target_dir("bin")

        # Just use oracle comparison - let the Perl vs Python comparison verify behavior
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=None,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_file_with_non_utf8_bytes(self, stow_env):
        """An ignore file holding a byte that is not valid UTF-8 must be
        read the way Perl reads it - as bytes - instead of aborting the
        run with a decoding error."""
        stow_env.create_package("pkg", {"bin/file": "content"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")
        with open(ignore_file, "wb") as f:
            f.write(b"--ignore=\xff\n")

        def setup():
            stow_env.create_target_dir("bin")

        def check(env):
            check_link(env, "bin/file", "../../stow/pkg/bin/file")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=check,
        )

    def test_ignore_file_is_a_directory(self, stow_env):
        """Perl's open() of a directory succeeds and reads nothing, so only
        the hardcoded self-ignore pattern applies: the directory named
        .stow-local-ignore is skipped and the built-in list stays bypassed."""
        stow_env.create_package("pkg", {"a/f": "content"})
        os.makedirs(os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore"))

        def setup():
            pass

        def check(env):
            check_link(env, "a", "../stow/pkg/a")
            check_not_exists(env, ".stow-local-ignore")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=check,
        )

    def test_ignore_file_bare_cr_is_one_pattern(self, stow_env):
        """Perl reads \\n-delimited records, so 'bar\\rbaz' is a single
        pattern matching nothing - universal-newline reading would split
        it and silently ignore two files the user expects to be stowed."""
        stow_env.create_package("pkg", {"bar": "a", "baz": "b"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")
        with open(ignore_file, "wb") as f:
            f.write(b"bar\rbaz\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bar", "../stow/pkg/bar")
            check_link(env, "baz", "../stow/pkg/baz")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=check,
        )

    def test_ignore_file_non_ascii_whitespace_is_not_stripped(self, stow_env):
        """Perl's s/^\\s+// runs on undecoded bytes, so a leading U+00A0
        stays part of the pattern and the pattern matches nothing."""
        stow_env.create_package("pkg", {"bar": "a", "has-dash": "b"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")
        with open(ignore_file, "wb") as f:
            f.write(" bar\n".encode())

        def setup():
            pass

        def check(env):
            check_link(env, "bar", "../stow/pkg/bar")
            check_link(env, "has-dash", "../stow/pkg/has-dash")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=check,
        )

    def test_ignore_file_leading_inline_flag_group(self, stow_env):
        """'(?i)man' is legal in both dialects; the anchoring wrapper pushes
        it off position 0, so the flag group is hoisted rather than
        rejected, and MAN is ignored case-insensitively as in Perl."""
        stow_env.create_package("pkg", {"MAN": "a", "keep": "b"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")
        with open(ignore_file, "w") as f:
            f.write("(?i)man\n")

        def setup():
            pass

        def check(env):
            check_link(env, "keep", "../stow/pkg/keep")
            check_not_exists(env, "MAN")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check_func=check,
        )

    def test_memoized_ignore_file_trace(self, stow_env):
        """The -v4 trace of a package with an ignore file must match line
        for line, including Perl's 'Using memoized regexps from <file>' on
        every cache hit after the first."""
        from conftest import assert_stow_match

        stow_env.create_package("pkg", {"bin/a": "a", "lib/b": "b"})
        with open(
            os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore"), "w"
        ) as f:
            f.write("foo\n")

        _, _, stderr, _ = assert_stow_match(
            stow_env, ["-v4", "-n", "-t", stow_env.target_dir, "pkg"]
        )
        assert stderr.count("Using memoized regexps from") >= 1, stderr
