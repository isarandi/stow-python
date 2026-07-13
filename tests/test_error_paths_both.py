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
Error-path tests: permission failures and the cross-device move fallback.

Exit codes differ between the implementations on error paths (see
docs/perl-differences.md section 13), so these are behavioral assertions
per implementation rather than byte-exact oracle comparisons: both must
fail loudly and cleanly, without tracebacks, and without partial changes
where the failure happens during planning.
"""

import errno
import os
import stat as stat_module
import sys

import pytest


needs_nonroot = pytest.mark.skipif(
    os.geteuid() == 0, reason="permission checks are bypassed as root"
)


class TestPermissionErrors:
    @needs_nonroot
    def test_unreadable_package_subdir(self, stow_env):
        """Planning must fail cleanly when a package subdir is unreadable.

        The target dir must pre-exist: otherwise stow folds (links the
        whole subdir) and never needs to read its contents.
        """
        stow_env.create_package("pkg", {"sub/file": "content"})
        subdir = os.path.join(stow_env.stow_dir, "pkg", "sub")
        os.chmod(subdir, 0)
        try:
            stow_env.reset_target()
            stow_env.create_target_dir("sub")
            rc, stdout, stderr = stow_env.run_python_stow(
                ["-t", stow_env.target_dir, "pkg"]
            )
            assert rc != 0
            assert "Traceback" not in stderr
            assert "sub" in stderr

            stow_env.reset_target()
            stow_env.create_target_dir("sub")
            rc, stdout, stderr = stow_env.run_perl_stow(
                ["-t", stow_env.target_dir, "pkg"]
            )
            assert rc != 0
        finally:
            os.chmod(subdir, stat_module.S_IRWXU)

    @needs_nonroot
    def test_unreadable_local_ignore_file_is_skipped(self, stow_env):
        """An unreadable .stow-local-ignore is silently skipped (Perl's -r
        check), so its patterns do not apply and stowing proceeds with the
        defaults."""
        stow_env.create_package("pkg", {"file": "content"})
        ignore_file = os.path.join(
            stow_env.stow_dir, "pkg", ".stow-local-ignore"
        )
        with open(ignore_file, "w") as f:
            f.write("file\n")  # would ignore "file" if it were readable
        os.chmod(ignore_file, 0)
        try:
            for run in (stow_env.run_python_stow, stow_env.run_perl_stow):
                stow_env.reset_target()
                rc, stdout, stderr = run(["-t", stow_env.target_dir, "pkg"])
                assert rc == 0, f"stow failed: {stderr}"
                assert "Traceback" not in stderr
                # The unreadable ignore file did not take effect
                assert os.path.islink(
                    os.path.join(stow_env.target_dir, "file")
                )
        finally:
            os.chmod(ignore_file, stat_module.S_IRUSR | stat_module.S_IWUSR)


class TestCrossDeviceMove:
    def test_move_falls_back_on_exdev(self, tmp_path, monkeypatch):
        """util.move must fall back to copy+delete when rename gives EXDEV,
        like Perl's File::Copy::move (used by --adopt across filesystems)."""
        sys.path.insert(
            0,
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"),
        )
        from stow_python import util

        src = tmp_path / "srcfile"
        dst = tmp_path / "dstfile"
        src.write_text("adopted content")

        real_rename = os.rename

        def exdev_rename(a, b, *args, **kwargs):
            raise OSError(errno.EXDEV, "Invalid cross-device link", a)

        monkeypatch.setattr(os, "rename", exdev_rename)
        try:
            util.move(str(src), str(dst))
        finally:
            monkeypatch.setattr(os, "rename", real_rename)

        assert dst.read_text() == "adopted content"
        assert not src.exists()
