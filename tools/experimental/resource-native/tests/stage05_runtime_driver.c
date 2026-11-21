#include "rir8_session.h"
#include "ir8_runtime_generated.h"
#include <errno.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    uint64_t repetitions = 1;
    Rt8Program program = ir8_runtime_generated_program();
    Ir8PacketExpectedBindings expected;
    static Rt8BindingWorkspace workspace;
    Rt8Options options = {UINT64_C(1000000), UINT64_C(100000), UINT64_C(0)};
    Rt8Report report;
    Rt8DestroyReport destroyed;
    if (argc > 2) return 64;
    if (argc == 2) {
        char *end = NULL;
        unsigned long long n;
        errno = 0;
        if (argv[1][0] == '-' || argv[1][0] == '+') return 64;
        n = strtoull(argv[1], &end, 10);
        if (errno || end == argv[1] || *end || n == 0 || n > 100) return 64;
        repetitions = (uint64_t)n;
    }
    memcpy(&expected, ir8_runtime_generated_expected_bindings(), sizeof expected);
    memset(&workspace, 0, sizeof workspace);
    memset(&report, 0, sizeof report);
    memset(&destroyed, 0, sizeof destroyed);
    return rt8_run_repeat_destroy_fault(&program, &expected, &workspace, &options,
        repetitions, stdout, &report, &destroyed);
}
