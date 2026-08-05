# Perl Compatibility Notes

This is the `bug4bug` branch, which achieves syscall-level exact matching with GNU Stow 2.4.1 (Perl).

**No behavioral differences.** All known Perl behaviors are replicated, including edge cases and arguable bugs. The one deliberate difference is the program's own name and issue tracker, under [Deliberate Divergence: Program Identity](#deliberate-divergence-program-identity). What cannot be reproduced at all is text the Perl runtime itself generates; those are listed under [Residual deltas](#residual-deltas).

## Syscall Name Normalization

Python and Perl make the same filesystem operations but use different syscall names due to glibc internals:

| Python | Perl | Notes |
|--------|------|-------|
| `stat(path)` | `newfstatat(AT_FDCWD, path, ..., 0)` | Same operation |
| `lstat(path)` | `newfstatat(AT_FDCWD, path, ..., AT_SYMLINK_NOFOLLOW)` | Same operation |
| `open(path)` | `openat(AT_FDCWD, path)` | Same operation |

Both link to the same glibc but call different wrapper functions. The test suite normalizes these.

---

## Quirks We Match

These are Perl behaviors that are edge cases or arguably bugs, but we replicate them for exact compatibility.

### Byte-Level CLI Parsing

Perl's Getopt::Long parses command-line arguments byte-by-byte, which leads to quirky behavior with unusual inputs. We replicate this exactly:

- **`--o=0` style package names**: If you try to stow a package literally named `--o=0`, Perl's Getopt::Long silently consumes it as an unknown option with an empty value, then complains "No packages to stow". We do the same.
- **Non-ASCII bytes after `-`**: A package named `-\x80` (dash followed by byte 0x80) gets parsed character-by-character, printing "Unknown option" twice. We match this byte-level iteration.
- **Bundled options**: `-npvS` is parsed exactly as Perl does, including edge cases with attached values like `-d/path` or `-v3`.

### Newline Warnings

When Perl's `-w` warnings are enabled (as they are in stow), any `stat` or `lstat` on a path containing a newline prints `Unsuccessful stat on filename containing newline` to stderr. This is a Perl runtime warning, not stow code. We emit identical warnings using Python's `warnings` module.

### Empty Package Names

Running `stow ''` (empty string as package name) causes Perl to interpret it as the current directory, which means it tries to stow the entire stow directory contents - including all other packages and the `.stow` marker file. This is almost certainly not what anyone wants, but we replicate it.

### Newline in Path Breaks Ignore Check

When a directory path contains a newline character, Perl's ignore pattern matching silently malfunctions. A file like `backup~` that should be ignored by the default `.+~` pattern gets symlinked anyway. This happens because the newline warning disrupts the pattern matching logic. We replicate this bug.

### lstat Before unlink

Perl's built-in `unlink` function (in `doio.c`) includes a safety check for root users on ancient Unix systems that allowed root to delete directories with `unlink`. Before removing a file, Perl does an `lstat` to verify it's not a directory. On modern Linux this is redundant (the kernel returns EISDIR), but Perl still does it, and so do we.

### RC File Stat Check

Before reading `.stowrc` configuration files, Perl checks if the file is readable using the `-r` test, which translates to a `stat` syscall. Only then does it `open` the file. The Pythonic approach would be to just try opening and catch exceptions, but we match Perl's two-step check.

### File::Find Traversal Pattern

The `chkstow` utility walks directory trees to find packages, bad links, and alien files. Perl's `File::Find` module has a specific traversal pattern:
- It `chdir`s into directories rather than using absolute paths
- When backtracking multiple levels, it uses `chdir("../..")` rather than multiple `chdir("..")` calls
- It performs `lstat`, `readlink`, and `open` calls in a specific order

We replicate this exactly, including the multi-level chdir optimization.

### Filenames Are Byte Strings

Perl neither decodes nor encodes filenames, so a name that is not valid in the ambient locale passes through untouched, and `chkstow -l` sorts package names by their bytes (`\x80z` before `\xc3\xa9w`, the other way round from a comparison by code point). Python decodes filenames with `surrogateescape` and both executables encode their output the same way, so the original bytes reach stdout and stderr.

Every `sort` over filenames is a byte sort for the same reason: the entries of a package or target directory are processed in byte order, as is the list of conflicting packages and the conflicts within each. `sorted_by_bytes()` expresses that.

The ignore-list files and `.stowrc` are read as `\n`-delimited byte records too — a pattern with undecodable bytes is applied, not rejected — and the character classes applied to those records are the ASCII ones Perl uses on bytes, not Python's Unicode ones. A no-break space in front of an ignore pattern stays part of the pattern, and a `$` in `.stowrc` followed by a non-ASCII byte does not start a variable name.

### NFS-Robust Move

When using `--adopt` to move a file into the stow package, the `rename()` syscall might "fail" even though it succeeded - this happens on NFS when the server completes the operation but the acknowledgment is lost. Perl's `File::Copy::move` handles this by checking if the source file disappeared and the destination has the expected size. We implement the same check.

### Perl-Compatible shellwords for .stowrc

Perl's `Text::ParseWords::shellwords` has different semantics than Python's `shlex.split()`:

- **Double quotes**: `\X` → `X` for ANY character (Perl consumes the backslash)
- **Single quotes**: backslash is copied literally, but `\X` still spans two
  characters while scanning, so `\'` does NOT close the quote
- **Unquoted**: `\X` → `X` for ANY character
- **Empty quoted words** (`""` or `''`) are kept as empty words
- **Parse failure** (unmatched quote or trailing lone backslash) makes the
  WHOLE line yield no words at all
- Words are delimited by any whitespace (`\s+`), not just space/tab

Python's `shlex.split()` only escapes specific characters in double quotes (`\`, `"`, `$`, backtick, newline), preserving other backslash sequences literally, and it raises on unmatched quotes instead of dropping the line.

This matters for `.stowrc` regex patterns:
```
--ignore="\.git"
```
- Perl parses as: `--ignore=.git` (dot matches ANY character)
- Python shlex would give: `--ignore=\.git` (literal dot)

We implement `perl_shellwords()` as a faithful port of the `parse_line()`
loop in Text::ParseWords 3.31, verified by fuzzing against the real Perl
module, so `.stowrc` files parse identically in both implementations.

### canonpath Path Normalization

Perl's `File::Spec::Unix->canonpath()` normalizes paths but does NOT resolve `..` in the middle of paths (unlike Python's `os.path.normpath`):

- Perl: `canonpath("/a/b/../c")` → `/a/b/../c` (unchanged)
- Python `os.path.normpath`: `/a/b/../c` → `/a/c` (resolved)

We implement a custom `canonpath()` function that matches Perl's exact behavior, including the rules for collapsing leading `/../` sequences after root. Note that at runtime Perl uses PathTools' XS (C) `canonpath`, which differs from the pure-Perl fallback source on some edge cases (e.g. `"/..\n"` is not rewritten by XS); we match the XS behavior, verified by fuzzing against `File::Spec` directly.

### Getopt::Long Option Parsing

Perl stow's CLI is parsed by Getopt::Long with `no_ignore_case`, `bundling` and `permute`, which implies a number of behaviors we replicate exactly:

- Any option name or alias works in long form (`--R`, `--n`, `--t DIR`)
- Unique prefixes are auto-abbreviated (`--tar DIR`, `--verb`); an ambiguous prefix is reported (`Option ver is ambiguous (verbose, version)`) and skipped; `POSIXLY_CORRECT` disables abbreviation (and the `+` prefix)
- The whole argument list is parsed before anything is acted upon: each bad option prints its complaint and only tallies an error, so `--bogus --alsobad --third` reports all three, and `--bogus --dir` reports the unknown option and the missing argument. `GetOptions` returning false lands in `usage('')`, which prints the usage message on stdout and exits 1
- `--help` and `--version` are checked only after parsing has finished, help first — so `--version --help` prints the help, and either together with a bad option still exits 1
- A value option at the end of a bundle consumes the next argument (`-nt DIR`)
- `--verbose`/`-v`/`+verbose` consume a following integer argument as the level (`-v 2`). "Integer" is Getopt::Long's `PAT_INT`, `[-+]?_*[0-9][0-9_]*`, with one trailing newline allowed (Perl's `$`-anchored check). A value in its own argument has its underscores deleted before the number is read (`--verbose=1_0` is 10), one bundled onto the option does not, so Perl's numeric conversion stops at the first underscore and warns (`-v1_0` is 1, `-v_2` is 0)
- An empty attached value for a string option (`--dir=`) is a missing argument, but an empty separate argument (`-d ""`) is accepted
- The `=` of an attached value is the first one with at least one name character in front of it, so `--=x=y` is the unknown option `=x`
- Everything after `--` is left in `@ARGV`, which stow never reads — those arguments are silently discarded
- `+option` forms accept space-separated values but not `=` values; a bare `+` is `Missing option after +`
- The name in the version, usage and `usage(MSG)` lines is the basename of `$0`, so a renamed copy names itself; only the `stow: ERROR:` prefix stays the literal `stow` that `Stow::Util` hardcodes

chkstow's `GetOptions` runs under Getopt::Long's *defaults* instead — no bundling, case-insensitive names, `getopt_compat` on — which changes what its diagnostics say: a known option is named by its lowercased, prefix-expanded name (`--targ` → `Option target requires an argument`), an unknown one by the name the lookup gave up on, which auto_abbrev has lowercased (`--FOO` → `Unknown option: foo`) and `POSIXLY_CORRECT` has not (`Unknown option: FOO`). With `getopt_compat` off, `-t=x` does not split at the `=` and is the unknown option `t=x`.

### Exit Codes on die()

Perl's `die` exits with `$!` (the errno of the last failed syscall) when it is nonzero, else 255. Every place a syscall can fail records its errno, and a fatal error that carries no exit status of its own exits with the recorded one, so a refused `mkdir`, `symlink`, `opendir` or `chdir` exits 13 (EACCES) and a missing package exits 2 (ENOENT, from the `opendir`). A few messages carry an explicit status instead: the "Slashes are not permitted in package names" error exits 2 because probing the nonexistent `.stowrc` just before leaves ENOENT in errno (it exits 255 if a `.stowrc` exists, which we do not reproduce), and a regexp that fails to compile exits 255, where Perl's errno happens to be clear.

### sprintf-Formatted Error Messages

Perl's `error()` and `internal_error()` build their message by interpolating paths and package names into a string and then running that string through `sprintf`. Percent sequences in a name are therefore conversions: package `a%%b` is reported as `a%b`, and a conversion with no argument left substitutes undef and warns `Missing argument in sprintf` before the error line — so a target named `tg%s-100%` produces `cannot chdir to tg-100 0.000000rom /...`, the `% f` of `-100% from` having been consumed as a float. `perl_sprintf()` reproduces this, verified by fuzzing against Perl's own `sprintf`.

### Inline Regex Flags in Patterns

Perl applies an inline flag group such as `(?i)` from where it appears to the end of the enclosing group, across alternations; Python's `re` only accepts one at the very start of a whole pattern. User patterns from `--ignore`, `--override`, `--defer` and the ignore-list files are rewritten into scoped groups (`(?i)man` inside `(...)` becomes `(?i:man)`) so they compile and reach as far as Perl's do.

### Newline Warnings

Perl's stat/lstat builtins print `Unsuccessful (l)stat on filename containing newline` when the call FAILS on a filename that ENDS with a newline (the forgot-to-chomp heuristic; a newline in the middle does not warn). We reproduce this at every stat-family call site, including the `-d` tests behind `--dir value '...' is not a valid directory` and its `--target` counterpart. The `at FILE line N.` location suffix of Perl's warnings cannot be reproduced and is normalized away in the test harness.

### `$` Matches Before a Trailing Newline

Perl's `$` anchor matches at the end of the string *or* just before a newline that ends it, which changes what several patterns do to a name ending in `\n`:

- the guard `/^\.\.?$/` that keeps `unadjust_dotfile()` off the `.` and `..` entries also catches `".\n"` and `"..\n"`, so such an entry is left alone under `--compat --dotfiles -D`
- `s{/+$}{}` on a package name strips the slash in `"a/\n"`, leaving the usable package `"a\n"`. The substitution runs on a `foreach` alias, so it writes back into the package lists the rest of the run works from — `stow a//` really does plan for package `a`
- Getopt::Long's integer test accepts `"2\n"` as a `--verbose` value

Python's `$` behaves the same way but `\Z` does not, so each of these spells the anchor out (`\n?\Z`) where the Perl original relies on `$`.

### Ignore File Memoization

Perl memoizes the regexps of each ignore file the first time it manages to read one, keyed by path, and traces `Using memoized regexps from <file>` on every later consultation. A file it could not open is *not* remembered: `Failed to open <file>: <$!>` is traced and the open is retried at every node, so an unreadable `.stow-local-ignore` is opened once per entry. `invalidate_memoized_regexp()` drops one entry, for a caller that changes such a file mid-run.

### stdout Flush and SIGPIPE

Perl flushes stdout as it exits and, when that fails, prints `Unable to flush stdout: <$!>` and exits 1 — so `stow --version > /dev/full` reports `No space left on device` and `stow --version >&-` reports `Bad file descriptor`. Python raises inside the interpreter's own shutdown instead, and print to a closed stdout does nothing at all, so the flush is done explicitly at the end of `main()`. Perl also leaves SIGPIPE at its default disposition, so a reader that has gone away kills the process by signal (shell status 141); Python ignores SIGPIPE and raises `BrokenPipeError`, so the default is restored at entry.

### The String "0" Is False

Perl's boolean test makes the one-character string `0` false, so stow takes the false branch wherever a path, package name or link destination happens to be `0`. `perl_true()` expresses that test, and every guard that mirrors a Perl truth test uses it:

- `readlink` returning `0` counts as a failure, so reading such a link is fatal — `Could not read link: <path> (<$!>)` from `read_a_link()`, or `Could not read link <path>` (no colon, no errno) from `cleanup_invalid_links()`, which calls `readlink` directly
- a package named `0` never owns anything as far as folding and orphan clean-up are concerned: its trees are not folded and its dangling links are not removed
- a directory whose links all point into a package subdirectory called `0` is reported as containing no links, so it is not folded
- `--dir 0/sub` (or `STOW_DIR=0/sub`) has parent `0`, so the default target falls back to `.`
- `~0/...` captures username `0`, which takes the bare-tilde branch and expands to `$HOME`, and `HOME=0` falls through to `$LOGDIR` and then to the passwd entry

### Uninitialized Value Warnings

An unset `HOME` reaches three interpolations that Perl warns about, at every verbosity, once per evaluation: the tildify substitutions in `stow_contents()` and `unstow_contents()` (`$ENV{"HOME"} in regexp compilation`), and the global-ignore-file path built by `join_paths()` (`$paths[0] in join or string`). An unknown user in `~user` warns `in substitution iterator` and expands to nothing, so `~nosuchuser/t` becomes `/t`.

Those substitutions interpolate `$HOME` into a *pattern*, so its contents are read as a regexp and an empty or unset `HOME` matches at every position: the trace line for a target under `/var/tmp` comes out as `(cwd=~/var~/tmp~/...)`.

---

## Deliberate Divergence: Program Identity

This is a reimplementation, not GNU Stow, and it says so:

- `--version` prints `stow (Stow-Python) version 2.4.1` where Perl prints `stow (GNU Stow) version 2.4.1`
- the usage text carries the same version header, plus two lines naming the reimplementation and the original authors
- the usage footer points at this project's issue tracker instead of `bug-stow@gnu.org` and the GNU help pages

Everything else in the usage text — synopsis, option list, wording, spacing — is byte-identical to Perl's. `normalize_stow_output()` in the test harness maps the three branding differences back to Perl's wording so that the oracle tests still compare the rest byte for byte.

---

## Residual deltas

Text produced by the language runtime rather than by stow cannot be reproduced. The test harness normalizes these away where they would otherwise break a byte comparison.

- **Regex engine messages.** `Failed to compile regexp: ...` and the warning Getopt::Long prints for a bad `--ignore`/`--override`/`--defer` pattern quote the regex engine's own complaint. Perl says `Unmatched ( in regex; marked by <-- HERE in m/^( <-- HERE foo()$/`, Python says `missing ), unterminated subpattern at position 1`. The surrounding message, stream, blank line and exit status match.
- **Perl source locations in warnings.** Perl appends ` at <perl source file> line <N>.` to its warnings — the sprintf warnings, the uninitialized-value warnings, Getopt::Long's `Argument "..." isn't numeric in addition (+)`, the newline stat warnings, and File::Find's `Can't stat` / `Can't cd to` / `Can't opendir` warnings. The first three name the running script and keep Perl's line number; the others carry no location at all.
- **Ignore list regexp dumps.** The two `Ignore list regexp for paths:` / `for segments:` lines at -v5 print a compiled regexp. Its alternation is built from a hash, so Perl orders it differently on every run — the line cannot match byte for byte even against Perl itself. Everything else in the -v5 trace does, including Perl's `(?^: ... )` stringification of the regexp itself; the oracle trace test compares the whole stream with just these two lines dropped.
- **Deep recursion warnings.** Walking a tree some hundreds of levels deep makes Perl print `Deep recursion on subroutine "Stow::stow_contents"` and one more for `stow_node`. Python has no such runtime diagnostic. Both implementations complete the walk and exit 0.
- **Internal error stack trace.** The `INTERNAL ERROR` banner carries a Python traceback where Perl carries `Carp::longmess` frames. The banner around it — leading blank line, the trace starting on the message's own line, two blank lines, the closing note — and the exit status match. The bug report URL points at this project.
- **Exotic printf conversions.** `%p` in a name formats a memory address in Perl, which no other process can match, and a few rare flag/precision/size combinations on `%c`, `%o` and `%b` format differently.
- **Syscall names.** As described above, the same operations appear under different names in strace output.

---

## Testing

The test suite runs both implementations under strace and compares:
- Return codes
- Stdout/stderr output
- Filesystem operations (same syscalls in same order)

Property-based tests with Hypothesis generate random package structures to find edge cases.
