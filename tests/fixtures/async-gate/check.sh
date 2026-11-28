#!/bin/sh
# Focused representation gate. No compiler bootstrap or package dependencies.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$root/../../.." && pwd)
. "$project/tools/testing/native-events.sh"
emlf=${EMLF:-emlf}
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-async-gate.XXXXXX")
trap 'status=$?; rm -rf "$work"; mlf_case_cleanup "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

check_target() {
  source=$1
  name=$(basename "$source" .emlf)
  "$emlf" -i "$root" "$source" > "$work/$name.xmlf"
  "$emlf" --check "$work/$name.xmlf" > "$work/$name.checked"
}

positive=0
for source in "$root"/positive/*.emlf; do
  name=$(basename "$source" .emlf)
  mlf_case_selected "async-gate/positive/$name" || continue
  mlf_case_start "async-gate/positive/$name"
  check_target "$source"
  mlf_case_result pass 0
  positive=$((positive + 1))
done

negative=0
for source in "$root"/negative/*.emlf; do
  name=$(basename "$source" .emlf)
  mlf_case_selected "async-gate/negative/$name" || continue
  mlf_case_start "async-gate/negative/$name"
  status=0
  "$emlf" -i "$root" "$source" > "$work/$name.stdout" 2> "$work/$name.stderr" || status=$?
  if [ "$status" -ne 1 ] || [ -s "$work/$name.stdout" ]; then
    printf 'FAIL: invalid rejection for %s (exit %s)\n' "$name" "$status" >&2
    exit 1
  fi
  # The imported explicit-alias annotation currently fails closed in
  # elaboration. Preserve this known diagnostic gap rather than counting an
  # arbitrary parse/module error as evidence of type safety.
  case "$name" in
    io-generalize-alias) expected='^(Inference: cannot raise a protected type variable|Elaboration: unbound type variable )' ;;
    *) expected='^Inference:' ;;
  esac
  if ! grep -Eq "$expected" "$work/$name.stderr"; then
    cat "$work/$name.stderr" >&2
    printf 'FAIL: fixture rejected in the wrong phase: %s\n' "$name" >&2
    exit 1
  fi
  mlf_case_result pass "$status"
  negative=$((negative + 1))
done

# This intentionally bad interface is accepted: it demonstrates why the
# quantifier must scope the allocation action, not the allocated cell.
# It is NEVER executed.
if mlf_case_selected async-gate/compile-only/incorrect-quantifier; then
  mlf_case_start async-gate/compile-only/incorrect-quantifier
  check_target "$root/counterexample/incorrect-quantifier.emlf"
  mlf_case_result pass 0
fi

runtime=0
for source in "$root"/runtime/*.emlf; do
  name=$(basename "$source" .emlf)
  mlf_case_selected "async-gate/runtime/$name" || continue
  mlf_case_start "async-gate/runtime/$name"
  check_target "$source"
  "$emlf" -i "$root" --run "$source" > "$work/$name.actual"
  diff -u "$root/runtime/$name.expected" "$work/$name.actual"
  mlf_case_result pass 0
  runtime=$((runtime + 1))
done
if [ -z "${MLF_TEST_EXACT:-}" ]; then
  printf 'Typed completion gate: %s positive, %s negative, 1 bad-contract counterexample, %s interpreter probes passed.\n' "$positive" "$negative" "$runtime"
  printf 'This is a representation gate, not a live IO-completion implementation.\n'
fi
