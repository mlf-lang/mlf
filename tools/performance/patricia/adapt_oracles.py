"""Explicit test-only Int64/Patricia adaptation; never edits historical inputs."""
from pathlib import Path
import difflib,hashlib,json,re

def require(value,message):
    if not value:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

RANK_IMPORT = b'  import qualified Bootstrap.IntRank as Rank;\n'
OLD_INDEX = b'case selected of {\n               IntMap tree -> tree\n             }'
NEW_INDEX = b'Rank.indexMap selected'

def without_rank_view(raw):
    require(raw.count(RANK_IMPORT)==1 and raw.count(b'Rank.MapIndex Node')==3
            and raw.count(NEW_INDEX)==1, 'exact session rank-view interface')
    restored=raw.replace(RANK_IMPORT,b'').replace(b'Rank.MapIndex Node',b'IntMapTree Node').replace(NEW_INDEX,OLD_INDEX)
    require(with_rank_view(restored)==raw, 'session rank-view inverse')
    return restored

def with_rank_view(raw):
    marker=b'  import qualified Bootstrap.IntSet as IS;\n'
    require(raw.count(marker)==1 and raw.count(b'IntMapTree Node')==3
            and raw.count(OLD_INDEX)==1 and RANK_IMPORT not in raw, 'exact previous session rank interface')
    return raw.replace(marker,marker+RANK_IMPORT).replace(b'IntMapTree Node',b'Rank.MapIndex Node').replace(OLD_INDEX,NEW_INDEX)

def prepare(root,out):
    out.mkdir(parents=True,exist_ok=False)
    a=root/'tools/performance/a1-private-index/controls';c=root/'tools/performance/c4-local-transaction/controls'
    files={p.name:p for p in c.glob('*.hs') if p.name!='FileControls.hs'}
    files['HeteroinputControls.hs']=c.parent/'entrypoints/HeteroinputMain.hs'
    for name in ['FrozenMap','FrozenIntMap','FrozenIntSet','SessionTests','AdmissionTests']:
        files[name+'.hs']=a/(name+'.hs')
    changes=[]
    for name,path in sorted(files.items()):
        original=path.read_text();s=original
        if name=='HeteroinputControls.hs':
            require(s.count('module Main where')==1,'one heteroinput entry header')
            s=s.replace('module Main where','module HeteroinputControls where')
        s=s.replace('import Bootstrap.Types;','import OracleTypes;').replace('import qualified Bootstrap.Types as T','import qualified OracleTypes as T')
        frozen=name.startswith('Frozen')
        if frozen:
            s=s.replace('import qualified Bootstrap.IntMap as IM;','import qualified FrozenIntMap as IM;').replace('import qualified Bootstrap.IntSet as IS;','import qualified FrozenIntSet as IS;')
            # Prove no algorithm-body edit slipped into the historical cores.
            strip=lambda x:'\n'.join(line for line in x.splitlines() if not line.lstrip().startswith('import '))
            require(strip(s)==strip(original),name+' changed beyond imports')
        else:
            tokens=re.findall(r'"(?:\\.|[^"\\])*"|--[^\n]*|[A-Za-z_][A-Za-z0-9_\']*|.',s,re.S)
            s=''.join('B.Int' if x=='Integer' else 'fromIntegral' if x=='toInteger' else x for x in tokens)
            if 'B.Int' in s and 'import qualified MLF.Host.Base as B' not in s:
                s=s.replace('import Prelude\n','import Prelude\nimport qualified MLF.Host.Base as B\n')
            # Fixed injective wide layouts replace formerly unbounded offsets;
            # all original cases and all relationships between IDs are retained.
            s=s.replace('10^40','2^60').replace('10^(40::B.Int)','2^(60::B.Int)')
            for delta in [0,2,8]:s=s.replace(str(10**30+delta),str(2**60+delta))
            s=s.replace('beyond-machine-Integer-identities','wide-signed-Int64-identities').replace('arbitrary precision identities','wide signed Int64 identities')
        if name=='SessionOracle.hs':
            replacements={
             'mapEntries (T.IntMap t)=entries t':'mapEntries=T.mapEntries',
             'setEntries (T.IntSet t)=map fst (entries t)':'setEntries=T.setEntries',
             'sameMapPhysical eq (T.IntMap a) (T.IntMap b)=sameTree eq a b':'sameMapPhysical=T.sameMap',
             'sameSetPhysical (T.IntSet a) (T.IntSet b)=sameTree (==) a b':'sameSetPhysical=T.sameSet',
             'validMap (T.IntMap tree)=validTree tree && M.valid cmp tree':'validMap=T.validMap',
             'validSet (T.IntSet tree)=validTree tree && M.valid cmp tree && all ((==()).snd) (entries tree)':'validSet=T.validSet'}
            for before,after in replacements.items():require(s.count(before)==1,(name,before));s=s.replace(before,after)
        if name=='SessionTests.hs':
            before=' checkOutcome(label++"/unchanged public route")True expected(C.solvePrepared input)'
            require(s.count(before)==1,'one session outcome adapter');s=s.replace(before,' C4.checkTransactionalOutcome(label++"/unchanged public route") expected(C.solvePrepared input)')
            s=s.replace('import SessionOracle\n','import SessionOracle\nimport qualified C4TransactionOracle as C4\n')
        if name=='C4TransactionControls.hs':
            s=s.replace('import C4TransactionOracle\n','import C4TransactionOracle\nimport qualified Bootstrap.Types as R\nimport qualified PatriciaOracleControls\n')
            s=s.replace('(O.validTree selected)','(T.validMap (R.IntMap selected))').replace('(O.entries selected)','(T.mapEntries (R.IntMap selected))')
            if 'Rank.MapIndex' in (root/'libraries/mlf-inference/Bootstrap/Graph/Solver.hs').read_text():
                # Observe the same raw tree through the new immutable view;
                # validation and enumeration remain independent oracle code.
                s=s.replace('import qualified Bootstrap.Types as R\n',
                    'import qualified Bootstrap.Types as R\nimport qualified Bootstrap.IntRank as Rank\n')
                require(s.count('(R.IntMap selected)')==2,'two rank-view observations')
                s=s.replace('(R.IntMap selected)',
                    '(case selected of Rank.MapIndex tree -> R.IntMap tree)')
            start=s.index('oracleBoundaryControls :: IO ()');end=s.index('prefixDemandControls :: IO ()',start)
            s=s[:start]+'oracleBoundaryControls :: IO ()\noracleBoundaryControls=PatriciaOracleControls.boundary\n\n'+s[end:]
        s=s.replace('\\"old_public_physical_oracle_weakened\\":false','\\"old_BST_representation_preserved\\":false,\\"Patricia_representation_independently_checked\\":true')
        s=s.replace('\\"oracle_boundary_checks\\":9','\\"oracle_boundary_suite\\":\\"PatriciaOracleControls\\"')
        if 'BST/size/balance/nonempty' in s:s=s.replace('BST/size/balance/nonempty','Patricia/prefix/bitmap/count/nonempty')
        if 'raw-source' in name:raise AssertionError(name)
        raw=s.encode();(out/name).write_bytes(raw)
        difference=list(difflib.ndiff(original.splitlines(keepends=True),s.splitlines(keepends=True)))
        require(''.join(difflib.restore(difference,1))==original,'exact original inverse')
        require(''.join(difflib.restore(difference,2))==s,'exact adapted inverse')
        (out/(name+'.ndiff')).write_text(''.join(difference))
        changes.append({'source':str(path),'source_sha256':sha(original.encode()),'adapted':str(out/name),'adapted_sha256':sha(raw),'algorithm_body_unchanged':frozen,'inverse_verified':True})
    owner=root/'libraries/mlf-crates/Bootstrap/CrateSession.hs';s=owner.read_text();before='module Bootstrap.CrateSession (compileSpecFile) where {';after='module SessionUnderTest where {'
    require(s.count(before)==1 and after not in s,'unique private header')
    adapted=s.replace(before,after);require(adapted.replace(after,before)==s,'private header inverse')
    (out/'SessionUnderTest.hs').write_text(adapted)
    changes.append({'source':str(owner),'source_sha256':sha(s.encode()),'adapted':str(out/'SessionUnderTest.hs'),'adapted_sha256':sha(adapted.encode()),'only_module_export_header_changed':True,'inverse_verified':True})
    (out/'adaptations.json').write_text(json.dumps({'purpose':'Int64/Patricia old-core differential controls; not unchanged historical BST physical-contract qualification','finite_total_container_spines_required_for_bridge':True,'frozen_bodies_preserved':True,'cases_removed':0,'representation_boundary_controls_replaced_explicitly':True,'changes':changes},indent=2)+'\n')
    return changes
