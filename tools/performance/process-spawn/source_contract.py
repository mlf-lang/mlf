"""Admit only the reviewed Darwin spawn header in the retained C4 source gate."""
import hashlib
from pathlib import Path

HEADER = 'runtime/mlf_system.h'
OLD_SHA = '9254a1d28a0718ef100916020a96d860ee559e797d311cd4569f887d5fec841e'
NEW_SHA = 'cc87aa9445c45e7e6fe66b2631a887be870baf3015f9daa6d6705d356ed37477'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def restore_previous(raw):
    require(sha(raw) == NEW_SHA, 'exact reviewed spawn header')
    includes = b'#include <crt_externs.h>\n#include <spawn.h>\n'
    start = b'#if defined(__APPLE__)\n    pid_t pid = -1;\n'
    end = b'#else\n    pid_t pid = fork();\n#endif\n'
    require(raw.count(includes) == raw.count(start) == raw.count(end) == 1, 'one additive Darwin branch')
    left = raw.index(start); right = raw.index(end, left)+len(end)
    previous = (raw[:left]+b'    pid_t pid = fork();\n'+raw[right:]).replace(includes,b'')
    require(sha(previous) == OLD_SHA, 'complete unchanged pre-spawn header recovered')
    return previous


def candidate_dependencies(expected, source):
    require(expected[HEADER] == OLD_SHA, 'exact existing C4 runtime dependency')
    raw = (Path(source)/HEADER).read_bytes()
    if sha(raw) == OLD_SHA:
        return expected
    restore_previous(raw)
    return {**expected, HEADER: NEW_SHA}
