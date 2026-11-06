#include "../../../../runtime/mlf_runtime.c"
#include <assert.h>
static int caught, skipped, after;
static MlfValue *message;
static MlfValue *ret(MlfValue *v) { return mlf_prim1(IO_RETURN,v); }
static MlfValue *raise_message(void) { return mlf_prim1(IO_ERROR, mlf_prim1(USER_ERROR,message)); }
static MlfValue *handler(MlfEnv *e,MlfValue *error) {
 (void)e; caught++;
 assert(mlf_truth(mlf_prim2(EQ_STRING,mlf_prim1(TEXT_FROM_CHARS,mlf_prim1(IO_ERROR_STRING,error)),mlf_string("h\xc3\xa9\xf0\x9f\x98\x80",7))));
 return ret(small(42));
}
static MlfValue *bad(MlfEnv *e,MlfValue *x) {(void)e;(void)x;skipped++;return ret(small(0));}
static MlfValue *done(MlfEnv *e,MlfValue *x) {(void)e;assert(bounded_integer(x,100,"test")==42);after++;return ret(x);}
static MlfValue *rethrow(MlfEnv *e,MlfValue *x) {(void)e;return mlf_prim1(IO_ERROR,x);}
static MlfValue *ignore(MlfEnv *e,MlfValue *x) {(void)e;(void)x;return ret(small(42));}
static MlfValue *raise_after(MlfEnv *e,MlfValue *x) {(void)e;(void)x;return raise_message();}
static MlfValue *gc_raise(MlfEnv *e,MlfValue *x) {(void)e;(void)x;GC_gcollect();return raise_message();}
static MlfValue *bottom_handler(MlfEnv *e,MlfValue *x) {(void)x;return ret(mlf_env_get(e,0));}
static MlfValue *busy_done(MlfEnv *e,MlfValue *x) {(void)e;assert(bounded_integer(x,100,"busy")==MLF_COMPLETION_BUSY);return ret(small(42));}
static MlfValue *busy_handler(MlfEnv *e,MlfValue *x) {(void)x;return mlf_prim2(IO_BIND,mlf_prim1(ASYNC_STEP,mlf_env_get(e,0)),mlf_closure(busy_done,NULL));}
static MlfValue *panic_thunk(MlfEnv *e,MlfValue *x) {(void)e;(void)x;return mlf_prim1(PANIC,mlf_string("pure panic",10));}
int main(int argc,char **argv) {
 message=mlf_prim1(TEXT_TO_CHARS,mlf_string("h\xc3\xa9\xf0\x9f\x98\x80",7));
 assert(mlf_tag(message)==3);
 assert(bounded_integer(mlf_prim1(CHAR_CODE,mlf_prim1(CHAR_FROM_CODE,small(0xd800))),0x10ffff,"test")==0xd800);
 if(argc>1 && !strcmp(argv[1],"surrogate")) { (void)mlf_prim1(TEXT_FROM_CHARS,mlf_constructor2(3,small(0xd800),mlf_constructor(2,0))); return 9; }
 if(argc>1 && !strcmp(argv[1],"panic")) return mlf_run(mlf_prim2(CATCH_IO_ERROR,mlf_thunk(panic_thunk,NULL),mlf_closure(handler,NULL)),1);
 if(argc>1 && !strcmp(argv[1],"uncaught")) return mlf_run(raise_message(),1);
 MlfValue *err=mlf_prim1(USER_ERROR,mlf_constructor2(3,small(0xd800),mlf_constructor(2,0)));
 assert(bounded_integer(mlf_field(mlf_prim1(IO_ERROR_STRING,err),0),0x10ffff,"test")==0xd800);
 MlfValue *action=mlf_prim2(IO_BIND,raise_message(),mlf_closure(bad,NULL));
 action=mlf_prim2(CATCH_IO_ERROR,action,mlf_closure(rethrow,NULL));
 action=mlf_prim2(CATCH_IO_ERROR,action,mlf_closure(handler,NULL));
 action=mlf_prim2(IO_BIND,action,mlf_closure(done,NULL));
 assert(mlf_run(action,1)==0); assert(caught==1&&skipped==0&&after==1);
 /* Construction, pure return, and catching must not force a bottom message. */
 MlfValue *bottom=mlf_thunk(panic_thunk,NULL);
 MlfValue *unused=mlf_prim1(IO_ERROR,bottom);
 assert(force(unused)->tag==ACTION);
 assert(mlf_run(ret(bottom),1)==0);
 action=mlf_prim2(CATCH_IO_ERROR,mlf_prim1(IO_ERROR,mlf_prim1(USER_ERROR,bottom)),mlf_closure(ignore,NULL));
 assert(mlf_run(action,1)==0);
 MlfEnv *bottomEnv=mlf_env_new(1); mlf_env_set(bottomEnv,0,bottom);
 action=mlf_prim2(CATCH_IO_ERROR,raise_message(),mlf_closure(bottom_handler,bottomEnv));
 assert(mlf_run(action,1)==0);
 /* A normal catch frame must expire before the continuation's later error. */
 action=mlf_prim2(CATCH_IO_ERROR,ret(small(1)),mlf_closure(bad,NULL));
 action=mlf_prim2(IO_BIND,action,mlf_closure(raise_after, NULL));
 action=mlf_prim2(CATCH_IO_ERROR,action,mlf_closure(handler,NULL));
 assert(mlf_run(action,1)==0); assert(skipped==0&&caught==2);
 /* Test async cleanup by enqueueing a failing callback and catching outside step. */
 MlfCompletionScope *scope=mlf_completion_scope_new(16,16);
 MlfValue *sv=async_scope_value(scope);
 MlfValue *callback=mlf_prim2(IO_BIND,ret(small(0)),mlf_closure(gc_raise,NULL));
 MlfCompletionResume *resume=NULL;
 assert(mlf_completion_enqueue(scope,callback,&resume)==MLF_COMPLETION_OK);
 action=mlf_prim2(CATCH_IO_ERROR,mlf_prim1(ASYNC_STEP,sv),mlf_closure(handler,NULL));
 assert(mlf_run(action,1)==0); assert(!scope->dispatching); assert(caught==3);
 /* Completion subscription callbacks use the same unwind cleanup. */
 MlfCompletion *cell=NULL;
 assert(mlf_completion_new(scope,&cell)==MLF_COMPLETION_OK);
 assert(mlf_completion_subscribe(scope,cell,mlf_closure(raise_after,NULL),&resume)==MLF_COMPLETION_OK);
 assert(mlf_completion_resolve(scope,cell,small(1))==MLF_COMPLETION_OK);
 action=mlf_prim2(CATCH_IO_ERROR,mlf_prim1(ASYNC_STEP,sv),mlf_closure(handler,NULL));
 assert(mlf_run(action,1)==0); assert(!scope->dispatching&&caught==4);
 /* A following callback still runs, and normal completion clears busy too. */
 assert(mlf_completion_enqueue(scope,ret(small(9)),&resume)==MLF_COMPLETION_OK);
 assert(mlf_run(mlf_prim1(ASYNC_STEP,sv),1)==0); assert(!scope->dispatching);
 /* Catch inside a callback must retain the enclosing busy frame. */
 MlfEnv *scopeEnv=mlf_env_new(1);mlf_env_set(scopeEnv,0,sv);
 callback=mlf_prim2(CATCH_IO_ERROR,raise_message(),mlf_closure(busy_handler,scopeEnv));
 assert(mlf_completion_enqueue(scope,callback,&resume)==MLF_COMPLETION_OK);
 assert(mlf_run(mlf_prim1(ASYNC_STEP,sv),1)==0);assert(!scope->dispatching);
 /* Unwind across nested different scopes must reset both finish frames. */
 MlfCompletionScope *inner=mlf_completion_scope_new(16,16);
 MlfValue *iv=async_scope_value(inner);
 assert(mlf_completion_enqueue(inner,raise_message(),&resume)==MLF_COMPLETION_OK);
 assert(mlf_completion_enqueue(scope,mlf_prim1(ASYNC_STEP,iv),&resume)==MLF_COMPLETION_OK);
 action=mlf_prim2(CATCH_IO_ERROR,mlf_prim1(ASYNC_STEP,sv),mlf_closure(handler,NULL));
 assert(mlf_run(action,1)==0);assert(!scope->dispatching&&!inner->dispatching&&caught==5);
 puts("native item4 assertions PASS"); return 0;
}
