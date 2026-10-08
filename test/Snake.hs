module Snake (snakeTests) where

import Control.Monad (unless)
import Data.IORef
import Data.List (isInfixOf, isPrefixOf)
import System.Timeout (timeout)
import Backends (Backends, Event (..))
import qualified Backends as B
import MLF.Compiler
import MLF.Parser (parseExpr, parseProgram)
import qualified MLF.Runtime as R
import qualified MLF.Syntax as S
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import qualified SnakeBaseline as H

type Test = (String, IO ())

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: Compilation -> IO X.Term
checked result = do
  term <- right (XP.parseTerm "<Snake xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed term)
  require (T.alphaEq ty (T.Con "IO" [T.Con "Unit" []])) "Snake must have type IO Unit"
  require (X.erase term == X.erase (compiledTerm result)) "Snake round trip changed erasure"
  pure term

-- Every scenario must consume exactly its scripted input and terminate.
runOn :: Backends -> X.Term -> [String] -> IO String
runOn backends term input = do
  (result,trace) <- B.capture backends term input
  right result
  pure (concat [text | Write text <- trace])

capture :: [String] -> (R.IOBackend -> IO ()) -> IO String
capture input action = do
  pending <- newIORef input
  output <- newIORef []
  let backend = R.IOBackend
        { R.readLine = do
            remaining <- readIORef pending
            case remaining of
              [] -> ioError (userError "Snake requested unexpected input")
              line:rest -> writeIORef pending rest >> pure line
        , R.writeText = \s -> modifyIORef' output (s:)
        , R.writeBytes = \_ -> fail "Snake unexpectedly wrote binary output"
        }
  outcome <- timeout 10000000 (action backend)
  case outcome of
    Nothing -> fail "Snake did not terminate"
    Just () -> pure ()
  remaining <- readIORef pending
  require (null remaining) ("Snake stopped before consuming " ++ show remaining)
  concat . reverse <$> readIORef output

runWithBaseline :: Backends -> X.Term -> [String] -> IO String
runWithBaseline backends term input = do
  output <- runOn backends term input
  baseline <- capture input $ \backend -> H.runGame H.Console
    { H.readLine = R.readLine backend
    , H.writeText = R.writeText backend
    }
  require (output == baseline) ("Haskell/eMLF transcript mismatch for " ++ show input ++
    "\neMLF:\n" ++ output ++ "\nHaskell:\n" ++ baseline)
  pure output

board :: [(Int,String)] -> [String]
board changed = ["|" ++ maybe (replicate 12 '.') id (lookup y changed) ++ "|" | y <- [0..7]]

frames :: String -> IO [[String]]
frames output = go (lines output)
  where
    border = "+------------+"
    go [] = pure []
    go (line:rest)
      | line == border = do
          let (cells,after) = splitAt 8 rest
          require (length cells == 8 && all validRow cells)
            ("malformed board: " ++ show cells)
          case after of
            end:more | end == border -> (cells:) <$> go more
            _ -> fail "missing bottom border"
      | otherwise = go rest
    validRow ('|':rest) = length rest == 13 && drop 12 rest == "|"
    validRow _ = False

initialBoard :: [String]
initialBoard = board [(3,"..oo@.*.....")]

snakeTests :: Backends -> [Test]
snakeTests backends =
  [ ("Snake: playable source and xMLF sessions", do
      putStrLn "  Snake: compiling the interactive example"
      source <- readFile "examples/snake.emlf"
      result <- right (compile "examples/snake.emlf" source)
      term <- checked result
      -- Exercise the source compiler's target as well as the standalone
      -- printed/reparsed xMLF used for all the longer sessions below.
      direct <- run (compiledTerm result) ["q"]
      quit <- runBoth term ["q"]
      require (direct == quit) "source and standalone xMLF execution differ"
      quitFrames <- frames quit
      require (quitFrames == [initialBoard] && "Goodbye. Score: 0\n" `isInfixOf` quit)
        ("unexpected initial game: " ++ quit)

      growth <- runBoth term ["d","d","q"]
      growthFrames <- frames growth
      require (growthFrames == [initialBoard,board [(3,"...oo@*.....")],board [(0,"*..........."),(3,"...ooo@.....")]])
        ("movement/growth rendered incorrectly: " ++ growth)
      require ("Goodbye. Score: 1\n" `isInfixOf` growth) "eating did not increase the score"

      invalid <- runBoth term ["x","","q"]
      invalidFrames <- frames invalid
      require (invalidFrames == [initialBoard,initialBoard,board [(3,"...oo@*.....")]] &&
        "No move made." `isInfixOf` invalid) ("invalid/empty command behavior: " ++ invalid)

      reverseTurn <- runBoth term ["a","q"]
      reverseFrames <- frames reverseTurn
      require (reverseFrames == [initialBoard,board [(3,"...oo@*.....")]]) "reverse turn was not ignored"

      turns <- runBoth term ["w","a","s","d","q"]
      turnFrames <- frames turns
      require (length turnFrames == 5 && last turnFrames == board [(2,"...o........"),(3,"...o@.*.....")])
        ("WASD turns produced the wrong snake: " ++ turns)
      require (filter (isPrefixOf "Score:") (lines turns) ==
        ["Score: 0  Direction: " ++ d | d <- ["right","up","left","down","right"]]) "wrong headings"

      wall <- runBoth term (replicate 8 "d")
      wallFrames <- frames wall
      require (length wallFrames == 8 && "Game over: hit wall. Score: 1\n" `isInfixOf` wall)
        ("wall collision did not end the game: " ++ wall)

      body <- runBoth term (["d","d"] ++ replicate 3 "w" ++ replicate 6 "a" ++ ["s","d","w"])
      bodyFrames <- frames body
      require (length bodyFrames == 14 && "Game over: hit body. Score: 2\n" `isInfixOf` body)
        ("body collision did not end the game: " ++ body)
      putStrLn "  Snake: all 7 sessions pass on both backends and match Haskell")
  , ("Snake: pure rules, departing tail, food search, and full-board win", do
      putStrLn "  Snake: compiling the pure-rule checks"
      source <- readFile "examples/snake.emlf"
      program <- right (parseProgram "examples/snake.emlf" source)
      entry <- right (parseExpr "<Snake rule checks>" rulesDriver)
      -- Keep the actual example's definitions through 'step', replacing only
      -- its UI with a test driver. No game rules are reimplemented here.
      program' <- right (withRulesEntry entry program)
      result <- right (compileProgram program')
      term <- checked result
      output <- run term []
      require (lines output == map (\(label,_,expected) -> label ++ ": " ++ expected) ruleCases)
        ("unexpected rule outcomes:\n" ++ output)
      let baseline = [label ++ ": " ++ describeOutcome result' | (label,result') <- baselineRuleCases]
      require (lines output == baseline) ("Haskell/eMLF rule mismatch:\n" ++ unlines baseline)
      putStrLn ("  Snake: " ++ show (length ruleCases) ++ " rule checks pass on both backends and match Haskell"))
  ]
  where
    run = runOn backends
    runBoth = runWithBaseline backends

withRulesEntry :: S.Expr -> S.Program -> Either String S.Program
withRulesEntry entry program = case program of
  S.Program ds body -> S.Program ds <$> replace body
  S.ClassProgram ds cs instances body -> S.ClassProgram ds cs instances <$> replace body
  where
    replace (S.Let name rhs body)
      | name == "step" = Right (S.Let name rhs entry)
      | otherwise = S.Let name rhs <$> replace body
    replace _ = Left "Snake example no longer defines step in its helper scope"

position :: (Int,Int) -> String
position (x,y) = "(Position " ++ show x ++ " " ++ show y ++ ")"

positions :: [(Int,Int)] -> String
positions = foldr (\p rest -> "(Cons " ++ position p ++ " " ++ rest ++ ")") "Nil"

game :: (Int,Int) -> [(Int,Int)] -> String -> (Int,Int) -> Int -> String
game headPosition body heading food score = "(Game (Snake " ++ position headPosition ++ " " ++ positions body ++ ") " ++
  heading ++ " " ++ position food ++ " " ++ show score ++ ")"

describeOutcome :: H.Outcome -> String
describeOutcome outcome = case outcome of
  H.Lost reason score -> "lost " ++ reason ++ " score=" ++ show score
  H.Won score -> "won score=" ++ show score
  H.Continue (H.Game (H.Snake headPosition body) _ food score) ->
    "continue " ++ showPosition headPosition ++ " [" ++ concatMap showPosition body ++
      "] food=" ++ showPosition food ++ " score=" ++ show score
  where
    showPosition (H.Position x y) = "(" ++ show x ++ "," ++ show y ++ ")"

-- Independently construct matching Haskell inputs. The existing handwritten
-- golden results below remain the oracle for both implementations.
baselineRuleCases :: [(String,H.Outcome)]
baselineRuleCases =
  [ ("ordinary move", H.step H.East (state (4,3) [(3,3),(2,3)] H.East (6,3) 0))
  , ("growth", H.step H.East (state (5,3) [(4,3),(3,3)] H.East (6,3) 0))
  , ("reverse", H.step H.West (state (4,3) [(3,3),(2,3)] H.East (6,3) 0))
  , ("departing tail", H.step H.West (state (1,1) [(1,2),(0,2),(0,1)] H.North (11,7) 7))
  , ("body", H.step H.East (state (1,1) [(1,0),(2,0),(2,1),(2,2)] H.South (11,7) 7))
  , ("left wall", H.step H.West (state (0,3) [] H.West (11,7) 7))
  , ("right wall", H.step H.East (state (11,3) [] H.East (0,0) 7))
  , ("top wall", H.step H.North (state (3,0) [] H.North (11,7) 7))
  , ("bottom wall", H.step H.South (state (3,7) [] H.South (0,0) 7))
  , ("food skips snake", H.step H.East (state (1,0) [(0,0)] H.East (2,0) 0))
  , ("full board", H.step H.West (state (1,0) almostFull H.West (0,0) 92))
  ]
  where
    state headPosition body heading food score = H.Game
      (H.Snake (point headPosition) (map point body)) heading (point food) score
    point (x,y) = H.Position x y
    almostFull = drop 2 [(x,y) | y <- [0..7], x <- if even y then [0..11] else [11,10..0]]

ruleCases :: [(String,String,String)]
ruleCases =
  [ ("ordinary move", "step East " ++ game (4,3) [(3,3),(2,3)] "East" (6,3) 0,
      "continue (5,3) [(4,3)(3,3)] food=(6,3) score=0")
  , ("growth", "step East " ++ game (5,3) [(4,3),(3,3)] "East" (6,3) 0,
      "continue (6,3) [(5,3)(4,3)(3,3)] food=(0,0) score=1")
  , ("reverse", "step West " ++ game (4,3) [(3,3),(2,3)] "East" (6,3) 0,
      "continue (5,3) [(4,3)(3,3)] food=(6,3) score=0")
  , ("departing tail", "step West " ++ game (1,1) [(1,2),(0,2),(0,1)] "North" (11,7) 7,
      "continue (0,1) [(1,1)(1,2)(0,2)] food=(11,7) score=7")
  , ("body", "step East " ++ game (1,1) [(1,0),(2,0),(2,1),(2,2)] "South" (11,7) 7, "lost body score=7")
  , ("left wall", "step West " ++ game (0,3) [] "West" (11,7) 7, "lost wall score=7")
  , ("right wall", "step East " ++ game (11,3) [] "East" (0,0) 7, "lost wall score=7")
  , ("top wall", "step North " ++ game (3,0) [] "North" (11,7) 7, "lost wall score=7")
  , ("bottom wall", "step South " ++ game (3,7) [] "South" (0,0) 7, "lost wall score=7")
  , ("food skips snake", "step East " ++ game (1,0) [(0,0)] "East" (2,0) 0,
      "continue (2,0) [(1,0)(0,0)] food=(3,0) score=1")
  , ("full board", "step West (Game (Snake (Position 1 0) (serpentine 2 0 1)) West (Position 0 0) 92)", "won score=93")
  ]

rulesDriver :: String
rulesDriver = unlines
  -- Construct the near-full fixture at runtime, keeping compilation small.
  -- Unlike findFood's row-major scan, this path alternates row direction.
  -- Starting at (2,0) leaves the head (1,0) and last food (0,0) free.
  [ "let serpentine : Int -> Int -> Int -> List Position = fix (\\again x y dx ->"
  , "  ifThenElse (eqInt y 8) Nil"
  , "    (ifThenElse (eqInt x 12) (again 11 (addInt y 1) (-1))"
  , "      (ifThenElse (ltInt x 0) (again 0 (addInt y 1) 1)"
  , "        (Cons (Position x y) (again (addInt x dx) y dx))))) in"
  , "let showPosition = \\position -> case position of { Position x y ->"
  , "  concatString \"(\" (concatString (showInt x) (concatString \",\" (concatString (showInt y) \")\"))) } in"
  , "let showBody : List Position -> String = fix (\\again body -> case body of {"
  , "  Nil -> \"\"; Cons p rest -> concatString (showPosition p) (again rest) }) in"
  , "let describe = \\outcome -> case outcome of {"
  , "  Lost reason score -> concatString \"lost \" (concatString reason (concatString \" score=\" (showInt score)));"
  , "  Won score -> concatString \"won score=\" (showInt score);"
  , "  Continue game -> case game of { Game snake heading food score -> case snake of { Snake head body ->"
  , "    concatString \"continue \" (concatString (showPosition head) (concatString \" [\" (concatString (showBody body)"
  , "      (concatString \"] food=\" (concatString (showPosition food) (concatString \" score=\" (showInt score))))))) } }"
  , "} in do {"
  , concat ["putStrLn (concatString " ++ show (label ++ ": ") ++ " (describe (" ++ expression ++ ")));\n" |
      (label,expression,_) <- ruleCases]
  , "return () }"
  ]
