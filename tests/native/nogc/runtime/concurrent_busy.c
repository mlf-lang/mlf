/* Alternative test guest: not combined with runtime_contract.c.
 * Requires C11 threads and an external deadline. The positive spin budget
 * is supplied by the caller and is not a production resource policy. */
#include "../../../../runtime/mlf_nogc_entry.h"
#include <stdatomic.h>
#include <threads.h>
static atomic_int entered, release_guest;
static uint64_t spin_budget;
static MlfNg0Limits limits;
static MlfNg0Result owner_result;
MlfNg0Value *mlf_ng0_guest_entry(void) {
    mlf_ng0_depth_enter();
    atomic_store_explicit(&entered,1,memory_order_release);
    uint64_t spins=0;
    while (!atomic_load_explicit(&release_guest,memory_order_acquire)) {
        if (++spins>=spin_budget) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        thrd_yield(); /* TEST ONLY; forbidden in production guest closure. */
    }
    MlfNg0Value *v=mlf_ng0_integer("7"); mlf_ng0_depth_leave(); return v;
}
static int owner(void *unused) {
    (void)unused; (void)mlf_ng0_eval(&limits,&owner_result); return 0;
}
/* Return0 means fixture observations match, 1 mismatch, 2 inconclusive setup
 * or spin-budget exhaustion. A killed external deadline is never a pass. */
int mlf_ng0_fixture_concurrent_busy(MlfNg0Limits l,uint64_t budget) {
    if (!budget) return 2;
    limits=l; spin_budget=budget;
    atomic_store(&entered,0); atomic_store(&release_guest,0);
    thrd_t worker;
    if (thrd_create(&worker,owner,0)!=thrd_success) return 2;
    uint64_t spins=0;
    while (!atomic_load_explicit(&entered,memory_order_acquire) && ++spins<budget) thrd_yield();
    MlfNg0Result competing={0};
    int observed=atomic_load_explicit(&entered,memory_order_acquire);
    if (observed) (void)mlf_ng0_eval(&l,&competing);
    atomic_store_explicit(&release_guest,1,memory_order_release);
    int ignored;
    if (thrd_join(worker,&ignored)!=thrd_success) return 2;
    if (!observed || owner_result.status!=MLF_NG0_OK) return 2;
    if (competing.status!=MLF_NG0_BUSY || competing.host_allocation_calls || competing.retained_bytes ||
        owner_result.value!=7 || owner_result.retained_bytes) return 1;
    MlfNg0Result repeated;
    return mlf_ng0_eval(&l,&repeated)!=MLF_NG0_OK || repeated.value!=7 || repeated.retained_bytes;
}
