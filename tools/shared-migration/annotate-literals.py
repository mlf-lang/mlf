#!/usr/bin/env python3
"""One-time annotations justified by actual GHC inferred-type diagnostics."""
import hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[2]
PLAN=pathlib.Path(__file__).with_name('literal-signatures.json')
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
    receipt_path=ROOT/'tools/shared-migration/evidence/literal-annotation-adjustment.json'
    assert not receipt_path.exists(),'Historical annotation receipt already exists; do not reapply or overwrite it.'
    plan=json.loads(PLAN.read_text());by_file={}
    for item in plan: by_file.setdefault(item['path'],[]).append(item)
    files=[]
    for path,items in by_file.items():
        p=ROOT/path;before=p.read_bytes();source=before.decode();insertions=[]
        for item in items:
            name=item['name'];declaration='  '+name+' :: '+item['signature']+';\n'
            existing=re.search(r'^  '+re.escape(name)+r'\s*::',source,re.M)
            if existing:
                assert declaration in source,'Existing different signature: '+name
                continue
            match=re.search(r'^  '+re.escape(name)+r'(?=\s|=)',source,re.M)
            assert match,'Top-level definition missing: '+name
            insertions.append((match.start(),declaration))
        for offset,declaration in sorted(insertions,reverse=True):
            source=source[:offset]+declaration+source[offset:]
        after=source.encode()
        # Every change is a standalone, literal-free ordinary signature. Removing
        # those exact new byte spans must recover the entire original source.
        restored=source
        for _,declaration in insertions:restored=restored.replace(declaration,'',1)
        assert restored.encode()==before,'Non-annotation bytes changed'
        assert p.read_bytes()==before,'Concurrent edit: '+path
        p.write_bytes(after)
        files.append({'path':path,'old_sha256':sha(before),'new_sha256':sha(after),'annotations':items,'added':len(insertions)})
    receipt={'format':1,'operation':'GHC-observed literal-variable concretization',
       'diagnostic':'standard-inferred-types-before.log','checks':{'only_literal_free_signature_insertions':True,'all_other_source_bytes_unchanged':True},'files':files}
    (ROOT/'tools/shared-migration/evidence/literal-annotation-adjustment.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'files':len(files),'signatures_added':sum(r['added'] for r in files)}))
if __name__=='__main__':main()
