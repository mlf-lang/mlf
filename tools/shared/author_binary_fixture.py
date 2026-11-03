#!/usr/bin/env python3
"""Static author only: expand the frozen published schema into explicit tests.
Never imported by the runtime runner; no target implementation source is read.
The checked-in result, not a freshly observed implementation, is the oracle.
"""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
contract = json.loads((HERE/'artifact_structure_contract.json').read_text())
rows = contract['schema_fields']
alias = {'Modules.Role':'Role','Modules.Entity':'Entity'}
def norm(t): return alias.get(t,t)
def constructor(name):
    if name.startswith('Modules.'): return 'M.'+name.split('.')[1]
    if name.startswith('Separate.'): return 'U.'+name.split('.')[1]
    if name in ('CrateInterfaceFields','CrateObjectFields'): return 'A.'+name
    return 'T.'+name

def expr(field, n, expected=False):
    if isinstance(field,str): return ('expect' if expected else 'sample')+norm(field)+' ('+n+')'
    form,*args=field
    if form=='list': return ('expectList' if expected else 'sampleList')+' (\\z -> '+expr(args[0],'z',expected)+') ('+n+')'
    if form=='maybe': return ('expectMaybe' if expected else 'sampleMaybe')+' (\\z -> '+expr(args[0],'z',expected)+') ('+n+')'
    children=[expr(arg,'('+n+') * 5 + '+str(i+1),expected) for i,arg in enumerate(args)]
    if expected: return 'W.VNode '+str(2 if form=='pair' else 3)+' ['+', '.join(children)+']'
    return '('+', '.join(children)+')'

def ctor_expr(row, n, expected):
    typ, tag, ctor, fs=row
    children=[expr(f,'('+n+') * 7 + '+str(i+1),expected) for i,f in enumerate(fs)]
    return ('W.VNode '+str(tag)+' ['+', '.join(children)+']') if expected else '('+constructor(ctor)+' '+ ' '.join('('+c+')' for c in children)+')'

def hs_string(s): return json.dumps(s,ensure_ascii=False)
header = r'''{-# LANGUAGE OverloadedStrings #-}
-- Frozen schema-conformance fixture. Generated from the published contract,
-- not from target to/from implementations or observed successful outputs.
module Main where
import Prelude
import Control.Monad (unless, forM_, zipWithM_)
import Control.Exception (try, evaluate, bracket)
import System.Mem.StableName (makeStableName, eqStableName)
import System.Environment (getArgs, getExecutablePath)
import System.Directory (doesPathExist, createDirectory, renameFile)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Module as M
import qualified Bootstrap.Separate as U
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.InferenceUnit as InferenceUnit
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.CrateArtifact as CrateArtifact
import qualified Package.Distribution as Distribution
import qualified Package.Release as Release
import qualified Package.Json as Json
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

need label value = unless value (error label)
expect label value = case value of T.Left e -> error (label ++ ": " ++ B.unpack e); T.Right v -> pure v
reject label value = case value of T.Left _ -> pure (); T.Right _ -> error ("accepted " ++ label)
same (W.VInt a) (W.VInt b) = a == b
same (W.VBits a) (W.VBits b) = a == b
same (W.VText a) (W.VText b) = a == b
same (W.VNode a xs) (W.VNode b ys) = a == b && length xs == length ys && and (zipWith same xs ys)
same _ _ = False
sameValues xs ys = length xs == length ys && and (zipWith same xs ys)
sampleString n = B.literal ("field-" ++ show n ++ "-α😀\NUL")
expectString n = W.VText (sampleString n)
sampleInt n = fromIntegral (negate (3*n+7)) :: P.Int
expectInt n = W.VInt (sampleInt n)
sampleDouble n = P.doubleFromBits (fromIntegral n)
expectDouble n = W.VBits (fromIntegral n)
sampleBool n = odd n
expectBool n = W.VNode (if odd n then 7 else 6) []
sampleList f n = [f (3*n+1), f (3*n+2), f (3*n+1)]
expectList f n = W.VNode 1 (sampleList f n)
sampleMaybe f n = if even n then T.Nothing else T.Just (f n)
expectMaybe f n = if even n then W.VNode 4 [] else W.VNode 5 [f n]
samplePrimitive _ = T.PByteArrayDigest
expectPrimitive _ = W.VNode 32 [W.VInt 131]
sampleInterfaceInstance n = T.SInstanceDecl [(sampleString n,T.Star)] [] (sampleString (n+1)) [T.STVar (sampleString (n+2))] [(sampleString (n+3),T.SIntLit (sampleInt n))]
expectInterfaceInstance n = W.VNode 173 [W.VNode 1 [W.VNode 2 [expectString n,W.VNode 10 []]],W.VNode 1 [],expectString (n+1),W.VNode 1 [W.VNode 100 [expectString (n+2)]],W.VNode 1 [expectString (n+3)]]
sampleRawUnitObject n = U.UnitObject (sampleUnitInterface n) (sampleXTerm (n+1))
expectRawUnitObject n = W.VNode 241 [expectUnitInterface n,expectXTerm (n+1)]

checkCase label encode decode value expected = do
  need (label ++ " exact published tag/ordered fields") (same (encode value) expected)
  restored <- expect (label ++ " decode explicit expected shape") (decode expected)
  need (label ++ " typed roundtrip") (same (encode restored) expected)
  reject (label ++ " wrong leaf kind") (decode (W.VBits 0))
  reject (label ++ " unknown tag") (decode (W.VNode 2147483647 []))
  case expected of
    W.VNode tag children -> do
      reject (label ++ " extra field") (decode (W.VNode tag (children ++ [W.VInt 0])))
      case children of
        [] -> pure ()
        _:rest -> do
          reject (label ++ " missing field") (decode (W.VNode tag rest))
          reject (label ++ " malformed recursive field") (decode (W.VNode tag (W.VNode 2147483647 []:rest)))
    _ -> pure ()
  pure expected

byteList a = do
  n <- P.lengthByteArray a
  mapM (P.readByteArray a) [0..n-1]
fromBytes xs = do
  array <- P.newByteArray (fromIntegral (length xs)) 0
  forM_ (zip [0..] xs) (\(i,x) -> P.writeByteArray array i x)
  pure array
saveBytes path bytes = do
  diagnostic <- P.writeByteFileOrError (B.literal path) bytes
  need ("raw binary write " ++ path ++ ": " ++ B.unpack diagnostic) (diagnostic == "")
wireCheck path roots = do
  bytes <- W.encode W.defaultLimits 7 roots >>= expect "wire encode all constructors"
  decoded <- W.decode W.defaultLimits 7 bytes >>= expect "wire decode all constructors"
  need "whole typed corpus preserves every root and order" (sameValues decoded roots)
  bytes2 <- W.encode W.defaultLimits 7 decoded >>= expect "deterministic reencode"
  a <- byteList bytes; b <- byteList bytes2
  need "deterministic byte-for-byte encoding" (a == b)
  saveBytes path bytes

'''
parts=[header]
first={}
for row in rows:
    typ=norm(row[0]); first.setdefault(typ,row)
for typ,row in first.items():
    parts += ['sample'+typ+' n = '+ctor_expr(row,'n',False)+'\n',
              'expect'+typ+' n = '+ctor_expr(row,'n',True)+'\n']
parts.append('\nconstructorTests = sequence [\n')
cases=[]
for index,row in enumerate(rows):
    typ=norm(row[0]); label=row[2]
    cases.append('  checkCase '+hs_string(label)+' A.to'+typ+' A.from'+typ+' '+ctor_expr(row,str(index+1),False)+' ('+ctor_expr(row,str(index+1),True)+')')
for name,code in contract['primitive_codes']:
    cases.append('  checkCase '+hs_string(name)+' A.toPrimitive A.fromPrimitive T.'+name+' (W.VNode 32 [W.VInt '+str(code)+'])')
parts.append(',\n'.join(cases)+'\n  ]\n')
parts.append('\ngraphChecks = [\n')
graph_cases=[]
for index,row in enumerate(rows):
    typ=norm(row[0])
    graph_cases.append('  \\g root -> checkGraph '+hs_string(row[2])+' A.to'+typ+' A.fromGraph'+typ+' g root ('+ctor_expr(row,str(index+1),True)+')')
for name,code in contract['primitive_codes']:
    graph_cases.append('  \\g root -> checkGraph '+hs_string(name)+' A.toPrimitive A.fromGraphPrimitive g root (W.VNode 32 [W.VInt '+str(code)+'])')
parts.append(',\n'.join(graph_cases)+'\n  ]\n')
parts.append('\n')
(HERE/'fixtures/item4/ArtifactBinary.hs').write_text(''.join(parts))
# The two exceptional typed wrappers are separately tested in the hand-written
# suffix; no inferred target output is used as an expected value.
with (HERE/'fixtures/item4/ArtifactBinary.hs').open('a') as stream:
    stream.write((HERE/'fixtures/item4/ArtifactBinarySuffix.hs.txt').read_text())
