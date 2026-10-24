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
list = P.foldr T.Cons T.Nil
toList T.Nil = []
toList (T.Cons x xs) = x : toList xs
main :: IO ()
main = do
  check "all append-only primitive codes" $
    toList (S.map Prim.primitiveCode Prim.allPrimitives) == [0..102]
  check "metadata arity agrees" $
    S.all (\p -> case Prim.primitiveSignature p of
      T.Pair _ f -> Prim.primitiveArity p == Prim.fieldArity f) Prim.allPrimitives
  check "canonical list constructor inventory" $ case D.lookupDatatype D.emptyDataEnv "[]" of
    T.Right d -> toList (S.map (B.unpack . D.constructorName) (D.datatypeConstructors d)) == ["[]", ":"]
    _ -> False
  check "unit and old unit coexist" $
    isRight (D.lookupDatatype D.emptyDataEnv "()") P.&& isRight (D.lookupDatatype D.emptyDataEnv "Unit")
  check "list kind" $ K.eqKind (D.constructorKind D.emptyDataEnv "[]" 0) (T.KArrow T.Star T.Star)
  check "tuple kind" $ K.eqKind (D.constructorKind D.emptyDataEnv "(,)" 0) (T.KArrow T.Star (T.KArrow T.Star T.Star))
  check "custom List remains distinct" $ case D.validateDeclarations
    (list [T.DataDecl "List" (list ["a"]) (list [T.ConstructorDecl "Nil" T.Nil])]) of
      T.Right env -> isRight (D.lookupDatatype env "[]") P.&& isRight (D.lookupDatatype env "List")
      _ -> False
  check "builtin Char cannot be redefined" $ case D.validateDeclarations
    (list [T.DataDecl "Char" T.Nil (list [T.ConstructorDecl "Character" T.Nil])]) of
      T.Left _ -> True
      _ -> False
  putStrLn "item4 canonical metadata: passed"
