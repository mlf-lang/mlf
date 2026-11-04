/* Real generated-program entry. Default faults retain the evaluation ledger;
 * terminal surrender is a separate, explicit opt-in policy, never success. */
#include "rir8_session.h"
#include "ir8_runtime_generated.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define DRIVER_DEFAULT_FUEL UINT64_C(1000000)
#define DRIVER_MAX_FUEL UINT64_C(10000000)

static int usage(void)
{
    fputs("usage: program [--fuel 1..10000000] "
          "[--failure-policy retain|destroy-terminal]\n", stderr);
    return 64;
}

static int parse_fuel(const char *text, uint64_t *result)
{
    uint64_t value = 0;
    const unsigned char *p = (const unsigned char *)text;
    if (!*p) return 0;
    do {
        uint64_t digit;
        if (*p < (unsigned char)'0' || *p > (unsigned char)'9') return 0;
        digit = (uint64_t)(*p - (unsigned char)'0');
        if (value > (DRIVER_MAX_FUEL - digit) / UINT64_C(10)) return 0;
        value = value * UINT64_C(10) + digit;
        ++p;
    } while (*p);
    if (!value) return 0;
    *result = value;
    return 1;
}

int main(int argc, char **argv)
{
    uint64_t fuel = DRIVER_DEFAULT_FUEL;
    int have_fuel = 0, have_policy = 0, terminal = 0, i, result;
    Rt8Program program;
    Ir8PacketExpectedBindings expected;
    static Rt8BindingWorkspace workspace;
    Rt8Options options;
    Rt8Report report = {0};
    Rt8DestroyReport destroyed = {0};

    /* Parse before obtaining the program or invoking any runtime API. */
    for (i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--fuel") == 0) {
            if (have_fuel || i + 1 >= argc || !parse_fuel(argv[++i], &fuel))
                return usage();
            have_fuel = 1;
        } else if (strcmp(argv[i], "--failure-policy") == 0) {
            if (have_policy || i + 1 >= argc) return usage();
            ++i;
            if (strcmp(argv[i], "retain") == 0) terminal = 0;
            else if (strcmp(argv[i], "destroy-terminal") == 0) terminal = 1;
            else return usage();
            have_policy = 1;
        } else return usage();
    }

    program = ir8_runtime_generated_program();
    /* The generated tuple is part of an immutable root. The binder requires
     * separate caller storage, not an aliased pointer into that root. */
    memcpy(&expected, ir8_runtime_generated_expected_bindings(), sizeof expected);
    options = (Rt8Options){fuel, UINT64_C(100000), UINT64_C(0)};
    if (terminal) {
        result = rt8_run_repeat_destroy_fault(&program, &expected, &workspace,
            &options, UINT64_C(1), stdout, &report, &destroyed);
    } else {
        result = rt8_run(&program, &expected, &workspace, &options, stdout, &report);
    }
    /* Never turn the genuine evaluation fault into success or replace its rc.
     * A healthy evaluation with an undeliverable report is an I/O failure. */
    if (fflush(stdout) != 0 || ferror(stdout)) {
        fputs("native driver: could not write the runtime report\n", stderr);
        return result ? result : 74;
    }
    return result;
}
