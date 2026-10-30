/* Exercise the same wait implementation through the compact native runtime. */
#include "mlf_runtime.c"
int main(int argc,char **argv) {
    if(argc!=3)return 90;
    const char *command=argv[1], *wanted=argv[2];
    char spec[1024];
    const char *fields[]={"1","","","","/bin/sh","-c",command};
    size_t n=0;
    for(size_t i=0;i<sizeof(fields)/sizeof(fields[0]);++i) {
        size_t k=strlen(fields[i])+1;if(n+k>sizeof(spec))return 91;
        memcpy(spec+n,fields[i],k);n+=k;
    }
    MlfValue *result=os_runProcess(mlf_string("",0),mlf_string(spec,n));
    uint64_t code=bounded_integer(result,255,"unexpected native process result");
    mlf_process_shutdown();
    if(code!=(uint64_t)strtoul(wanted,NULL,10))return 92;
    printf("PASS native process status %" PRIu64 "\n",code);return 0;
}
