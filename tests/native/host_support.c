/* Transport-only support for native MLF harnesses: environment names and
 * per-child wall/RSS measurements. Assertions and orchestration are in MLF. */
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE 1
#define _DEFAULT_SOURCE 1
#include <errno.h>
#include <stdint.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
extern char **environ;
static double now(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(70); }
  return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}
static volatile sig_atomic_t interrupted;
static void signal_handler(int sig) { interrupted = sig; }
static char *field(char **cursor, char *end) {
  if (*cursor >= end) { fputs("truncated process specification\n", stderr); exit(64); }
  char *value = *cursor;
  char *zero = memchr(value, 0, (size_t)(end - value));
  if (!zero) exit(64);
  *cursor = zero + 1;
  return value;
}
/* Dependencies are supplied by the native MLF caller. Validate the complete
 * acyclic specification before starting any children. No compiler policy here. */
static int group(double bound, const char *specification, int pipeline) {
  FILE *input = fopen(specification, "rb");
  if (!input || fseek(input, 0, SEEK_END)) return 64;
  long length = ftell(input);
  if (length < 1 || length > 100000000 || fseek(input, 0, SEEK_SET)) return 64;
  char *bytes = malloc((size_t)length);
  if (!bytes || fread(bytes, 1, (size_t)length, input) != (size_t)length) return 64;
  fclose(input);
  char *cursor = bytes, *end = bytes + length;
  long count = strtol(field(&cursor, end), NULL, 10);
  if (count < 1 || count > 64 || bound <= 0) return 64;
  struct command { char *cwd, *in, *out, *err, **args; uint64_t dependencies; } commands[64] = {0};
  for (long i = 0; i < count; ++i) {
    if (pipeline) {
      long dependencies = strtol(field(&cursor, end), NULL, 10);
      if (dependencies < 0 || dependencies > i) return 64;
      for (long j = 0; j < dependencies; ++j) {
        long dependency = strtol(field(&cursor, end), NULL, 10);
        if (dependency < 0 || dependency >= i) return 64;
        uint64_t bit = UINT64_C(1) << dependency;
        if (commands[i].dependencies & bit) return 64;
        commands[i].dependencies |= bit;
      }
    }
    commands[i].cwd = field(&cursor, end); commands[i].in = field(&cursor, end);
    commands[i].out = field(&cursor, end); commands[i].err = field(&cursor, end);
    long argc = strtol(field(&cursor, end), NULL, 10);
    if (argc < 1 || argc > 1024) return 64;
    commands[i].args = calloc((size_t)argc + 1, sizeof(char *));
    if (!commands[i].args) return 70;
    for (long a = 0; a < argc; ++a) commands[i].args[a] = field(&cursor, end);
  }
  if (cursor != end) return 64;
  pid_t pids[64] = {0}; int live[64] = {0}, statuses[64] = {0};
  double started[64] = {0}, finished[64] = {0}, cpu[64] = {0}; long rss[64] = {0};
  signal(SIGTERM, signal_handler); signal(SIGINT, signal_handler);
  double start = now();
  uint64_t completed = 0;
  int remaining = (int)count, running = 0, maximum = 0, failure = 0;
  while (remaining) {
    for (long i = 0; i < count && !failure && !interrupted; ++i) {
      if (pids[i] || (commands[i].dependencies & completed) != commands[i].dependencies) continue;
      started[i] = now() - start;
      pid_t pid = fork();
      if (pid < 0) { failure = 71; break; }
      if (!pid) {
        if (setpgid(0, 0) && getpgrp() != getpid()) _exit(71);
        if (*commands[i].cwd && chdir(commands[i].cwd)) _exit(72);
        if (*commands[i].in && !freopen(commands[i].in, "rb", stdin)) _exit(72);
        if (!freopen(commands[i].out, "wb", stdout) || !freopen(commands[i].err, "wb", stderr)) _exit(72);
        execvp(commands[i].args[0], commands[i].args); _exit(errno == ENOENT ? 127 : 126);
      }
      (void)setpgid(pid, pid);
      pids[i] = pid; live[i] = 1; ++running;
      if (running > maximum) maximum = running;
    }
    for (long i = 0; i < count; ++i) if (live[i]) {
      int status; struct rusage usage;
      pid_t done = wait4(pids[i], &status, WNOHANG, &usage);
      if (done == pids[i]) {
        live[i] = 0; --remaining; --running;
        statuses[i] = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        finished[i] = now() - start;
        cpu[i] = (double)usage.ru_utime.tv_sec + (double)usage.ru_utime.tv_usec / 1e6 +
          (double)usage.ru_stime.tv_sec + (double)usage.ru_stime.tv_usec / 1e6;
#ifdef __APPLE__
        rss[i] = usage.ru_maxrss;
#else
        rss[i] = usage.ru_maxrss * 1024L;
#endif
        if (statuses[i]) failure = statuses[i];
        else completed |= UINT64_C(1) << i;
      } else if (done < 0 && errno != EINTR) { failure = 71; }
    }
    if ((failure || interrupted || now() - start >= bound) && remaining) {
      if (!failure) failure = interrupted ? 128 + interrupted : 124;
      for (long i = 0; i < count; ++i) if (live[i]) (void)kill(-pids[i], SIGKILL);
      for (long i = 0; i < count; ++i) {
        if (live[i]) {
          int status;
          while (waitpid(pids[i], &status, 0) < 0) if (errno != EINTR) return 71;
          live[i] = 0; statuses[i] = failure; finished[i] = now() - start;
        } else if (!pids[i]) statuses[i] = 125;
      }
      remaining = 0;
    }
    if (remaining) { struct timespec pause = {0, 1000000}; nanosleep(&pause, NULL); }
  }
  for (long i = 0; i < count; ++i) if (pids[i]) (void)kill(-pids[i], SIGKILL);
  int status;
  int children = waitpid(-1, &status, WNOHANG) < 0 && errno == ECHILD ? 0 : 1;
  printf("{\"exit_code\":%d,\"wall_seconds\":%.9f,\"remaining_children\":%d,\"maximum_parallel_compilers\":%d,\"stages\":[", failure, now() - start, children, maximum);
  for (long i = 0; i < count; ++i) {
    if (i) putchar(',');
    printf("{\"exit_code\":%d,\"started_seconds\":%.9f,\"finished_seconds\":%.9f,\"wall_seconds\":%.9f,\"cpu_seconds\":%.9f,\"peak_rss_bytes\":%ld,\"pid\":%ld}", statuses[i], started[i], finished[i], finished[i] - started[i], cpu[i], rss[i], (long)pids[i]);
    free(commands[i].args);
  }
  puts("]}"); free(bytes); return 0;
}
int main(int argc, char **argv) {
  if (argc == 4 && !strcmp(argv[1], "group")) return group(strtod(argv[2], NULL), argv[3], 0);
  if (argc == 4 && !strcmp(argv[1], "pipeline")) return group(strtod(argv[2], NULL), argv[3], 1);
  if (argc == 2 && strcmp(argv[1], "env-names") == 0) {
    for (char **p = environ; *p; ++p) {
      const char *end = strchr(*p, '=');
      if (end) { fwrite(*p, 1, (size_t)(end - *p), stdout); fputc('\n', stdout); }
    }
    return 0;
  }
  if (argc < 7 || strcmp(argv[1], "measure")) return 64;
  char *end;
  long bound = strtol(argv[2], &end, 10);
  if (*end || bound < 1 || bound > 2147483647L) return 64;
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  double start = now();
  pid_t pid = fork();
  if (pid < 0) return 71;
  if (!pid) {
    if (setpgid(0, 0) && getpgrp() != getpid()) _exit(71);
    if (*argv[3] && !freopen(argv[3], "rb", stdin)) _exit(72);
    if (!freopen(argv[4], "wb", stdout) || !freopen(argv[5], "wb", stderr)) _exit(72);
    execvp(argv[6], argv + 6);
    _exit(errno == ENOENT ? 127 : 126);
  }
  /* Either side may win; a child that has exec'd already owns its group. */
  (void)setpgid(pid, pid);
  int status = 0, timed_out = 0;
  struct rusage usage;
  memset(&usage, 0, sizeof usage);
  for (;;) {
    pid_t done = wait4(pid, &status, WNOHANG, &usage);
    if (done == pid) break;
    if (done < 0 && errno != EINTR) return 71;
    if (interrupted || now() - start >= (double)bound) {
      timed_out = !interrupted;
      (void)kill(-pid, SIGKILL);
      while (wait4(pid, &status, 0, &usage) < 0) { if (errno != EINTR) return 71; }
      break;
    }
    struct timespec pause = {0, 1000000};
    nanosleep(&pause, NULL);
  }
  /* Reap the measured leader, and stop any surviving descendants. */
  (void)kill(-pid, SIGKILL);
  int code = timed_out ? 124 : interrupted ? 128 + interrupted :
    WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
#ifdef __APPLE__
  long rss = usage.ru_maxrss;
#else
  long rss = usage.ru_maxrss * 1024L;
#endif
  double cpu_seconds = (double)usage.ru_utime.tv_sec + (double)usage.ru_utime.tv_usec / 1e6 +
    (double)usage.ru_stime.tv_sec + (double)usage.ru_stime.tv_usec / 1e6;
  int termination_signal = !timed_out && !interrupted && WIFSIGNALED(status) ? WTERMSIG(status) : 0;
  printf("{\"exit_code\":%d,\"timed_out\":%s,\"interrupted\":%s,\"termination_signal\":%d,\"wall_seconds\":%.9f,\"cpu_seconds\":%.9f,\"peak_rss_bytes\":%ld,\"pid\":%ld}\n",
         code, timed_out ? "true" : "false", interrupted ? "true" : "false", termination_signal, now() - start, cpu_seconds, rss, (long)pid);
  return 0;
}
