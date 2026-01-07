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

Immutable configuration dataclass:

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
| `ignore` | tuple | () | Patterns to ignore |
| `defer` | tuple | () | Patterns to defer to other packages |
| `override` | tuple | () | Patterns to override other packages |

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
        self.dir_task_for: dict[str, Task] = {}   # Track dir operations
        self.link_task_for: dict[str, Task] = {}  # Track link operations
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

Tasks represent deferred filesystem operations:

```python
@dataclass
class Task:
    action: TaskAction   # CREATE, REMOVE, SKIP, MOVE
    type: TaskType       # LINK, DIR, FILE
    path: str            # Target path
    source: str | None   # For links: where it points
    dest: str | None     # For moves: destination
```

Tasks are tracked in dictionaries to detect conflicts:
- `dir_task_for[path]`: Pending directory operation at path
- `link_task_for[path]`: Pending symlink operation at path

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
    "emacs": ["existing target is not a symlink: bin/emacs"],
    "vim": ["existing target owned by other package: share/doc"],
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
2. **Global ignore**: `<stow_dir>/.stow-global-ignore`
3. **Local ignore**: `<package>/.stow-local-ignore`

Ignore files use regex patterns (Perl-compatible), one per line.

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
├── StowProgrammingError  # Internal bug
├── StowConflictError     # Conflicts detected
└── StowCLIError          # CLI usage error
```

The CLI catches these and formats appropriate error messages.

## CLI Structure

`cli.py` handles:
- Argument parsing (manual, for Perl compatibility)
- RC file loading (`~/.stowrc`, `.stowrc`)
- Environment variable expansion
- Main entry point

Option parsing uses `match/case` for bundled short options (`-npvS`).

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
