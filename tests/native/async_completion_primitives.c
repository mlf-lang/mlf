/* Integration test: all effects run through the real primitive ABI and one IO
 * driver invocation. C callbacks stand in for generated typed source closures;
 * source inference/checking/parity is covered by fixtures/async-completion. */
#include "../../runtime/mlf_runtime.h"
#include "../../runtime/mlf_process_supervisor.h"
#include <gc/gc.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned stage, checks, callbacks;
static MlfValue *scope, *integers, *strings, *ticket, *allocation;
static double wait_started;
static MlfValue *next(void);
static MlfValue *n(const char *s) { return mlf_integer(s); }
static MlfValue *unit(void) { return mlf_prim1(0,mlf_constructor(0,0)); }
static void require(int ok,const char *message) {
    ++checks;
    if(!ok) { fprintf(stderr,"primitive integration stage %u: %s\n",stage,message); exit(1); }
}
static void expect_int(MlfValue *v,const char *s) {
    require(mlf_truth(mlf_eq_int(v,n(s))),"unexpected integer");
}
static MlfValue *poison(MlfEnv *env,MlfValue *v) {
    (void)env;(void)v;require(0,"lazy poison forced");return unit();
}
static MlfValue *record_int(MlfEnv *env,MlfValue *v) {
    GC_gcollect();
    require(mlf_truth(mlf_eq_int(v,mlf_env_get(env,0))),"large integer capture lost");
    ++callbacks;return unit();
}
static MlfValue *record_string(MlfEnv *env,MlfValue *v) {
    GC_gcollect();
    require(mlf_truth(mlf_prim2(12,v,mlf_env_get(env,0))),"string capture lost");
    ++callbacks;return unit();
}
static MlfValue *record_timer(MlfEnv *env,MlfValue *v) {
    (void)env;(void)v;++callbacks;return unit();
}
static MlfValue *reentrant_status(MlfEnv *env,MlfValue *v) {
    (void)env;expect_int(v,"8");return unit();
}
static MlfValue *reentrant(MlfEnv *env,MlfValue *v) {
    (void)env;(void)v;++callbacks;
    return mlf_prim2(1,mlf_prim2(94,scope,n("0")),mlf_closure(reentrant_status,mlf_env_new(0)));
}
static MlfValue *capture(MlfCode code,MlfValue *v) {
    MlfEnv *env=mlf_env_new(1);mlf_env_set(env,0,v);return mlf_closure(code,env);
}
static MlfValue *return_value(MlfEnv *env,MlfValue *v) { (void)env;return mlf_prim1(0,v); }
static MlfValue *after(MlfEnv *env,MlfValue *v) {
    (void)env;
    switch(stage) {
    case 0: scope=v;break;
    case 1: integers=v;break;
    case 2: strings=v;break;
    case 3: case 4: case 12: case 15: case 18: ticket=v;break;
    case 5: case 6: case 8: case 9: case 13: case 16: case 20: expect_int(v,"0");break;
    case 7: expect_int(v,"2");break;
    case 10: case 14: expect_int(v,"1");break;
    case 11: case 21: break;
    case 17: expect_int(v,"6");break;
    case 19: expect_int(v,"0");require(mlf_process_monotonic_seconds()-wait_started>=0.008,"timer fired too early");break;
    case 22: case 23: expect_int(v,"3");break;
    default: require(0,"unexpected continuation");
    }
    ++stage;GC_gcollect();return next();
}
static MlfValue *next(void) {
    MlfValue *op=NULL;
    switch(stage) {
    case 0: op=mlf_prim2(83,n("2"),n("3"));break;
    case 1:
        allocation=mlf_prim3(85,scope,mlf_closure(return_value,mlf_env_new(0)),mlf_thunk(poison,mlf_env_new(0)));
        op=allocation;break;
    case 2: op=allocation;break; /* Reusing the cold action allocates a fresh cell. */
    case 3: op=mlf_prim2(88,integers,capture(record_int,n("123456789012345678901234567890")));break;
    case 4: op=mlf_prim2(88,strings,capture(record_string,mlf_string("typed",5)));break;
    case 5: op=mlf_prim2(86,integers,n("123456789012345678901234567890"));break;
    case 6: op=mlf_prim2(86,strings,mlf_string("typed",5));break;
    case 7: op=mlf_prim2(86,integers,mlf_thunk(poison,mlf_env_new(0)));break;
    case 8: case 9: case 10: op=mlf_prim1(91,scope);break;
    case 11: op=mlf_prim3(87,integers,capture(record_int,n("123456789012345678901234567890")),mlf_thunk(poison,mlf_env_new(0)));break;
    case 12: op=mlf_prim3(93,scope,n("4294967295"),mlf_thunk(poison,mlf_env_new(0)));break;
    case 13: op=mlf_prim1(90,ticket);break;
    case 14: op=mlf_prim2(94,scope,n("-1"));break;
    case 15: op=mlf_prim2(92,scope,mlf_application(mlf_closure(reentrant,mlf_env_new(0)),mlf_constructor(0,0)));break;
    case 16: op=mlf_prim1(91,scope);break;
    case 17: op=mlf_prim1(90,ticket);break;
    case 18: wait_started=mlf_process_monotonic_seconds();
        op=mlf_prim3(93,scope,n("10"),mlf_application(mlf_closure(record_timer,mlf_env_new(0)),mlf_constructor(0,0)));break;
    case 19: op=mlf_prim2(94,scope,n("-1"));break;
    case 20: op=mlf_prim1(91,scope);break;
    case 21: op=mlf_prim1(84,scope);break;
    case 22: op=mlf_prim2(86,integers,n("0"));break;
    case 23: op=mlf_prim2(94,scope,n("-1"));break;
    default: require(callbacks==5,"wrong callback count");return unit();
    }
    return mlf_prim2(1,op,mlf_closure(after,mlf_env_new(0)));
}
int main(void) {
    int status=mlf_run(next(),1);
    printf("Native completion primitives: %u checks, %u callbacks passed.\n",checks,callbacks);
    return status;
}
