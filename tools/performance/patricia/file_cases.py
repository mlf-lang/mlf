"""Authored file behavior controls shared by ordinary and session routes.

Case selection is a normal function argument. The runner checks complete
outputs, fresh inference, artifacts and failure behavior for the selected cases.
"""
import hashlib
import json
import os
from pathlib import Path

FIXTURE = Path(__file__).with_name('fixtures') / 'file-cases.json'


def load_cases(path=FIXTURE):
    authored = json.loads(path.read_text())
    cases = authored['cases']
    names = [case['name'] for case in cases]
    if len(cases) != authored['case_count'] or len(names) != len(set(names)) or not names:
        raise ValueError('file cases need unique names and a matching case count')
    return cases


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def run_files(H, run, save, record, input_pins, out, builtin, baseline_file, candidate_file, *, selected=None):
    """Nine authored files, same paths and builtin, complete raw byte comparison."""
    cases = load_cases()
    if selected is not None:
        H.require(selected in {case['name'] for case in cases}, 'unknown file case')
        cases = [case for case in cases if case['name'] == selected]
    files_root = out/'files'
    files_root.mkdir()
    for case in cases:
        folder = files_root/case['name']
        folder.mkdir()
        sources, source_pins, missing = [], {}, []
        for module, contents in sorted(case['modules'].items()):
            path = folder/'src'/(module.replace('.', '/')+'.emlf')
            path.parent.mkdir(parents=True, exist_ok=True)
            if module not in case.get('missing_modules', []):
                path.write_text(contents)
                source_pins[str(path)] = H.sha(path)
            else:
                missing.append(str(path))
            sources.append((module, str(path)))
        input_pins.update(source_pins)
        outcomes, artifacts = [], []
        for side, binary in [('base', baseline_file), ('candidate', candidate_file)]:
            output = folder/side
            output.mkdir()
            cache, prefix, spec = output/'queries', output/'unit', output/'crate.spec'
            H.require(not os.path.lexists(cache), 'fresh parsed-file query directory')
            spec.write_text(pack(['MLF-CRATE-1', case.get('identity', 'session-control/'+case['name']),
                'Main', 'true', pack([pack(pair) for pair in sources]), pack([]), str(cache), builtin]))
            input_pins[str(spec)] = H.sha(spec)
            so, se = run(str(output.relative_to(out))+'/command', [binary, spec, prefix, case['expected_type']], output)
            H.require(se == b'', 'file controls stderr empty')
            row = dict(side=side, stdout=so.decode(), artifacts={}, query_report_sha256=None)
            if case['expected_type'] == 'reject':
                H.require(so.startswith(b'REJECT ') and so.endswith(b'\n') and so.count(b'\n') == 1, 'complete rejection')
                for fragment in case.get('required_error_fragments', []):
                    H.require(fragment.encode() in so, 'authored rejection fragment')
                exact = case.get('exact_error', case.get('exact_error_template'))
                if exact is not None:
                    for module, path in sources:
                        exact = exact.replace('{source:'+module+'}', path)
                    H.require(so == ('REJECT '+json.dumps(exact, ensure_ascii=False)+'\n').encode(), 'authored exact error')
                H.require(all(not os.path.lexists(str(prefix)+s) for s in ['.mlfci', '.mlfco']), 'rejection publishes no artifacts')
                artifacts.append({})
            else:
                H.require(so == ('PASS file checked '+case['expected_type']+'\n').encode(), 'handwritten checked type')
                report = H.load(str(prefix)+'.queries')
                H.require(type(report['inferred_groups']) is int and report['inferred_groups'] > 0 and
                    type(report['reused_groups']) is int and report['reused_groups'] == 0 and
                    len(report['groups']) == report['inferred_groups'] and all(g['cached'] is False for g in report['groups']),
                    'genuinely fresh parsed-file inference')
                actual_bytes = {s:Path(str(prefix)+s).read_bytes() for s in ['.mlfci', '.mlfco']}
                artifacts.append(actual_bytes)
                row.update(artifacts={s:hashlib.sha256(b).hexdigest() for s,b in actual_bytes.items()},
                    query_report_sha256=H.sha(str(prefix)+'.queries'),
                    groups=[{'id':g['id'], 'members':g['members']} for g in report['groups']],
                    inferred_groups=report['inferred_groups'], reused_groups=0)
            outcomes.append(row)
        H.require(outcomes[0]['stdout'] == outcomes[1]['stdout'] and artifacts[0] == artifacts[1],
                  'actual whole checked artifact bytes and complete diagnostics equal; no normalization')
        H.require(outcomes[0].get('groups') == outcomes[1].get('groups'), 'exact ordered source groups')
        H.check_pins(source_pins)
        H.require(all(not os.path.lexists(p) for p in missing), 'missing-file fixtures stayed absent')
        record['file_cases'].append(dict(name=case['name'], complete=True, outcomes=outcomes,
            actual_raw_artifact_bytes_equal=True,
            query_key_policy='raw reports retained; implementation-dependent keys are not an artifact equality oracle'))
        save()
