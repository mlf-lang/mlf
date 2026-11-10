/* Standalone runtime fixtures linked instead of a generated guest.
 * Test control globals are scalar only and must not enter a production link. */
#include "../../../../runtime/mlf_nogc_entry.h"
#include <limits.h>
#include <stdint.h>

enum Scenario { ZERO, WRAP_HIGH, WRAP_LOW, SMALL_HIGH, SMALL_LOW,
    LAZY_BRANCH, LAZY_FIELD, LAZY_PARTIAL, SHARED, LEFT_DEMAND,
    HOLE_FAULT, CYCLE_FAULT, BAD_PRIMITIVE, BAD_APPLICATION, BAD_VALUE,
    MATCH_FAULT, ARENA_FAULT, DEPTH_FAULT, NESTED_BUSY, SPILL_MEMO,
    CONSTRUCTOR_CURRY };
static enum Scenario scenario;
static uint64_t visits;
static MlfNg0Limits fixture_limits;
static MlfNg0Value *one(MlfNg0Env *e,MlfNg0Value *a) {
    (void)e; (void)a; mlf_ng0_depth_enter(); ++visits;
    MlfNg0Value *v=mlf_ng0_integer("1"); mlf_ng0_depth_leave(); return v;
}
static MlfNg0Value *recursive_demand(MlfNg0Env *e,MlfNg0Value *a) {
    (void)e; (void)a; mlf_ng0_depth_enter();
    MlfNg0Value *v=mlf_ng0_force(mlf_ng0_thunk(recursive_demand,0));
    mlf_ng0_depth_leave(); return v;
}
static MlfNg0Value *forward(MlfNg0Env *e,MlfNg0Value *a) {
    (void)a; mlf_ng0_depth_enter(); MlfNg0Value *v=mlf_ng0_env_get(e,0);
    mlf_ng0_depth_leave(); return v;
}
MlfNg0Value *mlf_ng0_guest_entry(void) {
    mlf_ng0_depth_enter();
    MlfNg0Value *v=0;
    switch (scenario) {
    case ZERO: v=mlf_ng0_integer("0"); break;
    case WRAP_HIGH: v=mlf_ng0_add_int(mlf_ng0_integer("9223372036854775807"),mlf_ng0_integer("1")); break;
    case WRAP_LOW: v=mlf_ng0_add_int(mlf_ng0_integer("-9223372036854775808"),mlf_ng0_integer("-1")); break;
    case SMALL_HIGH: v=mlf_ng0_add_int(mlf_ng0_integer("4611686018427387903"),mlf_ng0_integer("1")); break;
    case SMALL_LOW: v=mlf_ng0_add_int(mlf_ng0_integer("-4611686018427387904"),mlf_ng0_integer("-1")); break;
    case LAZY_BRANCH: v=mlf_ng0_prim3(13,mlf_ng0_boolean(1),mlf_ng0_integer("7"),mlf_ng0_hole()); break;
    case LAZY_FIELD: v=mlf_ng0_field(mlf_ng0_constructor2(42,mlf_ng0_integer("7"),mlf_ng0_hole()),0); break;
    case LAZY_PARTIAL:
        (void)mlf_ng0_force(mlf_ng0_application(mlf_ng0_primitive(8),mlf_ng0_hole()));
        v=mlf_ng0_integer("7"); break;
    case SHARED: v=mlf_ng0_thunk(one,0); v=mlf_ng0_add_int(v,v); break;
    case LEFT_DEMAND:
        v=mlf_ng0_add_int(mlf_ng0_hole(),mlf_ng0_thunk(one,0)); break;
    case HOLE_FAULT: v=mlf_ng0_hole(); break;
    case CYCLE_FAULT: v=mlf_ng0_hole(); mlf_ng0_fill(v,v); break;
    case BAD_PRIMITIVE: v=mlf_ng0_primitive(9); break;
    case BAD_APPLICATION: v=mlf_ng0_application(mlf_ng0_integer("1"),mlf_ng0_integer("2")); break;
    case BAD_VALUE: v=mlf_ng0_boolean(1); break;
    case MATCH_FAULT: mlf_ng0_match_failure();
    case ARENA_FAULT: for (;;) (void)mlf_ng0_hole();
    case DEPTH_FAULT: v=mlf_ng0_thunk(recursive_demand,0); break;
    case NESTED_BUSY: {
        MlfNg0Result nested;
        if (mlf_ng0_eval(&fixture_limits,&nested)!=MLF_NG0_BUSY || nested.value || nested.host_allocation_calls)
            mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        v=mlf_ng0_integer("7"); break;
    }
    case SPILL_MEMO:
        v=mlf_ng0_thunk(one,0);
        for (unsigned i=0;i<16;++i) {
            MlfNg0Env *e=mlf_ng0_env_new(1); mlf_ng0_env_set(e,0,v);
            v=mlf_ng0_thunk(forward,e);
        }
        v=mlf_ng0_add_int(v,v); break;
    case CONSTRUCTOR_CURRY: {
        MlfNg0Value *p=mlf_ng0_application(mlf_ng0_constructor(42,2),mlf_ng0_integer("7"));
        p=mlf_ng0_application(p,mlf_ng0_hole());
        if (mlf_ng0_tag(p)!=42) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        v=mlf_ng0_field(p,0); break;
    }
    }
    mlf_ng0_depth_leave(); return v;
}
/* Caller supplies the fixture capacity and depth, not production ceilings.
 * Returns the mismatch count after actually running eval. */
unsigned mlf_ng0_fixture_contract(MlfNg0Limits limits) {
    static const struct { enum Scenario scenario; MlfNg0Status status; int64_t value; uint64_t visits; } cases[]={
        {ZERO,MLF_NG0_OK,0,0}, {WRAP_HIGH,MLF_NG0_OK,INT64_MIN,0},
        {WRAP_LOW,MLF_NG0_OK,INT64_MAX,0},
        {SMALL_HIGH,MLF_NG0_OK,INT64_C(4611686018427387904),0},
        {SMALL_LOW,MLF_NG0_OK,-INT64_C(4611686018427387905),0},
        {LAZY_BRANCH,MLF_NG0_OK,7,0}, {LAZY_FIELD,MLF_NG0_OK,7,0},
        {LAZY_PARTIAL,MLF_NG0_OK,7,0}, {SHARED,MLF_NG0_OK,2,1},
        {LEFT_DEMAND,MLF_NG0_BLACKHOLE,0,0}, {HOLE_FAULT,MLF_NG0_BLACKHOLE,0,0},
        {CYCLE_FAULT,MLF_NG0_BLACKHOLE,0,0}, {BAD_PRIMITIVE,MLF_NG0_INVALID_PRIMITIVE,0,0},
        {BAD_APPLICATION,MLF_NG0_INVALID_APPLICATION,0,0}, {BAD_VALUE,MLF_NG0_INVALID_VALUE,0,0},
        {MATCH_FAULT,MLF_NG0_MATCH_FAILURE,0,0}, {ARENA_FAULT,MLF_NG0_ARENA_LIMIT,0,0},
        {DEPTH_FAULT,MLF_NG0_DEPTH_LIMIT,0,0}, {NESTED_BUSY,MLF_NG0_OK,7,0},
        {SPILL_MEMO,MLF_NG0_OK,2,1}, {CONSTRUCTOR_CURRY,MLF_NG0_OK,7,0}, {ZERO,MLF_NG0_OK,0,0}
    };
    unsigned failures=0; fixture_limits=limits;
    for (size_t i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        MlfNg0Result r; scenario=cases[i].scenario; visits=0;
        MlfNg0Status s=mlf_ng0_eval(&limits,&r);
        failures+=(s!=cases[i].status || r.status!=s || r.value!=cases[i].value || visits!=cases[i].visits ||
            r.retained_bytes!=0 || r.host_allocation_calls>2 || r.used_high_water>limits.capacity);
        /* Every controlled failure must permit a fresh success. */
        scenario=ZERO; visits=0;
        failures+=(mlf_ng0_eval(&limits,&r)!=MLF_NG0_OK || r.value || r.retained_bytes);
    }
    MlfNg0Result r; MlfNg0Limits invalid=limits;
    invalid.capacity=0; failures+=(mlf_ng0_eval(&invalid,&r)!=MLF_NG0_INVALID_CONFIG);
    invalid=limits; invalid.depth_limit=0; failures+=(mlf_ng0_eval(&invalid,&r)!=MLF_NG0_INVALID_CONFIG);
    invalid=limits; invalid.abi^=1; failures+=(mlf_ng0_eval(&invalid,&r)!=MLF_NG0_INVALID_CONFIG);
    return failures;
}
