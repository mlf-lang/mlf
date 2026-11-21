/* Length-prefixed field primitive controls independent of generated LLVM.
 * Synthetic large lengths exercise overflow before any source byte is read. */
#include "mlf_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gc/gc.h>
#include <gc/gc_mark.h>

enum { NIL = 2, CONS = 3, PACK_STRING_FIELDS = 135, STRESS_PIECES = 2048 };
static unsigned events[16], event_count, stress_heads;
static MlfValue *kept;

static void require(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "runtime fields: %s\n", message); exit(90); }
}

static MlfValue *number(size_t n) {
    char text[32];
    snprintf(text, sizeof text, "%zu", n);
    return mlf_integer(text);
}

static size_t small_number(MlfValue *entry) {
    entry = mlf_force(entry);
    require(((uintptr_t)entry & 1) != 0, "expected test small integer");
    return (size_t)((intptr_t)entry >> 1);
}

static MlfValue *nil(void) { return mlf_constructor(NIL, 0); }
static MlfValue *cons(MlfValue *head, MlfValue *tail) {
    return mlf_constructor2(CONS, head, tail);
}

static MlfValue *panic_value(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    return mlf_prim1(55, mlf_env_get(env, 0));
}

static MlfValue *poison(const char *message) {
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, mlf_string(message, strlen(message)));
    return mlf_thunk(panic_value, env);
}

static MlfValue *event_value(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    require(event_count < 16, "too many event callbacks");
    events[event_count++] = (unsigned)small_number(mlf_env_get(env, 1));
    GC_gcollect();
    return mlf_env_get(env, 0);
}

static MlfValue *event(MlfValue *value, unsigned id) {
    MlfEnv *env = mlf_env_new(2);
    mlf_env_set(env, 0, value);
    mlf_env_set(env, 1, number(id));
    return mlf_thunk(event_value, env);
}

static void check_bytes(MlfValue *text, const void *expected, size_t length) {
    size_t actual;
    const char *bytes;
    text = mlf_force(text);
    memcpy(&actual, (const char *)text + 8, sizeof actual);
    memcpy(&bytes, (const char *)text + 16, sizeof bytes);
    require(actual == length, "byte length changed");
    require(!memcmp(bytes, expected, length), "joined bytes changed");
    require(bytes[length] == 0, "String terminator missing");
}

static void ordinary(void) {
    check_bytes(mlf_pack_string_fields(nil()), "", 0);
    MlfValue *single = mlf_string("single", 6);
    event_count = 0;
    MlfValue *only = cons(event(single, 1), event(nil(), 2));
    check_bytes(mlf_pack_string_fields(only), "6:single", 8);
    require(event_count == 2 && events[0] == 1 && events[1] == 2,
            "singleton did not force head before tail exactly once");

    const unsigned char prefix[] = {'A', 0, 0xce, 0xbb, 0xf0, 0x9f, 0x98, 0x80};
    const unsigned char framed[] = {'4', ':', 'A', 0, 0xce, 0xbb, 0xf0, 0x9f, 0x98, 0x80, '1', ':', 'Z'};
    MlfValue *left = mlf_string((const char *)prefix, sizeof prefix);
    MlfValue *right = mlf_string("Z", 1);
    event_count = 0;
    MlfValue *pieces = cons(event(left, 1),
        event(cons(event(right, 3), event(nil(), 4)), 2));
    MlfValue *output = mlf_pack_string_fields(pieces);
    check_bytes(output, framed, sizeof framed);
    check_bytes(left, prefix, sizeof prefix);
    require(event_count == 4 && events[0] == 1 && events[1] == 2 &&
            events[2] == 3 && events[3] == 4, "head/tail order or sharing changed");
    require(small_number(mlf_string_length(output)) == 9, "Unicode scalar length changed");
    const size_t scalars[] = {'4', ':', 65, 0, 955, 128512, '1', ':', 90};
    for (size_t i = 0; i < sizeof scalars / sizeof scalars[0]; ++i)
        require(small_number(mlf_string_code_at(output, number(i))) == scalars[i],
                "Unicode scalar index changed");
    check_bytes(mlf_prim1(PACK_STRING_FIELDS, pieces), framed, sizeof framed);
    check_bytes(mlf_force(mlf_application(mlf_primitive(PACK_STRING_FIELDS), pieces)),
                framed, sizeof framed);
    require(event_count == 4, "primitive entry re-evaluated a memoized fragment");
}

static MlfValue *stress_head(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    size_t index = small_number(mlf_env_get(env, 0));
    ++stress_heads;
    if (index % 64 == 0) GC_gcollect();
    const unsigned char bytes[] = {(unsigned char)('a' + index % 26), 0,
                                   0xce, 0xbb, 0xf0, 0x9f, 0x98, 0x80};
    return mlf_string((const char *)bytes, sizeof bytes);
}

static MlfValue *stress_tail(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    size_t index = small_number(mlf_env_get(env, 0));
    if (index == STRESS_PIECES) return nil();
    MlfEnv *head_env = mlf_env_new(1), *tail_env = mlf_env_new(1);
    mlf_env_set(head_env, 0, number(index));
    mlf_env_set(tail_env, 0, number(index + 1));
    MlfValue *head = mlf_thunk(stress_head, head_env);
    MlfValue *tail = mlf_thunk(stress_tail, tail_env);
    if (index % 127 == 0) GC_gcollect();
    return cons(head, tail);
}

static void stress(void) {
    size_t before = GC_get_gc_no();
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, number(0));
    kept = mlf_pack_string_fields(mlf_thunk(stress_tail, env));
    require(stress_heads == STRESS_PIECES, "lazy stress skipped or repeated a head");
    require(GC_get_gc_no() > before + 30, "stress did not collect while forcing fragments");
    for (size_t round = 0; round < 8; ++round) {
        for (size_t i = 0; i < 20000; ++i) {
            MlfEnv *temporary = mlf_env_new(i % 5);
            if (i % 5) mlf_env_set(temporary, 0, number(i));
            GC_reachable_here(temporary);
        }
        (void)GC_clear_stack(NULL);
        GC_gcollect();
    }
    require(small_number(mlf_string_length(kept)) == STRESS_PIECES * 6,
            "retained scalar length changed");
    for (size_t i = 0; i < STRESS_PIECES; ++i) {
        const size_t codes[] = {'4', ':', 'a' + i % 26, 0, 955, 128512};
        for (size_t j = 0; j < 6; ++j)
            require(small_number(mlf_string_code_at(kept, number(i * 6 + j))) == codes[j],
                    "retained result lost bytes across collection");
    }
    kept = NULL;
}

/* The compact static String layout is a public generated-code contract.
 * Lengths below intentionally exceed real storage; overflow must stop before
 * a single byte is copied from them. */
static size_t huge_indices[] = {0, 0};
static struct StaticString {
    uint32_t tag, padding;
    size_t length;
    const char *bytes;
    size_t *indices;
} huge = {8, 0, INT64_MAX - 1, "", huge_indices};

int main(int argc, char **argv) {
    require(argc == 2, "expected one probe mode");
    const char *mode = argv[1];
    GC_set_max_heap_size(8 * 1024 * 1024);
    if (!strcmp(mode, "no-interior")) GC_set_all_interior_pointers(0);
    if (!strcmp(mode, "success") || !strcmp(mode, "no-interior")) {
        ordinary();
        stress();
        puts("runtime fields: bytes, scalar indices, sharing, order, ABI, and GC passed");
        return 0;
    }
    if (!strcmp(mode, "list-bottom")) (void)mlf_pack_string_fields(poison("list-first"));
    else if (!strcmp(mode, "head-before-tail"))
        (void)mlf_pack_string_fields(cons(poison("head-first"), poison("tail-second")));
    else if (!strcmp(mode, "later-head-before-tail"))
        (void)mlf_pack_string_fields(cons(mlf_string("ok", 2),
            cons(poison("second-head"), poison("later-tail"))));
    else if (!strcmp(mode, "tail-bottom"))
        (void)mlf_pack_string_fields(cons(mlf_string("ok", 2), poison("tail-second")));
    else if (!strcmp(mode, "wrong-list"))
        (void)mlf_pack_string_fields(mlf_constructor(99, 0));
    else if (!strcmp(mode, "improper-tail"))
        (void)mlf_pack_string_fields(cons(mlf_string("ok", 2), mlf_constructor(99, 0)));
    else if (!strcmp(mode, "wrong-head"))
        (void)mlf_pack_string_fields(cons(number(0), nil()));
    else if (!strcmp(mode, "overflow-total"))
        (void)mlf_prim1(PACK_STRING_FIELDS, cons((MlfValue *)&huge, cons(mlf_string("x", 1), nil())));
    else if (!strcmp(mode, "overflow-wrap")) {
        huge.length = INT64_MAX - 2;
        (void)mlf_force(mlf_application(mlf_primitive(PACK_STRING_FIELDS),
            cons((MlfValue *)&huge, cons(mlf_string("xyz", 3), nil()))));
    } else if (!strcmp(mode, "overflow-scalars")) {
        huge.length = 0;
        huge_indices[0] = INT64_MAX;
        (void)mlf_pack_string_fields(cons((MlfValue *)&huge, poison("unneeded-tail")));
    } else if (!strcmp(mode, "overflow-before-tail"))
        (void)mlf_pack_string_fields(cons((MlfValue *)&huge, poison("unneeded-tail")));
    else require(0, "unknown probe mode");
    fputs("runtime fields: invalid operation unexpectedly succeeded\n", stderr);
    return 92;
}
