# Canonical resolver memo paired screen

Research-only candidate from finite gate227f4988, based on exact main fc300bc9.
Do not launch until finite gate44215699042 has passed and actual artifacts audited.
Source transformer identical to the finite test: single-invocation canonical-ID
memo, original public DenseValidation and helper semantics preserved, full gates.

Fresh isolated official GHC9.14.1 runner; A unchanged main, C same main with exact
pinned transformer applied only to Bootstrap.Graph. Fresh outputs and shared
seed-installed builtin for both producers. Preflight checks reject malformed,
wrong-stage, wrong-owner or reused evidence. Complete CI/CO/query bytes and all
1653 query result filenames/bytes must match on every call. No normalization.

Unchanged fixed sequence: seed A, qualification A,C, then A1,C1,C2,A2. Only last
four observations are performance samples. Runtime wall includes candidate memo
cost; peak RSS is process peak, not allocation bytes or tree sum. OS cache is not
flushed. Two-pair geometric ratio is descriptive screening only, not broad speed
proof or GHC parity. Stop if geometric wall ratio>1 or either pair wall>1.03 or
RSS>1.05. Native A/B fixed point remains paused. No production merge.
