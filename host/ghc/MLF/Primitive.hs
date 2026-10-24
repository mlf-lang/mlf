{-# LANGUAGE NoImplicitPrelude, RankNTypes, KindSignatures, ConstraintKinds #-}
-- GHC implementation of the stable native MLF.Primitive boundary.
-- Compiler algorithms import only this module, never MLF.Host.*.
-- Ordinary Haskell syntax uses the standard class identities and desugaring.
-- Only value representations and primitive operations are host adaptations.
module MLF.Primitive
  ( Int, Bool(..), Double, Char, IO, IOError, String, ST, STArray, Functor(..), Applicative(..), Monad(..), MonadFail(..), IsString(..), Eq(..), IntArray, DoubleArray, ByteArray, IntTable, AsyncScope, Completion, AsyncSubscription
  , HasCallStack, CallStack, callStack, prettyCallStack
  , MLFHasCallStack, MLFCallStack, MLFStackFrame(..), MLFStackEvidence(..)
  , mlfEmptyCallStack, mlfPushCallStack, mlfPrettyCallStack, mlfIOErrorWithStack
  , textToChars, textFromChars, charCode, charFromCode
  , userError, ioError, catchIOError, ioeGetErrorString
  , ioReturn, ioBind, putStr, putStrLn, getLine, printInt, concatString
  , showInt, addInt, subInt, eqInt, ltInt, eqString, ifThenElse
  , mulInt, quotInt, remInt, readInt, addDouble, subDouble, mulDouble
  , divDouble, sqrtDouble, eqDouble, ltDouble, intToDouble, formatDouble, newIntArray
  , readIntArray, writeIntArray, lengthIntArray, newDoubleArray, readDoubleArray, writeDoubleArray, lengthDoubleArray
  , newByteArray, readByteArray, writeByteArray, lengthByteArray, byteArrayFromString, putBytes, getByteLine
  , newIntTable, readIntTable, writeIntTable, andInt, stringLength, stringCodeAt, stringSlice
  , stringFromCode, compareString, readDouble, doubleToBits, doubleFromBits, seq, panic
  , readFile, writeFile, fileExists, canonicalPath, getArgCount, getArg, putErr
  , exitWith, getExecutablePath, getContents, stReturn, stBind, runST, newSTArray
  , readSTArray, writeSTArray, lengthSTArray, getEnv, setEnv, unsetEnv, runProcess
  , listDirectory, directoryExists, fileDigest, acquireFileLock, releaseFileLock, processSupervisor, asyncScopeNew
  , asyncScopeClose, asyncNewCompletion, asyncResolveCompletion, asyncReadCompletion, asyncSubscribeCompletion, asyncSubscriptionStatus, asyncCancelSubscription
  , asyncStep, asyncEnqueue, asyncDelay, asyncWait
  , implementationHost, bind, negate, otherwise
  , (+), (-), (*), (/), (%), (<), (<=), (>), (>=), (++), (&&), (||)
  ) where

import qualified Prelude as P
import Prelude (Functor(..), Applicative(..), Monad(..), Eq(..), Char, IOError)
import Control.Monad.Fail (MonadFail(..))
import Data.String (IsString(..))
import GHC.Stack (HasCallStack, CallStack, callStack, prettyCallStack)
import System.IO.Error (ioError)
import MLF.Host.Base (MLFHasCallStack, MLFCallStack, MLFStackFrame(..), MLFStackEvidence(..))
import MLF.Host.Base (Int, Bool(..), Double, IO, String, ST, STArray)
import MLF.Host.IO (IntArray, DoubleArray, ByteArray, IntTable)
import MLF.Host.Async (AsyncScope, Completion, AsyncSubscription)
import qualified MLF.Host.Base as Base
import qualified MLF.Host.IO as IO
import qualified MLF.Host.Async as Async

-- The standard classes above are imported unchanged, including the pinned
-- MonadFail/ioError HasCallStack constraints and GHC.Stack public identities.
mlfEmptyCallStack :: MLFCallStack
mlfEmptyCallStack = Base.v_emptyCallStack
mlfPushCallStack :: MLFStackFrame -> MLFCallStack -> MLFCallStack
mlfPushCallStack = Base.v_pushCallStack
mlfPrettyCallStack :: MLFCallStack -> [Char]
mlfPrettyCallStack = Base.v_prettyCallStack
mlfIOErrorWithStack :: IOError -> MLFCallStack -> IO a
mlfIOErrorWithStack = IO.v_ioErrorWithStack

textToChars :: String -> [Char]
textToChars = Base.v_textToChars
textFromChars :: [Char] -> String
textFromChars = Base.v_textFromChars
charCode :: Char -> Int
charCode = Base.v_charCode
charFromCode :: Int -> Char
charFromCode = Base.v_charFromCode
userError :: [Char] -> IOError
userError = IO.v_userError
catchIOError :: IO a -> (IOError -> IO a) -> IO a
catchIOError = IO.v_catchIOError
ioeGetErrorString :: IOError -> [Char]
ioeGetErrorString = IO.v_ioeGetErrorString

ioReturn :: a -> IO a
ioReturn = Base.v_ioReturn

ioBind :: IO a -> (a -> IO b) -> IO b
ioBind = Base.v_ioBind

putStr :: String -> IO ()
putStr = IO.v_putStr

putStrLn :: String -> IO ()
putStrLn = IO.v_putStrLn

getLine :: IO String
getLine = IO.v_getLine

printInt :: Int -> IO ()
printInt = IO.v_printInt

concatString :: String -> String -> String
concatString = Base.v_concatString

showInt :: Int -> String
showInt = Base.v_showInt

addInt :: Int -> Int -> Int
addInt = Base.v_addInt

subInt :: Int -> Int -> Int
subInt = Base.v_subInt

eqInt :: Int -> Int -> Bool
eqInt = Base.v_eqInt

ltInt :: Int -> Int -> Bool
ltInt = Base.v_ltInt

eqString :: String -> String -> Bool
eqString = Base.v_eqString

ifThenElse :: Bool -> a -> a -> a
ifThenElse = Base.v_ifThenElse

mulInt :: Int -> Int -> Int
mulInt = Base.v_mulInt

quotInt :: Int -> Int -> Int
quotInt = Base.v_quotInt

remInt :: Int -> Int -> Int
remInt = Base.v_remInt

readInt :: String -> Int
readInt = Base.v_readInt

addDouble :: Double -> Double -> Double
addDouble = Base.v_addDouble

subDouble :: Double -> Double -> Double
subDouble = Base.v_subDouble

mulDouble :: Double -> Double -> Double
mulDouble = Base.v_mulDouble

divDouble :: Double -> Double -> Double
divDouble = Base.v_divDouble

sqrtDouble :: Double -> Double
sqrtDouble = Base.v_sqrtDouble

eqDouble :: Double -> Double -> Bool
eqDouble = Base.v_eqDouble

ltDouble :: Double -> Double -> Bool
ltDouble = Base.v_ltDouble

intToDouble :: Int -> Double
intToDouble = Base.v_intToDouble

formatDouble :: Int -> Double -> String
formatDouble = Base.v_formatDouble

newIntArray :: Int -> Int -> IO IntArray
newIntArray = IO.v_newIntArray

readIntArray :: IntArray -> Int -> IO Int
readIntArray = IO.v_readIntArray

writeIntArray :: IntArray -> Int -> Int -> IO ()
writeIntArray = IO.v_writeIntArray

lengthIntArray :: IntArray -> IO Int
lengthIntArray = IO.v_lengthIntArray

newDoubleArray :: Int -> Double -> IO DoubleArray
newDoubleArray = IO.v_newDoubleArray

readDoubleArray :: DoubleArray -> Int -> IO Double
readDoubleArray = IO.v_readDoubleArray

writeDoubleArray :: DoubleArray -> Int -> Double -> IO ()
writeDoubleArray = IO.v_writeDoubleArray

lengthDoubleArray :: DoubleArray -> IO Int
lengthDoubleArray = IO.v_lengthDoubleArray

newByteArray :: Int -> Int -> IO ByteArray
newByteArray = IO.v_newByteArray

readByteArray :: ByteArray -> Int -> IO Int
readByteArray = IO.v_readByteArray

writeByteArray :: ByteArray -> Int -> Int -> IO ()
writeByteArray = IO.v_writeByteArray

lengthByteArray :: ByteArray -> IO Int
lengthByteArray = IO.v_lengthByteArray

byteArrayFromString :: String -> IO ByteArray
byteArrayFromString = IO.v_byteArrayFromString

putBytes :: ByteArray -> Int -> Int -> IO ()
putBytes = IO.v_putBytes

getByteLine :: IO ByteArray
getByteLine = IO.v_getByteLine

newIntTable :: IO IntTable
newIntTable = IO.v_newIntTable

readIntTable :: IntTable -> Int -> IO Int
readIntTable = IO.v_readIntTable

writeIntTable :: IntTable -> Int -> Int -> IO ()
writeIntTable = IO.v_writeIntTable

andInt :: Int -> Int -> Int
andInt = Base.v_andInt

stringLength :: String -> Int
stringLength = Base.v_stringLength

stringCodeAt :: String -> Int -> Int
stringCodeAt = Base.v_stringCodeAt

stringSlice :: String -> Int -> Int -> String
stringSlice = Base.v_stringSlice

stringFromCode :: Int -> String
stringFromCode = Base.v_stringFromCode

compareString :: String -> String -> Int
compareString = Base.v_compareString

readDouble :: String -> Double
readDouble = Base.v_readDouble

doubleToBits :: Double -> Int
doubleToBits = Base.v_doubleToBits

doubleFromBits :: Int -> Double
doubleFromBits = Base.v_doubleFromBits

seq :: a -> b -> b
seq = Base.v_seq

panic :: String -> a
panic = Base.v_panic

readFile :: String -> IO String
readFile = IO.v_readFile

writeFile :: String -> String -> IO ()
writeFile = IO.v_writeFile

fileExists :: String -> IO Bool
fileExists = IO.v_fileExists

canonicalPath :: String -> IO String
canonicalPath = IO.v_canonicalPath

getArgCount :: IO Int
getArgCount = IO.v_getArgCount

getArg :: Int -> IO String
getArg = IO.v_getArg

putErr :: String -> IO ()
putErr = IO.v_putErr

exitWith :: Int -> IO a
exitWith = IO.v_exitWith

getExecutablePath :: IO String
getExecutablePath = IO.v_getExecutablePath

getContents :: IO String
getContents = IO.v_getContents

stReturn :: a -> ST s a
stReturn = Base.v_stReturn

stBind :: ST s a -> (a -> ST s b) -> ST s b
stBind = Base.v_stBind

runST :: (forall s. ST s a) -> a
runST = Base.v_runST

newSTArray :: Int -> a -> ST s (STArray s a)
newSTArray = Base.v_newSTArray

readSTArray :: STArray s a -> Int -> ST s a
readSTArray = Base.v_readSTArray

writeSTArray :: STArray s a -> Int -> a -> ST s ()
writeSTArray = Base.v_writeSTArray

lengthSTArray :: STArray s a -> ST s Int
lengthSTArray = Base.v_lengthSTArray

getEnv :: String -> IO String
getEnv = IO.v_getEnv

setEnv :: String -> String -> IO ()
setEnv = IO.v_setEnv

unsetEnv :: String -> IO ()
unsetEnv = IO.v_unsetEnv

runProcess :: String -> String -> IO Int
runProcess = IO.v_runProcess

listDirectory :: String -> IO String
listDirectory = IO.v_listDirectory

directoryExists :: String -> IO Bool
directoryExists = IO.v_directoryExists

fileDigest :: String -> IO String
fileDigest = IO.v_fileDigest

acquireFileLock :: String -> IO Int
acquireFileLock = IO.v_acquireFileLock

releaseFileLock :: Int -> IO ()
releaseFileLock = IO.v_releaseFileLock

processSupervisor :: String -> IO String
processSupervisor = IO.v_processSupervisor

asyncScopeNew :: Int -> Int -> IO AsyncScope
asyncScopeNew = Async.v_asyncScopeNew

asyncScopeClose :: AsyncScope -> IO ()
asyncScopeClose = Async.v_asyncScopeClose

asyncNewCompletion :: AsyncScope -> (Completion a -> IO b) -> IO b -> IO b
asyncNewCompletion = Async.v_asyncNewCompletion

asyncResolveCompletion :: Completion a -> a -> IO Int
asyncResolveCompletion = Async.v_asyncResolveCompletion

asyncReadCompletion :: Completion a -> (a -> IO b) -> IO b -> IO b
asyncReadCompletion = Async.v_asyncReadCompletion

asyncSubscribeCompletion :: Completion a -> (a -> IO ()) -> IO AsyncSubscription
asyncSubscribeCompletion = Async.v_asyncSubscribeCompletion

asyncSubscriptionStatus :: AsyncSubscription -> IO Int
asyncSubscriptionStatus = Async.v_asyncSubscriptionStatus

asyncCancelSubscription :: AsyncSubscription -> IO Int
asyncCancelSubscription = Async.v_asyncCancelSubscription

asyncStep :: AsyncScope -> IO Int
asyncStep = Async.v_asyncStep

asyncEnqueue :: AsyncScope -> IO () -> IO AsyncSubscription
asyncEnqueue = Async.v_asyncEnqueue

asyncDelay :: AsyncScope -> Int -> IO () -> IO AsyncSubscription
asyncDelay = Async.v_asyncDelay

asyncWait :: AsyncScope -> Int -> IO Int
asyncWait = Async.v_asyncWait
implementationHost :: String
implementationHost = Base.literal "GHC"

-- Compatibility spelling is an ordinary value, not a do-notation hook.
bind :: Monad m => m a -> (a -> m b) -> m b
bind = (P.>>=)

negate :: Int -> Int
negate = subInt 0
otherwise :: Bool
otherwise = True

infixr 2 ||
infixr 3 &&
infix 4 <, <=, >, >=
infixr 5 ++
infixl 6 +, -
infixl 7 *, /, %
(+), (-), (*), (/), (%) :: Int -> Int -> Int
(+) = addInt
(-) = subInt
(*) = mulInt
(/) = quotInt
(%) = remInt
(<), (<=), (>), (>=) :: Int -> Int -> Bool
(<) = ltInt
(<=) = Base.leInt
(>) = Base.gtInt
(>=) = Base.geInt
(++) :: String -> String -> String
(++) = concatString
(&&), (||) :: Bool -> Bool -> Bool
(&&) a b = if a then b else False
(||) a b = if a then True else b
