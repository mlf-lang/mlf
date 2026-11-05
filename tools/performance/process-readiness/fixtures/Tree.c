#define _DEFAULT_SOURCE 1
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include "mlf_process_supervisor.h"
extern int mlf_ghc_host(int,const char*,size_t,const char*,size_t,int64_t,char**,size_t*,int64_t*);
static void check(int ok){if(!ok)exit(91);}
static void absent(const char *path){FILE*f=fopen(path,"r");check(f!=NULL);long pid=0;check(fscanf(f,"%ld",&pid)==1&&pid>0);fclose(f);errno=0;check(kill((pid_t)pid,0)==-1&&errno==ESRCH);}
int main(int argc,char**argv){
 check(argc==5);
 if(!strcmp(argv[1],"worker")){
   const char*scope=getenv("MLF_BUILD_SCOPE");check(scope&&strtol(scope,NULL,10)==getpgrp());
   if(!strcmp(argv[2],"unsupervised"))check(!unsetenv("MLF_BUILD_SCOPE"));
   const char*fields[]={"1","","","","/bin/sh","-c","echo $$ > \"$1\"; sleep 20 & echo $! > \"$2\"; wait","fixture",argv[3],argv[4]};
   char spec[8192];size_t n=0;for(size_t i=0;i<sizeof(fields)/sizeof(fields[0]);++i){size_t k=strlen(fields[i])+1;check(n+k<=sizeof(spec));memcpy(spec+n,fields[i],k);n+=k;}
   char*out=NULL;size_t len=0;int64_t result=0;int status=mlf_ghc_host(7,"",0,spec,n,0,&out,&len,&result);free(out);check(status==0&&result==124);return 124;
 }
 mlf_process_scope scope;mlf_process_options options={1,1,1};check(mlf_process_scope_create(&options,&scope)==MLF_PROCESS_OK);
 const char*child[]={argv[0],"worker",argv[2],argv[3],argv[4],NULL};mlf_process_spec spec={0};spec.executable=argv[0];spec.argv=child;spec.running_timeout_seconds=5;spec.total_timeout_seconds=7;
 mlf_process_handle handle;check(mlf_process_submit(scope,&spec,&handle)==MLF_PROCESS_OK);mlf_process_outcome outcome;
 check(mlf_process_await(scope,handle,10,&outcome)==MLF_PROCESS_OK);check(outcome.kind==MLF_PROCESS_EXITED&&outcome.exit_code==(!strcmp(argv[2],"supervised")?137:124)&&outcome.cleanup_error==0&&outcome.launch_error==0);
 check(mlf_process_scope_close(scope,MLF_PROCESS_CLOSE_JOIN)==MLF_PROCESS_OK);absent(argv[3]);absent(argv[4]);printf("PASS %s timeout descendant cleanup\n",argv[2]);return 0;
}
