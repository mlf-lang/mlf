/* Real inherited-state controls for both authenticated ordinary host objects. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
extern int mlf_ghc_host(int,const char*,size_t,const char*,size_t,int64_t,char**,size_t*,int64_t*);
extern void mlf_ghc_shutdown(void);
static void caught(int signal) {(void)signal;}
static int invoke(const char *file,const char *mode) {
    const char *fields[]={"3","","","",file,"child",mode};
    char spec[8192];size_t n=0;
    for(size_t i=0;i<7;++i) {
        size_t k=strlen(fields[i])+1;if(n+k>sizeof(spec))return 201;
        memcpy(spec+n,fields[i],k);n+=k;
    }
    char *bytes=NULL;size_t size=0;int64_t number=0;
    int error=mlf_ghc_host(7,"",0,spec,n,0,&bytes,&size,&number);
    free(bytes);return error || size ? 202 : (int)number;
}
static int child(int mode) {
    if(mode<6) {
        errno=0;return fcntl(mode%3,F_GETFD)==-1 && errno==EBADF ? 0 : 41;
    }
    if(mode==6)return fcntl(61,F_GETFD)==0 ? 0 : 42;
    if(mode==7) {errno=0;return fcntl(61,F_GETFD)==-1 && errno==EBADF ? 0 : 43;}
    if(mode==8) {
        struct sigaction first,second;sigset_t mask;
        if(sigaction(SIGUSR1,NULL,&first) || sigaction(SIGUSR2,NULL,&second) || sigprocmask(SIG_SETMASK,NULL,&mask))return 44;
        return first.sa_handler==SIG_IGN && second.sa_handler==SIG_DFL && sigismember(&mask,SIGTERM)==1 ? 0 : 45;
    }
    return mode==10 ? 0 : 46;
}
int main(int argc,char **argv) {
    /* The cwd's shadow `true` must not win when PATH is unset. */
    if(argc<2)return 17;
    if(!strcmp(argv[1],"child"))return argc==3 ? child(atoi(argv[2])) : 90;
    if(argc!=3)return 91;
    int mode=atoi(argv[1]);if(mode<0 || mode>10)return 92;
    if(invoke("/usr/bin/true","warm"))return 93;
    int saved=-1,fd=-1,extra=-1;const char *file=argv[0];
    if(mode<6) {
        fd=mode%3;saved=fcntl(fd,F_DUPFD_CLOEXEC,64);if(saved<0)return 94;
        if(mode<3) {if(close(fd))return 95;}
        else if(fcntl(fd,F_SETFD,FD_CLOEXEC))return 96;
    } else if(mode<8) {
        extra=open("/dev/null",O_RDONLY);if(extra<0 || dup2(extra,61)<0)return 97;
        if(extra!=61)close(extra);
        if(fcntl(61,F_SETFD,mode==7 ? FD_CLOEXEC : 0))return 98;
    } else if(mode==8) {
        struct sigaction action;memset(&action,0,sizeof(action));sigemptyset(&action.sa_mask);
        action.sa_handler=SIG_IGN;if(sigaction(SIGUSR1,&action,NULL))return 99;
        action.sa_handler=caught;if(sigaction(SIGUSR2,&action,NULL))return 100;
        sigset_t mask;sigemptyset(&mask);sigaddset(&mask,SIGTERM);
        if(sigprocmask(SIG_BLOCK,&mask,NULL))return 101;
    } else {
        if(chdir(argv[2]) || symlink(argv[0],mode==9 ? "true" : "path-child"))return 102;
        if(mode==9) {if(unsetenv("PATH"))return 103;file="true";}
        else {if(setenv("PATH","",1))return 104;file="path-child";}
    }
    int status=invoke(file,argv[1]);
    if(saved>=0) {if(dup2(saved,fd)<0 || close(saved))return 105;clearerr(stdin);clearerr(stdout);clearerr(stderr);}
    if(mode==6 || mode==7)close(61);
    mlf_ghc_shutdown();
    if(status) {fprintf(stderr,"mode %d, child status %d\n",mode,status);return 106;}
    printf("PASS inherited state %d\n",mode);return 0;
}
