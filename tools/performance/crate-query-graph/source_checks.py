#!/usr/bin/env python3
"""Build the source controls with an already qualified producer's exact flags."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('receipt', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--interface', type=Path, help='CLI-produced object to load in this different executable')
p.add_argument('--resume-build', action='store_true', help='reuse failed control-build objects; archive logs and start fresh test caches')
a = p.parse_args()
r = json.loads(a.receipt.read_text())
assert r['complete'] and r['optimization'] == '2'
root = Path(__file__).resolve().parents[3]
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=a.resume_build)
if a.resume_build:
    assert not (out / 'receipt.json').exists(), 'do not overwrite completed controls'
    attempts = out / ('failed-attempt-' + str(len(list(out.glob('failed-attempt-*')))))
    attempts.mkdir()
    for name in ('build.log', 'checks.log', 'cache'):
        if (out / name).exists(): (out / name).rename(attempts / name)
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
for entry in r['shared_inputs'].values():
    assert sha(entry['path']) == entry['sha256'], entry['path']
command = next(c['argv'] for c in r['commands'] if '-o' in c['argv'] and
               c['argv'][c['argv'].index('-o') + 1].endswith('/bin/emlf')).copy()
main = root / 'tools/performance/crate-query-graph/SourceChecks.hs'
command = [str(main) if v.endswith('/host/ghc/app/emlf/Main.hs') else v for v in command]
command[command.index('-o') + 1] = str(out / 'source-checks')
# Put Main in a fresh directory without changing the qualified producer.
objects = out / 'objects'; objects.mkdir(exist_ok=a.resume_build)
old_objects = command[command.index('-odir') + 1]
if not a.resume_build:
    # Reuse only the exact module objects authenticated by the ordinary build.
    # Main is the independent control, never the producer's executable wrapper.
    for source in Path(old_objects).rglob('*'):
        if not source.is_file(): continue
        relative = source.relative_to(old_objects)
        if str(relative) in ('Main.o', 'Main.hi'): continue
        assert sha(source) == r['object_inputs']['objects/' + str(relative)], source
        destination = objects / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
command[command.index('-odir') + 1] = str(objects)
command[command.index('-hidir') + 1] = str(objects)
command.insert(command.index('-odir'), '-i' + old_objects)
with (out / 'build.log').open('w') as log:
    subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
with (out / 'checks.log').open('w') as log:
    subprocess.run([out / 'source-checks', out / 'cache', *([a.interface.resolve()] if a.interface else [])], cwd=root,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
(out / 'receipt.json').write_text(json.dumps(dict(complete=True,
    producer_receipt_sha256=sha(a.receipt), fixture_sha256=sha(main),
    command=command, binary_sha256=sha(out / 'source-checks')), indent=2) + '\n')
print((out / 'checks.log').read_text(), end='')
