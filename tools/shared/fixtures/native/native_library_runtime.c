#include "mlf_runtime.h"
#include <gc/gc.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>

#ifndef EXPORT_COUNT
#error EXPORT_COUNT is required
#endif
#ifndef IO_EXPORT
#define IO_EXPORT 0
#endif
extern MlfValue *mlf_fixed_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_get(uint64_t);
#define get_export mlf_fixed_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_get

/* The emitted static pointer array is separately checked by the harness.
 * This pressure test additionally exercises the actual BDWGC-linked image. */
__attribute__((noinline)) static void initialize(void) {
    for (uint64_t i = 0; i < EXPORT_COUNT; ++i)
        if (get_export(i) != get_export(i)) _exit(20);
}
__attribute__((noinline)) static void pressure(void) {
    volatile uintptr_t scrub[32768];
    for (size_t i = 0; i < 32768; ++i) scrub[i] = i;
    for (size_t i = 0; i < 4096; ++i) {
        void *allocation = GC_malloc(1024);
        memset(allocation, 0, 1024);
    }
    GC_gcollect();
    if (scrub[32767] != 32767) _exit(21);
}
int main(int argc, char **argv) {
    const struct rlimit no_core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &no_core) != 0) return 29;
    mlf_set_args(argc, argv);
    initialize();
    pressure();
    if (argc > 1 && strcmp(argv[1], "demand") == 0) {
        if (EXPORT_COUNT == 0) return 22;
        mlf_force(get_export(EXPORT_COUNT - 1));
        return 23;
    }
    /* The getter must reject the empty table and the first out-of-range slot.
     * A child isolates llvm.trap; its signal number differs by architecture. */
    pid_t child = fork();
    if (child < 0) return 24;
    if (child == 0) { get_export(EXPORT_COUNT); _exit(25); }
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFSIGNALED(status)) return 26;
    if (IO_EXPORT) {
        if (mlf_run(get_export(0), 1) != 0) return 27;
        pressure();
        if (mlf_run(get_export(0), 1) != 0) return 28;
    }
    puts("PASS native lazy getters, shared slots, GC and bounds");
    return 0;
}
