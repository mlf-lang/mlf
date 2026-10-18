const fs=require('fs'),p='bootstrap/Bootstrap/Graph/Solver.emlf',b='.mlf-build/compile3';let s=fs.readFileSync(p,'utf8');
fs.writeFileSync(b+'/before-live-node-Solver.emlf',s,{flag:'wx'});
const marker='restoreNode : Graph';
if(!s.includes(marker))throw Error('Missing insertion point');
const body=`-- Prepared solver graphs forbid identities from being both live nodes and
-- aliases. Component selections consist of live identities, so inspect that
-- table directly. The fallback preserves alias lookup for external callers.
currentNode : Graph -> Int -> Node
currentNode graph identity = case IM.lookup identity (G.nodes graph) of
  Just node -> node
  Nothing -> G.nodeAt graph identity

`;
s=s.replace(marker,body+marker);
s=s.replace('let previous = G.nodeAt old original in','let previous = currentNode old original in');
s=s.replace('Pair n (G.nodeAt old n)) (IS.toList selected)','Pair n (currentNode old n)) (IS.toList selected)');
fs.writeFileSync(p,s);
