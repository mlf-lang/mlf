module Main where

import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (replicateM, unless)
import Data.Int (Int64)
import qualified Data.Map.Lazy as Oracle
import qualified Bootstrap.Map as M

cmp :: Int64 -> Int64 -> Int64
cmp a b = case compare a b of LT -> -1; EQ -> 0; GT -> 1

check :: String -> Bool -> IO ()
check label good = unless good (fail label)

caseOf :: [Int64] -> IO ()
caseOf keys = do
  let entries = zip keys (map (:[]) [0..] :: [[Int64]])
      ordinary = M.fromList cmp entries
      combined = M.fromListWith cmp (++) entries
  check ("fromList " ++ show keys)
    (M.toList ordinary == Oracle.toList (Oracle.fromList entries) && M.valid cmp ordinary)
  check ("fromListWith " ++ show keys)
    (M.toList combined == Oracle.toList (Oracle.fromListWith (++) entries) && M.valid cmp combined)
  -- Store the full representative as an oracle value, so the oracle's own
  -- policy for choosing equal keys cannot accidentally decide this check.
  let tagged = zipWith (\key ordinal -> ((key, ordinal), [ordinal])) keys [0..]
      order (a, _) (b, _) = cmp a b
      merge (newKey, newValue) (_, oldValue) = (newKey, newValue ++ oldValue)
      expected = map snd (Oracle.toList (Oracle.fromListWith merge
        [(key, (tag, value)) | (tag@(key, _), value) <- tagged]))
      actual = M.fromListWith order (++) tagged
      overwritten = M.fromList order tagged
      latest = map snd (Oracle.toList (Oracle.fromList
        [(key, (tag, value)) | (tag@(key, _), value) <- tagged]))
      combine new old = new * 131 + old * 17
      nonassociative = zip keys ([0..] :: [Int64])
  check ("representatives " ++ show keys) (M.toList actual == expected && M.valid order actual)
  check ("overwrite representatives " ++ show keys)
    (M.toList overwritten == latest && M.valid order overwritten)
  check ("nonassociative combine " ++ show keys)
    (M.toList (M.fromListWith cmp combine nonassociative) ==
      Oracle.toList (Oracle.fromListWith combine nonassociative))

expectBottom :: String -> Int64 -> IO ()
expectBottom message value = do
  result <- try (evaluate value) :: IO (Either SomeException Int64)
  check ("demand " ++ message) (case result of
    Left exception -> takeWhile (/= '\n') (displayException exception) == message
    Right _ -> False)

main :: IO ()
main = do
  let small = concatMap (\n -> replicateM n [-2..2]) [0..6]
      large = [keys | n <- [1,2,3,7,16,31,32,127,256,1024], keys <-
        [[0..n], reverse [0..n], concatMap (replicate 3) [0..n],
         [0..n] ++ [-1] ++ [0..n], [k * 79 `mod` (n + 1) | k <- [0..n]],
         concatMap (\k -> [k+3,k+2,k+1,k]) [0,4..n],
         concatMap (\k -> [k,k+1,k+2,k+3]) (reverse [0,4..n]),
         concatMap (\k -> [k,0,k,1,k,2]) [0..n]]]
  mapM_ caseOf (small ++ large)
  check "unselected value remains lazy"
    (M.get cmp 1 (M.fromList cmp [(-1, error "unselected"), (1, 17 :: Int64)]) == 17)
  check "replaced value remains lazy"
    (M.get cmp 1 (M.fromListWith cmp (\new _ -> new)
      [(1, error "replaced"), (1, 23 :: Int64)]) == 23)
  check "combination remains lazy"
    (M.size (M.fromListWith cmp (\_ _ -> error "deferred-combine")
      [(1, 0 :: Int64), (1, 0)]) == 1)
  expectBottom "first-key" (M.size (M.fromList cmp
    ((error "first-key", 0 :: Int64) : error "list-tail")))
  expectBottom "comparison" (M.size (M.fromList (\_ _ -> error "comparison")
    [(0 :: Int64, 0 :: Int64), (error "second-key", 0)]))
  check "empty comparator remains lazy"
    (M.size (M.fromList (\_ _ -> error "comparison") ([] :: [(Int64,Int64)])) == 0)
  check "singleton comparator and value remain lazy"
    (M.size (M.fromList (\_ _ -> error "comparison") [(0 :: Int64,error "value" :: Int64)]) == 1)
  check "descending duplicate discards old value"
    (M.get cmp 1 (M.fromList cmp [(2,0),(1,error "old"),(1,17 :: Int64),(0,0)]) == 17)
  check "cross-run duplicate discards old value"
    (M.get cmp 0 (M.fromList cmp [(0,error "old"),(2,0),(1,0),(0,17 :: Int64)]) == 17)
  check "cross-run unused value remains lazy"
    (M.get cmp 2 (M.fromList cmp [(0,error "unselected"),(2,17 :: Int64),(1,0)]) == 17)
  check "merged tree does not demand values"
    (M.size (M.fromList cmp [(key,error "value" :: Int64) | key <- [3,1,2,0]]) == 4)
  putStrLn ("PASS ordered maps: " ++ show (length small + length large) ++ " cases and 11 demand checks")
