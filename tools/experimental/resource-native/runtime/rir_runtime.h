#ifndef RIR_RUNTIME_H
#define RIR_RUNTIME_H
/* Bounded, sequential Repeat-only checked-IR target. Not a C memory-safety sandbox. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct RtContext RtContext;
typedef struct RtHandle RtHandle;
typedef struct RtGroup RtGroup;
typedef struct RtNode RtNode;
/* Typed caller storage. All members are runtime-private: generated C may only
 * zero-initialize a local array and pass a cell address to an _into helper.
 * Never copy owning structs or return a local pointer directly. */
typedef enum { RT_STORAGE_DEAD=0, RT_STORAGE_HEAP=1, RT_STORAGE_LOCAL=2 } RtStorageKind;
struct RtHandle {
    uint64_t id, scope, loans;
    RtGroup *group;
    RtNode *node;
    RtHandle *anchor, *previous, *next;
    unsigned role;
    int home;
    RtStorageKind storage_kind;
};
#define RT_STACK_HANDLE_BUDGET_BYTES 128
_Static_assert(sizeof(RtHandle)<=RT_STACK_HANDLE_BUDGET_BYTES,"unsupported handle storage ABI size");

typedef struct RtShape RtShape;
typedef struct RtCode RtCode;
typedef RtHandle *(*RtBody)(RtContext *, RtHandle *home, RtHandle **captures, RtHandle *argument);
typedef void (*RtEntry)(RtContext *);
typedef struct { const char *name; const RtShape *shape; } RtField;
typedef enum { RT_DATA = 0, RT_REPEAT = 1, RT_ONCE_UNSUPPORTED = 2,
               RT_I64 = 3, RT_BOOL = 4, RT_SUM = 5 } RtShapeKind;
typedef enum { RT_PRIM_ADD_INT=8, RT_PRIM_SUB_INT=9, RT_PRIM_EQ_INT=10,
               RT_PRIM_LT_INT=11, RT_PRIM_MUL_INT=14 } RtScalarPrimitive;
struct RtShape {
    const char *name;
    RtShapeKind kind;
    size_t field_count;
    const RtField *fields; /* sorted checked field names; DATA only */
    const RtShape *argument, *result; /* REPEAT only */
};
/* Closed nominal families. Positional field vectors are declaration ordered. */
#define RT_MAX_SUM_FAMILIES 64
#define RT_MAX_SUM_VARIANTS 64
#define RT_MAX_SUM_FIELDS 32
#define RT_MAX_FACTORY_CAPTURES 64
#define RT_MAX_FACTORY_FIELD_CAPTURES 32
#define RT_MAX_FACTORY_EXTERNAL_CAPTURES 32
typedef struct RtVariant {
    const char *name;
    const RtShape *family;
    size_t index, field_count;
    const RtField *fields; /* canonical decimal position names; i64/Bool/SUM only */
} RtVariant;
typedef struct RtFamily {
    const RtShape *shape;
    size_t variant_count;
    const RtVariant *const *variants; /* declaration order, indices 0..n-1 */
} RtFamily;
typedef struct { const RtVariant *variant; RtHandle *value; } RtCaseArm;
typedef enum { RT_FACTORY_FIELD=1, RT_FACTORY_EXTERNAL=2 } RtFactoryCaptureKind;
typedef struct {
    const char *name;
    RtFactoryCaptureKind kind;
    size_t field_index;
    RtHandle *external;
} RtFactoryCapture;
typedef struct {
    const RtVariant *variant;
    const RtCode *code;
    size_t capture_count;
    const RtFactoryCapture *captures;
} RtFactoryArm;
typedef enum { RT_FUNCTION = 1, RT_THUNK = 2 } RtCodeKind;
struct RtCode {
    const char *name;
    RtCodeKind kind;
    const RtShape *shape; /* closure shape for FUNCTION, result shape for THUNK */
    size_t capture_count;
    const RtField *captures; /* sorted checked capture names */
    RtBody body;
    int result_identity_argument; /* checked body property, FUNCTION only */
};
typedef struct {
    const char *artifact_sha256;
    size_t shape_count;
    const RtShape *const *shapes;
    size_t code_count;
    const RtCode *const *codes;
    size_t static_descriptor_bytes; /* codegen estimate, separate from runtime heap */
    size_t family_count;
    const RtFamily *const *families; /* closed family ABI; empty table is 0,NULL */
} RtProgram;
typedef struct { uint64_t fuel, event_limit; } RtOptions;
#define RT_MAX_FORCE_DEPTH 128
#define RT_MAX_ACTIVATION_DEPTH 128
#define RT_MEMORY_CATEGORIES 7
#define RT_RC_CATEGORIES 5
typedef struct {
    uint64_t allocated_bytes, freed_bytes, live_bytes, peak_bytes;
    uint64_t allocations, frees, live_blocks, peak_blocks;
} RtMemory;
typedef struct {
    const char *status, *fault; /* "complete" or "fault"; no fault cleanup promise */
    RtMemory memory, categories[RT_MEMORY_CATEGORIES];
    uint64_t rc_inc[RT_RC_CATEGORIES], rc_dec[RT_RC_CATEGORIES];
    uint64_t steps, groups_allocated, groups_closed, nodes_allocated, nodes_freed;
    uint64_t peak_groups, peak_nodes, peak_owner_handles;
    uint64_t owner_handle_acquisitions, owner_handle_releases;
    uint64_t loan_handle_acquisitions, loan_handle_releases;
    uint64_t force_calls, max_force_depth, callback_calls, ordinary_calls;
    uint64_t applications_allocated, raw_deferred_returns, memo_writes;
    uint64_t internal_memo_slots, cross_group_memo_slots, memo_fast_paths;
    uint64_t groups_closed_during_force, borrowed_slot_publications;
    uint64_t ir_retain_ops, ir_drop_ops, ir_borrow_ops, ir_end_borrow_ops, ir_application_borrow_ops;
    uint64_t events_emitted, events_omitted, max_activation_depth;
    uint64_t entries_completed;
    unsigned scalar_result_kind; /* 0=Unit/no result, RT_I64 or RT_BOOL */
    int64_t scalar_result;
} RtReport;

/* Emits one JSON object, streaming bounded events (no history allocation), then
 * full report. output may be NULL for silent handtests. report may be NULL.
 * Successful return=0, terminal fault=2. No malloc-ledger sweep on failure.
 * Program/descriptors/strings must have immutable static lifetime. */
int rt_run(const RtProgram *, RtEntry, const RtOptions *, FILE *output, RtReport *report);

/* Persistent DIAGNOSTIC session; sequential/nonreentrant, program immutable.
 * Open requires *session=NULL and allocates one context (never overwrites one).
 * Step reuses it and verifies context-only storage
 * after each unchanged entry. Reports are cumulative, including real live context.
 * Each entry gets its own fuel budget; semantic IDs/totals never reset.
 * Fault poisons session: subsequent step/close rejects before accessing stale
 * activation pointers. Fault close does NOT reclaim or null the session.
 * Success close snapshots final counters, frees context, then NULLs *session.
 * snapshot is an observation, not a cleanup/checkpoint operation. No API emits
 * JSON; rt_run_repeat below is the bounded-event convenience wrapper. */
int rt_session_open(const RtProgram *, const RtOptions *, RtContext **session, RtReport *report);
int rt_session_step(RtContext *, RtEntry, RtReport *report);
int rt_session_snapshot(const RtContext *, RtReport *report);
int rt_session_close(RtContext **session, RtReport *report);
int rt_run_repeat(const RtProgram *, RtEntry, const RtOptions *, uint64_t repetitions,
                  FILE *output, RtReport *report);

#define RT_LIFECYCLE_ID "resource-ir-terminal-destroy/1"
typedef enum {
    RT_DESTROY_DONE=1, RT_DESTROY_EMPTY=2, RT_DESTROY_ACTIVE=3, RT_DESTROY_INVALID=4
} RtDestroyStatus;
typedef struct {
    RtDestroyStatus status;
    uint64_t retired_blocks, retired_bytes;
    uint64_t category_blocks[RT_MEMORY_CATEGORIES];
    uint64_t category_bytes[RT_MEMORY_CATEGORIES];
    unsigned totals_overflow;
} RtDestroyReport;
/* TERMINAL WHOLE-DOMAIN SURRENDER, not ordinary close or language unwinding.
 * Outer open/step/close must have returned; exclusive authority and no remaining
 * callback/thread/foreign access. ALL aliases/handles/loans become invalid.
 * Caller slot and output storage must be valid, disjoint and outside the domain.
 * Headers are trusted private allocator metadata; forged pointers, corrupted
 * headers, manual frees and asynchronous/reentrant allocator access are excluded.
 * No finalizers or external-resource obligations may inhabit this domain.
 * Required receipt, optional original report snapshot. Return0: DONE/EMPTY;
 * return2: ACTIVE/INVALID. Reject/EMPTY does not touch before. NULL *session is
 * repeatable EMPTY; arbitrary stale aliases are not detected after destruction.
 * Frees only raw registered headers, context last. No graph/stack traversal,
 * callbacks, allocation, ownership cleanup or fault path. Totals saturate and
 * flag overflow; original report is historical and never normalized to zero. */
int rt_session_destroy_terminal(RtContext **session,RtReport *before,RtDestroyReport *destroyed);
/* Opt-in only: preserve fault result/report, destroy its context AFTER unwind.
 * New JSON envelope separates evaluation from raw destruction. Normal completion
 * still uses ordinary close. NULL report/receipt outputs are permitted here.
 * Legacy rt_run/rt_run_repeat retain their diagnostic failure policy/schema. */
int rt_run_repeat_destroy_fault(const RtProgram *,RtEntry,const RtOptions *,uint64_t,
                               FILE *,RtReport *,RtDestroyReport *);



/* Every call below corresponds to exactly one checked IR instruction, including
 * rt_return and rt_finish_entry. Constructors retain operands, never consume.
 * Arrays are borrowed for the duration of the call; count is descriptor-derived.
 * Only application_borrow permits loan operands. Authority may be owned handle
 * or the exact activation home key, never an ordinary loan. */
RtHandle *rt_new_root(RtContext *, size_t import_count, RtHandle *const *imports);
RtHandle *rt_new_below(RtContext *, RtHandle *ceiling, size_t import_count, RtHandle *const *imports);
RtHandle *rt_alloc(RtContext *, RtHandle *authority, const RtShape *, RtHandle *const *fields, const char *out);
RtHandle *rt_closure(RtContext *, RtHandle *authority, const RtCode *, RtHandle *const *captures, const char *out);
RtHandle *rt_thunk(RtContext *, RtHandle *authority, const RtCode *, RtHandle *const *captures, const char *out);
RtHandle *rt_application(RtContext *, RtHandle *authority, RtHandle *function, RtHandle *argument, const char *out);
RtHandle *rt_application_borrow(RtContext *, RtHandle *authority, RtHandle *function, RtHandle *argument, const char *out);
RtHandle *rt_hole(RtContext *, RtHandle *authority, const RtShape *, const char *out);
void rt_fill(RtContext *, RtHandle *hole, RtHandle *value, const char *hole_variable, const char *value_variable);
RtHandle *rt_retain(RtContext *, RtHandle *);
void rt_drop(RtContext *, RtHandle *);
RtHandle *rt_borrow(RtContext *, RtHandle *);
void rt_end_borrow(RtContext *, RtHandle *);
RtHandle *rt_field(RtContext *, RtHandle *source, size_t field_index, const char *out, const char *source_variable);
RtHandle *rt_force(RtContext *, RtHandle *, const char *out, const char *source_variable); /* consumes owner; returns owner; labels diagnostic only */
RtHandle *rt_return(RtContext *, RtHandle *); /* transfers owner; no extra retain */
void rt_finish_entry(RtContext *);

/* New scalar foundation/1. Exact registered intrinsic descriptor identity;
 * values remain boxed group-owned nodes. Inputs to prim2 are ready owners and
 * are not consumed/retained. Strict source demand is explicit Force L then R
 * in a delayed checked callback; these helpers never implicitly Force. */
RtHandle *rt_scalar_i64(RtContext *, RtHandle *authority, const RtShape *, int64_t, const char *out);
RtHandle *rt_scalar_bool(RtContext *, RtHandle *authority, const RtShape *, int, const char *out);
RtHandle *rt_prim2(RtContext *, RtHandle *authority, RtScalarPrimitive, const RtShape *result,
                   RtHandle *left, RtHandle *right, const char *out);
/* Consumes two distinct Int owners, transfers selected identity unchanged and
 * drops the other. Condition/authority stay live; no branch demand/allocation.
 * Checked Down(authority) proof is erased. Caller must retire both old bindings. */
RtHandle *rt_select_i64(RtContext *, RtHandle *authority, RtHandle *ready_bool,
                        RtHandle *then_owner, RtHandle *else_owner, const char *out);
/* Registered family/variant identity, never constructor-name equivalence.
 * case validates all arm entries before consuming any; no branch forcing.
 * Selected exact owner transfers, others drop in declared order. Bounded O(n^2)
 * alias validation and O(n) drop work, n<=RT_MAX_SUM_VARIANTS, one IR tick. */
RtHandle *rt_construct_nullary(RtContext *, RtHandle *authority, const RtFamily *,
                               const RtVariant *, const char *out);
RtHandle *rt_case_i64(RtContext *, RtHandle *authority, const RtFamily *,
                      RtHandle *ready_scrutinee, size_t arm_count, const RtCaseArm *, const char *out);
/* Constructor retains every positional field without forcing; raw HOLE fields
 * are admitted during knot construction. Factory authenticates every selected
 * payload slot (including wildcard slots) and rejects raw HOLE before capture.
 * All arms are validated before any field acquisition/allocation. Originals
 * remain live. Only selected field bindings get temporary owners; one chosen
 * THUNK owns capture slots before temporaries are dropped. OOM poisons and keeps
 * real partial allocations; no rollback/cleanup promise. One bounded IR tick. */
RtHandle *rt_construct_sum(RtContext *, RtHandle *authority, const RtFamily *,
                           const RtVariant *, size_t field_count,
                           RtHandle *const *fields, const char *out);
RtHandle *rt_case_fields_i64(RtContext *, RtHandle *authority, const RtFamily *,
                            RtHandle *ready_scrutinee, size_t arm_count,
                            const RtFactoryArm *, const char *out);
void rt_finish_scalar(RtContext *, RtHandle *owned_ready_scalar);

/* _into variants perform exactly one identical IR operation and return out.
 * out must be valid typed caller-owned DEAD storage with stable address until
 * dropped/moved; never the same cell as any live input. The code generator
 * proves liveness coloring, uses distinct outputs within each instruction, and
 * defaults to original heap helpers when its whole-body stack budget fails.
 * Caller storage is not stored in language nodes/slots. Exact anchors may not
 * be moved or dropped with live loans. rt_return automatically promotes a
 * LOCAL result to HEAP by storage move BEFORE C unwind, preserving logical ID
 * and counts; all callbacks must return that rt_return result, not old storage.
 * rt_force_into moves the canonical owner to out without extra retain/drop.
 * Internal activation owners/pins/cursors remain heap backed in this revision.
 * Once remains unsupported. */
RtHandle *rt_new_root_into(RtContext *, RtHandle *out, size_t, RtHandle *const *);
RtHandle *rt_new_below_into(RtContext *, RtHandle *out, RtHandle *ceiling, size_t, RtHandle *const *);
RtHandle *rt_alloc_into(RtContext *, RtHandle *out, RtHandle *authority, const RtShape *, RtHandle *const *, const char *);
RtHandle *rt_closure_into(RtContext *, RtHandle *out, RtHandle *authority, const RtCode *, RtHandle *const *, const char *);
RtHandle *rt_thunk_into(RtContext *, RtHandle *out, RtHandle *authority, const RtCode *, RtHandle *const *, const char *);
RtHandle *rt_application_into(RtContext *, RtHandle *out, RtHandle *authority, RtHandle *function, RtHandle *argument, const char *);
RtHandle *rt_application_borrow_into(RtContext *, RtHandle *out, RtHandle *authority, RtHandle *function, RtHandle *argument, const char *);
RtHandle *rt_hole_into(RtContext *, RtHandle *out, RtHandle *authority, const RtShape *, const char *);
RtHandle *rt_retain_into(RtContext *, RtHandle *out, RtHandle *source);
RtHandle *rt_borrow_into(RtContext *, RtHandle *out, RtHandle *source);
RtHandle *rt_field_into(RtContext *, RtHandle *out, RtHandle *source, size_t, const char *, const char *);
RtHandle *rt_force_into(RtContext *, RtHandle *out, RtHandle *consumed, const char *, const char *);

#endif
