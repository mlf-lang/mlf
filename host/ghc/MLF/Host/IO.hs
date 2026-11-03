{-# LANGUAGE ForeignFunctionInterface, ScopedTypeVariables, ImplicitParams, CPP #-}
module MLF.Host.IO where

import Prelude hiding (Int, String)
import qualified Prelude as P
import MLF.Host.Base
import qualified Data.ByteString as B
import qualified Data.Array.IO as A
import qualified Data.Array.Base as AB
#include "MachDeps.h"
#if WORD_SIZE_IN_BITS >= 64 && !defined(MLF_TEST_NARROW_INT_TABLE)
import qualified Data.IntMap.Lazy as M
#else
import qualified Data.Map.Lazy as M
#endif
import Data.IORef
import Data.Int (Int64)
import Data.Word (Word8)
import Foreign.Marshal.Alloc (mallocBytes)
import Foreign.ForeignPtr (ForeignPtr, mallocForeignPtrBytes, withForeignPtr)
import Foreign.Marshal.Utils (copyBytes, fillBytes)
import Foreign (Ptr, alloca, peek, peekElemOff, pokeElemOff, nullPtr, free, castPtr, plusPtr)
import Foreign.C
import Control.Concurrent.MVar
import Control.Exception
import System.IO.Unsafe (unsafePerformIO)
import qualified System.IO.Error as E
import qualified GHC.Stack as Stack
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
    status <- c_host operation pa (fromIntegral na) pb (fromIntegral nb) (fromIntegral n) out len number
    bytes <- peek out
    size <- peek len
    text <- if bytes==nullPtr then pure B.empty else bracket (pure bytes) free (\p -> B.packCStringLen (p,fromIntegral size))
    result <- peek number
    decoded <- evaluate (fromUtf8 text)
    if status/=0 then throwIO (HostError (unpack decoded)) else pure (decoded,fromIntegral result)
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
v_setEnv :: String -> String -> IO ()
v_setEnv name contents = do
  _ <- evaluate (path name)
  host 1 name contents 0 >> pure ()
v_unsetEnv :: String -> IO ()
v_unsetEnv a = host 2 a empty 0 >> pure ()
v_directoryExists :: String -> IO Bool
v_directoryExists a = (/=0) <$> hostNumber 3 a
v_acquireFileLock :: String -> IO Int
v_acquireFileLock = hostNumber 5
v_releaseFileLock :: Int -> IO ()
v_releaseFileLock n = do
  _ <- evaluate (bounded "invalid file lock" 2147483647 n)
  host 6 empty empty n  >> pure ()
v_runProcess :: String -> String -> IO Int
v_runProcess directory specification = do
  _ <- evaluate (path directory)
  snd <$> host 7 directory specification 0

-- Narrow standard IOException boundary. Existing HostError/panic adapters
-- deliberately remain outside this catch; this is not a universal exception API.
v_userError :: [Char] -> IOError
v_userError = E.userError
v_ioError :: Stack.HasCallStack => IOError -> IO a
v_ioError error = Stack.withFrozenCallStack (E.ioError error)
-- Compiler-supplied source evidence is captured only when this action runs.
-- A caught error does not demand its stack or message. Use the real GHC
-- exception-context machinery; hide private adapter call sites.
v_ioErrorWithStack :: IOError -> MLFCallStack -> IO a
v_ioErrorWithStack error stack =
  let ?callStack = stack in Stack.withFrozenCallStack (throwIO error)
v_catchIOError :: IO a -> (IOError -> IO a) -> IO a
v_catchIOError = E.catchIOError
v_ioeGetErrorString :: IOError -> [Char]
v_ioeGetErrorString = E.ioeGetErrorString

ioErrorAs :: P.String -> IO a -> IO a
ioErrorAs message action = action `catch` (\(_::IOException) -> throwIO (HostError message))
path :: String -> P.FilePath
path s = if '\0' `elem` unpack s then failure "file path contains NUL" else unpack s
v_readFile :: String -> IO String
v_readFile = hostText 13
v_writeFile :: String -> String -> IO ()
v_writeFile s contents = do
  -- Native writeFile validates the filename before demanding its contents.
  _ <- evaluate (path s)
  _ <- host 14 s contents 0
  pure ()
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
  action (max 0 (fromIntegral n-1)) argv
v_getArgCount :: IO Int
v_getArgCount = withRawArgs (\count _ -> pure count)
v_getArg :: Int -> IO String
v_getArg n = withRawArgs $ \count argv -> do
  i <- evaluate (bounded "argument index out of bounds" (count-1) n)
  bytes <- peekElemOff argv (i+1) >>= B.packCString
  evaluate (fromUtf8 bytes)
write :: H.Handle -> String -> IO ()
write handle text = ioErrorAs "IO error: output failed" $ do
  B.hPut handle (utf8 text)
  H.hFlush handle
  pure ()
v_putStr, v_putStrLn, v_putErr :: String -> IO ()
v_putStr = write H.stdout
v_putStrLn s = write H.stdout (v_concatString s (literal "\n"))
v_putErr = write H.stderr
v_printInt :: Int -> IO ()
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
-- The fixed length and private storage share one owner. File and digest
-- adapters take snapshots in bulk before calling out to the host.
data ByteArray = ByteArray !P.Int !(ForeignPtr Word8)
newArray :: Int -> a -> IO (A.IOArray P.Int a)
newArray n initial = do
  size <- evaluate (bounded "invalid array length" (9223372036854775807 `quot` 8) n)
  value <- evaluate initial
  A.newArray (0,size-1) value
index :: A.IOArray P.Int a -> Int -> IO P.Int
index array n = do
  (_,hi) <- A.getBounds array
  evaluate (stIndex (fromIntegral hi + 1) n)
readArray :: A.IOArray P.Int a -> Int -> IO a
readArray array n = index array n >>= AB.unsafeRead array
writeArray :: A.IOArray P.Int a -> Int -> a -> IO ()
writeArray array n value = do
  i <- index array n
  x <- evaluate value
  AB.unsafeWrite array i x
  pure ()
lengthArray :: A.IOArray P.Int a -> IO Int
lengthArray array = do { (_,hi) <- A.getBounds array; pure (fromIntegral hi+1) }
v_newIntArray :: Int -> Int -> IO IntArray
v_newIntArray n x = IntArray <$> newArray n x
v_newDoubleArray :: Int -> Double -> IO DoubleArray
v_newDoubleArray n x = DoubleArray <$> newArray n x
v_newByteArray :: Int -> Int -> IO ByteArray
v_newByteArray n x = do
  size <- evaluate (bounded "invalid array length" (9223372036854775807 `quot` 8) n)
  value <- evaluate (fromIntegral (bounded "byte value must be between 0 and 255" 255 x) :: Word8)
  storage <- mallocForeignPtrBytes (max 1 size)
  withForeignPtr storage $ \pointer -> fillBytes pointer value size
  pure (ByteArray size storage)
v_readIntArray :: IntArray -> Int -> IO Int
v_readIntArray (IntArray a) = readArray a
v_readDoubleArray :: DoubleArray -> Int -> IO Double
v_readDoubleArray (DoubleArray a) = readArray a
v_readByteArray :: ByteArray -> Int -> IO Int
v_readByteArray array n = do
  ByteArray size storage <- evaluate array
  i <- evaluate (stIndex (fromIntegral size) n)
  withForeignPtr storage $ \pointer -> fromIntegral <$> peekElemOff pointer i
v_writeIntArray :: IntArray -> Int -> Int -> IO ()
v_writeIntArray (IntArray a) = writeArray a
v_writeDoubleArray :: DoubleArray -> Int -> Double -> IO ()
v_writeDoubleArray (DoubleArray a) = writeArray a
v_writeByteArray :: ByteArray -> Int -> Int -> IO ()
v_writeByteArray array n x = do
  ByteArray size storage <- evaluate array
  i <- evaluate (stIndex (fromIntegral size) n)
  value <- evaluate (fromIntegral (bounded "byte value must be between 0 and 255" 255 x) :: Word8)
  withForeignPtr storage $ \pointer -> pokeElemOff pointer i value
v_lengthIntArray :: IntArray -> IO Int
v_lengthIntArray (IntArray a) = lengthArray a
v_lengthDoubleArray :: DoubleArray -> IO Int
v_lengthDoubleArray (DoubleArray a) = lengthArray a
v_lengthByteArray :: ByteArray -> IO Int
v_lengthByteArray array = do
  ByteArray size _ <- evaluate array
  pure (fromIntegral size)
bytesArray :: B.ByteString -> IO ByteArray
bytesArray bytes = B.useAsCStringLen bytes $ \(pointer,size) -> copyByteArray (castPtr pointer) size
copyByteArray :: Ptr Word8 -> P.Int -> IO ByteArray
copyByteArray input size = do
  storage <- mallocForeignPtrBytes (max 1 size)
  if size == 0 then pure () else withForeignPtr storage $ \pointer -> copyBytes pointer input size
  pure (ByteArray size storage)
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
v_putBytes :: ByteArray -> Int -> Int -> IO ()
v_putBytes array start count = do
  ByteArray size storage <- evaluate array
  i <- evaluate (bounded "byte slice out of bounds" (fromIntegral size) start)
  n <- evaluate (bounded "byte slice out of bounds" (fromIntegral size-start) count)
  bytes <- withForeignPtr storage $ \pointer -> B.packCStringLen (castBytePointer pointer `plusPtr` i,n)
  ioErrorAs "IO error: output failed" (B.hPut H.stdout bytes >> H.hFlush H.stdout)
-- The primitive owns evaluated Int64 keys/values. Machine IntMap is lossless
-- on 64-bit hosts; retain full keys on narrower hosts instead of truncating.
#if WORD_SIZE_IN_BITS >= 64 && !defined(MLF_TEST_NARROW_INT_TABLE)
type IntTable = IORef (M.IntMap Int)
intTableKey :: Int -> P.Int
intTableKey = fromIntegral
#else
type IntTable = IORef (M.Map Int Int)
intTableKey :: Int -> Int
intTableKey = id
#endif
v_newIntTable :: IO IntTable
v_newIntTable = newIORef M.empty
v_readIntTable :: IntTable -> Int -> IO Int
v_readIntTable table key = do
  values <- readIORef table
  k <- evaluate key
  pure (M.findWithDefault 0 (intTableKey k) values)
v_writeIntTable :: IntTable -> Int -> Int -> IO ()
v_writeIntTable table key value = do
  values <- readIORef table
  k <- evaluate key
  x <- evaluate value
  writeIORef table (M.insert (intTableKey k) x values)
  pure ()

runEntry :: IO () -> IO ()
runEntry entry = ((entry >> pure ()) `finally` c_shutdown)
  `catch` (\(HostError message) -> do
    B.hPut H.stderr (utf8 (literal ("Runtime: "++message++"\n")))
    H.hFlush H.stderr
    X.exitFailure)


foreign import ccall safe "mlf_ghc_read_byte_file" c_readByteFile :: CString -> CSize -> Int64 -> Ptr (Ptr Word8) -> Ptr CSize -> IO CString
foreign import ccall safe "mlf_ghc_write_byte_file" c_writeByteFile :: CString -> CSize -> Ptr Word8 -> CSize -> IO CString
castBytePointer :: Ptr Word8 -> CString
castBytePointer = castPtr
withByteSnapshot :: ByteArray -> (Ptr Word8 -> IO a) -> IO a
withByteSnapshot (ByteArray size storage) action = bracket (mallocBytes (max 1 size)) free $ \pointer -> do
  withForeignPtr storage $ \source -> copyBytes pointer source size
  action pointer
-- These two primitives return ordinary diagnostics, not HostError. Mask the
-- ownership handoff from the safe FFI just like host(), retaining cancellation
-- cleanup. They intentionally do not catch allocation failure or language panic.
v_readByteFileOrError :: String -> Int -> IO (String, ByteArray)
v_readByteFileOrError name limit = mask_ $
  B.useAsCStringLen (utf8 name) $ \(pathBytes,pathLength) -> do
    bound <- evaluate limit
    -- Array lengths use host Int, including on 32-bit GHC.
    -- Keep path-NUL priority over an invalid size, as in the shared C core.
    if bound > fromIntegral (maxBound :: P.Int) then do
      array <- bytesArray B.empty
      pure (literal (if '\0' `elem` unpack name then "file path contains NUL"
                     else "invalid byte file limit"), array)
    else alloca $ \out -> alloca $ \size -> do
      errorPointer <- c_readByteFile pathBytes (fromIntegral pathLength) bound out size
      bytes <- peek out
      count <- peek size
      bracket (pure bytes) free $ \owned -> do
        message <- B.packCString errorPointer >>= evaluate . fromUtf8
        array <- if owned == nullPtr then bytesArray B.empty
                 else copyByteArray owned (fromIntegral count)
        pure (message,array)
v_writeByteFileOrError :: String -> ByteArray -> IO String
v_writeByteFileOrError name array =
  if '\0' `elem` unpack name then pure (literal "file path contains NUL") else
  do
    ByteArray size _ <- evaluate array
    withByteSnapshot array $ \bytes ->
        B.useAsCStringLen (utf8 name) $ \(pathBytes,pathLength) -> do
          message <- c_writeByteFile pathBytes (fromIntegral pathLength) bytes (fromIntegral size)
          B.packCString message >>= evaluate . fromUtf8

foreign import ccall safe "mlf_ghc_byte_array_digest" c_byteArrayDigest :: Ptr Word8 -> CSize -> CString -> IO ()
v_byteArrayDigest :: ByteArray -> IO String
v_byteArrayDigest array = do
  ByteArray size _ <- evaluate array
  withByteSnapshot array $ \bytes ->
    bracket (mallocBytes 65) free $ \digest -> do
      c_byteArrayDigest bytes (fromIntegral size) digest
      B.packCStringLen (digest,64) >>= evaluate . fromUtf8
