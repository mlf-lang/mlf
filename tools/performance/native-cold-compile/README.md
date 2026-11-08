# Small native cold compile reproducer

The default input has 256 independent bindings. Both compiler arms receive the
same source, checked builtin pair and dependency interfaces, with fresh query
caches. The script measures CPU, wall time and peak RSS, then compares CI, CO,
queries, every logical query node, ordered read and raw payload. The query
configuration's actual compiler fingerprint is checked separately for each arm.

```sh
python3 tools/performance/native-cold-compile/repro.py \
  --reference /path/to/before/emlf --compiler /path/to/after/emlf \
  --builtin-prefix /path/to/verified/builtin --output /tmp/cold-small
```

Use a different fresh output directory and `--profile` for the six existing phase
clocks. Profiled samples are separate diagnostics. `--groups 16` makes a smaller
input. To check an untouched real compiler module, pass
`--source libraries/mlf-crates/Bootstrap/Bitstream.hs --module Bootstrap.Bitstream`
and `--dependency /path/to/checked-foundation/unit.mlfci`.

Each child has an explicit 120-second diagnostic budget, adjustable with
`--timeout`. Failed commands and partial output are retained. These small runs
do not replace the original root-test or CoreSolver acceptance limits.

## Scope encoding cache measurement (2026-11-07)

The ordinary native compiler CLI, built before and after the ScopeCache change,
produced the following single-pair cold measurements on Darwin. The source,
builtin, dependencies, runtime and GC settings were held fixed. Instrumented
phase measurements ran separately.

| Input | Before wall | After wall | Before CPU | After CPU |
| --- | ---: | ---: | ---: | ---: |
| 256 independent bindings | 12.382 s | 6.260 s | 11.878 s | 5.885 s |
| Untouched `Bootstrap.Bitstream` (168 groups) | 44.276 s | 44.027 s | 42.930 s | 42.567 s |

The 256-group graph phase fell from 9,021 to 2,936 ms in the separate profiled
pair. Its 1,702 logical nodes and 14,675 ordered reads stayed equal. The real
module's 2,510 nodes and 15,092 reads also stayed equal; its small timing change
does not establish a speedup. Both cases retained identical CI, CO, query report,
normalized generation and every payload. A compile with three different scopes,
an instance/contract reorder and a good-then-invalid binding control also kept
their original outputs or diagnostics. This verifies the local optimization;
full root, RSS and CoreSolver acceptance remain separate requirements.

The changed compiler target builds through the ordinary locked package path.
Its schema-7 crates object independently decodes with expanded work 66,952,713
under the unchanged 67,108,864 limit (156,151 remaining).

## Exact-source QueryGraph B control

`querygraph_boundary.py` compiles two copies of the real QueryGraph module,
changing only each module declaration. The reference comes from the specified
Git commit (default ScopeCache `1ce9f25e`); the candidate comes from the current
checkout. All other shared dependencies are the same. It replays a supplied
canonical generation and a small independently constructed generation containing
every descriptor kind, Unicode identities, payload references and repeated reads.

```sh
python3 tools/performance/native-cold-compile/querygraph_boundary.py \
  --input /path/to/generation.mlfqg --config /path/to/config.txt \
  --output /fresh/private/querygraph-boundary
```

The original seven fixed rejection messages and five multi-fault precedence
checks must match in both arms. The encoder output is fully forced, serialized
and compared byte for byte with the input. The independent Python reader also
checks every table, row and ordered read. The script records exact sources,
tools, commands, stderr and output hashes; failures retain their partial receipt.

This is a GHC-hosted semantic diagnostic. Before timing, the current driver
forces both map spines and every node field, including the candidate conversion.
Earlier checkpoint timing included lazy candidate conversion and remains only
historical host evidence. No host timing establishes native compiler performance.
Neither this probe nor the small generation's wire accounting establishes the
production schema-7 compiler object's expanded-work budget. A normal locked
native build, independent object accounting, native thin probe and real CLI
comparison are still required before claiming the plan B optimization is ready.
