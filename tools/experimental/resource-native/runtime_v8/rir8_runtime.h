/* Genuine future runtime ABI declarations. No Context/Node implementation,
 * fake layout, stub, old-ABI fallback or callback invocation is supplied. */
#ifndef RIR8_RUNTIME_H
#define RIR8_RUNTIME_H
#include "rir8_binding.h"

typedef enum {
    RT8_STORAGE_DEAD=0,
    RT8_STORAGE_HEAP=1,
    RT8_STORAGE_LOCAL=2
} Rt8StorageKind;

typedef enum {
    RT8_SCOPE_UNUSED=0,
    RT8_SCOPE_ACTIVE=1,
    RT8_SCOPE_SEALED=2
} Rt8ScopeState;

/* Runtime-private ownership storage. Never copy an owning Handle. Access
 * belongs to the actual value/loan, not necessarily its anchor. Pin/key/builder
 * roles are authority-only even when their node is nonnull. fill_ticket is the
 * original capability's ticket, not NS_HOLE: copies clear, storage moves preserve. */
struct Rt8Handle {
    uint64_t id;
    uint64_t scope;
    uint64_t loans;
    Rt8Group * group;
    Rt8Node * node;
    Rt8Handle * anchor;
    Rt8Handle * previous;
    Rt8Handle * next;
    unsigned role;
    int home;
    Rt8StorageKind storage_kind;
    const Rt8Access * access;
    uint32_t fill_ticket;
};

/* Enclosing-function lifetime, zero initialization; no token address escapes.
 * Begin/instantiate each tick once; seal has no extra tick and returns the same
 * owner pointer. Scope state rejects reuse; padding is never an authority. */
typedef struct Rt8GenericScope {
    uint64_t frame_id;
    uint64_t capsule_id;
    uint64_t handle_watermark;
    const Rt8Intro * intro;
    Rt8Handle * authority;
    const Rt8Env * prior_env;
    uint64_t prior_capsule_id;
    const Rt8Intro * prior_intro;
    uint32_t prior_origin_kind;
    uint32_t state;
} Rt8GenericScope;

typedef enum { RT8_FACTORY_FIELD=1, RT8_FACTORY_EXTERNAL=2 } Rt8FactoryCaptureKind;
typedef enum {
    RT8_PRIM_ADD_INT=8,
    RT8_PRIM_SUB_INT=9,
    RT8_PRIM_EQ_INT=10,
    RT8_PRIM_LT_INT=11,
    RT8_PRIM_MUL_INT=14
} Rt8ScalarPrimitive;

typedef struct Rt8CaseArm {
    const Rt8Variant * variant;
    Rt8Handle * value;
} Rt8CaseArm;

typedef struct Rt8FactoryCapture {
    const char * name;
    Rt8FactoryCaptureKind kind;
    size_t field_index;
    Rt8Handle * external;
} Rt8FactoryCapture;

typedef struct Rt8FactoryArm {
    const Rt8Variant * variant;
    const Rt8Site * site;
    const Rt8Code * code;
    size_t capture_count;
    const Rt8FactoryCapture * captures;
} Rt8FactoryArm;

_Static_assert(sizeof(Rt8Handle) <= UINT32_MAX, "Rt8Handle size fits uint32_t");
_Static_assert(_Alignof(Rt8Handle) <= UINT32_MAX, "Rt8Handle alignment fits uint32_t");
_Static_assert(sizeof(Rt8GenericScope) <= UINT32_MAX, "Rt8GenericScope size fits uint32_t");
_Static_assert(_Alignof(Rt8GenericScope) <= UINT32_MAX, "Rt8GenericScope alignment fits uint32_t");
_Static_assert(sizeof(Rt8CaseArm) <= UINT32_MAX, "Rt8CaseArm size fits uint32_t");
_Static_assert(_Alignof(Rt8CaseArm) <= UINT32_MAX, "Rt8CaseArm alignment fits uint32_t");
_Static_assert(sizeof(Rt8FactoryCapture) <= UINT32_MAX, "Rt8FactoryCapture size fits uint32_t");
_Static_assert(_Alignof(Rt8FactoryCapture) <= UINT32_MAX, "Rt8FactoryCapture alignment fits uint32_t");
_Static_assert(sizeof(Rt8FactoryArm) <= UINT32_MAX, "Rt8FactoryArm size fits uint32_t");
_Static_assert(_Alignof(Rt8FactoryArm) <= UINT32_MAX, "Rt8FactoryArm alignment fits uint32_t");
_Static_assert(sizeof(Rt8StorageKind) <= UINT32_MAX, "Rt8StorageKind size fits uint32_t");
_Static_assert(_Alignof(Rt8StorageKind) <= UINT32_MAX, "Rt8StorageKind alignment fits uint32_t");
_Static_assert(sizeof(Rt8ScopeState) <= UINT32_MAX, "Rt8ScopeState size fits uint32_t");
_Static_assert(_Alignof(Rt8ScopeState) <= UINT32_MAX, "Rt8ScopeState alignment fits uint32_t");
_Static_assert(sizeof(Rt8FactoryCaptureKind) <= UINT32_MAX, "Rt8FactoryCaptureKind size fits uint32_t");
_Static_assert(_Alignof(Rt8FactoryCaptureKind) <= UINT32_MAX, "Rt8FactoryCaptureKind alignment fits uint32_t");
_Static_assert(sizeof(Rt8ScalarPrimitive) <= UINT32_MAX, "Rt8ScalarPrimitive size fits uint32_t");
_Static_assert(_Alignof(Rt8ScalarPrimitive) <= UINT32_MAX, "Rt8ScalarPrimitive alignment fits uint32_t");
_Static_assert(sizeof(Rt8Handle) <= RT8_MAX_STACK_HANDLE_BYTES,
    "unsupported actual v8 Handle ABI size");

/* Each ctx helper either succeeds or poisons and transfers non-returningly to
 * the installed active session fault boundary. No NULL/error continuation and
 * no emitted status polling. These declarations intentionally stay unresolved
 * until the complete runtime/27 guards/ledger/lifecycle source is reviewed.
 * Accessors charge validation work, not IR ticks. All identifiers are fixed
 * domain numeric IDs; returned packet aliases must never be dereferenced by
 * generated code. site_shape uses current lexical SiteExecution, not a name
 * or first projected request. label includes factory capture textual operands. */
const Rt8Site *rt8_site(Rt8Context *, uint32_t site_id);
const Rt8Code *rt8_code(Rt8Context *, uint32_t code_id);
const Rt8Intro *rt8_intro(Rt8Context *, uint32_t intro_id);
const Rt8Instantiation *rt8_instantiation(Rt8Context *, uint32_t use_id);
const Rt8Shape *rt8_shape(Rt8Context *, uint32_t shape_id);
const Rt8Family *rt8_family(Rt8Context *, uint32_t family_id);
const Rt8Variant *rt8_variant(Rt8Context *, uint32_t variant_descriptor_id);
const Rt8Env *rt8_env(Rt8Context *, uint32_t env_id);
const Rt8Shape *rt8_site_shape(Rt8Context *, const Rt8Site *);
const char *rt8_label(Rt8Context *, uint32_t label_id);

/* Constructors retain operands and copy their actual Access. Site follows
 * authority for every node allocator. Factory has one Site per arm, including
 * nullary variants; all arms validate before selected payload acquisition.
 * Fill requires both operands in own mode but allows the same capability and
 * legal live-loan/self-edge knots. Only original ticket changes 1->0 on Fill.
 * View moves preserve the same owner/loan, storage, anchor and counters.
 * All generalize child storage belongs to the enclosing function. */
Rt8Handle *rt8_new_root(Rt8Context *, size_t import8_count, Rt8Handle *const *imports);
Rt8Handle *rt8_new_below(Rt8Context *, Rt8Handle *ceiling, size_t import8_count, Rt8Handle *const *imports);
Rt8Handle *rt8_alloc(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Shape *, Rt8Handle *const *fields, const char *out);
Rt8Handle *rt8_closure(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Code *, Rt8Handle *const *captures, const char *out);
Rt8Handle *rt8_thunk(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Code *, Rt8Handle *const *captures, const char *out);
Rt8Handle *rt8_application(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, Rt8Handle *function, Rt8Handle *argument, const char *out);
Rt8Handle *rt8_application_borrow(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, Rt8Handle *function, Rt8Handle *argument, const char *out);
Rt8Handle *rt8_hole(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Shape *, const char *out);
void rt8_fill(Rt8Context *, Rt8Handle *hole, Rt8Handle *value, const char *hole_variable, const char *value_variable);
Rt8Handle *rt8_retain(Rt8Context *, Rt8Handle *);
void rt8_drop(Rt8Context *, Rt8Handle *);
Rt8Handle *rt8_borrow(Rt8Context *, Rt8Handle *);
void rt8_end_borrow(Rt8Context *, Rt8Handle *);
Rt8Handle *rt8_field(Rt8Context *, Rt8Handle *source, size_t field_index, const char *out, const char *source_variable);
Rt8Handle *rt8_force(Rt8Context *, Rt8Handle *, const char *out, const char *source_variable);
Rt8Handle *rt8_return(Rt8Context *, Rt8Handle *);
void rt8_finish_entry(Rt8Context *);
Rt8Handle *rt8_scalar_i64(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Shape *, int64_t, const char *out);
Rt8Handle *rt8_scalar_bool(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Shape *, int, const char *out);
Rt8Handle *rt8_prim2(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, Rt8ScalarPrimitive, const Rt8Shape *result, Rt8Handle *left, Rt8Handle *right, const char *out);
Rt8Handle *rt8_select_i64(Rt8Context *, Rt8Handle *authority, Rt8Handle *ready_bool, Rt8Handle *then_owner, Rt8Handle *else_owner, const char *out);
Rt8Handle *rt8_construct_nullary(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Family *, const Rt8Variant *, const char *out);
Rt8Handle *rt8_case_i64(Rt8Context *, Rt8Handle *authority, const Rt8Family *, Rt8Handle *ready_scrutinee, size_t arm_count, const Rt8CaseArm *, const char *out);
Rt8Handle *rt8_construct_sum(Rt8Context *, Rt8Handle *authority, const Rt8Site *site, const Rt8Family *, const Rt8Variant *, size_t field_count, Rt8Handle *const *fields, const char *out);
Rt8Handle *rt8_case_fields_i64(Rt8Context *, Rt8Handle *authority, const Rt8Family *, Rt8Handle *ready_scrutinee, size_t arm_count, const Rt8FactoryArm *, const char *out);
void rt8_finish_scalar(Rt8Context *, Rt8Handle *owned_ready_scalar);
void rt8_generic_begin(Rt8Context *, Rt8GenericScope *zeroed_local, const Rt8Intro *, Rt8Handle *authority);
Rt8Handle *rt8_generic_seal(Rt8Context *, Rt8GenericScope *, Rt8Handle *owned_result, const char *out);
Rt8Handle *rt8_instantiate(Rt8Context *, Rt8Handle *owner_or_loan, const Rt8Instantiation *, const char *out, const char *source_variable);
#endif
