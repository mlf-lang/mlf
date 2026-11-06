/* Shared process ownership backend and bounded dynamic scopes.
 * This file may also be included once by monolithic native-runtime clients. */
#ifndef MLF_PROCESS_SUPERVISOR_IMPLEMENTED
#define MLF_PROCESS_SUPERVISOR_IMPLEMENTED
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _DARWIN_C_SOURCE
#define _DARWIN_C_SOURCE 1
#endif
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif
#include "mlf_process_supervisor.h"
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <wchar.h>
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
#define MLF_PS_MAX_SLOTS 100000U
#define MLF_PS_MAX_ARGUMENTS 65536U
#define MLF_PS_MAX_SPEC_BYTES (16U * 1024U * 1024U)
static void *mlf_ps_checked_alloc(size_t count,size_t size) {
    if(size && count>SIZE_MAX/size) return NULL;
    return calloc(count,size);
}
struct mlf_ps_process {
    struct mlf_ps_process *next;
    uint64_t pid,rss;
    double cpu;
    int exit_code,launch_error,cleanup_error;
#ifdef _WIN32
    HANDLE process,job;
#else
    pid_t guard;
    int control,result;
#endif
};
static struct mlf_ps_process *mlf_ps_active;
#ifdef _WIN32
static wchar_t *mlf_ps_wide(const char *s) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,NULL,0);
    wchar_t *out=n ? mlf_ps_checked_alloc((size_t)n,sizeof(wchar_t)) : NULL;
    if(out && !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,out,n)) { free(out); out=NULL; }
    return out;
}
double mlf_process_monotonic_seconds(void) { return (double)GetTickCount64()/1000.0; }
static void mlf_ps_pause_loop(void) { Sleep(5); }
#else
double mlf_process_monotonic_seconds(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) abort();
    return (double)t.tv_sec+(double)t.tv_nsec/1e9;
}
static void mlf_ps_pause_loop(void) { struct timespec t={0,5000000}; nanosleep(&t,NULL); }
static volatile sig_atomic_t mlf_ps_interrupted;
static void mlf_ps_on_signal(int sig) { mlf_ps_interrupted=sig; }
#endif
#ifndef _WIN32
#include "mlf_process_supervisor_posix.h"
struct mlf_ps_child_result { int code,launch_error,cleanup_error; uint64_t pid,rss; double cpu; };
static int mlf_ps_pipe_cloexec(int fds[2]) {
    if(pipe(fds)) return 0;
    /* Closed stdin/stdout/stderr must not let a private ownership/error pipe
     * be overwritten by the child's later dup2 redirections. */
    for(int i=0;i<2;++i) if(fds[i]<3) {
        int moved=fcntl(fds[i],F_DUPFD,3);
        if(moved<0) { int saved=errno; close(fds[0]); close(fds[1]); errno=saved; return 0; }
        close(fds[i]); fds[i]=moved;
    }
    if(fcntl(fds[0],F_SETFD,FD_CLOEXEC) || fcntl(fds[1],F_SETFD,FD_CLOEXEC)) {
        int saved=errno; close(fds[0]); close(fds[1]); errno=saved; return 0;
    }
    return 1;
}
static void mlf_ps_kill_scope(pid_t pid) {
    if(pid>0) { (void)kill(-pid,SIGKILL); (void)kill(pid,SIGKILL); }
}
static void mlf_ps_child_fail(int fd,int error) {
    /* Best-effort notification: retain the original single-write/exit path. */
    ssize_t written=write(fd,&error,sizeof(error));
    (void)written;
    _exit(error==ENOENT ? 127 : 126);
}
/* execve plus explicit PATH search avoids execvp's implicit shell fallback
 * for executable text files lacking a shebang. */
static void mlf_ps_exec(const mlf_process_spec *spec,int error_fd,char **env,int legacy) {
    if(legacy) {
        /* Preserve the v1 adapter's historical executable lookup/fallback. */
        execvp(spec->argv[0],(char *const *)spec->argv);
        mlf_ps_child_fail(error_fd,errno);
    }
    if(strchr(spec->executable,'/')) {
        execve(spec->executable,(char *const *)spec->argv,env);
        mlf_ps_child_fail(error_fd,errno);
    }
    const char *path=NULL;
    for(char **p=env;*p;++p) if(!strncmp(*p,"PATH=",5)) { path=*p+5; break; }
    if(!path) path="/usr/bin:/bin";
    size_t name_size=strlen(spec->executable),path_size=strlen(path);
    char *candidate=malloc(path_size+name_size+2);
    if(!candidate) mlf_ps_child_fail(error_fd,ENOMEM);
    int denied=0;
    const char *part=path;
    for(;;) {
        const char *end=strchr(part,':'); size_t n=end ? (size_t)(end-part) : strlen(part);
        if(n) { memcpy(candidate,part,n); candidate[n++]='/'; }
        memcpy(candidate+n,spec->executable,name_size+1);
        execve(candidate,(char *const *)spec->argv,env);
        int error=errno;
        if(error==EACCES) denied=1;
        else if(error!=ENOENT && error!=ENOTDIR) mlf_ps_child_fail(error_fd,error);
        if(!end) break;
        part=end+1;
    }
    mlf_ps_child_fail(error_fd,denied ? EACCES : ENOENT);
}
static void mlf_ps_guard_task(const mlf_process_spec *spec,int control,int result,int legacy) {
    /* Only the coordinator owns write ends. Close every other scope's ends,
     * including running processes in separately created dynamic scopes. */
    if(setpgid(0,0) && getpgrp()!=getpid()) _exit(126);
    for(struct mlf_ps_process *other=mlf_ps_active;other;other=other->next) {
        if(other->control>=0) close(other->control);
        if(other->result>=0) close(other->result);
    }
    signal(SIGPIPE,SIG_IGN); signal(SIGINT,mlf_ps_on_signal);
    signal(SIGTERM,mlf_ps_on_signal); signal(SIGHUP,mlf_ps_on_signal);
    mlf_ps_interrupted=0;
#ifdef __linux__
    if(prctl(PR_SET_CHILD_SUBREAPER,1)) _exit(126);
#endif
    if(fcntl(control,F_SETFL,O_NONBLOCK)) _exit(126);
    int exec_error[2];
    if(!mlf_ps_pipe_cloexec(exec_error)) _exit(126);
    fflush(NULL); pid_t child=fork();
    if(child<0) _exit(126);
    if(!child) {
        close(control); close(result); close(exec_error[0]);
        signal(SIGINT,SIG_DFL); signal(SIGTERM,SIG_DFL); signal(SIGHUP,SIG_DFL); signal(SIGPIPE,SIG_DFL);
        if(setsid()<0) mlf_ps_child_fail(exec_error[1],errno);
        char scope[64]; snprintf(scope,sizeof(scope),"MLF_BUILD_SCOPE=%ld",(long)getpid());
        char **environment;
        if(spec->environment==MLF_PROCESS_ENV_REPLACE) {
            size_t count=0; if(spec->env) while(spec->env[count]) ++count;
            environment=mlf_ps_checked_alloc(count+2,sizeof(char *));
            if(!environment) mlf_ps_child_fail(exec_error[1],ENOMEM);
            size_t used=0;
            for(size_t i=0;i<count;++i) if(strncmp(spec->env[i],"MLF_BUILD_SCOPE=",16)) environment[used++]=(char *)spec->env[i];
            environment[used]=scope;
        } else {
            extern char **environ;
            if(setenv("MLF_BUILD_SCOPE",scope+16,1)) mlf_ps_child_fail(exec_error[1],errno);
            environment=environ;
        }
        if(*spec->cwd && chdir(spec->cwd)) mlf_ps_child_fail(exec_error[1],errno);
        const char *paths[]={spec->input,spec->output,spec->error};
        for(int i=0;i<3;++i) {
            if(i==2 && *paths[2] && !strcmp(paths[1],paths[2])) {
                if(dup2(1,2)<0) mlf_ps_child_fail(exec_error[1],errno);
                continue;
            }
            if(!*paths[i]) continue;
            int fd=open(paths[i],i ? O_WRONLY|O_CREAT|O_TRUNC : O_RDONLY,0666);
            if(fd<0 || dup2(fd,i)<0) mlf_ps_child_fail(exec_error[1],errno);
            if(fd!=i) close(fd);
        }
        mlf_ps_exec(spec,exec_error[1],environment,legacy);
        _exit(126);
    }
    close(exec_error[1]);
    struct mlf_ps_child_result record={0}; record.pid=(uint64_t)child;
    /* Handshake establishes ownership before the caller returns from launch. */
    if(write(result,&record,sizeof(record))!=(ssize_t)sizeof(record)) {
        mlf_ps_kill_scope(child); (void)mlf_ps_stop_session(child); _exit(126);
    }
    struct rusage usage={0}; int status=0,cancelled=0;
    for(;;) {
        pid_t done=wait4(child,&status,WNOHANG,&usage);
        if(done==child) break;
        if(done<0 && errno!=EINTR) { record.cleanup_error=errno; cancelled=126; break; }
        char byte; ssize_t n=read(control,&byte,1);
        if(mlf_ps_interrupted || n==0 || n>0 || (n<0 && errno!=EAGAIN && errno!=EINTR)) {
            cancelled=125; mlf_ps_kill_scope(child);
            while(wait4(child,&status,0,&usage)<0) {
                if(errno!=EINTR) { record.cleanup_error=errno; break; }
            }
            break;
        }
        mlf_ps_pause_loop();
    }
    mlf_ps_kill_scope(child);
    if(!mlf_ps_stop_session(child)) record.cleanup_error=errno ? errno : EIO;
#ifdef __linux__
    while(waitpid(-1,NULL,0)>=0 || errno==EINTR) {}
#endif
    int error=0; ssize_t got;
    do { got=read(exec_error[0],&error,sizeof(error)); } while(got<0 && errno==EINTR);
    if(got==(ssize_t)sizeof(error)) record.launch_error=error;
    else if(got!=0) record.cleanup_error=EIO;
    close(exec_error[0]);
    record.code=cancelled ? cancelled : WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
    record.cpu=(double)usage.ru_utime.tv_sec+(double)usage.ru_utime.tv_usec/1e6+(double)usage.ru_stime.tv_sec+(double)usage.ru_stime.tv_usec/1e6;
#ifdef __APPLE__
    record.rss=(uint64_t)usage.ru_maxrss;
#else
    record.rss=(uint64_t)usage.ru_maxrss*1024;
#endif
    /* The receiver detects a missing/short record; do not retry at exit. */
    ssize_t written=write(result,&record,sizeof(record));
    (void)written; close(result); close(control); _exit(0);
}
static int mlf_ps_platform_launch(const mlf_process_spec *spec,struct mlf_ps_process *t,int legacy) {
    int control[2],result[2];
    if(!mlf_ps_pipe_cloexec(control)) { t->launch_error=errno; return 126; }
    if(!mlf_ps_pipe_cloexec(result)) { t->launch_error=errno; close(control[0]); close(control[1]); return 126; }
    fflush(NULL); pid_t guard=fork();
    if(!guard) { close(control[1]); close(result[0]); mlf_ps_guard_task(spec,control[0],result[1],legacy); }
    int saved=errno; close(control[0]); close(result[1]);
    if(guard<0) { t->launch_error=saved; close(control[1]); close(result[0]); return 126; }
    struct mlf_ps_child_result started={0}; ssize_t received;
    do { received=read(result[0],&started,sizeof(started)); } while(received<0 && errno==EINTR);
    if(received!=(ssize_t)sizeof(started) || !started.pid) {
        t->launch_error=EIO; close(control[1]); close(result[0]);
        while(waitpid(guard,NULL,0)<0 && errno==EINTR) {}
        return 126;
    }
    t->pid=started.pid; t->guard=guard; t->control=control[1]; t->result=result[0]; return 0;
}
static int mlf_ps_platform_poll(struct mlf_ps_process *t) {
    int status=0; pid_t done=waitpid(t->guard,&status,WNOHANG);
    if(!done || (done<0 && errno==EINTR)) return 0;
    struct mlf_ps_child_result result={0}; ssize_t n;
    do { n=read(t->result,&result,sizeof(result)); } while(n<0 && errno==EINTR);
    close(t->result); t->result=-1;
    if(t->control>=0) close(t->control);
    t->control=-1;
    if(done<0 || !WIFEXITED(status) || WEXITSTATUS(status) || n!=(ssize_t)sizeof(result)) {
        mlf_ps_kill_scope((pid_t)t->pid); (void)mlf_ps_stop_session((pid_t)t->pid);
        t->exit_code=126; t->cleanup_error=EIO;
    } else {
        t->exit_code=result.code; t->launch_error=result.launch_error; t->cleanup_error=result.cleanup_error;
        t->pid=result.pid; t->rss=result.rss; t->cpu=result.cpu;
    }
    return 1;
}
static void mlf_ps_platform_cancel(struct mlf_ps_process *t) {
    if(t->control>=0) { close(t->control); t->control=-1; }
}
#else
/* Win32 jobs are owned only by the runner and do not inherit. Closing the job
 * on runner death kills workers and all nested child jobs/processes. */
static wchar_t *mlf_ps_command_line(const char *const *args) {
    size_t capacity=1;
    for(const char *const *a=args;*a;++a) { size_t n=strlen(*a); if(n>(SIZE_MAX-capacity-3)/2) return NULL; capacity+=2*n+3; }
    wchar_t *line=mlf_ps_checked_alloc(capacity,sizeof(wchar_t)), *out=line;
    if(!line) return NULL;
    for(const char *const *a=args;*a;++a) {
        wchar_t *text=mlf_ps_wide(*a); if(!text) { free(line); return NULL; }
        if(a!=args) *out++=L' '; *out++=L'"';
        const wchar_t *c=text;
        while(*c) { size_t n=0; while(*c==L'\\') { ++n; ++c; } size_t emit=(*c==L'"' || !*c) ? n*2 : n; while(emit--) *out++=L'\\'; if(*c==L'"') *out++=L'\\'; if(*c) *out++=*c++; }
        *out++=L'"'; free(text);
    }
    *out=0; return line;
}
static HANDLE mlf_ps_redirect_stream(const char *path,int stream) {
    HANDLE handle=INVALID_HANDLE_VALUE;
    if(!*path) {
        HANDLE original=GetStdHandle(stream==0 ? STD_INPUT_HANDLE : stream==1 ? STD_OUTPUT_HANDLE : STD_ERROR_HANDLE);
        if(!original || original==INVALID_HANDLE_VALUE) path="NUL";
        else { if(!DuplicateHandle(GetCurrentProcess(),original,GetCurrentProcess(),&handle,0,TRUE,DUPLICATE_SAME_ACCESS)) return INVALID_HANDLE_VALUE; return handle; }
    }
    wchar_t *w=mlf_ps_wide(path); SECURITY_ATTRIBUTES sa={sizeof(sa),NULL,TRUE};
    if(w) handle=CreateFileW(w,stream ? GENERIC_WRITE : GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,&sa,stream ? CREATE_ALWAYS : OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    DWORD error=GetLastError(); free(w); SetLastError(error); return handle;
}
static int mlf_ps_environment_compare(const void *a,const void *b) {
    return _wcsicmp(*(const wchar_t *const *)a,*(const wchar_t *const *)b);
}
static wchar_t *mlf_ps_environment_block(const char *const *env) {
    size_t count=0,total=1;
    if(env) while(env[count]) ++count;
    wchar_t **items=mlf_ps_checked_alloc(count+1,sizeof(wchar_t *));
    if(!items) return NULL;
    for(size_t i=0;i<count;++i) {
        items[i]=mlf_ps_wide(env[i]);
        if(!items[i]) { for(size_t j=0;j<i;++j) free(items[j]); free(items); return NULL; }
        total+=wcslen(items[i])+1;
    }
    if(!count) ++total;
    qsort(items,count,sizeof(wchar_t *),mlf_ps_environment_compare);
    wchar_t *block=mlf_ps_checked_alloc(total,sizeof(wchar_t)),*out=block;
    for(size_t i=0;i<count;++i) {
        if(out) { size_t n=wcslen(items[i])+1; memcpy(out,items[i],n*sizeof(wchar_t)); out+=n; }
        free(items[i]);
    }
    free(items); return block;
}
/* Resolve explicitly so argv[0] may differ from the executable. SearchPathW
 * runs while child cwd is active; absolute executables avoid search policy. */
static wchar_t *mlf_ps_executable(const mlf_process_spec *spec) {
    wchar_t *wide=mlf_ps_wide(spec->executable),*path=NULL;
    int path_supplied=0;
    if(!wide) return NULL;
    if(spec->environment==MLF_PROCESS_ENV_REPLACE) {
        if(spec->env) for(size_t i=0;spec->env[i];++i) if(!_strnicmp(spec->env[i],"PATH=",5)) {
            path_supplied=1; path=mlf_ps_wide(spec->env[i]+5); break;
        }
    } else {
        SetLastError(ERROR_SUCCESS);
        DWORD n=GetEnvironmentVariableW(L"PATH",NULL,0);
        if(n) {
            path_supplied=1; path=mlf_ps_checked_alloc((size_t)n,sizeof(wchar_t));
            if(path && GetEnvironmentVariableW(L"PATH",path,n)>=n) { free(path); path=NULL; }
        } else if(GetLastError()==ERROR_SUCCESS) {
            path_supplied=1; path=mlf_ps_wide("");
        }
    }
    if(path_supplied && !path) { free(wide); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    /* An absent PATH uses the system binaries directory, not the coordinator's
     * inherited PATH. An explicitly empty PATH means the child cwd. */
    if(!path) {
        UINT n=GetSystemDirectoryW(NULL,0);
        path=mlf_ps_checked_alloc((size_t)n+1,sizeof(wchar_t));
        if(path && !GetSystemDirectoryW(path,n+1)) { free(path); path=NULL; }
    }
    if(!path) { free(wide); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    DWORD n=SearchPathW(*path ? path : L".",wide,L".exe",0,NULL,NULL);
    DWORD error=n ? ERROR_NOT_ENOUGH_MEMORY : GetLastError();
    wchar_t *full=n ? mlf_ps_checked_alloc((size_t)n+1,sizeof(wchar_t)) : NULL;
    if(full) {
        DWORD written=SearchPathW(*path ? path : L".",wide,L".exe",n+1,full,NULL);
        if(!written || written>n) { error=written ? ERROR_INSUFFICIENT_BUFFER : GetLastError(); free(full); full=NULL; }
    }
    free(wide); free(path); if(!full) SetLastError(error); return full;
}
/* K32 is available on the supported Windows 7+ baseline; resolving from the
 * already-loaded system DLL avoids a new psapi import for every MLF binary. */
static int mlf_ps_memory_info(HANDLE process,PROCESS_MEMORY_COUNTERS *info) {
    typedef BOOL (WINAPI *query_fn)(HANDLE,PPROCESS_MEMORY_COUNTERS,DWORD);
    query_fn query=(query_fn)(void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"K32GetProcessMemoryInfo");
    return query && query(process,info,(DWORD)sizeof(*info));
}
static int mlf_ps_platform_launch(const mlf_process_spec *spec,struct mlf_ps_process *t,int legacy) {
    wchar_t *line=mlf_ps_command_line(spec->argv),*cwd=*spec->cwd ? mlf_ps_wide(spec->cwd) : NULL;
    wchar_t *application=NULL,*environment=spec->environment==MLF_PROCESS_ENV_REPLACE ? mlf_ps_environment_block(spec->env) : NULL;
    HANDLE streams[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
    PROCESS_INFORMATION process={0}; int code=126; LPPROC_THREAD_ATTRIBUTE_LIST attributes=NULL;
    if(!line || (*spec->cwd && !cwd) || (spec->environment==MLF_PROCESS_ENV_REPLACE && !environment)) { t->launch_error=ERROR_NOT_ENOUGH_MEMORY; goto cleanup; }
    /* This API requires a single coordinator. Only it temporarily modifies cwd
     * to resolve relative redirect paths with the same meaning as POSIX. */
    DWORD size=GetCurrentDirectoryW(0,NULL); wchar_t *saved=mlf_ps_checked_alloc(size,sizeof(wchar_t));
    if(!saved || !GetCurrentDirectoryW(size,saved)) { t->launch_error=(int)GetLastError(); free(saved); goto cleanup; }
    if(cwd && !SetCurrentDirectoryW(cwd)) { t->launch_error=(int)GetLastError(); free(saved); goto cleanup; }
    for(int i=0;i<3;++i) {
        streams[i]=(i==2 && *spec->error && !strcmp(spec->output,spec->error)) ? streams[1] : mlf_ps_redirect_stream(i==0 ? spec->input : i==1 ? spec->output : spec->error,i);
        if(streams[i]==INVALID_HANDLE_VALUE && !t->launch_error) t->launch_error=(int)GetLastError();
    }
    if(!legacy) application=mlf_ps_executable(spec);
    if(!legacy && !application && !t->launch_error) t->launch_error=(int)GetLastError();
    int restored=SetCurrentDirectoryW(saved); free(saved);
    if(!restored) { t->cleanup_error=(int)GetLastError(); goto cleanup; }
    for(int i=0;i<3;++i) if(streams[i]==INVALID_HANDLE_VALUE) goto cleanup;
    if(!legacy && !application) { code=(t->launch_error==ERROR_FILE_NOT_FOUND || t->launch_error==ERROR_PATH_NOT_FOUND) ? 127 : 126; goto cleanup; }
    t->job=CreateJobObjectW(NULL,NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits={0}; limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if(!t->job || !SetInformationJobObject(t->job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))) goto cleanup;
    SIZE_T bytes=0; InitializeProcThreadAttributeList(NULL,1,0,&bytes); attributes=malloc(bytes);
    if(!attributes || !InitializeProcThreadAttributeList(attributes,1,0,&bytes)) { free(attributes); attributes=NULL; goto cleanup; }
    HANDLE inherited[3]={streams[0],streams[1],streams[2]}; SIZE_T inherited_count=streams[1]==streams[2] ? 2 : 3;
    if(!UpdateProcThreadAttribute(attributes,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,inherited,inherited_count*sizeof(HANDLE),NULL,NULL)) goto cleanup;
    STARTUPINFOEXW startup={0}; startup.StartupInfo.cb=sizeof(startup); startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput=streams[0]; startup.StartupInfo.hStdOutput=streams[1]; startup.StartupInfo.hStdError=streams[2]; startup.lpAttributeList=attributes;
    if(!CreateProcessW(application,line,NULL,NULL,TRUE,CREATE_SUSPENDED|CREATE_NO_WINDOW|EXTENDED_STARTUPINFO_PRESENT|CREATE_UNICODE_ENVIRONMENT,environment,cwd,&startup.StartupInfo,&process)) {
        t->launch_error=(int)GetLastError(); code=(t->launch_error==ERROR_FILE_NOT_FOUND || t->launch_error==ERROR_PATH_NOT_FOUND) ? 127 : 126; goto cleanup;
    }
    if(!AssignProcessToJobObject(t->job,process.hProcess) || ResumeThread(process.hThread)==(DWORD)-1) {
        t->launch_error=(int)GetLastError();
        if(!TerminateProcess(process.hProcess,126)) t->cleanup_error=(int)GetLastError();
        if(WaitForSingleObject(process.hProcess,INFINITE)!=WAIT_OBJECT_0) t->cleanup_error=(int)GetLastError();
        goto cleanup;
    }
    t->process=process.hProcess; t->pid=process.dwProcessId; process.hProcess=NULL; code=0;
cleanup:
    if(code && !t->launch_error) { t->launch_error=(int)GetLastError(); if(!t->launch_error) t->launch_error=ERROR_GEN_FAILURE; }
    if(attributes) { DeleteProcThreadAttributeList(attributes); free(attributes); }
    if(process.hThread) CloseHandle(process.hThread);
    if(process.hProcess) CloseHandle(process.hProcess);
    for(int i=0;i<3;++i) if(streams[i]!=INVALID_HANDLE_VALUE && (i!=2 || streams[2]!=streams[1])) CloseHandle(streams[i]);
    if(code && t->job) { CloseHandle(t->job); t->job=NULL; }
    free(line); free(cwd); free(application); free(environment); return code;
}
static int mlf_ps_platform_poll(struct mlf_ps_process *t) {
    DWORD wait=WaitForSingleObject(t->process,0);
    if(wait==WAIT_TIMEOUT) return 0;
    DWORD code=126;
    if(wait!=WAIT_OBJECT_0 || !GetExitCodeProcess(t->process,&code)) t->cleanup_error=(int)GetLastError();
    t->exit_code=(int)code;
    FILETIME creation,exit,kernel,user;
    if(GetProcessTimes(t->process,&creation,&exit,&kernel,&user)) {
        ULARGE_INTEGER k,u; k.LowPart=kernel.dwLowDateTime; k.HighPart=kernel.dwHighDateTime; u.LowPart=user.dwLowDateTime; u.HighPart=user.dwHighDateTime;
        t->cpu=(double)(k.QuadPart+u.QuadPart)/1e7;
    }
    PROCESS_MEMORY_COUNTERS memory={0}; memory.cb=sizeof(memory);
    if(mlf_ps_memory_info(t->process,&memory)) t->rss=memory.PeakWorkingSetSize;
    /* A main-process exit is not a completed lifetime until descendants have
     * stopped. The job remains owned until accounting confirms that fact. */
    if(!TerminateJobObject(t->job,125)) t->cleanup_error=(int)GetLastError();
    for(;;) {
        JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting={0};
        if(!QueryInformationJobObject(t->job,JobObjectBasicAccountingInformation,&accounting,sizeof(accounting),NULL)) { t->cleanup_error=(int)GetLastError(); break; }
        if(!accounting.ActiveProcesses) break;
        mlf_ps_pause_loop();
    }
    if(!CloseHandle(t->job)) t->cleanup_error=(int)GetLastError();
    t->job=NULL;
    if(!CloseHandle(t->process)) t->cleanup_error=(int)GetLastError();
    t->process=NULL; return 1;
}
static void mlf_ps_platform_cancel(struct mlf_ps_process *t) {
    if(t->job && !TerminateJobObject(t->job,125)) t->cleanup_error=(int)GetLastError();
}
#ifdef MLF_PROCESS_STATIC_ADAPTER
static HANDLE mlf_ps_owner_handle(void) {
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0), owner=NULL;
    if(snapshot==INVALID_HANDLE_VALUE) return NULL;
    PROCESSENTRY32W entry={0}; entry.dwSize=sizeof(entry);
    if(Process32FirstW(snapshot,&entry)) do { if(entry.th32ProcessID==GetCurrentProcessId()) { owner=OpenProcess(SYNCHRONIZE,FALSE,entry.th32ParentProcessID); break; } } while(Process32NextW(snapshot,&entry));
    CloseHandle(snapshot); return owner;
}
#endif
#endif
/* The static v1 runner and the dynamic registry share these exact launch,
 * cancellation and reap paths. There is no runner invocation in this API. */
static int mlf_ps_launch_policy(const mlf_process_spec *spec,struct mlf_ps_process *process,int legacy) {
    memset(process,0,sizeof(*process));
#ifndef _WIN32
    process->control=process->result=-1;
#endif
    int code=mlf_ps_platform_launch(spec,process,legacy);
    if(!code) { process->next=mlf_ps_active; mlf_ps_active=process; }
    return code;
}
static int mlf_ps_launch(const mlf_process_spec *spec,struct mlf_ps_process *process) {
    return mlf_ps_launch_policy(spec,process,0);
}
static int mlf_ps_poll_task(struct mlf_ps_process *process) {
    if(!mlf_ps_platform_poll(process)) return 0;
    struct mlf_ps_process **link=&mlf_ps_active;
    while(*link && *link!=process) link=&(*link)->next;
    if(*link) *link=process->next;
    process->next=NULL;
    return 1;
}
static void mlf_ps_cancel_task(struct mlf_ps_process *process) { mlf_ps_platform_cancel(process); }

/* Static adapter telemetry. Measurement does not participate in admission. */
#ifdef MLF_PROCESS_STATIC_ADAPTER
static uint64_t mlf_ps_process_memory(struct mlf_ps_process *process) {
    uint64_t current=0;
#ifdef _WIN32
    SIZE_T capacity=64;
    JOBOBJECT_BASIC_PROCESS_ID_LIST *list=NULL;
    for(;;) {
        size_t bytes=sizeof(*list)+(capacity-1)*sizeof(ULONG_PTR);
        free(list); list=malloc(bytes);
        if(!list) break;
        if(QueryInformationJobObject(process->job,JobObjectBasicProcessIdList,list,(DWORD)bytes,NULL)) break;
        if(GetLastError()!=ERROR_MORE_DATA || capacity>MLF_PS_MAX_SLOTS) { free(list); list=NULL; break; }
        capacity*=2;
    }
    if(list) for(DWORD j=0;j<list->NumberOfProcessIdsInList;++j) {
        HANDLE p=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,(DWORD)list->ProcessIdList[j]);
        if(p) { PROCESS_MEMORY_COUNTERS info={0}; info.cb=sizeof(info); if(mlf_ps_memory_info(p,&info)) current+=info.WorkingSetSize; CloseHandle(p); }
    }
    free(list);
#else
    size_t count; struct mlf_ps_process_sample *samples=mlf_ps_process_samples(&count,1);
    if(!samples) return 0;
    for(size_t j=0;j<count;++j) if((uint64_t)samples[j].session==process->pid) current+=samples[j].rss;
    free(samples);
#endif
    return current;
}
#endif

enum mlf_ps_state { MLF_PS_QUEUED, MLF_PS_RUNNING, MLF_PS_STOPPING, MLF_PS_FINISHED };
struct mlf_ps_entry {
    enum mlf_ps_state state;
    mlf_process_spec spec;
    struct mlf_ps_process native;
    mlf_process_outcome outcome;
    uint64_t generation;
    size_t spec_bytes;
    uint32_t next_event;
};
struct mlf_ps_scope {
    struct mlf_ps_scope *next;
    mlf_process_scope id;
    mlf_process_options options;
    struct mlf_ps_entry *entries;
    uint32_t used,running,pending,unfinished,event_head,event_tail;
    size_t spec_bytes;
    int accepting;
};
static struct mlf_ps_scope *mlf_ps_scopes;
static uint64_t mlf_ps_next_scope=1,mlf_ps_next_generation=1;
static int mlf_ps_exit_registered;

static struct mlf_ps_scope *mlf_ps_find_scope(mlf_process_scope id) {
    for(struct mlf_ps_scope *scope=mlf_ps_scopes;scope;scope=scope->next) if(scope->id==id) return scope;
    return NULL;
}
static struct mlf_ps_entry *mlf_ps_find_entry(struct mlf_ps_scope *scope,mlf_process_handle handle) {
    if(handle.scope!=scope->id || handle.slot>=scope->used) return NULL;
    struct mlf_ps_entry *entry=&scope->entries[handle.slot];
    return entry->generation==handle.generation ? entry : NULL;
}
static mlf_process_handle mlf_ps_handle(struct mlf_ps_scope *scope,uint32_t slot) {
    mlf_process_handle handle={scope->id,scope->entries[slot].generation,slot}; return handle;
}
static int mlf_ps_utf8(const unsigned char *p,size_t size) {
    size_t i=0;
    while(i<size) {
        unsigned a=p[i++],n; uint32_t value,minimum;
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
static int mlf_ps_size_string(const char *s,size_t *total) {
    size_t n=0;
    while(s[n]) { if(n==MLF_PS_MAX_SPEC_BYTES) return 0; ++n; }
    if(n+1>MLF_PS_MAX_SPEC_BYTES-*total || !mlf_ps_utf8((const unsigned char *)s,n)) return 0;
    *total+=n+1; return 1;
}
static char *mlf_ps_copy_string(const char *s) {
    size_t n=strlen(s)+1; char *out=malloc(n); if(out) memcpy(out,s,n); return out;
}
static void mlf_ps_free_spec(struct mlf_ps_entry *entry) {
    const char *const *argv=entry->spec.argv,*const *env=entry->spec.env;
    if(argv) { for(size_t i=0;argv[i];++i) free((void *)argv[i]); free((void *)argv); }
    if(env) { for(size_t i=0;env[i];++i) free((void *)env[i]); free((void *)env); }
    free((void *)entry->spec.executable); free((void *)entry->spec.cwd);
    free((void *)entry->spec.input); free((void *)entry->spec.output); free((void *)entry->spec.error);
    memset(&entry->spec,0,sizeof(entry->spec));
}
static mlf_process_status mlf_ps_copy_spec(const mlf_process_spec *source,struct mlf_ps_entry *entry) {
    if(!source || !source->executable || !*source->executable || !source->argv || !source->argv[0] ||
       !isfinite(source->running_timeout_seconds) || source->running_timeout_seconds<0 ||
       !isfinite(source->total_timeout_seconds) || source->total_timeout_seconds<0 ||
       (source->environment!=MLF_PROCESS_ENV_INHERIT && source->environment!=MLF_PROCESS_ENV_REPLACE) ||
       (source->environment==MLF_PROCESS_ENV_INHERIT && source->env)) return MLF_PROCESS_INVALID_ARGUMENT;
    const char *fields[]={source->executable,source->cwd ? source->cwd : "",source->input ? source->input : "",source->output ? source->output : "",source->error ? source->error : ""};
    size_t bytes=0,argc=0,envc=0;
    for(size_t i=0;i<5;++i) if(!mlf_ps_size_string(fields[i],&bytes)) return MLF_PROCESS_INVALID_ARGUMENT;
    while(source->argv[argc]) {
        if(argc==MLF_PS_MAX_ARGUMENTS || !mlf_ps_size_string(source->argv[argc],&bytes)) return MLF_PROCESS_INVALID_ARGUMENT;
        ++argc;
    }
    if(source->env) while(source->env[envc]) {
        const char *item=source->env[envc],*equal=strchr(item,'=');
        if(envc==MLF_PS_MAX_ARGUMENTS || !equal || equal==item || !mlf_ps_size_string(item,&bytes)) return MLF_PROCESS_INVALID_ARGUMENT;
        ++envc;
    }
    size_t pointers=(argc+envc+2)*sizeof(char *);
    if(pointers>MLF_PS_MAX_SPEC_BYTES-bytes) return MLF_PROCESS_INVALID_ARGUMENT;
    entry->spec_bytes=bytes+pointers;
    entry->spec.environment=source->environment;
    entry->spec.running_timeout_seconds=source->running_timeout_seconds;
    entry->spec.total_timeout_seconds=source->total_timeout_seconds;
    entry->spec.executable=mlf_ps_copy_string(fields[0]); entry->spec.cwd=mlf_ps_copy_string(fields[1]);
    entry->spec.input=mlf_ps_copy_string(fields[2]); entry->spec.output=mlf_ps_copy_string(fields[3]); entry->spec.error=mlf_ps_copy_string(fields[4]);
    char **argv=mlf_ps_checked_alloc(argc+1,sizeof(char *)),**env=mlf_ps_checked_alloc(envc+1,sizeof(char *));
    entry->spec.argv=(const char *const *)argv; entry->spec.env=(const char *const *)env;
    if(!entry->spec.executable || !entry->spec.cwd || !entry->spec.input || !entry->spec.output || !entry->spec.error || !argv || !env) goto no_memory;
    for(size_t i=0;i<argc;++i) if(!(argv[i]=mlf_ps_copy_string(source->argv[i]))) goto no_memory;
    for(size_t i=0;i<envc;++i) if(!(env[i]=mlf_ps_copy_string(source->env[i]))) goto no_memory;
    return MLF_PROCESS_OK;
no_memory:
    mlf_ps_free_spec(entry); return MLF_PROCESS_NO_MEMORY;
}
static void mlf_ps_commit(struct mlf_ps_scope *scope,uint32_t slot) {
    struct mlf_ps_entry *entry=&scope->entries[slot];
    if(entry->state==MLF_PS_FINISHED) return;
    if(entry->state==MLF_PS_QUEUED) --scope->pending; else --scope->running;
    --scope->unfinished;
    entry->outcome.pid=entry->native.pid;
    entry->outcome.peak_rss_bytes=entry->native.rss;
    entry->outcome.cpu_seconds=entry->native.cpu;
    entry->outcome.launch_error=entry->native.launch_error;
    entry->outcome.cleanup_error=entry->native.cleanup_error;
    entry->outcome.finished_seconds=mlf_process_monotonic_seconds();
    entry->state=MLF_PS_FINISHED;
    entry->next_event=UINT32_MAX;
    if(scope->event_tail==UINT32_MAX) scope->event_head=slot;
    else scope->entries[scope->event_tail].next_event=slot;
    scope->event_tail=slot;
    scope->spec_bytes-=entry->spec_bytes; entry->spec_bytes=0;
    mlf_ps_free_spec(entry);
}
static void mlf_ps_request_cancel(struct mlf_ps_scope *scope,uint32_t slot,mlf_process_outcome_kind kind,int reason) {
    struct mlf_ps_entry *entry=&scope->entries[slot];
    if(entry->state==MLF_PS_FINISHED || entry->state==MLF_PS_STOPPING) return;
    entry->outcome.kind=kind; entry->outcome.cancel_reason=reason;
    entry->outcome.exit_code=kind==MLF_PROCESS_TIMED_OUT ? 124 : 125;
    if(entry->state==MLF_PS_QUEUED) mlf_ps_commit(scope,slot);
    else { entry->state=MLF_PS_STOPPING; mlf_ps_cancel_task(&entry->native); }
}
static void mlf_ps_pump(struct mlf_ps_scope *scope) {
    /* Commit observed completion before admitting any later work. Once a
     * cancellation was accepted its outcome cannot become a successful exit. */
    for(uint32_t i=0;i<scope->used;++i) {
        struct mlf_ps_entry *entry=&scope->entries[i];
        if(entry->state!=MLF_PS_RUNNING && entry->state!=MLF_PS_STOPPING) continue;
        if(mlf_ps_poll_task(&entry->native)) {
            if(entry->state!=MLF_PS_STOPPING) {
                entry->outcome.kind=entry->native.launch_error ? MLF_PROCESS_LAUNCH_FAILED : MLF_PROCESS_EXITED;
                entry->outcome.exit_code=entry->native.exit_code;
            }
            mlf_ps_commit(scope,i);
        }
    }
    double now=mlf_process_monotonic_seconds();
    for(uint32_t i=0;i<scope->used;++i) {
        struct mlf_ps_entry *entry=&scope->entries[i];
        if(entry->state==MLF_PS_FINISHED || entry->state==MLF_PS_STOPPING) continue;
        if((entry->spec.total_timeout_seconds>0 && now-entry->outcome.submitted_seconds>=entry->spec.total_timeout_seconds) ||
           (entry->state==MLF_PS_RUNNING && entry->spec.running_timeout_seconds>0 && now-entry->outcome.started_seconds>=entry->spec.running_timeout_seconds))
            mlf_ps_request_cancel(scope,i,MLF_PROCESS_TIMED_OUT,0);
    }
    for(uint32_t i=0;i<scope->used && scope->running<scope->options.jobs;++i) {
        struct mlf_ps_entry *entry=&scope->entries[i];
        if(entry->state!=MLF_PS_QUEUED) continue;
        /* Recheck a queued total deadline immediately before admission. */
        now=mlf_process_monotonic_seconds();
        if(entry->spec.total_timeout_seconds>0 && now-entry->outcome.submitted_seconds>=entry->spec.total_timeout_seconds) {
            mlf_ps_request_cancel(scope,i,MLF_PROCESS_TIMED_OUT,0); continue;
        }
        entry->outcome.started_seconds=now;
        int code=mlf_ps_launch(&entry->spec,&entry->native);
        if(code) {
            entry->outcome.kind=MLF_PROCESS_LAUNCH_FAILED; entry->outcome.exit_code=code;
            mlf_ps_commit(scope,i);
        } else { entry->state=MLF_PS_RUNNING; --scope->pending; ++scope->running; }
    }
}
static void mlf_ps_pump_all(void) {
    for(struct mlf_ps_scope *scope=mlf_ps_scopes;scope;scope=scope->next) mlf_ps_pump(scope);
}
static mlf_process_status mlf_ps_event(struct mlf_ps_scope *scope,mlf_process_event *event) {
    if(scope->event_head==UINT32_MAX) return scope->unfinished ? MLF_PROCESS_WOULD_BLOCK : MLF_PROCESS_EMPTY;
    uint32_t slot=scope->event_head;
    struct mlf_ps_entry *entry=&scope->entries[slot];
    event->handle=mlf_ps_handle(scope,slot); event->outcome=entry->outcome;
    scope->event_head=entry->next_event;
    if(scope->event_head==UINT32_MAX) scope->event_tail=UINT32_MAX;
    return MLF_PROCESS_OK;
}
mlf_process_status mlf_process_scope_create(const mlf_process_options *options,mlf_process_scope *out) {
    if(!options || !out || !options->jobs || options->jobs>MLF_PS_MAX_SLOTS || !options->max_retained ||
       options->max_retained>MLF_PS_MAX_SLOTS || options->max_pending>options->max_retained) return MLF_PROCESS_INVALID_ARGUMENT;
    if(!mlf_ps_next_scope) return MLF_PROCESS_SYSTEM_ERROR;
    struct mlf_ps_scope *scope=calloc(1,sizeof(*scope));
    if(!scope) return MLF_PROCESS_NO_MEMORY;
    scope->entries=mlf_ps_checked_alloc(options->max_retained,sizeof(*scope->entries));
    if(!scope->entries) { free(scope); return MLF_PROCESS_NO_MEMORY; }
    if(!mlf_ps_exit_registered) {
        if(atexit(mlf_process_shutdown)) { free(scope->entries); free(scope); return MLF_PROCESS_SYSTEM_ERROR; }
        mlf_ps_exit_registered=1;
    }
    scope->options=*options; scope->id=mlf_ps_next_scope++; scope->accepting=1;
    scope->event_head=scope->event_tail=UINT32_MAX;
    scope->next=mlf_ps_scopes; mlf_ps_scopes=scope; *out=scope->id;
    return MLF_PROCESS_OK;
}
mlf_process_status mlf_process_submit(mlf_process_scope id,const mlf_process_spec *spec,mlf_process_handle *out) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    if(!out) return MLF_PROCESS_INVALID_ARGUMENT;
    if(!scope->accepting) return MLF_PROCESS_SCOPE_CLOSED;
    mlf_ps_pump_all();
    if(scope->used==scope->options.max_retained) return MLF_PROCESS_RETENTION_FULL;
    if(scope->running>=scope->options.jobs && scope->pending>=scope->options.max_pending) return MLF_PROCESS_QUEUE_FULL;
    if(!mlf_ps_next_generation) return MLF_PROCESS_SYSTEM_ERROR;
    struct mlf_ps_entry *entry=&scope->entries[scope->used];
    mlf_process_status copied=mlf_ps_copy_spec(spec,entry);
    if(copied!=MLF_PROCESS_OK) return copied;
    if(entry->spec_bytes>MLF_PS_MAX_SPEC_BYTES-scope->spec_bytes) { mlf_ps_free_spec(entry); return MLF_PROCESS_QUEUE_FULL; }
    entry->generation=mlf_ps_next_generation++; entry->state=MLF_PS_QUEUED;
    entry->outcome.submitted_seconds=mlf_process_monotonic_seconds();
    scope->spec_bytes+=entry->spec_bytes; ++scope->pending; ++scope->unfinished;
    *out=mlf_ps_handle(scope,scope->used++);
    mlf_ps_pump_all();
    return MLF_PROCESS_OK;
}
mlf_process_status mlf_process_poll(mlf_process_scope id,mlf_process_event *event) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    if(!event) return MLF_PROCESS_INVALID_ARGUMENT;
    mlf_ps_pump_all(); return mlf_ps_event(scope,event);
}
mlf_process_status mlf_process_wait_next(mlf_process_scope id,double wait_seconds,mlf_process_event *event) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    if(!event || !isfinite(wait_seconds)) return MLF_PROCESS_INVALID_ARGUMENT;
    double start=mlf_process_monotonic_seconds();
    for(;;) {
        mlf_ps_pump_all(); mlf_process_status status=mlf_ps_event(scope,event);
        if(status!=MLF_PROCESS_WOULD_BLOCK) return status;
        if(wait_seconds==0) return MLF_PROCESS_WOULD_BLOCK;
        if(wait_seconds>0 && mlf_process_monotonic_seconds()-start>=wait_seconds) return MLF_PROCESS_WAIT_TIMEOUT;
        mlf_ps_pause_loop();
    }
}
mlf_process_status mlf_process_await(mlf_process_scope id,mlf_process_handle handle,double wait_seconds,mlf_process_outcome *outcome) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    if(!outcome || !isfinite(wait_seconds)) return MLF_PROCESS_INVALID_ARGUMENT;
    struct mlf_ps_entry *entry=mlf_ps_find_entry(scope,handle);
    if(!entry) return MLF_PROCESS_INVALID_HANDLE;
    double start=mlf_process_monotonic_seconds();
    for(;;) {
        mlf_ps_pump_all();
        if(entry->state==MLF_PS_FINISHED) { *outcome=entry->outcome; return MLF_PROCESS_OK; }
        if(wait_seconds==0) return MLF_PROCESS_WOULD_BLOCK;
        if(wait_seconds>0 && mlf_process_monotonic_seconds()-start>=wait_seconds) return MLF_PROCESS_WAIT_TIMEOUT;
        mlf_ps_pause_loop();
    }
}
mlf_process_status mlf_process_request_cancel(mlf_process_scope id,mlf_process_handle handle,int reason) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    struct mlf_ps_entry *entry=mlf_ps_find_entry(scope,handle);
    if(!entry) return MLF_PROCESS_INVALID_HANDLE;
    mlf_ps_request_cancel(scope,handle.slot,MLF_PROCESS_CANCELLED,reason);
    return MLF_PROCESS_OK;
}
mlf_process_status mlf_process_cancel(mlf_process_scope id,mlf_process_handle handle,int reason) {
    mlf_process_status requested=mlf_process_request_cancel(id,handle,reason);
    if(requested!=MLF_PROCESS_OK) return requested;
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    struct mlf_ps_entry *entry=mlf_ps_find_entry(scope,handle);
    while(entry->state!=MLF_PS_FINISHED) { mlf_ps_pump_all(); if(entry->state!=MLF_PS_FINISHED) mlf_ps_pause_loop(); }
    return entry->outcome.cleanup_error ? MLF_PROCESS_SYSTEM_ERROR : MLF_PROCESS_OK;
}
mlf_process_status mlf_process_cancel_scope(mlf_process_scope id,int reason) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    scope->accepting=0;
    for(uint32_t i=0;i<scope->used;++i) mlf_ps_request_cancel(scope,i,MLF_PROCESS_CANCELLED,reason);
    while(scope->unfinished) { mlf_ps_pump_all(); if(scope->unfinished) mlf_ps_pause_loop(); }
    for(uint32_t i=0;i<scope->used;++i) if(scope->entries[i].outcome.cleanup_error) return MLF_PROCESS_SYSTEM_ERROR;
    return MLF_PROCESS_OK;
}
mlf_process_status mlf_process_scope_close(mlf_process_scope id,mlf_process_close_mode mode) {
    struct mlf_ps_scope *scope=mlf_ps_find_scope(id);
    if(!scope) return MLF_PROCESS_INVALID_SCOPE;
    if(mode!=MLF_PROCESS_CLOSE_JOIN && mode!=MLF_PROCESS_CLOSE_CANCEL) return MLF_PROCESS_INVALID_ARGUMENT;
    scope->accepting=0;
    if(mode==MLF_PROCESS_CLOSE_CANCEL) (void)mlf_process_cancel_scope(id,0);
    while(scope->unfinished) { mlf_ps_pump_all(); if(scope->unfinished) mlf_ps_pause_loop(); }
    mlf_process_status status=MLF_PROCESS_OK;
    for(uint32_t i=0;i<scope->used;++i) if(scope->entries[i].outcome.cleanup_error) status=MLF_PROCESS_SYSTEM_ERROR;
    struct mlf_ps_scope **link=&mlf_ps_scopes;
    while(*link && *link!=scope) link=&(*link)->next;
    if(*link) *link=scope->next;
    free(scope->entries); free(scope); return status;
}
void mlf_process_shutdown(void) {
    /* Stop admission in every scope before joining any: a join services all
     * scopes and must never start queued work during process-wide shutdown. */
    for(struct mlf_ps_scope *scope=mlf_ps_scopes;scope;scope=scope->next) {
        scope->accepting=0;
        for(uint32_t i=0;i<scope->used;++i) mlf_ps_request_cancel(scope,i,MLF_PROCESS_CANCELLED,0);
    }
    while(mlf_ps_scopes) {
        if(mlf_process_scope_close(mlf_ps_scopes->id,MLF_PROCESS_CLOSE_CANCEL)!=MLF_PROCESS_OK)
            fputs("mlf-process-supervisor: scope cleanup failed during shutdown\n",stderr);
    }
}
const char *mlf_process_status_string(mlf_process_status status) {
    static const char *const names[]={"ok","invalid_argument","no_memory","invalid_scope","invalid_handle","scope_closed","queue_full","retention_full","would_block","empty","wait_timeout","unsupported","system_error"};
    return (unsigned)status<sizeof(names)/sizeof(names[0]) ? names[status] : "unknown";
}
#endif /* MLF_PROCESS_SUPERVISOR_IMPLEMENTED */
