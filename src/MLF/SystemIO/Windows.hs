{-# LANGUAGE ForeignFunctionInterface #-}
-- | Synchronous Win32 byte-range locks. Closing the handle releases the lock,
-- including when the owning process exits.
module MLF.SystemIO.Windows (acquireFileLock, releaseFileLock) where

import Control.Exception (onException)
import Control.Monad (unless, when)
import Data.Int (Int32)
import Data.Word (Word32)
import Foreign (Ptr, allocaBytes, fillBytes, intPtrToPtr, nullPtr, ptrToIntPtr)
import Foreign.C.String (CWString, withCWString)

foreign import stdcall unsafe "CreateFileW"
  createFile :: CWString -> Word32 -> Word32 -> Ptr () -> Word32 -> Word32 -> Ptr () -> IO (Ptr ())
foreign import stdcall safe "LockFileEx"
  lockFile :: Ptr () -> Word32 -> Word32 -> Word32 -> Word32 -> Ptr () -> IO Int32
foreign import stdcall unsafe "CloseHandle"
  closeHandle :: Ptr () -> IO Int32
foreign import stdcall unsafe "GetLastError"
  lastError :: IO Word32

windowsError :: String -> IO a
windowsError operation = lastError >>= \code -> fail (operation ++ " failed (Win32 " ++ show code ++ ")")

acquireFileLock :: FilePath -> IO Integer
acquireFileLock path = withCWString path $ \name -> do
  handle <- createFile name 0xc0000000 7 nullPtr 4 0x80 nullPtr
  when (handle == intPtrToPtr (-1)) (windowsError "CreateFileW")
  (allocaBytes 32 $ \overlapped -> do
    fillBytes overlapped 0 32
    ok <- lockFile handle 2 0 maxBound maxBound overlapped
    unless (ok /= 0) (windowsError "LockFileEx")
    pure (toInteger (ptrToIntPtr handle))) `onException` closeHandle handle

releaseFileLock :: Integer -> IO ()
releaseFileLock token = do
  unless (token >= 0 && token <= toInteger (maxBound :: Int)) (fail "invalid file lock")
  ok <- closeHandle (intPtrToPtr (fromInteger token))
  unless (ok /= 0) (windowsError "CloseHandle")
