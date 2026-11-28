#!/usr/bin/env python3
"""Require the exact current standalone LLVM entry's runtime ABI guard."""
from pathlib import Path
import sys

GUARD = b'mlf_require_runtime_v5_abi'


def check(data):
    # Match emitted lines, not mentions in comments, strings or old symbol names.
    # LLVM.hs entryCode emits this guard unconditionally, before evaluating root.
    lines = data.split(b'\n')
    declaration = b'declare void @' + GUARD + b'()'
    call = b'  call void @' + GUARD + b'()'
    if [line for line in lines if line.startswith(b'declare void @mlf_require_')] != [declaration]:
        raise ValueError('expected one current ABI declaration: ' + GUARD.decode())
    if [line for line in lines if line.startswith(b'  call void @mlf_require_')] != [call]:
        raise ValueError('expected one current ABI call: ' + GUARD.decode())
    prefix = [b'define ptr @mlf_entry() {', call]
    if lines.count(prefix[0]) != 1:
        raise ValueError('missing or duplicate standalone mlf_entry')
    start = lines.index(prefix[0])
    if lines[start:start + len(prefix)] != prefix:
        raise ValueError('current ABI guard must begin mlf_entry before root evaluation')


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check_async_abi.py EMITTED_LLVM')
    try:
        check(Path(sys.argv[1]).read_bytes())
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
