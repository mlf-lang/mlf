const fs=require('fs'),p='bootstrap/Bootstrap/Graph/Solver.emlf',base='.mlf-build/compile3';
let s=fs.readFileSync(p,'utf8');fs.writeFileSync(base+'/before-component-scopes-Solver.emlf',s,{flag:'wx'});
const first=s.indexOf('componentVisit :'),last=s.indexOf('-- The ordered component set',first);
if(first<0||last<0)throw Error('Missing component traversal');
const body=`-- Collect scope boundaries while inspecting each newly discovered node.
-- The identity has just been resolved, so a second alias lookup is redundant.
componentScopesVisit : Solver -> IntSet -> IntSet -> List Int -> Either String (Pair IntSet IntSet)
componentScopesVisit solver seen scopes pending = case pending of
  Nil -> Right (Pair seen scopes)
  Cons original rest ->
    let currentGraph = graph solver in
    let n = G.resolve currentGraph original in
    if IS.member n seen then componentScopesVisit solver seen scopes rest else
      case IM.lookup n (G.nodes currentGraph) of
        Nothing -> Left ("missing graph node " ++ showInt n)
        Just node ->
          let boundary = G.isGen (G.tag node) in
          let connected = if boundary then rest else
                L.append (G.children (G.tag node)) (L.append (L.maybeToList (G.binder node))
                  (L.append (IS.toList (IM.findWithDefault IS.empty n (structuralParents solver)))
                    (L.append (IS.toList (IM.findWithDefault IS.empty n (bindingChildren solver))) rest))) in
          componentScopesVisit solver (IS.insert n seen) (if boundary then IS.insert n scopes else scopes) connected

componentVisit : Solver -> IntSet -> List Int -> Either String IntSet
componentVisit solver seen pending = G.bindE (componentScopesVisit solver seen IS.empty pending) (\\(Pair connected scopes) -> Right connected)

component : Solver -> List Int -> Either String IntSet
component solver starts = componentVisit solver IS.empty starts

componentScopes : Solver -> List Int -> Either String (Pair IntSet IntSet)
componentScopes solver starts = componentScopesVisit solver IS.empty IS.empty starts

`;
s=s.slice(0,first)+body+s.slice(last);
const before='  G.bindE (component solver (L.concatMap G.equationNodes equations)) (\\connected ->\n    let old = graph solver in\n    let boundaries = IS.fromList (L.filter (\\n -> G.isGen (G.tag (G.nodeAt old n))) (IS.toList connected)) in';
if(!s.includes(before))throw Error('Missing component boundary pass');
s=s.replace(before,'  G.bindE (componentScopes solver (L.concatMap G.equationNodes equations)) (\\(Pair connected boundaries) ->\n    let old = graph solver in');
fs.writeFileSync(p,s);
