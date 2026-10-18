// A fresh linker process may load its libraries while its object producers run.
// Completion markers are made only after successful compiler exits. Read the
// ordinary object files after that point; never parse a partially written file.
#include <lld/Common/Driver.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
#include <time.h>
LLD_HAS_DRIVER(macho)
int main(int argc, char **argv) {
    int separator = 1;
    while (separator < argc && std::strcmp(argv[separator], "--")) ++separator;
    if (separator == 1 || separator + 1 >= argc) {
        std::fprintf(stderr, "usage: mlf-link READY_FILE... -- LD64_LLD ARG...\n");
        return 2;
    }
    for (;;) {
        bool ready = true;
        for (int i = 1; i < separator; ++i) {
            struct stat info;
            if (!stat(argv[i], &info)) {
                if (!S_ISREG(info.st_mode)) {
                    std::fprintf(stderr, "mlf-link: invalid completion marker: %s\n", argv[i]);
                    return 2;
                }
            } else if (errno == ENOENT) ready = false;
            else { std::perror("mlf-link: completion marker"); return 2; }
        }
        if (ready) break;
        struct timespec pause = {0, 1000000};
        while (nanosleep(&pause, &pause) && errno == EINTR) {}
    }
    const lld::DriverDef drivers[] = {{lld::Darwin, &lld::macho::link}};
    auto result = lld::lldMain(
        llvm::ArrayRef<const char *>(argv + separator + 1, argc - separator - 1),
        llvm::outs(), llvm::errs(), drivers);
    return result.retCode;
}
