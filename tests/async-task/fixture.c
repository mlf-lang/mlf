/* Extra deterministic child operations for Task tests. Supervisor state and
 * scheduling assertions remain in MLF. The parent harness provides watchdogs. */
#define main process_fixture_main
#include "../async-process/fixture.c"
#undef main
#include <fcntl.h>

int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1], "once")) {
        int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0) return 103;
        if (write(fd, "once\n", 5) != 5 || close(fd)) return 104;
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "value")) {
        write_text(argv[3], argv[2]);
        return 0;
    }
    return process_fixture_main(argc, argv);
}
