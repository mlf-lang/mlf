{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module SharedIdentity where
import MLF.Primitive

data Box a = Box a
instance Functor Box where
  fmap f (Box x) = Box (f x)
instance Applicative Box where
  pure = Box
  Box f <*> Box x = Box (f x)
instance Monad Box where
  Box x >>= f = f x

custom :: Box Int
custom = do
  x <- pure 40
  pure (x + 2)

numberPattern :: Int -> Int
numberPattern 0 = 7
numberPattern n = n

numberGuard :: Int -> Int
numberGuard n | n == 0 = 9
              | otherwise = n

truth :: Bool
truth = True

large :: Int
large = 1267650600228229401496703205376

message :: String
message = "a😀\0"
