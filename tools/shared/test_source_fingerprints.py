#!/usr/bin/env python3
"""Exercise sampled and full source-result verification through --compile-crate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from artifact_binary_reference import read_document, tree_document
from artifact_binary_typed import inspect_artifact, verify_source_result, pack


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('output', type=Path, help='fresh, private directory')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cache = out / 'cache'
    module = out / 'FingerprintProbe.hs'
    module.write_text('-- mlf:syntax shared-haskell-v1\n'
                      '{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n'
                      'module FingerprintProbe where { import MLF.Primitive; ' +
                      '; '.join(f'v{i} :: Int; v{i} = {i}' for i in range(40)) + ' }\n')
    spec = out / 'probe.spec'
    spec.write_text(pack(['MLF-CRATE-1','fingerprint-test','','true',
                          pack([pack(['FingerprintProbe', str(module)])]),'',
                          str(cache),str(out/'builtin/unit')]))
    flag = '-Zincremental-verify-ich'
    observations = []

    def run(stage, expected_misses, position=None):
        prefix = out / stage
        command = [str(compiler), '--compile-crate', str(spec), '-o', str(prefix)]
        if position == 'prefix':
            command.insert(1, flag)
        elif position == 'suffix':
            command.append(flag)
        subprocess.run(command, check=True, timeout=180, cwd=out)
        report = json.loads(prefix.with_suffix('.queries').read_bytes())
        keys = [g['query_key'] for g in report['groups']]
        require(len(keys) == len(set(keys)) == 40, 'expected independent source groups')
        missed = {g['query_key'] for g in report['groups'] if not g['cached']}
        if callable(expected_misses):
            expected_misses = expected_misses(keys)
        require(missed == (set(keys) if expected_misses == 'all' else expected_misses) and
                report['inferred_groups'] == len(missed) and report['reused_groups'] == len(keys)-len(missed),
                f'{stage}: unexpected inferred groups {missed}')
        outputs = [prefix.with_suffix(s).read_bytes() for s in ('.mlfci','.mlfco')]
        observations.append([stage, len(missed), len(keys)-len(missed)])
        return keys, outputs

    def record_path(key):
        return cache / (key + '.mlfq')

    def replace_result(raw):
        root = read_document(raw, 2).values()[0]
        require(root[1] == 303, 'expected shared fingerprint record')
        ref, key, _, header, body = root[2]
        replacement = ('text','0'*64)
        return tree_document([('node',303,(ref,key,replacement,header,body))],schema=2)

    keys, cold = run('cold', 'all')
    pristine = {k: record_path(k).read_bytes() for k in keys}
    for k in keys:
        require(verify_source_result(inspect_artifact(pristine[k],2)) == k, 'independent result hash')
    require(run('default-warm',set())[1] == cold, 'default warm output')
    require(run('strict-warm',set(),'prefix')[1] == cold, 'full warm output')

    # Only the well-formed result fingerprint is wrong. Re-encode to preserve
    # valid framing, CRC, input SHA, shared context, typed header and body.
    poisoned = {k: replace_result(raw) for k,raw in pristine.items()}
    for k,raw in poisoned.items():
        require(raw != pristine[k], 'poison did not change record')
        record_path(k).write_bytes(raw)
    selected = {k for k in keys if int(k[:2],16) < 8}
    require(run('sampled-repair',selected)[1] == cold, 'sampled repair changed outputs')
    for k in keys:
        require(record_path(k).read_bytes() == (pristine[k] if k in selected else poisoned[k]),
                'sampled reader did not repair exactly its selection')
    require(run('strict-repair',set(keys)-selected,'suffix')[1] == cold, 'full repair changed outputs')
    require(all(record_path(k).read_bytes() == pristine[k] for k in keys), 'full repair not canonical')
    require(run('strict-repaired-warm',set(),'prefix')[1] == cold, 'post-repair output')

    # A recognized binary with a wrong input SHA or a truncated payload always misses.
    for stage, bad in [('wrong-input', pristine[keys[1]]), ('truncated', pristine[keys[0]][:-1])]:
        record_path(keys[0]).write_bytes(bad)
        require(run(stage,{keys[0]})[1] == cold and record_path(keys[0]).read_bytes() == pristine[keys[0]],
                stage + ' did not restore the original')
    # Replace an edited definition with the previous, independently checked
    # body of the same name and type. Preserve the edited input SHA and ICH,
    # and regenerate the CRC. Full verification must repair this one value.
    source = module.read_text()
    require(source.count('v0 = 0;') == 1, 'edit anchor')
    module.write_text(source.replace('v0 = 0;', 'v0 = 1000;'))
    edited_keys, edited_output = run('edit', lambda active: set(active)-set(keys), 'prefix')
    fresh, stale = set(edited_keys)-set(keys), set(keys)-set(edited_keys)
    require(len(fresh) == len(stale) == 1 and edited_output != cold, 'single edit')
    changed = fresh.pop()
    correct = record_path(changed).read_bytes()
    old = inspect_artifact(pristine[stale.pop()],2).values()[0][2]
    current = inspect_artifact(correct,2).values()[0][2]
    require(current[0] == old[0] and current[-1] != old[-1], 'same carrier, distinct old raw body')
    transplanted = tree_document([('node',303,(*current[:3],*old[3:]))],schema=2)
    inspect_artifact(transplanted,2)
    record_path(changed).write_bytes(transplanted)
    require(run('strict-transplant-repair',{changed},'suffix')[1] == edited_output and
            record_path(changed).read_bytes() == correct, 'stale checked result survived the audit')
    print(json.dumps({'complete': True, 'stages': observations,
                      'artifacts': [hashlib.sha256(raw).hexdigest() for raw in cold]}))


if __name__ == '__main__':
    main()
