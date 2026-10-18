/* Diagnostic-only runtime: JSON phase timing, allocation, GC, and peak RSS.
 * fwrite is intercepted only to observe the profiler's stderr markers. */
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>
#include <stdint.h>
#include <gc/gc.h>
static size_t profile_write(const void *, size_t, size_t, FILE *);
#define fwrite profile_write
#include "mlf_runtime.c"
#undef fwrite
static double profile_clock(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static double gc_seconds, gc_started;
static void profile_gc(GC_EventType event) {
    if (event == GC_EVENT_START) gc_started = profile_clock();
    if (event == GC_EVENT_END) gc_seconds += profile_clock() - gc_started;
}
static size_t profile_write(const void *p, size_t size, size_t count, FILE *f) {
    static double start, previous;
    size_t length = size * count;
    if (f == stderr && length > 11 && !memcmp(p, "MLF_PHASE ", 10)) {
        double now = profile_clock();
        if (!start) { start = previous = now; GC_set_on_collection_event(profile_gc); }
        struct rusage r; getrusage(RUSAGE_SELF, &r);
        fprintf(stderr, "{\"phase\":\"%.*s\",\"elapsed_seconds\":%.9f,\"delta_seconds\":%.9f,\"gc_seconds\":%.9f,\"allocated_bytes\":%zu,\"heap_bytes\":%zu,\"collections\":%lu,\"max_rss\":%ld}\n",
          (int)length - 11, (const char *)p + 10, now-start, now-previous,
          gc_seconds, GC_get_total_bytes(), GC_get_heap_size(),
          (unsigned long)GC_get_gc_no(), r.ru_maxrss);
        previous = now;
        return count;
    }
    return fwrite(p,size,count,f);
}
