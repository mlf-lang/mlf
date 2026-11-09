#include "mlf_runtime.c"
#include <assert.h>
static int checks;
static void unit(MlfValue *v){ assert(mlf_tag(v)==1);checks++; }
static MlfValue *check(MlfEnv *e,MlfValue *v){(void)e;unit(v);return action(IO_RETURN,v,NULL);}
static void run(MlfValue *a){assert(mlf_run(action(IO_BIND,a,mlf_closure(check,NULL)),1)==0);}
int main(int argc, char **argv){
 assert(argc == 2);
 MlfValue *a=mlf_new_array(NEW_INT_ARRAY,small(1),small(0));
 unit(write_array(array_write_action(WRITE_INT_ACTION,a,small(0),small(7))));
 MlfValue *d=mlf_new_array(NEW_DOUBLE_ARRAY,small(1),mlf_double(0));
 unit(write_array(array_write_action(WRITE_DOUBLE_ACTION,d,small(0),mlf_double(7))));
 MlfValue *b=mlf_new_array(NEW_BYTE_ARRAY,small(1),small(0));
 unit(write_array(array_write_action(WRITE_BYTE_ACTION,b,small(0),small(7))));
 unit(mlf_put_bytes(b,small(0),small(0)));
 MlfValue *t=mlf_new_int_table();unit(mlf_write_int_table(t,small(1),small(9)));
 MlfValue *big=mlf_integer("9223372036854775808");
 unit(mlf_write_int_table(t,big,small(8)));
 MlfValue *st=mlf_st_new_array(small(1),small(0));unit(mlf_st_write_array(st,small(0),small(2)));
 unit(run_st(mlf_prim3(WRITE_ST_ARRAY,st,small(0),small(3))));
 MlfValue *key=mlf_string("MLF_ITEM4_V3_UNIT_TEST",22),*empty=mlf_string("",0);
 unit(os_setEnv(key,empty));unit(os_unsetEnv(key));
 run(action(WRITE_FILE,mlf_string(argv[1],strlen(argv[1])),empty));
 run(action(PUT_STR,empty,NULL));run(action(PUT_ERR,empty,NULL));run(action(PUT_STR_LN,empty,NULL));run(action(PRINT_INT,small(0),NULL));
 run(mlf_prim1(ASYNC_SCOPE_CLOSE,async_scope_value(mlf_completion_scope_new(4,4))));
 MlfValue *custom=mlf_constructor(69,0);assert(mlf_tag(custom)==69&&mlf_tag(custom)!=1);
 MlfEnv *fields=mlf_env_new(64);for(int i=0;i<64;i++)mlf_env_set(fields,i,small(i));
 MlfValue *tuple=mlf_constructor_fields(68,fields);assert(mlf_tag(tuple)==68&&small_value(force(mlf_field(tuple,63)))==63);
 printf("native canonical unit assertions PASS (%d unit results)\n",checks);return 0;
}
