#!/usr/bin/env python3
"""Paired Foundation source-cache workload. All auditing is outside process timing."""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

if not __debug__:
    raise RuntimeError('study verification requires a normal Python invocation')

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('binary', type=Path)
p.add_argument('output', type=Path, help='fresh directory')
p.add_argument('--baseline-only', action='store_true')
a = p.parse_args()
binary, out = a.binary.resolve(strict=True), a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
order = ['Old', 'OldProbe'] if a.baseline_only else ['Old', 'New', 'New', 'Old', 'OldProbe', 'NewProbe']
foundation = ROOT/'libraries/mlf-foundation'
source = out/'source'
shutil.copytree(foundation, source)
version = source/'Bootstrap/Version.hs'
original = version.read_bytes()
assert original.count(b'version = "0.3.0"') == 1
changed = original.replace(b'version = "0.3.0"', b'version = "0.3.1"')
modules = json.loads((foundation/'mlf-package.json').read_text())['library']['modules']
assert len(modules) == 14

def pack(fields):
    return ''.join(str(len(x)) + ':' + x for x in fields)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(cache):
    return {f.name: sha(f) for f in sorted(cache.iterdir()) if f.is_file()}

def run(args, log):
    if shutil.disk_usage(out).free < 4 * 1024**3:
        raise RuntimeError('disk floor reached')
    with log.open('wb') as err:
        start = time.monotonic_ns()
        proc = subprocess.Popen([str(binary), *map(str, args)], cwd=out, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=err, start_new_session=True)
        timer = threading.Timer(900, lambda: os.killpg(proc.pid, signal.SIGKILL))
        timer.start()
        try:
            _, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
        finally:
            timer.cancel()
        wall = time.monotonic_ns() - start
    if proc.returncode:
        raise RuntimeError(f'{args} exit {proc.returncode}, see {log}')
    return dict(wall_s=wall/1e9, peak_rss_bytes=usage.ru_maxrss * (1 if sys.platform=='darwin' else 1024),
                cpu_s=usage.ru_utime + usage.ru_stime)

def phases(log, hits):
    rows = [line.split() for line in log.read_text().splitlines()]
    keys = [list(map(int, row[1:])) for row in rows if row[0] == 'key']
    assert len(keys) == 504
    record = dict(key_scalars=sum(k[0] for k in keys), force_s=sum(k[1] for k in keys)/1e9,
                  encode_write_s=sum(k[2] for k in keys)/1e9)
    for field, count in [('read+sha',504), ('read+decode',hits), ('prepared',hits)]:
        values = [int(row[1]) for row in rows if row[0]==field]
        assert len(values) == count
        record[field+'_s'] = sum(values)/1e9
    assert len(rows) == 504*2 + 2*hits
    return record

builtin = out/'builtin/unit'
run(['builtin', builtin], out/'builtin.log')
entries = pack(pack([name, str(source/rel)]) for name,rel in sorted(modules.items()))
record = dict(order=order, binary_sha256=sha(binary), modules={k:sha(source/v) for k,v in modules.items()}, samples=[])
expected_artifacts, expected_reports, same_arm = {}, {}, {}
for index, variant in enumerate(order):
    root = out/(str(index)+'-'+variant)
    root.mkdir()
    cache = root/'cache'
    spec = root/'crate.spec'
    spec.write_text(pack(['MLF-CRATE-1','mlf-foundation/0.3.0/library','','false',entries,'',str(cache),str(builtin)]))
    version.write_bytes(original)
    cold_groups = None
    for stage, counts in [('cold',(504,0)),('warm',(0,504)),('edit',(1,503))]:
        if stage == 'edit':
            version.write_bytes(changed)
        prefix = root/stage
        log = prefix.with_suffix('.log')
        metrics = run([variant,spec,prefix],log)
        report = json.loads(prefix.with_suffix('.queries').read_text())
        assert (report['inferred_groups'], report['reused_groups']) == counts
        groups = report['groups']
        projection = [(g['id'],g['members'],g['semantic_fingerprint']) for g in groups]
        assert len(groups)==len(set(g['id'] for g in groups))==504
        keys = [g['query_key'] for g in groups]
        if stage=='cold':
            cold_groups=keys
        assert sum(x != y for x,y in zip(cold_groups,keys)) == (1 if stage=='edit' else 0)
        arts = {ext:sha(prefix.with_suffix(ext)) for ext in ['.mlfci','.mlfco']}
        state = 'changed' if stage=='edit' else 'original'
        assert arts == expected_artifacts.setdefault(state, arts)
        assert projection == expected_reports.setdefault(state, projection)
        snap = snapshot(cache)
        assert len([k for k in snap if k.endswith('.mlfq')]) == (505 if stage=='edit' else 504)
        assert len([k for k in snap if k.endswith('.mlfqc')]) == 83
        compare = (keys,snap)
        assert same_arm.setdefault((variant.replace('Probe',''),state), compare) == compare
        if variant.endswith('Probe'):
            metrics.update(phases(log,counts[1]))
        else:
            assert not log.stat().st_size
        row = dict(variant=variant,index=index,stage=stage,inferred=counts[0],reused=counts[1],
                   cache_bytes=sum((cache/f).stat().st_size for f in snap),
                   artifact_sha256=arts, artifact_bytes={f:prefix.with_suffix(f).stat().st_size for f in arts},
                   **metrics)
        record['samples'].append(row)
        (out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
        print(variant,stage,metrics,flush=True)
assert expected_artifacts['original']['.mlfco'] != expected_artifacts['changed']['.mlfco']
