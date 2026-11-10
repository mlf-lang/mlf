/* Alternative test guest and independent host-allocation observer.
 * The test link must wrap runtime malloc/free references with --wrap=malloc
 * and --wrap=free. Never include these hooks in production. No other allocating
 * component may run concurrently during observation. Tracker pointers are
 * test-only and cleared on free. */
#include "../../../../runtime/mlf_nogc_entry.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

void *__real_malloc(size_t);
void __real_free(void *);
static struct {
    unsigned watching, fail_at, calls, frees, live, errors;
    size_t requested, freed;
    unsigned free_slot[2], probing;
    MlfNg0Limits limits;
    void *pointer[2];
    size_t bytes[2];
} trace;

void *__wrap_malloc(size_t bytes) {
    if (!trace.watching) return __real_malloc(bytes);
    unsigned call=++trace.calls;
    if (call>2 || bytes>SIZE_MAX-trace.requested) { ++trace.errors; return NULL; }
    trace.requested+=bytes;
    if (call==trace.fail_at) return NULL;
    void *p=__real_malloc(bytes);
    if (p) { trace.pointer[call-1]=p; trace.bytes[call-1]=bytes; ++trace.live; }
    return p;
}
void __wrap_free(void *p) {
    if (!trace.watching) { __real_free(p); return; }
    if (!p) return;
    for (unsigned i=0;i<2;++i) if (trace.pointer[i]==p) {
        /* Public reentry must remain BUSY throughout both frees, including
         * the context free. This probes only the gate, never active context. */
        if (!trace.probing) {
            MlfNg0Result nested;
            trace.probing=1;
            if (mlf_ng0_eval(&trace.limits,&nested)!=MLF_NG0_BUSY || nested.host_allocation_calls)
                ++trace.errors;
            trace.probing=0;
        }
        if (trace.frees<2) trace.free_slot[trace.frees]=i;
        ++trace.frees; --trace.live; trace.freed+=trace.bytes[i];
        trace.pointer[i]=NULL; trace.bytes[i]=0; __real_free(p); return;
    }
    /* Do not repeat an unknown/duplicate free just to observe a failure. */
    ++trace.errors;
}

enum Guest { BOX, ENV_SIZE_OVERFLOW, BUILD_SPINE, FORCE_SPINE, EXPLICIT_FAULT };
static enum Guest guest;
static MlfNg0Value *forward(MlfNg0Env *e,MlfNg0Value *a) {
    (void)a; mlf_ng0_depth_enter();
    MlfNg0Value *p=mlf_ng0_env_get(e,0); mlf_ng0_depth_leave(); return p;
}
MlfNg0Value *mlf_ng0_guest_entry(void) {
    mlf_ng0_depth_enter();
    MlfNg0Value *p=NULL;
    switch (guest) {
    case BOX: p=mlf_ng0_integer("9223372036854775807"); break;
    case ENV_SIZE_OVERFLOW: (void)mlf_ng0_env_new(UINT64_MAX); break;
    case EXPLICIT_FAULT: mlf_ng0_match_failure();
    case BUILD_SPINE: case FORCE_SPINE:
        p=mlf_ng0_integer("7");
        /* Fixture size, not a resource qualification ceiling. Length exceeds
         * the first spill buffer so multiple allocate/copy growths are needed. */
        for (unsigned i=0;i<16;++i) {
            MlfNg0Env *e=mlf_ng0_env_new(1); mlf_ng0_env_set(e,0,p);
            p=mlf_ng0_thunk(forward,e);
        }
        if (guest==BUILD_SPINE) p=mlf_ng0_integer("7");
        else p=mlf_ng0_force(p);
        break;
    }
    mlf_ng0_depth_leave(); return p;
}

/* Observes actual calls and frees at return, independently of retained_bytes.
 * Returns mismatch count. An unexpected real host allocation failure counts
 * as a mismatch/inconclusive environment, never a semantic pass. */
static unsigned observed(MlfNg0Limits limits, enum Guest which, unsigned fail_at,
                         MlfNg0Status expected, unsigned calls, unsigned frees,
                         MlfNg0Result *result) {
    if (trace.live) return 1; /* Never hide leaked allocations by resetting. */
    memset(&trace,0,sizeof(trace));
    trace.watching=1; trace.fail_at=fail_at; trace.limits=limits; guest=which;
    MlfNg0Status status=mlf_ng0_eval(&limits,result);
    trace.watching=0;
    unsigned bad=(status!=expected || result->status!=status || trace.calls!=calls || trace.frees!=frees ||
        trace.live || trace.errors || trace.pointer[0] || trace.pointer[1] ||
        result->host_allocation_calls!=calls || result->host_requested_bytes!=trace.requested || result->retained_bytes);
    if (!fail_at && calls==2) bad+=(trace.freed!=trace.requested);
    if (frees==2) bad+=(trace.free_slot[0]!=1 || trace.free_slot[1]!=0);
    if (frees==1) bad+=(trace.free_slot[0]!=0);
    if (fail_at==1) bad+=(trace.freed!=0);
    if (fail_at==2) bad+=(trace.freed!=result->context_bytes);
    if (status!=MLF_NG0_OK) bad+=(result->value!=0);
    return bad;
}
/* Caller supplies fixture limits, not production ceilings.
 * Return count must be zero AND the external bounded harness must finish.
 * Every observed failure is followed immediately by an independent successful
 * allocation/free cycle, establishing that the entry gate was released.
 */
unsigned mlf_ng0_fixture_allocation_faults(MlfNg0Limits limits) {
    unsigned bad=0; MlfNg0Result r;
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    if (bad || !r.used_high_water) return bad+1;
    uint64_t one_box=r.used_high_water;
    for (unsigned fail=1;fail<=2;++fail) {
        bad+=observed(limits,BOX,fail,MLF_NG0_HOST_ALLOCATION,fail,fail-1,&r);
        bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    }
    bad+=observed(limits,ENV_SIZE_OVERFLOW,0,MLF_NG0_ARENA_LIMIT,2,2,&r);
    bad+=(r.used_high_water!=0); /* overflow refused before any arena write */
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    bad+=observed(limits,EXPLICIT_FAULT,0,MLF_NG0_MATCH_FAILURE,2,2,&r);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);

    MlfNg0Limits boundary=limits;
    boundary.capacity=one_box-1;
    bad+=observed(boundary,BOX,0,MLF_NG0_ARENA_LIMIT,2,2,&r);
    bad+=(r.used_high_water!=0);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    boundary.capacity=one_box;
    bad+=observed(boundary,BOX,0,MLF_NG0_OK,2,2,&r);
    bad+=(r.used_high_water!=one_box || r.padding_bytes);
    if (one_box<limits.capacity) {
        /* Non-aligned capacity end, aligned allocations: no rounded capacity
         * overrun or false reliance on capacity being a multiple of8. */
        boundary.capacity=one_box+1;
        bad+=observed(boundary,BOX,0,MLF_NG0_OK,2,2,&r);
        bad+=(r.used_high_water!=one_box || r.padding_bytes);
    }
    bad+=observed(limits,BUILD_SPINE,0,MLF_NG0_OK,2,2,&r);
    uint64_t construction=r.used_high_water;
    bad+=observed(limits,FORCE_SPINE,0,MLF_NG0_OK,2,2,&r);
    uint64_t forced=r.used_high_water;
    if (forced<=construction) return bad+1;
    boundary=limits; boundary.capacity=construction;
    bad+=observed(boundary,FORCE_SPINE,0,MLF_NG0_ARENA_LIMIT,2,2,&r);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    boundary.capacity=forced-1;
    bad+=observed(boundary,FORCE_SPINE,0,MLF_NG0_ARENA_LIMIT,2,2,&r);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    boundary.capacity=forced;
    bad+=observed(boundary,FORCE_SPINE,0,MLF_NG0_OK,2,2,&r);

    boundary=limits; boundary.capacity=UINT64_MAX;
    bad+=observed(boundary,BOX,0,MLF_NG0_INVALID_CONFIG,0,0,&r);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    boundary=limits; boundary.depth_limit=0;
    bad+=observed(boundary,BOX,0,MLF_NG0_INVALID_CONFIG,0,0,&r);
    bad+=observed(limits,BOX,0,MLF_NG0_OK,2,2,&r);
    return bad;
}
