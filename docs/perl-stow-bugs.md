# Bugs and Likely-Unintended Behaviors in GNU Stow 2.4.1 (Perl)

Found by differential testing while building this reimplementation:
every scenario below was run side by side against the Perl `stow` and
`chkstow`, comparing exit codes, byte-exact output and resulting trees.
Line numbers refer to the GNU Stow 2.4.1 release (the copy under
`tests/gnu_stow_for_testing/`). Each entry states where the defect
lives, what it does, and the fix we would suggest upstream.

How this repository relates to them: the `main` branch deliberately does
not reproduce the harmful ones (each such divergence is documented in
`perl-differences.md` and pinned by a test asserting both behaviors);
the `bug4bug` and `py27-literal` branches reproduce them all faithfully.

---

## 1. `join_paths` cannot collapse after a `..`-prefixed name

**Location:** `lib/Stow/Util.pm:192`

```perl
1 while $result =~ s,(^|/)(?!\.\.)[^/]+/\.\.(/|$),$1,;
```

**Behavior:** the lookahead inspects only the next two characters, so a
component whose *name* merely starts with `..` — `..d`, `...`, `..bak` —
blocks the removal of a following `/..`, and the path never collapses.
Downstream, `find_stowed_path` then fails to resolve Stow's own symlinks
into the stow directory: a second `stow` of the same package reports
`existing target is not owned by stow` (exit 1), unstowing refuses to
remove the link, and conflict messages name the wrong owner. An
implementation that cannot recognize its own links cannot manage them.

**Suggested fix:** make the lookahead reject only the literal `..`
component: `(?!\.\.(?:/|$))`, or replace the textual loop with
component-wise normalization.

## 2. The string `"0"` is treated as false

**Locations (the family):**

- `lib/Stow.pm:2103` — `readlink $link or error("Could not read link: ...")`:
  a symlink whose destination is literally `0` is reported as a *failed*
  readlink and aborts the run (exit from `$!`), although the syscall
  succeeded.
- `lib/Stow.pm:1197`, `1289` — the cleanup and unstow paths test the
  returned destination for truth the same way.
- `lib/Stow.pm:1214` (`if ($owner)`), `1313`
  (`if ($self->link_owned_by_package(...))`) — a package literally named
  `0` is never recognized as an owner: its trees are never folded and
  its dangling links survive `--cleanup`.
- `lib/Stow.pm:1300` (`if (not $parent_in_pkg)`) — a common parent of
  `0` reads as "no links in this directory".
- `bin/stow.in:644` — `parent($options->{dir}) || '.'`: `--dir 0/sub`
  silently retargets to `.`.
- `bin/stow.in:777-779` — the tilde chain
  `$1 ? (getpwnam($1))[7] : ($ENV{HOME} || $ENV{LOGDIR} || ...)`:
  `~0` is read as a bare `~`, and `HOME=0` / `LOGDIR=0` fall through the
  chain.

**Behavior:** Perl's scalar truth test makes the one-character string
`0` false, so every plain `if ($name)` on a package name, link
destination or path takes the wrong branch when the value happens to be
`0`.

**Suggested fix:** test definedness/length where a *name or path* is
being tested: `defined($x) && length($x)` (or compare against `''`).

## 3. `error()` re-formats already-interpolated messages through `sprintf`

**Location:** `lib/Stow/Util.pm:64`

```perl
die "$ProgramName: ERROR: " . sprintf($format, @args) . "\n";
```

**Behavior:** several callers interpolate user-controlled strings into
`$format` itself (e.g. `error("... does not contain package $package")`),
so `%` sequences inside package or path names are format-processed: a
package `a%%b` is reported as `a%b`, a stray `%s` consumes a missing
argument (warning `Missing argument in sprintf`) and prints nothing, and
`-100% from` parses `% f` as a float conversion, printing
`-100 0.000000rom`.

**Suggested fix:** pass user data as arguments everywhere
(`error("... does not contain package %s", $package)`), or skip the
`sprintf` when `@args` is empty.

## 4. `do_rmdir` reads the wrong task hash

**Location:** `lib/Stow.pm:2367` (warnings at `2369`, `2373`, death at
`2380`)

```perl
if (exists $self->{dir_task_for}{$dir}) {
    my $task_ref = $self->{link_task_for}{$dir};   # wrong hash
```

**Behavior:** the guard at `lib/Stow.pm:2356` has already thrown if a
link task existed, so this fetch is always `undef`: instead of merging a
duplicate directory removal or reverting a planned creation, both action
comparisons emit `Use of uninitialized value in string eq` and control
falls through to `internal_error("bad task action: ")` — a crash with
the "This _is_ a bug" banner whenever the merge logic is needed.

**Suggested fix:** `my $task_ref = $self->{dir_task_for}{$dir};`

## 5. `do_unlink`'s clash guard compares a hashref with a string

**Location:** `lib/Stow.pm:2238`

```perl
if (exists $self->{dir_task_for}{$file} and $self->{dir_task_for}{$file} eq 'create') {
```

**Behavior:** the left operand is the task hashref, which stringifies to
`HASH(0x...)` and never equals `create` — the "unlink clashes with a
planned directory creation" internal error can never fire, and the
unlink is planned as if no dir task existed. The message body two lines
below already spells the intended field
(`$self->{dir_task_for}{$file}->{action}`).

**Suggested fix:** compare the field:
`$self->{dir_task_for}{$file}{action} eq 'create'`.

## 6. Ignore-list compilation order is nondeterministic

**Location:** `lib/Stow.pm:1615` (`for my $regexp (keys %regexps)`)

**Behavior:** the ignore patterns are joined into one alternation in
hash order, which differs between runs of the same configuration. Alone
this only scrambles a `-v5` trace line, but Perl accepts inline flag
groups such as `(?i)` inside a pattern and applies them *to the rest of
the enclosing group* — i.e. to every pattern that happens to be joined
after it. With `(?i)foo` and `BAR` in one ignore file, whether `bar` is
ignored varies run to run (observed 13/7 over twenty runs).

**Suggested fix:** iterate `sort keys %regexps`, and scope inline flags
per pattern (`(?i)foo` → `(?i:foo)`) when joining.

## 7. `$` anchors accept a trailing newline where `\z` is meant

**Locations:**

- `lib/Stow/Util.pm:251` — `return $target_node if $target_node =~ /^\.\.?$/;`
  also matches entries literally named `.<LF>` or `..<LF>`, so a real
  file with such a name is skipped as a dot directory.
- `bin/stow.in:657` — `$package =~ s{/+$}{};` strips a slash sitting
  *before* a trailing newline, so `stow 'a/<LF>'` quietly becomes the
  package `a<LF>`.
- `lib/Stow/Util.pm:192` — the same anchor in the `..`-collapse regex
  lets a component literally named `..<LF>` cancel the preceding
  component.

**Suggested fix:** use `\z` (and reject newlines in package names up
front).

## 8. `~nosuchuser` expands to the empty string

**Location:** `bin/stow.in:775-779`

**Behavior:** when `getpwnam` fails, its `undef` is interpolated
straight into the substitution: `~nosuchuser/t` becomes `/t` (plus a
`Use of uninitialized value in substitution iterator` warning). A typo
in a username silently retargets to the filesystem root rather than
failing.

**Suggested fix:** check `defined((getpwnam($1))[7])` and die with a
clear "unknown user" message.

## 9. `$HOME` is interpolated into a substitution as a *pattern*

**Locations:** `lib/Stow.pm:409`
(`$msg =~ s!$ENV{HOME}(/|$)!~$1!g;`), `lib/Stow.pm:760`

**Behavior:** the tildify of `-v3` trace messages reads `$HOME` as a
regexp. An empty (or unset) `HOME` then matches at every position —
`(cwd=/var/tmp/x)` prints as `(cwd=~/var~/tmp~/x)~` — with
uninitialized-value warnings when unset; a `HOME` containing regex
metacharacters warps or aborts the substitution.

**Suggested fix:** `s!\Q$ENV{HOME}\E(/|$)!~$1!g` guarded by
`defined && length`.

## 10. A user-constructible input reaches the internal-error banner

**Location:** `lib/Stow.pm:1124`
(`internal_error("find_stowed_path() called directly on stow dir")`)

**Behavior:** a symlink in the target pointing directly at a marked
stow directory (one containing `.stow`) makes `stow` print the
`INTERNAL ERROR ... This _is_ a bug. Please submit a bug report` banner
with a Carp trace and die — for an input any user can create with one
`ln -s`.

**Suggested fix:** treat the direct hit as an unowned node (skip or
conflict) instead of asserting it cannot happen.

## 11. Minor: deep recursion warnings

**Behavior:** `stow_contents`/`stow_node` (and the unstow pair) recurse
per directory level, so trees deeper than 100 levels spray
`Deep recursion on subroutine "Stow::stow_contents"` warnings on stderr
while completing successfully.

**Suggested fix:** `no warnings 'recursion';` in those subs, or an
iterative traversal.

---

## Inherited from CPAN (visible through stow, not stow's code)

- **Getopt::Long bundled values skip the underscore strip:** the value
  grammar `PAT_INT` accepts `1_0` and normalizes it to `10` for
  `--verbose=1_0`, but the bundling branch passes the raw string to the
  numeric addition, so `-v_2` warns
  `Argument "_2" isn't numeric in addition (+)` and yields level 0
  (`Getopt/Long.pm`, the `$opctl` addition around line 1238 in 2.54).
