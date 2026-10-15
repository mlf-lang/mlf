-- | Resolved primitive identities and their shared, explicitly polymorphic
-- signatures. Source names are looked up only when lexical lookup fails.
module MLF.Primitive
  ( Primitive (..), primitiveName, lookupPrimitive, lookupTargetPrimitive
  , primitiveSignature, primitiveArity, primitiveStrict
  ) where

import Data.List (find)
import MLF.Data (Field (..))
import MLF.Kind

data Primitive
  = IOReturn | IOBind | PutStr | PutStrLn | GetLine | PrintInt
  | ConcatString | ShowInt
  | AddInt | SubInt | EqInt | LtInt | EqString | IfThenElse
  | MulInt | QuotInt | RemInt | ReadInt
  | AddDouble | SubDouble | MulDouble | DivDouble | SqrtDouble
  | EqDouble | LtDouble | IntToDouble | FormatDouble
  | NewIntArray | ReadIntArray | WriteIntArray | LengthIntArray
  | NewDoubleArray | ReadDoubleArray | WriteDoubleArray | LengthDoubleArray
  | NewByteArray | ReadByteArray | WriteByteArray | LengthByteArray
  | ByteArrayFromString | PutBytes
  | GetByteLine | NewIntTable | ReadIntTable | WriteIntTable
  | AndInt
  | StringLength | StringCodeAt | StringSlice | StringFromCode | CompareString
  | ReadDouble | DoubleToBits | DoubleFromBits | Seq | Panic
  | ReadFile | WriteFile | FileExists | CanonicalPath | GetArgCount | GetArg | PutErr | ExitWith
  | GetExecutablePath | GetContents
  | STReturn | STBind | RunST | NewSTArray | ReadSTArray | WriteSTArray | LengthSTArray
  | GetEnv | SetEnv | UnsetEnv | RunProcess | ListDirectory | DirectoryExists | FileDigest | AcquireFileLock | ReleaseFileLock
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
  MulInt -> "mulInt"
  QuotInt -> "quotInt"
  RemInt -> "remInt"
  ReadInt -> "readInt"
  AddDouble -> "addDouble"
  SubDouble -> "subDouble"
  MulDouble -> "mulDouble"
  DivDouble -> "divDouble"
  SqrtDouble -> "sqrtDouble"
  EqDouble -> "eqDouble"
  LtDouble -> "ltDouble"
  IntToDouble -> "intToDouble"
  FormatDouble -> "formatDouble"
  NewIntArray -> "newIntArray"
  ReadIntArray -> "readIntArray"
  WriteIntArray -> "writeIntArray"
  LengthIntArray -> "lengthIntArray"
  NewDoubleArray -> "newDoubleArray"
  ReadDoubleArray -> "readDoubleArray"
  WriteDoubleArray -> "writeDoubleArray"
  LengthDoubleArray -> "lengthDoubleArray"
  NewByteArray -> "newByteArray"
  ReadByteArray -> "readByteArray"
  WriteByteArray -> "writeByteArray"
  LengthByteArray -> "lengthByteArray"
  ByteArrayFromString -> "byteArrayFromString"
  PutBytes -> "putBytes"
  GetByteLine -> "getByteLine"
  NewIntTable -> "newIntTable"
  ReadIntTable -> "readIntTable"
  WriteIntTable -> "writeIntTable"
  AndInt -> "andInt"
  StringLength -> "stringLength"
  StringCodeAt -> "stringCodeAt"
  StringSlice -> "stringSlice"
  StringFromCode -> "stringFromCode"
  CompareString -> "compareString"
  ReadDouble -> "readDouble"
  DoubleToBits -> "doubleToBits"
  DoubleFromBits -> "doubleFromBits"
  Seq -> "seq"
  Panic -> "panic"
  ReadFile -> "readFile"
  WriteFile -> "writeFile"
  FileExists -> "fileExists"
  CanonicalPath -> "canonicalPath"
  GetArgCount -> "getArgCount"
  GetArg -> "getArg"
  PutErr -> "putErr"
  ExitWith -> "exitWith"
  GetExecutablePath -> "getExecutablePath"
  GetContents -> "getContents"
  STReturn -> "stReturn"
  STBind -> "stBind"
  RunST -> "runST"
  NewSTArray -> "newSTArray"
  ReadSTArray -> "readSTArray"
  WriteSTArray -> "writeSTArray"
  LengthSTArray -> "lengthSTArray"

  GetEnv -> "getEnv"
  SetEnv -> "setEnv"
  UnsetEnv -> "unsetEnv"
  RunProcess -> "runProcess"
  ListDirectory -> "listDirectory"
  DirectoryExists -> "directoryExists"
  FileDigest -> "fileDigest"
  AcquireFileLock -> "acquireFileLock"
  ReleaseFileLock -> "releaseFileLock"

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
  MulInt -> ([],Function int (Function int int))
  QuotInt -> ([],Function int (Function int int))
  RemInt -> ([],Function int (Function int int))
  ReadInt -> ([],Function string int)
  AddDouble -> ([],Function double (Function double double))
  SubDouble -> ([],Function double (Function double double))
  MulDouble -> ([],Function double (Function double double))
  DivDouble -> ([],Function double (Function double double))
  SqrtDouble -> ([],Function double double)
  EqDouble -> ([],Function double (Function double bool))
  LtDouble -> ([],Function double (Function double bool))
  IntToDouble -> ([],Function int double)
  FormatDouble -> ([],Function int (Function double string))
  NewIntArray -> ([],Function int (Function int (io intArray)))
  ReadIntArray -> ([],Function intArray (Function int (io int)))
  WriteIntArray -> ([],Function intArray (Function int (Function int (io unit))))
  LengthIntArray -> ([],Function intArray (io int))
  NewDoubleArray -> ([],Function int (Function double (io doubleArray)))
  ReadDoubleArray -> ([],Function doubleArray (Function int (io double)))
  WriteDoubleArray -> ([],Function doubleArray (Function int (Function double (io unit))))
  LengthDoubleArray -> ([],Function doubleArray (io int))
  NewByteArray -> ([],Function int (Function int (io byteArray)))
  ReadByteArray -> ([],Function byteArray (Function int (io int)))
  WriteByteArray -> ([],Function byteArray (Function int (Function int (io unit))))
  LengthByteArray -> ([],Function byteArray (io int))
  ByteArrayFromString -> ([],Function string (io byteArray))
  PutBytes -> ([],Function byteArray (Function int (Function int (io unit))))
  GetByteLine -> ([],io byteArray)
  NewIntTable -> ([],io intTable)
  ReadIntTable -> ([],Function intTable (Function int (io int)))
  WriteIntTable -> ([],Function intTable (Function int (Function int (io unit))))
  AndInt -> ([],Function int (Function int int))
  StringLength -> ([],Function string int)
  StringCodeAt -> ([],Function string (Function int int))
  StringSlice -> ([],Function string (Function int (Function int string)))
  StringFromCode -> ([],Function int string)
  CompareString -> ([],Function string (Function string int))
  ReadDouble -> ([],Function string double)
  DoubleToBits -> ([],Function double int)
  DoubleFromBits -> ([],Function int double)
  Seq -> ([("a",Star),("b",Star)],Function a (Function b b))
  Panic -> ([("a",Star)],Function string a)
  ReadFile -> ([],Function string (io string))
  WriteFile -> ([],Function string (Function string (io unit)))
  FileExists -> ([],Function string (io bool))
  CanonicalPath -> ([],Function string (io string))
  GetArgCount -> ([],io int)
  GetArg -> ([],Function int (io string))
  PutErr -> ([],Function string (io unit))
  ExitWith -> ([("a",Star)],Function int (io a))
  GetExecutablePath -> ([],io string)
  GetContents -> ([],io string)
  STReturn -> ([("s",Star),("a",Star)],Function a (st a))
  STBind -> ([("s",Star),("a",Star),("b",Star)],Function (st a) (Function (Function a (st b)) (st b)))
  RunST -> ([("a",Star)],Function (Quantified "s" Star (st a)) a)
  NewSTArray -> ([("s",Star),("a",Star)],Function int (Function a (st (stArray a))))
  ReadSTArray -> ([("s",Star),("a",Star)],Function (stArray a) (Function int (st a)))
  WriteSTArray -> ([("s",Star),("a",Star)],Function (stArray a) (Function int (Function a (st unit))))
  LengthSTArray -> ([("s",Star),("a",Star)],Function (stArray a) (st int))
  GetEnv -> ([], (Function string (io string)))
  SetEnv -> ([], (Function string (Function string (io unit))))
  UnsetEnv -> ([], (Function string (io unit)))
  RunProcess -> ([], (Function string (Function string (io int))))
  ListDirectory -> ([], (Function string (io string)))
  DirectoryExists -> ([], (Function string (io bool)))
  FileDigest -> ([], (Function string (io string)))
  AcquireFileLock -> ([], (Function string (io int)))
  ReleaseFileLock -> ([], (Function int (io unit)))
  where
    a = Parameter "a"
    b = Parameter "b"
    io t = Applied "IO" [t]
    st t = Applied "ST" [Parameter "s",t]
    stArray t = Applied "STArray" [Parameter "s",t]
    string = Applied "String" []
    int = Applied "Int" []
    double = Applied "Double" []
    intArray = Applied "IntArray" []
    doubleArray = Applied "DoubleArray" []
    byteArray = Applied "ByteArray" []
    intTable = Applied "IntTable" []
    unit = Applied "Unit" []
    bool = Applied "Bool" []

primitiveArity :: Primitive -> Int
primitiveArity = arity . snd . primitiveSignature
  where
    arity (Function _ b) = 1 + arity b
    arity _ = 0

-- All arguments of these saturated pure primitives are demanded. IO
-- operands stay lazy until the action executes; conditionals are selective.
primitiveStrict :: Primitive -> Bool
primitiveStrict p = p `elem`
  [ConcatString,ShowInt,AddInt,SubInt,EqInt,LtInt,EqString,MulInt,QuotInt,RemInt,AndInt,ReadInt,
   AddDouble,SubDouble,MulDouble,DivDouble,SqrtDouble,EqDouble,LtDouble,IntToDouble,FormatDouble,
   StringLength,StringCodeAt,StringSlice,StringFromCode,CompareString,ReadDouble,DoubleToBits,DoubleFromBits,Panic,RunST]
