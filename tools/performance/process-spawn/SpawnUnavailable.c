/* Retain every old readiness fault expectation by exercising fork fallback. */
#include <spawn.h>
#include <errno.h>
int mlf_spawn_unavailable(pid_t *pid,const char *file,
    const posix_spawn_file_actions_t *actions,const posix_spawnattr_t *attributes,
    char *const argv[],char *const env[]) {
    (void)pid;(void)file;(void)actions;(void)attributes;(void)argv;(void)env;
    return ENOSYS;
}
