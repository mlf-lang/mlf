"""Offline query-graph evidence checks. No compiler execution or payload expansion."""
from pathlib import Path
import base64
import hashlib
import json
import re
import sys

SHARED = Path(__file__).resolve().parents[2] / 'shared'
sys.path.insert(0, str(SHARED))
from query_generation import CACHE_DIRECTORY, Generation
from artifact_binary_reference import read_document  # noqa: E402
from artifact_binary_open import compact_group_owner  # noqa: E402
from artifact_binary_typed import pack, text  # noqa: E402

GRAPH = CACHE_DIRECTORY + '/'
HASH = re.compile(r'[0-9a-f]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def cold_codegen_evidence(build, compiler):
    report = json.loads((build/'codegen.json').read_text())
    require(type(report.get('format')) is int and report['format'] == 1 and
            report.get('compiler') == compiler, 'expected code generation producer')
    require(report.get('input_reused') is False and report.get('optimized_reused') is False,
            'both code generation queries must be fresh')
    for key in ('input_key', 'optimized_key'):
        require(isinstance(report.get(key), str) and HASH.fullmatch(report[key]),
                'invalid code generation key')
    cached = build/'codegen-cache'/'objects'/(report['optimized_key']+'.ll')
    def file_sha(path):
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                hasher.update(block)
        return hasher.hexdigest()
    emitted = file_sha(build/'unit.ll')
    require(cached.stat().st_size > 0 and file_sha(cached) == emitted,
            'cached LLVM must match emitted LLVM')
    return {'report': report, 'llvm_sha256': emitted}


def unpack(value):
    fields = []
    while value:
        count, separator, rest = value.partition(':')
        require(separator and count.isascii() and count.isdecimal() and
                len(count) <= 10 and str(int(count)) == count and int(count) <= len(rest),
                'canonical query graph configuration')
        size = int(count)
        fields.append(rest[:size])
        value = rest[size:]
    return fields


def snapshot(query, report, destination, *, reference=False):
    """Retain the compiler report and the candidate's CURRENT/index bytes before cleanup."""
    files = {}
    if not reference:
        graph = query / CACHE_DIRECTORY
        if not (graph / 'CURRENT').is_file():
            return
        for path in sorted(graph.rglob('*')):
            if path.is_file() and (path.name == 'CURRENT' or path.suffix == '.mlfqg'):
                files[path.relative_to(query).as_posix()] = base64.b64encode(path.read_bytes()).decode('ascii')
    evidence = {'format': 1, 'files_base64': files,
                'query_report_json': report.read_bytes().decode('utf-8') if report.is_file() else None}
    destination.write_text(json.dumps(evidence, indent=2) + '\n')


def document(raw):
    roots = read_document(raw, 6).values()
    require(len(roots) == 1, 'query graph single root')
    return roots[0]


def valid_hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def validate_inventory(inventory):
    require(isinstance(inventory, dict), 'query inventory mapping')
    for path, record in inventory.items():
        require(isinstance(path, str) and not path.startswith('/') and
                all(part not in ('', '.', '..') for part in path.split('/')),
                'query cache relative path')
        require(isinstance(record, dict) and type(record.get('bytes')) is int and
                record['bytes'] >= 0 and valid_hash(record.get('sha256')),
                'finite integral query inventory bytes and SHA')


def reported_groups(evidence, fresh, max_members, crate):
    require(isinstance(evidence, dict) and evidence.get('format') == 1,
            'query graph evidence missing; re-measure, do not reconstruct an old cohort')
    report_text = evidence.get('query_report_json')
    require(isinstance(report_text, str), 'actual query report text missing')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate query report JSON key')
            result[key] = value
        return result
    report = json.loads(report_text, object_pairs_hook=unique_pairs)
    require(isinstance(report, dict) and type(report.get('format')) is int and
            report['format'] == 1 and report.get('crate') == crate,
            'actual query report format/crate')
    require(type(report.get('inferred_groups')) is int and
            report['inferred_groups'] == fresh and type(report.get('reused_groups')) is int and
            report['reused_groups'] == 0, 'actual query report fresh/reused counts')
    groups = report.get('groups')
    require(isinstance(groups, list) and len(groups) == fresh and groups,
            'actual query report group count')
    ids, members_seen = set(), set()
    for group in groups:
        require(isinstance(group, dict) and group.get('cached') is False,
                'actual query report contains reused group')
        identity, members = group.get('id'), group.get('members')
        require(isinstance(identity, str) and identity and identity not in ids,
                'unique query report group identities')
        require(isinstance(members, list) and members and
                all(isinstance(m, str) and m for m in members) and
                len(set(members)) == len(members) and not members_seen.intersection(members),
                'nonempty disjoint query group members')
        ids.add(identity)
        members_seen.update(members)
    require(max(len(g['members']) for g in groups) == max_members, 'actual maximum group members')
    return [(g['id'], g['members'], g.get('query_key')) for g in groups]


def check_reference_inventory(inventory, evidence, fresh, max_members, crate):
    """Measure the baseline compiler's private files without interpreting its cache schema."""
    validate_inventory(inventory)
    return {'files': len(inventory), 'bytes': sum(item['bytes'] for item in inventory.values()),
            'groups': reported_groups(evidence, fresh, max_members, crate)}


def check_graph(inventory, evidence, fresh, max_members, crate, compiler_sha):
    """Validate committed index, exact InferScc identities and retained results.

    Payloads may deduplicate across nodes. Extra results from overwritten nodes
    remain valid publication output; they are counted, never treated as groups.
    """
    validate_inventory(inventory)
    groups = reported_groups(evidence, fresh, max_members, crate)
    current = GRAPH + 'CURRENT'
    generations = [p for p in inventory if p.endswith('.mlfqg')]
    results = [p for p in inventory if p.endswith('.mlfqr')]
    require(current in inventory and len(generations) == 1 and results,
            'one committed graph generation and nonempty results')
    require(set(inventory) <= {current, *generations, *results, '.lock'},
            'unexpected file in the measured query cache')
    for path in generations + results:
        suffix = '.mlfqg' if path in generations else '.mlfqr'
        directory = 'generations/' if suffix == '.mlfqg' else 'results/'
        name = path.removeprefix(GRAPH + directory).removesuffix(suffix)
        require(path == GRAPH + directory + name + suffix and valid_hash(name),
                'content-addressed query graph path')
        require(inventory[path]['bytes'] > 0 and inventory[path]['sha256'] == name,
                'content-addressed query graph SHA')
    files = evidence.get('files_base64')
    require(isinstance(files, dict) and set(files) == {current, *generations},
            'exact retained CURRENT and index evidence')
    raw = {}
    for path, encoded in files.items():
        require(isinstance(encoded, str), 'query graph base64 text')
        try:
            value = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError('query graph invalid base64') from error
        require(len(value) == inventory[path]['bytes'] and digest(value) == inventory[path]['sha256'],
                'retained query graph bytes match inventory')
        raw[path] = value
    generation = text(document(raw[current]))
    require(valid_hash(generation) and generations == [GRAPH + 'generations/' + generation + '.mlfqg'],
            'CURRENT selects retained generation')
    wire = Generation(raw[generations[0]], expected_hash=generation)
    config = unpack(text(wire.config))
    require(len(config) == 5 and config[0] == crate and config[1] == compiler_sha and
            valid_hash(compiler_sha) and config[2] and
            config[3] == 'open-fragment-checker-1/finish-receipt-1' and
            config[4] in ('source', 'lowered'), 'query graph crate/compiler configuration')
    for row in wire.nodes.values():
        payload = row['payload']
        if payload is not None:
            require(GRAPH + 'results/' + payload + '.mlfqr' in inventory,
                    'query graph missing retained payload')
    identities = set()
    for identity, members, sha in groups:
        require(identity == compact_group_owner(crate, members),
                'actual query group id matches crate and members')
        key = pack(['InferScc', pack(sorted(members))])
        require(key not in identities and key in wire.nodes and valid_hash(sha) and
                wire.nodes[key]['sha'] == sha and wire.nodes[key]['payload'] == sha,
                'exact InferScc identity and raw payload SHA')
        identities.add(key)
    # Canonical packed keys make this prefix exact, not a substring match.
    require({k for k in wire.nodes if k.startswith(pack(['InferScc']))} == identities,
            'exact InferScc inventory, no extra groups')
    paths = [current, *generations, *results]
    return {'files': len(paths), 'bytes': sum(inventory[p]['bytes'] for p in paths),
            'groups': groups}

