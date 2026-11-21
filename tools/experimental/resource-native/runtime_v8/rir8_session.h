/* Stage05B genuine runtime/session API. SOURCE PREPARATION; not compiled. */
#ifndef RIR8_SESSION_H
#define RIR8_SESSION_H
#include "rir8_runtime.h"
#include <stdio.h>

#define RT8_MEMORY_CATEGORIES 7
#define RT8_RC_CATEGORIES 5
#define RT8_MAX_FORCE_DEPTH 128
#define RT8_MAX_ACTIVATION_DEPTH 128
#define RT8_LIFECYCLE_ID "resource-ir-v8-terminal-destroy/1"
#define RT8_RUN_COMPLETE UINT32_C(0)
#define RT8_RUN_FAULT UINT32_C(1)
#define RT8_FAULT_NONE UINT32_C(0)
#define RT8_FAULT_ARGUMENT UINT32_C(1)
#define RT8_FAULT_ADMISSION UINT32_C(2)
#define RT8_FAULT_OOM UINT32_C(3)
#define RT8_FAULT_FUEL UINT32_C(4)
#define RT8_FAULT_STACK_LIMIT UINT32_C(5)
#define RT8_FAULT_HOLE UINT32_C(6)
#define RT8_FAULT_BUSY UINT32_C(7)
#define RT8_FAULT_TYPED_GUARD UINT32_C(8)
#define RT8_FAULT_OVERFLOW UINT32_C(9)
#define RT8_FAULT_INVARIANT UINT32_C(10)
#define RT8_FAULT_ACTIVE UINT32_C(11)
#define RT8_DESTROY_DONE UINT32_C(1)
#define RT8_DESTROY_EMPTY UINT32_C(2)
#define RT8_DESTROY_ACTIVE UINT32_C(3)
#define RT8_DESTROY_INVALID UINT32_C(4)

typedef struct Rt8Options {
    uint64_t fuel;
    uint64_t event_limit;
    uint64_t guard_work_limit;
} Rt8Options;

typedef struct Rt8Memory {
    uint64_t allocated_bytes;
    uint64_t freed_bytes;
    uint64_t live_bytes;
    uint64_t peak_bytes;
    uint64_t allocations;
    uint64_t frees;
    uint64_t live_blocks;
    uint64_t peak_blocks;
} Rt8Memory;

typedef struct Rt8FaultInfo {
    uint32_t status;
    uint32_t phase;
    uint32_t detail;
    uint32_t region;
    uint32_t domain_kind;
    uint32_t domain;
    uint32_t object;
    uint32_t row;
    uint32_t field;
    uint32_t guard_index;
} Rt8FaultInfo;

typedef struct Rt8Report {
    uint32_t state;
    uint32_t fault;
    Rt8FaultInfo location;
    Rt8BindingReport binding;
    Rt8Memory memory;
    Rt8Memory categories[7];
    uint64_t rc_inc[5];
    uint64_t rc_dec[5];
    uint64_t steps;
    uint64_t groups_allocated;
    uint64_t groups_closed;
    uint64_t nodes_allocated;
    uint64_t nodes_freed;
    uint64_t peak_groups;
    uint64_t peak_nodes;
    uint64_t peak_owner_handles;
    uint64_t owner_handle_acquisitions;
    uint64_t owner_handle_releases;
    uint64_t loan_handle_acquisitions;
    uint64_t loan_handle_releases;
    uint64_t force_calls;
    uint64_t max_force_depth;
    uint64_t callback_calls;
    uint64_t ordinary_calls;
    uint64_t applications_allocated;
    uint64_t raw_deferred_returns;
    uint64_t memo_writes;
    uint64_t internal_memo_slots;
    uint64_t cross_group_memo_slots;
    uint64_t memo_fast_paths;
    uint64_t groups_closed_during_force;
    uint64_t borrowed_slot_publications;
    uint64_t ir_retain_ops;
    uint64_t ir_drop_ops;
    uint64_t ir_borrow_ops;
    uint64_t ir_end_borrow_ops;
    uint64_t ir_application_borrow_ops;
    uint64_t events_emitted;
    uint64_t events_omitted;
    uint64_t max_activation_depth;
    uint64_t entries_completed;
    uint32_t scalar_result_kind;
    int64_t scalar_result;
    uint64_t guard_work_used;
    uint64_t guard_work_total;
    uint64_t guard_work_limit;
    uint32_t guards_checked_mask;
    uint32_t guards_failed_mask;
    uint32_t graph_executed;
} Rt8Report;

typedef struct Rt8DestroyReport {
    uint32_t status;
    uint64_t retired_blocks;
    uint64_t retired_bytes;
    uint64_t category_blocks[7];
    uint64_t category_bytes[7];
    uint32_t totals_overflow;
} Rt8DestroyReport;

_Static_assert(sizeof(Rt8Options) <= UINT32_MAX, "Rt8Options size representable");
_Static_assert(_Alignof(Rt8Options) <= UINT32_MAX, "Rt8Options alignment representable");
_Static_assert(sizeof(Rt8Memory) <= UINT32_MAX, "Rt8Memory size representable");
_Static_assert(_Alignof(Rt8Memory) <= UINT32_MAX, "Rt8Memory alignment representable");
_Static_assert(sizeof(Rt8FaultInfo) <= UINT32_MAX, "Rt8FaultInfo size representable");
_Static_assert(_Alignof(Rt8FaultInfo) <= UINT32_MAX, "Rt8FaultInfo alignment representable");
_Static_assert(sizeof(Rt8Report) <= UINT32_MAX, "Rt8Report size representable");
_Static_assert(_Alignof(Rt8Report) <= UINT32_MAX, "Rt8Report alignment representable");
_Static_assert(sizeof(Rt8DestroyReport) <= UINT32_MAX, "Rt8DestroyReport size representable");
_Static_assert(_Alignof(Rt8DestroyReport) <= UINT32_MAX, "Rt8DestroyReport alignment representable");

/* Sequential/nonreentrant diagnostic sessions. Immutable program roots outlive
 * the session. Open copies wrappers/options, never scratch or expected pointers.
 * Expected/workspace/wrapper/session/report storage is valid and disjoint from
 * each other and both roots. Copy a generated expected tuple out of its root.
 * Optional report outputs are observations, not admission credentials.
 * Step invokes only the admitted real entry. Poison cannot resume or close;
 * terminal surrender is a separate explicit opt-in operation after unwind.
 * Return 0 is complete; return 2 is fault/rejection. No failure cleanup promise.
 */
int rt8_session_open(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, const Rt8Options *, Rt8Context **session, Rt8Report *report);
int rt8_session_step(Rt8Context *, Rt8Report *report);
int rt8_session_snapshot(const Rt8Context *, Rt8Report *report);
int rt8_session_close(Rt8Context **session, Rt8Report *report);
int rt8_run(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, const Rt8Options *, FILE *output, Rt8Report *report);
int rt8_run_repeat(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, const Rt8Options *, uint64_t repetitions, FILE *output, Rt8Report *report);
int rt8_session_destroy_terminal(Rt8Context **session, Rt8Report *before, Rt8DestroyReport *destroyed);
int rt8_run_repeat_destroy_fault(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, const Rt8Options *, uint64_t repetitions, FILE *output, Rt8Report *report, Rt8DestroyReport *destroyed);
#endif
