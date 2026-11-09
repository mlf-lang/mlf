#!/usr/bin/env python3
"""Capture the step 00 baseline using its installed programs and independent v1 reader."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = '726cd256aa90d3e8cf596842fbb29515c1bc5249'
CORPUS = 'c5928b5be73cd78d194405e734aa012415570e1a'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path, help='clean checkout at the fixed baseline')
    parser.add_argument('install', type=Path, help='complete public installation from that checkout')
    parser.add_argument('output', type=Path, help='new directory')
    args = parser.parse_args()
    root = args.checkout.resolve(strict=True)
    install = args.install.resolve(strict=True)
    output = args.output.resolve()
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() != BASE:
        raise ValueError('unexpected baseline source commit')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root):
        raise ValueError('baseline checkout must be clean')
    output.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(root / 'tools/performance' / area) for area in ('foundation-query', 'crate-query-graph')]
    from compare import compile_crate, crate_spec
    from verify import check_receipts, graph, read_document

    receipt_path = install / 'receipt.json'
    receipt = json.loads(receipt_path.read_bytes())
    if not receipt['complete'] or receipt['optimization'] != '2':
        raise ValueError('expected complete GHC -O2 installation')
    compiler = install / 'bin/emlf'
    manager = install / 'bin/mlfpkg'
    programs = {}
    for program in (compiler, manager):
        digest = sha(program)
        if digest != receipt['outputs'][program.name]['sha256']:
            raise ValueError(f'{program} differs from the installation receipt')
        programs[program.name] = {'path': str(program), 'sha256': digest}
    host = subprocess.check_output([compiler, '--implementation-identity'], text=True).strip()
    if host != receipt['implementation_identity']:
        raise ValueError('implementation identity differs from the receipt')
    plan = output / 'locked-plan.json'
    with plan.open('wb') as stream:
        subprocess.run([manager, '--offline', '--locked', 'plan'], cwd=root, stdout=stream, check=True)
    summary = {'source_commit': BASE, 'corpus_commit': CORPUS, 'host': host, 'ghc': receipt['ghc'],
               'optimization': receipt['optimization'], 'install_receipt_sha256': sha(receipt_path),
               'programs': programs, 'locked_plan_sha256': sha(plan), 'sources': {}, 'states': {}}

    # Extract exact blobs without host checkout filters or an existing build's inputs.
    sources = output / 'input/Bootstrap'
    sources.mkdir(parents=True)
    subtree = 'libraries/mlf-foundation/Bootstrap'
    files = subprocess.check_output(['git', 'ls-tree', '--name-only', f'{CORPUS}:{subtree}'], cwd=root, text=True)
    modules = []
    for name in sorted(files.splitlines()):
        if name.endswith('.hs'):
            path = sources / name
            path.write_bytes(subprocess.check_output(['git', 'show', f'{CORPUS}:{subtree}/{name}'], cwd=root))
            modules.append(('Bootstrap.' + path.stem, path))
            summary['sources'][name] = sha(path)
    if len(modules) != 14:
        raise ValueError('unexpected Foundation corpus inventory')
    version = sources / 'Version.hs'
    original = version.read_bytes()
    if original.count(b'version = "0.3.0"') != 1:
        raise ValueError('unexpected Foundation version source')
    cache = output / 'cache'
    spec = output / 'foundation.spec'
    spec.write_text(crate_spec(modules, 'mlf-foundation/0.3.0/library', cache, output / 'builtin/unit'))
    for variable in ('MLF_QUERY_FAILPOINT', 'MLF_QUERY_SEMANTIC_AUDIT', 'MLF_QUERY_PROFILE'):
        os.environ.pop(variable, None)
    try:
        for state, expected in [('cold', [504, 0]), ('warm', [0, 504]), ('edit', [1, 503])]:
            if state == 'edit':
                version.write_bytes(original.replace(b'version = "0.3.0"', b'version = "0.3.1"'))
            prefix = output / state / 'unit'
            prefix.parent.mkdir()
            resources = compile_crate(compiler, spec, prefix)
            report = json.loads(prefix.with_suffix('.queries').read_bytes())
            counts = [report['inferred_groups'], report['reused_groups']]
            if counts != expected:
                raise ValueError((state, counts))
            generation, rows = graph(cache)
            receipts = check_receipts(prefix, cache, rows)
            disk = cache / 'query-graph-v1/generations' / (generation + '.mlfqg')
            index = prefix.parent / 'generation.mlfqg'
            shutil.copyfile(disk, index)
            rows_path = prefix.parent / 'rows.json'
            save(rows_path, rows)
            summary['states'][state] = {
                'counts': counts, 'resources': resources, 'version_source_sha256': sha(version),
                'cache_bytes': sum(p.stat().st_size for p in cache.rglob('*') if p.is_file() and p.name != '.lock'),
                'products_sha256': {s: sha(prefix.with_suffix(s)) for s in ('.mlfci', '.mlfco', '.queries')},
                'generation_sha256': generation, 'rows_sha256': sha(rows_path), 'rows': len(rows),
                'ordered_reads': sum(len(row['reads']) for row in rows.values()), 'index': read_document(index.read_bytes(), 6).accounting(),
                'finish_receipts': receipts}
        if summary['states']['cold']['generation_sha256'] != summary['states']['warm']['generation_sha256']:
            raise ValueError('warm run changed the baseline generation')
    finally:
        version.write_bytes(original)
    save(output / 'summary.json', summary)


if __name__ == '__main__':
    main()
