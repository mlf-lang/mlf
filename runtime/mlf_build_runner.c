/* Supported build-process transport. Package policy belongs to MLF.
 *
 * Invocation: mlf-build-runner PLAN RESULT
 * PLAN is a sequence of UTF-8 NUL-terminated fields:
 *   MLF_BUILD_PLAN, 1, invocation-id, jobs, task-count,
 *   (task-id, timeout-seconds, dependency-count, dependency-ids...,
 *    cwd, stdin, stdout, stderr, argc, argv...)...
 * Empty stream paths inherit. Equal stdout/stderr paths share one descriptor.
 * The complete, acyclic plan is validated before opening output streams or
 * starting work. RESULT is atomically published JSON, bound to the exact plan
 * bytes by SHA-256. Exit zero requires every task to have succeeded.
 */
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE 1
#define _DEFAULT_SOURCE 1
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <time.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <wchar.h>
#include <io.h>
#include <fcntl.h>
#include "mlf_windows_path.h"
#else
#include <fcntl.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/prctl.h>
#endif
#endif
#include "mlf_build_runner_hash.h"
#define MLF_PROCESS_STATIC_ADAPTER
#define MLF_PROCESS_SUPERVISOR_IMPLEMENTATION
#include "mlf_process_supervisor.h"

#define MAX_PLAN_BYTES (256U * 1024U * 1024U)
#define MAX_TASKS 100000U
#define MAX_ARGUMENTS 65536U
static volatile sig_atomic_t interrupted;
static void on_signal(int sig) { interrupted = sig; }
static void *checked_alloc(size_t count, size_t size) {
    if (size && count > SIZE_MAX/size) return NULL;
    return calloc(count, size);
}
static int utf8(const unsigned char *p, size_t size) {
    size_t i=0;
    while(i<size) {
        unsigned a=p[i++], n; uint32_t value, minimum;
        if(a<128) continue;
        if(a>=0xc2 && a<=0xdf) { n=1; value=a&31; minimum=0x80; }
        else if(a>=0xe0 && a<=0xef) { n=2; value=a&15; minimum=0x800; }
        else if(a>=0xf0 && a<=0xf4) { n=3; value=a&7; minimum=0x10000; }
        else return 0;
        if(n>size-i) return 0;
        while(n--) { unsigned b=p[i++]; if((b&0xc0)!=0x80) return 0; value=(value<<6)|(b&63); }
        if(value<minimum || value>0x10ffff || (value>=0xd800 && value<=0xdfff)) return 0;
    }
    return 1;
}
static char *field(char **cursor, char *end) {
    if(*cursor>=end) return NULL;
    char *value=*cursor, *zero=memchr(value,0,(size_t)(end-value));
    if(!zero) return NULL;
    *cursor=zero+1; return value;
}
static int number(const char *text, unsigned long maximum, unsigned long *value) {
    if(!text || !*text) return 0;
    unsigned long n=0;
    for(const unsigned char *p=(const unsigned char *)text; *p; ++p) {
        if(*p<'0' || *p>'9' || (unsigned long)(*p-'0')>maximum || n>(maximum-(*p-'0'))/10) return 0;
        n=n*10+(*p-'0');
    }
    *value=n; return 1;
}
enum state { PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED, BLOCKED };
static const char *state_names[]={"pending","running","succeeded","failed","cancelled","blocked"};
struct task {
    char *id, *cwd, *input, *output, *error, **argv, **dependency_ids;
    size_t dependency_count, *dependencies;
    unsigned long timeout;
    enum state state;
    int exit_code;
    uint64_t pid, rss, aggregate_rss;
    double started, finished, cpu;
    struct mlf_ps_process native;
};
struct plan { char *bytes, *invocation; size_t count; unsigned long jobs; struct task *tasks; char digest[65]; };
#ifdef _WIN32
static wchar_t *wide(const char *s) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,NULL,0);
    wchar_t *out=n ? checked_alloc((size_t)n,sizeof(wchar_t)) : NULL;
    if(out && !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,out,n)) { free(out); out=NULL; }
    return out;
}
static FILE *open_file(const char *path, const char *mode) {
    wchar_t *w=wide(path), *p=w ? mlf_windows_path(w) : NULL, *m=wide(mode);
    FILE *f=p && m ? _wfopen(p,m) : NULL; free(w); free(p); free(m); return f;
}
static double now(void) { return (double)GetTickCount64()/1000.0; }
static void pause_loop(void) { Sleep(5); }
#else
static FILE *open_file(const char *path, const char *mode) { return fopen(path,mode); }
static double now(void) { struct timespec t; if(clock_gettime(CLOCK_MONOTONIC,&t)) abort(); return (double)t.tv_sec+(double)t.tv_nsec/1e9; }
static void pause_loop(void) { struct timespec t={0,5000000}; nanosleep(&t,NULL); }
#endif
static void free_plan(struct plan *p) {
    for(size_t i=0;i<p->count;++i) { free(p->tasks[i].argv); free(p->tasks[i].dependencies); free(p->tasks[i].dependency_ids); }
    free(p->tasks); free(p->bytes);
}
static int read_plan(const char *path, struct plan *p) {
    FILE *f=open_file(path,"rb");
    if(!f) return 0;
    if(fseek(f,0,SEEK_END)) { fclose(f); return 0; }
    long n=ftell(f);
    if(n<1 || (unsigned long)n>MAX_PLAN_BYTES || fseek(f,0,SEEK_SET)) { fclose(f); return 0; }
    p->bytes=checked_alloc((size_t)n,1);
    int valid=p->bytes && fread(p->bytes,1,(size_t)n,f)==(size_t)n && !ferror(f);
    if(fclose(f)) valid=0;
    if(!valid || !utf8((unsigned char *)p->bytes,(size_t)n)) return 0;
    build_hash((unsigned char *)p->bytes,(size_t)n,p->digest);
    char *cursor=p->bytes, *end=cursor+n, *magic=field(&cursor,end), *version=field(&cursor,end);
    if(!magic || strcmp(magic,"MLF_BUILD_PLAN") || !version || strcmp(version,"1")) return 0;
    p->invocation=field(&cursor,end);
    unsigned long count;
    if(!p->invocation || !*p->invocation || !number(field(&cursor,end),MAX_TASKS,&p->jobs) || !p->jobs ||
       !number(field(&cursor,end),MAX_TASKS,&count)) return 0;
    p->tasks=checked_alloc(count,sizeof(struct task));
    if(count && !p->tasks) return 0;
    p->count=count;
    for(size_t i=0;i<p->count;++i) {
        struct task *t=p->tasks+i; unsigned long dependencies, argc;
        t->id=field(&cursor,end);
        if(!t->id || !*t->id || !number(field(&cursor,end),INT_MAX,&t->timeout) || !t->timeout ||
           !number(field(&cursor,end),count,&dependencies)) return 0;
        for(size_t j=0;j<i;++j) if(!strcmp(t->id,p->tasks[j].id)) return 0;
        t->dependency_count=dependencies;
        t->dependencies=checked_alloc(dependencies,sizeof(size_t));
        t->dependency_ids=checked_alloc(dependencies,sizeof(char *));
        if(dependencies && (!t->dependencies || !t->dependency_ids)) return 0;
        for(size_t j=0;j<dependencies;++j) if(!(t->dependency_ids[j]=field(&cursor,end))) return 0;
        t->cwd=field(&cursor,end); t->input=field(&cursor,end); t->output=field(&cursor,end); t->error=field(&cursor,end);
        if(!t->cwd || !t->input || !t->output || !t->error || !number(field(&cursor,end),MAX_ARGUMENTS,&argc) || !argc) return 0;
        t->argv=checked_alloc(argc+1,sizeof(char *)); if(!t->argv) return 0;
        for(size_t j=0;j<argc;++j) if(!(t->argv[j]=field(&cursor,end))) return 0;
        if(!*t->argv[0]) return 0;
    }
    if(cursor!=end) return 0;
    for(size_t i=0;i<p->count;++i) for(size_t j=0;j<p->tasks[i].dependency_count;++j) {
        struct task *t=p->tasks+i; size_t k=0;
        while(k<p->count && strcmp(t->dependency_ids[j],p->tasks[k].id)) ++k;
        if(k==p->count || k==i) return 0;
        for(size_t d=0;d<j;++d) if(t->dependencies[d]==k) return 0;
        t->dependencies[j]=k;
    }
    /* Kahn validation also accepts forward references; execution order is not
     * encoded in task numbering. No fixed bitset or 64-task limit. */
    size_t seen=0;
    for(;;) {
        size_t before=seen;
        for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==PENDING) {
            struct task *t=p->tasks+i; size_t j=0;
            while(j<t->dependency_count && p->tasks[t->dependencies[j]].state==SUCCEEDED) ++j;
            if(j==t->dependency_count) { t->state=SUCCEEDED; ++seen; }
        }
        if(before==seen) break;
    }
    for(size_t i=0;i<p->count;++i) p->tasks[i].state=PENDING;
    return seen==p->count;
}
/* Version 1 is a static-DAG policy adapter over the same native lifecycle
 * backend used by dynamic Async.Process scopes. The transport remains v1. */
static int launch(struct plan *p,struct task *t) {
    (void)p;
    mlf_process_spec spec={0};
    spec.executable=t->argv[0]; spec.argv=(const char *const *)t->argv;
    spec.cwd=t->cwd; spec.input=t->input; spec.output=t->output; spec.error=t->error;
    int code=mlf_ps_launch_policy(&spec,&t->native,1); t->pid=t->native.pid; return code;
}
static int poll_task(struct task *t) {
    if(!mlf_ps_poll_task(&t->native)) return 0;
    t->exit_code=t->native.exit_code;
    if(t->native.cleanup_error && !t->exit_code) t->exit_code=126;
    t->pid=t->native.pid; t->rss=t->native.rss; t->cpu=t->native.cpu;
    return 1;
}
static void cancel_task(struct task *t) { mlf_ps_cancel_task(&t->native); }
static uint64_t sample_memory(struct plan *p) {
    uint64_t total=0;
    for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==RUNNING) {
        struct task *t=p->tasks+i; uint64_t current=mlf_ps_process_memory(&t->native);
        if(current>t->aggregate_rss) t->aggregate_rss=current;
        total+=current;
    }
    return total;
}
static int ready(struct plan *p, struct task *t) {
    for(size_t i=0;i<t->dependency_count;++i) if(p->tasks[t->dependencies[i]].state!=SUCCEEDED) return 0;
    return 1;
}
static void json_string(FILE *out,const char *text) {
    fputc('"',out);
    for(const unsigned char *p=(const unsigned char *)text;*p;++p) {
        if(*p=='"' || *p=='\\') { fputc('\\',out); fputc(*p,out); }
        else if(*p<32) fprintf(out,"\\u%04x",*p);
        else fputc(*p,out);
    }
    fputc('"',out);
}
static int write_result(const char *path,struct plan *p,int exit_code,size_t maximum,double wall,uint64_t aggregate_peak) {
    size_t size=strlen(path)+80; char *temporary=checked_alloc(size,1); if(!temporary) return 0;
#ifdef _WIN32
    snprintf(temporary,size,"%s.tmp.%lu",path,(unsigned long)GetCurrentProcessId());
#else
    snprintf(temporary,size,"%s.tmp.%ld",path,(long)getpid());
#endif
    FILE *out=open_file(temporary,"wb"); if(!out) { free(temporary); return 0; }
    fprintf(out,"{\"protocol_version\":1,\"invocation_id\":"); json_string(out,p->invocation);
    fprintf(out,",\"plan_digest\":\"%s\",\"complete\":true,\"exit_code\":%d,\"jobs\":%lu,\"maximum_parallel_jobs\":%zu,\"wall_seconds\":%.9f,\"aggregate_peak_rss_bytes\":%" PRIu64 ",\"memory_sample_interval_seconds\":0.05,\"tasks\":[",p->digest,exit_code,p->jobs,maximum,wall,aggregate_peak);
    for(size_t i=0;i<p->count;++i) {
        struct task *t=p->tasks+i; if(i) fputc(',',out);
        fputs("{\"id\":",out); json_string(out,t->id);
        fprintf(out,",\"state\":\"%s\",\"exit_code\":%d,\"pid\":%" PRIu64 ",\"started_seconds\":%.9f,\"finished_seconds\":%.9f,\"wall_seconds\":%.9f,\"cpu_seconds\":%.9f,\"peak_rss_bytes\":%" PRIu64 ",\"aggregate_peak_rss_bytes\":%" PRIu64 "}",state_names[t->state],t->exit_code,t->pid,t->started,t->finished,t->finished-t->started,t->cpu,t->rss,t->aggregate_rss);
    }
    fputs("]}\n",out); int ok=!ferror(out); if(fclose(out)) ok=0;
#ifdef _WIN32
    wchar_t *from=wide(temporary),*to=wide(path);
    if(ok) ok=from && to && MoveFileExW(from,to,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    if(!ok && from) DeleteFileW(from); free(from); free(to);
#else
    if(ok) ok=rename(temporary,path)==0;
    if(!ok) unlink(temporary);
#endif
    free(temporary); return ok;
}
static int execute(struct plan *p,const char *result) {
#ifdef _WIN32
    HANDLE owner=mlf_ps_owner_handle();
    if(!owner) { fputs("mlf-build-runner: cannot supervise coordinator\n",stderr); return 71; }
#else
    pid_t owner=getppid();
#endif
    signal(SIGINT,on_signal); signal(SIGTERM,on_signal);
#ifndef _WIN32
    signal(SIGHUP,on_signal); signal(SIGPIPE,SIG_IGN);
#endif
    double start=now(),sampled=start-1; size_t running=0,maximum=0,remaining=p->count; int failure=0; uint64_t aggregate_peak=0;
    while(remaining) {
#ifdef _WIN32
        int owner_gone=WaitForSingleObject(owner,0)!=WAIT_TIMEOUT;
#else
        int owner_gone=getppid()!=owner || owner==1;
#endif
        if(!failure && (interrupted || owner_gone)) failure=interrupted ? 128+interrupted : 125;
        if(running && now()-sampled>=0.05) { uint64_t memory=sample_memory(p); if(memory>aggregate_peak) aggregate_peak=memory; sampled=now(); }
        /* Observe all completed jobs before considering new launches. */
        for(size_t i=0;i<p->count;++i) {
            struct task *t=p->tasks+i;
            if(t->state!=RUNNING) continue;
            if(poll_task(t)) {
                t->finished=now()-start; --running; --remaining;
                t->state=t->exit_code ? FAILED : SUCCEEDED;
                if(t->exit_code && !failure) failure=t->exit_code;
            } else if(!failure && now()-start-t->started>=(double)t->timeout) {
                t->exit_code=124; t->state=FAILED; failure=124;
            }
        }
        if(failure) {
            /* FAILED with a live handle is a deadline victim. Preserve its
             * timeout code while terminating every other active lifetime. */
            for(size_t i=0;i<p->count;++i) {
                struct task *t=p->tasks+i;
#ifdef _WIN32
                int live=t->native.process!=NULL;
#else
                int live=t->native.pid && t->native.result>=0;
#endif
                if(live) {
                    int timeout=t->state==FAILED && t->exit_code==124;
                    cancel_task(t); while(!poll_task(t)) pause_loop();
                    t->exit_code=timeout ? 124 : 125; t->state=timeout ? FAILED : CANCELLED;
                    t->finished=now()-start; --remaining; --running;
                }
            }
            /* Dependants of a failed/cancelled task are blocked; independent
             * queued work is cancelled by fail-fast. Propagate transitively. */
            int changed;
            do { changed=0; for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==PENDING) {
                struct task *t=p->tasks+i;
                for(size_t j=0;j<t->dependency_count;++j) { enum state s=p->tasks[t->dependencies[j]].state;
                    if(s==FAILED || s==CANCELLED || s==BLOCKED) { t->state=BLOCKED; t->exit_code=125; ++changed; --remaining; break; }
                }
            } } while(changed);
            for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==PENDING) { p->tasks[i].state=CANCELLED; p->tasks[i].exit_code=125; --remaining; }
            break;
        }
        for(size_t i=0;i<p->count && running<p->jobs;++i) {
            struct task *t=p->tasks+i; if(t->state!=PENDING || !ready(p,t)) continue;
            t->started=now()-start;
            int code=launch(p,t);
            if(code) { t->exit_code=code; t->state=FAILED; t->finished=now()-start; --remaining; failure=code; break; }
            t->state=RUNNING; ++running; if(running>maximum) maximum=running;
        }
        if(remaining) pause_loop();
    }
#ifdef _WIN32
    CloseHandle(owner);
#endif
    if(!write_result(result,p,failure,maximum,now()-start,aggregate_peak)) { fputs("mlf-build-runner: cannot publish result\n",stderr); return 74; }
    return failure>255 ? 1 : failure;
}
static int new_invocation_id(void) {
    unsigned char bytes[32];
#ifdef _WIN32
    /* Load the system RNG without adding a runtime DLL to release bundles. */
    HMODULE library=LoadLibraryW(L"advapi32.dll");
    if(!library) return 71;
    typedef BOOLEAN (WINAPI *random_function)(PVOID,ULONG);
    random_function random_bytes=(random_function)(void *)GetProcAddress(library,"SystemFunction036");
    int ok=random_bytes && random_bytes(bytes,(ULONG)sizeof(bytes)); FreeLibrary(library); if(!ok) return 71;
#else
    int fd=open("/dev/urandom",O_RDONLY|O_CLOEXEC); if(fd<0) return 71;
    size_t done=0;
    while(done<sizeof(bytes)) { ssize_t n=read(fd,bytes+done,sizeof(bytes)-done); if(n<0 && errno==EINTR) continue; if(n<=0) { close(fd); return 71; } done+=(size_t)n; }
    close(fd);
#endif
    for(size_t i=0;i<sizeof(bytes);++i) printf("%02x",bytes[i]);
    putchar('\n'); return ferror(stdout) ? 74 : 0;
}
static int runner_main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--new-invocation-id")) return new_invocation_id();
    if(argc==2 && !strcmp(argv[1],"--protocol-version")) { puts("1"); return 0; }
    if(argc!=3) { fputs("usage: mlf-build-runner PLAN RESULT\n",stderr); return 64; }
    struct plan plan={0};
    if(!read_plan(argv[1],&plan)) { fputs("mlf-build-runner: invalid plan\n",stderr); free_plan(&plan); return 64; }
    int result=execute(&plan,argv[2]); free_plan(&plan); return result;
}
#ifdef _WIN32
int wmain(int argc,wchar_t **wide_argv) {
    _setmode(_fileno(stdout),_O_BINARY); _setmode(_fileno(stderr),_O_BINARY);
    char **argv=checked_alloc((size_t)argc+1,sizeof(char *)); if(!argv) return 70;
    for(int i=0;i<argc;++i) {
        int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide_argv[i],-1,NULL,0,NULL,NULL);
        argv[i]=n ? checked_alloc((size_t)n,1) : NULL;
        if(!argv[i] || !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide_argv[i],-1,argv[i],n,NULL,NULL)) return 64;
    }
    int result=runner_main(argc,argv); for(int i=0;i<argc;++i) free(argv[i]); free(argv); return result;
}
#else
int main(int argc,char **argv) { return runner_main(argc,argv); }
#endif
