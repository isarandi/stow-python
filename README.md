# Stow-Python

This is a pedantically faithful, singe-file, dependency-free Python reimplementation of all of [GNU Stow](https://www.gnu.org/software/stow/), the symlink farm manager, that runs on any Python version from 2.7 to 3.14 and beyond.

The reason for making this is that GNU Stow is very useful but it's written in Perl. This can cause some headaches on some HPC clusters or other systems that you don't control yourself regarding the Perl toolchain. This reimplementation lets you use Stow on systems where Perl isn't available (or isn't the correct version, or misses some packages etc.) but *some* version of Python is there (2.7 or 3.0–3.14+), which is basically always.

The goal here is identical behavior to GNU Stow, to achieve true, worry-free drop-in substitution. This is tested both with ports of the original Perl tests and with oracle tests against the Perl executable verifying identical output, return codes and filesystem state. The code itself is not very pythonic, following the logic of the original Perl code is of higher priority to ensure correctness.

## Install

Stow-Python is a single self-contained executable Python script that you can simply drop directly into any directory in your PATH, such as `~/.local/bin`:

```bash
wget -O ~/.local/bin/stow https://raw.githubusercontent.com/isarandi/stow-python/main/bin/stow
chmod +x ~/.local/bin/stow
```

But if you prefer, pip installation is also available:

```bash
pip install stow-python
```

After this, you can simply run the `stow` command since the executable will be in your PATH.

## Use

Stow-Python is an exact reimplementation of GNU Stow, so refer to the [GNU Stow manual](https://www.gnu.org/software/stow/manual/) for all options and usage details, or see `stow --help` for all options, or refer to the [GNU Stow manual](https://www.gnu.org/software/stow/manual/).

To use the `chkstow` diagnostic tool for common stow directory problems, you can either download it directly like the `stow` executable, or use pip, it is automatically installed with stow-python. The `stow` and `chkstow` executables do not depend on each other, both are standalone with Python as the sole dependency. 

## Run the tests

```bash
pip install stow-python[tests]
pytest tests/

# For oracle tests (comparing against the Perl-based GNU Stow), install GNU Stow first:
cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh && cd ..
pytest tests/
```

The test suite includes both ported unit tests from the original Perl codebase and tests that run both implementations and verify identical behavior.

## License

GPL-3.0-or-later

## Acknowledgements

This project constitutes derivative work of GNU Stow, whose authors are Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others. This code could not exist without them.
