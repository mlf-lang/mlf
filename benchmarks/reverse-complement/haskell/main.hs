
{-
The Computer Language Benchmarks Game
https://salsa.debian.org/benchmarksgame-team/benchmarksgame/

contributed by Louis Wasserman
GHC 9.0, 9.2 fix by Artem Pelenitsyn
-}

import Control.Monad
import qualified Data.ByteString as B
import Data.ByteString.Unsafe (unsafeUseAsCStringLen)
import Foreign
import Data.ByteString.Internal
import System.IO
import System.IO.Unsafe (unsafeDupablePerformIO)

data Buf = Buf !Int !Int !(Ptr Word8) 

withBuf run = run . Buf 0 ini =<< mallocBytes ini
  where ini = 1024

newSize len sz
  | len <= sz  = sz
  | otherwise  = newSize len (2 * sz)

{-# INLINE putBuf #-}
putBuf pS lS (Buf lD szD pD) run
  | lD' > szD  = do
    let szD' = newSize lD' szD
    pD' <- reallocBytes pD szD'
    copyArray (pD' +* lD) pS lS
    run (Buf lD' szD' pD')
  | otherwise  = do
    copyArray (pD +* lD) pS lS
    run (Buf lD' szD pD)
  where lD' = lD + lS

findChar p n c zero one = do
    q <- memchr p c (fromIntegral (n :: Int))
    if q == nullPtr then zero else one $! q `minusPtr` p

clearBuf (Buf _ lB pB) = Buf 0 lB pB

-- Buffered lines handle several short records in one input buffer and
-- arbitrarily long header lines. Keep the original growing Buf and rc loops.
main = withBuf go
  where
    go buf = do
      done <- hIsEOF stdin
      if done then revcomp buf >> freeBuf buf else do
        raw <- B.hGetLine stdin
        let line = B.snoc raw 10
        let header = not (B.null raw) && B.head raw == 62
        when header (revcomp buf)
        next <- unsafeUseAsCStringLen line $ \(p,n) ->
          putBuf (castPtr p) n (if header then clearBuf buf else buf) return
        go next

freeBuf (Buf _ _ p) = free p

(+*) = advancePtr

{-# INLINE comps #-}
comps = Prelude.zipWith (\ a b -> (fromEnum a, c2w b)) "AaCcGgTtUuMmRrYyKkVvHhDdBbWwSsNn" 
  "TTGGCCAAAAKKYYRRMMBBDDHHVVWWSSNN"

ca :: Ptr Word8
ca = unsafeDupablePerformIO $ do
       !a <- mallocArray 200
       mapM_ (\ i -> pokeByteOff a (fromIntegral i) i ) [0..199::Word8]
       mapM_ (uncurry (pokeByteOff a)) comps
       return a

revcomp (Buf lBuf _ pBuf) = when (lBuf > 0) $ ca `seq`
  findChar pBuf lBuf (c2w '\n') undefined $ \ begin -> let
    begin' = begin + 1
    rc :: Ptr Word8 -> Ptr Word8 -> IO ()
    rc !i !j | i < j = do
      x <- peek i
      if x == c2w '\n' then let !i' = i +* 1 in rc1 j i' =<< peek i'
        else rc1 j i x
    rc i j = when (i == j) (poke i =<< comp =<< peek i)
    
    rc1 !j !i !xi = do
      y <- peek j
      if y == c2w '\n' then let !j' = j +* (-1) in rc2 i xi j' =<< peek j'
        else rc2 i xi j y
    
    comp = peekElemOff ca . fromIntegral
    
    rc2 !i !xi !j !xj = do
      poke j =<< comp xi
      poke i =<< comp xj
      rc (i +* 1) (j +* (-1))
    in do
      hPutBuf stdout pBuf begin'
      rc (pBuf +* begin') (pBuf +* (lBuf - 1))
      hPutBuf stdout (pBuf +* begin') (lBuf - begin - 1)
    