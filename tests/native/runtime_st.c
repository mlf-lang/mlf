/* Native ST ABI semantics, independent of compiler lowering. */
#include "mlf_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef MLF_USE_BDWGC
#include <gc/gc.h>
#endif

enum { IO_RETURN = 0, IO_BIND = 1, ST_RETURN = 66, ST_BIND = 67, RUN_ST = 68,
       NEW_ST_ARRAY = 69, READ_ST_ARRAY = 70, WRITE_ST_ARRAY = 71, LENGTH_ST_ARRAY = 72 };
static unsigned calls;
static void require(int test, const char *message) {
    if (!test) { fprintf(stderr,"runtime ST: %s\n",message); exit(90); }
}
static MlfValue *integer(const char *s) { return mlf_integer(s); }
static MlfValue *unit(void) { return mlf_constructor(0,0); }
static MlfValue *ret(MlfValue *a) { return mlf_prim1(ST_RETURN,a); }
static MlfValue *run(MlfValue *a) { return mlf_prim1(RUN_ST,a); }
static MlfValue *read_at(MlfValue *a, const char *index) { return mlf_prim2(READ_ST_ARRAY,a,integer(index)); }
static MlfValue *write_at(MlfValue *a, const char *index, MlfValue *x) {
    return mlf_prim3(WRITE_ST_ARRAY,a,integer(index),x);
}
static MlfEnv *env1(MlfValue *a) {
    MlfEnv *e=mlf_env_new(1); mlf_env_set(e,0,a); return e;
}
static MlfEnv *env2(MlfValue *a, MlfValue *b) {
    MlfEnv *e=mlf_env_new(2); mlf_env_set(e,0,a); mlf_env_set(e,1,b); return e;
}
static MlfValue *closure(MlfCode code, MlfEnv *env) { return mlf_closure(code,env); }
static MlfValue *bind(MlfValue *a, MlfValue *f) { return mlf_prim2(ST_BIND,a,f); }
static void number(MlfValue *actual, const char *expected) {
    require(mlf_truth(mlf_eq_int(actual,integer(expected))),"integer result changed");
}
static MlfValue *poison(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    fputs("runtime ST: forced a lazy element\n",stderr); exit(91);
}
static MlfValue *bad(void) { return mlf_thunk(poison,mlf_env_new(0)); }
static MlfValue *counted(MlfEnv *env, MlfValue *argument) {
    (void)argument; ++calls;
#ifdef MLF_USE_BDWGC
    GC_gcollect();
#endif
    return mlf_env_get(env,0);
}
static MlfValue *return_argument(MlfEnv *env, MlfValue *argument) {
    (void)env; ++calls;
#ifdef MLF_USE_BDWGC
    if (calls % 257 == 0) GC_gcollect();
#endif
    return ret(argument);
}
static MlfValue *ignore_argument(MlfEnv *env, MlfValue *argument) {
    (void)argument; return ret(mlf_env_get(env,0));
}
static MlfValue *return_snapshot(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    require(calls==0,"read forced its result before it was used");
    number(run(read_at(mlf_env_get(env,0),"0")),"43");
    return ret(mlf_env_get(env,1));
}
static MlfValue *after_read(MlfEnv *env, MlfValue *old) {
    require(calls==0,"read forced its lazy element");
    MlfValue *array=mlf_env_get(env,0);
    return bind(write_at(array,"0",integer("43")),closure(return_snapshot,env2(array,old)));
}
static MlfValue *nested(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    MlfValue *outer=mlf_env_get(env,0);
    MlfValue *inner=run(mlf_prim2(NEW_ST_ARRAY,integer("1"),integer("17")));
    run(write_at(inner,"0",integer("19")));
#ifdef MLF_USE_BDWGC
    GC_gcollect();
#endif
    number(run(read_at(outer,"0")),"7");
    return ret(mlf_add_int(run(read_at(inner,"0")),run(read_at(outer,"0"))));
}
static MlfValue *run_expression(MlfEnv *env, MlfValue *argument) {
    (void)argument; return run(mlf_env_get(env,0));
}
static void semantic_cases(void) {
    MlfValue *lazy=bad();
    /* Descriptions themselves are values even when every operand is bottom. */
    (void)ret(lazy);
    (void)bind(lazy,lazy);
    (void)mlf_prim2(NEW_ST_ARRAY,lazy,lazy);
    (void)mlf_prim2(READ_ST_ARRAY,lazy,lazy);
    (void)mlf_prim3(WRITE_ST_ARRAY,lazy,lazy,lazy);
    (void)mlf_prim1(LENGTH_ST_ARRAY,lazy);
    MlfValue *a=run(mlf_prim2(NEW_ST_ARRAY,integer("2"),lazy));
    number(run(mlf_prim1(LENGTH_ST_ARRAY,a)),"2");
    run(write_at(a,"0",integer("42")));
    number(run(read_at(a,"0")),"42");
    run(write_at(a,"1",lazy));
    number(run(mlf_prim1(LENGTH_ST_ARRAY,a)),"2");
    MlfValue *zero=run(mlf_prim2(NEW_ST_ARRAY,integer("0"),lazy));
    number(run(mlf_prim1(LENGTH_ST_ARRAY,zero)),"0");
    number(run(bind(ret(lazy),closure(ignore_argument,env1(integer("11"))))),"11");

    MlfValue *big=integer("1234567890123456789012345678901234567890");
    MlfValue *fresh=mlf_prim2(NEW_ST_ARRAY,integer("1"),big);
    MlfValue *first=run(fresh), *second=run(fresh);
    require(first!=second,"repeated allocation action reused its array");
    run(write_at(first,"0",integer("8")));
    number(run(read_at(second,"0")),"1234567890123456789012345678901234567890");
    MlfValue *read=read_at(first,"0");
    number(run(read),"8"); run(write_at(first,"0",integer("9"))); number(run(read),"9");

    calls=0;
    MlfValue *old=mlf_thunk(counted,env1(integer("42")));
    run(write_at(first,"0",old));
    number(run(bind(read_at(first,"0"),closure(after_read,env1(first)))),"42");
    require(calls==1,"snapshot was not shared");
    number(run(read_at(first,"0")),"43");

    MlfValue *ring=mlf_hole();
    MlfValue *node=mlf_constructor2(17,integer("6"),ring); mlf_fill(ring,node);
    run(write_at(second,"0",node));
    MlfValue *read_node=run(read_at(second,"0"));
    require(mlf_tag(read_node)==17 && mlf_tag(mlf_field(read_node,1))==17,"recursive cell changed");
    number(mlf_field(read_node,0),"6");
    MlfValue *function=closure(return_argument,mlf_env_new(0));
    run(write_at(second,"0",function));
    require(run(read_at(second,"0"))==function,"polymorphic closure cell changed");
    MlfValue *text=mlf_string("boxed",5); run(write_at(second,"0",text));
    require(run(read_at(second,"0"))==text,"polymorphic String cell changed");
    MlfValue *floating=mlf_double(1.25); run(write_at(second,"0",floating));
    require(run(read_at(second,"0"))==floating,"polymorphic Double cell changed");

    MlfValue *outer=run(mlf_prim2(NEW_ST_ARRAY,integer("1"),integer("7")));
    number(run(bind(ret(unit()),closure(nested,env1(outer)))),"26");
    number(run(read_at(outer,"0")),"7");

    calls=0;
    MlfValue *return42=bind(ret(integer("42")),closure(return_argument,mlf_env_new(0)));
    MlfValue *expression=mlf_thunk(run_expression,env1(return42));
    number(mlf_force(expression),"42"); number(mlf_force(expression),"42");
    require(calls==1,"a shared runST expression was executed twice");
    number(run(return42),"42"); number(run(return42),"42");
    require(calls==3,"repeated ST action was memoized");

    calls=0;
    MlfValue *false_thunk=mlf_thunk(counted,env1(mlf_boolean(0)));
    MlfValue *hole=mlf_hole(); mlf_fill(hole,false_thunk);
    require((uintptr_t)run(ret(hole))==2,"runST returned a non-WHNF Bool pointer");
    require(calls==1,"runST did not evaluate its final result once");
    MlfValue *wrapped=run(ret(mlf_constructor2(18,integer("1"),bad())));
    require(mlf_tag(wrapped)==18,"runST forced lazy result fields");
    MlfValue *io=mlf_prim1(IO_RETURN,bad());
    require(run(ret(io))==io,"runST changed a returned IO description");

    /* Exercise partial primitive application independently of the saturated ABI. */
    MlfValue *partial=mlf_application(mlf_primitive(ST_RETURN),integer("23"));
    number(mlf_application(mlf_primitive(RUN_ST),partial),"23");
    MlfValue *newpartial=mlf_application(mlf_application(mlf_primitive(NEW_ST_ARRAY),integer("3")),integer("9"));
    MlfValue *array=run(newpartial);
    MlfValue *writepartial=mlf_application(mlf_application(mlf_application(mlf_primitive(WRITE_ST_ARRAY),array),integer("2")),integer("29"));
    run(writepartial);
    number(run(mlf_application(mlf_application(mlf_primitive(READ_ST_ARRAY),array),integer("2"))),"29");
    number(run(mlf_application(mlf_primitive(LENGTH_ST_ARRAY),array)),"3");
    MlfValue *bindpartial=mlf_application(mlf_application(mlf_primitive(ST_BIND),ret(integer("31"))),function);
    number(run(bindpartial),"31");

    MlfValue *chain=ret(integer("37"));
    for (unsigned i=0;i<20000;++i) chain=bind(chain,function);
    calls=0; number(run(chain),"37"); require(calls==20000,"ST continuation stack skipped a bind");
}

/* All retained state is reachable from the pending IO root. Tiny collector
 * thresholds exercise ST actions, arrays and lazy recursive elements together. */
static MlfValue *gc_finish(MlfEnv *env, MlfValue *state_action) {
    (void)env;
    MlfValue *node=run(state_action);
    require(mlf_tag(node)==77 && mlf_tag(mlf_field(node,1))==77,"collector lost recursive ST cell");
    number(mlf_field(node,0),"1234567890123456789012345678901234567890");
    return mlf_prim1(IO_RETURN,unit());
}
static int gc_case(void) {
    MlfValue *ring=mlf_hole();
    MlfValue *node=mlf_constructor2(77,integer("1234567890123456789012345678901234567890"),ring);
    mlf_fill(ring,node);
    MlfValue *array=run(mlf_prim2(NEW_ST_ARRAY,integer("1"),node));
    MlfValue *action=read_at(array,"0");
    MlfValue *io=mlf_prim2(IO_BIND,mlf_prim1(IO_RETURN,action),closure(gc_finish,mlf_env_new(0)));
    for (unsigned i=0;i<4096;++i) (void)mlf_constructor2(88,integer("1"),integer("2"));
    return mlf_run(io,1);
}
static MlfValue *return_io(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument; return mlf_prim1(IO_RETURN,unit());
}
static void direct_cases(void) {
    MlfValue *lazy=bad();
    MlfValue *zero=mlf_st_new_array(integer("0"),lazy);
    number(mlf_st_length_array(zero),"0");
    MlfValue *array=mlf_st_new_array(integer("1"),lazy);
    require(mlf_st_read_array(array,integer("0"))==lazy,"direct read forced a stored thunk");
    require(mlf_execute_st_lazy(ret(lazy))==lazy,"lazy executor forced the final result");
    require(mlf_execute_st_lazy(read_at(array,"0"))==lazy,"lazy executor forced a read result");
    calls=0;
    MlfValue *old=mlf_thunk(counted,env1(integer("41")));
    mlf_st_write_array(array,integer("0"),old);
    MlfValue *snapshot=mlf_st_read_array(array,integer("0"));
    require(snapshot==old && calls==0,"direct read did not snapshot the cell pointer");
    mlf_st_write_array(array,integer("0"),integer("43"));
    number(snapshot,"41"); require(calls==1,"direct snapshot lost sharing");
    number(mlf_st_read_array(array,integer("0")),"43");
    run(write_at(array,"0",integer("47")));
    number(mlf_st_read_array(array,integer("0")),"47");
    mlf_st_write_array(array,integer("0"),integer("53"));
    number(run(read_at(array,"0")),"53");
    MlfValue *fresh=mlf_st_new_array(integer("1"),integer("59"));
    require(fresh!=array,"direct allocation reused a live array");
    number(mlf_st_read_array(array,integer("0")),"53");
    number(mlf_execute_st_lazy(bind(ret(integer("61")),closure(return_argument,mlf_env_new(0)))),"61");
    MlfValue *io=mlf_prim1(IO_RETURN,unit());
    require(mlf_execute_st_lazy(ret(io))==io,"executor changed an IO description result");
    mlf_st_write_array(fresh,integer("0"),bad());
    number(mlf_st_length_array(fresh),"1");
#ifdef MLF_USE_BDWGC
    GC_gcollect();
#endif
    number(mlf_st_read_array(array,integer("0")),"53");
}

int main(int argc, char **argv) {
    const char *mode=argc>1?argv[1]:"success";
    if (!strcmp(mode,"success")) {
        semantic_cases(); direct_cases(); require(gc_case()==0,"IO-root GC check failed");
        puts("runtime ST: laziness, snapshots, repetition, nesting, WHNF, and GC passed"); return 0;
    }
    MlfValue *array=run(mlf_prim2(NEW_ST_ARRAY,integer("1"),integer("5")));
    if (!strcmp(mode,"negative-size")) run(mlf_prim2(NEW_ST_ARRAY,integer("-1"),bad()));
    else if (!strcmp(mode,"huge-size")) run(mlf_prim2(NEW_ST_ARRAY,integer("123456789012345678901234567890"),bad()));
    else if (!strcmp(mode,"zero-read")) run(read_at(run(mlf_prim2(NEW_ST_ARRAY,integer("0"),bad())),"0"));
    else if (!strcmp(mode,"negative-read")) run(read_at(array,"-1"));
    else if (!strcmp(mode,"past-read")) run(read_at(array,"1"));
    else if (!strcmp(mode,"huge-read")) run(read_at(array,"123456789012345678901234567890"));
    else if (!strcmp(mode,"negative-write")) run(write_at(array,"-1",bad()));
    else if (!strcmp(mode,"past-write")) run(write_at(array,"1",bad()));
    else if (!strcmp(mode,"huge-write")) run(write_at(array,"123456789012345678901234567890",bad()));
    else if (!strcmp(mode,"ignored-invalid-read")) run(bind(read_at(array,"1"),closure(ignore_argument,env1(unit()))));
    else if (!strcmp(mode,"io-as-st")) run(mlf_prim1(IO_RETURN,unit()));
    else if (!strcmp(mode,"nested-io-as-st")) run(bind(ret(unit()),closure(return_io,mlf_env_new(0))));
    else if (!strcmp(mode,"st-as-io")) return mlf_run(ret(unit()),1);
    else if (!strcmp(mode,"int-array-as-st")) run(read_at(mlf_new_array(27,integer("1"),integer("1")),"0"));
    else if (!strcmp(mode,"st-array-as-io")) return mlf_run(mlf_prim2(28,array,integer("0")),1);
    else if (!strcmp(mode,"null-return")) (void)ret(NULL);
    else if (!strcmp(mode,"wrong-arity")) (void)mlf_prim1(ST_BIND,unit());
    else if (!strcmp(mode,"demand-poison")) run(ret(bad()));
    else if (!strcmp(mode,"cycle")) { MlfValue *hole=mlf_hole(); mlf_fill(hole,hole); run(ret(hole)); }
    else if (!strcmp(mode,"direct-negative-size")) (void)mlf_st_new_array(integer("-1"),bad());
    else if (!strcmp(mode,"direct-huge-size")) (void)mlf_st_new_array(integer("123456789012345678901234567890"),bad());
    else if (!strcmp(mode,"direct-zero-read")) (void)mlf_st_read_array(mlf_st_new_array(integer("0"),bad()),integer("0"));
    else if (!strcmp(mode,"direct-negative-read")) (void)mlf_st_read_array(array,integer("-1"));
    else if (!strcmp(mode,"direct-past-read")) (void)mlf_st_read_array(array,integer("1"));
    else if (!strcmp(mode,"direct-huge-read")) (void)mlf_st_read_array(array,integer("123456789012345678901234567890"));
    else if (!strcmp(mode,"direct-negative-write")) (void)mlf_st_write_array(array,integer("-1"),bad());
    else if (!strcmp(mode,"direct-past-write")) (void)mlf_st_write_array(array,integer("1"),bad());
    else if (!strcmp(mode,"direct-huge-write")) (void)mlf_st_write_array(array,integer("123456789012345678901234567890"),bad());
    else if (!strcmp(mode,"direct-io-as-st")) (void)mlf_execute_st_lazy(mlf_prim1(IO_RETURN,unit()));
    else if (!strcmp(mode,"direct-nested-io-as-st")) (void)mlf_execute_st_lazy(bind(ret(unit()),closure(return_io,mlf_env_new(0))));
    else if (!strcmp(mode,"direct-int-array-as-st")) (void)mlf_st_read_array(mlf_new_array(27,integer("1"),integer("1")),integer("0"));
    else if (!strcmp(mode,"direct-wrong-length")) (void)mlf_st_length_array(integer("1"));
    else if (!strcmp(mode,"direct-null-initial")) (void)mlf_st_new_array(integer("1"),NULL);
    else if (!strcmp(mode,"direct-null-stored")) (void)mlf_st_write_array(array,integer("0"),NULL);
    else { fprintf(stderr,"unknown ST mode: %s\n",mode); return 92; }
    fputs("runtime ST: invalid input was accepted\n",stderr); return 93;
}
