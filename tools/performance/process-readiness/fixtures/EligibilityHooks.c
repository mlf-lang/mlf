#define _DEFAULT_SOURCE 1
#include <stdint.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <dirent.h>
#include <signal.h>
#include <sys/syscall.h>
static int64_t attempts,opened,closed,polls,cloexec,eligible;
static int owned=-1;
long mlf_wait_test_syscall(long number,...) {
  va_list args;va_start(args,number);long pid=va_arg(args,long),flags=va_arg(args,long);va_end(args);
  if(number!=SYS_pidfd_open || flags!=0 || owned!=-1) abort();
  ++attempts;long fd=syscall(number,pid,flags);
  if(fd>=0){++opened;owned=(int)fd;if(fcntl(owned,F_GETFD)&FD_CLOEXEC)++cloexec;}
  return fd;
}
int mlf_wait_test_poll(struct pollfd *fds,nfds_t count,int timeout) {
  if(count!=1 || timeout!=10 || fds[0].fd!=owned || fds[0].events!=POLLIN)abort();
  ++polls;return poll(fds,count,timeout);
}
int mlf_wait_test_close(int fd) {
  if(fd==owned){++closed;owned=-1;}return close(fd);
}
int64_t mlf_wait_test_stat(int which) {
  struct sigaction a;eligible=!sigaction(SIGCHLD,NULL,&a)&&a.sa_handler==SIG_DFL&&!(a.sa_flags&SA_NOCLDWAIT);
  int64_t values[]={attempts,opened,closed,polls,cloexec,eligible};
  if(which<0 || which>5)abort();return values[which];
}
int mlf_wait_test_fd_count(void) {
  DIR *d=opendir("/proc/self/fd");if(!d)return -1;int n=0;struct dirent *p;
  while((p=readdir(d)))if(p->d_name[0]!='.')++n;
  if(closedir(d))return -1;return n;
}
