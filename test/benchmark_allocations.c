/* Untimed allocation audit for benchmarks/binary-trees/mlf/main.emlf.
 * Linked only by benchmark-harness-tests, never by benchmark executables. */
#include "mlf_runtime.h"
#include <inttypes.h>
#include <stdio.h>

static uint64_t tree_nodes;
int32_t mlf_original_run(MlfValue *root, int64_t is_io);

void mlf_bench_constructed_node(int64_t tag) {
    if (tag == 2) ++tree_nodes;
}

int32_t mlf_run(MlfValue *root, int64_t is_io) {
    int32_t result = mlf_original_run(root, is_io);
    fprintf(stderr, "allocated_tree_nodes=%" PRIu64 "\n", tree_nodes);
    return result;
}
