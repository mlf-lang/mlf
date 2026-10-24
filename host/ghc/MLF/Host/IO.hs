{-# LANGUAGE ForeignFunctionInterface, ScopedTypeVariables #-}
module MLF.Host.IO where

import Prelude hiding (Int, String)
import qualified Prelude as P
import MLF.Host.Base
import qualified Data.ByteString as B
import qualified Data.Array.IO as A
import qualified Data.Map.Strict as M
import Data.IORef
import Data.Int (Int64)
import Foreign (Ptr, alloca, peek, peekElemOff, nullPtr, free)
import Foreign.C
import Control.Concurrent.MVar
import Control.Exception
import System.IO.Unsafe (unsafePerformIO)
import qualified System.IO as H
import qualified System.Exit as X

foreign import ccall safe "mlf_ghc_host" c_host :: CInt -> CString -> CSize -> CString -> CSize -> Int64 -> Ptr CString -> Ptr CSize -> Ptr Int64 -> IO CInt
foreign import ccall safe "mlf_ghc_shutdown" c_shutdown :: IO ()
-- This is the same RTS provider used by GHC 9.14.1 System.Environment.getArgs.
-- Decode its borrowed bytes as MLF UTF-8, independently of argvEncoding/locale.
foreign import ccall unsafe "getProgArgv" c_args :: Ptr CInt -> Ptr (Ptr CString) -> IO ()

-- Native supervisor and transport metadata have a single coordinator. The
-- lock contains no language values; returned byte buffers have explicit owners.
{-# NOINLINE hostLock #-}
hostLock :: MVar ()
hostLock = unsafePerformIO (newMVar ())
host :: CInt -> String -> String -> Int -> IO (String,Int)
-- A safe foreign call can finish with an asynchronous exception pending.
-- Mask until its owned output has been copied and freed, so cancellation
-- cannot strand the buffer between the return and bracket acquisition.
host operation a b n = withMVar hostLock $ \_ -> mask_ $
  B.useAsCStringLen (utf8 a) $ \(pa,na) ->
  B.useAsCStringLen (utf8 b) $ \(pb,nb) ->
  alloca $ \out -> alloca $ \len -> alloca $ \number -> do
    status <- c_host operation pa (fromIntegral na) pb (fromIntegral nb) (fromInteger n) out len number
    bytes <- peek out
    size <- peek len
    text <- if bytes==nullPtr then pure B.empty else bracket (pure bytes) free (\p -> B.packCStringLen (p,fromIntegral size))
    result <- peek number
    decoded <- evaluate (fromUtf8 text)
    if status/=0 then throwIO (HostError (unpack decoded)) else pure (decoded,toInteger result)
empty :: String
empty = literal ""
hostText :: CInt -> String -> IO String
hostText op a = fst <$> host op a empty 0
hostNumber :: CInt -> String -> IO Int
hostNumber op a = snd <$> host op a empty 0
v_getEnv, v_listDirectory, v_fileDigest, v_processSupervisor :: String -> IO String
v_getEnv = hostText 0
v_listDirectory = hostText 4
v_fileDigest = hostText 8
v_processSupervisor = hostText 9
v_setEnv :: String -> String -> IO Unit
v_setEnv name contents = do
  _ <- evaluate (path name)
  host 1 name contents 0 >> pure Unit
v_unsetEnv :: String -> IO Unit
v_unsetEnv a = host 2 a empty 0 >> pure Unit
v_directoryExists :: String -> IO Bool
v_directoryExists a = (/=0) <$> hostNumber 3 a
v_acquireFileLock :: String -> IO Int
v_acquireFileLock = hostNumber 5
v_releaseFileLock :: Int -> IO Unit
v_releaseFileLock n = do
  _ <- evaluate (bounded "invalid file lock" 2147483647 n)
  host 6 empty empty n  >> pure Unit
v_runProcess :: String -> String -> IO Int
v_runProcess directory specification = do
  _ <- evaluate (path directory)
  snd <$> host 7 directory specification 0

ioErrorAs :: P.String -> IO a -> IO a
ioErrorAs message action = action `catch` (\(_::IOException) -> throwIO (HostError message))
path :: String -> P.FilePath
path s = if '\0' `elem` unpack s then failure "file path contains NUL" else unpack s
v_readFile :: String -> IO String
v_readFile = hostText 13
v_writeFile :: String -> String -> IO Unit
v_writeFile s contents = do
  -- Native writeFile validates the filename before demanding its contents.
  _ <- evaluate (path s)
  _ <- host 14 s contents 0
  pure Unit
v_fileExists :: String -> IO Bool
v_fileExists s = (/=0) <$> hostNumber 10 s
v_canonicalPath :: String -> IO String
v_canonicalPath = hostText 11
v_getExecutablePath :: IO String
v_getExecutablePath = hostText 12 empty
withRawArgs :: (Int -> Ptr CString -> IO a) -> IO a
withRawArgs action = alloca $ \count -> alloca $ \arguments -> do
  c_args count arguments
  n <- peek count
  argv <- peek arguments
  action (max 0 (toInteger n-1)) argv
v_getArgCount :: IO Int
v_getArgCount = withRawArgs (\count _ -> pure count)
v_getArg :: Int -> IO String
v_getArg n = withRawArgs $ \count argv -> do
  i <- evaluate (bounded "argument index out of bounds" (count-1) n)
  bytes <- peekElemOff argv (i+1) >>= B.packCString
  evaluate (fromUtf8 bytes)
write :: H.Handle -> String -> IO Unit
write handle text = ioErrorAs "IO error: output failed" $ do
  B.hPut handle (utf8 text)
  H.hFlush handle
  pure Unit
v_putStr, v_putStrLn, v_putErr :: String -> IO Unit
v_putStr = write H.stdout
v_putStrLn s = write H.stdout (v_concatString s (literal "\n"))
v_putErr = write H.stderr
v_printInt :: Int -> IO Unit
v_printInt = v_putStrLn . v_showInt
v_getContents :: IO String
-- The native operation consumes stdin without taking ownership of the handle.
-- ByteString.getContents would close it, changing subsequent EOF operations.
v_getContents = ioErrorAs "IO error: input failed" (readChunks [] >>= evaluate . fromUtf8)
  where readChunks chunks = do
          chunk <- B.hGetSome H.stdin 32768
          if B.null chunk then pure (B.concat (reverse chunks)) else readChunks (chunk:chunks)
v_getLine :: IO String
v_getLine = ioErrorAs "IO error: getLine reached EOF or failed" $ do
  end <- H.hIsEOF H.stdin
  if end then throwIO (HostError "IO error: getLine reached EOF or failed") else B.hGetLine H.stdin >>= evaluate . fromUtf8
v_exitWith :: Int -> IO a
v_exitWith n = do
  i <- evaluate (bounded "exit status must be between 0 and 255" 255 n)
  X.exitWith (if i==0 then X.ExitSuccess else X.ExitFailure i)

-- Keep native primitive type identities distinct even when two host storage
-- representations coincide. The facade exports these types abstractly.
newtype IntArray = IntArray (A.IOArray P.Int Int)
newtype DoubleArray = DoubleArray (A.IOArray P.Int Double)
newtype ByteArray = ByteArray (A.IOArray P.Int Int)
newArray :: Int -> a -> IO (A.IOArray P.Int a)
newArray n initial = do
  size <- evaluate (bounded "invalid array length" (9223372036854775807 `quot` 8) n)
  value <- evaluate initial
  A.newArray (0,size-1) value
index :: A.IOArray P.Int a -> Int -> IO P.Int
index array n = do
  (_,hi) <- A.getBounds array
  evaluate (bounded "array index out of bounds" (toInteger hi) n)
readArray :: A.IOArray P.Int a -> Int -> IO a
readArray array n = index array n >>= A.readArray array
writeArray :: A.IOArray P.Int a -> Int -> a -> IO Unit
writeArray array n value = do
  i <- index array n
  x <- evaluate value
  A.writeArray array i x
  pure Unit
lengthArray :: A.IOArray P.Int a -> IO Int
lengthArray array = do { (_,hi) <- A.getBounds array; pure (toInteger hi+1) }
v_newIntArray :: Int -> Int -> IO IntArray
v_newIntArray n x = IntArray <$> newArray n x
v_newDoubleArray :: Int -> Double -> IO DoubleArray
v_newDoubleArray n x = DoubleArray <$> newArray n x
v_newByteArray :: Int -> Int -> IO ByteArray
v_newByteArray n x = ByteArray <$> newArray n (toInteger (bounded "byte value must be between 0 and 255" 255 x))
v_readIntArray :: IntArray -> Int -> IO Int
v_readIntArray (IntArray a) = readArray a
v_readDoubleArray :: DoubleArray -> Int -> IO Double
v_readDoubleArray (DoubleArray a) = readArray a
v_readByteArray :: ByteArray -> Int -> IO Int
v_readByteArray (ByteArray a) = readArray a
v_writeIntArray :: IntArray -> Int -> Int -> IO Unit
v_writeIntArray (IntArray a) = writeArray a
v_writeDoubleArray :: DoubleArray -> Int -> Double -> IO Unit
v_writeDoubleArray (DoubleArray a) = writeArray a
v_writeByteArray :: ByteArray -> Int -> Int -> IO Unit
v_writeByteArray (ByteArray a) n x = writeArray a n (toInteger (bounded "byte value must be between 0 and 255" 255 x))
v_lengthIntArray :: IntArray -> IO Int
v_lengthIntArray (IntArray a) = lengthArray a
v_lengthDoubleArray :: DoubleArray -> IO Int
v_lengthDoubleArray (DoubleArray a) = lengthArray a
v_lengthByteArray :: ByteArray -> IO Int
v_lengthByteArray (ByteArray a) = lengthArray a
bytesArray :: B.ByteString -> IO ByteArray
bytesArray bytes = ByteArray <$> A.newListArray (0,B.length bytes-1) (map toInteger (B.unpack bytes))
v_byteArrayFromString :: String -> IO ByteArray
v_byteArrayFromString = bytesArray . utf8
v_getByteLine :: IO ByteArray
v_getByteLine = ioErrorAs "IO error: byte input failed" $ do
  bytes <- readByteLine []
  bytesArray (B.pack (reverse bytes))
  where readByteLine acc = do
          one <- B.hGet H.stdin 1
          if B.null one then pure acc else
            let b=B.head one in if b==10 then pure (b:acc) else readByteLine (b:acc)
v_putBytes :: ByteArray -> Int -> Int -> IO Unit
v_putBytes (ByteArray a) start count = do
  size <- lengthArray a
  i <- evaluate (bounded "byte slice out of bounds" size start)
  n <- evaluate (bounded "byte slice out of bounds" (size-start) count)
  bytes <- mapM (A.readArray a) [i..i+n-1]
  ioErrorAs "IO error: output failed" (B.hPut H.stdout (B.pack (map fromInteger bytes)) >> H.hFlush H.stdout)
  pure Unit
type IntTable = IORef (M.Map Int Int)
v_newIntTable :: IO IntTable
v_newIntTable = newIORef M.empty
v_readIntTable :: IntTable -> Int -> IO Int
v_readIntTable table key = do
  values <- readIORef table
  k <- evaluate key
  pure (M.findWithDefault 0 k values)
v_writeIntTable :: IntTable -> Int -> Int -> IO Unit
v_writeIntTable table key value = do
  values <- readIORef table
  k <- evaluate key
  x <- evaluate value
  writeIORef table (M.insert k x values)
  pure Unit

runEntry :: IO Unit -> IO ()
runEntry entry = ((entry >> pure ()) `finally` c_shutdown)
  `catch` (\(HostError message) -> do
    B.hPut H.stderr (utf8 (literal ("Runtime: "++message++"\n")))
    H.hFlush H.stderr
    X.exitFailure)
