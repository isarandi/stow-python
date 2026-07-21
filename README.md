# Stow-Python

This is a pedantically faithful, single-file, dependency-free Python reimplementation of all of [GNU Stow](https://www.gnu.org/software/stow/), the symlink farm manager, that runs on Python 3.10 and above.

**Note:** Stow-Python is an independent reimplementation and not an official GNU project; it is not affiliated with or endorsed by the GNU Project or the GNU Stow maintainers. Throughout this document, "GNU Stow" refers to the original Perl program.

The reason for making this is to help transition the GNU Stow project from Perl to Python, providing a modern, maintainable codebase while preserving full compatibility with existing workflows.

The goal here is identical behavior to GNU Stow, to achieve true, worry-free drop-in substitution. This is tested both with ports of the original Perl tests and with oracle tests against the Perl executable verifying identical output, return codes and filesystem state. The code follows modern Python idioms using dataclasses and enums, while maintaining behavioral equivalence with GNU Stow verified through oracle testing. See [known differences](docs/perl-differences.md) for minor edge cases.

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

## Use

Since Stow-Python is an exact reimplementation of GNU Stow, you can refer to the [GNU Stow manual](https://www.gnu.org/software/stow/manual/) for all options and usage details, or see `stow --help`.

## Documentation

An adapted Texinfo manual is included as [docs/stow.texi](docs/stow.texi) (builds `stow-python.info`), and man pages for `stow` and `chkstow` are in [docs/man/](docs/man/). The minor known behavioral differences from the Perl implementation are documented in [docs/perl-differences.md](docs/perl-differences.md).

To use the `chkstow` diagnostic tool for common stow directory problems, you can either download it directly like the `stow` executable, or use pip, it is automatically installed with stow-python. The `stow` and `chkstow` executables do not depend on each other, both are standalone with Python as the sole dependency.

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
pip install stow-python[tests]  # installs pytest and hypothesis
pytest tests/

# For oracle tests (comparing against the Perl-based GNU Stow), install GNU Stow first:
cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh && cd ..
pytest tests/
```

The test suite includes both ported unit tests from the original Perl codebase and tests that run both implementations and verify identical behavior.

## Repository layout

Branch `pythonic` (this branch) is the maintained product. Branch `main` is a frozen, Python 2.7-compatible literal transpilation of the Perl code for ancient systems. Branch `pythonic-bug4bug` is a bug-for-bug reference that replicates the Perl implementation exactly, including its bugs.

## License

GPL-3.0-or-later

## Acknowledgements

This project constitutes derivative work of GNU Stow, whose authors are Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others. This code could not exist without them.
