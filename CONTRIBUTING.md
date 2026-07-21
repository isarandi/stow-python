# Contributing to Stow-Python

## Development setup

Stow-Python requires Python >= 3.10 and has no runtime dependencies.
The test suite needs `pytest` and `hypothesis`:

```bash
pip install pytest hypothesis
```

## Running the tests

```bash
PYTHONPATH=$PWD/src pytest tests/
```

The oracle tests compare Stow-Python black-box against the original
Perl implementation. Download and build the Perl oracle first:

```bash
cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh && cd ..
```

The syscall-comparison layer of the oracle tests requires `strace`
(Linux). Without it, all other comparison layers still run and only the
syscall layer is skipped (loudly); CI on Linux hard-requires strace.

## Lint gates

CI enforces all three of the following, with tool versions pinned in
`.github/workflows/ci.yml`:

```bash
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
mypy src/
```

Keep all of them clean; the ruff and mypy configuration lives in
`pyproject.toml`.

## The golden rule

Stow-Python's purpose is identical behavior to GNU Stow 2.4.1. **No
behavioral divergence may be introduced without (a) documenting it in
`docs/perl-differences.md` and (b) pinning it with a test that asserts
BOTH behaviors** — the Perl behavior on the Perl oracle and the
Stow-Python behavior on this implementation.

## License

Stow-Python is licensed under the GNU General Public License, version 3
or later (GPLv3+). Every source file must carry the per-file license
header, including the upstream GNU Stow copyright chain.
