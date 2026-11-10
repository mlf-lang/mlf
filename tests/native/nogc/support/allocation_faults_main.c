#include "../../../../runtime/mlf_nogc_entry.h"
unsigned mlf_ng0_fixture_allocation_faults(MlfNg0Limits);
int main(void) {
    const MlfNg0Limits limits={MLF_NG0_ABI,65536,128};
    return mlf_ng0_fixture_allocation_faults(limits)!=0 ? 1 : 0;
}
