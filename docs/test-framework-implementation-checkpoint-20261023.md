# Test-framework implementation checkpoint

This is a staged, **unqualified implementation checkpoint**, not completion of
P0–P7. The frozen integration baseline is
`8a3e69b165765931c3ff762379a78db9659b2cd8`; the implementation branch started at
`2f8584423fa3055ca96d1479734357f742c9b3df`.

## What is implemented

- P0: source-role review for all 339 former review obligations, preserving the
  577 layered records, 170 families, 202 external paths, 90 tuple observations
  and 3,486 asset identities. This is **not** dynamic internal-assertion export.
- P1: typed descriptors, registry, outcomes, phase-specific expectations and
  plan-bound evidence assessment. Existing Case/Result constructors and v1
  reports remain supported. Actual Runner summaries validate exact planned IDs.
- P2: pure lifecycle, fixture, capability, resource, plan and diagnostic
  contracts; Process keeps v1 compatibility and adds typed outcomes and raw
  evidence digests. Its historical transport cannot attest complete descendant
  cleanup and therefore explicitly remains ineligible for v2 qualification.
  NativeProcess separately adapts the existing Async.Process ownership API.
- P3: 90 tuple/list recoverable Case leaves, plus an opt-in Core registry with
  739 original actions and 13 named substring observations. Tuple/list's frozen
  legacy implementation and Core's original campaign remain defaults pending
  executed equivalence. Core legacy IO actions execute one per supervised child;
  this avoids a fatal action silently swallowing the rest of the planned set.

There is exactly one selected implementation per invocation. No runtime/native
oracle, performance threshold, historical reference or default campaign was
removed. No real publication is reachable through the new test APIs.

## Opt-in entrypoints

After building matching candidate binaries, tuple/list supports:

    tuple-list --framework-list --format json
    tuple-list --framework --exact tuple-list/focused/unit-ast --format json

The original no-argument tuple/list command still runs the frozen legacy checks.
The separate tuple/list interpreter/native script remains unchanged.

Each Core binary supports:

    core-language --framework-list --format json
    core-language --framework --work-dir WORK --host-tool HOST --exact ID

`HOST` is the existing native measurement helper. Core's explicit child route
requires discovery or exactly one selected ID and an isolated supervisor work
directory. Its original coverage observations are retained in each child's
`legacy-coverage.jsonl`, never appended to a parent full-campaign receipt.

A v1 `scope: full` describes the **physical** registry, not the logical union of
Core partitions. Opt-in Core descriptors remain `qualification:ineligible`;
logical-partial tags and explicit v2 coverage intent prevent promotion to full
qualification. Preparation/cache hits do not earn test coverage.

## Safety and equivalence boundaries

The async incorrect-quantifier counterexample is deliberately compile-accepted
by the original demonstration. It may be compiled/typechecked and inspected,
never interpreted or executed natively. Compile-only restrictions in plans
propagate through dependencies and still permit actual typecheck test cases.

Static preservation checks compare original tuple/list predicates and Core
family/label bindings to frozen Git bytes, not regenerated candidate goldens.
They are useful mutation controls, **not proofs of language semantics**.
Neither the known package cache invalidation assertion nor regex-redux
performance criteria are relaxed by this migration.

## Validation commands

These commands are lightweight source/contract audits only:

    python3 tools/testing/migration_inventory.py
    python3 tools/testing/test_migration_inventory.py
    python3 tools/testing/check_tuple_list_migration.py
    python3 tools/testing/check_core_leaf_migration.py
    python3 tools/testing/check_manifest_snapshot.py
    python3 tools/testing/check_manifest_snapshot.py --manifest tests/mlf-package.json --graph-only
    python3 tools/testing/test_manifest_snapshot.py
    git diff --check

The local-source snapshot tool reproduces Package.Manifest's documented local
source graph contract and checks direct imports lexically. It reproduced the
frozen lock bytes exactly before refreshing the changed root graph. It is not
the native parser or `mlfpkg --locked plan`; non-local dependencies fail closed.

New MLF contract/lifecycle fault-control sources must themselves be compiled and
executed before being counted as passing tests. At this checkpoint the cloud
host has no native MLF seed or Clang, and no BDWGC development pkg-config package.
No dependencies were installed. Native compilation and semantic execution are
unverified. Complete campaigns, bootstrap/fixed-point, Windows qualification,
benchmarks and remote full-workflow dispatch were not run.

## What remains before completion

P0 dynamic/internal leaf exports, P3 Harness and full Core typed conversion,
P4 native/async/package scenario integration, P5 campaign/differential/self-host
integration, P6 SDK/performance/CI profile ownership and P7 legacy retirement
remain open. All required exact-source/platform equivalence and qualification
must pass before activation/retirement or any claim that all tests migrated.
