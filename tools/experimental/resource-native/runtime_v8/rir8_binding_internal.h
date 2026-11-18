/* Private bounded readers. A view is not a public admission credential. */
#ifndef RIR8_BINDING_INTERNAL_H
#define RIR8_BINDING_INTERNAL_H
#include "rir8_binding.h"

typedef struct Rt8Work {
    uint64_t used;
    uint64_t total;
    uint64_t limit;
} Rt8Work;

typedef struct Rt8Diagnostic {
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
} Rt8Diagnostic;

typedef struct Rt8ProgramView {
    Rt8Program program;
    Rt8BindingHeader binding_header;
    Ir8PacketProgramHeader packet_header;
    Ir8PacketTypedHeader typed_header;
    Ir8PacketObjectDirectoryEntry string_pool;
} Rt8ProgramView;

typedef struct Rt8ReadState {
    Rt8Work * work;
    Rt8Diagnostic * diagnostic;
} Rt8ReadState;

_Static_assert(sizeof(Rt8Work) <= UINT32_MAX, "Rt8Work size fits uint32_t");
_Static_assert(_Alignof(Rt8Work) <= UINT32_MAX, "Rt8Work alignment fits uint32_t");
_Static_assert(sizeof(Rt8Diagnostic) <= UINT32_MAX, "Rt8Diagnostic size fits uint32_t");
_Static_assert(_Alignof(Rt8Diagnostic) <= UINT32_MAX, "Rt8Diagnostic alignment fits uint32_t");
_Static_assert(sizeof(Rt8ProgramView) <= UINT32_MAX, "Rt8ProgramView size fits uint32_t");
_Static_assert(_Alignof(Rt8ProgramView) <= UINT32_MAX, "Rt8ProgramView alignment fits uint32_t");
_Static_assert(sizeof(Rt8ReadState) <= UINT32_MAX, "Rt8ReadState size fits uint32_t");
_Static_assert(_Alignof(Rt8ReadState) <= UINT32_MAX, "Rt8ReadState alignment fits uint32_t");

/* ReadState work/diagnostic storage is valid and writable; initial diagnostic
 * status is OK, absent coordinates are RT8_NULL. Failed reservations preserve
 * both counters. Row/ref/auth outputs are unchanged on failure. A fresh prepare
 * zeroes its output view on failure and retains no scratch/report pointer.
 * Reader views originate only from fresh prepare and borrow immutable roots.
 * Output storage must not overlap the view, roots, state or state pointees. */
uint32_t rt8_binding_prepare(const Rt8Program *, const Ir8PacketExpectedBindings *, Rt8BindingWorkspace *, Rt8ProgramView *, Rt8BindingReport *);
uint32_t rt8_view_table_read(const Rt8ProgramView *, uint32_t domain, uint32_t row, void *out, size_t out_bytes, Rt8ReadState *);
uint32_t rt8_view_descriptor_read(const Rt8ProgramView *, uint32_t domain, uint32_t row, void *out, size_t out_bytes, Rt8ReadState *);
uint32_t rt8_view_object_read(const Rt8ProgramView *, uint32_t object, uint32_t element, uint32_t row, void *out, size_t out_bytes, Rt8ReadState *);
uint32_t rt8_view_table_ref(const Rt8ProgramView *, uint32_t domain, uint32_t row, const void **out, Rt8ReadState *);
uint32_t rt8_view_descriptor_ref(const Rt8ProgramView *, uint32_t domain, uint32_t row, const void **out, Rt8ReadState *);
uint32_t rt8_view_table_auth(const Rt8ProgramView *, uint32_t domain, const void *reference, uint32_t *row, Rt8ReadState *);
uint32_t rt8_view_descriptor_auth(const Rt8ProgramView *, uint32_t domain, const void *reference, uint32_t *row, Rt8ReadState *);
uint32_t rt8_view_code_read(const Rt8ProgramView *, uint32_t code_id, Rt8Code *out, Rt8ReadState *);
uint32_t rt8_view_code_ref(const Rt8ProgramView *, uint32_t code_id, const Rt8Code **out, Rt8ReadState *);
uint32_t rt8_view_code_auth(const Rt8ProgramView *, const Rt8Code *, uint32_t *code_id, Rt8ReadState *);
uint32_t rt8_view_label(const Rt8ProgramView *, uint32_t label_id, const char **out, Rt8ReadState *);
uint32_t rt8_view_label_auth(const Rt8ProgramView *, const char *, uint32_t *label_id, Rt8ReadState *);
uint32_t rt8_work_reserve(Rt8ReadState *, uint64_t units);
#endif
