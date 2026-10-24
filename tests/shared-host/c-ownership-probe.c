#define _XOPEN_SOURCE 700
/* Fault-inject only the adapter's calloc; no production source is modified. */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static unsigned allocations, fail_at, outstanding;
static void *probe_calloc(size_t n,size_t size) {
    if (++allocations==fail_at) return NULL;
    void *p=calloc(n,size); if(p) ++outstanding; return p;
}
static void probe_free(void *p) { if(p) --outstanding; free(p); }
#define calloc probe_calloc
#define free probe_free
#include "../../host/ghc/cbits/host.c"
#undef calloc
#undef free
int main(void) {
    /* getenv returns a newly allocated transport wrapper and byte buffer.
       Fail buffer allocation after the wrapper was allocated successfully. */
    fail_at=2;
    char *out=NULL; size_t length=0; int64_t number=0;
    int status=mlf_ghc_host(0,"MLF_HOST_REVIEW_NO_SUCH_VAR",27,"",0,0,&out,&length,&number);
    printf("status=%d output=%.*s outstanding_adapter_allocations=%u\n",status,(int)length,out?out:"",outstanding);
    free(out); /* Error output uses malloc, not tracked calloc. */
    return outstanding ? 1 : 0;
}
