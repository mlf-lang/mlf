#!/usr/bin/env python3
"""Run the real fixed-library generator and validate its schema against manifest."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / 'tools/shared'))
from test_direct import authenticate_build, sha, verify_file
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--producer', type=Path, required=True, help='Authenticated GHC producer build directory')
parser.add_argument('--output', type=Path, required=True, help='Fresh independent audit directory')
args = parser.parse_args()
build = args.producer.resolve(strict=True)
out = args.output.resolve()
p = authenticate_build(build / 'receipt.json', build / 'bin')
subprocess.run([sys.executable, str(root / 'tools/experimental/prepared-libraries/prepare.py'),
    '--library-manifest', str(root / 'tools/experimental/prepared-libraries/fixtures/mlf-package.json'),
    '--module', 'Fixed.API', '--output', str(out)], cwd=root, check=True)
objdir = out / 'probe-objects'
objdir.mkdir()
objects = []
for name, digest in p['object_inputs'].items():
    path = (build / name).resolve(strict=True)
    verify_file({'path': str(path), 'sha256': digest})
    if path.suffix == '.o' and path.name != 'Main.o': objects.append(path)
for label, source in [('host', root / 'host/ghc/cbits/host.c'), ('supervisor', root / 'runtime/mlf_process_supervisor.c')]:
    target = objdir / (label + '.o')
    subprocess.run([p['cc']['path'], '-O2', '-std=c11', '-I' + str(root/'runtime'), '-c', str(source), '-o', str(target)], check=True)
    objects.append(target)
flags = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-package-env', '-', '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages']
for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']: flags += ['-package', package]
source = out / 'sources/tools/experimental/prepared-libraries/Generate.hs'
subprocess.run([p['ghc']['path'], '-c', *flags, '-i', '-i' + str(build/'objects'), str(source), '-o', str(objdir/'Main.o'), '-ohi', str(objdir/'Main.hi')], check=True)
exe = out / 'generate'
subprocess.run([p['ghc']['path'], *flags, str(objdir/'Main.o'), *map(str, objects), '-o', str(exe)], check=True)
with (out / 'generation.stdout').open('wb') as stdout, (out / 'generation.stderr').open('wb') as stderr:
    result = subprocess.run([str(exe), str(out/'request.json')], cwd=root, stdout=stdout, stderr=stderr, timeout=240)
if result.returncode: raise RuntimeError('generation failed; see generation.stderr')
manifest = json.loads((root/'shared-sources.json').read_text())
product = json.loads((out/'artifacts/generation.json').read_text())
count = re.fullmatch(r'mlf-primitive-(\d+)-v\d+', manifest['primitive_abi']).group(1)
expected = '/'.join(['mlf-prepared-libraries/1', manifest['frontend_semantics'], manifest['builtin_interface'], count])
if product['schema'] != expected: raise RuntimeError('prepared generation schema differs from manifest')
if set(product['modules']) != {'Fixed.API','Fixed.Class','Fixed.Functions','Fixed.Instances','Fixed.Stack','Fixed.Types'}: raise RuntimeError('unexpected fixture closure')
for artifact in product['artifacts']:
    for field in ['metadata', 'object']:
        verify_file({'path':artifact[field+'_path'], 'sha256':artifact[field+'_sha256']})
verify_file({'path':product['generated_source'], 'sha256':product['generated_sha256']})
for pin in json.loads((out/'source-pins.json').read_text()).values():
    verify_file({'path':pin['snapshot'], 'sha256':pin['sha256']})
authenticate_build(build/'receipt.json', build/'bin')
record = {'passed':True, 'scope':'real nonempty prepared-library generation/admission/schema; not installed registry qualification', 'schema':expected, 'modules':product['modules'], 'producer_receipt_sha256':sha(build/'receipt.json'), 'generator_sha256':sha(exe), 'generator_source_sha256':sha(source), 'manifest_sha256':sha(root/'shared-sources.json'), 'audit_driver_sha256':sha(Path(__file__).resolve()), 'product':product}
(out/'audit.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='product'},indent=2))
