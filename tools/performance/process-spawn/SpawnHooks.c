/* Diagnostic only: count actual kernel spawn/fork calls without changing them. */
#include <spawn.h>
#include <unistd.h>
#include <stdint.h>
#include <stdlib.h>
#include <dirent.h>
static int64_t attempted,succeeded,forked,initialized,destroyed,own_group,inherited_group;
pid_t mlf_spawn_fork(void) {++forked;return fork();}
int mlf_spawn_init(posix_spawnattr_t *a) {++initialized;return posix_spawnattr_init(a);}
int mlf_spawn_destroy(posix_spawnattr_t *a) {++destroyed;return posix_spawnattr_destroy(a);}
int mlf_spawn_call(pid_t *pid,const char *file,const posix_spawn_file_actions_t *actions,
    const posix_spawnattr_t *a,char *const argv[],char *const env[]) {
    ++attempted;short flags;pid_t group;
    if(actions || !a || posix_spawnattr_getflags(a,&flags) || posix_spawnattr_getpgroup(a,&group))abort();
    if(flags==POSIX_SPAWN_SETPGROUP && !group)++own_group;
    else if(!flags)++inherited_group;else abort();
    int code=posix_spawnp(pid,file,actions,a,argv,env);if(!code)++succeeded;return code;
}
int64_t mlf_spawn_stat(int index) {
    int64_t counters[]={attempted,succeeded,forked,initialized,destroyed,own_group,inherited_group};
    if(index<0 || index>=7)abort();return counters[index];
}
int mlf_spawn_fd_count(void) {
    DIR *d=opendir("/dev/fd");if(!d)return -1;int n=0;struct dirent *p;
    while((p=readdir(d)))if(p->d_name[0]!='.')++n;
    if(closedir(d))return -1;return n;
}
