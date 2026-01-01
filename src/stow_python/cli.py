# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Command-line interface for stow-python.

This module contains the CLI functions including argument parsing,
configuration file handling, and the main entry point.
"""

from __future__ import annotations

import os
import pwd
import re
import shlex
import sys

from stow_python.stow import Stow
from stow_python.util import VERSION, PROGRAM_NAME, error, parent


def main() -> None:
    """Main entry point for stow command."""
    options, pkgs_to_unstow, pkgs_to_stow = process_options()

    stow = Stow(**options)

    stow.plan_unstow(*pkgs_to_unstow)
    stow.plan_stow(*pkgs_to_stow)

    conflicts = stow.get_conflicts()

    if conflicts:
        for action in ("unstow", "stow"):
            if action not in conflicts:
                continue
            for package in sorted(conflicts[action].keys()):
                print(
                    f"WARNING! {action}ing {package} would cause conflicts:",
                    file=sys.stderr,
                )
                for message in sorted(conflicts[action][package]):
                    print(f"  * {message}", file=sys.stderr)
        print("All operations aborted.", file=sys.stderr)
        sys.exit(1)
    else:
        if options.get("simulate"):
            print(
                "WARNING: in simulation mode so not modifying filesystem.",
                file=sys.stderr,
            )
            return

        stow.process_tasks()


def process_options() -> tuple[dict, list[str], list[str]]:
    """
    Parse and process command line and .stowrc file options.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    cli_options, pkgs_to_unstow, pkgs_to_stow = parse_options(sys.argv[1:])
    rc_options, _, _ = get_config_file_options()

    # Merge .stowrc and command line options
    options = dict(rc_options)
    for option, cli_value in cli_options.items():
        rc_value = rc_options.get(option)

        if isinstance(cli_value, list) and rc_value is not None:
            options[option] = list(rc_value) + list(cli_value)
        else:
            options[option] = cli_value

    sanitize_path_options(options)
    check_packages(pkgs_to_unstow, pkgs_to_stow)

    return (options, pkgs_to_unstow, pkgs_to_stow)


def parse_options(args: list[str]) -> tuple[dict, list[str], list[str]]:
    """
    Parse command line options.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    options: dict = {}
    pkgs_to_unstow: list[str] = []
    pkgs_to_stow: list[str] = []
    action = "stow"

    i = 0
    while i < len(args):
        arg = args[i]

        # Handle options with values
        if arg in ("-d", "--dir") and i + 1 < len(args):
            i += 1
            options["dir"] = args[i]
        elif arg.startswith("--dir="):
            options["dir"] = arg[6:]
        elif arg.startswith("-d") and len(arg) > 2:
            options["dir"] = arg[2:]

        elif arg in ("-t", "--target") and i + 1 < len(args):
            i += 1
            options["target"] = args[i]
        elif arg.startswith("--target="):
            options["target"] = arg[9:]
        elif arg.startswith("-t") and len(arg) > 2:
            options["target"] = arg[2:]

        elif arg == "--ignore" and i + 1 < len(args):
            i += 1
            regex = args[i]
            options.setdefault("ignore", []).append(re.compile(rf"({regex})\Z"))
        elif arg.startswith("--ignore="):
            regex = arg[9:]
            options.setdefault("ignore", []).append(re.compile(rf"({regex})\Z"))

        elif arg == "--override" and i + 1 < len(args):
            i += 1
            regex = args[i]
            options.setdefault("override", []).append(re.compile(rf"\A({regex})"))
        elif arg.startswith("--override="):
            regex = arg[11:]
            options.setdefault("override", []).append(re.compile(rf"\A({regex})"))

        elif arg == "--defer" and i + 1 < len(args):
            i += 1
            regex = args[i]
            options.setdefault("defer", []).append(re.compile(rf"\A({regex})"))
        elif arg.startswith("--defer="):
            regex = arg[8:]
            options.setdefault("defer", []).append(re.compile(rf"\A({regex})"))

        # Verbose option with optional value
        elif arg in ("-v", "--verbose"):
            options["verbose"] = options.get("verbose", 0) + 1
        elif arg.startswith("--verbose="):
            try:
                options["verbose"] = int(arg[10:])
            except ValueError:
                options["verbose"] = 1

        # Boolean flags
        elif arg in ("-n", "--no", "--simulate"):
            options["simulate"] = 1
        elif arg in ("-p", "--compat"):
            options["compat"] = 1
        elif arg == "--adopt":
            options["adopt"] = 1
        elif arg == "--no-folding":
            options["no-folding"] = 1
        elif arg == "--dotfiles":
            options["dotfiles"] = 1

        # Action flags
        elif arg in ("-D", "--delete"):
            action = "unstow"
        elif arg in ("-S", "--stow"):
            action = "stow"
        elif arg in ("-R", "--restow"):
            action = "restow"

        # Help and version
        elif arg in ("-h", "--help"):
            usage()
        elif arg in ("-V", "--version"):
            version()

        # Package argument
        elif not arg.startswith("-"):
            match action:
                case "restow":
                    pkgs_to_unstow.append(arg)
                    pkgs_to_stow.append(arg)
                case "unstow":
                    pkgs_to_unstow.append(arg)
                case _:
                    pkgs_to_stow.append(arg)

        else:
            opt_name = arg.lstrip("-")
            print(f"Unknown option: {opt_name}", file=sys.stderr)
            usage(exit_code=1)

        i += 1

    return (options, pkgs_to_unstow, pkgs_to_stow)


def sanitize_path_options(options: dict) -> None:
    """Validate and set defaults for dir and target options."""
    if "dir" not in options:
        stow_dir_env = os.environ.get("STOW_DIR", "")
        options["dir"] = stow_dir_env if stow_dir_env else os.getcwd()

    if not os.path.isdir(options["dir"]):
        usage(f"--dir value '{options['dir']}' is not a valid directory")

    if "target" in options:
        if not os.path.isdir(options["target"]):
            usage(f"--target value '{options['target']}' is not a valid directory")
    else:
        target = parent(options["dir"])
        options["target"] = target if target else "."


def check_packages(pkgs_to_stow: list[str], pkgs_to_unstow: list[str]) -> None:
    """Validate package names."""
    if not pkgs_to_stow and not pkgs_to_unstow:
        usage("No packages to stow or unstow")

    for package in list(pkgs_to_stow) + list(pkgs_to_unstow):
        package = package.rstrip("/")
        if "/" in package:
            error("Slashes are not permitted in package names")


def get_config_file_options() -> tuple[dict, list[str], list[str]]:
    """
    Search for default settings in any .stowrc files.

    Returns: (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)
    """
    defaults: list[str] = []
    dirlist = [".stowrc"]

    home = os.environ.get("HOME")
    if home:
        dirlist.insert(0, os.path.join(home, ".stowrc"))

    for file_path in dirlist:
        if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
            try:
                with open(file_path, "r") as f:
                    for line in f:
                        line = line.rstrip("\n\r")
                        try:
                            words = shlex.split(line)
                            defaults.extend(words)
                        except ValueError:
                            defaults.extend(line.split())
            except IOError:
                print(f"Could not open {file_path} for reading", file=sys.stderr)
                sys.exit(1)

    rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow = parse_options(defaults)

    if "target" in rc_options:
        rc_options["target"] = expand_filepath(rc_options["target"], "--target option")
    if "dir" in rc_options:
        rc_options["dir"] = expand_filepath(rc_options["dir"], "--dir option")

    return (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)


def expand_filepath(path: str, source: str) -> str:
    """Expand environment variables and tilde in file paths."""
    path = expand_environment(path, source)
    path = expand_tilde(path)
    return path


def expand_environment(path: str, source: str) -> str:
    """
    Expand environment variables.

    Replace non-escaped $VAR and ${VAR} with os.environ[VAR].
    """

    def replace_var(match):
        var = match.group(1) or match.group(2)
        if var not in os.environ:
            print(
                f"{source} references undefined environment variable ${var}; aborting!",
                file=sys.stderr,
            )
            sys.exit(1)
        return os.environ[var]

    path = re.sub(r"(?<!\\)\$\{([^}]+)\}", replace_var, path)
    path = re.sub(r"(?<!\\)\$(\w+)", replace_var, path)
    path = path.replace("\\$", "$")

    return path


def expand_tilde(path: str) -> str:
    """Expand tilde to user's home directory path."""
    if "\\~" in path:
        return path.replace("\\~", "~")

    if not path.startswith("~"):
        return path

    match = re.match(r"^~([^/]*)", path)
    if match:
        user = match.group(1)
        if user:
            try:
                home = pwd.getpwnam(user)[5]
            except KeyError:
                return path
        else:
            home = os.environ.get("HOME") or os.environ.get("LOGDIR")
            if not home:
                try:
                    home = pwd.getpwuid(os.getuid())[5]
                except KeyError:
                    return path

        path = home + path[len(match.group(0)) :]

    return path


def usage(msg: str | None = None, exit_code: int | None = None) -> None:
    """Print program usage message and exit."""
    if msg:
        print(f"{PROGRAM_NAME}: {msg}\n", file=sys.stderr)

    print(f"""{PROGRAM_NAME} (Stow-Python) version {VERSION}

Stow-Python is a Python reimplementation of GNU Stow.
Original GNU Stow by Bob Glickstein, Guillaume Morin, Kahlil Hodgson, Adam Spiers, and others.

SYNOPSIS:

    {PROGRAM_NAME} [OPTION ...] [-D|-S|-R] PACKAGE ... [-D|-S|-R] PACKAGE ...

OPTIONS:

    -d DIR, --dir=DIR     Set stow dir to DIR (default is current dir)
    -t DIR, --target=DIR  Set target to DIR (default is parent of stow dir)

    -S, --stow            Stow the package names that follow this option
    -D, --delete          Unstow the package names that follow this option
    -R, --restow          Restow (like stow -D followed by stow -S)

    --ignore=REGEX        Ignore files ending in this Perl regex
    --defer=REGEX         Don't stow files beginning with this Perl regex
                          if the file is already stowed to another package
    --override=REGEX      Force stowing files beginning with this Perl regex
                          if the file is already stowed to another package
    --adopt               (Use with care!)  Import existing files into stow package
                          from target.  Please read docs before using.
    --dotfiles            Enables special handling for dotfiles that are
                          Stow packages that start with "dot-" and not "."
    -p, --compat          Use legacy algorithm for unstowing

    -n, --no, --simulate  Do not actually make any filesystem changes
    -v, --verbose[=N]     Increase verbosity (levels are from 0 to 5;
                            -v or --verbose adds 1; --verbose=N sets level)
    -V, --version         Show stow version number
    -h, --help            Show this help

GNU Stow home page: <http://www.gnu.org/software/stow/>
Report deviations from GNU Stow: <https://github.com/isarandi/stow-python/issues>""")

    if exit_code is not None:
        sys.exit(exit_code)
    elif msg:
        sys.exit(1)
    else:
        sys.exit(0)


def version() -> None:
    """Print version and exit."""
    print(f"{PROGRAM_NAME} (Stow-Python) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
