{-# LANGUAGE NoImplicitPrelude, KindSignatures #-}
module MLF.Primitive
  (Int, Double, String, Bool(..), List(..), Pair(..), Functor(..), Applicative(..), Monad(..), bind,
   fromInteger, fromRational, fromString, negate, ifThenElse,
   (+), (-), (*), (==), (/=), (<), (<=), (>), (>=),
   eqString, eqInt, doubleToBits, doubleFromBits, panic) where
import qualified Prelude as P
import Prelude (Bool(..), Functor(..), Applicative(..), Monad(..))
import qualified GHC.Float as F
type Int = P.Integer
type Double = P.Double
type String = P.String
data List a = Nil | Cons a (List a)
data Pair a b = Pair a b
bind :: Monad m => m a -> (a -> m b) -> m b
bind = (P.>>=)
fromInteger :: P.Integer -> Int
fromInteger = P.id
fromRational :: P.Rational -> Double
fromRational = P.fromRational
fromString :: P.String -> String
fromString = P.id
negate :: Int -> Int
negate = P.negate
ifThenElse :: Bool -> a -> a -> a
ifThenElse condition yes no = case condition of {True -> yes; False -> no}
(+) :: Int -> Int -> Int
(+) = (P.+)
(-) :: Int -> Int -> Int
(-) = (P.-)
(*) :: Int -> Int -> Int
(*) = (P.*)
(==), (/=), (<), (<=), (>), (>=) :: Int -> Int -> Bool
(==) = (P.==)
(/=) = (P./=)
(<) = (P.<)
(<=) = (P.<=)
(>) = (P.>)
(>=) = (P.>=)
eqString :: String -> String -> Bool
eqString = (P.==)
eqInt :: Int -> Int -> Bool
eqInt = (P.==)
doubleToBits :: Double -> Int
doubleToBits value = P.toInteger (F.castDoubleToWord64 value)
doubleFromBits :: Int -> Double
doubleFromBits value = F.castWord64ToDouble (P.fromInteger value)
panic :: String -> a
panic = P.error
infixl 6 +, -
infixl 7 *
infix 4 ==, /=, <, <=, >, >=
