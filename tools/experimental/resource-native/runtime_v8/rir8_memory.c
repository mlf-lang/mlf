/* Genuine Stage05B ownership kernel. Source preparation, not qualification.
 * All dynamic runtime storage has one raw, max-aligned ledger header. Typed
 * validation is separate from trusted operational retirement and publication. */
#include "rir8_runtime_internal.h"
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>

_Noreturn void rt8_private_fault(Rt8Context *c, uint32_t fault)
{
    /* A valid active boundary is a private-helper precondition. Never inspect
     * a Frame here: a previous nonlocal transfer may have abandoned it. */
    if (c->report.state != RT8_RUN_FAULT) {
        c->report.state = RT8_RUN_FAULT;
        c->report.fault = fault;
    }
    longjmp(c->failure, 1);
}

void rt8_private_add(Rt8Context *c, uint64_t *value, uint64_t amount)
{
    if (UINT64_MAX - *value < amount)
        rt8_private_fault(c, RT8_FAULT_OVERFLOW);
    *value += amount;
}

void rt8_private_bump(Rt8Context *c, uint64_t *value)
{
    rt8_private_add(c, value, UINT64_C(1));
}

uint64_t rt8_private_identity(Rt8Context *c, uint64_t *value)
{
    rt8_private_bump(c, value);
    return *value;
}

void rt8_private_peak(uint64_t *peak, uint64_t value)
{
    if (value > *peak) *peak = value;
}

void rt8_private_tick(Rt8Context *c)
{
    if (c->frame && c->frame->returned)
        rt8_private_fault(c, RT8_FAULT_INVARIANT);
    rt8_private_bump(c, &c->report.steps);
    if (!c->fuel_remaining) rt8_private_fault(c, RT8_FAULT_FUEL);
    --c->fuel_remaining;
}

static void account_alloc(Rt8Context *c, Rt8Memory *m, size_t requested)
{
    rt8_private_add(c, &m->allocated_bytes, (uint64_t)requested);
    rt8_private_add(c, &m->live_bytes, (uint64_t)requested);
    rt8_private_bump(c, &m->allocations);
    rt8_private_bump(c, &m->live_blocks);
    rt8_private_peak(&m->peak_bytes, m->live_bytes);
    rt8_private_peak(&m->peak_blocks, m->live_blocks);
}

Rt8Memory rt8_private_free_preflight(Rt8Context *c, const Rt8Memory *m,
                                   size_t requested)
{
    Rt8Memory result;
    if (m->live_bytes < (uint64_t)requested || !m->live_blocks)
        rt8_private_fault(c, RT8_FAULT_INVARIANT);
    if (UINT64_MAX - m->freed_bytes < (uint64_t)requested ||
        m->frees == UINT64_MAX)
        rt8_private_fault(c, RT8_FAULT_OVERFLOW);
    result = *m;
    result.freed_bytes += (uint64_t)requested;
    result.live_bytes -= (uint64_t)requested;
    ++result.frees;
    --result.live_blocks;
    return result;
}

void *rt8_private_alloc(Rt8Context *c, size_t bytes, unsigned category)
{
    size_t requested;
    Rt8MemHeader *h;
    void *result;
    if (category >= RT8_MEMORY_CATEGORIES)
        rt8_private_fault(c, RT8_FAULT_INVARIANT);
    if (bytes > SIZE_MAX - sizeof(Rt8MemHeader))
        rt8_private_fault(c, RT8_FAULT_OVERFLOW);
    requested = sizeof(Rt8MemHeader) + bytes;
    h = malloc(requested);
    if (!h) rt8_private_fault(c, RT8_FAULT_OOM);
    h->info.previous = NULL;
    h->info.next = c->ledger;
    h->info.requested = requested;
    h->info.category = category;
    if (c->ledger) c->ledger->info.previous = h;
    c->ledger = h;
    /* Registration precedes BOTH possibly failing accounting operations.
     * A partial accounting history remains genuine and terminally surrenderable. */
    account_alloc(c, &c->report.memory, requested);
    account_alloc(c, &c->report.categories[category], requested);
    result = h + 1;
    memset(result, 0, bytes);
    return result;
}

void *rt8_private_array(Rt8Context *c, size_t count, size_t bytes,
                        unsigned category)
{
    if (!count) return NULL;
    if (!bytes || count > SIZE_MAX / bytes)
        rt8_private_fault(c, RT8_FAULT_OVERFLOW);
    return rt8_private_alloc(c, count * bytes, category);
}

void rt8_private_free(Rt8Context *c, void *payload)
{
    Rt8MemHeader *h;
    Rt8Memory total, category;
    if (!payload) return;
    /* Only a trusted registered payload reaches retirement. External-pointer
     * provenance belongs to the charged preflight, never this suffix. */
    h = (Rt8MemHeader *)payload - 1;
    if (h->info.category >= RT8_MEMORY_CATEGORIES)
        rt8_private_fault(c, RT8_FAULT_INVARIANT);
    total = rt8_private_free_preflight(c, &c->report.memory, h->info.requested);
    category = rt8_private_free_preflight(c,
        &c->report.categories[h->info.category], h->info.requested);
    /* From this commit through free: no fallible work, event or callback. */
    c->report.memory = total;
    c->report.categories[h->info.category] = category;
    if (h->info.previous) h->info.previous->info.next = h->info.next;
    else c->ledger = h->info.next;
    if (h->info.next) h->info.next->info.previous = h->info.previous;
    free(h);
}

size_t rt8_private_extent(Rt8Context *c, const void *payload, unsigned category)
{
    Rt8MemHeader *h;
    rt8_private_guard_seen(c, 2);
    rt8_private_charge(c, 2);
    if (!payload || category >= RT8_MEMORY_CATEGORIES)
        rt8_private_guard_fault(c, RT8_STATUS_STATE, RT8_DETAIL_LENGTH,
                               2, RT8_NULL, RT8_NULL, RT8_NULL);
    rt8_private_charge(c, sizeof(h));
    h = c->ledger;
    for (;;) {
        rt8_private_charge(c, 1);
        if (!h) break;
        /* Header links are trusted allocator control storage. Compare exact
         * payload addresses before reading or subtracting any supplied pointer. */
        rt8_private_charge(c, sizeof(*h) + UINT64_C(3));
        if ((const void *)(h + 1) == payload) {
            if (h->info.category != category ||
                h->info.requested < sizeof(*h))
                rt8_private_guard_fault(c, RT8_STATUS_STATE, RT8_DETAIL_LENGTH,
                                       2, RT8_NULL, RT8_NULL, RT8_NULL);
            return h->info.requested - sizeof(*h);
        }
        h = h->info.next;
    }
    rt8_private_guard_fault(c, RT8_STATUS_STATE, RT8_DETAIL_UNREGISTERED,
                           2, RT8_NULL, RT8_NULL, RT8_NULL);
}

Rt8Handle *rt8_private_live(Rt8Context *c, Rt8Handle *candidate)
{
    Rt8Handle *h;
    rt8_private_guard_seen(c, 7);
    rt8_private_charge(c, sizeof(h));
    h = c->handles;
    for (;;) {
        rt8_private_charge(c, 1);
        if (!h) break;
        rt8_private_charge(c, sizeof(h->next) + UINT64_C(2));
        if (h == candidate) {
            /* Registry nodes themselves are trusted. Candidate bytes are read
             * only after an exact match; no candidate->next traversal. */
            rt8_private_charge(c, sizeof(*h) + UINT64_C(3));
            if (h->storage_kind == RT8_STORAGE_HEAP) {
                if (rt8_private_extent(c, h, RT8_MC_HANDLE) != sizeof(*h))
                    rt8_private_guard_fault(c, RT8_STATUS_OWNERSHIP,
                        RT8_DETAIL_LENGTH, 7, RT8_NULL, RT8_NULL, RT8_NULL);
            } else if (h->storage_kind != RT8_STORAGE_LOCAL) {
                rt8_private_guard_fault(c, RT8_STATUS_OWNERSHIP,
                    RT8_DETAIL_STATE, 7, RT8_NULL, RT8_NULL, RT8_NULL);
            }
            if (rt8_private_extent(c, h->group, RT8_MC_GROUP) != sizeof(Rt8Group))
                rt8_private_guard_fault(c, RT8_STATUS_OWNERSHIP,
                    RT8_DETAIL_LENGTH, 7, RT8_NULL, RT8_NULL, RT8_NULL);
            rt8_private_charge(c, UINT64_C(10));
            if (!h->id || h->id > c->next_handle || !h->group->id ||
                h->group->id > c->next_group || !h->group->count)
                rt8_private_guard_fault(c, RT8_STATUS_OWNERSHIP,
                    RT8_DETAIL_OWNER, 7, RT8_NULL, RT8_NULL, RT8_NULL);
            return h;
        }
        h = h->next;
    }
    rt8_private_guard_fault(c, RT8_STATUS_OWNERSHIP, RT8_DETAIL_UNREGISTERED,
                           7, RT8_NULL, RT8_NULL, RT8_NULL);
}

static void quoted(FILE *output, const char *value)
{
    const unsigned char *p;
    if (!value) { fputs("null", output); return; }
    fputc('"', output);
    /* Values are previously authenticated bounded immutable text, or fixed
     * common literals. Rendering adds no metadata proof or guard-work failure. */
    for (p = (const unsigned char *)value; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            fputc('\\', output);
            fputc(*p, output);
        } else if (*p < 32) {
            fprintf(output, "\\u%04x", (unsigned)*p);
        } else fputc(*p, output);
    }
    fputc('"', output);
}

Rt8EventReservation rt8_private_event_prepare(Rt8Context *c)
{
    Rt8EventReservation event = {
        c->report.events_emitted, c->report.events_omitted, 0
    };
    if (!c->options.event_limit) return event;
    if (event.emitted >= c->options.event_limit) {
        rt8_private_bump(c, &event.omitted);
    } else {
        rt8_private_bump(c, &event.emitted);
        event.write = c->output != NULL;
    }
    return event;
}

int rt8_private_event_commit(Rt8Context *c, const char *kind,
                             Rt8EventReservation event)
{
    /* Reservation is immediate-use, with no intervening event. No fault is
     * possible after a caller has committed a view/frame/token transition. */
    c->report.events_emitted = event.emitted;
    c->report.events_omitted = event.omitted;
    if (!event.write) return 0;
    if (event.emitted > 1) fputc(',', c->output);
    fputs("{\"event\":", c->output);
    quoted(c->output, kind);
    return 1;
}

int rt8_private_event(Rt8Context *c, const char *kind)
{
    Rt8EventReservation reservation = rt8_private_event_prepare(c);
    return rt8_private_event_commit(c, kind, reservation);
}

void rt8_private_num(Rt8Context *c, const char *key, uint64_t value)
{
    fputc(',', c->output);
    quoted(c->output, key);
    fprintf(c->output, ":%" PRIu64, value);
}

void rt8_private_str(Rt8Context *c, const char *key, const char *value)
{
    fputc(',', c->output);
    quoted(c->output, key);
    fputc(':', c->output);
    quoted(c->output, value);
}

void rt8_private_bool(Rt8Context *c, const char *key, int value)
{
    fputc(',', c->output);
    quoted(c->output, key);
    fputs(value ? ":true" : ":false", c->output);
}

void rt8_private_end_event(Rt8Context *c)
{
    fputc('}', c->output);
}

static const char *state_name(uint32_t state)
{
    switch (state) {
    case RT8_NS_READY: return "READY";
    case RT8_NS_HOLE: return "HOLE";
    case RT8_NS_INDIRECT: return "INDIRECT";
    case RT8_NS_THUNK: return "THUNK";
    case RT8_NS_CLOSURE: return "CLOSURE";
    case RT8_NS_APPLICATION: return "APPLICATION";
    case RT8_NS_BUSY: return "BUSY";
    case RT8_NS_MEMO: return "MEMO";
    default: return "INVALID";
    }
}

void rt8_private_slot_event(Rt8Context *c, const char *kind, Rt8Node *host,
                            const char *name, Rt8Node *target,
                            const char *reason)
{
    if (rt8_private_event(c, kind)) {
        rt8_private_num(c, "host", host->id);
        rt8_private_num(c, "host_group", host->group->id);
        rt8_private_str(c, "field", name);
        rt8_private_num(c, "target", target->id);
        rt8_private_num(c, "target_group", target->group->id);
        rt8_private_str(c, "target_state", state_name(target->state));
        rt8_private_bool(c, "internal", host->group == target->group);
        rt8_private_str(c, "reason", reason);
        rt8_private_end_event(c);
    }
}

void rt8_private_inc(Rt8Context *c, Rt8Group *group, unsigned role)
{
    /* role and group were preflighted or created here. These are operational
     * counters, not typed-work reservations and not metadata validation. */
    rt8_private_bump(c, &c->rc_inc_total);
    rt8_private_bump(c, &group->count);
    rt8_private_bump(c, &c->report.rc_inc[role]);
}

Rt8Handle *rt8_private_handle(Rt8Context *c, Rt8Group *group, Rt8Node *node,
                              const Rt8Access *access, Rt8Handle *anchor,
                              unsigned role)
{
    Rt8Handle *h;
    /* The caller supplies an authenticated exact owner anchor, if any. Field
     * and instantiated loans need not equal their anchor's Node/group/Access. */
    if (anchor) rt8_private_bump(c, &anchor->loans);
    h = rt8_private_alloc(c, sizeof(*h), RT8_MC_HANDLE);
    h->storage_kind = RT8_STORAGE_HEAP;
    h->id = rt8_private_identity(c, &c->next_handle);
    h->group = group;
    h->node = node;
    h->anchor = anchor;
    h->role = role;
    h->access = access;
    h->fill_ticket = 0;
    h->next = c->handles;
    if (c->handles) c->handles->previous = h;
    c->handles = h;
    if (anchor) rt8_private_bump(c, &c->report.loan_handle_acquisitions);
    else {
        rt8_private_inc(c, group, role);
        rt8_private_bump(c, &c->live_owners);
        rt8_private_bump(c, &c->report.owner_handle_acquisitions);
        rt8_private_peak(&c->report.peak_owner_handles, c->live_owners);
    }
    return h;
}

Rt8Handle *rt8_private_acquire(Rt8Context *c, Rt8Node *node,
                               const Rt8Access *access)
{
    return rt8_private_handle(c, node->group, node, access, NULL, RT8_RC_OWNER);
}

Rt8Handle *rt8_private_local(Rt8Context *c, Rt8Handle *h)
{
    h->scope = c->frame ? c->frame->id : 0;
    return h;
}

static void retire_storage(Rt8Context *c, Rt8Handle *h, Rt8StorageKind kind)
{
    if (kind == RT8_STORAGE_HEAP) rt8_private_free(c, h);
    else memset(h, 0, sizeof(*h)); /* preflight guarantees LOCAL */
}

void rt8_private_drop_prepared(Rt8Context *c, Rt8Handle *h)
{
    Rt8StorageKind kind = h->storage_kind;
    Rt8Group *group = h->group;
    unsigned role = h->role;
    int owning = h->anchor == NULL;
    /* The entire capability tuple, no dependent loans, exact owner anchor,
     * and live storage were checked before effects. No late registry scan. */
    if (h->anchor) {
        --h->anchor->loans;
        rt8_private_bump(c, &c->report.loan_handle_releases);
    } else {
        --c->live_owners;
        rt8_private_bump(c, &c->report.owner_handle_releases);
    }
    if (h->previous) h->previous->next = h->next;
    else c->handles = h->next;
    if (h->next) h->next->previous = h->previous;
    retire_storage(c, h, kind);
    if (owning) rt8_private_dec(c, group, role);
}

Rt8Handle *rt8_private_escape_prepared(Rt8Context *c, Rt8Handle *source)
{
    Rt8Handle *destination;
    if (source->storage_kind == RT8_STORAGE_HEAP) return source;
    /* Valid LOCAL owner, ticket rule and no dependent loans are preflighted.
     * OOM leaves the old owner live. Promotion preserves its exact capability,
     * including Access and ticket; it creates no logical acquire/release. */
    destination = rt8_private_alloc(c, sizeof(*destination), RT8_MC_HANDLE);
    *destination = *source;
    destination->storage_kind = RT8_STORAGE_HEAP;
    if (destination->previous) destination->previous->next = destination;
    else c->handles = destination;
    if (destination->next) destination->next->previous = destination;
    memset(source, 0, sizeof(*source));
    return destination;
}

void rt8_private_dec(Rt8Context *c, Rt8Group *group, unsigned role)
{
    if (!group->count) rt8_private_fault(c, RT8_FAULT_INVARIANT);
    --group->count;
    rt8_private_bump(c, &c->rc_dec_total);
    rt8_private_bump(c, &c->report.rc_dec[role]);
    if (!group->count) {
        if (c->close_last) c->close_last->queue_next = group;
        else c->close_first = group;
        c->close_last = group;
    }
    if (c->closing) return;
    c->closing = 1;
    while (c->close_first) {
        Rt8Group *dead = c->close_first;
        Rt8Node *node;
        c->close_first = dead->queue_next;
        if (!c->close_first) c->close_last = NULL;
        if (dead->count) rt8_private_fault(c, RT8_FAULT_INVARIANT);
        if (rt8_private_event(c, "close_group")) {
            uint64_t internal = 0, cross = 0;
            for (node = dead->first; node; node = node->next) {
                size_t i;
                for (i = 0; i < node->used; ++i) {
                    if (node->slots[i].target->group == dead)
                        rt8_private_bump(c, &internal);
                    else rt8_private_bump(c, &cross);
                }
            }
            rt8_private_num(c, "group", dead->id);
            rt8_private_num(c, "members", dead->members);
            rt8_private_num(c, "force_depth", c->force_depth);
            rt8_private_num(c, "live_groups_before", c->live_groups);
            rt8_private_num(c, "internal_slots", internal);
            rt8_private_num(c, "cross_slots", cross);
            rt8_private_end_event(c);
        }
        if (c->force_depth)
            rt8_private_bump(c, &c->report.groups_closed_during_force);
        /* Pass one removes every owning edge while ALL member nodes and all
         * newly queued targets remain alive. Internal knots do not own RC. */
        for (node = dead->first; node; node = node->next) {
            size_t i;
            for (i = 0; i < node->used; ++i) {
                Rt8Slot *slot = &node->slots[i];
                Rt8Node *target = slot->target;
                rt8_private_slot_event(c, "slot_remove", node,
                                      slot->name, target, "group_close");
                if (target->group != dead)
                    rt8_private_dec(c, target->group, RT8_RC_SLOT);
            }
            node->used = 0;
        }
        /* Pass two cannot leave a later internal edge pointing to a freed
         * member. Any failure preserves raw ledger custody without rollback. */
        node = dead->first;
        while (node) {
            Rt8Node *next = node->next;
            rt8_private_free(c, node->slots);
            rt8_private_free(c, node);
            rt8_private_bump(c, &c->report.nodes_freed);
            --c->live_nodes;
            node = next;
        }
        rt8_private_free(c, dead);
        rt8_private_bump(c, &c->report.groups_closed);
        --c->live_groups;
    }
    c->closing = 0;
}

Rt8Handle *rt8_private_new_group(Rt8Context *c)
{
    Rt8Group *group = rt8_private_alloc(c, sizeof(*group), RT8_MC_GROUP);
    Rt8Handle *handle;
    group->id = rt8_private_identity(c, &c->next_group);
    rt8_private_bump(c, &c->live_groups);
    rt8_private_bump(c, &c->report.groups_allocated);
    rt8_private_peak(&c->report.peak_groups, c->live_groups);
    handle = rt8_private_handle(c, group, NULL, NULL, NULL, RT8_RC_BUILDER);
    if (rt8_private_event(c, "new_group")) {
        rt8_private_num(c, "group", group->id);
        rt8_private_end_event(c);
    }
    return rt8_private_local(c, handle);
}

Rt8Node *rt8_private_new_node(Rt8Context *c, Rt8Group *group,
                             const Rt8SiteFacts *facts, uint32_t state,
                             const Rt8Code *code, size_t capacity)
{
    Rt8Node *node;
    uint32_t storage;
    size_t bytes;
    /* facts and capacity are immediate-use authenticated construction facts.
     * Physical storage uses the OWN SiteExecution shape, never a projection. */
    if (facts->shape.kind == IR8_PACKET_SHAPE_KIND_I64 ||
        facts->shape.kind == IR8_PACKET_SHAPE_KIND_BOOL) {
        bytes = sizeof(Rt8ScalarNode);
        storage = RT8_STORAGE_CLASS_SCALAR;
    } else if (facts->shape.kind == IR8_PACKET_SHAPE_KIND_SUM) {
        bytes = sizeof(Rt8SumNode);
        storage = RT8_STORAGE_CLASS_SUM;
    } else {
        bytes = sizeof(Rt8Node);
        storage = RT8_STORAGE_CLASS_BASE;
    }
    node = rt8_private_alloc(c, bytes, RT8_MC_NODE);
    node->id = rt8_private_identity(c, &c->next_node);
    node->group = group;
    node->shape = facts->shape_ref;
    node->code = code;
    node->state = state;
    node->origin_site = facts->site_ref;
    node->origin = facts->origin;
    node->storage_class = storage;
    node->capacity = capacity;
    node->slots = rt8_private_array(c, capacity, sizeof(Rt8Slot), RT8_MC_SLOTS);
    if (group->last) group->last->next = node;
    else group->first = node;
    group->last = node;
    rt8_private_bump(c, &group->members);
    /* The constructor records nodes_allocated/live_nodes/peak_nodes AFTER all
     * initial slot publications and BEFORE owner acquisition, retaining the
     * inherited partial-history order. This primitive does not count twice. */
    return node;
}

void rt8_private_publish_prepared(Rt8Context *c, Rt8Node *host,
                                 const char *name, Rt8Node *target,
                                 const Rt8Access *access)
{
    /* Exact capacity/role/name/type/origin/extent/support have already passed.
     * This forward phase cannot make a new typed or work-limit failure. */
    if (host->group != target->group)
        rt8_private_inc(c, target->group, RT8_RC_SLOT);
    host->slots[host->used++] = (Rt8Slot){ name, target, access };
    rt8_private_slot_event(c, "slot_install", host, name, target, "publication");
}

void rt8_private_clear_prepared(Rt8Context *c, Rt8Node *node)
{
    size_t count = node->used, i;
    /* Acquired owners or existing host support protect later targets. Unused
     * cells are not edges and may retain stale, never-dereferenced bytes. */
    node->used = 0;
    for (i = 0; i < count; ++i) {
        Rt8Slot *slot = &node->slots[i];
        Rt8Node *target = slot->target;
        rt8_private_slot_event(c, "slot_remove", node,
                              slot->name, target, "payload_clear");
        if (target->group != node->group)
            rt8_private_dec(c, target->group, RT8_RC_SLOT);
    }
}
