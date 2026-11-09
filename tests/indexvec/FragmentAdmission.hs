{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import System.Environment (getArgs)
import qualified Bootstrap.ArtifactStorage as Store
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

ok (T.Right x) = pure x
ok (T.Left message) = error (H.unpack message)
reject label action = action >>= \result -> case result of
  T.Left _ -> pure ()
  T.Right _ -> error (label ++ " accepted")
main = do
  [dir] <- getArgs
  let file = H.literal (dir ++ "/raw-record")
      int = T.XCon "Int" []
      a = T.XName 42 "a"; b = T.XName 2 "b"; owned = T.XName 4 "owner"
      ps = [(V.fromInt 7,"a",int), (V.fromInt 3,"b",int)]
      os = [(V.fromInt 12,"owner")]
      refs = [("binding:a","a version"),("binding:b","b version")]
  env <- ok (O.environment [])
  fragment <- ok (O.check env [(a,int), (b,int)]
    (T.XLet owned (T.XVarTerm a) (T.XConstructor "()" [])))
  bytes <- Store.encode 6 [W.VNode 425 [A.toList (A.toPair W.VText W.VText) refs,
    O.encodeBody "raw" "group" fragment]] >>= ok
  Store.writeRawAtomic file bytes >>= ok
  digest <- P.byteArrayDigest bytes
  let load sha version stage group = O.decodeTrustedIds file sha version stage group env
  good <- load digest refs "raw" "group" ps os >>= ok
  unless (map fst (O.parameters good) `sameNames` [a,b]) (error "lost local binder order")
  reject "missing" (load digest refs "raw" "group" (tail ps) os)
  reject "extra" (load digest refs "raw" "group" (ps ++ [head ps]) os)
  reject "reordered" (load digest refs "raw" "group" (reverse ps) os)
  reject "duplicate declaration" (load digest refs "raw" "group" ps [(V.fromInt 7,"owner")])
  reject "wrong owner" (load digest refs "raw" "another" ps os)
  reject "wrong stage" (load digest refs "finish" "group" ps os)
  reject "wrong member" (load digest refs "raw" "group" ps [(V.fromInt 12,"another")])
  reject "stale reads" (load digest (reverse refs) "raw" "group" ps os)
  reject "wrong SHA" (load "bad" refs "raw" "group" ps os)
  package <- O.makePackage "compiler" "metadata" [("group",fragment)] >>= ok
  let body = O.packageBytes package; hash = O.packageHash package
      types = M.fromList P.compareString [("a",int),("b",int),("owner",int)]
      readFinal blob h identity metadata contracts = O.readPackage blob h identity metadata contracts M.empty
  _ <- readFinal body hash "compiler" "metadata" types >>= ok
  reject "wrong contract type" (readFinal body hash "compiler" "metadata"
    (M.insert P.compareString "a" (T.XCon "Bool" []) types))
  reject "missing contract" (readFinal body hash "compiler" "metadata" (M.delete P.compareString "a" types))
  reject "wrong version" (readFinal body hash "other" "metadata" types)
  reject "wrong object owner" (readFinal body hash "compiler" "other" types)
  [header@(W.VNode 432 [_,compiler,meta,bindings,ds,W.VInt 1]),
    W.VNode 401 [n,h,layouts,W.VNode 1 params,t,bs,used]]
    <- W.decode W.defaultLimits 8 body >>= ok
  let final changed = W.VNode 401 [n,h,layouts,W.VNode 1 changed,t,bs,used]
      roots8 changed = [header, final changed]
      roots7 changed = [W.VNode 430
        [W.VText "MLF-OPEN-CRATE-1/checker-1",compiler,meta,bindings,ds,W.VNode 1 [final changed]]]
      checkSchema schema roots = do
        valid <- Store.encode schema (roots params) >>= ok
        validHash <- P.byteArrayDigest valid
        _ <- readFinal valid validHash "compiler" "metadata" types >>= ok
        let tryParams label changed = do
              forged <- Store.encode schema (roots changed) >>= ok
              forgedHash <- P.byteArrayDigest forged
              reject ("schema " ++ show schema ++ " " ++ label)
                (readFinal forged forgedHash "compiler" "metadata" types)
        tryParams "final missing parameter" (tail params)
        tryParams "final extra parameter" (params ++ [head params])
        tryParams "final wrong order" (reverse params)
  checkSchema 8 roots8
  checkSchema 7 roots7
  putStrLn "raw and final fragment admission controls passed"
  where sameNames xs ys = map view xs == map view ys
        view (T.XName i n) = (i,H.unpack n)
