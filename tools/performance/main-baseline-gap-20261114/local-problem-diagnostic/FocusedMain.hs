{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import Prelude
import Data.Int (Int64)
import Data.Word (Word64)
import Data.List (nub)
import Control.Exception (try,evaluate,ErrorCall)
import Control.Monad (unless)
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import qualified Prototype.LocalProblemDigest as C
empty :: T.IntMap a
empty = T.IntMap T.IntMapNil
one :: T.GTag -> T.Maybe Int64 -> T.Flag -> T.Graph
one t b f = T.Graph (T.IntMap (T.IntMapTip 0 (T.Node t b f))) empty 1
bot = one T.GBot T.Nothing T.Flexible
cases :: [(String,T.Graph,[(Int64,Int64)])]
cases =
 [("empty",T.Graph empty empty 0,[])
 ,("bot",bot,[])
 ,("botk",one (T.GBotK T.Star) T.Nothing T.Flexible,[])
 ,("arrow-kind",one (T.GBotK (T.KArrow T.Star T.Star)) T.Nothing T.Flexible,[])
 ,("arr",one (T.GArr (-1) 9223372036854775807) T.Nothing T.Flexible,[])
 ,("con",one (T.GCon (P.textFromChars "A") [1,2]) T.Nothing T.Flexible,[])
 ,("con-order",one (T.GCon (P.textFromChars "A") [2,1]) T.Nothing T.Flexible,[])
 ,("unicode",one (T.GCon (P.textFromChars "\x1f600\x4e2d") []) T.Nothing T.Flexible,[])
 ,("tycon",one (T.GTyCon (P.textFromChars "A") T.Star) T.Nothing T.Flexible,[])
 ,("skolem",one (T.GSkolem (-9223372036854775808) (T.KArrow T.Star T.Star)) T.Nothing T.Flexible,[])
 ,("app",one (T.GTyApp 2 3) T.Nothing T.Flexible,[])
 ,("gen",one (T.GGen 3) T.Nothing T.Flexible,[])
 ,("binder",one T.GBot (T.Just (-1)) T.Flexible,[])
 ,("rigid",one T.GBot T.Nothing T.Rigid,[])
 ,("next",T.Graph (T.IntMap (T.IntMapTip 0 (T.Node T.GBot T.Nothing T.Flexible))) empty 2,[])
 ,("key",T.Graph (T.IntMap (T.IntMapTip (-1) (T.Node T.GBot T.Nothing T.Flexible))) empty 1,[])
 ,("links",T.Graph (T.IntMap (T.IntMapTip 0 (T.Node T.GBot T.Nothing T.Flexible))) (T.IntMap (T.IntMapTip 2 0)) 1,[])
 ,("bin",tree 2 1 False,[])
 ,("bin-count",tree 3 1 False,[])
 ,("bin-prefix",tree 2 2 False,[])
 ,("bin-order",tree 2 1 True,[])
 ,("equation",bot,[(0,1)])
 ,("equation-reverse",bot,[(1,0)])
 ,("equation-duplicates",bot,[(0,1),(0,1)])
 ,("equation-order",bot,[(0,1),(2,3)])
 ,("equation-order-reverse",bot,[(2,3),(0,1)])]
 where
  tree count prefix rev = let a=T.IntMapTip 0 (T.Node T.GBot T.Nothing T.Flexible)
                              b=T.IntMapTip 1 (T.Node T.GBot T.Nothing T.Flexible)
                          in T.Graph (T.IntMap (if rev then T.IntMapBin count prefix b a else T.IntMapBin count prefix a b)) empty 2
main :: IO ()
main = do
 let enc=[C.wireWords g es | (_,g,es)<-cases]
 unless (length enc==26 && length (nub enc)==26) (error "finite encodings not distinct")
 unless (head enc==[0x4d4c464c504431,0,0,0,0]) (error "empty literal")
 unless (enc!!1==[0x4d4c464c504431,1,0,128,0,0,0,0,1,0]) (error "bot literal")
 mapM_ (\(_,g,es)->evaluate (C.fingerprint g es)) cases
 writeFile "encoding-cases.tsv" (unlines [name++"\t"++show (C.wireWords g es) | (name,g,es)<-cases])
 result <- evaluate (C.observe C.UnifyDistinct (\_ _ -> T.Left (P.textFromChars "expected-left"))
   (error "unwanted equations") (error "unwanted graph"))
 case result of T.Left e -> unless (P.textToChars e == "expected-left") (error "Left value changed"); _ -> error "Left bypass"
 answer <- evaluate (C.observe C.PreparedFallback (\_ g->T.Right g) [] bot)
 case answer of T.Right g -> unless (C.wireWords g [] == enc!!1) (error "returned graph changed"); _ -> error "Right failed"
 poisoned <- try (evaluate (C.observe C.PreparedFallback (\_ g->T.Right g) [] (error "selected-right-poison"))) :: IO (Either ErrorCall (T.Either P.String T.Graph))
 case poisoned of Left _ -> pure (); Right _ -> error "Right full input not forced"
 capped <- try (evaluate (C.fingerprint bot (repeat (0,0)))) :: IO (Either ErrorCall C.Fingerprint)
 case capped of Left _ -> pure (); Right _ -> error "per-input cap absent"
 C.writeCapture "local-problem-digest.tsv"

 -- Only report-shape/nonnegative/sum checks; no positive duration threshold.
 capture <- readFile "local-problem-digest.tsv"
 let rows = map words (lines capture)
     natural x = case reads x :: [(Integer,String)] of
       [(n,"")] | n >= 0 && n <= 18446744073709551615 -> n
       _ -> error "invalid timing/count integer"
 case rows of
  [header,columns,leftRow,rightRow,footer] -> do
   unless (length header==5 && length footer==5 &&
           head header=="local-problem-digest-v2" && head footer=="complete" &&
           tail header==tail footer && header!!1=="2") (error "capture totals")
   unless (columns==words "event site success words nodes h1 h2 encoding_ns action_whnf_ns")
     (error "capture columns")
   unless (length leftRow==9 && length rightRow==9 &&
           take 7 leftRow==words "0 UnifyDistinct 0 0 0 0 0" &&
           take 7 rightRow==words "1 PreparedFallback 1 10 1 7315885365150003742 3930716039965229128")
     (error "capture original rows changed")
   let es=natural (leftRow!!7)+natural (rightRow!!7)
       ats=natural (leftRow!!8)+natural (rightRow!!8)
   unless (natural (header!!2)==10 && natural (header!!3)==es &&
           natural (header!!4)==ats) (error "capture time sums")
  _ -> error "capture row count"
 putStrLn "PASS 26 exact encoding cases, Left bypass, Right force, bounded cap"
