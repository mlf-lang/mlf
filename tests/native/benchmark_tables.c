/* Untimed work audit. Runtime hooks count actual library insert/update calls;
 * no benchmark-specific code is present in measured runtime builds. */
#include "mlf_runtime.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

static struct { MlfValue *table; uint64_t writes, distinct; } tables[7];
static size_t count;
int32_t mlf_original_run(MlfValue *root, int64_t is_io);

void mlf_bench_table_created(MlfValue *table) {
    if (count == 7) abort();
    tables[count++].table = table;
}
void mlf_bench_table_written(MlfValue *table, int inserted) {
    /* The collector can reuse a dead table's address. Match the latest
     * allocation so the audit preserves table generations. */
    for (size_t i = count; i > 0; --i) {
        if (tables[i-1].table == table) {
            ++tables[i-1].writes;
            tables[i-1].distinct += inserted != 0;
            return;
        }
    }
    abort();
}
int32_t mlf_run(MlfValue *root, int64_t is_io) {
    int32_t result = mlf_original_run(root, is_io);
    fprintf(stderr, "tables=%zu\n", count);
    for (size_t i = 0; i < count; ++i)
        fprintf(stderr, "writes=%" PRIu64 " distinct=%" PRIu64 "\n", tables[i].writes, tables[i].distinct);
    return result;
}
