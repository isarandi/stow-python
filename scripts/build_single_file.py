#!/usr/bin/env python3
# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Build single-file executables from stow_python modules.

This script concatenates stow_python modules into single executable
Python scripts that can be deployed without installation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Order matters: dependencies must come before dependents
STOW_MODULES = ["types", "util", "stow", "cli"]
CHKSTOW_MODULES = ["chkstow"]

COPYRIGHT_HEADER = """\
# Stow-Python - Python reimplementation of GNU Stow
# Python reimplementation:
#   Copyright (C) 2025 Istvan Sarandi
# Original GNU Stow:
#   Copyright (C) 1993, 1994, 1995, 1996 by Bob Glickstein
#   Copyright (C) 2000, 2001 Guillaume Morin
#   Copyright (C) 2007 Kahlil Hodgson
#   Copyright (C) 2011 Adam Spiers
#   and others.
#
# This file is part of Stow-Python.
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


def extract_imports(content: str) -> tuple[set[str], str]:
    """
    Extract standard library imports and remove stow_python imports.

    Returns (stdlib_imports, cleaned_content).
    """
    stdlib_imports: set[str] = set()

    # Remove multi-line stow_python imports: from stow_python.xxx import (\n...\n)
    content = re.sub(
        r"from stow_python\.\w+ import \([^)]+\)\n?", "", content, flags=re.DOTALL
    )
    # Remove single-line stow_python imports
    content = re.sub(
        r"^from stow_python\.\w+ import [^\n]+\n", "", content, flags=re.MULTILINE
    )
    content = re.sub(r"^import stow_python[^\n]*\n", "", content, flags=re.MULTILINE)

    lines = content.split("\n")
    cleaned_lines: list[str] = []

    for line in lines:
        # Collect stdlib imports (single line)
        if match := re.match(r"^(from \S+ import .+|import \S+)", line):
            import_line = match.group(1)
            # Skip __future__ imports (we add them in header)
            if "from __future__" in import_line:
                continue
            stdlib_imports.add(import_line)
            continue

        cleaned_lines.append(line)

    return stdlib_imports, "\n".join(cleaned_lines)


def remove_module_docstring(content: str) -> str:
    """Remove the module-level docstring."""
    # Match triple-quoted docstring at start (after any comments/blank lines)
    pattern = r'^(\s*#[^\n]*\n)*\s*"""[\s\S]*?"""\s*\n'
    return re.sub(pattern, "", content, count=1)


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
) -> None:
    """Build a single-file executable from the given modules."""
    stow_python_dir = project_root / "src" / "stow_python"
    output_file = project_root / "bin" / output_name

    all_imports: set[str] = set()
    module_contents: list[str] = []

    for module_name in modules:
        module_path = stow_python_dir / f"{module_name}.py"
        if not module_path.exists():
            print(f"Error: Module not found: {module_path}", file=sys.stderr)
            sys.exit(1)

        content = module_path.read_text()

        # Extract imports and clean content
        imports, content = extract_imports(content)
        all_imports.update(imports)

        # Remove module docstring and copyright header
        content = remove_copyright_header(content)
        content = remove_module_docstring(content)

        # Remove the if __name__ == '__main__' block (handles both quote styles)
        content = re.sub(
            r"\nif __name__ == ['\"]__main__['\"]:\n    main\(\)\n?", "", content
        )

        # Add section marker for multi-module builds
        if len(modules) > 1:
            section_header = (
                f"\n\n{'#' * 78}\n# From stow_python/{module_name}.py\n{'#' * 78}\n\n"
            )
            module_contents.append(section_header + content.strip())
        else:
            module_contents.append(content.strip())

    # Build the final output
    output_parts = [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        "",
        COPYRIGHT_HEADER,
        docstring,
        "from __future__ import annotations",
        "",
    ]

    # Add sorted imports
    sorted_imports = sorted(
        all_imports, key=lambda x: (not x.startswith("import "), x.lower())
    )
    output_parts.append("\n".join(sorted_imports))

    # Add module contents
    output_parts.extend(module_contents)

    # Add footer
    output_parts.append(FOOTER)

    # Write output
    output_content = "\n".join(output_parts)

    # Clean up multiple blank lines
    output_content = re.sub(r"\n{4,}", "\n\n\n", output_content)

    output_file.write_text(output_content)
    output_file.chmod(0o755)

    print(f"Built: {output_file}")
    print(f"  Modules: {', '.join(modules)}")
    print(f"  Imports: {len(all_imports)}")

    # Count lines
    line_count = len(output_content.split("\n"))
    print(f"  Lines: {line_count}")


def build() -> None:
    """Build all single-file executables."""
    project_root = Path(__file__).parent.parent

    # Build stow
    build_executable(STOW_MODULES, "stow", STOW_DOCSTRING, project_root)

    print()

    # Build chkstow
    build_executable(CHKSTOW_MODULES, "chkstow", CHKSTOW_DOCSTRING, project_root)


if __name__ == "__main__":
    build()
