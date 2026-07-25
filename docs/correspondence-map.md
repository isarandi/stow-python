# stow-python ↔ GNU Stow 2.4.1 correspondence map

This map pairs every subroutine of GNU Stow 2.4.1 (Perl) with the Python code
that carries out its work, and records how close that correspondence is at the
level of observable behaviour: exit status, byte-exact stdout/stderr, the
sequence of filesystem operations, and the resulting tree. It is meant to be
read alongside [perl-differences.md](perl-differences.md): every intentional
behavioural difference cited below is documented there and pinned by a test
asserting both behaviours.

**Conventions**

* Perl line numbers refer to `lib/Stow.pm`, `lib/Stow/Util.pm`, `bin/stow` and
  `bin/chkstow` of GNU Stow 2.4.1 — the pinned oracle version, so they stay
  valid. Python code is cited by file and symbol.
* This map describes the maintained package sources (`src/stow_python/`) and
  the single-file executables built from them. The frozen `py27-literal`
  branch is a separate line-for-line transpilation with its own known defects
  and is not covered here.

**Classification vocabulary**

| Classification | Meaning |
| --- | --- |
| `faithful` | Statement-for-statement port; no behavioural difference. |
| `restructured` | Body reshaped (callback → context manager or generator, mutual recursion → explicit job stack, hash → dataclass, accessor → attribute) with no observable difference. |
| `divergent_documented` | Behaviour differs only in ways recorded in `perl-differences.md` (entry numbers cited). |
| `divergent_open` | A known, tracked behavioural difference not yet resolved or documented. |
| `infrastructure_only` | Perl-runtime or test-harness plumbing with no user-visible effect and no counterpart. |

Rows are in source-line order within each file.

---

## lib/Stow.pm

| Perl sub | Python counterpart(s) | Classification | Notes |
| --- | --- | --- | --- |
| `new` (135-166) | `stow.py: _Stower.__init__`; `types.py: StowConfig`; `stow.py: _make_config` | restructured | Constructor absorbs `set_stow_dir` and `init_state`; option hash becomes a frozen dataclass, unknown-key rejection retained. `canon_path` order and both level-2 debug lines unchanged. Perl's dead `action_count`/`paranoid` state has no counterpart. |
| `get_verbosity` (168-181) | `stow.py: _Stower._session`; `util.py: set_debug_level` | restructured | Production half is `set_debug_level(config.verbose)`, applied per phase instead of once in the constructor. The `test_mode`/`TEST_VERBOSE` branch is unreachable from either executable and is not ported. |
| `set_stow_dir` (197-215) | inlined in `_Stower.__init__`; `util.py: canon_path` | restructured | Canonicalisation order, `os.path.relpath` for `abs2rel`, and both "stow dir is …" lines are identical. The optional re-set argument has no counterpart: each operation builds a fresh stower. |
| `init_state` (217-260) | `_Stower.__init__` state; `types.py` task dataclasses | restructured | `conflicts` flattened to package → messages (the action level only ever holds `stow` in 2.4.1); `tasks`, `dir_task_for`, `link_task_for` retained. `conflict_count`, `pkgs_to_stow`, `pkgs_to_delete` are dead upstream and dropped. |
| `plan_unstow` (270-294) | `stow.py: plan_unstow`; `util.py: within_dir`, `require_directory` | divergent_documented | Near-literal port: same early return, same three debug messages. Fatal-path differences only: Perl's `sprintf` mangling (#26) and cwd restoration (#27). |
| `plan_stow` (304-329) | `stow.py: plan_stow` | divergent_documented | Statement-for-statement. The only difference is the up-front rejection of an empty package name (#6). |
| `within_target_do` (349-362) | `util.py: within_dir`; `stow.py: _Stower._session` | divergent_documented | Method-taking-a-callback becomes a context manager; chdir target, "cwd now" line and the three call sites are preserved. Python restores the directory in a `finally` where Perl does not on `die` (#27); the chdir-failure message itself is byte-identical. |
| `stow_contents` (401-453) | `stow.py: stow_contents`, `_stow_scan_dir`, `_stow_visit_node` | restructured | Split into scan and visit, driven by an explicit LIFO job stack that reproduces Perl's depth-first order and syscall sequencing. Skip check, `is_a_node` guard, byte-order sorted listing, ignore call and dotfile adjustment all match. |
| `stow_node` (492-661) | `stow.py: _stow_node`, `_stow_node_for_existing_link`, `_stow_node_for_existing_node` | divergent_documented | Absolute-symlink guard, level arithmetic, link destination and the 3-way dispatch are exact; unfold ordering is preserved by the job stack; all conflict strings byte-identical. Perl aborts on a symlink destination of `0` where we treat it as the ordinary value it is (#25); Perl's deep-recursion warning noise is not reproduced (#4). |
| `should_skip_target` (686-708) | `stow.py: _should_skip_target` | faithful | Three guards in Perl's order, byte-identical warnings, including the upstream quirk of passing the package subdirectory at the stow call site. |
| `marked_stow_dir` (711-720) | `stow.py: _is_marked_stow_dir` | faithful | `-e join_paths(dir, ".stow")` → `os.path.exists`; same `debug(5, 5)` line; return value used only in boolean context. |
| `unstow_contents` (752-841) | `stow.py: unstow_contents`, `_unstow_scan_dir`, `_unstow_visit_node` | divergent_documented | Recursion replaced by an order-equivalent job stack (children → cleanup → fold). Three error guards, `--compat` directory choice, sorted listing, ignore call and both dotfile branches match. With `HOME` empty, Perl mangles its own `-v3` line where we print it clean (#19). |
| `unstow_node` (872-899) | `stow.py: _unstow_node`, `_fold_if_foldable` | restructured | 4-way dispatch and all four debug strings unchanged; the post-recursion fold becomes a queued job that pops in Perl's position, including after an early skip. |
| `unstow_link_node` (901-944) | `stow.py: _unstow_link_node` | divergent_documented | Branch order, helper call order and all messages match; the `('','','')` sentinel becomes an optional value. Perl aborts on a target link pointing at `0` (#25). |
| `link_owned_by_package` (969-976) | `stow.py: _get_owning_package` | divergent_documented | A one-line wrapper over `find_stowed_path` in both. Both callers test the returned package name for truth, which in Perl treats a package literally named `0` as "no owner" (#25). |
| `find_stowed_path` (1017-1052) | `stow.py: _find_stowed_path`; `types.py: StowedPath` | divergent_documented | Absolute-destination early return, two-stage lookup, debug levels and text all preserved; the sentinel triple becomes `StowedPath` or `None`. A destination that cancels back to the target root yields `.` rather than Perl's `''`, adding one probe (syscall appendix). |
| `link_dest_within_stow_dir` (1069-1087) | `stow.py: _parse_link_dest_as_package_subpath`; `types.py: PackageSubpath` | faithful | Anchored prefix strip and first-segment split reproduced exactly, with the same three debug calls and the same lossy `''` contract at the caller. |
| `find_containing_marked_stow_dir` (1110-1129) | `stow.py: _find_containing_marked_stow_dir`; `types.py: MarkedStowDir` | faithful | Shallowest-match prefix loop, package index and the terminal internal error are preserved, including Perl's `join_paths` tracing lines. |
| `cleanup_invalid_links` (1160-1225) | `stow.py: _cleanup_invalid_links` | divergent_documented | Directory guard, byte-order sorted listing, symlink filter, pending-task short-circuit and all messages match. Perl aborts the whole unstow on a foreign symlink pointing at `0` (#25). |
| `foldable` (1245-1321) | `stow.py: _foldable`, `_fold_if_foldable` | divergent_documented | Loop, single leading `../` strip and debug text match. The `''` tracking sentinel becomes `None`, which is #14; a package literally named `0` is never folded by Perl (#25). |
| `fold_tree` (1343-1382) | `stow.py: _fold_tree` | faithful | Literal port of the body: folding message, sorted listing, `is_a_node` guard, then rmdir followed by link, in that order. |
| `conflict` (1385-1395) | `stow.py: _record_conflict`; conflict printing in `cli.py: _main` | restructured | The action dimension is dropped because all six call sites pass `stow`; message text, package and message sorting, and the debug line are unchanged. |
| `get_conflicts` (1415-1418) | `_Stower.conflicts`; `types.py: StowResult.conflicts` | restructured | Accessor replaced by an attribute plus a result field; emptiness test and reported output are the same. |
| `get_conflict_count` (1426-1429) | *(none)* | infrastructure_only | Accessor for a counter that no shipped code path reads; equal to the total number of recorded messages. |
| `get_tasks` (1437-1440) | `_Stower.tasks`; `types.py: StowResult.tasks` | restructured | Read accessor becomes a public attribute plus a copied result field; contents, ordering and skip semantics unchanged. |
| `get_action_count` (1442-1451) | *(none)* | infrastructure_only | Accessor for a per-package counter whose only reference in the shipped driver is commented out. |
| `ignore` (1478-1512) | `stow.py: _should_ignore`, `_get_ignore_regexps`; `types.py: IgnorePatterns` | divergent_documented | Empty-target guard, per-option loop, both `-v5` dumps and the path-versus-segment match are in Perl's order with identical text. The `-v4` `--ignore` trace stringifies the compiled pattern differently (#23). |
| `get_ignore_regexps` (1515-1541) | `stow.py: _get_ignore_regexps`, `_get_ignore_regexps_from_file` | restructured | Local-then-global lookup, existence probe, all three messages, the memoized-regexps debug line and the built-in fallback are preserved; memoisation moved up into this function. |
| `get_ignore_regexps_from_file` (1545-1565) | `stow.py: _get_ignore_regexps_from_file`, `_read_ignore_file` | restructured | Open plus parse retained; a failed open is not memoized (Perl returns before its memo assignment) and is traced with Perl's message. The memo lives on the stower rather than the process. |
| `invalidate_memoized_regexp` (1576-1586) | *(none)* — per-instance cache | infrastructure_only | The invalidation hook has no counterpart: the cache is scoped to one operation, so re-reading happens automatically. |
| `get_ignore_regexps_from_fh` (1588-1607) | `stow.py: _read_ignore_file` (parse loop), `_get_default_global_ignore_regexps` | restructured | The filehandle-generic parser is inlined twice. Byte-transparent `\n`-delimited reading, ASCII-only whitespace and comment stripping, `\#` unescape, deduplication and the hardcoded self-ignore pattern all match Perl, including an ignore file that is a directory. |
| `compile_ignore_regexps` (1609-1634) | `stow.py: _compile_ignore_patterns`; `types.py: IgnorePatterns` | divergent_documented | Path-versus-segment partition, both wrappers and the empty-list guards are exact; alternation order is sorted rather than hash-random (#23); the regex dialect boundary and its guardrails are #28. |
| `compile_regexp` (1636-1642) | `stow.py: _compile_user_regexp`, `_compile_option_pattern` | divergent_documented | `eval { qr// }` plus `die` becomes `re.compile` in a `try`/`except re.error`. This is the point at which Perl's regex dialect is exchanged for Python's, with `re.ASCII` character semantics, hoisted leading flag groups and loud rejection of POSIX classes (#28, #12). |
| `get_default_global_ignore_regexps` (1644-1651) | `stow.py: _get_default_global_ignore_regexps` | restructured | The `__DATA__` handle becomes an inline constant plus a one-shot cache; the resulting 16-pattern set and its path/segment split are identical. |
| `defer` (1667-1675) | `stow.py: _should_defer`, `_compile_option_pattern` | divergent_documented | Loop, first-match short-circuit, empty-list result and `\A(...)` anchoring are identical, as is the single call site. Dialect boundary per #28. |
| `override` (1691-1699) | `stow.py: _should_override` | divergent_documented | Same loop, same anchoring, same single call site in the existing-link chain; no debug side effect in either. Dialect boundary per #28. |
| `process_tasks` (1723-1742) | `stow.py: process_tasks`; `util.py: within_dir` | divergent_documented | "Processing tasks…" line before the strip, skip-filter, rebinding of the task list and the chdir scope all match; skip is encoded as a flag instead of an action value. The cwd is restored when a task dies (#27). |
| `process_task` (1763-1807) | `stow.py: _process_task`; `types.py` tasks; `util.py: move` | divergent_documented | String dispatch on (action, type) becomes class dispatch; same syscalls, same argument order, same `0o777` mode, `$!`-style `strerror` message text. Perl's `sprintf` mangling of `%` in paths is #26. |
| `link_task_action` (1824-1839) | `stow.py: _get_link_task_action` | faithful | Same guard and same two debug calls, including Perl's asymmetric indent; the `''` sentinel becomes `None` and is only ever tested or compared. |
| `dir_task_action` (1856-1871) | `stow.py: _get_dir_task_action` | faithful | Line-for-line; the unreachable "bad task action" branch is replaced by an enum with exactly two members. |
| `parent_link_scheduled_for_removal` (1888-1905) | `stow.py: _is_parent_link_scheduled_for_removal` | faithful | Prefix accumulation, per-prefix debug line, early return on the first pending removal, and the same treatment of duplicate and trailing slashes. |
| `is_a_link` (1922-1947) | `stow.py: _is_a_link` | faithful | Task-action short-circuits, the lstat test and the negated parent-removal delegation are in Perl's order with identical messages. |
| `is_a_dir` (1965-1988) | `stow.py: _is_a_dir` | faithful | Three-phase decision preserved; `-d` becomes `os.path.isdir`, which follows symlinks and reports false on stat failure exactly as Perl does. |
| `is_a_node` (2006-2067) | `stow.py: _is_a_node` | faithful | The full 3×3 truth table is reproduced cell for cell, including both fatal cells and the fall-through order of the parent-removal and existence checks. |
| `read_a_link` (2093-2110) | `stow.py: _read_a_link` | divergent_documented | Task-action branches, the `-l` plus `readlink` fallback and the terminal internal error are a near-literal parallel; failure messages use `strerror` like Perl's `$!`. Perl treats a successful readlink result of `0` as failure (#25). |
| `do_link` (2130-2196) | `stow.py: _do_link`; `types.py: LinkTask` | faithful | Clash guard, duplicate and revert handling, the skip-and-delete pairing, message text and task ordering are all reproduced. |
| `do_unlink` (2216-2265) | `stow.py: _do_unlink` | divergent_documented | Guard order, all three messages, revert semantics and the deliberate absence of an index registration match. Perl's `readlink ... or error` idiom carries the `"0"` falsiness (#25), unreachable through this site. |
| `do_mkdir` (2281-2329) | `stow.py: _do_mkdir` | faithful | Guard order, duplicate and revert messages (including the upstream colon asymmetry against `do_rmdir`) and task registration order are identical. |
| `do_rmdir` (2352-2393) | `stow.py: _do_rmdir` | faithful | Guards, message text and revert handling parallel Perl. Perl's second guard reads the link-task table while testing the directory-task table, so its duplicate and revert arms always die; Python runs the intended logic. No invocation can reach the difference. |
| `do_mv` (2418-2451) | `stow.py: _do_mv`; `types.py: MoveTask` | faithful | Both guards, the `MV` debug line, task shape and the deliberate absence of an index entry are preserved; the sole call site is the `--adopt` branch in both. |
| `internal_error` (2477-2489) | raise + handler in `cli.py: main`; `types.py: StowInternalError` | divergent_documented | The subroutine becomes raise-plus-handler; the message payloads of all fourteen sites match their Perl counterparts. The banner wrapper (bug-report URL, trace shape) differs per #17. |

---

## lib/Stow/Util.pm

| Perl sub | Python counterpart(s) | Classification | Notes |
| --- | --- | --- | --- |
| `error` (62-65) | `types.py: StowError`; handler in `cli.py: main` | divergent_documented | `die` at the call site becomes raise plus one top-level handler; prefix, single trailing newline, stderr routing and the absence of a Perl `at FILE line N` suffix all match. Perl runs the message through `sprintf`, mangling `%` in paths (#26); exit codes follow the #13 taxonomy. |
| `set_debug_level` (75-78) | `util.py: set_debug_level` | restructured | The package global becomes a logging filter with the same `>=` gate and the same default of 0; applied per phase rather than once per process, which is unobservable from either executable. |
| `set_test_mode` (88-96) | *(none)* | infrastructure_only | Test-harness hook that redirects diagnostics to stdout; neither shipped executable ever sets it. |
| `debug` (129-144) | `util.py: debug` | restructured | Level gate, four-spaces-per-indent prefix and the stderr write are reproduced through the logging machinery; the backwards-compatible two-argument form is dead upstream. The stream handle is bound at import, observable only to embedders redirecting `sys.stderr` mid-run. |
| `join_paths` (168-199) | `util.py: join_paths` | divergent_documented | Skip-empty, absolute-part reset, separator rule and all three debug lines are a literal parallel. The canonpath-plus-removal loop becomes one `os.path.normpath`, whose differences are #29 (`..`-prefixed names, where Perl misparses its own symlinks) and the syscall appendix (`''` vs `.`, `//`). |
| `parent` (210-216) | `util.py: parent` | divergent_documented | Different algorithm, same contract: leading empty field for absolute paths, dropped trailing fields, collapsed slash runs. Call sites test the result for truth, which in Perl collapses a directory named `0` (#25). |
| `canon_path` (226-234) | `util.py: canon_path`, `current_dir` | divergent_documented | getcwd, chdir, getcwd, restore — same order, same syscalls, same error text on the reachable failure, including the vanished-directory message byte for byte. `%` mangling on the Perl side is #26; exit codes are #13. |
| `restore_cwd` (237-240) | `util.py: restore_cwd` | divergent_documented | chdir-or-fail with a byte-identical "seems to have vanished" message; #26/#13 as above. |
| `adjust_dotfile` (242-246) | `util.py: adjust_dotfile` | faithful | The substitution becomes an equivalent three-part predicate, including the requirement that a character follow `dot-` and that it not be a dot. Both call sites keep the copy-then-compare idiom. |
| `unadjust_dotfile` (249-254) | `util.py: unadjust_dotfile` | faithful | The `.` to `dot-` substitution matches exactly; the `.`/`..` guard reproduces Perl's `$`-before-newline acceptance of `.<LF>` and `..<LF>`. |

---

## bin/stow

| Perl sub | Python counterpart(s) | Classification | Notes |
| --- | --- | --- | --- |
| `main` (474-506) | `cli.py: main`, `_main` | divergent_documented | Statement for statement: unstow planned before stow, conflicts before simulate, all four stderr strings byte-identical. Fatal-error handling is hoisted into a wrapper; the internal-error banner differs per #17. |
| `process_options` (517-552) | `cli.py: process_options` | restructured | Call order, rc-file merge, per-key override and the array-merge guard are faithful. Perl's aliasing side effect inside `check_packages` is emulated by rebuilding both package lists here, with the `$`-before-newline trailing-slash strip. |
| `parse_options` (565-626) | `cli.py: parse_cli_options`, `_parse_bundled_options`, `_find_long_option` | divergent_documented | Hand-written subset of Getopt::Long: bundling, unique-prefix abbreviation, ambiguity lists, `POSIXLY_CORRECT`, PAT_INT value grammar, whole-line scanning with errors-then-help-then-version precedence, per-character bundle errors and D/S/R action switching all produce Perl's wording. Deliberate non-reproductions: `+` prefixes except `+n` (#5, #22), `-v N`/`--verbose N` value gobbling (#10), `--` termination behaviour (#11). |
| `sanitize_path_options` (628-646) | `cli.py: sanitize_path_options` | divergent_documented | `STOW_DIR` default (using length, not truth), both directory checks, in-place mutation and the usage message are faithful. The derived-target fallback uses truthiness in Perl, collapsing a parent named `0` (#25). |
| `check_packages` (648-662) | `cli.py: check_packages` | faithful | Empty-list usage error (including Perl's blank line) and the slash rejection are identical. |
| `get_config_file_options` (675-707) | `cli.py: get_config_file_options` | divergent_documented | Candidate list with `$HOME` first (defined-test, so `HOME=""` probes `/.stowrc`), byte-transparent `\n`-record reads, silent skip of missing or unreadable files, delegation to the option parser, `exists`-keyed expansion of target then dir, and the discarded rc-file package lists all match. A `.stowrc` that is a directory is #20. |
| `expand_filepath` (720-727) | `cli.py: expand_filepath` | divergent_documented | Two-step composition in the same order, same return, same two call sites, same die message for an undefined variable. The home fallback chain's `"0"` handling is #25. |
| `expand_environment` (739-753) | `cli.py: expand_environment_variables` | faithful | Braced pass then bare pass then `\$` unescape, with the undefined-variable helper inlined as a closure; ASCII `\w`/`\s` matching, escaping, empty braces, rescanning and the die text all agree. |
| `_safe_expand_env_var` (755-761) | `cli.py: replace_var` (nested); `types.py: StowCLIError` | faithful | Existence test rather than truthiness, byte-identical message, same evaluation order, same left-to-right abort on the first undefined variable (exit code per #13). |
| `expand_tilde` (772-785) | `cli.py: expand_tilde_to_homedir`, `get_homedir_from_passwd` | divergent_documented | The single substitution becomes prefix handling with the same semantics, including the ordering of expansion before the `\~` unescape. An unknown `~username` stays literal (#21); `~0` and `HOME=0` follow #25. |
| `usage` (796-842) | `cli.py: show_usage_and_exit` | divergent_documented | Message prefixing moves to the three call sites that correspond to Perl's own `usage(...)` calls; the program name is derived from `argv[0]` as Perl derives it from `$0`; stderr and exit codes are byte-identical across the error paths. The added attribution lines are #17. |
| `version` (843-846) | `cli.py: show_version_and_exit` | divergent_documented | One-line printer with the same text, stream and exit 0; `stow --version` is byte-identical, and precedence against `--help` and later bad options follows Getopt::Long. The attribution differences are #17. |

---

## bin/chkstow

| Perl sub | Python counterpart(s) | Classification | Notes |
| --- | --- | --- | --- |
| `process_options` (43-51) | `chkstow.py: parse_args`, `_find_option` | faithful | Getopt::Long's default configuration is hand-emulated: case-insensitive long names, unique-prefix abbreviation, single-dash long forms, `+` prefixes including a bare `+`, absence of bundling, `--` terminator, permute versus require-order, canonical names in diagnostics, empty attached values, accumulated errors and the single trailing usage call. |
| `usage` (53-67) | `chkstow.py: usage`, `default_target` | divergent_documented | Heredoc becomes an f-string; both call sites and the exit-0-even-on-error behaviour are preserved, and the text is byte-identical. The only difference is the default target under `STOW_DIR=0` (#16). |
| `check_stow` (69-88) | `chkstow.py: main`, `_walk_target`, mode functions | divergent_open | `find()` plus post-processing is restructured into a generator with per-mode filters; readlink rewriting, deletion of `''` and `..`, byte-order sort and traversal-order output are equivalent, and unreadable or unenterable directories warn in File::Find's wording. One open difference: with a deleted working directory Perl exits 2 (`Can't cd to :`) where we exit 0 silently — tracked, not yet resolved. |
| `skip_dirs` (90-98) | inline preprocess in `chkstow.py: _walk_target` | restructured | The preprocess callback is inlined into the walker: same `.stow`/`.notstowed` probe with the same short-circuit, same suppression of both entries and descent, same warning text (one trailing slash stripped, like File::Find) and exit status. |
| `bad_links` (101-104) | `chkstow.py: find_bad_links` | restructured | The `-l && !-e` predicate is translated exactly, including the fresh stat that makes a dangling link bogus; the callback becomes a lazily consumed generator, so ordering is unchanged, and names that are not valid UTF-8 are written out byte for byte. |
| `aliens` (107-109) | `chkstow.py: find_aliens` | restructured | Push-model callback becomes a pull-model generator; the `!-l && !-d` predicate, its short-circuit and its treatment of symlinked directories, fifos and unstattable entries are identical, including skipping directories File::Find cannot enter. |
| `list` (113-120) | `chkstow.py: list_packages` | restructured | The wanted callback and `check_stow`'s deduplicate-sort-print tail are folded into one function; both readlink rewrites, the removal of `''` and `..` and the byte-order sort produce the same package listing. |

---

## Summary statistics

**Subroutines mapped: 80**

| Classification | Count |
| --- | ---: |
| `divergent_documented` | 34 |
| `restructured` | 20 |
| `faithful` | 21 |
| `infrastructure_only` | 4 |
| `divergent_open` | 1 |

Per source file:

| File | Subs | faithful | restructured | divergent_documented | divergent_open | infrastructure_only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lib/Stow.pm` | 51 | 15 | 13 | 20 | 0 | 3 |
| `lib/Stow/Util.pm` | 10 | 2 | 2 | 5 | 0 | 1 |
| `bin/stow` | 12 | 3 | 1 | 8 | 0 | 0 |
| `bin/chkstow` | 7 | 1 | 4 | 1 | 1 | 0 |
| **Total** | **80** | **21** | **20** | **34** | **1** | **4** |

Every `divergent_documented` citation resolves to a numbered entry in
[perl-differences.md](perl-differences.md), each of which is pinned by a test
asserting both the Perl and the Python behaviour. The single `divergent_open`
row (chkstow under a deleted working directory) is the only known behavioural
difference not yet fixed or formally documented.
