const fs=require('fs'),p='bootstrap/Bootstrap/Graph/Solver.emlf',b='.mlf-build/compile3';let s=fs.readFileSync(p,'utf8');
fs.writeFileSync(b+'/before-project-enumeration-Solver.emlf',s,{flag:'wx'});
const marker='matchesNode : IntMap Node';
if(!s.includes(marker))throw Error('Missing insertion point');
const body=`-- The originals enumerate the selected set in ascending order. Their
-- compact identities are consecutive positions; field identities still pass
-- through the alias-resolving rank lookup in localNode.
projectNodes : Graph -> IntSet -> IntMap (Maybe Int) -> IntMap Int -> Int -> List (Pair Int Node) -> List (Pair Int Node)
projectNodes graph selected scopes stubs position originals = case originals of
  Nil -> Nil
  Cons (Pair n node) rest -> Cons (Pair position (localNode graph selected scopes stubs n node))
    (projectNodes graph selected scopes stubs (position + 1) rest)

`;
s=s.replace(marker,body+marker);
const old='let existing = L.map (\\entry -> case entry of Pair n v -> Pair (compact n) (localNode old forward scopes stubs n v)) originals';
if(!s.includes(old))throw Error('Missing node projection');
s=s.replace(old,'let existing = projectNodes old forward scopes stubs 0 originals');fs.writeFileSync(p,s);
