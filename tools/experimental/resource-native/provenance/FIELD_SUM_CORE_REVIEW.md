# Independent v7 recursive sum-field / chosen-thunk core review

Accepted for bounded bridge integration only. Authoritative FINAL_CONTRACT.md SHA256 `f3ad74dc05e744c7200f0da766d9639e494bd5139abaea1aab221a9d90097ba1`; six-file implementation manifest SHA256 `e66da7f94b5985a6daebd0351eea19b9d9389f904259060d7f56ffaf7be65dfe`. No intermediate crossed proposal was implemented or accepted.

## New protocol, not the old no-allocation selection receipt

New v7 fields are ordered Int/Bool/registered SUM cursors only, at most32 fields/variant; no Unit/record/function/parameter field admission. Complete family registries resolve nominal recursion without recursive unfolding. Constructors validate exact arity/type/Down support and publish independent owning edges without forcing or consuming originals; construction HOLEs are allowed for later-filled knots.

The new case_fields_i64 factory validates every arm/code/capture/external owner before selected payload access/acquisition/allocation. Callback result is Int; field capture relation is down-only, never invented same/strict. Bounds are64 captures per arm, at most32 field plus32 external bindings, counting duplicates. Parent must be Down(authority), remain owned throughout publication, and every actual selected-variant payload slot must match canonical numeric position/name/shape and not be a raw HOLE, even when wildcard. Filled indirections/MEMO/BUSY/cycles stay lazy. This conservative construction barrier is not a global inference from parent readiness.

Only chosen fields get temporary owners in sorted callback-capture-name order; each duplicate binding gets a distinct owner. External originals stay live. Exactly one chosen whole-branch thunk is allocated and owns all selected captures before temporary handles/array are retired. Success records fresh thunk identity, captures and derived32-bit mask. Unselected code is checked but not allocated/executed. Existing raw Force markers remain individually bound; no event filtering hides new ownership or allocation cost.

I inspected checker, model, native descriptor/constructor/factory/Force guards and emitter. Position names use numeric declaration order (including10/31), while callback names sort lexically. Field masks use unsigned shifts; caller compound descriptor storage counts against512 pointer cells. Normal support follows child<=parent<=authority. This is bounded, not constant-time, not allocation-free, and not a hostile-C memory sandbox.

## Evidence

Author coherent gate76/76:11 normal IR,3 faults,36 checker negatives,48 commands/96 streams. Separate native helper gate55 commands and allocator/OOM gate12 commands: total115 gate commands/230 streams independently hash-verified with unchanged inputs. Native coverage includes malformed unselected code/captures, field arity/type/tag/position corruption, wildcard raw HOLE, filled ignored cycles, selected fields and external aliases. Old v6 nullary compatibility is only one finite control, not historical matrix restoration.

OOM witness wraps malloc/calloc/free and observes every requested runtime allocation through nine actual failpoints: constructor node/slots/owner (3), factory temp array/two field owners/new thunk node/slots/owner (6), plus two normal controls. I verified all raw observations against report's eight memory fields. Failure keeps original parent/external anchors; real partial slot publication/allocations remain recorded, no factory success/scalar result is emitted, poisoned snapshot/reentry/close preserve report and memory. No rollback, sweep or terminal leak-free claim. Observer storage, libc internals/RSS/stack are outside these requested-byte totals.

Independent8 fresh subprocess commands compile/run two scenarios under O0 and ASan+UBSan:32-field constructor, highest index31, duplicate field bindings or field/external alias, child group below parent group below factory authority. Both return74 with zero final live heap and exact model/native event equality. The actual parent group closes before first Force, while the child survives via chosen-thunk captures. Mask is2^31; duplicate temporary owners remain distinct. Independent same/below field-relation forgeries reject CAPTURE_RELATION; malformed unselected external rejects LAYOUT.

## Preserved failures and limitations

Initial native test compilation used a `boolean` identifier colliding with runtime JSON helper because the test intentionally includes exact runtime source for typed corruption probes. Only test identifier changed; runtime unchanged. Original diagnostic was tool output, not a captured artifact. Exact old test is preserved; a separately labeled NEW compile-only failure reproduction captures exit1/diagnostics honestly, not as the missing original stream. Passing gates are separate.

My first independent harness assumed the older flat manifest schema; it failed before any compile/run. Corrected harness reads this stage's explicit nested files map. Original script/stderr retained; no candidate change.

ASan+UBSan controls have no diagnostics; leak detection disabled for intentional terminal retention. This accepts the finite runtime protocol, not genuine Kind source provenance, arbitrary programs, fields outside the grammar, polymorphism/defaults/modules, full M1–M6, whole GC replacement, or performance. Fresh source qualification is still required.
