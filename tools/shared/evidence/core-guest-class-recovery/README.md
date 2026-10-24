# Guest Core/backend compatibility checkpoint

This is the reviewed follow-up to published `ee49a0584a36846fa96b901f450fba8c23f770ba` (CI run `40076803522` passed). Exact follow-up files are bound by `reviewed-inputs.json`; that earlier CI is not relabeled as this follow-up's result. Shared compiler implementation, host adapters, runtime and frozen bridge archive are unchanged.

## Actual MLF source checks

The authenticated O2 compiler ran maintained `--compile-crate` with manifest-derived modules, entries and direct interfaces (own tests-library interface last). All six checks passed with zero query reuse:

| Target | Module entries | Fresh groups | Seconds | Peak RSS bytes | Checked artifacts bytes |
|---|---:|---:|---:|---:|---:|
| core-crates | 10 | 129 | 72.84 | 516444160 | 69742198 |
| core-language | 11 | 113 | 51.00 | 452620288 | 49262603 |
| core-modules | 12 | 123 | 68.98 | 498360320 | 64263587 |
| core-solver | 19 | 346 | 80.16 | 598306816 | 81413387 |
| core | 41 | 614 | 172.14 | 829104128 | 205473540 |
| backends | 31 | 302 | 157.17 | 1109176320 | 266550512 |

Totals are **124 module entries including overlap**, 68 distinct module names across these six targets, and 1,627 fresh groups. Do not add overlapping entries as distinct source coverage. The saved manager plan agrees with the independent 13-package/212-source snapshot; not every target in that plan was checked. The [preceding four-target batch](../guest-small-targets/README.md) remains separately scoped.

Input and required interface/object hashes are retained, with producer plus all object files reauthenticated. Resource summaries bind full local raw receipts by SHA256 and report sampled minima/maxima. Limits: 900 seconds, AS 3 GiB, process-tree RSS 1.5 GiB, host available memory at least 3 GiB, disk at least 3 GiB and output at most 512 MiB. These probes used a local copy of the then-maintained watchdog with only its disk floor raised to 3 GiB; the original is recoverable from the base commit. The subsequent maintained watchdog now exposes that stricter floor as an optional argument, leaving its 768 MiB default unchanged.

These results establish inference/elaboration and checked-fragment generation, **not execution of 739 Core actions, backend parity, whole-unit qualification, full manager cache/stamp/closure validation, standalone complete object re-decoding, or native LLVM/link/bootstrap/fixed point**. No checked objects, query caches or binaries are uploaded here.

## Minimal compatibility repairs

Legacy guest `Prelude.Monad` and shared standard classes are different identities. Repairs were inventoried and reviewed per concrete use, not blanket imports:

- `CoreRegistry`, `CoreRunner`, `CoreSolver`, `CrateCodegen`, `EmbeddingPruning`, `GraphValidation`, `Separate`: select canonical Monad for actual shared Either operations, with original bodies retained.
- `OptimizerUses`: select canonical Monad for the shared optimizer's `Fresh` actions; differential traversal/oracle bodies are unchanged.
- `GraphDenseReference`, `InferenceReference`, `GraphUnification`: select canonical sequencing and replace only proved Either-specific legacy `H.fmap` calls with `S.mapEither`.
- `GraphScopesReference`, `GraphUnification`, `GraphSolver`: proved Maybe mappings use `S.mapOptional`, not list-filtering `mapMaybe`. The GraphSolver Build mapping uses canonical `fmap`.
- `Graph`: standard Functor/Applicative/Monad instances delegate to unchanged `returnBuild`/`bindBuild`, preserving data/state/error kernels. `GraphSolver` and `GraphUnificationReference` select those classes for mixed Build/Either use. Canonical `pure` explicitly hides legacy Prelude's IO-specific `pure` where needed.
- `Snake`: only four Either-specific mappings change. Its independent legacy Script instance remains intact.
- `Oracle`: its independent Algorithm W and legacy W API remain intact. One local, closed `mapW` specialization of ordinary monadic list traversal replaces the sole incompatible shared `S.mapM` call, using unchanged `returnW`/`bindW` and preserving fresh-variable order.

Existing fixture strings, expected labels/types, and logical Core family composition remain unchanged. The Core checker originally rejected CoreSolver's import insertion under whole-file equality. It now permits exactly those reviewed three lines after that one frozen header, while requiring every original byte and all other family files unchanged. Three negative controls reject removed/changed imports and changed bodies; no general import normalization or baseline refresh is used. The frozen 35-family/739-action inventory still passes.

## Actual behavior and maintained regression

`tools/shared/test_guest_state_laws.py` imports the real guest Graph/Oracle modules through authenticated O2 MLF, without copying implementations or interpreting the compiler inside itself. Its final four-stage campaign passed: 14 explicit Graph state/class checks, four independent Oracle traversal checks, plus two intentionally incorrect-oracle controls. Identity/associativity examples, state and application ordering, Left short-circuiting, lazy payloads and explicit fresh-variable expectations are covered. This is focused behavior coverage, not a universal law proof.

Positive stages require exact PASS output; negatives require exit 1, no resource reason, and exact failure output. Resource/time errors cannot count as expected failures. Source/tool inventories are checked between stages and at completion, including contained symlink aliases and source additions/removals. All producer objects and retained resource/log hashes are rechecked. The watchdog limit is **90 seconds per stage**, not per campaign; the observed campaign took 95.38 seconds. O2-only CI now runs this gate. Twelve Python-only fault controls, existing guest-source controls, CI policy and full release/static controls passed locally; remote follow-up CI is a separate result.

Failures remain under `failures/`: unresolved guest class boundaries, an unsupported legacy infix spelling corrected to ordinary prefix `(<*>)`, and old IO-specific `pure` ambiguity fixed by an explicit hide. They are not qualified passes.

This checkpoint precedes the next standard list/tuple/unit, overloaded-string pattern and MonadFail alignment. It does not implement or qualify those later semantics. Full native bootstrap is deliberately held until that new contract is stable.
