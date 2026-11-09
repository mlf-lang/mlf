{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless,forM_)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.X.Type as Ty
import qualified Bootstrap.LLVM.Library as N
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
main=do
 let layout=right (N.prepareLayout identity [("value","parameter",int)] [])
     checked=right (C.check (wrapper "parameter" int))
 assert "valid actual prefix" (not (left (N.emitRoot layout ["value"] checked)))
 assert "wrong actual parameter type" (left (N.emitRoot layout ["value"] (right (C.check (wrapper "parameter" bool)))))
 assert "wrong actual binder hint" (left (N.emitRoot layout ["value"] (right (C.check (wrapper "wrong" int)))))
 assert "missing selected arrow" (left (N.emitRoot layout ["value"] (right (C.check (T.XIntTerm 1)))))
 assert "uninstalled symbol" (left (N.emitRoot layout ["private"] checked))
 assert "duplicate selected slot" (left (N.emitRoot layout ["value","value"] checked))
 assert "selected signatures mutation" (left (N.emitRoot (right (N.prepareLayout identity [("value","parameter",bool)] [])) ["value"] checked))
 let extra=T.DataDecl "Extra" [] [T.ConstructorDecl "MkExtra" []]
 assert "new root layout rejected" (left (N.emitRoot layout ["value"] (right (C.check (T.XWithData [extra] (wrapper "parameter" int))))))
 assert "no imports preserves returned lambda" (not (left (N.emitRoot layout [] checked)))
 assert "duplicate exported keys" (left (N.prepareLayout identity [("value","a",int),("value","b",int)] []))
 assert "ambiguous exported hint" (left (N.prepareLayout identity [("x","a",int),("y","a",int)] []))
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
 -- An unused private function still reserves its annotation's nominal name.
 let hidden=T.XLet (name 90 "private") (T.XAbs (name 91 "x") (T.XCon "Opaque" []) (T.XVarTerm (name 91 "x"))) unit
     hiddenSpine=right (C.appendSpine C.emptySpine (right (C.check hidden)))
     base=right (N.prepareLayout identity [] [])
     census=right (N.libraryTypeNames base hiddenSpine)
     admitted=right (N.prepareLayoutWithTypeNames identity [] [] census)
     incomplete=right (N.prepareLayoutWithTypeNames identity [] [] (filter (not . P.eqString "Opaque") census))
     opaque=T.DataDecl "Opaque" ["a"] [T.ConstructorDecl "MkOpaque" [T.Parameter "a"]]
     fresh=T.DataDecl "Fresh" [] [T.ConstructorDecl "MkFresh" []]
 assert "private annotation included in installed census" (any (P.eqString "Opaque") census)
 assert "complete installed census emits" (not (left (N.emitLibrary admitted hiddenSpine)))
 assert "omitted private nominal census rejected at installation" (left (N.emitLibrary incomplete hiddenSpine))
 assert "reserved unknown type cannot acquire a new kind" (left (N.emitRoot admitted [] (right (C.check (T.XWithData [opaque] (T.XIntTerm 1))))))
 assert "genuinely fresh datatype accepted" (not (left (N.emitRoot admitted [] (right (C.check (T.XWithData [fresh] (T.XConstructor "MkFresh" [])))))))
 let storedA=T.DataDecl "StoredA" [] [T.ConstructorDecl "MkStoredA" []]
     storedB=T.DataDecl "StoredB" [] [T.ConstructorDecl "MkStoredB" []]
     tagged=right (N.prepareLayoutWithTypeNames identity [] [storedA,storedB] [])
     before=N.constructorTags tagged
     after=right (N.rootConstructorTags tagged [fresh,storedB,storedA])
     sameTag key=case (M.lookup P.compareString key before,M.lookup P.compareString key after) of
       (T.Just x,T.Just y)->x==y
       _->False
 assert "installed tags preserved through root declaration reorder" (sameTag "MkStoredA" && sameTag "MkStoredB")
 assert "new constructor follows installed tag prefix" (case M.lookup P.compareString "MkFresh" after of {T.Just (71,0)->True; _->False})
 assert "missing installed datatype rejected" (left (N.rootConstructorTags tagged [storedA,fresh]))
 assert "changed installed constructor fields rejected" (left (N.rootConstructorTags tagged [T.DataDecl "StoredA" [] [T.ConstructorDecl "MkStoredA" [T.Applied "Int" []]],storedB]))
 assert "constructor collision rejected" (left (N.rootConstructorTags tagged [storedA,storedB,T.DataDecl "Collision" [] [T.ConstructorDecl "MkStoredA" []]]))
 assert "noncanonical census rejected" (left (N.prepareLayoutWithTypeNames identity [] [] ["z","a"]))
 putStrLn "PASS native datatype extension: complete census, kind preservation, stable tags and collision rejection"
