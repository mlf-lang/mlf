{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where
import Prelude
import Control.Exception (Exception,throw,try,evaluate)
import Control.Monad (unless)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Prototype.PrefixReasons as C
data Probe = Probe deriving (Show,Typeable)
instance Exception Probe
poison :: a
poison=throw Probe
node :: T.GTag -> T.Node
node t=T.Node t T.Nothing T.Flexible
graph :: [(P.Int,T.Node)] -> T.Graph
graph ns=T.Graph (IM.fromList ns) IM.empty 100
type Input = (T.Graph,P.Int,T.IntMap P.Int,[(P.Int,P.Int)])
observe :: Bool -> IO String
observe value=do
 r<-try (evaluate value) :: IO (Either Probe Bool)
 pure (case r of {Left Probe -> "Probe"; Right b -> show b})
test :: String -> (() -> Input) -> P.Int -> IO ()
test label factory expected=do
 let (ga,fa,ia,pa)=factory ()
     (gc,fc,ic,pc)=factory ()
 a<-observe (S.fallbackPrefixRejectedOriginal ga fa ia pa)
 c<-observe (C.observeReason (S.fallbackPrefixReason gc fc ic pc) /= 0)
 let wanted=show (expected/=0)
 writeFile (label++".A") (a++"\n")
 writeFile (label++".C") (c++"\n")
 writeFile (label++".expected") (wanted++"\n")
 unless (a==wanted && c==wanted) (error ("prefix mismatch "++label))
 -- Pure reason literal is checked separately; no second observer call.
 let (gr,fr,ir,pr)=factory ()
 reason<-evaluate (S.fallbackPrefixReason gr fr ir pr)
 unless (reason==expected) (error ("reason mismatch "++label))
 writeFile (label++".result") "PASS\n"
main :: IO ()
main=do
 test "empty" (\()->(poison,poison,poison,[])) 0
 test "old-source" (\()->(poison,10,poison,[(1,poison)])) 0
 test "fresh-target" (\()->(poison,10,poison,[(10,10)])) 0
 test "mapping-conflict" (\()->(poison,10,IM.fromList [(10,2)],(10,1):poison)) 1
 test "mapping-same" (\()->(poison,10,IM.fromList [(10,1)],[(10,1)])) 0
 test "source-missing" (\()->(graph [],10,IM.empty,(10,1):poison)) 0
 test "target-missing" (\()->(graph [(10,poison)],10,IM.empty,(10,1):poison)) 0
 test "old-gen" (\()->(graph [(1,node (T.GGen poison)),(10,poison)],10,IM.empty,(10,1):poison)) 0
 test "old-hole" (\()->(graph [(1,node T.GBot),(10,node (T.GTyCon poison poison))],10,IM.empty,(10,1):poison)) 2
 test "copy-bottom" (\()->(graph [(1,node (T.GTyCon poison poison)),(10,node T.GBot)],10,IM.empty,[(10,1)])) 0
 test "arr-first-hole" (\()->(graph [(1,node (T.GArr 2 3)),(2,node T.GBot),(10,node (T.GArr 11 12)),(11,node (T.GTyCon poison poison))],10,IM.empty,(10,1):poison)) 2
 test "unknown-payload" (\()->(graph [(1,node (T.GTyCon poison poison)),(10,node (T.GTyCon poison poison))],10,IM.empty,(10,1):poison)) 0
 test "raw-alias-not-resolved" (\()->(T.Graph (IM.fromList [(1,node T.GBot),(11,node T.GBot)]) (IM.fromList [(10,11)]) 100,10,IM.empty,(10,1):poison)) 0
 a<-observe (S.fallbackPrefixRejectedOriginal poison 10 IM.empty poison)
 c<-observe (C.observeReason (S.fallbackPrefixReason poison 10 IM.empty poison)/=0)
 writeFile "poison.A" (a++"\n");writeFile "poison.C" (c++"\n")
 writeFile "poison.expected" "Probe\n"
 unless (a=="Probe" && c=="Probe") (error "poison mismatch")
 writeFile "poison.result" "PASS\n"
 totals<-C.snapshot
 writeFile "counts.actual" (show totals++"\n")
 writeFile "counts.expected" "(13,10,1,2)\n"
 unless (totals==(13,10,1,2)) (error "count conservation")
 C.writeCapture "prefix-reasons.tsv"
 putStrLn "PASS 14 prefix reason finite cases; diagnostic only"
