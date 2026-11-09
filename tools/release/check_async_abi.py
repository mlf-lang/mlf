#!/usr/bin/env python3
"""Require the exact current standalone LLVM entry's runtime ABI guards."""
from pathlib import Path
import sys

GUARDS = (
    b'mlf_require_haskell_boundary_v4_abi',
    b'mlf_require_byte_file_v2_abi',
    b'mlf_require_freeze_st_array_abi',
    b'mlf_require_st_to_io_abi',
)


def check(data):
    # Match emitted lines, not mentions in comments, strings or old symbol names.
    # LLVM.hs entryCode emits these guards unconditionally, before evaluating root.
    lines = data.split(b'\n')
    for guard in GUARDS:
        declaration = b'declare void @' + guard + b'()'
        if lines.count(declaration) != 1:
            raise ValueError('missing or duplicate ABI declaration: ' + guard.decode())
    prefix = [b'define ptr @mlf_entry() {'] + [
        b'  call void @' + guard + b'()' for guard in GUARDS]
    if lines.count(prefix[0]) != 1:
        raise ValueError('missing or duplicate standalone mlf_entry')
    start = lines.index(prefix[0])
    if lines[start:start + len(prefix)] != prefix:
        raise ValueError('current ABI guards must begin mlf_entry before root evaluation')


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check_async_abi.py EMITTED_LLVM')
    try:
        check(Path(sys.argv[1]).read_bytes())
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
