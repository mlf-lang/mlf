module Main where

import Prelude
import Control.Exception (Exception, catch, evaluate, throw)
import Control.Monad (forM_, unless)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Lexer as L
import qualified Bootstrap.Parsec as C

literal = B.literal
append = B.v_concatString
join = B.v_concatStringList

-- Frozen pre-worker semantics, independent of the maintained pSatisfy helper.
reference predicate expected = C.Parser $ \state -> case state of
  C.ParseState file tokens finish syntax source package _ -> case tokens of
    [] -> C.PFailure (append (literal "unexpected end of input; expected ") expected) state False
    token : rest -> if predicate (L.tokenText token)
      then C.PSuccess (L.tokenText token) (C.ParseState file rest finish syntax source package tokens) True
      else C.PFailure (append (literal "unexpected ") (append (L.tokenText token) (append (literal "; expected ") expected))) state False

tokenView (L.Token value a b c d) = (B.unpack value,a,b,c,d)
stateView (C.ParseState file tokens finish syntax source package _) =
  (B.unpack file,map tokenView tokens,tokenView finish,B.unpack (L.sourceSyntaxName syntax),B.unpack source,B.unpack package)
resultView result = case result of
  C.PFailure message state consumed -> (False,B.unpack message,stateView state,consumed)
  C.PSuccess value state consumed -> (True,B.unpack value,stateView state,consumed)
spanValue (T.SourceSpan package source file a b c d,value) = literal (show (B.unpack package,B.unpack source,B.unpack file,a,b,c,d,B.unpack value))
maybeValue value = case value of { T.Nothing -> literal "nothing"; T.Just a -> join [literal "just:",a] }
parsers atom expected =
  let x = atom (B.v_eqString (literal "x")) expected
      y = atom (B.v_eqString (literal "y")) (literal "tail")
      xy = C.pThen x y
  in
  [ atom (const True) expected
  , atom (const False) expected
  , x
  , C.pChoice x y
  , C.pChoice xy y
  , C.pChoice (C.pTry xy) x
  , C.pLook xy
  , C.pMap (const (literal "unit")) (C.pNot x)
  , C.pMap join (C.pMany x)
  , C.pMap join (C.pSome x)
  , C.pMap maybeValue (C.pOptional x)
  , C.pMap join (C.pSepEndBy x (atom (B.v_eqString (literal ",")) (literal ",")))
  , C.pMap spanValue (C.pWithSpan xy)
  , C.pMap join (C.pMany (C.pTry xy))
  ]
check label ok = unless ok (fail label)
data Demand = Demand String deriving Show
instance Exception Demand
bottom = throw . Demand
outcome value = catch (Right <$> evaluate (length value `seq` value)) handler
  where handler (Demand label) = pure (Left label)
tag result = case result of { C.PFailure _ _ _ -> "failure"; C.PSuccess _ _ _ -> "success" }
message result = case result of { C.PFailure value _ _ -> B.unpack value; C.PSuccess value _ _ -> B.unpack value }

main = do
  let profiles = [T.SharedHaskellV1,T.LegacyEmlfV1,T.MetadataSyntax]
      lists = [[],["x"],["y"],["x","y"],["x","x"],["x",",","x"],["x",","],["(","x",")"],["{","x","}"],[".suffix"],["λ"],["\0"],["x","y","tail"],["","x"],["x",",","x",",","y"]]
      offsets = [0,1,100,-1]
      labels = ["expected","","wanted\0λ"]
      makeTokens base names = zipWith (\index name -> L.Token (literal name) (base+index) 3 (base+index) 7) [0..] names
      finish = L.Token (literal "<eof>") 999 9 999 9
      state tokens syntax = C.initialParseState (literal "input\0λ") tokens finish syntax (literal "M") (literal "pkg")
  forM_ profiles $ \syntax -> forM_ lists $ \names -> forM_ offsets $ \offset -> forM_ labels $ \label -> do
    let current = parsers C.pSatisfy (literal label)
        old = parsers reference (literal label)
        input = state (makeTokens offset names) syntax
    check "nonvacuous parser graph" (length current == 14 && length old == 14)
    forM_ (zip current old) $ \(a,b) -> check "complete parser result/state/error/consumption" (resultView (C.pRun a input) == resultView (C.pRun b input))
  let run atom predicate expected tokens = C.pRun (atom predicate expected) (state tokens T.SharedHaskellV1)
      good = makeTokens 1 ["x"]
      bad = [bottom "token"]
      cases atom =
        [ ("constructor",case atom (bottom "predicate") (bottom "expected") of C.Parser _ -> "parser",Right "parser")
        , ("empty predicate",tag (run atom (bottom "predicate") (bottom "expected") []),Right "failure")
        , ("empty expected",message (run atom (bottom "predicate") (bottom "expected") []),Left "expected")
        , ("predicate first",tag (run atom (bottom "predicate") (bottom "expected") good),Left "predicate")
        , ("failure token lazy",tag (run atom (const False) (bottom "expected") bad),Right "failure")
        , ("success token lazy",tag (run atom (const True) (bottom "expected") bad),Right "success")
        , ("message token first",message (run atom (const False) (bottom "expected") bad),Left "token")
        , ("success value",message (run atom (const True) (bottom "expected") bad),Left "token")
        , ("message expected",message (run atom (const False) (bottom "expected") good),Left "expected")
        , ("token list first",tag (run atom (bottom "predicate") (bottom "expected") (bottom "tokens")),Left "tokens")
        , ("backtracking skips expected",message (C.pRun (C.pChoice (atom (const False) (bottom "expected")) (C.pPure (literal "fallback"))) (state good T.SharedHaskellV1)),Right "fallback")
        ]
  forM_ (zip (cases C.pSatisfy) (cases reference)) $ \((label,a,expected),(_,b,_)) -> do
    actual <- outcome a
    old <- outcome b
    check (label ++ show (actual,old,expected)) (actual == old && actual == expected)
  putStrLn ("Parser satisfy controls: " ++ show (length profiles * length lists * length offsets * length labels * 14) ++ " complete result cases; " ++ show (length (cases reference)) ++ " demand checks")
