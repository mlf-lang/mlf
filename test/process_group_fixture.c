/* Fault injection only. The MLF harness checks status and process cleanup.
 * Simulate Darwin rejecting a redundant setpgid after its required state has
 * already been established. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <sys/types.h>
#include <unistd.h>
#undef setpgid
extern int setpgid(pid_t, pid_t);

int mlf_test_setpgid(pid_t pid, pid_t group) {
    int result = setpgid(pid, group);
    if (result == 0) {
        errno = EPERM;
        return -1;
    }
    return result;
}
