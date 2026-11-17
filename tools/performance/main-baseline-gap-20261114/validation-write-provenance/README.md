# Validation write provenance safety model

This research archive extends the [finite Haskell read observer](../validation-read-observer) with a source-level write/provenance audit and a separate symbolic Python protocol. One bounded model execution and independent offline audit matched all **24 frozen literal checks**, including four deliberately incorrect caches and two complete total-tree interval cases. This is not a compiler optimization, Graph.hs translation, Haskell demand proof, production qualification or performance result.

## What was learned

- A numeric merge winner is not necessarily the source of its fields. In Graph's ordered merge, binder/flag come from resolved operand `a`, while the lower identity wins. Alias entries that are unchanged can resolve differently after another merge.
- `canonicalize` rebuilds every surviving Node/tag expression. GCon child-list mapping remains lazy, and leaf Kind/name payloads can remain unforced. Pointer equality, equal numeric IDs and deep payload comparison do not provide a valid cross-graph certificate.
- Dense rebinding's unchanged branch retains the current canonical skeleton node, not the original input. Sparse intermediate raised binders belong to a different graph view, not the returned graph.
- In the finite protocol, copies transport exact field-origin cells; every assignment or deletion creates a new token even for equal values. Unknown writes, foreign owners and unsupported modes fail closed. Successful child facts neither certify a new parent edge nor publish a failed transaction.
- Omitting alias dependencies, omitting global binding dependencies, trusting the same ID, and trusting endpoint Node tokens each produce the specific stale answer recorded in `results.json`. Correct warm and fresh evaluations agree in those cases. Both use the same toy semantics, not an independent Graph implementation.

## A concrete remaining algorithm boundary

The current model deliberately gives rebuilt constructors fresh tokens and conservatively invalidates global binding facts. Applied indiscriminately across canonicalization/rebinding, this policy loses substantial reuse opportunity; it is not an optimization ready for a real shadow run.

The two total-tree controls distinguish relation meaning from Euler coordinates. Deleting an unrelated sibling changes interval `[5,9)` to `[4,8)` and a queried start from 8 to 7, yet dominance remains true. Moving a non-endpoint ancestor changes dominance from true to false while the query endpoints' own binders stay unchanged. Every interval, not only the Boolean, was independently recomputed by ancestor-path ordering and descendant cardinalities.

A possible next model would preserve a *particular dominance relation's* generation after recomputing its already-demanded Boolean in a complete, successful new prepass. This does not permit using old true without checking, skipping the prepass, suppressing incoming edge gates or changing an error prefix. The cost of replaying all relation queries, dependency propagation and retained payloads must be paid and measured. No finer relation-ticket reuse is implemented here.

## Evidence and limits

`model_validation_write.py`, `expected.json` and `results.json` are exact archived bytes. The expected values were frozen before execution. `AUDIT.json` is a sanitized independent audit; `PROVENANCE.md` covers graph-construction exits within `Graph.unify`, not every graph API; `RELATIONS.json` distinguishes unexecuted source-derived Graph witnesses from the two executed total-tree controls. `PINS.json` records content identities.

The model's edge rule checks kind **before** dominance, unlike production `denseChild`, which checks Gen/binder/dominance before kind. Its Poison controls are symbolic, not GHC bottom, exception or sharing equivalence. Real signed/sparse identities, dense/sparse dispatch, raw Patricia routing/counts, all Gen/structural validation, permission ordering and precise lazy production write capture remain unqualified. The existing sparse observer still delegates to the original validator and is unobserved.

No Haskell was compiled or executed in this batch. There was one model run, with empty stderr and exact type-sensitive JSON comparison. Resource configuration was 512 MiB address space, 20 CPU seconds, a 30-second alarm, 64 descriptors and 1 MiB per output file; this is not an OS sandbox or absolute full-process deadline proof. The original terminal confirmed success and release of the original locks; after a brief reconnect, the same boot/root and those locks were verified without rerunning the model.

For local inspection, `python3 model_validation_write.py` emits a RESULTS object. Compare its `checks` with `expected.json` using canonical JSON serialization so Boolean and integer values cannot compare equal accidentally. A RESULTS label alone is not a passed qualification.

Baseline: `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. Main and PR51 are not changed; no merge, real shadow, production reuse or native/fixed-point A/B is admitted. Earlier failures and stopped candidates remain unchanged. No speedup, allocation saving or profitable hit rate is established.
