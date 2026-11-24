"""Offline query-graph evidence checks. No compiler execution or payload expansion."""
from pathlib import Path
import base64
import hashlib
import json
import re
import sys

SHARED = Path(__file__).resolve().parents[2] / 'shared'
sys.path.insert(0, str(SHARED))
from query_generation import Generation, cache_directory
from artifact_binary_reference import read_document  # noqa: E402
from artifact_binary_open import compact_group_owner, compact_group_owner_v2  # noqa: E402
from test_query_index import read_index  # noqa: E402

GRAPH = 'query-graph-v1/'
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


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


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


def snapshot(query, report, destination):
    """Retain actual CURRENT/index bytes before cleanup, outside timed work.

    JSON wrapping also keeps these inputs in the CI receipts-only upload.
    Result bytes are already hashed by the ordinary complete file inventory.
    """
    if not any((query / g / 'CURRENT').is_file() for g in (GRAPH, 'query-graph-v2', 'query-graph-v3')):
        return
    graph = cache_directory(query)
    files = {}
    for path in sorted(graph.rglob('*')):
        if path.is_file() and (path.name == 'CURRENT' or path.suffix == '.mlfqg'):
            files[path.relative_to(query).as_posix()] = base64.b64encode(path.read_bytes()).decode('ascii')
    evidence = {'format': 1, 'files_base64': files,
                'query_report_json': report.read_bytes().decode('utf-8') if report.is_file() else None}
    destination.write_text(json.dumps(evidence, indent=2) + '\n')


def text(value):
    require(value[0] == 'text', 'query graph expected text')
    return value[1]


def node(value, tag, arity=None):
    require(value[0] == 'node' and value[1] == tag, 'query graph expected tag ' + str(tag))
    children = value[2]
    require(arity is None or len(children) == arity, 'query graph constructor arity')
    return children


def document(raw):
    roots = read_document(raw, 6).values()
    require(len(roots) == 1, 'query graph single root')
    return roots[0]


def valid_hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def check_graph(inventory, evidence, fresh, max_members, crate, compiler_sha):
    """Validate committed index, exact InferScc identities and retained results.

    Payloads may deduplicate across nodes. Extra results from overwritten nodes
    remain valid publication output; they are counted, never treated as groups.
    """
    require(isinstance(evidence, dict) and evidence.get('format') == 1,
            'query graph evidence missing; re-measure, do not reconstruct an old cohort')
    for path, record in inventory.items():
        require(isinstance(path, str) and not path.startswith('/') and
                all(part not in ('', '.', '..') for part in path.split('/')),
                'query cache relative path')
        require(isinstance(record, dict) and type(record.get('bytes')) is int and
                record['bytes'] >= 0 and valid_hash(record.get('sha256')),
                'finite integral query inventory bytes and SHA')
    require(not any(p.endswith('.mlfq') for p in inventory), 'mixed legacy and graph query storage')
    graph = next((f'query-graph-v{v}/' for v in (3, 2, 1)
                  if f'query-graph-v{v}/CURRENT' in inventory), GRAPH)
    current = graph + 'CURRENT'
    generations = [p for p in inventory if p.endswith('.mlfqg')]
    results = [p for p in inventory if p.endswith('.mlfqr')]
    require(current in inventory and len(generations) == 1 and results,
            'one committed graph generation and nonempty results')
    require(not any('/staging/' in p for p in inventory), 'unpublished query staging files')
    for path in generations + results:
        suffix = '.mlfqg' if path in generations else '.mlfqr'
        directory = 'generations/' if suffix == '.mlfqg' else 'results/'
        name = path.removeprefix(graph + directory).removesuffix(suffix)
        require(path == graph + directory + name + suffix and valid_hash(name),
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
    require(valid_hash(generation) and generations == [graph + 'generations/' + generation + '.mlfqg'],
            'CURRENT selects retained generation')
    wire = Generation(raw[generations[0]], expected_hash=generation)
    expected_directory = 1 if wire.dictionary_format else wire.version
    require(graph == 'query-graph-v' + str(expected_directory) + '/', 'generation directory version')
    config = unpack(text(wire.config))
    require(len(config) == 5 and config[0] == crate and config[1] == compiler_sha and
            valid_hash(compiler_sha) and config[2] and config[3] in
            ('open-fragment-checker-1', 'open-fragment-checker-1/finish-receipt-1') and
            config[4] in ('source', 'lowered'), 'query graph crate/compiler configuration')
    nodes = {}
    for key, row in wire.nodes.items():
        payload = row['payload']
        if payload is not None:
            require(graph + 'results/' + payload + '.mlfqr' in inventory,
                    'query graph missing retained payload')
        nodes[key] = (row['sha'], row['reads'], payload)
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
    ids, identities, members_seen = set(), set(), set()
    for group in groups:
        require(isinstance(group, dict) and group.get('cached') is False,
                'actual query report contains reused group')
        identity, members, sha = group.get('id'), group.get('members'), group.get('query_key')
        require(isinstance(identity, str) and identity and identity not in ids,
                'unique query report group identities')
        require(isinstance(members, list) and members and
                all(isinstance(m, str) and m for m in members) and
                len(set(members)) == len(members) and not members_seen.intersection(members),
                'nonempty disjoint query group members')
        ids.add(identity)
        members_seen.update(members)
        encoded = lambda value: ''.join(str(ord(c)) + '_' for c in value)
        framed_owner = pack(['MLF-OPEN-GROUP-1', crate, pack(sorted(members))])
        legacy_owner = 'Query_' + encoded(crate) + 'z_' + encoded(min(members))
        require(identity in (framed_owner, legacy_owner, compact_group_owner_v2(crate, members),
                             compact_group_owner(crate, members)),
                'actual query group id matches crate and members')
        key = pack(['InferScc', pack(sorted(members))])
        require(key not in identities and key in nodes and valid_hash(sha) and
                nodes[key][0] == sha and nodes[key][2] == sha,
                'exact InferScc identity and raw payload SHA')
        identities.add(key)
    # Canonical packed keys make this prefix exact, not a substring match.
    require({k for k in nodes if k.startswith(pack(['InferScc']))} == identities,
            'exact InferScc inventory, no extra groups')
    require(max(len(g['members']) for g in groups) == max_members, 'actual maximum group members')
    paths = [current, *generations, *results]
    return {'files': len(paths), 'bytes': sum(inventory[p]['bytes'] for p in paths),
            'groups': [(g['id'], g['members'], g['query_key']) for g in groups]}

