/* Exercise unchanged native runtime helpers without building the compiler. */
#include "../../runtime/mlf_runtime.c"
int main(int argc,char **argv) {
  if(argc==3 && !strcmp(argv[1],"file-exists")) {
    printf("%s\n",mlf_truth(file_exists(mlf_string(argv[2],strlen(argv[2]))))?"True":"False");
  } else if(argc==3 && !strcmp(argv[1],"canonical")) {
    (void)canonical_path(mlf_string(argv[2],strlen(argv[2])));
    puts("returned");
  } else if(argc==2 && !strcmp(argv[1],"contents-byte-line")) {
    (void)read_contents();
    MlfValue *bytes=mlf_get_byte_line();
    printf("%zu\n",bytes->as.byte_array.length);
  } else return 2;
  cleanup(); return 0;
}
