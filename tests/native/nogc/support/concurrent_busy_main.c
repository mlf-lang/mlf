#include "../../../../runtime/mlf_nogc_entry.h"
int mlf_ng0_fixture_concurrent_busy(MlfNg0Limits,uint64_t);
int main(void) {
    const MlfNg0Limits limits={MLF_NG0_ABI,65536,128};
    return mlf_ng0_fixture_concurrent_busy(limits,UINT64_C(1000000));
}
