from pathlib import Path
import re,hashlib
SOURCE_SHA='380d29e7b951da022b49517237d74df2ecd3ee3a'
def instrument(source):
    raw=source.encode();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==SOURCE_SHA
    names=['denseValidation','denseStructurally','denseValidateEntries','denseChild','denseKindBinder','denseKind','denseTagKind','denseKindEntries','denseChildKinds']
    clones=[]
    for name in names:
        start=source.index('  '+name+' ::');m=re.search(r'\n  [A-Za-z][A-Za-z0-9_]* ::',source[start+3:]);end=start+3+m.start()+1
        text=source[start:end]
        text=text.replace('forall s. ','forall s. STArray s (IntMap Int) -> ',1)
        for old in sorted(names,key=len,reverse=True):
            text=re.sub(r'\b'+old+r'\b(?! ::)',old+'Memo memo',text)
            text=text.replace(old+' ::',old+'Memo ::')
        if name=='denseStructurally':
            text=text.replace('''            let {
              n = resolve graph original
            } in
''','''            stBind (resolveMemo memo graph original) (\\n ->
''')
            text=text.replace('(L.append (children (tag v)) rest))))','(L.append (children (tag v)) rest)))))')
        if name=='denseChild':
            text=text.replace('''        let {
          n = resolve graph original
        } in
''','''        stBind (resolveMemo memo graph original) (\\n ->
''')
            text=text.replace('''                  })
    };''','''                  }))
    };''')
        if name=='denseKindBinder':
            text=text.replace('''                      if L.any (\\child -> (resolve graph child == n)) (children (tag parent))
''','''                      stBind (directChildMemo memo graph n (children (tag parent))) (\\direct ->
                      if direct
''')
            text=text.replace('''"a type binder must structurally contain its node"))''','''"a type binder must structurally contain its node")))''')
        clones.append(text)
    helper='''  -- Research candidate: cache lifetime is exactly one validateDense call.
  -- Only the three existing strict resolver consumers are redirected.
  -- No parent-dependent check or original exported dense helper is replaced.
  resolveMemo :: forall s. STArray s (IntMap Int) -> Graph -> Int -> ST s Int;
  resolveMemo memo graph original =
    stBind (readSTArray memo 0) (\\known ->
      case IM.lookup original known of {
        Just canonical -> stReturn canonical;
        Nothing -> let { canonical = resolve graph original } in
          seq canonical (stBind (writeSTArray memo 0 (IM.insert original canonical known))
            (\\saved -> stReturn canonical))
      });
  directChildMemo :: forall s. STArray s (IntMap Int) -> Graph -> Int -> [] Int -> ST s Bool;
  directChildMemo memo graph wanted pending = case pending of {
    [] -> stReturn False;
    (:) child rest -> stBind (resolveMemo memo graph child) (\\n ->
      if n == wanted then stReturn True else directChildMemo memo graph wanted rest)
  };
'''
    before='  validateDense graph low high = runST (denseValidation graph low high);'
    after='  validateDense graph low high = runST (stBind (newSTArray 1 IM.empty) (\\memo -> denseValidationMemo memo graph low high));'
    assert source.count(before)==1
    source=source.replace(before,after)
    pos=source.rfind('}');source=source[:pos]+';\n'+helper+''.join(clones)+source[pos:]
    return source
if __name__=='__main__':
    root=Path(__file__).parent;s=instrument((root/'Graph.original.hs').read_text());(root/'Graph.candidate.hs').write_text(s)
    (root/'CanonicalMemo.hs').write_text(s.replace('module Bootstrap.Graph where','module Prototype.CanonicalMemo where',1))
