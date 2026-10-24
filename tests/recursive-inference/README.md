# Focused recursive-inference discovery

`RecursiveInventoryDiscovery.emlf` inspects the actual retained Modules,
Separate, Readability and CoreSolver test-list spines and labels. It compares
these with the registry/catalog and verifies all 742 Core labels against the
preserved golden inventory, including unique stable IDs and partition totals.
It **does not execute** any test action, fixture program, LLVM/native campaign,
or security campaign.

Run from the repository root with the current compiler and each shared source
root except `host/ghc` on its `-i` search path, for example:

```sh
emlf $(jq -r '.source_roots[] | select(. != "host/ghc") | "-i " + .' shared-sources.json) \
  --run tests/recursive-inference/RecursiveInventoryDiscovery.emlf
```

The direct GHC `shared-frontend --recursive-inference` executable separately
executes the 53 focused source cases, finite-origin planner checks, and current
plus frozen target/evidence checks. The discovery harness does not substitute
for those checks or claim that all 742 Core actions have been executed.

`runtime/*.emlf` are three terminating host-interpreter checks. Run each with
`emlf --run FILE` and compare exact stdout with its `.stdout` sibling. They
exercise factorial, a mutual recursive knot, and explicit inferred dictionary
arguments over repeated recursive calls. They are separate from the 742-case
Core inventory and require no LLVM/GC/native compilation.
