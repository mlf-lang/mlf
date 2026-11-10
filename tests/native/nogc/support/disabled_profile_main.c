/* Link only with a separately built, default-disabled runtime. A qualified
 * runtime with valid positive ceilings must fail this test. */
#include "../../../../runtime/mlf_nogc_entry.h"
static unsigned guest_calls;
MlfNg0Value *mlf_ng0_guest_entry(void) {
    ++guest_calls;
    return mlf_ng0_integer("7");
}
static int refused(const MlfNg0Limits *limits) {
    MlfNg0Result result={0};
    MlfNg0Status status=mlf_ng0_eval(limits,&result);
    return status==MLF_NG0_INVALID_CONFIG &&
        result.abi==MLF_NG0_ABI && result.status==MLF_NG0_INVALID_CONFIG &&
        result.requested_capacity==(limits ? limits->capacity : 0) &&
        result.value==0 && result.used_high_water==0 && result.padding_bytes==0 &&
        result.context_bytes==0 && result.host_allocation_calls==0 &&
        result.host_requested_bytes==0 && result.depth_high_water==0 &&
        result.retained_bytes==0 && result.peak_rss_bytes==0 &&
        result.peak_rss_available==0 && guest_calls==0;
}
int main(void) {
    const MlfNg0Limits valid={MLF_NG0_ABI,65536,128};
    const MlfNg0Limits wrong_abi={0,65536,128};
    const MlfNg0Limits zero_capacity={MLF_NG0_ABI,0,128};
    const MlfNg0Limits zero_depth={MLF_NG0_ABI,65536,0};
    if (!refused(&valid) || !refused(&wrong_abi) || !refused(&zero_capacity) ||
        !refused(&zero_depth) || !refused(0) ||
        mlf_ng0_eval(&valid,0)!=MLF_NG0_INVALID_CONFIG || guest_calls) return 1;
    return refused(&valid) ? 0 : 1;
}
