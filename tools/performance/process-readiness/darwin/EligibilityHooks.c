#include <sys/types.h>
#include <sys/event.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
static int owned=-1;
static int64_t opened,registered,waits,closed,cloexec;
int mlf_ready_kqueue(void) {
    if(owned!=-1)abort(); int fd=kqueue(); if(fd>=0){owned=fd;++opened;}return fd;
}
int mlf_ready_fcntl(int fd,int command,...) {
    va_list args;va_start(args,command);
    if(fd==owned) {
        int flags=va_arg(args,int);va_end(args);
        if(command!=F_SETFD || flags!=FD_CLOEXEC)abort();
        int result=fcntl(fd,command,flags);
        if(!result && (fcntl(fd,F_GETFD)&FD_CLOEXEC))++cloexec;
        return result;
    }
    struct flock *lock=va_arg(args,struct flock*);va_end(args);
    if(command!=F_SETLKW)abort();return fcntl(fd,command,lock);
}
int mlf_ready_kevent(int fd,const struct kevent *changes,int nc,struct kevent *events,int ne,const struct timespec *timeout) {
    if(fd!=owned)abort();
    if(nc)++registered;else ++waits;
    return kevent(fd,changes,nc,events,ne,timeout);
}
int mlf_ready_close(int fd) {
    if(fd==owned){++closed;owned=-1;}return close(fd);
}
int64_t mlf_ready_stat(int n) {
    int64_t values[]={opened,registered,waits,closed,cloexec};
    if(n<0 || n>=5)abort();return values[n];
}
int mlf_ready_fd_count(void) {
    DIR*d=opendir("/dev/fd");if(!d)return -1;int n=0;struct dirent*p;
    while((p=readdir(d)))if(p->d_name[0]!='.')++n;
    if(closedir(d))return -1;return n;
}
