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
static unsigned char *pending_error;
static size_t error_used;

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
    free(pending_error);
}

__attribute__((constructor)) static void initialize(void) {
    const char *file = getenv("MLF_TEST_TRACE");
    if (!file || !(trace = fopen(file, "wb"))) {
        fputs("native trace initialization failed\n", stderr);
        exit(2);
    }
    if (atexit(finish)) exit(2);
}

static void append(const void *data, size_t length, FILE *stream) {
    unsigned char **buffer = stream == stderr ? &pending_error : &pending;
    size_t *count = stream == stderr ? &error_used : &used;
    if (length > SIZE_MAX - *count) exit(2);
    if (!length) return;
    unsigned char *larger = realloc(*buffer, *count + length);
    if (!larger) exit(2);
    *buffer = larger;
    memcpy(*buffer + *count, data, length);
    *count += length;
}

ssize_t mlf_test_getline(char **line, size_t *capacity, FILE *stream) {
    if (stream == stdin) fputs("R\n", trace);
    return getline(line, capacity, stream);
}

size_t mlf_test_fwrite(const void *data, size_t size, size_t count, FILE *stream) {
    if (size && count > SIZE_MAX / size) exit(2);
    if (stream == stdout || stream == stderr) append(data, size * count, stream);
    return fwrite(data, size, count, stream);
}

int mlf_test_fputc(int c, FILE *stream) {
    unsigned char byte = (unsigned char)c;
    if (stream == stdout || stream == stderr) append(&byte, 1, stream);
    return fputc(c, stream);
}

int mlf_test_fflush(FILE *stream) {
    if (stream != stdout && stream != stderr) return fflush(stream);
    fputs(stream == stderr ? "E " : "W ", trace);
    hex(stream == stderr ? pending_error : pending, stream == stderr ? error_used : used);
    fputc('\n', trace);
    if (stream == stderr) error_used = 0; else used = 0;
    int result = fflush(stream);
    return getenv("MLF_TEST_FAIL_WRITE") ? EOF : result;
}
