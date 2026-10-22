#!/bin/sh
# Focused representation gate. No compiler bootstrap or package dependencies.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
emlf=${EMLF:-emlf}
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-async-gate.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

check_target() {
  source=$1
  name=$(basename "$source" .emlf)
  "$emlf" -i "$root" "$source" > "$work/$name.xmlf"
  "$emlf" --check "$work/$name.xmlf" > "$work/$name.checked"
}

positive=0
for source in "$root"/positive/*.emlf; do
  check_target "$source"
  positive=$((positive + 1))
done

negative=0
for source in "$root"/negative/*.emlf; do
  name=$(basename "$source" .emlf)
  if "$emlf" -i "$root" "$source" > "$work/$name.stdout" 2> "$work/$name.stderr"; then
    printf 'FAIL: ill-typed fixture accepted: %s\n' "$name" >&2
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
  negative=$((negative + 1))
done

# This intentionally bad interface is accepted: it demonstrates why the
# quantifier must scope the allocation action, not the allocated cell.
# It is NEVER executed.
check_target "$root/counterexample/incorrect-quantifier.emlf"

runtime=0
for source in "$root"/runtime/*.emlf; do
  name=$(basename "$source" .emlf)
  check_target "$source"
  "$emlf" -i "$root" --run "$source" > "$work/$name.actual"
  diff -u "$root/runtime/$name.expected" "$work/$name.actual"
  runtime=$((runtime + 1))
done
printf 'Typed completion gate: %s positive, %s negative, 1 bad-contract counterexample, %s interpreter probes passed.\n' "$positive" "$negative" "$runtime"
printf 'This is a representation gate, not a live IO-completion implementation.\n'
