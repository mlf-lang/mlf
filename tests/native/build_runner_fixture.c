#include "build_runner_test_support.h"
static int fixture(int argc,char **argv) {
    if(argc>=3 && !strcmp(argv[1],"exit")) return atoi(argv[2]);
    if(argc>=2 && !strcmp(argv[1],"echo")) { for(int i=2;i<argc;++i) printf("%s\n",argv[i]); fputs("stderr\n",stderr); return 0; }
    if(argc==4 && !strcmp(argv[1],"waitfail")) return test_await(argv[2],20) ? atoi(argv[3]) : 24;
    if(argc==3 && !strcmp(argv[1],"signal")) { test_touch(argv[2]); return 0; }
    if(argc==3 && !strcmp(argv[1],"require")) return test_exists(argv[2]) ? 0 : 23;
    if(argc==4 && !strcmp(argv[1],"gate")) { test_touch(argv[2]); return test_await(argv[3],20) ? 0 : 24; }
    if(argc==4 && !strcmp(argv[1],"meet")) { test_touch(argv[2]); return test_await(argv[3],20) ? 0 : 24; }
    if(argc==2 && !strcmp(argv[1],"copy")) { int c; while((c=getchar())!=EOF) if(putchar(c)==EOF) return 26; return ferror(stdin) ? 26 : 0; }
    if(argc==3 && !strcmp(argv[1],"group-leaf")) {
#ifndef _WIN32
        if(setpgid(0,0) && getpgrp()!=getpid()) return 27;
#endif
        test_write_pid(argv[2]); for(;;) test_pause();
    }
    if(argc==3 && !strcmp(argv[1],"leaf")) { test_write_pid(argv[2]); for(;;) test_pause(); }
    if(argc==3 && (!strcmp(argv[1],"tree") || !strcmp(argv[1],"tree-exit"))) {
        char child[4096], grandchild[4096];
        snprintf(child,sizeof(child),"%s.child",argv[2]); snprintf(grandchild,sizeof(grandchild),"%s.grandchild",argv[2]);
        char *one[]={argv[0],"group-leaf",child,NULL},*two[]={argv[0],"group-leaf",grandchild,NULL};
        (void)test_spawn(one); (void)test_spawn(two);
        if(!test_await(child,10) || !test_await(grandchild,10)) return 28;
        test_write_pid(argv[2]); if(!strcmp(argv[1],"tree-exit")) return 0; for(;;) test_pause();
    }
    /* The runner sees this process as its coordinator; killing it must stop
     * every task even when the runner itself receives no signal. */
    if(argc==6 && !strcmp(argv[1],"owner")) {
        char *child[]={argv[2],argv[3],argv[4],NULL}; test_process p=test_spawn(child);
        FILE *f=test_open(argv[5],"wb"); if(!f) return 25; fprintf(f,"%lu\n",(unsigned long)p.id); fclose(f);
        return test_wait(p,30);
    }
    return 64;
}
TEST_MAIN(fixture)
