# Small guest targets and PR-smoke: source acceptance

This follow-up starts from `ee49a0584a36846fa96b901f450fba8c23f770ba` and the three exact files in `reviewed-inputs.json`. It changes no shared compiler implementation or producer. These are actual MLF `--compile-crate` checks, **not execution** of the named campaigns.

| Maintained target | Module entries | Fresh groups | Seconds | Peak RSS bytes |
|---|---:|---:|---:|---:|
| figure12 | 3 | 20 | 19.56 | 248406016 |
| int-set-unions | 2 | 7 | 15.31 | 223268864 |
| check-target | 1 | 2 | 16.13 | 223170560 |
| pr-smoke | 13 | 124 | 48.55 | 476676096 |

All four checks completed with zero query reuse: **19 module entries including overlap / 153 fresh groups**. Figure12's sources also appear in pr-smoke; these counts must not be presented as 19 distinct modules. Exact identities, entries and module sets match the real manager plan. That plan's source snapshot agrees with the independent audit (13 packages / 212 hashes), but not all targets in this graph were checked.

The first actual Figure12 source check rejected the legacy Monad selection for shared Either in `assumptions`/`program`. The sole guest-source fix adds explicit `Prelude hiding (Monad, return, bind)` and `MLF.Primitive (Monad, return, bind)` imports. Every pre-existing body, fixture string, expected type and label remains byte-for-byte unchanged. No compiler rule, duplicate instance or source translator was added.

The original Figure12 semantic pin correctly rejected this import change. Independent review confirmed unchanged lookup ordering, Left propagation, lazy Right construction and wrapping strings, then approved the exact new digest. The decoder adds a negative control removing both imports. Thirteen decoder tests pass, and fresh faithful host Figure12 runs pass at O0 and O2 (77 substantive checks each). These host runs do not execute the legacy guest compiler-within-compiler suite. The failed source receipt and old-pin rejection remain recorded; neither is relabeled as success.

Full release/static controls passed. Source/interface inputs were unchanged during each probe; authenticated O2 producer and object hashes were rechecked. Required nonempty checked artifacts have recorded hashes. Full query/artifact inventories remain local; no binaries, checked objects or caches are published. Copied probe drivers explain collection, not a new normal build or maintained CI gate.

Full guest/Core/unit execution, remaining source targets, manager cache/stamp/closure qualification, native LLVM/linking, released-seed frozen bridge and native fixed point remain separate gates. Resource caps here were 900 seconds, AS 3 GiB, process-tree RSS 1.5 GiB, host available memory at least 3 GiB, output at most 100 MiB and disk free at least 768 MiB.
