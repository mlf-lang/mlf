/* Deterministic child-side transport only. MLF owns all assertions about the
 * supervisor. No shell commands, process DAG, or supervisor implementation. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int exists(const char *path) { return access(path, F_OK) == 0; }
static void write_text(const char *path, const char *text) {
    size_t size = strlen(path) + 64;
    char *temporary = malloc(size);
    if (!temporary) exit(90);
    snprintf(temporary, size, "%s.%ld.tmp", path, (long)getpid());
    FILE *file = fopen(temporary, "w");
    if (!file) exit(90);
    if (fputs(text, file) < 0 || fclose(file) || rename(temporary, path)) exit(90);
    free(temporary);
}
static void wait_for(const char *path) {
    struct timespec delay = {0, 1000000};
    for (int i = 0; i < 20000; ++i) {
        if (exists(path)) return;
        nanosleep(&delay, NULL);
    }
    fputs("child gate timed out\n", stderr);
    exit(91);
}
static int equal_env(const char *name, const char *value) {
    const char *actual = getenv(name);
    return actual && !strcmp(actual, value);
}
int main(int argc, char **argv) {
    if (argc < 2) return 92;
    if (!strcmp(argv[1], "exit") && argc == 3) return atoi(argv[2]);
    if (!strcmp(argv[1], "mark") && argc == 3) {
        write_text(argv[2], "launched\n"); return 0;
    }
    if (!strcmp(argv[1], "hold") && argc == 4) {
        char pid[64]; snprintf(pid, sizeof(pid), "%ld\n", (long)getpid());
        write_text(argv[2], pid);
        wait_for(argv[3]);
        puts("released"); return 0;
    }
    if (!strcmp(argv[1], "after-start") && argc == 3) {
        wait_for(argv[2]); puts("A result"); return 23;
    }
    if (!strcmp(argv[1], "dependent") && argc == 5) {
        if (strcmp(argv[2], "23") || !exists(argv[3]) || exists(argv[4])) return 93;
        puts("B saw A=23 while C was waiting");
        write_text(argv[4], "release\n"); return 0;
    }
    if (!strcmp(argv[1], "assert-gone") && argc == 3) {
        long pid = 0; FILE *file = fopen(argv[2], "r");
        if (!file || fscanf(file, "%ld", &pid) != 1 || pid <= 0) return 94;
        fclose(file);
        errno = 0;
        return kill((pid_t)pid, 0) == -1 && errno == ESRCH ? 0 : 95;
    }
    if (!strcmp(argv[1], "transport") && argc == 3) {
        const char *literal = "space ; $() ' \" \\ \t\nλ";
        if (strcmp(argv[2], literal)) return 96;
        puts("argv-exact");
        if (!equal_env("ASYNC_VALUE", "line one\nλ=x") ||
            !equal_env("ASYNC_EMPTY", "") || getenv("ASYNC_PARENT_ONLY")) return 97;
        puts("env-exact");
        if (!exists("cwd.marker")) return 98;
        puts("cwd-exact");
        char input[128] = {0};
        if (!fgets(input, sizeof(input), stdin) || strcmp(input, "stdin λ\n")) return 99;
        puts("stdin-exact"); fputs("stderr λ\n", stderr); return 0;
    }
    if (!strcmp(argv[1], "environment") && argc == 2) {
        const char *value = getenv("ASYNC_SNAPSHOT");
        if (!value) return 100;
        puts(value); return 0;
    }
    if (!strcmp(argv[1], "large-logs") && argc == 2) {
        for (int i = 0; i < 262144; ++i) {
            if (fputc('o', stdout) == EOF || fputc('e', stderr) == EOF) return 101;
        }
        return 0;
    }
    return 102;
}
