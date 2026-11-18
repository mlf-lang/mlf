import json,hashlib,pathlib,zipfile,sys
root=pathlib.Path(__file__).parent;path=root/'paired.zip';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();assert digest==sys.argv[1]
z=zipfile.ZipFile(path);assert z.testzip() is None
names=z.namelist();assert len(names)==len(set(names));assert all(not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts for n in names)
inv=json.loads(z.read('artifact-inventory.json'))
missing=[r for r in inv['files'] if r['path'] not in names]
assert not missing,missing
for r in inv['files']:
 b=z.read(r['path']);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
receipts={n:json.loads(z.read(n)) for n in ['install-receipt.json','build-receipt.json','screen-outer.json','screen/screen-receipt.json'] if n in names}
for n,d in receipts.items():
 assert d['complete'],(n,d.get('errors'))
 if n in ['install-receipt.json','build-receipt.json']:assert d['cleanup'] and d['within_whole'] and not d['errors']
o=receipts['screen-outer.json'];assert o['cleanup_complete'] and o['reason']=='target exited' and o['target_exit_code']==0 and not o['survivors'] and not o['signals'] and not o['cancel_signals']
r=receipts['screen/screen-receipt.json'];assert r['owned_quiescent'] and r['postchecks'] and not r['errors']
def outputs(label):
 prefix='screen/evidence-'+label+'/'
 return {n[len(prefix):]:z.read(n) for n in names if n.startswith(prefix) and (n[len(prefix):] in ['unit.mlfci','unit.mlfco','unit.queries'] or n[len(prefix):].startswith('query-cache/query-graph-v2/results/'))}
a=outputs('qual-A');assert len(a)==1656,len(a)
for label in ['qual-C']+[side+str(i) for i in range(1,7) for side in ['A','C']]:assert outputs(label)==a,label
receipts['screen/screen-receipt.json']={k:v for k,v in r.items() if k!='targets'}
receipts['screen/screen-receipt.json']['targets']=[{k:v for k,v in t.items() if k not in ['qualification_summary','raw_equality']} for t in r['targets']]
summary=dict(missing_archive_files=missing,archive_complete=True,verified_inventory_files=len(inv['files'])-len(missing),run=44221594799,commit='5bd6fe7b96dca544413e2eee51789dd6f690ac55',zip_sha256=digest,inventory_files=len(inv['files']),raw_artifact_files_equal_per_call=len(a),scope='same-main Foundation15 compiler A/C screening, not GHC parity or native fixed point',receipts=receipts)
(root/'results.json').write_text(json.dumps(summary,indent=2)+'\n');(root/'artifact-inventory.json').write_bytes(z.read('artifact-inventory.json'))
print(json.dumps(dict(decision=r['decision'],ratio=r['geometric_wall_C_over_A'],pairs=r['pairs'],measurements=[dict(name=t['name'],wall_s=t['measurement']['wall_ns']/1e9,rss=t['measurement']['maxrss_KiB']) for t in r['targets']],files=len(inv['files'])),indent=2))
