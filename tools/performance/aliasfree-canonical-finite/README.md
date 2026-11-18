# Alias free canonicalization experiment

Baseline: fc300bc9fdc389b585cbef0630fc8915d53e89c5. Candidate: only unify's already-validated call site bypasses canonicalize when links skeleton is empty. Public canonicalize, checkedFirstOrder, rebind and both validateGraph calls are unchanged. No binder-fusion or memo candidate is stacked.

Hypothesis: avoid an entire O(V+E) node/tag rebuild when alias resolution is identity. This is not evidence that the fast path is frequent or dominant. Historical canonicalization attributed roughly342ms of21.9s in one instrumented run, so upside may be limited; no promise of GHC parity.

Finite gate: 33 exact original validation/error cases;160 paired unify cases across empty, self, merge and missing-node equations. Observe both result constructor and forced node/tag/binder/flag/link/next-id payload. Includes poison kind/name/next/link/binder fields, valid aliases, sparse identities, missing nodes and ordering cases. O0/O2 with pedantic bottoms and disabled state hack;612 sidecars must match. Existing bounded reachable alias cycle control is retained. These finite cases are not a general semantic proof.

Only after the actual gate passes and is audited: a single predeclared fresh-runner Foundation15 paired screen using the existing raw output, resource and cleanup gates, not repeated binder-fusion samples. Stop on semantic mismatch or original regression gates. Native fixed-point A/B remains paused. No merge authorized by qualification.
 Added review-driven dense/sparse poisoned leaf flags, competing nextId/flag poisons and lazy GCon payloads; passing source review is not semantic qualification.
