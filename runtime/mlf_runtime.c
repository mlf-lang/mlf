/* Runtime support for native xMLF functions, not an AST interpreter.
 * Call-by-need memoizes values; executing an IO action is never memoized.
 * The IO driver and explicitly rooted native IO entries collect. Ordinary
 * lazy evaluation and scalar primitives never collect on the native stack.
 */
#define _POSIX_C_SOURCE 200809L
#include "mlf_runtime.h"
#include "khash.h"
#include <gmp.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MLF_GC_THRESHOLD
#define MLF_GC_THRESHOLD 4096
#endif
#ifndef MLF_GC_INTEGER_BYTES
#define MLF_GC_INTEGER_BYTES (8 * 1024 * 1024)
#endif

typedef enum { OBJECT_VALUE, OBJECT_ENV } ObjectKind;
typedef struct Object {
    struct Object *next;
    ObjectKind kind;
    unsigned marked;
} Object;

typedef enum {
    HOLE, BUSY, INDIRECT, THUNK, APPLICATION, CLOSURE,
    INTEGER, BOOLEAN, STRING, CONSTRUCTOR, PRIMITIVE, ACTION,
    CONSTRUCTOR_1, CONSTRUCTOR_2, DOUBLE, INT_ARRAY, DOUBLE_ARRAY,
    WRITE_INT_ACTION, WRITE_DOUBLE_ACTION, NATIVE_IO,
    BYTE_ARRAY, WRITE_BYTE_ACTION, PUT_BYTES_ACTION, INT_TABLE, WRITE_TABLE_ACTION,
    SMALL_INT_TABLE
} Tag;

/* These numbers are shared with primitiveCode in MLF.LLVM. */
typedef enum {
    IO_RETURN, IO_BIND, PUT_STR, PUT_STR_LN, GET_LINE, PRINT_INT,
    CONCAT_STRING, SHOW_INT, ADD_INT, SUB_INT, EQ_INT, LT_INT,
    EQ_STRING, IF_THEN_ELSE, MUL_INT, QUOT_INT, REM_INT, READ_INT,
    ADD_DOUBLE, SUB_DOUBLE, MUL_DOUBLE, DIV_DOUBLE, SQRT_DOUBLE,
    EQ_DOUBLE, LT_DOUBLE, INT_TO_DOUBLE, FORMAT_DOUBLE,
    NEW_INT_ARRAY, READ_INT_ARRAY, WRITE_INT_ARRAY, LENGTH_INT_ARRAY,
    NEW_DOUBLE_ARRAY, READ_DOUBLE_ARRAY, WRITE_DOUBLE_ARRAY, LENGTH_DOUBLE_ARRAY,
    NEW_BYTE_ARRAY, READ_BYTE_ARRAY, WRITE_BYTE_ARRAY, LENGTH_BYTE_ARRAY,
    BYTE_ARRAY_FROM_STRING, PUT_BYTES, GET_BYTE_LINE, NEW_INT_TABLE, READ_INT_TABLE, WRITE_INT_TABLE,
    AND_INT,
    PRIMITIVE_COUNT
} Primitive;

struct MlfEnv {
    Object object;
    size_t count;
    MlfValue *slots[];
};

static khint_t integer_hash(MlfValue *key);
static int integer_equal(MlfValue *a, MlfValue *b);
KHASH_INIT(mlf_int, MlfValue *, MlfValue *, 1, integer_hash, integer_equal)
/* Immediate keys need only pointer equality. Upgrade to the fully general
 * table on the first large key; arbitrary-precision values work in both. */
#define tagged_hash(key) kh_int64_hash_func((uint64_t)((int64_t)(intptr_t)(key) >> 1))
#define tagged_equal(a,b) ((a) == (b))
KHASH_INIT(mlf_tagged, MlfValue *, MlfValue *, 1, tagged_hash, tagged_equal)

struct MlfValue {
    Object object;
    Tag tag;
    union {
        MlfValue *indirect;
        struct { MlfCode code; MlfEnv *env; } closure;
        struct { MlfValue *function, *argument; } application;
        mpz_t integer;
        double floating;
        struct { size_t length; MlfValue **cells; } int_array;
        struct { size_t length; double *cells; } double_array;
        struct { size_t length; unsigned char *cells; } byte_array;
        khash_t(mlf_int) *int_table;
        khash_t(mlf_tagged) *small_table;
        struct { MlfValue *array, *index, *entry; } array_write;
        int boolean;
        struct { size_t length; char *bytes; } string;
        struct { int64_t identity, arity; MlfEnv *fields; } constructor;
        struct { int64_t identity; MlfValue *fields[2]; } packed;
        struct { Primitive identity; MlfEnv *arguments; } primitive;
        struct { Primitive operation; MlfValue *first, *second; } action;
    } as;
};

typedef struct Stack {
    void **items;
    size_t count, capacity;
    struct Stack *next;
} Stack;
static Object *heap;
/* Register auxiliary stacks so fatal IO/black-hole errors also release them. */
static Stack *active_stacks;
static MlfRoots *native_roots;
static MlfValue **io_current;
static const Stack *io_continuations;
static size_t objects;
static size_t collection_limit = MLF_GC_THRESHOLD;
static size_t integer_bytes;
static size_t integer_collection_limit = MLF_GC_INTEGER_BYTES;
static void cleanup(void);

/* The low bits distinguish immediate integers, booleans and nullary data
 * from aligned heap pointers. Integers outside the signed 63-bit range keep
 * their arbitrary-precision GMP representation. */
_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "native runtime requires a 64-bit ABI");
_Static_assert(_Alignof(MlfValue) >= 8, "native tagged pointer alignment");
_Static_assert(offsetof(MlfValue, as.packed.identity) == 24, "constructor identity ABI");
_Static_assert(offsetof(MlfValue, as.packed.fields) == 32, "constructor field ABI");
_Static_assert(offsetof(MlfValue, as.floating) == 24, "Double payload ABI");
_Static_assert(offsetof(MlfValue, as.int_array.length) == 24 &&
               offsetof(MlfValue, as.double_array.length) == 24 &&
               offsetof(MlfValue, as.byte_array.length) == 24, "array length ABI");
_Static_assert(offsetof(MlfValue, as.int_array.cells) == 32 &&
               offsetof(MlfValue, as.double_array.cells) == 32 &&
               offsetof(MlfValue, as.byte_array.cells) == 32, "array storage ABI");
_Static_assert(sizeof(MlfValue) == 48, "managed value size ABI");
_Static_assert(sizeof(MlfRoots) == 24, "native roots ABI");
#define SMALL_MIN (-(INT64_C(1) << 62))
#define SMALL_MAX ((INT64_C(1) << 62) - 1)
static int immediate(const void *p) { return ((uintptr_t)p & 7) != 0; }
static int small_integer(const MlfValue *p) { return ((uintptr_t)p & 1) != 0; }
static int64_t small_value(const MlfValue *p) { return (int64_t)(intptr_t)p >> 1; }
static MlfValue *small(int64_t n) { return (MlfValue *)(uintptr_t)(((uint64_t)n << 1) | 1); }
/* Hash all integer representations by value, including negative/GMP keys. */
static khint_t integer_hash(MlfValue *key) {
    if (small_integer(key)) return kh_int64_hash_func((uint64_t)small_value(key));
    if (mpz_fits_slong_p(key->as.integer))
        return kh_int64_hash_func((uint64_t)mpz_get_si(key->as.integer));
    khint_t hash = (khint_t)mpz_sgn(key->as.integer);
    for (size_t i = 0; i < mpz_size(key->as.integer); ++i)
        hash = (hash * 16777619u) ^ kh_int64_hash_func(mpz_getlimbn(key->as.integer,(mp_size_t)i));
    return hash;
}
static int integer_equal(MlfValue *a, MlfValue *b) {
    if (a == b) return 1;
    if (small_integer(a)) return small_integer(b) ? 0 : mpz_cmp_si(b->as.integer,small_value(a)) == 0;
    if (small_integer(b)) return mpz_cmp_si(a->as.integer,small_value(b)) == 0;
    return mpz_cmp(a->as.integer,b->as.integer) == 0;
}

static int nullary(const MlfValue *p) { return ((uintptr_t)p & 7) == 4; }
static int boolean_value(const MlfValue *p) { return ((uintptr_t)p & 3) == 2; }

/* Fixed-size managed values share allocation pages. Reclamation still follows
 * reachability, not benchmark-specific lifetimes or a datatype-specific arena. */
typedef struct ValuePage {
    struct ValuePage *next;
    size_t used;
    MlfValue values[4096];
} ValuePage;
static ValuePage *value_pages;
static MlfValue *free_values;

#ifdef MLF_ALLOCATION_AUDIT
extern void mlf_bench_constructed_node(int64_t tag);
#define CONSTRUCTED(tag) mlf_bench_constructed_node(tag)
#else
#define CONSTRUCTED(tag) ((void)0)
#endif

#ifdef MLF_TABLE_AUDIT
extern void mlf_bench_table_created(MlfValue *table);
extern void mlf_bench_table_written(MlfValue *table, int inserted);
#define TABLE_CREATED(table) mlf_bench_table_created(table)
#define TABLE_WRITTEN(table, inserted) mlf_bench_table_written(table, inserted)
#else
#define TABLE_CREATED(table) ((void)0)
#define TABLE_WRITTEN(table, inserted) ((void)0)
#endif

static _Noreturn void fail(const char *message) {
    fprintf(stderr, "Runtime: %s\n", message);
    cleanup();
    exit(1);
}

static void *allocate(size_t size) {
    void *memory = calloc(1, size);
    if (!memory) fail("out of memory");
    return memory;
}

static void push(Stack *stack, void *item) {
    if (stack->count == stack->capacity) {
        if (!stack->capacity) { stack->next = active_stacks; active_stacks = stack; }
        size_t capacity = stack->capacity ? stack->capacity * 2 : 64;
        if (capacity < stack->capacity || capacity > SIZE_MAX / sizeof(void *)) fail("stack too large");
        void **items = realloc(stack->items, capacity * sizeof(void *));
        if (!items) fail("out of memory");
        stack->items = items;
        stack->capacity = capacity;
    }
    stack->items[stack->count++] = item;
}

static void release_stack(Stack *stack) {
    if (!stack->items) return;
    Stack **cursor = &active_stacks;
    while (*cursor && *cursor != stack) cursor = &(*cursor)->next;
    if (*cursor) *cursor = stack->next;
    free(stack->items);
    *stack = (Stack){0};
}

static void *object(size_t size, ObjectKind kind) {
    Object *result = allocate(size);
    result->kind = kind;
    result->next = heap;
    heap = result;
    ++objects;
    return result;
}

static MlfValue *value(Tag tag) {
    MlfValue *result;
    if (free_values) {
        result = free_values;
        free_values = (MlfValue *)result->object.next;
    } else {
        if (!value_pages || value_pages->used == 4096) {
            ValuePage *page = allocate(sizeof(*page));
            page->next = value_pages;
            value_pages = page;
        }
        result = &value_pages->values[value_pages->used++];
    }
    result->object = (Object){heap, OBJECT_VALUE, 0};
    heap = &result->object;
    ++objects;
    result->tag = tag;
    return result;
}

MlfEnv *mlf_env_new(uint64_t count) {
    if (count > (SIZE_MAX - sizeof(MlfEnv)) / sizeof(MlfValue *)) fail("environment too large");
    MlfEnv *env = object(sizeof(*env) + (size_t)count * sizeof(MlfValue *), OBJECT_ENV);
    env->count = (size_t)count;
    return env;
}

void mlf_env_set(MlfEnv *env, uint64_t index, MlfValue *entry) {
    if (!env || index >= env->count || !entry) fail("invalid environment write");
    env->slots[index] = entry;
}

MlfValue *mlf_env_get(MlfEnv *env, uint64_t index) {
    if (!env || index >= env->count || !env->slots[index]) fail("invalid environment read");
    return env->slots[index];
}

static MlfValue *code_value(Tag tag, MlfCode code, MlfEnv *env) {
    if (!code) fail("missing native code");
    MlfValue *result = value(tag);
    result->as.closure.code = code;
    result->as.closure.env = env;
    return result;
}

MlfValue *mlf_thunk(MlfCode code, MlfEnv *env) { return code_value(THUNK, code, env); }
MlfValue *mlf_closure(MlfCode code, MlfEnv *env) { return code_value(CLOSURE, code, env); }
MlfValue *mlf_native_io(MlfCode code, MlfEnv *env) { return code_value(NATIVE_IO, code, env); }
MlfValue *mlf_hole(void) { return value(HOLE); }

void mlf_fill(MlfValue *hole, MlfValue *entry) {
    if (!hole || hole->tag != HOLE || !entry) fail("invalid recursive binding");
    hole->tag = INDIRECT;
    hole->as.indirect = entry;
}

MlfValue *mlf_application(MlfValue *function, MlfValue *argument) {
    MlfValue *result = value(APPLICATION);
    result->as.application.function = function;
    result->as.application.argument = argument;
    return result;
}

MlfValue *mlf_integer(const char *decimal) {
    char *end;
    errno = 0;
    int64_t n = strtoll(decimal, &end, 10);
    if (!errno && end != decimal && !*end && n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
    MlfValue *result = value(INTEGER);
    mpz_init(result->as.integer);
    if (mpz_set_str(result->as.integer, decimal, 10)) fail("invalid integer literal");
    integer_bytes += mpz_size(result->as.integer) * sizeof(mp_limb_t);
    return result;
}

MlfValue *mlf_boolean(int64_t boolean) {
    return (MlfValue *)(uintptr_t)(boolean ? 6 : 2);
}

MlfValue *mlf_double(double n) {
    MlfValue *result = value(DOUBLE);
    result->as.floating = n;
    return result;
}

MlfValue *mlf_string(const char *bytes, uint64_t length) {
    if (length >= SIZE_MAX) fail("string too large");
    MlfValue *result = value(STRING);
    result->as.string.length = (size_t)length;
    result->as.string.bytes = allocate((size_t)length + 1);
    memcpy(result->as.string.bytes, bytes, (size_t)length);
    return result;
}

MlfValue *mlf_constructor(int64_t identity, int64_t arity) {
    if (identity < 0 || arity < 0) fail("invalid constructor descriptor");
    if (!arity && identity < (INT64_C(1) << 60)) {
        CONSTRUCTED(identity);
        return (MlfValue *)(uintptr_t)(((uint64_t)identity << 3) | 4);
    }
    MlfValue *result = value(CONSTRUCTOR);
    result->as.constructor.identity = identity;
    result->as.constructor.arity = arity;
    result->as.constructor.fields = mlf_env_new(0);
    return result;
}

MlfValue *mlf_constructor1(int64_t identity, MlfValue *a) {
    MlfValue *result = value(CONSTRUCTOR_1);
    result->as.packed.identity = identity;
    result->as.packed.fields[0] = a;
    CONSTRUCTED(identity);
    return result;
}

MlfValue *mlf_constructor2(int64_t identity, MlfValue *a, MlfValue *b) {
    MlfValue *result = value(CONSTRUCTOR_2);
    result->as.packed.identity = identity;
    result->as.packed.fields[0] = a;
    result->as.packed.fields[1] = b;
    CONSTRUCTED(identity);
    return result;
}

static MlfValue *action(Primitive operation, MlfValue *first, MlfValue *second) {
    MlfValue *result = value(ACTION);
    result->as.action.operation = operation;
    result->as.action.first = first;
    result->as.action.second = second;
    return result;
}

MlfValue *mlf_primitive(int64_t identity) {
    if (identity < 0 || identity >= PRIMITIVE_COUNT) fail("unknown primitive");
    if (identity == GET_LINE || identity == GET_BYTE_LINE || identity == NEW_INT_TABLE)
        return action((Primitive)identity, NULL, NULL);
    MlfValue *result = value(PRIMITIVE);
    result->as.primitive.identity = (Primitive)identity;
    result->as.primitive.arguments = mlf_env_new(0);
    return result;
}

static MlfValue *force(MlfValue *entry);
static MlfValue *expect(MlfValue *entry, Tag tag) {
    MlfValue *result = mlf_force(entry);
    if (immediate(result)) {
        if ((tag == INTEGER && small_integer(result)) ||
            (tag == BOOLEAN && boolean_value(result)) ||
            (tag == CONSTRUCTOR && nullary(result))) return result;
        fail("invalid value for runtime operation");
    }
    if (tag == CONSTRUCTOR && (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2)) return result;
    if (tag == INT_TABLE && result->tag == SMALL_INT_TABLE) return result;
    if (result->tag != tag) fail("invalid value for runtime operation");
    return result;
}

int64_t mlf_tag(MlfValue *entry) {
    MlfValue *result = expect(entry, CONSTRUCTOR);
    if (nullary(result)) return (int64_t)((uintptr_t)result >> 3);
    if (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2) return result->as.packed.identity;
    if ((uint64_t)result->as.constructor.arity != result->as.constructor.fields->count)
        fail("case scrutinized a partial constructor");
    return result->as.constructor.identity;
}

MlfValue *mlf_field(MlfValue *entry, uint64_t index) {
    MlfValue *result = expect(entry, CONSTRUCTOR);
    if (nullary(result)) fail("invalid environment read");
    if (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2) {
        if (index >= (uint64_t)(result->tag == CONSTRUCTOR_1 ? 1 : 2)) fail("invalid environment read");
        return result->as.packed.fields[index];
    }
    return mlf_env_get(result->as.constructor.fields, index);
}

_Noreturn void mlf_match_failure(void) { fail("non-exhaustive runtime case"); }
_Noreturn void mlf_bounds_failure(void) { fail("array index out of bounds"); }

/* Non-forcing guard for an eager numeric region. INDIRECT chains only arise
 * from completed evaluation (recursive holes may form cycles, so they are
 * deliberately not followed here). A miss uses the ordinary lazy worker. */
MlfValue *mlf_peek(MlfValue *entry) {
    if (!entry) return NULL;
    if (immediate(entry) || entry->tag >= CLOSURE) return entry;
    if (entry->tag == INDIRECT) {
        MlfValue *next = entry->as.indirect;
        if (next && (immediate(next) || next->tag >= CLOSURE)) return next;
    }
    return NULL;
}

static MlfEnv *append(MlfEnv *env, MlfValue *entry) {
    if (env->count == SIZE_MAX) fail("too many arguments");
    MlfEnv *result = mlf_env_new(env->count + 1);
    memcpy(result->slots, env->slots, env->count * sizeof(MlfValue *));
    result->slots[env->count] = entry;
    return result;
}

static MlfValue *show_integer(MlfValue *entry) {
    MlfValue *integer = expect(entry, INTEGER);
    if (small_integer(integer)) {
        char text[32];
        int length = snprintf(text, sizeof(text), "%" PRId64, small_value(integer));
        return mlf_string(text, (uint64_t)length);
    }
    size_t capacity = mpz_sizeinbase(integer->as.integer, 10) + 3;
    char *buffer = allocate(capacity);
    mpz_get_str(buffer, 10, integer->as.integer);
    MlfValue *result = mlf_string(buffer, strlen(buffer));
    free(buffer);
    return result;
}

/* The result is the newest managed allocation. A small result need not
 * retain a dead GMP allocation until the next IO collection. */
static MlfValue *compact_integer(MlfValue *result) {
    if (mpz_fits_slong_p(result->as.integer)) {
        int64_t n = mpz_get_si(result->as.integer);
        if (n >= SMALL_MIN && n <= SMALL_MAX) {
            mpz_clear(result->as.integer);
            heap = result->object.next;
            --objects;
            result->object.next = (Object *)free_values;
            free_values = result;
            return small(n);
        }
    }
    integer_bytes += mpz_size(result->as.integer) * sizeof(mp_limb_t);
    return result;
}

static MlfValue *integer_operation(MlfValue *a, MlfValue *b, int subtract) {
    a = expect(a, INTEGER); b = expect(b, INTEGER);
    if (small_integer(a) && small_integer(b)) {
        int64_t n = subtract ? small_value(a) - small_value(b) : small_value(a) + small_value(b);
        if (n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
    }
    MlfValue *result = value(INTEGER);
    mpz_init(result->as.integer);
    if (!small_integer(a) && !small_integer(b)) {
        if (subtract) mpz_sub(result->as.integer,a->as.integer,b->as.integer);
        else mpz_add(result->as.integer,a->as.integer,b->as.integer);
    } else if (small_integer(a) && small_integer(b)) {
        mpz_set_si(result->as.integer,small_value(a));
        int64_t n = small_value(b);
        if (subtract) n = -n;
        if (n >= 0) mpz_add_ui(result->as.integer,result->as.integer,(unsigned long)n);
        else mpz_sub_ui(result->as.integer,result->as.integer,(unsigned long)-n);
    } else {
        MlfValue *big = small_integer(a) ? b : a;
        int64_t n = small_value(small_integer(a) ? a : b);
        if (subtract && !small_integer(a)) n = -n;
        if (subtract && small_integer(a)) {
            /* n - big = -(big - n), without copying either operand. */
            if (n >= 0) mpz_sub_ui(result->as.integer,big->as.integer,(unsigned long)n);
            else mpz_add_ui(result->as.integer,big->as.integer,(unsigned long)-n);
            mpz_neg(result->as.integer,result->as.integer);
        } else if (n >= 0) mpz_add_ui(result->as.integer,big->as.integer,(unsigned long)n);
        else mpz_sub_ui(result->as.integer,big->as.integer,(unsigned long)-n);
    }
    return compact_integer(result);
}

MlfValue *mlf_add_int(MlfValue *a, MlfValue *b) { return integer_operation(a, b, 0); }
MlfValue *mlf_sub_int(MlfValue *a, MlfValue *b) { return integer_operation(a, b, 1); }

static MlfValue *integer_extended(Primitive p, MlfValue *a, MlfValue *b) {
    a = expect(a, INTEGER); b = expect(b, INTEGER);
    if ((p == QUOT_INT || p == REM_INT) && (small_integer(b) ? small_value(b) == 0 : mpz_sgn(b->as.integer) == 0))
        fail("integer division by zero");
    if (small_integer(a) && small_integer(b)) {
        int64_t x = small_value(a), y = small_value(b), n;
        if (p == AND_INT) return small(x & y);
        if (p == MUL_INT) {
            if (!__builtin_mul_overflow(x,y,&n) && n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
        } else {
            /* The 63-bit operands cannot trigger INT64_MIN/-1 overflow. */
            n = p == QUOT_INT ? x / y : x % y;
            if (n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
        }
    }
    MlfValue *result = value(INTEGER);
    mpz_init(result->as.integer);
    if (p == MUL_INT && (small_integer(a) || small_integer(b))) {
        MlfValue *big = small_integer(a) ? b : a;
        long n = small_value(small_integer(a) ? a : b);
        if (small_integer(big)) {
            mpz_set_si(result->as.integer,small_value(big));
            mpz_mul_si(result->as.integer,result->as.integer,n);
        } else mpz_mul_si(result->as.integer,big->as.integer,n);
    } else {
        /* GMP accepts immutable operand pointers. Only immediate operands
         * need a temporary, avoiding two full bignum copies per operation. */
        mpz_t left, right;
        mpz_srcptr x, y;
        if (small_integer(a)) { mpz_init_set_si(left,small_value(a)); x = left; }
        else x = a->as.integer;
        if (small_integer(b)) { mpz_init_set_si(right,small_value(b)); y = right; }
        else y = b->as.integer;
        if (p == MUL_INT) mpz_mul(result->as.integer,x,y);
        else if (p == AND_INT) mpz_and(result->as.integer,x,y);
        else if (p == QUOT_INT) mpz_tdiv_q(result->as.integer,x,y);
        else mpz_tdiv_r(result->as.integer,x,y);
        if (small_integer(a)) mpz_clear(left);
        if (small_integer(b)) mpz_clear(right);
    }
    return compact_integer(result);
}

static MlfValue *read_integer(MlfValue *entry) {
    MlfValue *s = expect(entry, STRING);
    size_t n = s->as.string.length, i = 0;
    const char *bytes = s->as.string.bytes;
    if (n && (bytes[0] == '-' || bytes[0] == '+')) ++i;
    if (i == n) fail("invalid integer input");
    for (; i < n; ++i) if (bytes[i] < '0' || bytes[i] > '9') fail("invalid integer input");
    return mlf_integer(bytes + (bytes[0] == '+'));
}

static int integer_compare(MlfValue *a, MlfValue *b) {
    a = expect(a, INTEGER); b = expect(b, INTEGER);
    if (small_integer(a) && small_integer(b)) return (small_value(a) > small_value(b)) - (small_value(a) < small_value(b));
    if (small_integer(a)) {
        int order = mpz_cmp_si(b->as.integer, (long)small_value(a));
        return (order < 0) - (order > 0);
    }
    if (small_integer(b)) return mpz_cmp_si(a->as.integer, (long)small_value(b));
    return mpz_cmp(a->as.integer, b->as.integer);
}

MlfValue *mlf_eq_int(MlfValue *a, MlfValue *b) { return mlf_boolean(integer_compare(a,b) == 0); }
MlfValue *mlf_lt_int(MlfValue *a, MlfValue *b) { return mlf_boolean(integer_compare(a,b) < 0); }

int64_t mlf_truth(MlfValue *entry) {
    MlfValue *b = expect(entry, BOOLEAN);
    return boolean_value(b) ? ((uintptr_t)b == 6) : b->as.boolean;
}

static uint64_t bounded_integer(MlfValue *entry, uint64_t limit, const char *error) {
    entry = expect(entry, INTEGER);
    uint64_t n;
    if (small_integer(entry)) {
        int64_t signed_n = small_value(entry);
        if (signed_n < 0) fail(error);
        n = (uint64_t)signed_n;
    } else {
        if (!mpz_fits_ulong_p(entry->as.integer)) fail(error);
        n = mpz_get_ui(entry->as.integer);
    }
    if (n > limit) fail(error);
    return n;
}

static double unbox_double(MlfValue *entry) { return expect(entry, DOUBLE)->as.floating; }

uint8_t mlf_byte(MlfValue *entry) {
    return (uint8_t)bounded_integer(entry,255,"byte value must be between 0 and 255");
}

double mlf_int_to_double(MlfValue *entry) {
    entry = expect(entry, INTEGER);
    if (small_integer(entry)) return (double)small_value(entry);
    /* mpz_get_d truncates. Decimal conversion rounds to nearest like the
     * interpreter, including integers outside the finite binary64 range. */
    MlfValue *decimal = show_integer(entry);
    return strtod(decimal->as.string.bytes,NULL);
}

static MlfValue *format_double(MlfValue *places, MlfValue *entry) {
    /* Match the strict left-to-right arguments of saturated generated calls,
     * including when the primitive escapes and is applied by the runtime. */
    places = expect(places,INTEGER);
    double n = unbox_double(entry);
    int precision = (int)bounded_integer(places,17,"Double precision must be between 0 and 17");
    if (isnan(n)) return mlf_string("NaN",3);
    if (isinf(n)) return n < 0 ? mlf_string("-Infinity",9) : mlf_string("Infinity",8);
    /* binary64 needs at most 309 integer digits, a sign, dot and 17 decimals.
     * The runtime never changes the initial C locale or rounding mode. */
    char text[384];
    int length = snprintf(text,sizeof(text),"%.*f",precision,n);
    if (length < 0 || (size_t)length >= sizeof(text)) fail("Double formatting failed");
    return mlf_string(text,(uint64_t)length);
}

static MlfValue *array_write_action(Tag tag, MlfValue *a, MlfValue *i, MlfValue *x) {
    MlfValue *result = value(tag);
    result->as.array_write.array = a;
    result->as.array_write.index = i;
    result->as.array_write.entry = x;
    return result;
}

static MlfValue *primitive_result(Primitive p, MlfValue *a, MlfValue *b, MlfValue *c) {
    switch (p) {
    case IO_RETURN: case IO_BIND: case PUT_STR: case PUT_STR_LN: case GET_LINE: case PRINT_INT:
    case NEW_INT_ARRAY: case READ_INT_ARRAY: case LENGTH_INT_ARRAY:
    case NEW_DOUBLE_ARRAY: case READ_DOUBLE_ARRAY: case LENGTH_DOUBLE_ARRAY:
    case NEW_BYTE_ARRAY: case READ_BYTE_ARRAY: case LENGTH_BYTE_ARRAY: case BYTE_ARRAY_FROM_STRING:
    case GET_BYTE_LINE: case NEW_INT_TABLE: case READ_INT_TABLE:
        return action(p, a, b);
    case WRITE_INT_ARRAY: return array_write_action(WRITE_INT_ACTION,a,b,c);
    case WRITE_DOUBLE_ARRAY: return array_write_action(WRITE_DOUBLE_ACTION,a,b,c);
    case WRITE_BYTE_ARRAY: return array_write_action(WRITE_BYTE_ACTION,a,b,c);
    case PUT_BYTES: return array_write_action(PUT_BYTES_ACTION,a,b,c);
    case WRITE_INT_TABLE: return array_write_action(WRITE_TABLE_ACTION,a,b,c);
    case SHOW_INT: return show_integer(a);
    case CONCAT_STRING: {
        a = expect(a, STRING); b = expect(b, STRING);
        size_t left = a->as.string.length, right = b->as.string.length;
        if (right >= SIZE_MAX - left) fail("string too large");
        MlfValue *result = value(STRING);
        result->as.string.length = left + right;
        result->as.string.bytes = allocate(left + right + 1);
        memcpy(result->as.string.bytes, a->as.string.bytes, left);
        memcpy(result->as.string.bytes + left, b->as.string.bytes, right);
        return result;
    }
    case ADD_INT: return mlf_add_int(a,b);
    case SUB_INT: return mlf_sub_int(a,b);
    case MUL_INT: case QUOT_INT: case REM_INT: case AND_INT: return integer_extended(p,a,b);
    case READ_INT: return read_integer(a);
    case ADD_DOUBLE: case SUB_DOUBLE: case MUL_DOUBLE: case DIV_DOUBLE: case EQ_DOUBLE: case LT_DOUBLE: {
        double x = unbox_double(a);
        double y = unbox_double(b);
        switch (p) {
        case ADD_DOUBLE: return mlf_double(x + y);
        case SUB_DOUBLE: return mlf_double(x - y);
        case MUL_DOUBLE: return mlf_double(x * y);
        case DIV_DOUBLE: return mlf_double(x / y);
        case EQ_DOUBLE: return mlf_boolean(x == y);
        default: return mlf_boolean(x < y);
        }
    }
    case SQRT_DOUBLE: return mlf_double(sqrt(unbox_double(a)));
    case INT_TO_DOUBLE: return mlf_double(mlf_int_to_double(a));
    case FORMAT_DOUBLE: return format_double(a,b);
    case EQ_INT: return mlf_eq_int(a,b);
    case LT_INT: return mlf_lt_int(a,b);
    case EQ_STRING:
        a = expect(a, STRING); b = expect(b, STRING);
        return mlf_boolean(a->as.string.length == b->as.string.length &&
            !memcmp(a->as.string.bytes, b->as.string.bytes, a->as.string.length));
    case IF_THEN_ELSE:
        return mlf_truth(a) ? b : c;
    default: fail("unknown primitive");
    }
}

static MlfValue *primitive(Primitive p, MlfEnv *arguments) {
    static const size_t arities[PRIMITIVE_COUNT] = {
        1,2,1,1,0,1,2,1,2,2,2,2,2,3,2,2,2,1,
        2,2,2,2,1,2,2,1,2,2,2,3,1,2,2,3,1,2,2,3,1,1,3,0,0,2,3,2
    };
    if (arguments->count < arities[p]) {
        MlfValue *result = value(PRIMITIVE);
        result->as.primitive.identity = p;
        result->as.primitive.arguments = arguments;
        return result;
    }
    if (arguments->count != arities[p]) fail("primitive arity mismatch");
    return primitive_result(p, arguments->count > 0 ? arguments->slots[0] : NULL,
        arguments->count > 1 ? arguments->slots[1] : NULL,
        arguments->count > 2 ? arguments->slots[2] : NULL);
}

static MlfValue *apply(MlfValue *function, MlfValue *argument) {
    function = force(function);
    if (immediate(function)) fail("application of a non-function");
    switch (function->tag) {
    case CLOSURE: return function->as.closure.code(function->as.closure.env, argument);
    case PRIMITIVE:
        return primitive(function->as.primitive.identity, append(function->as.primitive.arguments, argument));
    case CONSTRUCTOR: {
        if (function->as.constructor.fields->count >= (uint64_t)function->as.constructor.arity)
            fail("constructor overapplication");
        if (function->as.constructor.arity == 1) return mlf_constructor1(function->as.constructor.identity, argument);
        if (function->as.constructor.arity == 2 && function->as.constructor.fields->count == 1)
            return mlf_constructor2(function->as.constructor.identity, function->as.constructor.fields->slots[0], argument);
        MlfValue *result = value(CONSTRUCTOR);
        result->as.constructor = function->as.constructor;
        result->as.constructor.fields = append(function->as.constructor.fields, argument);
        if ((uint64_t)result->as.constructor.arity == result->as.constructor.fields->count) CONSTRUCTED(result->as.constructor.identity);
        return result;
    }
    default: fail("application of a non-function");
    }
}

/* Follow tail applications/indirections iteratively and update every thunk
 * on the spine. BUSY catches recursive demand, including x = x cycles.
 */
static MlfValue *force(MlfValue *entry) {
    Stack updates = {0};
    for (;;) {
        if (!entry) fail("missing runtime value");
        if (immediate(entry)) break;
        Tag tag = entry->tag;
        if (tag == HOLE || tag == BUSY) fail("cyclic evaluation of a recursive binding");
        if (tag != THUNK && tag != APPLICATION && tag != INDIRECT) break;
        MlfValue *old = entry;
        push(&updates, old);
        old->tag = BUSY;
        if (tag == THUNK) entry = old->as.closure.code(old->as.closure.env, NULL);
        else if (tag == APPLICATION) entry = apply(old->as.application.function, old->as.application.argument);
        else entry = old->as.indirect;
    }
    for (size_t i = 0; i < updates.count; ++i) {
        MlfValue *old = updates.items[i];
        old->tag = INDIRECT;
        old->as.indirect = entry;
    }
    release_stack(&updates);
    return entry;
}

MlfValue *mlf_force(MlfValue *entry) {
    if (entry && (immediate(entry) || entry->tag >= CLOSURE)) return entry;
    return force(entry);
}

/* Saturated primitive calls from native workers. Arguments remain lazy for
 * IO actions; only the ordinary strict primitives demand their operands. */
MlfValue *mlf_prim1(int64_t p, MlfValue *a) {
    switch (p) {
    case IO_RETURN: case PUT_STR: case PUT_STR_LN: case PRINT_INT: case SHOW_INT: case READ_INT:
    case SQRT_DOUBLE: case INT_TO_DOUBLE: case LENGTH_INT_ARRAY: case LENGTH_DOUBLE_ARRAY:
    case LENGTH_BYTE_ARRAY: case BYTE_ARRAY_FROM_STRING:
        return primitive_result((Primitive)p,a,NULL,NULL);
    default: fail("unary primitive arity mismatch");
    }
}
MlfValue *mlf_prim2(int64_t p, MlfValue *a, MlfValue *b) {
    switch (p) {
    case IO_BIND: case CONCAT_STRING: case ADD_INT: case SUB_INT: case EQ_INT: case LT_INT: case EQ_STRING:
    case MUL_INT: case QUOT_INT: case REM_INT: case AND_INT:
    case ADD_DOUBLE: case SUB_DOUBLE: case MUL_DOUBLE: case DIV_DOUBLE: case EQ_DOUBLE: case LT_DOUBLE:
    case FORMAT_DOUBLE: case NEW_INT_ARRAY: case READ_INT_ARRAY: case NEW_DOUBLE_ARRAY: case READ_DOUBLE_ARRAY:
    case NEW_BYTE_ARRAY: case READ_BYTE_ARRAY: case READ_INT_TABLE:
        return primitive_result((Primitive)p,a,b,NULL);
    default: fail("binary primitive arity mismatch");
    }
}

MlfValue *mlf_prim3(int64_t p, MlfValue *a, MlfValue *b, MlfValue *c) {
    switch (p) {
    case IF_THEN_ELSE: case WRITE_INT_ARRAY: case WRITE_DOUBLE_ARRAY: case WRITE_BYTE_ARRAY: case PUT_BYTES: case WRITE_INT_TABLE:
        return primitive_result((Primitive)p,a,b,c);
    default: fail("ternary primitive arity mismatch");
    }
}

static void release(Object *entry) {
    if (entry->kind == OBJECT_VALUE) {
        MlfValue *v = (MlfValue *)entry;
        if (v->tag == INTEGER) {
            integer_bytes -= mpz_size(v->as.integer) * sizeof(mp_limb_t);
            mpz_clear(v->as.integer);
        }
        if (v->tag == STRING) free(v->as.string.bytes);
        if (v->tag == INT_ARRAY) free(v->as.int_array.cells);
        if (v->tag == DOUBLE_ARRAY) free(v->as.double_array.cells);
        if (v->tag == BYTE_ARRAY) free(v->as.byte_array.cells);
        if (v->tag == INT_TABLE) kh_destroy(mlf_int,v->as.int_table);
        if (v->tag == SMALL_INT_TABLE) kh_destroy(mlf_tagged,v->as.small_table);
        v->object.next = (Object *)free_values;
        free_values = v;
        return;
    }
    free(entry);
}

static void cleanup(void) {
    while (active_stacks) {
        Stack *next = active_stacks->next;
        free(active_stacks->items);
        active_stacks = next;
    }
    while (heap) {
        Object *next = heap->next;
        release(heap);
        heap = next;
    }
    while (value_pages) {
        ValuePage *next = value_pages->next;
        free(value_pages);
        value_pages = next;
    }
    free_values = NULL;
    native_roots = NULL;
    io_current = NULL;
    io_continuations = NULL;
    objects = 0;
    collection_limit = MLF_GC_THRESHOLD;
    integer_bytes = 0;
    integer_collection_limit = MLF_GC_INTEGER_BYTES;
}

/* The collector visits many distinct field layouts. Sharing this helper
 * avoids duplicating its growable-stack path at every field of every tag. */
static __attribute__((noinline)) void mark(Stack *pending, void *entry) {
    if (immediate(entry)) return;
    Object *o = entry;
    if (o && !o->marked) { o->marked = 1; push(pending, o); }
}

static void collect(MlfValue *root, const Stack *continuations) {
    Stack pending = {0};
    mark(&pending, root);
    for (size_t i = 0; i < continuations->count; ++i) mark(&pending, continuations->items[i]);
    for (const MlfRoots *frame = native_roots; frame; frame = frame->previous)
        for (uint64_t i = 0; i < frame->count; ++i) mark(&pending,frame->values[i]);
    while (pending.count) {
        Object *o = pending.items[--pending.count];
        if (o->kind == OBJECT_ENV) {
            MlfEnv *env = (MlfEnv *)o;
            for (size_t i = 0; i < env->count; ++i) mark(&pending, env->slots[i]);
            continue;
        }
        MlfValue *v = (MlfValue *)o;
        switch (v->tag) {
        case INDIRECT: mark(&pending, v->as.indirect); break;
        case THUNK: case CLOSURE: case NATIVE_IO: mark(&pending, v->as.closure.env); break;
        case APPLICATION:
            mark(&pending, v->as.application.function); mark(&pending, v->as.application.argument); break;
        case CONSTRUCTOR: mark(&pending, v->as.constructor.fields); break;
        case CONSTRUCTOR_1: mark(&pending, v->as.packed.fields[0]); break;
        case CONSTRUCTOR_2:
            mark(&pending, v->as.packed.fields[0]); mark(&pending, v->as.packed.fields[1]); break;
        case PRIMITIVE: mark(&pending, v->as.primitive.arguments); break;
        case ACTION: mark(&pending, v->as.action.first); mark(&pending, v->as.action.second); break;
        case INT_ARRAY:
            for (size_t i = 0; i < v->as.int_array.length; ++i) mark(&pending, v->as.int_array.cells[i]);
            break;
        case INT_TABLE:
            for (khiter_t i = kh_begin(v->as.int_table); i != kh_end(v->as.int_table); ++i)
                if (kh_exist(v->as.int_table,i)) {
                    mark(&pending,kh_key(v->as.int_table,i)); mark(&pending,kh_val(v->as.int_table,i));
                }
            break;
        case SMALL_INT_TABLE:
            for (khiter_t i = kh_begin(v->as.small_table); i != kh_end(v->as.small_table); ++i)
                if (kh_exist(v->as.small_table,i)) mark(&pending,kh_val(v->as.small_table,i));
            break;
        case WRITE_INT_ACTION: case WRITE_DOUBLE_ACTION: case WRITE_BYTE_ACTION: case PUT_BYTES_ACTION: case WRITE_TABLE_ACTION:
            mark(&pending, v->as.array_write.array); mark(&pending, v->as.array_write.index);
            mark(&pending, v->as.array_write.entry); break;
        case BUSY: case HOLE: fail("unfinished evaluation at garbage collection");
        default: break;
        }
    }
    release_stack(&pending);
    Object **cursor = &heap;
    while (*cursor) {
        Object *o = *cursor;
        if (o->marked) { o->marked = 0; cursor = &o->next; }
        else { *cursor = o->next; release(o); --objects; }
    }
    collection_limit = objects > (SIZE_MAX - MLF_GC_THRESHOLD) / 2 ? SIZE_MAX :
        objects * 2 + MLF_GC_THRESHOLD;
    integer_collection_limit = integer_bytes > (SIZE_MAX - MLF_GC_INTEGER_BYTES) / 2 ? SIZE_MAX :
        integer_bytes * 2 + MLF_GC_INTEGER_BYTES;
}

void mlf_roots_enter(MlfRoots *frame, uint64_t count, MlfValue **values) {
    *frame = (MlfRoots){native_roots,count,values};
    native_roots = frame;
}

void mlf_roots_leave(MlfRoots *frame) { native_roots = frame->previous; }

void mlf_gc_check(uint64_t count, MlfValue **values) {
    if (objects < collection_limit && integer_bytes < integer_collection_limit) return;
    MlfRoots frame;
    mlf_roots_enter(&frame,count,values);
    collect(*io_current,io_continuations);
    mlf_roots_leave(&frame);
}

static void write_string(MlfValue *entry, int newline) {
    MlfValue *text = expect(entry, STRING);
    size_t size = text->as.string.length;
    if (fwrite(text->as.string.bytes, 1, size, stdout) != size ||
        (newline && fputc('\n', stdout) == EOF) || fflush(stdout) == EOF)
        fail("IO error: output failed");
}

static int valid_utf8(const unsigned char *bytes, size_t length) {
    for (size_t i = 0; i < length;) {
        unsigned c = bytes[i++], remaining = 0, minimum = 0;
        if (c < 0x80) continue;
        if (c >= 0xc2 && c <= 0xdf) { c &= 0x1f; remaining = 1; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { c &= 0x0f; remaining = 2; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { c &= 7; remaining = 3; minimum = 0x10000; }
        else return 0;
        if (remaining > length - i) return 0;
        while (remaining--) {
            unsigned next = bytes[i++];
            if ((next & 0xc0) != 0x80) return 0;
            c = (c << 6) | (next & 0x3f);
        }
        if (c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) return 0;
    }
    return 1;
}

static MlfValue *read_line(void) {
    char *buffer = NULL;
    size_t capacity = 0;
    ssize_t length = getline(&buffer, &capacity, stdin);
    if (length < 0) { free(buffer); fail("IO error: getLine reached EOF or failed"); }
    if (length && buffer[length - 1] == '\n') --length;
    if (!valid_utf8((unsigned char *)buffer, (size_t)length)) {
        free(buffer); fail("IO error: invalid UTF-8 input");
    }
    MlfValue *result = mlf_string(buffer, (uint64_t)length);
    free(buffer);
    return result;
}

MlfValue *mlf_get_byte_line(void) {
    char *buffer = NULL;
    size_t capacity = 0;
    ssize_t length = getline(&buffer,&capacity,stdin);
    if (length < 0 && !feof(stdin)) { free(buffer); fail("IO error: byte input failed"); }
    MlfValue *result = value(BYTE_ARRAY);
    result->as.byte_array.length = length < 0 ? 0 : (size_t)length;
    result->as.byte_array.cells = (unsigned char *)buffer;
    if (!buffer) result->as.byte_array.cells = allocate(1);
    return result;
}

static MlfValue *table_key(MlfValue *key) {
    if (!small_integer(key) && mpz_cmp_si(key->as.integer,SMALL_MIN) >= 0 &&
        mpz_cmp_si(key->as.integer,SMALL_MAX) <= 0) return small(mpz_get_si(key->as.integer));
    return key;
}

static void promote_table(MlfValue *table) {
    khash_t(mlf_tagged) *old = table->as.small_table;
    khash_t(mlf_int) *next = kh_init(mlf_int);
    if (!next) fail("out of memory");
    if (kh_resize(mlf_int,next,old->n_buckets) < 0) { kh_destroy(mlf_int,next); fail("out of memory"); }
    for (khiter_t i = kh_begin(old); i != kh_end(old); ++i) if (kh_exist(old,i)) {
        int inserted;
        khiter_t j = kh_put(mlf_int,next,kh_key(old,i),&inserted);
        if (inserted < 0) { kh_destroy(mlf_int,next); fail("out of memory"); }
        kh_val(next,j) = kh_val(old,i);
    }
    kh_destroy(mlf_tagged,old);
    table->as.int_table = next;
    table->tag = INT_TABLE;
}

MlfValue *mlf_read_int_table(MlfValue *table, MlfValue *key) {
    table = expect(table,INT_TABLE);
    key = table_key(expect(key,INTEGER));
    if (table->tag == SMALL_INT_TABLE) {
        if (!small_integer(key)) return small(0);
        khash_t(mlf_tagged) *t = table->as.small_table;
        khiter_t i = kh_get(mlf_tagged,t,key);
        return i == kh_end(t) ? small(0) : kh_val(t,i);
    }
    khash_t(mlf_int) *t = table->as.int_table;
    khiter_t i = kh_get(mlf_int,t,key);
    return i == kh_end(t) ? small(0) : kh_val(t,i);
}

MlfValue *mlf_write_int_table(MlfValue *table, MlfValue *key, MlfValue *entry) {
    table = expect(table,INT_TABLE);
    key = table_key(expect(key,INTEGER));
    entry = expect(entry,INTEGER);
    if (table->tag == SMALL_INT_TABLE) {
        if (small_integer(key)) {
            khash_t(mlf_tagged) *t = table->as.small_table;
            if (t->n_occupied >= t->upper_bound && t->n_buckets >= (1u << 31)) fail("integer table too large");
            int inserted;
            khiter_t i = kh_put(mlf_tagged,t,key,&inserted);
            if (inserted < 0) fail("out of memory");
            kh_val(t,i) = entry;
            TABLE_WRITTEN(table,inserted);
            return mlf_constructor(0,0);
        }
        promote_table(table);
    }
    khash_t(mlf_int) *t = table->as.int_table;
    if (t->n_occupied >= t->upper_bound && t->n_buckets >= (1u << 31)) fail("integer table too large");
    int inserted;
    khiter_t i = kh_put(mlf_int,t,key,&inserted);
    if (inserted < 0) fail("out of memory");
    kh_val(t,i) = entry;
    TABLE_WRITTEN(table,inserted);
    return mlf_constructor(0,0);
}

static inline MlfValue *add_evaluated_integers(MlfValue *a, MlfValue *b) {
    intptr_t bits;
    if (small_integer(a) && small_integer(b) &&
        !__builtin_add_overflow((intptr_t)a,(intptr_t)b-1,&bits)) return (MlfValue *)bits;
    return mlf_add_int(a,b);
}

/* Fused read/add/write from a checked native region. Its operands are
 * already evaluated, like the compiler's direct array loads. Return the
 * immutable previous value so later uses retain snapshot semantics. */
MlfValue *mlf_add_int_table(MlfValue *table, MlfValue *key, MlfValue *delta) {
    key = table_key(key);
    if (table->tag == SMALL_INT_TABLE) {
        if (small_integer(key)) {
            khash_t(mlf_tagged) *t = table->as.small_table;
            /* Repeated updates need neither the insertion bookkeeping nor
             * a resize. Keep the library's full insertion path for misses. */
            int inserted = 0;
            khiter_t i = kh_get(mlf_tagged,t,key);
            if (i == kh_end(t)) {
                if (t->n_occupied >= t->upper_bound && t->n_buckets >= (1u << 31)) fail("integer table too large");
                i = kh_put(mlf_tagged,t,key,&inserted);
                if (inserted < 0) fail("out of memory");
            }
            MlfValue *old = inserted ? small(0) : kh_val(t,i);
            kh_val(t,i) = add_evaluated_integers(old,delta);
            TABLE_WRITTEN(table,inserted);
            return old;
        }
        promote_table(table);
    }
    khash_t(mlf_int) *t = table->as.int_table;
    if (t->n_occupied >= t->upper_bound && t->n_buckets >= (1u << 31)) fail("integer table too large");
    int inserted;
    khiter_t i = kh_put(mlf_int,t,key,&inserted);
    if (inserted < 0) fail("out of memory");
    MlfValue *old = inserted ? small(0) : kh_val(t,i);
    kh_val(t,i) = add_evaluated_integers(old,delta);
    TABLE_WRITTEN(table,inserted);
    return old;
}

static size_t array_index(MlfValue *index, size_t length) {
    index = expect(index,INTEGER);
    if (!length) fail("array index out of bounds");
    return (size_t)bounded_integer(index,length-1,"array index out of bounds");
}

MlfValue *mlf_new_array(int64_t p, MlfValue *size, MlfValue *initial) {
    size_t n = (size_t)bounded_integer(size,INT64_MAX / 8,"invalid array length");
    if (p == NEW_BYTE_ARRAY) {
        uint8_t x = mlf_byte(initial);
        MlfValue *result = value(BYTE_ARRAY);
        result->as.byte_array.length = n;
        result->as.byte_array.cells = NULL;
        result->as.byte_array.cells = allocate(n ? n : 1);
        memset(result->as.byte_array.cells,x,n);
        return result;
    }
    if (p == NEW_INT_ARRAY) {
        initial = expect(initial,INTEGER);
        MlfValue *result = value(INT_ARRAY);
        result->as.int_array.length = n;
        result->as.int_array.cells = NULL;
        result->as.int_array.cells = allocate(n ? n * sizeof(MlfValue *) : 1);
        for (size_t i = 0; i < n; ++i) result->as.int_array.cells[i] = initial;
        return result;
    }
    double x = unbox_double(initial);
    MlfValue *result = value(DOUBLE_ARRAY);
    result->as.double_array.length = n;
    result->as.double_array.cells = NULL;
    result->as.double_array.cells = allocate(n ? n * sizeof(double) : 1);
    for (size_t i = 0; i < n; ++i) result->as.double_array.cells[i] = x;
    return result;
}

static MlfValue *write_array(MlfValue *operation) {
    MlfValue *a = operation->as.array_write.array;
    MlfValue *i = operation->as.array_write.index;
    MlfValue *x = operation->as.array_write.entry;
    if (operation->tag == WRITE_INT_ACTION) {
        a = expect(a,INT_ARRAY);
        size_t index = array_index(i,a->as.int_array.length);
        a->as.int_array.cells[index] = expect(x,INTEGER);
    } else if (operation->tag == WRITE_BYTE_ACTION) {
        a = expect(a,BYTE_ARRAY);
        size_t index = array_index(i,a->as.byte_array.length);
        a->as.byte_array.cells[index] = mlf_byte(x);
    } else {
        a = expect(a,DOUBLE_ARRAY);
        size_t index = array_index(i,a->as.double_array.length);
        a->as.double_array.cells[index] = unbox_double(x);
    }
    return mlf_constructor(0,0);
}

MlfValue *mlf_bytes_from_string(MlfValue *text) {
    text = expect(text,STRING);
    size_t length = text->as.string.length;
    if (length > INT64_MAX / 8) fail("invalid array length");
    MlfValue *result = value(BYTE_ARRAY);
    result->as.byte_array.length = length;
    result->as.byte_array.cells = NULL;
    result->as.byte_array.cells = allocate(length ? length : 1);
    memcpy(result->as.byte_array.cells,text->as.string.bytes,length);
    return result;
}

MlfValue *mlf_put_bytes(MlfValue *array, MlfValue *start, MlfValue *size) {
    MlfValue *a = expect(array,BYTE_ARRAY);
    size_t length = a->as.byte_array.length;
    size_t offset = (size_t)bounded_integer(start,length,"byte slice out of bounds");
    size_t count = (size_t)bounded_integer(size,length-offset,"byte slice out of bounds");
    if (fwrite(a->as.byte_array.cells+offset,1,count,stdout) != count || fflush(stdout) == EOF)
        fail("IO error: output failed");
    return mlf_constructor(0,0);
}

MlfValue *mlf_new_int_table(void) {
    MlfValue *result = value(SMALL_INT_TABLE);
    result->as.small_table = kh_init(mlf_tagged);
    if (!result->as.small_table) fail("out of memory");
    TABLE_CREATED(result);
    return result;
}

int32_t mlf_run(MlfValue *root, int64_t is_io) {
    if (!is_io) { (void)force(root); cleanup(); return 0; }
    Stack continuations = {0};
    MlfValue *current = root;
    io_current = &current;
    io_continuations = &continuations;
    for (;;) {
        if (objects >= collection_limit || integer_bytes >= integer_collection_limit)
            collect(current, &continuations);
        MlfValue *operation = force(current);
        MlfValue *result;
        if (!immediate(operation) && operation->tag == NATIVE_IO) {
            current = operation->as.closure.code(operation->as.closure.env,NULL);
            continue;
        }
        if (!immediate(operation) && operation->tag == PUT_BYTES_ACTION) {
            result = mlf_put_bytes(operation->as.array_write.array,operation->as.array_write.index,
                                   operation->as.array_write.entry);
        } else if (!immediate(operation) && operation->tag == WRITE_TABLE_ACTION) {
            result = mlf_write_int_table(operation->as.array_write.array,operation->as.array_write.index,
                                         operation->as.array_write.entry);
        } else if (!immediate(operation) && (operation->tag == WRITE_INT_ACTION ||
                   operation->tag == WRITE_DOUBLE_ACTION || operation->tag == WRITE_BYTE_ACTION)) {
            result = write_array(operation);
        } else {
        operation = expect(operation,ACTION);
        switch (operation->as.action.operation) {
        case IO_BIND:
            push(&continuations, operation->as.action.second);
            current = operation->as.action.first;
            continue;
        case IO_RETURN: result = operation->as.action.first; break;
        case GET_LINE: result = read_line(); break;
        case GET_BYTE_LINE: result = mlf_get_byte_line(); break;
        case NEW_INT_TABLE: result = mlf_new_int_table(); break;
        case READ_INT_TABLE:
            result = mlf_read_int_table(operation->as.action.first,operation->as.action.second); break;
        case PUT_STR: case PUT_STR_LN:
            write_string(operation->as.action.first, operation->as.action.operation == PUT_STR_LN);
            result = mlf_constructor(0, 0); break;
        case PRINT_INT:
            write_string(show_integer(operation->as.action.first), 1);
            result = mlf_constructor(0, 0); break;
        case NEW_INT_ARRAY: case NEW_DOUBLE_ARRAY: case NEW_BYTE_ARRAY:
            result = mlf_new_array(operation->as.action.operation,operation->as.action.first,operation->as.action.second);
            break;
        case READ_INT_ARRAY: {
            MlfValue *a = expect(operation->as.action.first,INT_ARRAY);
            size_t i = array_index(operation->as.action.second,a->as.int_array.length);
            result = a->as.int_array.cells[i]; break;
        }
        case READ_DOUBLE_ARRAY: {
            MlfValue *a = expect(operation->as.action.first,DOUBLE_ARRAY);
            size_t i = array_index(operation->as.action.second,a->as.double_array.length);
            result = mlf_double(a->as.double_array.cells[i]); break;
        }
        case READ_BYTE_ARRAY: {
            MlfValue *a = expect(operation->as.action.first,BYTE_ARRAY);
            size_t i = array_index(operation->as.action.second,a->as.byte_array.length);
            result = small(a->as.byte_array.cells[i]); break;
        }
        case BYTE_ARRAY_FROM_STRING:
            result = mlf_bytes_from_string(operation->as.action.first); break;
        case LENGTH_BYTE_ARRAY:
            result = small((int64_t)expect(operation->as.action.first,BYTE_ARRAY)->as.byte_array.length); break;
        case LENGTH_INT_ARRAY:
            result = small((int64_t)expect(operation->as.action.first,INT_ARRAY)->as.int_array.length); break;
        case LENGTH_DOUBLE_ARRAY:
            result = small((int64_t)expect(operation->as.action.first,DOUBLE_ARRAY)->as.double_array.length); break;
        default: fail("invalid IO action");
        }
        }
        if (!continuations.count) break;
        MlfValue *next = continuations.items[--continuations.count];
        current = mlf_application(next, result);
    }
    release_stack(&continuations);
    cleanup();
    return 0;
}
