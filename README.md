# Stow-Python

This is a pedantically faithful, single-file, dependency-free Python reimplementation of all of [GNU Stow](https://www.gnu.org/software/stow/), the symlink farm manager, that runs on Python 3.10 and above.

**Note:** Stow-Python is an independent reimplementation and not an official GNU project; it is not affiliated with or endorsed by the GNU Project or the GNU Stow maintainers. Throughout this document, "GNU Stow" refers to the original Perl program.

## Project goal

The aim of this project is to help the GNU Stow project transition from Perl to Python: a modern, maintainable codebase that is a true, worry-free **drop-in replacement**. Feature parity is not enough for that — behavior parity is the bar. Existing scripts, `.stowrc` files, ignore lists, `--verbose` output parsers and exit-code checks should not be able to tell the difference. Where we deviate from the Perl implementation at all, it is deliberate, documented and test-pinned (see [How we verify equivalence](#how-we-verify-equivalence) below).

## Install

Stow-Python has a single self-contained executable Python script `stow`, which you can simply drop directly into any directory in your PATH, such as `~/.local/bin`. The `stow` and `chkstow` scripts are attached to each [GitHub release](https://github.com/isarandi/stow-python/releases):

```bash
wget -O ~/.local/bin/stow https://github.com/isarandi/stow-python/releases/latest/download/stow
chmod +x ~/.local/bin/stow
```

But if you prefer, pip installation is also available:

```bash
pip install stow-python
```

After this, you can simply run the `stow` command since the executable will be in your PATH.

## Versioning

The version number mirrors the GNU Stow version whose behavior is reproduced: `2.4.1.post1` behaves like GNU Stow 2.4.1, and the `.postN` suffix increments with each stow-python release on top of that behavior.

When GNU Stow releases a new version, stow-python will port and verify that behavior and adopt the new base version number; `.postN` releases contain stow-python-only changes on top of the current base behavior.

## Use

Since Stow-Python is an exact reimplementation of GNU Stow, you can refer to the [GNU Stow manual](https://www.gnu.org/software/stow/manual/) for all options and usage details, or see `stow --help`.

## How we verify equivalence

"Behaves identically" is a strong claim, so it is backed by several independent verification layers:

- **Ported upstream test suite.** Every file of GNU Stow's own `t/` test suite is ported 1:1, with the expected values taken from the Perl sources, not from this implementation.
- **Oracle testing.** Black-box tests run the real Perl GNU Stow 2.4.1 and this implementation side by side on the same scenarios and require identical results on four levels: exit codes, byte-exact stdout and stderr, whole-tree filesystem state (file types, contents, permissions, ownership and symlink destinations), and even the ordered sequence of filesystem syscalls observed via strace. Each scenario runs with and without `POSIXLY_CORRECT`.
- **Property-based testing.** [Hypothesis](https://hypothesis.readthedocs.io/) generates randomized package trees and operation sequences, each checked against the Perl oracle.
- **A divergence contract.** Every intentional difference from the Perl implementation — mostly Perl bugs we refuse to reproduce, plus a few interpreter-level artifacts — is catalogued in [docs/perl-differences.md](docs/perl-differences.md) *and* pinned by a test that asserts both the Perl behavior and the Python behavior, so silent drift on either side fails the suite. New divergences are not accepted without both.
- **Continuous integration.** CI builds the Perl GNU Stow 2.4.1 oracle from source and runs the full suite on Python 3.10 through 3.14 on Linux (with the strace layer mandatory) and on macOS, alongside pinned lint/type gates, a packaging build check and Texinfo validation.

Emulation runs deep where it matters for compatibility: option parsing reproduces Perl `Getopt::Long` semantics (bundling, unique-prefix abbreviation, ambiguity errors, `POSIXLY_CORRECT`), `.stowrc` parsing reproduces `Text::ParseWords::shellwords`, and verbose debug output is byte-identical up to the highest levels except for two documented, provably unmatchable lines.

## Repository layout

- **`main`** (this branch) — the maintained product: idiomatic Python 3.10+ with dataclasses and enums, sources in [`src/stow_python/`](src/stow_python/), bundled into standalone single-file executables.
- **`bug4bug`** — a bug-for-bug reference that replicates the Perl implementation *exactly*, including its bugs, warning quirks and syscall sequences. It serves as the executable answer key for what Perl does.
- **`py27-literal`** — a frozen, Python 2.7-compatible literal transpilation of the Perl code, kept for ancient systems. It follows the original Perl logic line by line; `bin/` is the hand-maintained source there.

## Reviewing the port

Automated equivalence testing does not replace human review, so the repository is structured to make review tractable without requiring one person to hold both languages in their head at once:

1. **Perl ↔ `bug4bug`**: the bug-for-bug branch mirrors the Perl sub-for-sub and is held to the strictest oracle tests (including syscall sequences), so the cross-language comparison is between two texts designed to align.
2. **`bug4bug` ↔ `main`**: a same-language diff of about two thousand lines, where every behavioral delta must correspond to an entry in [docs/perl-differences.md](docs/perl-differences.md).

Reviewers also do not have to trust our test scenarios: the `tests/test_*_both.py` files show how to write a new adversarial oracle scenario in a few lines, which then automatically checks exit codes, output bytes, tree state and syscalls against the real Perl Stow.

## Documentation

An adapted Texinfo manual is included as [docs/stow.texi](docs/stow.texi) (builds `stow-python.info`), and man pages for `stow` and `chkstow` are in [docs/man/](docs/man/). The minor known behavioral differences from the Perl implementation are documented in [docs/perl-differences.md](docs/perl-differences.md). Note for distribution packagers: pip does not install the man pages or the Info manual, so packages should install `docs/man/*.8` and build `stow-python.info` from `docs/stow.texi` with `makeinfo`.

To use the `chkstow` diagnostic tool for common stow directory problems, you can either download it directly like the `stow` executable, or use pip, it is automatically installed with stow-python. The `stow` and `chkstow` executables do not depend on each other, both are standalone with Python as the sole dependency.

The internal architecture (two-phase planning/execution, the task system, tree folding) is described in [docs/architecture.md](docs/architecture.md), and the testing approach in [docs/TESTING.md](docs/TESTING.md).

## Library Usage

Stow-Python can also be used as a Python library:

```python
from stow_python import stow, unstow, restow, StowConfig

# Simple usage
result = stow("emacs", "vim", dir="./stow", target="/home/user")
if result.conflicts:
    print("Conflicts:", result.conflicts)

# With reusable configuration
config = StowConfig(dir="./stow", target="/home/user", dotfiles=True)
stow("pkg1", config=config)
unstow("pkg2", config=config)

# Dry-run mode
result = stow("pkg", dir="./stow", target="/home/user", simulate=True)
print("Would perform:", result.tasks)
```

## Building

The single-file executables (`bin/stow` and `bin/chkstow`) are built from the multi-file library in `src/stow_python/`:

```bash
python scripts/build_single_file.py
```

This bundles all modules into standalone scripts with no dependencies beyond Python 3.10+.

## Run the tests

```bash
pip install -e ".[tests]"  # installs pytest and hypothesis
pytest tests/

# For oracle tests (comparing against the Perl-based GNU Stow), install GNU Stow first:
cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh && cd ..
pytest tests/
```

The test suite includes both ported unit tests from the original Perl codebase and tests that run both implementations and verify identical behavior.

## Not done yet

Planned work, roughly in order of priority:

- A **correspondence map** (each Perl sub → its Python counterpart, with notes) and a **reviewer's guide**, to lower the cost of independent human review further.
- The **extreme test layer**: real cross-filesystem `--adopt`, disk-full and permission failures mid-operation, races, and large-scale trees ([docs/EXTREME_TESTS_PLAN.md](docs/EXTREME_TESTS_PLAN.md)); today only a monkeypatched EXDEV path is covered.
- Broader **non-UTF-8 filename** coverage (currently one oracle scenario).
- A **mutation-testing** pass to measure the suite's bug-catching power empirically.
- Porting the behavior of the **next upstream GNU Stow release** when it appears (see Versioning).

## License

GPL-3.0-or-later

## Acknowledgements

This project constitutes derivative work of GNU Stow, whose authors are Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others. This code could not exist without them.
