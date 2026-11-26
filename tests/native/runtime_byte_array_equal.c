/* Independent saturated/dynamic opcode and IO/GC controls for primitive137. */
#include "mlf_runtime.h"
#include <gc/gc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { IO_RETURN=0, IO_BIND=1, NEW_BYTE_ARRAY=35, PANIC=55, BYTE_ARRAY_EQUAL=137 };
static unsigned forced, current_case;
static void need(int okay,const char *message) {
    if (!okay) { fprintf(stderr,"runtime byte-array equality: %s\n",message); exit(90); }
}
static MlfValue *integer(size_t n) {
    char text[32]; snprintf(text,sizeof text,"%zu",n); return mlf_integer(text);
}
static MlfValue *unit(void) { return mlf_constructor(1,0); }
static MlfValue *event(MlfEnv *env,MlfValue *ignored) {
    (void)ignored;
    forced=forced*10+(unsigned)mlf_truth(mlf_env_get(env,1))+1;
    GC_gcollect();
    return mlf_env_get(env,0);
}
static MlfValue *poison(MlfEnv *env,MlfValue *ignored) {
    (void)ignored; return mlf_prim1(PANIC,mlf_env_get(env,0));
}
static MlfValue *bad(const char *message) {
    MlfEnv *env=mlf_env_new(1);
    mlf_env_set(env,0,mlf_string(message,strlen(message)));
    return mlf_thunk(poison,env);
}
static MlfValue *observed(MlfValue *array,int right) {
    MlfEnv *env=mlf_env_new(2); mlf_env_set(env,0,array); mlf_env_set(env,1,mlf_boolean(right));
    return mlf_thunk(event,env);
}
static MlfValue *next(void);
static MlfValue *checked(MlfEnv *env,MlfValue *result) {
    need(mlf_truth(result)==mlf_truth(mlf_env_get(env,0)),"exact equality result");
    need(forced==12,"both operands must be forced exactly once in left-to-right order");
    ++current_case;
    return next();
}
static MlfValue *next(void) {
    static const size_t sizes[]={0,1,7,256,4097,65537};
    if (current_case>=sizeof sizes/sizeof sizes[0]*6) return mlf_prim1(IO_RETURN,unit());
    size_t size=sizes[current_case/6];
    unsigned variant=(current_case/2)%3, dynamic=current_case%2;
    MlfValue *left=mlf_new_array(NEW_BYTE_ARRAY,integer(size),integer(31));
    MlfValue *right=mlf_new_array(NEW_BYTE_ARRAY,integer(size+(variant==1)),integer(variant==2?32:31));
    left=observed(left,0); right=observed(right,1); forced=0;
    MlfValue *action=dynamic
        ?mlf_application(mlf_application(mlf_primitive(BYTE_ARRAY_EQUAL),left),right)
        :mlf_prim2(BYTE_ARRAY_EQUAL,left,right);
    (void)mlf_force(action);
    need(forced==0,"constructing saturated/dynamic IO must defer both operands");
    GC_gcollect();
    MlfEnv *env=mlf_env_new(1);
    mlf_env_set(env,0,mlf_boolean(variant==0 || (size==0 && variant==2)));
    return mlf_prim2(IO_BIND,action,mlf_closure(checked,env));
}
int main(int argc,char **argv) {
    need(argc==2,"expected mode");
    const char *mode=argv[1];
    if (!strcmp(mode,"no-interior")) GC_set_all_interior_pointers(0);
    GC_set_max_heap_size(8*1024*1024);
    mlf_require_byte_array_equal_abi();
    if (!strcmp(mode,"success") || !strcmp(mode,"no-interior")) {
        int status=mlf_run(next(),1); need(status==0,"IO program failed");
        puts("runtime byte-array equality: 36 dynamic/saturated ABI, IO demand, exact-byte and GC cases passed");
        return 0;
    }
    MlfValue *left=mlf_new_array(NEW_BYTE_ARRAY,integer(0),integer(0));
    MlfValue *right=left;
    if (!strcmp(mode,"left")) { left=bad("left-demand"); right=bad("right-demand"); }
    else if (!strcmp(mode,"right")) right=bad("right-demand");
    else if (!strcmp(mode,"wrong-left")) { left=integer(0); right=bad("right-demand"); }
    else if (!strcmp(mode,"wrong-right")) right=integer(0);
    else need(0,"unknown mode");
    return mlf_run(mlf_prim2(BYTE_ARRAY_EQUAL,left,right),1);
}
