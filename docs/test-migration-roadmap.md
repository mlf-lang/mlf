# Test migration and speed roadmap

Deliver all [15 suite subplans](test-migration-subplans.md) in one integration PR and two phases. Phase 1 ends with one integrated code cutover and zero test runs. Phase 2 begins with that revision, compares it with the original parent, and fixes the implementation until the complete migration passes. Merge after Phase 2.

## Phase 1 — Cut over all code in parallel

The lead records the exact baseline commit before the first migration edit. Keep it available in a separate checkout for Phase 2, including the legacy suites and workflows removed by the cutover. Read the [framework design](test-framework-integration-plan-20261023.md), [implementation checkpoint](test-framework-implementation-checkpoint-20261023.md), and [current catalog](../tests/test-catalog.json). Use source, manifests, workflow definitions and existing receipts to assign each maintained entry point to an owner. Mark dynamically generated counts for Phase 2 discovery.

Give subagents disjoint implementation areas. The lead owns shared interfaces, root manifests, the catalog, lockfile, workflow changes and final integration. Agree on case IDs, selection, adapter results and evidence fields before editing shared callers. Each agent supplies its registration changes to the lead. Assign exclusive ownership if a shared file needs a specialist.

| Subagent area | Phase 1 deliverable |
| --- | --- |
| TupleList, Core and library cases | Switch default dispatchers, port legacy assertions, preserve exact selection and partitions, and share repeated fixture compilation. |
| Figure 12, parity and direct language tests | Map paper labels, corpus rows and smoke cases to registry IDs. Preserve aliases, independent checkers and batched execution. |
| Backends, port and native runtime | Register matrix coordinates, IO traces, fixture and reference identities. Wire routine backend parity to the hosted compiler and retain native runtime and platform adapters. |
| Framework, harness and package management | Integrate framework self-tests and process outcomes. Preserve crash, cache, concurrent-write and fresh-install conditions. |
| Self-host, tooling, platform and release | Register bootstrap and release checks, including manual entry points. Keep pre-bootstrap adapters executable before MLF is available. |
| Benchmarks and performance gates | Register workload correctness and timing profiles. Preserve independent baselines, sample counts, optimization settings and timed boundaries. |

Implement test-code changes, adapters, updated defaults, removal of duplicate runners, and proposed speedups together. Ordinary hosted language and backend checks use GHC-hosted MLF at `-O0`. The same hosted compiler interprets fixtures and emits LLVM for Clang to link with the MLF runtime, GMP and BDWGC. Reserve the self-built compiler for self-host and release qualification. Keep targeted `-O2` tests where optimization or performance is the contract. [Hosted backend example](../tools/shared/test_symbol_prefix.py)

During this phase use static inspection and diff review. Defer suite execution, probes, executable discovery, timing runs and CI to Phase 2. Keep Phase 1 commits local when pushing would automatically start tests. Each owner hands off its code, old-to-new coverage map, compatibility changes, expected saving, exact verification commands and any unverified assumptions. The lead waits for every subagent, integrates all contributions, checks references and records the candidate commit. **Phase 1 is complete when every subplan is implemented and handed off. Its status is unverified.**

## Phase 2 — Run, compare, fix and qualify

1. **Establish the comparison.** Use the recorded parent and integrated candidate in separate build directories. Record host, compiler producer, tool versions, optimization, selection, parallelism and cache state. Run discovery on both revisions. Account for every case, generated family, alias, backend, platform and independent oracle using the agents' coverage maps.
2. **Find failures cheaply.** Build the affected tools, exercise selection and a small representative case through each adapter, then run affected suites. Check deliberate wrong results, failure exit codes, interruption, partial reports and cleanup. Assign failures to the owning agents. After each fix rerun its reproduction and affected suites; rerun dependent checks when shared code changes.
3. **Measure each optimization.** Compare the same parent and candidate workloads. Count repeated compilations, fixture builds and process launches as applicable. Separate setup from execution and identify cold versus warm cache. Repeat noisy focused measurements and report the spread. Historical [port timings](port-test-performance.md) and [artifact measurements](shared-test-artifacts.md) can guide investigation. Keep benchmark setup outside its sample window.
4. **Qualify the final revision.** Run the applicable [contributor validation](../CONTRIBUTING.md), root campaigns and [CI profiles](ci.md), including native self-host, required platforms and release rehearsals. During cutover compare hosted backend results with the legacy native baseline and independent expectations. Verify the final routine schedule runs ordinary hosted semantics once while retaining distinct interpreter/LLVM and platform coverage.
5. **Close the PR with evidence.** Record results for the final source revision and resolve failures or unexplained regressions before merge. Report total runner-minutes and time to the last required PR check separately. Include compilation and process counts where work was removed, and identify suites where the migration improved reporting but delivered no measurable speedup.

The completion record for each suite is its baseline and candidate IDs, coverage comparison, commands and outcomes, failures fixed, and measured cost. Mark any unavailable platform or unexecuted check as outstanding. The migration is complete when every subplan has this record and the integrated revision passes the required gates.
