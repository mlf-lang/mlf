-- | A lazy interpreter for checked xMLF erasure. Evaluating a term constructs
-- IO actions; only the action interpreter below can call the backend.
module MLF.Runtime
  ( IOBackend (..), consoleBackend, RuntimeError (..), runTerm, runProgram
  , RuntimeOptions (..), defaultRuntimeOptions
  , runTermWithArguments, runProgramWithArguments, runTermWithOptions, runProgramWithOptions
  ) where

import Control.Exception (IOException, displayException, try)
import qualified Control.Exception as Exception
import Control.Monad (unless)
import qualified Data.Array.IO as Array
import Data.Bifunctor (first)
import Data.Bits ((.&.))
import Data.Char (chr, ord)
import qualified Data.ByteString as BS
import qualified Data.Map.Lazy as Map
import qualified Data.IntMap.Lazy as IM
import qualified Data.HashTable.IO as Hash
import Data.Maybe (fromMaybe)
import qualified Data.List as List
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import Data.Word (Word8, Word64)
import GHC.Float (castDoubleToWord64, castWord64ToDouble)
import System.Directory (canonicalizePath, doesFileExist, doesPathExist)
import qualified System.Environment as Environment
import qualified System.Exit as Exit
import System.IO (hFlush, hPutStr, stdin, stdout, stderr)
import Text.Read (readMaybe)
import qualified MLF.Data as D
import qualified MLF.SystemIO as Sys
import MLF.Primitive
import qualified MLF.X.Check as C
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

data IOBackend = IOBackend
  { readLine :: IO String
  , writeText :: String -> IO ()
  , writeBytes :: BS.ByteString -> IO ()
  , readByteLine :: IO BS.ByteString
  }

-- Keep the stream backend compatible with callers that construct it directly.
-- Command arguments and diagnostic output are configured independently.
data RuntimeOptions = RuntimeOptions
  { runtimeArguments :: [String]
  , runtimeWriteError :: String -> IO ()
  }

defaultRuntimeOptions :: RuntimeOptions
defaultRuntimeOptions = RuntimeOptions [] (\text -> hPutStr stderr text >> hFlush stderr)

consoleBackend :: IOBackend
consoleBackend = IOBackend getLine (\text -> hPutStr stdout text >> hFlush stdout)
  (\bytes -> BS.hPut stdout bytes >> hFlush stdout) (rawLine [])
  where
    -- The reference interpreter preserves LF, a final unterminated line and
    -- arbitrary bytes. An empty result denotes EOF, not a blank line.
    rawLine bytes = do
      next <- BS.hGet stdin 1
      case BS.uncons next of
        Nothing -> pure (BS.pack (reverse bytes))
        Just (10,_) -> pure (BS.pack (reverse (10:bytes)))
        Just (b,_) -> rawLine (b:bytes)

newtype RuntimeError = RuntimeError String deriving Eq
instance Show RuntimeError where show (RuntimeError message) = message

type Result a = Either RuntimeError a
type Thunk = Result Value
type Env = Map.Map X.Name Thunk

data Value
  = IntegerValue Integer
  | DoubleValue Double
  | IntArrayValue Int (Array.IOArray Int Integer)
  | DoubleArrayValue Int (Array.IOUArray Int Double)
  | ByteArrayValue Int (Array.IOUArray Int Word8)
  | IntTableValue (Hash.BasicHashTable Integer Integer)
  | BooleanValue Bool
  | StringValue String
  | Closure Env X.Name X.Erased
  | ConstructorValue String [Thunk]
  | PrimitiveValue Primitive [Thunk]
  | ActionValue Action
  | STActionValue Primitive [Thunk]
  | STArrayValue Int

data Action
  = ReturnAction Thunk
  | BindAction Thunk Thunk
  | ReadLineAction
  | WriteAction Bool Thunk
  | PrintIntAction Thunk
  | ArrayAction Primitive [Thunk]
  | SystemAction Primitive [Thunk]

failure :: String -> Result a
failure = Left . RuntimeError

-- | Check even caller-constructed target terms before executing any effects.
-- The result value of the final IO action is discarded, as with a main action.
runTerm :: IOBackend -> X.Term -> IO (Result ())
runTerm = runTermWithOptions defaultRuntimeOptions

-- | The native executable entry convention: execute IO, or evaluate a pure
-- program to weak head normal form without printing or forcing its fields.
runProgram :: IOBackend -> X.Term -> IO (Result ())
runProgram = runProgramWithOptions defaultRuntimeOptions

runTermWithArguments :: [String] -> IOBackend -> X.Term -> IO (Result ())
runTermWithArguments args = runTermWithOptions defaultRuntimeOptions { runtimeArguments = args }

runProgramWithArguments :: [String] -> IOBackend -> X.Term -> IO (Result ())
runProgramWithArguments args = runProgramWithOptions defaultRuntimeOptions { runtimeArguments = args }

runTermWithOptions :: RuntimeOptions -> IOBackend -> X.Term -> IO (Result ())
runTermWithOptions = runEntry True

runProgramWithOptions :: RuntimeOptions -> IOBackend -> X.Term -> IO (Result ())
runProgramWithOptions = runEntry False

runEntry :: Bool -> RuntimeOptions -> IOBackend -> X.Term -> IO (Result ())
runEntry requireIO options backend term = case prepare of
  Left err -> pure (Left err)
  Right (ds,action) -> do
    let value = evaluate ds Map.empty (X.erase term)
        execute | action = fmap (fmap (const ())) (runAction options ds backend value)
                | otherwise = Exception.evaluate (value >>= \v -> v `seq` Right ())
    outcome <- try execute
      :: IO (Either IOException (Result ()))
    pure (either (Left . RuntimeError . ("IO error: " ++) . displayException) id outcome)
  where
    prepare = do
      ty <- first (RuntimeError . ("target verification failed: " ++)) (C.checkClosed term)
      unless (not requireIO || isIO ty) (failure "program must have type IO a to run")
      ds <- first RuntimeError (D.validateDeclarations (case term of X.WithData declarations _ -> declarations; _ -> []))
      pure (ds,isIO ty)
    isIO (T.Forall _ _ body) = isIO body
    isIO (T.Con "IO" [_]) = True
    isIO _ = False

evaluate :: D.DataEnv -> Env -> X.Erased -> Thunk
evaluate ds env expression = case expression of
  X.EVar n -> maybe (failure ("unbound runtime variable: " ++ X.nameHint n)) id (Map.lookup n env)
  X.EAbs n body -> pure (Closure env n body)
  X.EApp f a -> evaluate ds env f >>= \function -> apply ds function (evaluate ds env a)
  X.ELet n a b -> evaluate ds (Map.insert n (evaluate ds env a) env) b
  X.ELetRec bindings body ->
    let recursive = Map.union (Map.fromList [(n,evaluate ds recursive rhs) | (n,rhs) <- bindings]) env
    in evaluate ds recursive body
  X.EInt n -> pure (IntegerValue n)
  X.EDouble n -> pure (DoubleValue n)
  X.EBool b -> pure (BooleanValue b)
  X.EString s -> pure (StringValue s)
  X.EPrimitive p -> primitive ds p []
  X.EConstructor c -> D.lookupConstructor ds c `orError` \_ -> pure (ConstructorValue c [])
  X.ECase scrutinee alternatives -> choose alternatives
    where
      value = evaluate ds env scrutinee
      choose [] = failure "non-exhaustive runtime case"
      choose (X.ErasedAlternative pattern' body:rest) = case pattern' of
        X.DefaultPattern name -> evaluate ds (maybe env (\n -> Map.insert n value env) name) body
        X.ConstructorPattern c names -> do
          v <- value
          case v of
            ConstructorValue tag fields | c == tag -> do
              unless (length names == length fields) (failure "runtime constructor pattern arity mismatch")
              let locals = Map.fromList [(n,field) | (Just n,field) <- zip names fields]
              evaluate ds (Map.union locals env) body
            ConstructorValue _ _ -> choose rest
            _ -> failure "constructor pattern matched a non-data value"
  X.EEvidenceHole _ -> failure "unresolved runtime dictionary evidence"

orError :: Either String a -> (a -> Result b) -> Result b
orError value next = first RuntimeError value >>= next

apply :: D.DataEnv -> Value -> Thunk -> Thunk
apply ds function argument = case function of
  Closure env name body -> evaluate ds (Map.insert name argument env) body
  ConstructorValue name fields -> D.lookupConstructor ds name `orError` \(_,constructor) -> do
    unless (length fields < length (D.constructorFields constructor)) (failure "runtime constructor overapplication")
    pure (ConstructorValue name (fields ++ [argument]))
  PrimitiveValue p arguments -> primitive ds p (arguments ++ [argument])
  _ -> failure "runtime application of a non-function"

primitive :: D.DataEnv -> Primitive -> [Thunk] -> Thunk
primitive ds p arguments
  | length arguments < primitiveArity p = pure (PrimitiveValue p arguments)
  | length arguments == primitiveArity p && p `elem`
      [ReadFile,WriteFile,FileExists,CanonicalPath,GetArgCount,GetArg,PutErr,ExitWith,GetExecutablePath,GetContents,GetEnv,SetEnv,UnsetEnv,RunProcess,ListDirectory,DirectoryExists,FileDigest,AcquireFileLock,ReleaseFileLock] =
      pure (ActionValue (SystemAction p arguments))
  | length arguments == primitiveArity p && p `elem`
      [NewIntArray,ReadIntArray,WriteIntArray,LengthIntArray,
       NewDoubleArray,ReadDoubleArray,WriteDoubleArray,LengthDoubleArray,
       NewByteArray,ReadByteArray,WriteByteArray,LengthByteArray,ByteArrayFromString,PutBytes,GetByteLine,NewIntTable,ReadIntTable,WriteIntTable] =
      pure (ActionValue (ArrayAction p arguments))
  | length arguments == primitiveArity p && p `elem`
      [STReturn,STBind,NewSTArray,ReadSTArray,WriteSTArray,LengthSTArray] =
      pure (STActionValue p arguments)
  | otherwise = case (p,arguments) of
      (RunST,[action]) -> runStateRegion ds action
      (IOReturn,[value]) -> pure (ActionValue (ReturnAction value))
      (IOBind,[action,next]) -> pure (ActionValue (BindAction action next))
      (GetLine,[]) -> pure (ActionValue ReadLineAction)
      (PutStr,[value]) -> pure (ActionValue (WriteAction False value))
      (PutStrLn,[value]) -> pure (ActionValue (WriteAction True value))
      (PrintInt,[value]) -> pure (ActionValue (PrintIntAction value))
      (ConcatString,[a,b]) -> StringValue <$> ((++) <$> string a <*> string b)
      (ShowInt,[value]) -> StringValue . show <$> integer value
      (AddInt,[a,b]) -> IntegerValue <$> ((+) <$> integer a <*> integer b)
      (SubInt,[a,b]) -> IntegerValue <$> ((-) <$> integer a <*> integer b)
      (MulInt,[a,b]) -> IntegerValue <$> ((*) <$> integer a <*> integer b)
      (AndInt,[a,b]) -> IntegerValue <$> ((.&.) <$> integer a <*> integer b)
      (QuotInt,[a,b]) -> divide quot a b
      (RemInt,[a,b]) -> divide rem a b
      (ReadInt,[a]) -> string a >>= parseInteger
      (StringLength,[a]) -> IntegerValue . toInteger . length <$> string a
      (StringCodeAt,[a,b]) -> do
        s <- string a
        i <- integer b
        if i < 0 || i >= toInteger (length s) then failure "string index out of bounds"
          else pure (IntegerValue (toInteger (ord (s !! fromInteger i))))
      (StringSlice,[a,b,c]) -> do
        s <- string a
        i <- integer b
        n <- integer c
        if i < 0 || i > toInteger (length s) || n < 0 || n > toInteger (length s)-i
          then failure "string slice out of bounds"
          else pure (StringValue (take (fromInteger n) (drop (fromInteger i) s)))
      (StringFromCode,[a]) -> do
        n <- integer a
        if n < 0 || n > 0x10ffff || (n >= 0xd800 && n <= 0xdfff)
          then failure "invalid Unicode scalar" else pure (StringValue [chr (fromInteger n)])
      (CompareString,[a,b]) -> do
        x <- string a
        y <- string b
        pure (IntegerValue (case compare x y of LT -> -1; EQ -> 0; GT -> 1))
      (ReadDouble,[a]) -> do
        s <- string a
        if decimal s then maybe (failure "invalid Double input") (pure . DoubleValue)
          (readMaybe (case s of '+':rest -> rest; _ -> s))
          else failure "invalid Double input"
      (DoubleToBits,[a]) -> IntegerValue . toInteger . castDoubleToWord64 <$> double a
      (DoubleFromBits,[a]) -> do
        n <- integer a
        if n < 0 || n > toInteger (maxBound :: Word64) then failure "Double bit pattern out of bounds"
          else pure (DoubleValue (castWord64ToDouble (fromInteger n)))
      (Seq,[a,b]) -> a >>= \v -> v `seq` b
      (Panic,[a]) -> string a >>= failure
      (AddDouble,[a,b]) -> DoubleValue <$> ((+) <$> double a <*> double b)
      (SubDouble,[a,b]) -> DoubleValue <$> ((-) <$> double a <*> double b)
      (MulDouble,[a,b]) -> DoubleValue <$> ((*) <$> double a <*> double b)
      (DivDouble,[a,b]) -> DoubleValue <$> ((/) <$> double a <*> double b)
      (SqrtDouble,[a]) -> DoubleValue . sqrt <$> double a
      (EqDouble,[a,b]) -> BooleanValue <$> ((==) <$> double a <*> double b)
      (LtDouble,[a,b]) -> BooleanValue <$> ((<) <$> double a <*> double b)
      (IntToDouble,[a]) -> DoubleValue . fromInteger <$> integer a
      (FormatDouble,[a,b]) -> do
        places <- integer a
        n <- double b
        if places < 0 || places > 17 then failure "Double precision must be between 0 and 17"
          else pure (StringValue (fixedDouble (fromInteger places) n))
      (EqInt,[a,b]) -> BooleanValue <$> ((==) <$> integer a <*> integer b)
      (LtInt,[a,b]) -> BooleanValue <$> ((<) <$> integer a <*> integer b)
      (EqString,[a,b]) -> BooleanValue <$> ((==) <$> string a <*> string b)
      -- Branches are thunks: only the selected branch is evaluated, and an
      -- IO-valued branch still needs to be executed by runAction.
      (IfThenElse,[condition,yes,no]) -> do
        choice <- boolean condition
        if choice then yes else no
      _ -> failure ("runtime primitive arity mismatch: " ++ primitiveName p)
  where
    divide op a b = do
      x <- integer a
      y <- integer b
      if y == 0 then failure "integer division by zero" else pure (IntegerValue (op x y))
    parseInteger text =
      let (sign,digits) = case text of '-':xs -> (-1,xs); '+':xs -> (1,xs); _ -> (1,text)
      in if null digits || any (\c -> c < '0' || c > '9') digits
         then failure "invalid integer input"
         else pure (IntegerValue (sign * List.foldl' (\n c -> 10*n + toInteger (fromEnum c - fromEnum '0')) 0 digits))

-- A locale-independent, whole-input decimal grammar shared with the native
-- parser. Binary64 overflow/underflow follow the normal IEEE conversion.
decimal :: String -> Bool
decimal input = case span digit (sign input) of
  ([],_) -> False
  (_,'.':rest) -> case span digit rest of ([],_) -> False; (_,xs) -> decimalExponent xs
  (_,rest) -> decimalExponent rest
  where
    digit c = c >= '0' && c <= '9'
    sign ('+':xs) = xs
    sign ('-':xs) = xs
    sign xs = xs
    decimalExponent [] = True
    decimalExponent (e:xs) | e == 'e' || e == 'E' = let digits = sign xs in not (null digits) && all digit digits
    decimalExponent _ = False

-- Round the exact binary value to nearest, ties to even. This agrees with
-- printf in the native runtime, including negative zero, without depending
-- on a host locale or decimal-to-binary round trips.
fixedDouble :: Int -> Double -> String
fixedDouble places n
  | isNaN n = "NaN"
  | isInfinite n = if n < 0 then "-Infinity" else "Infinity"
  | otherwise = sign ++ whole ++ fraction
  where
    sign = if n < 0 || isNegativeZero n then "-" else ""
    scaled = round (toRational (abs n) * fromInteger (10 ^ places)) :: Integer
    digits = show scaled
    padded = replicate (max 0 (places + 1 - length digits)) '0' ++ digits
    (whole,rest) = splitAt (length padded - places) padded
    fraction = if places == 0 then "" else '.' : rest

string :: Thunk -> Result String
string thunk = do
  value <- thunk
  case value of
    StringValue s -> pure s
    _ -> failure "runtime primitive expected String"

integer :: Thunk -> Result Integer
integer thunk = do
  value <- thunk
  case value of
    IntegerValue n -> pure n
    _ -> failure "runtime primitive expected Int"

double :: Thunk -> Result Double
double thunk = do
  value <- thunk
  case value of
    DoubleValue n -> pure n
    _ -> failure "runtime primitive expected Double"

intArray :: Thunk -> Result (Int,Array.IOArray Int Integer)
intArray thunk = do
  value <- thunk
  case value of
    IntArrayValue n a -> pure (n,a)
    _ -> failure "runtime primitive expected IntArray"

doubleArray :: Thunk -> Result (Int,Array.IOUArray Int Double)
doubleArray thunk = do
  value <- thunk
  case value of
    DoubleArrayValue n a -> pure (n,a)
    _ -> failure "runtime primitive expected DoubleArray"

arraySize :: Thunk -> Result Int
arraySize thunk = do
  n <- integer thunk
  if n < 0 || n > toInteger (maxBound :: Int) `quot` 8
    then failure "invalid array length" else pure (fromInteger n)

byteArray :: Thunk -> Result (Int,Array.IOUArray Int Word8)
byteArray thunk = do
  value <- thunk
  case value of
    ByteArrayValue n a -> pure (n,a)
    _ -> failure "runtime primitive expected ByteArray"

intTable :: Thunk -> Result (Hash.BasicHashTable Integer Integer)
intTable thunk = do
  value <- thunk
  case value of
    IntTableValue t -> pure t
    _ -> failure "runtime primitive expected IntTable"

byte :: Thunk -> Result Word8
byte thunk = do
  n <- integer thunk
  if n < 0 || n > 255 then failure "byte value must be between 0 and 255" else pure (fromInteger n)

byteSlice :: Int -> Thunk -> Thunk -> Result (Int,Int)
byteSlice size offset count = do
  start <- integer offset
  unless (start >= 0 && start <= toInteger size) (failure "byte slice out of bounds")
  length' <- integer count
  unless (length' >= 0 && length' <= toInteger size-start) (failure "byte slice out of bounds")
  pure (fromInteger start,fromInteger length')

arrayIndex :: Int -> Thunk -> Result Int
arrayIndex size thunk = do
  n <- integer thunk
  if n < 0 || n >= toInteger size then failure "array index out of bounds" else pure (fromInteger n)

boolean :: Thunk -> Result Bool
boolean thunk = do
  value <- thunk
  case value of
    BooleanValue b -> pure b
    _ -> failure "runtime primitive expected Bool"

runAction :: RuntimeOptions -> D.DataEnv -> IOBackend -> Thunk -> IO (Result Thunk)
runAction options ds backend thunk = case thunk of
  Left err -> pure (Left err)
  Right (ActionValue action) -> perform action
  Right _ -> pure (failure "runtime expected an IO action")
  where
    unit = pure (ConstructorValue "Unit" [])
    perform (ReturnAction value) = pure (Right value)
    perform (BindAction firstAction next) = do
      result <- runAction options ds backend firstAction
      case result of
        Left err -> pure (Left err)
        Right value -> runAction options ds backend (next >>= \function -> apply ds function value)
    perform ReadLineAction = do
      line <- readLine backend
      pure (Right (pure (StringValue line)))
    perform (WriteAction newline value) = case string value of
      Left err -> pure (Left err)
      Right text -> do
        writeText backend (text ++ if newline then "\n" else "")
        pure (Right unit)
    perform (PrintIntAction value) = case integer value of
      Left err -> pure (Left err)
      Right n -> do
        writeText backend (show n ++ "\n")
        pure (Right unit)
    perform (SystemAction p arguments) = case (p,arguments) of
      (ReadFile,[name]) -> checked (path name) $ \file -> systemIO "file read failed" $ do
        bytes <- BS.readFile file
        pure $ case Text.decodeUtf8' bytes of
          Left _ -> failure "IO error: invalid UTF-8 input"
          Right s -> Right (pure (StringValue (Text.unpack s)))
      (WriteFile,[name,contents]) -> checked ((,) <$> path name <*> string contents) $ \(file,s) ->
        systemIO "file write failed" (BS.writeFile file (Text.encodeUtf8 (Text.pack s)) >> pure (Right unit))
      (FileExists,[name]) -> checked (path name) $ \file ->
        systemIO "file existence check failed" (Right . pure . BooleanValue <$> doesFileExist file)
      (CanonicalPath,[name]) -> checked (path name) $ \file -> systemIO "canonical path failed" $ do
        exists <- doesPathExist file
        if exists then Right . pure . StringValue <$> canonicalizePath file
          else pure (failure "IO error: canonical path failed")
      (GetArgCount,[]) -> pure (Right (pure (IntegerValue (toInteger (length (runtimeArguments options))))))
      (GetArg,[index]) -> checked (integer index) $ \i ->
        if i < 0 || i >= toInteger (length (runtimeArguments options))
          then pure (failure "argument index out of bounds")
          else pure (Right (pure (StringValue (runtimeArguments options !! fromInteger i))))
      (PutErr,[text]) -> checked (string text) $ \s -> do
        runtimeWriteError options s
        pure (Right unit)
      (ExitWith,[code]) -> checked (integer code) $ \n ->
        if n < 0 || n > 255 then pure (failure "exit status must be between 0 and 255")
          else Exit.exitWith (if n == 0 then Exit.ExitSuccess else Exit.ExitFailure (fromInteger n))
      (GetExecutablePath,[]) -> systemIO "executable path failed" $
        Right . pure . StringValue <$> (Environment.getExecutablePath >>= canonicalizePath)
      (GetContents,[]) -> do
        bytes <- contents []
        pure $ case Text.decodeUtf8' bytes of
          Left _ -> failure "IO error: invalid UTF-8 input"
          Right s -> Right (pure (StringValue (Text.unpack s)))
      (GetEnv,[a]) -> checked (path a) $ \x -> systemIO "getEnv failed" (Right . pure . StringValue <$> Sys.getEnv x)
      (SetEnv,[a,b]) -> checked (((,) <$> path a <*> string b)) $ \(x,y) -> systemIO "setEnv failed" (Sys.setEnv x y >> pure (Right unit))
      (UnsetEnv,[a]) -> checked (path a) $ \x -> systemIO "unsetEnv failed" (Sys.unsetEnv x >> pure (Right unit))
      (RunProcess,[a,b]) -> checked (((,) <$> path a <*> string b)) $ \(x,y) -> systemIO "runProcess failed" (Right . pure . IntegerValue <$> Sys.runProcess x y)
      (ListDirectory,[a]) -> checked (path a) $ \x -> systemIO "listDirectory failed" (Right . pure . StringValue <$> Sys.listDirectory x)
      (DirectoryExists,[a]) -> checked (path a) $ \x -> systemIO "directoryExists failed" (Right . pure . BooleanValue <$> Sys.directoryExists x)
      (FileDigest,[a]) -> checked (path a) $ \x -> systemIO "fileDigest failed" (Right . pure . StringValue <$> Sys.fileDigest x)
      (AcquireFileLock,[a]) -> checked (path a) $ \x -> systemIO "acquireFileLock failed" (Right . pure . IntegerValue <$> Sys.acquireFileLock x)
      (ReleaseFileLock,[a]) -> checked (integer a) $ \x -> systemIO "releaseFileLock failed" (Sys.releaseFileLock x >> pure (Right unit))
      _ -> pure (failure "runtime system primitive arity mismatch")
    perform (ArrayAction p arguments) = case (p,arguments) of
      (GetByteLine,[]) -> do
        bytes <- readByteLine backend
        let n = BS.length bytes
        a <- Array.newListArray (0,n-1) (BS.unpack bytes)
        pure (Right (pure (ByteArrayValue n a)))
      (NewIntTable,[]) -> Right . pure . IntTableValue <$> Hash.new
      (ReadIntTable,[table,key]) -> checked ((,) <$> intTable table <*> integer key) $ \(t,k) -> do
        x <- Hash.lookup t k
        pure (Right (pure (IntegerValue (fromMaybe 0 x))))
      (WriteIntTable,[table,key,entry]) -> checked (do
        t <- intTable table; k <- integer key; x <- integer entry; pure (t,k,x)) $ \(t,k,x) -> do
          k `seq` x `seq` Hash.insert t k x
          pure (Right unit)
      (NewByteArray,[size,initial]) -> checked ((,) <$> arraySize size <*> byte initial) $ \(n,x) -> do
        a <- x `seq` Array.newArray (0,n-1) x
        pure (Right (pure (ByteArrayValue n a)))
      (ByteArrayFromString,[text]) -> checked (string text) $ \s -> do
        let bytes = Text.encodeUtf8 (Text.pack s)
            n = BS.length bytes
        a <- Array.newListArray (0,n-1) (BS.unpack bytes)
        pure (Right (pure (ByteArrayValue n a)))
      (ReadByteArray,[array,index]) -> checked (do
        (n,a) <- byteArray array; i <- arrayIndex n index; pure (a,i)) $ \(a,i) -> do
          x <- Array.readArray a i
          pure (Right (pure (IntegerValue (toInteger x))))
      (WriteByteArray,[array,index,entry]) -> checked (do
        (n,a) <- byteArray array; i <- arrayIndex n index; x <- byte entry; pure (a,i,x)) $ \(a,i,x) -> do
          x `seq` Array.writeArray a i x
          pure (Right unit)
      (LengthByteArray,[array]) -> pure (fmap (pure . IntegerValue . toInteger . fst) (byteArray array))
      (PutBytes,[array,offset,count]) -> checked (do
        (n,a) <- byteArray array; (i,k) <- byteSlice n offset count; pure (a,i,k)) $ \(a,i,k) -> do
          bytes <- BS.pack <$> mapM (Array.readArray a) [i..i+k-1]
          writeBytes backend bytes
          pure (Right unit)
      (NewIntArray,[size,initial]) -> checked ((,) <$> arraySize size <*> integer initial) $ \(n,x) -> do
        a <- x `seq` Array.newArray (0,n-1) x
        pure (Right (pure (IntArrayValue n a)))
      (NewDoubleArray,[size,initial]) -> checked ((,) <$> arraySize size <*> double initial) $ \(n,x) -> do
        a <- x `seq` Array.newArray (0,n-1) x
        pure (Right (pure (DoubleArrayValue n a)))
      (ReadIntArray,[array,index]) -> checked (do
        (n,a) <- intArray array; i <- arrayIndex n index; pure (a,i)) $ \(a,i) -> do
          x <- Array.readArray a i
          pure (Right (pure (IntegerValue x)))
      (ReadDoubleArray,[array,index]) -> checked (do
        (n,a) <- doubleArray array; i <- arrayIndex n index; pure (a,i)) $ \(a,i) -> do
          x <- Array.readArray a i
          pure (Right (pure (DoubleValue x)))
      (WriteIntArray,[array,index,entry]) -> checked (do
        (n,a) <- intArray array; i <- arrayIndex n index; x <- integer entry; pure (a,i,x)) $ \(a,i,x) -> do
          x `seq` Array.writeArray a i x
          pure (Right unit)
      (WriteDoubleArray,[array,index,entry]) -> checked (do
        (n,a) <- doubleArray array; i <- arrayIndex n index; x <- double entry; pure (a,i,x)) $ \(a,i,x) -> do
          x `seq` Array.writeArray a i x
          pure (Right unit)
      (LengthIntArray,[array]) -> pure (fmap (pure . IntegerValue . toInteger . fst) (intArray array))
      (LengthDoubleArray,[array]) -> pure (fmap (pure . IntegerValue . toInteger . fst) (doubleArray array))
      _ -> pure (failure "runtime array primitive arity mismatch")
    checked (Left err) _ = pure (Left err)
    checked (Right a) next = next a
    path argument = do
      name <- string argument
      if '\0' `elem` name then failure "file path contains NUL" else pure name
    systemIO message action = do
      result <- try action
      pure (either (const (failure ("IO error: " ++ message))) id (result :: Either IOException (Result Thunk)))
    contents chunks = do
      line <- readByteLine backend
      if BS.null line then pure (BS.concat (reverse chunks)) else contents (line:chunks)


-- A reference semantics for local state: no host IO or unsafe coercion is
-- needed. Cells hold shared lazy values; reading snapshots the stored thunk
-- before a later write changes the persistent store. Each runST has its own
-- store and continuation stack, so nested regions remain independent.
data RegionArray = RegionArray !Int Thunk (IM.IntMap Thunk)
data RegionStore = RegionStore !Int (IM.IntMap RegionArray)

runStateRegion :: D.DataEnv -> Thunk -> Thunk
runStateRegion ds action = run (RegionStore 0 IM.empty) [] action
  where
    run store continuations current = do
      operation <- current
      case operation of
        STActionValue STBind [firstAction,next] -> run store (next:continuations) firstAction
        STActionValue p args -> do
          (result,nextStore) <- step store p args
          case continuations of
            [] -> result
            next:rest -> run nextStore rest (next >>= \function -> apply ds function result)
        _ -> failure "invalid ST action"
    step store p args = case (p,args) of
      (STReturn,[entry]) -> pure (entry,store)
      (NewSTArray,[size,initial]) -> do
        count <- arraySize size
        case store of
          RegionStore fresh arrays ->
            if fresh == maxBound then failure "too many ST arrays" else
            let array = RegionArray count initial IM.empty
            in pure (pure (STArrayValue fresh),RegionStore (fresh+1) (IM.insert fresh array arrays))
      (ReadSTArray,[array,index]) -> do
        (_,RegionArray count initial cells) <- regionArray store array
        offset <- arrayIndex count index
        pure (IM.findWithDefault initial offset cells,store)
      (WriteSTArray,[array,index,entry]) -> do
        (identity,RegionArray count initial cells) <- regionArray store array
        offset <- arrayIndex count index
        case store of
          RegionStore fresh arrays ->
            let changed = RegionArray count initial (IM.insert offset entry cells)
            in pure (pure (ConstructorValue "Unit" []),RegionStore fresh (IM.insert identity changed arrays))
      (LengthSTArray,[array]) -> do
        (_,RegionArray count _ _) <- regionArray store array
        pure (pure (IntegerValue (toInteger count)),store)
      _ -> failure "runtime ST primitive arity mismatch"
    regionArray (RegionStore _ arrays) thunk = do
      value <- thunk
      case value of
        STArrayValue identity -> case IM.lookup identity arrays of
          Just array -> pure (identity,array)
          Nothing -> failure "ST array is outside its region"
        _ -> failure "runtime primitive expected STArray"
