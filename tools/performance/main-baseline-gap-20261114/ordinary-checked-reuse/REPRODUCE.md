# Focused reproduction

Use a disposable checkout of `mlf-lang/mlf` at the exact baseline commit in
`SOURCE-PINS.json`, Linux x86_64, GHC 9.14.1 and GCC 14. Do not apply this patch
to a live working tree. The fixture's `DiagnosticBaseline.InferenceUnit` is the
original baseline module with only its module declaration renamed. It must not
be regenerated from the patched file.

The shell recipe below reproduces the test logic. It has been syntax-checked,
not executed as an additional run. It intentionally does not reproduce private
resource supervision, locks, runtime-byte backups, or the full evidence archive.
It is not a performance recipe. The original focused run used 4 GiB address-space
limits, 180 seconds per GHC command / 210 seconds aggregate compilation,
15 seconds per fixture / 30 seconds aggregate, and 300 seconds for the phase.
Use an appropriately isolated supervisor if those same execution bounds matter.

Set `BUNDLE` and `SRC` to the extracted bundle and disposable checkout. `OUT`
must be a new directory. No default `build.py` or native stage is involved.

```bash
set -euo pipefail
BUNDLE=$(cd path-to-this-bundle && pwd)
SRC=$(cd path-to-disposable-mlf-checkout && pwd)
GHC=ghc
CC=gcc
OUT="$PWD/ordinary-checked-reuse-reproduction"
test ! -e "$OUT"
test "$(git -C "$SRC" rev-parse HEAD)" = fc300bc9fdc389b585cbef0630fc8915d53e89c5
git -C "$SRC" diff --quiet
git -C "$SRC" diff --cached --quiet
# Begin with a fresh checkout; this extra-file check alone does not detect ignored artifacts.
test -z "$(git -C "$SRC" ls-files --others --exclude-standard)"
git -C "$SRC" apply --check "$BUNDLE/candidate.patch"
git -C "$SRC" apply "$BUNDLE/candidate.patch"
mkdir -p "$OUT/c" "$OUT/bin" "$OUT/tmp"
export LC_ALL=C LANG=C TZ=UTC TMPDIR="$OUT/tmp"
unset GHCRTS GHC_ENVIRONMENT
"$CC" -O2 -std=c11 -I"$SRC/runtime" -c "$SRC/host/ghc/cbits/host.c" -o "$OUT/c/host.o"
"$CC" -O2 -std=c11 -I"$SRC/runtime" -c "$SRC/runtime/mlf_process_supervisor.c" -o "$OUT/c/supervisor.o"
roots=(-i "-i$BUNDLE/fixtures")
for root in libraries/mlf-crates libraries/mlf-foundation libraries/mlf-frontend libraries/mlf-inference libraries/mlf-language-core libraries/mlf-xmlf host/ghc; do
  roots+=("-i$SRC/$root")
done
common=(--make -j1 -fforce-recomp -XHaskell2010 -fpedantic-bottoms -fno-state-hack -Werror=incomplete-patterns -Werror=incomplete-uni-patterns -package-env - -clear-package-db -global-package-db -no-user-package-db -hide-all-packages -rtsopts=ignoreAll)
packages=(-package base -package array -package bytestring -package text -package containers -package directory)
for opt in 0 2; do
  lane="$OUT/o$opt"
  mkdir -p "$lane/objects" "$lane/stubs" "$lane/work"
  "$GHC" "${common[@]}" "-O$opt" "${roots[@]}" -odir "$lane/objects" -hidir "$lane/objects" -stubdir "$lane/stubs" "${packages[@]}" "$BUNDLE/fixtures/Main.hs" "$OUT/c/host.o" "$OUT/c/supervisor.o" -o "$OUT/bin/semantic-o$opt" >"$lane/build.stdout" 2>"$lane/build.stderr"
  (cd "$lane/work"; "$OUT/bin/semantic-o$opt") >"$lane/stdout" 2>"$lane/stderr"
  cmp "$BUNDLE/expected.stdout" "$lane/stdout"
  test ! -s "$lane/stderr"
  python3 - "$BUNDLE/TEST-CONTRACT.json" "$lane/work" <<'PYTEST'
import json, pathlib, sys
contract = json.loads(pathlib.Path(sys.argv[1]).read_text())
work = pathlib.Path(sys.argv[2]); expected = set()
for case in contract['cases']:
    name = case['label']; kind = case['expected_outcome']
    result = name + '.result'; expected.add(result)
    assert (work / result).read_bytes() == b'PASS\n'
    values = []
    for side in ('A', 'C'):
        key = name + '-' + side + '.outcome'; expected.add(key)
        values.append((work / key).read_bytes())
    assert values[0] == values[1]
    if kind == 'Right':
        assert values[0] == b'Right\n'
        for suffix in ('.raw', '.typed'):
            keys = [name + '-' + s + suffix for s in ('A', 'C')]
            expected.update(keys)
            a, c = [(work / key).read_bytes() for key in keys]
            assert a and a == c
    elif kind == 'Left':
        assert values[0].startswith(b'Left ') and values[0].endswith(b'\n')
        if 'exact_outcome_utf8' in case:
            assert values[0] == case['exact_outcome_utf8'].encode()
    else:
        assert kind == 'Probe' and values[0] == contract['probe_expected_utf8'].encode()
assert len(expected) == contract['successful_work_files'] == 63
assert {p.name for p in work.iterdir()} == expected
assert all(p.is_file() and not p.is_symlink() for p in work.iterdir())
PYTEST
done
```

The fixture itself enforces the ordered interface and audit checks, not just the
sidecar test above. The loop is fail-fast: any compile, fixture or evidence error
stops before the next lane. Keep all partial output on failure; do not substitute
new expected values. A portable rebuild need not reproduce the archived ELF
hashes because toolchain installation and link paths can affect binary identity.
For a production build, use the real `host/ghc/app/emlf/Main.hs` and ordered roots
from the baseline `shared-sources.json`, fresh objects per producer, and O2 with
the same demand/package flags. Do not use the renamed fixture module as a
production code-size or workload proxy.
