{-# LANGUAGE OverloadedStrings #-}
-- Compare resource admission and hashes with the frozen pre-change compiler.
module Main where
import Prelude
import Control.Monad (forM_, unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.CrateGraph as C
import qualified Bootstrap.QueryGraph as G
import qualified LegacyGraph as L
import qualified MLF.Host.Base as B

need label ok = unless ok (fail label)
same (T.Left a) (T.Left b) = a == b
same (T.Right a) (T.Right b) = a == b
same _ _ = False
text = W.VText . B.literal
chain 0 x = x
chain n x = W.VNode 1 [chain (n-1) x]
cacheControls = do
 let values = [W.VInt minBound,W.VBits minBound,text "α😀\NUL",W.VNode 420 [W.VInt 0],
               W.VNode 420 [W.VInt 1],W.VNode 420 [W.VBits 1],W.VNode 421 [W.VInt 1],
               chain 15 (text "bounded"),W.VNode 1 (replicate 127 (W.VInt 1)),
               text (replicate 256 'α')]
     fallback = [chain 16 (text "deep"),W.VNode 1 (replicate 128 (W.VInt 1)),
                 text (replicate 257 'α')]
     go _ [] = pure ()
     go previous (value:rest) = do
      expected <- G.hashValue value
      actual <- C.hashContractCached previous value
      case (expected,actual) of
       (T.Right wanted,T.Right (got,next)) -> do
        need "contract cache equals uncached canonical digest" (wanted==got)
        go next rest
       _ -> fail "valid contract digest control failed"
 go T.Nothing (concatMap (\value->[value,value]) (values ++ reverse values ++ fallback ++ values))
 forM_ values $ \value -> do
  actual <- C.hashContractCached T.Nothing value
  need "bounded contract cache is populated" (case actual of T.Right (_,T.Just _) -> True; _ -> False)
 forM_ fallback $ \value -> do
  actual <- C.hashContractCached T.Nothing value
  need "large contracts are not retained" (case actual of T.Right (_,T.Nothing) -> True; _ -> False)
 seeded <- C.hashContractCached T.Nothing (W.VInt 1)
 let previous = case seeded of T.Right (_,next) -> next; _ -> T.Nothing
 forM_ [W.VNode (-1) [],W.VNode 2147483648 []] $ \value -> do
  expected <- G.hashValue value
  actual <- C.hashContractCached previous value
  need "cache does not bypass invalid-value rejection" (case (expected,actual) of
    (T.Left a,T.Left b)->a==b; _->False)
main = do
 cacheControls
 let valid = [text "",text "ASCII",text "α😀\NUL",W.VNode 2147483647 [],
              chain 7 (text "last"),W.VNode 1 (replicate 255 (text "same")),
              text (replicate 16384 '\x10ffff')]
     outside = [W.VInt 1,W.VBits minBound,W.VNode (-1) [],W.VNode 2147483648 [],
                chain 8 (text "last"),W.VNode 1 (replicate 256 (text "same")),
                text (replicate 16385 'a')]
 forM_ valid $ \value -> do
  need "small admission is nonvacuous" (C.smallRebuiltValue value)
  case W.prepareGraphPlan W.defaultLimits [value] of
   T.Left e -> fail ("admitted beyond planner: " ++ B.unpack e)
   T.Right _ -> pure ()
 forM_ outside $ \value -> need "conservative fallback boundaries" (not (C.smallRebuiltValue value))
 let inputs = valid ++ outside ++
       [W.VNode 422 (map text fields) | fields <- [[],["","a","α😀"],replicate 255 "same",replicate 256 "same"]] ++
       [W.VNode 421 [text "prepared-declarations-1",W.VNode 1 [text "name"],text content,text content,W.VNode 1 [text "meta"]]
         | content <- ["", "field\NULα😀", replicate 9000 'a']] ++
       [W.VNode 427 [text "group",text "fragment",W.VNode 1 [W.VNode 2 [text "name",text "hash"]]],
        W.VNode 423 [W.VNode 422 [text "scope"],W.VNode 1 [W.VNode 2 [text "name",text "digest"]]],
        chain 16384 (text "deep")]
 forM_ inputs $ \value -> do
  old <- L.hashRebuiltValue value
  actual <- C.hashRebuiltValue value
  need "identical digest or exact planner rejection" (same old actual)
 putStrLn "PASS contract cache exactness, bounds, invalidation and rejection"
 putStrLn "PASS rebuilt receipt bounds, fallback, Unicode and frozen digest parity"
