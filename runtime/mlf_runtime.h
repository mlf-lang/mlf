#if !defined(MLF_RUNTIME_H)
#define MLF_RUNTIME_H

#include <stdint.h>

/* Compact 64-bit BDWGC ABI. Low bits encode immediate integers, booleans
 * and nullary constructors. Heap value tags start at byte 0; payloads at
 * byte 8, packed fields at byte 16, wide fields at byte 24 and environment
 * slots at byte 8. The runtime requires GMP and BDWGC. Old standard-layout
 * LLVM/object files must be regenerated; their ABI guard is not exported. */
/* Boundary v3: true unit is constructor tag1, tuple arities2..64, source
 * stack frames7/evidence8. No earlier ABI guard is exported: old generated
 * objects must use their frozen old runtime, not silently cross this boundary. */
void mlf_require_haskell_boundary_v3_abi(void);

typedef struct MlfValue MlfValue;
typedef struct MlfEnv MlfEnv;
typedef MlfValue *(*MlfCode)(MlfEnv *, MlfValue *);
typedef struct MlfRoots {
    struct MlfRoots *previous;
    uint64_t count;
    MlfValue **values;
} MlfRoots;

void mlf_roots_enter(MlfRoots *frame, uint64_t count, MlfValue **values);
void mlf_roots_leave(MlfRoots *frame);
void mlf_gc_check(uint64_t count, MlfValue **values);
MlfValue *mlf_get_byte_line(void);
MlfValue *mlf_new_array(int64_t primitive, MlfValue *size, MlfValue *initial);
MlfValue *mlf_bytes_from_string(MlfValue *text);
MlfValue *mlf_put_bytes(MlfValue *array, MlfValue *offset, MlfValue *count);
MlfValue *mlf_new_int_table(void);

MlfEnv *mlf_env_new(uint64_t count);
void mlf_env_set(MlfEnv *env, uint64_t index, MlfValue *value);
MlfValue *mlf_env_get(MlfEnv *env, uint64_t index);
/* Private captures for a single-entry callback. The caller initializes every
 * slot before publishing the thunk. The callback loads, then clears its slots
 * before evaluating its body. Environment pointer: byte 16. */
MlfValue *mlf_thunk_new(MlfCode code, uint64_t count);
MlfValue *mlf_thunk(MlfCode code, MlfEnv *env);
MlfValue *mlf_closure(MlfCode code, MlfEnv *env);
MlfValue *mlf_native_io(MlfCode code, MlfEnv *env);
MlfValue *mlf_peek(MlfValue *value);
_Noreturn void mlf_bounds_failure(void);
MlfValue *mlf_application(MlfValue *function, MlfValue *argument);
MlfValue *mlf_hole(void);
void mlf_fill(MlfValue *hole, MlfValue *value);
MlfValue *mlf_integer(const char *decimal);
MlfValue *mlf_double(double value);
double mlf_int_to_double(MlfValue *value);
uint8_t mlf_byte(MlfValue *value);
MlfValue *mlf_boolean(int64_t boolean);
MlfValue *mlf_string(const char *bytes, uint64_t length);
MlfValue *mlf_primitive(int64_t primitive);
MlfValue *mlf_constructor(int64_t tag, int64_t arity);
MlfValue *mlf_constructor1(int64_t tag, MlfValue *a);
MlfValue *mlf_constructor2(int64_t tag, MlfValue *a, MlfValue *b);
/* Construct a saturated data value from a fully initialized environment.
 * Fields remain lazy. The caller must not write the environment afterwards. */
MlfValue *mlf_constructor_fields(int64_t tag, MlfEnv *fields);
/* Allocate a saturated constructor of arity >= 3 with cleared field slots.
 * Generated code initializes every slot through the documented layout before
 * exposing the value. Field initialization must not evaluate the fields. */
MlfValue *mlf_constructor_new(int64_t tag, uint64_t count);
MlfValue *mlf_force(MlfValue *value);
MlfValue *mlf_add_int(MlfValue *a, MlfValue *b);
MlfValue *mlf_sub_int(MlfValue *a, MlfValue *b);
MlfValue *mlf_eq_int(MlfValue *a, MlfValue *b);
MlfValue *mlf_lt_int(MlfValue *a, MlfValue *b);
int64_t mlf_truth(MlfValue *value);
MlfValue *mlf_read_int_table(MlfValue *table, MlfValue *key);
MlfValue *mlf_write_int_table(MlfValue *table, MlfValue *key, MlfValue *entry);
/* Native-region ABI: all three operands have checked types and are values. */
MlfValue *mlf_add_int_table(MlfValue *table, MlfValue *key, MlfValue *delta);
/* Execution-only ST helpers. Array elements and executor results stay lazy;
 * the enclosing checked runST expression forces only its final result. These
 * functions never perform the ordinary collector's explicit IO-boundary GC. */
MlfValue *mlf_execute_st_lazy(MlfValue *action);
MlfValue *mlf_st_new_array(MlfValue *size, MlfValue *initial);
MlfValue *mlf_st_read_array(MlfValue *array, MlfValue *index);
MlfValue *mlf_st_write_array(MlfValue *array, MlfValue *index, MlfValue *entry);
MlfValue *mlf_st_length_array(MlfValue *array);
MlfValue *mlf_prim1(int64_t primitive, MlfValue *a);
MlfValue *mlf_prim2(int64_t primitive, MlfValue *a, MlfValue *b);
MlfValue *mlf_prim3(int64_t primitive, MlfValue *a, MlfValue *b, MlfValue *c);
int64_t mlf_tag(MlfValue *value);
MlfValue *mlf_field(MlfValue *value, uint64_t index);
_Noreturn void mlf_match_failure(void);
void mlf_set_args(int32_t argc, char **argv);
int32_t mlf_run(MlfValue *root, int64_t is_io);

/* Reserved for generated small captured thunks. These are the runtime's own
 * traced batches, indexed by requested bytes / 16; debug heads stay empty. */
extern void *mlf_compact_pending[17];
/* Reserved for generated constructor allocation. The caller initializes the
 * already-cleared object immediately; the heads are collector roots. */
extern void *mlf_constructor_pending[33];
void *mlf_constructor_allocate(int64_t identity, uint64_t count);

#endif
