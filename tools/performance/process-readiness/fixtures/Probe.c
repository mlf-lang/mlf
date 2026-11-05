#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
extern int mlf_ghc_host(int,const char*,size_t,const char*,size_t,int64_t,char**,size_t*,int64_t*);
extern void mlf_ghc_shutdown(void);
static char *read_bytes(const char *name,size_t *size) {
  FILE *f=fopen(name,"rb");if(!f)exit(90);
  if(fseek(f,0,SEEK_END))exit(91);long n=ftell(f);if(n<0)exit(92);rewind(f);
  char *bytes=calloc((size_t)n+1,1);if(!bytes)exit(93);
  if(fread(bytes,1,(size_t)n,f)!=(size_t)n || fclose(f))exit(94);*size=(size_t)n;return bytes;
}
int main(int argc,char **argv) {
  if(argc!=4)return 95;
  size_t na,nb,len=0;char *a=read_bytes(argv[2],&na),*b=read_bytes(argv[3],&nb),*out=NULL;int64_t number=0;
  int status=mlf_ghc_host(atoi(argv[1]),a,na,b,nb,0,&out,&len,&number);
  printf("%d %" PRId64 " %zu ",status,number,len);
  for(size_t i=0;i<len;++i)printf("%02x",(unsigned char)out[i]);printf("\n");
  free(a);free(b);free(out);mlf_ghc_shutdown();return 0;
}
