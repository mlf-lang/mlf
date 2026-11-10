{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import GHC.Clock (getMonotonicTimeNSec)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Kind as K
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.Std as L
import qualified Bootstrap.X.Type as X
import qualified MLF.Host.Base as B

-- The unchanged public recursive entry retains the pre-change algorithm.
-- Keep the old top-level algorithm explicit rather than calling kindOf twice.
oldKindOf ds bounds ty = do
  kinds <- L.mapM (X.kindBinding ds bounds S.empty) (S.toList (X.freeVars ty))
  X.kindIn ds (M.fromList X.compareTyVar kinds) ty

renderKind T.Star = "*"
renderKind (T.KArrow a b) = "(" ++ renderKind a ++ "->" ++ renderKind b ++ ")"
render (T.Left e) = "error:" ++ B.unpack e
render (T.Right k) = "kind:" ++ renderKind k

forceText text = sum (map fromEnum text)
observe value = do
  result <- try (evaluate (forceText (render value))) :: IO (Either SomeException Int)
  pure $ case result of
    Left error -> Left (takeWhile (/= '\n') (displayException error))
    Right count -> Right (count, render value)

need label condition = unless condition (error label)
v n = T.XTyVar n
bounds entries = M.fromList X.compareTyVar [(v i, ty) | (i,ty) <- entries]
check label ds env ty expected = do
  before <- observe (oldKindOf ds env ty)
  after <- observe (X.kindOf ds env ty)
  need (label ++ ": differential result") (before == after)
  case expected of
    Nothing -> pure ()
    Just wanted -> need (label ++ ": authored oracle") (after == Right (forceText wanted,wanted))

controls = do
  let star = T.XBot
      arrowKind = T.KArrow T.Star T.Star
      refs = [T.XVar (v n) | n <- [0..3]]
      options = star : T.XBotKind arrowKind : refs
      environments = sequence (replicate 4 options)
  forM_ (zip [0 :: Int ..] environments) $ \(i,ts) ->
    forM_ refs $ \ty -> check ("environment " ++ show i) D.emptyDataEnv
      (bounds (zip [0..] ts)) ty Nothing
  forM_ [0..16] $ \n -> check ("diamond " ++ show n) D.emptyDataEnv
    (diamond 0 n) (T.XVar (v n)) (Just "kind:*")
  check "closed ignores bounds" D.emptyDataEnv (error "unused bounds") T.XBot (Just "kind:*")
  check "unused binding" D.emptyDataEnv (bounds [(0,star),(1,error "unused value")])
    (T.XVar (v 0)) (Just "kind:*")
  check "missing first" D.emptyDataEnv (bounds [(1,error "later bottom")])
    (T.XArrow (T.XVar (v 0)) (T.XVar (v 1))) (Just "error:unbound type variable 0")
  check "cycle first" D.emptyDataEnv (bounds [(0,T.XVar (v 0)),(1,error "later bottom")])
    (T.XArrow (T.XVar (v 0)) (T.XVar (v 1))) (Just "error:cyclic type environment")
  check "bound bottom" D.emptyDataEnv (bounds [(0,error "bound bottom")]) (T.XVar (v 0)) Nothing
  check "shared higher kind" D.emptyDataEnv (bounds [(0,T.XBotKind arrowKind),(1,T.XVar (v 0))])
    (T.XApply (T.XVar (v 1)) T.XBot) (Just "kind:*")
  check "shared wrong kind" D.emptyDataEnv (bounds [(0,T.XBotKind arrowKind),(1,T.XVar (v 0))])
    (T.XArrow (T.XVar (v 1)) T.XBot) (Just "error:function types require kind * arguments")
  check "shadowed forall" D.emptyDataEnv (bounds [(0,T.XBotKind arrowKind)])
    (T.XForall (v 0) T.XBot (T.XVar (v 0))) (Just "kind:*")
  check "forall bound retains outer binding" D.emptyDataEnv (bounds [(0,T.XBotKind arrowKind)])
    (T.XForall (v 0) (T.XVar (v 0)) (T.XVar (v 0))) (Just "kind:(*->*)")
  putStrLn "PASS type-kind memo: 5184 generated cases, 17 diamonds, 9 demand/kind controls"

diamond offset n = bounds [(offset+i, node i) | i <- [0..n]]
  where node i | i < 2 = T.XBot
               | otherwise = T.XArrow (T.XVar (v (offset+i-1))) (T.XVar (v (offset+i-2)))

bench variant n count = do
  let action = if variant == "old" then oldKindOf else X.kindOf
  start <- getMonotonicTimeNSec
  forM_ [1..count] $ \i -> do
    let offset = i * (n+1)
    result <- evaluate (forceText (render (action D.emptyDataEnv (diamond offset n) (T.XVar (v (offset+n))))))
    need "bench result" (result == forceText "kind:*")
  finish <- getMonotonicTimeNSec
  putStrLn ("PASS " ++ variant ++ " depth=" ++ show n ++ " count=" ++ show count ++ " wall_ns=" ++ show (finish-start))

main = getArgs >>= \args -> case args of
  [] -> controls
  ["bench", variant, n, count] | variant `elem` ["old","memo"] -> bench variant (read n) (read count)
  _ -> error "usage: type-kind-memo [bench old|memo depth count]"
