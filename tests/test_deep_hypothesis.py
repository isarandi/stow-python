"""Deep oracle exploration - a long-running, wide-net hypothesis session.

Runs the same Perl-vs-Python oracle comparison as tests/test_oracle_hypothesis.py
but with substantially wider input spaces and dimensions the regular suite does
not explore: pre-existing target content, multi-step operation sequences where
each side runs its own implementation throughout, --dotfiles/--compat and
--no-folding interactions, and adopt over random overlaps. Documented
divergences (#25/#29) are generated and recognized by the shared classifier;
anything unclassified fails.

Not part of the regular suite: without DEEP_SCALE set the module is
skipped, so default runs stay fast. Run it explicitly:

    DEEP_SCALE=1.0 PYTHONPATH=src micromamba run -n pystow-test \
        pytest tests/test_deep_hypothesis.py -q \
        --hypothesis-show-statistics

DEEP_SCALE=0.02 gives a quick smoke run; 1.0 is the full session
(several minutes).
"""

import os
import tempfile

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from conftest import (
    StowTestEnv,
    assert_stow_match_with_fs_ops,
    normalize_getopt_long_wording,
    normalize_newline_warnings,
    normalize_stow_output,
)
from test_oracle_hypothesis import (
    assert_match_or_documented,
    content_st,
    try_create_packages,
)

_SCALE_ENV = os.environ.get("DEEP_SCALE")
pytestmark = pytest.mark.skipif(
    _SCALE_ENV is None,
    reason="deep exploration session; set DEEP_SCALE (e.g. 1.0) to run",
)
SCALE = float(_SCALE_ENV or "1.0")

DEEP = dict(
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.filter_too_much,
        HealthCheck.data_too_large,
    ],
    print_blob=True,
)


def n_examples(base):
    return max(5, int(base * SCALE))


# --- Wider strategies -------------------------------------------------------

wide_name_st = st.text(min_size=1, max_size=24).filter(
    lambda x: "\0" not in x
    and "/" not in x
    and not x.startswith("-")
    and not x.startswith("+")
    and x != ".stowrc"
)

wide_component_st = st.text(min_size=1, max_size=16).filter(
    lambda x: "\0" not in x
    and "/" not in x
    and x not in (".", "..")
    and not x.endswith("~")
)

# Sequences compound state across steps, so a documented divergence at step k
# cascades into every later step in ways the per-command classifier cannot
# credit to its origin; the sequence dimension therefore excludes the
# documented triggers and hunts undocumented interaction bugs only.
seq_name_st = wide_name_st.filter(lambda x: x != "0")
seq_component_st = wide_component_st.filter(lambda x: not x.startswith(".."))


@st.composite
def wide_tree_st(
    draw, component=wide_component_st, max_depth=5, max_files=15, inject_triggers=True
):
    num_files = draw(st.integers(min_value=1, max_value=max_files))
    files = {}
    used_dirs = set()
    for _ in range(num_files):
        depth = draw(st.integers(min_value=1, max_value=max_depth))
        components = draw(
            st.lists(component, min_size=depth, max_size=depth, unique=True)
        )
        # Same deliberate #29-trigger rate as the regular suite's strategies
        if inject_triggers and draw(st.integers(min_value=0, max_value=19)) == 0:
            components[0] = ".." + components[0]
        path = "/".join(components)
        if path in used_dirs:
            continue
        prefixes = ["/".join(components[:i]) for i in range(1, len(components))]
        if any(p in files for p in prefixes) or path in files:
            continue
        used_dirs.update(prefixes)
        files[path] = draw(content_st)
    return files if files else {"file": "content"}


@st.composite
def wide_package_set_st(
    draw,
    name=wide_name_st,
    component=wide_component_st,
    max_packages=5,
    inject_triggers=True,
):
    num = draw(st.integers(min_value=1, max_value=max_packages))
    names = draw(st.lists(name, min_size=num, max_size=num, unique=True))
    # Same deliberate #25-trigger rate as the regular suite's strategies
    if inject_triggers and draw(st.integers(min_value=0, max_value=9)) == 0:
        if "0" not in names:
            names[-1] = "0"
    return {
        n: draw(
            wide_tree_st(
                component=component,
                max_depth=3,
                max_files=6,
                inject_triggers=inject_triggers,
            )
        )
        for n in names
    }


@st.composite
def prefill_st(draw, packages):
    """Pre-existing target content: files at package paths (conflicts),
    unrelated files/dirs, dangling links and unowned links."""
    all_paths = [p for files in packages.values() for p in files]
    entries = {}
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        kind = draw(st.sampled_from(["conflict_file", "file", "dir", "link"]))
        if kind == "conflict_file" and all_paths:
            path = draw(st.sampled_from(all_paths))
            entries[path] = ("file", draw(content_st))
        elif kind == "file":
            entries[draw(wide_component_st)] = ("file", draw(content_st))
        elif kind == "dir":
            entries[draw(wide_component_st)] = ("dir",)
        else:
            dest = draw(
                st.sampled_from(
                    ["nowhere", "../elsewhere", "loop", "../stow/unrelated/x"]
                )
            )
            entries[draw(wide_component_st)] = ("link", dest)
    return entries


def apply_prefill(env, entries):
    for path, spec in entries.items():
        try:
            if spec[0] == "file":
                env.create_target_file(path, spec[1])
            elif spec[0] == "dir":
                env.create_target_dir(path)
            else:
                env.create_target_link(path, spec[1])
        except OSError:
            return False
    return True


# --- Single-command properties over the widened space -----------------------


class TestDeepSingleCommands:
    @settings(max_examples=n_examples(1200), **DEEP)
    @given(packages=wide_package_set_st(), data=st.data())
    def test_stow_with_prefilled_target(self, packages, data):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))
            prefill = data.draw(prefill_st(packages))
            pkg_names = list(packages.keys())

            def setup():
                assume(apply_prefill(env, prefill))

            assert_match_or_documented(
                env, ["-t", env.target_dir] + pkg_names, packages, setup
            )

    @settings(max_examples=n_examples(900), **DEEP)
    @given(packages=wide_package_set_st())
    def test_unstow_wide(self, packages):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))
            pkg_names = list(packages.keys())

            def setup():
                env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            assert_match_or_documented(
                env, ["-t", env.target_dir, "-D"] + pkg_names, packages, setup
            )

    @settings(max_examples=n_examples(700), **DEEP)
    @given(packages=wide_package_set_st())
    def test_restow_wide(self, packages):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))
            pkg_names = list(packages.keys())

            def setup():
                env.run_perl_stow(["-t", env.target_dir] + pkg_names)

            assert_match_or_documented(
                env, ["-t", env.target_dir, "-R"] + pkg_names, packages, setup
            )

    @settings(max_examples=n_examples(600), **DEEP)
    @given(packages=wide_package_set_st(max_packages=2))
    def test_no_folding_stow_then_unstow(self, packages):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, packages))
            pkg_names = list(packages.keys())

            def setup():
                env.run_perl_stow(["-t", env.target_dir, "--no-folding"] + pkg_names)

            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "--no-folding", "-D"] + pkg_names,
                packages,
                setup,
            )

    @settings(max_examples=n_examples(600), **DEEP)
    @given(files=wide_tree_st(max_depth=3, max_files=8))
    def test_dotfiles_compat_unstow(self, files):
        dotted = {
            ("dot-" + p if not p.startswith("dot-") else p): c for p, c in files.items()
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            assume(try_create_packages(env, {"dotpkg": dotted}))

            def setup():
                env.run_perl_stow(["-t", env.target_dir, "--dotfiles", "dotpkg"])

            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "--dotfiles", "--compat", "-D", "dotpkg"],
                {"dotpkg": dotted},
                setup,
            )

    @settings(max_examples=n_examples(500), **DEEP)
    @given(
        pkg_files=wide_tree_st(max_depth=3, max_files=8),
        adopt_count=st.integers(min_value=1, max_value=4),
    )
    def test_adopt_wide(self, pkg_files, adopt_count):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = StowTestEnv(tmpdir)
            paths = list(pkg_files.keys())

            def setup():
                env.create_package("pkg", pkg_files)
                for p in paths[:adopt_count]:
                    env.create_target_file(p, "to be adopted: " + p)

            assert_match_or_documented(
                env,
                ["-t", env.target_dir, "--adopt", "pkg"],
                {"pkg": pkg_files},
                setup,
                matcher=assert_stow_match_with_fs_ops,
            )


# --- Operation sequences: each side runs its own implementation -------------


def _scrub(text, tmpdir):
    return text.replace(tmpdir, "TMP")


def _run_sequence(env, runner, ops):
    """Apply ops with one implementation; return per-step records + tree."""
    records = []
    for flag, pkg in ops:
        rc, out, err = runner(["-t", env.target_dir, flag, pkg])
        out = _scrub(normalize_stow_output(out), env.tmpdir)
        err = _scrub(
            normalize_getopt_long_wording(
                normalize_newline_warnings(normalize_stow_output(err))
            ),
            env.tmpdir,
        )
        records.append((rc, out, err))
    return records, env.get_filesystem_state()


class TestDeepSequences:
    @settings(max_examples=n_examples(500), **DEEP)
    @given(
        packages=wide_package_set_st(
            name=seq_name_st,
            component=seq_component_st,
            max_packages=3,
            inject_triggers=False,
        ),
        data=st.data(),
    )
    def test_operation_sequences(self, packages, data):
        """A whole command sequence, each side using its own implementation
        throughout, must agree step for step and end in the same tree."""
        pkg_names = list(packages.keys())
        n_ops = data.draw(st.integers(min_value=2, max_value=6))
        ops = [
            (
                data.draw(st.sampled_from(["-S", "-D", "-R"])),
                data.draw(st.sampled_from(pkg_names)),
            )
            for _ in range(n_ops)
        ]

        with (
            tempfile.TemporaryDirectory() as perl_dir,
            tempfile.TemporaryDirectory() as py_dir,
        ):
            perl_env = StowTestEnv(perl_dir)
            py_env = StowTestEnv(py_dir)
            assume(try_create_packages(perl_env, packages))
            assume(try_create_packages(py_env, packages))

            perl_records, perl_state = _run_sequence(
                perl_env, perl_env.run_perl_stow, ops
            )
            py_records, py_state = _run_sequence(py_env, py_env.run_python_stow, ops)

            assert perl_records == py_records, (
                f"sequence {ops}: step records diverged:\n"
                f"  perl:   {perl_records}\n  python: {py_records}"
            )
            assert perl_state == py_state, f"sequence {ops}: final trees diverged"
