#ifndef MLF_NOGC_ENTRY_H
#define MLF_NOGC_ENTRY_H
#include <stddef.h>
#include <stdint.h>
#if defined(__GNUC__) || defined(__clang__)
#define MLF_NG0_PRIVATE __attribute__((visibility("hidden")))
#else
#error "Restricted native ABI requires qualified hidden symbol visibility"
#endif
#define MLF_NG0_ABI UINT64_C(0x4e4730454e545230)
typedef enum {
    MLF_NG0_OK = 0, MLF_NG0_INVALID_CONFIG, MLF_NG0_BUSY,
    MLF_NG0_HOST_ALLOCATION, MLF_NG0_ARENA_LIMIT, MLF_NG0_DEPTH_LIMIT,
    MLF_NG0_BLACKHOLE, MLF_NG0_INVALID_PRIMITIVE, MLF_NG0_INVALID_APPLICATION,
    MLF_NG0_INVALID_VALUE, MLF_NG0_MATCH_FAILURE, MLF_NG0_INTERNAL_CONTRACT
} MlfNg0Status;
typedef struct { uint64_t abi, capacity, depth_limit; } MlfNg0Limits;
/* No language pointers escape. peak_rss_available is zero: a later external
 * observer must supply measured peak RSS, not infer it from arena use. */
typedef struct {
    uint64_t abi;
    MlfNg0Status status;
    int64_t value;
    uint64_t requested_capacity, used_high_water, padding_bytes, context_bytes;
    uint64_t host_allocation_calls, host_requested_bytes, depth_high_water;
    uint64_t retained_bytes, peak_rss_bytes, peak_rss_available;
} MlfNg0Result;
MlfNg0Status mlf_ng0_eval(const MlfNg0Limits *limits, MlfNg0Result *out);
/* Internal compiler ABI. Not a host extension or callback registration API.
 * Only the closed generated link unit may supply any of these pointers. */
typedef struct MlfNg0Value MlfNg0Value;
typedef struct MlfNg0Env MlfNg0Env;
typedef MlfNg0Value *(*MlfNg0Code)(MlfNg0Env *, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_guest_entry(void);
MLF_NG0_PRIVATE void mlf_ng0_require_entry_region_v0(void);
MLF_NG0_PRIVATE void mlf_ng0_depth_enter(void);
MLF_NG0_PRIVATE void mlf_ng0_depth_leave(void);
MLF_NG0_PRIVATE _Noreturn void mlf_ng0_fault(int32_t status);
MLF_NG0_PRIVATE _Noreturn void mlf_ng0_match_failure(void);
MLF_NG0_PRIVATE MlfNg0Env *mlf_ng0_env_new(uint64_t count);
MLF_NG0_PRIVATE void mlf_ng0_env_set(MlfNg0Env *, uint64_t, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_env_get(MlfNg0Env *, uint64_t);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_thunk_new(MlfNg0Code, uint64_t);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_thunk(MlfNg0Code, MlfNg0Env *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_closure(MlfNg0Code, MlfNg0Env *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_application(MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_hole(void);
MLF_NG0_PRIVATE void mlf_ng0_fill(MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_integer(const char *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_boolean(int64_t);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_primitive(int64_t);
MLF_NG0_PRIVATE void *mlf_ng0_constructor_allocate(int64_t, uint64_t);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_constructor(int64_t, int64_t);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_constructor1(int64_t, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_constructor2(int64_t, MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_constructor_fields(int64_t, MlfNg0Env *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_force(MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_peek(MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_add_int(MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE int64_t mlf_ng0_truth(MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_prim2(int64_t, MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_prim3(int64_t, MlfNg0Value *, MlfNg0Value *, MlfNg0Value *);
MLF_NG0_PRIVATE int64_t mlf_ng0_tag(MlfNg0Value *);
MLF_NG0_PRIVATE MlfNg0Value *mlf_ng0_field(MlfNg0Value *, uint64_t);
#endif
