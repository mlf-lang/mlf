#!/usr/bin/env bash
set -euo pipefail
manager="$PWD/.mlf-build/shared-ghc-O0/bin/mlfpkg"
"$manager" --version > .mlf-build/shared-lock-probe/version.txt
"$manager" lock > .mlf-build/shared-lock-probe/lock.stdout 2> .mlf-build/shared-lock-probe/lock.stderr
"$manager" --locked plan > .mlf-build/shared-lock-probe/plan.json 2> .mlf-build/shared-lock-probe/plan.stderr
