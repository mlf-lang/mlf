/* Session membership survives reparenting and subprocess-created groups. This
 * covers seed compilers whose older runProcess does not know MLF_BUILD_SCOPE.
 * Task programs must not deliberately escape their lifetime with setsid(). */
#ifndef MLF_PROCESS_SUPERVISOR_POSIX_H
#define MLF_PROCESS_SUPERVISOR_POSIX_H
#ifdef __APPLE__
#include <libproc.h>
#else
#include <dirent.h>
#endif
struct mlf_ps_process_sample { pid_t pid, session; uint64_t rss; };
static struct mlf_ps_process_sample *mlf_ps_process_samples(size_t *count,int memory) {
    *count=0; size_t capacity=256; struct mlf_ps_process_sample *samples=mlf_ps_checked_alloc(capacity,sizeof(*samples));
    if(!samples) return NULL;
#ifdef __APPLE__
    int needed=proc_listallpids(NULL,0); if(needed<1) { free(samples); return NULL; }
    size_t available=(size_t)needed+256; pid_t *ids=mlf_ps_checked_alloc(available,sizeof(pid_t));
    if(!ids || available>(size_t)INT_MAX/sizeof(pid_t)) { free(ids); free(samples); return NULL; }
    int found=proc_listallpids(ids,(int)(available*sizeof(pid_t)));
    if(found<0 || (size_t)found>=available) { free(ids); free(samples); return NULL; }
    for(int i=0;i<found;++i) { pid_t pid=ids[i];
#else
    DIR *directory=opendir("/proc"); if(!directory) { free(samples); return NULL; }
    struct dirent *entry;
    while((entry=readdir(directory))) {
        char *end; long value=strtol(entry->d_name,&end,10); if(!*entry->d_name || *end || value<=0 || value>INT_MAX) continue;
        pid_t pid=(pid_t)value;
#endif
        if(pid<=0) continue;
        pid_t session=getsid(pid); if(session<0) continue;
        if(*count==capacity) {
            if(capacity>SIZE_MAX/2/sizeof(*samples)) goto no_memory;
            capacity*=2; void *next=realloc(samples,capacity*sizeof(*samples));
            if(!next) goto no_memory;
            samples=next;
        }
        struct mlf_ps_process_sample sample={pid,session,0};
        if(memory) {
#ifdef __APPLE__
            struct proc_taskinfo info;
            if(proc_pidinfo(pid,PROC_PIDTASKINFO,0,&info,sizeof(info))==sizeof(info)) sample.rss=info.pti_resident_size;
#else
            char path[80]; snprintf(path,sizeof(path),"/proc/%ld/statm",(long)pid); FILE *file=fopen(path,"r");
            unsigned long ignored,resident;
            if(file) { if(fscanf(file,"%lu %lu",&ignored,&resident)==2) sample.rss=(uint64_t)resident*(uint64_t)sysconf(_SC_PAGESIZE); fclose(file); }
#endif
        }
        samples[(*count)++]=sample;
    }
#ifdef __APPLE__
    free(ids);
#else
    closedir(directory);
#endif
    return samples;
no_memory:
#ifdef __APPLE__
    free(ids);
#else
    closedir(directory);
#endif
    free(samples); errno=ENOMEM; return NULL;
}
static int mlf_ps_stop_session(pid_t session) {
    /* Freeze every live member before killing. Repeat the snapshot so a fork
     * racing the first enumeration cannot leave a new process group alive. */
    int ok=1,saved=0;
    for(unsigned pass=0;pass<3;++pass) {
        size_t count; struct mlf_ps_process_sample *samples=mlf_ps_process_samples(&count,0);
        if(!samples) return 0;
        size_t members=0;
        for(size_t i=0;i<count;++i) if(samples[i].session==session) {
            ++members;
            if(kill(samples[i].pid,SIGSTOP) && errno!=ESRCH) { ok=0; saved=errno; }
        }
        for(size_t i=0;i<count;++i) if(samples[i].session==session && kill(samples[i].pid,SIGKILL) && errno!=ESRCH) { ok=0; saved=errno; }
        free(samples); if(!members) break;
    }
    if(!ok) errno=saved;
    return ok;
}
#endif
