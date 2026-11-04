#include "allocation_observer.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

/* Qualification-only observer of runtime malloc/calloc/free. It does not know
 * about MemHeader, frames, groups, nodes, handles, or semantic ownership. Its
 * map is static; libc allocation used by FILE/stdio is deliberately outside
 * the intercepted translation unit and outside the reported memory scope. */
#define OBSERVER_CAPACITY 4096u
_Static_assert(SIZE_MAX <= UINT64_MAX, "observer requires size_t at most 64 bits");
typedef struct { void *pointer; size_t requested; } ObservedBlock;
static ObservedBlock blocks[OBSERVER_CAPACITY];
static RtMemory memory;
static uintptr_t context_address;
static uint64_t context_requested_bytes;
static int context_seen, context_freed, last_free_was_context, reported;

static _Noreturn void observer_fail(const char *reason) {
    fputs("runtime allocation observer failure: ", stderr);
    fputs(reason, stderr);
    fputc('\n', stderr);
    abort();
}
static uint64_t checked_add(uint64_t a, uint64_t b) {
    if (UINT64_MAX - a < b) observer_fail("counter overflow");
    return a + b;
}
static size_t available_slot(void) {
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (!blocks[i].pointer) return i;
    }
    observer_fail("live pointer map capacity exhausted");
}
static RtMemory allocation_preflight(size_t requested) {
    if (reported) observer_fail("allocation after final observer report");
    RtMemory next = memory;
    next.allocated_bytes = checked_add(next.allocated_bytes, (uint64_t)requested);
    next.live_bytes = checked_add(next.live_bytes, (uint64_t)requested);
    next.allocations = checked_add(next.allocations, 1);
    next.live_blocks = checked_add(next.live_blocks, 1);
    if (next.live_bytes > next.peak_bytes) next.peak_bytes = next.live_bytes;
    if (next.live_blocks > next.peak_blocks) next.peak_blocks = next.live_blocks;
    return next;
}
static void register_allocation(void *pointer, size_t requested, size_t slot,
                                const RtMemory *next) {
    if (!pointer) return; /* Failed real allocation creates no physical block. */
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (blocks[i].pointer == pointer) observer_fail("duplicate live allocator pointer");
    }
    blocks[slot].pointer = pointer;
    blocks[slot].requested = requested;
    memory = *next;
    if (!context_seen) {
        /* Source wrapper's first runtime allocation is the separately malloc'd
         * context. This order is validated independently against native source. */
        context_seen = 1;
        context_address = (uintptr_t)pointer;
        context_requested_bytes = (uint64_t)requested;
    }
}
void *rir_observer_malloc(size_t size) {
    size_t slot = available_slot();
    RtMemory next = allocation_preflight(size);
    void *pointer = malloc(size);
    register_allocation(pointer, size, slot, &next);
    return pointer;
}
void *rir_observer_calloc(size_t count, size_t size) {
    if (size && count > SIZE_MAX / size) observer_fail("calloc size overflow");
    size_t requested = count * size;
    size_t slot = available_slot();
    RtMemory next = allocation_preflight(requested);
    void *pointer = calloc(count, size);
    register_allocation(pointer, requested, slot, &next);
    return pointer;
}
void rir_observer_free(void *pointer) {
    if (!pointer) return;
    if (reported) observer_fail("free after final observer report");
    size_t slot = OBSERVER_CAPACITY;
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (blocks[i].pointer == pointer) { slot = i; break; }
    }
    if (slot == OBSERVER_CAPACITY) observer_fail("unmatched or repeated free");
    uint64_t requested = (uint64_t)blocks[slot].requested;
    if (!memory.live_blocks || memory.live_bytes < requested)
        observer_fail("physical live-counter underflow");
    RtMemory next = memory;
    next.freed_bytes = checked_add(next.freed_bytes, requested);
    next.frees = checked_add(next.frees, 1);
    next.live_bytes -= requested;
    --next.live_blocks;
    int is_context = context_seen && (uintptr_t)pointer == context_address;
    if (is_context) {
        if (context_freed) observer_fail("context address reused and freed twice");
        context_freed = 1;
    }
    last_free_was_context = is_context;
    /* Inspect pointer value only while its allocation is live. The retained
     * context identity is an integer; no freed pointer is dereferenced. */
    blocks[slot].pointer = NULL;
    blocks[slot].requested = 0;
    memory = next;
    free(pointer);
}
static int inside_live_runtime_storage(const void *pointer) {
    if (!pointer) return 0;
    uintptr_t address = (uintptr_t)pointer;
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (blocks[i].pointer) {
            uintptr_t start = (uintptr_t)blocks[i].pointer;
            if (address == start || (address > start && address - start < blocks[i].requested))
                return 1;
        }
    }
    return 0;
}
static void json_string(FILE *file, const char *text) {
    if (!text) { fputs("null", file); return; }
    fputc('"', file);
    /* Runtime status/fault identifiers are short immutable literals. Bound
     * serialization too, rather than treating a stray pointer as unbounded text. */
    for (size_t i = 0; i < 256; ++i) {
        unsigned char ch = (unsigned char)text[i];
        if (!ch) { fputc('"', file); return; }
        if (ch == '"' || ch == '\\') { fputc('\\', file); fputc(ch, file); }
        else if (ch < 0x20 || ch >= 0x7f) fprintf(file, "\\u%04x", (unsigned)ch);
        else fputc(ch, file);
    }
    observer_fail("report identifier exceeds literal bound");
}
void rir_observer_report(const RtReport *report) {
    if (reported || !report) observer_fail("missing or repeated final report");
    if (inside_live_runtime_storage(report) ||
        inside_live_runtime_storage(report->status) ||
        inside_live_runtime_storage(report->fault))
        observer_fail("report or transitive strings use live runtime storage");
    if (!report->status) observer_fail("missing copied report status");
    /* This does NOT prove arbitrary freed pointers valid. Static string origins
     * are established from pinned runtime/generated source; sanitizers exercise
     * these reads after terminal destruction on the qualified source path. */
    uint64_t map_bytes = 0, map_blocks = 0;
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (blocks[i].pointer) {
            map_bytes = checked_add(map_bytes, (uint64_t)blocks[i].requested);
            map_blocks = checked_add(map_blocks, 1);
        }
    }
    if (map_bytes != memory.live_bytes || map_blocks != memory.live_blocks ||
        memory.allocated_bytes < memory.freed_bytes ||
        memory.allocated_bytes - memory.freed_bytes != memory.live_bytes ||
        memory.allocations < memory.frees || memory.allocations - memory.frees != memory.live_blocks)
        observer_fail("physical map/counter mismatch");
    reported = 1;
    FILE *file = fopen("allocation-observer.json", "wb");
    if (!file) observer_fail("cannot open observer report");
    fputs("{\"schema\":\"runtime-physical-observer/1\",\"memory\":{", file);
    fprintf(file, "\"allocated_bytes\":%" PRIu64 ",\"freed_bytes\":%" PRIu64
                  ",\"live_bytes\":%" PRIu64 ",\"peak_bytes\":%" PRIu64
                  ",\"allocations\":%" PRIu64 ",\"frees\":%" PRIu64
                  ",\"live_blocks\":%" PRIu64 ",\"peak_blocks\":%" PRIu64 "}",
            memory.allocated_bytes, memory.freed_bytes, memory.live_bytes, memory.peak_bytes,
            memory.allocations, memory.frees, memory.live_blocks, memory.peak_blocks);
    fprintf(file, ",\"context_requested_bytes\":%" PRIu64 ",\"context_freed_last\":%s,"
                  "\"live_allocations\":[",
            context_requested_bytes,
            context_freed && last_free_was_context && !memory.live_blocks ? "true" : "false");
    int comma = 0;
    for (size_t i = 0; i < OBSERVER_CAPACITY; ++i) {
        if (blocks[i].pointer) {
            if (comma) fputc(',', file);
            comma = 1;
            fprintf(file, "{\"pointer\":\"0x%" PRIxPTR "\",\"bytes\":%" PRIu64 "}",
                    (uintptr_t)blocks[i].pointer, (uint64_t)blocks[i].requested);
        }
    }
    fputs("],\"report_status\":", file); json_string(file, report->status);
    fputs(",\"report_fault\":", file); json_string(file, report->fault);
    fputs("}\n", file);
    if (ferror(file)) observer_fail("observer report write failed");
    if (fclose(file)) observer_fail("observer report close failed");
}
