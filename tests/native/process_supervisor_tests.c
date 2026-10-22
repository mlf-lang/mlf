/* Dynamic process-scope contract tests. Gates, readiness files and PID checks
 * establish ordering; elapsed waits are used only to exercise timeout APIs.
 * Each scenario runs in a bounded child of the test harness, so a regression
 * cannot hang the entire suite. The same binary supplies a few child modes. */
#include "build_runner_test_support.h"
#include "../../runtime/mlf_process_supervisor.h"
#include <math.h>

static const char *self, *fixture;
static char scratch[4096];
static unsigned checks;
static void check(int condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "process supervisor test failed: %s\n", message);
        exit(1);
    }
}
static void status(mlf_process_status actual, mlf_process_status expected, const char *message) {
    if (actual != expected) {
        fprintf(stderr, "process supervisor test failed: %s: got %s, expected %s\n",
                message, mlf_process_status_string(actual), mlf_process_status_string(expected));
        exit(1);
    }
}
static void path(char *out, size_t size, const char *name) {
    int n = snprintf(out, size, "%s/%s", scratch, name);
    check(n >= 0 && (size_t)n < size, "test path length");
}
static mlf_process_scope scope(unsigned jobs, unsigned pending, unsigned retained) {
    mlf_process_options options = {jobs, pending, retained};
    mlf_process_scope result = 0;
    status(mlf_process_scope_create(&options, &result), MLF_PROCESS_OK, "create scope");
    check(result != 0, "nonzero scope identity");
    return result;
}
static mlf_process_spec spec(const char *const *argv) {
    mlf_process_spec result;
    memset(&result, 0, sizeof(result));
    result.executable = argv[0];
    result.argv = argv;
    result.running_timeout_seconds = 10;
    return result;
}
static mlf_process_handle submit_spec(mlf_process_scope s, const mlf_process_spec *p) {
    mlf_process_handle result;
    memset(&result, 0, sizeof(result));
    status(mlf_process_submit(s, p, &result), MLF_PROCESS_OK, "submit process");
    check(result.scope == s, "handle belongs to submitting scope");
    return result;
}
static mlf_process_handle submit(mlf_process_scope s, const char *const *argv) {
    mlf_process_spec p = spec(argv);
    return submit_spec(s, &p);
}
static mlf_process_outcome await(mlf_process_scope s, mlf_process_handle h) {
    mlf_process_outcome result;
    memset(&result, 0, sizeof(result));
    status(mlf_process_await(s, h, 15, &result), MLF_PROCESS_OK, "await process");
    check(!result.cleanup_error, "successful native cleanup");
    check(result.finished_seconds >= result.submitted_seconds, "monotonic outcome times");
    return result;
}
static void exited(mlf_process_outcome out, int code) {
    check(out.kind == MLF_PROCESS_EXITED, "ordinary exit outcome");
    check(out.exit_code == code, "ordinary exit code");
    check(!out.launch_error && !out.cleanup_error, "ordinary outcome has no launch/cleanup error");
}
static int same_handle(mlf_process_handle a, mlf_process_handle b) {
    return a.scope == b.scope && a.generation == b.generation && a.slot == b.slot;
}
static void same_outcome(mlf_process_outcome a, mlf_process_outcome b) {
    check(a.kind == b.kind && a.exit_code == b.exit_code && a.launch_error == b.launch_error &&
          a.cleanup_error == b.cleanup_error && a.cancel_reason == b.cancel_reason &&
          a.pid == b.pid && a.peak_rss_bytes == b.peak_rss_bytes &&
          a.submitted_seconds == b.submitted_seconds && a.started_seconds == b.started_seconds &&
          a.finished_seconds == b.finished_seconds && a.cpu_seconds == b.cpu_seconds,
          "retained outcome is unchanged");
}
static void close_scope(mlf_process_scope s) {
    status(mlf_process_scope_close(s, MLF_PROCESS_CLOSE_JOIN), MLF_PROCESS_OK, "join and close scope");
}
static long read_pid(const char *file) {
    check(test_await(file, 10), "process readiness marker exists");
    char *text = test_read(file);
    check(text != NULL, "read process marker");
    long pid = strtol(text, NULL, 10);
    free(text);
    check(pid > 0, "valid process pid");
    return pid;
}
static void stopped(long pid) {
    double begin = test_now();
    while (test_alive(pid) && test_now() - begin < 10) test_pause();
    check(!test_alive(pid), "managed process stopped");
}
static void tree_pids(const char *file, long pids[3]) {
    char nested[4200];
    pids[0] = read_pid(file);
    int n = snprintf(nested, sizeof(nested), "%s.child", file);
    check(n >= 0 && (size_t)n < sizeof(nested), "child path length");
    pids[1] = read_pid(nested);
    n = snprintf(nested, sizeof(nested), "%s.grandchild", file);
    check(n >= 0 && (size_t)n < sizeof(nested), "grandchild path length");
    pids[2] = read_pid(nested);
}
static void tree_stopped(long pids[3]) {
    for (unsigned i = 0; i < 3; ++i) stopped(pids[i]);
}
static void empty_scope(void) {
    mlf_process_scope s = scope(1, 1, 2);
    mlf_process_event event;
    status(mlf_process_poll(s, &event), MLF_PROCESS_EMPTY, "empty poll");
    status(mlf_process_wait_next(s, 0.02, &event), MLF_PROCESS_EMPTY, "empty wait");
    close_scope(s);
}
static void dynamic_submission(void) {
    char alive[4096], release[4096], prerequisite[4096];
    path(alive, sizeof(alive), "C-running"); path(release, sizeof(release), "C-release");
    path(prerequisite, sizeof(prerequisite), "A-result");
    mlf_process_scope s = scope(2, 4, 8);
    const char *c_args[] = {fixture, "gate", alive, release, NULL};
    const char *a_args[] = {fixture, "signal", prerequisite, NULL};
    mlf_process_handle c = submit(s, c_args), a = submit(s, a_args);
    check(test_await(alive, 10), "unrelated C is running");
    mlf_process_outcome first = await(s, a);
    exited(first, 0);
    check(test_exists(prerequisite), "A result available before B submission");
    /* B is constructed only after inspecting A, not predeclared in a DAG. */
    const char *b_args[] = {fixture, first.exit_code ? "exit" : "require", prerequisite, NULL};
    mlf_process_handle b = submit(s, b_args);
    exited(await(s, b), 0);
    mlf_process_outcome pending;
    status(mlf_process_await(s, c, 0, &pending), MLF_PROCESS_WOULD_BLOCK, "C remains alive while dynamic B completes");
    test_touch(release);
    exited(await(s, c), 0);
    close_scope(s);
}
static void serial_dynamic(void) {
    char result[4096]; path(result, sizeof(result), "serial-prerequisite");
    mlf_process_scope s = scope(1, 1, 4);
    const char *a[] = {fixture, "signal", result, NULL}, *b[] = {fixture, "require", result, NULL};
    mlf_process_handle first = submit(s, a);
    exited(await(s, first), 0);
    mlf_process_handle second = submit(s, b);
    exited(await(s, second), 0);
    close_scope(s);
}
static void admission_bound(void) {
    char ready[4][4096], release[4][4096];
    mlf_process_handle handles[4];
    mlf_process_scope s = scope(2, 2, 8);
    for (unsigned i = 0; i < 4; ++i) {
        char name[40]; snprintf(name, sizeof(name), "ready-%u", i); path(ready[i], sizeof(ready[i]), name);
        snprintf(name, sizeof(name), "release-%u", i); path(release[i], sizeof(release[i]), name);
        const char *args[] = {fixture, "gate", ready[i], release[i], NULL};
        handles[i] = submit(s, args);
    }
    check(test_await(ready[0], 10) && test_await(ready[1], 10), "two concurrent processes start");
    check(!test_exists(ready[2]) && !test_exists(ready[3]), "queued processes do not exceed jobs bound");
    const char *extra_args[] = {fixture, "exit", "0", NULL};
    mlf_process_spec extra = spec(extra_args); mlf_process_handle rejected;
    status(mlf_process_submit(s, &extra, &rejected), MLF_PROCESS_QUEUE_FULL, "bounded pending queue");
    test_touch(release[0]); exited(await(s, handles[0]), 0);
    /* Service admission without requiring a completion event to be consumed. */
    mlf_process_outcome pending;
    status(mlf_process_await(s, handles[2], 0.02, &pending), MLF_PROCESS_WAIT_TIMEOUT, "third task admitted and waiting");
    check(test_await(ready[2], 10), "completion admits next queued process");
    check(!test_exists(ready[3]), "admission never exceeds two running processes");
    test_touch(release[1]); exited(await(s, handles[1]), 0);
    status(mlf_process_await(s, handles[3], 0.02, &pending), MLF_PROCESS_WAIT_TIMEOUT, "fourth task admitted and waiting");
    check(test_await(ready[3], 10), "second completion admits fourth process");
    for (unsigned i = 2; i < 4; ++i) { test_touch(release[i]); exited(await(s, handles[i]), 0); }
    exited(await(s, submit(s, extra_args)), 0);
    close_scope(s);
    /* A zero-capacity queue still admits work directly into a free slot. */
    s = scope(1, 0, 3);
    char noqueue_ready[4096], noqueue_release[4096];
    path(noqueue_ready, sizeof(noqueue_ready), "noqueue-ready");
    path(noqueue_release, sizeof(noqueue_release), "noqueue-release");
    const char *gate[] = {fixture, "gate", noqueue_ready, noqueue_release, NULL};
    mlf_process_handle active = submit(s, gate);
    check(test_await(noqueue_ready, 10), "zero-queue scope immediately launches with a free slot");
    status(mlf_process_submit(s, &extra, &rejected), MLF_PROCESS_QUEUE_FULL, "zero-queue scope never retains pending work");
    status(mlf_process_cancel(s, active, 40), MLF_PROCESS_OK, "release zero-queue active slot");
    exited(await(s, submit(s, extra_args)), 0);
    close_scope(s);
}
static void retained_limit(void) {
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "exit", "0", NULL};
    mlf_process_handle first = submit(s, args), second;
    mlf_process_outcome initial = await(s, first);
    second = submit(s, args); exited(await(s, second), 0);
    mlf_process_spec p = spec(args); mlf_process_handle rejected;
    status(mlf_process_submit(s, &p, &rejected), MLF_PROCESS_RETENTION_FULL, "retained outcomes are independently bounded");
    same_outcome(initial, await(s, first));
    close_scope(s);
}
static void repeat_await(void) {
    mlf_process_scope s = scope(1, 2, 4);
    const char *args[] = {fixture, "exit", "23", NULL};
    mlf_process_handle h = submit(s, args);
    mlf_process_outcome a = await(s, h); exited(a, 23);
    for (unsigned i = 0; i < 6; ++i) same_outcome(a, await(s, h));
    mlf_process_event event;
    status(mlf_process_poll(s, &event), MLF_PROCESS_OK, "await preserves completion event");
    check(same_handle(event.handle, h), "completion has original handle"); same_outcome(a, event.outcome);
    status(mlf_process_poll(s, &event), MLF_PROCESS_EMPTY, "completion event delivered exactly once");
    same_outcome(a, await(s, h)); close_scope(s);
}
static void launch_and_exit(void) {
    mlf_process_scope s = scope(2, 3, 6);
    const char *missing[] = {"mlf-process-intentionally-missing-7b79", NULL};
    mlf_process_outcome failed = await(s, submit(s, missing));
    check(failed.kind == MLF_PROCESS_LAUNCH_FAILED && failed.launch_error != 0, "missing executable is a launch error");
    const char *exit126[] = {fixture, "exit", "126", NULL}, *exit127[] = {fixture, "exit", "127", NULL};
    exited(await(s, submit(s, exit126)), 126);
    exited(await(s, submit(s, exit127)), 127);
    char invalid_path[4096]; path(invalid_path, sizeof(invalid_path), "nonexistent/path");
    mlf_process_spec p = spec(exit126); p.cwd = invalid_path;
    failed = await(s, submit_spec(s, &p));
    check(failed.kind == MLF_PROCESS_LAUNCH_FAILED && failed.launch_error != 0, "invalid working directory is a launch error");
    p = spec(exit126); p.input = invalid_path;
    failed = await(s, submit_spec(s, &p));
    check(failed.kind == MLF_PROCESS_LAUNCH_FAILED && failed.launch_error != 0, "invalid stdin path is a launch error");
    char text_executable[4096]; path(text_executable, sizeof(text_executable), "not-an-executable.exe");
    FILE *f = test_open(text_executable, "wb"); check(f != NULL, "create malformed executable");
    check(fputs("exit 0\n", f) >= 0 && !fclose(f), "write malformed executable");
#ifndef _WIN32
    check(!chmod(text_executable, 0700), "make shebang-free text executable");
#endif
    const char *text_args[] = {text_executable, NULL};
    failed = await(s, submit(s, text_args));
    check(failed.kind == MLF_PROCESS_LAUNCH_FAILED && failed.launch_error != 0, "malformed executable cannot trigger an implicit shell");
    close_scope(s);
}
static void nonzero_is_data(void) {
    char marker[4096]; path(marker, sizeof(marker), "sibling-ran");
    mlf_process_scope s = scope(1, 2, 4);
    const char *bad[] = {fixture, "exit", "23", NULL}, *good[] = {fixture, "signal", marker, NULL};
    mlf_process_handle a = submit(s, bad), b = submit(s, good);
    exited(await(s, a), 23); exited(await(s, b), 0);
    check(test_exists(marker), "nonzero exit does not cancel unrelated work"); close_scope(s);
}
static void cancel_queued(void) {
    char ready[4096], release[4096], forbidden[4096];
    path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release"); path(forbidden, sizeof(forbidden), "forbidden");
    mlf_process_scope s = scope(1, 2, 4);
    const char *gate[] = {fixture, "gate", ready, release, NULL}, *queued[] = {fixture, "signal", forbidden, NULL};
    mlf_process_handle a = submit(s, gate), b = submit(s, queued);
    check(test_await(ready, 10), "first process running before queued cancellation");
    status(mlf_process_cancel(s, b, 41), MLF_PROCESS_OK, "cancel queued process");
    mlf_process_outcome out = await(s, b);
    check(out.kind == MLF_PROCESS_CANCELLED && out.cancel_reason == 41 && !out.pid, "queued cancellation has no child pid");
    test_touch(release); exited(await(s, a), 0); same_outcome(out, await(s, b));
    check(!test_exists(forbidden), "cancelled queued work is never launched"); close_scope(s);
}
static void cancel_running(void) {
    char marker[4096]; path(marker, sizeof(marker), "tree");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "tree", marker, NULL};
    mlf_process_handle h = submit(s, args); long pids[3]; tree_pids(marker, pids);
    status(mlf_process_cancel(s, h, 42), MLF_PROCESS_OK, "cancel running tree and join");
    tree_stopped(pids);
    mlf_process_outcome out = await(s, h);
    check(out.kind == MLF_PROCESS_CANCELLED && out.cancel_reason == 42 && out.pid, "running cancellation outcome");
    status(mlf_process_cancel(s, h, 99), MLF_PROCESS_OK, "repeat cancellation is idempotent");
    same_outcome(out, await(s, h)); close_scope(s);
}
static void request_cancel(void) {
    char marker[4096], forbidden[4096];
    path(marker, sizeof(marker), "request-tree"); path(forbidden, sizeof(forbidden), "request-forbidden");
    mlf_process_scope s = scope(1, 2, 4), other = scope(1, 1, 2);
    const char *tree[] = {fixture, "tree", marker, NULL}, *queued[] = {fixture, "signal", forbidden, NULL};
    mlf_process_handle running = submit(s, tree), pending = submit(s, queued);
    long pids[3]; tree_pids(marker, pids);
    status(mlf_process_request_cancel(other, running, 60), MLF_PROCESS_INVALID_HANDLE, "request rejects cross-scope handle");
    status(mlf_process_request_cancel(s, pending, 61), MLF_PROCESS_OK, "request queued cancellation");
    status(mlf_process_request_cancel(s, pending, 62), MLF_PROCESS_OK, "queued request is idempotent");
    status(mlf_process_request_cancel(s, running, 63), MLF_PROCESS_OK, "request running cancellation without a join");
    status(mlf_process_request_cancel(s, running, 64), MLF_PROCESS_OK, "running request is idempotent");
    check(!test_exists(forbidden), "request cancellation never admits cancelled queued work");
    /* The coordinator can perform unrelated work before it chooses to await
     * cleanup; only await/poll subsequently commits the running outcome. */
    const char *ok[] = {fixture, "exit", "0", NULL};
    exited(await(other, submit(other, ok)), 0);
    mlf_process_outcome a = await(s, running), b = await(s, pending);
    check(a.kind == MLF_PROCESS_CANCELLED && a.cancel_reason == 63, "first running cancellation reason wins");
    check(b.kind == MLF_PROCESS_CANCELLED && b.cancel_reason == 61 && !b.pid, "first queued cancellation reason wins");
    tree_stopped(pids);
    status(mlf_process_request_cancel(s, running, 65), MLF_PROCESS_OK, "request after completion preserves outcome");
    same_outcome(a, await(s, running));
    mlf_process_event event;
    status(mlf_process_poll(s, &event), MLF_PROCESS_OK, "queued request produces one event");
    check(same_handle(event.handle, pending), "queued cancellation is committed first");
    status(mlf_process_poll(s, &event), MLF_PROCESS_OK, "running request produces one event");
    check(same_handle(event.handle, running), "running event follows cleanup");
    status(mlf_process_poll(s, &event), MLF_PROCESS_EMPTY, "request events are exactly once");
    close_scope(s); close_scope(other);
    status(mlf_process_request_cancel(s, running, 66), MLF_PROCESS_INVALID_SCOPE, "request rejects closed scope");
}
static void cancel_scope(void) {
    char marker[4096], forbidden[4096]; path(marker, sizeof(marker), "tree"); path(forbidden, sizeof(forbidden), "forbidden");
    mlf_process_scope s = scope(1, 2, 4);
    const char *tree[] = {fixture, "tree", marker, NULL}, *queued[] = {fixture, "signal", forbidden, NULL};
    mlf_process_handle a = submit(s, tree), b = submit(s, queued); long pids[3]; tree_pids(marker, pids);
    status(mlf_process_cancel_scope(s, 43), MLF_PROCESS_OK, "cancel and join entire scope");
    tree_stopped(pids);
    mlf_process_outcome x = await(s, a), y = await(s, b);
    check(x.kind == MLF_PROCESS_CANCELLED && y.kind == MLF_PROCESS_CANCELLED, "scope cancels queued and running work");
    check(x.cancel_reason == 43 && y.cancel_reason == 43, "scope cancellation reason retained");
    mlf_process_spec p = spec(queued); mlf_process_handle rejected;
    status(mlf_process_submit(s, &p, &rejected), MLF_PROCESS_SCOPE_CLOSED, "cancelled scope rejects admission");
    status(mlf_process_cancel_scope(s, 44), MLF_PROCESS_OK, "scope cancellation is idempotent");
    same_outcome(x, await(s, a)); same_outcome(y, await(s, b));
    check(!test_exists(forbidden), "scope-cancelled queued child never launches"); close_scope(s);
}
static void cancel_completed(void) {
    mlf_process_scope s = scope(1, 1, 3);
    const char *args[] = {fixture, "exit", "0", NULL};
    mlf_process_handle h = submit(s, args); mlf_process_outcome out = await(s, h);
    status(mlf_process_cancel(s, h, 44), MLF_PROCESS_OK, "cancelling committed completion succeeds");
    same_outcome(out, await(s, h)); exited(await(s, submit(s, args)), 0);
    char marker[4096], release[4096]; path(marker, sizeof(marker), "uncommitted-pid"); path(release, sizeof(release), "uncommitted-release");
    const char *gate[] = {self, "--child", "pid-gate", marker, release, NULL};
    h = submit(s, gate); long pid = read_pid(marker);
    test_touch(release); stopped(pid);
    /* No supervisor call has observed this OS exit yet. Cancellation is
     * accepted before terminal commit, so the final result stays cancelled. */
    status(mlf_process_cancel(s, h, 51), MLF_PROCESS_OK, "cancel exited but uncommitted child");
    out = await(s, h);
    check(out.kind == MLF_PROCESS_CANCELLED && out.cancel_reason == 51, "uncommitted OS success cannot resurrect accepted cancellation");
    close_scope(s);
}
static void running_timeout(void) {
    char marker[4096]; path(marker, sizeof(marker), "timeout-tree");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "tree", marker, NULL};
    mlf_process_spec p = spec(args); p.running_timeout_seconds = 1;
    mlf_process_handle h = submit_spec(s, &p); long pids[3]; tree_pids(marker, pids);
    mlf_process_outcome out = await(s, h);
    check(out.kind == MLF_PROCESS_TIMED_OUT && !out.cancel_reason, "running deadline is explicit timeout");
    tree_stopped(pids);
    status(mlf_process_cancel(s, h, 45), MLF_PROCESS_OK, "timeout completion survives later cancellation");
    same_outcome(out, await(s, h)); close_scope(s);
#ifndef _WIN32
    /* Opening a FIFO for stdin blocks before exec. Ownership/cancellation
     * must already work, rather than waiting for successful exec first. */
    char fifo[4096]; path(fifo, sizeof(fifo), "blocked-exec-input");
    check(!mkfifo(fifo, 0600), "create pre-exec blocking FIFO");
    s = scope(1, 1, 2);
    const char *copy[] = {fixture, "copy", NULL}; p = spec(copy);
    p.input = fifo; p.running_timeout_seconds = 0.05;
    out = await(s, submit_spec(s, &p));
    check(out.kind == MLF_PROCESS_TIMED_OUT && out.pid, "cancellation can stop a child blocked before exec");
    stopped((long)out.pid); close_scope(s);
#endif
}
static void queued_timeout(void) {
    char ready[4096], release[4096], forbidden[4096];
    path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release"); path(forbidden, sizeof(forbidden), "forbidden");
    mlf_process_scope s = scope(1, 2, 4);
    const char *gate[] = {fixture, "gate", ready, release, NULL}, *queued[] = {fixture, "signal", forbidden, NULL};
    mlf_process_handle a = submit(s, gate);
    mlf_process_spec p = spec(queued); p.total_timeout_seconds = 0.05;
    mlf_process_handle b = submit_spec(s, &p);
    mlf_process_outcome out = await(s, b);
    check(out.kind == MLF_PROCESS_TIMED_OUT && !out.pid, "total deadline includes queued time");
    check(!test_exists(forbidden), "queued timeout does not launch child");
    test_touch(release); exited(await(s, a), 0); same_outcome(out, await(s, b));
    check(!test_exists(forbidden), "expired queue entry never resurrects after permit release"); close_scope(s);
}
static void running_timeout_excludes_queue(void) {
    char ready[4096], release[4096], marker[4096];
    path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release"); path(marker, sizeof(marker), "queued-output");
    mlf_process_scope s = scope(1, 2, 4);
    const char *gate[] = {fixture, "gate", ready, release, NULL}, *queued[] = {fixture, "signal", marker, NULL};
    mlf_process_handle a = submit(s, gate);
    mlf_process_spec p = spec(queued); p.running_timeout_seconds = 0.2;
    mlf_process_handle b = submit_spec(s, &p);
    mlf_process_outcome pending;
    status(mlf_process_await(s, b, 0.35, &pending), MLF_PROCESS_WAIT_TIMEOUT, "running timeout does not include queue time");
    check(!test_exists(marker), "task remains queued during wait bound");
    test_touch(release); exited(await(s, a), 0); exited(await(s, b), 0);
    check(test_exists(marker), "queued task runs after permit becomes available"); close_scope(s);
}
static void wait_bound(void) {
    char ready[4096], release[4096]; path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "gate", ready, release, NULL};
    mlf_process_handle h = submit(s, args); mlf_process_event event; mlf_process_outcome out;
    check(test_await(ready, 10), "wait-bound child ready");
    status(mlf_process_poll(s, &event), MLF_PROCESS_WOULD_BLOCK, "nonblocking poll of live work");
    status(mlf_process_wait_next(s, 0.02, &event), MLF_PROCESS_WAIT_TIMEOUT, "event wait bound");
    status(mlf_process_await(s, h, 0, &out), MLF_PROCESS_WOULD_BLOCK, "wait timeout does not cancel process");
    test_touch(release); exited(await(s, h), 0); close_scope(s);
    /* An active wait must service every scope. A depends on B's queued
     * successor, whose admission must progress without an explicit B call. */
    char a_ready[4096], a_release[4096], b_ready[4096], b_release[4096];
    path(a_ready, sizeof(a_ready), "scope-A-ready"); path(a_release, sizeof(a_release), "scope-A-release");
    path(b_ready, sizeof(b_ready), "scope-B-ready"); path(b_release, sizeof(b_release), "scope-B-release");
    mlf_process_scope a = scope(1, 2, 4), b = scope(1, 2, 4);
    const char *a_gate[] = {fixture, "gate", a_ready, a_release, NULL};
    const char *b_gate[] = {fixture, "gate", b_ready, b_release, NULL};
    const char *b_successor[] = {fixture, "signal", a_release, NULL};
    mlf_process_handle b_first = submit(b, b_gate), b_second = submit(b, b_successor), a_first = submit(a, a_gate);
    check(test_await(a_ready, 10) && test_await(b_ready, 10), "cross-scope dependency gates ready");
    test_touch(b_release);
    status(mlf_process_await(a, a_first, 2, &out), MLF_PROCESS_OK, "waiting one scope services queued successor in another");
    exited(out, 0); exited(await(b, b_first), 0); exited(await(b, b_second), 0);
    close_scope(a); close_scope(b);
}
static void no_resurrection(void) {
    char ready[4096], release[4096]; path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "gate", ready, release, NULL};
    mlf_process_handle h = submit(s, args); check(test_await(ready, 10), "cancellation race child is running");
    status(mlf_process_cancel(s, h, 46), MLF_PROCESS_OK, "accept cancellation before success gate");
    test_touch(release);
    mlf_process_outcome out = await(s, h);
    check(out.kind == MLF_PROCESS_CANCELLED && out.cancel_reason == 46, "late success cannot replace accepted cancellation");
    mlf_process_event event;
    status(mlf_process_wait_next(s, 1, &event), MLF_PROCESS_OK, "cancelled event available");
    same_outcome(out, event.outcome);
    status(mlf_process_poll(s, &event), MLF_PROCESS_EMPTY, "no late second event");
    same_outcome(out, await(s, h)); close_scope(s);
}
static void handle_validation(void) {
    mlf_process_scope a = scope(1, 1, 2), b = scope(1, 1, 2);
    const char *args[] = {fixture, "exit", "0", NULL};
    mlf_process_handle h = submit(a, args); mlf_process_outcome out;
    status(mlf_process_await(b, h, 0, &out), MLF_PROCESS_INVALID_HANDLE, "cross-scope await rejected");
    status(mlf_process_cancel(b, h, 47), MLF_PROCESS_INVALID_HANDLE, "cross-scope cancellation rejected");
    mlf_process_handle forged = h; forged.generation ^= UINT64_C(0x4000000000000000);
    status(mlf_process_await(a, forged, 0, &out), MLF_PROCESS_INVALID_HANDLE, "stale generation rejected");
    forged = h; forged.slot = UINT32_MAX;
    status(mlf_process_cancel(a, forged, 47), MLF_PROCESS_INVALID_HANDLE, "invalid slot rejected");
    exited(await(a, h), 0); close_scope(a);
    status(mlf_process_await(a, h, 0, &out), MLF_PROCESS_INVALID_SCOPE, "closed scope handle rejected");
    mlf_process_scope c = scope(1, 1, 2);
    check(c != a && c != b, "closed scope identity is never reused");
    mlf_process_handle fresh = submit(c, args);
    check(!same_handle(h, fresh), "new scope cannot alias old handle");
    status(mlf_process_await(c, h, 0, &out), MLF_PROCESS_INVALID_HANDLE, "old handle invalid in replacement scope");
    exited(await(c, fresh), 0); close_scope(c); close_scope(b);
}
static void large_output(void) {
    char output[4096], error[4096]; path(output, sizeof(output), "stdout"); path(error, sizeof(error), "stderr");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {self, "--child", "large-output", NULL};
    mlf_process_spec p = spec(args); p.output = output; p.error = error;
    exited(await(s, submit_spec(s, &p)), 0);
    const char *files[] = {output, error};
    for (unsigned i = 0; i < 2; ++i) {
        FILE *f = test_open(files[i], "rb"); check(f != NULL, "large output file exists");
        size_t count = 0; int c;
        while ((c = fgetc(f)) != EOF) { check(c == (i ? 'e' : 'o'), "large stream contents intact"); ++count; }
        check(!ferror(f) && count == 2U * 1024U * 1024U, "both streams exceed pipe capacity without truncation");
        fclose(f);
    }
    close_scope(s);
}
static void owner_death(void) {
    char marker[4096], second[4096];
    path(marker, sizeof(marker), "orphan-tree"); path(second, sizeof(second), "orphan-second-scope");
    char *args[] = {(char *)self, "--owner", (char *)fixture, marker, second, NULL};
    test_process owner = test_spawn(args); long pids[3], other[3]; tree_pids(marker, pids); tree_pids(second, other);
    test_kill(owner); check(test_wait(owner, 10) != 0, "scope coordinator was killed abruptly");
    tree_stopped(pids); tree_stopped(other);
}
static void normal_close_joins(void) {
    char marker[4096], descendant[4096]; path(marker, sizeof(marker), "normal-tree"); path(descendant, sizeof(descendant), "queued-finished");
    mlf_process_scope s = scope(1, 2, 4);
    const char *tree[] = {fixture, "tree-exit", marker, NULL}, *queued[] = {fixture, "signal", descendant, NULL};
    (void)submit(s, tree); (void)submit(s, queued);
    close_scope(s);
    long pids[3]; tree_pids(marker, pids); tree_stopped(pids);
    check(test_exists(descendant), "normal close joins queued children instead of dropping them");
}
static void cancel_close_joins(void) {
    char marker[4096], forbidden[4096]; path(marker, sizeof(marker), "cancel-close-tree"); path(forbidden, sizeof(forbidden), "forbidden");
    mlf_process_scope s = scope(1, 2, 4);
    const char *tree[] = {fixture, "tree", marker, NULL}, *queued[] = {fixture, "signal", forbidden, NULL};
    mlf_process_handle h = submit(s, tree); (void)submit(s, queued);
    long pids[3]; tree_pids(marker, pids);
    status(mlf_process_scope_close(s, MLF_PROCESS_CLOSE_CANCEL), MLF_PROCESS_OK, "cancel-close synchronously joins children");
    tree_stopped(pids); check(!test_exists(forbidden), "cancel-close never launches queued children");
    mlf_process_outcome out;
    status(mlf_process_await(s, h, 0, &out), MLF_PROCESS_INVALID_SCOPE, "cancel-close invalidates handles");
}
static void copied_submission(void) {
    char ready[4096], release[4096], output[4096];
    path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release"); path(output, sizeof(output), "copied-argv");
    mlf_process_scope s = scope(1, 2, 4);
    const char *gate[] = {fixture, "gate", ready, release, NULL}; mlf_process_handle first = submit(s, gate);
    char payload[64] = "original argument", outcopy[4096]; strcpy(outcopy, output);
    const char *args[] = {fixture, "echo", payload, NULL}; mlf_process_spec p = spec(args); p.output = outcopy; p.error = outcopy;
    mlf_process_handle copied = submit_spec(s, &p);
    strcpy(payload, "mutated argument"); strcpy(outcopy, "invalid/changed-output"); args[1] = "invalid-command"; p.executable = "invalid/changed-executable";
    test_touch(release); exited(await(s, first), 0); exited(await(s, copied), 0);
    char *text = test_read(output); check(text && strstr(text, "original argument\n") && !strstr(text, "mutated"), "submit copies argument and path buffers"); free(text); close_scope(s);
    /* Copied metadata has a byte limit independent of both queue length and
     * retained result count. Large queued arguments are never passed to exec. */
    s = scope(1, 3, 6);
    path(ready, sizeof(ready), "metadata-running"); path(release, sizeof(release), "metadata-release");
    const char *metadata_gate[] = {fixture, "gate", ready, release, NULL}; (void)submit(s, metadata_gate);
    size_t size = 9U * 1024U * 1024U;
    char *large = malloc(size + 1); check(large != NULL, "allocate metadata-bound fixture");
    memset(large, 'x', size); large[size] = 0;
    const char *large_args[] = {fixture, "echo", large, NULL}; p = spec(large_args);
    mlf_process_handle queued = submit_spec(s, &p), rejected;
    status(mlf_process_submit(s, &p, &rejected), MLF_PROCESS_QUEUE_FULL, "pending metadata byte bound is enforced");
    status(mlf_process_cancel(s, queued, 48), MLF_PROCESS_OK, "cancel oversized queued metadata holder");
    queued = submit_spec(s, &p);
    status(mlf_process_cancel(s, queued, 49), MLF_PROCESS_OK, "metadata bytes released after terminal outcome");
    free(large);
    status(mlf_process_cancel_scope(s, 50), MLF_PROCESS_OK, "cleanup metadata-bound scope"); close_scope(s);
}
static void unicode_and_streams(void) {
    char cwd[4096], log[4096]; path(cwd, sizeof(cwd), "space \xe4\xb8\xad\xe6\x96\x87"); test_mkdir(cwd);
    int n = snprintf(log, sizeof(log), "%s/merged \xe6\x97\xa5\xe5\xbf\x97.txt", cwd); check(n >= 0 && (size_t)n < sizeof(log), "unicode log path");
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {fixture, "echo", "hello space", "quote\"slash\\", "\xe4\xb8\xad\xe6\x96\x87", "", NULL};
    mlf_process_spec p = spec(args); p.cwd = cwd; p.output = p.error = "merged \xe6\x97\xa5\xe5\xbf\x97.txt";
    exited(await(s, submit_spec(s, &p)), 0);
    char *text = test_read(log);
    check(text && strstr(text, "hello space\nquote\"slash\\\n\xe4\xb8\xad\xe6\x96\x87\n\n") && strstr(text, "stderr\n"), "Unicode cwd, literal argv and merged relative streams");
    free(text); close_scope(s);
}
static void redirected_input(void) {
    char input[4096], output[4096]; path(input, sizeof(input), "input"); path(output, sizeof(output), "output");
    FILE *f = test_open(input, "wb"); check(f != NULL, "create input file"); check(fputs("binary\r\ninput\n", f) >= 0 && !fclose(f), "write input file");
    mlf_process_scope s = scope(1, 1, 2); const char *args[] = {fixture, "copy", NULL}; mlf_process_spec p = spec(args);
    p.cwd = scratch; p.input = "input"; p.output = "output";
    exited(await(s, submit_spec(s, &p)), 0);
    char *text = test_read(output); check(text && !strcmp(text, "binary\r\ninput\n"), "binary stdin redirection relative to cwd"); free(text); close_scope(s);
}
static void environment_policy(void) {
    char ready[4096], release[4096]; path(ready, sizeof(ready), "running"); path(release, sizeof(release), "release");
#ifdef _WIN32
    check(SetEnvironmentVariableA("MLF_ASYNC_INHERITED", "parent") != 0, "set inherited environment fixture");
#else
    check(!setenv("MLF_ASYNC_INHERITED", "parent", 1), "set inherited environment fixture");
#endif
    mlf_process_scope s = scope(1, 2, 5);
    const char *inherit[] = {self, "--child", "env-inherited", NULL}; exited(await(s, submit(s, inherit)), 0);
    const char *gate[] = {fixture, "gate", ready, release, NULL}; mlf_process_handle first = submit(s, gate);
    char entry[64] = "MLF_ASYNC_REPLACED=original";
    const char *env[] = {entry, NULL}, *args[] = {self, "--child", "env-replaced", NULL};
    mlf_process_spec p = spec(args); p.environment = MLF_PROCESS_ENV_REPLACE; p.env = env;
    mlf_process_handle second = submit_spec(s, &p); strcpy(entry, "MLF_ASYNC_REPLACED=mutated"); env[0] = "MLF_ASYNC_REPLACED=changed";
    test_touch(release); exited(await(s, first), 0); exited(await(s, second), 0);
    const char *empty[] = {self, "--child", "env-empty", NULL}; p = spec(empty); p.environment = MLF_PROCESS_ENV_REPLACE;
    exited(await(s, submit_spec(s, &p)), 0);
    char bin[4096], executable[4200], basename[80], replacement_path[4200];
    path(bin, sizeof(bin), "replacement-path-bin"); test_mkdir(bin);
    int n = snprintf(basename, sizeof(basename), "mlf-async-path-probe-%ld.exe", test_pid());
    check(n >= 0 && (size_t)n < sizeof(basename), "PATH fixture basename");
    n = snprintf(executable, sizeof(executable), "%s/%s", bin, basename);
    check(n >= 0 && (size_t)n < sizeof(executable), "PATH fixture executable path");
    FILE *from = test_open(fixture, "rb"), *to = test_open(executable, "wb");
    check(from && to, "open PATH fixture binary copy");
    unsigned char buffer[8192]; size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), from)) != 0)
        check(fwrite(buffer, 1, count, to) == count, "copy PATH fixture bytes");
    check(!ferror(from) && !fclose(from) && !fclose(to), "finish PATH fixture copy");
#ifndef _WIN32
    check(!chmod(executable, 0700), "PATH fixture executable permission");
#endif
    n = snprintf(replacement_path, sizeof(replacement_path), "PATH=%s", bin);
    check(n >= 0 && (size_t)n < sizeof(replacement_path), "replacement PATH entry");
    const char *search_env[] = {replacement_path, NULL}, *search_args[] = {basename, "exit", "0", NULL};
    p = spec(search_args); p.environment = MLF_PROCESS_ENV_REPLACE; p.env = search_env;
    exited(await(s, submit_spec(s, &p)), 0); close_scope(s);
}
static void explicit_executable(void) {
    mlf_process_scope s = scope(1, 1, 2);
    const char *args[] = {"arbitrary-literal-argv-zero", "exit", "0", NULL};
    mlf_process_spec p = spec(args); p.executable = fixture;
    exited(await(s, submit_spec(s, &p)), 0); close_scope(s);
}
static void event_order(void) {
    char ready[2][4096], release[2][4096]; mlf_process_handle h[2];
    mlf_process_scope s = scope(2, 2, 4);
    for (unsigned i = 0; i < 2; ++i) {
        char name[32]; snprintf(name, sizeof(name), "ready-%u", i); path(ready[i], sizeof(ready[i]), name);
        snprintf(name, sizeof(name), "release-%u", i); path(release[i], sizeof(release[i]), name);
        const char *args[] = {fixture, "gate", ready[i], release[i], NULL}; h[i] = submit(s, args);
    }
    check(test_await(ready[0], 10) && test_await(ready[1], 10), "both event-order children ready");
    test_touch(release[1]); mlf_process_event e;
    status(mlf_process_wait_next(s, 10, &e), MLF_PROCESS_OK, "next completion waits for released child");
    check(same_handle(e.handle, h[1]), "wait-next returns completion rather than submission order"); exited(e.outcome, 0);
    same_outcome(e.outcome, await(s, h[1]));
    test_touch(release[0]); status(mlf_process_wait_next(s, 10, &e), MLF_PROCESS_OK, "remaining completion");
    check(same_handle(e.handle, h[0]), "remaining event preserves handle identity");
    status(mlf_process_poll(s, &e), MLF_PROCESS_EMPTY, "both events consumed once"); close_scope(s);
}
static void invalid_arguments(void) {
    mlf_process_scope s = 0; mlf_process_options invalid = {0, 1, 2};
    status(mlf_process_scope_create(&invalid, &s), MLF_PROCESS_INVALID_ARGUMENT, "zero jobs rejected");
    s = scope(1, 2, 4);
    const char *args[] = {fixture, "exit", "0", NULL}; mlf_process_spec p = spec(args); mlf_process_handle h;
    p.executable = ""; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "empty executable rejected");
    p = spec(args); p.argv = NULL; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "null argv rejected");
    p = spec(args); p.running_timeout_seconds = -1; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "negative timeout rejected");
    p = spec(args); p.running_timeout_seconds = NAN; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "NaN timeout rejected");
    p = spec(args); p.total_timeout_seconds = INFINITY; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "infinite timeout rejected");
    p = spec(args); p.environment = (mlf_process_environment)99; status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "invalid environment policy rejected");
    const char *bad_env[] = {"NO_EQUALS", NULL};
    p = spec(args); p.environment = MLF_PROCESS_ENV_REPLACE; p.env = bad_env;
    status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "malformed environment rejected");
    const char *invalid_utf8[] = {fixture, "echo", "\xc0\xaf", NULL}; p = spec(invalid_utf8);
    status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "invalid UTF-8 argv rejected");
    size_t size = 16U * 1024U * 1024U + 1;
    char *large = malloc(size + 1); check(large != NULL, "allocate overlarge-spec fixture");
    memset(large, 'x', size); large[size] = 0;
    const char *large_args[] = {fixture, "echo", large, NULL}; p = spec(large_args);
    status(mlf_process_submit(s, &p, &h), MLF_PROCESS_INVALID_ARGUMENT, "single submission metadata byte bound enforced");
    free(large);
    exited(await(s, submit(s, args)), 0); close_scope(s);
}
static void shutdown_joins(void) {
    char one[4096], two[4096], ready[4096], release[4096], forbidden[4096];
    path(one, sizeof(one), "tree-one"); path(two, sizeof(two), "tree-two");
    path(ready, sizeof(ready), "shutdown-pending-pid"); path(release, sizeof(release), "shutdown-pending-release");
    path(forbidden, sizeof(forbidden), "shutdown-forbidden");
    mlf_process_scope queued_scope = scope(1, 2, 3);
    const char *gate[] = {self, "--child", "pid-gate", ready, release, NULL};
    const char *queued[] = {fixture, "signal", forbidden, NULL};
    (void)submit(queued_scope, gate); (void)submit(queued_scope, queued);
    long gate_pid = read_pid(ready);
    mlf_process_scope a = scope(1, 1, 2), b = scope(1, 1, 2);
    const char *one_args[] = {fixture, "tree", one, NULL}, *two_args[] = {fixture, "tree", two, NULL};
    (void)submit(a, one_args); (void)submit(b, two_args);
    long first[3], second[3]; tree_pids(one, first); tree_pids(two, second);
    test_touch(release); stopped(gate_pid);
    mlf_process_shutdown(); tree_stopped(first); tree_stopped(second);
    check(!test_exists(forbidden), "shutdown cancels every scope before pumping admission in any scope");
    mlf_process_event event;
    status(mlf_process_poll(a, &event), MLF_PROCESS_INVALID_SCOPE, "shutdown closes first scope");
    status(mlf_process_poll(b, &event), MLF_PROCESS_INVALID_SCOPE, "shutdown closes second scope");
    status(mlf_process_poll(queued_scope, &event), MLF_PROCESS_INVALID_SCOPE, "shutdown closes queued scope");
    mlf_process_shutdown();
}

struct scenario { const char *name; void (*run)(void); };
static const struct scenario scenarios[] = {
    {"empty-scope", empty_scope}, {"dynamic-A-to-B-with-C", dynamic_submission},
    {"jobs-one-dynamic", serial_dynamic}, {"admission-and-queue-bound", admission_bound},
    {"retained-outcome-bound", retained_limit}, {"repeat-await-once-event", repeat_await},
    {"launch-versus-126-127", launch_and_exit}, {"nonzero-is-data", nonzero_is_data},
    {"cancel-queued", cancel_queued}, {"cancel-running-tree", cancel_running}, {"request-cancel", request_cancel},
    {"cancel-scope", cancel_scope}, {"cancel-completed", cancel_completed},
    {"running-timeout", running_timeout}, {"queued-total-timeout", queued_timeout},
    {"running-timeout-excludes-queue", running_timeout_excludes_queue}, {"wait-bound", wait_bound},
    {"no-late-resurrection", no_resurrection}, {"handle-validation", handle_validation},
    {"large-stdout-and-stderr", large_output}, {"abrupt-owner-death", owner_death},
    {"normal-close-joins", normal_close_joins}, {"cancel-close-joins", cancel_close_joins},
    {"submission-copies-data", copied_submission}, {"unicode-argv-and-streams", unicode_and_streams},
    {"redirected-input", redirected_input}, {"environment-policy", environment_policy},
    {"explicit-executable", explicit_executable}, {"completion-event-order", event_order},
    {"invalid-arguments", invalid_arguments}, {"shutdown-joins-all-scopes", shutdown_joins}
};
static int child_mode(int argc, char **argv) {
    if (argc == 5 && !strcmp(argv[2], "pid-gate")) {
        test_write_pid(argv[3]); return test_await(argv[4], 20) ? 0 : 24;
    }
    if (argc != 3) return 64;
    if (!strcmp(argv[2], "large-output")) {
        char out[8192], err[8192]; memset(out, 'o', sizeof(out)); memset(err, 'e', sizeof(err));
        for (unsigned i = 0; i < 256; ++i) {
            if (fwrite(out, 1, sizeof(out), stdout) != sizeof(out) || fwrite(err, 1, sizeof(err), stderr) != sizeof(err)) return 26;
        }
        return fflush(stdout) || fflush(stderr) ? 26 : 0;
    }
    if (!strcmp(argv[2], "env-inherited")) {
        const char *value = getenv("MLF_ASYNC_INHERITED"); return value && !strcmp(value, "parent") ? 0 : 23;
    }
    if (!strcmp(argv[2], "env-replaced")) {
        const char *value = getenv("MLF_ASYNC_REPLACED"); return value && !strcmp(value, "original") && !getenv("MLF_ASYNC_INHERITED") ? 0 : 23;
    }
    if (!strcmp(argv[2], "env-empty")) return !getenv("MLF_ASYNC_INHERITED") && !getenv("MLF_ASYNC_REPLACED") ? 0 : 23;
    return 64;
}
static int tests(int argc, char **argv) {
    self = argv[0];
    if (argc >= 2 && !strcmp(argv[1], "--child")) return child_mode(argc, argv);
    if (argc == 5 && !strcmp(argv[1], "--owner")) {
        fixture = argv[2]; mlf_process_scope a = scope(1, 1, 2), b = scope(1, 1, 2);
        const char *one[] = {fixture, "tree", argv[3], NULL}, *two[] = {fixture, "tree", argv[4], NULL};
        (void)submit(a, one); (void)submit(b, two);
        for (;;) test_pause();
    }
    if (argc == 5 && !strcmp(argv[1], "--case")) {
        fixture = argv[3]; int n = snprintf(scratch, sizeof(scratch), "%s/%s", argv[4], argv[2]);
        check(n >= 0 && (size_t)n < sizeof(scratch), "scenario path length"); test_mkdir(scratch);
        for (unsigned i = 0; i < sizeof(scenarios) / sizeof(scenarios[0]); ++i) {
            if (!strcmp(argv[2], scenarios[i].name)) { scenarios[i].run(); return 0; }
        }
        return 64;
    }
    if (argc != 3) {
        fprintf(stderr, "usage: process-supervisor-tests BUILD_RUNNER_FIXTURE OUTPUT_DIRECTORY\n"); return 64;
    }
    fixture = argv[1]; test_mkdir(argv[2]);
    /* PID namespaces may reuse the same numeric PID across executor calls. */
    int n = snprintf(scratch, sizeof(scratch), "%s/process-supervisor-%ld-%llu", argv[2], test_pid(),
                     (unsigned long long)(test_now() * 1000000.0));
    check(n >= 0 && (size_t)n < sizeof(scratch), "scratch path length"); test_mkdir(scratch);
    for (unsigned i = 0; i < sizeof(scenarios) / sizeof(scenarios[0]); ++i) {
        char *args[] = {(char *)self, "--case", (char *)scenarios[i].name, (char *)fixture, scratch, NULL};
        int result = test_wait(test_spawn(args), 45);
        if (result) {
            fprintf(stderr, "process supervisor scenario %s failed with exit %d\n", scenarios[i].name, result); return 1;
        }
        printf("ok %s\n", scenarios[i].name); fflush(stdout); ++checks;
    }
    printf("%u native process supervisor tests passed\n", checks); return 0;
}
TEST_MAIN(tests)
