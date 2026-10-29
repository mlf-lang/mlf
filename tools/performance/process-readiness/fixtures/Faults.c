#define _DEFAULT_SOURCE 1
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/syscall.h>
#include <signal.h>
#include <poll.h>
#include <unistd.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static const char *mode;static int initialized,waits,clocks,closes;static char trace[4096];
static void emit(void){fprintf(stderr,"MOCK %s\n",trace);}
static void event(const char *name){
 if(!initialized){initialized=1;mode=getenv("MLF_WAIT_FAULT");if(!mode)abort();atexit(emit);}
 if(strlen(trace)+strlen(name)+2>=sizeof(trace))abort();if(*trace)strcat(trace,",");strcat(trace,name);
}
static int is(const char *name){return !strcmp(mode,name);}
static void custom(int signal){(void)signal;}
pid_t mlf_mock_fork(void){event("fork");if(is("fork-fail")){errno=EAGAIN;return -1;}return 4242;}
int mlf_mock_clock_gettime(clockid_t clock,struct timespec *value){
 event("clock");if(clock!=CLOCK_MONOTONIC || ++clocks>4)abort();
 if(is("start-clock-fail")){errno=EINVAL;return -1;}
 value->tv_sec=clocks>1 && (is("timeout") || is("deadline-ready"))?2:0;value->tv_nsec=0;return 0;
}
int mlf_mock_sigaction(int signal,const struct sigaction *action,struct sigaction *old){
 event("sigaction");if(signal!=SIGCHLD || action || !old)abort();
 if(is("sig-query-fail")){errno=EINVAL;return -1;}
 memset(old,0,sizeof(*old));old->sa_handler=is("sig-ignore")?SIG_IGN:is("sig-custom")?custom:SIG_DFL;
 if(is("sig-no-wait"))old->sa_flags=SA_NOCLDWAIT;return 0;
}
long mlf_mock_syscall(long number,...){
 event("open");va_list a;va_start(a,number);long pid=va_arg(a,long),flags=va_arg(a,long);va_end(a);
 if(number!=SYS_pidfd_open || pid!=4242 || flags!=0)abort();
 if(is("open-enosys")||is("open-emfile")||is("open-eperm")){errno=is("open-enosys")?ENOSYS:is("open-emfile")?EMFILE:EPERM;return -1;}return 17;
}
pid_t mlf_mock_waitpid(pid_t pid,int *status,int flags){
 event(flags?"wait":"reap");if(pid!=4242 || (flags!=WNOHANG && flags!=0) || ++waits>4)abort();
 if(is("wait-error")){errno=ECHILD;return -1;}
 if(!flags || waits>1 || is("immediate") || is("deadline-ready")){if(status)*status=7<<8;return pid;}return 0;
}
int mlf_mock_poll(struct pollfd *fds,nfds_t count,int timeout){
 event("poll");if(count!=1 || timeout!=10 || fds[0].fd!=17 || fds[0].events!=POLLIN)abort();
 if(is("poll-eintr")||is("poll-error")){errno=is("poll-eintr")?EINTR:EINVAL;return -1;}
 fds[0].revents=is("poll-nval")?POLLNVAL:is("poll-err-event")?POLLERR:is("poll-hup")?POLLHUP:POLLIN;return 1;
}
int mlf_mock_close(int fd){event("close");if(fd!=17 || ++closes!=1)abort();if(is("close-eintr")){errno=EINTR;return -1;}return 0;}
int mlf_mock_nanosleep(const struct timespec *request,struct timespec *left){event("sleep");if(request->tv_sec!=0||request->tv_nsec!=10000000||left)abort();return 0;}
int mlf_mock_kill(pid_t pid,int signal){event(pid<0?"kill-group":"kill-child");if((pid!=4242&&pid!=-4242)||signal!=SIGKILL)abort();return 0;}
