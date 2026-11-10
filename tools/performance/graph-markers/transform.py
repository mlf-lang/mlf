"""Reversible two-owner markers. No pure owner or ordinary flags are changed."""
from pathlib import Path
import types
BASE=Path(__file__).resolve().parent.parent/'type-kind-memo/progress.py'
P=types.ModuleType('old_progress');P.__file__=str(BASE)
exec(compile(BASE.read_bytes(),str(BASE),'exec'),P.__dict__)
OWNERS=P.OWNERS

def instrument(name, original):
    raw,count=P.instrument(name,original)
    source=raw.decode();changes=[]
    def replace(old,new):
        nonlocal source
        if source.count(old)!=1:raise ValueError('ambiguous marker transform')
        changes.append((old,new));source=source.replace(old,new,1)
    replace('import qualified KindCounters as Progress;', 'import qualified GraphProgress as Progress;')
    if name=='CrateGraph':
        anchor='              Progress.event "scc.scope-inventory.enter";'
        replace(anchor,anchor+'\n              Progress.identity (length owners) (map (\\i -> (,) (V.toInt i) (textToChars (Source.declStable scope i))) (take 4 owners));')
    restored=source
    for old,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('ambiguous marker inverse')
        restored=restored.replace(new,old,1)
    if restored.encode()!=raw:raise ValueError('marker inverse mismatch')
    return source.encode(),count+len(changes)
