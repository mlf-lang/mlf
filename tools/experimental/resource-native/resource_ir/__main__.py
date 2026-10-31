from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import CheckError, RuntimeFault, check, loads, run


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone resource IR v3 with anchored borrowed publication (planner separate)")
    parser.add_argument("command", choices=("check", "run"))
    parser.add_argument("program", type=Path)
    parser.add_argument("--fuel", type=int, default=1_000_000)
    parser.add_argument("--events", type=int, default=0, help="bounded diagnostic event count; not needed for acceptance")
    args = parser.parse_args()
    try:
        program = loads(args.program.read_text(encoding="utf-8"))
        result = check(program).report() if args.command == "check" else run(program, fuel=args.fuel, event_limit=args.events)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except CheckError as exc:
        print(json.dumps({"status": "rejected", "path": exc.path, "code": exc.code, "message": exc.message}), file=sys.stderr)
        return 2
    except RuntimeFault as exc:
        print(json.dumps({"status": "aborted", "code": exc.code, "message": exc.message,
                          "cleanup": "unsupported on terminal machine failure"}), file=sys.stderr)
        return 3
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "input_error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
