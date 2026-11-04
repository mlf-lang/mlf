/* Genuine Stage05B admission/session boundaries and explicit domain surrender.
 * This file neither forwards to the old runtime nor supplies a callback body.
 * Source preparation only; compilation and execution require a separate gate. */
#include "rir8_runtime_internal.h"
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>

static Rt8FaultInfo empty_location(void)
{
    Rt8FaultInfo result = {0};
    result.domain = RT8_NULL;
    result.object = RT8_NULL;
    result.row = RT8_NULL;
    result.field = RT8_NULL;
    result.guard_index = RT8_NULL;
    return result;
}

static void empty_report(Rt8Report *report)
{
    *report = (Rt8Report){0};
    report->location = empty_location();
    report->binding.domain = RT8_NULL;
    report->binding.object = RT8_NULL;
    report->binding.row = RT8_NULL;
    report->binding.field = RT8_NULL;
    report->binding.guard_index = RT8_NULL;
    report->binding.packet.domain = RT8_NULL;
    report->binding.packet.object = RT8_NULL;
    report->binding.packet.row = RT8_NULL;
    report->binding.packet.field = RT8_NULL;
}

static int rejected(Rt8Report *report, uint32_t fault, uint32_t detail)
{
    if (report) {
        empty_report(report);
        report->state = RT8_RUN_FAULT;
        report->fault = fault;
        report->location.status = fault == RT8_FAULT_ACTIVE ?
            RT8_STATUS_STATE : RT8_STATUS_ARGUMENT;
        report->location.phase = RT8_PHASE_ARGUMENTS;
        report->location.detail = detail;
    }
    return 2;
}

static void admission_report(Rt8Report *report, uint32_t fault,
                             const Rt8BindingReport *binding)
{
    if (!report) return;
    empty_report(report);
    report->state = RT8_RUN_FAULT;
    report->fault = fault;
    report->binding = *binding;
    if (fault == RT8_FAULT_ADMISSION) {
        report->location.status = binding->status;
        report->location.phase = binding->phase;
        report->location.detail = binding->detail;
        report->location.region = binding->region;
        report->location.domain_kind = binding->domain_kind;
        report->location.domain = binding->domain;
        report->location.object = binding->object;
        report->location.row = binding->row;
        report->location.field = binding->field;
        report->location.guard_index = binding->guard_index;
    }
}

void rt8_private_report_copy(const Rt8Context *c, Rt8Report *report)
{
    if (!report) return;
    /* This never reads semantic lists, Frames or root descriptors. The output
     * is caller-owned and disjoint; no report/scratch pointer is retained. */
    *report = c->report;
    report->guard_work_used = c->guard_work.used;
    report->guard_work_total = c->guard_work.total;
    report->guard_work_limit = c->guard_work.limit;
}

void rt8_private_checkpoint(Rt8Context *c)
{
    Rt8MemHeader *header = (Rt8MemHeader *)c - 1;
    size_t i;
    /* Fixed lifecycle control is deliberately outside per-entry typed work.
     * It observes custody and never repairs, sweeps or clears abandoned state. */
    if (c->handles || c->live_groups || c->live_nodes || c->live_owners ||
        c->close_first || c->close_last || c->closing || c->force_depth ||
        c->activation_depth || c->frame || c->ledger != header ||
        header->info.previous || header->info.next ||
        header->info.category != RT8_MC_CONTEXT ||
        header->info.requested != sizeof(*header) + sizeof(*c) ||
        c->report.memory.live_blocks != 1 ||
        c->report.memory.live_bytes != (uint64_t)header->info.requested ||
        c->report.categories[RT8_MC_CONTEXT].live_blocks != 1 ||
        c->report.categories[RT8_MC_CONTEXT].live_bytes !=
            (uint64_t)header->info.requested)
        rt8_private_fault(c, RT8_FAULT_INVARIANT);
    for (i = 1; i < RT8_MEMORY_CATEGORIES; ++i) {
        if (c->report.categories[i].live_blocks ||
            c->report.categories[i].live_bytes)
            rt8_private_fault(c, RT8_FAULT_INVARIANT);
    }
}

int rt8_session_snapshot(const Rt8Context *c, Rt8Report *report)
{
    if (!c) return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_NULL_ARGUMENT);
    rt8_private_report_copy(c, report);
    return c->report.state == RT8_RUN_COMPLETE ? 0 : 2;
}

int rt8_session_open(const Rt8Program *program,
                     const Ir8PacketExpectedBindings *expected,
                     Rt8BindingWorkspace *workspace, const Rt8Options *options,
                     Rt8Context **session, Rt8Report *report)
{
    Rt8Options chosen;
    Rt8ProgramView view;
    Rt8BindingReport binding;
    Rt8MemHeader *header;
    Rt8Context *c;
    size_t requested;
    uint32_t status;
    /* Caller storage and both immutable roots have the frozen disjointness
     * and lifetime preconditions. A generated expected tuple must be copied
     * outside its binding root by the caller before fresh admission. */
    if (!program || !expected || !workspace || !session)
        return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_NULL_ARGUMENT);
    if (*session)
        return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_STATE);
    chosen = options ? *options : (Rt8Options){
        UINT64_C(1000000), 0, RT8_MAX_GUARD_WORK
    };
    if (!chosen.guard_work_limit) chosen.guard_work_limit = RT8_MAX_GUARD_WORK;
    if (chosen.guard_work_limit > RT8_MAX_GUARD_WORK)
        return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_COUNT);
    status = rt8_binding_prepare(program, expected, workspace, &view, &binding);
    if (status != RT8_STATUS_OK) {
        admission_report(report, RT8_FAULT_ADMISSION, &binding);
        return 2;
    }
    if (sizeof(*c) > SIZE_MAX - sizeof(*header)) {
        admission_report(report, RT8_FAULT_OVERFLOW, &binding);
        return 2;
    }
    requested = sizeof(*header) + sizeof(*c);
    header = malloc(requested);
    if (!header) {
        admission_report(report, RT8_FAULT_OOM, &binding);
        return 2;
    }
    memset(header, 0, requested);
    c = (Rt8Context *)(header + 1);
    header->info.requested = requested;
    header->info.category = RT8_MC_CONTEXT;
    c->ledger = header;
    *session = c;
    /* c is established before setjmp and never reassigned afterwards. All
     * durable state lives on the heap, not in modified automatic objects. */
    c->program = view;
    c->options = chosen;
    empty_report(&c->report);
    c->report.binding = binding;
    c->guard_work.limit = chosen.guard_work_limit;
    c->fuel_remaining = chosen.fuel;
    /* The fresh zero account cannot overflow: requested was checked in size_t,
     * whose representability in uint64_t is asserted in the actual header. */
    c->report.memory = (Rt8Memory){
        (uint64_t)requested, 0, (uint64_t)requested, (uint64_t)requested,
        1, 0, 1, 1
    };
    c->report.categories[RT8_MC_CONTEXT] = c->report.memory;
    c->api_active = 1;
    if (setjmp(c->failure) == 0) rt8_private_checkpoint(c);
    c->api_active = 0;
    return rt8_session_snapshot(c, report);
}

int rt8_session_step(Rt8Context *c, Rt8Report *report)
{
    if (!c) return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_NULL_ARGUMENT);
    if (c->api_active) return rejected(report, RT8_FAULT_ACTIVE, RT8_DETAIL_STATE);
    /* Poison is inspected BEFORE an abandoned automatic Frame, a Handle, a
     * Group, metadata or the previous jump buffer can be inspected or reused. */
    if (c->report.state != RT8_RUN_COMPLETE)
        return rt8_session_snapshot(c, report);
    c->api_active = 1;
    if (setjmp(c->failure) == 0) {
        Rt8Frame frame = {0};
        rt8_private_checkpoint(c);
        c->finished = 0;
        c->fuel_remaining = c->options.fuel;
        c->guard_work.used = 0;
        c->report.scalar_result_kind = 0;
        c->report.scalar_result = 0;
        frame.kind = RT8_FRAME_ENTRY;
        frame.expected_result_type = RT8_NULL;
        frame.result_identity = RT8_NULL;
        frame.execution.env = rt8_private_table_ref(c, 4, 0) /* Env table domain */;
        frame.execution.kind = IR8_PACKET_ORIGIN_KIND_CONCRETE;
        rt8_private_frame_push(c, &frame, NULL, NULL);
        /* Fresh admission checked this exact typed entry pointer. No externally
         * supplied entry, wrapper-retained pointer or callback replacement. */
        c->report.graph_executed = 1;
        c->program.binding_header.entry(c);
        if (!c->finished) rt8_private_fault(c, RT8_FAULT_INVARIANT);
        rt8_private_frame_pop(c, &frame);
        rt8_private_checkpoint(c);
        rt8_private_bump(c, &c->report.entries_completed);
    }
    /* A fault does not restore frame, release owners, or normalize counters. */
    c->api_active = 0;
    return rt8_session_snapshot(c, report);
}

int rt8_session_close(Rt8Context **session, Rt8Report *report)
{
    Rt8Context *c;
    Rt8MemHeader *header;
    Rt8Memory total, category;
    if (!session || !*session)
        return rejected(report, RT8_FAULT_ARGUMENT, RT8_DETAIL_NULL_ARGUMENT);
    c = *session;
    if (c->api_active) return rejected(report, RT8_FAULT_ACTIVE, RT8_DETAIL_STATE);
    if (c->report.state != RT8_RUN_COMPLETE)
        return rt8_session_snapshot(c, report);
    c->api_active = 1;
    if (setjmp(c->failure) != 0) {
        c->api_active = 0;
        return rt8_session_snapshot(c, report);
    }
    rt8_private_checkpoint(c);
    header = (Rt8MemHeader *)c - 1;
    total = rt8_private_free_preflight(c, &c->report.memory, header->info.requested);
    category = rt8_private_free_preflight(c,
        &c->report.categories[RT8_MC_CONTEXT], header->info.requested);
    /* Two-copy preflight has completed. Report copy, caller-slot surrender and
     * final raw free form a no-fault suffix; Context is the last block. */
    c->report.memory = total;
    c->report.categories[RT8_MC_CONTEXT] = category;
    rt8_private_report_copy(c, report);
    *session = NULL;
    free(header);
    return 0;
}

static void destroy_add(uint64_t *value, uint64_t amount, uint32_t *overflow)
{
    if (UINT64_MAX - *value < amount) {
        *value = UINT64_MAX;
        *overflow = 1;
    } else *value += amount;
}

static void destroy_record(Rt8DestroyReport *destroyed, const Rt8MemHeader *header)
{
    /* Trusted registered headers, including valid category, are an explicit
     * surrender precondition. This is not hostile-header recovery. */
    unsigned category = header->info.category;
    destroy_add(&destroyed->retired_blocks, 1, &destroyed->totals_overflow);
    destroy_add(&destroyed->retired_bytes, (uint64_t)header->info.requested,
                &destroyed->totals_overflow);
    destroy_add(&destroyed->category_blocks[category], 1,
                &destroyed->totals_overflow);
    destroy_add(&destroyed->category_bytes[category],
                (uint64_t)header->info.requested, &destroyed->totals_overflow);
}

int rt8_session_destroy_terminal(Rt8Context **session, Rt8Report *before,
                                 Rt8DestroyReport *destroyed)
{
    Rt8Context *c;
    Rt8MemHeader *context, *header;
    if (!destroyed) return 2;
    *destroyed = (Rt8DestroyReport){0};
    if (!session) { destroyed->status = RT8_DESTROY_INVALID; return 2; }
    c = *session;
    if (!c) { destroyed->status = RT8_DESTROY_EMPTY; return 0; }
    if (c->api_active) { destroyed->status = RT8_DESTROY_ACTIVE; return 2; }
    /* The optional before output is untouched on ACTIVE/INVALID/EMPTY. */
    rt8_private_report_copy(c, before);
    c->api_active = 2;
    context = (Rt8MemHeader *)c - 1;
    destroyed->status = RT8_DESTROY_DONE;
    /* No payload, Frame, Handle, Node, Access, Env, token or callback traversal.
     * Even uninitialized payloads from a partially accounted malloc are safe
     * to surrender through their already linked, trusted raw headers. */
    header = c->ledger;
    while (header) {
        Rt8MemHeader *next = header->info.next;
        if (header != context) {
            destroy_record(destroyed, header);
            free(header);
        }
        header = next;
    }
    destroy_record(destroyed, context);
    *session = NULL;
    free(context);
    return 0;
}

static const char *const memory_names[RT8_MEMORY_CATEGORIES] = {
    "context", "groups", "nodes", "slots", "handles", "captures", "pending"
};
static const char *const rc_names[RT8_RC_CATEGORIES] = {
    "owner", "builder", "pin", "key", "slot"
};

static void memory_json(FILE *output, const Rt8Memory *m)
{
    fprintf(output,
        "{\"allocated_bytes\":%" PRIu64 ",\"freed_bytes\":%" PRIu64
        ",\"live_bytes\":%" PRIu64 ",\"peak_bytes\":%" PRIu64
        ",\"allocations\":%" PRIu64 ",\"frees\":%" PRIu64
        ",\"live_blocks\":%" PRIu64 ",\"peak_blocks\":%" PRIu64 "}",
        m->allocated_bytes, m->freed_bytes, m->live_bytes, m->peak_bytes,
        m->allocations, m->frees, m->live_blocks, m->peak_blocks);
}

static void fault_json(FILE *output, const Rt8FaultInfo *location)
{
    fputc('{', output);
#define LOCATION(name) fprintf(output, "\"" #name "\":%" PRIu32 ",", location->name)
    LOCATION(status); LOCATION(phase); LOCATION(detail); LOCATION(region);
    LOCATION(domain_kind); LOCATION(domain); LOCATION(object); LOCATION(row);
    LOCATION(field);
#undef LOCATION
    fprintf(output, "\"guard_index\":%" PRIu32 "}", location->guard_index);
}

static void packet_json(FILE *output, const Ir8PacketReport *packet)
{
    fputc('{', output);
#define PACKET(name) fprintf(output, "\"" #name "\":%" PRIu32 ",", packet->name)
    PACKET(status); PACKET(phase); PACKET(domain); PACKET(object); PACKET(row);
    PACKET(field); PACKET(detail); PACKET(packet_bytes); PACKET(declared_packet_alignment);
    PACKET(member_bytes_sum); PACKET(padding_bytes); PACKET(directory_entries);
    PACKET(member_objects); PACKET(resolution_access_transport_rows);
    PACKET(workspace_bytes); PACKET(graph_executed); PACKET(source_admitted);
    PACKET(runtime_admitted); PACKET(runtime_guards_executed);
#undef PACKET
    fprintf(output, "\"work_used\":%" PRIu64 "}", packet->work_used);
}

static void binding_json(FILE *output, const Rt8BindingReport *binding)
{
    fputc('{', output);
#define BINDING(name) fprintf(output, "\"" #name "\":%" PRIu32 ",", binding->name)
    BINDING(status); BINDING(phase); BINDING(detail); BINDING(region);
    BINDING(domain_kind); BINDING(domain); BINDING(object); BINDING(row);
    BINDING(field); BINDING(guard_index); BINDING(packet_checked);
    BINDING(packet_bytes); BINDING(binding_bytes); BINDING(runtime_total_static_bytes);
    BINDING(workspace_bytes); BINDING(header_bytes); BINDING(code_bytes);
    BINDING(label_index_bytes); BINDING(label_bytes); BINDING(padding_bytes);
    BINDING(code_count); BINDING(label_count); BINDING(binding_validated);
    BINDING(runtime_admitted); BINDING(source_admitted); BINDING(graph_executed);
    BINDING(runtime_guards_executed);
#undef BINDING
    fprintf(output, "\"work_used\":%" PRIu64 ",\"work_limit\":%" PRIu64
            ",\"packet\":", binding->work_used, binding->work_limit);
    packet_json(output, &binding->packet);
    fputc('}', output);
}

static void report_json(FILE *output, const Rt8Report *report)
{
    size_t i;
    uint64_t increments = 0, decrements = 0;
    int totals_overflow = 0;
    fprintf(output, "],\"state\":%" PRIu32 ",\"fault\":%" PRIu32
            ",\"location\":", report->state, report->fault);
    fault_json(output, &report->location);
    fputs(",\"binding\":", output);
    binding_json(output, &report->binding);
    fputs(",\"memory\":", output);
    memory_json(output, &report->memory);
    fputs(",\"memory_categories\":{", output);
    for (i = 0; i < RT8_MEMORY_CATEGORIES; ++i) {
        if (i) fputc(',', output);
        fprintf(output, "\"%s\":", memory_names[i]);
        memory_json(output, &report->categories[i]);
    }
    fputs("},\"metrics\":{", output);
#define METRIC(name) fprintf(output, "\"" #name "\":%" PRIu64 ",", report->name)
    METRIC(steps); METRIC(groups_allocated); METRIC(groups_closed);
    METRIC(nodes_allocated); METRIC(nodes_freed); METRIC(peak_groups);
    METRIC(peak_nodes); METRIC(peak_owner_handles); METRIC(owner_handle_acquisitions);
    METRIC(owner_handle_releases); METRIC(loan_handle_acquisitions);
    METRIC(loan_handle_releases); METRIC(force_calls); METRIC(max_force_depth);
    METRIC(callback_calls); METRIC(ordinary_calls); METRIC(applications_allocated);
    METRIC(raw_deferred_returns); METRIC(memo_writes); METRIC(internal_memo_slots);
    METRIC(cross_group_memo_slots); METRIC(memo_fast_paths);
    METRIC(groups_closed_during_force); METRIC(borrowed_slot_publications);
    METRIC(ir_retain_ops); METRIC(ir_drop_ops); METRIC(ir_borrow_ops);
    METRIC(ir_end_borrow_ops); METRIC(ir_application_borrow_ops);
    METRIC(max_activation_depth); METRIC(entries_completed);
#undef METRIC
    for (i = 0; i < RT8_RC_CATEGORIES; ++i) {
        fprintf(output, "\"rc_inc_%s\":%" PRIu64 ",\"rc_dec_%s\":%" PRIu64 ",",
                rc_names[i], report->rc_inc[i], rc_names[i], report->rc_dec[i]);
        /* Poison reports can contain deliberately perturbed or partially
         * updated counters. Never wrap a derived observation into a lie. */
        if (UINT64_MAX - increments < report->rc_inc[i]) totals_overflow = 1;
        else increments += report->rc_inc[i];
        if (UINT64_MAX - decrements < report->rc_dec[i]) totals_overflow = 1;
        else decrements += report->rc_dec[i];
    }
    if (totals_overflow)
        fputs("\"rc_inc_sum\":null,\"rc_dec_sum\":null", output);
    else fprintf(output, "\"rc_inc_sum\":%" PRIu64 ",\"rc_dec_sum\":%" PRIu64,
                 increments, decrements);
    fprintf(output,
        "},\"events_emitted\":%" PRIu64 ",\"events_omitted\":%" PRIu64
        ",\"guard_work_used\":%" PRIu64 ",\"guard_work_total\":%" PRIu64
        ",\"guard_work_limit\":%" PRIu64 ",\"guards_checked_mask\":%" PRIu32
        ",\"guards_failed_mask\":%" PRIu32 ",\"graph_executed\":%" PRIu32
        ",\"scalar_result_kind\":%" PRIu32 ",\"scalar_result\":%" PRId64
        ",\"result\":", report->events_emitted, report->events_omitted,
        report->guard_work_used, report->guard_work_total, report->guard_work_limit,
        report->guards_checked_mask, report->guards_failed_mask, report->graph_executed,
        report->scalar_result_kind, report->scalar_result);
    if (report->state == RT8_RUN_COMPLETE &&
        report->scalar_result_kind == IR8_PACKET_SHAPE_KIND_I64)
        fprintf(output, "{\"kind\":\"i64\",\"value\":%" PRId64 "}", report->scalar_result);
    else if (report->state == RT8_RUN_COMPLETE &&
             report->scalar_result_kind == IR8_PACKET_SHAPE_KIND_BOOL)
        fprintf(output, "{\"kind\":\"bool\",\"value\":%s}",
                report->scalar_result ? "true" : "false");
    else fputs("null", output);
    fputs(",\"cleanup_claim\":", output);
    fputs(report->state == RT8_RUN_COMPLETE ?
          "\"all runtime-owned requested blocks freed\"}" :
          "\"terminal fault; ordinary cleanup unsupported\"}", output);
}

static void destroy_json(FILE *output, const Rt8DestroyReport *destroyed)
{
    size_t i;
    fprintf(output, "{\"lifecycle\":\"" RT8_LIFECYCLE_ID
            "\",\"status\":%" PRIu32 ",\"retired_blocks\":%" PRIu64
            ",\"retired_bytes\":%" PRIu64 ",\"totals_overflow\":%s,\"categories\":{",
            destroyed->status, destroyed->retired_blocks, destroyed->retired_bytes,
            destroyed->totals_overflow ? "true" : "false");
    for (i = 0; i < RT8_MEMORY_CATEGORIES; ++i) {
        if (i) fputc(',', output);
        fprintf(output, "\"%s\":{\"blocks\":%" PRIu64 ",\"bytes\":%" PRIu64 "}",
                memory_names[i], destroyed->category_blocks[i], destroyed->category_bytes[i]);
    }
    fputs("}}", output);
}

static int run_loop(const Rt8Program *program,
                    const Ir8PacketExpectedBindings *expected,
                    Rt8BindingWorkspace *workspace, const Rt8Options *options,
                    uint64_t repetitions, FILE *output, Rt8Report *snapshot,
                    Rt8DestroyReport *terminal)
{
    Rt8Context *c = NULL;
    uint64_t i;
    int result;
    if (terminal) {
        *terminal = (Rt8DestroyReport){0};
        terminal->status = RT8_DESTROY_EMPTY;
    }
    if (!repetitions)
        return rejected(snapshot, RT8_FAULT_ARGUMENT, RT8_DETAIL_COUNT);
    result = rt8_session_open(program, expected, workspace, options, &c, snapshot);
    if (result == 0) {
        c->output = output;
        for (i = 0; i < repetitions; ++i) {
            result = rt8_session_step(c, snapshot);
            if (result) break;
        }
    }
    if (c) result = rt8_session_close(&c, snapshot);
    if (result && c && terminal) {
        /* Each failing API has already unwound and cleared api_active. Return
         * the original evaluation error, with surrender in a separate receipt. */
        (void)rt8_session_destroy_terminal(&c, NULL, terminal);
    }
    /* Without terminal opt-in, poison intentionally remains a diagnostic
     * domain. Callers needing its address use explicit session APIs instead. */
    return result;
}

int rt8_run_repeat(const Rt8Program *program,
                   const Ir8PacketExpectedBindings *expected,
                   Rt8BindingWorkspace *workspace, const Rt8Options *options,
                   uint64_t repetitions, FILE *output, Rt8Report *report)
{
    Rt8Report snapshot;
    int result;
    if (output) fputs("{\"schema\":\"resource-ir-v8-run/1\",\"events\":[", output);
    result = run_loop(program, expected, workspace, options, repetitions,
                      output, &snapshot, NULL);
    if (report) *report = snapshot;
    if (output) { report_json(output, &snapshot); fputc('\n', output); }
    return result;
}

int rt8_run(const Rt8Program *program, const Ir8PacketExpectedBindings *expected,
            Rt8BindingWorkspace *workspace, const Rt8Options *options,
            FILE *output, Rt8Report *report)
{
    return rt8_run_repeat(program, expected, workspace, options, 1, output, report);
}

int rt8_run_repeat_destroy_fault(const Rt8Program *program,
                                const Ir8PacketExpectedBindings *expected,
                                Rt8BindingWorkspace *workspace,
                                const Rt8Options *options, uint64_t repetitions,
                                FILE *output, Rt8Report *report,
                                Rt8DestroyReport *destroyed)
{
    Rt8Report snapshot;
    Rt8DestroyReport terminal;
    int result;
    if (output) fputs("{\"schema\":\"resource-ir-v8-terminal-run/1\","
                      "\"evaluation\":{\"schema\":\"resource-ir-v8-run/1\",\"events\":[", output);
    result = run_loop(program, expected, workspace, options, repetitions,
                      output, &snapshot, &terminal);
    if (report) *report = snapshot;
    if (destroyed) *destroyed = terminal;
    if (output) {
        report_json(output, &snapshot);
        fputs(",\"destruction\":", output);
        destroy_json(output, &terminal);
        fputs("}\n", output);
    }
    return result;
}
