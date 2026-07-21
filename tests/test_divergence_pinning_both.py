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

from conftest import check_not_exists


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
        """perl-differences.md #10: '-v 3 pkg'.

        Perl's 'verbose|v:+' spec gobbles the following integer as the
        verbosity level and stows pkg; Python treats 3 as a package name
        and fails because no such package exists.
        """
        stow_env.create_package("pkg", {"file": "content"})

        stow_env.reset_target()
        prc, _, perr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "-v", "3", "pkg"]
        )
        assert prc == 0, f"Perl should gobble 3 as verbosity: {perr}"
        assert os.path.islink(os.path.join(stow_env.target_dir, "file"))

        stow_env.reset_target()
        yrc, _, yerr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, "-v", "3", "pkg"]
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
