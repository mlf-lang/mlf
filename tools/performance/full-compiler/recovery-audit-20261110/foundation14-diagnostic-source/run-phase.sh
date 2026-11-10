#!/usr/bin/env bash
# No automatic SETUP -> QD. Each invocation requires coordinator admission.
set -euo pipefail
[[ $# == 5 ]] || { echo 'usage: run-phase.sh SETUP|QD SOURCE HANDOFF SHA256 NEW_PHASE_ROOT' >&2; exit 2; }
phase=$1; source=$2; handoff=$3; digest=$4; root=$5
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${MLF_GC_PYTHON:?set the exact absolute producer Python, currently /usr/bin/python3}"
python=$MLF_GC_PYTHON
[[ -x "$python" ]] || exit 2
[[ "$python" == /* && "$source" == /* && "$handoff" == /* && "$root" == /* ]] || exit 2
case "$phase" in SETUP) seconds=120;; QD) seconds=420;; *) exit 2;; esac
[[ $(sha256sum "$source/tools/shared/resource_watchdog.py" | cut -d' ' -f1) == 5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f ]] || exit 3
[[ $(sha256sum "$source/tools/performance/process-spawn/with_scope.py" | cut -d' ' -f1) == d8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3 ]] || exit 3
[[ $(sha256sum "$handoff" | cut -d' ' -f1) == "$digest" && ! -e "$root" && ! -L "$root" ]] || exit 3
umask 077
exec "$python" -B "$here/run_envelope.py" "$phase" "$source" "$handoff" "$digest" "$root"
