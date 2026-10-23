/* Portable process/file transport for the native build-runner fixtures. */
#ifndef MLF_BUILD_RUNNER_TEST_SUPPORT_H
#define MLF_BUILD_RUNNER_TEST_SUPPORT_H
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE 1
#define _DEFAULT_SOURCE 1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdint.h>
#include <time.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#include <direct.h>
#include <io.h>
#include <fcntl.h>
#include "../../runtime/mlf_windows_path.h"
typedef struct { HANDLE handle; DWORD id; } test_process;
static inline wchar_t *test_wide(const char *s) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,NULL,0);
    wchar_t *w=n ? calloc((size_t)n,sizeof(wchar_t)) : NULL;
    if(w) MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,w,n);
    return w;
}
static inline FILE *test_open(const char *path,const char *mode) {
    wchar_t *w=test_wide(path),*p=w ? mlf_windows_path(w) : NULL,*m=test_wide(mode);
    FILE *f=p&&m ? _wfopen(p,m) : NULL; free(w); free(p); free(m); return f;
}
static inline double test_now(void) { return (double)GetTickCount64()/1000.; }
static inline void test_pause(void) { Sleep(5); }
static inline long test_pid(void) { return (long)GetCurrentProcessId(); }
static inline void test_mkdir(const char *path) { wchar_t *w=test_wide(path); if(!w || (!CreateDirectoryW(w,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)) abort(); free(w); }
static inline test_process test_spawn(char **argv) {
    size_t capacity=1; for(char **a=argv;*a;++a) capacity+=2*strlen(*a)+3;
    wchar_t *line=calloc(capacity,sizeof(wchar_t)),*out=line;
    if(!line) abort();
    for(char **a=argv;*a;++a) { wchar_t *w=test_wide(*a); if(!w) abort(); const wchar_t *p=w;
        if(a!=argv) *out++=L' ';
        *out++=L'"'; while(*p) { size_t n=0; while(*p==L'\\') { ++n; ++p; } size_t emit=(*p==L'"'||!*p)?2*n:n; while(emit--) *out++=L'\\'; if(*p==L'"') *out++=L'\\'; if(*p) *out++=*p++; } *out++=L'"'; free(w);
    }
    *out=0; STARTUPINFOW startup={0}; startup.cb=sizeof(startup); PROCESS_INFORMATION process={0};
    int ok=CreateProcessW(NULL,line,NULL,NULL,FALSE,0,NULL,NULL,&startup,&process); free(line);
    if(!ok) abort(); CloseHandle(process.hThread); test_process result={process.hProcess,process.dwProcessId}; return result;
}
static inline int test_poll(test_process p,int *status) {
    if(WaitForSingleObject(p.handle,0)==WAIT_TIMEOUT) return 0;
    DWORD code=126; GetExitCodeProcess(p.handle,&code); *status=(int)code; CloseHandle(p.handle); return 1;
}
static inline void test_kill(test_process p) { TerminateProcess(p.handle,137); }
static inline int test_alive(long pid) {
    HANDLE p=OpenProcess(SYNCHRONIZE,FALSE,(DWORD)pid); if(!p) return 0;
    int alive=WaitForSingleObject(p,0)==WAIT_TIMEOUT; CloseHandle(p); return alive;
}
#else
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
typedef struct { pid_t id; } test_process;
static inline FILE *test_open(const char *path,const char *mode) { return fopen(path,mode); }
static inline double test_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (double)t.tv_sec+(double)t.tv_nsec/1e9; }
static inline void test_pause(void) { struct timespec t={0,5000000}; nanosleep(&t,NULL); }
static inline long test_pid(void) { return (long)getpid(); }
static inline void test_mkdir(const char *path) { if(mkdir(path,0700) && errno!=EEXIST) abort(); }
static inline test_process test_spawn(char **argv) {
    pid_t pid=fork(); if(pid<0) abort(); if(!pid) { execvp(argv[0],argv); _exit(127); } test_process result={pid}; return result;
}
static inline int test_poll(test_process p,int *status) {
    int raw; pid_t done=waitpid(p.id,&raw,WNOHANG); if(!done || (done<0&&errno==EINTR)) return 0;
    if(done<0) abort(); *status=WIFEXITED(raw)?WEXITSTATUS(raw):128+WTERMSIG(raw); return 1;
}
static inline void test_kill(test_process p) { kill(p.id,SIGKILL); }
static inline int test_alive(long pid) {
#ifdef __linux__
    /* A reparented zombie has released locks and cannot execute. Container
     * PID 1 may not reap it immediately; do not mistake that for live work. */
    char path[80],line[1024]; snprintf(path,sizeof(path),"/proc/%ld/stat",pid);
    FILE *f=fopen(path,"r"); if(f) { char *text=fgets(line,sizeof(line),f); fclose(f); char *last=text?strrchr(text,')'):NULL; if(last && last[1]==' ' && last[2]=='Z') return 0; }
#endif
    return kill((pid_t)pid,0)==0 || errno==EPERM;
}
#endif
static inline int test_wait(test_process p,double bound) {
    double start=test_now(); int status;
    while(!test_poll(p,&status)) { if(test_now()-start>bound) { test_kill(p); while(!test_poll(p,&status)) test_pause(); return 124; } test_pause(); }
    return status;
}
static inline int test_exists(const char *path) { FILE *f=test_open(path,"rb"); if(!f) return 0; fclose(f); return 1; }
static inline void test_touch(const char *path) { FILE *f=test_open(path,"wb"); if(!f) abort(); fclose(f); }
static inline void test_write_pid(const char *path) {
    /* Readiness must never expose an empty/partially written process ID. */
    size_t size=strlen(path)+40; char *temporary=malloc(size); if(!temporary) abort();
    snprintf(temporary,size,"%s.%ld.tmp",path,test_pid());
    FILE *f=test_open(temporary,"wb"); if(!f) abort();
    if(fprintf(f,"%ld\n",test_pid())<0 || fclose(f)) abort();
#ifdef _WIN32
    wchar_t *from=test_wide(temporary),*to=test_wide(path);
    if(!from || !to || _wrename(from,to)) abort(); free(from); free(to);
#else
    if(rename(temporary,path)) abort();
#endif
    free(temporary);
}
static inline int test_await(const char *path,double bound) { double start=test_now(); while(!test_exists(path)) { if(test_now()-start>bound) return 0; test_pause(); } return 1; }
static inline char *test_read(const char *path) {
    FILE *f=test_open(path,"rb"); if(!f) return NULL;
    if(fseek(f,0,SEEK_END)) abort(); long n=ftell(f); if(n<0 || fseek(f,0,SEEK_SET)) abort();
    char *s=calloc((size_t)n+1,1); if(!s || fread(s,1,(size_t)n,f)!=(size_t)n) abort(); fclose(f); return s;
}
#ifdef _WIN32
#define TEST_MAIN(function) \
int wmain(int argc,wchar_t **wide_argv) { \
    _setmode(_fileno(stdin),_O_BINARY); _setmode(_fileno(stdout),_O_BINARY); _setmode(_fileno(stderr),_O_BINARY); \
    char **argv=calloc((size_t)argc+1,sizeof(char *)); if(!argv) return 70; \
    for(int i=0;i<argc;++i) { int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide_argv[i],-1,NULL,0,NULL,NULL); argv[i]=n?calloc((size_t)n,1):NULL; if(!argv[i] || !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide_argv[i],-1,argv[i],n,NULL,NULL)) return 64; } \
    int code=function(argc,argv); for(int i=0;i<argc;++i) free(argv[i]); free(argv); return code; \
}
#else
#define TEST_MAIN(function) int main(int argc,char **argv) { return function(argc,argv); }
#endif
#endif
