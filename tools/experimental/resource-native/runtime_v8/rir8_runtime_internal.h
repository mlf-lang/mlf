/* Shared private kernel contract. Every definition is genuine, not a stub. */
#ifndef RIR8_RUNTIME_INTERNAL_H
#define RIR8_RUNTIME_INTERNAL_H
#include "rir8_session.h"
#include "rir8_binding_internal.h"
#include <setjmp.h>
#include <stdint.h>
#include <limits.h>
#include <stddef.h>

#define RT8_MC_CONTEXT UINT32_C(0)
#define RT8_MC_GROUP UINT32_C(1)
#define RT8_MC_NODE UINT32_C(2)
#define RT8_MC_SLOTS UINT32_C(3)
#define RT8_MC_HANDLE UINT32_C(4)
#define RT8_MC_CAPTURES UINT32_C(5)
#define RT8_MC_PENDING UINT32_C(6)
#define RT8_RC_OWNER UINT32_C(0)
#define RT8_RC_BUILDER UINT32_C(1)
#define RT8_RC_PIN UINT32_C(2)
#define RT8_RC_KEY UINT32_C(3)
#define RT8_RC_SLOT UINT32_C(4)
#define RT8_NS_READY UINT32_C(0)
#define RT8_NS_HOLE UINT32_C(1)
#define RT8_NS_INDIRECT UINT32_C(2)
#define RT8_NS_THUNK UINT32_C(3)
#define RT8_NS_CLOSURE UINT32_C(4)
#define RT8_NS_APPLICATION UINT32_C(5)
#define RT8_NS_BUSY UINT32_C(6)
#define RT8_NS_MEMO UINT32_C(7)
#define RT8_STORAGE_CLASS_BASE UINT32_C(1)
#define RT8_STORAGE_CLASS_SCALAR UINT32_C(2)
#define RT8_STORAGE_CLASS_SUM UINT32_C(3)
#define RT8_FRAME_ENTRY UINT32_C(1)
#define RT8_FRAME_FUNCTION UINT32_C(2)
#define RT8_FRAME_THUNK UINT32_C(3)

#define RT8_VALUE_OWN UINT32_C(1)
#define RT8_VALUE_MONO UINT32_C(2)
#define RT8_VALUE_TICKET_FREE UINT32_C(4)
#define RT8_VALUE_NO_LOANS UINT32_C(8)
#define RT8_MAX_IMPORTS 512
#define RT8_MAX_DATA_FIELDS 4096
#define RT8_MAX_CAPTURES 64
#define RT8_MAX_VARIANTS 64
#define RT8_MAX_VARIANT_FIELDS 32
#define RT8_MAX_FACTORY_FIELDS 32
#define RT8_MAX_FACTORY_EXTERNALS 32

/* Op IDs are private control identities, never metadata row IDs or IR ticks. */
typedef enum Rt8Operation {
 RT8_OP_NEW_ROOT, RT8_OP_NEW_BELOW, RT8_OP_ALLOC, RT8_OP_CLOSURE,
 RT8_OP_THUNK, RT8_OP_APPLICATION, RT8_OP_APPLICATION_BORROW, RT8_OP_HOLE,
 RT8_OP_FILL, RT8_OP_RETAIN, RT8_OP_DROP, RT8_OP_BORROW, RT8_OP_END_BORROW,
 RT8_OP_FIELD, RT8_OP_FORCE, RT8_OP_RETURN, RT8_OP_FINISH,
 RT8_OP_SCALAR, RT8_OP_PRIM2, RT8_OP_SELECT, RT8_OP_NULLARY, RT8_OP_CASE,
 RT8_OP_SUM, RT8_OP_FACTORY, RT8_OP_FINISH_SCALAR, RT8_OP_BEGIN,
 RT8_OP_SEAL, RT8_OP_INSTANTIATE, RT8_OP_ACCESSOR
} Rt8Operation;

typedef union Rt8MemHeader Rt8MemHeader;
typedef struct Rt8Slot Rt8Slot;
typedef struct Rt8Origin Rt8Origin;
typedef struct Rt8Frame Rt8Frame;
typedef struct Rt8Pending Rt8Pending;
union Rt8MemHeader {
 max_align_t alignment;
 struct { Rt8MemHeader *previous, *next; size_t requested; unsigned category; } info;
};

typedef struct Rt8Origin {
    const Rt8Env * env;
    uint64_t capsule_id;
    uint64_t creation_activation;
    uint32_t kind;
} Rt8Origin;

typedef struct Rt8Slot {
    const char * name;
    Rt8Node * target;
    const Rt8Access * access;
} Rt8Slot;

struct Rt8Group {
    uint64_t id;
    uint64_t count;
    uint64_t members;
    Rt8Node * first;
    Rt8Node * last;
    Rt8Group * queue_next;
};

struct Rt8Node {
    uint64_t id;
    Rt8Group * group;
    const Rt8Shape * shape;
    const Rt8Code * code;
    uint32_t state;
    size_t used;
    size_t capacity;
    Rt8Slot * slots;
    Rt8Node * next;
    const Rt8Site * origin_site;
    Rt8Origin origin;
    uint32_t storage_class;
};

typedef struct Rt8ScalarNode {
    Rt8Node base;
    int64_t value;
} Rt8ScalarNode;

typedef struct Rt8SumNode {
    Rt8Node base;
    const Rt8Variant * variant;
} Rt8SumNode;

typedef struct Rt8Frame {
    uint64_t id;
    Rt8Frame * parent;
    Rt8Handle * home;
    uint32_t kind;
    uint32_t returned;
    const Rt8Code * code;
    const Ir8PacketCodeExecution * code_execution;
    Rt8Origin execution;
    const Rt8Intro * active_intro;
    uint32_t expected_result_type;
    uint32_t result_identity;
    uint64_t argument_node_id;
    Rt8Group * argument_group;
    Rt8Handle * returned_handle;
} Rt8Frame;

typedef struct Rt8Pending {
    Rt8Node * node;
    Rt8Handle * pin;
    Rt8Pending * next;
    Rt8Pending * previous;
    const Rt8Access * requested;
    const Rt8Access * memo_access;
    uint32_t memo_slot_id;
    uint32_t prepared;
} Rt8Pending;

struct Rt8Context {
    Rt8ProgramView program;
    Rt8Options options;
    Rt8Report report;
    Rt8Work guard_work;
    FILE * output;
    jmp_buf failure;
    Rt8MemHeader * ledger;
    Rt8Handle * handles;
    Rt8Group * close_first;
    Rt8Group * close_last;
    uint32_t closing;
    uint32_t finished;
    uint32_t api_active;
    uint64_t next_group;
    uint64_t next_node;
    uint64_t next_handle;
    uint64_t next_frame;
    uint64_t next_capsule;
    uint64_t live_groups;
    uint64_t live_nodes;
    uint64_t live_owners;
    uint64_t force_depth;
    uint64_t activation_depth;
    uint64_t rc_inc_total;
    uint64_t rc_dec_total;
    uint64_t fuel_remaining;
    Rt8Frame * frame;
};

/* Immediate-use facts: no stored owner, callback, scope token or heap cache. */
typedef struct Rt8ValueFacts {
 Rt8Node *node;
 const Rt8Access *access;
 Ir8PacketAccess row;
 Ir8PacketSite site;
 Ir8PacketSiteExecution execution;
 Ir8PacketShapeSpec shape;
} Rt8ValueFacts;
typedef struct Rt8SiteFacts {
 const Rt8Site *site_ref;
 const Rt8Shape *shape_ref;
 const Rt8Access *principal_access;
 Rt8Origin origin;
 Ir8PacketSite site;
 Ir8PacketSiteExecution execution;
 Ir8PacketShapeSpec shape;
} Rt8SiteFacts;
typedef struct Rt8SlotFacts {
 Ir8PacketSlot row;
 uint32_t resolved_type;
 const char *name;
} Rt8SlotFacts;
typedef struct Rt8EventReservation {
 uint64_t emitted;
 uint64_t omitted;
 uint32_t write;
} Rt8EventReservation;

/* Memory/session-independent fault transfer and checked operational arithmetic. */
_Noreturn void rt8_private_fault(Rt8Context *, uint32_t fault);
_Noreturn void rt8_private_guard_fault(Rt8Context *, uint32_t status, uint32_t detail,
 uint32_t guard, uint32_t domain, uint32_t row, uint32_t field);
void rt8_private_add(Rt8Context *, uint64_t *, uint64_t);
void rt8_private_bump(Rt8Context *, uint64_t *);
uint64_t rt8_private_identity(Rt8Context *, uint64_t *);
void rt8_private_peak(uint64_t *, uint64_t);
void rt8_private_tick(Rt8Context *);
void rt8_private_enter(Rt8Context *, Rt8Operation, int tick);
void rt8_private_charge(Rt8Context *, uint64_t);
void rt8_private_guard_seen(Rt8Context *, uint32_t);

/* Bounded metadata functions. All outputs are immediate local copies/identities. */
void rt8_private_table(Rt8Context *, uint32_t, uint32_t, void *, size_t);
void rt8_private_descriptor(Rt8Context *, uint32_t, uint32_t, void *, size_t);
void rt8_private_vector(Rt8Context *, uint32_t, uint32_t, uint32_t, void *, size_t);
uint32_t rt8_private_table_auth(Rt8Context *, uint32_t, const void *);
uint32_t rt8_private_descriptor_auth(Rt8Context *, uint32_t, const void *);
const void *rt8_private_table_ref(Rt8Context *, uint32_t, uint32_t);
const void *rt8_private_descriptor_ref(Rt8Context *, uint32_t, uint32_t);
const char *rt8_private_string(Rt8Context *, uint32_t offset);
void rt8_private_label(Rt8Context *, const char *);
int rt8_private_text_equal(Rt8Context *, const char *, const char *);
uint32_t rt8_private_resolve(Rt8Context *, uint32_t type, const Rt8Env *);
int rt8_private_type_closed(Rt8Context *, uint32_t type);
const Rt8Access *rt8_private_access(Rt8Context *, uint32_t site, uint32_t origin_env,
 uint32_t mode, uint32_t use_env, uint32_t scheme);
void rt8_private_site_facts(Rt8Context *, const Rt8Site *, uint32_t category,
 const Rt8Code *, const Rt8Shape *, Rt8SiteFacts *);
void rt8_private_node_access(Rt8Context *, Rt8Node *, const Rt8Access *, int mono, Rt8ValueFacts *);
void rt8_private_value(Rt8Context *, Rt8Handle *, uint32_t flags, Rt8ValueFacts *);
void rt8_private_authority(Rt8Context *, Rt8Handle *);
void rt8_private_slot_spec(Rt8Context *, const Rt8Site *, const Rt8Env *,
 uint32_t role, size_t index, Rt8SlotFacts *);
void rt8_private_publish_check(Rt8Context *, const Rt8Origin *, uint32_t expected_type,
 const Rt8ValueFacts *);
void rt8_private_capture_publish(Rt8Context *, const Rt8Origin *,
 const Rt8SlotFacts *, const Rt8ValueFacts *);
void rt8_private_slot_check(Rt8Context *, Rt8Node *host, uint32_t role, size_t index,
 const Rt8Slot *, Rt8ValueFacts *, Rt8SlotFacts *);
const Rt8Access *rt8_private_transport(Rt8Context *, Rt8Node *host, uint32_t expected_type,
 const Rt8Access *request, Rt8Node *target, const Rt8Access *actual);
const Rt8Access *rt8_private_capture_transport(Rt8Context *, Rt8Node *host,
 const Rt8Access *request, size_t index);
const Ir8PacketCodeExecution *rt8_private_code_execution(Rt8Context *, const Rt8Code *,
 const Rt8Env *, Ir8PacketCodeTyping *, Ir8PacketCodeExecution *);
void rt8_private_result_check(Rt8Context *, const Rt8Frame *, const Rt8ValueFacts *);
uint32_t rt8_private_intrinsic_scalar_type(Rt8Context *, uint32_t);
void rt8_private_node_state(Rt8Context *, Rt8Node *, const Rt8ValueFacts *);

/* Operational kernel. Prepared primitives require all typed guard/charge work
 * already done; their RC/allocation/event failures retain genuine partial state. */
void *rt8_private_alloc(Rt8Context *, size_t, unsigned);
void *rt8_private_array(Rt8Context *, size_t, size_t, unsigned);
void rt8_private_free(Rt8Context *, void *);
Rt8Memory rt8_private_free_preflight(Rt8Context *, const Rt8Memory *, size_t);
size_t rt8_private_extent(Rt8Context *, const void *, unsigned category);
Rt8Handle *rt8_private_live(Rt8Context *, Rt8Handle *);
Rt8Handle *rt8_private_handle(Rt8Context *, Rt8Group *, Rt8Node *, const Rt8Access *,
 Rt8Handle *anchor, unsigned role);
Rt8Handle *rt8_private_acquire(Rt8Context *, Rt8Node *, const Rt8Access *);
Rt8Handle *rt8_private_local(Rt8Context *, Rt8Handle *);
void rt8_private_drop_prepared(Rt8Context *, Rt8Handle *);
Rt8Handle *rt8_private_escape_prepared(Rt8Context *, Rt8Handle *);
Rt8Handle *rt8_private_new_group(Rt8Context *);
Rt8Node *rt8_private_new_node(Rt8Context *, Rt8Group *, const Rt8SiteFacts *,
 uint32_t state, const Rt8Code *, size_t capacity);
void rt8_private_publish_prepared(Rt8Context *, Rt8Node *, const char *, Rt8Node *, const Rt8Access *);
void rt8_private_clear_prepared(Rt8Context *, Rt8Node *);
void rt8_private_inc(Rt8Context *, Rt8Group *, unsigned);
void rt8_private_dec(Rt8Context *, Rt8Group *, unsigned);

/* Events retain operational order. Prepare/commit is used by no-fault view moves.
 * Validated stable names only; no unknown user pointer enters these renderers. */
Rt8EventReservation rt8_private_event_prepare(Rt8Context *);
int rt8_private_event_commit(Rt8Context *, const char *, Rt8EventReservation);
int rt8_private_event(Rt8Context *, const char *);
void rt8_private_num(Rt8Context *, const char *, uint64_t);
void rt8_private_str(Rt8Context *, const char *, const char *);
void rt8_private_bool(Rt8Context *, const char *, int);
void rt8_private_end_event(Rt8Context *);
void rt8_private_slot_event(Rt8Context *, const char *, Rt8Node *, const char *, Rt8Node *, const char *);

/* Genuine activation and evaluator internals, implemented in rir8_force.c. */
void rt8_private_frame_push(Rt8Context *, Rt8Frame *, const char *prepared_code_name, Rt8Node *prepared_source);
void rt8_private_frame_pop(Rt8Context *, Rt8Frame *);
Rt8Handle *rt8_private_force(Rt8Context *, Rt8Handle *);
void rt8_private_checkpoint(Rt8Context *);
void rt8_private_report_copy(const Rt8Context *, Rt8Report *);

_Static_assert(sizeof(Rt8MemHeader) <= UINT32_MAX, "Rt8MemHeader size representable");
_Static_assert(_Alignof(Rt8MemHeader) <= UINT32_MAX, "Rt8MemHeader alignment representable");
_Static_assert(sizeof(Rt8Origin) <= UINT32_MAX, "Rt8Origin size representable");
_Static_assert(_Alignof(Rt8Origin) <= UINT32_MAX, "Rt8Origin alignment representable");
_Static_assert(sizeof(Rt8Slot) <= UINT32_MAX, "Rt8Slot size representable");
_Static_assert(_Alignof(Rt8Slot) <= UINT32_MAX, "Rt8Slot alignment representable");
_Static_assert(sizeof(Rt8Group) <= UINT32_MAX, "Rt8Group size representable");
_Static_assert(_Alignof(Rt8Group) <= UINT32_MAX, "Rt8Group alignment representable");
_Static_assert(sizeof(Rt8Node) <= UINT32_MAX, "Rt8Node size representable");
_Static_assert(_Alignof(Rt8Node) <= UINT32_MAX, "Rt8Node alignment representable");
_Static_assert(sizeof(Rt8ScalarNode) <= UINT32_MAX, "Rt8ScalarNode size representable");
_Static_assert(_Alignof(Rt8ScalarNode) <= UINT32_MAX, "Rt8ScalarNode alignment representable");
_Static_assert(sizeof(Rt8SumNode) <= UINT32_MAX, "Rt8SumNode size representable");
_Static_assert(_Alignof(Rt8SumNode) <= UINT32_MAX, "Rt8SumNode alignment representable");
_Static_assert(sizeof(Rt8Frame) <= UINT32_MAX, "Rt8Frame size representable");
_Static_assert(_Alignof(Rt8Frame) <= UINT32_MAX, "Rt8Frame alignment representable");
_Static_assert(sizeof(Rt8Pending) <= UINT32_MAX, "Rt8Pending size representable");
_Static_assert(_Alignof(Rt8Pending) <= UINT32_MAX, "Rt8Pending alignment representable");
_Static_assert(sizeof(Rt8Context) <= UINT32_MAX, "Rt8Context size representable");
_Static_assert(_Alignof(Rt8Context) <= UINT32_MAX, "Rt8Context alignment representable");
_Static_assert(sizeof(Rt8ValueFacts) <= UINT32_MAX, "Rt8ValueFacts size representable");
_Static_assert(_Alignof(Rt8ValueFacts) <= UINT32_MAX, "Rt8ValueFacts alignment representable");
_Static_assert(sizeof(Rt8SiteFacts) <= UINT32_MAX, "Rt8SiteFacts size representable");
_Static_assert(_Alignof(Rt8SiteFacts) <= UINT32_MAX, "Rt8SiteFacts alignment representable");
_Static_assert(sizeof(Rt8SlotFacts) <= UINT32_MAX, "Rt8SlotFacts size representable");
_Static_assert(_Alignof(Rt8SlotFacts) <= UINT32_MAX, "Rt8SlotFacts alignment representable");
_Static_assert(sizeof(Rt8EventReservation) <= UINT32_MAX, "Rt8EventReservation size representable");
_Static_assert(_Alignof(Rt8EventReservation) <= UINT32_MAX, "Rt8EventReservation alignment representable");
_Static_assert(sizeof(Rt8Operation) <= UINT32_MAX, "Rt8Operation size representable");
_Static_assert(_Alignof(Rt8Operation) <= UINT32_MAX, "Rt8Operation alignment representable");
_Static_assert(offsetof(Rt8ScalarNode, base) == 0, "scalar Node base first");
_Static_assert(offsetof(Rt8SumNode, base) == 0, "SUM Node base first");
_Static_assert(sizeof(size_t) <= sizeof(uint64_t), "ledger sizes fit uint64_t");
#endif
