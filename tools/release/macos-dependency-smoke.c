#include <stdio.h>
#include <gmp.h>
#include <gc.h>

int main(void) {
    GC_INIT();
    if (GC_malloc(32) == NULL) {
        return 1;
    }
    mpz_t value;
    mpz_init_set_ui(value, 42);
    gmp_printf("%Zd\n", value);
    mpz_clear(value);
    return 0;
}
