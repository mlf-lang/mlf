{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless,forM_)
import qualified Data.List as List
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Module as M
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as S
import qualified MLF.Primitive as P
assert label x=unless x (error label)
text=P.textFromChars
appendText a b=text (P.textToChars a++P.textToChars b)
oldName identity entity=case S.managedBuiltinName entity of
 T.Just name->name
 T.Nothing->if P.eqString (M.owner entity) "Prelude" || M.isRole M.BuiltinType entity
  then S.stableName entity
  else appendText (if M.compareSpace (M.space entity) M.Types==0 || constructor entity then "Module_" else "module_")
       (appendText (S.encoded identity) (appendText "z_" (S.encoded (S.entityEncoding entity))))
 where constructor e=case M.role e of {M.Constructor _->True; _->False}
leftText (T.Left e)=Just(P.textToChars e)
leftText _=Nothing
main=do
 let alphabet=map text ["", "a", "aa", "\0", "é", "😀"]
     lists=concat [sequence (replicate n alphabet)|n<-[0..4]]
 forM_ lists $ \xs->assert "distinct matches independent list oracle and exact error"
  (leftText(D.distinct "test" xs)==if length xs==length(List.nubBy P.eqString xs) then Nothing else Just "duplicate test")
 assert "duplicate datatypes" (leftText(D.validateDeclarations [T.DataDecl "A" [] [T.ConstructorDecl "A1" []],T.DataDecl "A" [] [T.ConstructorDecl "A2" []]])==Just "duplicate data type")
 assert "duplicate constructors" (leftText(D.validateDeclarations [T.DataDecl "A" [] [T.ConstructorDecl "C" []],T.DataDecl "B" [] [T.ConstructorDecl "C" []]])==Just "duplicate data constructor")
 assert "duplicate type parameters" (leftText(D.validateDeclarations [T.DataDecl "A" ["a","a"] [T.ConstructorDecl "C" []]])==Just "duplicate type parameter")
 let roles=[M.Value,M.Datatype,M.Class,M.Constructor "T",M.Method "C",M.BuiltinType,M.Primitive T.PAddInt,M.Primitive T.PSubInt,M.Boolean True,M.Boolean False,M.ManagedConstraint]
     originals=M.primitiveEntities++M.sharedPrimitiveEntities
     entities=originals++[M.Entity owner name role|owner<-["Prelude","MLF.Primitive","User","模块"],name<-["addInt","CallStack","True","x","λ😀"],role<-roles]
 forM_ entities $ \e->assert "primitive membership preserves complete entity identity" (A.isPrimitiveEntity e==any (\p->M.compareEntity p e==0) originals)
 forM_ ["", "mlf:crate:test", "é\0😀"] $ \identity->forM_ entities $ \e->do
  let expected=oldName identity e
  assert "ordinary export naming is byte exact" (P.eqString expected (A.definitionName identity e))
  assert "cached encoded prefix is byte exact" (P.eqString expected (A.definitionNameEncoded (S.encoded identity) e))
 let fake=M.Entity "Own" "addInt" (M.Primitive T.PAddInt)
     iface=A.CrateInterface "id" [] ["Own"] [("Own",[fake])] [("Own",["Own"])] [] [] [] [] [] "" "fingerprint" []
 assert "forged primitive export still rejected" (case A.validateInterface iface of {T.Left _->True; _->False})
 putStrLn "PASS header duplicate errors, entity identity, Unicode naming and forged primitive rejection"
