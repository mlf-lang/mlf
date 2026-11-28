#!/usr/bin/env python3
"""Static provenance checks only; this does not compile or run benchmarks."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


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
require([w['name'] for w in rows] == list(expected), 'workload inventory/order changed')
for path, digest in manifest['pinned_sha256'].items():
    require(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path)
for w in rows:
    require((w['default_input'], w['check_inputs']) == expected[w['name']], w['name'])
    require(w['flags']['c'] == ['-O3'], w['name'])
    require(w['flags']['mlf'] == ['-O2', '-Wno-override-module'], w['name'])
    for p in [w['sources']['c'], w['sources']['mlf'], w['fixture'], *w.get('mlf_dependencies', [])]:
        require((ROOT / p).is_file(), p)
    for p in [w['sources']['mlf'], *w.get('mlf_dependencies', [])]:
        require(p in manifest['pinned_sha256'], 'unbound migrated source: ' + p)
regex = rows[-1]
require(regex['pkg_config_versions'] == {'libpcre2-8': '10.49'}, 'PCRE2 version pin changed')
require(regex['sources']['c'] == 'benchmarks/regex-redux/c/main.c', 'PCRE2 C implementation changed')
require(regex['mlf_include_dirs'] == ['libraries/mlf-foundation'], 'regex dependency roots changed')
package = json.loads((ROOT / 'tools/bench/mlf-package.json').read_text())
for name in ['bench', 'build-backend', 'build-linker']:
    target = package['executables'][name]
    require(target['link'] == 'source' and target['profile'] == 'compiler', name + ': source compiler profile required')
    require((ROOT / 'tools/bench' / target['main']).is_file(), name + ': missing entry point')
# CLI modes, optional dependency maps and report claims are exercised through
# Package.Benchmark by Tests.BenchmarkSuite. Their source spelling is not a
# provenance boundary, and this cheap gate does not inspect runner code.
print('PASS: static ten-workload inventory, pins, flags, fixtures and dependencies')
print('Native benchmark contract cases qualify CLI modes and report semantics.')
print('Not a compiler, native execution or performance qualification.')
