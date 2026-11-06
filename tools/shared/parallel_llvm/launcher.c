/* Native fast path: unrelated C/link/version invocations exec Clang directly. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "driver-config.h"

int main(int argc,char **argv) {
  int source=0,output=0,compile=0,optimize=0,selected=1;
  for(int i=1;i<argc;++i) {
    const char *value=argv[i];size_t length=strlen(value);
    if(!strcmp(value,"-o") && i+1<argc){if(output++)selected=0;++i;}
    else if(!strcmp(value,"-c"))compile=1;
    else if(!strcmp(value,"-O2"))optimize=1;
    else if(!strcmp(value,"-Wno-override-module")){}
    else if(value[0]!='-' && length>=3 && !strcmp(value+length-3,".ll"))++source;
    else selected=0;
  }
  if(!(selected && compile && optimize && source==1 && output==1)) {
    argv[0]=(char*)MLF_CLANG;execv(MLF_CLANG,argv);perror("exec ordinary Clang");return 127;
  }
  char **command=calloc((size_t)argc+3,sizeof(char*));
  if(!command){perror("allocate driver arguments");return 127;}
  command[0]=(char*)MLF_HELPER;command[1]="--driver";command[2]=(char*)MLF_CONFIG;
  for(int i=1;i<argc;++i)command[i+2]=argv[i];
  execv(MLF_HELPER,command);perror("exec parallel LLVM driver");return 127;
}
