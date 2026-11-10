#!/usr/bin/env python3
"""Private control child: record actual PID identity, then remain alive."""
from pathlib import Path
import json
import os
import sys
import time

destination = Path(sys.argv[1])
fields = Path('/proc/self/stat').read_text().split(') ', 1)[1].split()
value = {'pid': os.getpid(), 'parent_pid': os.getppid(),
         'start_ticks': fields[19], 'process_group': os.getpgrp()}
temporary = Path(str(destination) + '.tmp')
temporary.write_text(json.dumps(value) + '\n')
temporary.replace(destination)
time.sleep(30)
