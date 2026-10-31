{-# LANGUAGE ScopedTypeVariables, RankNTypes #-}
module Main where
import Prelude
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as H
import qualified MLF.Host.Async as A
import Control.Exception
import Control.Monad (forM_, unless)
import Data.IORef
import qualified Data.ByteString as BS
import System.Exit

poison :: a
poison = B.failure "operand forced during action construction"
check :: String -> IO () -> IO Bool
check label action = do
  r <- try action
  case r of
    Left (e :: SomeException) -> putStrLn ("FAIL "++label++": "++displayException e) >> pure False
    Right () -> putStrLn ("PASS "++label) >> pure True
cold :: String -> a -> IO Bool
cold label action = check ("cold "++label) (evaluate action >> pure ())
expect :: (Eq a,Show a) => a -> a -> IO ()
expect a b = unless (a==b) (error ("expected "++show a++", got "++show b))
fails :: String -> a -> IO ()
fails s a = do
  r <- try (evaluate a)
  case r of
    Left (B.HostError t) -> expect s t
    Right _ -> error "expected HostError"
main :: IO ()
main = do
  cs <- sequence
    [ cold "ioReturn" (F.ioReturn poison)
    , cold "ioBind" (F.ioBind poison (\_ -> F.ioReturn ()))
    , cold "stReturn" (F.stReturn poison)
    , cold "stBind" (F.stBind poison (\_ -> F.stReturn ()))
    , cold "newSTArray" (F.newSTArray poison poison)
    , cold "readSTArray" (F.readSTArray poison poison)
    , cold "writeSTArray" (F.writeSTArray poison poison poison)
    , cold "lengthSTArray" (F.lengthSTArray poison)
    , cold "newIntArray" (F.newIntArray poison poison)
    , cold "readIntArray" (F.readIntArray poison poison)
    , cold "writeIntArray" (F.writeIntArray poison poison poison)
    , cold "lengthIntArray" (F.lengthIntArray poison)
    , cold "newDoubleArray" (F.newDoubleArray poison poison)
    , cold "readDoubleArray" (F.readDoubleArray poison poison)
    , cold "writeDoubleArray" (F.writeDoubleArray poison poison poison)
    , cold "lengthDoubleArray" (F.lengthDoubleArray poison)
    , cold "newByteArray" (F.newByteArray poison poison)
    , cold "readByteArray" (F.readByteArray poison poison)
    , cold "writeByteArray" (F.writeByteArray poison poison poison)
    , cold "lengthByteArray" (F.lengthByteArray poison)
    , cold "byteArrayFromString" (F.byteArrayFromString poison)
    , cold "putBytes" (F.putBytes poison poison poison)
    , cold "readIntTable" (F.readIntTable poison poison)
    , cold "writeIntTable" (F.writeIntTable poison poison poison)
    , cold "putStr" (F.putStr poison)
    , cold "putStrLn" (F.putStrLn poison)
    , cold "printInt" (F.printInt poison)
    , cold "readFile" (F.readFile poison)
    , cold "writeFile" (F.writeFile poison poison)
    , cold "fileExists" (F.fileExists poison)
    , cold "canonicalPath" (F.canonicalPath poison)
    , cold "getArg" (F.getArg poison)
    , cold "exitWith" (F.exitWith poison)
    , cold "getEnv" (F.getEnv poison)
    , cold "setEnv" (F.setEnv poison poison)
    , cold "unsetEnv" (F.unsetEnv poison)
    , cold "runProcess" (F.runProcess poison poison)
    , cold "listDirectory" (F.listDirectory poison)
    , cold "directoryExists" (F.directoryExists poison)
    , cold "fileDigest" (F.fileDigest poison)
    , cold "acquireFileLock" (F.acquireFileLock poison)
    , cold "releaseFileLock" (F.releaseFileLock poison)
    , cold "processSupervisor" (F.processSupervisor poison)
    , cold "asyncScopeNew" (F.asyncScopeNew poison poison)
    , cold "asyncScopeClose" (F.asyncScopeClose poison)
    , cold "asyncNewCompletion" (F.asyncNewCompletion poison poison poison)
    , cold "asyncResolveCompletion" (F.asyncResolveCompletion poison poison)
    , cold "asyncReadCompletion" (F.asyncReadCompletion poison poison poison)
    , cold "asyncSubscribeCompletion" (F.asyncSubscribeCompletion poison poison)
    , cold "asyncSubscriptionStatus" (F.asyncSubscriptionStatus poison)
    , cold "asyncCancelSubscription" (F.asyncCancelSubscription poison)
    , cold "asyncStep" (F.asyncStep poison)
    , cold "asyncEnqueue" (F.asyncEnqueue poison poison)
    , cold "asyncDelay" (F.asyncDelay poison poison poison)
    , cold "asyncWait" (F.asyncWait poison poison)
    ]
  rs <- sequence
    [ check "Int64 addition wraps" (expect minBound (F.addInt maxBound 1))
    , check "Int64 multiplication wraps" (expect 0 (F.mulInt 4294967296 4294967296))
    , check "explicit Integer remains unbounded" (expect (2^100::Integer) (F.addInteger (2^100-1) 1))
    , check "comparison right-first <=" (fails "right" ((F.<=) (B.failure "left") (B.failure "right")))
    , check "comparison right-first >" (fails "right" ((F.>) (B.failure "left") (B.failure "right")))
    , check "comparison left-first >=" (fails "left" ((F.>=) (B.failure "left") (B.failure "right")))
    , check "format value before bound check" (fails "value" (F.formatDouble 99 (B.failure "value")))
    , check "empty ST initializer lazy" (expect 0 (F.runST (F.newSTArray 0 poison >>= F.lengthSTArray)))
    , check "ST snapshot execution time" (expect (10,20) (F.runST $ do
        a <- F.newSTArray 1 (10::Integer)
        let readAgain=F.readSTArray a 0
        before <- readAgain
        F.writeSTArray a 0 20
        after <- readAgain
        pure (before,after)))
    , check "empty IO initializer strict" $ do
        r <- try (F.newIntArray 0 (B.failure "init"))
        case r of { Left (B.HostError s) -> expect "init" s; Right _ -> error "initializer not forced" }
    , check "array index checks despite result discarded" $ do
        a <- F.newIntArray 0 0
        r <- try (F.readIntArray a 0 >> pure ())
        case r of { Left (B.HostError s) -> expect "array index out of bounds" s; Right _ -> error "read not checked" }
    , check "Unicode scalar and NUL indexing" $ do
        let s=B.literal "a😀\0\x10ffff"
        expect 4 (F.stringLength s)
        expect 128512 (F.stringCodeAt s 1)
        expect 0 (F.stringCodeAt s 2)
        expect "😀\0" (B.unpack (F.stringSlice s 1 2))
    , check "invalid UTF8 action-time" $ do
        BS.writeFile "tests/shared-host/invalid-utf8.tmp" (BS.pack [255])
        r <- try (F.readFile (B.literal "tests/shared-host/invalid-utf8.tmp") >> pure ())
        case r of { Left (B.HostError s) -> expect "IO error: invalid UTF-8 input" s; Right _ -> error "UTF8 not checked" }
    , check "file path NUL rejected during action" $ do
        r <- try (F.fileExists (B.literal "bad\0path") >> pure ())
        case r of { Left (B.HostError s) -> expect "file path contains NUL" s; Right _ -> error "NUL not checked" }
    , check "writeFile validates filename before contents" $ do
        r <- try (F.writeFile (B.literal "bad\0path") (B.failure "contents"))
        case r of { Left (B.HostError s) -> expect "file path contains NUL" s; Right _ -> error "NUL not checked" }
    , check "writeFile forces contents before truncation" $ do
        let filename="tests/shared-host/preserve-on-panic.tmp"
        BS.writeFile filename (BS.pack [111,107])
        r <- try (F.writeFile (B.literal filename) (B.failure "contents"))
        case r of { Left (B.HostError s) -> expect "contents" s; Right _ -> error "contents not forced" }
        BS.readFile filename >>= expect (BS.pack [111,107])
    , check "runProcess validates cwd before specification" $ do
        r <- try (F.runProcess (B.literal "bad\0cwd") (B.failure "specification"))
        case r of { Left (B.HostError s) -> expect "file path contains NUL" s; Right _ -> error "cwd not checked" }
    , check "setEnv validates name before contents" $ do
        r <- try (F.setEnv (B.literal "bad\0name") (B.failure "contents"))
        case r of { Left (B.HostError s) -> expect "file path contains NUL" s; Right _ -> error "name not checked" }
    , check "setEnv forces name before contents" $ do
        r <- try (F.setEnv (B.failure "name") (B.failure "contents"))
        case r of { Left (B.HostError s) -> expect "name" s; Right _ -> error "name not forced" }
    , check "exitWith exact native bound diagnostic" $ do
        r <- try (F.exitWith 256 :: IO ())
        case r of { Left (B.HostError s) -> expect "exit status must be between 0 and 255" s; Right _ -> error "exit code not checked" }
    , check "nested panic message demand" (fails "inner" (F.panic (F.panic (B.literal "inner")) :: Integer))
    , check "zero length byte initializer validation" $ do
        r <- try (F.newByteArray 0 300)
        case r of { Left (B.HostError s) -> expect "byte value must be between 0 and 255" s; Right _ -> error "byte initializer not checked" }
    , check "nominal array read write and length" $ do
        ints <- F.newIntArray 1 (2^100)
        doubles <- F.newDoubleArray 1 2.5
        bytes <- F.newByteArray 1 255
        F.writeIntArray ints 0 300
        F.writeDoubleArray doubles 0 3.5
        F.writeByteArray bytes 0 42
        F.readIntArray ints 0 >>= expect 300
        F.readDoubleArray doubles 0 >>= expect 3.5
        F.readByteArray bytes 0 >>= expect 42
        F.lengthIntArray ints >>= expect 1
        F.lengthDoubleArray doubles >>= expect 1
        F.lengthByteArray bytes >>= expect 1
    , check "UTF8 byte array conversion" $ do
        bytes <- F.byteArrayFromString (B.literal "😀\0")
        F.lengthByteArray bytes >>= expect 5
        mapM (F.readByteArray bytes) [0..4] >>= expect [240,159,152,128,0]
    , check "file lock narrowing is checked" $ do
        r <- try (F.releaseFileLock 9223372036854775807)
        case r of { Left (B.HostError s) -> expect "invalid file lock" s; Right _ -> error "huge handle truncated" }
    , check "huge array length is checked" $ do
        r <- try (F.newIntArray 9223372036854775807 0)
        case r of { Left (B.HostError s) -> expect "invalid array length" s; Right _ -> error "huge size truncated" }
    , check "huge index is checked" $ do
        a <- F.newIntArray 1 0
        r <- try (F.readIntArray a 9223372036854775807)
        case r of { Left (B.HostError s) -> expect "array index out of bounds" s; Right _ -> error "huge index truncated" }
    , check "huge async delay is checked" $ do
        scope <- F.asyncScopeNew 0 0
        r <- try (F.asyncDelay scope 9223372036854775807 (pure ()))
        F.asyncScopeClose scope
        case r of { Left (B.HostError s) -> expect "invalid async delay" s; Right _ -> error "huge delay truncated" }
    , check "huge async wait is checked" $ do
        scope <- F.asyncScopeNew 0 0
        r <- try (F.asyncWait scope 9223372036854775807)
        F.asyncScopeClose scope
        case r of { Left (B.HostError s) -> expect "invalid async wait" s; Right _ -> error "huge wait truncated" }
    , check "Double bit input wraps as Int64" (expect 0 (F.doubleToBits (F.doubleFromBits (2^64))))
    , check "Double negative zero bits" (expect (2^63) (F.doubleToBits (F.doubleFromBits (2^63))))
    , check "String scalar maximum" (expect 0x10ffff (F.stringCodeAt (F.stringFromCode 0x10ffff) 0))
    , check "String surrogate rejected" (fails "invalid Unicode scalar" (F.stringFromCode 0xdfff))
    , check "async lazy payload, rejection, FIFO, close" $ do
        scope <- F.asyncScopeNew 1 3
        order <- newIORef ([]::[Integer])
        F.asyncNewCompletion scope (\cell -> do
          _ <- F.asyncSubscribeCompletion cell (\_ -> modifyIORef' order (++[1]) >> pure ())
          _ <- F.asyncSubscribeCompletion cell (\_ -> modifyIORef' order (++[2]) >> pure ())
          F.asyncResolveCompletion cell poison >>= expect 0
          F.asyncResolveCompletion cell poison >>= expect 2
          readIORef order >>= expect []
          F.asyncStep scope >>= expect 0
          F.asyncStep scope >>= expect 0
          readIORef order >>= expect [1,2]
          F.asyncScopeClose scope
          F.asyncResolveCompletion cell poison >>= expect 3
          F.asyncReadCompletion cell poison (pure 77) >>= expect (77::Integer)
          pure ()) (error "cell allocation rejected")
        pure ()
    ]
  putStrLn ("TOTAL "++show (length (cs++rs))++" FAILED "++show (length (filter not (cs++rs))))
  unless (and (cs++rs)) exitFailure
