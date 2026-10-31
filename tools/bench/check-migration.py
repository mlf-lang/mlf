#!/usr/bin/env python3
"""Static provenance checks only; this does not compile or run benchmarks."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
manifest = json.loads((ROOT / 'benchmarks/manifest.json').read_text())
expected = {
    'binary-trees': (16, [0, 7, 10]),
    'pidigits': (10000, [1, 10, 27, 30]),
    'n-body': (2000000, [0, 1, 1000]),
    'fannkuch-redux': (10, [1, 2, 5, 7]),
    'spectral-norm': (2000, [1, 2, 3, 100]),
    'fasta': (2000000, [0, 1, 29, 30, 31, 1000, 12288, 12289]),
    'mandelbrot': (4096, [1, 2, 7, 8, 9, 200]),
    'reverse-complement': (10000000, [1, 7, 31, 1000, 12288, 12289]),
    'k-nucleotide': (1000000, [1, 7, 31, 1000]),
    'regex-redux': (1000000, [1, 7, 31, 1000]),
}
rows = manifest['workloads']
assert [w['name'] for w in rows] == list(expected), 'workload inventory/order changed'
for path, digest in manifest['pinned_sha256'].items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
for w in rows:
    assert (w['default_input'], w['check_inputs']) == expected[w['name']], w['name']
    assert w['flags']['c'] == ['-O3'], w['name']
    assert w['flags']['mlf'] == ['-O2', '-Wno-override-module'], w['name']
    for p in [w['sources']['c'], w['sources']['mlf'], w['fixture'], *w.get('mlf_dependencies', [])]:
        assert (ROOT / p).is_file(), p
    for p in [w['sources']['mlf'], *w.get('mlf_dependencies', [])]:
        assert p in manifest['pinned_sha256'], 'unbound migrated source: ' + p
regex = rows[-1]
assert regex['pkg_config_versions'] == {'libpcre2-8': '10.49'}
assert regex['sources']['c'] == 'benchmarks/regex-redux/c/main.c'
assert regex['mlf_include_dirs'] == ['libraries/mlf-foundation']
package = json.loads((ROOT / 'tools/bench/mlf-package.json').read_text())
for name in ['bench', 'build-backend', 'build-linker']:
    target = package['executables'][name]
    assert target['link'] == 'source' and target['profile'] == 'compiler'
    assert (ROOT / 'tools/bench' / target['main']).is_file()
entry = (ROOT / 'tools/bench/Main.emlf').read_text()
for path in re.findall(r'libraries/[A-Za-z0-9_./-]+\.(?:hs|emlf)', entry):
    assert (ROOT / path).is_file(), 'missing runner integrity input: ' + path
def check_mode_contract(source):
    # Source-shape guard only: native CLI refusal tests remain an execution gate.
    options = source.split('checkOnly limits selected <- case options of', 1)[1].split(
        '   O.require (B.validateLimits limits)', 1)[0]
    # Empty, singleton and two-or-more lists exhaust this options case. A final
    # wildcard is unreachable and is correctly rejected by the real compiler.
    branches = re.findall(r'^    (.+?) ->', options, re.MULTILINE)
    assert branches == ['[]', '(:) option []',
                        '(:) compileLimit ((:) runtimeLimit names)'], (
        'options case must have exactly its three exhaustive list branches')
    for fragment in [
        '(:) option [] -> if eqString option "--check-only"',
        '"invalid workload selection"',
        '"check-only requires the complete canonical workload inventory"',
        'if checkOnly then checkWorkload c else workload c',
        'if checkOnly then [] else B.performanceChecks rows limits',
        'if checkOnly then "correctness-passed"',
        'J.num (if checkOnly then 0 else n)',
        'J.set "performance_checked" (J.Boolean false)',
    ]:
        assert fragment in source, 'check-only source contract changed: ' + fragment

def check_optional_maps(source):
    # Only absent optional package maps get an empty object. Required maps and
    # present malformed values remain strict in the actual Json API.
    for field, count in [('pkg_config', 3), ('pkg_config_versions', 1),
                         ('pkg_config_headers', 1)]:
        assert source.count('J.getObject "' + field + '" work') == count, field
        assert 'J.get "' + field + '" work' not in source, field
    for field in ['sources', 'flags']:
        assert 'J.get "' + field + '" work' in source, field
        assert 'J.getObject "' + field + '" work' not in source, field

check_optional_maps(entry)
for field in ['pkg_config', 'pkg_config_versions', 'pkg_config_headers']:
    mutated = entry.replace('J.getObject "' + field + '" work',
                            'J.get "' + field + '" work', 1)
    assert mutated != entry
    try:
        check_optional_maps(mutated)
    except AssertionError:
        pass
    else:
        raise AssertionError('optional-map regression unexpectedly accepted: ' + field)
check_mode_contract(entry)
# Negative mutation controls establish that the static guard rejects these
# regressions, not that a compiler has executed or proved the CLI semantics.
for old, new in [('(:) option []', '(:) option rest'),
                 ('J.Boolean false', 'J.Boolean true'),
                 ('then "correctness-passed"', 'then "passed"'),
                 ('   O.require (B.validateLimits limits)',
                  '    _ -> O.fatal "redundant fallback"\n   O.require (B.validateLimits limits)')]:
    mutated = entry.replace(old, new)
    assert mutated != entry
    try:
        check_mode_contract(mutated)
    except AssertionError:
        pass
    else:
        raise AssertionError('static negative mutation unexpectedly accepted: ' + old)
print('PASS: static ten-workload inventory, pins, flags, fixtures, dependencies and entry paths')
print('Not a compiler, native execution, performance or check-only CLI qualification.')
