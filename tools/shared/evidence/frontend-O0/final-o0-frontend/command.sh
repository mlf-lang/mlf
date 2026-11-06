#!/usr/bin/env bash
set -euo pipefail
exec /workspace/shared/mlf-shared-source-migration/.mlf-build/shared-ghc-O0/bin/shared-frontend --frontend >/tmp/mlf-shared-frontend-evidence/final-o0-frontend/stdout 2>/tmp/mlf-shared-frontend-evidence/final-o0-frontend/stderr
