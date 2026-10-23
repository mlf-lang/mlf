# Independent lock-file audit

Scope: the root local-source package graph in `mlf-integrated`, after the guards and tuple/list inputs were combined. This is a static audit of the lock snapshot, not a native `mlfpkg --locked plan`, compiler validation, or test run. The available SDK manager cannot start because its linked `libgmp.10.dylib` is absent; this review installs nothing and changes no environment or worktree code.

## Source contract reviewed

- `libraries/mlf-package-core/Package/Manifest.emlf:visitWith` sorts dependency names, visits dependencies recursively, deduplicates canonical manifest paths, and appends the current package after its children. Dependency cycles, duplicate package identities and dependency-name mismatches are rejected.
- `sourceFiles` includes every library module and every executable/test target that has a `main`, including its entry source and private modules. It canonicalizes local paths, rejects paths escaping the package, sorts and deduplicates source paths. Command-only tests do not add source paths.
- `snapshot` records raw-file SHA-256 for each manifest and source, package name/version, and root-relative package path. The root package path is `.`. The current root closure contains local-source dependencies only.
- `Package.Json.render` recursively sorts object keys while preserving array order. `Json.write` appends exactly one newline. For this tree's ordinary ASCII paths and values, compact sorted JSON with `ensure_ascii=False` reproduces the bytes. This is a narrow correspondence for the observed inputs, not a claim that a generic Python JSON renderer implements every MLF string escaping case.

## Independent method and result

`independent_lock_audit.py` independently walks the actual merged manifests. It does not take package/source membership from the lock being checked and never writes that lock. It checks duplicate JSON keys, canonical path boundaries, the package graph, target dependency membership, source module headers and ordinary import declarations, then compares both the complete snapshot structure and canonical bytes. It also rereads all inputs to detect changes during the audit.

The initial merged-source audit passed:

- HEAD at observation: `2e394ff375ec3ca86df58a1ad12f27d73122cd66` (the working tree already contained the combined #12 inputs).
- 11 packages/manifests, 37 dependency edges, 80 source hashes.
- Source counts in package order: foundation 12, language-core 4, frontend 9, xmlf 6, inference 8, llvm 9, crates 7, package-core 8, developer-tools 2, interpreter 2, root compiler 13.
- Complete package/source sets, order, all manifest/source hashes, and serialized bytes match.
- Lock SHA-256: `2b45bb8ce32058d971a93ae92526c42ab647b46500f6f8c73ec4b02d5e8ba9bd`.
- No source/manifest input changed during the audit.

Evidence: `independent-lock-audit.json` contains every input path/hash and graph edge. The audit covers the actual merged frontend Parser/Layout, report runner source, and TupleList entry source included by the root manifests. It correctly does not invent coverage for native/runtime inputs, command scripts, or independently loaded suite manifests that are outside the root snapshot contract.

The primary agent's `regenerate-lock.py` was also read. Its dependency order, source union, SHA-256 and compact sorted serialization match the reviewed source contract for this local graph. The primary agent reports exact byte replay against main and all four original PR lockfiles; that is a separate replay check from this independent current-tree audit.

## Limitations and finalization

- Module/import checks are lexical checks of normal declarations, not execution of the MLF parser or a proof of source-language validity.
- No compiler, package manager, native test, campaign, benchmark or CI job was run by this reviewer.
- Final audit was rerun against code handoff commit `8a3e69b165765931c3ff762379a78db9659b2cd8`, after #16 was merged. The worktree was clean at this observation. All 11 package/manifests, 37 graph edges and 80 source hashes still match; structural and canonical-byte comparisons pass, the lock SHA-256 remains `2b45bb8ce32058d971a93ae92526c42ab647b46500f6f8c73ec4b02d5e8ba9bd`, and no audited input changed during the read. `independent-lock-audit.json` records this final code HEAD and complete input inventory.
