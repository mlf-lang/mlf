# r28 codec phase screen: raw observations, not an optimization result

Independent same-build emitted Core/STG review passed the limited action-entry
and result-forcing boundaries. No compiler speedup, exclusive library-function
cost or new optimization is claimed. See emitted-review.json for the precise
qualification: action/thunk closure construction remains outside the intervals,
and the recursive force-tables-control traversal was NOT optimized away.

The phase fixture was compiled and ran successfully in one bounded batch of
12 commands. There are four fixed payloads and seven observations each, once
only: empty-before, plan, force-tables-control, layout, writer-plus-crc,
standalone-crc, empty-after. observations.json preserves all 28 numeric rows
without subtraction or filtering. They were independently compared to actual
stdout ending in PASS codec-phases. Payload sizes and hashes were checked
against actual bytes. The production codec and its compiled dependency closure
were outside this experiment's changes; the observer is a separate Main.

## Interpretation constraints

- The four payloads are unweighted: smallest/median/largest result by size and
  filename from one fixed 1,478-result corpus, plus its generation index.
  They are not compiler-wide workload weights. Do not project their proportions
  onto a compiler allocation bucket or infer whole-compiler improvement.
- Small action/thunk closures are constructed outside each measured interval;
  the primary phase operations enter within it. The force-tables-control
  traversal remains present, despite its zero observed allocation.
- Allocation observations are current-thread getAllocationCounter differences
  in bytes, not process total allocations or RSS. Effective resolution is about
  4 KiB; empty-observer noise and small/negative/zero values remain unresolved.
  Zero force-tables-control does not establish zero traversal cost.
- Times are monotonic nanoseconds for single observations, not stable benchmark
  medians or statistical significance evidence.
- Plan includes structural Tables forcing, not exclusively the raw plan call.
  Input Values and scalar lookup resources are forced before the intervals.
  Tables retain the same input texts; the v2 observer forces text WHNF/count
  without repeating per-scalar indexing. Production utf8Size/map work remains.
- The writer observation includes CRC. The standalone CRC runs on warm output
  later and must NOT be subtracted as an exact writer-exclusive cost.
- File IO, decode, initial input forcing, output equality, stored checksum
  validation and the production dependency closure are outside the intervals.
- No native-generation A/B fixed-point run is included; that work remains paused.

## Source and reproduction scope

CodecControl.hs and CodecPhases.hs are exact archived sources. Their initial
SOURCE ONLY headers describe drafting time, not the later completed phase run.
source-pins.json identifies the frozen production sources and same-build Main
Core/STG captures by hash; it does not bundle object files or large dump files.
CodecControl is a control fixture, not itself the source of these 28 observations.

To reproduce a comparable screen, prepare the exact pinned ordinary F25 codec
source/dependency build. Compile CodecPhases.hs as Main against that coherent
ordinary closure, capture Main.dump-simpl and Main.dump-stg-final from that
same compilation, and link that exact Main object with its matching dependencies.
Run the resulting executable with four payload filenames in payloads.json order.
Require all four payload SHA-256 values and sizes to match, exactly 28 rows in
frozen stage order and final PASS codec-phases. Review emitted ordering and
forcing before attributing any interval to a production phase. Never silently
substitute a different corpus or regenerate an expected payload after failure.

Payload bytes, generated builtin, machine-specific runner, object closure and
internal execution receipts are intentionally not bundled. This is therefore
an evidence/source archive, not a self-contained one-command reproduction kit.
No additional compilation or rerun was performed while staging this archive.
