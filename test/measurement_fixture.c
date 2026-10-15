#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
  if (argc != 2) return 64;
  if (!strcmp(argv[1], "fail")) return 9;
  if (!strcmp(argv[1], "timeout")) { sleep(10); return 0; }
  if (!strcmp(argv[1], "large")) {
    size_t n = 64 * 1024 * 1024;
    volatile unsigned char *bytes = malloc(n);
    if (!bytes) return 70;
    for (size_t i = 0; i < n; i += 4096) bytes[i] = (unsigned char)i;
    sleep(1);
    free((void *)bytes);
    return 0;
  }
  if (!strcmp(argv[1], "descendants")) {
    pid_t pid = fork();
    if (pid < 0) return 70;
    if (!pid) { sleep(30); return 0; }
    printf("%ld\n", (long)pid); fflush(stdout);
    sleep(30);
    return 0;
  }
  if (!strcmp(argv[1], "small")) return 0;
  return 64;
}
