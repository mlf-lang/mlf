"""Read-only r16 postprocessor; original r13 profile.py and coarse labels stay fixed.

This tool does not run a compiler, control, benchmark, cleanup, or stage admission.
Caller-supplied hashes must come from separately authenticated stage evidence.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import stat
from collections import defaultdict

HERE = Path(__file__).resolve().parent
COARSE_READER_SHA256 = 'f31b0d9569dc7328198e92e5e439183f9cd1f5a4365407041c7739a095cb0c96'
BASE = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
PREFIX = 'libraries/mlf-inference/Bootstrap/'
EXPECTED = {
    'prepare': ('SOLVER_PREPARE', 'Bootstrap.Graph.Solver', PREFIX + 'Graph/Solver.hs'),
    'steps': ('SOLVER_STEPS', 'Bootstrap.Constraint', PREFIX + 'Constraint.hs'),
    'expansion': ('SOLVER_EXPANSION', 'Bootstrap.Graph', PREFIX + 'Graph.hs'),
    'transaction-distinct': ('SOLVER_TRANSACTION', 'Bootstrap.Graph.Solver', PREFIX + 'Graph/Solver.hs'),
    'transaction-prepared': ('SOLVER_TRANSACTION', 'Bootstrap.Graph.Solver', PREFIX + 'Graph/Solver.hs'),
    'local-unify': ('SOLVER_LOCAL_UNIFY', 'Bootstrap.Graph', PREFIX + 'Graph.hs'),
    'finish-audit': ('SOLVER_FINISH_AUDIT', 'Bootstrap.Graph.Solver', PREFIX + 'Graph/Solver.hs'),
}
FINE_LABELS = frozenset(x[0] for x in EXPECTED.values())


class FineProfileError(ValueError):
    pass


def require(okay, message):
    if not okay:
        raise FineProfileError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path):
    path = Path(path)
    require('..' not in path.parts, 'parent traversal forbidden')
    path = path.absolute()
    for item in (path, *path.parents):
        require(not item.is_symlink(), 'symlink input forbidden')
    require(stat.S_ISREG(path.lstat().st_mode), 'regular input required')
    return path


def read_verified(path, expected, maximum=64 * 1024 * 1024):
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'invalid expected SHA256')
    path = regular(path)
    require(path.stat().st_size <= maximum, 'input exceeds size limit')
    raw = path.read_bytes()
    require(len(raw) <= maximum and digest(raw) == expected, 'input SHA256 mismatch')
    return raw


def load_coarse_reader():
    path = HERE / 'profile.py'
    read_verified(path, COARSE_READER_SHA256)
    spec = importlib.util.spec_from_file_location('_r16_original_coarse_reader', path)
    require(spec is not None and spec.loader is not None, 'coarse reader unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(not (FINE_LABELS & module.LABELS), 'fine labels contaminate original coarse labels')
    return module


COARSE = load_coarse_reader()


def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=COARSE.unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(FineProfileError('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise FineProfileError('invalid JSON: ' + str(error)) from error


def load_fine_spec():
    spec = strict_json(regular(HERE / 'insertion-map.json').read_bytes())
    require(spec.get('source_commit') == BASE, 'source revision mismatch')
    fine = spec.get('r16_fine')
    require(type(fine) is dict and fine.get('schema') == 'solver-r16-fine-sites-v1', 'fine spec schema')
    require(fine.get('coarse_profile_sha256') == COARSE_READER_SHA256, 'coarse reader pin mismatch')
    require(fine.get('labels') == sorted(FINE_LABELS), 'exact fine label inventory required')
    sites = fine.get('sites')
    require(type(sites) is list and len(sites) == 7, 'seven fine sites required')
    require({s.get('site_id') for s in sites} == set(EXPECTED), 'fine site IDs differ')
    for site in sites:
        require((site.get('label'), site.get('module'), site.get('path')) == EXPECTED[site['site_id']],
                'fine site identity differs')
        extent = site.get('fine_rhs_span', {})
        for key in ('start', 'end_exclusive'):
            pair = extent.get(key)
            require(type(pair) is list and len(pair) == 2 and
                    all(type(n) is int and n > 0 for n in pair), 'fine source position invalid')
        require(extent['start'] <= extent['end_exclusive'], 'fine source extent reversed')
    return spec


def source_extent(location, absolute_source):
    prefix = str(absolute_source) + ':'
    require(location.startswith(prefix), 'fine cost centre source path differs')
    tail = location[len(prefix):]
    one = re.fullmatch(r'(\d+):(\d+)(?:-(\d+))?', tail)
    if one:
        line, start, end = (int(one[1]), int(one[2]), int(one[3] or one[2]))
        require(line > 0 and 0 < start <= end, 'invalid fine single-line extent')
        return line, line
    multiple = re.fullmatch(r'\((\d+),(\d+)\)-\((\d+),(\d+)\)', tail)
    require(multiple is not None, 'unsupported fine source location format')
    a, b, c, d = map(int, multiple.groups())
    require(min(a, b, c, d) > 0 and (a, b) <= (c, d), 'invalid fine multi-line extent')
    return a, c


def identify_sites(report, mirror_root, spec):
    root = Path(mirror_root).absolute()
    sites = spec['r16_fine']['sites']
    by_id = {}
    for cc in report['cost_centres']:
        label = cc['label']
        if label not in FINE_LABELS:
            require(not label.startswith('SOLVER_'), 'unknown SOLVER_ label')
            continue
        require(cc['is_caf'] is False, 'fine cost centre may not be a CAF')
        matches = []
        for site in sites:
            if (label, cc['module']) != (site['label'], site['module']):
                continue
            prefix = str(root / site['path']) + ':'
            if not cc['src_loc'].startswith(prefix):
                continue
            first, last = source_extent(cc['src_loc'], root / site['path'])
            bounds = site['fine_rhs_span']
            if bounds['start'][0] <= first <= last <= bounds['end_exclusive'][0]:
                matches.append(site['site_id'])
        require(len(matches) == 1, 'fine cost centre does not uniquely match a reviewed site')
        by_id[cc['id']] = matches[0]
    require(set(by_id.values()) == set(EXPECTED), 'not all seven fine sites are declared in raw profile')
    return by_id


def partition(raw, mirror_root, spec=None):
    """Strict raw parse plus disjoint coarse x nearest-fine allocation matrix.

    No caller-supplied stack summary is trusted. All rows come from the original
    parser. Raw ticks are retained as counts, not interpreted as ordinary CPU.
    """
    if spec is None:
        spec = load_fine_spec()
    # Parsing raw bytes retains original duplicate-key and schema rejection.
    coarse = COARSE.parse_profile(raw)
    report = strict_json(raw) if isinstance(raw, (str, bytes)) else raw
    sites = identify_sites(report, mirror_root, spec)
    matrix = defaultdict(lambda: {'alloc': 0, 'ticks': 0, 'nodes': 0})
    site_matrix = defaultdict(lambda: {'alloc': 0, 'ticks': 0, 'nodes': 0})
    observed = set()
    for row in coarse['stacks']:
        stack = row['stack']
        boundary = max((i for i, cc in enumerate(stack) if cc['label'] in COARSE.LABELS), default=-1)
        nearest = next((cc for cc in reversed(stack[boundary + 1:]) if cc['id'] in sites), None)
        label = nearest['label'] if nearest is not None else 'UNLABELLED'
        site = sites[nearest['id']] if nearest is not None else 'UNLABELLED'
        if nearest is not None:
            observed.add(site)
        # An original semantic label appearing below a fine label starts a new
        # coarse context. The older fine label is deliberately not inherited.
        key = (row['bucket'], label)
        site_key = (row['bucket'], site)
        for target, item in ((matrix, key), (site_matrix, site_key)):
            target[item]['alloc'] += row['self_alloc']
            target[item]['ticks'] += row['self_ticks']
            target[item]['nodes'] += 1
    for bucket, expected in coarse['partition'].items():
        actual = {field: sum(v[field] for (owner, _), v in matrix.items() if owner == bucket)
                  for field in ('alloc', 'ticks', 'nodes')}
        require(actual == expected, 'coarse row conservation failed')
    require(sum(v['alloc'] for v in matrix.values()) == coarse['total_alloc'], 'global allocation conservation failed')
    require(sum(v['ticks'] for v in matrix.values()) == coarse['total_ticks'], 'global tick conservation failed')
    require(sum(v['alloc'] for v in site_matrix.values()) == coarse['total_alloc'], 'site allocation conservation failed')
    rows = [dict(coarse=owner, fine=label, **values) for (owner, label), values in sorted(matrix.items())]
    per_site = [dict(coarse=owner, site=site, **values) for (owner, site), values in sorted(site_matrix.items())]
    result = dict(schema='solver-r16-fine-partition-v1',
                  interpretation='profiled source-demand allocation; not ordinary exclusive CPU, heap or savings',
                  unit=coarse['unit'], total_alloc=coarse['total_alloc'], total_ticks=coarse['total_ticks'],
                  coarse_partition=coarse['partition'], matrix=rows, site_matrix=per_site,
                  defined_sites=sorted(set(sites.values())), observed_sites=sorted(observed),
                  unobserved_sites=sorted(set(EXPECTED) - observed),
                  all_coarse_rows_conserved=True, global_totals_conserved=True,
                  actual_execution_established_by_this_tool=False, byte_control_reexecuted=False,
                  resume_authorized=False)
    return result, coarse


def match_qualified_summary(coarse, supplied, toolchain_sha256):
    require(type(supplied) is dict and supplied.get('unit') == 'bytes', 'qualified original summary required')
    require('unit_evidence' in supplied, 'unit evidence missing')
    expected = COARSE.qualify_units(coarse, supplied['unit_evidence'], toolchain_sha256=toolchain_sha256)
    # Exact JSON equality alone permits True == 1. Compare canonical JSON bytes
    # as well as structure so tampered boolean/number representations fail.
    dump = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(dump(supplied) == dump(expected), 'original qualified summary differs from raw parse')
    return expected['unit_evidence']


def verify_mirror_snapshot(root, expected_manifest_sha, spec):
    root = Path(root).absolute()
    raw = read_verified(root / 'mirror-manifest.json', expected_manifest_sha)
    manifest = strict_json(raw)
    require(manifest.get('schema') == 'sparse-scc-mirror-v1' and manifest.get('source_commit') == BASE,
            'mirror manifest identity')
    require(manifest.get('mirror') == str(root), 'mirror manifest root differs')
    files = spec['r16_fine']['files']
    require(set(manifest.get('files', {})) == set(files), 'mirror manifest source inventory differs')
    expected_disk = set(files) | {'mirror-manifest.json', 'mirror.patch'}
    expected_dirs = {str(p) for rel in expected_disk for p in Path(rel).parents if str(p) != '.'}
    seen, seen_dirs = set(), set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'mirror symlink forbidden')
        if path.is_dir():
            seen_dirs.add(str(path.relative_to(root)))
            continue
        regular(path)
        seen.add(str(path.relative_to(root)))
    require(seen == expected_disk and seen_dirs == expected_dirs, 'mirror disk inventory differs')
    for rel, record in files.items():
        require(manifest['files'][rel]['original_sha256'] == record['source_sha256'] and
                manifest['files'][rel]['annotated_sha256'] == record['fine_sha256'], 'mirror file pin differs')
        read_verified(root / rel, record['fine_sha256'])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--profile-sha256', required=True)
    parser.add_argument('--coarse-summary', required=True, type=Path)
    parser.add_argument('--coarse-summary-sha256', required=True)
    parser.add_argument('--mirror-root', required=True, type=Path)
    parser.add_argument('--mirror-manifest-sha256', required=True)
    parser.add_argument('--toolchain-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    spec = load_fine_spec()
    verify_mirror_snapshot(args.mirror_root, args.mirror_manifest_sha256, spec)
    raw = read_verified(args.profile, args.profile_sha256)
    supplied = strict_json(read_verified(args.coarse_summary, args.coarse_summary_sha256))
    result, coarse = partition(raw, args.mirror_root, spec)
    evidence = match_qualified_summary(coarse, supplied, args.toolchain_sha256)
    require(any(row['coarse'] == 'SOLVE' and row['fine'] != 'UNLABELLED' for row in result['matrix']),
            'no observed fine subdivision of SOLVE')
    result.update(unit='bytes', unit_evidence=evidence,
                  input_pins={'raw_profile': args.profile_sha256, 'coarse_summary': args.coarse_summary_sha256,
                              'mirror_manifest': args.mirror_manifest_sha256,
                              'insertion_map': digest((HERE / 'insertion-map.json').read_bytes()),
                              'coarse_reader': COARSE_READER_SHA256,
                              'fine_reader': digest(Path(__file__).read_bytes())})
    output = args.output.absolute()
    require('..' not in args.output.parts and not output.is_symlink(), 'unsafe output')
    for parent in output.parents:
        require(not parent.is_symlink(), 'output symlink parent forbidden')
    require(output.parent.is_dir(), 'output parent must exist')
    # Exclusive creation prevents overwriting a raw profile, manifest or receipt.
    with output.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'written': str(output), 'total_alloc': result['total_alloc'],
                      'cells': len(result['matrix']), 'actual_execution_established_by_this_tool': False}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit('fine-profile: ' + str(error))
