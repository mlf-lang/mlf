# Finite Haskell validation read observer

This archive is an **O2-only, GHC-only finite observation experiment**, not a validation cache, production patch, complete dependency certificate or performance result. The original `Bootstrap.Graph` at baseline `fc300bc9fdc389b585cbef0630fc8915d53e89c5` remains unchanged and is the oracle in the same executable.

## Actual result

The one controlled finite execution and its independent actual audit passed: **14 cases, all 71 sidecars, and the deliberately wrong mutant distinguished**. All five child steps exited successfully. The exact fixture marker is 67 bytes with empty fixture stderr. The build retained 17 GHC warnings (one GHC-68441 and sixteen GHC-39567), not errors; private full compiler logs are not copied into this archive.

The exact original stdout is retained in `results.json`. All 71 finite sidecar files are preserved there as UTF-8 text with their original byte counts and SHA-256 values. These are manually constructed small inputs, not captured real-program graphs. A/C files are complete validator outcome strings, not raw Graph serializations.

Each of 14 original/observed outcomes must equal its hand-authored literal, and each result file must be `PASS\n`. The intentionally wrong mutant must return `Right\n` on the cached-kind edge witness, whereas both correct paths return `Left ill-dominated type graph\n`. This demonstrates why a successful child-kind check cannot replace the later parent-dependent edge gate.

The retained trace also checks alias 10 present followed by canonical 1 absent, successful kind(2) at line 54 before the later edge failure at line 80, and the sparse path's exact `sparse:unobserved` marker. The v2 root-tag token occurs in ten returned traces; containment visits structural-tag/children at nodes 1 then 2. These are selector-location events, not proof of nested payload demand. Other event streams are preserved, not invented independent goldens. Typed Probe outcomes use an explicit unavailable-trace marker rather than pretending an interrupted report is complete.

## Source and history

- `Prototype/ValidationReadObserver.hs`: exact v2 observer; fresh bounded runST log state, no unsafe global cache.
- `Prototype/ValidationReadObserverMutant.hs`: exact intentionally invalid negative control. **Do not adopt it.**
- `Main.hs`: exact finite factories, original Graph oracle, literal/error/Probe and mutant assertions.
- `mechanical-dense.patch`: exact comparison of 19 selected original dense functions with observer functions. It is a review aid, **not an applyable whole-file production patch**.
- `v1-to-v2.patch`: exact two-selector-token repair to the observer.
- `fixture-contract.json`: frozen pre-execution source contract; its `executed: false` records when that contract was written. Actual evidence is separate in `results.json`.
- `results.json`: complete finite evidence and sanitized execution facts.
- `PINS.json`: exact source, baseline, fixture executable and independent-review identities. No executable is included.

V1 was an unexecuted draft. Static review identified missing explicit root-tag and structural DFS tag/children tokens. V2 adds those fixed location tokens at their existing selector boundaries, with no extra payload serialization. The same wrappers are present in the mutant; its intentionally wrong cache shortcut remains the distinguishing difference. No earlier actual failure is reclassified.

## Demand and semantic boundaries

The tests include unused boxed Kind, constructor name and nextId payloads; a demanded Arrow argument Kind; an earlier Gen/root/binder error masking later poison; alias presence/absence; missing child; occurs failure; binder containment; and sparse pass-through. Only the dedicated Probe exception type is caught. Unexpected exceptions, a cap breach, mismatched outcome, missing output or wrong mutant result stop the gate.

A selector token records a field location or conservative rule scope, not proof that its payload was forced. In particular, a successful Kind result is only Either-Right WHNF. Node existence does not certify Tag dependence. Euler/binding-tree dependence remains a conservative global token; equal intervals are not cross-graph certificates. No complete write log, subfact invalidation engine or replay is implemented.

The observer copies the dense path and delegates the sparse path to the unchanged sparse validator without observing its internals. Arbitrary public DenseValidation states or aliased arrays are not replaced. Different NOINLINE factory salts do not prove heap-disjoint input objects or complete Haskell demand equivalence.

## Execution boundary

One fresh executable was built with GHC 9.14.1, `-O2 -j1 -fpedantic-bottoms -fno-state-hack`; 16 home modules, two fresh C objects and the unchanged runtime boundary. No O0 comparison was performed. The fixed finite gate retained 120-second aggregate compilation, 15-second fixture, 180-second whole and 4-GiB address-space caps. These are resource bounds, **not timing or allocation measurements**.

There was no ordinary compiler workload, production optimization, real-program shadow, native-backend/fixed-point qualification or extra sample in this archive. The experiment executes the finite Haskell fixture, not the user's compiled application. Native work remains paused; main and the user PR are unchanged.

The next step is not automatic. Full field/per-edge dependency obligations, complete transformation/write coverage, ordered-error and partial-value semantics, and the cost of first construction/invalidation/replay/retention would need separate source and finite qualification before considering any real shadow. This result alone does not admit one.
