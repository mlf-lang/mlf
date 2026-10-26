/* Runtime ABI and call-by-need checks independent of generated LLVM.
 * BDWGC collection runs while update roots are live. */
#define _POSIX_C_SOURCE 200809L
#include "mlf_runtime.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gc/gc.h>
#include <gc/gc_mark.h>
#if defined(_WIN32)
#include <io.h>
#include <fcntl.h>
#define dup _dup
#define dup2 _dup2
#define close _close
#define fileno _fileno
#else
#include <unistd.h>
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
    if (calls == expected_calls) GC_gcollect();
    return answer;
}

static MlfValue *identity(MlfEnv *env, MlfValue *argument) {
    (void)env;
    ++calls;
    if (calls == expected_calls) GC_gcollect();
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
    uint32_t tag;
    memcpy(&tag, entry, sizeof tag);
    require(tag == 9 || tag == 28, "unexpected general constructor tag");
    if (tag == 28) env = (MlfEnv *)((unsigned char *)entry + 24);
    else memcpy(&env, (const unsigned char *)entry + 24, sizeof env);
    for (unsigned i = 0; i < count; ++i) {
        MlfValue *field;
        memcpy(&field, (const unsigned char *)env + (tag == 28 ? 0 : 8) + 8 * i, sizeof field);
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
    GC_gcollect();
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
    memset((unsigned char *)env + 8, 0, private_count * sizeof(MlfValue *));
    GC_gcollect();
    return mlf_constructor2(73, first, last);
}

static void private_thunks(void) {
    const unsigned counts[] = {0, 1, 2, 17, 513};
    for (unsigned c = 0; c < sizeof counts / sizeof *counts; ++c) {
        private_count = counts[c]; calls = 0;
        MlfValue *entry = mlf_thunk_new(consume_captures, private_count);
        MlfEnv *env;
        memcpy(&env, (const unsigned char *)entry + 16, sizeof env);
        MlfValue *answer = mlf_integer("340282366920938463463374607431768211456");
        for (unsigned i = 0; i < private_count; ++i)
            mlf_env_set(env, i, i == 0 || i + 1 == private_count ? answer : mlf_thunk(poison, NULL));
        GC_gcollect();
        MlfValue *result = mlf_force(entry);
        require(calls == 1 && mlf_force(entry) == result, "private thunk was reexecuted");
        if (private_count) {
            require(mlf_field(result, 0) == answer && mlf_field(result, 1) == answer, "private captures lost across collection");
            for (unsigned i = 0; i < private_count; ++i) {
                MlfValue *slot;
                memcpy(&slot, (const unsigned char *)env + 8 + i * sizeof slot, sizeof slot);
                require(slot == NULL, "consumed private capture retained");
            }
        }
    }
}

static size_t *string_index_storage(MlfValue *entry) {
    size_t *indices;
    memcpy(&indices, (const unsigned char *)entry + 24, sizeof indices);
    return indices;
}

enum { SPARSE_SCALARS = 1024 * 1024 };
static unsigned sparse_scalar(size_t i) {
    if (i == 0 || i == 123) return 955;
    if (i == 124 || i == 4096 || i == SPARSE_SCALARS - 1) return 128512;
    return (unsigned)(i % 128);
}

static MlfValue *sparse_string(void) {
    char *bytes = malloc(SPARSE_SCALARS + 11);
    require(bytes != NULL, "sparse Unicode probe allocation failed");
    size_t position = 0;
    for (size_t i = 0; i < SPARSE_SCALARS; ++i) {
        unsigned scalar = sparse_scalar(i);
        if (scalar == 955) { memcpy(bytes + position, "\xce\xbb", 2); position += 2; }
        else if (scalar == 128512) { memcpy(bytes + position, "\xf0\x9f\x98\x80", 4); position += 4; }
        else bytes[position++] = (char)scalar;
    }
    require(position == SPARSE_SCALARS + 11, "sparse Unicode fixture size");
    MlfValue *result = mlf_string(bytes, position);
    free(bytes);
    return result;
}

static MlfValue *scalar_index(size_t i) {
    char decimal[32];
    snprintf(decimal, sizeof decimal, "%zu", i);
    return mlf_integer(decimal);
}

static void sparse_strings(void) {
    MlfValue *text = sparse_string();
    for (unsigned pass = 0; pass < 3; ++pass) {
        require(mlf_prim1(46, text) == mlf_integer("1048576"), "sparse Unicode scalar length changed");
        const size_t centers[] = {0, 123, 124, 4096, SPARSE_SCALARS - 1};
        for (size_t center = 0; center < sizeof centers / sizeof *centers; ++center) {
            size_t first = centers[center] > 16 ? centers[center] - 16 : 0;
            size_t last = centers[center] + 16 < SPARSE_SCALARS ? centers[center] + 16 : SPARSE_SCALARS - 1;
            for (size_t i = first; i <= last; ++i)
                require(mlf_prim2(47, text, scalar_index(i)) == scalar_index(sparse_scalar(i)), "sparse Unicode sequential index changed");
            MlfValue *slice = mlf_prim3(48, text, scalar_index(first), scalar_index(last - first + 1));
            require(mlf_prim1(46, slice) == scalar_index(last - first + 1), "sparse Unicode slice length changed");
            for (size_t i = first; i <= last; ++i)
                require(mlf_prim2(47, slice, scalar_index(i - first)) == scalar_index(sparse_scalar(i)), "sparse Unicode slice used byte offsets");
        }
        uint32_t state = 17;
        for (unsigned attempt = 0; attempt < 2000; ++attempt) {
            state = state * UINT32_C(1664525) + UINT32_C(1013904223);
            size_t i = state & (SPARSE_SCALARS - 1);
            require(mlf_prim2(47, text, scalar_index(i)) == scalar_index(sparse_scalar(i)), "sparse Unicode random index changed");
        }
        require(mlf_prim1(46, mlf_prim3(48, text, scalar_index(SPARSE_SCALARS), mlf_integer("0"))) == mlf_integer("0"), "sparse Unicode end slice changed");
        GC_clear_stack(NULL);
        GC_gcollect();
    }
}

static void strings(void) {
    MlfValue *ascii = mlf_string("A\0z\x7f", 4);
    MlfValue *empty = mlf_string("", 0);
    MlfValue *mixed = mlf_string("A\xce\xbb\0\xf0\x9f\x98\x80Z", 9);
    const size_t size = 1024 * 1024;
    char *bytes = malloc(size);
    require(bytes != NULL, "large ASCII probe allocation failed");
    for (size_t i = 0; i < size; ++i) bytes[i] = (char)(i % 128);
    MlfValue *large = mlf_string(bytes, size);
    free(bytes);
    for (unsigned pass = 0; pass < 3; ++pass) {
        require(mlf_prim1(46, ascii) == mlf_integer("4"), "ASCII scalar length changed");
        require(mlf_prim2(47, ascii, mlf_integer("0")) == mlf_integer("65") &&
                mlf_prim2(47, ascii, mlf_integer("1")) == mlf_integer("0") &&
                mlf_prim2(47, ascii, mlf_integer("3")) == mlf_integer("127"), "ASCII scalar indexing changed");
        require(mlf_prim1(46, empty) == mlf_integer("0"), "empty scalar length changed");
        require(mlf_prim1(46, large) == mlf_integer("1048576") &&
                mlf_prim2(47, large, mlf_integer("1048575")) == mlf_integer("127") &&
                mlf_prim2(47, large, mlf_integer("524288")) == mlf_integer("0"), "large ASCII or embedded NUL changed");
        require(string_index_storage(ascii) != NULL &&
                string_index_storage(ascii) == string_index_storage(empty) &&
                string_index_storage(ascii) == string_index_storage(large), "ASCII indexing allocated per-string offset tables");
        require(mlf_prim1(46, mixed) == mlf_integer("5") &&
                mlf_prim2(47, mixed, mlf_integer("1")) == mlf_integer("955") &&
                mlf_prim2(47, mixed, mlf_integer("2")) == mlf_integer("0") &&
                mlf_prim2(47, mixed, mlf_integer("3")) == mlf_integer("128512") &&
                mlf_prim2(47, mixed, mlf_integer("4")) == mlf_integer("90"), "mixed Unicode scalar offsets changed");
        require(string_index_storage(mixed) != string_index_storage(ascii), "Unicode indexing reused ASCII offsets");
        MlfValue *slice = mlf_prim3(48, ascii, mlf_integer("1"), mlf_integer("2"));
        require(mlf_truth(mlf_prim2(12, slice, mlf_string("\0z", 2))), "ASCII slice lost embedded NUL");
        require(mlf_prim1(46, mlf_prim3(48, ascii, mlf_integer("4"), mlf_integer("0"))) == mlf_integer("0") &&
                mlf_prim1(46, mlf_prim3(48, empty, mlf_integer("0"), mlf_integer("0"))) == mlf_integer("0"), "ASCII end/empty slice changed");
        slice = mlf_prim3(48, mixed, mlf_integer("1"), mlf_integer("3"));
        require(mlf_truth(mlf_prim2(12, slice, mlf_string("\xce\xbb\0\xf0\x9f\x98\x80", 7))), "Unicode slice used byte offsets");
        require(mlf_prim1(46, mlf_prim3(48, mixed, mlf_integer("5"), mlf_integer("0"))) == mlf_integer("0"), "Unicode end slice changed");
        MlfValue *joined = mlf_prim2(6, ascii, mixed);
        require(mlf_prim1(46, joined) == mlf_integer("9") &&
                mlf_prim2(47, joined, mlf_integer("5")) == mlf_integer("955"), "concatenation cached incorrect scalar offsets");
        require(mlf_prim2(47, mlf_prim1(49, mlf_integer("127")), mlf_integer("0")) == mlf_integer("127") &&
                mlf_prim2(47, mlf_prim1(49, mlf_integer("128512")), mlf_integer("0")) == mlf_integer("128512"), "scalar construction changed");
        GC_clear_stack(NULL);
        GC_gcollect();
    }
}

static void string_failure(const char *mode) {
    /* Bounds failures need the sparse representation, not a million scalars. */
    static const char sparse_bytes[] = "012345678901234567890123456789\xce\xbb";
    static const struct {
        const char *name, *bytes;
        uint64_t length;
        int operation;
        const char *offset, *count;
    } failures[] = {
        {"string-sparse-negative-index", NULL, 0, 47, "-1", NULL},
        {"string-sparse-past-index", NULL, 0, 47, "31", NULL},
        {"string-sparse-huge-index", NULL, 0, 47, "18446744073709551616", NULL},
        {"string-sparse-past-offset", NULL, 0, 48, "32", "0"},
        {"string-sparse-past-count", NULL, 0, 48, "30", "2"},
        {"string-ascii-negative-index", "abc", 3, 47, "-1", NULL},
        {"string-ascii-past-index", "abc", 3, 47, "3", NULL},
        {"string-ascii-huge-index", "abc", 3, 47, "18446744073709551616", NULL},
        {"string-empty-index", "", 0, 47, "0", NULL},
        {"string-mixed-negative-index", "a\xce\xbb", 3, 47, "-1", NULL},
        {"string-mixed-past-index", "a\xce\xbb", 3, 47, "2", NULL},
        {"string-mixed-huge-index", "a\xce\xbb", 3, 47, "18446744073709551616", NULL},
        {"string-ascii-negative-offset", "abc", 3, 48, "-1", "0"},
        {"string-ascii-past-offset", "abc", 3, 48, "4", "0"},
        {"string-ascii-negative-count", "abc", 3, 48, "0", "-1"},
        {"string-ascii-past-count", "abc", 3, 48, "2", "2"},
        {"string-ascii-huge-count", "abc", 3, 48, "0", "18446744073709551616"},
        {"string-empty-past-count", "", 0, 48, "0", "1"},
        {"string-mixed-negative-offset", "a\xce\xbb", 3, 48, "-1", "0"},
        {"string-mixed-past-offset", "a\xce\xbb", 3, 48, "3", "0"},
        {"string-mixed-negative-count", "a\xce\xbb", 3, 48, "0", "-1"},
        {"string-mixed-past-count", "a\xce\xbb", 3, 48, "1", "2"},
        {"string-mixed-huge-count", "a\xce\xbb", 3, 48, "0", "18446744073709551616"},
        {"string-invalid-prefix", "ascii\x80", 6, 46, NULL, NULL},
        {"string-invalid-surrogate-index", "\xed\xa0\x80", 3, 47, "0", NULL},
        {"string-invalid-surrogate-slice", "\xed\xa0\x80", 3, 48, "0", "0"},
        {"string-invalid-overlong", "\xc0\xaf", 2, 46, NULL, NULL},
        {"string-invalid-truncated", "\xf0\x9f", 2, 46, NULL, NULL},
        {"string-invalid-stray", "\x80", 1, 46, NULL, NULL},
        {"string-invalid-range", "\xf4\x90\x80\x80", 4, 46, NULL, NULL},
        {"string-invalid-after-nul", "a\0\x80", 3, 46, NULL, NULL}
    };
    for (size_t i = 0; i < sizeof failures / sizeof *failures; ++i) {
        if (strcmp(mode, failures[i].name)) continue;
        MlfValue *text = failures[i].bytes ? mlf_string(failures[i].bytes, failures[i].length) : mlf_string(sparse_bytes, sizeof sparse_bytes - 1);
        if (!failures[i].bytes) {
            require(mlf_prim1(46, text) == mlf_integer("31"), "small sparse scalar length changed");
            size_t *indices = string_index_storage(text);
            require(indices && indices[0] == SIZE_MAX && indices[1] == 31 && indices[2] == 1,
                    "bounds probe did not select sparse Unicode indexing");
        }
        if (failures[i].operation == 46) (void)mlf_prim1(46, text);
        else if (failures[i].operation == 47) (void)mlf_prim2(47, text, mlf_integer(failures[i].offset));
        else (void)mlf_prim3(48, text, mlf_integer(failures[i].offset), mlf_integer(failures[i].count));
        return;
    }
    require(0, "unknown string failure mode");
}

/* The generated compact string ABI permits writable static values. Their
 * Unicode index must remain rooted even when no evaluated MLF value owns it. */
static struct LiteralString {
    int32_t tag, padding;
    uint64_t length;
    const unsigned char *bytes;
    size_t *indices;
} unicode_literal = {8, 0, 6, (const unsigned char *)"\xce\xbb\xf0\x9f\x98\x80", NULL},
  sparse_literal = {8, 0, 32, (const unsigned char *)"012345678901234567890123456789\xce\xbb", NULL},
  ascii_literal = {8, 0, 3, (const unsigned char *)"abc", NULL},
  nul_literal = {8, 0, 3, (const unsigned char *)"a\0b", NULL},
  empty_literal = {8, 0, 0, (const unsigned char *)"", NULL};
static void static_strings(void) {
    MlfValue *unicode = (MlfValue *)&unicode_literal;
    MlfValue *sparse = (MlfValue *)&sparse_literal;
    MlfValue *ascii = (MlfValue *)&ascii_literal;
    MlfValue *nul = (MlfValue *)&nul_literal;
    MlfValue *empty = (MlfValue *)&empty_literal;
    for (unsigned pass = 0; pass < 3; ++pass) {
        require(mlf_prim1(46, unicode) == mlf_integer("2"), "static Unicode length changed");
        require(mlf_prim2(47, unicode, mlf_integer("0")) == mlf_integer("955"), "static Unicode first scalar changed");
        require(mlf_prim2(47, unicode, mlf_integer("1")) == mlf_integer("128512"), "static Unicode final scalar changed");
        require(mlf_prim1(46, sparse) == mlf_integer("31") &&
                mlf_prim2(47, sparse, mlf_integer("30")) == mlf_integer("955"), "static sparse Unicode offsets changed");
        require(mlf_prim1(46, nul) == mlf_integer("3") &&
                mlf_prim2(47, nul, mlf_integer("1")) == mlf_integer("0"), "static embedded NUL changed");
        require(mlf_prim1(46, ascii) == mlf_integer("3") &&
                mlf_prim2(47, ascii, mlf_integer("2")) == mlf_integer("99"), "static ASCII string changed");
        require(mlf_prim1(46, empty) == mlf_integer("0"), "static empty string changed");
        require(ascii_literal.indices == nul_literal.indices && ascii_literal.indices == empty_literal.indices &&
                ascii_literal.indices != unicode_literal.indices, "static ASCII/Unicode cache distinction changed");
        (void)GC_clear_stack(NULL);
        GC_gcollect();
    }
}

#if defined(MLF_ALLOCATION_AUDIT)
static size_t constructor_audits;
void mlf_bench_constructed_node(int64_t identity) {
    (void)identity;
    ++constructor_audits;
}
#endif

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
#if defined(MLF_ALLOCATION_AUDIT)
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
#if defined(MLF_ALLOCATION_AUDIT)
        require(constructor_audits == before + 140 * (count + 1), "inline constructor audit coverage");
        for (size_t head = 0; head < 33; ++head)
            require(mlf_constructor_pending[head] == NULL, "audited constructor bypassed hook");
#endif
    }
}

/* Retain independent raw lines across scratch-buffer reuse, growth, GC and
 * complete runtime cleanup. These bytes deliberately include NUL and invalid
 * UTF-8: getByteLine must remain a byte operation. */
static void check_bytes(MlfValue *array, const unsigned char *expected, size_t count) {
    size_t length;
    unsigned char *cells;
    memcpy(&length, (unsigned char *)array + 8, sizeof length);
    memcpy(&cells, (unsigned char *)array + 16, sizeof cells);
    require(length == count, "raw line length changed");
    require(!memcmp(cells, expected, count), "retained raw line changed");
}

static void raw_lines(void) {
    const unsigned char first[] = {255, 0, 128, 10};
    unsigned char long_line[4099];
    memset(long_line, 'A', sizeof long_line);
    long_line[sizeof long_line - 2] = 13;
    long_line[sizeof long_line - 1] = 10;
    const unsigned char empty[] = {10};
    const unsigned char final[] = {0, 7, 255};
    FILE *input = tmpfile();
    require(input != NULL, "raw-line temporary input");
    require(fwrite(first, 1, sizeof first, input) == sizeof first &&
            fwrite(long_line, 1, sizeof long_line, input) == sizeof long_line &&
            fwrite(empty, 1, sizeof empty, input) == sizeof empty &&
            fwrite(final, 1, sizeof final, input) == sizeof final,
            "write raw-line input");
    rewind(input);
    int saved_input = dup(fileno(stdin));
    require(saved_input >= 0 && dup2(fileno(input), fileno(stdin)) >= 0,
            "redirect raw-line input");
#if defined(_WIN32)
    int previous_mode = _setmode(fileno(stdin), _O_BINARY);
    require(previous_mode != -1, "set binary raw-line input");
#endif
    require(!setvbuf(stdin, NULL, _IONBF, 0), "set raw-line buffering");
    clearerr(stdin);
    MlfValue *a = mlf_get_byte_line();
    MlfValue *b = mlf_get_byte_line();
    MlfValue *c = mlf_get_byte_line();
    MlfValue *d = mlf_get_byte_line();
    GC_gcollect();
    check_bytes(a, first, sizeof first);
    check_bytes(b, long_line, sizeof long_line);
    check_bytes(c, empty, sizeof empty);
    check_bytes(d, final, sizeof final);
    check_bytes(mlf_get_byte_line(), empty, 0);
    check_bytes(mlf_get_byte_line(), empty, 0);
    require(mlf_run(mlf_integer("0"), 0) == 0, "raw-line cleanup");
    rewind(input);
    clearerr(stdin);
    check_bytes(mlf_get_byte_line(), first, sizeof first);
    GC_gcollect();
    check_bytes(a, first, sizeof first);
    check_bytes(b, long_line, sizeof long_line);
    check_bytes(d, final, sizeof final);
    require(mlf_run(mlf_integer("0"), 0) == 0, "second raw-line cleanup");
#if defined(_WIN32)
    require(_setmode(fileno(stdin), previous_mode) != -1, "restore raw-line mode");
#endif
    require(dup2(saved_input, fileno(stdin)) >= 0 && !close(saved_input),
            "restore raw-line input");
    clearerr(stdin);
    require(!fclose(input), "close raw-line input");
}

int main(int argc, char **argv) {
    require(argc == 2, "expected one probe mode");
    const char *mode = argv[1];
    GC_set_max_heap_size(8 * 1024 * 1024);
    if (!strcmp(mode, "no-interior")) GC_set_all_interior_pointers(0);
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
        strings();
        sparse_strings();
        raw_lines();
        /* Ordinary cleanup must release real Unicode tables, never the shared
         * ASCII marker. It also exercises the marker after pooled values die. */
        (void)mlf_run(mlf_integer("0"), 0);
        puts("runtime values: sharing, lazy fields, recursive data, and spill boundaries passed");
        return 0;
    }
    if (!strcmp(mode, "capture-null-code")) (void)mlf_thunk_new(NULL, 1);
    else if (!strncmp(mode, "string-", 7)) string_failure(mode);
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
