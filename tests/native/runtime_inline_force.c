#include "mlf_runtime.h"
#include <assert.h>
#include <gc.h>
#include <stdio.h>
#include <string.h>

extern MlfValue *probe_force(MlfValue *);
static unsigned calls;
#ifdef MLF_ALLOCATION_AUDIT
static unsigned constructed;
void mlf_bench_constructed_node(int64_t identity) { assert(identity == 17); ++constructed; }
#endif
static MlfValue *returned(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    ++calls;
    return mlf_env_get(env, 0);
}
static MlfValue *failed(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    puts("before generated force failure");
    return mlf_force(NULL);
}
static MlfValue *entered(MlfEnv *env, MlfValue *argument) {
    return probe_force(returned(env, argument));
}
static MlfValue *suspend(MlfValue *value, MlfCode code) {
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, value);
    return mlf_thunk(code, env);
}
int main(int argc, char **argv) {
    assert(argc == 2);
    GC_set_all_interior_pointers(0);
    mlf_require_haskell_boundary_v4_abi();
    if (!strcmp(argv[1], "null")) { probe_force(NULL); return 99; }
    if (!strcmp(argv[1], "failure-order")) {
        probe_force(mlf_thunk(failed, NULL));
        puts("after generated force failure");
        return 99;
    }
    if (!strcmp(argv[1], "hole")) { probe_force(mlf_hole()); return 99; }
    if (!strcmp(argv[1], "cycle-enter") || !strcmp(argv[1], "cycle-return")) {
        MlfEnv *env = mlf_env_new(1);
        MlfValue *value = mlf_thunk(!strcmp(argv[1], "cycle-enter") ? entered : returned, env);
        mlf_env_set(env, 0, value);
        probe_force(value);
        return 99;
    }
    assert(!strcmp(argv[1], "success"));
    MlfValue *leaf = mlf_constructor1(17, mlf_integer("42"));
    MlfValue *shared = suspend(leaf, returned);
    assert(probe_force(shared) == leaf && calls == 1);
    assert(probe_force(shared) == leaf && calls == 1);
    MlfValue *closure = mlf_closure(returned, NULL);
    assert(probe_force(closure) == closure && calls == 1);
    MlfValue *integer = mlf_integer("123");
    assert(probe_force(integer) == integer);
    MlfValue *boolean = mlf_boolean(1);
    assert(probe_force(boolean) == boolean);
    MlfValue *spine = leaf;
    for (unsigned i = 0; i < 100000; ++i) spine = suspend(spine, returned);
    assert(probe_force(spine) == leaf && calls == 100001);
    assert(probe_force(spine) == leaf && calls == 100001);
    MlfValue *alias = mlf_hole();
    mlf_fill(alias, spine);
    assert(probe_force(alias) == leaf && calls == 100001);
#ifdef MLF_ALLOCATION_AUDIT
    assert(constructed == 1);
#endif
    puts("generated force: sharing, canonical values, long spines and no-interior GC passed");
    return 0;
}
