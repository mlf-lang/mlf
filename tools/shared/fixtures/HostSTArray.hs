{-# LANGUAGE RankNTypes #-}
module Main where

import Prelude
import Control.Exception (evaluate, try)
import qualified MLF.Host.Base as B

poison :: String -> a
poison = B.failure

check :: String -> Integer -> Integer -> IO ()
check label expected actual = do
  value <- evaluate actual
  if value == expected then putStrLn ("PASS " ++ label)
  else error (label ++ ": expected " ++ show expected ++ ", got " ++ show value)

reject :: String -> String -> Integer -> IO ()
reject label message actual = do
  result <- try (evaluate actual) :: IO (Either B.HostError Integer)
  case result of
    Left (B.HostError observed) | observed == message -> putStrLn ("PASS " ++ label)
    Left (B.HostError observed) -> error (label ++ ": wrong error " ++ observed)
    Right value -> error (label ++ ": accepted " ++ show value)

readAt :: Integer -> Integer -> Integer
readAt size index = B.v_runST $ do
  array <- B.v_newSTArray size (7 :: Integer)
  B.v_readSTArray array index

writeAt :: Integer -> Integer -> Integer
writeAt size index = B.v_runST $ do
  array <- B.v_newSTArray size (7 :: Integer)
  B.v_writeSTArray array index (poison "written cell")
  B.v_lengthSTArray array

main :: IO ()
main = do
  check "empty array retains lazy initial value" 0 $ B.v_runST $ do
    array <- B.v_newSTArray 0 (poison "initial cell" :: Integer)
    B.v_lengthSTArray array
  check "length retains lazy initial value" 3 $ B.v_runST $ do
    array <- B.v_newSTArray 3 (poison "initial cell" :: Integer)
    B.v_lengthSTArray array
  check "first index" 7 (readAt 3 0)
  check "last index" 7 (readAt 3 2)
  check "write retains lazy value" 1 (writeAt 1 0)
  check "ignored read retains lazy cell" 42 $ B.v_runST $ do
    array <- B.v_newSTArray 1 (poison "initial cell" :: Integer)
    _ <- B.v_readSTArray array 0
    pure 42
  check "write then read" 42 $ B.v_runST $ do
    array <- B.v_newSTArray 2 (poison "initial cell" :: Integer)
    B.v_writeSTArray array 1 42
    B.v_readSTArray array 1
  check "read snapshots before write" 7 $ B.v_runST $ do
    array <- B.v_newSTArray 1 (7 :: Integer)
    old <- B.v_readSTArray array 0
    B.v_writeSTArray array 0 42
    pure old
  check "repeated read action observes each execution" 49 $ B.v_runST $ do
    array <- B.v_newSTArray 1 (7 :: Integer)
    let readCell = B.v_readSTArray array 0
    before <- readCell
    B.v_writeSTArray array 0 42
    after <- readCell
    pure (before + after)
  check "repeated allocation action creates independent arrays" 7 $ B.v_runST $ do
    let allocate = B.v_newSTArray 1 (7 :: Integer)
    first <- allocate
    second <- allocate
    B.v_writeSTArray first 0 42
    B.v_readSTArray second 0
  check "independent cells" 15 $ B.v_runST $ do
    array <- B.v_newSTArray 3 (7 :: Integer)
    B.v_writeSTArray array 1 1
    left <- B.v_readSTArray array 0
    middle <- B.v_readSTArray array 1
    right <- B.v_readSTArray array 2
    pure (left + middle + right)
  check "unused read action" 42 $ B.v_runST $ do
    let action = B.v_readSTArray (poison "array") (poison "index")
    action `seq` pure 42
  check "unused allocation action" 42 $ B.v_runST $ do
    let action = B.v_newSTArray (poison "length") (poison "initial cell" :: Integer)
    action `seq` pure 42
  reject "negative allocation" "invalid array length" (readAt (-1) 0)
  reject "huge allocation" "invalid array length" (readAt (10^80) 0)
  reject "allocation demands length before initial" "length" (readAt (poison "length") 0)
  mapM_ (\(label,size,index) -> do
    reject ("read " ++ label) "array index out of bounds" (readAt size index)
    reject ("write " ++ label) "array index out of bounds" (writeAt size index))
    [("negative index",1,-1), ("past end",1,1), ("empty",0,0),
     ("huge positive index",1,10^80), ("huge negative index",1,negate (10^80))]
  reject "empty read demands index" "index" (readAt 0 (poison "index"))
  reject "empty write demands index before value" "index" (writeAt 0 (poison "index"))
  reject "read demands array before index" "array" $ B.v_runST
    (B.v_readSTArray (poison "array") (poison "index"))
  reject "write demands array before index and value" "array" $ B.v_runST $ do
    B.v_writeSTArray (poison "array") (poison "index") (poison "written cell" :: Integer)
    pure 42
  reject "length demands array" "array" $ B.v_runST
    (B.v_lengthSTArray (poison "array"))
  reject "demanded initial cell" "initial cell" $ B.v_runST $ do
    array <- B.v_newSTArray 1 (poison "initial cell" :: Integer)
    B.v_readSTArray array 0
  reject "demanded written cell" "written cell" $ B.v_runST $ do
    array <- B.v_newSTArray 1 (7 :: Integer)
    B.v_writeSTArray array 0 (poison "written cell")
    B.v_readSTArray array 0
  putStrLn "PASS 33 host ST array controls"
