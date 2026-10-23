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
#ifdef _WIN32
    HANDLE process, job;
#else
    pid_t guard;
    int control, result;
#endif
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
    wchar_t *p=wide(path), *m=wide(mode); FILE *f=p && m ? _wfopen(p,m) : NULL; free(p); free(m); return f;
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
#ifndef _WIN32
        t->control=t->result=-1;
#endif
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
#ifndef _WIN32
#include "mlf_build_runner_posix.h"
struct child_result { int code; uint64_t pid, rss; double cpu; };
static int pipe_cloexec(int fds[2]) {
    if(pipe(fds)) return 0;
    if(fcntl(fds[0],F_SETFD,FD_CLOEXEC) || fcntl(fds[1],F_SETFD,FD_CLOEXEC)) { close(fds[0]); close(fds[1]); return 0; }
    return 1;
}
static void kill_scope(pid_t pid) { if(pid>0) { (void)kill(-pid,SIGKILL); (void)kill(pid,SIGKILL); } }
static void guard_task(struct plan *p, struct task *t, int control, int result) {
    /* The guardian survives a kill of the runner's process group. Its control
     * pipe has exactly one writer, the runner: EOF covers even SIGKILL/crashes. */
    if(setpgid(0,0) && getpgrp()!=getpid()) _exit(126);
    for(size_t i=0;i<p->count;++i) {
        if(p->tasks[i].control>=0) close(p->tasks[i].control);
        if(p->tasks[i].result>=0) close(p->tasks[i].result);
    }
    signal(SIGPIPE,SIG_IGN); interrupted=0;
#ifdef __linux__
    /* Reap orphaned grandchildren ourselves on Linux, including subprocesses
     * that created new process groups before their parent terminated. */
    if(prctl(PR_SET_CHILD_SUBREAPER,1)) _exit(126);
#endif
    if(fcntl(control,F_SETFL,O_NONBLOCK)) _exit(126);
    fflush(NULL); pid_t child=fork();
    if(child<0) _exit(126);
    if(!child) {
        close(control); close(result);
        signal(SIGINT,SIG_DFL); signal(SIGTERM,SIG_DFL); signal(SIGHUP,SIG_DFL); signal(SIGPIPE,SIG_DFL);
        if(setsid()<0) _exit(126);
        char scope[32]; snprintf(scope,sizeof(scope),"%ld",(long)getpid());
        if(setenv("MLF_BUILD_SCOPE",scope,1)) _exit(126);
        if(*t->cwd && chdir(t->cwd)) _exit(126);
        const char *paths[]={t->input,t->output,t->error};
        for(int i=0;i<3;++i) {
            if(i==2 && *paths[2] && !strcmp(paths[1],paths[2])) { if(dup2(1,2)<0) _exit(126); continue; }
            if(!*paths[i]) continue;
            int fd=open(paths[i],i ? O_WRONLY|O_CREAT|O_TRUNC : O_RDONLY,0666);
            if(fd<0 || dup2(fd,i)<0) _exit(126);
            if(fd!=i) close(fd);
        }
        execvp(t->argv[0],t->argv); _exit(errno==ENOENT ? 127 : 126);
    }
    struct child_result record={0}; record.pid=(uint64_t)child;
    /* Startup handshake gives the runner the session ID for aggregate memory
     * measurements before it returns from launch. The worker alone calls
     * setsid: parent-side setpgid would prevent that call on some races. */
    if(write(result,&record,sizeof(record))!=(ssize_t)sizeof(record)) { kill_scope(child); (void)stop_session(child); _exit(126); }
    struct rusage usage={0}; int status=0, cancelled=0;
    for(;;) {
        pid_t done=wait4(child,&status,WNOHANG,&usage);
        if(done==child) break;
        if(done<0 && errno!=EINTR) { cancelled=126; break; }
        char byte; ssize_t n=read(control,&byte,1);
        if(interrupted || n==0 || n>0 || (n<0 && errno!=EAGAIN && errno!=EINTR)) {
            cancelled=125; kill_scope(child);
            while(wait4(child,&status,0,&usage)<0 && errno==EINTR) {}
            break;
        }
        pause_loop();
    }
    kill_scope(child);
    if(!stop_session(child) && !cancelled) cancelled=126;
#ifdef __linux__
    while(waitpid(-1,NULL,0)>=0 || errno==EINTR) {}
#endif
    record.code=cancelled ? cancelled : WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
    record.cpu=(double)usage.ru_utime.tv_sec+(double)usage.ru_utime.tv_usec/1e6+(double)usage.ru_stime.tv_sec+(double)usage.ru_stime.tv_usec/1e6;
#ifdef __APPLE__
    record.rss=(uint64_t)usage.ru_maxrss;
#else
    record.rss=(uint64_t)usage.ru_maxrss*1024;
#endif
    (void)write(result,&record,sizeof(record)); close(result); close(control); _exit(0);
}
static int launch(struct plan *p, struct task *t) {
    int control[2], result[2];
    if(!pipe_cloexec(control)) return 126;
    if(!pipe_cloexec(result)) { close(control[0]); close(control[1]); return 126; }
    fflush(NULL); pid_t guard=fork();
    if(!guard) { close(control[1]); close(result[0]); guard_task(p,t,control[0],result[1]); }
    close(control[0]); close(result[1]);
    if(guard<0) { close(control[1]); close(result[0]); return 126; }
    struct child_result started={0}; ssize_t received;
    do { received=read(result[0],&started,sizeof(started)); } while(received<0 && errno==EINTR);
    if(received!=(ssize_t)sizeof(started) || !started.pid) {
        close(control[1]); close(result[0]); while(waitpid(guard,NULL,0)<0 && errno==EINTR) {} return 126;
    }
    t->pid=started.pid; t->guard=guard; t->control=control[1]; t->result=result[0]; return 0;
}
static int poll_task(struct task *t) {
    int status=0; pid_t done=waitpid(t->guard,&status,WNOHANG);
    if(!done || (done<0 && errno==EINTR)) return 0;
    struct child_result result={0}; ssize_t n=read(t->result,&result,sizeof(result));
    close(t->result); t->result=-1;
    if(t->control>=0) close(t->control);
    t->control=-1;
    if(done<0 || !WIFEXITED(status) || WEXITSTATUS(status) || n!=(ssize_t)sizeof(result)) {
        /* If a guardian itself fails while its runner survives, the runner
         * still knows the worker session from the startup handshake. */
        kill_scope((pid_t)t->pid); (void)stop_session((pid_t)t->pid); t->exit_code=126;
    } else { t->exit_code=result.code; t->pid=result.pid; t->rss=result.rss; t->cpu=result.cpu; }
    return 1;
}
static void cancel_task(struct task *t) {
    if(t->control>=0) { close(t->control); t->control=-1; }
}
#else
/* Win32 jobs are owned only by the runner and do not inherit. Closing the job
 * on runner death kills workers and all nested child jobs/processes. */
static wchar_t *command_line(char **args) {
    size_t capacity=1;
    for(char **a=args;*a;++a) { size_t n=strlen(*a); if(n>(SIZE_MAX-capacity-3)/2) return NULL; capacity+=2*n+3; }
    wchar_t *line=checked_alloc(capacity,sizeof(wchar_t)), *out=line;
    if(!line) return NULL;
    for(char **a=args;*a;++a) {
        wchar_t *text=wide(*a); if(!text) { free(line); return NULL; }
        if(a!=args) *out++=L' '; *out++=L'"';
        const wchar_t *c=text;
        while(*c) { size_t n=0; while(*c==L'\\') { ++n; ++c; } size_t emit=(*c==L'"' || !*c) ? n*2 : n; while(emit--) *out++=L'\\'; if(*c==L'"') *out++=L'\\'; if(*c) *out++=*c++; }
        *out++=L'"'; free(text);
    }
    *out=0; return line;
}
static HANDLE redirect_stream(const char *path,int stream) {
    HANDLE handle=INVALID_HANDLE_VALUE;
    if(!*path) {
        HANDLE original=GetStdHandle(stream==0 ? STD_INPUT_HANDLE : stream==1 ? STD_OUTPUT_HANDLE : STD_ERROR_HANDLE);
        if(!original || original==INVALID_HANDLE_VALUE) path="NUL";
        else { if(!DuplicateHandle(GetCurrentProcess(),original,GetCurrentProcess(),&handle,0,TRUE,DUPLICATE_SAME_ACCESS)) return INVALID_HANDLE_VALUE; return handle; }
    }
    wchar_t *w=wide(path); SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};
    if(w) handle=CreateFileW(w,stream ? GENERIC_WRITE : GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,&sa,stream ? CREATE_ALWAYS : OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    free(w); return handle;
}
static int launch(struct plan *p, struct task *t) {
    (void)p;
    wchar_t *line=command_line(t->argv), *cwd=*t->cwd ? wide(t->cwd) : NULL;
    HANDLE streams[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
    PROCESS_INFORMATION process={0}; int code=126; LPPROC_THREAD_ATTRIBUTE_LIST attributes=NULL;
    if(!line || (*t->cwd && !cwd)) goto cleanup;
    /* Relative redirect paths have the same meaning as on POSIX: relative to
     * task cwd. Only the runner thread modifies cwd while opening handles. */
    DWORD size=GetCurrentDirectoryW(0,NULL); wchar_t *saved=checked_alloc(size,sizeof(wchar_t));
    if(!saved || !GetCurrentDirectoryW(size,saved)) { free(saved); goto cleanup; }
    if(cwd && !SetCurrentDirectoryW(cwd)) { free(saved); goto cleanup; }
    for(int i=0;i<3;++i) streams[i]=(i==2 && *t->error && !strcmp(t->output,t->error)) ? streams[1] : redirect_stream(i==0 ? t->input : i==1 ? t->output : t->error,i);
    int restored=SetCurrentDirectoryW(saved); free(saved); if(!restored) goto cleanup;
    for(int i=0;i<3;++i) if(streams[i]==INVALID_HANDLE_VALUE) goto cleanup;
    t->job=CreateJobObjectW(NULL,NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits={0}; limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if(!t->job || !SetInformationJobObject(t->job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))) goto cleanup;
    SIZE_T bytes=0; InitializeProcThreadAttributeList(NULL,1,0,&bytes); attributes=malloc(bytes);
    if(!attributes || !InitializeProcThreadAttributeList(attributes,1,0,&bytes)) { free(attributes); attributes=NULL; goto cleanup; }
    HANDLE inherited[3]={streams[0],streams[1],streams[2]}; SIZE_T inherited_count=streams[1]==streams[2] ? 2 : 3;
    if(!UpdateProcThreadAttribute(attributes,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,inherited,inherited_count*sizeof(HANDLE),NULL,NULL)) goto cleanup;
    STARTUPINFOEXW startup={0}; startup.StartupInfo.cb=sizeof(startup); startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput=streams[0]; startup.StartupInfo.hStdOutput=streams[1]; startup.StartupInfo.hStdError=streams[2]; startup.lpAttributeList=attributes;
    if(!CreateProcessW(NULL,line,NULL,NULL,TRUE,CREATE_SUSPENDED|CREATE_NO_WINDOW|EXTENDED_STARTUPINFO_PRESENT,NULL,cwd,&startup.StartupInfo,&process)) {
        DWORD error=GetLastError(); code=(error==ERROR_FILE_NOT_FOUND || error==ERROR_PATH_NOT_FOUND) ? 127 : 126; goto cleanup;
    }
    if(!AssignProcessToJobObject(t->job,process.hProcess) || ResumeThread(process.hThread)==(DWORD)-1) { TerminateProcess(process.hProcess,126); WaitForSingleObject(process.hProcess,INFINITE); goto cleanup; }
    t->process=process.hProcess; t->pid=process.dwProcessId; process.hProcess=NULL; code=0;
cleanup:
    if(attributes) { DeleteProcThreadAttributeList(attributes); free(attributes); }
    if(process.hThread) CloseHandle(process.hThread);
    if(process.hProcess) CloseHandle(process.hProcess);
    for(int i=0;i<3;++i) if(streams[i]!=INVALID_HANDLE_VALUE && (i!=2 || streams[2]!=streams[1])) CloseHandle(streams[i]);
    if(code && t->job) { CloseHandle(t->job); t->job=NULL; }
    free(line); free(cwd); return code;
}
static int poll_task(struct task *t) {
    DWORD wait=WaitForSingleObject(t->process,0); if(wait==WAIT_TIMEOUT) return 0;
    DWORD code=126; if(wait==WAIT_OBJECT_0) GetExitCodeProcess(t->process,&code); t->exit_code=(int)code;
    FILETIME creation,exit,kernel,user;
    if(GetProcessTimes(t->process,&creation,&exit,&kernel,&user)) {
        ULARGE_INTEGER k,u; k.LowPart=kernel.dwLowDateTime; k.HighPart=kernel.dwHighDateTime; u.LowPart=user.dwLowDateTime; u.HighPart=user.dwHighDateTime;
        t->cpu=(double)(k.QuadPart+u.QuadPart)/1e7;
    }
    PROCESS_MEMORY_COUNTERS memory={0}; memory.cb=sizeof(memory); if(GetProcessMemoryInfo(t->process,&memory,sizeof(memory))) t->rss=memory.PeakWorkingSetSize;
    CloseHandle(t->job); t->job=NULL; CloseHandle(t->process); t->process=NULL; return 1;
}
static void cancel_task(struct task *t) { if(t->job) TerminateJobObject(t->job,125); }
static HANDLE owner_handle(void) {
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0), owner=NULL;
    if(snapshot==INVALID_HANDLE_VALUE) return NULL;
    PROCESSENTRY32W entry={0}; entry.dwSize=sizeof(entry);
    if(Process32FirstW(snapshot,&entry)) do { if(entry.th32ProcessID==GetCurrentProcessId()) { owner=OpenProcess(SYNCHRONIZE,FALSE,entry.th32ParentProcessID); break; } } while(Process32NextW(snapshot,&entry));
    CloseHandle(snapshot); return owner;
}
#endif
static uint64_t sample_memory(struct plan *p) {
    uint64_t total=0;
#ifdef _WIN32
    for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==RUNNING && p->tasks[i].job) {
        struct task *t=p->tasks+i; SIZE_T capacity=64;
        JOBOBJECT_BASIC_PROCESS_ID_LIST *list=NULL;
        for(;;) {
            size_t bytes=sizeof(*list)+(capacity-1)*sizeof(ULONG_PTR); free(list); list=malloc(bytes);
            if(!list) break;
            if(QueryInformationJobObject(t->job,JobObjectBasicProcessIdList,list,(DWORD)bytes,NULL)) break;
            if(GetLastError()!=ERROR_MORE_DATA || capacity>MAX_TASKS) { free(list); list=NULL; break; }
            capacity*=2;
        }
        uint64_t current=0;
        if(list) for(DWORD j=0;j<list->NumberOfProcessIdsInList;++j) {
            HANDLE process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,(DWORD)list->ProcessIdList[j]);
            if(process) { PROCESS_MEMORY_COUNTERS info={0}; info.cb=sizeof(info); if(GetProcessMemoryInfo(process,&info,sizeof(info))) current+=info.WorkingSetSize; CloseHandle(process); }
        }
        free(list); if(current>t->aggregate_rss) t->aggregate_rss=current; total+=current;
    }
#else
    size_t count; struct process_sample *samples=process_samples(&count,1);
    if(!samples) return 0;
    for(size_t i=0;i<p->count;++i) if(p->tasks[i].state==RUNNING) {
        struct task *t=p->tasks+i; uint64_t current=0;
        for(size_t j=0;j<count;++j) if((uint64_t)samples[j].session==t->pid) current+=samples[j].rss;
        if(current>t->aggregate_rss) t->aggregate_rss=current; total+=current;
    }
    free(samples);
#endif
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
    HANDLE owner=owner_handle();
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
                int live=t->process!=NULL;
#else
                int live=t->result>=0;
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
