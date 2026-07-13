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
        rc, stdout, stderr = stow_env.run_python_stow(
            ["-t", stow_env.target_dir, ""]
        )
        assert rc != 0, "Python must reject an empty package name"
        assert "empty" in stderr.lower()
        check_not_exists(stow_env, "file")

        stow_env.reset_target()
        rc, stdout, stderr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, ""]
        )
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
        rc, stdout, stderr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "pkg"]
        )
        assert rc == 0, f"Perl stow failed: {stderr}"
        # Perl's ignore check malfunctioned: the link exists
        assert os.path.islink(
            os.path.join(stow_env.target_dir, "\n", "backup~")
        )

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
        rc, stdout, stderr = stow_env.run_perl_stow(
            ["-t", stow_env.target_dir, "pkg"]
        )
        assert rc == 0, f"Perl stow failed: {stderr}"
        assert "Unsuccessful" in stderr, "Perl should warn about the newline"
