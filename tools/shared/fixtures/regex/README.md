# Regex fast-path semantic audit

`RegexReference.hs` is the ordered Thompson matcher from commit
`2957dd08321c38dbf94a75cb275a5f48e897f58e`, with only its module name changed.
The driver authenticates that exact source before building. It is a historical
behavioral reference, not an independently implemented regex specification.
`Main.hs` also supplies literal expected results for priority, greedy matching,
offsets, Unicode scalar positions, zero-length advancement, and replacement.

Run after other measured tasks have released the CPU:

```sh
python3 tools/shared/test_regex_fast.py --ghc /path/to/ghc-9.14.1 \
  --cc /path/to/clang --output /path/to/new-audit-directory
```

Both `test_regex_fast.py` and `test_native_regex.py` accept an optional
`--candidate-regex /path/to/Regex.hs`. It selects alternate source only for the
isolated snapshot; production files are untouched. The receipt records the
resolved selected path, its SHA-256, and whether an override was requested.
Selected bytes are authenticated before the test-only export overlay, and
source/snapshot integrity is checked after execution. Default source selection
and all semantic inventories and export guards remain unchanged.

The test builds an isolated source snapshot at O2. Only the copied candidate's
export list changes, exposing its plan constructors for twenty nonvacuous
admission checks and `scanSkip`/`countSkip` for scheduling controls. Matching and
plan-selection code are untouched. Public find,
count, and replacement operations are compared for 233 patterns and 356 subjects
(82,948 pairs); find tests every offset from -1 through length+1. The generated
corpus includes every string through length four over `a`, `b`, LF, and Greek
alpha, plus explicit astral, NUL, span, and failure subjects. Eighteen invalid
patterns must preserve exact nonempty diagnostics.

Fifteen demand oracles run separately against both the candidate and frozen
reference (thirty evaluations), using `evaluate`/`try` and exact exception
markers. They check subject-before-regex error order, a required regex for an
empty count, unused regexes for invalid find offsets, and unused replacement
bottoms when neither an empty nor a nonempty subject matches. Regex failure
must precede replacement failure for a valid subject; fixed, terminal nullable,
and Unicode span matches must demand a bottom replacement. Skip-plan matches
must also demand replacement, while empty and too-short subjects leave it unused.

Twelve additional private-scheduler oracles use literal dead/accepting transition
tables to isolate demand order. Both scanners require width before credit,
credit before poisoned shift tables, and shift tables on mismatch. Empty/base
branches ignore unused operands. Immediate scan acceptance ignores width,
credit and shifts; a width-one count acceptance ignores incoming credit and
shifts. Acceptance must force the count before the next offset's width, then
require that width after a valid count. Each case has an exact first-error
marker or literal integer result.
`NativeScheduling.emlf` repeats these twelve controls at Clang O0/O2 through
`test_native_regex.py`, whose isolated snapshot exposes only the two private
functions. That driver requires 52 executions: two public-API runs, twenty-six
public-demand cases, and twenty-four private-scheduling cases. Production exports
remain unchanged.

Eighteen additional adversarial pairs cover long repetitive failed suffixes,
the skip matcher's bounded-work fallback, matches after long runs, overlapping
alternatives, shared shifts, Unicode prefixes, NUL and DEL, and the 64/65-width
optimization boundary. Every valid and invalid offset is checked for each pair,
along with count and replacement. Sixty literal oracles independently check
exact results, including nonoverlapping counts after fallback and deletion of
fixed-width matches between retained Unicode prefixes, gaps, and suffixes.

The receipt records complete command outputs, timeouts, tool and source hashes,
and post-run integrity. Compile and test processes are individually bounded.
This is finite GHC-host semantic evidence. It neither proves equivalence for all
regular expressions nor establishes native-runtime or benchmark performance.

`Native.emlf` independently asserts public-API results for the bounded skip
fallback, overlapping alternatives, Unicode/NUL/DEL, width limits, nullable
patterns, and empty replacement fragments. `NativeDemand.emlf` checks exact
failure ordering and arguments that must remain unused. Run both through the
selected compiler and fresh native runtime at Clang O0 and O2 with:

```sh
python3 tools/shared/test_native_regex.py --compiler /path/to/emlf \
  --clang /path/to/clang --gc-prefix /path/to/bdw-gc \
  --output /path/to/new-native-audit-directory
```

The native receipt authenticates its selected tools, source snapshots and
artifacts and requires all fourteen executions. It does not authenticate the
compiler's source build or the complete system toolchain closure and makes no
performance claim.
