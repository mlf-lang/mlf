# Proposed small ordinary Graph sample

Attempted once after independent code-generation review; preflight timed out
before any Graph process. No further run is authorized by this file. Any new
attempt needs a separate coordinator decision and a fresh output directory.

## Fixed scope

- Reuse the exact O2 `controls-probe` from successful F3 semantic gate 01. No
  compilation, relinking, producer construction, or new RTS flags.
- One outer 60-second resource scope includes authentication, all processes,
  and postchecks. Each child has an additional 15-second cap. Original memory,
  disk, outer sprint lock and frozen producer lock remain in force.
- Exactly 32 batches per process: 5,616 corpus inputs per batch, for 179,712
  public unifications. No calibration or adaptive repetition count.
- Two unsampled warm-ups, base then candidate. Then eight samples in fixed order:
  base, candidate, candidate, base, base, candidate, candidate, base.
- Every child uses the same executable and environment. Each batch varies graph
  identities using its runtime iteration index. The complete serialized graph or
  error is consumed into a character-code sum. This is a weak checksum with
  collisions, not raw graph-text equality or a cryptographic digest. The printed
  count/checksum bytes must match, and the operation count must be exactly 179,712.
  Exact graph/error parity is supported by the separate semantic controls, not
  established for every timed result by this weak checksum.
- A timeout, nonzero exit, stderr, changed pin or mismatch stops the attempt. Keep
  every produced sample and failure; no replacement or selective omission.

## Interpretation

This is a representative sample of the renamed dual-module Graph test harness,
not a production compiler. The separately built original-name owner evidence is
kept separate. Timing includes process startup, frozen-oracle corpus selection,
ID renaming, public unify, complete result serialization and checksum. It is not
pure-unify latency, compiler source-to-checked time, or native MLF performance.

The finite corpus reaches dense validation and nonempty successful rebindings.
Its per-batch frozen coverage inventory includes 1,433 successful rebinds and 16
graft-parent edges. It does not call normalize, so eight normal* read sites are
excluded. The other 46 changed sites are only a static reachable upper bound,
not proof every site was dynamically hit.

Preserve all eight wall/user/system values and peak child RSS. Report each
side's four wall values, median and candidate/base median ratio. Also compare
the geometric means and show the two ABBA-block candidate/base geometric ratios
as consistency checks. Ratios below 1 mean the candidate took less wall time. These descriptive summaries are
not a significance test and do not establish a whole-compiler speedup. Warm-ups
remain in the record but are not included in those means.

Allocation is not measured. The existing binary was linked with
`-rtsopts=ignoreAll`; this plan neither opens GHCRTS statistics nor recompiles a
stats harness. RSS is recorded as memory footprint, not allocated bytes.

## Recovery inputs

`sample.py` verifies the exact semantic scope, O0 and O2 receipt hashes, all
semantic source/object pins, the existing binary hash and producer identity.
It also pins both successful owner-codegen receipts, all their inputs/outputs,
exact equality of rebuilt baseline .o/.hi to the original anchor, and the
independent positive mechanism-review JSON. That file itself grants no execution
permission. The fixed ten process-log names are disjoint from scope and summary.
Raw semantic receipts and that binary remain local and were not published;
recovery on another machine must recreate and qualify them, not invent receipt
bytes matching hashes. No performance result exists for this plan yet.

The fixed invocation must include the outer lock and absolute paths, from the
F3 checkout. This is an invocation template, not permission to run:

```
flock -n "$MLF_SPRINT_LOCK" python3 -B "$F3_CHECKOUT/tools/performance/graph-read-fusion/sample.py" \
  --producer "$FROZEN_PRODUCER" --producer-source "$FROZEN_SOURCE" \
  --semantics "$F3_SEMANTIC_GATE" --codegen "$OWNER_CODEGEN_CAPTURE" \
  --mechanism "$MECHANISM_REVIEW_JSON" --output "$FRESH_SAMPLE_OUTPUT"
```


## Attempt 01 outcome

The one admitted attempt stopped at the outer 60-second wall guard (observed
60.740 seconds), before any Graph warm-up or sample process was launched. Both
lists were empty; no medians, ratios or performance result exist. The exact
preflight substage is unknown because only the initial worker record was saved.
The outer guard recorded no surviving descendants and both locks were free.
Full postflight pin checks were not reached. Six critical source and receipt
hashes were independently rechecked afterward, which is not a substitute for
those full checks. The original output remains intact; no retry or smaller-N
replacement was run.

`sample-01-summary.json` is the safe failure record. Raw command metadata and
receipts remain local and are not part of this public checkpoint.
