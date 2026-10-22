/* Allocation and constructor ABI checks independent of generated LLVM. */
#include "mlf_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gc/gc.h>

static unsigned calls;
enum { ZERO_ENVIRONMENT_ROUNDS = 100 };
static void require(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "runtime allocation: %s\n", message); exit(90); }
}

static MlfValue *poison(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    fputs("runtime allocation: forced a lazy field\n", stderr);
    exit(91);
}

static MlfValue *counted(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    ++calls;
    GC_gcollect();
    return mlf_env_get(env, 0);
}

/* Use the public generated-code layout, independently of the accessors. */
static unsigned char *fields_of(MlfValue *value) {
    return (unsigned char *)value + 24;
}

static MlfValue *field_at(unsigned char *fields, size_t index) {
    MlfValue *value;
    memcpy(&value, fields + 8 * index, sizeof value);
    return value;
}

static void put_field(unsigned char *fields, size_t index, MlfValue *value) {
    memcpy(fields + 8 * index, &value, sizeof value);
}

static void check_empty_slots(MlfEnv *env, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        MlfValue *field;
        memcpy(&field, (const unsigned char *)env + 8 + 8 * i, sizeof field);
        require(field == NULL, "fresh environment contains a stale pointer");
    }
}

static void constructor(size_t count) {
    MlfValue *answer = mlf_integer("42"), *hole = mlf_hole();
    MlfEnv *capture = mlf_env_new(1);
    mlf_env_set(capture, 0, answer);
    MlfValue *shared = mlf_thunk(counted, capture);
    MlfValue *unused = mlf_thunk(poison, mlf_env_new(0));
    MlfValue *value = mlf_constructor_new(93, count);
    unsigned char *fields = fields_of(value);
    for (size_t i = 0; i < count; ++i) require(field_at(fields,i) == NULL, "fresh field is not empty");
    for (size_t i = 0; i < count; ++i) {
        MlfValue *field = i == 1 ? unused : i == count - 1 ? hole : shared;
        put_field(fields, i, field);
    }
    mlf_fill(hole, value);
    GC_gcollect();
    require(mlf_tag(value) == 93, "constructor tag changed");
    unsigned previous = calls;
    require(mlf_force(mlf_field(value, 0)) == answer, "constructor field changed");
    require(mlf_force(mlf_field(value, 0)) == answer, "shared field changed");
    require(calls == previous + 1, "field evaluation was not shared");
    require(mlf_field(value, 1) == unused, "lazy field identity changed");
    require(mlf_tag(mlf_field(value, count - 1)) == 93, "recursive field changed");
}

static void zero_environments(void) {
    for (unsigned repetition = 0; repetition < ZERO_ENVIRONMENT_ROUNDS; ++repetition) {
        /* Exercise every small environment size class and the uncached path. */
        for (size_t count = 0; count <= 40; ++count) {
            MlfEnv *env = mlf_env_new(count);
            check_empty_slots(env, count);
            for (size_t i = 0; i < count; ++i)
                mlf_env_set(env, i, mlf_integer("91"));
        }
        GC_gcollect();
    }
}

/* Static/heap roots need the registered displacement when arbitrary interior
 * pointers are disabled. A stack root alone would not test that requirement. */
static unsigned char *escaped_fields;

__attribute__((noinline)) static unsigned char *escape_environment(void) {
    MlfValue *value = mlf_constructor_new(67, 17);
    unsigned char *fields = fields_of(value);
    for (size_t i = 0; i < 17; ++i) put_field(fields, i, mlf_integer("42"));
    return fields;
}

__attribute__((noinline)) static void churn(void) {
    volatile uintptr_t scratch[512] = {0};
    for (unsigned i = 0; i < 1000000; ++i) {
        size_t count = i % 32;
        MlfEnv *env = mlf_env_new(count);
        check_empty_slots(env, count);
        if (count) mlf_env_set(env, count - 1, mlf_integer("91"));
    }
    GC_reachable_here(scratch);
}

static size_t check_retention(void) {
    escaped_fields = escape_environment();
    size_t collections = GC_get_gc_no();
    churn();
    GC_gcollect();
    require(GC_get_gc_no() > collections + 10, "retention probe did not collect repeatedly");
    for (size_t i = 0; i < 17; ++i) {
        MlfValue *entry = field_at(escaped_fields, i);
        require(mlf_truth(mlf_eq_int(entry, mlf_integer("42"))), "lost a fields-only root");
    }
    escaped_fields = NULL;
    GC_gcollect();
    GC_gcollect();
    size_t retained = GC_get_heap_size() - GC_get_free_bytes();
    require(retained < 4 * 1024 * 1024, "allocator retains discarded allocation history");
    require(GC_get_heap_size() <= 8 * 1024 * 1024, "allocator bypassed the heap limit");
    return retained;
}

int main(int argc, char **argv) {
    require(argc == 2, "expected one probe mode");
    const char *mode = argv[1];
    GC_set_max_heap_size(8 * 1024 * 1024);
    if (!strcmp(mode, "no-interior")) GC_set_all_interior_pointers(0);
    if (!strcmp(mode, "incremental")) GC_enable_incremental();
    if (!strcmp(mode, "negative-tag")) (void)mlf_constructor_new(-1, 3);
    else if (!strcmp(mode, "short")) (void)mlf_constructor_new(1, 2);
    else if (!strcmp(mode, "overflow")) (void)mlf_constructor_new(1, UINT64_MAX);
    else if (!strcmp(mode, "unset-slot")) (void)mlf_field(mlf_constructor_new(1, 17), 16);
    else {
        require(!strcmp(mode, "success") || !strcmp(mode, "no-interior") || !strcmp(mode, "incremental"),
                "unknown probe mode");
        const size_t arities[] = {3, 4, 5, 17, 18, 33, 257};
        for (size_t i = 0; i < sizeof arities / sizeof *arities; ++i) constructor(arities[i]);
        zero_environments();
        size_t retained = 0;
        retained = check_retention();
        /* Exercise ordinary collector registration/release, then allocate
         * again to catch stale ownership after a complete runtime cleanup. */
        require(mlf_run(mlf_integer("42"), 0) == 0, "cleanup failed");
        constructor(5);
        require(mlf_run(mlf_integer("42"), 0) == 0, "second cleanup failed");
        require(calls == 8, "unexpected field evaluation count");
        printf("{\"constructor_arities\":7,\"field_evaluations\":8,\"zero_environments\":%u,\"retained_bytes\":%zu}\n", 41U * ZERO_ENVIRONMENT_ROUNDS, retained);
        return 0;
    }
    fputs("runtime allocation: invalid operation unexpectedly succeeded\n", stderr);
    return 92;
}
