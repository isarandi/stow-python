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
Pinning tests for documented, intentional divergences from Perl stow.

The hypothesis strategies deliberately exclude the input classes covered
here (see docs/perl-differences.md), which means the suite would otherwise
be structurally unable to notice if these divergences silently grew or
changed. Each test asserts BOTH the Perl behavior and the intended Python
behavior, so any drift on either side fails loudly.
"""

import os
import stat as stat_module

import pytest

from conftest import check_not_exists


needs_nonroot = pytest.mark.skipif(
    os.geteuid() == 0, reason="permission checks are bypassed as root"
)


class TestDocumentedDivergences:
    def test_empty_package_name(self, stow_env):
        """perl-differences.md #6: empty package name.

        Perl treats '' as a package whose path is the stow dir itself and
        happily stows its contents (linking sibling packages into the
        target); Python rejects the empty name.
        """
        stow_env.create_package("pkg", {"file": "content"})

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(["-t", stow_env.target_dir, ""])
        assert rc != 0, "Python must reject an empty package name"
        assert "empty" in stderr.lower()
        check_not_exists(stow_env, "file")

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_perl_stow(["-t", stow_env.target_dir, ""])
        assert rc == 0, f"Perl stows the '' package: {stderr}"
        # Perl linked the stow dir's contents (the pkg directory) into target
        assert os.path.islink(os.path.join(stow_env.target_dir, "pkg"))

    def test_backup_file_in_newline_dir_ignored_only_by_python(self, stow_env):
        """perl-differences.md #3: newline breaks Perl's ignore check.

        Inside a directory named "\\n", a file "backup~" should be ignored
        per the default .+~ pattern. Perl's ignore check malfunctions on
        the newline-containing path and stows the file anyway; Python
        correctly ignores it. The target dir must pre-exist so the
        contents are considered per-file rather than folded away.
        """
        stow_env.create_package("pkg", {"\n/backup~": "content"})

        stow_env.reset_target()
        stow_env.create_target_dir("\n")
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "pkg"]
        )
        assert rc == 0, f"Python stow failed: {stderr}"
        check_not_exists(stow_env, "\n/backup~")  # ignored by ~ rule

        stow_env.reset_target()
        stow_env.create_target_dir("\n")
        rc, stdout, stderr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert rc == 0, f"Perl stow failed: {stderr}"
        # Perl's ignore check malfunctioned: the link exists
        assert os.path.islink(os.path.join(stow_env.target_dir, "\n", "backup~"))

    def test_newline_warnings_only_from_perl(self, stow_env):
        """perl-differences.md #4: Perl warns on failed stat of a name
        ending in newline; Python intentionally emits no such warning."""
        stow_env.create_package("pkg", {"x\n": "content"})

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "pkg"]
        )
        assert rc == 0, f"Python stow failed: {stderr}"
        assert "Unsuccessful" not in stderr

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert rc == 0, f"Perl stow failed: {stderr}"
        assert "Unsuccessful" in stderr, "Perl should warn about the newline"

    def test_foldable_empty_dest_preserves_foreign_link(self, stow_env):
        """perl-differences.md #14: foldable('') data-loss bug.

        pkg1 and pkg2 both populate dir/. With both stowed, target/dir is a
        real directory holding file1 and file2 symlinks. The user then adds
        an unrelated symlink `a -> file1` whose destination has NO slash,
        which is what trips Perl's foldable('') bug. Unstowing pkg2 makes
        dir foldable in Perl's eyes: Perl folds dir back into a single
        symlink and DESTROYS the user's link `a` (data loss). Python treats
        the directory as not foldable, leaving dir real and `a` intact.
        """
        stow_env.create_package("pkg1", {"dir/file1": "one"})
        stow_env.create_package("pkg2", {"dir/file2": "two"})

        dir_path = os.path.join(stow_env.target_dir, "dir")
        a_path = os.path.join(stow_env.target_dir, "dir", "a")

        # Perl: folds dir into a symlink; the user's link `a` is destroyed.
        stow_env.reset_target()
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg1", "pkg2"])
        os.symlink("file1", a_path)
        rc, stdout, stderr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "-D", "pkg2"]
        )
        assert rc == 0, f"Perl unstow failed: {stderr}"
        assert os.path.islink(dir_path), "Perl folds dir into a symlink"
        assert os.readlink(dir_path) == "../stow/pkg1/dir"
        # dir is now a symlink into pkg1, which has no `a`: the link is gone.
        assert not os.path.lexists(a_path), "Perl destroyed the user's link a"

        # Python: dir stays a real directory and `a` survives with its dest.
        stow_env.reset_target()
        stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg1", "pkg2"])
        os.symlink("file1", a_path)
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "-D", "pkg2"]
        )
        assert rc == 0, f"Python unstow failed: {stderr}"
        assert not os.path.islink(dir_path), "Python keeps dir a real directory"
        assert os.path.isdir(dir_path)
        assert os.path.islink(a_path), "Python preserves the user's link a"
        assert os.readlink(a_path) == "file1"

    def test_nonascii_option_bundle_byte_vs_char(self, stow_env):
        """perl-differences.md #2: '-é' bundle.

        Perl scans the option string byte by byte, so the two UTF-8 bytes
        of é each produce an 'Unknown option' line; Python scans by
        character and reports a single line. Both exit 1.
        """
        stow_env.create_package("pkg", {"file": "content"})

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "-é", "pkg"])
        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "-é", "pkg"]
        )

        assert prc == 1 and yrc == 1
        assert perr.count("Unknown option:") == 2, f"Perl stderr: {perr!r}"
        assert yerr.count("Unknown option:") == 1, f"Python stderr: {yerr!r}"

    def test_plus_v_getopt_compat_vs_package(self, stow_env):
        """perl-differences.md #5: '+v'.

        Perl's deprecated getopt_compat treats '+v' like '-v' (verbose) and
        stows pkg; Python only special-cases '+n', so '+v' is a package name
        and stow fails because no such package exists.
        """
        stow_env.create_package("pkg", {"file": "content"})

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "+v", "pkg"])
        assert prc == 0, f"Perl should treat +v as -v: {perr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "file"))

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "+v", "pkg"]
        )
        assert yrc != 0, "Python treats +v as a (missing) package"
        assert "+v" in yerr
        check_not_exists(stow_env, "file")

    def test_verbose_value_gobbling(self, stow_env):
        """perl-differences.md #10: '-v 3 pkg' and '--verbose 3 pkg'.

        Perl's 'verbose|v:+' spec gobbles the following integer as the
        verbosity level, in the short and the long form alike, and stows
        pkg; Python treats 3 as a package name and fails because no such
        package exists.
        """
        stow_env.create_package("pkg", {"file": "content"})

        for verbose_form in ("-v", "--verbose"):
            stow_env.reset_target()
            prc, _, perr = stow_env.run_perl_stow(
                ["-t", stow_env.target_dir, verbose_form, "3", "pkg"]
            )
            assert prc == 0, f"Perl should gobble 3 after {verbose_form}: {perr}"
            assert os.path.islink(os.path.join(stow_env.target_dir, "file"))

            stow_env.reset_target()
            yrc, _, yerr = stow_env.run_python_stow(
                ["-t", stow_env.target_dir, verbose_form, "3", "pkg"]
            )
            assert yrc != 0, "Python treats 3 as a (missing) package"
            assert "3" in yerr
            check_not_exists(stow_env, "file")

    def test_ignore_perl_regex_QE_clause(self, stow_env):
        r"""perl-differences.md #12: --ignore='\Qfoo.\E'.

        Perl warns 'Unrecognized escape' but proceeds and stows; Python
        rejects the Perl-only \Q...\E regex syntax with a clean 'Failed to
        compile regexp' error (exit 1, no traceback) and stows nothing.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "--ignore=\\Qfoo.\\E", "pkg"]
        )
        assert prc == 0, f"Perl should warn but proceed: {perr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "bin"))
        assert "Unrecognized escape" in perr

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--ignore=\\Qfoo.\\E", "pkg"]
        )
        assert yrc == 1
        assert "Failed to compile regexp" in yerr
        assert "Traceback" not in yerr
        check_not_exists(stow_env, "bin")

    def test_chkstow_stow_dir_zero_falls_back(self, stow_env):
        """perl-differences.md #16: chkstow with STOW_DIR="0".

        Perl uses $ENV{STOW_DIR} in boolean context, and "0" is false in
        Perl, so chkstow falls back to scanning the default /usr/local and
        never sees the local ./0 tree. Python treats "0" as an ordinary
        non-empty directory name, scans it, and reports the dangling link
        inside. Pin: the bogus link appears only in Python's output.
        """
        # chkstow runs with cwd=target_dir, so ./0 lives under target.
        zero = os.path.join(stow_env.target_dir, "0")
        os.makedirs(zero)
        os.symlink("nonexistent-target", os.path.join(zero, "bogus"))

        prc, pout, _ = stow_env.run_perl_chkstow(["-b"], env={"STOW_DIR": "0"})
        yrc, yout, _ = stow_env.run_python_chkstow(["-b"], env={"STOW_DIR": "0"})

        assert prc == 0 and yrc == 0
        assert "0/bogus" in yout, "Python scans ./0 and reports the dangling link"
        assert "0/bogus" not in pout, "Perl fell back to /usr/local, never saw ./0"

    def test_percent_in_package_name_garbles_perl_message(self, stow_env):
        """perl-differences.md #26: error() runs the message through sprintf.

        Perl's error() is `die ... sprintf($format, @args) ...` with no
        args, so a `%` that came from the package name is consumed as a
        conversion: `a%%b` is reported as `a%b`, and `pkg%s-x` as `pkg-x`
        plus a `Missing argument in sprintf` warning. We print the name
        the user typed.
        """
        stow_env.create_package("pkg", {"file": "content"})

        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "a%%b"])
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "a%%b"])
        assert prc != 0 and yrc != 0
        assert "does not contain package a%b" in perr, f"Perl stderr: {perr!r}"
        assert "does not contain package a%%b" in yerr, f"Python stderr: {yerr!r}"

        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg%s-x"])
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg%s-x"])
        assert prc != 0 and yrc != 0
        assert "Missing argument in sprintf" in perr
        assert "does not contain package pkg-x" in perr, f"Perl stderr: {perr!r}"
        assert "does not contain package pkg%s-x" in yerr, f"Python stderr: {yerr!r}"

    def test_cwd_restored_on_fatal_error(self, stow_env):
        """perl-differences.md #27: the cwd is restored when a run dies.

        Perl's within_target_do has no eval, so a fatal error skips the
        restore and the process dies inside the target; we restore in a
        finally, which adds exactly one `cwd restored to` line at -v3.
        Every other trace line must still be byte-identical.
        """
        stow_env.create_package("pkg", {"file": "content"})
        args = ["-v3", "-t", stow_env.target_dir, "-D", "nosuchpkg"]

        prc, _, perr = stow_env.run_perl_stow(args)
        yrc, _, yerr = stow_env.run_python_stow(args)
        assert prc != 0 and yrc != 0
        assert "does not contain package nosuchpkg" in perr
        assert "does not contain package nosuchpkg" in yerr
        assert "cwd restored to" not in perr, "Perl dies inside the target"
        assert "cwd restored to" in yerr, "Python restores the caller's cwd"

        python_rest = [ln for ln in yerr.splitlines() if "cwd restored to" not in ln]
        assert python_rest == perr.splitlines(), (
            "only the restore line may differ:\nPerl: %r\nPython: %r" % (perr, yerr)
        )

    def test_posix_character_class_rejected_not_misread(self, stow_env):
        """perl-differences.md #28: [[:alpha:]] means different things.

        Perl reads it as a character class and ignores `abc`; Python's re
        would read it as the set `[[:alph]` plus a literal `]` and ignore
        neither, so we refuse to compile it with a fix-it hint instead of
        silently applying a different rule.
        """
        stow_env.create_package("pkg", {"abc": "a", "12": "b"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")
        with open(ignore_file, "w") as f:
            f.write(".*[[:alpha:]]\n")

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc == 0, f"Perl stows what its class does not match: {perr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "12"))
        assert not os.path.lexists(os.path.join(stow_env.target_dir, "abc"))

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert yrc == 1
        assert "Failed to compile regexp" in yerr
        assert "POSIX character classes" in yerr, f"fix-it hint expected: {yerr!r}"
        assert "Traceback" not in yerr
        check_not_exists(stow_env, "12")
        check_not_exists(stow_env, "abc")

        # Same rejection through the CLI options, where the silent
        # divergence would otherwise change the resulting tree
        os.remove(ignore_file)
        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "--override=[[:alpha:]]+", "pkg"]
        )
        assert yrc == 1
        assert "POSIX character classes" in yerr
        assert "Traceback" not in yerr

    def test_byte_vs_character_counting_in_pattern(self, stow_env):
        """perl-differences.md #28: byte-mode classes match, counting does not.

        `\\w+` now selects the same names on both sides (user patterns are
        compiled with re.ASCII, like Perl's byte-mode engine), but a
        pattern that COUNTS - `^.....$` - still counts bytes in Perl and
        characters here, so a five-byte four-character name diverges.
        """
        stow_env.create_package("pkg", {"café": "a", "abcde": "b"})
        ignore_file = os.path.join(stow_env.stow_dir, "pkg", ".stow-local-ignore")

        with open(ignore_file, "w") as f:
            f.write("\\w+\n")
        for run in (stow_env.run_perl_stow, stow_env.run_python_stow):
            stow_env.reset_target()
            rc, _, stderr = run(["-t", stow_env.target_dir, "pkg"])
            assert rc == 0, stderr
            assert os.path.islink(os.path.join(stow_env.target_dir, "café")), (
                "\\w is ASCII-only in both engines, so café is not ignored"
            )
            assert not os.path.lexists(os.path.join(stow_env.target_dir, "abcde"))

        with open(ignore_file, "w") as f:
            f.write("^.....$\n")
        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc == 0, perr
        assert not os.path.lexists(os.path.join(stow_env.target_dir, "café")), (
            "Perl counts the five bytes of café"
        )

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert yrc == 0, yerr
        assert os.path.islink(os.path.join(stow_env.target_dir, "café")), (
            "Python counts the four characters of café"
        )

    def test_dotdot_prefixed_directory_collapse(self, stow_env):
        """perl-differences.md #29: a component named `..d` blocks Perl's
        `X/..` removal, so Perl stops recognizing its own symlinks - a
        second stow reports a conflict where we are idempotent."""
        stow_env.create_package("pkg", {"..d/f1": "x"})

        stow_env.reset_target()
        stow_env.create_target_dir("..d")
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc == 0, f"Perl's first stow succeeds: {perr}"
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc == 1, "Perl no longer recognizes the link it just created"
        assert "existing target is not owned by stow: ..d/f1" in perr

        stow_env.reset_target()
        stow_env.create_target_dir("..d")
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert yrc == 0, yerr
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert yrc == 0, f"restow must be idempotent: {yerr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "..d", "f1"))

    @needs_nonroot
    def test_chkstow_cannot_enter_directory_warning(self, stow_env):
        """perl-differences.md #18: File::Find's warnings carry Perl's
        ` at <script> line N.` suffix; we print the message alone.

        The message text, the skipped subtree and the exit code must all
        agree - a diagnostic tool must not report an unqualified all-clear
        for a directory it could not inspect.
        """
        noread = os.path.join(stow_env.target_dir, "noread")
        os.makedirs(noread)
        os.symlink("nowhere", os.path.join(noread, "hidden"))
        os.symlink("nowhere", os.path.join(stow_env.target_dir, "bogus_top"))
        os.chmod(noread, 0)
        try:
            prc, pout, perr = stow_env.run_perl_chkstow(["-b", "-t", "."])
            yrc, yout, yerr = stow_env.run_python_chkstow(["-b", "-t", "."])
        finally:
            os.chmod(noread, stat_module.S_IRWXU)

        assert prc == 0 and yrc == 0
        assert pout == yout == "Bogus link: ./bogus_top\n"
        warning = "Can't cd to (./) noread: Permission denied"
        assert perr.startswith(warning), f"Perl stderr: {perr!r}"
        assert " line " in perr, f"Perl warn suffix expected: {perr!r}"
        assert yerr == warning + "\n"


class TestZeroIsFalseInPerl:
    """Pins for perl-differences.md #25.

    Perl has no boolean type and the one-character string "0" is false, so
    anything literally named 0 takes the "absent" or "failed" branch there.
    Each test asserts Perl's branch and ours.
    """

    def test_symlink_destination_zero_aborts_perl(self, stow_env):
        """readlink returning "0" reads as failure to Perl (Stow.pm:2103),
        so the whole run dies and nothing is stowed."""
        stow_env.create_package("pkg", {})
        os.symlink("0", os.path.join(stow_env.stow_dir, "pkg", "link"))

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc != 0
        assert "Could not read link" in perr, f"Perl stderr: {perr!r}"
        check_not_exists(stow_env, "link")

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert yrc == 0, f"Python stow failed: {yerr}"
        assert os.readlink(os.path.join(stow_env.target_dir, "link")) == (
            "../stow/pkg/link"
        )

    def test_foreign_link_to_zero_aborts_perl_unstow(self, stow_env):
        """An unrelated `z -> 0` anywhere in the target stops Perl's whole
        unstow (Stow.pm:1195); we unstow normally and leave z alone."""
        stow_env.create_package("pkg", {"f": "hi"})

        for run, expect_removed in (
            (stow_env.run_perl_stow, False),
            (stow_env.run_python_stow, True),
        ):
            stow_env.reset_target()
            stow_env.create_target_link("f", "../stow/pkg/f")
            stow_env.create_target_link("z", "0")
            rc, _, stderr = run(["-t", stow_env.target_dir, "-D", "pkg"])
            removed = not os.path.lexists(os.path.join(stow_env.target_dir, "f"))
            assert removed is expect_removed, f"{run.__name__}: {stderr!r}"
            assert (rc == 0) is expect_removed
            assert os.path.lexists(os.path.join(stow_env.target_dir, "z"))

    def test_package_named_zero_blocks_folding(self, stow_env):
        """link_owned_by_package returns the package NAME, and Perl tests
        it for truth (Stow.pm:1313), so a directory whose remaining links
        belong to a package named 0 is never folded."""
        stow_env.create_package("0", {"dir/file0": "a"})
        stow_env.create_package("p1", {"dir/file1": "b"})
        dir_path = os.path.join(stow_env.target_dir, "dir")

        stow_env.reset_target()
        stow_env.run_perl_stow(["-t", stow_env.target_dir, "0", "p1"])
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "-D", "p1"])
        assert prc == 0, f"Perl unstow failed: {perr}"
        assert os.path.isdir(dir_path) and not os.path.islink(dir_path), (
            "Perl leaves dir a real directory"
        )

        stow_env.reset_target()
        stow_env.run_python_stow(["-t", stow_env.target_dir, "0", "p1"])
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "-D", "p1"])
        assert yrc == 0, f"Python unstow failed: {yerr}"
        assert os.path.islink(dir_path), "Python folds dir back into a symlink"
        assert os.readlink(dir_path) == "../stow/0/dir"

    def test_stow_dir_parent_zero_changes_default_target(self, stow_env):
        """`parent($options->{dir}) || '.'` (bin/stow:644) turns the parent
        directory named 0 into the current directory."""
        pkg = os.path.join(stow_env.stow_dir, "0", "sub", "pkg")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "file.txt"), "w") as f:
            f.write("hello")

        # Both run with cwd = the stow dir, so Perl's "." is that directory
        perl_link = os.path.join(stow_env.stow_dir, "file.txt")
        python_link = os.path.join(stow_env.stow_dir, "0", "file.txt")

        prc, _, perr = stow_env.run_perl_stow(["--dir", "0/sub", "pkg"])
        assert prc == 0, f"Perl stow failed: {perr}"
        assert os.path.islink(perl_link), "Perl targets the current directory"
        assert not os.path.lexists(python_link)
        os.unlink(perl_link)

        yrc, _, yerr = stow_env.run_python_stow(["--dir", "0/sub", "pkg"])
        assert yrc == 0, f"Python stow failed: {yerr}"
        assert os.path.islink(python_link), "Python targets the directory named 0"
        assert not os.path.lexists(perl_link)

    def test_tilde_zero_is_a_bare_tilde_in_perl(self, stow_env):
        """`$1 ? (getpwnam($1))[7] : ($ENV{HOME} || ...)` (bin/stow:776):
        the captured user name "0" is false, so Perl takes the bare-tilde
        branch. Not covered by #21, which is about an unknown user."""
        stow_env.create_package("pkg", {"file": "content"})
        expanded = os.path.join(stow_env.tmpdir, "t")
        os.makedirs(expanded)
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write("--target=~0/t\n")

        prc, _, perr = stow_env.run_perl_stow(["pkg"])
        assert prc == 0, f"Perl expands ~0 like ~: {perr}"
        assert os.path.islink(os.path.join(expanded, "file"))
        os.unlink(os.path.join(expanded, "file"))

        yrc, _, yerr = stow_env.run_python_stow(["pkg"])
        assert yrc != 0, "Python looks 0 up as a user name and keeps the path"
        assert "~0/t" in yerr, f"Python stderr: {yerr!r}"
        assert not os.path.lexists(os.path.join(expanded, "file"))

    def test_home_zero_falls_through_to_logdir_in_perl(self, stow_env):
        """`$ENV{HOME} || $ENV{LOGDIR} || (getpwuid($<))[7]`
        (bin/stow:778): HOME=0 is false, so Perl uses LOGDIR."""
        stow_env.create_package("pkg", {"file": "content"})
        logdir = os.path.join(stow_env.tmpdir, "logdir")
        os.makedirs(os.path.join(logdir, "tgt"))
        os.makedirs(os.path.join(stow_env.stow_dir, "0", "tgt"))
        # cwd is the stow dir, so ./.stowrc is the one that gets read
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write("--target=~/tgt\n")

        env = {"HOME": "0", "LOGDIR": logdir}
        perl_link = os.path.join(logdir, "tgt", "file")
        python_link = os.path.join(stow_env.stow_dir, "0", "tgt", "file")

        prc, _, perr = stow_env.run_perl_stow(["pkg"], env=env)
        assert prc == 0, f"Perl stow failed: {perr}"
        assert os.path.islink(perl_link), "Perl skipped HOME=0 for LOGDIR"
        os.unlink(perl_link)

        yrc, _, yerr = stow_env.run_python_stow(["pkg"], env=env)
        assert yrc == 0, f"Python stow failed: {yerr}"
        assert os.path.islink(python_link), "Python honors the directory named 0"
        assert not os.path.lexists(perl_link)


class TestExitCodeAndWarningDivergences:
    """Pins for perl-differences.md #13 and #18-#23."""

    def test_package_is_file_exit_codes(self, stow_env):
        """#13: the package path exists but is a plain file.

        Both sides print the identical 'does not contain package' error;
        Perl exits with its leftover $! (ENOENT=2 from probing the absent
        .stowrc files earlier in the run), Python with the semantically
        correct ENOTDIR=20. Covers both the stow and unstow planners.
        """
        stow_env.create_package("pkg", {"file": "content"})
        with open(os.path.join(stow_env.stow_dir, "pkgfile"), "w") as f:
            f.write("not a directory")

        for action_args in ([], ["-D"]):
            stow_env.reset_target()
            prc, _, perr = stow_env.run_perl_stow(
                ["-t", stow_env.target_dir] + action_args + ["pkgfile"]
            )
            stow_env.reset_target()
            yrc, _, yerr = stow_env.run_python_stow(
                ["-t", stow_env.target_dir] + action_args + ["pkgfile"]
            )
            assert "does not contain package pkgfile" in perr
            assert perr == yerr, f"stderr must be identical: {perr!r} vs {yerr!r}"
            assert "Traceback" not in yerr
            assert prc == 2, "Perl: leftover ENOENT from the .stowrc probes"
            assert yrc == 20, "Python: ENOTDIR, the check that actually failed"

    def test_die_exit_codes_slash_package(self, stow_env):
        """#13: 'stow a/b' exits 2 (no rc file) or 255 (rc file present)
        in Perl — whatever $! happens to hold — and always 1 in Python."""
        stow_env.create_package("pkg", {"file": "content"})

        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "a/b"])
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "a/b"])
        assert "Slashes are not permitted" in perr
        assert "Slashes are not permitted" in yerr
        assert prc == 2, "Perl: ENOENT left over from probing absent .stowrc"
        assert yrc == 1

        # When the LAST rc-file probe succeeds, $! is clean and Perl's die
        # falls back to 255; Python is unaffected. Perl probes ~/.stowrc
        # then ./.stowrc, so the cwd one (cwd is the stow dir) must exist —
        # a readable ~/.stowrc alone still leaves ENOENT from the ./.stowrc
        # probe.
        with open(os.path.join(stow_env.stow_dir, ".stowrc"), "w") as f:
            f.write("")
        prc, _, _ = stow_env.run_perl_stow(["-t", stow_env.target_dir, "a/b"])
        yrc, _, _ = stow_env.run_python_stow(["-t", stow_env.target_dir, "a/b"])
        assert prc == 255, "Perl: die with $! == 0 exits 255"
        assert yrc == 1

    def test_stowrc_is_a_directory(self, stow_env):
        """#20: ~/.stowrc is a directory.

        Perl's open() of a directory succeeds, the read fails, and the
        pending handle error surfaces at close(): 'Could not close open
        file', exit 21 (EISDIR). Python's open() fails up front with a
        truthful 'Could not open ... for reading' and exit 1.
        """
        stow_env.create_package("pkg", {"file": "content"})
        os.mkdir(os.path.join(stow_env.tmpdir, ".stowrc"))

        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "pkg"])
        yrc, _, yerr = stow_env.run_python_stow(["-t", stow_env.target_dir, "pkg"])
        assert prc == 21, f"Perl: EISDIR via $! at close; stderr: {perr!r}"
        assert "Could not close open file" in perr
        assert yrc == 1
        assert "Could not open" in yerr and "for reading" in yerr
        assert "Traceback" not in yerr

    def test_tilde_unknown_user_in_stowrc(self, stow_env):
        """#21: '--target=~nosuchuser/t' in .stowrc.

        Perl substitutes the unknown user's home as the EMPTY string
        (with an uninitialized-value warning), mangling the path to
        '/t'; Python keeps the literal path. Both then fail on a
        nonexistent target directory, naming different paths.
        """
        stow_env.create_package("pkg", {"file": "content"})
        with open(os.path.join(stow_env.tmpdir, ".stowrc"), "w") as f:
            f.write(f"-d {stow_env.stow_dir}\n")
            f.write("--target=~nosuchuserqz042/t\n")

        prc, _, perr = stow_env.run_perl_stow(["pkg"])
        yrc, _, yerr = stow_env.run_python_stow(["pkg"])
        assert prc != 0 and yrc != 0
        assert "Use of uninitialized value" in perr
        assert "'/t'" in perr, f"Perl mangles the target to /t: {perr!r}"
        assert "~nosuchuserqz042/t" in yerr, "Python keeps the literal path"
        assert "Use of uninitialized value" not in yerr

    def test_home_unset_perl_warning_noise(self, stow_env):
        """#19: with HOME unset, Perl emits 'Use of uninitialized value'
        warnings on an otherwise successful run; Python is silent."""
        stow_env.create_package("pkg", {"file": "content"})
        args = ["-d", stow_env.stow_dir, "-t", stow_env.target_dir, "pkg"]

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(args, env={"HOME": None})
        assert prc == 0, f"Perl run should succeed: {perr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "file"))
        assert "Use of uninitialized value" in perr

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(args, env={"HOME": None})
        assert yrc == 0, f"Python run should succeed: {yerr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "file"))
        assert yerr == ""

    def test_plus_n_deprecation_warning(self, stow_env):
        """#22: '+n' simulates on both sides; Python adds one deprecation
        warning line that Perl does not print."""
        stow_env.create_package("pkg", {"file": "content"})
        simulate_line = "WARNING: in simulation mode so not modifying filesystem.\n"

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(["-t", stow_env.target_dir, "+n", "pkg"])
        assert prc == 0
        assert perr == simulate_line
        check_not_exists(stow_env, "file")

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "+n", "pkg"]
        )
        assert yrc == 0
        assert yerr == "Warning: +n is deprecated, use -n instead\n" + simulate_line
        check_not_exists(stow_env, "file")

    def test_v5_ignore_regexp_lines_unmatchable(self, stow_env):
        """#23: at -v5 the two 'Ignore list regexp' lines can never match
        (Perl's qr stringification plus per-process hash-order random
        alternation); every OTHER -v5 stderr line must be byte-identical.
        """
        stow_env.create_package("pkg", {"bin/file": "content"})
        args = ["-v5", "-n", "-t", stow_env.target_dir, "pkg"]

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(args)
        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(args)
        assert prc == 0 and yrc == 0

        def split(text):
            lines = text.splitlines()
            regexp_lines = [ln for ln in lines if "Ignore list regexp" in ln]
            other_lines = [ln for ln in lines if "Ignore list regexp" not in ln]
            return regexp_lines, other_lines

        perl_regexp, perl_rest = split(perr)
        python_regexp, python_rest = split(yerr)
        assert len(perl_regexp) == 2 and all("(?^:" in ln for ln in perl_regexp)
        assert len(python_regexp) == 2 and not any("(?^:" in ln for ln in python_regexp)
        assert perl_rest == python_rest, "all other -v5 lines must match exactly"

    def test_chkstow_cant_stat_without_perl_suffix(self, stow_env):
        """#18: for an unstattable target, Perl's warn appends its
        ' at <script> line N.' suffix (an artifact of the Perl runtime);
        Python prints the message alone. Both exit 0 reporting nothing."""
        prc, pout, perr = stow_env.run_perl_chkstow(["-t", "nosuchdir", "-b"])
        yrc, yout, yerr = stow_env.run_python_chkstow(["-t", "nosuchdir", "-b"])
        assert prc == 0 and yrc == 0
        assert pout == "" and yout == ""
        assert yerr == "Can't stat nosuchdir: No such file or directory\n"
        assert perr.startswith("Can't stat nosuchdir: No such file or directory")
        assert " line " in perr, f"Perl warn suffix expected: {perr!r}"
