/* The existing handwritten wait/readiness oracle remains independent. */
#include "../process-readiness/darwin/Faults.c"
#include <spawn.h>
#include <crt_externs.h>
static const posix_spawnattr_t *owned;
static int group,flags;
static const posix_spawn_file_actions_t *owned_actions;
static int spawn_is(const char *name) {
    const char *selected=getenv("MLF_SPAWN_FAULT");
    if(!selected)abort();return !strcmp(selected,name);
}
pid_t mlf_mock_getpgrp(void) {return 4242;}
int mlf_mock_posix_spawnattr_init(posix_spawnattr_t *a) {
    event("init");if(owned)abort();
    if(spawn_is("init-fail"))return ENOMEM;
    memset(a,0,sizeof(*a));owned=a;return 0;
}
int mlf_mock_posix_spawnattr_setpgroup(posix_spawnattr_t *a,pid_t p) {
    event("group");if(a!=owned || p || group++)abort();
    return spawn_is("group-fail")?EINVAL:0;
}
int mlf_mock_posix_spawnattr_setflags(posix_spawnattr_t *a,short f) {
    event("flags");if(a!=owned || group!=1 || flags++ || f!=POSIX_SPAWN_SETPGROUP)abort();
    return spawn_is("flags-fail")?EINVAL:0;
}
int mlf_mock_posix_spawnattr_destroy(posix_spawnattr_t *a) {
    event("destroy");if(a!=owned)abort();owned=NULL;
    return spawn_is("destroy-fail")?EINVAL:0;
}
int mlf_mock_posix_spawn_file_actions_init(posix_spawn_file_actions_t *actions) {
    event("actions-init"); if(owned_actions)abort();
    if(spawn_is("actions-init-fail"))return ENOMEM;
    owned_actions=actions;return 0;
}
int mlf_mock_posix_spawn_file_actions_addchdir(posix_spawn_file_actions_t *actions,const char *directory) {
    event("chdir"); if(actions!=owned_actions || strcmp(directory,"."))abort();
    return spawn_is("chdir-fail")?ENOENT:0;
}
int mlf_mock_posix_spawn_file_actions_destroy(posix_spawn_file_actions_t *actions) {
    event("actions-destroy");if(actions!=owned_actions)abort();
    owned_actions=NULL;return 0;
}
int mlf_mock_posix_spawnp(pid_t *pid,const char *file,
    const posix_spawn_file_actions_t *actions,const posix_spawnattr_t *a,
    char *const argv[],char *const env[]) {
    event("spawn");
    if(a!=owned || actions!=owned_actions || strcmp(file,"/usr/bin/true") || strcmp(argv[0],file) ||
       argv[1] || env!=*_NSGetEnviron())abort();
    const char *scope=getenv("MLF_BUILD_SCOPE");
    int inherited=scope && !strcmp(scope,"4242");
    if(group!=!inherited || flags!=!inherited)abort();
    if(spawn_is("spawn-fail") || spawn_is("spawn-resource-fail")) {
        *pid=0; /* Must not accidentally enter the child branch after failure. */
        return spawn_is("spawn-fail")?ENOEXEC:EAGAIN;
    }
    *pid=4242;return 0;
}
