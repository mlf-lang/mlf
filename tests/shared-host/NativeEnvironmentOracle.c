#include "../../runtime/mlf_runtime.c"
static MlfValue *poison_name(MlfEnv *env,MlfValue *ignored) {
    (void)env; (void)ignored; fail("name");
}
static MlfValue *poison_contents(MlfEnv *env,MlfValue *ignored) {
    (void)env; (void)ignored; fail("contents");
}
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    MlfValue *name=!strcmp(argv[1],"both-bottom")
        ? mlf_thunk(poison_name,NULL) : mlf_string("bad\0name",8);
    (void)os_setEnv(name,mlf_thunk(poison_contents,NULL));
    cleanup(); return 0;
}
