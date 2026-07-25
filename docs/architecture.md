# Stow-Python Architecture

This document describes the internal architecture of Stow-Python.

## High-Level Overview

Stow-Python manages "symlink farms" - directories populated with symbolic links that point into package directories. This allows multiple packages to share a common installation target (like `/usr/local`) while keeping their files organized separately.

```
stow/                      target/
├── emacs/                 ├── bin/
│   └── bin/               │   ├── emacs -> ../stow/emacs/bin/emacs
│       └── emacs          │   └── vim -> ../stow/vim/bin/vim
└── vim/                   └── share/
    ├── bin/                   └── vim -> ../stow/vim/share/vim
    │   └── vim
    └── share/
        └── vim/
```

### Core Operations

1. **Stow**: Create symlinks in target directory pointing to package contents
2. **Unstow**: Remove symlinks that point to a package
3. **Restow**: Unstow then stow (useful after updating package contents)

## Module Structure

```
src/stow_python/
├── __init__.py    # Public API exports
├── types.py       # Dataclasses, enums, exceptions
├── stow.py        # Core stow/unstow logic
├── cli.py         # Command-line interface
├── perlcompat.py  # Perl library emulations (Getopt::Long, shellwords, regexps)
├── util.py        # Path utilities, debugging
└── chkstow.py     # Target directory diagnostics
```

## Public API

The library exposes three main functions:

```python
from stow_python import stow, unstow, restow, StowConfig

# Simple usage
result = stow("emacs", "vim", dir="./stow", target="/home/user")

# With configuration object
config = StowConfig(dir="./stow", target="/home/user", dotfiles=True)
result = stow("pkg1", config=config)

# Check result
if result.success:
    print(f"Performed {len(result.tasks)} operations")
else:
    print(f"Conflicts: {result.conflicts}")
```

### StowConfig

Configuration class with the following fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dir` | str | "." | Stow directory containing packages |
| `target` | str | parent of dir | Target directory for symlinks |
| `dotfiles` | bool | False | Enable `dot-` prefix handling |
| `adopt` | bool | False | Move existing files into package |
| `no_folding` | bool | False | Disable tree folding optimization |
| `simulate` | bool | False | Plan but don't execute |
| `verbose` | int | 0 | Debug output level (0-5) |
| `compat` | bool | False | Legacy unstow algorithm |
| `ignore` | tuple[str, ...] | () | Regex pattern strings for files to ignore |
| `defer` | tuple[str, ...] | () | Regex pattern strings to defer to other packages |
| `override` | tuple[str, ...] | () | Regex pattern strings to override other packages |

The pattern fields take the same raw regex strings a user would pass to
`--ignore`/`--defer`/`--override`; anchoring (`--ignore` matches at the end
of a path, the other two at the start) and compilation happen inside the
stower, so library callers and the CLI get identical semantics. A malformed
pattern raises `StowError`; unknown keyword arguments to `stow()`/`unstow()`/
`restow()` raise `TypeError` rather than being silently ignored.

### Process-Global State and Threading

Planning and execution `chdir()` into the target tree, mirroring Perl stow's
behavior and syscall sequence, and debug verbosity is applied process-wide
for the duration of an operation. A process-wide re-entrant lock serializes
these phases, so calling `stow()`/`unstow()`/`restow()` concurrently from
multiple threads is safe but serialized. What the lock cannot protect
against is *other* code in the host application depending on or changing
the current working directory while an operation runs — do not run stow
operations concurrently with cwd-sensitive code.

### StowResult

Returned by all operations:

```python
@dataclass
class StowResult:
    success: bool                      # False if conflicts detected
    conflicts: dict[str, list[str]]    # Package -> conflict messages
    tasks: list[Task]                  # Operations performed (or planned)
```

## Internal Architecture

### The _Stower Class

The internal `_Stower` class manages state during planning and execution:

```python
class _Stower:
    def __init__(self, config: StowConfig):
        self.c = config
        self.conflicts: dict[str, list[str]] = {}
        self.tasks: list[Task] = []
        self.dir_task_for: dict[str, DirTask] = {}   # Track dir operations
        self.link_task_for: dict[str, LinkTask] = {}  # Track link operations
```

### Two-Phase Execution

Operations are split into **planning** and **execution** phases:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Plan      │ --> │   Check     │ --> │   Execute   │
│   Stow      │     │   Conflicts │     │   Tasks     │
│   Unstow    │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
     │                    │                    │
     v                    v                    v
  self.tasks         self.conflicts      filesystem
```

**Planning phase** (`plan_stow`, `plan_unstow`):
- Walks package directory tree
- Determines required operations
- Detects conflicts
- Queues tasks without executing

**Execution phase** (`process_tasks`):
- Only runs if no conflicts
- Executes queued tasks in order
- Creates/removes symlinks and directories

### Task System

Tasks represent deferred filesystem operations. Three separate dataclasses handle different operation types:

```python
class Action(Enum):
    CREATE = "create"
    REMOVE = "remove"

@dataclass
class LinkTask:
    action: Action
    path: str
    source: str
    skipped: bool = False

@dataclass
class DirTask:
    action: Action
    path: str
    skipped: bool = False

@dataclass
class MoveTask:
    path: str
    dest: str
    skipped: bool = False

Task = Union[LinkTask, DirTask, MoveTask]
```

Tasks are tracked in dictionaries to detect conflicts:
- `dir_task_for[path]`: Pending DirTask at path
- `link_task_for[path]`: Pending LinkTask at path

### Tree Folding

Stow optimizes symlink farms using "tree folding":

**Without folding** (many symlinks):
```
target/share/
├── vim/
│   ├── file1 -> ../../stow/vim/share/vim/file1
│   ├── file2 -> ../../stow/vim/share/vim/file2
│   └── file3 -> ../../stow/vim/share/vim/file3
```

**With folding** (single symlink to directory):
```
target/share/
└── vim -> ../stow/vim/share/vim
```

When multiple packages need the same directory, stow "unfolds" it:
1. Remove directory symlink
2. Create real directory
3. Create individual symlinks for each package's contents

### Conflict Detection

Conflicts occur when stow cannot safely proceed:

1. **Existing file**: Target path has a real file (not symlink)
2. **Wrong ownership**: Symlink points outside any stow directory
3. **Different package**: Symlink points to different package (without override)
4. **Directory vs file**: Package has file where target has directory

Conflicts are collected per-package:
```python
self.conflicts = {
    "emacs": ["existing target is not owned by stow: bin/emacs"],
    "vim": ["existing target is stowed to a different package: share/doc => ../stow/emacs/share/doc"],
}
```

### Ownership Detection

`find_stowed_path()` determines if a symlink is "owned" by stow:

```python
@dataclass
class StowedPath:
    path: str       # Full path to the stowed file
    stow_dir: str   # Which stow directory owns it
    package: str    # Which package within that stow dir
```

A symlink is stow-owned if:
1. It points into a directory containing `.stow` marker file
2. The path structure is `<stow_dir>/<package>/<subpath>`

### Ignore Patterns

Files can be ignored via:
1. **CLI patterns**: `--ignore=REGEX`
2. **Local ignore**: `<package>/.stow-local-ignore`
3. **Global ignore**: `$HOME/.stow-global-ignore`

The local ignore file takes precedence over the global ignore file. If neither exists, built-in defaults are used. Ignore files use regex patterns (Perl-compatible), one per line.

### Dotfiles Mode

With `dotfiles=True`, files named `dot-foo` in packages become `.foo` in target:

```
stow/bash/dot-bashrc  -->  target/.bashrc
stow/vim/dot-vimrc    -->  target/.vimrc
```

This allows packages to store dotfiles without the leading dot.

## Exception Hierarchy

```
StowError (base)
├── StowInternalError  # Internal bug
└── StowCLIError       # CLI usage error
```

The CLI catches these and formats appropriate error messages. Conflicts are not exceptions: they are reported via `StowResult.conflicts` (with `success=False`), never raised.

## CLI Structure

`cli.py` handles:
- Argument parsing (manual, for Perl compatibility)
- RC file loading (`~/.stowrc`, `.stowrc`)
- Environment variable expansion
- Main entry point

Option parsing is driven by a declarative option table (`_OPTION_SPECS`) combined with a hand-written resolver that emulates Getopt::Long's matching rules and a separate parser for bundled short options (`-npvS`).

## chkstow Module

`chkstow.py` provides target directory diagnostics:

- **List packages** (`-l`): Find all stowed packages
- **Bad links** (`-b`): Find broken symlinks
- **Aliens** (`-a`): Find non-stow files

## Testing Strategy

Three levels of testing:

1. **Unit tests**: Test library functions directly
2. **Oracle tests**: Compare Python vs Perl output
3. **Hypothesis tests**: Property-based random testing

See [perl-differences.md](perl-differences.md) for known edge case differences.
