/* Independent native ABI, demand and lazy Unicode-validation controls. */
#include "mlf_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gc/gc.h>

enum { UTF8_LENGTH = 136 };
static unsigned forced;
static void need(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "runtime UTF-8 length: %s\n", message); exit(90); }
}
static int64_t number(MlfValue *value) {
    value=mlf_force(value);
    need(((uintptr_t)value & 1)!=0, "expected small integer");
    return (int64_t)((intptr_t)value >> 1);
}
static MlfValue *event(MlfEnv *env, MlfValue *ignored) {
    (void)ignored; ++forced; GC_gcollect(); return mlf_env_get(env,0);
}
static MlfValue *poison(MlfEnv *env, MlfValue *ignored) {
    (void)ignored; return mlf_prim1(55,mlf_env_get(env,0));
}
static MlfValue *thunk(MlfCode code, MlfValue *value) {
    MlfEnv *env=mlf_env_new(1); mlf_env_set(env,0,value); return mlf_thunk(code,env);
}
static void check(const unsigned char *bytes, size_t size, size_t scalars) {
    MlfValue *text=mlf_string((const char *)bytes,size);
    forced=0;
    MlfValue *input=thunk(event,text);
    need(number(mlf_string_utf8_length(input))==(int64_t)size,"direct byte count");
    need(forced==1,"text thunk must be forced once");
    GC_gcollect();
    need(number(mlf_prim1(UTF8_LENGTH,input))==(int64_t)size,"saturated opcode");
    need(number(mlf_force(mlf_application(mlf_primitive(UTF8_LENGTH),input)))==(int64_t)size,"dynamic opcode/arity");
    need(number(mlf_string_length(input))==(int64_t)scalars,"scalar count preserved");
    need(forced==1,"cached thunk forced twice");
    GC_reachable_here(text);
}
static struct StaticString {
    uint32_t tag,padding; size_t length; const char *bytes; size_t *indices;
} huge={8,0,(size_t)INT64_MAX+1,"",NULL};
int main(int argc,char **argv) {
    need(argc==2,"expected mode"); const char *mode=argv[1];
    if (!strcmp(mode,"no-interior")) GC_set_all_interior_pointers(0);
    GC_set_max_heap_size(8*1024*1024);
    if (!strcmp(mode,"success") || !strcmp(mode,"no-interior")) {
        static const unsigned char mixed[]={65,0,0xce,0xbb,0xe4,0xb8,0xad,0xf0,0x9f,0x98,0x80};
        check((const unsigned char *)"",0,0); check((const unsigned char *)"A\0B",3,3); check(mixed,sizeof mixed,5);
        for (size_t n=1;n<=257;n+=16) {
            unsigned char *bytes=malloc(n*sizeof mixed); need(bytes!=NULL,"fixture allocation");
            for (size_t i=0;i<n;++i) memcpy(bytes+i*sizeof mixed,mixed,sizeof mixed);
            check(bytes,n*sizeof mixed,n*5); free(bytes);
        }
        puts("runtime UTF-8 length: values, validation cache, ABI, demand and GC passed"); return 0;
    }
    if (!strcmp(mode,"bottom")) (void)mlf_string_utf8_length(thunk(poison,mlf_string("text-first",10)));
    else if (!strcmp(mode,"wrong-type")) (void)mlf_string_utf8_length(mlf_integer("1"));
    else if (!strcmp(mode,"overflow")) (void)mlf_string_utf8_length((MlfValue *)&huge);
    else if (!strcmp(mode,"invalid-utf8")) {
        static const unsigned char invalid[]={0xc0,0xaf};
        (void)mlf_string_utf8_length(mlf_string((const char *)invalid,sizeof invalid));
    } else need(0,"unknown mode");
    fputs("runtime UTF-8 length: expected error missing\n",stderr); return 92;
}
