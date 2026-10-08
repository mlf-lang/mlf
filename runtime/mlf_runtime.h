#ifndef MLF_RUNTIME_H
#define MLF_RUNTIME_H

#include <stdint.h>

/* 64-bit ABI used by MLF.LLVM.Codegen. Low bits: odd = signed 63-bit
 * integer, 2/6 = false/true, (tag << 3)|4 = nullary constructor. Heap
 * pointers are aligned to 8 bytes. Evaluated constructors store their tag
 * at byte 24; fully applied unary/binary constructors have inline fields
 * at byte 32. Static assertions in the implementation guard these offsets. */
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
MlfValue *mlf_prim1(int64_t primitive, MlfValue *a);
MlfValue *mlf_prim2(int64_t primitive, MlfValue *a, MlfValue *b);
MlfValue *mlf_prim3(int64_t primitive, MlfValue *a, MlfValue *b, MlfValue *c);
int64_t mlf_tag(MlfValue *value);
MlfValue *mlf_field(MlfValue *value, uint64_t index);
_Noreturn void mlf_match_failure(void);
int32_t mlf_run(MlfValue *root, int64_t is_io);

#endif
