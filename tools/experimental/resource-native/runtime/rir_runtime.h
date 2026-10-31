#ifndef RIR_RUNTIME_H
#define RIR_RUNTIME_H
/* Bounded, sequential Repeat-only checked-IR target. Not a C memory-safety sandbox. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct RtContext RtContext;
typedef struct RtHandle RtHandle;
typedef struct RtShape RtShape;
typedef struct RtCode RtCode;
typedef RtHandle *(*RtBody)(RtContext *, RtHandle *home, RtHandle **captures, RtHandle *argument);
typedef void (*RtEntry)(RtContext *);
typedef struct { const char *name; const RtShape *shape; } RtField;
typedef enum { RT_DATA = 0, RT_REPEAT = 1, RT_ONCE_UNSUPPORTED = 2 } RtShapeKind;
struct RtShape {
    const char *name;
    RtShapeKind kind;
    size_t field_count;
    const RtField *fields; /* sorted checked field names; DATA only */
    const RtShape *argument, *result; /* REPEAT only */
};
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
} RtReport;

/* Emits one JSON object, streaming bounded events (no history allocation), then
 * full report. output may be NULL for silent handtests. report may be NULL.
 * Successful return=0, terminal fault=2. No malloc-ledger sweep on failure.
 * Program/descriptors/strings must have immutable static lifetime. */
int rt_run(const RtProgram *, RtEntry, const RtOptions *, FILE *output, RtReport *report);

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
#endif
