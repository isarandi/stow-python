# Function clarity assessment

A per-function review of `src/stow_python/`, made to decide where code should
live and which functions deserve a clearer reimplementation. The criterion is
**eye-traceability**: looking only at the function's own shape — its control
structure and the names of what it calls, without stepping into callees — how
clearly does it show that it correctly does what its name and docstring
claim? A callee misbehaving despite its name is that callee's defect, not the
caller's; each function is judged on its own surface.

**Score (out of 10)**

| Score | Meaning |
| --- | --- |
| 9-10 | Reads as a sentence; the structure *is* the intent. |
| 7-8 | Clear with a moment's attention; minor friction (a flag, an index, a subtle guard). |
| 5-6 | Needs careful reading; interleaved concerns or a non-obvious protocol, though still linear. |
| 3-4 | Stateful or entangled; the reader must mentally simulate it. |
| 1-2 | Actively resists reading. |

**Metrics.** Lines include the docstring. Depth counts nested
`if`/`for`/`while`/`try`/`with`, with an `elif` chain counted flat (it reads
flat). A deliberately verbose shape can score high: `_is_a_node`'s written-out
truth table is long precisely so that every case is visible.

## stow.py — core engine (mirrors `Stow.pm`)

| Function | Lines | Depth | Score | Notes |
| --- | ---: | ---: | ---: | --- |
| `stow` / `unstow` / `restow` | 19-22 | 0 | 10 | Make config, plan, execute. |
| `_make_config` | 19 | 2 | 8 | Unknown-kwarg rejection plus tuple coercion; small. |
| `_compile_option_pattern` | 21 | 1 | 8 | Guard, hoist, compile — linear (regexp-semantics helpers live in `perlcompat.py`). |
| `_Stower.__init__` | 36 | 1 | 8 | Config, pattern compiles, cache, stow-path computation; two concerns but each labeled. |
| `_session` | 16 | 2 | 8 | Lock plus verbosity save/restore. |
| `plan_stow` / `plan_unstow` | 21 | 3 | 9 | Validate, enter target, loop packages: require directory, stow contents. Literate. |
| `execute` | 32 | 1 | 9 | Three-way: conflicts / simulate / process. |
| `process_tasks` | 16 | 3 | 9 | Strip skipped, enter target, run each. |
| `stow_contents` | 36 | 2 | 8 | Job-stack loop dispatching scan/visit; the docstring carries the recursion-equivalence argument. |
| `_stow_scan_dir` | 48 | 1 | 8 | Skip guard, listing, reverse push; the HOME-tildification block is Perl-mandated noise. |
| `_stow_visit_node` | 28 | 2 | 9 | Guards, dotfile adjust, delegate. |
| `_stow_node` | 56 | 2 | 7 | Clear branch headers; the level arithmetic and link-destination construction need a pause. |
| `_stow_node_for_existing_link` | 72 | 2 | 6 | Five-way ladder over the ownership model; each branch clear, the whole needs the model in mind. Mirrors Perl's `stow_node` core. |
| `_stow_node_for_existing_node` | 38 | 2 | 8 | Directory/file × adopt dispatch. |
| `unstow_contents` | 27 | 2 | 8 | Job stack with four job kinds; ordering trick documented. |
| `_unstow_scan_dir` | 61 | 2 | 7 | Compat-mode branching plus cleanup-job push ordering. |
| `_unstow_visit_node` | 34 | 3 | 8 | Dotfile adjust in both directions. |
| `_unstow_node` | 19 | 1 | 9 | Four-way dispatch, one line each. |
| `_fold_if_foldable` | 5 | 1 | 10 | |
| `_unstow_link_node` | 43 | 2 | 8 | Guard ladder with clear reasons. |
| `_cleanup_invalid_links` | 73 | 3 | 7 | Linear scan with continues; debug chatter dilutes the signal. |
| `_foldable` | 64 | 2 | 8 | Early returns each naming their reason — reads like the spec. |
| `_fold_tree` | 21 | 2 | 9 | Unlink all, rmdir, link. |
| `_process_task` | 41 | 3 | 8 | Type dispatch, one guarded syscall per arm. |
| `_record_conflict` | 4 | 0 | 10 | |
| `_should_ignore` | 44 | 2 | 7 | Two regexp kinds plus their `-v5` dumps interleaved. |
| `_get_ignore_regexps` | 15 | 2 | 9 | Local, global, built-in — in order. |
| `_get_ignore_regexps_from_file` | 19 | 1 | 9 | Memo protocol documented. |
| `_should_defer` / `_should_override` | 3 | 0 | 10 | |
| `_should_skip_target` | 19 | 1 | 9 | Three named guards. |
| `_is_marked_stow_dir` | 6 | 1 | 10 | |
| `_get_owning_package` | 4 | 0 | 10 | |
| `_find_stowed_path` | 35 | 1 | 8 | Two-stage lookup, staged debug. |
| `_parse_link_dest_as_package_subpath` | 16 | 1 | 9 | Prefix strip, partition. |
| `_find_containing_marked_stow_dir` | 21 | 3 | 7 | Prefix loop with index arithmetic and a fatal edge. |
| `_get_link_task_action` / `_get_dir_task_action` | 12 | 1 | 9 | |
| `_is_parent_link_scheduled_for_removal` | 27 | 2 | 8 | Prefix accumulation. |
| `_is_a_link` / `_is_a_dir` | 18-19 | 1 | 9 | Task-table short-circuits then filesystem. |
| `_is_a_node` | 37 | 1 | 8 | The 3×3 truth table written out; verbose on purpose, every case visible. |
| `_read_a_link` | 21 | 2 | 8 | |
| `_do_link` | 45 | 3 | 7 | Guard matrix against both task tables; revert semantics need thought. |
| `_do_unlink` | 36 | 2 | 7 | Same family. |
| `_do_mkdir` / `_do_rmdir` | 27-29 | 2 | 8 | Smaller instances of the same pattern. |
| `_do_mv` | 20 | 1 | 9 | |
| `_read_ignore_file` | 29 | 1 | 8 | Open-mode subtleties documented; parsing delegated. |
| `_parse_ignore_lines` | 16 | 2 | 9 | The one ignore-file line parser, shared. |
| `_compile_ignore_patterns` | 31 | 2 | 8 | Partition, guard, join, compile. |
| `_get_default_global_ignore_regexps` | 30 | 0 | 9 | Built-in pattern data through the shared parser. |

## util.py — helpers (mirrors `Stow/Util.pm`)

| Function | Lines | Depth | Score | Notes |
| --- | ---: | ---: | ---: | --- |
| `_VerbosityFilter` / `_IndentFormatter` | 2-3 | 0 | 10 | |
| `require_directory` | 8 | 2 | 9 | |
| `set_debug_level` / `get_debug_level` / `debug` | 3-13 | 0 | 10 | |
| `join_paths` | 36 | 3 | 7 | Accumulate-then-normalize with debug chatter; the normpath semantics carry #29's weight. |
| `parent` | 5 | 0 | 8 | Dense one-liner contract (leading-empty-field behavior). |
| `current_dir` | 13 | 1 | 9 | |
| `canon_path` | 17 | 1 | 9 | getcwd, chdir, getcwd, restore. |
| `restore_cwd` | 10 | 1 | 9 | |
| `within_dir` | 14 | 1 | 9 | |
| `adjust_dotfile` / `unadjust_dotfile` | 14-16 | 1 | 9 | Predicates spelled out. |
| `move` | 56 | 3 | 6 | The NFS-lost-ACK heuristic is inherently subtle; documented, verifiable only against `File::Copy`. |

## cli.py — command line (mirrors `bin/stow`; newspaper-ordered)

| Function | Lines | Depth | Score | Notes |
| --- | ---: | ---: | ---: | --- |
| `main` | 28 | 1 | 9 | Setup, run, three except arms. |
| `configure_standard_streams` | 19 | 2 | 9 | |
| `_main` | 42 | 3 | 8 | Build config, plan, report conflicts or execute. |
| `process_options` | 27 | 2 | 8 | CLI-over-rc merge with the list-append rule. |
| `parse_cli_options` | 6 | 0 | 10 | Builds the scanner and returns its result. |
| `_ArgumentScanner.__init__` | 10 | 0 | 10 | The scan state, one named attribute each. |
| `_ArgumentScanner.scan` | 55 | 2 | 9 | Five-arm dispatcher (`--` / long option / `+n` / package / bundle) over the scanner's own state; errors-then-help-then-version acted on after the scan. Reads as a sentence. |
| `_ArgumentScanner._take_rest_as_packages` | 11 | 1 | 10 | |
| `_ArgumentScanner._add_package` | 9 | 1 | 10 | Action-directed append. |
| `_ArgumentScanner._scan_long_option` | 17 | 2 | 9 | Split `=`, resolve, apply, collect the diagnostic. |
| `_ArgumentScanner._apply_long_option` | 10 | 1 | 9 | Three-way dispatch on value type. |
| `_ArgumentScanner._apply_string_option` | 24 | 1 | 8 | The attached/separate/missing value rules, spelled out. |
| `_ArgumentScanner._apply_optint_option` | 16 | 1 | 9 | |
| `_ArgumentScanner._apply_flag_option` | 23 | 1 | 9 | Flag table plus action switching. |
| `_ArgumentScanner._scan_bundled_options` | 40 | 2 | 7 | Still a character loop that consumes its own tail — that is what bundling is — but flat, with the state mutations named. |
| `_ArgumentScanner._apply_bundled_verbose` | 12 | 1 | 8 | Returns characters consumed. |
| `_ArgumentScanner._take_next_arg_as_path` | 9 | 1 | 9 | |
| `_validate_option_regex` | 12 | 1 | 9 | |
| `_strip_trailing_slashes` | 8 | 0 | 9 | |
| `sanitize_path_options` | 19 | 2 | 8 | |
| `check_packages` | 8 | 2 | 9 | |
| `get_config_file_options` | 40 | 4 | 7 | Read protocol (encodings, exceptions) plus expansion ordering. |
| `expand_filepath` | 5 | 0 | 10 | |
| `expand_environment_variables` (+ `replace_var`) | 26 | 1 | 8 | Two passes plus unescape, in stated order. |
| `expand_tilde_to_homedir` | 29 | 2 | 8 | Expansion-before-unescape order documented. |
| `get_homedir_from_passwd` | 11 | 2 | 9 | |
| `show_usage_and_exit` | 51 | 1 | 8 | Mostly the literal text; exit-code protocol at the end. |
| `show_version_and_exit` | 6 | 0 | 10 | |

## perlcompat.py — Perl library emulations

Code that emulates Perl *libraries* (as opposed to Stow's own logic), with
no `Stow.pm`/`bin/stow` counterpart to review against: its trust rests on
the oracle suite and on differential fuzzing.

| Function | Lines | Depth | Score | Notes |
| --- | ---: | ---: | ---: | --- |
| `perl_shellwords` | 61 | 3 | 5 | Regex alternation plus stateful word assembly; shape cannot radiate correctness — its trust comes from fuzzing against `Text::ParseWords` 3.31. |
| `find_long_option` | 30 | 2 | 7 | Exact, then abbreviation, then ambiguity; parameterized by the spec table. |
| `parse_optint_value` | 10 | 1 | 9 | |
| `take_bundled_optint` | 13 | 1 | 7 | The numify-versus-strip distinction is documented but easy to miss. |
| `compile_user_regexp` | 12 | 1 | 9 | |
| `hoist_leading_flags` / `scope_leading_flags` | 13-16 | 1 | 8 | Match, translate, slice. |

## chkstow.py — diagnostics (mirrors `bin/chkstow`)

| Function | Lines | Depth | Score | Notes |
| --- | ---: | ---: | ---: | --- |
| `default_target` | 11 | 0 | 9 | |
| `main` | 18 | 2 | 8 | |
| `configure_standard_streams` | 14 | 2 | 9 | |
| `parse_args` | 66 | 3 | 6 | Getopt::Long-default-config emulation: one argument per step, prefix/`=` surgery delegated to `_split_option_arg`. Self-contained by design (chkstow builds standalone). |
| `_split_option_arg` | 27 | 1 | 8 | Classify one argument: long/short/`+`-form/non-option. |
| `_find_option` | 22 | 2 | 7 | Case-fold, exact, abbreviate. |
| `usage` | 14 | 0 | 9 | |
| `find_bad_links` / `find_aliens` | 5 | 2 | 9 | Generator with a named predicate. |
| `list_packages` | 13 | 2 | 8 | |
| `_walk_target` | 70 | 3 | 6 | Dense File::Find emulation; each quirk documented, but many quirks. |
| `_cannot_enter` | 12 | 1 | 9 | The `stat(path/.)` trick, explained. |
| `_report_opendir_error` | 4 | 0 | 10 | |

## types.py

All dataclasses and exceptions; the three tiny methods (`StowError.__init__`,
`StowInternalError.__init__`, `StowConfig.__post_init__`) score 9-10. No
concerns.

## What the scores say

Median score is 8-9: the codebase passes the literate test. Every score of
6 or below is a case where the complexity *is* the referenced Perl behavior,
so a rewrite would not simplify it, only detach it from what it emulates:

1. **Intrinsically subtle library emulations** — `perl_shellwords` (5),
   chkstow `parse_args` (6). Their correctness cannot radiate from shape;
   it rests on fuzzing against the real Perl modules and on the oracle
   suite, which is stated at their definitions.
2. **Intrinsically subtle ports** — `move` (6), `_walk_target` (6),
   `join_paths` (7). Documented, verifiable only against the Perl
   behavior they reproduce.
3. **The ownership ladder** — `_stow_node_for_existing_link` (6). Its shape
   is `Stow.pm`'s shape, which is exactly what makes it reviewable
   side-by-side.

## Architecture decisions in force

**`perlcompat.py` holds the Perl-library emulations** (Text::ParseWords
shellwords, the Getopt::Long value grammar and option-name resolution, the
Perl regexp-semantics helpers). This matches Perl's own architecture —
these are separate modules in Perl-land — so `cli.py` reads as the mirror
of `bin/stow`'s subs that it is. chkstow's `parse_args` emulates a
*different* Getopt::Long configuration and stays self-contained in
`chkstow.py`, which builds standalone.

**The argument scanner holds its state explicitly**: `_ArgumentScanner`
keeps the scan position, the selected action, the collected options and the
error/help/version flags as attributes, and each arm of `scan()` dispatches
to a method that names the state it touches — no closures over loop state,
no `nonlocal`, no tuple juggling. `parse_cli_options` is the module-level
entry point that builds one and returns its result. Equivalence with the
predecessor scanners is established by differential fuzzing (comparing
return value, stdout, stderr and exit status over tens of thousands of
argument vectors, with and without `POSIXLY_CORRECT`, zero mismatches) on
top of the oracle suite.

**One shared ignore-file line parser** (`_parse_ignore_lines`) serves both
`_read_ignore_file` and `_get_default_global_ignore_regexps`.

**Deliberately left alone**: the groups above, and `stow.py`'s overall body
and ordering — its correspondence with `Stow.pm` is the review story, and
reorganizing it would explode the bug4bug↔main same-language diff that the
story depends on.
