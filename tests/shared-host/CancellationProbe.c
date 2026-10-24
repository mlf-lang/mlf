#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <time.h>
#include <stdatomic.h>
static void *tracked;
static _Atomic int ready, freed;
extern int __real_mlf_ghc_host(int,const char *,size_t,const char *,size_t,int64_t,char **,size_t *,int64_t *);
extern void __real_free(void *);
int __wrap_mlf_ghc_host(int op,const char *a,size_t na,const char *b,size_t nb,int64_t n,char **out,size_t *len,int64_t *result) {
  int status=__real_mlf_ghc_host(op,a,na,b,nb,n,out,len,result);
  tracked=*out;
  atomic_store(&ready,1);
  struct timespec delay={0,200000000};
  nanosleep(&delay,0);
  return status;
}
void __wrap_free(void *p) {
  if(p && p==tracked) atomic_store(&freed,1);
  __real_free(p);
}
int mlf_probe_ready(void) { return atomic_load(&ready); }
int mlf_probe_freed(void) { return atomic_load(&freed); }
