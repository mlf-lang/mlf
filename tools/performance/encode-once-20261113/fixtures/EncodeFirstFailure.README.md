# First-encoding failure supplement

Source-only, candidate-only fixture. **Not compiled or executed by its author.** It directly calls the candidate's `Bootstrap.CrateGraph.recordInputAndDerived`; the unchanged baseline does not export that helper. Build only this new Main against the authenticated candidate producer, using the same original host flags/packages and isolated output convention. It needs no extra package, arguments, environment mutation or output directory. It performs real in-memory encoding/hash IO but no file publication.

There are exactly two cases:

1. Both the frozen original two-`QueryGraph.record` protocol and the actual candidate helper must return `Left "binary constructor tag out of range"` for a negative constructor tag. Children, wanted key and session are independently poisoned. Any exception or demand of those poisoned fields fails the process. This exercises the first encoding's real `Left` branch, not an exception relabeled as a codec rejection.
2. A small finite value must give identical fully observed returned node, all session fields, old/current node rows, ordered reads, payload locations and pending payload bytes. Additional assertions require a nonpersistent Input plus persistent derived row, precisely one dependency edge, unchanged empty previous nodes and one queued digest.

The exact stdout is in `EncodeFirstFailure.expected`, including literal tab separators and final newline. Require exit zero and full byte equality; missing/truncated lines fail. No successful runtime output has been generated here.

The malformed raw `W.Value` is a public-helper error-protocol test, not evidence that admitted contract/declaration metadata or source text can produce a negative constructor tag. It does not test resource exhaustion, cancellation, transient second-encoding IO failure, or general partial-value equivalence. The existing 22-case fixture and frozen production source are untouched.
