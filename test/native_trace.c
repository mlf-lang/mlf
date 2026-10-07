/* Test-only stdio interposition. The generated code and runtime still execute
 * normally; this records actual read requests and flushed writes separately
 * from stdout. Compile only the runtime with the four symbol-renaming macros.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static FILE *trace;
static unsigned char *pending;
static size_t used;

static void hex(const void *data, size_t length) {
    const unsigned char *bytes = data;
    for (size_t i = 0; i < length; ++i) fprintf(trace, "%02x", bytes[i]);
}

static void finish(void) {
    /* Draining the input is outside language execution, and exposes unused
     * input to the harness without adding a ReadLine event. */
    fputs("U ", trace);
    int c;
    while ((c = fgetc(stdin)) != EOF) fprintf(trace, "%02x", (unsigned)c);
    fputc('\n', trace);
    fclose(trace);
    free(pending);
}

__attribute__((constructor)) static void initialize(void) {
    const char *file = getenv("MLF_TEST_TRACE");
    if (!file || !(trace = fopen(file, "wb"))) {
        fputs("native trace initialization failed\n", stderr);
        exit(2);
    }
    if (atexit(finish)) exit(2);
}

static void append(const void *data, size_t length) {
    if (length > SIZE_MAX - used) exit(2);
    if (!length) return;
    unsigned char *larger = realloc(pending, used + length);
    if (!larger) exit(2);
    pending = larger;
    memcpy(pending + used, data, length);
    used += length;
}

ssize_t mlf_test_getline(char **line, size_t *capacity, FILE *stream) {
    if (stream != stdin) exit(2);
    fputs("R\n", trace);
    return getline(line, capacity, stream);
}

size_t mlf_test_fwrite(const void *data, size_t size, size_t count, FILE *stream) {
    if (stream != stdout || (size && count > SIZE_MAX / size)) exit(2);
    append(data, size * count);
    return fwrite(data, size, count, stream);
}

int mlf_test_fputc(int c, FILE *stream) {
    if (stream != stdout) exit(2);
    unsigned char byte = (unsigned char)c;
    append(&byte, 1);
    return fputc(c, stream);
}

int mlf_test_fflush(FILE *stream) {
    if (stream != stdout) exit(2);
    fputs("W ", trace);
    hex(pending, used);
    fputc('\n', trace);
    used = 0;
    int result = fflush(stream);
    return getenv("MLF_TEST_FAIL_WRITE") ? EOF : result;
}
