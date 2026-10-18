/* Runtime ABI and call-by-need checks independent of generated LLVM.
 * Compile with MLF_USE_BDWGC to collect while update roots are live. */
#include "mlf_runtime.h"
#ifdef MLF_COMPACT_BDWGC
#define HEADER_BYTES 0
#else
#define HEADER_BYTES 16
#endif
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef MLF_USE_BDWGC
#include <gc/gc.h>
#include <gc/gc_mark.h>
#endif

static unsigned calls, expected_calls;
static MlfValue *saved_alias, *self;

static void require(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "runtime values: %s\n", message); exit(90); }
}

static MlfValue *poison(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    fputs("runtime values: forced a lazy constructor field\n", stderr);
    exit(91);
}

static MlfValue *counted(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    ++calls;
    MlfValue *answer = mlf_env_get(env, 0);
#ifdef MLF_USE_BDWGC
    if (calls == expected_calls) GC_gcollect();
#endif
    return answer;
}

static MlfValue *identity(MlfEnv *env, MlfValue *argument) {
    (void)env;
    ++calls;
#ifdef MLF_USE_BDWGC
    if (calls == expected_calls) GC_gcollect();
#endif
    return argument;
}

static MlfValue *self_demand(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    return self;
}

static void force_chain(unsigned length, unsigned mode) {
    calls = 0;
    expected_calls = length;
    saved_alias = NULL;
    MlfValue *answer = mlf_integer("42");
    MlfValue *root = answer;
    MlfValue *function = mlf_closure(identity, mlf_env_new(0));
    for (unsigned i = 0; i < length; ++i) {
        if (mode == 0) {
            MlfEnv *env = mlf_env_new(1);
            mlf_env_set(env, 0, root);
            root = mlf_thunk(counted, env);
        } else if (mode == 1) {
            root = mlf_application(function, root);
        } else {
            MlfValue *hole = mlf_hole();
            mlf_fill(hole, root);
            root = hole;
        }
        if (i == length / 2) saved_alias = root;
    }
    require(mlf_force(root) == answer, "force changed a chain result");
    require(calls == (mode == 2 ? 0 : expected_calls), "force skipped/repeated a callback");
    require(mlf_force(root) == answer, "memoized force changed its result");
    if (saved_alias) require(mlf_force(saved_alias) == answer, "intermediate alias was not memoized");
    require(calls == (mode == 2 ? 0 : expected_calls), "forcing an alias re-executed a callback");
}

static MlfValue *wide(unsigned arity) {
    MlfEnv *env = mlf_env_new(arity);
    for (unsigned i = 0; i < arity; ++i) mlf_env_set(env, i, mlf_integer("42"));
    return mlf_constructor_fields(73, env);
}

static void general_fields(MlfValue *entry, MlfValue **expected, unsigned count) {
    /* Use the public generated-code ABI, independently of runtime accessors.
     * memcpy avoids adding alignment or C aliasing assumptions to the test. */
    MlfEnv *env;
#ifdef MLF_COMPACT_BDWGC
    uint32_t tag;
    memcpy(&tag, entry, sizeof tag);
    require(tag == 9 || tag == 28, "unexpected general constructor tag");
    if (tag == 28) env = (MlfEnv *)((unsigned char *)entry + 24);
    else memcpy(&env, (const unsigned char *)entry + 24, sizeof env);
#else
    memcpy(&env, (const unsigned char *)entry + 40, sizeof env);
#endif
    for (unsigned i = 0; i < count; ++i) {
        MlfValue *field;
#ifdef MLF_COMPACT_BDWGC
        memcpy(&field, (const unsigned char *)env + (tag == 28 ? 0 : 8) + 8 * i, sizeof field);
#else
        memcpy(&field, (const unsigned char *)env + 24 + 8 * i, sizeof field);
#endif
        require(field == expected[i], "general constructor field layout changed");
        require(field == mlf_field(entry, i), "direct field load disagrees with accessor");
    }
}

static void constructor(unsigned arity, int partial) {
    require(arity <= 17, "constructor probe is too wide");
    MlfValue *fields[17];
    MlfValue *answer = mlf_integer("42");
    MlfValue *hole = mlf_hole();
    for (unsigned i = 0; i < arity; ++i) fields[i] = answer;
    if (arity > 1) fields[1] = mlf_thunk(poison, mlf_env_new(0));
    if (arity > 2) fields[arity - 1] = hole;
    MlfValue *entry, *prefix = NULL;
    if (partial) {
        entry = mlf_constructor(73, arity);
        for (unsigned i = 0; i < arity; ++i) {
            entry = mlf_force(mlf_application(entry, fields[i]));
            if (!i) prefix = entry;
            if (arity > 2) general_fields(entry, fields, i + 1);
        }
    } else {
        MlfEnv *env = mlf_env_new(arity);
        for (unsigned i = 0; i < arity; ++i) mlf_env_set(env, i, fields[i]);
        entry = mlf_constructor_fields(73, env);
    }
    mlf_fill(hole, entry);
#ifdef MLF_USE_BDWGC
    GC_gcollect();
#endif
    if (arity > 2) {
        general_fields(entry, fields, arity);
        if (prefix) general_fields(prefix, fields, 1);
    }
    require(mlf_tag(entry) == 73, "constructor tag changed");
    if (arity) require(mlf_force(mlf_field(entry, 0)) == answer, "constructor field changed");
    if (arity > 2) require(mlf_tag(mlf_field(entry, arity - 1)) == 73, "recursive field changed");
}

static void canonical_boolean(MlfValue *entry, int answer) {
    MlfValue *ready = mlf_force(entry);
    require((uintptr_t)ready == (answer ? 6u : 2u), "Boolean result is not a canonical tagged value");
    require(mlf_truth(entry) == answer, "tagged Boolean disagrees with generic truth");
}

static void booleans(void) {
    canonical_boolean(mlf_boolean(0), 0);
    canonical_boolean(mlf_boolean(1), 1);
    canonical_boolean(mlf_boolean(-1), 1);
    canonical_boolean(mlf_boolean(INT64_MAX), 1);
    MlfValue *small = mlf_integer("-2"), *other = mlf_integer("3");
    MlfValue *large = mlf_integer("123456789012345678901234567890");
    canonical_boolean(mlf_eq_int(small, small), 1);
    canonical_boolean(mlf_eq_int(small, other), 0);
    canonical_boolean(mlf_lt_int(small, other), 1);
    canonical_boolean(mlf_lt_int(other, small), 0);
    canonical_boolean(mlf_eq_int(large, large), 1);
    canonical_boolean(mlf_eq_int(large, small), 0);
    canonical_boolean(mlf_lt_int(small, large), 1);
    canonical_boolean(mlf_lt_int(large, small), 0);
    for (int answer = 0; answer < 2; ++answer) {
        calls = 0;
        expected_calls = 1;
        MlfEnv *env = mlf_env_new(1);
        mlf_env_set(env, 0, mlf_boolean(answer));
        MlfValue *thunk = mlf_thunk(counted, env);
        MlfValue *hole = mlf_hole();
        mlf_fill(hole, thunk);
        canonical_boolean(hole, answer);
        canonical_boolean(thunk, answer);
        require(calls == 1, "Boolean thunk lost memoization through an alias");
    }
}

static unsigned private_count;
static MlfValue *consume_captures(MlfEnv *env, MlfValue *argument) {
    require(argument == NULL, "thunk received an argument");
    ++calls;
    if (!private_count) { require(env == NULL, "empty capture environment"); return mlf_integer("42"); }
    MlfValue *first = mlf_env_get(env, 0);
    MlfValue *last = mlf_env_get(env, private_count - 1);
    /* Model the generated callback: retain loaded values, then clear slots
     * before allocating/collecting. Unused captures remain unevaluated. */
    memset((unsigned char *)env + HEADER_BYTES + 8, 0, private_count * sizeof(MlfValue *));
#ifdef MLF_USE_BDWGC
    GC_gcollect();
#endif
    return mlf_constructor2(73, first, last);
}

static void private_thunks(void) {
    const unsigned counts[] = {0, 1, 2, 17, 513};
    for (unsigned c = 0; c < sizeof counts / sizeof *counts; ++c) {
        private_count = counts[c]; calls = 0;
        MlfValue *entry = mlf_thunk_new(consume_captures, private_count);
        MlfEnv *env;
        memcpy(&env, (const unsigned char *)entry + HEADER_BYTES + 16, sizeof env);
        MlfValue *answer = mlf_integer("340282366920938463463374607431768211456");
        for (unsigned i = 0; i < private_count; ++i)
            mlf_env_set(env, i, i == 0 || i + 1 == private_count ? answer : mlf_thunk(poison, NULL));
#ifdef MLF_USE_BDWGC
        GC_gcollect();
#endif
        MlfValue *result = mlf_force(entry);
        require(calls == 1 && mlf_force(entry) == result, "private thunk was reexecuted");
        if (private_count) {
            require(mlf_field(result, 0) == answer && mlf_field(result, 1) == answer, "private captures lost across collection");
            for (unsigned i = 0; i < private_count; ++i) {
                MlfValue *slot;
                memcpy(&slot, (const unsigned char *)env + HEADER_BYTES + 8 + i * sizeof slot, sizeof slot);
                require(slot == NULL, "consumed private capture retained");
            }
        }
    }
}

#ifdef MLF_COMPACT_BDWGC
/* The generated compact string ABI permits writable static values. Their
 * Unicode index must remain rooted even when no evaluated MLF value owns it. */
static struct LiteralString {
    int32_t tag, padding;
    uint64_t length;
    const unsigned char *bytes;
    size_t *indices;
} unicode_literal = {8, 0, 6, (const unsigned char *)"\xce\xbb\xf0\x9f\x98\x80", NULL},
  nul_literal = {8, 0, 3, (const unsigned char *)"a\0b", NULL},
  empty_literal = {8, 0, 0, (const unsigned char *)"", NULL};
static void static_strings(void) {
    MlfValue *unicode = (MlfValue *)&unicode_literal;
    MlfValue *nul = (MlfValue *)&nul_literal;
    MlfValue *empty = (MlfValue *)&empty_literal;
    for (unsigned pass = 0; pass < 3; ++pass) {
        require(mlf_prim1(46, unicode) == mlf_integer("2"), "static Unicode length changed");
        require(mlf_prim2(47, unicode, mlf_integer("0")) == mlf_integer("955"), "static Unicode first scalar changed");
        require(mlf_prim2(47, unicode, mlf_integer("1")) == mlf_integer("128512"), "static Unicode final scalar changed");
        require(mlf_prim1(46, nul) == mlf_integer("3") &&
                mlf_prim2(47, nul, mlf_integer("1")) == mlf_integer("0"), "static embedded NUL changed");
        require(mlf_prim1(46, empty) == mlf_integer("0"), "static empty string changed");
        (void)GC_clear_stack(NULL);
        GC_gcollect();
    }
}
#else
static void static_strings(void) {}
#endif

#ifdef MLF_ALLOCATION_AUDIT
static size_t constructor_audits;
void mlf_bench_constructed_node(int64_t identity) {
    (void)identity;
    ++constructor_audits;
}
#endif

#ifdef MLF_COMPACT_BDWGC
/* Independently exercise the emitted allocation protocol, including its last
 * size class, the first oversized object, and debug/audit refill fallbacks. */
static MlfValue *generated_constructor(int64_t identity, size_t count) {
    size_t offset = count <= 2 ? 16 : 24;
    size_t bytes = offset + 8 * count;
    void *memory = bytes <= 256 ? mlf_constructor_pending[bytes / 8] : NULL;
    if (memory) {
        void *next;
        memcpy(&next, memory, sizeof next);
        mlf_constructor_pending[bytes / 8] = next;
    } else memory = mlf_constructor_allocate(identity, count);
    uint32_t kind = count == 1 ? 12 : count == 2 ? 13 : 28;
    memset(memory, 0, 8);
    memcpy(memory, &kind, sizeof kind);
    memcpy((char *)memory + 8, &identity, 8);
    if (count > 2) memcpy((char *)memory + 16, &count, 8);
    for (size_t i = 0; i < count; ++i) {
        MlfValue *entry = mlf_constructor1(900, mlf_integer("71"));
        memcpy((char *)memory + offset + 8 * i, &entry, sizeof entry);
    }
    return memory;
}
static void inline_constructors(void) {
    static const size_t widths[] = {1, 2, 3, 4, 5, 17, 28, 29, 30, 31, 32, 513};
    for (size_t i = 0; i < sizeof widths / sizeof widths[0]; ++i) {
        size_t count = widths[i];
#ifdef MLF_ALLOCATION_AUDIT
        size_t before = constructor_audits;
#endif
        for (size_t repeat = 0; repeat < 140; ++repeat) {
            MlfValue *root = generated_constructor(901, count);
            GC_clear_stack(NULL);
            GC_gcollect();
            require(mlf_tag(root) == 901, "inline constructor identity");
            for (size_t field = 0; field < count; ++field) {
                MlfValue *child = mlf_field(root, field);
                require(mlf_tag(child) == 900 && mlf_force(mlf_field(child, 0)) == mlf_integer("71"),
                        "inline constructor field survived collection");
            }
        }
#ifdef MLF_ALLOCATION_AUDIT
        require(constructor_audits == before + 140 * (count + 1), "inline constructor audit coverage");
        for (size_t head = 0; head < 33; ++head)
            require(mlf_constructor_pending[head] == NULL, "audited constructor bypassed hook");
#endif
    }
}
#else
static void inline_constructors(void) {}
#endif

int main(int argc, char **argv) {
    require(argc == 2, "expected one probe mode");
    const char *mode = argv[1];
#ifdef MLF_USE_BDWGC
    GC_set_max_heap_size(8 * 1024 * 1024);
    if (!strcmp(mode, "no-interior")) GC_set_all_interior_pointers(0);
#endif
    if (!strcmp(mode, "success") || !strcmp(mode, "no-interior")) {
        const unsigned lengths[] = {0, 1, 2, 3, 4, 5, 16, 17, 64, 65, 1025};
        for (unsigned mode = 0; mode < 3; ++mode)
            for (unsigned i = 0; i < sizeof lengths / sizeof *lengths; ++i)
                force_chain(lengths[i], mode);
        const unsigned arities[] = {0, 1, 2, 3, 5, 17};
        for (unsigned i = 0; i < sizeof arities / sizeof *arities; ++i) {
            constructor(arities[i], 0);
            if (arities[i] > 2) constructor(arities[i], 1);
        }
        booleans();
        private_thunks();
        static_strings();
        inline_constructors();
        puts("runtime values: sharing, lazy fields, recursive data, and spill boundaries passed");
        return 0;
    }
    if (!strcmp(mode, "capture-null-code")) (void)mlf_thunk_new(NULL, 1);
    else if (!strcmp(mode, "capture-overflow")) (void)mlf_thunk_new(consume_captures, UINT64_MAX);
    else if (!strcmp(mode, "negative-tag")) (void)mlf_constructor_fields(-1, mlf_env_new(3));
    else if (!strcmp(mode, "null-fields")) (void)mlf_constructor_fields(1, NULL);
    else if (!strcmp(mode, "overapplication")) (void)mlf_force(mlf_application(wide(5), mlf_integer("1")));
    else if (!strcmp(mode, "field-bounds")) (void)mlf_field(wide(5), 5);
    else if (!strcmp(mode, "cycle-hole")) {
        self = mlf_hole(); mlf_fill(self, self); (void)mlf_force(self);
    } else if (!strcmp(mode, "cycle-pair")) {
        self = mlf_hole(); MlfValue *other = mlf_hole();
        mlf_fill(self, other); mlf_fill(other, self); (void)mlf_force(self);
    } else if (!strcmp(mode, "cycle-thunk")) {
        self = mlf_thunk(self_demand, mlf_env_new(0)); (void)mlf_force(self);
    } else require(0, "unknown probe mode");
    fputs("runtime values: invalid operation unexpectedly succeeded\n", stderr);
    return 92;
}
