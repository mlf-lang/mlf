# Private fresh-validator binder fusion candidate

Baseline main fc300bc9fdc389b585cbef0630fc8915d53e89c5; original Graph blob 380d29e7b951da022b49517237d74df2ecd3ee3a.

This candidate removes the separate descendant-loading list traversal by constructing the private descendant table after each successful binder existence check. It does not remove any binder check, Euler validation, structural edge check, canonical resolution or kind check, and adds no cache. Expected saving is traversal and binder dispatch, not a duplicate node lookup. Original public denseValidation/denseValidateEntries and all existing helpers remain byte-for-byte unchanged; only validateDense selects a new private fresh-allocation driver.

Root counting remains first. No descendant table is read by Euler traversal until every binder check passes; construction order remains ascending entries with prepended sibling lists. Failure discards the private ST state. Public malformed scratch state must continue using original helpers.

Finite gate compares the exact original and candidate real Graph at O0/O2 with 33 expected-result/ordered exception graph controls and 132 sidecars, plus bounded reachable alias-cycle smoke controls. These are finite semantic screens, not general proof or performance evidence. A paired same-runner Foundation15 ABBA workload is permitted only after the gate passes. Native A/B fixed point remains paused. No main merge or speedup claim.

Prior canonical-ID memo candidate STOP (9.1455% slower) is not reused or stacked; depth-cursor STOP also remains final. Preserve all prior evidence.
