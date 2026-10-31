{-# LANGUAGE RankNTypes, KindSignatures, FlexibleInstances, ForeignFunctionInterface, ConstraintKinds, MagicHash #-}
module MLF.Host.Base
  ( Int, Integer, Bool(..), Double, Char, IO, String, ST, STArray
  , MLFCallStack, MLFHasCallStack, MLFStackFrame(..), MLFStackEvidence(..)
  , v_emptyCallStack, v_pushCallStack, v_prettyCallStack
  , literal, unpack, utf8, fromUtf8, matchString, neInt, leInt, gtInt, geInt
  , v_textToChars, v_textFromChars, v_charCode, v_charFromCode
  , v_ioReturn, v_ioBind, v_stReturn, v_stBind, v_runST
  , v_newSTArray, v_readSTArray, v_writeSTArray, v_lengthSTArray
  , v_addInt, v_subInt, v_mulInt, v_quotInt, v_remInt, v_eqInt, v_ltInt, v_andInt
  , v_orInt, v_xorInt, v_shiftLInt, v_shiftRInt, v_unsignedShiftRInt
  , v_countLeadingZerosInt, v_countTrailingZerosInt, v_popCountInt, v_unsignedLtInt
  , v_intToInteger, v_integerToInt, v_addInteger, v_subInteger, v_mulInteger
  , v_quotInteger, v_remInteger, v_eqInteger, v_ltInteger, v_showInteger, v_readInteger, v_integerToDouble
  , v_addDouble, v_subDouble, v_mulDouble, v_divDouble, v_sqrtDouble
  , v_eqDouble, v_ltDouble, v_intToDouble, v_doubleToBits, v_doubleFromBits
  , v_concatString, v_concatStringList, v_eqString, v_compareString, v_stringLength, v_stringCodeAt
  , v_stringSlice, v_stringFromCode, v_showInt, v_readInt, v_readDouble, v_formatDouble
  , v_ifThenElse, v_seq, v_panic, HostError(..), failure, bounded, strict2
  ) where

import Prelude hiding (Int, String)
import qualified Prelude as P
import qualified Data.Text as T
import qualified Data.Text.Internal as TI
import qualified Data.Text.Array as TA
import qualified Data.Text.Encoding as TE
import qualified Data.ByteString as BS
import Data.Char (ord, chr)
import qualified Data.String as TextLiteral
import qualified GHC.Stack as Stack
import qualified Data.Array as Array
import Data.Bits ((.&.))
import qualified Data.Int as Fixed
import qualified Data.Bits as Bits
import qualified Data.Word as Word
import Data.Typeable (Typeable)
import Control.Exception (Exception, throw)
import qualified Control.Monad.ST as S
import qualified Data.Array.ST as A
import qualified Data.Array.Base as AB
import GHC.Float (castDoubleToWord64, castWord64ToDouble)
import GHC.Conc (pseq)
import GHC.Exts (isTrue#, (<#))
import GHC.Num.Integer (Integer(IS))
import Foreign.C (CInt(..), CDouble(..), CString, peekCStringLen)
import Foreign.Marshal.Alloc (allocaBytes)
import System.IO.Unsafe (unsafeDupablePerformIO)
import Text.Read (readMaybe)

-- Language integers have the same signed, wrapping 64-bit representation on every host.
type Int = Fixed.Int64
type ST = S.ST
-- The private constructor fixes zero-based bounds once. Language lengths are
-- Int64; only a proven in-range index is converted to the host machine index.
data STArray s a = STArray !Int !(A.STArray s P.Int a)
-- Text is strict UTF-8 in the supported text-2 toolchain. String indices and
-- lengths below count Unicode scalars, never bytes or UTF-16 code units.
data String = String !T.Text !P.Int (Array.Array P.Int Char)
mkText :: T.Text -> String
mkText text = mkSizedText (T.length text) text
mkSizedText :: P.Int -> T.Text -> String
mkSizedText count text = String text count (Array.listArray (0,count-1) (T.unpack text))
-- Private compiler-managed evidence uses real GHC stack values on this host.
-- These adapters do not redefine the public HasCallStack constraint.
type MLFCallStack = Stack.CallStack
type MLFHasCallStack = Stack.HasCallStack
data MLFStackFrame = MLFStackFrame String String String String Int Int Int Int
data MLFStackEvidence = MLFStackEvidence MLFCallStack
v_emptyCallStack :: MLFCallStack
v_emptyCallStack = Stack.emptyCallStack
v_pushCallStack :: MLFStackFrame -> MLFCallStack -> MLFCallStack
v_pushCallStack (MLFStackFrame name packageName moduleName file sl sc el ec) =
  Stack.pushCallStack (unpack name, Stack.SrcLoc (unpack packageName) (unpack moduleName)
    (unpack file) (coordinate sl) (coordinate sc) (coordinate el) (coordinate ec))
  where coordinate n
          | n < fromIntegral (minBound :: P.Int) || n > fromIntegral (maxBound :: P.Int)
          = failure "source coordinate out of bounds"
          | otherwise = fromIntegral n
v_prettyCallStack :: MLFCallStack -> [Char]
v_prettyCallStack = Stack.prettyCallStack

data HostError = HostError P.String deriving (Show, Typeable)
instance Exception HostError
failure :: P.String -> a
failure = throw . HostError
v_panic :: String -> a
v_panic s = s `pseq` failure (unpack s)

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

-- Canonical Haskell character lists are distinct from our opaque UTF-8 text.
-- Char includes surrogate codepoints; converting those to text rejects them.
v_textToChars :: String -> [Char]
v_textToChars = unpack
v_textFromChars :: [Char] -> String
v_textFromChars = literal
v_charCode :: Char -> Int
v_charCode = fromIntegral . ord
v_charFromCode :: Int -> Char
v_charFromCode n = chr (bounded "invalid Char codepoint" 0x10ffff n)

-- Ordinary Haskell overloaded string literals use the standard class.  This
-- instance is representation adaptation, not a source-language syntax hook.
instance Eq String where
  (==) = v_eqString

instance TextLiteral.IsString String where
  fromString = literal
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
bounded message limit n = if n<0 || n>limit || n>fromIntegral (maxBound::P.Int)
  then failure message else fromIntegral n
arrayLength :: Int -> P.Int
arrayLength = bounded "invalid array length" (9223372036854775807 `quot` 8)
v_newSTArray :: Int -> a -> ST s (STArray s a)
v_newSTArray n initial = pure n >>= \operand -> do
  let size=arrayLength operand
  cells <- size `pseq` A.newArray (0,size-1) initial
  pure (STArray (fromIntegral size) cells)
stIndex :: Int -> Int -> P.Int
stIndex size n =
  if n<0 || n>=size then failure "array index out of bounds" else fromIntegral n
v_readSTArray :: STArray s a -> Int -> ST s a
v_readSTArray a n = pure a >>= \(STArray size cells) ->
  let i=stIndex size n in i `pseq` AB.unsafeRead cells i
v_writeSTArray :: STArray s a -> Int -> a -> ST s ()
v_writeSTArray a n value = pure a >>= \(STArray size cells) ->
  let i=stIndex size n in i `pseq` AB.unsafeWrite cells i value
v_lengthSTArray :: STArray s a -> ST s Int
v_lengthSTArray a = pure a >>= \(STArray size _) -> pure size

strict2 :: (a -> b -> c) -> a -> b -> c
strict2 f a b = a `pseq` b `pseq` f a b
v_addInt, v_subInt, v_mulInt, v_quotInt, v_remInt, v_andInt :: Int -> Int -> Int
v_addInt = strict2 (+)
v_subInt = strict2 (-)
v_mulInt = strict2 (*)
v_quotInt = strict2 (\a b -> if b==0 then failure "integer division by zero"
  else if a==minBound && b==(-1) then failure "integer division overflow" else quot a b)
v_remInt = strict2 (\a b -> if b==0 then failure "integer division by zero" else rem a b)
v_andInt = strict2 (.&.)

-- These operations already use machine Int64 arithmetic. The former
-- Integer-to-Int64 rolling-hash rules and their guarded fallback are unnecessary.
{-# INLINE v_addInt #-}
{-# INLINE v_subInt #-}
{-# INLINE v_mulInt #-}
{-# INLINE v_remInt #-}

v_eqInt, v_ltInt, neInt, leInt, gtInt, geInt :: Int -> Int -> Bool
v_eqInt = strict2 (==)
v_ltInt = strict2 (<)
{-# INLINE v_ltInt #-}
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
v_intToDouble = fromIntegral
v_doubleToBits :: Double -> Int
v_doubleToBits = fromIntegral . castDoubleToWord64
v_doubleFromBits :: Int -> Double
v_doubleFromBits = castWord64ToDouble . fromIntegral
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
v_readInt = readDecimal
-- Preserve MLF's signed-decimal grammar. Overflow follows the destination
-- Num instance: Int64 wraps and explicit Integer remains arbitrary precision.
readDecimal :: Num a => String -> a
readDecimal text = let { chars=unpack text; (negative,digits)=case chars of { '-':xs -> (True,xs); '+':xs -> (False,xs); _ -> (False,chars) } }
                in if null digits || any (\c -> c<'0'||c>'9') digits then failure "invalid integer input"
                   else let n=foldl (\a c -> a*10+fromIntegral (ord c-48)) 0 digits in if negative then negate n else n
{-# INLINE readDecimal #-}
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
-- Force each fragment before demanding the next list cell, matching the
-- balanced source join's observable failure order. Text.concat then copies
-- the validated fragments once rather than at every balanced-tree level.
v_concatStringList :: [String] -> String
v_concatStringList pieces = case pieces of
  [] -> literal ""
  first:rest -> first `pseq` case rest of
    [] -> first
    _ -> collect 0 0 [] pieces
  where
    collect scalarCount byteCount chunks remaining = case remaining of
      [] -> mkSizedText scalarCount (T.concat (reverse chunks))
      piece:rest -> piece `pseq` case piece of
        String text count _ -> case text of
          TI.Text _ _ bytes ->
            if count > maxBound - scalarCount || bytes > maxBound - byteCount
            then failure "string too large"
            else let nextScalars = scalarCount + count
                     nextBytes = byteCount + bytes
                 in nextScalars `pseq` nextBytes `pseq`
                      collect nextScalars nextBytes (text:chunks) rest
v_eqString :: String -> String -> Bool
v_eqString = strict2 (\(String a _ _) (String b _ _) -> a==b)
v_compareString :: String -> String -> Int
v_compareString = strict2 (\(String a _ _) (String b _ _) -> case compare a b of { LT -> -1; EQ -> 0; GT -> 1 })
v_stringLength :: String -> Int
v_stringLength (String _ n _) = fromIntegral n
-- All String constructors are private and preserve valid UTF-8 plus exact
-- scalar count. Equality of byte/scalar counts proves ASCII. Bounds precede
-- unchecked byte indexing; slice copies to avoid retaining the source buffer.
v_stringCodeAt :: String -> Int -> Int
v_stringCodeAt text@(String t size characters) index = text `pseq` index `pseq`
  let i=bounded "string index out of bounds" (fromIntegral size-1) index
  in case t of
    TI.Text bytes offset byteLength
      | byteLength == size -> i `pseq` fromIntegral (TA.unsafeIndex bytes (offset+i))
      | otherwise -> fromIntegral (ord (characters Array.! i))
v_stringSlice :: String -> Int -> Int -> String
v_stringSlice text@(String t size characters) start count = text `pseq` start `pseq` count `pseq`
  let i=bounded "string slice out of bounds" (fromIntegral size) start
      n=bounded "string slice out of bounds" (fromIntegral size-start) count
  in i `pseq` n `pseq` case t of
    TI.Text bytes offset byteLength
      | byteLength == size -> mkSizedText n (T.copy (TI.text bytes (offset+i) n))
      | otherwise -> literal [characters Array.! j | j <- [i..i+n-1]]
v_stringFromCode :: Int -> String
v_stringFromCode n = if n<0 || n>0x10ffff || (n>=0xd800 && n<=0xdfff) then failure "invalid Unicode scalar" else literal [chr (fromIntegral n)]
v_ifThenElse :: Bool -> a -> a -> a
v_ifThenElse c a b = if c then a else b
v_seq :: a -> b -> b
v_seq = pseq

-- Explicit arbitrary precision is separate from language Int.
v_intToInteger :: Int -> Integer
v_intToInteger = toInteger
v_integerToInt :: Integer -> Int
v_integerToInt = fromInteger
v_addInteger, v_subInteger, v_mulInteger, v_quotInteger, v_remInteger :: Integer -> Integer -> Integer
v_addInteger = strict2 (+)
v_subInteger = strict2 (-)
v_mulInteger = strict2 (*)
v_quotInteger = strict2 (\a b -> if b==0 then failure "integer division by zero" else quot a b)
v_remInteger = strict2 (\a b -> if b==0 then failure "integer division by zero" else rem a b)
v_eqInteger, v_ltInteger :: Integer -> Integer -> Bool
v_eqInteger = strict2 (==)
-- Keep the language's ordered demand, then expose the common small-Integer
-- representation to callers. Large operands retain arbitrary-precision order;
-- no conversion or range truncation is involved in the small case.
v_ltInteger a b = a `pseq` b `pseq` case a of
  IS x# -> case b of
    IS y# -> isTrue# (x# <# y#)
    _ -> integerLtFallback a b
  _ -> integerLtFallback a b
{-# INLINE v_ltInteger #-}

-- Keep uncommon arbitrary-precision cases out of each caller's hot path.
integerLtFallback :: Integer -> Integer -> Bool
integerLtFallback = (<)
{-# NOINLINE integerLtFallback #-}
v_showInteger :: Integer -> String
v_showInteger = literal . show
v_readInteger :: String -> Integer
v_readInteger = readDecimal
v_integerToDouble :: Integer -> Double
v_integerToDouble = fromInteger

v_unsignedLtInt :: Int -> Int -> Bool
v_unsignedLtInt = strict2 (\a b -> (fromIntegral a :: Word.Word64) < fromIntegral b)
{-# INLINE v_unsignedLtInt #-}

v_orInt, v_xorInt, v_shiftLInt, v_shiftRInt, v_unsignedShiftRInt :: Int -> Int -> Int
v_orInt = strict2 (Bits..|.)
v_xorInt = strict2 Bits.xor
v_shiftLInt = strict2 (\x n -> if n<0 then failure "integer shift overflow"
  else if n>=64 then 0 else Bits.shiftL x (fromIntegral n))
v_shiftRInt = strict2 (\x n -> if n<0 then failure "integer shift overflow"
  else if n>=64 then if x<0 then -1 else 0 else Bits.shiftR x (fromIntegral n))
v_unsignedShiftRInt = strict2 (\x n -> if n<0 then failure "integer shift overflow"
  else if n>=64 then 0 else fromIntegral (Bits.shiftR (fromIntegral x :: Word.Word64) (fromIntegral n)))
v_countLeadingZerosInt, v_countTrailingZerosInt, v_popCountInt :: Int -> Int
v_countLeadingZerosInt = fromIntegral . Bits.countLeadingZeros
v_countTrailingZerosInt = fromIntegral . Bits.countTrailingZeros
v_popCountInt = fromIntegral . Bits.popCount
