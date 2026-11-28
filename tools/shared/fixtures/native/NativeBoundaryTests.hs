{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless,forM_)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.X.Type as Ty
import qualified Bootstrap.LLVM.Library as N
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified MLF.Primitive as P
right (T.Right x)=x
right (T.Left x)=error (P.textToChars x)
left (T.Left _)=True
left _=False
assert label condition=unless condition (error label)
identity=P.textFromChars (replicate 64 'a')
int=T.XCon "Int" []
bool=T.XCon "Bool" []
unit=T.XConstructor "()" []
name i hint=T.XName i hint
wrapper hint ty=T.XAbs (name 1 hint) ty (T.XLetRec [] (T.XVarTerm (name 1 hint)))
emitRoot layout keys = N.emitCrateProgram [(layout,key) | key <- keys]
emitLibrary layout linked = N.emitCrateLibrary layout (right (N.libraryTerm layout linked))
main=do
 let layout=right (N.prepareLayout identity [("value","parameter",int)] [])
     checked=right (C.check (wrapper "parameter" int))
 assert "valid actual prefix" (not (left (emitRoot layout ["value"] checked)))
 assert "wrong actual parameter type" (left (emitRoot layout ["value"] (right (C.check (wrapper "parameter" bool)))))
 assert "wrong actual binder hint" (left (emitRoot layout ["value"] (right (C.check (wrapper "wrong" int)))))
 assert "missing selected arrow" (left (emitRoot layout ["value"] (right (C.check (T.XIntTerm 1)))))
 assert "unavailable symbol" (left (emitRoot layout ["private"] checked))
 assert "duplicate selected slot" (left (emitRoot layout ["value","value"] checked))
 assert "selected signatures mutation" (left (emitRoot (right (N.prepareLayout identity [("value","parameter",bool)] [])) ["value"] checked))
 let extra=T.DataDecl "Extra" [] [T.ConstructorDecl "MkExtra" []]
 assert "new root layout admitted" (not (left (emitRoot layout ["value"] (right (C.check (T.XWithData [extra] (wrapper "parameter" int)))))))
 assert "no imports preserves returned lambda" (not (left (N.emitCrateProgram [] checked)))
 assert "duplicate exported keys" (left (N.prepareLayout identity [("value","a",int),("value","b",int)] []))
 assert "ambiguous exported hint" (left (N.prepareLayout identity [("x","a",int),("y","a",int)] []))
 assert "duplicate declaration ID" (left (N.prepareLayoutIds identity [(V.fromInt 7,("x","a",int)),(V.fromInt 7,("y","b",int))] []))
 assert "negative declaration ID" (left (N.prepareLayoutIds identity [(V.fromInt (-1),("x","a",int))] []))
 assert "unknown export projection" (left (N.projectExport layout "private" 0 (T.XIntTerm 0)))
 assert "open exported type" (left (N.prepareLayout identity [("x","a",T.XVar (T.XTyVar 9))] []))
 assert "nonstar exported type" (left (N.prepareLayout identity [("x","a",T.XCon "IO" [])] []))
 assert "unsafe identity in symbol" (left (N.prepareLayout "a\"\n" [("x","a",int)] []))
 forM_ [0,1,2,65] $ \count->do
  let entries=[(P.textFromChars ("v"++show i),P.textFromChars ("p"++show i),int) | i<-[0..count-1]]
      l=right (N.prepareLayout identity entries [])
      linked=foldl (\prior i->right (C.appendSpine prior (right (C.check (T.XLet (name i (P.textFromChars ("v"++show i))) (T.XIntTerm i) unit))))) C.emptySpine [0..count-1]
      term=right (N.libraryTerm l linked)
      again=right (C.check (C.term term))
  assert ("installed typed product independent check "++show count) (Ty.alphaEq (C.typeOf term) (C.typeOf again))
 putStrLn "PASS native schema and actual checked-wrapper negative controls; 0/1/2/65 export library terms independently checked"
 -- Even an unused private annotation must belong to the producer's closed
 -- nominal layout. The generic ABI does not rely on an installed name census.
 let hidden=T.XLet (name 90 "private") (T.XAbs (name 91 "x") (T.XCon "Opaque" []) (T.XVarTerm (name 91 "x"))) unit
     hiddenSpine=right (C.appendSpine C.emptySpine (right (C.check hidden)))
     base=right (N.prepareLayout identity [] [])
     opaque=T.DataDecl "Opaque" [] [T.ConstructorDecl "MkOpaque" []]
     declared=right (N.prepareLayout identity [] [opaque])
     declaredSpine=right (C.appendSpine C.emptySpine (right (C.check (T.XWithData [opaque] hidden))))
     fresh=T.DataDecl "Fresh" [] [T.ConstructorDecl "MkFresh" []]
 assert "undeclared private nominal type rejected" (left (emitLibrary base hiddenSpine))
 assert "closed private nominal type admitted" (not (left (emitLibrary declared declaredSpine)))
 assert "producer layout must match checked code" (left (N.emitCrateLibrary base (right (N.libraryTerm declared declaredSpine))))
 assert "fresh root datatype admitted" (not (left (N.emitCrateProgram [] (right (C.check (T.XWithData [fresh] (T.XConstructor "MkFresh" [])))))))
 let storedA=T.DataDecl "StoredA" [] [T.ConstructorDecl "MkStoredA" []]
     storedB=T.DataDecl "StoredB" [] [T.ConstructorDecl "MkStoredB" []]
     tagged=right (N.prepareLayout identity [("value","parameter",int)] [storedA,storedB])
     before=right (N.crateConstructorTags [storedA,storedB])
     after=right (N.crateConstructorTags [fresh,storedB,storedA])
     sameTag key=case (M.lookup P.compareString key before,M.lookup P.compareString key after) of
       (T.Just x,T.Just y)->x==y
       _->False
     consumer ds=right (C.check (T.XWithData ds (wrapper "parameter" int)))
 assert "crate tags survive declaration reorder and extension" (sameTag "MkStoredA" && sameTag "MkStoredB")
 assert "fresh constructor has a distinct tag" (case M.lookup P.compareString "MkFresh" after of
   T.Just (tag,0)->all ((/=tag) . fst . snd) (M.toList before)
   _->False)
 assert "matching dependency layout admitted" (not (left (emitRoot tagged ["value"] (consumer [fresh,storedB,storedA]))))
 assert "missing dependency datatype rejected" (left (emitRoot tagged ["value"] (consumer [storedA,fresh])))
 assert "changed dependency constructor fields rejected" (left (emitRoot tagged ["value"]
   (consumer [T.DataDecl "StoredA" [] [T.ConstructorDecl "MkStoredA" [T.Applied "Int" []]],storedB])))
 assert "constructor collision rejected" (left (N.crateConstructorTags
   [storedA,storedB,T.DataDecl "Collision" [] [T.ConstructorDecl "MkStoredA" []]]))
 putStrLn "PASS native crate closed layouts, stable tags and collision rejection"
