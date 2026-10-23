/* Byte/integer-only FFI adapter. These private transport objects never contain
 * a Haskell or MLF heap pointer. Reuse the native OS and process protocol code
 * without linking mlf_runtime.c, GMP allocator hooks, or BDWGC. */
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <time.h>
#include <setjmp.h>
#include "mlf_process_supervisor.h"

typedef struct MlfValue {
  union { struct { const char *bytes; size_t length; } string; int64_t integer; } as;
} MlfValue;
#define STRING 1
static jmp_buf host_failure;
static const char *host_error;
static _Noreturn void fail(const char *message) { host_error=message; longjmp(host_failure,1); }
static void *allocate(size_t size) { void *p=calloc(size ? size : 1,1); if (!p) fail("out of memory"); return p; }
static MlfValue *expect(MlfValue *v, int tag) { (void)tag; return v; }
static MlfValue *mlf_string(const char *bytes, uint64_t n) {
  MlfValue *v=allocate(sizeof(*v)); char *copy=allocate(n+1);
  memcpy(copy,bytes,n); v->as.string.bytes=copy; v->as.string.length=n; return v;
}
static MlfValue *small(int64_t n) { MlfValue *v=allocate(sizeof(*v)); v->as.integer=n; return v; }
static MlfValue *mlf_boolean(int b) { return small(b); }
static MlfValue *mlf_constructor(int tag,int arity) { (void)tag; (void)arity; return small(0); }
static uint64_t bounded_integer(MlfValue *v,uint64_t maximum,const char *message) {
  if (v->as.integer<0 || (uint64_t)v->as.integer>maximum) fail(message);
  return (uint64_t)v->as.integer;
}
static const char *file_path(MlfValue *v) {
  if (memchr(v->as.string.bytes,0,v->as.string.length)) fail("file path contains NUL");
  return v->as.string.bytes;
}
static int valid_utf8(const unsigned char *bytes, size_t length) {
    for (size_t i = 0; i < length;) {
        unsigned c = bytes[i++], remaining = 0, minimum = 0;
        if (c < 0x80) continue;
        if (c >= 0xc2 && c <= 0xdf) { c &= 0x1f; remaining = 1; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { c &= 0x0f; remaining = 2; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { c &= 7; remaining = 3; minimum = 0x10000; }
        else return 0;
        if (remaining > length - i) return 0;
        while (remaining--) {
            unsigned next = bytes[i++];
            if ((next & 0xc0) != 0x80) return 0;
            c = (c << 6) | (next & 0x3f);
        }
        if (c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) return 0;
    }
    return 1;
}

#include "mlf_system.h"
static uint64_t async_clock_ms(void) { return (uint64_t)(mlf_process_monotonic_seconds()*1000.0); }
static void async_pause_ms(uint32_t ms) {
  if (ms>1000) fail("async host pause exceeds 1000 milliseconds");
  struct timespec delay={ms/1000,(long)(ms%1000)*1000000};
  while (nanosleep(&delay,&delay) && errno==EINTR) {}
}
#include "mlf_process_binding.h"

/* Return an owned byte buffer, including error text when status is nonzero.
 * A call is serialized by the Haskell adapter. The caller always frees output. */
int mlf_ghc_host(int operation,const char *a,size_t na,const char *b,size_t nb,
                 int64_t number,char **output,size_t *length,int64_t *result) {
  *output=NULL; *length=0; *result=0;
  if (setjmp(host_failure)) {
    *length=strlen(host_error); *output=malloc(*length+1);
    if (*output) memcpy(*output,host_error,*length+1);
    return 1;
  }
  MlfValue first={0},second={0},integer={0};
  first.as.string.bytes=a; first.as.string.length=na;
  second.as.string.bytes=b; second.as.string.length=nb;
  integer.as.integer=number;
  MlfValue *value=NULL; int text=0;
  switch(operation) {
    case 0: value=os_getEnv(&first);text=1;break;
    case 1: value=os_setEnv(&first,&second);break;
    case 2: value=os_unsetEnv(&first);break;
    case 3: value=os_directoryExists(&first);break;
    case 4: value=os_listDirectory(&first);text=1;break;
    case 5: value=os_acquireFileLock(&first);break;
    case 6: value=os_releaseFileLock(&integer);break;
    case 7: value=os_runProcess(&first,&second);break;
    case 8: value=os_fileDigest(&first);text=1;break;
    case 9: value=mlf_process_request(&first);text=1;break;
    default: fail("invalid GHC host operation");
  }
  if (text) { *output=(char *)value->as.string.bytes; *length=value->as.string.length; }
  else *result=value->as.integer;
  free(value); return 0;
}
void mlf_ghc_shutdown(void) { mlf_process_shutdown();mlf_process_binding_clear(); }
/* The native contract uses the initial C locale and snprintf binary64 rounding. */
int mlf_ghc_format(int places,double n,char *buffer) {
  return snprintf(buffer,384,"%.*f",places,n);
}
