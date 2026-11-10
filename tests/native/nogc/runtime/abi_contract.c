/* Compile-only checks for the runtime C signatures and scalar result layout.
 * No guest and no executable main. This does not test generated LLVM. */
#include "../../../../runtime/mlf_nogc_entry.h"
#define ABI_FN(fn, type) _Static_assert(_Generic(&(fn), type: 1, default: 0), #fn " signature")
ABI_FN(mlf_ng0_eval, MlfNg0Status (*)(const MlfNg0Limits *, MlfNg0Result *));
ABI_FN(mlf_ng0_guest_entry, MlfNg0Value *(*)(void));
ABI_FN(mlf_ng0_env_new, MlfNg0Env *(*)(uint64_t));
ABI_FN(mlf_ng0_env_get, MlfNg0Value *(*)(MlfNg0Env *, uint64_t));
ABI_FN(mlf_ng0_env_set, void (*)(MlfNg0Env *, uint64_t, MlfNg0Value *));
ABI_FN(mlf_ng0_thunk_new, MlfNg0Value *(*)(MlfNg0Code, uint64_t));
ABI_FN(mlf_ng0_thunk, MlfNg0Value *(*)(MlfNg0Code, MlfNg0Env *));
ABI_FN(mlf_ng0_closure, MlfNg0Value *(*)(MlfNg0Code, MlfNg0Env *));
ABI_FN(mlf_ng0_application, MlfNg0Value *(*)(MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_add_int, MlfNg0Value *(*)(MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_force, MlfNg0Value *(*)(MlfNg0Value *));
ABI_FN(mlf_ng0_peek, MlfNg0Value *(*)(MlfNg0Value *));
ABI_FN(mlf_ng0_hole, MlfNg0Value *(*)(void));
ABI_FN(mlf_ng0_fill, void (*)(MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_boolean, MlfNg0Value *(*)(int64_t));
ABI_FN(mlf_ng0_tag, int64_t (*)(MlfNg0Value *));
ABI_FN(mlf_ng0_fault, void (*)(int32_t));
ABI_FN(mlf_ng0_integer, MlfNg0Value *(*)(const char *));
ABI_FN(mlf_ng0_primitive, MlfNg0Value *(*)(int64_t));
ABI_FN(mlf_ng0_constructor_allocate, void *(*)(int64_t, uint64_t));
ABI_FN(mlf_ng0_constructor, MlfNg0Value *(*)(int64_t, int64_t));
ABI_FN(mlf_ng0_constructor1, MlfNg0Value *(*)(int64_t, MlfNg0Value *));
ABI_FN(mlf_ng0_constructor2, MlfNg0Value *(*)(int64_t, MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_constructor_fields, MlfNg0Value *(*)(int64_t, MlfNg0Env *));
ABI_FN(mlf_ng0_prim2, MlfNg0Value *(*)(int64_t, MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_prim3, MlfNg0Value *(*)(int64_t, MlfNg0Value *, MlfNg0Value *, MlfNg0Value *));
ABI_FN(mlf_ng0_truth, int64_t (*)(MlfNg0Value *));
ABI_FN(mlf_ng0_field, MlfNg0Value *(*)(MlfNg0Value *, uint64_t));
ABI_FN(mlf_ng0_depth_enter, void (*)(void));
ABI_FN(mlf_ng0_depth_leave, void (*)(void));
ABI_FN(mlf_ng0_require_entry_region_v0, void (*)(void));
ABI_FN(mlf_ng0_match_failure, void (*)(void));
_Static_assert(sizeof(MlfNg0Limits)==24 && offsetof(MlfNg0Limits,depth_limit)==16, "limits ABI");
_Static_assert(sizeof(MlfNg0Result)==104 && offsetof(MlfNg0Result,status)==8 &&
    offsetof(MlfNg0Result,value)==16 && offsetof(MlfNg0Result,requested_capacity)==24, "scalar result ABI");
#undef ABI_FN
