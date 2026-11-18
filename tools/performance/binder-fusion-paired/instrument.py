from pathlib import Path
import re,hashlib
SOURCE_SHA='380d29e7b951da022b49517237d74df2ecd3ee3a'
def instrument(source):
    raw=source.encode();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==SOURCE_SHA
    names=['denseValidation','denseValidateEntries']
    clones=[]
    for name in names:
        start=source.index('  '+name+' ::');m=re.search(r'\n  [A-Za-z][A-Za-z0-9_]* ::',source[start+3:]);end=start+3+m.start()+1
        text=source[start:end]
        for old in names:text=re.sub(r'\b'+old+r'\b',old+'Fused',text)
        if name=='denseValidateEntries':
            old='''        ST.bindE (denseCheckBinders state entries)
          (\\binders ->
             stBind (denseAddDescendants state entries)
               (\\loaded ->
                  stBind (denseBindingVisit state root 0)
                    (\\count ->
                       if (count == L.length entries)
                       then denseKindEntries state entries
                       else ST.failE "cyclic binding tree")));'''
            new='''        ST.bindE (denseCheckAndAddDescendants state entries)
          (\\binders ->
             stBind (denseBindingVisit state root 0)
               (\\count ->
                  if (count == L.length entries)
                  then denseKindEntries state entries
                  else ST.failE "cyclic binding tree"));'''
            assert text.count(old)==1;text=text.replace(old,new)
        clones.append(text)
    helper='''  -- Private fresh-validator path: construct descendant lists while checking
  -- binders. No descendant list is observed until every binder check passes.
  denseCheckAndAddDescendants :: forall s. DenseValidation s ->
    [] ((,) Int Node) -> ST s (Either String ());
  denseCheckAndAddDescendants state entries = case entries of {
    [] -> ST.pureE ();
    (:) ((,) n v) rest -> case binder v of {
      Nothing -> denseCheckAndAddDescendants state rest;
      Just b -> stBind (denseGetNode state b) (\\answer -> case answer of {
        Nothing -> ST.failE "missing binder";
        Just ignored -> case state of {
          DenseValidation graph low high table descendants colours kinds starts ends visited ->
            stBind (readDense low descendants b) (\\previous ->
              stBind (writeDense low descendants b ((:) n previous))
                (\\written -> denseCheckAndAddDescendants state rest))
        }
      })
    }
  };
'''
    old='validateDense graph low high = runST (denseValidation graph low high);'
    assert source.count(old)==1
    source=source.replace(old,'validateDense graph low high = runST (denseValidationFused graph low high);')
    pos=source.rfind('}')
    return source[:pos].rstrip()+';\n'+''.join(clones)+helper+'\n}\n'
if __name__=='__main__':
    import sys
    Path(sys.argv[2]).write_text(instrument(Path(sys.argv[1]).read_text()))
