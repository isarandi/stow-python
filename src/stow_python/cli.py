# Stow-Python - Python reimplementation of GNU Stow
# Copyright (C) 2025 Istvan Sarandi
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Command-line interface for stow-python.

This module contains the CLI functions including argument parsing,
configuration file handling, and the main entry point.
"""

from __future__ import annotations
import itertools
import os
import pwd
import re
import shlex
import sys
import traceback
from typing import Sequence

from stow_python.stow import _Stower
from stow_python.types import StowError, StowProgrammingError, StowCLIError, StowConfig
from stow_python.util import VERSION, PROGRAM_NAME, parent


def main() -> None:
    """Main entry point for stow command."""
    try:
        _main()
    except StowProgrammingError as e:
        print(
            f"\n{PROGRAM_NAME}: INTERNAL ERROR: {e.message}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        print(
            "This _is_ a bug. Please submit a bug report so we can fix it! :-)",
            file=sys.stderr,
        )
        print(
            "See https://github.com/isarandi/stow-python for how to do this.",
            file=sys.stderr,
        )
        sys.exit(e.errno)
    except StowCLIError as e:
        print(e.message, file=sys.stderr)
        sys.exit(e.errno)
    except StowError as e:
        print(f"{PROGRAM_NAME}: ERROR: {e.message}", file=sys.stderr)
        sys.exit(e.errno)


def _main() -> None:
    """Main implementation (can raise StowError)."""
    options, pkgs_to_unstow, pkgs_to_stow = process_options()

    # Build StowConfig from parsed options
    config = StowConfig(
        dir=options.get("dir", "."),
        target=options.get("target"),
        dotfiles=options.get("dotfiles", False),
        adopt=options.get("adopt", False),
        no_folding=options.get("no-folding", False),
        simulate=options.get("simulate", False),
        verbose=options.get("verbose", 0),
        compat=options.get("compat", False),
        ignore=tuple(options.get("ignore", [])),
        defer=tuple(options.get("defer", [])),
        override=tuple(options.get("override", [])),
    )

    stower = _Stower(config)
    stower.plan_unstow(pkgs_to_unstow)
    stower.plan_stow(pkgs_to_stow)

    if stower.conflicts:
        for package in sorted(stower.conflicts.keys()):
            print(
                f"WARNING! stowing {package} would cause conflicts:",
                file=sys.stderr,
            )
            for message in sorted(stower.conflicts[package]):
                print(f"  * {message}", file=sys.stderr)
        print("All operations aborted.", file=sys.stderr)
        sys.exit(1)
    else:
        if config.simulate:
            print(
                "WARNING: in simulation mode so not modifying filesystem.",
                file=sys.stderr,
            )
            return

        stower.process_tasks()


def _parse_bundled_options(
    chars: str, options: dict, action: str
) -> tuple[str, bool, bool, bool]:
    """Parse bundled short options like -npvS.

    Perl's Getopt::Long iterates byte-by-byte, not character-by-character.
    We re-encode to bytes to match this behavior for multi-byte characters.

    Returns (action, has_any_unknown_options, should_show_help, should_show_version).
    """
    has_any_unknown_options = False
    should_show_help = False
    should_show_version = False

    # Convert to bytes to iterate byte-by-byte like Perl
    char_bytes = chars.encode('utf-8', errors='surrogateescape')
    i = 0

    while i < len(char_bytes):
        byte = char_bytes[i]
        char = chr(byte) if byte < 128 else char_bytes[i:i+1].decode('latin-1')
        rest_bytes = char_bytes[i + 1:]
        rest = rest_bytes.decode('utf-8', errors='surrogateescape')

        match char:
            case "n":
                options["simulate"] = True
            case "p":
                options["compat"] = True
            case "v" if (m := re.match(r"\d+", rest)):
                options["verbose"] = int(m.group())
                # Skip bytes for matched digits
                i += len(m.group().encode('utf-8'))
            case "v":
                options["verbose"] = options.get("verbose", 0) + 1
            case "S":
                action = "stow"
            case "D":
                action = "unstow"
            case "R":
                action = "restow"
            case "h":
                should_show_help = True
            case "V":
                should_show_version = True
            case "d" | "t" if rest:
                options["dir" if char == "d" else "target"] = rest
                i += len(rest_bytes)  # Skip remaining bytes
            case "d" | "t":
                show_usage_and_exit(f"Option {char} requires an argument")
            case _:
                # Output raw byte like Perl does
                sys.stderr.buffer.write(b"Unknown option: " + bytes([byte]) + b"\n")
                sys.stderr.buffer.flush()
                has_any_unknown_options = True
                # Perl continues processing all bytes, printing each unknown
        i += 1

    return action, has_any_unknown_options, should_show_help, should_show_version


def process_options() -> tuple[dict, list[str], list[str]]:
    """Parse and process command line and .stowrc file options.

    Returns: (options, pkgs_to_unstow, pkgs_to_stow)
    """
    cli_options, pkgs_to_unstow, pkgs_to_stow = parse_cli_options(sys.argv[1:])
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


def parse_cli_options(args: Sequence[str]) -> tuple[dict, list[str], list[str]]:
    """Parse command line options.

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
            options["simulate"] = True
        elif arg in ("-p", "--compat"):
            options["compat"] = True
        elif arg == "--adopt":
            options["adopt"] = True
        elif arg == "--no-folding":
            options["no-folding"] = True
        elif arg == "--dotfiles":
            options["dotfiles"] = True

        # Action flags
        elif arg in ("-D", "--delete"):
            action = "unstow"
        elif arg in ("-S", "--stow"):
            action = "stow"
        elif arg in ("-R", "--restow"):
            action = "restow"

        # Help and version
        elif arg in ("-h", "--help"):
            show_usage_and_exit()
        elif arg in ("-V", "--version"):
            show_version_and_exit()

        # Support + prefix (Perl's Getopt::Long getopt_compat mode)
        # With +, bundling does NOT apply - treat as long option attempt
        elif arg == "+":
            # Bare + with nothing after it
            show_usage_and_exit("Missing option after +")
        elif arg.startswith("+") and len(arg) > 1:
            opt = arg[1:]
            # Map known long options
            if opt in ("verbose", "v"):
                options["verbose"] = options.get("verbose", 0) + 1
            elif opt in ("n", "no", "simulate"):
                options["simulate"] = True
            elif opt in ("p", "compat"):
                options["compat"] = True
            elif opt == "adopt":
                options["adopt"] = True
            elif opt == "no-folding":
                options["no-folding"] = True
            elif opt == "dotfiles":
                options["dotfiles"] = True
            elif opt in ("D", "delete"):
                action = "unstow"
            elif opt in ("S", "stow"):
                action = "stow"
            elif opt in ("R", "restow"):
                action = "restow"
            elif opt in ("h", "help"):
                show_usage_and_exit()
            elif opt in ("V", "version"):
                show_version_and_exit()
            else:
                # Unknown + option: report first BYTE only (Perl behavior)
                first_byte = opt.encode('utf-8', errors='surrogateescape')[0:1]
                sys.stderr.buffer.write(b"Unknown option: " + first_byte + b"\n")
                sys.stderr.buffer.flush()
                show_usage_and_exit(exit_code=1)

        # Package argument (including "-" which is a valid package name)
        elif not arg.startswith("-") or arg == "-":
            match action:
                case "restow":
                    pkgs_to_unstow.append(arg)
                    pkgs_to_stow.append(arg)
                case "unstow":
                    pkgs_to_unstow.append(arg)
                case _:
                    pkgs_to_stow.append(arg)

        elif arg.startswith("--"):
            # Unknown long option - split at = first like Getopt::Long
            opt_name = arg[2:]
            if "=" in opt_name:
                opt_name = opt_name.split("=", 1)[0]
            show_usage_and_exit(f"Unknown option: {opt_name}")

        else:
            # Bundled short options: -xyz is parsed as -x -y -z
            action, has_any_unknown_options, should_show_help, should_show_version = (
                _parse_bundled_options(arg[1:], options, action)
            )
            if has_any_unknown_options:
                show_usage_and_exit(exit_code=1)
            if should_show_help:
                show_usage_and_exit()
            if should_show_version:
                show_version_and_exit()

        i += 1

    return (options, pkgs_to_unstow, pkgs_to_stow)


def sanitize_path_options(options: dict) -> None:
    """Validate and set defaults for dir and target options."""
    if "dir" not in options:
        stow_dir_env = os.environ.get("STOW_DIR")
        options["dir"] = stow_dir_env if stow_dir_env else os.getcwd()

    if not os.path.isdir(options["dir"]):
        show_usage_and_exit(f"{PROGRAM_NAME}: --dir value '{options['dir']}' is not a valid directory\n")

    if "target" in options:
        if not os.path.isdir(options["target"]):
            show_usage_and_exit(f"{PROGRAM_NAME}: --target value '{options['target']}' is not a valid directory\n")
    else:
        target = parent(options["dir"])
        options["target"] = target if target else "."


def check_packages(pkgs_to_stow: Sequence[str], pkgs_to_unstow: Sequence[str]) -> None:
    """Validate package names."""
    if not pkgs_to_stow and not pkgs_to_unstow:
        show_usage_and_exit(f"{PROGRAM_NAME}: No packages to stow or unstow\n")

    for package in itertools.chain(pkgs_to_stow, pkgs_to_unstow):
        package = package.rstrip("/")
        if "/" in package:
            raise StowError("Slashes are not permitted in package names")


def get_config_file_options() -> tuple[dict, list[str], list[str]]:
    """Search for default settings in any .stowrc files.

    Returns: (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)
    """
    defaults: list[str] = []
    stowrc_candidate_paths = [".stowrc"]

    home = os.environ.get("HOME")
    if home:
        stowrc_candidate_paths.insert(0, os.path.join(home, ".stowrc"))

    for file_path in stowrc_candidate_paths:
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.rstrip("\n\r")
                    try:
                        defaults.extend(shlex.split(line))
                    except ValueError:
                        defaults.extend(line.split())
        except (FileNotFoundError, PermissionError):
            continue  # Skip missing or unreadable files
        except IsADirectoryError:
            raise StowCLIError(f"Could not open {file_path} for reading")

    rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow = parse_cli_options(defaults)

    if "target" in rc_options:
        rc_options["target"] = expand_filepath(rc_options["target"], "--target option")
    if "dir" in rc_options:
        rc_options["dir"] = expand_filepath(rc_options["dir"], "--dir option")

    return (rc_options, rc_pkgs_to_unstow, rc_pkgs_to_stow)


def expand_filepath(path: str, source: str) -> str:
    """Expand environment variables and tilde in file paths."""
    path = expand_environment_variables(path, source)
    path = expand_tilde_to_homedir(path)
    return path


def expand_environment_variables(path: str, source: str) -> str:
    """Expand environment variables in path.

    Replace non-escaped $VAR and ${VAR} with os.environ[VAR].
    """

    def replace_var(match):
        var = match.group(1)
        try:
            return os.environ[var]
        except KeyError:
            raise StowCLIError(
                f"{source} references undefined environment variable ${var}; aborting!"
            )

    path = re.sub(r"(?<!\\)\$\{([^}]+)}", replace_var, path)
    path = re.sub(r"(?<!\\)\$(\w+)", replace_var, path)
    path = path.replace("\\$", "$")

    return path


def expand_tilde_to_homedir(path: str) -> str:
    """Expand tilde to user's home directory path."""
    if "\\~" in path:
        return path.replace("\\~", "~")

    if not path.startswith("~"):
        return path

    # Split ~username/rest into parts
    tilde_part, slash, rest = path.partition("/")
    username = tilde_part.removeprefix("~")

    if username:
        home = get_homedir_from_passwd(username=username)
    else:
        home = (
                os.environ.get("HOME")
                or os.environ.get("LOGDIR")
                or get_homedir_from_passwd()
        )

    if not home:
        return path
    return home + slash + rest


def get_homedir_from_passwd(username: str | None = None, uid: int | None = None) -> str | None:
    try:
        if username is not None:
            return pwd.getpwnam(username).pw_dir
        if uid is not None:
            return pwd.getpwuid(uid).pw_dir
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None


def show_usage_and_exit(msg: str | None = None, exit_code: int | None = None) -> None:
    """Print program usage message and exit."""
    if msg:
        print(msg, file=sys.stderr)

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


def show_version_and_exit() -> None:
    """Print version and exit."""
    print(f"{PROGRAM_NAME} (Stow-Python) version {VERSION}")
    sys.exit(0)


if __name__ == "__main__":
    main()
