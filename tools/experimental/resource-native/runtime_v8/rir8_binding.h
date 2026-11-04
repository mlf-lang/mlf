/* Stage05A real binding ABI; no runtime implementation or execution capability.
 * Same-ABI immutable readable roots and disjoint valid caller storage required.
 * Function-pointer members must have valid native object representations. */
#ifndef RIR8_BINDING_H
#define RIR8_BINDING_H
#include "../packet_v8/ir8_packet.h"
#if !defined(UINTPTR_MAX)
#error "IR8 binding requires uintptr_t for the supported address profile"
#endif
_Static_assert(SIZE_MAX <= UINTPTR_MAX, "size_t address extents fit uintptr_t");
_Static_assert(sizeof(size_t) <= sizeof(uint64_t), "size_t work extents fit uint64_t");

typedef struct Rt8Context Rt8Context;
typedef struct Rt8Handle Rt8Handle;
typedef struct Rt8Group Rt8Group;
typedef struct Rt8Node Rt8Node;
typedef Ir8PacketEnv Rt8Env;
typedef Ir8PacketSite Rt8Site;
typedef Ir8PacketAccess Rt8Access;
typedef Ir8PacketIntro Rt8Intro;
typedef Ir8PacketUse Rt8Instantiation;
typedef Ir8PacketShapeSpec Rt8Shape;
typedef Ir8PacketFamilySpec Rt8Family;
typedef Ir8PacketVariantSpec Rt8Variant;
typedef Ir8PacketWorkspace Rt8BindingWorkspace;
typedef Rt8Handle *(*Rt8Body)(Rt8Context *, Rt8Handle *home,
    Rt8Handle **captures, Rt8Handle *argument, const Rt8Env *env);
typedef void (*Rt8Entry)(Rt8Context *);

#define RT8_BINDING_ABI_REVISION UINT32_C(1)
#define RT8_BINDING_PURPOSE_STATIC_REAL_BODIES UINT32_C(1)
#define RT8_BINDING_MAGIC {73, 82, 56, 66, 73, 78, 68, 0}
#define RT8_MAX_STATIC_BYTES UINT32_C(4194304)
#define RT8_MAX_LABEL_BYTES UINT32_C(1048576)
#define RT8_MAX_LABELS UINT32_C(65536)
#define RT8_MAX_BINDING_WORK UINT64_C(67108864)
#define RT8_MAX_GUARD_WORK UINT64_C(67108864)
#define RT8_MAX_WORKSPACE_BYTES UINT32_C(131072)
#define RT8_MAX_STACK_HANDLE_BYTES UINT32_C(128)
#define RT8_MAX_GENERATED_POINTER_CELLS UINT32_C(512)
#define RT8_MAX_WALK_DEPTH UINT32_C(32)
#define RT8_NULL UINT32_C(4294967295)
#define RT8_STATUS_OK UINT32_C(0)
#define RT8_STATUS_ARGUMENT UINT32_C(1)
#define RT8_STATUS_ABI UINT32_C(2)
#define RT8_STATUS_SIZE_LIMIT UINT32_C(3)
#define RT8_STATUS_ALIGNMENT UINT32_C(4)
#define RT8_STATUS_PACKET UINT32_C(5)
#define RT8_STATUS_BINDING UINT32_C(6)
#define RT8_STATUS_STATIC_LIMIT UINT32_C(7)
#define RT8_STATUS_WORK_LIMIT UINT32_C(8)
#define RT8_STATUS_REFERENCE UINT32_C(9)
#define RT8_STATUS_TYPE UINT32_C(10)
#define RT8_STATUS_ORIGIN UINT32_C(11)
#define RT8_STATUS_STATE UINT32_C(12)
#define RT8_STATUS_OWNERSHIP UINT32_C(13)
#define RT8_STATUS_OVERFLOW UINT32_C(14)
#define RT8_STATUS_INTERNAL UINT32_C(15)
#define RT8_STATUS_UNBOUND UINT32_C(16)
#define RT8_PHASE_NONE UINT32_C(0)
#define RT8_PHASE_ARGUMENTS UINT32_C(1)
#define RT8_PHASE_NATIVE_HEADER UINT32_C(2)
#define RT8_PHASE_EXPECTED_BINDINGS UINT32_C(3)
#define RT8_PHASE_PACKET UINT32_C(4)
#define RT8_PHASE_NATIVE_LAYOUT UINT32_C(5)
#define RT8_PHASE_CODE_BINDINGS UINT32_C(6)
#define RT8_PHASE_LABELS UINT32_C(7)
#define RT8_PHASE_STATIC_CENSUS UINT32_C(8)
#define RT8_PHASE_FINAL UINT32_C(9)
#define RT8_PHASE_LOOKUP UINT32_C(10)
#define RT8_PHASE_DYNAMIC_GUARD UINT32_C(11)
#define RT8_DETAIL_NONE UINT32_C(0)
#define RT8_DETAIL_NULL_ARGUMENT UINT32_C(1)
#define RT8_DETAIL_REVISION UINT32_C(2)
#define RT8_DETAIL_MAGIC UINT32_C(3)
#define RT8_DETAIL_PURPOSE UINT32_C(4)
#define RT8_DETAIL_LENGTH UINT32_C(5)
#define RT8_DETAIL_OVERFLOW UINT32_C(6)
#define RT8_DETAIL_OFFSET UINT32_C(7)
#define RT8_DETAIL_OVERLAP UINT32_C(8)
#define RT8_DETAIL_ALIGNMENT UINT32_C(9)
#define RT8_DETAIL_COUNT UINT32_C(10)
#define RT8_DETAIL_ORDER UINT32_C(11)
#define RT8_DETAIL_DUPLICATE UINT32_C(12)
#define RT8_DETAIL_MISSING UINT32_C(13)
#define RT8_DETAIL_EXTRA UINT32_C(14)
#define RT8_DETAIL_NULL_CALLBACK UINT32_C(15)
#define RT8_DETAIL_BINDING_MISMATCH UINT32_C(16)
#define RT8_DETAIL_STATIC_BUDGET UINT32_C(17)
#define RT8_DETAIL_UNSUPPORTED UINT32_C(18)
#define RT8_DETAIL_UNREGISTERED UINT32_C(19)
#define RT8_DETAIL_DOMAIN UINT32_C(20)
#define RT8_DETAIL_APPLICABILITY UINT32_C(21)
#define RT8_DETAIL_WORK_EXHAUSTED UINT32_C(22)
#define RT8_DETAIL_EQUATION UINT32_C(23)
#define RT8_DETAIL_ANCHOR UINT32_C(24)
#define RT8_DETAIL_OWNER UINT32_C(25)
#define RT8_DETAIL_TOKEN UINT32_C(26)
#define RT8_DETAIL_STATE UINT32_C(27)
#define RT8_DETAIL_DEPENDENT_LOAN UINT32_C(28)
#define RT8_DETAIL_TICKET UINT32_C(29)
#define RT8_DETAIL_INTERNAL_INVARIANT UINT32_C(30)
#define RT8_REGION_NONE UINT32_C(0)
#define RT8_REGION_PACKET UINT32_C(1)
#define RT8_REGION_BINDING UINT32_C(2)
#define RT8_DOMAIN_KIND_NONE UINT32_C(0)
#define RT8_DOMAIN_KIND_PACKET_TABLE UINT32_C(1)
#define RT8_DOMAIN_KIND_PACKET_DESCRIPTOR UINT32_C(2)
#define RT8_DOMAIN_KIND_NATIVE_CODE UINT32_C(3)
#define RT8_DOMAIN_KIND_LABEL UINT32_C(4)

typedef struct Rt8Program {
    const void * packet;
    size_t packet_bytes;
    const void * binding;
    size_t binding_bytes;
} Rt8Program;

typedef struct Rt8Code {
    uint32_t code_id;
    Rt8Body body;
} Rt8Code;

typedef struct Rt8BindingHeader {
    unsigned char magic[8];
    uint32_t abi_revision;
    uint32_t purpose;
    uint32_t binding_bytes;
    uint32_t binding_alignment;
    uint32_t packet_bytes;
    uint32_t packet_alignment;
    uint32_t code_offset;
    uint32_t code_count;
    uint32_t label_index_offset;
    uint32_t label_count;
    uint32_t label_bytes_offset;
    uint32_t label_bytes;
    uint32_t runtime_total_static_bytes;
    Ir8PacketExpectedBindings expected;
    Rt8Entry entry;
} Rt8BindingHeader;

typedef struct Rt8BindingReport {
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
    uint64_t work_used;
    uint64_t work_limit;
    uint32_t packet_checked;
    uint32_t packet_bytes;
    uint32_t binding_bytes;
    uint32_t runtime_total_static_bytes;
    uint32_t workspace_bytes;
    uint32_t header_bytes;
    uint32_t code_bytes;
    uint32_t label_index_bytes;
    uint32_t label_bytes;
    uint32_t padding_bytes;
    uint32_t code_count;
    uint32_t label_count;
    uint32_t binding_validated;
    uint32_t runtime_admitted;
    uint32_t source_admitted;
    uint32_t graph_executed;
    uint32_t runtime_guards_executed;
    Ir8PacketReport packet;
} Rt8BindingReport;

_Static_assert(sizeof(Rt8Program) <= UINT32_MAX, "Rt8Program size fits uint32_t");
_Static_assert(_Alignof(Rt8Program) <= UINT32_MAX, "Rt8Program alignment fits uint32_t");
_Static_assert(sizeof(Rt8Code) <= UINT32_MAX, "Rt8Code size fits uint32_t");
_Static_assert(_Alignof(Rt8Code) <= UINT32_MAX, "Rt8Code alignment fits uint32_t");
_Static_assert(sizeof(Rt8BindingHeader) <= UINT32_MAX, "Rt8BindingHeader size fits uint32_t");
_Static_assert(_Alignof(Rt8BindingHeader) <= UINT32_MAX, "Rt8BindingHeader alignment fits uint32_t");
_Static_assert(sizeof(Rt8BindingReport) <= UINT32_MAX, "Rt8BindingReport size fits uint32_t");
_Static_assert(_Alignof(Rt8BindingReport) <= UINT32_MAX, "Rt8BindingReport alignment fits uint32_t");
_Static_assert(sizeof(Rt8Body) <= UINT32_MAX, "Rt8Body size fits uint32_t");
_Static_assert(_Alignof(Rt8Body) <= UINT32_MAX, "Rt8Body alignment fits uint32_t");
_Static_assert(sizeof(Rt8Entry) <= UINT32_MAX, "Rt8Entry size fits uint32_t");
_Static_assert(_Alignof(Rt8Entry) <= UINT32_MAX, "Rt8Entry alignment fits uint32_t");
_Static_assert(sizeof(Rt8BindingWorkspace) <= UINT32_MAX, "Rt8BindingWorkspace size fits uint32_t");
_Static_assert(_Alignof(Rt8BindingWorkspace) <= UINT32_MAX, "Rt8BindingWorkspace alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketExpectedBindings) <= UINT32_MAX, "Ir8PacketExpectedBindings size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketExpectedBindings) <= UINT32_MAX, "Ir8PacketExpectedBindings alignment fits uint32_t");
_Static_assert(sizeof(uint32_t) <= UINT32_MAX, "uint32_t size fits uint32_t");
_Static_assert(_Alignof(uint32_t) <= UINT32_MAX, "uint32_t alignment fits uint32_t");
_Static_assert(sizeof(unsigned char) <= UINT32_MAX, "unsigned char size fits uint32_t");
_Static_assert(_Alignof(unsigned char) <= UINT32_MAX, "unsigned char alignment fits uint32_t");
_Static_assert(sizeof(Rt8BindingWorkspace) <= RT8_MAX_WORKSPACE_BYTES,
    "actual packet workspace stays within fixed binding scratch cap");

/* Fresh structural validation only. Never allocates or invokes a callback.
 * program/expected/workspace/report are valid, mutually disjoint caller objects;
 * both roots are immutable, readable, valid native representations, disjoint
 * from those objects. Their lifetimes cover every future reference/session.
 * A temporary Program wrapper is copied, not retained. Scratch/report are never
 * retained. On any return, all runtime/source/graph/guard flags remain zero.
 * report is required; a NULL report returns ARGUMENT without a write.
 * Return equals report.status when report exists. Prior reports grant nothing. */
uint32_t rt8_binding_validate(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, Rt8BindingReport *);
#endif
