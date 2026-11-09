/* Independent, exact syscall-order expectations live in run_controls.py. */
#include <sys/types.h>
#include <sys/event.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static const char *mode;
static int initialized, waits, clocks, closes;
static char trace[4096];
static void emit(void) { fprintf(stderr,"MOCK %s\n",trace); }
static void event(const char *name) {
    if (!initialized) { initialized=1; mode=getenv("MLF_WAIT_FAULT"); if(!mode)abort(); atexit(emit); }
    if (strlen(trace)+strlen(name)+2>=sizeof(trace)) abort();
    if (*trace) strcat(trace,","); strcat(trace,name);
}
static int is(const char *name) { return !strcmp(mode,name); }
static void custom(int signal) { (void)signal; }
pid_t mlf_mock_fork(void) {
    event("fork"); if(is("fork-fail")){errno=EAGAIN;return -1;} return 4242;
}
int mlf_mock_clock_gettime(clockid_t clock,struct timespec *value) {
    event("clock"); if(clock!=CLOCK_MONOTONIC || ++clocks>4)abort();
    if(is("start-clock-fail")){errno=EINVAL;return -1;}
    value->tv_sec=clocks>1 && (is("timeout") || is("deadline-ready"))?2:0;
    value->tv_nsec=0; return 0;
}
int mlf_mock_sigaction(int signal,const struct sigaction *action,struct sigaction *old) {
    event("sigaction"); if(signal!=SIGCHLD || action || !old)abort();
    if(is("sig-query-fail")){errno=EINVAL;return -1;}
    memset(old,0,sizeof(*old));
    old->sa_handler=is("sig-ignore")?SIG_IGN:is("sig-custom")?custom:SIG_DFL;
    if(is("sig-no-wait"))old->sa_flags=SA_NOCLDWAIT; return 0;
}
int mlf_mock_kqueue(void) {
    event("open");
    if(is("open-emfile") || is("open-enomem")){errno=is("open-emfile")?EMFILE:ENOMEM;return -1;}
    return 17;
}
int mlf_mock_fcntl(int fd,int command,...) {
    event("cloexec"); va_list args;va_start(args,command);int flags=va_arg(args,int);va_end(args);
    if(fd!=17 || command!=F_SETFD || flags!=FD_CLOEXEC)abort();
    if(is("cloexec-fail")){errno=EBADF;return -1;} return 0;
}
int mlf_mock_kevent(int fd,const struct kevent *changes,int nc,struct kevent *events,int ne,const struct timespec *timeout) {
    if(fd!=17)abort();
    if(nc) {
        event("register");
        if(nc!=1 || !changes || ne || events || timeout || changes->ident!=4242 ||
           changes->filter!=EVFILT_PROC || changes->flags!=(EV_ADD|EV_ONESHOT) ||
           changes->fflags!=NOTE_EXIT || changes->data || changes->udata)abort();
        if(is("register-esrch") || is("register-eintr") || is("register-eperm")) {
            errno=is("register-esrch")?ESRCH:is("register-eintr")?EINTR:EPERM; return -1;
        }
        return 0;
    }
    event("event");
    if(changes || ne!=1 || !events || !timeout || timeout->tv_sec || timeout->tv_nsec!=10000000)abort();
    if(is("event-eintr") || is("event-error")){errno=is("event-eintr")?EINTR:EINVAL;return -1;}
    if(is("event-timeout"))return 0;
    EV_SET(events,is("event-wrong-pid")?4243:4242,is("event-wrong-filter")?EVFILT_READ:EVFILT_PROC,
           is("event-ev-error")?EV_ERROR:0,is("event-no-exit")?NOTE_EXEC:NOTE_EXIT,0,NULL);
    return is("event-count")?2:1;
}
pid_t mlf_mock_waitpid(pid_t pid,int *status,int flags) {
    event(flags?"wait":"reap"); if(pid!=4242 || (flags!=WNOHANG && flags!=0) || ++waits>4)abort();
    if(is("wait-error")){errno=ECHILD;return -1;}
    if(is("wait-eintr") && waits==1){errno=EINTR;return -1;}
    if(!flags || waits>1 || is("immediate") || is("deadline-ready")){if(status)*status=7<<8;return pid;}
    return 0;
}
int mlf_mock_close(int fd) {
    event("close"); if(fd!=17 || ++closes!=1)abort();
    if(is("close-eintr")){errno=EINTR;return -1;}return 0;
}
int mlf_mock_nanosleep(const struct timespec *request,struct timespec *left) {
    event("sleep"); if(request->tv_sec || request->tv_nsec!=10000000 || left)abort();return 0;
}
int mlf_mock_kill(pid_t pid,int signal) {
    event(pid<0?"kill-group":"kill-child"); if((pid!=4242 && pid!=-4242) || signal!=SIGKILL)abort();return 0;
}
