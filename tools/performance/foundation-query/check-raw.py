#!/usr/bin/env python3
"""Compare two PR-29-family ABBA sequences made from the same absolute input paths."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
import run_context_controls as wire

reader, typed, _ = wire.binary_helpers()


def require(value, message):
    if not value:
        raise ValueError(message)


def read_group(cache, key, contexts, compiler, baseline_fields=None):
    doc = reader.read_document((cache / (key + '.mlfq')).read_bytes(), 2)
    root = typed.query_payload_root(doc)
    if doc.nodes[root].data[0] == 303:
        ref, stored_key, _, header, body = wire.graph_node(doc, root, 303, 5)
        require(baseline_fields is not None, 'comparison needs an exact-key reference compiler')
        require(wire.graph_text(doc, stored_key) == key == typed.verify_source_result(doc),
                'record input and independently recomputed result fingerprint')
        fields = baseline_fields.copy()
        fields[2] = compiler
    else:
        ref, field_list, header, body = wire.graph_node(doc, root, 301, 4)
        fields = [wire.graph_text(doc, child) for child in wire.graph_node(doc, field_list, 1)]
    typed.validate_type(doc, header, 'UnitInterface')
    typed.validate_type(doc, body, 'XTerm')
    digest = wire.graph_text(doc, ref)
    if digest not in contexts:
        raw = (cache / ('context-' + digest + '.mlfqc')).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'context digest')
        context = reader.read_document(raw, 1)
        typed.validate_type(context, context.roots[0], 'DataContext')
        declarations = wire.graph_node(context, context.roots[0], 244, 1)[0]
        contexts[digest] = (raw, context, declarations)
    raw, context, declarations = contexts[digest]
    restored = wire.source_key_from_binary(context, declarations, fields)
    require(hashlib.sha256(restored.encode()).hexdigest() == key, 'complete key/address mismatch')
    require(fields[2] == compiler, 'stored compiler identity differs from executable')
    return doc, header, body, raw, fields


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path, help='PR 29 sequence directory')
    p.add_argument('candidate', type=Path)
    p.add_argument('baseline_binary', type=Path)
    p.add_argument('candidate_binary', type=Path)
    a = p.parse_args()
    runs = [a.baseline, a.candidate]
    compilers = [hashlib.sha256(exe.read_bytes()).hexdigest() for exe in [a.baseline_binary, a.candidate_binary]]
    contexts = [{}, {}]
    visited = set()
    for stage in ('cold', 'warm', 'edit'):
        # The archived study uses stage/unit.*, while compare.py uses stage.*.
        prefixes = [r / stage / 'unit' if (r / stage).is_dir() else r / stage for r in runs]
        for suffix in ('.mlfci', '.mlfco'):
            require(prefixes[0].with_suffix(suffix).read_bytes() == prefixes[1].with_suffix(suffix).read_bytes(),
                    f'{stage} final {suffix}')
        reports = [json.loads(p.with_suffix('.queries').read_text()) for p in prefixes]
        counts = {'cold': (504, 0), 'warm': (0, 504), 'edit': (1, 503)}
        for report in reports:
            require(len(report['groups']) == 504 and
                    (report['inferred_groups'], report['reused_groups']) == counts[stage], 'group counts')
        for groups in zip(*(r['groups'] for r in reports)):
            left_group, right_group = ({k: v for k, v in g.items() if k != 'query_key'} for g in groups)
            require(left_group == right_group, 'group semantics')
            keys = tuple(g['query_key'] for g in groups)
            if keys in visited:
                continue
            left = read_group(runs[0] / 'cache', keys[0], contexts[0], compilers[0])
            right = read_group(runs[1] / 'cache', keys[1], contexts[1], compilers[1], left[4])
            require(left[3] == right[3] and left[4][:2] + left[4][3:] == right[4][:2] + right[4][3:],
                    'actual context or input fields changed')
            wire.require_graph_equal(left[0], left[1], right[0], right[1], 'raw header')
            wire.require_graph_equal(left[0], left[2], right[0], right[2], 'raw body')
            visited.add(keys)
    print(f'PASS {len(visited)} group versions, {len(contexts[0])} contexts, raw and final artifacts')


if __name__ == '__main__':
    main()
