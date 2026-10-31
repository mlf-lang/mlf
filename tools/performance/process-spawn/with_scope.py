#!/usr/bin/env python3
"""Keep nested process helpers inside the unchanged runner's owned kill group."""
import os
import sys

if len(sys.argv) < 2:
    raise SystemExit('expected an absolute executable path and its arguments')
os.environ['MLF_BUILD_SCOPE'] = str(os.getpgrp())
os.execv(sys.argv[1], sys.argv[1:])
