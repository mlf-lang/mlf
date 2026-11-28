/* Probe the public SDK/runtime interface used by the current CWD spawn path. */
#include <stdio.h>
#if defined(__APPLE__)
#include <spawn.h>
#endif

int main(void) {
#if defined(__APPLE__) && defined(__MAC_26_0) && __MAC_OS_X_VERSION_MAX_ALLOWED >= __MAC_26_0
    if (__builtin_available(macOS 26.0, *)) {
        posix_spawn_file_actions_t actions;
        if (posix_spawn_file_actions_init(&actions)) return 2;
        int changed = posix_spawn_file_actions_addchdir(&actions, ".");
        int destroyed = posix_spawn_file_actions_destroy(&actions);
        if (changed || destroyed) return 2;
        puts("spawn-cwd");
        return 0;
    }
#endif
    puts("fork-cwd-fallback");
    return 0;
}
