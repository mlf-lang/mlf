const fs=require('fs'),p='bootstrap/Bootstrap/IntMap.emlf',b='.mlf-build/compile3';
let s=fs.readFileSync(p,'utf8');
fs.writeFileSync(b+'/before-map-update-IntMap.emlf',s,{flag:'wx'});
for(const call of ['insertTree key value','insertWithTree combine key value']){
 const before=`    if key < oldKey then M.balance oldKey oldValue (${call} left) right\n    else if key > oldKey then M.balance oldKey oldValue left (${call} right)`;
 if(!s.includes(before))throw Error('Missing insertion path '+call);
 const after=`    if key < oldKey then
      let updated = ${call} left in
      if M.size updated == M.size left then M.node n oldKey oldValue updated right
      else M.balance oldKey oldValue updated right
    else if key > oldKey then
      let updated = ${call} right in
      if M.size updated == M.size right then M.node n oldKey oldValue left updated
      else M.balance oldKey oldValue left updated`;
 s=s.replace(before,after);
}
s=s.replace('insertTree : forall a.', '-- Replacing a value preserves every subtree size and the existing balance.\n-- Only a new key needs a balance calculation on the return path.\ninsertTree : forall a.');
fs.writeFileSync(p,s);
