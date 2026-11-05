#include <unistd.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    if(argc!=3)return 90;
    const char *value=getenv("MLF_SPAWN_SENTINEL");
    if(!value || strcmp(value,"inherited λ environment"))return 91;
    pid_t expected=(pid_t)strtol(argv[2],NULL,10);
    if(!strcmp(argv[1],"own")) {
        if(getpgrp()!=getpid() || getpgrp()==expected)return 92;
    } else if(!strcmp(argv[1],"inherit")) {
        if(getpgrp()!=expected || getpgrp()==getpid())return 93;
    } else return 94;
    return 0;
}
