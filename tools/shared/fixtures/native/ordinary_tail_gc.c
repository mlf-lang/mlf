#include <gc.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
extern int32_t tail_program_main(int32_t, char **);
int main(int argc, char **argv) {
    GC_set_all_interior_pointers(0);
    GC_set_free_space_divisor(64);
    GC_INIT();
    GC_word before = GC_get_gc_no();
    int result = tail_program_main(argc, argv);
    printf("collections=%" PRIuPTR "\n", (uintptr_t)(GC_get_gc_no() - before));
    return result;
}
