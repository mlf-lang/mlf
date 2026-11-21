#ifndef MLF_NATIVE_TEST_CASE_EVENTS_H
#define MLF_NATIVE_TEST_CASE_EVENTS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <wchar.h>
#endif

/* The case names are compile-time registry constants. Existing stdout and
 * exit values stay available to the runtime and release evidence consumers. */
static const char *mlf_case_active;

static inline int mlf_case_selected(const char *id) {
    const char *exact = getenv("MLF_TEST_EXACT");
    return !exact || !*exact || !strcmp(exact, id);
}

static inline FILE *mlf_event_file(void) {
#ifdef _WIN32
    const wchar_t *path = _wgetenv(L"MLF_TEST_EVENTS");
    FILE *file = path && *path ? _wfopen(path, L"ab") : NULL;
#else
    const char *path = getenv("MLF_TEST_EVENTS");
    FILE *file = path && *path ? fopen(path, "ab") : NULL;
#endif
    if (path && *path && !file) exit(74);
    return file;
}

static inline void mlf_case_start(const char *id) {
    mlf_case_active = id;
    FILE *file = mlf_event_file();
    if (!file) return;
    int written = fprintf(file, "{\"start\":\"%s\"}\n", id);
    if (fclose(file) || written < 0) exit(74);
}

static inline void mlf_case_result(const char *status, int exit_code) {
    if (!mlf_case_active) return;
    FILE *file = mlf_event_file();
    if (file) {
        int written = fprintf(file, "{\"id\":\"%s\",\"status\":\"%s\",\"observed_exit\":%d}\n",
                              mlf_case_active, status, exit_code);
        if (fclose(file) || written < 0) exit(74);
    }
    mlf_case_active = NULL;
}

#endif
