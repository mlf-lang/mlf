{-# LANGUAGE OverloadedStrings #-}
-- Focused host-side artifact contract; not a guest or native execution receipt.
module Main where
import Prelude
import Data.List (isInfixOf)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.X.Check as XC
import qualified Bootstrap.X.Syntax as XS
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.Primitive as Prim
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

list = foldr (:) []
toList [] = []
toList ((:) x xs) = x : toList xs
isRight (T.Right _) = True
isRight _ = False
isLeft = not . isRight
same = P.eqString
int = T.XCon "Int" []
char = T.XCon "Char" []
builtinTypes = [T.XCon "()" [], T.XCon "[]" (list [char]),
  T.XCon "(,)" (list [int,char]), T.XCon "(,,)" (list [int,char,int]),
  T.XCon "(,,,)" (list [int,char,int,char]), T.XCon "IOError" []]
classes = list
  [ T.SClassDecl "Eq" (list [(,) "a" T.Star]) []
      (list [(,) "==" (T.SArrow (T.STVar "a") (T.SArrow (T.STVar "a") (T.SCon "Bool" [])))])
  , T.SClassDecl "IsString" (list [(,) "a" T.Star]) []
      (list [(,) "fromString" (T.SArrow (T.SCon "[]" (list [T.SCon "Char" []])) (T.STVar "a"))])
  , T.SClassDecl "Monad" (list [(,) "m" (T.KArrow T.Star T.Star)]) [] []
  , T.SClassDecl "MonadFail" (list [(,) "m" (T.KArrow T.Star T.Star)])
      (list [T.SPredicate "Monad" (list [T.STVar "m"])])
      (list [(,) "fail" (T.SForall T.Flexible "a" T.SBottom
        (T.SArrow (T.SCon "[]" (list [T.SCon "Char" []]))
          (T.STypeApp (T.STVar "m") (T.STVar "a"))))]) ]
family extra = T.DataDecl "Box" (list ["a"])
  (list ([T.ConstructorDecl "Box" (list [T.Parameter "a"])] ++ extra))
iface cs bs = U.UnitInterface "Example" [] [] (list [family []]) cs [] bs "test-object"
bindings = list (zipWith (\n ty -> (,) (B.literal ("value" ++ show n)) ty) [0::Int ..] builtinTypes)
roundtrip i = case U.decodeInterface (U.encodeInterface i) of
  T.Right restored -> same (U.encodeInterface restored) (U.encodeInterface i)
  T.Left _ -> False
oldTag tag wire = case U.unpack wire of
  T.Right ((:) _ rest) -> U.pack ((:) tag rest)
  _ -> wire
key ds = Q.queryKey "crate" "compiler" [] [] ds
crate cs = A.CrateInterface "test:artifact" [] [] [] [] (list [family []]) cs []
  (list [family []]) bindings "" "test-object" (S.map (\((,) n _) -> (,) n False) bindings)
canonicalFamily = T.DataDecl "Envelope" [] (list [T.ConstructorDecl "Envelope"
  (list [T.Applied "[]" (list [T.Applied "Char" []]), T.Applied "()" [],
         T.Applied "(,)" (list [T.Applied "Int" [], T.Applied "Char" []])])])
tuple64 = B.literal ("(" ++ replicate 63 ',' ++ ")")
fullChars = T.CharString (list [0,65,55296,57343,1114111])
terminal (T.Function _ result) = terminal result
terminal result = result
checks =
  [ ("source definition boundary changes query encoding", not (same
      (Q.encodeExpression (T.SSourceDefinition (T.SVar "f"))) (Q.encodeExpression (T.SVar "f"))))
  , ("source definition equality retains boundary and body", E.eqSExpr
      (T.SSourceDefinition (T.SVar "f")) (T.SSourceDefinition (T.SVar "f"))
      && not (E.eqSExpr (T.SSourceDefinition (T.SVar "f")) (T.SVar "f"))
      && not (E.eqSExpr (T.SSourceDefinition (T.SVar "f")) (T.SSourceDefinition (T.SVar "g"))))
  , ("source definition canonicalization preserves lexical binder", E.eqSExpr
      (Q.canonicalExpression Map.empty 0 Map.empty 0 (T.SLam "x" T.Nothing (T.SSourceDefinition (T.SVar "x"))))
      (T.SLam "local:0" T.Nothing (T.SSourceDefinition (T.SVar "local:0"))))
  , ("source definition hygiene retains wrapper and lexical binding", case U.hygiene (T.SLam "x" T.Nothing (T.SSourceDefinition (T.SVar "x"))) of
      T.Right (T.SLam name T.Nothing (T.SSourceDefinition (T.SVar use))) -> same name use
      _ -> False)
  , ("overloaded string patterns cannot collide with legacy strings",
      not (same (Q.encodePattern (T.SStringPattern "x"))
        (Q.encodePattern (T.SOverloadedStringPattern (T.ScalarString "x") "eq" "from"))))
  , ("string pattern Eq and IsString identities affect key",
      let p = Q.encodePattern (T.SOverloadedStringPattern (T.ScalarString "x") "eq" "from")
      in not (same p (Q.encodePattern (T.SOverloadedStringPattern (T.ScalarString "x") "other" "from")))
         && not (same p (Q.encodePattern (T.SOverloadedStringPattern (T.ScalarString "x") "eq" "other"))))
  , ("string pattern method refs canonicalize", E.eqSPattern
      (Q.canonicalPattern (Map.fromList P.compareString (list [(,) "eq" "e", (,) "from" "f"])) Map.empty 0
        (T.SOverloadedStringPattern (T.ScalarString "x") "eq" "from")) (T.SOverloadedStringPattern (T.ScalarString "x") "e" "f"))
  , ("full Char payload exact equality", E.eqSourceString fullChars fullChars
      && not (E.eqSourceString fullChars (T.CharString (list [0,65,55297,57343,1114111])))
      && not (E.eqSourceString (T.ScalarString "A") (T.CharString (list [65]))))
  , ("full Char payload key includes every codepoint and order",
      let original = Q.encodeSourceString fullChars
          variants = [T.CharString (list xs) | xs <- [[1,65,55296,57343,1114111],
            [0,66,55296,57343,1114111],[0,65,55297,57343,1114111],
            [0,65,55296,57342,1114111],[0,65,55296,57343,1114110],
            [65,0,55296,57343,1114111],[0,65,55296,57343]]]
      in all (not . same original . Q.encodeSourceString) variants)
  , ("full Char payload survives method canonicalization", E.eqSPattern
      (Q.canonicalPattern (Map.fromList P.compareString (list [(,) "eq" "e", (,) "from" "f"])) Map.empty 0
        (T.SOverloadedStringPattern fullChars "eq" "from")) (T.SOverloadedStringPattern fullChars "e" "f"))
  , ("tuple64 X type roundtrip", let ty = T.XCon tuple64 (list (replicate 64 int)) in
      case XP.parseType (Pretty.prettyType ty) of
        T.Right rt -> same (Pretty.prettyType rt) (Pretty.prettyType ty)
        _ -> False)
  , ("tuple64 module metadata roundtrip", roundtrip (iface []
      (list [(,) "wide" (T.XCon tuple64 (list (replicate 64 int)))])))
  , ("tuple64 complete builtin family affects cache identity",
      let ds = toList D.builtinDeclarations
          wide (T.DataDecl name _ _) = same name tuple64
          valid (T.DataDecl _ params ctors) = length (toList params) == 64 && case toList ctors of
            [T.ConstructorDecl name fields] -> same name tuple64 && length (toList fields) == 64
            _ -> False
      in case filter wide ds of
        [d] -> valid d && case U.unpack (key []) of
          T.Right fields ->
            let changed = U.pack (list (init (toList fields) ++ [Q.list Q.encodeDatatype (list (filter (not . wide) ds))]))
                object = U.UnitObject (U.UnitInterface "Empty" [] [] [] [] [] [] "unused")
                  (T.XConstructor "()" [])
            in not (same (key []) changed) && Q.contextualCache (key []) object
                 && not (Q.contextualCache changed object)
          _ -> False
        _ -> False)
  , ("declared IO write results are canonical unit", all (\p -> case Prim.primitiveSignature p of
      (,) _ field -> E.eqField (terminal field) (T.Applied "IO" (list [T.Applied "()" []])))
      [T.PPutStr,T.PPutStrLn,T.PWriteIntArray,T.PWriteDoubleArray,T.PWriteByteArray,T.PWriteIntTable,T.PWriteFile])
  , ("declared ST write result is canonical unit", case Prim.primitiveSignature T.PWriteSTArray of
      (,) _ field -> E.eqField (terminal field)
        (T.Applied "ST" (list [T.Parameter "s",T.Applied "()" []])))
  , ("all pre-v4 query formats rejected", let object = U.UnitObject (U.UnitInterface "Empty" [] [] [] [] [] [] "unused") (T.XConstructor "()" [])
      in all (\tag -> not (Q.contextualCache (oldTag (B.literal tag) (key [])) object))
           ["MLF-CRATE-QUERY-1","MLF-CRATE-QUERY-2","MLF-CRATE-QUERY-3"])
  , ("actual source canonical datatype fields preserve target type and erasure",
      case C.compile "CanonicalFields.emlf" "data Box = Box [Int] (Int,Int) (); Box [42] (1,2) ()" of
        T.Left _ -> False
        T.Right result -> let term = C.compiledTerm result in
          case XP.parseTerm "CanonicalFields.xmlf" (Pretty.prettyTerm term) of
            T.Left _ -> False
            T.Right restored -> case XC.checkClosed restored of
              T.Left _ -> False
              T.Right ty -> XT.alphaEq ty (C.inferredType result)
                && XS.equalErased (XS.erase term) (XS.erase restored))
  , ("malformed canonical builtin layout parses but is semantically rejected",
      let invalid = T.XWithData [T.DataDecl "[]" ["a"] [T.ConstructorDecl "[]" []]]
            (T.XConstructor "[]" [int])
      in case XP.parseTerm "Malformed.xmlf" (Pretty.prettyTerm invalid) of
        T.Left _ -> False
        T.Right restored -> case XC.checkClosed restored of
          T.Left message -> "invalid data type name: []" `isInfixOf` B.unpack message
          T.Right _ -> False)
  , ("canonical X type roundtrip", all (\ty -> case XP.parseType (Pretty.prettyType ty) of
        T.Right rt -> same (Pretty.prettyType rt) (Pretty.prettyType ty); _ -> False)
      (builtinTypes ++ [T.XCon "[]" [],T.XCon "(,)" [],T.XCon tuple64 []]))
  , ("canonical constructor term roundtrip", all (\term -> case XP.parseTerm "artifact" (Pretty.prettyTerm term) of
        T.Right rt -> same (Pretty.prettyTerm rt) (Pretty.prettyTerm term); _ -> False)
      [T.XConstructor "()" [], T.XConstructor "[]" (list [char]),
       T.XConstructor ":" (list [char]), T.XConstructor "(,)" (list [int,char]),
       T.XConstructor tuple64 (replicate 64 int)])
  , ("raw canonical constructor patterns print and parse", all (\(name,arity,types) ->
      let term = T.XCase (T.XConstructor name types) int
            [T.XAlternative (T.XConstructorPattern name (replicate arity T.Nothing)) (T.XIntTerm 0)]
      in case XP.parseTerm "CanonicalPatterns.xmlf" (Pretty.prettyTerm term) of
        T.Left _ -> False
        T.Right restored -> same (Pretty.prettyTerm restored) (Pretty.prettyTerm term))
      [("()",0,[]),("[]",0,[char]),(":",2,[char]),("(,)",2,[int,char]),(tuple64,64,replicate 64 int)])
  , ("tuple64 datatype field target roundtrip checks closed",
      let term = T.XWithData [T.DataDecl "Wide" [] [T.ConstructorDecl "Wide"
            [T.Applied tuple64 (replicate 64 (T.Applied "Int" []))]]] (T.XIntTerm 0)
      in case XP.parseTerm "Wide.xmlf" (Pretty.prettyTerm term) of
        T.Left _ -> False
        T.Right restored -> same (Pretty.prettyTerm restored) (Pretty.prettyTerm term)
          && isRight (XC.checkClosed restored))
  , ("canonical datatype field metadata roundtrip", roundtrip
      (U.UnitInterface "Example" [] []
        (list [T.DataDecl "Envelope" [] (list [T.ConstructorDecl "Envelope"
          (list [T.Applied "[]" (list [T.Applied "Char" []]), T.Applied "()" [],
                 T.Applied "(,)" (list [T.Applied "Int" [], T.Applied "Char" []])])])])
        [] [] [] "test-object"))
  , ("pooled datatype canonical fields roundtrip", case A.decodeTypePool (U.pack (list [D.prettyDeclaration canonicalFamily])) of
      T.Right pool -> case Map.lookup S.compareInt 0 pool of
        T.Just d -> E.eqDataDecl d canonicalFamily
        _ -> False
      _ -> False)
  , ("checked canonical unit object roundtrip",
      let term = T.XConstructor "()" []
          i = U.UnitInterface "Example" [] [] [] [] [] [] (U.fingerprint (Pretty.prettyTerm term))
          object = U.UnitObject i term
      in isRight (U.decodeObject i (U.encodeObject object)))
  , ("canonical module interface roundtrip", roundtrip (iface [] bindings))
  , ("class signatures and superclass roundtrip", roundtrip (iface classes []))
  , ("canonical crate metadata roundtrip", case A.decodeInterface (A.encodeInterface (crate classes)) of
        T.Right rt -> same (A.encodeInterface rt) (A.encodeInterface (crate classes)); _ -> False)
  , ("semantic fingerprint uses v5 namespace", let
      empty = A.CrateInterface "empty" [] [] [] [] [] [] [] [] [] "" "object" []
      fingerprint tag = U.fingerprint (U.pack (list [tag,"empty",A.encodeExports [],
        A.encodeImports [],A.sourceMetadata [] [] [],U.pack [],"",A.encodeBindings [],A.encodeProtection [],U.pack []]))
      in same (A.semanticFingerprint empty) (fingerprint "MLF-CRATE-SEMANTICS-5")
         && not (same (A.semanticFingerprint empty) (fingerprint "MLF-CRATE-SEMANTICS-4")))
  , ("all pre-v4 module formats rejected", all (\tag -> isLeft (U.decodeInterface (oldTag (B.literal tag) (U.encodeInterface (iface [] []))))) ["MLFI-1","MLFI-2","MLFI-3"])
  , ("all pre-v5 crate formats rejected", all (\tag -> isLeft (A.decodeInterface (oldTag (B.literal tag) (A.encodeInterface (crate []))))) ["MLFCI-1","MLFCI-2","MLFCI-3","MLFCI-4"])
  , ("constructor family changes query key", not (same (key (list [family []]))
      (key (list [family [T.ConstructorDecl "Empty" []]]))))
  , ("nested field type changes query key", not (same (key (list [family []]))
      (key (list [T.DataDecl "Box" (list ["a"]) (list [T.ConstructorDecl "Box" (list [T.Applied "Int" []])])]))))
  , ("builtin family inventory in query key", case U.unpack (key []) of
      T.Right fields -> same (last (toList fields)) (Q.list Q.encodeDatatype D.builtinDeclarations)
      _ -> False)
  , ("canonical ctor stable only in Prelude", same (U.stableName (M.Entity "Prelude" ":" (M.Constructor "[]"))) ":"
      && not (same (U.stableName (M.Entity "User" ":" (M.Constructor "List"))) ":"))

  ]
main = do
  case U.decodeInterface (U.encodeInterface (iface classes [])) of
    T.Left err -> putStrLn ("CLASS DIAGNOSTIC: " ++ B.unpack err)
    _ -> pure ()
  case A.decodeInterface (A.encodeInterface (crate classes)) of
    T.Left err -> putStrLn ("CRATE DIAGNOSTIC: " ++ B.unpack err)
    _ -> pure ()
  results <- mapM (\(name, ok) -> putStrLn ((if ok then "PASS " else "FAIL ") ++ name) >> pure ok) checks
  if and results then putStrLn "item4 artifact contracts: passed" else exitFailure
