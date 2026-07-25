# Future ideas

Ideas worth doing that are not on the active roadmap (for that, see the
README's "Not done yet" list).

## Per-function Perl oracles for perlcompat.py

`src/stow_python/perlcompat.py` is the one module whose code cannot be
reviewed against `Stow.pm` — it emulates Perl *libraries*. Its functions
could each be tested directly against their Perl counterparts, at function
granularity, the same way the rest of the suite uses the real Perl stow:

- `perl_shellwords` ↔ `Text::ParseWords::shellwords()` (core Perl, present
  wherever the suite runs): a Hypothesis test generating lines, feeding both
  implementations (batched, many lines per perl invocation) and comparing
  token lists. This would make the fuzz verification that the port's
  docstring cites a permanent, repeatable part of the suite.
- `find_long_option`, `parse_optint_value`, `take_bundled_optint` ↔
  Getopt::Long's name resolution and PAT_INT value grammar: these are
  internals, so drive `perl -MGetopt::Long` through its public `GetOptions`
  with crafted argv (abbreviations, ambiguous prefixes, `-v3_0`,
  `--verbose=_4`) and compare *outcomes* — accepted/rejected, resulting
  value, resolved option. Never compare diagnostic wording: it drifts
  across Getopt::Long versions (perl-differences.md #24).
- `compile_user_regexp`, `hoist_leading_flags`, `scope_leading_flags` have
  no Perl counterpart — they implement the documented dialect boundary
  (perl-differences.md #28) — so they get contract unit tests instead
  (hoisted `(?i)` equals `re.IGNORECASE`; POSIX classes rejected with the
  hint; `\w` matches ASCII only).

Suggested home: `tests/test_perlcompat_both.py`.

## A natively designed Python stow

[docs/native-design.md](docs/native-design.md) inventories the code that
exists purely to look like Perl and sketches what a future major version
could drop. Not actionable now; kept so the costs stay visible and listed.
