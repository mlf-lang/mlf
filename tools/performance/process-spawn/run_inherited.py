#!/usr/bin/env python3
"""Supplemental real descriptor, signal and PATH controls; no timing claims."""
from pathlib import Path
import argparse
import sys
import types

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
p=argparse.ArgumentParser(description=__doc__)
for name in ['baseline-root','baseline-producer','producer','output']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();base=a.baseline_root.resolve();old=a.baseline_producer.resolve();new=a.producer.resolve();out=a.output.resolve()
out.mkdir(parents=True,exist_ok=False)
hp=HERE.parent/'a1-private-index/helper.py';H=types.ModuleType('unchanged_helper');H.__file__=str(hp)
exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
auth=[H.authenticate(old,base),H.authenticate(new,ROOT)]
pins={str(f):H.sha(f) for f in [Path(__file__),HERE/'InheritedState.c',HERE/'with_scope.py',hp]}
for producer in [old,new]:
    for name in ['receipt.json','bin/emlf','host.o','supervisor.o']:pins[str(producer/name)]=H.sha(producer/name)
limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,
    'max_work_bytes':256*1024**2,'process_tree_rss_bytes':5*1024**3,'wall_seconds':120}
record={'complete':False,'performance_measured':False,'inputs':pins,'cases':[],'commands':[]}
def save():H.save(out/'receipt.json',record)
def run(label,argv):
    record['commands'].append(H.Runner(out,limits).run(argv,ROOT,out/label));save()
save()
try:
    with H.SerialLock(ROOT/'.mlf-build'):
        for side,producer in [('base',old),('candidate',new)]:
            binary=out/('state-'+side)
            run('build-'+side,[auth[0]['cc']['path'],'-O2','-std=c11',HERE/'InheritedState.c',producer/'host.o',producer/'supervisor.o','-o',binary])
            for mode in range(11):
                label=side+'-'+str(mode);work=out/('cwd-'+label);work.mkdir()
                run(label,[sys.executable,'-B',HERE/'with_scope.py',binary,str(mode),work])
                H.require((out/label/'stdout').read_bytes()==f'PASS inherited state {mode}\n'.encode()
                    and not (out/label/'stderr').read_bytes(),'independent inherited-state expectation')
                record['cases'].append([side,mode]);save()
        H.check_pins(pins);H.require(auth==[H.authenticate(old,base),H.authenticate(new,ROOT)],'ordinary producers unchanged')
        record['complete']=True;save()
except BaseException as error:
    record['error']=repr(error);save();raise
print('PASS 22 real inherited-state cases against both ordinary host objects')
