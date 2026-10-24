{-# LANGUAGE OverloadedStrings #-}
-- Focused host-side artifact contract; not a guest or native execution receipt.
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Data as D
import qualified Bootstrap.Module as M
import qualified Bootstrap.SourceEquality as E
import qualified Bootstrap.Map as Map
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Parser as XP
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import System.Exit (exitFailure)

list = foldr T.Cons T.Nil
toList T.Nil = []
toList (T.Cons x xs) = x : toList xs
isRight (T.Right _) = True
isRight _ = False
isLeft = not . isRight
same = P.eqString
int = T.XCon "Int" T.Nil
char = T.XCon "Char" T.Nil
builtinTypes = [T.XCon "()" T.Nil, T.XCon "[]" (list [char]),
  T.XCon "(,)" (list [int,char]), T.XCon "(,,)" (list [int,char,int]),
  T.XCon "(,,,)" (list [int,char,int,char]), T.XCon "IOError" T.Nil]
classes = list
  [ T.SClassDecl "Eq" (list [T.Pair "a" T.Star]) T.Nil
      (list [T.Pair "==" (T.SArrow (T.STVar "a") (T.SArrow (T.STVar "a") (T.SCon "Bool" T.Nil)))])
  , T.SClassDecl "IsString" (list [T.Pair "a" T.Star]) T.Nil
      (list [T.Pair "fromString" (T.SArrow (T.SCon "[]" (list [T.SCon "Char" T.Nil])) (T.STVar "a"))])
  , T.SClassDecl "Monad" (list [T.Pair "m" (T.KArrow T.Star T.Star)]) T.Nil T.Nil
  , T.SClassDecl "MonadFail" (list [T.Pair "m" (T.KArrow T.Star T.Star)])
      (list [T.SPredicate "Monad" (list [T.STVar "m"])])
      (list [T.Pair "fail" (T.SForall T.Flexible "a" T.SBottom
        (T.SArrow (T.SCon "[]" (list [T.SCon "Char" T.Nil]))
          (T.STypeApp (T.STVar "m") (T.STVar "a"))))]) ]
family extra = T.DataDecl "Box" (list ["a"])
  (list ([T.ConstructorDecl "Box" (list [T.Parameter "a"])] ++ extra))
iface cs bs = U.UnitInterface "Example" T.Nil T.Nil (list [family []]) cs T.Nil bs "test-object"
bindings = list (zipWith (\n ty -> T.Pair (B.literal ("value" ++ show n)) ty) [0::Int ..] builtinTypes)
roundtrip i = case U.decodeInterface (U.encodeInterface i) of
  T.Right restored -> same (U.encodeInterface restored) (U.encodeInterface i)
  T.Left _ -> False
oldTag tag wire = case U.unpack wire of
  T.Right (T.Cons _ rest) -> U.pack (T.Cons tag rest)
  _ -> wire
key ds = Q.queryKey "crate" "compiler" T.Nil T.Nil ds
crate cs = A.CrateInterface "test:artifact" T.Nil T.Nil T.Nil T.Nil (list [family []]) cs T.Nil
  (list [family []]) bindings "" "test-object"
canonicalFamily = T.DataDecl "Envelope" T.Nil (list [T.ConstructorDecl "Envelope"
  (list [T.Applied "[]" (list [T.Applied "Char" T.Nil]), T.Applied "()" T.Nil,
         T.Applied "(,)" (list [T.Applied "Int" T.Nil, T.Applied "Char" T.Nil])])])
checks =
  [ ("overloaded string patterns cannot collide with legacy strings",
      not (same (Q.encodePattern (T.SStringPattern "x"))
        (Q.encodePattern (T.SOverloadedStringPattern "x" "eq" "from"))))
  , ("string pattern Eq and IsString identities affect key",
      let p = Q.encodePattern (T.SOverloadedStringPattern "x" "eq" "from")
      in not (same p (Q.encodePattern (T.SOverloadedStringPattern "x" "other" "from")))
         && not (same p (Q.encodePattern (T.SOverloadedStringPattern "x" "eq" "other"))))
  , ("string pattern method refs canonicalize", E.eqSPattern
      (Q.canonicalPattern (Map.fromList P.compareString (list [T.Pair "eq" "e", T.Pair "from" "f"])) Map.empty 0
        (T.SOverloadedStringPattern "x" "eq" "from")) (T.SOverloadedStringPattern "x" "e" "f"))
  , ("canonical X type roundtrip", all (\ty -> case XP.parseType (Pretty.prettyType ty) of
        T.Right rt -> same (Pretty.prettyType rt) (Pretty.prettyType ty); _ -> False) builtinTypes)
  , ("canonical constructor term roundtrip", all (\term -> case XP.parseTerm "artifact" (Pretty.prettyTerm term) of
        T.Right rt -> same (Pretty.prettyTerm rt) (Pretty.prettyTerm term); _ -> False)
      [T.XConstructor "()" T.Nil, T.XConstructor "[]" (list [char]),
       T.XConstructor ":" (list [char]), T.XConstructor "(,)" (list [int,char])])
  , ("canonical datatype field metadata roundtrip", roundtrip
      (U.UnitInterface "Example" T.Nil T.Nil
        (list [T.DataDecl "Envelope" T.Nil (list [T.ConstructorDecl "Envelope"
          (list [T.Applied "[]" (list [T.Applied "Char" T.Nil]), T.Applied "()" T.Nil,
                 T.Applied "(,)" (list [T.Applied "Int" T.Nil, T.Applied "Char" T.Nil])])])])
        T.Nil T.Nil T.Nil "test-object"))
  , ("pooled datatype canonical fields roundtrip", case A.decodeTypePool (U.pack (list [D.prettyDeclaration canonicalFamily])) of
      T.Right pool -> case Map.lookup S.compareInt 0 pool of
        T.Just d -> E.eqDataDecl d canonicalFamily
        _ -> False
      _ -> False)
  , ("checked canonical unit object roundtrip",
      let term = T.XConstructor "()" T.Nil
          i = U.UnitInterface "Example" T.Nil T.Nil T.Nil T.Nil T.Nil T.Nil (U.fingerprint (Pretty.prettyTerm term))
          object = U.UnitObject i term
      in isRight (U.decodeObject i (U.encodeObject object)))
  , ("canonical module interface roundtrip", roundtrip (iface T.Nil bindings))
  , ("class signatures and superclass roundtrip", roundtrip (iface classes T.Nil))
  , ("canonical crate metadata roundtrip", case A.decodeInterface (A.encodeInterface (crate classes)) of
        T.Right rt -> same (A.encodeInterface rt) (A.encodeInterface (crate classes)); _ -> False)
  , ("stale module format rejected", isLeft (U.decodeInterface (oldTag "MLFI-1" (U.encodeInterface (iface T.Nil T.Nil)))))
  , ("stale crate format rejected", isLeft (A.decodeInterface (oldTag "MLFCI-1" (A.encodeInterface (crate T.Nil)))))
  , ("constructor family changes query key", not (same (key (list [family []]))
      (key (list [family [T.ConstructorDecl "Empty" T.Nil]]))))
  , ("nested field type changes query key", not (same (key (list [family []]))
      (key (list [T.DataDecl "Box" (list ["a"]) (list [T.ConstructorDecl "Box" (list [T.Applied "Int" T.Nil])])]))))
  , ("builtin family inventory in query key", case U.unpack (key T.Nil) of
      T.Right fields -> same (last (toList fields)) (Q.list Q.encodeDatatype D.builtinDeclarations)
      _ -> False)
  , ("canonical ctor stable only in Prelude", same (U.stableName (M.Entity "Prelude" ":" (M.Constructor "[]"))) ":"
      && not (same (U.stableName (M.Entity "User" ":" (M.Constructor "List"))) ":"))

  ]
main = do
  case U.decodeInterface (U.encodeInterface (iface classes T.Nil)) of
    T.Left err -> putStrLn ("CLASS DIAGNOSTIC: " ++ B.unpack err)
    _ -> pure ()
  case A.decodeInterface (A.encodeInterface (crate classes)) of
    T.Left err -> putStrLn ("CRATE DIAGNOSTIC: " ++ B.unpack err)
    _ -> pure ()
  results <- mapM (\(name, ok) -> putStrLn ((if ok then "PASS " else "FAIL ") ++ name) >> pure ok) checks
  if and results then putStrLn "item4 artifact contracts: passed" else exitFailure
