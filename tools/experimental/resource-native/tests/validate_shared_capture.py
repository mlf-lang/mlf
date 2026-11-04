"""Backward-compatible script/import wrapper for diagnostic capture replay.

Authority and replay semantics live unchanged in source_capture_v8; callers
still must authenticate the fresh source/build/invocation externally.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_capture_v8 as _implementation
# Preserve the former helper names too for existing integration users.
globals().update({name: value for name, value in vars(_implementation).items()
                  if not name.startswith('__')})
if __name__ == '__main__':
    raise SystemExit(_implementation.main())
