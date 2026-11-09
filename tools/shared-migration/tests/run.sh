#!/usr/bin/env bash
set -euo pipefail
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${GHC:=ghc}"
: "${MIGRATOR:=/tmp/mlf-migrate-shared}"
: "${OUT:=$(mktemp -d /tmp/mlf-shared-codemod-tests.XXXXXX)}"
mkdir -p "$OUT/generated" "$OUT/report" "$OUT/objects"
: > "$OUT/primitives.txt"
printf '%s\t%s\t%s\n' "$here/DemandScope.emlf" "$OUT/generated/DemandScope.hs" DemandScope "$here/PrimitiveShadow.emlf" "$OUT/generated/PrimitiveShadow.hs" PrimitiveShadow "$here/Comments.emlf" "$OUT/generated/Comments.hs" Comments "$here/NegativeDouble.emlf" "$OUT/generated/NegativeDouble.hs" NegativeDouble "$here/legacy/Bootstrap/Std.emlf" "$OUT/generated/Bootstrap/Std.hs" Bootstrap.Std > "$OUT/manifest.tsv"
"$MIGRATOR" "$OUT/manifest.tsv" "$OUT/primitives.txt" "$OUT/report"
python3 - "$OUT/generated/Comments.hs" <<'PYTEST'
import pathlib,sys
source=pathlib.Path(sys.argv[1]).read_text()
for marker in ["leading-comment-must-survive","outer-block-must-survive","nested-block-must-survive","gap-trailer-must-survive","final-comment-must-survive"]:
    assert source.count(marker)==1, "Lost or duplicated source comment: "+marker
assert source.count("-- still only data")==1, "String content was misclassified as a comment"
print("PASS lexical comment preservation")
PYTEST
"$GHC" -XHaskell2010 -O0 -fforce-recomp -i"$here/support" -i"$OUT/generated" -outputdir "$OUT/objects" -o "$OUT/check" "$here/Runner.hs"
timeout 20 "$OUT/check" "$@"
for fixture in RejectedLambda RejectedUnreachable RejectedOpenRec RejectedUnsignedRec; do
  printf '%s\t%s\t%s\n' "$here/$fixture.emlf" "$OUT/generated/$fixture.hs" "$fixture" > "$OUT/rejected.tsv"
  if "$MIGRATOR" "$OUT/rejected.tsv" "$OUT/primitives.txt" "$OUT/rejected-report" >"$OUT/$fixture.log" 2>&1; then
    echo "FAIL accepted negative fixture $fixture" >&2
    exit 1
  fi
  grep -Eq 'non-exhaustive|unreachable|closed signature' "$OUT/$fixture.log"
  echo "PASS rejected $fixture"
done
printf 'Fixture output: %s\n' "$OUT"
