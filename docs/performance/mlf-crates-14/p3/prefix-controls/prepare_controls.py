from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent
S=Path('/workspace/scratch/3f83e2ebe290/mlf-crates-fingerprint-source-20261026/libraries/mlf-crates/Bootstrap')
a=(S/'Separate.hs').read_text();q=(S/'CrateQuery.hs').read_text();i=(S/'InferenceUnit.hs').read_text()
def block(s,start,end):return s[s.index(start):s.index(end,s.index(start))]
blocks=[block(a,'  interfaceFields i =','  decodePair text ='),block(a,'  encodeObject object =','  -- Crate objects and inference queries'),block(q,'  encodeCached key object =','  -- Commands receive NUL-separated argv'),block(q,'  sourceQueryKey crateId','  -- Raw checked inference payloads')]
header='''{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenPrefix where {
 import MLF.Primitive;
 import Bootstrap.Types;
 import Bootstrap.Std;
 import Bootstrap.Separate hiding (interfaceFields,interfaceFingerprint,encodeInterface,encodeObject);
 import Bootstrap.CrateQuery hiding (encodeCached,sourceQueryKey);
 import qualified Bootstrap.Separate as Separate;
 import qualified Bootstrap.Data as D;
 import qualified Bootstrap.X.Pretty as Pretty;
 import qualified Bootstrap.SourceInference as Source;
 import qualified Bootstrap.Dependency as Dependency;
 import qualified Bootstrap.Map as M;
 import qualified Bootstrap.Set as S;
'''
# Use the frozen local encoders, not the candidate's old-named encoders.
blocks[2]=blocks[2].replace('Separate.encodeInterface','encodeInterface').replace('Separate.encodeObject','encodeObject')
(D/'FrozenPrefix.hs').write_text(header+''.join(blocks)+'}\n')
(D/'FrozenInferenceUnit.hs').write_text(i.replace('module Bootstrap.InferenceUnit where','module FrozenInferenceUnit where',1))
manifest={'status':'not run; prepared for authenticated P3 producer under serial guard','baseline':'P2 provisional frozen source','sources':{str(S/n):hashlib.sha256((S/n).read_bytes()).hexdigest() for n in ['Separate.hs','CrateQuery.hs','InferenceUnit.hs']},'frozen':{n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in ['FrozenPrefix.hs','FrozenInferenceUnit.hs']},'permitted_transforms':['Separate encoder excerpts copied byte-for-byte except frozen local encoder calls replacing qualified candidate encoder calls in encodeCached','module name/import preamble','full InferenceUnit copied with module name only changed']}
(D/'oracle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
