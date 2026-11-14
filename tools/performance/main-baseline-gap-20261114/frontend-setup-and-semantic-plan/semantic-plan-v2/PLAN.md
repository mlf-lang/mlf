# Main12 semantic qualification v2: producer-aware proof, then same-binary raw oracles

**Source-only proposal. No successful SETUP, workload qualification, runner,
admission, epoch, target execution or sampling is claimed.** This is a new
package; the v1 plan, its review and the failed run03 evidence remain unchanged.
Main stays fixed at `fc300bc9fdc389b585cbef0630fc8915d53e89c5`.

## Why the contract changes, and what does not

Run03 exposed a real incompatibility between different binaries and the old
whole-raw-A-versus-B gate. Main fingerprints its own executable, puts that SHA
in the query-generation configuration and rejects a saved generation with a
different configuration. The two observed fixture snapshots differed only in
that producer field and derived checksum/content-address/CURRENT bytes. Their
semantic files and graph bodies were exact. The old gate correctly failed;
this plan does not rescore that run or call the producer field dispensable.

SETUP v5 is a separately prepared **fixed-Fixture** producer-aware gate. Even a
future actual successful v5 does not qualify these twelve workloads or provide
their query counts, owners, graph rows, result files or GHC interfaces. Its
exact final source, actual receipt, original/stats binaries, dependency and
runtime closures must first be independently accepted. Those bindings remain
null here. No v5 files or running work were read or changed for this package.

Keep the already reviewed inputs and exact twelve-cell order: baseline0;
flat_functions16/32/64/128/256; higher_order_chain16/32/64/128/256;
Foundation14. All25 source files and both endpoints' ordered input paths remain
unchanged. Declared module names and formula expectations come from the frozen
input specification. **Observed** owners, counts and outputs remain unknown.
Neither old475 nor the failed fixed-Fixture's1/78/87/172/140 inventories become
an expected count for any cell.

## Two distinct proofs

### 1. Actual original main versus actual stats binary

For each cell, authenticate both executing binaries against their own complete
accepted provenance: actual file contents, source commit/inventory, fresh Main
and selected producer object/link mapping, toolchain, libraries, loader and
package/builtin closure. A displayed version, claimed semantic identity or
copied digest is not a producer proof. Each process's configuration must contain
its **own** independently hashed binary SHA. Different SHA values are not
silently made equal; equal actual SHA values need not be artificially rejected.

The original main remains the independent semantic reference. Execute its
fresh compile once, retain its full checked pair, ordered query report and
query-publication tree, then perform show-crate and the existing three formula
controls for each executable shape. Foundation14 has no Main/runtime formula.
Metadata must match the input crate/dependency/declared-module contract, while
all actual fingerprints/query inventories are observed from this real output.
Read-only controls must leave the files unchanged.

Before either artifact becomes evidence, a separately reviewed generic decoder
must authenticate the whole original container, not merely extract a string:

* Exact MLFBIN schema/version/flags/header/sections/widths/counts, strict UTF8,
  canonical varints/padding/sharing and full bounded DAG/root/table validity.
* Independent CRC, full-generation SHA and content-addressed filename. CURRENT
  must be a complete supported pointer to that same real generation.
* Complete tag412 seven-field snapshot and the complete canonical five-part
  configuration. The crate ID, query format and checker version come from
  pinned source. The source/lowered flavor must be justified by the per-cell
  source route before admission, not permissively chosen after a failure.
* Every table, descriptor, row digest, payload location and read occurrence.
  Reads are **ordered lists with potentially legal repetitions**. Preserve all
  occurrences and order. Validate target/closure/cycle rules, but do not turn
  lists into sets, sort them or reject a repetition without a source rule.
* The set of distinct non-null payload locations must equal the entire actual
  results directory. Each content-addressed filename must hash its complete
  bytes. Multiple rows may share one payload. Missing, extra, stale, aliased or
  staging files are failures. Row/read multiplicity is not file multiplicity.

Archive the original cell, retaining original absolute-path correspondence.
Recreate the **same** empty active path, source/spec bytes and dependencies;
compile stats exactly once. Its whole container/SHA/CURRENT/provenance chain
must pass independently too. Then compare:

1. Full checked pair, complete ordered `.queries`, every result/lock/spec/source
   file and the complete semantic relative inventory, byte for byte.
2. All non-compiler configuration fields, every snapshot table/row/read/location,
   and the full node/root structure. No incidental field is dropped.
3. Every unchanged wire span. Locate the compiler-hash field structurally from
   canonical decoding; never reuse run03's fixed offsets or perform a global
   string replacement. Each producer field is checked against its own binary;
   each derived CRC, generation name and CURRENT pointer is separately checked.
   No other byte/field difference is allowed.

This is an explicit new producer-aware relation, not “raw equality after
normalization.” Do not construct patched containers, rewrite timestamps, strip
configuration, repair CRCs, or publish transformed files as original evidence.
If a larger cell reveals another difference, stop and review it rather than
broadening this relation or selecting a subset of its results.

### 2. Later same-stats-binary full-raw oracle

After **all twelve** actual reference controls, producer-aware comparisons and
GHC typed checks finish, an independent actual review must accept the complete
stage. Only then freeze each successful B tree as its per-cell future M oracle.
The oracle must include exact full file names and bytes: checked pair, query
report, all results/locks, generation file and CURRENT, together with original
active-path correspondence and exact binary/input/spec/dependency/runtime pins.
Its semantic authority is the original-main proof plus complete cross-producer
comparison; B is never its own independent correctness oracle.

Every later M leg uses this exact accepted B binary at the identical original
active path with empty target state and zero reuse. **No producer exception
remains:** the complete relative file inventory and every raw byte, including
config/CRC/CURRENT/generation filenames, must match the frozen B oracle.
Changed executable, input, dependency, package, runtime, path or output means
stop. Do not regenerate/rebase an oracle from a failed or measured sample.

Freshness metadata is retained for process/file ownership, not rewritten to
force byte equality. Artifact byte equality does not require equal filesystem
mtime/inode between fresh runs. No archived tree is mounted as a query root or
GHC import path, and no relocated embedded-path artifact is executed.

## Exact command, lifecycle and budget boundaries

The semantic ledger still has **91 commands**:12 original compiles,12 shows,
33 original formula observations,12 stats compiles,12 GHC typed calls and10
before/after loader-only resolutions. All argv, order, expected exit/output
oracles and per-child caps are unchanged. Only the explicitly named
cross-producer artifact relation changes; COMMANDS-v1-to-v2.patch records it.
No extra stats formula calls, relink, setup rebuild, warmup or retry is hidden.
Strict decoding/hashing/comparison is also charged to the same scope elapsed.

Original guard maximum600s and whole-call-through-return cleanup-inclusive
ceiling600e9ns remain. Child nominal caps sum1420s, not a permission to consume
that much. Derive one deadline from the outer call entry, freeze cleanup
headroom in the future adapter, shrink every child to the shared remainder and
stop on exhaustion. Completion feasibility is unproven.

Let E be the actual accepted SETUP WORK. The stats binary's fixed sink is
E/active/mlf.stats. Original and nested bounded_root must be exactly E, not all
R and not only E/semantic-qualification-01. The guard's containment rule makes
the narrower child-only root unable to contain the fixed sink. All old setup
bytes and retained archives count against E's footprint cap.

A bound is not a write ACL. Use an independently reviewed positive allowlist
for the new append-only scope, designated transient active cells/sink and an
explicit fresh temporary directory. Keep every prior static setup pin/receipt
unchanged. Use new current-boot admission/epoch/one-use claim with the same
global serial dual locks. Never reopen an old SETUP claim or rewrite a prior
scope. E/active already exists; create only missing authorized children. Create
commands/archive parents before guard-owned child outputs, not those outputs.

Command logs, RTS reports and guard/lifecycle receipts stay outside the semantic
cell payload. Stats sink follows absent→fresh report→original guard atomic
archive→absent. All12 stats plus12 GHC reports are compatibility evidence,
not samples. Only positive completed worker archives are pinned mid-stage;
outer/controller/watchdog/self receipts are authenticated after their writers
return, including cleanup/lease/lock and old-input rechecks.

## GHC boundary and the later48 legs

GHC uses exactly the same source operands, isolated authenticated private/global
packages, reset -i and the frozen typed-only flags. No extra Main, host source
root or producer object search root is added. Actual full Compiling events must
show each expected input module/path once and no hidden home dependency rebuild.
Retain complete raw logs and exact fresh nonempty `.hi` inventory, with no
objects/dynamic artifacts/executable. Do not substitute old81+wrapper rules.
The original successful GHC per-cell interfaces provide a same-tool raw oracle
for later G legs at the same paths; actual acceptance remains unknown now.

Timed endpoints remain **MLF frontend checked+published artifacts versus GHC
typed interfaces**. MLF includes additional checking, serialization, content
hashing and query publication work. GHC typing is not a runtime formula test,
there is no cross-compiler raw-byte oracle, and this is not GHC parity or native
program performance.

Preserve48 timed legs, M,G,G,M per cell, in two consecutive24-leg scopes.
First block nominal510s, second630s; each actual scope including cleanup≤600s,
exploration cumulative≤1200s, proposed post-setup semantic+exploration≤1800s.
All next-scope entry checks must fit a full600s. Later runtime/support command
ledgers are still unimplemented and must be explicit, separately counted and
charged within those same scopes before admission; no support run is a hidden
sample. Per-leg baseline15s, shape M30/G15 and Foundation M60/G30 caps remain.
The semantic Foundation M90 cap does not silently replace measurement M60.

Only two samples per endpoint per cell: retain both, use exploratory scaling/
order-of-magnitude language only. No stable wall gain, significance or asymptotic
proof. Near-resolution/zero denominators remain unknown. Qualification touches
OS caches; “fresh” means target-result state, not cold filesystem cache. Graph/
constraint counters remain unimplemented and unknown, never zero. Native fixed
point remains paused.

## What exists and what is still required

This package supplies the revised contract/ledger/flow, dynamic oracle slots,
codec and negative-test requirements, and a small **synthetic decoded-data
model**. Its44 model checks include legal duplicate reads, order/multiplicity
changes, result closure, malformed freshness types and exact later same-B raw
comparison. It is not a real MLFBIN decoder, trusted artifact verifier, execution
adapter or source/actual qualification gate. In particular it cannot tie model
dictionaries to real wire bytes or authenticate OS ownership/provenance.

Required before execution: accepted actual SETUP plus independent review;
independent review of this revised12cell relation; generic bounded decoder and
complete parser/adversarial tests with independent mutation review; reviewed
execution adapter and precise runtime/support/path/ownership/deadline ledger;
fresh resource/epoch admission. Then the actual91-command stage and independent
all-cell review must precede freezing dynamic oracles. Separately reviewed
sampling source/admission must precede any of48 legs. No plan or synthetic pass
fulfills any of those actual gates.
