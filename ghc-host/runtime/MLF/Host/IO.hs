{-# LANGUAGE ForeignFunctionInterface, ScopedTypeVariables #-}
module MLF.Host.IO where

import Prelude hiding (Int, String)
import qualified Prelude as P
import MLF.Host.Base hiding (Monad(..))
import qualified Data.ByteString as B
import qualified Data.Array.IO as A
import qualified Data.Map.Strict as M
import Data.IORef
import Data.Int (Int64)
import Foreign (Ptr, alloca, peek, nullPtr, free)
import Foreign.C
import Control.Concurrent.MVar
import Control.Exception
import System.IO.Unsafe (unsafePerformIO)
import qualified System.IO as H
import qualified System.Environment as E
import qualified System.Directory as D
import qualified System.Exit as X

foreign import ccall safe "mlf_ghc_host" c_host :: CInt -> CString -> CSize -> CString -> CSize -> Int64 -> Ptr CString -> Ptr CSize -> Ptr Int64 -> IO CInt
foreign import ccall safe "mlf_ghc_shutdown" c_shutdown :: IO ()

-- Native supervisor and transport metadata have a single coordinator. The
-- lock contains no language values; returned byte buffers have explicit owners.
{-# NOINLINE hostLock #-}
hostLock :: MVar ()
hostLock = unsafePerformIO (newMVar ())
host :: CInt -> String -> String -> Int -> IO (String,Int)
host operation a b n = withMVar hostLock $ \_ ->
  B.useAsCStringLen (utf8 a) $ \(pa,na) ->
  B.useAsCStringLen (utf8 b) $ \(pb,nb) ->
  alloca $ \out -> alloca $ \len -> alloca $ \number -> do
    status <- c_host operation pa (fromIntegral na) pb (fromIntegral nb) (fromInteger n) out len number
    bytes <- peek out
    size <- peek len
    text <- if bytes==nullPtr then pure B.empty else bracket (pure bytes) free (\p -> B.packCStringLen (p,fromIntegral size))
    result <- peek number
    if status/=0 then throwIO (HostError (unpack (fromUtf8 text))) else pure (fromUtf8 text,toInteger result)
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
v_setEnv a b = host 1 a b 0 >> pure Unit
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
v_runProcess a b = snd <$> host 7 a b 0

ioErrorAs :: P.String -> IO a -> IO a
ioErrorAs message action = action `catch` (\(_::IOException) -> throwIO (HostError message))
path :: String -> P.FilePath
path s = if '\0' `elem` unpack s then failure "file path contains NUL" else unpack s
v_readFile :: String -> IO String
v_readFile s = ioErrorAs "IO error: file read failed" $ do
  bytes <- B.readFile (path s)
  evaluate (fromUtf8 bytes)
v_writeFile :: String -> String -> IO Unit
v_writeFile s contents = ioErrorAs "IO error: file write failed" $ do
  filename <- evaluate (path s)
  bytes <- evaluate (utf8 contents)
  B.writeFile filename bytes
  pure Unit
v_fileExists :: String -> IO Bool
v_fileExists s = D.doesFileExist (path s)
v_canonicalPath :: String -> IO String
v_canonicalPath s = ioErrorAs "IO error: canonical path failed" $ do
  exists <- D.doesPathExist (path s)
  if exists then literal <$> D.canonicalizePath (path s) else throwIO (HostError "IO error: canonical path failed")
v_getExecutablePath :: IO String
v_getExecutablePath = literal <$> (E.getExecutablePath >>= D.canonicalizePath)
v_getArgCount :: IO Int
v_getArgCount = toInteger . length <$> E.getArgs
v_getArg :: Int -> IO String
v_getArg n = do
  args <- E.getArgs
  let i=bounded "argument index out of bounds" (toInteger (length args)-1) n
  pure (literal (args!!i))
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
v_getContents = ioErrorAs "IO error: input failed" (B.getContents >>= evaluate . fromUtf8)
v_getLine :: IO String
v_getLine = ioErrorAs "IO error: getLine reached EOF or failed" $ do
  end <- H.hIsEOF H.stdin
  if end then throwIO (HostError "IO error: getLine reached EOF or failed") else B.hGetLine H.stdin >>= evaluate . fromUtf8
v_exitWith :: Int -> IO a
v_exitWith n = do
  i <- evaluate (bounded "invalid exit code" 255 n)
  X.exitWith (if i==0 then X.ExitSuccess else X.ExitFailure i)

type IntArray = A.IOArray P.Int Int
type DoubleArray = A.IOArray P.Int Double
type ByteArray = A.IOArray P.Int Int
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
v_newIntArray = newArray
v_newDoubleArray :: Int -> Double -> IO DoubleArray
v_newDoubleArray = newArray
v_newByteArray :: Int -> Int -> IO ByteArray
v_newByteArray n x = newArray n (toInteger (bounded "byte value must be between 0 and 255" 255 x))
v_readIntArray :: IntArray -> Int -> IO Int
v_readIntArray = readArray
v_readDoubleArray :: DoubleArray -> Int -> IO Double
v_readDoubleArray = readArray
v_readByteArray :: ByteArray -> Int -> IO Int
v_readByteArray = readArray
v_writeIntArray :: IntArray -> Int -> Int -> IO Unit
v_writeIntArray = writeArray
v_writeDoubleArray :: DoubleArray -> Int -> Double -> IO Unit
v_writeDoubleArray = writeArray
v_writeByteArray :: ByteArray -> Int -> Int -> IO Unit
v_writeByteArray a n x = writeArray a n (toInteger (bounded "byte value must be between 0 and 255" 255 x))
v_lengthIntArray :: IntArray -> IO Int
v_lengthIntArray = lengthArray
v_lengthDoubleArray :: DoubleArray -> IO Int
v_lengthDoubleArray = lengthArray
v_lengthByteArray :: ByteArray -> IO Int
v_lengthByteArray = lengthArray
bytesArray :: B.ByteString -> IO ByteArray
bytesArray bytes = A.newListArray (0,B.length bytes-1) (map toInteger (B.unpack bytes))
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
v_putBytes a start count = do
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
  `catch` (\(HostError message) -> H.hPutStrLn H.stderr ("Runtime: "++message) >> X.exitFailure)
