"""One-time reviewed preparation generator. Not used by mirror execution."""
from pathlib import Path
import json, hashlib, re, argparse
parser=argparse.ArgumentParser(); parser.add_argument('workspace',type=Path)
base=parser.parse_args().workspace
src=base/'source'; out=base/'implementation'
closure=json.loads((base/'repository/tools/performance/full-compiler/recovery-audit-20261110/allocation-attribution-design/proposed-build-closure.json').read_text())['union']
edits={}
def wrap(path, expression, label):
    text=(src/path).read_text()
    if label == 'CANONICAL_RESULT':
        before = '    result <- finalSyntaxTerm normalized;\n    if finalSyntaxUnchanged'
        assert text.count(before) == 1
        edits.setdefault(path,[]).append({'label':label,'before':before,'after':before.replace(expression, '({-# SCC \"'+label+'\" #-} '+expression+')')})
        return
    assert text.count(expression)==1,(path,label,text.count(expression))
    edits.setdefault(path,[]).append({'label':label,'before':expression,'after':'({-# SCC "'+label+'" #-} '+expression+')'})
def between(path,start,end,label):
    t=(src/path).read_text(); a=t.index(start)+len(start); b=t.index(end,a); wrap(path,t[a:b],label)
p='libraries/mlf-inference/Bootstrap/CompilerCore.hs'
for e,l in [('C.generateProgram program','CONSTRAINT_GENERATION'),('C.solvePrepared constraints','SOLVE'),('E.prepareTypes graph','PREPARED_TYPES'),('E.resolveEvidenceIn types (C.skeleton constraints)','RESOLVE_EVIDENCE'),('E.elaboratePreparedIn types solved evidence (C.skeleton constraints)','ELABORATE'),('E.schemeTypeIn types (C.generalization (C.skeleton constraints))','SCHEME_TYPE'),('T.alphaEq ty expected','TYPE_AGREEMENT'),('X.equalErased (X.erase term)\n                       (C.eraseSourceWith evidence (C.skeleton constraints))','ERASURE_AGREEMENT')]:wrap(p,e,l)
between('libraries/mlf-xmlf/Bootstrap/X/Checked.hs','  check source =\n',';\n  -- Opaque','CLOSED_CHECK')
p='libraries/mlf-crates/Bootstrap/InferenceUnit.hs'
for e,l in [('Open.environment declarations','OPEN_ENV'),('Open.check env parameters implementation','OPEN_INITIAL'),('eqList eqString (sortBy compareString (map (\\((,) n _) -> X.nameHint n) (Open.bindings checked)))\n        (sortBy compareString (map (\\((,,) n _ _) -> n) members))','OPEN_OWNERSHIP')]:wrap(p,e,l)
p='libraries/mlf-xmlf/Bootstrap/X/Check.hs'
for e in ['closedBindingInventory ((:) ((,) name ty) []) (L.snd answer)','closedBindingInventory (L.map bindingPair bindings) (L.snd answer)']:wrap(p,e,'INVENTORY')
between(p,'      let { inventory = ',' };\n      Right ((,) ty inventory)','INVENTORY')
p='libraries/mlf-crates/Bootstrap/SourceInference.hs'
for e,l in [('Wire.prepareGraphPlan Wire.defaultLimits [Structure.toXTerm (Open.body object)]','CANONICAL_PLAN'),('Wire.realizeGraphPlan plan','CANONICAL_REALIZE'),('finalSyntaxRun graph [FinalVisit identity (FinalTerm (Open.body object))] []\n      (FinalSyntaxState M.empty M.empty 0 0 0)','CANONICAL_SYNTAX'),('finalSyntaxTerm normalized','CANONICAL_RESULT'),('Open.normalize object result','OPEN_NORMALIZE')]:wrap(p,e,l)
p='libraries/mlf-crates/Bootstrap/OpenFragment.hs'
between(p,'  stamp env ps term bs = ',';\n  make env','STAMP')
wrap(p,'Boundary.nubNames (Boundary.freeNames term)','FREE_NAMES')
wrap(p,'map name (usedParameters fragment)','FREE_NAMES')
p='libraries/mlf-crates/Bootstrap/QueryGraph.hs'
wrap(p,'Storage.encode 6 [value]','ENCODE')
# This digest expression occurs elsewhere; include the uniquely matching assignment context.
before='      digest <- byteArrayDigest bytes;'
assert (src/p).read_text().count(before)==1
edits.setdefault(p,[]).append({'label':'CONTENT_SHA','before':before,'after':'      digest <- ({-# SCC "CONTENT_SHA" #-} byteArrayDigest bytes);'})
between(p,'  publish session@(Session path config previous old nodes pending) = ',';\n  -- Staging','PUBLISH')
wrap('libraries/mlf-inference/Bootstrap/Elaborate.hs','Solver.witness (C.fromGen edge) target solver','WITNESS_FALLBACK')
# Compute and pin import closures from the unchanged modules (not the annotated text).
def visit(name, seen):
    if name in seen:return
    assert name in closure,name
    seen.add(name)
    for imported in re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_.]*)', (src/closure[name]).read_text(),re.M):
        if imported in closure:visit(imported,seen)
def reach(entry):
    seen=set();visit(entry,seen);return sorted(seen)
emlf=reach('MLF.Entry.Emlf'); gen=reach('MLF.Entry.BuiltinPrelude')
assert len(emlf)==94 and len(gen)==60 and len(set(emlf)|set(gen))==95,(len(emlf),len(gen))
paths=list(closure.values())+['host/ghc/app/emlf/Main.hs','host/ghc/app/builtin-prelude/Main.hs']
pins={p:hashlib.sha256((src/p).read_bytes()).hexdigest() for p in paths}
(out/'insertion-map.json').write_text(json.dumps({'source_commit':'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1','union':closure,'emlf_modules':emlf,'generator_modules':gen,'pins':pins,'edits':edits},indent=2)+'\n')
