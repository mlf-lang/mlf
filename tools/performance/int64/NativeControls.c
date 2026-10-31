/* Exercises the public runtime ABI; expected answers come from GHC Int64. */
#define _POSIX_C_SOURCE 200809L
#include "mlf_runtime.h"
#include <gc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int curried;
static MlfValue *apply(int p, int arity, MlfValue *a, MlfValue *b) {
    if (!curried) return arity == 1 ? mlf_prim1(p,a) : mlf_prim2(p,a,b);
    MlfValue *r = mlf_application(mlf_primitive(p),a);
    return arity == 1 ? r : mlf_application(r,b);
}
static void print_text(MlfValue *text) {
    MlfValue *n = mlf_string_length(text), *i = mlf_integer("0"), *one = mlf_integer("1");
    while (mlf_truth(mlf_lt_int(i,n))) {
        putchar(mlf_byte(mlf_string_code_at(text,i)));
        i = mlf_add_int(i,one);
    }
    putchar('\n');
}
static MlfValue *panic_argument(MlfEnv *env, MlfValue *ignored) {
    (void)ignored;
    return mlf_prim1(55,mlf_env_get(env,0));
}
static MlfValue *failure(const char *message) {
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env,0,mlf_string(message,strlen(message)));
    return mlf_thunk(panic_argument,env);
}
int main(int argc, char **argv) {
    mlf_require_haskell_boundary_v4_abi();
    if (argc == 2 && !strcmp(argv[1],"--unsigned-allocation")) {
        GC_INIT();
        MlfValue *zero = mlf_integer("0"), *negative = mlf_integer("-1");
        MlfValue *sign = mlf_integer("-9223372036854775808");
        size_t before = GC_get_total_bytes();
        unsigned direct_true = 0, xor_true = 0;
        for (int i = 0; i < 10000; ++i)
            direct_true += mlf_truth(mlf_prim2(128,zero,negative));
        size_t direct_bytes = GC_get_total_bytes() - before;
        before = GC_get_total_bytes();
        for (int i = 0; i < 10000; ++i)
            xor_true += mlf_truth(mlf_lt_int(mlf_prim2(109,zero,sign),mlf_prim2(109,negative,sign)));
        size_t xor_bytes = GC_get_total_bytes() - before;
        printf("unsigned comparison: direct=%zu xor=%zu true=%u/%u\n",
               direct_bytes,xor_bytes,direct_true,xor_true);
        return direct_bytes == 0 && xor_bytes > 0 && direct_true == 10000 && xor_true == 10000 ? 0 : 3;
    }
    if (argc == 3 && (!strcmp(argv[1],"--demand") || !strcmp(argv[1],"--demand-curried"))) {
        curried = !strcmp(argv[1],"--demand-curried");
        mlf_force(apply(atoi(argv[2]),2,failure("left"),failure("right")));
        return 3;
    }
    if (argc != 3) return 2;
    curried = !strcmp(argv[2],"curried");
    FILE *input = fopen(argv[1],"r");
    if (!input) return 2;
    char line[8192];
    MlfValue *table = mlf_new_int_table();
    unsigned long count = 0;
    while (fgets(line,sizeof(line),input)) {
        char *state, *id = strtok_r(line,"\t\n",&state);
        char *left = strtok_r(NULL,"\t\n",&state), *right = strtok_r(NULL,"\t\n",&state);
        if (!id || !left || !right) return 2;
        int p = atoi(id);
        MlfValue *a, *b = NULL, *result;
        if (p == 17 || p == 126) a = mlf_string(left,strlen(left));
        else if (p >= 117 && p <= 127) a = mlf_prim1(126,mlf_string(left,strlen(left)));
        else a = mlf_integer(left);
        int binary = (p >= 8 && p <= 11) || (p >= 14 && p <= 16) || p == 45 ||
                     (p >= 108 && p <= 112) || (p >= 118 && p <= 124) || p == 128 || p >= 1002;
        if (binary) b = p >= 118 && p <= 124
            ? mlf_prim1(126,mlf_string(right,strlen(right))) : mlf_integer(right);
        if (p == 1000) result = apply(52,1,apply(53,1,a,NULL),NULL);
        else if (p == 1002) { mlf_write_int_table(table,a,b); result = mlf_read_int_table(table,a); }
        else if (p == 1003) result = mlf_read_int_table(table,a);
        else if (p == 1004) { mlf_add_int_table(table,a,b); result = mlf_read_int_table(table,a); }
        else result = apply(p,binary ? 2 : 1,a,b);
        if (p == 10 || p == 11 || p == 123 || p == 124 || p == 128) {
            puts(mlf_truth(result) ? "1" : "0");
        } else {
            if (p == 25 || p == 127) result = apply(52,1,result,NULL);
            if (p != 7 && p != 125) result = apply(
                p == 116 || (p >= 118 && p <= 122) || p == 126 ? 125 : 7,1,result,NULL);
            print_text(result);
        }
        if ((++count % 1024) == 0) mlf_gc_check(1,&table);
    }
    fclose(input);
    return ferror(stdout) ? 2 : 0;
}
