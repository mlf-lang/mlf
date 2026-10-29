/* Byte/integer-only FFI adapter. These private transport objects never contain
 * a Haskell or MLF heap pointer. Reuse the native OS and process protocol code
 * without linking mlf_runtime.c, GMP allocator hooks, or BDWGC. */
/* Expose the existing syscall ABI for optional Linux child readiness. */
#if defined(__linux__) && !defined(_DEFAULT_SOURCE)
#define _DEFAULT_SOURCE 1
#endif
#ifndef _XOPEN_SOURCE
#define _XOPEN_SOURCE 700
#endif
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
#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif
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
  if (n>=SIZE_MAX) fail("string too large");
  MlfValue *v=allocate(sizeof(*v)); char *copy=calloc((size_t)n+1,1);
  if (!copy) { free(v); fail("out of memory"); }
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
/* Filesystem strings use native UTF-8 bytes, including validation during the
 * action even if its returned String is discarded. Directory.doesFileExist
 * accepts non-directory special files, unlike the native regular-file test. */
static MlfValue *host_owned_bytes(char *bytes, size_t length) {
  if (!valid_utf8((const unsigned char *)bytes,length)) {
    free(bytes); fail("IO error: invalid UTF-8 input");
  }
  MlfValue *result=calloc(1,sizeof(*result));
  if (!result) { free(bytes); fail("out of memory"); }
  result->as.string.bytes=bytes; result->as.string.length=length;
  return result;
}
static MlfValue *host_owned_string(char *bytes, const char *missing) {
  if (!bytes) fail(missing);
  return host_owned_bytes(bytes,strlen(bytes));
}
static MlfValue *host_file_exists(MlfValue *name) {
  const char *path=file_path(name);
#if defined(_WIN32)
  DWORD attributes=mlf_windows_attributes(path);
  return mlf_boolean(attributes!=INVALID_FILE_ATTRIBUTES && !(attributes&FILE_ATTRIBUTE_DIRECTORY));
#else
  struct stat status;
  return mlf_boolean(stat(path,&status)==0 && S_ISREG(status.st_mode));
#endif
}
static MlfValue *host_canonical_path(MlfValue *name) {
  return host_owned_string(realpath(file_path(name),NULL),"IO error: canonical path failed");
}
static MlfValue *host_executable_path(void) {
  char *buffer=NULL;
#if defined(__APPLE__)
  uint32_t capacity=0;
  (void)_NSGetExecutablePath(NULL,&capacity);
  if (!capacity) fail("IO error: executable path failed");
  buffer=allocate(capacity);
  if (_NSGetExecutablePath(buffer,&capacity)) { free(buffer); fail("IO error: executable path failed"); }
#elif defined(__linux__)
  size_t capacity=256;
  for (;;) {
    buffer=allocate(capacity+1);
    ssize_t size=readlink("/proc/self/exe",buffer,capacity);
    if (size<0) { free(buffer); fail("IO error: executable path failed"); }
    if ((size_t)size<capacity) { buffer[size]=0; break; }
    free(buffer);
    if (capacity>SIZE_MAX/2-1) fail("IO error: executable path failed");
    capacity*=2;
  }
#else
  fail("IO error: executable path failed");
#endif
  char *resolved=realpath(buffer,NULL);
  free(buffer);
  return host_owned_string(resolved,"IO error: executable path failed");
}
static MlfValue *host_read_file(MlfValue *name) {
  FILE *file=fopen(file_path(name),"rb");
  if (!file) fail("IO error: file read failed");
  size_t length=0, capacity=4096;
  char *buffer=calloc(capacity,1);
  if (!buffer) { fclose(file); fail("out of memory"); }
  for (;;) {
    size_t n=fread(buffer+length,1,capacity-length,file);
    length+=n;
    if (ferror(file)) { free(buffer); fclose(file); fail("IO error: file read failed"); }
    if (feof(file)) break;
    if (length==capacity) {
      if (capacity>SIZE_MAX/2) { free(buffer); fclose(file); fail("string too large"); }
      capacity*=2;
      char *next=realloc(buffer,capacity);
      if (!next) { free(buffer); fclose(file); fail("out of memory"); }
      buffer=next;
    }
  }
  if (fclose(file)) { free(buffer); fail("IO error: file read failed"); }
  return host_owned_bytes(buffer,length);
}
static MlfValue *host_write_file(MlfValue *name, MlfValue *contents) {
  const char *path=file_path(name);
  FILE *file=fopen(path,"wb");
  if (!file) fail("IO error: file write failed");
  int failed=fwrite(contents->as.string.bytes,1,contents->as.string.length,file)!=contents->as.string.length;
  if (fclose(file)) failed=1;
  if (failed) fail("IO error: file write failed");
  return mlf_constructor(0,0);
}
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
    case 10: value=host_file_exists(&first);break;
    case 11: value=host_canonical_path(&first);text=1;break;
    case 12: value=host_executable_path();text=1;break;
    case 13: value=host_read_file(&first);text=1;break;
    case 14: value=host_write_file(&first,&second);break;
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
