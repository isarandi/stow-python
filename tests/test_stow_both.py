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
Black-box oracle tests for stow operations.
Tests both Perl and Python implementations via CLI, verifying:
1. Each implementation passes the original .t-style assertions
2. Both implementations produce identical results (with and without -n)

Based on Perl t/stow.t
"""

import errno
import os

from conftest import (
    assert_stow_match,
    assert_stow_match_raw,
    check_dir,
    check_link,
    check_not_exists,
    normalize_newline_warnings,
    run_both_tests,
)


class TestStowBoth:
    """Test stow operations - black-box comparison of both implementations."""

    def test_stow_simple_tree_minimally(self, stow_env):
        """Stow a simple tree minimally."""
        stow_env.create_package("pkg1", {"bin1/file1": "content"})

        def setup():
            pass

        def check(env):
            check_link(env, "bin1", "../stow/pkg1/bin1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg1"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stow_simple_tree_into_existing_directory(self, stow_env):
        """Stow a simple tree into an existing directory."""
        stow_env.create_package("pkg2", {"lib2/file2": "content"})

        def setup():
            stow_env.create_target_dir("lib2")

        def check(env):
            check_link(env, "lib2/file2", "../../stow/pkg2/lib2/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_unfold_existing_tree(self, stow_env):
        """Unfold existing tree when stowing second package."""
        stow_env.create_package("pkg3a", {"bin3/file3a": "content a"})
        stow_env.create_package("pkg3b", {"bin3/file3b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg3a"])

        def check(env):
            check_dir(env, "bin3")
            check_link(env, "bin3/file3a", "../../stow/pkg3a/bin3/file3a")
            check_link(env, "bin3/file3b", "../../stow/pkg3b/bin3/file3b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg3b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowing_directories_named_0(self, stow_env):
        """Stowing directories named 0."""
        stow_env.create_package("pkg8a", {"0/file8a": "content a"})
        stow_env.create_package("pkg8b", {"0/file8b": "content b"})

        def setup():
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg8a"])

        def check(env):
            check_dir(env, "0")
            check_link(env, "0/file8a", "../../stow/pkg8a/0/file8a")
            check_link(env, "0/file8b", "../../stow/pkg8b/0/file8b")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg8b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stow_with_no_folding(self, stow_env):
        """Stow with --no-folding creates individual links."""
        stow_env.create_package(
            "pkg",
            {
                "bin/file1": "content1",
                "bin/file2": "content2",
            },
        )

        def setup():
            pass

        def check(env):
            check_dir(env, "bin")
            check_link(env, "bin/file1", "../../stow/pkg/bin/file1")
            check_link(env, "bin/file2", "../../stow/pkg/bin/file2")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--no-folding", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_stowing_links_to_library_files(self, stow_env):
        """Stowing package with symlinks (like lib.so -> lib.so.1)."""
        pkg_dir = os.path.join(stow_env.stow_dir, "pkg12", "lib12")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "lib.so.1"), "w") as f:
            f.write("library")
        os.symlink("lib.so.1", os.path.join(pkg_dir, "lib.so"))

        def setup():
            stow_env.create_target_dir("lib12")

        def check(env):
            check_link(env, "lib12/lib.so.1", "../../stow/pkg12/lib12/lib.so.1")
            check_link(env, "lib12/lib.so", "../../stow/pkg12/lib12/lib.so")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg12"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_conflict_existing_file(self, stow_env):
        """Conflict when target file already exists."""
        stow_env.create_package("pkg", {"bin/file": "package content"})

        def setup():
            stow_env.create_target_file("bin/file", "existing content")

        def check(env):
            # File should still be the original, not a symlink
            full_path = os.path.join(env.target_dir, "bin/file")
            assert os.path.isfile(full_path), "bin/file should exist"
            assert not os.path.islink(full_path), "bin/file should not be a symlink"

        # For conflicts, check on simulate (planning detects conflict)
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkg"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_adopt_existing_file(self, stow_env):
        """Adopt existing files into the package."""
        stow_env.create_package("pkg", {"file": "package version"})

        def setup():
            stow_env.create_target_file("file", "target version")
            # Restore package file to original state for each run
            with open(os.path.join(stow_env.stow_dir, "pkg", "file"), "w") as f:
                f.write("package version")

        def check(env):
            full_path = os.path.join(env.target_dir, "file")
            assert os.path.islink(full_path), "file should be a symlink after adopt"
            pkg_file = os.path.join(env.stow_dir, "pkg", "file")
            with open(pkg_file) as f:
                content = f.read()
            assert content == "target version", "package file should have adopted content"

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--adopt", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_pattern(self, stow_env):
        """Ignore files matching pattern."""
        stow_env.create_package(
            "pkg",
            {
                "man/man1/file.1": "content",
                "man/man1/file.1~": "backup",
                "man/man1/.#file.1": "emacs temp",
            },
        )

        def setup():
            stow_env.create_target_dir("man/man1")

        def check(env):
            check_link(env, "man/man1/file.1", "../../../stow/pkg/man/man1/file.1")
            check_not_exists(env, "man/man1/file.1~")
            check_not_exists(env, "man/man1/.#file.1")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--ignore=~", "--ignore=\\.#.*", "pkg"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_ignore_file_with_non_utf8_bytes(self, stow_env):
        """An ignore file is a byte stream. Patterns whose bytes are not
        valid in the ambient encoding are read and applied like any other,
        instead of aborting the run."""
        stow_env.create_package("pkgnb", {"bin/file": "content", "keepme": "keep"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkgnb", ".stow-local-ignore")
        with open(ignore_file, "wb") as f:
            f.write(b"caf\xe9\n\xff\nkeepme\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkgnb/bin")
            check_not_exists(env, "keepme")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkgnb"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
            env_vars={"LC_ALL": "en_US.UTF-8"},
        )

    def test_ignore_file_pattern_matching_non_utf8_name(self, stow_env):
        """A pattern with non-UTF-8 bytes matches the file of that name."""
        stow_env.create_package("pkgnm", {"bin/file": "content"})
        pkg_dir = os.path.join(stow_env.stow_dir, "pkgnm").encode()
        with open(pkg_dir + b"/caf\xe9", "wb") as f:
            f.write(b"x")
        with open(pkg_dir + b"/.stow-local-ignore", "wb") as f:
            f.write(b"caf\xe9\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkgnm/bin")
            assert not os.path.lexists(
                os.path.join(env.target_dir.encode(), b"caf\xe9")
            )

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkgnm"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
            env_vars={"LC_ALL": "en_US.UTF-8"},
        )

    def test_stowrc_with_non_utf8_bytes(self, stow_env):
        """.stowrc is read as bytes too."""
        stow_env.create_package("pkgrc", {"bin/file": "content"})
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "wb") as f:
            f.write(b"--ignore=caf\xe9\n")

        def setup():
            pass

        def check(env):
            check_link(env, "bin", "../stow/pkgrc/bin")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkgrc"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
            env_vars={"LC_ALL": "en_US.UTF-8"},
        )

    def test_override_already_stowed(self, stow_env):
        """Override already stowed paths."""
        stow_env.create_package("pkg9a", {"man9/man1/file9.1": "old"})
        stow_env.create_package("pkg9b", {"man9/man1/file9.1": "new"})

        def setup():
            stow_env.create_target_dir("man9/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg9a"])

        def check(env):
            check_link(
                env, "man9/man1/file9.1", "../../../stow/pkg9b/man9/man1/file9.1"
            )

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=man9", "pkg9b"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_defer_to_already_stowed(self, stow_env):
        """Defer to already stowed paths."""
        stow_env.create_package("pkg10a", {"man10/man1/file10.1": "first"})
        stow_env.create_package("pkg10b", {"man10/man1/file10.1": "second"})

        def setup():
            stow_env.create_target_dir("man10/man1")
            stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg10a"])

        def check(env):
            check_link(
                env, "man10/man1/file10.1", "../../../stow/pkg10a/man10/man1/file10.1"
            )

        # Defer is a planning decision, check on simulate
        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--defer=man10", "pkg10b"],
            setup,
            check,
            check_on_simulate=True,
            compare_fs_ops=True,
        )

    def test_malformed_regex_in_ignore_file(self, stow_env):
        """A pattern the regex engine rejects while reading an ignore file
        is fatal: one message, a blank line after it, nothing on stdout,
        exit status 255, nothing stowed. The engine's wording of the
        complaint, and Perl's source location inside it, differ."""
        stow_env.create_package("pkgbad", {"file": "content"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkgbad", ".stow-local-ignore")
        with open(ignore_file, "w") as f:
            f.write("foo(\n")

        args = ["-t", stow_env.target_dir, "pkgbad"]

        stow_env.reset_target()
        perl_rc, perl_stdout, perl_stderr = stow_env.run_perl_stow(args)
        check_not_exists(stow_env, "file")

        stow_env.reset_target()
        python_rc, python_stdout, python_stderr = stow_env.run_python_stow(args)
        check_not_exists(stow_env, "file")

        assert perl_rc == python_rc == 255
        assert perl_stdout == python_stdout == ""
        for stderr in (perl_stderr, python_stderr):
            assert stderr.startswith("Failed to compile regexp: ")
            assert stderr.endswith("\n\n")
            assert len(stderr.rstrip("\n").splitlines()) == 1

    def test_inline_flag_regex_in_ignore_file(self, stow_env):
        """Perl's inline flag groups apply from where they appear to the
        end of the enclosing group, so an ignore pattern can turn case
        sensitivity off for itself."""
        stow_env.create_package("pkgif", {"MAN/f": "content", "keep/g": "content"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkgif", ".stow-local-ignore")
        with open(ignore_file, "w") as f:
            f.write("(?i)man\n")

        def setup():
            pass

        def check(env):
            check_not_exists(env, "MAN")
            check_link(env, "keep", "../stow/pkgif/keep")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "pkgif"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_inline_flag_regex_override(self, stow_env):
        """--override='(?i)MAN' repoints both spellings of an already
        stowed directory."""
        stow_env.create_package("pkgo1", {"MAN/f": "one", "man/g": "one"})
        stow_env.create_package("pkgo2", {"MAN/f": "two", "man/g": "two"})

        def setup():
            # Unfolded, so both spellings are individual links to pkgo1
            stow_env.create_target_dir("MAN")
            stow_env.create_target_dir("man")
            stow_env.create_target_link("MAN/f", "../../stow/pkgo1/MAN/f")
            stow_env.create_target_link("man/g", "../../stow/pkgo1/man/g")

        def check(env):
            check_link(env, "MAN/f", "../../stow/pkgo2/MAN/f")
            check_link(env, "man/g", "../../stow/pkgo2/man/g")

        run_both_tests(
            stow_env,
            ["-t", stow_env.target_dir, "--override=(?i)MAN", "pkgo2"],
            setup,
            check,
            check_on_simulate=False,
            compare_fs_ops=True,
        )

    def test_deep_tree_walks_to_the_bottom(self, stow_env):
        """A tree far deeper than Python's default recursion limit allows
        (which the mutually recursive planning routines exhaust at around
        330 levels) is walked all the way down, both stowing and
        unstowing. Perl reports its own "Deep recursion" runtime warnings,
        which have no Python equivalent, so those lines are dropped before
        comparing stderr."""
        depth = 400
        deep = "/".join(["s"] * depth)
        stow_env.create_package("pkgdeep", {deep + "/leaf": "content"})
        args = ["-t", stow_env.target_dir, "pkgdeep"]

        def drop_deep_recursion(text):
            return "".join(
                line
                for line in text.splitlines(True)
                if not line.startswith("Deep recursion on subroutine ")
            )

        results = {}
        for name, run in (
            ("perl", stow_env.run_perl_stow),
            ("python", stow_env.run_python_stow),
        ):
            stow_env.reset_target()
            stow_env.create_target_dir(deep)
            stow_rc, stow_stdout, stow_stderr = run(args)
            stowed = stow_env.get_filesystem_state()
            unstow_rc, unstow_stdout, unstow_stderr = run(["-D"] + args)
            results[name] = (
                stow_rc,
                stow_stdout,
                drop_deep_recursion(stow_stderr),
                stowed,
                unstow_rc,
                unstow_stdout,
                drop_deep_recursion(unstow_stderr),
                stow_env.get_filesystem_state(),
            )

        assert results["perl"][0] == results["python"][0] == 0
        assert results["perl"][4] == results["python"][4] == 0
        assert results["perl"] == results["python"]
        # The leaf really was reached
        assert (deep + "/leaf") in results["perl"][3]

    def test_percent_in_package_name_goes_through_sprintf(self, stow_env):
        """Fatal messages are formatted with sprintf after the offending
        name has been interpolated into them, so percent sequences in the
        name are conversions: "%%" collapses to one percent."""
        rc, _, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "a%%b"]
        )
        assert rc == 2
        assert stderr.endswith("does not contain package a%b\n")

    def test_percent_s_in_package_name_consumes_missing_argument(self, stow_env):
        """A conversion with no argument left formats undef and warns
        before the message it was formatting is printed."""
        rc, _, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "pkg%s-x"]
        )
        assert rc == 2
        # The harness drops the source location Perl names in the warning
        assert stderr.splitlines()[0] == "Missing argument in sprintf"
        assert stderr.endswith("does not contain package pkg-x\n")

    def test_unprintable_conversion_is_octal_escaped_in_the_warning(self, stow_env):
        """Perl quotes the offending conversion in its warning character by
        character, printing anything outside printable ASCII as a
        three-digit octal escape of its first byte."""
        rc, _, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "pkg%\x1fx"]
        )
        assert rc == 2
        assert stderr.splitlines()[0] == 'Invalid conversion in sprintf: "%\\037"'

    def test_percent_in_target_name_reaches_canon_path_message(self, stow_env):
        """The chdir failure message is formatted the same way, where a
        "% f" in the name consumes the following characters as a float."""
        target = os.path.join(stow_env.tmpdir, "tg%s-100%")
        os.makedirs(target)
        stow_env.create_package("pkgt", {"file": "content"})
        os.chmod(target, 0o600)
        try:
            perl = stow_env.run_perl_stow(["-t", target, "pkgt"])
            python = stow_env.run_python_stow(["-t", target, "pkgt"])
        finally:
            os.chmod(target, 0o755)

        assert perl[0] == python[0] == errno.EACCES
        for rc, stdout, stderr in (perl, python):
            assert stdout == ""
            assert normalize_newline_warnings(stderr).splitlines() == [
                "Missing argument in sprintf",
                "Missing argument in sprintf",
                "stow: ERROR: canon_path: cannot chdir to %s/tg-100 0.000000rom %s"
                % (stow_env.tmpdir, stow_env.stow_dir),
            ]

    def test_unreadable_package_subdir_is_fatal(self, stow_env):
        """A package subdirectory that cannot be read is fatal, and the
        exit status is the errno of the syscall that failed."""
        stow_env.create_package("pkgperm", {"bin/file": "content"})
        locked = os.path.join(stow_env.stow_dir, "pkgperm", "bin")
        os.chmod(locked, 0o000)
        try:
            rc, stdout, stderr, _ = assert_stow_match(
                stow_env, ["-t", stow_env.target_dir, "--no-folding", "pkgperm"]
            )
        finally:
            os.chmod(locked, 0o755)

        assert rc == errno.EACCES
        assert stdout == ""
        assert stderr.endswith("/pkgperm/bin (Permission denied)\n")
        assert stderr.startswith("stow: ERROR: cannot read directory: ")

    def test_denied_symlink_and_mkdir_are_fatal(self, stow_env):
        """A refused symlink() or mkdir() reports the errno text and exits
        with the errno itself."""
        stow_env.create_package("pkgro", {"bin/file1": "one", "bin/file2": "two"})

        def setup():
            os.chmod(stow_env.target_dir, 0o555)

        try:
            rc, stdout, stderr, _ = assert_stow_match(
                stow_env, ["-t", stow_env.target_dir, "pkgro"], setup
            )
            assert rc == errno.EACCES
            assert stdout == ""
            assert stderr == (
                "stow: ERROR: Could not create symlink: bin => ../stow/pkgro/bin"
                " (Permission denied)\n"
            )

            rc, stdout, stderr, _ = assert_stow_match(
                stow_env, ["-t", stow_env.target_dir, "--no-folding", "pkgro"], setup
            )
            assert rc == errno.EACCES
            assert stderr == (
                "stow: ERROR: Could not create directory: bin (Permission denied)\n"
            )
        finally:
            os.chmod(stow_env.target_dir, 0o755)

    def test_internal_error_banner(self, stow_env):
        """The internal error banner: a blank line, the message with the
        trace starting on the same line, two blank lines, then the closing
        note. Perl's Carp frames have no Python equivalent, so only the
        shape is compared; the exit status comes from the last failed
        syscall, as for any other fatal error."""
        stow_env.create_package("pkgie", {"f": "content"})

        def setup():
            stow_env.create_target_dir("marked")
            with open(os.path.join(stow_env.target_dir, "marked", ".stow"), "w"):
                pass
            stow_env.create_target_link("f", "marked")

        results = []
        for run in (stow_env.run_perl_stow, stow_env.run_python_stow):
            stow_env.reset_target()
            setup()
            results.append(run(["-t", stow_env.target_dir, "pkgie"]))

        perl, python = results
        assert perl[0] == python[0] == 2
        for rc, stdout, stderr in results:
            assert stdout == ""
            head = "\nstow: INTERNAL ERROR: find_stowed_path() called directly on stow dir"
            assert stderr.startswith(head)
            # The trace starts on the message's own line
            assert len(stderr.splitlines()[1]) > len(head)
            assert "\n\n\nThis _is_ a bug. Please submit a bug report so we can fix it! :-)\n" in stderr
            assert stderr.endswith(" for how to do this.\n")

    def test_link_destination_zero_is_unreadable(self, stow_env):
        """Perl guards readlink() with "or error(...)", so a link whose
        destination is the string "0" counts as unreadable. Stowing a
        package containing one is fatal and nothing is created."""
        stow_env.create_package("pkgz", {"other.txt": "content"})
        os.symlink("0", os.path.join(stow_env.stow_dir, "pkgz", "link"))

        def setup():
            pass

        rc, stdout, stderr, state = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "pkgz"], setup
        )
        assert rc == errno.ENOENT
        assert stdout == ""
        assert stderr == (
            "stow: ERROR: Could not read link: ../stow/pkgz/link"
            " (No such file or directory)\n"
        )
        assert state == {}

    def test_existing_target_link_to_zero_is_unreadable(self, stow_env):
        """An existing target link pointing at "0" is unreadable too, so
        stowing over it is fatal rather than a conflict."""
        stow_env.create_package("pkgz2", {"link": "content"})

        def setup():
            stow_env.create_target_link("link", "0")

        rc, stdout, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "pkgz2"], setup
        )
        assert rc == errno.ENOENT
        assert stdout == ""
        assert stderr == (
            "stow: ERROR: Could not read link: link (No such file or directory)\n"
        )

    def test_entries_are_processed_in_byte_order(self, stow_env):
        """Perl sorts what readdir gives it as byte strings, so a name
        starting with 0x80 comes after "zzz" and before one starting with
        0xff, wherever the code points of those bytes would land. The raw
        comparison also pins that the trace prints the name's own bytes."""
        pkg_dir = os.path.join(stow_env.stow_dir, "pkgbo").encode()
        os.makedirs(pkg_dir)
        for name in (b"Zebra", b"_under", b"apple", b"zzz",
                     b"\xc3\xa9tude", b"\x80raw", b"\xffraw"):
            with open(pkg_dir + b"/" + name, "wb") as f:
                f.write(b"x")

        def setup():
            pass

        rc, stdout, stderr = assert_stow_match_raw(
            stow_env, ["-t", stow_env.target_dir, "-v3", "pkgbo"], setup
        )
        assert rc == 0
        assert stdout == b""
        stowed = [
            line[len(b"Stowing entry ../stow / pkgbo / "):]
            for line in stderr.split(b"\n")
            if line.startswith(b"Stowing entry ")
        ]
        assert stowed == [
            b"Zebra", b"_under", b"apple", b"zzz",
            b"\x80raw", b"\xc3\xa9tude", b"\xffraw",
        ]

    def test_ignore_record_whitespace_is_ascii_only(self, stow_env):
        """The records of an ignore file are bytes, so the whitespace Perl
        strips from them and the whitespace that starts a trailing comment
        are the ASCII ones. A no-break space in front of a pattern and a
        line separator in the middle of one both stay part of the
        pattern, which then fails to match the plain file name."""
        for package, record in (
            ("pkgws1", b"\xc2\xa0bar\n"),
            ("pkgws2", b"bar\xe2\x80\xa8#c\n"),
        ):
            stow_env.create_package(package, {"bar": "x", "keep": "x"})
            ignore = os.path.join(stow_env.stow_dir, package, ".stow-local-ignore")
            with open(ignore, "wb") as f:
                f.write(record)

            def setup():
                pass

            def check(env, package=package):
                check_link(env, "bar", "../stow/%s/bar" % package)
                check_link(env, "keep", "../stow/%s/keep" % package)

            run_both_tests(
                stow_env,
                ["-t", stow_env.target_dir, package],
                setup,
                check,
                check_on_simulate=False,
                env_vars={"LC_ALL": "en_US.UTF-8"},
            )

    def test_unreadable_ignore_file_is_reopened_at_every_node(self, stow_env):
        """Only a successfully read ignore file is memoized, so one that
        cannot be opened is tried again for every entry, and each attempt
        traces the failure."""
        stow_env.create_package("pkgui", {"a": "x", "b": "x"})
        ignore = os.path.join(stow_env.stow_dir, "pkgui", ".stow-local-ignore")
        with open(ignore, "w") as f:
            f.write("zzz\n")
        os.chmod(ignore, 0o000)

        def setup():
            pass

        rc, stdout, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "-v5", "pkgui"], setup
        )
        assert rc == 0
        assert stdout == ""
        failures = [
            line for line in stderr.splitlines()
            if line.endswith("/.stow-local-ignore: Permission denied")
        ]
        assert len(failures) == 3
        assert failures[0] == (
            "        Failed to open ../stow/pkgui/.stow-local-ignore:"
            " Permission denied"
        )
        assert "Using memoized regexps from" not in stderr

    def test_readable_ignore_file_is_memoized_after_the_first_read(self, stow_env):
        """A readable ignore file is read once and reported as memoized on
        every later consultation."""
        stow_env.create_package("pkgmi", {"a": "x", "b": "x"})
        ignore = os.path.join(stow_env.stow_dir, "pkgmi", ".stow-local-ignore")
        with open(ignore, "w") as f:
            f.write("zzz\n")

        def setup():
            pass

        rc, stdout, stderr, _ = assert_stow_match(
            stow_env, ["-t", stow_env.target_dir, "-v5", "pkgmi"], setup
        )
        assert rc == 0
        assert stdout == ""
        memoized = [
            line for line in stderr.splitlines()
            if "Using memoized regexps from" in line
        ]
        assert memoized == [
            "        Using memoized regexps from ../stow/pkgmi/.stow-local-ignore"
        ] * 2

    def test_ignore_regexps_are_printed_as_perl_stringifies_them(self, stow_env):
        """A compiled regexp interpolated into the trace comes out as
        Perl's qr// stringification, "(?^:PATTERN)" — for the ignore file
        regexps and for a --ignore pattern alike."""
        stow_env.create_package("pkgqr", {"bar": "x", "keep": "x"})
        ignore = os.path.join(stow_env.stow_dir, "pkgqr", ".stow-local-ignore")
        with open(ignore, "w") as f:
            f.write("bar\n")

        def setup():
            pass

        rc, stdout, stderr, _ = assert_stow_match(
            stow_env,
            ["-t", stow_env.target_dir, "-v5", "--ignore=keep", "pkgqr"],
            setup,
        )
        assert rc == 0
        assert stdout == ""
        assert (
            "        Ignore list regexp for segments: /(?^:^(bar)$)/" in stderr
        )
        assert (
            "        Ignore list regexp for paths:    "
            "/(?^:(^|/)(^/\\.stow\\-local\\-ignore$)(/|$))/" in stderr
        )
        assert (
            "    Ignoring path keep due to --ignore=(?^:(keep)\\z)" in stderr
        )
