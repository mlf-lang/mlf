#!/usr/bin/env python3
"""Narrow historical/current Header controls using a fresh authenticated GHC O0 producer.
Run inside qualification_stage's 120-second owned-tree stage. This entry does
not implement containment and never invokes the complete native-library main.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import header_validation_adapter as H
import test_native_library as N
from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
BANNER = b'PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection\n'
LANES = [('historical', 'HeaderValidationHistorical'), ('current', 'HeaderValidationCurrent')]
HELPERS = ['HistoricalHeaderNames', 'HeaderNamingOracle']
OWN_INPUTS = [
    'tools/shared/qualify_header_only.py',
    'tools/shared/header_validation_adapter.py',
    'tools/shared/test_native_library.py', 'tools/shared/test_direct.py',
    'tools/shared/test_native_string_index.py', 'tools/shared/build.py',
    'tools/shared/fixtures/native/HeaderValidationTests.hs',
    'tools/shared/fixtures/native/HeaderNamingOracle.hs',
]
GENERATED = {'HistoricalHeaderNames.hs', 'HeaderNamingOracle.hs',
             'HeaderValidationHistorical.hs', 'HeaderValidationCurrent.hs',
             'historical-formatter.raw', 'HeaderValidationTests.original.hs', 'adaptation.json'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def regular(path):
    path = Path(path)
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), 'regular input required')
    return path

def pin(paths):
    return {str(regular(p).resolve()): sha(p) for p in sorted(set(map(Path, paths)))}

def unchanged(before):
    require(pin(map(Path, before)) == before, 'immutable input/artifact changed')

def git(root, *args):
    result = subprocess.run(['git', '--no-replace-objects', *args], cwd=root,
                            capture_output=True, timeout=20, check=True)
    require(not result.stderr, 'Git source diagnostic')
    return result.stdout

def producer_contract(producer):
    require(producer.get('complete') is True and producer.get('typecheck_only') is False,
            'complete executable producer')
    require(producer.get('producer_host') == 'GHC' and
            producer.get('implementation_identity') == 'MLF/shared-haskell-v1 GHC',
            'GHC producer identity')
    require(producer.get('optimization') == '0' and producer.get('ghc', {}).get('version') == '9.14.1',
            'exact GHC O0 producer')
    require(isinstance(producer.get('object_inputs'), dict) and producer['object_inputs'],
            'producer object inventory')

def source_snapshot(root, producer, expected_head):
    require(re.fullmatch('[0-9a-f]{40}', expected_head) is not None, 'exact commit required')
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == expected_head, 'wrong source HEAD')
    manifest = json.loads((root / 'shared-sources.json').read_text())
    names = set(OWN_INPUTS)
    names.update(row['path'] for row in manifest['modules'])
    names.update(producer['host_inputs'])
    names.update(producer['configuration_inputs'])
    names.update(producer['builtin_verification_helpers'])
    names.add('tools/shared/verify_prepared_libraries.py')
    names.add('shared-sources.json')
    require(len(names) < 2048, 'source inventory bound')
    rows = git(root, 'ls-tree', '-rz', '--full-tree', expected_head, '--', *sorted(names))
    tree = {}
    for row in rows.split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = name.decode()
        require(mode in ('100644', '100755') and kind == 'blob' and name not in tree,
                'source tree entry')
        tree[name] = (mode, blob)
    require(set(tree) == names, 'tracked source inventory')
    total = 0
    result = {}
    for name in sorted(names):
        path = regular(root / name)
        require(path.resolve().is_relative_to(root), 'source escaped root')
        raw = path.read_bytes()
        total += len(raw)
        require(len(raw) <= 32*1024*1024 and total <= 128*1024*1024, 'source byte bound')
        mode, blob = tree[name]
        require(H.blob_id(raw) == blob, 'source differs from exact commit: ' + name)
        require(bool(path.stat().st_mode & 0o111) == (mode == '100755'), 'source mode')
        result[name] = {'sha256': digest(raw), 'blob': blob, 'bytes': len(raw)}
    return result

def object_paths(build, producer):
    paths = []
    for name, expected in producer['object_inputs'].items():
        path = regular(build / name)
        require(path.resolve().is_relative_to(build) and sha(path) == expected,
                'producer object identity')
        paths.append(path)
    links = [build / name for name in sorted(producer['object_inputs'])
             if name.endswith('.o') and name != 'objects/Main.o']
    require(links and all(p in paths for p in links), 'authenticated link object inventory')
    return paths, links

def command_plan(root, build, output, producer, links):
    header = output / 'header-validation'
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
             '-global-package-db', '-no-user-package-db', '-hide-all-packages',
             '-O0', *N.DEMAND_FLAGS]
    for package in N.PACKAGES:
        flags += ['-package', package]
    ghc = producer['ghc']['path']
    cc = producer['cc']['path']
    commands = []
    transports = [output / 'host.o', output / 'supervisor.o']
    for label, source, target in [
        ('host', root / 'host/ghc/cbits/host.c', transports[0]),
        ('supervisor', root / 'runtime/mlf_process_supervisor.c', transports[1]),
    ]:
        commands.append(('compile-' + label, [cc, '-O2', '-std=c11', '-I'+str(root/'runtime'),
                                              '-c', source, '-o', target], None))
    helper_objects = [header / (name+'.o') for name in HELPERS]
    for name in HELPERS:
        commands.append(('compile-'+name, [ghc, '-c', *flags, *N.EXHAUSTIVENESS_FLAGS,
            '-i', '-i'+str(build/'objects'), '-i'+str(header),
            '-o', header/(name+'.o'), '-ohi', header/(name+'.hi'), header/(name+'.hs')], None))
    for lane, fixture in LANES:
        obj, hi, binary = [output/(fixture+suffix) for suffix in ('.o','.hi','')]
        commands.append(('compile-'+fixture, [ghc, '-c', *flags, *N.EXHAUSTIVENESS_FLAGS,
            '-i', '-i'+str(build/'objects'), '-i'+str(header), '-o', obj, '-ohi', hi,
            header/(fixture+'.hs')], None))
        commands.append(('link-'+fixture, [ghc,*flags,'-rtsopts=ignoreAll',obj,
            *links,*helper_objects,*transports,'-o',binary], None))
    for lane, fixture in LANES:
        commands.append(('header-validation-'+lane,[output/fixture],BANNER))
    return [(name,list(map(str,argv)),expected) for name,argv,expected in commands]

def generated_snapshot(header, fixture, oracle, history):
    require({p.name for p in header.iterdir()} == GENERATED, 'generated exact inventory')
    evidence = json.loads((header/'adaptation.json').read_text())
    expected_module, expected_body = H.historical_module(history)
    require((header/'HistoricalHeaderNames.hs').read_bytes() == expected_module and
            (header/'historical-formatter.raw').read_bytes() == expected_body,
            'physical historical body linkage')
    require((header/'HeaderValidationTests.original.hs').read_bytes() == fixture and
            (header/'HeaderNamingOracle.hs').read_bytes() == oracle, 'generated source linkage')
    for lane, name in LANES:
        require(H.restore_fixture((header/(name+'.hs')).read_bytes(),lane) == fixture,
                'actual generated inverse')
    expected_names = GENERATED - {'adaptation.json'}
    actual = {name: sha(header/name) for name in expected_names}
    require(evidence.get('generated') == actual and
            evidence.get('fixture_git_blob') == H.FIXTURE_BLOB and
            evidence.get('historical_source_git_blob') == H.HISTORICAL_BLOB and
            evidence.get('historical_body_sha256') == digest(expected_body) and
            evidence.get('fixture_inverse_verified') is True and
            evidence.get('historical_inverse_verified') is True and
            evidence.get('historical_complete_compiler_qualified') is False and
            evidence.get('qualification_executed') is False, 'adaptation record chain')
    return pin(header/name for name in GENERATED), evidence

def verify_commands(record, plan, output, root):
    commands = record.get('commands')
    require(isinstance(commands,list) and len(commands)==len(plan)==10, 'complete exact command inventory')
    captures = {}
    for row,(name,argv,expected) in zip(commands,plan):
        require(row.get('name')==name and row.get('argv')==argv and row.get('cwd')==str(root) and
                row.get('timeout_seconds')==120 and row.get('environment_overrides')=={} and
                row.get('state')=='passed' and type(row.get('exit_code')) is int and row['exit_code']==0 and
                not row.get('timed_out') and 'error' not in row and 'cleanup' not in row,
                'actual command ledger')
        stdout = regular(output/(name+'.stdout')).read_bytes()
        stderr = regular(output/(name+'.stderr')).read_bytes()
        require(not stderr and (expected is None or stdout==expected), 'actual command banner/diagnostic')
        for suffix,raw in [('stdout',stdout),('stderr',stderr)]:
            require(row.get(suffix+'_sha256')==digest(raw), 'capture ledger chain')
            captures[str(output/(name+'.'+suffix))] = digest(raw)
    return captures

def qualify(build_receipt, binaries, output, clang_name='clang', *, expected_head=None):
    """The caller must provide the 120s owned-tree stage and whole-source gate."""
    expected_head = expected_head if expected_head is not None else os.environ.get('GITHUB_SHA', '')
    root = ROOT.resolve(strict=True)
    require(N.ROOT.resolve()==root and
            Path(N.__file__).resolve()==root/'tools/shared/test_native_library.py' and
            Path(H.__file__).resolve()==root/'tools/shared/header_validation_adapter.py' and
            Path(sys.modules[authenticate_build.__module__].__file__).resolve()==root/'tools/shared/test_direct.py' and
            N.CommandRunner is CommandRunner and N.authenticate_build is authenticate_build and
            N.prepare_header_validation is H.prepare, 'same-source imported modules')
    receipt = regular(build_receipt).resolve(strict=True)
    build, output = receipt.parent, Path(output).resolve()
    binaries = Path(binaries).resolve(strict=True)
    require(binaries == build/'bin' and binaries.is_dir(), 'exact producer binary directory')
    require(not output.is_relative_to(build) and not build.is_relative_to(output) and
            not root.is_relative_to(output), 'independent output directory')
    output.mkdir(parents=True,exist_ok=False)
    record = {'format':1,'complete':False,'commands':[],'expected_head':expected_head,
        'scope':'two Header fixtures only; not complete native-library orchestration',
        'full_native_suite_qualified':False,'historical_complete_compiler_qualified':False,
        'clang_argument':clang_name,'clang_argument_used':False,
        'external_owned_tree_supervision_required':True,'stage_budget_seconds':120}
    inputs, artifacts = {}, {}
    producer = None
    source_before = None
    started = time.monotonic()
    def save():
        raw = (json.dumps(record,indent=2)+'\n').encode()
        temporary = output/'receipt.json.new'
        temporary.write_bytes(raw)
        require(temporary.read_bytes()==raw,'receipt readback')
        temporary.replace(output/'receipt.json')
    runner = CommandRunner(root,output,record,save)
    save()
    try:
        producer = authenticate_build(receipt,binaries,root=root)
        producer_contract(producer)
        source_before = source_snapshot(root,producer,expected_head)
        record['source_before'] = source_before
        objects,links = object_paths(build,producer)
        tools = [Path(producer['ghc']['path']),Path(producer['cc']['path']),Path(sys.executable).resolve()]
        inputs = pin([receipt,*objects,*tools,*[root/name for name in source_before]])
        record['inputs'] = inputs
        record['producer_receipt_sha256'] = sha(receipt)
        record['object_inputs'] = producer['object_inputs']
        history = H.fixed_history(root)
        header,evidence = H.prepare(root,output,history)
        artifacts,evidence_again = generated_snapshot(
            header,(root/'tools/shared/fixtures/native/HeaderValidationTests.hs').read_bytes(),
            (root/'tools/shared/fixtures/native/HeaderNamingOracle.hs').read_bytes(),history)
        require(evidence==evidence_again,'returned adaptation record')
        record['header_adaptation'] = evidence
        save()
        plan = command_plan(root,build,output,producer,links)
        for name,argv,expected in plan:
            runner.run(name,argv,expected=expected,timeout=120)
            # Capture each newly built artifact before any later command consumes it.
            created = []
            if '-o' in argv:
                created.append(Path(argv[argv.index('-o')+1]))
            if '-ohi' in argv:
                created.append(Path(argv[argv.index('-ohi')+1]))
            artifacts.update(pin(created))
            unchanged(artifacts)
        captures = verify_commands(record,plan,output,root)
        artifacts.update(captures)
        unchanged(artifacts)
        record['header_qualification'] = {
            'complete':True,'lanes':['historical','current'],
            'adaptation_sha256':artifacts[str(header/'adaptation.json')],
            'compiler_and_test_command_count':10,
        }
        record['complete'] = True
    except BaseException as error:
        record.update(complete=False,error=type(error).__name__+': '+str(error))
        raise
    finally:
        try:
            unchanged(inputs)
            unchanged(artifacts)
            if producer is not None:
                after = authenticate_build(receipt,binaries,root=root)
                producer_contract(after)
                require(after==producer,'producer changed')
                source_after = source_snapshot(root,after,expected_head)
                require(source_after==source_before,'source HEAD/bytes changed')
                record['source_after'] = source_after
            record['inputs_verified_after'] = True
            record['artifacts'] = artifacts
        except BaseException as error:
            record.update(complete=False,integrity_error=type(error).__name__+': '+str(error))
            raise
        finally:
            record['seconds'] = time.monotonic()-started
            save()
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt',type=Path,required=True)
    parser.add_argument('--bin-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--clang',default='clang')
    parser.add_argument('--expected-head',required=True)
    args = parser.parse_args()
    qualify(args.build_receipt,args.bin_dir,args.output,args.clang,expected_head=args.expected_head)
    print(str(args.output/'receipt.json')+': narrow Header qualification passed')

if __name__ == '__main__':
    main()
