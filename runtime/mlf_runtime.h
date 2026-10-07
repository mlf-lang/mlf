#ifndef MLF_RUNTIME_H
#define MLF_RUNTIME_H

#include <stdint.h>

/* ABI used by MLF.LLVM. Generated code never depends on object layouts. */
typedef struct MlfValue MlfValue;
typedef struct MlfEnv MlfEnv;
typedef MlfValue *(*MlfCode)(MlfEnv *, MlfValue *);

MlfEnv *mlf_env_new(uint64_t count);
void mlf_env_set(MlfEnv *env, uint64_t index, MlfValue *value);
MlfValue *mlf_env_get(MlfEnv *env, uint64_t index);
MlfValue *mlf_thunk(MlfCode code, MlfEnv *env);
MlfValue *mlf_closure(MlfCode code, MlfEnv *env);
MlfValue *mlf_application(MlfValue *function, MlfValue *argument);
MlfValue *mlf_hole(void);
void mlf_fill(MlfValue *hole, MlfValue *value);
MlfValue *mlf_integer(const char *decimal);
MlfValue *mlf_boolean(int64_t boolean);
MlfValue *mlf_string(const char *bytes, uint64_t length);
MlfValue *mlf_primitive(int64_t primitive);
MlfValue *mlf_constructor(int64_t tag, int64_t arity);
int64_t mlf_tag(MlfValue *value);
MlfValue *mlf_field(MlfValue *value, uint64_t index);
_Noreturn void mlf_match_failure(void);
int32_t mlf_run(MlfValue *root, int64_t is_io);

#endif
