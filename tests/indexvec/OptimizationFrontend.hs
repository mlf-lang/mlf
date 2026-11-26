{-# LANGUAGE OverloadedStrings #-}
module OptimizationFrontend (run) where

import Control.Monad (forM_, unless)
import Data.List (mapAccumL)
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Fresh as Fresh
import qualified Bootstrap.Lexer as Lexer
import qualified Bootstrap.Parsec as Parsec
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Set as Set
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Surface as Surface
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as Prim

check :: String -> Bool -> IO ()
check label passed = unless passed (fail label)

tokenView (Lexer.Token text sl sc el ec) = (H.unpack text,sl,sc,el,ec)
stateView (Parsec.ParseState file tokens finish syntax owner packageName) =
  (H.unpack file,map tokenView tokens,tokenView finish,profile syntax,H.unpack owner,H.unpack packageName)
  where
    profile T.LegacyEmlfV1 = (0 :: Int)
    profile T.SharedHaskellV1 = 1
    profile T.MetadataSyntax = 2

sameResult (Parsec.PSuccess a end consumed) (Parsec.PSuccess b other consumedOther) =
  Equality.eqSExpr a b && stateView end == stateView other && consumed == consumedOther
sameResult (Parsec.PFailure a end consumed) (Parsec.PFailure b other consumedOther) =
  H.unpack a == H.unpack b && stateView end == stateView other && consumed == consumedOther
sameResult _ _ = False

tokensFor :: [String] -> [Lexer.Token]
tokensFor = snd . mapAccumL token 5
  where
    token column spelling =
      let end = column + fromIntegral (length spelling)
      in (end+1, Lexer.Token (H.literal spelling) 3 column 3 end)

stateFor syntax spellings = Parsec.ParseState "Operators.hs" (tokensFor spellings)
  (Lexer.Token "<end>" 9 7 9 7) syntax "Operators" "span-package"

-- Keep the previous span implementation as the differential oracle. Comparing
-- the complete result checks error selection and consumption as well as ASTs.
oldPrefix = Parser.locatedReference
  (Parsec.pBefore Parser.operatorReference (Parsec.pLook (Parsec.pToken ")")))
oldInfix choices = Parsec.pTry $ do
  (location, operator) <- Parsec.pWithSpan Parser.operatorReference
  let leaf = Parser.referenceLeaf operator
  if Std.elem Prim.eqString leaf choices
    then Parsec.pPure (\a b -> T.SApp
      (T.SApp (T.SCallSite leaf location (T.SVar (Parser.sourceOperatorName operator))) a) b)
    else Parsec.pFail "operator at another precedence"

operatorChecks :: IO ()
operatorChecks = do
  let operators = map H.unpack Lexer.sharedValueOperators
      references = concatMap (\op -> [[op],["M",".",op],["M","."++op],
        ["M",".","N","."++op]]) operators
      errors = [[],[")"],["M"],["M","."],["M",".","bad"],["M",".?"] ,
        ["+","bad"],["M",".+","bad"],["++"],["x",")"],[":",")"]]
      inputs = errors ++ [reference ++ [")"] ++ replicate n "tail"
        | reference <- references, n <- [0,1,256]]
  forM_ [T.LegacyEmlfV1,T.SharedHaskellV1,T.MetadataSyntax] $ \syntax ->
    forM_ inputs $ \input -> do
      let state = stateFor syntax input
      forM_ [id,Parsec.pTry] $ \attempt ->
        check ("operator prefix preserves full parse result: " ++ show (take 8 input))
          (sameResult (Parsec.pRun (attempt oldPrefix) state)
            (Parsec.pRun (attempt Parser.parenthesizedOperatorReference) state))
      let applied parser = Parsec.pMap (\f -> f (T.SVar "left") (T.SVar "right")) parser
      check ("infix endpoints preserve precedence failures: " ++ show (take 8 input))
        (sameResult (Parsec.pRun (applied (oldInfix ["+","-"])) state)
          (Parsec.pRun (applied (Parser.sharedOperatorParser ["+","-"])) state))

  -- Independently pin the original whole-token endpoint when pSymbolPrefix
  -- splits a qualifier's dot from the final '.++' token.
  let state = stateFor T.SharedHaskellV1 ["M",".","N",".++",")","tail"]
      expected = T.SCallSite "++"
        (T.SourceSpan "span-package" "Operators" "Operators.hs" 3 5 3 14)
        (T.SVar "M.N.++")
  case Parsec.pRun Parser.parenthesizedOperatorReference state of
    Parsec.PSuccess tree (Parsec.ParseState _ rest _ _ _ _) True -> do
      check "qualified prefix has exact package/module/file and token endpoints"
        (Equality.eqSExpr expected tree)
      check "prefix leaves closing delimiter and continuation untouched"
        (map (H.unpack . Lexer.tokenText) rest == [")","tail"])
    _ -> fail "qualified prefix did not parse"

moduleChecks :: IO ()
moduleChecks = do
  let prologue = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n"
      shared = prologue ++ "module Operators where {\nprefix = (M.+);\ninfixValue = left M.N.++ right;\n}\n"
      spanAt line start end = T.SourceSpan "span-package" "Operators" "Operators.hs" line start line end
      variable line name start end = T.SCallSite name (spanAt line start end) (T.SVar name)
      expectedPrefix = T.SCallSite "+" (spanAt 4 11 14) (T.SVar "M.+")
      expectedInfix = T.SApp (T.SApp
        (T.SCallSite "++" (spanAt 5 19 25) (T.SVar "$MLF.Infix.M.N.++"))
        (variable 5 "left" 14 18)) (variable 5 "right" 26 31)
  case Parser.parseModuleWithProfileInPackage "span-package" T.SharedHaskellV1 "Operators.hs" (H.literal shared) of
    T.Right (T.SourceModule _ _ _ _ _ _ _ values _ _) -> do
      let binding wanted = [body | (name,_,body) <- values, Prim.eqString name wanted]
      case (binding "prefix",binding "infixValue") of
        ([prefix],[infixValue]) -> do
          check "normal module parser preserves qualified prefix call sites"
            (Equality.eqSExpr expectedPrefix prefix)
          check "normal module parser preserves qualified infix call sites"
            (Equality.eqSExpr expectedInfix infixValue)
        _ -> fail "module parser lost operator bindings"
    T.Left message -> fail (H.unpack message)

-- Reproduce the pre-9815b98 append accumulator without duplicating any pattern
-- normalization. This catches ordering/fresh-name changes on wide mixed rows.
oldNormalizeRow env values (Surface.MatchRow patterns body rowIndex) = do
  (normalized, rhs) <- Std.foldM
    (\(done,current) (value,pattern) -> do
      (next,updated) <- Surface.normalizePattern env value pattern current
      Fresh.freshPure (done ++ [next],updated)) ([],body) (zip values patterns)
  Fresh.freshPure (Surface.MatchRow normalized rhs rowIndex)

sameRow (Surface.MatchRow patterns body rowIndex) (Surface.MatchRow other rhs otherIndex) =
  length patterns == length other && and (zipWith Equality.eqSPattern patterns other) &&
    Equality.eqSExpr body rhs && rowIndex == otherIndex

sameFresh (T.Left a) (T.Left b) = Prim.eqString a b
sameFresh (T.Right (a,counter,used)) (T.Right (b,otherCounter,otherUsed)) =
  sameRow a b && counter == otherCounter &&
    map H.unpack (Set.toList used) == map H.unpack (Set.toList otherUsed)
sameFresh _ _ = False

rowChecks :: IO ()
rowChecks = do
  let name prefix i = H.literal (prefix ++ show i)
      patternAt i = case i `mod` 4 of
        0 -> T.SAsPattern (name "as" i) (T.SIntPattern (fromIntegral i))
        1 -> T.SLazyPattern (T.SNestedPattern "(,)"
          [T.SDefaultPattern (T.Just (name "first" i)),T.SDefaultPattern (T.Just (name "last" i))])
        2 -> T.SDefaultPattern (T.Just (name "plain" i))
        _ -> T.SAsPattern (name "outer" i)
          (T.SLazyPattern (T.SDefaultPattern (T.Just (name "lazy" i))))
      runRow normal values patterns = Fresh.runFreshState
        (normal Data.emptyDataEnv values (Surface.MatchRow patterns (T.SVar "result") 73)) 17
        (Fresh.reservedNames ["lazyPatternMatch17","lazyPatternHead19","matchValue18"])
  forM_ [0,1,2,7,32] $ \width -> do
    let patterns = map patternAt [0..width-1]
        values = [T.SVar (name "value" i) | i <- [0..width-1]]
    check ("row order, row identity, fresh counter and reserved names at width " ++ show width)
      (sameFresh (runRow oldNormalizeRow values patterns) (runRow Surface.normalizeRow values patterns))
  forM_ [0,1,2,17,128,1024] $ \width -> do
    let patterns = [T.SIntPattern (fromIntegral i) | i <- [0..width-1]]
        values = replicate width (T.SVar "value")
    check ("wide row preserves every column at width " ++ show width)
      (sameFresh (runRow oldNormalizeRow values patterns) (runRow Surface.normalizeRow values patterns))

run :: IO ()
run = operatorChecks >> moduleChecks >> rowChecks
