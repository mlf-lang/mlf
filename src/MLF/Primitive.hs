-- | Resolved primitive identities and their shared, explicitly polymorphic
-- signatures. Source names are looked up only when lexical lookup fails.
module MLF.Primitive
  ( Primitive (..), primitiveName, lookupPrimitive, lookupTargetPrimitive
  , primitiveSignature, primitiveArity
  ) where

import Data.List (find)
import MLF.Data (Field (..))
import MLF.Kind

data Primitive
  = IOReturn | IOBind | PutStr | PutStrLn | GetLine | PrintInt
  | ConcatString | ShowInt
  | AddInt | SubInt | EqInt | LtInt | EqString | IfThenElse
  deriving (Eq, Ord, Show, Enum, Bounded)

primitiveName :: Primitive -> String
primitiveName p = case p of
  IOReturn -> "ioReturn"
  IOBind -> "ioBind"
  PutStr -> "putStr"
  PutStrLn -> "putStrLn"
  GetLine -> "getLine"
  PrintInt -> "printInt"
  ConcatString -> "concatString"
  ShowInt -> "showInt"
  AddInt -> "addInt"
  SubInt -> "subInt"
  EqInt -> "eqInt"
  LtInt -> "ltInt"
  EqString -> "eqString"
  IfThenElse -> "ifThenElse"

lookupTargetPrimitive :: String -> Maybe Primitive
lookupTargetPrimitive name = find ((== name) . primitiveName) [minBound .. maxBound]

lookupPrimitive :: String -> Maybe Primitive
lookupPrimitive "return" = Just IOReturn
lookupPrimitive "pure" = Just IOReturn
lookupPrimitive "bind" = Just IOBind
lookupPrimitive name = lookupTargetPrimitive name

primitiveSignature :: Primitive -> ([(String,Kind)], Field)
primitiveSignature primitive = case primitive of
  IOReturn -> ([("a",Star)], Function a (io a))
  IOBind -> ([("a",Star),("b",Star)], Function (io a) (Function (Function a (io b)) (io b)))
  PutStr -> ([],Function string (io unit))
  PutStrLn -> ([],Function string (io unit))
  GetLine -> ([],io string)
  PrintInt -> ([],Function int (io unit))
  ConcatString -> ([],Function string (Function string string))
  ShowInt -> ([],Function int string)
  AddInt -> ([],Function int (Function int int))
  SubInt -> ([],Function int (Function int int))
  EqInt -> ([],Function int (Function int bool))
  LtInt -> ([],Function int (Function int bool))
  EqString -> ([],Function string (Function string bool))
  IfThenElse -> ([("a",Star)],Function bool (Function a (Function a a)))
  where
    a = Parameter "a"
    b = Parameter "b"
    io t = Applied "IO" [t]
    string = Applied "String" []
    int = Applied "Int" []
    unit = Applied "Unit" []
    bool = Applied "Bool" []

primitiveArity :: Primitive -> Int
primitiveArity = arity . snd . primitiveSignature
  where
    arity (Function _ b) = 1 + arity b
    arity _ = 0
