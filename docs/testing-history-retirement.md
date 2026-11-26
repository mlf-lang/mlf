# Retiring historical test infrastructure

The current test tree no longer authenticates the PR19/22/25/43 release and
squash history as a prerequisite for building or testing the compiler. The
last complete archive of that infrastructure is commit
`496dcae024cae1a93096d9bdb9d6b93e57359dc0`.

## Current checks

- `tools/release/check.sh` runs current metadata, package, benchmark-input,
  runner, workflow and evidence checks. It does not fetch or certify old PRs.
- `tests/golden/core-registry-contract.json` remains the independently reviewed
  public Core ID/name/family contract. Its schema and current catalog agreement
  are checked directly. `Tests.CompilerTests` validates executable discovery;
  `verify-unit-evidence.sh` validates retained discovery and execution reports.
  No historical rename projection or fixed total is needed to add a case.
- `tools/shared/run_direct.py` uses one bounded runner for CRC, UTF8 and
  candidate-selection checks. Ordinary Haskell fixtures, independent expected
  vectors, fresh demand cases, current Classes API checks, timeouts and
  descendant cleanup remain part of the actual campaign.
- `map-policy` records the current import/include closure and recompiles its
  two optimization lanes against independent reference modules. Inputs are
  checked again after execution; editing current code does not require adding
  an admitted hash to a list.
- Patricia file controls use `file_cases.run_files` and a directly compilable
  reference reader in `oracles/file-format`. The reference reader's own format
  and dependency format have explicit validation parameters. Frozen query
  adaptation checks the supported constructor interface rather than the hash
  of the entire current Types module. Run its four interface tests with
  `python3 -B tools/testing/run.py python-frozen-query`. The O2 CI job runs
  them before compiling the datatype-context controls.
- Current package/lock snapshots, producer identities, source immutability
  during execution, binary compatibility, independent algorithm oracles and
  failure propagation remain qualification boundaries.

Immutable reference fixtures may retain origin hashes. Those hashes identify
the reference algorithm; they do not admit or reject the current implementation
or require a historical Git checkout at test time.

## Retired material

The removed material includes historical reference preparation and workflow
policy, Core/Tuple-list migration proofs, dated inventory and reconciliation
audits, source-projection/successor replay chains, migration ledgers,
`tools/shared-migration`, and the old framework-reconciliation execution logs.
Obsolete A1 current-source adapters and C4 reproduction wrappers are also
retired. Maintained finite controls use their direct fixtures.

`tools/performance/artifact-binary` retains `BinaryBuiltinControls.hs`,
`BinaryP2WriterControls.hs`, `API.md` and `WIRE.md`: these still support current
semantic and binary compatibility checks. The rest of that directory's old
source-transition machinery has been removed. Current benchmark sources and
upstream adaptations remain pinned by `benchmarks/manifest.json`; obsolete
historical transition manifests are no longer benchmark inputs.

The full-compiler timing-analysis tests and current source-manifest checker
remain. A test named “contract” or “migration” is not automatically historical:
for example, actual old/new query-cache format compatibility is behavior.

## Inspect or reproduce an old record

Use the recorded Git tree, outside the current qualification checkout:

```sh
git show 496dcae024cae1a93096d9bdb9d6b93e57359dc0:tools/shared-migration/README.md
git worktree add --detach ../mlf-history-496dcae0 \
  496dcae024cae1a93096d9bdb9d6b93e57359dc0
```

For an individual historical campaign, use the exact revision, inputs,
toolchain and commands recorded in that campaign. The archive preserves old
claims and limitations; it does not imply that every old registered suite
passed at the retirement commit. Do not update its pins to make it qualify a
different current tree.

Current correctness receipts and current performance measurements should be
produced by the maintained runners in the current checkout.

## Validation of this retirement

The following checks were run on Linux with GHC 9.14.1 and a complete current
O0 bootstrap producer. A lane described as O2 below actually recompiles its
tested Haskell modules with O2; it is not inferred from the producer's name.

| Check | Observed result |
| --- | --- |
| `tools/release/check.sh` | Passed all 47 registered suite invocations, including current package/lock, manifest, Core contract and evidence checks. |
| Default gates in a real depth-2 clone | The complete release check passed with old PR source objects absent. Fourteen selected fixture/runner suites and the frozen-query interface tests also passed there. |
| Core registry contract | Six schema, descriptor, ordering and ordinary current-case addition tests passed. |
| Candidate / UTF8 / CRC | All three managed campaigns completed, including real host/interpreter/native paths, demand/error cases and successful process cleanup. Candidate made 263 physical commands; UTF8 made 133. |
| Map policy | Both O0 and O2 lanes passed 24,649 raw tree pairs, 400 mutation steps, 30 retained demand probes and 25 current demand observations. |
| P1 selector differential | Passed 154,072 selector/interface checks and 6,162 collection checks. |
| LLVM Unicode controls | Both O0 and O2 lanes passed all 94 fixtures. |
| Header validation | The selected historical and current native lanes each passed with complete execution receipts and unchanged inputs. |
| Patricia file controls | All nine ordinary file cases and all nine session cases passed, including three real corrupted-artifact rejections. A final selected case also completed through the normal CLI after the session wiring correction. |
| Frozen query | O0 datatype controls passed 5,178 checks; O0 sparse controls passed 186 checks. Each includes 23 unsupported-syntax rejection checks with poisoned payloads to verify rejection before evaluation. |
| Runtime spawn protocol | Five controls passed in normal and optimized Python; the Linux fallback capability probe compiled and ran. |

The first full file-control attempt completed all ordinary cases, then exposed
a session loader access left over from the former dictionary-shaped data. Its
failed receipt was retained. The corrected session stage passed all nine cases;
the subsequent normal-CLI selection completed both routes in one execution.

The pure adapter, runner and fixture controls were also exercised with normal
Python and `python -O`. An independent call-graph review found no active import
or registered command targeting the retired files. The shared provenance suite
passed all 87 tests; the retained full-compiler timing contract passed all five.

These results are correctness evidence. They do not claim a new performance
measurement, a full self-hosting A/B qualification, a complete native-library
matrix, or execution of the Darwin-specific spawn path on this Linux host.
