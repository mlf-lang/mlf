/* Separate private-runtime fixture guest, never a production link.
 * Reproduces compact capture load/store layout, not source admission or
 * execution of generated LLVM. Caller supplies fixture limits. */
#include "../../../../runtime/mlf_nogc_entry.h"
#include <stdint.h>
#include <string.h>

enum CompactCase { EMPTY_CAPTURE, ONE_CAPTURE, TWO_CAPTURES, MANY_CAPTURES,
    PENDING_RESULT, SELF_BLACKHOLE, COUNT_OVERFLOW };
static enum CompactCase which;
static uint64_t visits, leaf_visits;

static MlfNg0Env *capture_env(MlfNg0Value *value) {
    MlfNg0Env *env;
    memcpy(&env,(unsigned char *)value+16,sizeof(env));
    return env;
}
static void capture_store(MlfNg0Env *env,uint64_t index,MlfNg0Value *value) {
    memcpy((unsigned char *)env+8+8*index,&value,sizeof(value));
}
static MlfNg0Value *capture_load(MlfNg0Env *env,uint64_t index) {
    MlfNg0Value *value;
    memcpy(&value,(unsigned char *)env+8+8*index,sizeof(value));
    return value;
}
static uint64_t capture_count(MlfNg0Env *env) {
    uint64_t count;
    memcpy(&count,env,sizeof(count));
    return count;
}
static MlfNg0Value *leaf(MlfNg0Env *env,MlfNg0Value *argument) {
    (void)argument; mlf_ng0_depth_enter();
    if (env) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    ++leaf_visits;
    MlfNg0Value *result=mlf_ng0_integer("7");
    mlf_ng0_depth_leave(); return result;
}
static MlfNg0Value *captured(MlfNg0Env *env,MlfNg0Value *argument) {
    (void)argument; mlf_ng0_depth_enter(); ++visits;
    if (which==EMPTY_CAPTURE) {
        if (env) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        MlfNg0Value *result=mlf_ng0_integer("7");
        mlf_ng0_depth_leave(); return result;
    }
    uint64_t expected=which==TWO_CAPTURES ? 2 : which==MANY_CAPTURES ? 29 : 1;
    if (!env || capture_count(env)!=expected) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    MlfNg0Value *result=mlf_ng0_integer("0");
    for (uint64_t i=0;i<expected;++i) {
        /* Match the generated callback rule: load each value, then clear the
         * owned capture slot; never capture the address of a stack variable. */
        MlfNg0Value *value=capture_load(env,i);
        capture_store(env,i,NULL);
        if (!value) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        if (which==SELF_BLACKHOLE) result=mlf_ng0_force(value);
        else if (which==PENDING_RESULT) result=value;
        else result=mlf_ng0_add_int(result,value);
    }
    mlf_ng0_depth_leave(); return result;
}
MlfNg0Value *mlf_ng0_guest_entry(void) {
    mlf_ng0_depth_enter();
    if (which==COUNT_OVERFLOW) {
        (void)mlf_ng0_thunk_new(captured,UINT64_MAX);
        mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    }
    uint64_t count=which==EMPTY_CAPTURE ? 0 : which==TWO_CAPTURES ? 2 : which==MANY_CAPTURES ? 29 : 1;
    MlfNg0Value *value=mlf_ng0_thunk_new(captured,count);
    MlfNg0Env *env=capture_env(value);
    if (count) {
        if (env!=(MlfNg0Env *)((unsigned char *)value+24) || capture_count(env)!=count)
            mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        for (uint64_t i=0;i<count;++i) {
            if (capture_load(env,i)!=NULL) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
            MlfNg0Value *field=which==SELF_BLACKHOLE ? value :
                which==PENDING_RESULT ? mlf_ng0_thunk_new(leaf,0) : mlf_ng0_integer("1");
            capture_store(env,i,field);
        }
    } else if (env) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    MlfNg0Value *first=mlf_ng0_force(value);
    MlfNg0Value *second=mlf_ng0_force(value);
    int32_t tag; MlfNg0Value *forwarded;
    memcpy(&tag,value,sizeof(tag));
    memcpy(&forwarded,(unsigned char *)value+8,sizeof(forwarded));
    if (tag!=2 || first!=second || first!=forwarded || visits!=1)
        mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    for (uint64_t i=0;i<count;++i)
        if (capture_load(env,i)!=NULL) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    mlf_ng0_depth_leave(); return first;
}
static unsigned observe(MlfNg0Limits limits,enum CompactCase scenario,
                        MlfNg0Status expected,int64_t expected_value,uint64_t expected_visits,
                        uint64_t expected_leaf_visits,MlfNg0Result *result) {
    which=scenario; visits=0; leaf_visits=0;
    MlfNg0Status status=mlf_ng0_eval(&limits,result);
    return status!=expected || result->status!=status || result->value!=expected_value ||
        visits!=expected_visits || leaf_visits!=expected_leaf_visits || result->retained_bytes ||
        result->host_allocation_calls!=2 || result->used_high_water>limits.capacity;
}
/* Unexpected setup/arena/depth failure is a mismatch, never an assumed pass. */
unsigned mlf_ng0_fixture_compact_thunks(MlfNg0Limits limits) {
    unsigned bad=0; MlfNg0Result r;
    bad+=observe(limits,EMPTY_CAPTURE,MLF_NG0_OK,7,1,0,&r);
    bad+=observe(limits,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
    if (bad || r.used_high_water!=40) return bad+1;
    bad+=observe(limits,TWO_CAPTURES,MLF_NG0_OK,2,1,0,&r);
    bad+=observe(limits,MANY_CAPTURES,MLF_NG0_OK,29,1,0,&r);
    bad+=observe(limits,PENDING_RESULT,MLF_NG0_OK,7,1,1,&r);
    bad+=observe(limits,SELF_BLACKHOLE,MLF_NG0_BLACKHOLE,0,1,0,&r);
    bad+=observe(limits,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
    bad+=observe(limits,COUNT_OVERFLOW,MLF_NG0_ARENA_LIMIT,0,0,0,&r);
    bad+=(r.used_high_water!=0);
    bad+=observe(limits,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
    MlfNg0Limits boundary=limits;
    /* 40 is the specified one-capture object size, not a profile ceiling. */
    boundary.capacity=39;
    bad+=observe(boundary,ONE_CAPTURE,MLF_NG0_ARENA_LIMIT,0,0,0,&r);
    bad+=(r.used_high_water!=0);
    bad+=observe(limits,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
    boundary.capacity=40;
    bad+=observe(boundary,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
    bad+=(r.used_high_water!=40 || r.padding_bytes);
    if (limits.capacity>40) {
        boundary.capacity=41;
        bad+=observe(boundary,ONE_CAPTURE,MLF_NG0_OK,1,1,0,&r);
        bad+=(r.used_high_water!=40 || r.padding_bytes);
    }
    return bad;
}
