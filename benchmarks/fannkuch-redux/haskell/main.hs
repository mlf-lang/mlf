
{-  The Computer Language Benchmarks Game

    https://salsa.debian.org/benchmarksgame-team/benchmarksgame/

    contributed by Branimir Maksimovic
    optimized/rewritten by Bryan O'Sullivan
    modified by Gabriel Gonzalez
    fix for GHC 9.2 by Artem Pelenitsyn    
-}

import System.Environment
import Text.Printf
import Data.Bits

import Data.Array.IO (IOUArray, newListArray, newArray)
import Data.Array.Base (unsafeRead, unsafeWrite)

main = do
    n <- getArgs >>= readIO.head
    (checksum,maxflips) <- fannkuch n
    printf "%d\nPfannkuchen(%d) = %d\n" checksum n maxflips

fannkuch :: Int -> IO (Int, Int)
fannkuch n = do
    perm <- newListArray (0,n-1) [1..n]
    !tperm <- newArray (0,n-1) 0
    !cnt <- newArray (0,n-1) 0
    let
        loop :: Int -> Int -> Int -> IO(Int,Int)
        loop !c !m !pc = do
            b <- next_permutation perm n cnt
            if b == False
            then return (c,m)
            else do
                copyInts n tperm perm
                let count_flips !flips = {-# SCC "count_flips" #-} do
                        f <- unsafeRead tperm 0
                        if f == 1
                        then loop (c + (if pc .&. 1 == 0 then flips else -flips))
                                (max m flips)
                                (pc+1)
                        else do
                                reversePrefix f tperm
                                count_flips (flips+1)
                count_flips 0
    loop 0 0 1

next_permutation :: IOUArray Int Int -> Int -> IOUArray Int Int -> IO Bool
next_permutation perm !n !cnt = loop 1
    where
    loop :: Int -> IO Bool
    loop i
        | i >= n = done i
        | otherwise = do
            tmp <- unsafeRead perm 0
            let
                rotate :: Int -> IO()
                rotate j
                    | j >= i = unsafeWrite perm i tmp
                    | otherwise = do
                        !v <- unsafeRead perm (j+1)
                        unsafeWrite perm j v
                        rotate (j+1)
            rotate 0
            v <- unsafeRead cnt i
            if v >= i
            then unsafeWrite cnt i 0 >> loop (i+1)
            else done i

    done :: Int -> IO Bool
    done i
        | i >= n = return False
        | otherwise = do
            v <- unsafeRead cnt i
            unsafeWrite cnt i (v+1)
            return True
    
-- Storage adapter: contiguous unboxed arrays from GHC's boot array package.
copyInts :: Int -> IOUArray Int Int -> IOUArray Int Int -> IO ()
copyInts n dst src = go 0
  where
    go :: Int -> IO ()
    go !i | i == n = return ()
          | otherwise = unsafeRead src i >>= unsafeWrite dst i >> go (i+1)

reversePrefix :: Int -> IOUArray Int Int -> IO ()
reversePrefix n a = go 0 (n-1)
  where
    go :: Int -> Int -> IO ()
    go !i !j | i >= j = return ()
             | otherwise = do
                 x <- unsafeRead a i
                 y <- unsafeRead a j
                 unsafeWrite a i y
                 unsafeWrite a j x
                 go (i+1) (j-1)
