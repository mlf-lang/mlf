#!/usr/bin/env python3
"""Pin completed controls, qualified producers and every paired timing sample."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def identity(p):
    p = Path(p).resolve()
    return dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline_receipt','candidate_receipt','acceptance','external','source_checks','study','profile','output'):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    producers={}
    for name,path in [('29',a.baseline_receipt),('candidate',a.candidate_receipt)]:
        r=read(path); assert r['complete'] and r['optimization']=='2'
        for item in [r['ghc'],r['outputs']['emlf'],*r['shared_inputs'].values()]:
            assert sha(item['path'])==item['sha256'],item['path']
        producers[name]=dict(receipt=identity(path),ghc=r['ghc'],compiler=r['outputs']['emlf'],flags=r['flags'],
            shared_sources={k:dict(path=v['path'],sha256=v['sha256']) for k,v in r['shared_inputs'].items()},
            builtin_verification=r['builtin_verification'])
    assert producers['29']['ghc']==producers['candidate']['ghc']
    study=read(a.study/'results.json'); profile=read(a.profile/'results.json')
    assert study['complete'] and profile['complete']
    assert study['order']==['29','candidate','candidate','29'] and len(study['samples'])==12
    assert study['binaries']=={k:v['compiler']['sha256'] for k,v in producers.items()}
    assert profile['binary_sha256']==study['binaries']['candidate']
    summary={}
    for stage in ('cold','warm','edit'):
        summary[stage]={}
        for arm in ('29','candidate'):
            rows=[s for s in study['samples'] if s['arm']==arm and s['stage']==stage]
            assert len(rows)==2
            for row in rows:
                prefix=a.study/(str(row['index'])+'-'+arm)/stage
                row['interface_bytes']=prefix.with_suffix('.mlfci').stat().st_size
                row['object_bytes']=prefix.with_suffix('.mlfco').stat().st_size
            summary[stage][arm]={k:statistics.mean(s[k] for s in rows)
                for k in ('wall_s','cpu_s','rss_bytes','cache_bytes','interface_bytes','object_bytes')}
        summary[stage]['wall_change_percent']=100*(summary[stage]['candidate']['wall_s']/summary[stage]['29']['wall_s']-1)
    controls={}
    for name,path in [('cli',a.acceptance/'results.json'),('external',a.external/'results.json'),
                      ('source',a.source_checks/'receipt.json')]:
        record=read(path); assert record['complete']
        controls[name]=dict(receipt=identity(path),record=record)
    assert controls['cli']['record']['binary_sha256']==study['binaries']['candidate']
    assert len(controls['cli']['record']['cases'])==20
    assert len(controls['cli']['record']['recovery'])==9
    assert controls['cli']['record']['partial_batch_preserves_previous_generation']
    assert controls['external']['record']['candidate_sha256']==study['binaries']['candidate']
    assert controls['source']['record']['producer_receipt_sha256']==sha(a.candidate_receipt)
    checks=a.source_checks/'checks.log'
    controls['source']['log']=dict(**identity(checks),text=checks.read_text())
    comparisons=[]
    for name in ('comparison-0-1.log','comparison-3-2.log'):
        log=a.study/name
        assert log.read_text().strip()=='PASS 505 raw versions and all final interfaces/bodies/environments'
        comparisons.append(identity(log))
    folder=Path(__file__).resolve().parent
    result=dict(format=1,baseline_commit='3283899e8ab03af048a674ee41988e454dca813a',
        complete=True,producers=producers,controls=controls,study_directory=str(a.study.resolve()),
        study=study,summary=summary,comparisons=comparisons,profile_directory=str(a.profile.resolve()),
        profile=profile,control_sources={str(f.relative_to(folder)):sha(f) for f in sorted(folder.iterdir())
            if f.suffix in ('.py','.hs')})
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
