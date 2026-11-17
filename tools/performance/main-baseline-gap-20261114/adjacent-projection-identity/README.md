# Adjacent projection identity diagnostic

This is one bounded diagnostic on main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`, not an optimization or benchmark. A fresh ordinary GHC 9.14.1 O2 producer passed its built-in self-test and the original shared Root plus Foundation `--type` workload. Target stdout was exactly `Bool\n`; stderr was empty. The same ELF, runtime and staged source identities were checked around both executions.

## Observed prefix

The capture retained 32 pairs / 46 ID-only sample records from genuinely consecutive operations within epoch 0. Sample operations were 53–707; actual local graph sizes were 129–277, despite the admitted 129–2048 band. Selected original IDs numbered 105–272. The Jaccard min / median / max was 0.744047619 / 0.872832370 / 0.993902439.

The LEFT operation's removed, changed, deleted and alias-left key sets were unioned, not summed. Across pair occurrences, their union contained 339 occurrences: 154 inside and 185 outside the left selected set. These are neither globally distinct nodes nor measured costs. Only left writes relate the two snapshots. Node payloads, names, kinds and alias-right values were not recorded.

The last saved pair's commit was event 2793. The event cap was reached at 65,536, ending at operation 18823 BEGIN. Thus `truncated=true` does not invalidate these completed pairs, but this is only an eligible prefix: it is not a random sample, all-epoch count, survey of the largest graphs, or workload-wide eligibility estimate.

## Decision

NO_GO for incremental projection or cross-call solver reuse on this evidence. High identity overlap does not establish equal fields, equal problems, a complete dependency set, safe reuse, or available speedup. External binder/ancestor, alias, hidden-root and scope changes can alter closure and dense numbering nonlocally. The original first error and lazy payload demand, including restoration's nonlocal name demand, must remain intact. A final validator cannot replace those obligations. No production shortcut or further sampling is admitted by this result.

## Source and evidence

The two patches are against the named main; the helper and entry point are included separately. These files are an archived source/evidence slice, not a turn-key build or deployment harness. The executed private closure bound 96 home modules and 128 staged inputs. Ordinary GHC settings included `-O2 -fpedantic-bottoms -fno-state-hack`, fresh compilation and isolated output directories; modified diagnostic modules disabled CSE and full-laziness. No native/fixed-point A/B was run.

Source v2 had two static-review blockers: a missing declaration separator and possible pair publication before all required events survived capacity checks. Both were fixed in v3 before compilation; v1/v2 and the blocked review remain preserved. This limited diagnostic does not establish general arbitrary-lazy/concurrent-input equivalence. The independent offline audit retained its initial reader truncation/schema error rather than rewriting it as a pass.

All 359 actual files plus five outer records (73,046,156 bytes) were privately saved with complete Library readback; PINS identifies this raw archive, executed producer and source reviews. Public data omit binaries, private paths and Node/name/kind payloads. The full event trace remains in that private raw archive; its SHA is recorded here. No main or PR51 change, merge, CI qualification or performance claim is made.
