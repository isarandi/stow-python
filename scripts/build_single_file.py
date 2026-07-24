#!/usr/bin/env python3
# Stow-Python - manage farms of symbolic links
# Python reimplementation of GNU Stow, and a derivative work of it.
#
# Copyright (C) 1993, 1994, 1995, 1996 by Bob Glickstein
# Copyright (C) 2000, 2001 Guillaume Morin
# Copyright (C) 2007 Kahlil Hodgson
# Copyright (C) 2011 Adam Spiers
# Copyright (C) 2025, 2026 Istvan Sarandi
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Stow-Python is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Stow-Python is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.

"""
Build single-file executables from stow_python modules.

This script concatenates stow_python modules into single executable
Python scripts that can be deployed without installation. Each artifact
is verified after the build: it must byte-compile and pass a smoke-test
invocation in a subprocess.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

# Order matters: dependencies must come before dependents
STOW_MODULES = ["types", "util", "stow", "cli"]
CHKSTOW_MODULES = ["chkstow"]

COPYRIGHT_HEADER = """\
# Stow-Python - manage farms of symbolic links
# Python reimplementation of GNU Stow, and a derivative work of it.
#
# Copyright (C) 1993, 1994, 1995, 1996 by Bob Glickstein
# Copyright (C) 2000, 2001 Guillaume Morin
# Copyright (C) 2007 Kahlil Hodgson
# Copyright (C) 2011 Adam Spiers
# Copyright (C) 2025, 2026 Istvan Sarandi
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Stow-Python is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Stow-Python is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.

# AUTO-GENERATED from stow_python modules - do not edit directly.
# Run scripts/build_single_file.py to regenerate.
# stow-python release {release} (behaves as GNU Stow {version})
"""

STOW_DOCSTRING = '''
"""
stow - manage farms of symbolic links

SYNOPSIS:
    stow [ options ] package ...

DESCRIPTION:
    Stow is a symlink farm manager which takes distinct sets of software
    and/or data located in separate directories on the filesystem, and
    makes them all appear to be installed in a single directory tree.
"""
'''

CHKSTOW_DOCSTRING = '''
"""
chkstow - Check stow target directory for problems.

Modes:
    -b, --badlinks  Report symlinks pointing to non-existent files (default)
    -a, --aliens    Report non-symlink, non-directory files
    -l, --list      List packages in the target directory
"""
'''

FOOTER = """

if __name__ == "__main__":
    main()
"""

# One (module, asname) or (name, asname) pair of an import statement
_ImportPair = tuple[str, str | None]


def read_version_constants(util_path: Path) -> tuple[str, str]:
    """Extract RELEASE and VERSION from util.py for the artifact header.

    The header comment is the only release identification a standalone
    single-file artifact carries (--version output is byte-identical to
    GNU Stow by design), so a missing constant must fail the build."""
    content = util_path.read_text()
    values = {}
    for name in ("VERSION", "RELEASE"):
        m = re.search(rf'^{name} = "([^"]+)"$', content, re.MULTILINE)
        if not m:
            print(f"Error: {name} constant not found in {util_path}", file=sys.stderr)
            sys.exit(1)
        values[name] = m.group(1)
    return values["RELEASE"], values["VERSION"]


def check_no_top_level_collisions(module_asts: dict[str, ast.Module]) -> None:
    """Fail the build if the concatenated modules bind one top-level name
    to two different things (two definitions, or a definition and an
    external import): the later binding would silently shadow the earlier
    one in the single-file artifact, even though the package form is fine.
    The same external import appearing in several modules is not a
    collision - the merged import block binds it once."""
    source_of: dict[str, str] = {}

    def record(module_name: str, name: str, source: str) -> None:
        previous = source_of.setdefault(name, source)
        if previous != source:
            print(
                f"Error: top-level name collision in {module_name}.py: "
                f"{name} is bound by both '{previous}' and '{source}'",
                file=sys.stderr,
            )
            sys.exit(1)

    for module_name, tree in module_asts.items():
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    record(module_name, bound, f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "__future__" or module.split(".")[0] == "stow_python":
                    continue
                for alias in node.names:
                    bound = alias.asname or alias.name
                    record(module_name, bound, f"from {module} import {alias.name}")
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                record(module_name, node.name, f"definition in {module_name}.py")
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        record(module_name, t.id, f"definition in {module_name}.py")
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                record(module_name, node.target.id, f"definition in {module_name}.py")


def extract_imports(
    content: str,
) -> tuple[set[_ImportPair], dict[str, set[_ImportPair]], str]:
    """Collect top-level imports via the AST and strip them, together with
    the module docstring, from the module body.

    Returns (plain_imports, from_imports, cleaned_content): plain_imports
    holds (module, asname) pairs of `import x [as y]` statements, and
    from_imports maps a module to its set of (name, asname) pairs from
    `from x import ...` statements. __future__ imports are dropped (the
    build adds one header import) and stow_python-internal imports are
    dropped (satisfied by concatenation). Working on the AST keeps aliased
    imports (import errno as errno_module) and parenthesized multi-line
    imports intact; a regex-based predecessor of this function silently
    dropped an alias, producing an artifact that crashed at runtime.
    """
    tree = ast.parse(content)
    lines = content.split("\n")
    dropped_linenos: set[int] = set()
    plain_imports: set[_ImportPair] = set()
    from_imports: dict[str, set[_ImportPair]] = {}

    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        dropped_linenos.update(range(body[0].lineno - 1, body[0].end_lineno or 0))

    for node in body:
        if isinstance(node, ast.Import):
            dropped_linenos.update(range(node.lineno - 1, node.end_lineno or 0))
            for alias in node.names:
                plain_imports.add((alias.name, alias.asname))
        elif isinstance(node, ast.ImportFrom):
            dropped_linenos.update(range(node.lineno - 1, node.end_lineno or 0))
            module = node.module or ""
            if module == "__future__" or module.split(".")[0] == "stow_python":
                continue
            for alias in node.names:
                from_imports.setdefault(module, set()).add((alias.name, alias.asname))

    cleaned = "\n".join(
        line for lineno, line in enumerate(lines) if lineno not in dropped_linenos
    )
    return plain_imports, from_imports, cleaned


def render_imports(
    plain_imports: set[_ImportPair], from_imports: dict[str, set[_ImportPair]]
) -> str:
    """Render the merged import block: plain imports first, then one
    `from` import per module with its names merged across all source
    modules, everything sorted for a deterministic artifact."""

    def fmt(name: str, asname: str | None) -> str:
        return f"{name} as {asname}" if asname else name

    def pair_key(pair: _ImportPair) -> tuple[str, str]:
        return (pair[0], pair[1] or "")

    lines = [f"import {fmt(*pair)}" for pair in sorted(plain_imports, key=pair_key)]
    lines += [
        f"from {module} import "
        + ", ".join(fmt(*pair) for pair in sorted(names, key=pair_key))
        for module, names in sorted(from_imports.items())
    ]
    return "\n".join(lines)


def remove_copyright_header(content: str) -> str:
    """Remove the copyright header comments."""
    lines = content.split("\n")
    result_lines: list[str] = []
    in_header = True

    for line in lines:
        if in_header:
            # Skip comment lines and blank lines at the start
            if line.startswith("#") or line.strip() == "":
                continue
            in_header = False
        result_lines.append(line)

    return "\n".join(result_lines)


def build_executable(
    modules: list[str],
    output_name: str,
    docstring: str,
    project_root: Path,
    smoke_args: list[str],
) -> None:
    """Build a single-file executable from the given modules."""
    stow_python_dir = project_root / "src" / "stow_python"
    output_file = project_root / "bin" / output_name

    plain_imports: set[_ImportPair] = set()
    from_imports: dict[str, set[_ImportPair]] = {}
    module_contents: list[str] = []
    module_asts: dict[str, ast.Module] = {}

    for module_name in modules:
        module_path = stow_python_dir / f"{module_name}.py"
        if not module_path.exists():
            print(f"Error: Module not found: {module_path}", file=sys.stderr)
            sys.exit(1)

        content = module_path.read_text()
        module_asts[module_name] = ast.parse(content)

        # Extract imports (and the docstring) and clean the content
        module_plain, module_from, content = extract_imports(content)
        plain_imports.update(module_plain)
        for module, names in module_from.items():
            from_imports.setdefault(module, set()).update(names)

        content = remove_copyright_header(content)

        # Remove the if __name__ == '__main__' block (handles both quote styles)
        content = re.sub(
            r"\nif __name__ == ['\"]__main__['\"]:\n    main\(\)\n?", "", content
        )
        # The removal above matches the block's exact text; if the block is
        # ever reformatted, it must fail the build rather than survive
        # embedded mid-artifact where it would execute during import
        if "__main__" in content:
            print(
                f"Error: __main__ block in {module_name}.py did not match the "
                "removal pattern in build_single_file.py",
                file=sys.stderr,
            )
            sys.exit(1)

        # Add section marker for multi-module builds
        if len(modules) > 1:
            section_header = (
                f"\n\n{'#' * 78}\n# From stow_python/{module_name}.py\n{'#' * 78}\n\n"
            )
            module_contents.append(section_header + content.strip())
        else:
            module_contents.append(content.strip())

    check_no_top_level_collisions(module_asts)

    # Build the final output
    release, version = read_version_constants(stow_python_dir / "util.py")
    output_parts = [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        "",
        COPYRIGHT_HEADER.format(release=release, version=version),
        docstring,
        "from __future__ import annotations",
        "",
        render_imports(plain_imports, from_imports),
    ]
    output_parts.extend(module_contents)
    output_parts.append(FOOTER)

    output_content = "\n".join(output_parts)

    # Clean up multiple blank lines
    output_content = re.sub(r"\n{4,}", "\n\n\n", output_content)

    # The artifact must at minimum byte-compile before it is written out
    compile(output_content, str(output_file), "exec")

    output_file.write_text(output_content)
    output_file.chmod(0o755)

    # ... and actually run: a build defect that only manifests at runtime
    # (a mangled import, a name collision between concatenated modules)
    # must fail the build, not the first user who hits the affected path.
    result = subprocess.run(
        [sys.executable, str(output_file), *smoke_args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: smoke test of {output_file} failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print(f"Built: {output_file}")
    print(f"  Modules: {', '.join(modules)}")
    print(f"  Imports: {len(plain_imports) + sum(map(len, from_imports.values()))}")

    # Count lines
    line_count = len(output_content.split("\n"))
    print(f"  Lines: {line_count}")


def build() -> None:
    """Build all single-file executables."""
    project_root = Path(__file__).parent.parent

    # Build stow; --version exits 0 without touching the filesystem
    build_executable(
        STOW_MODULES, "stow", STOW_DOCSTRING, project_root, smoke_args=["--version"]
    )

    print()

    # Build chkstow; without arguments it prints usage and exits 0
    build_executable(
        CHKSTOW_MODULES, "chkstow", CHKSTOW_DOCSTRING, project_root, smoke_args=[]
    )


if __name__ == "__main__":
    build()
