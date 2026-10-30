{-# OPTIONS_GHC -O0 #-}
module Main(main) where
import Prelude
import Control.Exception(evaluate,try,throw)
import Control.Monad(forM_,unless)
import Data.List(nub)
import GHC.Conc(pseq)
import GHC.Num.Integer(Integer(..))
import System.Timeout(timeout)
import qualified MLF.Host.Base as B
import Bootstrap.Types(Map(..))
import qualified Oracle as O
import qualified Probe

check :: String -> Bool -> IO ()
check label good = unless good (errorWithoutStackTrace ("FAIL "++label))
panic :: String -> a
panic = throw . B.HostError
observe :: Bool -> IO (Either B.HostError Bool)
observe = try . evaluate
tag :: Integer -> Int
tag (IS _) = 0
tag (IP _) = 1
tag (IN _) = 2
reference :: String -> Integer -> Integer -> Bool
reference name = case name of
  "lt" -> O.lt; "gt" -> O.gt; "le" -> O.le; "ge" -> O.ge
  _ -> errorWithoutStackTrace "unknown explicit route"
values :: [Integer]
values = [-64..64] ++ [lo-1,lo,lo+1,hi-1,hi,hi+1,2^128,-(2^128),2^1024,-(2^1024)]
  where lo=toInteger (minBound::Int);hi=toInteger (maxBound::Int)
expect :: String -> String -> Bool -> IO ()
expect label wanted expression = do
  result <- timeout 2000000 (observe expression)
  case result of
    Just (Left (B.HostError actual)) -> check label (actual==wanted)
    _ -> check label False
{-# NOINLINE diverge #-}
diverge :: Integer -> Integer
diverge n = n `pseq` diverge (n+1)

main :: IO ()
main = do
  check "139 unfiltered inputs, 9 public routes" (length values==139 && length Probe.routes==9)
  check "all nine Integer constructor pairs exercised"
    (length (nub [(tag a,tag b)|a<-values,b<-values])==9)
  forM_ Probe.routes $ \(name,actual,kind) -> do
    forM_ values $ \a -> forM_ values $ \b ->
      check (name++" value") (actual a b==reference kind a b)
    forM_ [("candidate",actual),("oracle",reference kind)] $ \(side,op) -> do
      let label=name++"/"++side; reversed=kind=="gt" || kind=="le"
      expect (label++"/both") (if reversed then "b" else "a") (op (panic "a") (panic "b"))
      expect (label++"/a") "a" (op (panic "a") 0)
      expect (label++"/b") "b" (op 0 (panic "b"))
      expect (label++"/big-a") "a" (op (panic "a") (2^1024))
      expect (label++"/big-b") "b" (op (-(2^1024)) (panic "b"))
      partial <- timeout 2000000 (try (evaluate (op (panic "partial"))) :: IO (Either B.HostError (Integer->Bool)))
      case partial of Just (Right _) -> pure (); _ -> check (label++" partial") False
      let first=if reversed then \a b->op b a else op
      expect (label++" panic before divergence") "first" (first (panic "first") (diverge 0))
      delayed <- timeout 200000 (observe (first (diverge 1) (panic "second")))
      case delayed of Nothing -> pure (); _ -> check (label++" divergence before panic") False
  let leaf key value=MapNode 1 key value MapEmpty MapEmpty
      tree=MapNode (-999) 0 7 (leaf (-(2^128)) 11) (leaf (2^128) 13)
      trees=[MapEmpty,leaf 0 9,tree,MapNode (2^1024) 0 7 (leaf 10 11) (leaf (-10) 13)]
  forM_ trees $ \t -> forM_ values $ \key ->
    check "raw-tree lookup including inconsistent counts/order" (Probe.lookupTree key t==O.lookupTree key t)
  forM_ [("candidate",Probe.lookupTree),("oracle",O.lookupTree)] $ \(side,look) -> do
    check (side++" empty query is lazy") (look (panic "query") (MapEmpty::Map Integer Bool)==Nothing)
    check (side++" hit subtrees/count lazy")
      (look 0 (MapNode (panic "size") 0 True (panic "left") (panic "right"))==Just True)
    let value=look 0 (MapNode 1 0 (panic "value") MapEmpty MapEmpty)::Maybe Bool
    check (side++" stored value lazy") (case value of Just _->True;_->False)
    expect (side++" query before key") "query"
      (case look (panic "query") (MapNode 1 (panic "key") True MapEmpty MapEmpty) of Just x->x;_->False)
    expect (side++" selected value") "value" (case value of Just x->x;_->False)
    expect (side++" chosen child") "left" (case look (-1) (MapNode 1 0 True (panic "left") (panic "right")) of Just x->x;_->False)
  putStrLn "PASS integer comparison: 173889 values; 90 error-order, 18 partial, 36 divergence observations; 556 raw-tree lookups; 12 tree demand controls"
