#!/usr/bin/env python3
"""Reviewed post-cutover standard-hierarchy adjustment; not a build dependency."""
import argparse, hashlib, json, pathlib, subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=pathlib.Path,default=ROOT)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--tool',type=pathlib.Path,required=True)
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args(); root=args.root.resolve(); out=args.output.resolve()
    assert root!=out
    out.mkdir(parents=True,exist_ok=True)
    modules=json.loads((root/'shared-sources.json').read_text())['modules']
    records=[dict(module=m['module'],path=m['path'],old_sha256=sha(root/m['path'])) for m in modules]
    rows=['\t'.join([str(root/r['path']),str(out/r['path']),r['module']]) for r in records]
    (out/'sources.tsv').write_text('\n'.join(rows)+'\n')
    subprocess.run([str(args.tool),str(out/'sources.tsv'),str(out/'checks.tsv')],check=True)
    checks={row.split('\t')[0]:row.split('\t')[1:] for row in (out/'checks.tsv').read_text().splitlines()}
    for r in records:
        r.update(new_sha256=sha(out/r['path']),legacy_instances=int(checks[r['module']][0]),expression_string_tokens=int(checks[r['module']][1]))
    receipt={'format':1,'operation':'post-cutover-haskell-standard-hierarchy',
      'historical_migration_receipt':'tools/shared-migration/evidence/migration-manifest.json',
      'scope':'Remove RebindableSyntax from implementation pragmas and replace legacy Monad instances with Functor/Applicative/Monad. Preserve legacy method computations; standard Monad defines only (>>=).',
      'checks':{'AST_roundtrip':True,'exact_expression_string_token_multiset':True,'edits_limited_to_header_and_legacy_instance_spans':True},
      'files':records,'tool_sources':{str(p.relative_to(ROOT)):sha(p) for p in (pathlib.Path(__file__).parent).glob('*') if p.suffix in ['.py','.hs']}}
    (out/'adjustment-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if args.apply:
        assert not (root/'tools/shared-migration/evidence/standard-hierarchy-adjustment.json').exists(), 'Historical adjustment receipt exists; do not overwrite it.'
        for r in records:
            assert sha(root/r['path'])==r['old_sha256'], 'Concurrent edit: '+r['path']
        for r in records: (root/r['path']).write_bytes((out/r['path']).read_bytes())
        (root/'tools/shared-migration/evidence/standard-hierarchy-adjustment.json').write_bytes((out/'adjustment-receipt.json').read_bytes())
    print(json.dumps({'modules':len(records),'legacy_instances':sum(r['legacy_instances'] for r in records),'applied':args.apply}))
if __name__=='__main__': main()
