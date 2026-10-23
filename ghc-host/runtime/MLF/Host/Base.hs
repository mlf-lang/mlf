{-# LANGUAGE RankNTypes, KindSignatures, FlexibleInstances, ForeignFunctionInterface #-}
module MLF.Host.Base
  ( Int, Bool(..), Double, IO, Unit(..), String, ST, STArray
  , Monad(..), literal, unpack, utf8, fromUtf8, matchString, neInt, leInt, gtInt, geInt
  , v_ioReturn, v_ioBind, v_stReturn, v_stBind, v_runST
  , v_newSTArray, v_readSTArray, v_writeSTArray, v_lengthSTArray
  , v_addInt, v_subInt, v_mulInt, v_quotInt, v_remInt, v_eqInt, v_ltInt, v_andInt
  , v_addDouble, v_subDouble, v_mulDouble, v_divDouble, v_sqrtDouble
  , v_eqDouble, v_ltDouble, v_intToDouble, v_doubleToBits, v_doubleFromBits
  , v_concatString, v_eqString, v_compareString, v_stringLength, v_stringCodeAt
  , v_stringSlice, v_stringFromCode, v_showInt, v_readInt, v_readDouble, v_formatDouble
  , v_ifThenElse, v_seq, v_panic, HostError(..), failure, bounded, strict2
  ) where

import Prelude hiding (Int, String, Monad)
import qualified Prelude as P
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import qualified Data.ByteString as BS
import Data.Char (ord, chr)
import qualified Data.Array as Array
import Data.Bits ((.&.))
import Data.Typeable (Typeable)
import Control.Exception (Exception, throw)
import qualified Control.Monad.ST as S
import qualified Data.Array.ST as A
import GHC.Float (castDoubleToWord64, castWord64ToDouble)
import GHC.Conc (pseq)
import Foreign.C (CInt(..), CDouble(..), CString, peekCStringLen)
import Foreign.Marshal.Alloc (allocaBytes)
import System.IO.Unsafe (unsafeDupablePerformIO)
import Text.Read (readMaybe)

type Int = Integer
type ST = S.ST
type STArray s a = A.STArray s P.Int a
data Unit = Unit
-- Text is strict UTF-8 in the supported text-2 toolchain. String indices and
-- lengths below count Unicode scalars, never bytes or UTF-16 code units.
data String = String !T.Text !P.Int (Array.Array P.Int Char)
mkText :: T.Text -> String
mkText text = mkSizedText (T.length text) text
mkSizedText :: P.Int -> T.Text -> String
mkSizedText count text = String text count (Array.listArray (0,count-1) (T.unpack text))
data HostError = HostError P.String deriving (Show, Typeable)
instance Exception HostError
failure :: P.String -> a
failure = throw . HostError
v_panic :: String -> a
v_panic s = failure (unpack s)

literal :: P.String -> String
literal chars = if any (\c -> let n=ord c in n>=0xd800 && n<=0xdfff) chars
  then failure "invalid Unicode scalar" else mkText (T.pack chars)
unpack :: String -> P.String
unpack (String t _ _) = T.unpack t
utf8 :: String -> BS.ByteString
utf8 (String t _ _) = TE.encodeUtf8 t
fromUtf8 :: BS.ByteString -> String
fromUtf8 bytes = case TE.decodeUtf8' bytes of
  Left _ -> failure "IO error: invalid UTF-8 input"
  Right t -> mkText t
matchString :: P.String -> String -> Bool
matchString chars value = v_eqString value (literal chars)

class Monad (m :: * -> *) where
  v_return :: a -> m a
  v_bind :: m a -> (a -> m b) -> m b
instance Monad IO where
  v_return = pure
  v_bind = (>>=)
instance Monad (ST s) where
  v_return = pure
  v_bind = (>>=)
v_ioReturn :: a -> IO a
v_ioReturn = pure
v_ioBind :: IO a -> (a -> IO b) -> IO b
v_ioBind = (>>=)
v_stReturn :: a -> ST s a
v_stReturn = pure
v_stBind :: ST s a -> (a -> ST s b) -> ST s b
v_stBind = (>>=)
v_runST :: (forall s. ST s a) -> a
v_runST = S.runST

bounded :: P.String -> Int -> Int -> P.Int
bounded message limit n = if n<0 || n>limit || n>toInteger (maxBound::P.Int)
  then failure message else fromInteger n
arrayLength :: Int -> P.Int
arrayLength = bounded "invalid array length" (9223372036854775807 `quot` 8)
v_newSTArray :: Int -> a -> ST s (STArray s a)
v_newSTArray n initial = pure n >>= \operand ->
  let size=arrayLength operand in size `pseq` A.newArray (0,size-1) initial
stIndex :: STArray s a -> Int -> ST s P.Int
stIndex a n = do
  (_,hi) <- A.getBounds a
  let i=bounded "array index out of bounds" (toInteger hi) n
  i `seq` pure i
v_readSTArray :: STArray s a -> Int -> ST s a
v_readSTArray a n = stIndex a n >>= A.readArray a
v_writeSTArray :: STArray s a -> Int -> a -> ST s Unit
v_writeSTArray a n value = do
  i <- stIndex a n
  A.writeArray a i value
  pure Unit
v_lengthSTArray :: STArray s a -> ST s Int
v_lengthSTArray a = do
  (_,hi) <- A.getBounds a
  pure (toInteger hi+1)

strict2 :: (a -> b -> c) -> a -> b -> c
strict2 f a b = a `pseq` b `pseq` f a b
v_addInt, v_subInt, v_mulInt, v_quotInt, v_remInt, v_andInt :: Int -> Int -> Int
v_addInt = strict2 (+)
v_subInt = strict2 (-)
v_mulInt = strict2 (*)
v_quotInt = strict2 (\a b -> if b==0 then failure "integer division by zero" else quot a b)
v_remInt = strict2 (\a b -> if b==0 then failure "integer division by zero" else rem a b)
v_andInt = strict2 (.&.)
v_eqInt, v_ltInt, neInt, leInt, gtInt, geInt :: Int -> Int -> Bool
v_eqInt = strict2 (==)
v_ltInt = strict2 (<)
neInt a b = not (v_eqInt a b)
leInt a b = not (v_ltInt b a)
gtInt a b = v_ltInt b a
geInt a b = not (v_ltInt a b)
v_addDouble, v_subDouble, v_mulDouble, v_divDouble :: Double -> Double -> Double
v_addDouble = strict2 (+)
v_subDouble = strict2 (-)
v_mulDouble = strict2 (*)
v_divDouble = strict2 (/)
v_sqrtDouble :: Double -> Double
v_sqrtDouble = sqrt
v_eqDouble, v_ltDouble :: Double -> Double -> Bool
v_eqDouble = strict2 (==)
v_ltDouble = strict2 (<)
v_intToDouble :: Int -> Double
v_intToDouble = fromInteger
v_doubleToBits :: Double -> Int
v_doubleToBits = toInteger . castDoubleToWord64
v_doubleFromBits :: Int -> Double
v_doubleFromBits n = if n<0 || n>18446744073709551615 then failure "Double bit pattern out of bounds" else castWord64ToDouble (fromInteger n)
foreign import ccall unsafe "mlf_ghc_format" c_format :: CInt -> CDouble -> CString -> IO CInt
-- This FFI operation is pure: it writes only the supplied private buffer and
-- reads the initial C numeric locale, as the native runtime does. It owns no
-- language values and does not touch GMP/GC or process state.
formatFinite :: P.Int -> Double -> P.String
formatFinite places value = unsafeDupablePerformIO $ allocaBytes 384 $ \buffer -> do
  n <- c_format (fromIntegral places) (CDouble value) buffer
  if n<0 || n>=384 then pure (failure "Double formatting failed") else peekCStringLen (buffer,fromIntegral n)
v_formatDouble :: Int -> Double -> String
v_formatDouble places value = places `pseq` value `pseq`
  let p=bounded "Double precision must be between 0 and 17" 17 places in p `seq`
  literal (if isNaN value then "NaN" else if isInfinite value then if value<0 then "-Infinity" else "Infinity" else formatFinite p value)
v_showInt :: Int -> String
v_showInt = literal . show
v_readInt :: String -> Int
v_readInt text = let { chars=unpack text; (negative,digits)=case chars of { '-':xs -> (True,xs); '+':xs -> (False,xs); _ -> (False,chars) } }
                in if null digits || any (\c -> c<'0'||c>'9') digits then failure "invalid integer input"
                   else let n=foldl (\a c -> a*10+toInteger (ord c-48)) 0 digits in if negative then negate n else n
v_readDouble :: String -> Double
v_readDouble text = let s=unpack text in
  if not (validDecimal s) then failure "invalid Double input" else
  case readMaybe (case s of { '+':xs -> xs; _ -> s }) of
    Just n -> n
    Nothing -> failure "invalid Double input"
  where validDecimal s = let unsigned=case s of { c:xs | c=='+' || c=='-' -> xs; _ -> s }
                             (whole,rest)=span digit unsigned
                         in not (null whole) && fraction rest
        digit c = c>='0' && c<='9'
        fraction ('.':xs) = let (digits,rest)=span digit xs in not (null digits) && exponent rest
        fraction xs = exponent xs
        exponent [] = True
        exponent (e:xs) | e=='e' || e=='E' = let digits=case xs of { c:ys | c=='+' || c=='-' -> ys; _ -> xs }
                                            in not (null digits) && all digit digits
        exponent _ = False
v_concatString :: String -> String -> String
v_concatString = strict2 (\(String a na _) (String b nb _) -> mkSizedText (na+nb) (T.append a b))
v_eqString :: String -> String -> Bool
v_eqString = strict2 (\(String a _ _) (String b _ _) -> a==b)
v_compareString :: String -> String -> Int
v_compareString = strict2 (\(String a _ _) (String b _ _) -> case compare a b of { LT -> -1; EQ -> 0; GT -> 1 })
v_stringLength :: String -> Int
v_stringLength (String _ n _) = toInteger n
v_stringCodeAt :: String -> Int -> Int
v_stringCodeAt text@(String _ size characters) index = text `pseq` index `pseq`
  let i=bounded "string index out of bounds" (toInteger size-1) index in toInteger (ord (characters Array.! i))
v_stringSlice :: String -> Int -> Int -> String
v_stringSlice text@(String _ size characters) start count = text `pseq` start `pseq` count `pseq`
  let i=bounded "string slice out of bounds" (toInteger size) start
      n=bounded "string slice out of bounds" (toInteger size-start) count
  in i `pseq` n `pseq` literal [characters Array.! j | j <- [i..i+n-1]]
v_stringFromCode :: Int -> String
v_stringFromCode n = if n<0 || n>0x10ffff || (n>=0xd800 && n<=0xdfff) then failure "invalid Unicode scalar" else literal [chr (fromInteger n)]
v_ifThenElse :: Bool -> a -> a -> a
v_ifThenElse c a b = if c then a else b
v_seq :: a -> b -> b
v_seq = pseq
