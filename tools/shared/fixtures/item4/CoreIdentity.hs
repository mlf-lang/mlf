{-# LANGUAGE OverloadedStrings #-}
-- Host-side regression of the compiler's canonical metadata, not a guest
-- execution receipt. This deliberately keeps old user ADTs distinct.
module Main where
import qualified Prelude as P
import Prelude (IO, Bool(..), ($), (.), (==), (/=), error, putStrLn)
import qualified Bootstrap.Data as D
import qualified Bootstrap.Primitive as Prim
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Kind as K
import qualified MLF.Host.Base as B

check :: P.String -> Bool -> IO ()
check name ok = if ok then P.pure () else error name
isRight (T.Right _) = True
isRight _ = False
list = P.foldr (:) []
toList [] = []
toList ((:) x xs) = x : toList xs
main :: IO ()
main = do
  check "all append-only primitive codes" $
    toList (S.map Prim.primitiveCode Prim.allPrimitives) == [0..106]
  check "metadata arity agrees" $
    S.all (\p -> case Prim.primitiveSignature p of
      (,) _ f -> Prim.primitiveArity p == Prim.fieldArity f) Prim.allPrimitives
  check "managed frame/evidence ABI positions" $
    P.take 9 (P.map (B.unpack . D.constructorName) (toList (S.concatMap D.datatypeConstructors D.builtinDeclarations)))
      == ["MLFLegacyUnit", "()", "[]", ":", "(,)", "(,,)", "(,,,)", "MLFStackFrame", "MLFStackEvidence"]
  check "canonical list constructor inventory" $ case D.lookupDatatype D.emptyDataEnv "[]" of
    T.Right d -> toList (S.map (B.unpack . D.constructorName) (D.datatypeConstructors d)) == ["[]", ":"]
    _ -> False
  check "canonical unit and private tombstone are distinct" $
    isRight (D.lookupDatatype D.emptyDataEnv "()") P.&& isRight (D.lookupDatatype D.emptyDataEnv "MLFLegacyUnit")
      P.&& P.not (isRight (D.lookupDatatype D.emptyDataEnv "Unit"))
  check "user Unit is an ordinary distinct datatype" $ case D.validateDeclarations
    [T.DataDecl "Unit" [] [T.ConstructorDecl "Unit" []]] of
      T.Right env -> isRight (D.lookupDatatype env "()") P.&& isRight (D.lookupDatatype env "Unit")
      _ -> False
  check "full canonical constructor registry has user start69" $
    P.length (toList (S.concatMap D.datatypeConstructors D.builtinDeclarations)) == 69
  check "tuple64 constructor has64 fields" $ case D.lookupDatatype D.emptyDataEnv (B.literal ("(" P.++ P.replicate 63 ',' P.++ ")")) of
    T.Right d -> case toList (D.datatypeConstructors d) of
      [c] -> P.length (toList (D.constructorFields c)) == 64
      _ -> False
    _ -> False
  check "list kind" $ K.eqKind (D.constructorKind D.emptyDataEnv "[]" 0) (T.KArrow T.Star T.Star)
  check "tuple kind" $ K.eqKind (D.constructorKind D.emptyDataEnv "(,)" 0) (T.KArrow T.Star (T.KArrow T.Star T.Star))
  check "custom List remains distinct" $ case D.validateDeclarations
    (list [T.DataDecl "List" (list ["a"]) (list [T.ConstructorDecl "Nil" []])]) of
      T.Right env -> isRight (D.lookupDatatype env "[]") P.&& isRight (D.lookupDatatype env "List")
      _ -> False
  check "builtin Char cannot be redefined" $ case D.validateDeclarations
    (list [T.DataDecl "Char" [] (list [T.ConstructorDecl "Character" []])]) of
      T.Left _ -> True
      _ -> False
  putStrLn "item4 canonical metadata: passed"
