/* Entered lazy values must release obsolete environments before reaching the
 * final result. Each callback checks its live capture, then replaces it with
 * a fresh 64 KiB capture. Only update identities remain needed on the spine.
 * Retaining all those captures uses more than 128 MiB at the final callback.
 */
#include "mlf_runtime.h"
#include <gc/gc.h>
#include <stdio.h>
#include <stdlib.h>

enum { EQ_INT = 10, STRING_LENGTH = 46 };
static unsigned remaining = 2000;
static const char payload[65536];
static size_t retained_bytes;
static const size_t retained_limit = 4 * 1024 * 1024;

static MlfValue *walk(MlfEnv *, MlfValue *);

static MlfValue *step(void) {
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, mlf_string(payload, sizeof(payload)));
    return mlf_thunk(walk, env);
}

static MlfValue *walk(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    MlfValue *length = mlf_prim1(STRING_LENGTH, mlf_env_get(env, 0));
    if (!mlf_truth(mlf_prim2(EQ_INT, length, mlf_integer("65536")))) {
        fputs("GC spine lost a live closure capture\n", stderr);
        exit(1);
    }
    if (remaining) {
        --remaining;
        return step();
    }
    GC_gcollect();
    retained_bytes = GC_get_heap_size() - GC_get_free_bytes();
    return mlf_integer("42");
}

int main(void) {
    MlfValue *result = mlf_force(step());
    if (!mlf_truth(mlf_prim2(EQ_INT, result, mlf_integer("42")))) {
        fputs("GC spine changed its result\n", stderr);
        return 1;
    }
    MlfValue *cycle = mlf_hole();
    mlf_fill(cycle, mlf_constructor1(17, cycle));
    if (mlf_tag(mlf_field(mlf_force(cycle), 0)) != 17) {
        fputs("GC spine changed a recursive data cycle\n", stderr);
        return 1;
    }
    if (retained_bytes > retained_limit) {
        fprintf(stderr, "GC spine retains %zu bytes; expected at most %zu\n",
                retained_bytes, retained_limit);
        return 1;
    }
    printf("{\"retained_bytes\":%zu,\"retained_limit\":%zu,\"result\":42,\"cycle_tag\":17}\n",
           retained_bytes, retained_limit);
    return 0;
}
