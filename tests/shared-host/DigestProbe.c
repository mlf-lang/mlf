/* Exercise the real host adapter and its selected digest transport. */
#include "../../host/ghc/cbits/host.c"
int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1], "--bytes")) {
        unsigned char *bytes = NULL;
        size_t length = 0;
        const char *error = mlf_ghc_read_byte_file(argv[2], strlen(argv[2]),
                                                16777216, &bytes, &length);
        if (error[0]) { fprintf(stderr, "%s\n", error); free(bytes); return 1; }
        char digest[65];
        mlf_ghc_byte_array_digest(bytes, length, digest);
        puts(digest);
        free(bytes);
        return 0;
    }
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
