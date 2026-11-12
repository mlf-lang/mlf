# Future public-API Haskell regression fixture

**Source only. All 24 Haskell cases are uncompiled and unrun.** No host output, expected-success receipt, build wrapper, or automatic compiler invocation is supplied. The source is intended to be compiled unchanged in three separately admitted ordinary builds: pinned baseline, delete-only, and spine-only. The two candidate patches are alternatives, not cumulative.

Source pin: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. The restored original source and prior standalone `CheckedOpenProjection.hs` supply the real imports, custom Either/types, Open/Checked APIs, and structural encoding helpers. This fixture does not construct opaque CheckedTerm, Environment, or Fragment values. `Open.environment` constructs its context; `Checked.check` constructs every tested receipt.

## Coverage, not results

`OpenFragmentGuardPublicApi.hs` defines one host `Main`, with a fixed ordered list of **24** cases:

- 6 small total Open fragments, including empty inventory, explicit external use, mixed/empty recursive chunks, RHS-local binding exclusion, and a polymorphic RHS. They observe public constructor boundaries, check prescribed exact fields, encode seven real snapshot fields, and exercise unchanged `normalize` and `audit`.
- 10 exact Open first-error controls for parameter, body, recursive declaration, and fragment-shape checks.
- 4 public raw-checker two-layer controls. Their nonempty XEnv is first validated through `Check.inferWithData`. Outer inference errors are distinguished from the separately deferred inventory error. This is not a claim that Open.check admits open parameter types.
- 2 genuine Checked nonfragments. Integer and leading-lambda receipts permit type access but have distinct raw inventory outcomes; their unpeeled open bodies still reject.
- 2 partial-host paths for the unused outer type-binder case, one through a genuine Checked receipt and one through Open.check.

`CASE-MAP.json` gives every must-run ID in order, the intended observations/errors, and explicit deferred coverage. A named case here is an assertion to be tested, not an observation that it passed.

## Partial-host case and safe observation boundary

The partial input is a finite host AST equivalent to:

```haskell
p = forall good : XBot . good -> good
rhs = XTypeAbs bad XBot (XAbs local p (XVarTerm local))
body = XLet m rhs unit
```

Only `bad`'s integer ID throws a dedicated `LatentBinder` exception. It is a deterministic host exception sentinel, not language `XBot`, a divergent loop, or a claim about source-text reachability. The checked and open routes use different sentinel tags.

The fixture first observes safe public Either/opaque receipt/Fragment/body/bindings boundaries. It checks the total inferred program type and the total `p -> p` children, without encoding the partial outer type or body. Its **last** observation deliberately forces the binder ID from the actual owned output type and requires the matching sentinel. This witnesses that the tested output still contains the partial binder; a standalone unrelated sentinel would not suffice.

The partial Open case deliberately does not request fingerprint, encoded body/type, used parameters, normalize, or audit. Their additional partial-input demand is not claimed safe by this fixture. They remain deferred rather than being replaced with fake PASS records.

`evaluate` only establishes WHNF of the explicitly supplied value. `length owned` observes completed traversal at that later explicit consumer. Neither proves that the entire appended owned spine was forced before Open.check returned Right. No unsafePerformIO allocation probe, opaque-constructor escape, production instrumentation, or heap claim is added. Actual append-spine timing, residency, stack, and performance remain deferred.

## Stable stdout contract

For each case, the fixture aggregates real successful observations and encoded bytes in memory, then emits exactly:

```text
PASS<TAB>case-id<TAB><Haskell show String of the aggregate observations>
```

A failed assertion or unexpected synchronous host exception emits the same three-column form with `FAIL`, followed by the eventual summary. The final line is:

```text
SUMMARY<TAB>total<TAB>passed
```

All lines end in LF. Failure makes the process exit unsuccessfully after the summary; asynchronous cancellation is rethrown, not converted into a passing record. Expected sentinel observations are recorded inside a successful case only after the exact exception tag is checked. Unexpected exception details are suppressed rather than printing host paths or call stacks.

The aggregate String contains ordered `observation=value` lines, escaped by Prelude `show` so stdout remains one line per case. Only after all case observations finish, a test-only `forceString` fully evaluates the rendered PASS line (characters and spine) inside the per-case exception handler. Lazy rendering failures therefore become FAIL rather than escaping that handler. FAIL rendering has a stable suppressed-detail fallback. This is output validation after the observation sequence, not production forcing or evidence of earlier list-spine demand. External stdout write failures can still truncate output; the comparator rejects incomplete records. Total snapshot bytes are recorded as `field.bytes=decimal-byte-count:lowercase-hex`. These are actual Wire bytes obtained from the public fragment during a future run, not predefined expected output. The source does not include variant IDs or timestamps in the payload; external records identify the build being compared.

Do not generate a host-output record from the CASE-MAP or expected values. There is no genuine host stdout in this directory.

## Output comparison tool and independent review

`validate_host_outputs.py` compares three externally supplied output records. It does not run, build, or resume the fixture. It requires exactly baseline/delete-only/spine-only records; matching fixture and case-map digests; the pinned baseline and expected candidate OpenFragment digests; declared ordinary/shared-build-input metadata; complete ordered PASS case coverage; exact summary; fresh stdout digests; and identical aggregate payload bytes across variants.

It rejects missing/duplicate/unknown/reordered cases, FAIL, truncation, changed payloads, and inconsistent source/build claims. It treats the shown aggregate String as opaque text with a surrounding-quote shape check. It does **not** parse full Haskell `show` syntax, validate internal observation completeness/hex, authenticate self-reported build identity, or prove that Haskell actually ran. If all three records omit the same internal observation, the comparator cannot infer that omission; case internals must be reviewed in this pinned fixture source.

I independently read the comparator and its tests, then ran only:

```text
python3 -B -m unittest -v test_validate_host_outputs.py
```

Observed: **16 pure synthetic-record tests passed in 0.005 seconds**. These tests contain no actual Haskell execution or host result. The validator always leaves `actual_haskell_execution_established`, `build_provenance_authenticated`, `artifact_equivalence_established`, `performance_claim_established`, and `resume_authorized` false, including for records labeled reported-host-output.

Reviewed comparator SHA256: `4016078063da0539cb9f6e9087fe013a0440f15fe8ecfe62a4cf15419d0f96d3`.
Reviewed comparator-tests SHA256: `2eb9fc54b1a1ca684c0611107d0f80da2f0ac3feb581d108a24b85b2d5fe53e4`.

## Future real qualification

A separately approved ordinary setup must establish cleanup/admission, source/toolchain/package/producer identity, isolation of the three variants, exact compile/link provenance, bounded execution, full stdout/stderr and exit status, and post-run cleanup. A self-reported record or successful content comparison is not that authorization or evidence. No archived admission, new path, or source-only recovery authorizes a run.

The same unchanged fixture source and CASE-MAP must be used for all three variants. Do not mix ordinary and profiled objects, introduce test forcing into production, weaken assertions after a failure, or substitute this small fixture for existing complete checker/context/scope/artifact suites. Real CompilerCore phases, named/indexed group compilation, composed-receipt demand, complete interface/object/query artifacts, and native A/B/fixed-point work remain outside this preparation.
