# Map balance bound ordering, 2026-10-30

The candidate changes two expression lines in `Bootstrap.Map.balance`: after the unchanged total-size guard, choose the larger child before testing its balance bound. Balanced and left-heavy calls avoid one Integer multiplication; right-heavy calls add one comparison. There is no new transaction path or representation. The [control documentation](../../tools/performance/map-balance/README.md) gives the signed-Integer argument and exact oracle boundaries.

## Independent confirmation

The frozen comparison used ordinary GHC 9.14.1 `-O2` executables, a single execution lane, and the fixed 15-module mlf-crates task. Every execution inferred **711 fresh / 0 reused** groups and compared both checked outputs with the independently qualified pre-candidate reference using their raw bytes. Fixed dependencies were reused. No target inference result was reused.

The predeclared main estimate averages six block means of paired log(B/A) wall ratios. The fixed 24-run window gave **1.2200%** improvement, with a nominal 95% Student-t interval of **0.4470% to 1.9871%**. The AB and BA direction estimates were 1.0247% and 1.4151%. Descriptive arithmetic mean wall times were 71.4183 s before and 70.5459 s after; ordinary child CPU means were 70.0786 s and 69.1595 s.

| Block | Order | Point improvement |
| --- | --- | ---: |
| 0 | BAAB | 1.3067% |
| 1 | ABBA | 0.6564% |
| 2 | ABBA | 0.7646% |
| 3 | ABBA | 2.4408% |
| 4 | BAAB | 0.5165% |
| 5 | BAAB | 1.6216% |

The frozen acceptance rule required a point improvement of at least 1%, a positive interval lower bound, positive AB and BA direction estimates, and every correctness/resource gate. It passed. These are conditional results for the fixed binaries and this macOS host, not a search-wide 95% guarantee, a minimum 1% benefit, a complete compiler build measurement or a new MLF/GHC ratio.

**Protocol deviation:** after block 2, strict equality of the `kern.boottime` text falsely reported a reboot when only its microsecond field changed by 59,932. The continuously running Codex parent predated the cohort. The original failure receipt was preserved; a separate recovery changed only the boundary identity check to `kern.bootsessionuuid`. All first 12 executions were retained, and the remaining 12 followed the original order, limits and acceptance rule. There was no failed/partial target execution, sample replacement or sample addition. This was a recovered window, not an uninterrupted protocol.

The raw reference for this current 15-module task was qualified against the pre-candidate/d96 ordinary compiler. This round did not rebuild original P3 for that target. The separate original P3-based semantic oracles remained frozen and executed.

## Discovery record

| Candidate | Low-cost evidence | Decision |
| --- | --- | --- |
| Late inline integer equality/ordering | Ordinary lookup machine code remained byte-identical | Reject at the mechanism gate; no full timing window |
| IntMap equal-or-right reads | Smaller ordinary code; two screening blocks gave 0.5993% pooled improvement with opposite block directions | Defer; no confirmation or integration |
| Map balance bound ordering | Two screening blocks both improved; pooled point estimate 1.2297% | Freeze, qualify, then run the independent window above |

A separate baseline counter relink observed 243,937,556 balance calls: 30,558,276 small, 16,216,552 right-heavy, 4,002,761 left-heavy and 193,159,967 balanced. These diagnostic counts support a potential saving of one multiplication in 197,162,728 logical calls. They are not ordinary exclusive wall-time shares, and no allocation percentage is claimed for this candidate.

Ordinary object disassembly preserves the direction comparison before two alternative multiplication branches. Both multiplication call sites still exist statically; the saving is on the executed path. The rewrite adds one source-level conditional, correcting the frozen discovery card's wording about an unchanged branch count. The symbol-bounded region, including local continuations and info tables, grows by 400 bytes on this host. The experiment measures the net effect of that cost and the avoided work.

## Integration and qualification

PR #25 advanced from the experimental baseline `823f3060` to C4 head `51953cb8` during this work. Integration preserves that upstream change. A separate ordinary C4 producer and the actual combined producer were built from their own sources. The ordinary Map objects on each side are byte-identical to their corresponding pre-C4 objects. A separate, predeclared four-run ABBA window checked the combined product against C4: its descriptive block-log improvement was **0.9458%**, with positive AB and BA directions (0.5143% and 1.3754%). Mean wall times were 71.7207 s and 71.0423 s. All four runs passed the fresh, raw-byte and resource checks, satisfying the fixed integration rule. This single block supplies no new confidence interval and is not pooled with the independent confirmation. Exact artifact identities and chronological data are in [the evidence summary](map-balance-20261030-evidence.json).

The frozen integration workload file retained an obsolete `compiler_baseline_commit` label from the earlier experiment. The executed A binary and its authenticated source closure were the newly built C4 baseline `51953cb8`, as recorded by the pre-run authentication and each command receipt. A separate metadata correction preserves the original file and verifies its producer source inputs against that Git commit; no executable, input, timing row or acceptance rule changed.

The actual combined producer passed:

- 24,649 raw-shape pairs, 400 mutation steps and 30 independent demand/error-order cases.
- The complete retained P1/P2/P3, A1, F1 and QueryEncoding gates.
- Full C4 graph/transaction/layout controls, all nine before/after file comparisons and shared builtin admission.
- Native Map controls at ordinary Clang `-O2`, including the original 1,024 subset pairs and the additional literal/demand cases.
- Source-migration refusal tests in normal Python and Python `-O`.

The generated Prelude changed only its source-identity token and was independently regenerated by the unmodified ordinary build. A1/P1/P2/C4 admission updates preserve the earlier oracle bodies and expected results. The C4 dependency extension inverses to the entire earlier manifest byte-for-byte, retaining all 179 before inputs and the two C4 algorithm hashes. A new O2 CI step runs the independent Map controls.

The first pushed commit's Release metadata job detected an omitted dependency-pin update in the active benchmark manifest. The follow-up updates only its Map source hash: benchmark programs, expected outputs and thresholds are unchanged. The provenance gate then passed all pinned hashes and 19 exact adaptation reconstructions. The measured ordinary producer still authenticates, so this metadata correction does not change the measured artifact or require new timing samples.

The root package's `mlfpkg --locked plan` passed. The local full CI-policy command encounters the macOS system Bash 3 empty-array/nounset incompatibility, reproduced on the unchanged C4 baseline. It is not reported as a passing full local release gate. Hosted CI, complete native bootstrap, all ten benchmark-game runtime workloads and whole-compiler timing are separate qualification scopes.

Raw checked outputs, process receipts, input/cache inventories, ordinary objects and failed exploratory attempts remain in the local evidence directories. The repository summary retains artifact hashes, chronological timing rows and gate receipts without committing the large checked/cache payloads.
