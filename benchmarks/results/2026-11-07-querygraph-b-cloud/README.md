# QueryGraph B cloud checkpoint

Status: work in progress, not native-qualified and not ready to merge.

Production change: `3c7c2b7a4774f403f93bb77ac38d5cb143ce7743`, based on
ScopeCache `1ce9f25eecf8283cd818ba79ea5d751ab05d0df4`. Only QueryGraph and its
lockfile source hash changed in that commit. The implementation is the exact
diagnostic `encodeIndexB` and `encodeIndexRows` port, with one shared row helper.
Independent static review found no validation, ordering or tuple-field change.

## Executed controls

- All 22 supplied evidence files and the complete Git bundle matched their
  supplied SHA-256 values. The independent reader admitted the 384,302-byte
  snapshot: 2,510 query rows, 15,092 ordered reads and 1,434 payload references.
- A fresh GHC 9.14.1 `-O0` thin probe compiled the reference and candidate modules
  after changing only their module names. Both emitted the exact original bytes
  and SHA. All tables, logical rows and ordered reads matched the independent
  reader. All seven original expected errors and five multi-fault ordering
  assertions passed. Compilation took 16.76 seconds; these are host controls,
  not native compiler performance measurements.
- The same probe passed an independently generated 12-node fixture containing
  all descriptor kinds, Unicode, payload references, 10 ordered reads and two
  duplicate reads. This adds explicit coverage absent from the large snapshot.
- The ordinary GHC-hosted manager from clean `98540496` ran offline `lock` and
  `--locked plan` successfully. The semantic lock diff is exactly one source
  hash. JSON indentation was retained after generation.
- The repository shared-source inventory and dependency boundaries passed for
  140 modules. Python syntax and `git diff --check` passed.
- The existing complete Linux release bundle passed this checkout's actual
  `scripts/bootstrap-shared.sh --verify-seed-only`. Its native origin is verified,
  but no bridge, stage-1 or candidate compiler was built by this check.

The initial probe receipt did not include hashes for the independent reader
modules or Python interpreter. A new-directory replay of the final runner now
passes with these pins and both fixtures. The 12 fixed negative controls run
against both inputs; all commands exit zero with empty runtime stderr. The
outer watchdog records 27.812 seconds, 665,600,000-byte peak process-tree RSS
and no remaining descendants. The original result and limitation note remain
unchanged. That historical replay included lazy candidate node conversion and establishes
no speedup. A subsequent driver now fully prepares both maps before timing;
its new-directory replay also passed in 27.626 seconds, peak RSS 659,095,552
bytes, with the same full bytes and 12 negative controls. It remains a
GHC-hosted semantic diagnostic, not native performance qualification.

## Ordinary producer and actual builtin regeneration

The QueryGraph change is inside the 56-module builtin source-identity closure.
An unchanged ordinary O0 builder in a frozen clean clone therefore failed the
exact stale-identity gate after all preceding commands succeeded. The maintained
collector generated actual fresh bytes and re-authenticated its inputs. The
2,220,407-byte output differs only by the sole 64-hex identity at byte offset
776. Independent review confirmed this full-byte equality. The actual stdout
was copied unchanged and the ordinary lock/locked-plan path updated only its
source hash. The original failed producer and receipts remain untouched.

The repaired source commit is `5bd186d`. A fresh ordinary GHC 9.14.1 O2 build
then passed for all 140 shared modules and the complete builtin verification
gate. The maintained `authenticate_build` verifier passed again after completion.
The run took 234.881 seconds with peak process-tree RSS 1,066,844,160 bytes;
there was no resource-stop reason. This qualifies the exact-source ordinary
GHC development producer only. It does not satisfy native build, fixed-point,
performance, CLI or complete step-18 acceptance. See `builtin-generation/` and
`ordinary-o2/` for original evidence copies and hash indexes.

## Integration observations

The current remote heads still match the handoff: #43 is an open draft at
`0812ca846b91ad55abc433d7fa352d18f315cadf`; migration is at
`3d6c472b403f6aebd1960a4c1b7fb84b33af4261`. Both are ancestors of this checkpoint.
#43 is not currently mergeable against main.

The exact `a250ec334b70b0e587c2dd6e894d111bf879c024` commit is not in the bundle;
GitHub reports it and the migration head as diverged from `c5928b5b` (55 ahead,
1 behind). The checked Prelude `cratePrelude` and `checkedCrateObject` functions
are already present and were introduced in this ancestry by `6927bfac` (#32).
Do not blindly replay the later duplicate change. A complete integration audit
and final-SHA checks remain necessary.

## Remaining acceptance

1. Build current-source native input tools through the documented release-seed
   bridge/stage-1 route, keeping each producer and cache isolated.
2. Run ordinary offline locked native `emlf` construction. Independently decode
   the actual schema-7 `mlf-crates` object under the original 67,108,864 work limit.
   The supplied schema-6 snapshot's accounting is not evidence for this gate.
3. Run the native thin probe and real CLI comparisons for 4/256 groups,
   Bitstream and IntSet with identical input/dependency/builtin bytes.
4. Complete the original step-18 semantic, compatibility, concurrent publication,
   ABI, cold/warm self, root build/test, CoreSolver 1,800-second, Port and
   Foundation RSS gates without changing their budgets or oracles.
5. Recheck remote heads, integrate and validate the final exact SHA. Publishing,
   PR creation and merge have not been performed.

The cloud work uses its own directory and caches. It shares only the verified
read-only tool installation with the concurrent #22 recovery. Heavy compilation
is serialized; no existing jobs or outputs were overwritten.
