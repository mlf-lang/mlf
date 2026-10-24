#include "../../runtime/mlf_runtime.c"
int main(int argc,char **argv) {
  mlf_set_args(argc,argv);
  MlfValue *argument=get_argument(mlf_integer("0"));
  printf("%zu\n",argument->as.string.length);
  cleanup();return 0;
}
