/* Test-only observation: production allocation and collection are untouched. */
#include <gc/gc.h>
#include <stdio.h>
#include <stdlib.h>

__attribute__((destructor)) static void report_concat_gc(void) {
    const char *path = getenv("MLF_CONCAT_GC_REPORT");
    if (path && path[0]) {
        FILE *report = fopen(path, "w");
        if (!report) { perror("concat GC report"); return; }
        int failed = fprintf(report, "%lu\n", (unsigned long)GC_get_gc_no()) < 0;
        if (fclose(report) != 0) failed = 1;
        if (failed) fputs("concat GC report write failed\n", stderr);
    }
}
