# Main frontend SETUP v5: explicit cross-compiler publication contract

DISABLED source only. `READY=False`, new fixed work scope `main-gap-setup-run04`.
No run04, active copy, admission, epoch, claim, loader, compiler, guard, lock or
new target is created/executed by this preparation. Old source packages and
failed runs01–03 stay untouched. This is an explicitly authorized correction
batch, not an automatic retry or a retroactive PASS for run03.

## Why the qualification contract changes

Run03 completed29 nested children and6 RTS reports, including the private unit,
fresh stats relink and five CLI controls. Both Fixture compiles returned0, but
v4's full raw equality check failed. The independent actual failure review
preserves that failure and complete cleanup (33,108,900,562 ns).

Main's production CrateSession hashes its own executable. CrateGraph packs that
SHA into configuration field2 (index1). QueryGraph includes the configuration in
its generation, then derives a content-addressed filename and CURRENT. The
ordinary producer and stats-relinked binary deliberately have different bytes.
They therefore cannot satisfy cross-compiler generation/CURRENT byte equality.
Actual diagnosis found89 files each,87 identical, with only CURRENT and two
individual content-addressed generation paths different. Generation bytes differ
only in the actual compiler-SHA field and its CRC. Source/spec bytes and original
input paths match; changed file timestamps are not the cause. The old predicate
remains false. Its failure is not reclassified as success.

`QUALIFICATION.json` now explicitly names a DIFFERENT cross-compiler contract.
Production code, executable hashing, cache identity and invalidation are not
modified. No result is rewritten, stripped, normalized or globally substituted.
The predecessor's rule requiring all semantic artifacts to match still applies.

## Exact new pure oracle

`publication_oracle.py` accepts complete byte maps and separately authenticated
actual executable SHAs from the precise ordinary/stats invocation identities.
It never opens files, runs code, changes artifacts or modifies caches.

* Fully consume each schema6 generation and CURRENT container: magic, version,
  flags, schema, header/section sizes, limits, canonical widths and varints,
  strict UTF8, unique symbols and nodes, backward references, edge/root counts,
  zero padding, no trailing bytes, canonical reachable postorder and first-use
  symbol order. CRC32 uses the format-prescribed zero checksum field only during
  checksum calculation, not normalization of accepted artifacts.
* The unique root must be typed node412 with exactly7 fields. Locate its config
  text through that node, not byte search. Require the exact five packed fields:
  `compiler-shapes/builtin`, actual executable SHA, `MLF-SOURCE-CRATE-QUERY-7`,
  `open-fragment-checker-1/finish-receipt-1`, `source`. Reject any other incoming
  reference to the config text node, so changing it cannot change a hidden alias.
* Decode every snapshot dictionary/group/evidence/entry/location. Verify valid
  descriptor indices, known tag/arity, unique entries, ordered reads including duplicates, complete
  acyclic query dependency closure and payload=digest. The complete results
  directory must equal the referenced payload set, not its intersection.
  Each result filename must equal the full raw content SHA; fully decode each
  schema6 result container. Checked/interface containers are also structurally
  decoded with exact schemas3/4/8; their full raw bytes remain equal. Public
  show-crate ownership/meaning checks remain separately required below.
* Require CURRENT's single text root to equal the actual full generation SHA,
  which must equal its filename. Exact whole fixture inventory consists only of
  the original9 static files, CURRENT, one own generation, and precisely all
  referenced results. Missing/extra/stale/unknown files fail. Lock files are empty.
* Compare every nonpublication file byte-for-byte, including Fixture/spec,
  .mlfci/.mlfco/.queries, builtin pair, lock files and every result payload.
  Generation nodes/roots and all other symbols are exact. Only the structurally
  located64 ASCII compiler-SHA bytes and CRC field76:80 may differ. All remaining
  raw generation bytes, including framing and header fields, are identical.
  CURRENT has identical shape/framing and differs only in its independently
  derived64-byte generation digest and CRC. Generation names may differ only by
  those authenticated SHA values. No broad field exclusion is used.

The container limits retain the production maximum256 MiB,4,194,304 nodes,
16,777,216 edges and1,048,576 symbols; constructor tags are at most2,147,483,647.
Single/total symbol bytes are at most16,777,216/134,217,728. Per-node depth is
at most16,384, expanded node work and aggregate root work at most67,108,864.
Backward-node dynamic summaries count every repeated occurrence without
expanding the Value tree. Query dependency longest paths are at most4096.
The four typed identity tables and reconstructed descriptor keys have separate
67,108,864-character budgets, including decimal-length framing for packed names.
Evidence goals must be nonempty. Group member order and repeated read order are
preserved, not sorted or deduplicated. This small fixture oracle additionally
rejects an aggregate above256 MiB or more than4096 files, never expanding the
original guard's4 GiB footprint allowance. Parsing is iterative over the encoded
DAG, not expanded Value trees; list reads are checked against remaining section
bytes/counts before allocation. Unsupported structure fails closed. Its STATIC inventory and node412 config contract apply only to fixed Fixture;
future12cells need their own explicit general contract. It is a
narrow setup qualification oracle, not a replacement production parser, runtime equivalence proof, or a general
12-cell qualification oracle.

The positive actual run03 pair can pass this NEW pure predicate while its old
SETUP qualification remains failed. For any later comparison using the same
stats executable, the entire raw map must be exactly identical to that binary's
own independent qualification reference. No compiler-identity exception applies
to same-binary timing samples. Future12cells/48legs still need separate semantic
qualification and are not executed or qualified here.

## Unchanged single bounded SETUP

All main source stays at authenticated commit
`fc300bc9fdc389b585cbef0630fc8915d53e89c5`; no F25 qualification is inherited.
The private package correction, exclusive commands-parent creation and positive
worker output ownership fixes from v4 stay unchanged. COMMANDS bytes are exact.
There are exactly40 nested children:13 preparation payloads,11 qualification
commands,16 bounded runtime queries. Exactly9 genuine RTS reports are required
(8 MLF,1 GHC). Controls are not performance samples or future workload warmup.

One stage only: original immutable outer guard600 s and independent
600,000,000,000 ns full guard-call-return ceiling, including cleanup. Each child
cap shrinks to shared remainder. No retry, expanded cap, changed samples or hidden
command is added. All input/source/runtime pins, both actual shared/main locks,
current-boot fresh epoch, resource observation, one-use preparation/claim,
complete child receipts, RTS sink archival, final outer receipt and cleanup
checks remain unchanged. Historical completed baseline BUILD/CONTROLS may be
from an earlier boot only with all original trustworthy pins/cleanup intact;
new SETUP always requires actual current-boot admission/runtime. No history is
rewritten or historical lease assumed absent.

The actual qualified main producer must still pass its maintained authentication,
full source/tool/object/interface closure and fresh canonical whole-file builtin
verification. Fresh original Emlf Main is compiled once and linked with exactly94
same-producer non-Main objects and2 C objects. Never borrow the producer's last
Main.o, native runtime or generation outputs. Four private host modules and six
actual package IDs are bounded setup commands; global DB remains read-only.

All five original CLI argv/exit/byte oracles remain unchanged, including the
negative type-rejection exit1. Ordinary Fixture and builtin are shown first;
all artifacts are archived; identical source/spec paths are recreated with empty
queries/no builtin pair; stats compiles freshly1 group/0 reuse. The new pure
cross-compiler comparison runs at that original comparison point. Both stats
show-crate outputs must still equal the original raw outputs and ownership.
GHC's fixed SetupCheck must still produce only its .hi and a complete RTS report,
without dependency recompilation, object/link or native work.

The external stats parser remains the exact independently reviewed file at
`dense-direct-capture-r24-source/implementation/stats.py`, not a main-maintained
parser. Its accepted format/finite/unique-field/serial-GC scope is unchanged.
No statistics here are cost attribution, future GHC parity, scaling evidence,
Foundation compiler share or stable wall improvement.

## Review, activation and sole operational entry

The complete new source review must have schema `main-gap-setup-source-review-v1`,
`complete=true`, `source_gate_passed=true`, `blockers=[]` and the full pin of this
exact package MANIFEST. It does not exist at source freeze. CONFIG binds the
actual completed main BUILD/CONTROLS review identities, but this is not SETUP
qualification. ANCESTRY pins the actual failed predecessor and independent cause
reports; their outcomes do not authorize execution by themselves.

Only after full review may the coordinator make the fixed new WORK and copy
`controller.py` to `controller.disabled.py`; the executable copy changes only the
unique `\nREADY = False\n` to `\nREADY = True\n`. The actual enabled copy then gets
its independent mechanical review before a new resource/lock/epoch admission.
No other source byte or pin is guessed or filled during activation.

Future command templates, not commands to execute during source review:

```
/usr/bin/python3.13 -B WORK/controller.py prepare SETUP \
  --source-review ACTUAL_SOURCE_REVIEW --source-review-sha256 ACTUAL_SHA \
  --build-review ACTUAL_MAIN_BUILD_REVIEW --build-review-sha256 ACTUAL_SHA \
  --controls-review ACTUAL_MAIN_CONTROLS_REVIEW --controls-review-sha256 ACTUAL_SHA
/usr/bin/python3.13 -B WORK/controller.py run SETUP \
  --admission WORK/coordination/SETUP-admission.json --sha256 ACTUAL_ADMISSION_SHA
```

Only the controller `run SETUP` entry invokes the immutable outer guard. Do not
run an inner watchdog, `_setup`, payload, runtime loader or budget argv directly.
No valid envelope, incomplete/failed stage, excessive duration, changed input,
unexpected output or uncertain cleanup means stop and retain evidence. Even a
successful execution keeps stop_required true until independent actual review.
