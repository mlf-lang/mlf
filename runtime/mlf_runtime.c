/* Runtime support for native xMLF functions, not an AST interpreter.
 * Call-by-need memoizes values; executing an IO action is never memoized.
 * Only the IO driver collects: at those safe points no generated function,
 * force operation, or primitive has live roots on the native stack.
 */
#define _POSIX_C_SOURCE 200809L
#include "mlf_runtime.h"
#include <gmp.h>
#include <errno.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MLF_GC_THRESHOLD
#define MLF_GC_THRESHOLD 4096
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
    CONSTRUCTOR_1, CONSTRUCTOR_2
} Tag;

/* These numbers are shared with primitiveCode in MLF.LLVM. */
typedef enum {
    IO_RETURN, IO_BIND, PUT_STR, PUT_STR_LN, GET_LINE, PRINT_INT,
    CONCAT_STRING, SHOW_INT, ADD_INT, SUB_INT, EQ_INT, LT_INT,
    EQ_STRING, IF_THEN_ELSE, PRIMITIVE_COUNT
} Primitive;

struct MlfEnv {
    Object object;
    size_t count;
    MlfValue *slots[];
};

struct MlfValue {
    Object object;
    Tag tag;
    union {
        MlfValue *indirect;
        struct { MlfCode code; MlfEnv *env; } closure;
        struct { MlfValue *function, *argument; } application;
        mpz_t integer;
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
static size_t objects;
static size_t collection_limit = MLF_GC_THRESHOLD;
static void cleanup(void);

/* The low bits distinguish immediate integers, booleans and nullary data
 * from aligned heap pointers. Integers outside the signed 63-bit range keep
 * their arbitrary-precision GMP representation. */
_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "native runtime requires a 64-bit ABI");
_Static_assert(_Alignof(MlfValue) >= 8, "native tagged pointer alignment");
_Static_assert(offsetof(MlfValue, as.packed.identity) == 24, "constructor identity ABI");
_Static_assert(offsetof(MlfValue, as.packed.fields) == 32, "constructor field ABI");
#define SMALL_MIN (-(INT64_C(1) << 62))
#define SMALL_MAX ((INT64_C(1) << 62) - 1)
static int immediate(const void *p) { return ((uintptr_t)p & 7) != 0; }
static int small_integer(const MlfValue *p) { return ((uintptr_t)p & 1) != 0; }
static int64_t small_value(const MlfValue *p) { return (int64_t)(intptr_t)p >> 1; }
static MlfValue *small(int64_t n) { return (MlfValue *)(uintptr_t)(((uint64_t)n << 1) | 1); }
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
    return result;
}

MlfValue *mlf_boolean(int64_t boolean) {
    return (MlfValue *)(uintptr_t)(boolean ? 6 : 2);
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
    if (identity == GET_LINE) return action(GET_LINE, NULL, NULL);
    MlfValue *result = value(PRIMITIVE);
    result->as.primitive.identity = (Primitive)identity;
    result->as.primitive.arguments = mlf_env_new(0);
    return result;
}

static MlfValue *force(MlfValue *entry);
static MlfValue *expect(MlfValue *entry, Tag tag) {
    MlfValue *result = force(entry);
    if (immediate(result)) {
        if ((tag == INTEGER && small_integer(result)) ||
            (tag == BOOLEAN && boolean_value(result)) ||
            (tag == CONSTRUCTOR && nullary(result))) return result;
        fail("invalid value for runtime operation");
    }
    if (tag == CONSTRUCTOR && (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2)) return result;
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

static void integer_copy(mpz_t destination, MlfValue *source) {
    if (small_integer(source)) mpz_set_si(destination, (long)small_value(source));
    else mpz_set(destination, source->as.integer);
}

static MlfValue *integer_operation(MlfValue *a, MlfValue *b, int subtract) {
    a = expect(a, INTEGER); b = expect(b, INTEGER);
    if (small_integer(a) && small_integer(b)) {
        int64_t n = subtract ? small_value(a) - small_value(b) : small_value(a) + small_value(b);
        if (n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
    }
    MlfValue *result = value(INTEGER);
    mpz_t other;
    mpz_init(result->as.integer); mpz_init(other);
    integer_copy(result->as.integer, a); integer_copy(other, b);
    if (subtract) mpz_sub(result->as.integer, result->as.integer, other);
    else mpz_add(result->as.integer, result->as.integer, other);
    mpz_clear(other);
    if (mpz_fits_slong_p(result->as.integer)) {
        int64_t n = mpz_get_si(result->as.integer);
        if (n >= SMALL_MIN && n <= SMALL_MAX) return small(n);
    }
    return result;
}

MlfValue *mlf_add_int(MlfValue *a, MlfValue *b) { return integer_operation(a, b, 0); }
MlfValue *mlf_sub_int(MlfValue *a, MlfValue *b) { return integer_operation(a, b, 1); }

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

static MlfValue *primitive_result(Primitive p, MlfValue *a, MlfValue *b, MlfValue *c) {
    switch (p) {
    case IO_RETURN: case IO_BIND: case PUT_STR: case PUT_STR_LN: case GET_LINE: case PRINT_INT:
        return action(p, a, b);
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
    static const size_t arities[PRIMITIVE_COUNT] = {1,2,1,1,0,1,2,1,2,2,2,2,2,3};
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
    case IO_RETURN: case PUT_STR: case PUT_STR_LN: case PRINT_INT: case SHOW_INT:
        return primitive_result((Primitive)p,a,NULL,NULL);
    default: fail("unary primitive arity mismatch");
    }
}
MlfValue *mlf_prim2(int64_t p, MlfValue *a, MlfValue *b) {
    switch (p) {
    case IO_BIND: case CONCAT_STRING: case ADD_INT: case SUB_INT: case EQ_INT: case LT_INT: case EQ_STRING:
        return primitive_result((Primitive)p,a,b,NULL);
    default: fail("binary primitive arity mismatch");
    }
}

static void release(Object *entry) {
    if (entry->kind == OBJECT_VALUE) {
        MlfValue *v = (MlfValue *)entry;
        if (v->tag == INTEGER) mpz_clear(v->as.integer);
        if (v->tag == STRING) free(v->as.string.bytes);
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
    objects = 0;
    collection_limit = MLF_GC_THRESHOLD;
}

static void mark(Stack *pending, void *entry) {
    if (immediate(entry)) return;
    Object *o = entry;
    if (o && !o->marked) { o->marked = 1; push(pending, o); }
}

static void collect(MlfValue *root, const Stack *continuations) {
    Stack pending = {0};
    mark(&pending, root);
    for (size_t i = 0; i < continuations->count; ++i) mark(&pending, continuations->items[i]);
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
        case THUNK: case CLOSURE: mark(&pending, v->as.closure.env); break;
        case APPLICATION:
            mark(&pending, v->as.application.function); mark(&pending, v->as.application.argument); break;
        case CONSTRUCTOR: mark(&pending, v->as.constructor.fields); break;
        case CONSTRUCTOR_1: mark(&pending, v->as.packed.fields[0]); break;
        case CONSTRUCTOR_2:
            mark(&pending, v->as.packed.fields[0]); mark(&pending, v->as.packed.fields[1]); break;
        case PRIMITIVE: mark(&pending, v->as.primitive.arguments); break;
        case ACTION: mark(&pending, v->as.action.first); mark(&pending, v->as.action.second); break;
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

int32_t mlf_run(MlfValue *root, int64_t is_io) {
    if (!is_io) { (void)force(root); cleanup(); return 0; }
    Stack continuations = {0};
    MlfValue *current = root;
    for (;;) {
        if (objects >= collection_limit) collect(current, &continuations);
        MlfValue *operation = expect(current, ACTION);
        MlfValue *result;
        switch (operation->as.action.operation) {
        case IO_BIND:
            push(&continuations, operation->as.action.second);
            current = operation->as.action.first;
            continue;
        case IO_RETURN: result = operation->as.action.first; break;
        case GET_LINE: result = read_line(); break;
        case PUT_STR: case PUT_STR_LN:
            write_string(operation->as.action.first, operation->as.action.operation == PUT_STR_LN);
            result = mlf_constructor(0, 0); break;
        case PRINT_INT:
            write_string(show_integer(operation->as.action.first), 1);
            result = mlf_constructor(0, 0); break;
        default: fail("invalid IO action");
        }
        if (!continuations.count) break;
        MlfValue *next = continuations.items[--continuations.count];
        current = mlf_application(next, result);
    }
    release_stack(&continuations);
    cleanup();
    return 0;
}
