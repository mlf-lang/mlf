{-# LANGUAGE BangPatterns #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
-- Baseline diagnostic only: forces complete input after successful unify WHNF.
-- This changes demand, allocation, residency and time; it is NOT a pure wrapper.
module Prototype.LocalProblemDigest
  ( Site(..), Fingerprint(..), fingerprint, wireWords, observe, writeCapture ) where
import Prelude
import Control.Exception (evaluate, throwIO)
import Control.Monad (when, unless)
import Data.Bits (xor, rotateL)
import Data.Int (Int64)
import Data.Word (Word64)
import Data.Char (ord)
import Data.IORef
import GHC.Clock (getMonotonicTimeNSec)
import System.IO (withFile, IOMode(WriteMode), hPutStrLn)
import System.IO.Unsafe (unsafePerformIO)
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P

data Site = UnifyDistinct | PreparedFallback deriving (Eq,Show)
data Token = W !Word64 | N
data Fingerprint = Fingerprint !Int !Int !Word64 !Word64 deriving (Eq,Show)
-- Physical maps include cached count and prefix, not just ascending entries.
mapTokens :: (a -> [Token]) -> T.IntMap a -> [Token]
mapTokens f (T.IntMap t) = tree t where
  tree T.IntMapNil = [W 0]
  tree (T.IntMapTip k v) = W 1 : int k ++ f v
  tree (T.IntMapBin count prefix l r) =
    W 2 : int count ++ int prefix ++ tree l ++ tree r
int :: Int64 -> [Token]
int n = [W (fromIntegral n)]
list :: (a -> [Token]) -> [a] -> [Token]
list _ [] = [W 0]
list f (x:xs) = W 1 : f x ++ list f xs
text :: P.String -> [Token]
text = list (\c -> [W (fromIntegral (ord c))]) . P.textToChars
kind :: T.Kind -> [Token]
kind T.Star = [W 0]
kind (T.KArrow a b) = W 1 : kind a ++ kind b
tag :: T.GTag -> [Token]
tag T.GBot = [W 0]
tag (T.GBotK k) = W 1 : kind k
tag (T.GArr a b) = W 2 : int a ++ int b
tag (T.GCon n cs) = W 3 : text n ++ list int cs
tag (T.GTyCon n k) = W 4 : text n ++ kind k
tag (T.GSkolem n k) = W 5 : int n ++ kind k
tag (T.GTyApp a b) = W 6 : int a ++ int b
tag (T.GGen n) = W 7 : int n
node :: T.Node -> [Token]
node (T.Node t b f) = N : tag t ++ (case b of T.Nothing -> [W 0]; T.Just v -> W 1:int v)
  ++ [W (case f of T.Flexible -> 0; T.Rigid -> 1)]
input :: T.Graph -> [(Int64,Int64)] -> [Token]
input (T.Graph ns links next) eqs =
  [W 0x4d4c464c504431] ++ mapTokens node ns ++ mapTokens int links
  ++ int next ++ list (\(a,b) -> int a ++ int b) eqs
wireWords :: T.Graph -> [(Int64,Int64)] -> [Word64]
wireWords g es = map (\t -> case t of N -> 128; W n -> n) (input g es)
fingerprint :: T.Graph -> [(Int64,Int64)] -> Fingerprint
fingerprint g es = go 0 0 14695981039346656037 7809847782465536322 (input g es) where
  go !w !n !a !b [] = Fingerprint w n a b
  go !w !n !a !b (t:ts)
    | w >= 1048576 = error "local digest per-input word cap"
    | n' > 131072 = error "local digest per-input node cap"
    | otherwise = go (w+1) n' ((a `xor` v)*1099511628211)
        ((rotateL b 13 `xor` v)*14029467366897019727+1609587929392839161) ts
    where (v,n') = case t of N -> (128,n+1); W x -> (x,n)

data Row = Row !Int !Site !Bool !Fingerprint !Word64 !Word64
data State = State !Int !Int !Word64 !Word64 ![Row]
{-# NOINLINE state #-}
state :: IORef State
state = unsafePerformIO (newIORef (State 0 0 0 0 []))
{-# NOINLINE observe #-}
observe :: Site -> ([(Int64,Int64)] -> T.Graph -> T.Either P.String T.Graph)
  -> [(Int64,Int64)] -> T.Graph -> T.Either P.String T.Graph
observe site action eqs graph = unsafePerformIO $ do
  actionStart <- getMonotonicTimeNSec
  result <- evaluate (action eqs graph)
  actionEnd <- getMonotonicTimeNSec
  start <- getMonotonicTimeNSec
  fp <- case result of
    T.Left _ -> pure (Fingerprint 0 0 0 0)
    T.Right _ -> evaluate (fingerprint graph eqs)
  end <- getMonotonicTimeNSec
  let success = case result of T.Left _ -> False; T.Right _ -> True
      Fingerprint words _ _ _ = fp
  accepted <- atomicModifyIORef' state $ \old@(State calls total nanos actionNanos rows) ->
    if calls >= 32768 || total + words > 134217728
    then (old,False)
    else let !row = Row calls site success fp (end-start) (actionEnd-actionStart)
         in (State (calls+1) (total+words) (nanos+end-start)
                  (actionNanos+actionEnd-actionStart) (row:rows),True)
  unless accepted (throwIO (userError "local digest global cap"))
  pure result
writeCapture :: FilePath -> IO ()
writeCapture path = do
  State calls total nanos actionNanos rows <- readIORef state
  unless (calls>0) (throwIO (userError "local digest empty"))
  withFile path WriteMode $ \h -> do
    hPutStrLn h ("local-problem-digest-v2\t" ++ show calls ++ "\t" ++ show total ++ "\t" ++ show nanos ++ "\t" ++ show actionNanos)
    hPutStrLn h "event\tsite\tsuccess\twords\tnodes\th1\th2\tencoding_ns\taction_whnf_ns"
    mapM_ (\(Row ix site ok (Fingerprint w n a b) ns actionNs) ->
      hPutStrLn h (show ix ++ "\t" ++ show site ++ "\t" ++ (if ok then "1" else "0")
        ++ "\t" ++ show w ++ "\t" ++ show n ++ "\t" ++ show a ++ "\t" ++ show b ++ "\t" ++ show ns ++ "\t" ++ show actionNs))
      (reverse rows)
    hPutStrLn h ("complete\t" ++ show calls ++ "\t" ++ show total ++ "\t" ++ show nanos ++ "\t" ++ show actionNanos)
