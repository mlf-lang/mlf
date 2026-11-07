#!/usr/bin/env python3
"""Fresh exact-manifest package-core source campaign, not full native qualification.

Never resumes or re-labels an earlier run. Producer authentication binds actual
source bytes, not their semantic purpose. The caller must declare the reviewed
source variant; diagnostic variants are explicitly outside qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--variant', required=True, choices=['baseline', 'candidate', 'diagnostic'])
    parser.add_argument('--producer-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', choices=['mlf-package-core'])
    parser.add_argument('--dependency-root', type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve(strict=True)
    # Authentication receipts bind helper paths as well as their bytes.
    sys.path.insert(0, str(root / 'tools/shared'))
    from test_direct import authenticate_build
    receipt = args.producer_receipt.resolve(strict=True)
    compiler = receipt.parent / 'bin/emlf'
    producer = authenticate_build(receipt, compiler.parent, root=root)
    if producer['optimization'] != '2':
        raise ValueError('this campaign requires an authenticated O2 producer')
    if args.variant == 'baseline':
        for item in producer['shared_inputs'].values():
            relative = str(Path(item['path']).relative_to(root))
            baseline = subprocess.check_output(['git', 'show', '98540496cd5e94d2de87894486acdc9bb945fdac:' + relative], cwd=root)
            if hashlib.sha256(baseline).hexdigest() != item['sha256']:
                raise ValueError('baseline shared source changed: ' + relative)
    if bool(args.only) != bool(args.dependency_root):
        parser.error('--only and --dependency-root must be supplied together')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    basis = args.dependency_root.resolve(strict=True) if args.dependency_root else output
    ordered, seen = [], set()
    def visit(path):
        path = path.resolve(strict=True)
        if path in seen:
            return
        if not path.is_relative_to(root):
            raise ValueError('manifest escapes source root')
        seen.add(path)
        manifest = json.loads(path.read_text())
        for dependency in manifest.get('dependencies', {}).values():
            visit(path.parent / dependency['path'] / 'mlf-package.json')
        ordered.append((path, manifest))
    visit(root / 'libraries/mlf-package-core/mlf-package.json')
    record = {'kind': ('diagnostic-overlay-source-campaign' if args.variant == 'diagnostic'
                       else 'exact-manifest-package-source-campaign'), 'source_variant': args.variant,
              'tracked_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=root)).hexdigest(),
              'complete': False,
              'native_qualification': False, 'source_root': str(root),
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'producer_receipt': str(receipt), 'producer_receipt_sha256': sha(receipt), 'compiler_sha256': sha(compiler),
              'driver_sha256': sha(HERE), 'inputs': {}, 'stages': []}
    def save():
        temporary = output / 'campaign.json.tmp'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'campaign.json')
    if args.only:
        # Reuse is an explicit diagnostic comparison, never qualification of
        # the current compiler's complete dependency-source closure.
        prior_path = basis / 'campaign.json'
        prior = json.loads(prior_path.read_text())
        if prior.get('kind') != 'exact-manifest-package-source-campaign':
            raise ValueError('reuse requires a recorded full source campaign')
        if not prior.get('inputs_unchanged'):
            raise ValueError('dependency campaign did not authenticate its inputs')
        if not all(sha(path) == digest for path, digest in prior['inputs'].items()):
            raise ValueError('dependency campaign input no longer matches')
        previous = {row['name']: row for row in prior['stages']}
        reused = []
        for _, manifest in ordered:
            name = manifest['name']
            if name == args.only:
                continue
            row = previous.get(name)
            if not row or row.get('complete') is not True:
                raise ValueError('dependency stage was not complete: ' + name)
            for suffix, digest in row['artifacts'].items():
                if sha(basis / name / ('artifact/unit.' + suffix)) != digest:
                    raise ValueError('dependency artifact changed: ' + name)
            reused.append(name)
        record.update(kind='diagnostic-package-with-reused-dependencies',
                      limitations=['Borrowed dependencies do not qualify the current source closure.'],
                      dependency_campaign=str(prior_path), dependency_campaign_sha256=sha(prior_path),
                      dependency_source_root=prior['source_root'], reused_stages=reused,
                      dependency_producer_receipt_sha256=prior['producer_receipt_sha256'],
                      dependency_compiler_sha256=prior['compiler_sha256'])
        record['inputs'][str(prior_path)] = sha(prior_path)
    helpers = [root / 'tools/shared' / name for name in
               ('test_direct.py', 'verify_builtin_prelude.py', 'verify_prepared_libraries.py',
                'builtin_prelude_identity.py')]
    for source in (HERE, receipt, compiler, root / 'tools/shared/resource_watchdog.py', *helpers):
        record['inputs'][str(source)] = sha(source)
    for path, manifest in ordered:
        for source in [path, *[path.parent / value for value in manifest['library']['modules'].values()]]:
            actual = source.resolve(strict=True)
            if not actual.is_relative_to(root):
                raise ValueError('source escapes repository')
            record['inputs'][str(actual)] = sha(actual)
    save()
    for path, manifest in ordered:
        name = manifest['name']
        if args.only and name != args.only:
            continue
        stage = output / name
        stage.mkdir()
        for directory in ('queries', 'artifact', 'builtin'):
            (stage / directory).mkdir()
        modules = [(name, str((path.parent / relative).resolve(strict=True)))
                   for name, relative in sorted(manifest['library']['modules'].items())]
        dependencies = [basis / name / 'artifact/unit.mlfci' for name in manifest.get('dependencies', {})]
        for interface in dependencies:
            for source in (interface, interface.with_suffix('.mlfco')):
                record['inputs'][str(source)] = sha(source)
        builtin = basis / 'mlf-foundation/builtin/unit'
        if name != 'mlf-foundation':
            for suffix in ('.mlfci', '.mlfco'):
                source = Path(str(builtin) + suffix)
                record['inputs'][str(source)] = sha(source)
        fields = ['MLF-CRATE-1', name + '/' + manifest['version'] + '/library', '', 'false',
                  pack([pack([name, path]) for name, path in modules]),
                  pack([str(path) for path in dependencies]), str(stage / 'queries'),
                  str(builtin)]
        spec = stage / 'crate.spec'
        spec.write_text(pack(fields))
        (stage / 'spec-fields.json').write_text(json.dumps(fields, indent=2) + '\n')
        record['inputs'][str(spec)] = sha(spec)
        command = [str(compiler), '--compile-crate', str(spec), '-o', str(stage / 'artifact/unit')]
        row = {'name': name, 'command': command, 'complete': False}
        record['stages'].append(row)
        save()
        guarded = [sys.executable, str(root / 'tools/shared/resource_watchdog.py'),
                   '--seconds', '1800' if name == 'mlf-crates' else '900',
                   '--address-space-mib', '4096', '--rss-mib', '2048',
                   '--max-output-mib', '256', '--disk-free-mib', '8192', str(stage),
                   'nice', '-n', '19', 'ionice', '-c', '3', *command]
        result = subprocess.run(guarded, cwd=root)
        resource = json.loads((stage / 'bounded-receipt.json').read_text())
        row.update(wrapper_exit=result.returncode, resource_receipt_sha256=sha(stage / 'bounded-receipt.json'))
        record['inputs_unchanged'] = all(sha(path) == digest for path, digest in record['inputs'].items())
        save()
        if not record['inputs_unchanged']:
            raise RuntimeError('campaign input changed')
        if result.returncode or not resource['complete'] or resource.get('reason') is not None:
            raise SystemExit(1)
        row['artifacts'] = {suffix: sha(stage / ('artifact/unit.' + suffix)) for suffix in ('mlfci', 'mlfco', 'queries')}
        row['complete'] = True
        save()
    authenticate_build(receipt, compiler.parent, root=root)
    record['complete'] = True
    save()

if __name__ == '__main__':
    main()
