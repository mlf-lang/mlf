import json,zipfile,hashlib,pathlib,sys
root=pathlib.Path(__file__).parent;raw=(root/'retry.zip').read_bytes();digest=hashlib.sha256(raw).hexdigest();assert digest==sys.argv[1]
z=zipfile.ZipFile(root/'retry.zip');assert z.testzip() is None;names=z.namelist();assert len(names)==len(set(names));assert all(not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts for n in names)
inv=json.loads(z.read('artifact-inventory.json'))
for row in inv['files']:
 b=z.read(row['path']);assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
receipts={n:json.loads(z.read(n)) for n in ['install-receipt.json','finite-receipt.json','outer.json','O0-cycle.json','O2-cycle.json']}
for n in ['install-receipt.json','finite-receipt.json']:
 d=receipts[n];assert d['complete'] and d['cleanup'] and d['within_whole'] and not d['errors']
o=receipts['outer.json'];assert o['complete'] and o['cleanup_complete'] and o['target_exit_code']==0 and not o['survivors'] and not o['signals'] and not o['cancel_signals'];assert all(x['status']==0 for x in o['reaped'])
for name in ['O0-cycle.json','O2-cycle.json']:
 rows=receipts[name]['rows'];assert len(rows)==2 and {r['side'] for r in rows}=={'original','candidate'};assert all(r['bounded_timeout'] and r['cleanup'] and r['exit']==-9 for r in rows)
a={n[3:]:z.read(n) for n in names if n.startswith('O0/')};b={n[3:]:z.read(n) for n in names if n.startswith('O2/')};assert len(a)==132 and a==b
for n in a:
 if n.endswith('.A'):assert a[n]==a[n[:-2]+'.C']==a[n[:-2]+'.expected'];assert a[n[:-2]+'.result']==b'PASS\n'
s=dict(run=44219094415,commit='8879a04eb63f1578b192218c7c90c9396b8f1d74',zip_sha256=digest,inventory_files=len(inv['files']),archive_complete=True,finite_cases=33,sidecars=[dict(name=n,utf8=v.decode(),sha256=hashlib.sha256(v).hexdigest()) for n,v in sorted(a.items())],receipts=receipts,performance_claim=False)
(root/'results.json').write_text(json.dumps(s,indent=2)+'\n');print('PASS',len(inv['files']),'inventory hashes; 132 equal sidecars')
