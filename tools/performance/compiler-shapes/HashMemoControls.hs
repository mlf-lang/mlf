{-# LANGUAGE OverloadedStrings #-}
-- Differential oracle: the independent frozen OpenFragment implementation.
module Main where
import Prelude
import Control.Monad (forM_, unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.Map as M
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified MemoOpen as C
import qualified LegacyOpen as L
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.Separate as U

need label ok = unless ok (fail label)
equalResult (T.Left a) (T.Left b) = a == b
equalResult (T.Right a) (T.Right b) = a == b
equalResult _ _ = False
expect label (T.Left e) = fail (label ++ ": " ++ B.unpack e)
expect _ (T.Right a) = pure a
strip (T.Left e) = T.Left e
strip (T.Right (digest,remaining,_)) = T.Right (digest,remaining)

main = do
 let values = [W.VInt (-1),W.VBits (-1),W.VText "α😀\NUL",W.VNode 7 [],
               W.VNode 7 [W.VText "same",W.VText "same"],
               W.VNode 8 [W.VNode 7 [W.VInt 1],W.VBits 1]]
 forM_ values $ \value -> do
  (digest,next,cache) <- C.hashSyntaxMemo T.Nothing 100000 value >>= expect "first hash"
  let used = 100000-next
  need "positive, explicit work charge" (used > 0)
  forM_ [-1,0,1,used-1,used,used+1,100000,2147483648] $ \budget -> do
   original <- L.hashSyntaxBudget budget value
   actual <- C.hashSyntaxMemo cache budget value
   need "exact digest, remaining budget and rejection parity" (equalResult original (strip actual))
  forM_ values $ \changed -> do
   original <- L.hashSyntaxBudget 100000 changed
   actual <- C.hashSyntaxMemo cache 100000 changed
   need "all wire constructors participate in equality" (equalResult original (strip actual))
  let entries = [(B.literal ("name" ++ show i),value) | i <- [1..128::Int]]
  forM_ [128*used-1,128*used,128*used+1] $ \budget -> do
   original <- L.referenceHashesBudget id entries budget []
   actual <- C.referenceHashesBudget id entries budget []
   need "repeated references retain exact aggregate charging" (equalResult original actual)
  let available = M.fromList P.compareString entries
      refs = [(key,digest) | (key,_) <- entries]
      check label rows = do
       original <- L.validateReferencesBudget id available rows 100000 M.empty
       actual <- C.validateReferencesBudget id available rows 100000 M.empty
       case (original,actual) of
        (T.Left a,T.Left b) -> need label (a == b)
        (T.Right (a,x),T.Right (b,y)) -> need label (M.keys a == M.keys b && x == y)
        _ -> fail label
  check "reader checks every repeated reference" refs
  check "duplicate reference rejected" (take 1 refs ++ refs)
  check "missing reference rejected" (("missing",digest):refs)
  check "changed dependency digest rejected" ((fst (head refs),"wrong"):tail refs)
 -- Use the public opaque receipt API, not the private renamed test module.
 forM_ values $ \value -> do
  receipt <- O.makeMetadataReceipt value >>= expect "metadata receipt"
  let digest = O.metadataReceiptHash receipt
      metadata = U.pack [digest]
  package <- O.makePackage "receipt-control" metadata [] >>= expect "empty package"
  bound <- expect "bind authenticated metadata" (O.withMetadataReceipt receipt package)
  need "equal metadata reuses its authenticated digest"
    (case O.cachedMetadata value bound of T.Just x -> x == digest; _ -> False)
  forM_ values $ \changed ->
   need "every metadata constructor and field participates"
     (case O.cachedMetadata changed bound of
       T.Just x -> x == digest && C.sameSyntax value changed
       T.Nothing -> not (C.sameSyntax value changed))
  wrong <- O.makePackage "receipt-control" (U.pack ["wrong"]) [] >>= expect "other package"
  need "receipt cannot bind another manifest"
    (case O.withMetadataReceipt receipt wrong of T.Left _ -> True; _ -> False)
  restored <- O.readPackage (O.packageBytes bound) (O.packageHash bound)
    "receipt-control" metadata M.empty M.empty >>= expect "disk package"
  need "disk readers never acquire an in-memory receipt"
    (case O.cachedMetadata value restored of T.Nothing -> True; _ -> False)
 putStrLn "PASS memo digest, exact budgets, structural changes and reference admission"
 putStrLn "PASS opaque metadata receipt, manifest binding and disk fallback"
