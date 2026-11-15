{-# LANGUAGE DeriveDataTypeable, ScopedTypeVariables #-}
module Main where

import Prelude
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as H
import qualified Bootstrap.Bitstream as Bit
import Control.Exception (Exception, Handler(..), catches, evaluate, throw, throwIO)
import Control.Monad (unless)
import Data.Typeable (Typeable)
import Foreign.ForeignPtr (mallocForeignPtrBytes)
import System.Mem (performGC)

data ProbeError = ProbeError String deriving (Show, Typeable)
instance Exception ProbeError
data Fault = Probe String | Host String deriving (Eq, Show)

poison :: String -> a
poison label = throw (ProbeError label)

capture :: IO a -> IO (Either Fault a)
capture action = (Right <$> action) `catches`
  [ Handler (\(ProbeError label) -> pure (Left (Probe label)))
  , Handler (\(B.HostError label) -> pure (Left (Host label)))
  ]

assertEq :: (Eq a, Show a) => a -> a -> IO ()
assertEq want got = unless (want == got) (error ("expected " ++ show want ++ ", got " ++ show got))

expectFault :: Fault -> IO a -> IO ()
expectFault want action = do
  got <- capture action
  case got of
    Left actual -> assertEq want actual
    Right _ -> error ("expected fault " ++ show want)

cold :: a -> IO ()
cold action = evaluate action >> pure ()

bytes :: F.ByteArray -> F.Int -> IO [F.Int]
bytes array count = mapM (F.readByteArray array) [0 .. count - 1]

boundError, byteError :: Fault
boundError = Host "array index out of bounds"
byteError = Host "byte value must be between 0 and 255"

cases :: [(String, IO ())]
cases =
  [ ("cold read array and index", cold (F.readByteArray (poison "array") (poison "index")))
  , ("cold write array index value", cold (F.writeByteArray (poison "array") (poison "index") (poison "value")))
  , ("cold length array", cold (F.lengthByteArray (poison "array")))
  , ("read array before index", expectFault (Probe "array") (F.readByteArray (poison "array") (poison "index")))
  , ("write array before index and value", expectFault (Probe "array") (F.writeByteArray (poison "array") (poison "index") (poison "value")))
  , ("length demands array when executed", expectFault (Probe "array") (F.lengthByteArray (poison "array")))
  , ("read index forced even result ignored", do
      a <- F.newByteArray 1 7
      expectFault (Probe "index") (F.readByteArray a (poison "index") >> pure ()))
  , ("write index before value", do
      a <- F.newByteArray 1 7
      expectFault (Probe "index") (F.writeByteArray a (poison "index") (poison "value")))
  , ("write bounds before value and no mutation", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.writeByteArray a 1 (poison "value"))
      F.readByteArray a 0 >>= assertEq 7)
  , ("write value before mutation", do
      a <- F.newByteArray 1 7
      expectFault (Probe "value") (F.writeByteArray a 0 (poison "value"))
      F.readByteArray a 0 >>= assertEq 7)
  , ("zero length is zero", F.newByteArray 0 0 >>= F.lengthByteArray >>= assertEq 0)
  , ("zero read checked despite discarded result", do
      a <- F.newByteArray 0 0
      expectFault boundError (F.readByteArray a 0 >> pure ()))
  , ("zero write bounds before value", do
      a <- F.newByteArray 0 0
      expectFault boundError (F.writeByteArray a 0 (poison "value")))
  , ("zero initializer still validated", expectFault byteError (F.newByteArray 0 256))
  , ("negative read index", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.readByteArray a (-1)))
  , ("minimum Int64 read index", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.readByteArray a minBound))
  , ("maximum Int64 read index", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.readByteArray a maxBound))
  , ("upper exclusive read bound", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.readByteArray a 1))
  , ("minimum Int64 write index", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.writeByteArray a minBound (poison "value")))
  , ("maximum Int64 write index", do
      a <- F.newByteArray 1 7
      expectFault boundError (F.writeByteArray a maxBound (poison "value")))
  , ("negative byte value rejected", do
      a <- F.newByteArray 1 7
      expectFault byteError (F.writeByteArray a 0 (-1))
      F.readByteArray a 0 >>= assertEq 7)
  , ("byte value 256 rejected", do
      a <- F.newByteArray 1 7
      expectFault byteError (F.writeByteArray a 0 256)
      F.readByteArray a 0 >>= assertEq 7)
  , ("minimum Int64 byte rejected", do
      a <- F.newByteArray 1 7
      expectFault byteError (F.writeByteArray a 0 minBound))
  , ("maximum Int64 byte rejected", do
      a <- F.newByteArray 1 7
      expectFault byteError (F.writeByteArray a 0 maxBound))
  , ("boundary bytes and length", do
      a <- F.newByteArray 2 9
      F.writeByteArray a 0 0
      F.writeByteArray a 1 255
      bytes a 2 >>= assertEq [0,255]
      F.lengthByteArray a >>= assertEq 2)
  , ("same read action observes alias mutation", do
      a <- F.newByteArray 1 2
      let alias = a; readAgain = F.readByteArray a 0
      before <- readAgain
      F.writeByteArray alias 0 3
      after <- readAgain
      assertEq (2,3) (before,after))
  , ("same write action executes twice", do
      a <- F.newByteArray 1 0
      let writeAgain = F.writeByteArray a 0 5
      writeAgain
      F.writeByteArray a 0 9
      writeAgain
      F.readByteArray a 0 >>= assertEq 5)
  , ("read write actions retain owner across GC", do
      a <- F.newByteArray 1 7
      let readLater = F.readByteArray a 0; writeLater = F.writeByteArray a 0 23
      cold readLater
      cold writeLater
      performGC
      readLater >>= assertEq 7
      writeLater
      readLater >>= assertEq 23)
  , ("prior synchronous error skips write", do
      a <- F.newByteArray 1 7
      expectFault (Probe "prior") (throwIO (ProbeError "prior") >> F.writeByteArray a 0 23)
      F.readByteArray a 0 >>= assertEq 7)
  , ("later synchronous error follows write", do
      a <- F.newByteArray 1 7
      expectFault (Probe "later") (F.writeByteArray a 0 23 >> throwIO (ProbeError "later"))
      F.readByteArray a 0 >>= assertEq 23)
  , ("unselected action has no demand or effect", do
      a <- F.newByteArray 1 7
      let ignored = F.writeByteArray (poison "array") (poison "index") (poison "value")
      cold (Just ignored)
      F.readByteArray a 0 >>= assertEq 7)
  , ("raw negative length observed without access", do
      storage <- mallocForeignPtrBytes 1
      F.lengthByteArray (H.ByteArray (-1) storage) >>= assertEq (-1))
  , ("UTF8 byte view has fixed bytes", do
      a <- F.byteArrayFromString (B.literal "A\0é😀")
      F.lengthByteArray a >>= assertEq 8
      bytes a 8 >>= assertEq [65,0,195,169,240,159,152,128])
  , ("real Bitstream aligned ASCII Unicode preserves sentinel", do
      a <- F.newByteArray 12 170
      Bit.putText a 8 (B.literal "AZ\0é😀") 0 >>= assertEq 80
      bytes a 12 >>= assertEq [170,65,90,0,195,169,240,159,152,128,170,170])
  , ("real Bitstream empty text does not demand array", do
      Bit.putText (poison "array") 0 (B.literal "") 0 >>= assertEq 0)
  , ("real Bitstream invalid text index precedes array", do
      expectFault (Host "string index out of bounds") (Bit.putText (poison "array") 0 (B.literal "A") (-1)))
  , ("real Bitstream insufficient buffer preserves first write", do
      a <- F.newByteArray 1 0
      expectFault boundError (Bit.putText a 0 (B.literal "AB") 0)
      bytes a 1 >>= assertEq [65])
  , ("real Bitstream unaligned fixed bit bytes", do
      a <- F.newByteArray 2 0
      Bit.putBits a 3 10 341 >>= assertEq 13
      bytes a 2 >>= assertEq [168,10])
  , ("real Bitstream standard CRC32 check vector", do
      a <- F.byteArrayFromString (B.literal "123456789")
      Bit.checksum a 9 >>= assertEq 3421780262)
  ]

main :: IO ()
main = do
  mapM_ (\(label, action) -> action >> putStrLn ("PASS " ++ label)) cases
  putStrLn ("TOTAL " ++ show (length cases) ++ " FAILED 0")
