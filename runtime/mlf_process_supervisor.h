/* Dynamic subprocess scopes. No compiler, cache, dependency-graph or task-value
 * policy lives here. All calls are made by one coordinator thread.
 *
 * Build either mlf_process_supervisor.c as a separate translation unit, or
 * define MLF_PROCESS_SUPERVISOR_IMPLEMENTATION before including this header.
 * Do not do both in the same executable. */
#ifndef MLF_PROCESS_SUPERVISOR_H
#define MLF_PROCESS_SUPERVISOR_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define MLF_PROCESS_SUPERVISOR_VERSION 1

typedef uint64_t mlf_process_scope;
typedef struct {
    mlf_process_scope scope;
    uint64_t generation;
    uint32_t slot;
} mlf_process_handle;

typedef enum {
    MLF_PROCESS_OK=0,
    MLF_PROCESS_INVALID_ARGUMENT,
    MLF_PROCESS_NO_MEMORY,
    MLF_PROCESS_INVALID_SCOPE,
    MLF_PROCESS_INVALID_HANDLE,
    MLF_PROCESS_SCOPE_CLOSED,
    MLF_PROCESS_QUEUE_FULL,
    MLF_PROCESS_RETENTION_FULL,
    MLF_PROCESS_WOULD_BLOCK,
    MLF_PROCESS_EMPTY,
    MLF_PROCESS_WAIT_TIMEOUT,
    MLF_PROCESS_UNSUPPORTED,
    MLF_PROCESS_SYSTEM_ERROR
} mlf_process_status;

typedef struct {
    uint32_t jobs;
    uint32_t max_pending;
    /* Each accepted submission reserves one retained slot until scope close.
     * Completed outcomes are never evicted, so repeated await is safe.
     * Copied unfinished specs additionally share a 16 MiB per-scope budget;
     * exhausting it returns QUEUE_FULL. Specs are freed on completion. */
    uint32_t max_retained;
} mlf_process_options;

typedef enum {
    MLF_PROCESS_ENV_INHERIT=0,
    MLF_PROCESS_ENV_REPLACE=1
} mlf_process_environment;

typedef struct {
    const char *executable;
    /* NULL-terminated, nonempty argv, INCLUDING argv[0]. No shell parsing. */
    const char *const *argv;
    /* NULL or empty cwd/stream paths inherit. Relative streams use child cwd.
     * Equal nonempty stdout/stderr paths share a descriptor. */
    const char *cwd, *input, *output, *error;
    mlf_process_environment environment;
    /* NULL-terminated NAME=VALUE entries; only valid with ENV_REPLACE.
     * NULL with ENV_REPLACE means an empty environment, except the reserved
     * POSIX MLF_BUILD_SCOPE containment variable set by this backend.
     * Inherited environment is read at actual launch, not at submission. */
    const char *const *env;
    /* Zero disables. Total includes queue time; running starts at launch.
     * Monotonic seconds. Expiry requests cancellation; cleanup may take longer.
     * Timers/admission in all scopes are serviced only inside supervisor calls. */
    double running_timeout_seconds;
    double total_timeout_seconds;
} mlf_process_spec;

typedef enum {
    MLF_PROCESS_EXITED=0,
    MLF_PROCESS_LAUNCH_FAILED,
    MLF_PROCESS_CANCELLED,
    MLF_PROCESS_TIMED_OUT
} mlf_process_outcome_kind;

typedef struct {
    mlf_process_outcome_kind kind;
    int exit_code;              /* Ordinary exits, including nonzero, are data. */
    int launch_error;           /* errno or GetLastError; zero if not relevant. */
    int cleanup_error;          /* Separate from the primary outcome. */
    int cancel_reason;          /* Caller-supplied integer; zero for deadlines. */
    uint64_t pid, peak_rss_bytes;
    double submitted_seconds, started_seconds, finished_seconds, cpu_seconds;
} mlf_process_outcome;

typedef struct {
    mlf_process_handle handle;
    mlf_process_outcome outcome;
} mlf_process_event;

typedef enum {
    MLF_PROCESS_CLOSE_JOIN=0,
    MLF_PROCESS_CLOSE_CANCEL=1
} mlf_process_close_mode;

/* Scope IDs never reuse within this process. Closed/stale IDs and handles are
 * rejected. create/submit copy caller data; caller retains its own buffers. */
mlf_process_status mlf_process_scope_create(const mlf_process_options *, mlf_process_scope *);
mlf_process_status mlf_process_submit(mlf_process_scope, const mlf_process_spec *, mlf_process_handle *);
/* Events are delivered at most once. await does not consume an event.
 * poll: WOULD_BLOCK while unfinished children exist, EMPTY when none remain.
 * wait_next/await: wait_seconds < 0 means infinite, 0 means nonblocking.
 * WAIT_TIMEOUT is a wait bound, not a child timeout/cancellation. */
mlf_process_status mlf_process_poll(mlf_process_scope, mlf_process_event *);
mlf_process_status mlf_process_wait_next(mlf_process_scope, double wait_seconds, mlf_process_event *);
mlf_process_status mlf_process_await(mlf_process_scope, mlf_process_handle, double wait_seconds, mlf_process_outcome *);
/* cancel(handle) accepts cancellation and joins that child. cancel_scope stops
 * admission, cancels queued/running work and joins every child. Already
 * committed outcomes do not change. Both are idempotent for valid handles. */
mlf_process_status mlf_process_cancel(mlf_process_scope, mlf_process_handle, int reason);
mlf_process_status mlf_process_cancel_scope(mlf_process_scope, int reason);
/* close joins/cancels and releases all retained metadata. ID invalid afterward.
 * A cleanup failure returns SYSTEM_ERROR, but close still releases the scope. */
mlf_process_status mlf_process_scope_close(mlf_process_scope, mlf_process_close_mode);
/* For runtime orderly shutdown (including panic/exit); owner death also has
 * native guardian/Job Object containment. Cleanup errors are reported on stderr. */
void mlf_process_shutdown(void);
const char *mlf_process_status_string(mlf_process_status);
double mlf_process_monotonic_seconds(void);
#ifdef __cplusplus
}
#endif
#endif
#ifdef MLF_PROCESS_SUPERVISOR_IMPLEMENTATION
#undef MLF_PROCESS_SUPERVISOR_IMPLEMENTATION
#include "mlf_process_supervisor.c"
#endif
