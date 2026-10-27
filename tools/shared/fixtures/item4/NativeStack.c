#include "../../../../runtime/mlf_runtime.c"
#include <assert.h>
static MlfValue *str(const char *s){return mlf_string(s,strlen(s));}
static MlfValue *frame(const char *name,int line){
 MlfEnv *f=mlf_env_new(8);mlf_env_set(f,0,str(name));mlf_env_set(f,1,str("pkg"));mlf_env_set(f,2,str("Mod"));mlf_env_set(f,3,str("file.hs"));
 mlf_env_set(f,4,small(line));mlf_env_set(f,5,small(2));mlf_env_set(f,6,small(line+2));mlf_env_set(f,7,small(9));return mlf_constructor_fields(7,f);
}
static MlfValue *ret(MlfValue *x){return mlf_prim1(IO_RETURN,x);}
static MlfValue *stack;
static MlfValue *raise_error(const char *s){return mlf_prim2(IO_ERROR_WITH_STACK,mlf_prim1(USER_ERROR,mlf_prim1(TEXT_TO_CHARS,str(s))),stack);}
static MlfValue *b(MlfEnv *e,MlfValue *v){(void)e;(void)v;return raise_error("b");}
static MlfValue *c(MlfEnv *e,MlfValue *v){(void)e;(void)v;return raise_error("c");}
static MlfValue *nested(MlfEnv *e,MlfValue *v){(void)e;(void)v;return mlf_prim2(CATCH_IO_ERROR,raise_error("b"),mlf_closure(c,NULL));}
static MlfValue *ignore(MlfEnv *e,MlfValue *v){(void)e;(void)v;return ret(small(42));}
static MlfValue *bad(MlfEnv *e,MlfValue *v){(void)e;(void)v;return mlf_prim1(PANIC,str("bottom"));}
static MlfValue *gc_raise(MlfEnv *e,MlfValue *v){(void)e;(void)v;GC_gcollect();return raise_error("gc");}
int main(int argc,char **argv){
 MlfValue *empty=mlf_primitive(EMPTY_CALL_STACK);
 assert(mlf_tag(mlf_prim1(PRETTY_CALL_STACK,empty))==2);
 MlfEnv *unicode=mlf_env_new(8);
 mlf_env_set(unicode,0,str("函数λ😀"));mlf_env_set(unicode,1,str("包"));mlf_env_set(unicode,2,str("模"));mlf_env_set(unicode,3,str("源.hs"));
 mlf_env_set(unicode,4,small(7));mlf_env_set(unicode,5,small(8));mlf_env_set(unicode,6,small(9));mlf_env_set(unicode,7,small(10));
 MlfValue *unicodeStack=mlf_prim2(PUSH_CALL_STACK,mlf_constructor_fields(7,unicode),empty);
 assert(mlf_truth(mlf_prim2(EQ_STRING,mlf_prim1(TEXT_FROM_CHARS,mlf_prim1(PRETTY_CALL_STACK,unicodeStack)),str("CallStack (from HasCallStack):\n  函数λ😀, called at 源.hs:7:8 in 包:模"))));
 if(argc>1 && !strcmp(argv[1],"surrogate")) {
  MlfValue *chars=mlf_constructor2(3,small(0xd800),mlf_constructor(2,0));
  return mlf_run(mlf_prim2(IO_ERROR_WITH_STACK,mlf_prim1(USER_ERROR,chars),empty),1);
 }
 stack=mlf_prim2(PUSH_CALL_STACK,frame("outer",20),empty);
 stack=mlf_prim2(PUSH_CALL_STACK,frame("inner",10),stack);
 MlfValue *text=mlf_prim1(TEXT_FROM_CHARS,mlf_prim1(PRETTY_CALL_STACK,stack));
 assert(mlf_truth(mlf_prim2(EQ_STRING,text,str("CallStack (from HasCallStack):\n  inner, called at file.hs:10:2 in pkg:Mod\n  outer, called at file.hs:20:2 in pkg:Mod"))));
 if(argc>1&& !strcmp(argv[1],"nested"))return mlf_run(mlf_prim2(CATCH_IO_ERROR,mlf_prim2(CATCH_IO_ERROR,raise_error("a"),mlf_closure(b,NULL)),mlf_closure(c,NULL)),1);
 if(argc>1&& !strcmp(argv[1],"active"))return mlf_run(mlf_prim2(CATCH_IO_ERROR,raise_error("a"),mlf_closure(nested,NULL)),1);
 if(argc>1&& !strcmp(argv[1],"direct"))return mlf_run(raise_error("source"),1);
 MlfValue *bottom=mlf_thunk(bad,NULL);
 MlfValue *err=mlf_prim1(USER_ERROR,bottom);
 MlfValue *action=mlf_prim2(IO_ERROR_WITH_STACK,err,bottom);
 assert(force(action)->tag==ACTION);
 assert(mlf_run(mlf_prim2(CATCH_IO_ERROR,action,mlf_closure(ignore,NULL)),1)==0);
 MlfEnv *fields=mlf_env_new(8);for(int i=0;i<8;i++)mlf_env_set(fields,i,bottom);
 MlfValue *lazy=mlf_prim2(PUSH_CALL_STACK,mlf_constructor_fields(7,fields),empty);
 MlfValue *prefix=mlf_prim1(PRETTY_CALL_STACK,lazy);
 const char *header="CallStack (from HasCallStack):\n  ";
 for(size_t i=0;i<strlen(header);i++){assert(mlf_tag(prefix)==3);assert(bounded_integer(mlf_field(prefix,0),0x10ffff,"char")==header[i]);prefix=mlf_field(prefix,1);}
 MlfValue *gcAction=mlf_prim2(IO_BIND,ret(small(0)),mlf_closure(gc_raise,NULL));
 assert(mlf_run(mlf_prim2(CATCH_IO_ERROR,gcAction,mlf_closure(ignore,NULL)),1)==0);
 puts("native stack assertions PASS");return 0;
}
