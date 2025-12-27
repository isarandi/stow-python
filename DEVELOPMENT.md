# Stow Perl→Python Merge Guide

Guide for integrating upstream GNU Stow changes (e.g., 2.5.0) into this Python port in the future.

## File Mapping

The Python port consolidates everything into standalone scripts with no dependencies.

| Perl Source | Python Port |
|-------------|-------------|
| `bin/stow` | `bin/stow` (CLI section) |
| `lib/Stow.pm` | `bin/stow` (main Stow class) |
| `lib/Stow/Util.pm` | `bin/stow` (utility functions at top) |
| `bin/chkstow` | `bin/chkstow` |
| `t/*.t` | `tests/test_*.py` |
| `t/testutil.pm` | `tests/testutil.py` |

The `bin/stow` file is organized with section dividers:
```
# From Stow/Util.pm - utility functions
# From Stow.pm - main Stow class
# CLI - argument parsing and main()
```

## Perl→Python Gotchas

### 1. Scalar Context vs Python Collections

**Perl:**
```perl
is($stow->get_tasks, 0, 'no tasks');           # scalar context = count
is_deeply([$stow->get_conflicts], [], 'ok');   # list context = array
```

**Python:**
```python
assert len(stow.get_tasks()) == 0              # get_tasks() returns list
assert stow.get_conflict_count() == 0          # use helper for count
assert stow.get_conflicts() == {}              # get_conflicts() returns dict
```

### 2. Errno and Exit Codes

Perl's `-d` operator sets `$!` (errno) on failure. Stow's `die()` uses errno as exit code.

**Python implementation** (in `bin/stow`):
```python
_last_errno = 0  # Global to track errno like Perl's $!

def is_a_directory(path):
    """Sets _last_errno like Perl's -d operator."""
    global _last_errno
    try:
        stat_result = os.stat(path)
        if stat.S_ISDIR(stat_result.st_mode):
            _last_errno = 0
            return True
        else:
            _last_errno = errno_module.ENOTDIR
            return False
    except OSError as e:
        _last_errno = e.errno
        return False

def error(format_str, *args):
    """Mimics Perl die() - uses errno as exit code if set."""
    global _last_errno
    # ... format message ...
    if _last_errno != 0:
        exit_code = _last_errno
        _last_errno = 0
    else:
        exit_code = 255
    sys.exit(exit_code)
```

### 3. die() vs Exceptions

Perl's `die` can be caught with `eval {}`. Some code uses `die` expecting it to be caught.

**Perl:**
```perl
my $compiled = eval { qr/$regexp/ };
die "Failed to compile regexp: $@\n" if $@;
```

**Python:**
```python
def compile_regexp(self, regexp):
    try:
        return re.compile(regexp)
    except re.error as e:
        # Raise exception (not sys.exit) so it can be caught
        raise RuntimeError("Failed to compile regexp: %s" % e)
```

### 4. parent() Function - Leading Slash Preservation

**Perl behavior:**
```perl
parent('/a/b/c')  # returns '/a/b' (preserves leading slash)
parent('a/b/c')   # returns 'a/b'
```

**Python implementation must use `re.split(r'/+', path)`:**
```python
def parent(*path_parts):
    path = '/'.join(path_parts)
    elts = re.split(r'/+', path)
    # Perl's split drops trailing empty strings, Python's doesn't
    while elts and elts[-1] == '':
        elts.pop()
    if elts:
        elts.pop()
    return '/'.join(elts)  # Empty first element = leading slash preserved
```

### 5. Regex Pattern Storage

defer/override/ignore patterns are passed as strings but must be compiled:

```python
def __init__(self, **opts):
    # ... other init ...
    # Compile patterns into regex objects
    self._defer = [re.compile(p) for p in self._defer]
    self._override = [re.compile(p) for p in self._override]
    self._ignore = [re.compile(p) for p in self._ignore]
```

### 6. Getopt::Long Error Format

**Perl Getopt::Long:**
```
Unknown option: foo
```

**Python must match (no dashes, no prefix):**
```python
opt_name = arg.lstrip('-')
sys.stderr.write("Unknown option: %s\n" % opt_name)
```

### 7. File::Find vs os.walk

Perl's `File::Find` has a `preprocess` callback to skip directories.
Python's `os.walk` enables the same by allowing the caller to edit the dirname list. To fully prevent descent, one has to clear it:

```python
for dirpath, dirnames, filenames in os.walk(target):
    if should_skip(dirpath):
        dirnames[:] = []  # Modify in place to skip subdirs (Python 2/3 compatible)
        continue
```

## Test Migration Notes

### Perl Test Patterns → Python

| Perl | Python |
|------|--------|
| `plan tests => N` | pytest auto-discovers |
| `is($a, $b, 'msg')` | `assert a == b, 'msg'` |
| `is_deeply(\@a, \@b)` | `assert a == b` |
| `ok($cond, 'msg')` | `assert cond, 'msg'` |
| `like($str, qr/pat/)` | `assert re.search(r'pat', str)` |
| `stderr_like(sub{...}, qr//)` | `capsys.readouterr()` |
| `dies_ok { ... }` | `with pytest.raises(...)` |

### Test Isolation

Perl tests share state across `subtests()`. Python tests get fresh `tmp_path`:

```python
@pytest.fixture
def stow_test_env(tmp_path):
    # Creates isolated test dirs in tmp_path
    abs_test_dir = init_test_dirs(tmp_path)
    target_dir = os.path.join(abs_test_dir, 'target')
    cd(target_dir)
    yield abs_test_dir
    # Cleanup automatic via tmp_path
```

### Tests Requiring Package Setup

Some Perl tests rely on packages created by earlier tests. Python tests must create their own:

```python
def test_unstow_already_unstowed(self, stow_test_env):
    # Must create package first (Perl relied on earlier test)
    make_path('../stow/pkg12/man12/man1')
    make_file('../stow/pkg12/man12/man1/file12.1')
    # Now test unstowing
    stow.plan_unstow('pkg12')
```

## Merge Workflow

1. **Check Perl diff:**
   ```bash
   diff -r stow-2.4.1 stow-2.5.0 > upstream.diff
   ```

2. **Identify changed functions** in `lib/Stow.pm`, `lib/Stow/Util.pm`, `bin/stow`

3. **Apply equivalent changes** to `bin/stow`, watching for gotchas above

4. **Run oracle tests** against new Perl version:
   ```bash
   # Update VERSION in tests/get_gnu_stow_for_testing_identical_behavior.sh
   cd tests && ./get_gnu_stow_for_testing_identical_behavior.sh && cd ..
   pytest tests/test_oracle.py -v
   ```

5. **Fix discrepancies** until oracle tests pass

6. **Port new tests** from `t/*.t` to `tests/test_*.py` and run all tests.

## Debug Output Matching

Debug messages must match exactly for verbose mode compatibility:

```python
# Perl: debug(2, "  Deferring $target_subpath");
debug(2, "  Deferring %s" % target_subpath)

# Note: Some messages have colons, some don't:
# "MKDIR: $dir" but "RMDIR $dir" (no colon!)
```
