{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (SomeException, evaluate, try, displayException)
import Control.Monad (forM_, unless, foldM)
import Data.IORef
import System.Mem.StableName (makeStableName)
import qualified Bootstrap.CrateQuery as Q
import qualified FrozenCrateQuery as F
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

declarations =
  [T.DataDecl "A" ["a"] [T.ConstructorDecl "MakeA" [T.Parameter "a"]],
   T.DataDecl "A" ["a"] [T.ConstructorDecl "OtherA" [T.Parameter "a"]],
   T.DataDecl "A" ["a"] [T.ConstructorDecl "MakeA" [T.Applied "Int" []]],
   T.DataDecl "A" ["b"] [T.ConstructorDecl "MakeA" [T.Parameter "b"]],
   T.DataDeclK "A" [("a",T.Star)] [T.ConstructorDecl "MakeA" [T.Parameter "a"]],
   T.DataDeclK "A" [("a",T.KArrow T.Star T.Star)] [T.ConstructorDecl "MakeA" []],
   T.DataDeclK "B" [("f",T.KArrow T.Star T.Star)]
     [T.ConstructorDecl "MakeB" [T.Application (T.Parameter "f") (T.Applied "Int" [])]],
   T.DataDecl "α😀\NUL4:data" [] [T.ConstructorDecl "构造" []],
   T.DataDecl "Empty" [] [],
   T.DataDecl "Pair" ["a","b"] [T.ConstructorDecl "Pair" [T.Parameter "a",T.Parameter "b"]],
   T.DataDecl "Pair" ["a","b"] [T.ConstructorDecl "Pair" [T.Parameter "b",T.Parameter "a"]],
   T.DataDecl "A" ["a"] [T.ConstructorDecl "First" [],T.ConstructorDecl "Second" []],
   T.DataDecl "A" ["a"] [T.ConstructorDecl "Second" [],T.ConstructorDecl "First" []],
   T.DataDecl "Arrow" ["a"] [T.ConstructorDecl "Fn" [T.Function (T.Parameter "a") (T.Applied "Int" [])]],
   T.DataDecl "Arrow" ["a"] [T.ConstructorDecl "Fn" [T.Function (T.Applied "Int" []) (T.Parameter "a")]],
   T.DataDecl "Poly" [] [T.ConstructorDecl "Fn" [T.Quantified "a" T.Star (T.Parameter "a")]],
   T.DataDecl "Poly" [] [T.ConstructorDecl "Fn" [T.Quantified "b" T.Star (T.Parameter "b")]],
   T.DataDecl "Poly" [] [T.ConstructorDecl "Fn" [T.Quantified "a" (T.KArrow T.Star T.Star) (T.Parameter "a")]]]
contexts = [] : map (:[]) declarations ++
  [[declarations!!0,declarations!!6], [declarations!!6,declarations!!0],
   [declarations!!0,declarations!!0], [declarations!!0,declarations!!1]]
pools = map Q.prepareSourceEncodings [[],take 1 declarations,declarations]

sameObject a b = do
  x<-evaluate a; y<-evaluate b
  sx<-makeStableName x; sy<-makeStableName y
  pure (sx==sy)
observe :: B.String -> IO (Either String String)
observe text = do
  value<-try (evaluate (length (B.unpack text))) :: IO (Either SomeException Int)
  pure $ case value of Left e->Left (displayException e);Right _->Right (B.unpack text)
prepared body = S.PreparedGroup [("root",T.Nothing,body)] [("root",T.Nothing,body)]
  [("value",T.XCon "Int" [])] M.empty [("root",[],False)]
  (T.Just (S.RootAuthority "root" [] False [(T.GivenEvidence,"value",T.XCon "Int" [])] ["value"]))
  [("value",False)]

main = do
  count<-newIORef (0::Int)
  let check label ok=do
        unless ok (fail label)
        modifyIORef' count (+1)
      expected=map F.encodeDatatypeContext contexts
  -- Force independent expectations once. The tested cache never supplies them.
  mapM_ (evaluate . P.stringLength) expected
  forM_ pools $ \pool->do
    let empty=Q.emptyDatatypeContextEncoding pool
    forM_ contexts $ \previous->forM_ (zip contexts expected) $ \(current,reference)->do
      let (_,before)=Q.reuseDatatypeContext pool empty previous
          (actual,after)=Q.reuseDatatypeContext pool before current
          (again,_)=Q.reuseDatatypeContext pool after current
      check "exact old bytes after every ordered context transition" (actual==reference)
      check "repeat exact old bytes" (again==reference)
      shared<-sameObject actual again
      check "complete repeated context object is shared" shared
    _<-foldM (\cache (current,reference)->do
      let (actual,next)=Q.reuseDatatypeContext pool cache current
      check "long trace survives changes, order, duplication and returning contexts" (actual==reference)
      pure next) empty (concat (replicate 4 (zip contexts expected)))
    pure ()
  let pool=last pools
      bodies=[T.SIntLit 4,T.SVar "value",T.SApp (T.SVar "value") (T.SIntLit 3),
              T.SLam "x" T.Nothing (T.SVar "x"),
              T.SWanted "Dict" [(T.GivenEvidence,"value")]]
      contracts=M.fromList P.compareString [("value",S.SourceContract (T.XCon "Int" []) [] False)]
  forM_ (zip contexts expected) $ \(current,_)->forM_ bodies $ \body->do
    let group=prepared body
        (context,_)=Q.reuseDatatypeContext pool (Q.emptyDatatypeContextEncoding pool) current
        actual=Q.sourceQueryKeyWithContext "crate" "fixed-compiler" group contracts context
        old=F.sourceQueryKey "crate" "fixed-compiler" group contracts current
    check "whole original query key with reused datatype context" (actual==old)
  -- Existing structural encoders retain their original partial-value behavior.
  let bad label=errorWithoutStackTrace label
      broken=T.DataDecl (bad "datatype name first") [] [T.ConstructorDecl (bad "constructor next") []]
      pairs=[(Q.encodeDatatypeContext [broken],F.encodeDatatypeContext [broken]),
             (Q.encodeDatatypeContextWithPool (Q.prepareSourceEncodings []) [broken],
              F.encodeDatatypeContextWithPool (F.prepareSourceEncodings []) [broken]),
             (Q.sourceQueryKeyWithContext (bad "crate first") (bad "compiler next")
                (prepared (T.SIntLit 0)) M.empty (bad "context later"),
              F.sourceQueryKeyWithContext (bad "crate first") (bad "compiler next")
                (prepared (T.SIntLit 0)) M.empty (bad "context later"))]
  forM_ pairs $ \(actual,old)->do
    a<-observe actual;b<-observe old
    check "retained structural demand and first error" (a==b)
  total<-readIORef count
  unless (total>3000) (fail "non-vacuous transition matrix required")
  putStrLn ("PASS datatype context reuse: "++show total++" checks")
