/* Runtime support for native xMLF functions, not an AST interpreter.
 * Call-by-need memoizes values; executing an IO action is never memoized.
 * The IO driver and explicitly rooted native IO entries collect. Ordinary
 * lazy evaluation and scalar primitives never collect on the native stack.
 */
#define _DEFAULT_SOURCE 1
#define _DARWIN_C_SOURCE 1
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#include "mlf_runtime.h"
#include <gmp.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "mlf_integer64.h"
#define MLF_PROCESS_SUPERVISOR_IMPLEMENTATION
#include "mlf_process_supervisor.h"
#if defined(_WIN32)
#include "mlf_windows.h"
#endif
#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif

/* Compact BDWGC is the only native ABI. Every pointer-bearing allocation
 * uses the collector; GMP limbs use atomic allocations. */
#include <gc/gc.h>
#include "mlf_completion.h"
static void gc_register_layout(void);
static void *gc_integer_malloc(size_t size) {
    void *memory = GC_MALLOC_ATOMIC(size ? size : 1);
    if (!memory) abort();
    return memory;
}
static void *gc_integer_realloc(void *memory, size_t old_size, size_t size) {
    (void)old_size;
    void *result = GC_REALLOC(memory,size ? size : 1);
    if (!result) abort();
    return result;
}
static void gc_integer_free(void *memory, size_t size) { (void)size; GC_FREE(memory); }
static void gc_start(void) {
    static int initialized;
    if (initialized) return;
    initialized = 1;
    gc_register_layout();
    GC_INIT();
#if !defined(GC_FREE_SPACE_DIVISOR)
    if (!getenv("GC_FREE_SPACE_DIVISOR")) GC_set_free_space_divisor(1);
#endif
#if !defined(GC_INITIAL_HEAP_SIZE)
    if (!getenv("GC_INITIAL_HEAP_SIZE")) {
        const size_t preferred = 512 * 1024 * 1024;
        size_t current = GC_get_heap_size();
        /* GC_INIT has already read any maximum-heap setting. Expansion is
         * only a preference: GC_expand_hp also honors a cap set through the
         * collector API, and may reject the request without failing startup. */
        if (current < preferred) (void)GC_expand_hp(preferred - current);
    }
#endif
    mp_set_memory_functions(gc_integer_malloc,gc_integer_realloc,gc_integer_free);
}
/* Generated compact thunks share the runtime's traced small-object batches.
 * A nonempty head proves initialization; debug heads stay empty. */
void *mlf_compact_pending[17];
#define gc_pending mlf_compact_pending
#if defined(GC_DEBUG) || defined(GC_DEBUG_REPLACEMENT)
/* The batch API has no debugging allocator counterpart. */
static void *gc_malloc(size_t size) { gc_start(); return GC_MALLOC(size ? size : 1); }
#else
/* The runtime is single-threaded. Cache one traced batch per small size
 * class; the pinned collector returns at most one block plus one object.
 * Class upper bounds leave room for its one-past-the-end padding in the
 * same allocation bucket. Batches are cleared except for first-word links.
 * Static heads retain only unused objects (less than 75 KiB with BDWGC
 * 8.2.12). A populated class proves gc_start has already completed. */
static void *gc_malloc(size_t size) {
    if (size > 256) { gc_start(); return GC_MALLOC(size); }
    size_t index = size / 16;
    void *result = gc_pending[index];
    if (!result) {
        gc_start();
        result = GC_malloc_many((index + 1) * 16 - 1);
        if (!result) return GC_MALLOC(size ? size : 1);
    }
    void *next = GC_NEXT(result);
    gc_pending[index] = next;
    GC_NEXT(result) = NULL;
    GC_reachable_here(next);
    return result;
}
#endif
static void *gc_calloc(size_t count, size_t size) {
    if (size && count > SIZE_MAX / size) return NULL;
    return gc_malloc(count * size);
}
static void *gc_realloc(void *memory, size_t size) {
    gc_start();
    return !memory || GC_base(memory) ? GC_REALLOC(memory,size ? size : 1) : realloc(memory,size);
}
static void gc_free(void *memory) {
    if (!memory) return;
    if (GC_base(memory)) GC_FREE(memory); else free(memory);
}
#define malloc(size) gc_malloc(size)
#define calloc(count,size) gc_calloc(count,size)
#define realloc(memory,size) gc_realloc(memory,size)
#define free(memory) gc_free(memory)
#include "khash.h"

/* Generated modules reference exactly one ABI symbol. Linking against a
 * runtime with incompatible field offsets must fail before execution. */
/* Canonical source constructor tags and Char/typed-IOError primitives 95..102 and managed stack/context 103..106. */
void mlf_require_haskell_boundary_v3_abi(void) {}

typedef enum {
    HOLE, BUSY, INDIRECT, THUNK, APPLICATION, CLOSURE,
    INTEGER, MLF_BOOLEAN, STRING, CONSTRUCTOR, PRIMITIVE, ACTION,
    CONSTRUCTOR_1, CONSTRUCTOR_2, DOUBLE, INT_ARRAY, DOUBLE_ARRAY,
    WRITE_INT_ACTION, WRITE_DOUBLE_ACTION, NATIVE_IO,
    BYTE_ARRAY, WRITE_BYTE_ACTION, PUT_BYTES_ACTION, INT_TABLE, WRITE_TABLE_ACTION,
    SMALL_INT_TABLE, ST_ACTION, ST_ARRAY, CONSTRUCTOR_WIDE,
    ASYNC_SCOPE, COMPLETION, ASYNC_SUBSCRIPTION, ASYNC_ACTION,
    IO_ERROR_VALUE, IO_CATCH_FRAME, IO_ASYNC_FINISH_FRAME,
    CALL_STACK, IO_HANDLER_FRAME
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
    STRING_LENGTH, STRING_CODE_AT, STRING_SLICE, STRING_FROM_CODE, MLF_COMPARE_STRING,
    READ_DOUBLE, DOUBLE_TO_BITS, DOUBLE_FROM_BITS, SEQ, PANIC,
    READ_FILE, WRITE_FILE, FILE_EXISTS, CANONICAL_PATH, GET_ARG_COUNT, GET_ARG, PUT_ERR, EXIT_WITH,
    GET_EXECUTABLE_PATH, GET_CONTENTS,
    ST_RETURN, ST_BIND, RUN_ST, NEW_ST_ARRAY, READ_ST_ARRAY, WRITE_ST_ARRAY, LENGTH_ST_ARRAY,
    GET_ENV, SET_ENV, UNSET_ENV, RUN_PROCESS, LIST_DIRECTORY, DIRECTORY_EXISTS, FILE_DIGEST, ACQUIRE_FILE_LOCK, RELEASE_FILE_LOCK, PROCESS_SUPERVISOR,
    ASYNC_SCOPE_NEW, ASYNC_SCOPE_CLOSE, ASYNC_NEW_COMPLETION, ASYNC_RESOLVE_COMPLETION,
    ASYNC_READ_COMPLETION, ASYNC_SUBSCRIBE_COMPLETION, ASYNC_SUBSCRIPTION_STATUS,
    ASYNC_CANCEL_SUBSCRIPTION, ASYNC_STEP, ASYNC_ENQUEUE, ASYNC_DELAY, ASYNC_WAIT,
    TEXT_TO_CHARS, TEXT_FROM_CHARS, CHAR_CODE, CHAR_FROM_CODE,
    USER_ERROR, IO_ERROR, CATCH_IO_ERROR, IO_ERROR_STRING,
    EMPTY_CALL_STACK, PUSH_CALL_STACK, PRETTY_CALL_STACK, IO_ERROR_WITH_STACK,
    PRIMITIVE_COUNT
} Primitive;

struct MlfEnv {
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
        struct { size_t length; char *bytes; size_t *indices; } string;
        struct { int64_t identity, arity; MlfEnv *fields; } constructor;
        struct { int64_t identity; MlfValue *fields[2]; } packed;
        struct { Primitive identity; MlfEnv *arguments; } primitive;
        struct { Primitive operation; MlfValue *first, *second; } action;
        MlfCompletionScope *async_scope;
        MlfCompletion *completion;
        struct { MlfCompletionResume *resume; MlfCompletionStatus rejected; } subscription;
    } as;
};

/* Wide compact constructors keep MlfValue as their first real subobject.
 * Field zero uses its final pointer slot; the remaining fields follow it. */
typedef struct {
    MlfValue value;
    MlfValue *remaining_fields[];
} WideConstructor;
_Static_assert(offsetof(WideConstructor, remaining_fields) == 32, "compact wide tail ABI");
static MlfValue *wide_field(MlfValue *value, uint64_t index) {
    return index ? ((WideConstructor *)value)->remaining_fields[index - 1]
                 : (MlfValue *)value->as.constructor.fields;
}

static void gc_register_layout(void) {
    /* A general constructor may share an allocation with its environment.
     * Retain that allocation even when only an environment reference remains
     * and the embedding caller has disabled arbitrary interior pointers.
     * Register before initialization/allocation; the macro also accounts for
     * collector debug headers. */
    GC_REGISTER_DISPLACEMENT(sizeof(MlfValue));
    /* Generated field views can outlive the value pointer itself. */
    GC_REGISTER_DISPLACEMENT(offsetof(MlfValue, as.constructor.fields));
}

typedef struct Stack {
    void **items;
    size_t count, capacity;
    struct Stack *next;
} Stack;
/* Register auxiliary stacks so fatal IO/black-hole errors also release them. */
static Stack *active_stacks;
static MlfRoots *native_roots;
static void cleanup(void);
static void mlf_process_binding_clear(void);
static int valid_utf8(const unsigned char *bytes, size_t length);
static int argument_count;
static char **argument_values;

void mlf_set_args(int32_t argc, char **argv) {
    /* Generated entry points initialize arguments before any language IO.
     * Batch byte/line reads share a modest stdio buffer; getline still defines
     * read boundaries, and every output action keeps its explicit flush.
     * Do this only once, so an embedding cannot discard buffered input when
     * updating arguments for another entry point in the same process. */
    static char input_buffer[65536];
    static int input_configured;
    if (!input_configured) {
#if defined(_WIN32)
        _setmode(_fileno(stdin),_O_BINARY);
        _setmode(_fileno(stdout),_O_BINARY);
        _setmode(_fileno(stderr),_O_BINARY);
#endif
        (void)setvbuf(stdin, input_buffer, _IOFBF, sizeof(input_buffer));
        input_configured = 1;
    }
    argument_count = argc > 0 ? argc - 1 : 0;
    argument_values = argc > 0 ? argv + 1 : NULL;
#if defined(_WIN32)
    int count;
    wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&count);
    if (!wide) abort();
    char **utf8=malloc((size_t)count*sizeof(char *));
    if (!utf8) abort();
    for (int i=0;i<count;++i) { utf8[i]=mlf_utf8(wide[i]); if (!utf8[i]) abort(); }
    LocalFree(wide);
    argument_count=count>0 ? count-1 : 0;
    argument_values=count>0 ? utf8+1 : NULL;
#endif
}

/* The low bits distinguish immediate integers, booleans and nullary data
 * from aligned heap pointers. Integers outside the signed 63-bit range keep
 * their arbitrary-precision GMP representation. */
_Static_assert(sizeof(void *) == 8 && sizeof(size_t) == 8, "native runtime requires a 64-bit ABI");
_Static_assert(_Alignof(MlfValue) >= 8, "native tagged pointer alignment");
_Static_assert(sizeof(Tag) == 4 && INDIRECT == 2 && CLOSURE == 5 &&
               HOLE < CLOSURE && BUSY < CLOSURE && THUNK < CLOSURE && APPLICATION < CLOSURE,
               "generated WHNF test tag ABI");
_Static_assert(offsetof(MlfValue, tag) == 0 && offsetof(MlfValue, as.indirect) == 8,
               "compact generated WHNF test offsets");
_Static_assert(BUSY == 1 && INDIRECT == 2 && THUNK == 3 && CLOSURE == 5, "compact force tag ABI");
_Static_assert(offsetof(MlfValue, tag) == 0 && offsetof(MlfValue, as.closure.code) == 8 && offsetof(MlfValue, as.closure.env) == 16, "compact force payload ABI");
_Static_assert(offsetof(MlfValue, as.packed.identity) == 8, "constructor identity ABI");
_Static_assert(offsetof(MlfValue, as.packed.fields) == 16, "constructor field ABI");
_Static_assert(offsetof(MlfValue, as.constructor.fields) == 24, "general constructor environment ABI");
_Static_assert(offsetof(MlfEnv, slots) == 8, "environment slots ABI");
_Static_assert(offsetof(MlfValue, as.floating) == 8, "Double payload ABI");
_Static_assert(offsetof(MlfValue, as.int_array.length) == 8 &&
               offsetof(MlfValue, as.double_array.length) == 8 &&
               offsetof(MlfValue, as.byte_array.length) == 8, "array length ABI");
_Static_assert(offsetof(MlfValue, as.int_array.cells) == 16 &&
               offsetof(MlfValue, as.double_array.cells) == 16 &&
               offsetof(MlfValue, as.byte_array.cells) == 16, "array storage ABI");
_Static_assert(sizeof(MlfValue) == 32, "managed value size ABI");
_Static_assert(STRING == 8 && offsetof(MlfValue, as.string.length) == 8 &&
               offsetof(MlfValue, as.string.bytes) == 16 &&
               offsetof(MlfValue, as.string.indices) == 24, "compact static string ABI");
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

#if defined(MLF_ALLOCATION_AUDIT)
extern void mlf_bench_constructed_node(int64_t tag);
#define CONSTRUCTED(tag) mlf_bench_constructed_node(tag)
#else
#define CONSTRUCTED(tag) ((void)0)
#endif

#if defined(MLF_TABLE_AUDIT)
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

static MlfValue *value(Tag tag) {
    MlfValue *result;
    /* These tags use at most two payload words. Mutable evaluation cells only
     * become BUSY/INDIRECT and clear those same two words. No operation reads
     * the unused trailing union word; keeping the prefix saves a GC size class. */
    switch (tag) {
    case HOLE: case BUSY: case INDIRECT: case THUNK: case APPLICATION:
    case CLOSURE: case INTEGER: case DOUBLE: case PRIMITIVE: case NATIVE_IO:
    case CONSTRUCTOR_1: case INT_ARRAY: case DOUBLE_ARRAY: case BYTE_ARRAY:
    case INT_TABLE: case SMALL_INT_TABLE: case ST_ARRAY:
    case ASYNC_SCOPE: case COMPLETION: case ASYNC_SUBSCRIPTION: case ASYNC_ACTION:
        result = allocate(offsetof(MlfValue, as) + 2 * sizeof(void *));
        break;
    default: result = allocate(sizeof(*result)); break;
    }

    result->tag = tag;
    return result;
}

MlfEnv *mlf_env_new(uint64_t count) {
    if (count > (SIZE_MAX - sizeof(MlfEnv)) / sizeof(MlfValue *)) fail("environment too large");
    MlfEnv *env = allocate(sizeof(*env) + (size_t)count * sizeof(MlfValue *));
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

/* The generated single-entry callback consumes and clears this private
 * environment before evaluating its body. Clearing is essential: after the
 * thunk is entered, its update root otherwise keeps every captured value
 * alive through this shared allocation, even after the union is cleared. */
MlfValue *mlf_thunk_new(MlfCode code, uint64_t count) {
    if (!code) fail("missing native code");
    if (!count) return code_value(THUNK, code, NULL);
    if (count > (SIZE_MAX - sizeof(MlfValue) - sizeof(MlfEnv)) / sizeof(MlfValue *))
        fail("environment too large");
    /* Captures follow the closure payload. The unused third union word
     * belongs to the environment count in compact allocations. The existing
     * displacement registration at byte 24 also covers this environment. */
    const size_t prefix = offsetof(MlfValue, as.closure) + sizeof(((MlfValue *)0)->as.closure);
    _Static_assert(offsetof(MlfValue, as.closure) + sizeof(((MlfValue *)0)->as.closure) == 24, "compact capture prefix ABI");
    _Static_assert(THUNK == 3 && offsetof(MlfValue, as.closure.code) == 8 && offsetof(MlfValue, as.closure.env) == 16 && sizeof(MlfEnv) == 8, "compact inline thunk ABI");
    MlfValue *result = allocate(prefix + sizeof(MlfEnv) + (size_t)count * sizeof(MlfValue *));
    MlfEnv *env = (MlfEnv *)((unsigned char *)result + prefix);
    result->tag = THUNK;
    result->as.closure.code = code;
    result->as.closure.env = env;
    env->count = (size_t)count;

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
    result->as.string.indices = NULL;
    memcpy(result->as.string.bytes, bytes, (size_t)length);
    return result;
}

/* Only generated compact constructors use these batches. In debug/audit
 * builds the heads stay empty, routing every allocation through the public
 * allocator or audit hook. Each index denotes the exact requested word count.
 * Normal BDWGC allocation retains its one-past-end padding and descriptor. */
_Static_assert(CONSTRUCTOR_1 == 12 && CONSTRUCTOR_2 == 13 && CONSTRUCTOR_WIDE == 28, "compact constructor tag ABI");
_Static_assert(offsetof(MlfValue, as.packed.identity) == 8 && offsetof(MlfValue, as.packed.fields) == 16, "compact packed constructor ABI");
void *mlf_constructor_pending[33];
void *mlf_constructor_allocate(int64_t identity, uint64_t count) {
    if (identity < 0 || count == 0 || count > INT64_MAX ||
        count > (SIZE_MAX - 24) / sizeof(void *))
        fail("invalid constructor descriptor");
    size_t size = (count <= 2 ? 16 : 24) + count * sizeof(void *);
    void *result;
#if !defined(GC_DEBUG) && !defined(GC_DEBUG_REPLACEMENT) && !defined(MLF_ALLOCATION_AUDIT)
    if (size <= 256) {
        gc_start();
        result = GC_malloc_many((size / 16 + 1) * 16 - 1);
        if (!result) result = GC_MALLOC(size);
        if (!result) fail("out of memory");
        void *next = GC_NEXT(result);
        mlf_constructor_pending[size / sizeof(void *)] = next;
        GC_NEXT(result) = NULL;
        GC_reachable_here(next);
    } else
#endif
        result = allocate(size);
    CONSTRUCTED(identity);
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

MlfValue *mlf_constructor_fields(int64_t identity, MlfEnv *fields) {
    if (identity < 0 || !fields || fields->count > INT64_MAX)
        fail("invalid constructor descriptor");
    if (!fields->count) return mlf_constructor(identity, 0);
    if (fields->count == 1) return mlf_constructor1(identity, fields->slots[0]);
    if (fields->count == 2) return mlf_constructor2(identity, fields->slots[0], fields->slots[1]);
    MlfValue *result = mlf_constructor_new(identity, fields->count);
    result->as.constructor.fields = (MlfEnv *)fields->slots[0];
    memcpy(((WideConstructor *)result)->remaining_fields, fields->slots + 1,
           (fields->count - 1) * sizeof(MlfValue *));
    return result;
}

MlfValue *mlf_constructor_new(int64_t identity, uint64_t count) {
    if (identity < 0 || count < 3 || count > INT64_MAX ||
        count > (SIZE_MAX - sizeof(MlfValue) - sizeof(MlfEnv)) / sizeof(MlfValue *))
        fail("invalid constructor descriptor");
    WideConstructor *allocation = allocate(sizeof(WideConstructor) + (count - 1) * sizeof(MlfValue *));
    MlfValue *result = &allocation->value;
    result->tag = CONSTRUCTOR_WIDE;
    result->as.constructor.identity = identity;
    result->as.constructor.arity = (int64_t)count;

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
    if (identity == EMPTY_CALL_STACK) return value(CALL_STACK);
    if (identity == GET_LINE || identity == GET_BYTE_LINE || identity == NEW_INT_TABLE || identity == GET_ARG_COUNT ||
        identity == GET_EXECUTABLE_PATH || identity == GET_CONTENTS)
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
            (tag == MLF_BOOLEAN && boolean_value(result)) ||
            (tag == CONSTRUCTOR && nullary(result))) return result;
        fail("invalid value for runtime operation");
    }
    if (tag == CONSTRUCTOR && (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2 || result->tag == CONSTRUCTOR_WIDE)) return result;
    if (tag == INT_TABLE && result->tag == SMALL_INT_TABLE) return result;
    if (result->tag != tag) fail("invalid value for runtime operation");
    return result;
}

int64_t mlf_tag(MlfValue *entry) {
    MlfValue *result = expect(entry, CONSTRUCTOR);
    if (nullary(result)) return (int64_t)((uintptr_t)result >> 3);
    if (result->tag == CONSTRUCTOR_1 || result->tag == CONSTRUCTOR_2) return result->as.packed.identity;
    if (result->tag == CONSTRUCTOR_WIDE) return result->as.constructor.identity;
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
    if (result->tag == CONSTRUCTOR_WIDE) {
        if (index >= (uint64_t)result->as.constructor.arity || !wide_field(result,index))
            fail("invalid environment read");
        return wide_field(result,index);
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
            free(result);

            return small(n);
        }
    }

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
        if (n >= 0) mpz_add_ui(result->as.integer,result->as.integer,(uint64_t)n);
        else mpz_sub_ui(result->as.integer,result->as.integer,(uint64_t)-n);
    } else {
        MlfValue *big = small_integer(a) ? b : a;
        int64_t n = small_value(small_integer(a) ? a : b);
        if (subtract && !small_integer(a)) n = -n;
        if (subtract && small_integer(a)) {
            /* n - big = -(big - n), without copying either operand. */
            if (n >= 0) mpz_sub_ui(result->as.integer,big->as.integer,(uint64_t)n);
            else mpz_add_ui(result->as.integer,big->as.integer,(uint64_t)-n);
            mpz_neg(result->as.integer,result->as.integer);
        } else if (n >= 0) mpz_add_ui(result->as.integer,big->as.integer,(uint64_t)n);
        else mpz_sub_ui(result->as.integer,big->as.integer,(uint64_t)-n);
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
        int64_t n = small_value(small_integer(a) ? a : b);
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
        int order = mpz_cmp_si(b->as.integer, (int64_t)small_value(a));
        return (order < 0) - (order > 0);
    }
    if (small_integer(b)) return mpz_cmp_si(a->as.integer, (int64_t)small_value(b));
    return mpz_cmp(a->as.integer, b->as.integer);
}

MlfValue *mlf_eq_int(MlfValue *a, MlfValue *b) { return mlf_boolean(integer_compare(a,b) == 0); }
MlfValue *mlf_lt_int(MlfValue *a, MlfValue *b) { return mlf_boolean(integer_compare(a,b) < 0); }

int64_t mlf_truth(MlfValue *entry) {
    MlfValue *b = expect(entry, MLF_BOOLEAN);
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

/* The private index slot retains the generated string ABI. ASCII needs only
 * a marker. Mostly ASCII text stores correction events after multibyte scalars;
 * dense Unicode keeps its direct table. A cached event interval makes sequential
 * indexing constant time without a size_t entry for every ASCII character. */
static size_t ascii_string_indices;
static size_t *string_indices(MlfValue *text) {
    if (text->as.string.indices) return text->as.string.indices;
    const unsigned char *bytes = (const unsigned char *)text->as.string.bytes;
    size_t length = text->as.string.length, count = 0;
    while (count < length && bytes[count] < 0x80) ++count;
    if (count == length) {
        text->as.string.indices = &ascii_string_indices;
        return &ascii_string_indices;
    }
    if (!valid_utf8(bytes,length)) fail("invalid Unicode scalar");
    count = 0;
    size_t multibyte = 0;
    for (size_t i = 0; i < length; ++i) if ((bytes[i] & 0xc0) != 0x80) {
        ++count;
        if (bytes[i] >= 0xc0) ++multibyte;
    }
    if (count > SIZE_MAX / sizeof(size_t) - 2) fail("string too large");
    if (6 + 2 * multibyte < count + 2) {
        /* Header: sentinel, scalar count, event count, cached inclusive
         * lower/upper bounds, cached byte correction. Each event stores the
         * scalar boundary after a multibyte character and its byte correction.
         * A real dense count cannot reach the sentinel after the size check. */
        size_t *indices = allocate((6 + 2 * multibyte) * sizeof(size_t));
        indices[0] = SIZE_MAX;
        indices[1] = count;
        indices[2] = multibyte;
        size_t next = 6, scalar = 0;
        for (size_t i = 0; i < length; ++scalar) {
            unsigned lead = bytes[i];
            size_t width = lead < 0x80 ? 1 : lead < 0xe0 ? 2 : lead < 0xf0 ? 3 : 4;
            i += width;
            if (width > 1) {
                indices[next++] = scalar + 1;
                indices[next++] = i - scalar - 1;
            }
        }
        indices[3] = 0;
        indices[4] = indices[6] - 1;
        indices[5] = 0;
        text->as.string.indices = indices;
        return indices;
    }
    size_t *indices = allocate((count + 2) * sizeof(size_t));
    indices[0] = count;
    size_t next = 1;
    for (size_t i = 0; i < length; ++i) if ((bytes[i] & 0xc0) != 0x80) indices[next++] = i;
    indices[next] = length;
    text->as.string.indices = indices;
    return indices;
}

static size_t string_index_count(MlfValue *text, size_t *indices) {
    return indices == &ascii_string_indices ? text->as.string.length :
        indices[0] == SIZE_MAX ? indices[1] : indices[0];
}

static size_t string_byte_offset(size_t *indices, size_t scalar) {
    if (indices[0] != SIZE_MAX) return indices[scalar + 1];
    if (scalar < indices[3] || scalar > indices[4]) {
        /* Upper-bound search also accepts the final boundary for slicing. */
        size_t low = 0, high = indices[2];
        while (low < high) {
            size_t middle = low + (high - low) / 2;
            if (indices[6 + 2 * middle] <= scalar) low = middle + 1;
            else high = middle;
        }
        indices[3] = low ? indices[6 + 2 * (low - 1)] : 0;
        indices[4] = low < indices[2] ? indices[6 + 2 * low] - 1 : indices[1];
        indices[5] = low ? indices[7 + 2 * (low - 1)] : 0;
    }
    return scalar + indices[5];
}

static size_t string_length(MlfValue *text) {
    return string_index_count(text,string_indices(text));
}

static MlfValue *string_code_at(MlfValue *text, MlfValue *index) {
    text = expect(text,STRING);
    index = expect(index,INTEGER);
    size_t *indices = string_indices(text);
    size_t count = string_index_count(text,indices);
    if (!count) fail("string index out of bounds");
    size_t i = (size_t)bounded_integer(index,count-1,"string index out of bounds");
    const unsigned char *bytes = (const unsigned char *)text->as.string.bytes;
    if (indices == &ascii_string_indices) return small((int64_t)bytes[i]);
    size_t position = string_byte_offset(indices,i), end = string_byte_offset(indices,i+1);
    unsigned scalar = bytes[position++];
    if (scalar >= 0xc0) scalar &= end-position == 1 ? 0x1f : end-position == 2 ? 0x0f : 7;
    while (position < end) scalar = (scalar << 6) | (bytes[position++] & 0x3f);
    return small((int64_t)scalar);
}

static MlfValue *string_slice(MlfValue *text, MlfValue *offset, MlfValue *count) {
    text = expect(text,STRING);
    offset = expect(offset,INTEGER);
    count = expect(count,INTEGER);
    size_t *indices = string_indices(text);
    size_t scalars = string_index_count(text,indices);
    size_t start = (size_t)bounded_integer(offset,scalars,"string slice out of bounds");
    size_t length = (size_t)bounded_integer(count,scalars-start,"string slice out of bounds");
    if (indices == &ascii_string_indices) {
        MlfValue *result = mlf_string(text->as.string.bytes + start,length);
        result->as.string.indices = &ascii_string_indices;
        return result;
    }
    size_t first = string_byte_offset(indices,start);
    size_t last = string_byte_offset(indices,start+length);
    return mlf_string(text->as.string.bytes + first,last-first);
}

static MlfValue *string_from_code(MlfValue *entry) {
    unsigned scalar = (unsigned)bounded_integer(entry,0x10ffff,"invalid Unicode scalar");
    if (scalar >= 0xd800 && scalar <= 0xdfff) fail("invalid Unicode scalar");
    unsigned char bytes[4];
    size_t count;
    if (scalar < 0x80) { count = 1; bytes[0] = (unsigned char)scalar; }
    else if (scalar < 0x800) {
        count = 2; bytes[0] = 0xc0 | (scalar >> 6); bytes[1] = 0x80 | (scalar & 0x3f);
    } else if (scalar < 0x10000) {
        count = 3; bytes[0] = 0xe0 | (scalar >> 12); bytes[1] = 0x80 | ((scalar >> 6) & 0x3f); bytes[2] = 0x80 | (scalar & 0x3f);
    } else {
        count = 4; bytes[0] = 0xf0 | (scalar >> 18); bytes[1] = 0x80 | ((scalar >> 12) & 0x3f);
        bytes[2] = 0x80 | ((scalar >> 6) & 0x3f); bytes[3] = 0x80 | (scalar & 0x3f);
    }
    return mlf_string((const char *)bytes,count);
}

/* Fixed canonical constructor ABI, shared with LLVM.entryConstructors.
 * Legacy tag0 is a private tombstone; ()=1, []=2, (:)=3, tuples2..4=4..6. */
enum { SOURCE_NIL = 2, SOURCE_CONS = 3, SOURCE_STACK_FRAME = 7 };
static MlfValue *text_chars_step(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    MlfValue *text = mlf_env_get(env, 0);
    uint64_t index = bounded_integer(mlf_env_get(env, 1), INT64_MAX, "text index overflow");
    if (index == string_length(text)) return mlf_constructor(SOURCE_NIL, 0);
    MlfEnv *next = mlf_env_new(2);
    mlf_env_set(next, 0, text);
    mlf_env_set(next, 1, small((int64_t)index + 1));
    return mlf_constructor2(SOURCE_CONS, string_code_at(text, small((int64_t)index)),
                            mlf_thunk(text_chars_step, next));
}
static MlfValue *text_to_chars(MlfValue *text) {
    MlfEnv *env = mlf_env_new(2);
    mlf_env_set(env, 0, expect(text, STRING));
    mlf_env_set(env, 1, small(0));
    return text_chars_step(env, NULL);
}
static MlfValue *text_from_chars(MlfValue *chars) {
    size_t size = 0, capacity = 64;
    char *bytes = allocate(capacity);
    while (mlf_tag(chars) != SOURCE_NIL) {
        if (mlf_tag(chars) != SOURCE_CONS) fail("expected canonical character list");
        MlfValue *piece = string_from_code(mlf_field(chars, 0));
        size_t n = piece->as.string.length;
        if (size > SIZE_MAX - n) fail("string too large");
        if (size + n > capacity) {
            if (capacity > SIZE_MAX / 2) fail("string too large");
            capacity *= 2;
            bytes = realloc(bytes, capacity);
            if (!bytes) fail("out of memory");
        }
        memcpy(bytes + size, piece->as.string.bytes, n);
        size += n;
        chars = mlf_field(chars, 1);
    }
    MlfValue *result = mlf_string(bytes, size);
    free(bytes);
    return result;
}
/* Managed source stacks retain lazy frame fields. The opaque representation
 * is not a new ordinary class dictionary and does not simulate machine stacks. */
static MlfValue *push_call_stack(MlfValue *frame, MlfValue *stack) {
    if (mlf_tag(frame) != SOURCE_STACK_FRAME) fail("expected source stack frame");
    stack = expect(stack, CALL_STACK);
    MlfValue *result = value(CALL_STACK);
    result->as.application.function = frame;
    result->as.application.argument = stack;
    return result;
}
static MlfValue *chars_append_step(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    MlfValue *left = mlf_env_get(env, 0), *right = mlf_env_get(env, 1);
    if (mlf_tag(left) == SOURCE_NIL) return right;
    if (mlf_tag(left) != SOURCE_CONS) fail("expected canonical character list");
    MlfEnv *next = mlf_env_new(2);
    mlf_env_set(next, 0, mlf_field(left, 1));
    mlf_env_set(next, 1, right);
    return mlf_constructor2(SOURCE_CONS, mlf_field(left, 0), mlf_thunk(chars_append_step, next));
}
static MlfValue *chars_append(MlfValue *left, MlfValue *right) {
    MlfEnv *env = mlf_env_new(2);
    mlf_env_set(env, 0, left);
    mlf_env_set(env, 1, right);
    return mlf_thunk(chars_append_step, env);
}
static void source_coordinates(MlfValue *frame) {
    /* GHC SrcLoc's four machine-Int fields are strict once its location is
     * demanded, even though the end coordinates are not pretty-printed. */
    for (unsigned i = 4; i < 8; ++i) {
        MlfValue *n = expect(mlf_field(frame, i), INTEGER);
        if (!small_integer(n) && !mpz_fits_slong_p(n->as.integer))
            fail("source coordinate out of bounds");
    }
}
static MlfValue *stack_segment(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    MlfValue *stack = expect(mlf_env_get(env, 0), CALL_STACK);
    MlfValue *frame = stack->as.application.function;
    if (!frame) return mlf_constructor(SOURCE_NIL, 0);
    unsigned part = (unsigned)bounded_integer(mlf_env_get(env, 1), 12, "invalid stack segment");
    if (part == 12) {
        MlfEnv *next = mlf_env_new(2);
        mlf_env_set(next, 0, stack->as.application.argument);
        mlf_env_set(next, 1, small(0));
        return mlf_thunk(stack_segment, next);
    }
    MlfValue *text;
    switch (part) {
    case 0: text = mlf_string("\n  ", 3); break;
    case 1: text = mlf_field(frame, 0); break;
    case 2: text = mlf_string(", called at ", 12); break;
    case 3: source_coordinates(frame); text = mlf_field(frame, 3); break;
    case 4: case 6: case 10: text = mlf_string(":", 1); break;
    case 5: text = show_integer(mlf_field(frame, 4)); break;
    case 7: text = show_integer(mlf_field(frame, 5)); break;
    case 8: text = mlf_string(" in ", 4); break;
    case 9: text = mlf_field(frame, 1); break;
    default: text = mlf_field(frame, 2); break;
    }
    MlfEnv *next = mlf_env_new(2);
    mlf_env_set(next, 0, stack);
    mlf_env_set(next, 1, small((int64_t)part + 1));
    return chars_append(text_to_chars(text), mlf_thunk(stack_segment, next));
}
static MlfValue *pretty_call_stack(MlfValue *stack) {
    stack = expect(stack, CALL_STACK);
    if (!stack->as.application.function) return mlf_constructor(SOURCE_NIL, 0);
    MlfEnv *env = mlf_env_new(2);
    mlf_env_set(env, 0, stack);
    mlf_env_set(env, 1, small(0));
    const char *header = "CallStack (from HasCallStack):";
    return force(chars_append(text_to_chars(mlf_string(header, strlen(header))),
                              mlf_thunk(stack_segment, env)));
}
/* Only uncaught diagnostics demand message/context strings. Valid surrogate
 * Char values are escaped here, rather than altering the typed error channel. */
static void write_diagnostic_chars(MlfValue *chars) {
    while (mlf_tag(chars) != SOURCE_NIL) {
        if (mlf_tag(chars) != SOURCE_CONS) fail("expected canonical character list");
        MlfValue *ch = mlf_field(chars, 0);
        unsigned code = (unsigned)bounded_integer(ch, 0x10ffff, "invalid Char codepoint");
        if (code >= 0xd800 && code <= 0xdfff) fprintf(stderr, "\\u%04x", code);
        else {
            MlfValue *piece = string_from_code(ch);
            fwrite(piece->as.string.bytes, 1, piece->as.string.length, stderr);
        }
        chars = mlf_field(chars, 1);
    }
}
static void write_io_error(MlfValue *error) {
    fputs("user error (", stderr);
    write_diagnostic_chars(expect(error, IO_ERROR_VALUE)->as.indirect);
    fputc(')', stderr);
}
static _Noreturn void uncaught_io_error(MlfValue *error, MlfValue *stack, MlfValue *contexts) {
    fputs("Runtime: ", stderr);
    write_io_error(error);
    fputc('\n', stderr);
    while (mlf_tag(contexts) != SOURCE_NIL) {
        fputs("While handling ", stderr);
        write_io_error(mlf_field(contexts, 0));
        fputc('\n', stderr);
        contexts = mlf_field(contexts, 1);
    }
    if (stack) {
        MlfValue *chars = pretty_call_stack(stack);
        if (mlf_tag(chars) != SOURCE_NIL) {
            write_diagnostic_chars(chars);
            fputc('\n', stderr);
        }
    }
    cleanup();
    exit(1);
}

static MlfValue *compare_string(MlfValue *a, MlfValue *b) {
    a = expect(a,STRING); b = expect(b,STRING);
    size_t left = a->as.string.length, right = b->as.string.length;
    int order = memcmp(a->as.string.bytes,b->as.string.bytes,left < right ? left : right);
    if (!order) order = (left > right) - (left < right);
    return small((order > 0) - (order < 0));
}

static int decimal_digit(char c) { return c >= '0' && c <= '9'; }
static MlfValue *read_double(MlfValue *text) {
    text = expect(text,STRING);
    const char *s = text->as.string.bytes;
    size_t n = text->as.string.length, i = 0, start;
    if (i < n && (s[i] == '-' || s[i] == '+')) ++i;
    start = i;
    while (i < n && decimal_digit(s[i])) ++i;
    if (i == start) fail("invalid Double input");
    if (i < n && s[i] == '.') {
        start = ++i;
        while (i < n && decimal_digit(s[i])) ++i;
        if (i == start) fail("invalid Double input");
    }
    if (i < n && (s[i] == 'e' || s[i] == 'E')) {
        ++i;
        if (i < n && (s[i] == '-' || s[i] == '+')) ++i;
        start = i;
        while (i < n && decimal_digit(s[i])) ++i;
        if (i == start) fail("invalid Double input");
    }
    if (i != n) fail("invalid Double input");
    return mlf_double(strtod(s,NULL));
}

static MlfValue *double_to_bits(MlfValue *entry) {
    double n = unbox_double(entry);
    uint64_t bits;
    memcpy(&bits,&n,sizeof(bits));
    if (bits <= SMALL_MAX) return small((int64_t)bits);
    MlfValue *result = value(INTEGER);
    mpz_init_set_ui(result->as.integer,(uint64_t)bits);

    return result;
}

static MlfValue *double_from_bits(MlfValue *entry) {
    uint64_t bits = bounded_integer(entry,UINT64_MAX,"Double bit pattern out of bounds");
    double n;
    memcpy(&n,&bits,sizeof(n));
    return mlf_double(n);
}

/* State actions are immutable descriptions, distinct from IO. Stored operands
 * remain lazy until the local executor needs their sizes, indices or arrays. */
static MlfValue *st_action(Primitive operation, size_t count,
                           MlfValue *first, MlfValue *second, MlfValue *third) {
    MlfEnv *arguments = mlf_env_new(count);
    if (count > 0) mlf_env_set(arguments,0,first);
    if (count > 1) mlf_env_set(arguments,1,second);
    if (count > 2) mlf_env_set(arguments,2,third);
    MlfValue *result = value(ST_ACTION);
    result->as.primitive.identity = operation;
    result->as.primitive.arguments = arguments;
    return result;
}

static MlfValue *async_action(Primitive operation, size_t count,
                              MlfValue *a, MlfValue *b, MlfValue *c) {
    MlfValue *result = st_action(operation, count, a, b, c);
    result->tag = ASYNC_ACTION;
    return result;
}

static MlfValue *run_st(MlfValue *root);

static MlfValue *primitive_result(Primitive p, MlfValue *a, MlfValue *b, MlfValue *c) {
    switch (p) {
    case ASYNC_SCOPE_CLOSE: case ASYNC_SUBSCRIPTION_STATUS: case ASYNC_CANCEL_SUBSCRIPTION:
    case ASYNC_STEP: return async_action(p,1,a,NULL,NULL);
    case ASYNC_SCOPE_NEW: case ASYNC_RESOLVE_COMPLETION: case ASYNC_SUBSCRIBE_COMPLETION:
    case ASYNC_ENQUEUE: case ASYNC_WAIT: return async_action(p,2,a,b,NULL);
    case ASYNC_NEW_COMPLETION: case ASYNC_READ_COMPLETION: case ASYNC_DELAY: return async_action(p,3,a,b,c);
    case ST_RETURN: case LENGTH_ST_ARRAY: return st_action(p,1,a,NULL,NULL);
    case ST_BIND: case NEW_ST_ARRAY: case READ_ST_ARRAY: return st_action(p,2,a,b,NULL);
    case WRITE_ST_ARRAY: return st_action(p,3,a,b,c);
    /* Codegen.evaluate promises canonical WHNF for a saturated pure result.
     * The executor itself preserves the laziness of values passed to binds. */
    case RUN_ST: return force(run_st(a));
    case IO_ERROR: case CATCH_IO_ERROR: case IO_ERROR_WITH_STACK:
    case IO_RETURN: case IO_BIND: case PUT_STR: case PUT_STR_LN: case GET_LINE: case PRINT_INT:
    case NEW_INT_ARRAY: case READ_INT_ARRAY: case LENGTH_INT_ARRAY:
    case NEW_DOUBLE_ARRAY: case READ_DOUBLE_ARRAY: case LENGTH_DOUBLE_ARRAY:
    case NEW_BYTE_ARRAY: case READ_BYTE_ARRAY: case LENGTH_BYTE_ARRAY: case BYTE_ARRAY_FROM_STRING:
    case GET_BYTE_LINE: case NEW_INT_TABLE: case READ_INT_TABLE:
    case READ_FILE: case WRITE_FILE: case FILE_EXISTS: case CANONICAL_PATH:
    case GET_ARG_COUNT: case GET_ARG: case PUT_ERR: case EXIT_WITH:
    case GET_EXECUTABLE_PATH: case GET_CONTENTS:
    case GET_ENV: case SET_ENV: case UNSET_ENV: case RUN_PROCESS: case LIST_DIRECTORY: case DIRECTORY_EXISTS: case FILE_DIGEST: case ACQUIRE_FILE_LOCK: case RELEASE_FILE_LOCK: case PROCESS_SUPERVISOR:
        return action(p, a, b);
    case WRITE_INT_ARRAY: return array_write_action(WRITE_INT_ACTION,a,b,c);
    case WRITE_DOUBLE_ARRAY: return array_write_action(WRITE_DOUBLE_ACTION,a,b,c);
    case WRITE_BYTE_ARRAY: return array_write_action(WRITE_BYTE_ACTION,a,b,c);
    case PUT_BYTES: return array_write_action(PUT_BYTES_ACTION,a,b,c);
    case WRITE_INT_TABLE: return array_write_action(WRITE_TABLE_ACTION,a,b,c);
    case EMPTY_CALL_STACK: return value(CALL_STACK);
    case PUSH_CALL_STACK: return push_call_stack(a, b);
    case PRETTY_CALL_STACK: return pretty_call_stack(a);
    case TEXT_TO_CHARS: return text_to_chars(a);
    case TEXT_FROM_CHARS: return text_from_chars(a);
    case CHAR_CODE: case CHAR_FROM_CODE:
        return small((int64_t)bounded_integer(a, 0x10ffff, "invalid Char codepoint"));
    case USER_ERROR: {
        MlfValue *error = value(IO_ERROR_VALUE);
        error->as.indirect = a;
        return error;
    }
    case IO_ERROR_STRING: return force(expect(a, IO_ERROR_VALUE)->as.indirect);
    case SHOW_INT: return show_integer(a);
    case CONCAT_STRING: {
        a = expect(a, STRING); b = expect(b, STRING);
        size_t left = a->as.string.length, right = b->as.string.length;
        if (right >= SIZE_MAX - left) fail("string too large");
        MlfValue *result = value(STRING);
        result->as.string.length = left + right;
        result->as.string.bytes = allocate(left + right + 1);
        result->as.string.indices = NULL;
        memcpy(result->as.string.bytes, a->as.string.bytes, left);
        memcpy(result->as.string.bytes + left, b->as.string.bytes, right);
        return result;
    }
    case ADD_INT: return mlf_add_int(a,b);
    case SUB_INT: return mlf_sub_int(a,b);
    case MUL_INT: case QUOT_INT: case REM_INT: case AND_INT: return integer_extended(p,a,b);
    case READ_INT: return read_integer(a);
    case STRING_LENGTH: return small((int64_t)string_length(expect(a,STRING)));
    case STRING_CODE_AT: return string_code_at(a,b);
    case STRING_SLICE: return string_slice(a,b,c);
    case STRING_FROM_CODE: return string_from_code(a);
    case MLF_COMPARE_STRING: return compare_string(a,b);
    case READ_DOUBLE: return read_double(a);
    case DOUBLE_TO_BITS: return double_to_bits(a);
    case DOUBLE_FROM_BITS: return double_from_bits(a);
    case SEQ: (void)force(a); return b;
    case PANIC:
        a = expect(a,STRING);
        fprintf(stderr,"Runtime: ");
        for (size_t i = 0; i < a->as.string.length; ++i) fprintf(stderr,"%c",(unsigned char)a->as.string.bytes[i]);
        fprintf(stderr,"\n");
        cleanup(); exit(1);
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
        2,2,2,2,1,2,2,1,2,2,2,3,1,2,2,3,1,2,2,3,1,1,3,0,0,2,3,2,
        1,2,3,1,2,1,1,1,2,1,1,2,1,1,0,1,1,1,0,0,
        1,2,1,2,2,3,1,
        1,2,1,2,1,1,1,1,1,1, 2,1,3,2,3,2,1,1,1,2,3,2, 1,1,1,1,1,1,2,1, 0,2,1,2
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
    case CONSTRUCTOR_WIDE: fail("constructor overapplication");
    case CONSTRUCTOR: {
        if (function->as.constructor.fields->count >= (uint64_t)function->as.constructor.arity)
            fail("constructor overapplication");
        if (function->as.constructor.arity == 1) return mlf_constructor1(function->as.constructor.identity, argument);
        if (function->as.constructor.arity == 2 && function->as.constructor.fields->count == 1)
            return mlf_constructor2(function->as.constructor.identity, function->as.constructor.fields->slots[0], argument);
        MlfValue *result = value(CONSTRUCTOR);
        result->as.constructor = function->as.constructor;
        result->as.constructor.fields = append(function->as.constructor.fields, argument);
        if ((uint64_t)result->as.constructor.arity == result->as.constructor.fields->count)
            return mlf_constructor_fields(result->as.constructor.identity,result->as.constructor.fields);
        return result;
    }
    default: fail("application of a non-function");
    }
}

/* Follow tail applications/indirections iteratively and update every thunk
 * on the spine. BUSY catches recursive demand, including x = x cycles.
 */
static void memoize(MlfValue *old, MlfValue *entry) {
    old->tag = INDIRECT;
    /* The collector scans the whole union, so discard obsolete closure
     * environments and application arguments after memoizing the result. */
    memset(&old->as, 0, sizeof(old->as.closure));
    old->as.indirect = entry;
}

static MlfValue *force(MlfValue *entry) {
    /* Most evaluations update one thunk. Keep that root on the native stack
     * and use the managed spill stack only for longer update spines. */
    MlfValue *first_update = NULL;
    Stack updates = {0};
    for (;;) {
        if (!entry) fail("missing runtime value");
        if (immediate(entry)) break;
        Tag tag = entry->tag;
        if (tag == HOLE || tag == BUSY) fail("cyclic evaluation of a recursive binding");
        if (tag != THUNK && tag != APPLICATION && tag != INDIRECT) break;
        if (tag == INDIRECT) {
            MlfValue *ready = mlf_peek(entry);
            if (ready) { entry = ready; break; }
        }
        MlfValue *old = entry;
        if (first_update) push(&updates, old);
        else first_update = old;
        old->tag = BUSY;
        /* An entered thunk only needs its identity for the eventual update.
         * Keeping its old environment on this spine retains every historical
         * state until the whole computation returns. Live C operands protect
         * the values still needed by the callback or application. */
        if (tag == THUNK) {
            MlfCode code = old->as.closure.code;
            MlfEnv *env = old->as.closure.env;
            memset(&old->as, 0, sizeof(old->as.closure));
            entry = code(env, NULL);
        } else if (tag == APPLICATION) {
            MlfValue *function = old->as.application.function;
            MlfValue *argument = old->as.application.argument;
            memset(&old->as, 0, sizeof(old->as.closure));
            entry = apply(function, argument);
        } else {
            entry = old->as.indirect;
            memset(&old->as, 0, sizeof(old->as.closure));
        }
    }
    if (first_update) memoize(first_update, entry);
    for (size_t i = 0; i < updates.count; ++i) memoize(updates.items[i], entry);
    release_stack(&updates);
    return entry;
}

MlfValue *mlf_force(MlfValue *entry) {
    MlfValue *ready = mlf_peek(entry);
    if (ready) return ready;
    return force(entry);
}

/* Saturated primitive calls from native workers. Arguments remain lazy for
 * IO actions; only the ordinary strict primitives demand their operands. */
MlfValue *mlf_prim1(int64_t p, MlfValue *a) {
    switch (p) {
    case TEXT_TO_CHARS: case TEXT_FROM_CHARS: case CHAR_CODE: case CHAR_FROM_CODE:
    case USER_ERROR: case IO_ERROR: case IO_ERROR_STRING: case PRETTY_CALL_STACK:
    case IO_RETURN: case PUT_STR: case PUT_STR_LN: case PRINT_INT: case SHOW_INT: case READ_INT:
    case SQRT_DOUBLE: case INT_TO_DOUBLE: case LENGTH_INT_ARRAY: case LENGTH_DOUBLE_ARRAY:
    case LENGTH_BYTE_ARRAY: case BYTE_ARRAY_FROM_STRING:
    case STRING_LENGTH: case STRING_FROM_CODE: case READ_DOUBLE: case DOUBLE_TO_BITS: case DOUBLE_FROM_BITS:
    case PANIC: case READ_FILE: case FILE_EXISTS: case CANONICAL_PATH: case GET_ARG: case PUT_ERR: case EXIT_WITH:
    case GET_ENV: case UNSET_ENV: case LIST_DIRECTORY: case DIRECTORY_EXISTS: case FILE_DIGEST: case ACQUIRE_FILE_LOCK: case RELEASE_FILE_LOCK: case PROCESS_SUPERVISOR:
    case ASYNC_SCOPE_CLOSE: case ASYNC_SUBSCRIPTION_STATUS: case ASYNC_CANCEL_SUBSCRIPTION: case ASYNC_STEP:
    case ST_RETURN: case RUN_ST: case LENGTH_ST_ARRAY:
        return primitive_result((Primitive)p,a,NULL,NULL);
    default: fail("unary primitive arity mismatch");
    }
}
MlfValue *mlf_prim2(int64_t p, MlfValue *a, MlfValue *b) {
    switch (p) {
    case CATCH_IO_ERROR: case PUSH_CALL_STACK: case IO_ERROR_WITH_STACK:
    case IO_BIND: case CONCAT_STRING: case ADD_INT: case SUB_INT: case EQ_INT: case LT_INT: case EQ_STRING:
    case MUL_INT: case QUOT_INT: case REM_INT: case AND_INT:
    case ADD_DOUBLE: case SUB_DOUBLE: case MUL_DOUBLE: case DIV_DOUBLE: case EQ_DOUBLE: case LT_DOUBLE:
    case FORMAT_DOUBLE: case NEW_INT_ARRAY: case READ_INT_ARRAY: case NEW_DOUBLE_ARRAY: case READ_DOUBLE_ARRAY:
    case NEW_BYTE_ARRAY: case READ_BYTE_ARRAY: case READ_INT_TABLE:
    case STRING_CODE_AT: case MLF_COMPARE_STRING: case SEQ: case WRITE_FILE:
    case SET_ENV: case RUN_PROCESS:
    case ASYNC_SCOPE_NEW: case ASYNC_RESOLVE_COMPLETION: case ASYNC_SUBSCRIBE_COMPLETION: case ASYNC_ENQUEUE: case ASYNC_WAIT:
    case ST_BIND: case NEW_ST_ARRAY: case READ_ST_ARRAY:
        return primitive_result((Primitive)p,a,b,NULL);
    default: fail("binary primitive arity mismatch");
    }
}

MlfValue *mlf_prim3(int64_t p, MlfValue *a, MlfValue *b, MlfValue *c) {
    switch (p) {
    case IF_THEN_ELSE: case WRITE_INT_ARRAY: case WRITE_DOUBLE_ARRAY: case WRITE_BYTE_ARRAY: case PUT_BYTES: case WRITE_INT_TABLE: case STRING_SLICE:
    case ASYNC_NEW_COMPLETION: case ASYNC_READ_COMPLETION: case ASYNC_DELAY:
    case WRITE_ST_ARRAY:
        return primitive_result((Primitive)p,a,b,c);
    default: fail("ternary primitive arity mismatch");
    }
}

static void cleanup(void) {
    mlf_process_shutdown();
    mlf_process_binding_clear();
    while (active_stacks) {
        Stack *next = active_stacks->next;
        free(active_stacks->items);
        active_stacks = next;
    }
    native_roots = NULL;
}

void mlf_roots_enter(MlfRoots *frame, uint64_t count, MlfValue **values) {
    *frame = (MlfRoots){native_roots,count,values};
    native_roots = frame;
}

void mlf_roots_leave(MlfRoots *frame) { native_roots = frame->previous; }

/* BDWGC schedules collection at allocation sites. Keep the root array live
 * through this safepoint without running a second collector. */
void mlf_gc_check(uint64_t count, MlfValue **values) {
    (void)count;
    GC_reachable_here(values);
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

static const char *file_path(MlfValue *entry) {
    entry = expect(entry,STRING);
    if (memchr(entry->as.string.bytes,0,entry->as.string.length)) fail("file path contains NUL");
    return entry->as.string.bytes;
}

static MlfValue *read_file(MlfValue *entry) {
    const char *path = file_path(entry);
    FILE *file = fopen(path,"rb");
    if (!file) fail("IO error: file read failed");
    size_t length = 0, capacity = 4096;
    char *buffer = allocate(capacity);
    for (;;) {
        size_t n = fread(buffer + length,1,capacity - length,file);
        length += n;
        if (ferror(file)) { free(buffer); fclose(file); fail("IO error: file read failed"); }
        if (feof(file)) break;
        if (length == capacity) {
            if (capacity > SIZE_MAX / 2) { free(buffer); fclose(file); fail("string too large"); }
            capacity *= 2;
            char *next = realloc(buffer,capacity);
            if (!next) { free(buffer); fclose(file); fail("out of memory"); }
            buffer = next;
        }
    }
    if (fclose(file)) { free(buffer); fail("IO error: file read failed"); }
    if (!valid_utf8((unsigned char *)buffer,length)) { free(buffer); fail("IO error: invalid UTF-8 input"); }
    MlfValue *result = mlf_string(buffer,length);
    free(buffer);
    return result;
}

static void write_file(MlfValue *name, MlfValue *contents) {
    const char *path = file_path(name);
    contents = expect(contents,STRING);
    FILE *file = fopen(path,"wb");
    if (!file) fail("IO error: file write failed");
    int failed = fwrite(contents->as.string.bytes,1,contents->as.string.length,file) != contents->as.string.length;
    if (fclose(file)) failed = 1;
    if (failed) fail("IO error: file write failed");
}

static MlfValue *file_exists(MlfValue *name) {
    const char *path = file_path(name);
#if defined(_WIN32)
    DWORD attributes = mlf_windows_attributes(path);
    return mlf_boolean(attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY));
#else
    struct stat status;
    return mlf_boolean(stat(path,&status) == 0 && S_ISREG(status.st_mode));
#endif
}

static MlfValue *canonical_path(MlfValue *name) {
    const char *path = file_path(name);
    char *resolved = realpath(path,NULL);
    if (!resolved) fail("IO error: canonical path failed");
    size_t n = strlen(resolved);
    if (!valid_utf8((unsigned char *)resolved,n)) { free(resolved); fail("IO error: invalid UTF-8 input"); }
    MlfValue *result = mlf_string(resolved,n);
    free(resolved);
    return result;
}

static MlfValue *executable_path(void) {
    char *buffer = NULL;
#if defined(_WIN32)
    DWORD capacity = 256;
    for (;;) {
        wchar_t *wide = allocate((size_t)capacity * sizeof(wchar_t));
        DWORD size = GetModuleFileNameW(NULL,wide,capacity);
        if (!size) { free(wide); fail("IO error: executable path failed"); }
        if (size < capacity) { buffer=mlf_utf8(wide); free(wide); break; }
        free(wide);
        if (capacity > 32768) fail("IO error: executable path failed");
        capacity *= 2;
    }
    if (!buffer) fail("IO error: executable path failed");
#elif defined(__APPLE__)
    uint32_t capacity = 0;
    (void)_NSGetExecutablePath(NULL,&capacity);
    if (!capacity) fail("IO error: executable path failed");
    buffer = allocate(capacity);
    if (_NSGetExecutablePath(buffer,&capacity)) { free(buffer); fail("IO error: executable path failed"); }
#elif defined(__linux__)
    size_t capacity = 256;
    for (;;) {
        buffer = allocate(capacity + 1);
        ssize_t size = readlink("/proc/self/exe",buffer,capacity);
        if (size < 0) { free(buffer); fail("IO error: executable path failed"); }
        if ((size_t)size < capacity) { buffer[size] = 0; break; }
        free(buffer);
        if (capacity > SIZE_MAX / 2 - 1) fail("IO error: executable path failed");
        capacity *= 2;
    }
#else
    fail("IO error: executable path failed");
#endif
    char *resolved = realpath(buffer,NULL);
    free(buffer);
    if (!resolved) fail("IO error: executable path failed");
    size_t length = strlen(resolved);
    if (!valid_utf8((unsigned char *)resolved,length)) { free(resolved); fail("IO error: invalid UTF-8 input"); }
    MlfValue *result = mlf_string(resolved,length);
    free(resolved);
    return result;
}

#include "mlf_system.h"

static MlfValue *read_contents(void) {
    char *line = NULL;
    size_t line_capacity = 0, capacity = 4096, length = 0;
    char *buffer = allocate(capacity);
    for (;;) {
        ssize_t count = getline(&line,&line_capacity,stdin);
        if (count < 0) break;
        if ((size_t)count > SIZE_MAX - length) { free(buffer); free(line); fail("string too large"); }
        size_t required = length + (size_t)count;
        if (required > capacity) {
            while (capacity < required) {
                if (capacity > SIZE_MAX / 2) { capacity = required; break; }
                capacity *= 2;
            }
            char *next = realloc(buffer,capacity);
            if (!next) { free(buffer); free(line); fail("out of memory"); }
            buffer = next;
        }
        memcpy(buffer + length,line,(size_t)count);
        length = required;
    }
    free(line);
    if (!feof(stdin)) { free(buffer); fail("IO error: input failed"); }
    if (!valid_utf8((unsigned char *)buffer,length)) { free(buffer); fail("IO error: invalid UTF-8 input"); }
    MlfValue *result = mlf_string(buffer,length);
    free(buffer);
    return result;
}

static MlfValue *get_argument(MlfValue *entry) {
    entry = expect(entry,INTEGER);
    if (!argument_count) fail("argument index out of bounds");
    uint64_t i = bounded_integer(entry,(uint64_t)argument_count-1,"argument index out of bounds");
    const char *s = argument_values[i];
    size_t n = strlen(s);
    if (!valid_utf8((const unsigned char *)s,n)) fail("IO error: invalid UTF-8 input");
    return mlf_string(s,n);
}

static void write_error(MlfValue *entry) {
    entry = expect(entry,STRING);
    if (fwrite(entry->as.string.bytes,1,entry->as.string.length,stderr) != entry->as.string.length || fflush(stderr) == EOF)
        fail("IO error: output failed");
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
    result->as.byte_array.cells = allocate(result->as.byte_array.length ? result->as.byte_array.length : 1);
    if (length > 0) memcpy(result->as.byte_array.cells,buffer,(size_t)length);
    free(buffer);
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
            return mlf_constructor(1,0);
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
    return mlf_constructor(1,0);
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

MlfValue *mlf_st_new_array(MlfValue *size, MlfValue *initial) {
    size_t count = (size_t)bounded_integer(size,
        INT64_MAX / sizeof(MlfValue *),"invalid array length");
    if (!initial) fail("missing runtime value");
    MlfValue *result = value(ST_ARRAY);
    result->as.int_array.length = count;
    result->as.int_array.cells = NULL;
    result->as.int_array.cells = allocate(count ? count * sizeof(MlfValue *) : 1);
    for (size_t i = 0; i < count; ++i) result->as.int_array.cells[i] = initial;
    return result;
}

MlfValue *mlf_st_read_array(MlfValue *array, MlfValue *index) {
    array = expect(array,ST_ARRAY);
    size_t i = array_index(index,array->as.int_array.length);
    /* Snapshot now. A deferred lookup would observe a later write. */
    return array->as.int_array.cells[i];
}

MlfValue *mlf_st_write_array(MlfValue *array, MlfValue *index, MlfValue *entry) {
    array = expect(array,ST_ARRAY);
    size_t i = array_index(index,array->as.int_array.length);
    if (!entry) fail("missing runtime value");
    array->as.int_array.cells[i] = entry;
    return mlf_constructor(1,0);
}

MlfValue *mlf_st_length_array(MlfValue *array) {
    return small((int64_t)expect(array,ST_ARRAY)->as.int_array.length);
}

/* ST has no process-global current action or mutable store: each call owns
 * its continuation stack, while boxed arrays keep ordinary heap reachability.
 * Do not explicitly collect here. Pure generated frames do not register every
 * live root with the ordinary collector; BDWGC scans the native stack itself. */
static MlfValue *run_st(MlfValue *root) {
    Stack continuations = {0};
    MlfValue *current = root;
    for (;;) {
        MlfValue *operation = expect(current,ST_ACTION);
        MlfEnv *arguments = operation->as.primitive.arguments;
        MlfValue *result;
        switch (operation->as.primitive.identity) {
        case ST_BIND:
            push(&continuations, mlf_env_get(arguments,1));
            current = mlf_env_get(arguments,0);
            continue;
        case ST_RETURN:
            result = mlf_env_get(arguments,0);
            break;
        case NEW_ST_ARRAY:
            result = mlf_st_new_array(mlf_env_get(arguments,0),mlf_env_get(arguments,1));
            break;
        case READ_ST_ARRAY:
            result = mlf_st_read_array(mlf_env_get(arguments,0),mlf_env_get(arguments,1));
            break;
        case WRITE_ST_ARRAY:
            result = mlf_st_write_array(mlf_env_get(arguments,0),mlf_env_get(arguments,1),mlf_env_get(arguments,2));
            break;
        case LENGTH_ST_ARRAY:
            result = mlf_st_length_array(mlf_env_get(arguments,0));
            break;
        default: fail("invalid ST action");
        }
        if (!continuations.count) {
            release_stack(&continuations);
            return result;
        }
        MlfValue *next = continuations.items[--continuations.count];
        continuations.items[continuations.count] = NULL;
        current = mlf_application(next,result);
    }
}

MlfValue *mlf_execute_st_lazy(MlfValue *action) { return run_st(action); }

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
    return mlf_constructor(1,0);
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
    return mlf_constructor(1,0);
}

MlfValue *mlf_new_int_table(void) {
    MlfValue *result = value(SMALL_INT_TABLE);
    result->as.small_table = kh_init(mlf_tagged);
    if (!result->as.small_table) fail("out of memory");
    TABLE_CREATED(result);
    return result;
}

/* Shared monotonic metadata bridge for native and interpreted timers. Each
 * host sleep is bounded; the coordinator only sleeps with an empty ready queue. */
static uint64_t async_clock_ms(void) {
    return (uint64_t)(mlf_process_monotonic_seconds() * 1000.0);
}
static void async_pause_ms(uint32_t milliseconds) {
    if (milliseconds > 1000) fail("async host pause exceeds 1000 milliseconds");
#ifdef _WIN32
    Sleep(milliseconds);
#else
    struct timespec delay = { milliseconds / 1000, (long)(milliseconds % 1000) * 1000000 };
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
#endif
}
#include "mlf_process_binding.h"

/* Completion handles never contain user-visible numeric identities. */
static MlfValue *async_scope_value(MlfCompletionScope *scope) {
    MlfValue *result = value(ASYNC_SCOPE);
    result->as.async_scope = scope;
    return result;
}
static MlfValue *async_cell_value(MlfCompletion *cell) {
    MlfValue *result = value(COMPLETION);
    result->as.completion = cell;
    return result;
}
static MlfValue *async_subscription_value(MlfCompletionResume *resume,
                                         MlfCompletionStatus rejected) {
    if (rejected == MLF_COMPLETION_NO_MEMORY) fail("out of memory");
    MlfValue *result = value(ASYNC_SUBSCRIPTION);
    result->as.subscription.resume = resume;
    result->as.subscription.rejected = rejected;
    return result;
}
static MlfCompletionStatus async_subscription_status(MlfValue *entry) {
    entry = expect(entry, ASYNC_SUBSCRIPTION);
    if (entry->as.subscription.rejected != MLF_COMPLETION_OK)
        return entry->as.subscription.rejected;
    MlfCompletionResume *resume = entry->as.subscription.resume;
    if (resume->owner->closed) return MLF_COMPLETION_CLOSED;
    if (resume->state >= MLF_RESUME_CONSUMED) return MLF_COMPLETION_CONSUMED;
    return MLF_COMPLETION_OK;
}
/* Executor frames are distinct from user continuations. Both normal return
 * and typed-error unwind reset async dispatch state; arbitrary panic is fatal. */
static MlfValue *io_frame(Tag tag, MlfValue *payload) {
    MlfValue *frame = value(tag);
    frame->as.indirect = payload;
    return frame;
}

int32_t mlf_run(MlfValue *root, int64_t is_io) {
    if (!is_io) { (void)force(root); cleanup(); return 0; }
    Stack continuations = {0};
    MlfValue *current = root;
    for (;;) {
        MlfValue *operation = force(current);
        MlfValue *result;
        if (!immediate(operation) && operation->tag == ASYNC_ACTION) {
            MlfEnv *arguments = operation->as.primitive.arguments;
            MlfValue *a = mlf_env_get(arguments, 0);
            switch (operation->as.primitive.identity) {
            case ASYNC_SCOPE_NEW: {
                size_t cells = (size_t)bounded_integer(a, INT64_MAX / 8, "invalid async cell limit");
                size_t callbacks = (size_t)bounded_integer(mlf_env_get(arguments, 1), INT64_MAX / 8,
                                                          "invalid async callback limit");
                MlfCompletionScope *scope = mlf_completion_scope_new(cells, callbacks);
                if (!scope) fail("out of memory");
                result = async_scope_value(scope);
                break;
            }
            case ASYNC_SCOPE_CLOSE:
                mlf_completion_scope_close(expect(a, ASYNC_SCOPE)->as.async_scope);
                result = mlf_constructor(1,0);
                break;
            case ASYNC_NEW_COMPLETION: {
                MlfCompletionScope *scope = expect(a, ASYNC_SCOPE)->as.async_scope;
                MlfCompletion *cell = NULL;
                MlfCompletionStatus status = mlf_completion_new(scope, &cell);
                if (status == MLF_COMPLETION_NO_MEMORY) fail("out of memory");
                current = status == MLF_COMPLETION_OK
                    ? mlf_application(mlf_env_get(arguments, 1), async_cell_value(cell))
                    : mlf_env_get(arguments, 2);
                continue;
            }
            case ASYNC_RESOLVE_COMPLETION: {
                MlfCompletion *cell = expect(a, COMPLETION)->as.completion;
                result = small(mlf_completion_resolve(cell->owner, cell, mlf_env_get(arguments, 1)));
                break;
            }
            case ASYNC_READ_COMPLETION: {
                MlfCompletion *cell = expect(a, COMPLETION)->as.completion;
                MlfValue *payload = NULL;
                MlfCompletionStatus status = mlf_completion_read(cell->owner, cell, &payload);
                current = status == MLF_COMPLETION_OK
                    ? mlf_application(mlf_env_get(arguments, 1), payload)
                    : mlf_env_get(arguments, 2);
                continue;
            }
            case ASYNC_SUBSCRIBE_COMPLETION: {
                MlfCompletion *cell = expect(a, COMPLETION)->as.completion;
                MlfCompletionResume *resume = NULL;
                MlfCompletionStatus status = mlf_completion_subscribe(cell->owner, cell,
                                                        mlf_env_get(arguments, 1), &resume);
                result = async_subscription_value(resume, status);
                break;
            }
            case ASYNC_SUBSCRIPTION_STATUS:
                result = small(async_subscription_status(a));
                break;
            case ASYNC_CANCEL_SUBSCRIPTION: {
                MlfCompletionStatus status = async_subscription_status(a);
                if (status == MLF_COMPLETION_OK) {
                    MlfCompletionResume *resume = expect(a, ASYNC_SUBSCRIPTION)->as.subscription.resume;
                    status = mlf_completion_unsubscribe(resume->owner, resume);
                }
                result = small(status);
                break;
            }
            case ASYNC_ENQUEUE: {
                MlfCompletionScope *scope = expect(a, ASYNC_SCOPE)->as.async_scope;
                MlfCompletionResume *resume = NULL;
                MlfCompletionStatus status = mlf_completion_enqueue(scope,
                                                        mlf_env_get(arguments, 1), &resume);
                result = async_subscription_value(resume, status);
                break;
            }
            case ASYNC_DELAY: {
                MlfCompletionScope *scope = expect(a, ASYNC_SCOPE)->as.async_scope;
                uint64_t delay = bounded_integer(mlf_env_get(arguments, 1), UINT32_MAX,
                                                 "invalid async delay");
                MlfCompletionResume *resume = NULL;
                MlfCompletionStatus status = mlf_completion_delay(scope, async_clock_ms() + delay,
                                                          mlf_env_get(arguments, 2), &resume);
                result = async_subscription_value(resume, status);
                break;
            }
            case ASYNC_WAIT: {
                MlfCompletionScope *scope = expect(a, ASYNC_SCOPE)->as.async_scope;
                MlfValue *limit_value = expect(mlf_env_get(arguments, 1), INTEGER);
                int indefinite = small_integer(limit_value) && small_value(limit_value) == -1;
                uint64_t limit = indefinite ? 0 : bounded_integer(limit_value, UINT32_MAX,
                                                                  "invalid async wait");
                uint64_t start = async_clock_ms();
                for (;;) {
                    if (scope->closed) { result = small(MLF_COMPLETION_CLOSED); break; }
                    if (scope->dispatching) { result = small(MLF_COMPLETION_BUSY); break; }
                    uint64_t now = async_clock_ms();
                    mlf_completion_mature(scope, now);
                    if (scope->ready_head) { result = small(MLF_COMPLETION_OK); break; }
                    if (!scope->timer_head || (!indefinite && now - start >= limit)) {
                        result = small(MLF_COMPLETION_EMPTY); break;
                    }
                    uint64_t pause = scope->timer_head->deadline_ms - now;
                    if (!indefinite && pause > limit - (now - start)) pause = limit - (now - start);
                    async_pause_ms((uint32_t)(pause > 1000 ? 1000 : pause));
                }
                break;
            }
            case ASYNC_STEP: {
                MlfCompletionScope *scope = expect(a, ASYNC_SCOPE)->as.async_scope;
                if (scope->closed) { result = small(MLF_COMPLETION_CLOSED); break; }
                if (scope->dispatching) { result = small(MLF_COMPLETION_BUSY); break; }
                mlf_completion_mature(scope, async_clock_ms());
                MlfCompletionResume *resume = NULL;
                MlfCompletionStatus status = mlf_completion_dequeue(scope, &resume);
                if (status != MLF_COMPLETION_OK) { result = small(status); break; }
                int is_action = resume->is_action;
                MlfValue *callback = NULL, *payload = NULL;
                status = mlf_completion_take(scope, resume, &callback, &payload);
                if (status != MLF_COMPLETION_OK) { result = small(status); break; }
                scope->dispatching = 1;
                push(&continuations, io_frame(IO_ASYNC_FINISH_FRAME, a));
                current = is_action ? callback : mlf_application(callback, payload);
                continue;
            }
            default: fail("invalid async action");
            }
        } else
        if (!immediate(operation) && operation->tag == NATIVE_IO) {
            current = operation->as.closure.code(operation->as.closure.env,NULL);
            continue;
        }
        else if (!immediate(operation) && operation->tag == PUT_BYTES_ACTION) {
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
        case CATCH_IO_ERROR:
            push(&continuations, io_frame(IO_CATCH_FRAME, operation->as.action.second));
            current = operation->as.action.first;
            continue;
        case IO_ERROR: case IO_ERROR_WITH_STACK: {
            MlfValue *error = expect(operation->as.action.first, IO_ERROR_VALUE);
            MlfValue *stack = operation->as.action.operation == IO_ERROR_WITH_STACK
                ? operation->as.action.second : NULL;
            MlfValue *contexts = mlf_constructor(SOURCE_NIL, 0);
            MlfValue *handler = NULL;
            while (continuations.count) {
                MlfValue *frame = continuations.items[--continuations.count];
                continuations.items[continuations.count] = NULL;
                if (!immediate(frame) && frame->tag == IO_ASYNC_FINISH_FRAME)
                    expect(frame->as.indirect, ASYNC_SCOPE)->as.async_scope->dispatching = 0;
                else if (!immediate(frame) && frame->tag == IO_HANDLER_FRAME)
                    contexts = mlf_constructor2(SOURCE_CONS, frame->as.indirect, contexts);
                else if (!immediate(frame) && frame->tag == IO_CATCH_FRAME) {
                    handler = frame->as.indirect;
                    break;
                }
            }
            if (!handler) uncaught_io_error(error, stack, contexts);
            /* A typed catch strips the old context. Its handler establishes
             * a fresh, dynamically scoped annotation; normal return removes it. */
            push(&continuations, io_frame(IO_HANDLER_FRAME, error));
            current = mlf_application(handler, error);
            continue;
        }
        case IO_BIND:
            push(&continuations, operation->as.action.second);
            current = operation->as.action.first;
            continue;
        case IO_RETURN: result = operation->as.action.first; break;
        case GET_LINE: result = read_line(); break;
        case READ_FILE: result = read_file(operation->as.action.first); break;
        case WRITE_FILE:
            write_file(operation->as.action.first,operation->as.action.second);
            result = mlf_constructor(1,0); break;
        case FILE_EXISTS: result = file_exists(operation->as.action.first); break;
        case CANONICAL_PATH: result = canonical_path(operation->as.action.first); break;
        case GET_ARG_COUNT: result = small(argument_count); break;
        case GET_ARG: result = get_argument(operation->as.action.first); break;
        case GET_EXECUTABLE_PATH: result = executable_path(); break;
        case GET_CONTENTS: result = read_contents(); break;
        case GET_ENV: result = os_getEnv(operation->as.action.first); break;
        case SET_ENV: result = os_setEnv(operation->as.action.first,operation->as.action.second); break;
        case UNSET_ENV: result = os_unsetEnv(operation->as.action.first); break;
        case RUN_PROCESS: result = os_runProcess(operation->as.action.first,operation->as.action.second); break;
        case LIST_DIRECTORY: result = os_listDirectory(operation->as.action.first); break;
        case DIRECTORY_EXISTS: result = os_directoryExists(operation->as.action.first); break;
        case FILE_DIGEST: result = os_fileDigest(operation->as.action.first); break;
        case ACQUIRE_FILE_LOCK: result = os_acquireFileLock(operation->as.action.first); break;
        case RELEASE_FILE_LOCK: result = os_releaseFileLock(operation->as.action.first); break;
        case PROCESS_SUPERVISOR: result = mlf_process_request(operation->as.action.first); break;

        case PUT_ERR:
            write_error(operation->as.action.first);
            result = mlf_constructor(1,0); break;
        case EXIT_WITH: {
            int status = (int)bounded_integer(operation->as.action.first,255,"exit status must be between 0 and 255");
            cleanup(); exit(status);
        }
        case GET_BYTE_LINE: result = mlf_get_byte_line(); break;
        case NEW_INT_TABLE: result = mlf_new_int_table(); break;
        case READ_INT_TABLE:
            result = mlf_read_int_table(operation->as.action.first,operation->as.action.second); break;
        case PUT_STR: case PUT_STR_LN:
            write_string(operation->as.action.first, operation->as.action.operation == PUT_STR_LN);
            result = mlf_constructor(1,0); break;
        case PRINT_INT:
            write_string(show_integer(operation->as.action.first), 1);
            result = mlf_constructor(1,0); break;
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
        MlfValue *next = NULL;
        while (continuations.count) {
            MlfValue *frame = continuations.items[--continuations.count];
            continuations.items[continuations.count] = NULL;
            if (!immediate(frame) && (frame->tag == IO_CATCH_FRAME || frame->tag == IO_HANDLER_FRAME)) continue;
            if (!immediate(frame) && frame->tag == IO_ASYNC_FINISH_FRAME) {
                expect(frame->as.indirect, ASYNC_SCOPE)->as.async_scope->dispatching = 0;
                result = small(MLF_COMPLETION_OK);
                continue;
            }
            next = frame;
            break;
        }
        if (!next) break;
        current = mlf_application(next, result);
    }
    release_stack(&continuations);
    cleanup();
    return 0;
}
