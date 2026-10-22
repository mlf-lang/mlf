/* Lifecycle/protocol integration checks. The scheduler is always executed as
 * a separate process. Gates establish overlap and dependency ordering without
 * assuming that a compiler completes within some arbitrary sleep interval. */
#include "build_runner_test_support.h"
static const char *runner,*fixture;
static char scratch[4096],plan_path[4096],result_path[4096];
static unsigned checks;
static void check(int condition,const char *message) {
    if(!condition) { fprintf(stderr,"build runner test failed: %s\n",message); exit(1); }
}
static void path(char *out,size_t size,const char *name) { int n=snprintf(out,size,"%s/%s",scratch,name); check(n>=0 && (size_t)n<size,"test path length"); }
static void field(FILE *f,const char *s) { check(fwrite(s,1,strlen(s)+1,f)==strlen(s)+1,"write plan"); }
static void integer(FILE *f,unsigned n) { char text[32]; snprintf(text,sizeof(text),"%u",n); field(f,text); }
static FILE *begin(const char *name,unsigned jobs,unsigned count) {
    char suffix[160]; snprintf(suffix,sizeof(suffix),"%s.plan",name); path(plan_path,sizeof(plan_path),suffix);
    snprintf(suffix,sizeof(suffix),"%s.result",name); path(result_path,sizeof(result_path),suffix);
    FILE *f=test_open(plan_path,"wb"); check(f!=NULL,"open plan");
    field(f,"MLF_BUILD_PLAN"); field(f,"1"); field(f,name); integer(f,jobs); integer(f,count); return f;
}
static void task(FILE *f,const char *id,unsigned timeout,char **deps,const char *cwd,const char *out,const char *err,char **argv) {
    field(f,id); integer(f,timeout); unsigned n=0; if(deps) while(deps[n]) ++n; integer(f,n); for(unsigned i=0;i<n;++i) field(f,deps[i]);
    field(f,cwd?cwd:""); field(f,""); field(f,out?out:""); field(f,err?err:""); n=0; while(argv[n]) ++n; integer(f,n); for(unsigned i=0;i<n;++i) field(f,argv[i]);
}
static test_process start(FILE *f) { check(!fclose(f),"close plan"); char *argv[]={(char *)runner,plan_path,result_path,NULL}; return test_spawn(argv); }
static char *finish(test_process p,int code) {
    check(test_wait(p,25)==code,"runner exit status"); char *text=test_read(result_path); check(text!=NULL,"complete result exists");
    check(strstr(text,"\"protocol_version\":1")!=NULL && strstr(text,"\"complete\":true")!=NULL,"complete protocol result");
    check(strstr(text,"\"plan_digest\":\"")!=NULL,"plan digest present"); return text;
}
static void state(const char *text,const char *id,const char *expected) {
    char needle[300]; snprintf(needle,sizeof(needle),"{\"id\":\"%s\",\"state\":\"%s\"",id,expected); check(strstr(text,needle)!=NULL,needle);
}
static long read_pid(const char *file) { check(test_await(file,10),"process marker created"); char *text=test_read(file); check(text!=NULL,"read process marker"); long pid=strtol(text,NULL,10); free(text); check(pid>0,"valid process pid"); return pid; }
static void stopped(long pid) { double start=test_now(); while(test_alive(pid) && test_now()-start<10) test_pause(); check(!test_alive(pid),"descendant stopped"); }
static void tree_pids(const char *file,long pids[3]) {
    char nested[4200]; pids[0]=read_pid(file); snprintf(nested,sizeof(nested),"%s.child",file); pids[1]=read_pid(nested); snprintf(nested,sizeof(nested),"%s.grandchild",file); pids[2]=read_pid(nested);
}
static void tree_stopped(long pids[3]) { for(int i=0;i<3;++i) stopped(pids[i]); }
static void diamond(void) {
    char root[4096],left[4096],right[4096]; path(root,sizeof(root),"diamond-root"); path(left,sizeof(left),"diamond-left"); path(right,sizeof(right),"diamond-right");
    FILE *f=begin("diamond",2,4); char *root_args[]={(char *)fixture,"signal",root,NULL},*left_args[]={(char *)fixture,"meet",left,right,NULL},*right_args[]={(char *)fixture,"meet",right,left,NULL},*last_args[]={(char *)fixture,"require",right,NULL};
    char *first[]={"root",NULL},*both[]={"left","right",NULL};
    /* Forward dependency references also exercise whole-graph validation. */
    task(f,"last",5,both,NULL,NULL,NULL,last_args); task(f,"root",5,NULL,NULL,NULL,NULL,root_args); task(f,"left",5,first,NULL,NULL,NULL,left_args); task(f,"right",5,first,NULL,NULL,NULL,right_args);
    char *text=finish(start(f),0); state(text,"last","succeeded"); state(text,"root","succeeded"); state(text,"left","succeeded"); state(text,"right","succeeded"); check(strstr(text,"\"maximum_parallel_jobs\":2")!=NULL,"diamond overlaps within bound"); free(text); ++checks;
}
static void large_serial(void) {
    FILE *f=begin("eighty-tasks",1,80); char *args[]={(char *)fixture,"exit","0",NULL};
    for(unsigned i=0;i<80;++i) { char id[40]; snprintf(id,sizeof(id),"task-%u",i); task(f,id,5,NULL,NULL,NULL,NULL,args); }
    char *text=finish(start(f),0); unsigned count=0; for(char *p=text;(p=strstr(p,"\"state\":\"succeeded\""));++p) ++count;
    check(count==80,"all eighty results present"); check(strstr(text,"\"maximum_parallel_jobs\":1")!=NULL,"one-job limit"); free(text); ++checks;
}
static void no_barrier(void) {
    char arrived[4096],release[4096],quick[4096]; path(arrived,sizeof(arrived),"barrier-arrived"); path(release,sizeof(release),"barrier-release"); path(quick,sizeof(quick),"barrier-quick");
    FILE *f=begin("no-level-barrier",2,3); char *long_args[]={(char *)fixture,"gate",arrived,release,NULL},*short_args[]={(char *)fixture,"signal",quick,NULL},*release_args[]={(char *)fixture,"signal",release,NULL}; char *deps[]={"quick",NULL};
    task(f,"long",5,NULL,NULL,NULL,NULL,long_args); task(f,"quick",5,NULL,NULL,NULL,NULL,short_args); task(f,"release",5,deps,NULL,NULL,NULL,release_args);
    char *text=finish(start(f),0); state(text,"long","succeeded"); state(text,"release","succeeded"); check(strstr(text,"\"maximum_parallel_jobs\":2")!=NULL,"two-job limit"); free(text); ++checks;
}
static void failure(void) {
    char marker[4096]; path(marker,sizeof(marker),"must-not-run"); FILE *f=begin("fail-fast",1,4);
    char *bad[]={(char *)fixture,"exit","23",NULL},*other[]={(char *)fixture,"signal",marker,NULL},*deps[]={"bad",NULL},*transitive[]={"dependent",NULL};
    task(f,"bad",5,NULL,NULL,NULL,NULL,bad); task(f,"dependent",5,deps,NULL,NULL,NULL,other); task(f,"transitive",5,transitive,NULL,NULL,NULL,other); task(f,"independent",5,NULL,NULL,NULL,NULL,other);
    char *text=finish(start(f),23); state(text,"bad","failed"); state(text,"dependent","blocked"); state(text,"transitive","blocked"); state(text,"independent","cancelled"); check(!test_exists(marker),"no launch after failure"); free(text); ++checks;
}
static void active_failure(void) {
    char pidfile[4096],ready[4200]; path(pidfile,sizeof(pidfile),"active-failure-tree"); snprintf(ready,sizeof(ready),"%s.grandchild",pidfile);
    FILE *f=begin("active-failure",2,2); char *tree[]={(char *)fixture,"tree",pidfile,NULL},*bad[]={(char *)fixture,"waitfail",ready,"23",NULL};
    task(f,"tree",10,NULL,NULL,NULL,NULL,tree); task(f,"bad",10,NULL,NULL,NULL,NULL,bad);
    test_process p=start(f); long pids[3]; tree_pids(pidfile,pids); char *text=finish(p,23); state(text,"tree","cancelled"); state(text,"bad","failed"); tree_stopped(pids); free(text); ++checks;
}
static void successful_cleanup(void) {
    char pidfile[4096]; path(pidfile,sizeof(pidfile),"successful-tree"); FILE *f=begin("successful-cleanup",1,1);
    char *args[]={(char *)fixture,"tree-exit",pidfile,NULL}; task(f,"tree",10,NULL,NULL,NULL,NULL,args);
    test_process p=start(f); long pids[3]; tree_pids(pidfile,pids); char *text=finish(p,0); state(text,"tree","succeeded"); tree_stopped(pids); free(text); ++checks;
}
static void timeout(void) {
    char pidfile[4096]; path(pidfile,sizeof(pidfile),"timeout-tree"); FILE *f=begin("deadline",1,2);
    char *args[]={(char *)fixture,"tree",pidfile,NULL},*next[]={(char *)fixture,"exit","0",NULL},*deps[]={"tree",NULL}; task(f,"tree",1,NULL,NULL,NULL,NULL,args); task(f,"next",1,deps,NULL,NULL,NULL,next);
    test_process p=start(f); long pids[3]; tree_pids(pidfile,pids); char *text=finish(p,124); state(text,"tree","failed"); state(text,"next","blocked"); tree_stopped(pids); free(text); ++checks;
}
static void crash(int coordinator) {
    const char *name=coordinator==1 ? "coordinator-death" : coordinator==2 ? "windows-cancel" : "runner-death"; coordinator=coordinator==1; char pidfile[4096],runnerpid[4096]; path(pidfile,sizeof(pidfile),name); path(runnerpid,sizeof(runnerpid),"owner-runner-pid");
    FILE *f=begin(name,1,1); char *args[]={(char *)fixture,"tree",pidfile,NULL}; task(f,"tree",20,NULL,NULL,NULL,NULL,args);
    test_process process;
    long runner_id=0;
    if(coordinator) { check(!fclose(f),"close owner plan"); char *owner[]={(char *)fixture,"owner",(char *)runner,plan_path,result_path,runnerpid,NULL}; process=test_spawn(owner); runner_id=read_pid(runnerpid); }
    else process=start(f);
    long pids[3]; tree_pids(pidfile,pids); test_kill(process); check(test_wait(process,10)!=0,"crashed process exits nonzero"); tree_stopped(pids); if(coordinator) stopped(runner_id); ++checks;
}
static void cancellation(void) {
#ifndef _WIN32
    char pidfile[4096]; path(pidfile,sizeof(pidfile),"cancel-tree"); FILE *f=begin("cancel",1,1); char *args[]={(char *)fixture,"tree",pidfile,NULL}; task(f,"tree",20,NULL,NULL,NULL,NULL,args);
    test_process p=start(f); long pids[3]; tree_pids(pidfile,pids); kill(p.id,SIGTERM); char *text=finish(p,128+SIGTERM); state(text,"tree","cancelled"); tree_stopped(pids); free(text);
#else
    /* Abrupt Windows cancellation is job-handle closure, checked by crash. */
    crash(2); --checks;
#endif
    ++checks;
}
static void unicode(void) {
    char dir[4096],log[4096]; path(dir,sizeof(dir),"space \xe4\xb8\xad\xe6\x96\x87"); test_mkdir(dir);
    int n=snprintf(log,sizeof(log),"%s/merged \xe6\x97\xa5\xe5\xbf\x97.txt",dir); check(n>=0 && (size_t)n<sizeof(log),"unicode log path");
    FILE *f=begin("unicode-argv",1,1); char *args[]={(char *)fixture,"echo","hello space","quote\"slash\\","\xe4\xb8\xad\xe6\x96\x87","",NULL};
    task(f,"unicode",5,NULL,dir,"merged \xe6\x97\xa5\xe5\xbf\x97.txt","merged \xe6\x97\xa5\xe5\xbf\x97.txt",args);
    char *text=finish(start(f),0); state(text,"unicode","succeeded"); free(text); text=test_read(log); check(text!=NULL,"unicode relative redirection"); check(strstr(text,"hello space\nquote\"slash\\\n\xe4\xb8\xad\xe6\x96\x87\n\n")!=NULL,"structured Unicode argv"); check(strstr(text,"stderr\n")!=NULL,"merged stdout stderr"); free(text); ++checks;
}
static void redirected_input(void) {
    char input[4096],output[4096]; path(input,sizeof(input),"stdin.txt"); path(output,sizeof(output),"copied.txt");
    FILE *in=test_open(input,"wb"); check(in!=NULL,"write input"); fputs("structured stdin\n",in); fclose(in);
    FILE *f=begin("stdin",1,1); field(f,"copy"); integer(f,5); integer(f,0); field(f,scratch); field(f,"stdin.txt"); field(f,"copied.txt"); field(f,""); integer(f,2); field(f,fixture); field(f,"copy");
    char *text=finish(start(f),0); free(text); text=test_read(output); check(text && !strcmp(text,"structured stdin\n"),"relative stdin redirection"); free(text); ++checks;
}
static void nonce(void) {
    char output[4096]; path(output,sizeof(output),"nonce.txt"); char *previous=NULL;
    for(unsigned i=0;i<2;++i) {
        FILE *f=begin(i ? "nonce-two" : "nonce-one",1,1); char *args[]={(char *)runner,"--new-invocation-id",NULL}; task(f,"nonce",5,NULL,NULL,output,NULL,args);
        char *text=finish(start(f),0); free(text); text=test_read(output); check(text && strlen(text)==65 && text[64]=='\n',"random invocation id length");
        for(unsigned j=0;j<64;++j) check((text[j]>='0' && text[j]<='9') || (text[j]>='a' && text[j]<='f'),"random invocation id encoding");
        if(previous) { check(strcmp(previous,text)!=0,"fresh invocation id"); free(previous); } previous=text;
    }
    free(previous); ++checks;
}
static void missing_tool(void) {
    FILE *f=begin("missing-tool",1,1); char *args[]={"mlf-intentionally-nonexistent-executable-7b79",NULL}; task(f,"missing",5,NULL,NULL,NULL,NULL,args); char *text=finish(start(f),127); state(text,"missing","failed"); free(text); ++checks;
}
static void invalid(unsigned kind) {
    char name[60],marker[4096]; snprintf(name,sizeof(name),"invalid-%u",kind); path(marker,sizeof(marker),name); FILE *f=begin(name,1,kind==4 ? 1 : 2);
    char *args[]={(char *)fixture,"signal",marker,NULL},*unknown[]={"unknown",NULL},*cycle1[]={"b",NULL},*cycle2[]={"a",NULL},*duplicate[]={"a","a",NULL};
    if(kind==0) { task(f,"a",5,cycle1,NULL,NULL,NULL,args); task(f,"b",5,cycle2,NULL,NULL,NULL,args); }
    if(kind==1) { task(f,"a",5,NULL,NULL,NULL,NULL,args); task(f,"a",5,NULL,NULL,NULL,NULL,args); }
    if(kind==2) { task(f,"a",5,NULL,NULL,NULL,NULL,args); task(f,"b",5,unknown,NULL,NULL,NULL,args); }
    if(kind==3) { task(f,"a",5,NULL,NULL,NULL,NULL,args); task(f,"b",5,duplicate,NULL,NULL,NULL,args); }
    if(kind==4) { task(f,"a",5,NULL,NULL,NULL,NULL,args); fputc('x',f); }
    if(kind==5) { task(f,"a",5,NULL,NULL,NULL,NULL,args); /* truncated second record */ }
    test_process p=start(f); check(test_wait(p,10)==64,"malformed plan rejected"); check(!test_exists(marker),"malformed plan never launches"); check(!test_exists(result_path),"malformed plan has no complete result"); ++checks;
}
static void binding(void) {
    FILE *f=begin("binding-one",1,0); char *one=finish(start(f),0);
    f=begin("binding-two",1,0); char *two=finish(start(f),0);
    char *a=strstr(one,"\"plan_digest\":\""),*b=strstr(two,"\"plan_digest\":\""); check(a&&b,"plan digests"); a+=15; b+=15; check(strncmp(a,b,64)!=0,"plan digest binds invocation bytes"); free(one); free(two); ++checks;
}
static int tests(int argc,char **argv) {
    if(argc!=4) return 64; runner=argv[1]; fixture=argv[2]; test_mkdir(argv[3]);
    int n=snprintf(scratch,sizeof(scratch),"%s/build-runner-%ld",argv[3],test_pid()); check(n>=0 && (size_t)n<sizeof(scratch),"scratch path"); test_mkdir(scratch);
    char *version[]={(char *)runner,"--protocol-version",NULL}; check(test_wait(test_spawn(version),10)==0,"protocol capability"); ++checks;
    diamond(); large_serial(); no_barrier(); failure(); active_failure(); successful_cleanup(); timeout(); crash(0); crash(1); cancellation(); unicode(); redirected_input(); nonce(); missing_tool(); for(unsigned i=0;i<6;++i) invalid(i); binding();
    printf("%u native build runner tests passed\n",checks); return 0;
}
TEST_MAIN(tests)
