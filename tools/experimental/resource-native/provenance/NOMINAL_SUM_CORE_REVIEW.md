# Independent v6 nominal-nullary-sum core review

Accepted for bounded source integration, not genuine-source qualification.

Exact implementation is bound by the author's six-file IMPLEMENTATION_MANIFEST.json (SHA256 `3c021a111e3f16d1caf85dd8910b6209ea926a13dc7f95648b87d292e1999c1d`). New IR identity resource-ir-nullary-sum/1, version6; appended native family table is a new ABI, not binary compatibility.

## Contract/source inspection

The finite registered family table supports an empty table or up to64 families with1–64 ordered nullary variants each. `%Family` static shape is separate from variant payload identity and intrinsic Bool. Checker validates all family references and exact exhaustive arm keys, owned Int capabilities, no authority alias/loans/tickets and Down support. Output is conservatively not ready, unknown identity and a fresh abstract Down group, never a fabricated physical group equality.

Native validation binds SUM shapes one-to-one to family descriptors, contiguous variant IDs, unique names/pointers, zero fields and exact backlinks before entry. Helpers authenticate family/variant pointers before payload use. Every SUM node allocation has SumNode storage, including holes/thunks/applications; ordinary rt_alloc cannot forge a READY sum. Ready-tag and expected-family checks cover Force/deferred/memo chains and callback returns before publication. These are defined runtime-helper guards, not a sandbox for hostile arbitrary C descriptor memory.

Case validates every ordered arm before event or consumption, transfers the selected exact owner, releases all other owners in declaration order, and does not Force/read arm payloads/retain/allocate. Codegen emits the exact declared order and binds the checked artifact digest. Model/native observations agree. Selection has one IR tick but bounded O(n²) alias validation and O(n) release work, n<=64; this is not a constant-cost or speed claim.

## Evidence inspected and independently executed

Author gate:130/130 checks,110 subprocess records and220 complete stream hashes verified. All input hashes match before/after/current bytes. Includes13 normal IR,3 terminal IR,28 checker negatives,1-/3-variant families, equal variant spelling across nominal families, deferred/filled-hole/closure family propagation, native malformed registrations/arm ownership/local return, cross-family callback/application returns and typed internal corruption probes (foreign memo/foreign READY/unregistered pointer). Negative probes reject before case/publication/Force-return as applicable. Internal corruption probes explicitly include the implementation and are tests, not public APIs.

Independent16 subprocess commands, all retained: three generated cases under O0 and ASan+UBSan (last-arm same-node distinct owners; unselected filled self-cycle; selected filled self-cycle BUSY), exact complete normal observations/terminal prefixes against independent model execution. Fresh native session tests in both profiles perform37 middle/last selections using same-node owners and different support groups. They assert exact selected handle, no allocation or acquisition across selection, exactly two owner releases; scalar then Unit clears result kind;39 completed entries close with zero live bytes/blocks. Wrong-family case with identical variant spellings faults INVARIANT, null result/no entries, then subsequent step and close preserve poison and exact retained memory. Independent checker wrong-family mutation rejects FAMILY.

ASan+UBSan had no diagnostics; leak detection is deliberately disabled because terminal poison has no cleanup promise. No independent malloc/free interposition was added in this stage; selection allocation statements are source inspection plus counter/snapshot controls.

## Exclusions

No field-bearing/recursive sum payloads, parameters, default branches, arbitrary case results, general source sums/modules, source compiler replacement, whole M1–M6 replay, full GC replacement or performance. Source must separately establish authentic complete DataEnv and checked branch authority. Core allows same constructor names in distinct families; source DataEnv's separate identity restrictions are not inferred from this core table. Fresh source acceptance remains required.
