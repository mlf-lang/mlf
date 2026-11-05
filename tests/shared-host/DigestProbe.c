/* Exercise the real host adapter and its selected digest transport. */
#include "../../host/ghc/cbits/host.c"
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    MlfValue input = {0};
    input.as.string.bytes = argv[1];
    input.as.string.length = strlen(argv[1]);
    if (!strcmp(argv[1], "--nul-test")) {
        input.as.string.bytes = "a\0b";
        input.as.string.length = 3;
    }
    if (setjmp(host_failure)) {
        fprintf(stderr, "%s\n", host_error);
        return 1;
    }
    MlfValue *result = os_fileDigest(&input);
    puts(result->as.string.bytes);
    return 0;
}
