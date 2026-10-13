/* Inspect allocator startup through the same public runtime API as generated
 * code. In "api-cap" mode an embedding caller imposes its own heap limit. */
#include "mlf_runtime.h"
#include <gc/gc.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "api-cap"))
        GC_set_max_heap_size(8 * 1024 * 1024);
    else if (argc != 1) return 2;
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, mlf_integer("42"));
    if (!mlf_truth(mlf_eq_int(mlf_env_get(env, 0), mlf_integer("42")))) return 3;
    printf("{\"heap_bytes\":%zu,\"divisor\":%zu}\n", GC_get_heap_size(), (size_t)GC_get_free_space_divisor());
    return 0;
}
