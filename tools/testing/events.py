"""Write case evidence from the adapter that actually ran the check."""

import json
import os


def _emit(event):
    path = os.environ.get("MLF_TEST_EVENTS")
    if path:
        line = (json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            if os.write(descriptor, line) != len(line):
                raise OSError("short write to test event log")
        finally:
            os.close(descriptor)


def plan(ids):
    _emit({"plan": list(ids)})


def start(identity, **details):
    _emit({"start": identity, **details})


def result(identity, status, **details):
    _emit({"id": identity, "status": status, **details})
