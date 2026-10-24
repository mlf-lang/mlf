#!/usr/bin/env bash
set -euo pipefail
exec /workspace/shared/mlf-shared-source-migration/.mlf-build/shared-ghc-O0/bin/shared-frontend --native-first >/tmp/mlf-shared-frontend-evidence/final-o0-native-first/stdout 2>/tmp/mlf-shared-frontend-evidence/final-o0-native-first/stderr
