-- Native Haskell baseline for snake.emlf. Only the base package is needed.
--
-- mkdir -p dist-newstyle/snake-baseline
-- ghc -O2 -Wall -Werror -main-is SnakeBaseline examples/SnakeBaseline.hs \
--   -outputdir dist-newstyle/snake-baseline -o dist-newstyle/snake-baseline/snake-haskell
-- dist-newstyle/snake-baseline/snake-haskell
module SnakeBaseline where

import System.IO (hFlush, stdout)

-- Integer matches the source language's arbitrary-precision Int.
data Position = Position Integer Integer deriving (Eq, Show)
data Direction = North | South | West | East deriving (Eq, Show)
data Command = Turn Direction | Forward | Quit | Invalid deriving (Eq, Show)
data Snake = Snake Position [Position] deriving (Eq, Show)
data Game = Game Snake Direction Position Integer deriving (Eq, Show)
data Outcome = Continue Game | Lost String Integer | Won Integer deriving (Eq, Show)

-- The same monadic interface serves the real console and scripted tests.
data Console m = Console
  { readLine :: m String
  , writeText :: String -> m ()
  }

width, height :: Integer
width = 12
height = 8

dropLast :: [a] -> [a]
dropLast [] = []
dropLast [_] = []
dropLast (first:rest) = first : dropLast rest

move :: Direction -> Position -> Position
move direction (Position x y) = case direction of
  North -> Position x (y - 1)
  South -> Position x (y + 1)
  West -> Position (x - 1) y
  East -> Position (x + 1) y

opposite :: Direction -> Direction -> Bool
opposite a b = case a of
  North -> b == South
  South -> b == North
  West -> b == East
  East -> b == West

outside :: Position -> Bool
outside (Position x y) = x < 0 || y < 0 || x == width || y == height

-- Keep the same row-major food search as the eMLF game.
findFood :: [Position] -> Maybe Position
findFood occupied = scan 0 0
  where
    scan x y
      | y == height = Nothing
      | x == width = scan 0 (y + 1)
      | candidate `elem` occupied = scan (x + 1) y
      | otherwise = Just candidate
      where candidate = Position x y

step :: Direction -> Game -> Outcome
step requested (Game (Snake headPosition body) heading food score)
  | outside next = Lost "wall" score
  | next `elem` remaining = Lost "body" score
  | eating = case findFood (next : remaining) of
      Nothing -> Won (score + 1)
      Just newFood -> Continue (Game moved direction newFood (score + 1))
  | otherwise = Continue (Game moved direction food score)
  where
    direction = if opposite heading requested then heading else requested
    next = move direction headPosition
    eating = next == food
    -- The old tail leaves before collision checking, except when eating.
    remaining = if eating then headPosition : body else dropLast (headPosition : body)
    moved = Snake next remaining

parseCommand :: String -> Command
parseCommand text = case text of
  "q" -> Quit
  "w" -> Turn North
  "s" -> Turn South
  "a" -> Turn West
  "d" -> Turn East
  "" -> Forward
  _ -> Invalid

tile :: Game -> Position -> String
tile (Game (Snake headPosition body) _ food _) position
  | position == headPosition = "@"
  | position `elem` body = "o"
  | position == food = "*"
  | otherwise = "."

row :: Game -> Integer -> String
row game y = "|" ++ cells 0
  where
    cells x
      | x == width = "|\n"
      | otherwise = tile game (Position x y) ++ cells (x + 1)

rows :: Game -> Integer -> String
rows game y
  | y == height = ""
  | otherwise = row game y ++ rows game (y + 1)

directionName :: Direction -> String
directionName direction = case direction of
  North -> "up"
  South -> "down"
  West -> "left"
  East -> "right"

writeLine :: Monad m => Console m -> String -> m ()
writeLine console text = writeText console (text ++ "\n")

draw :: Monad m => Console m -> Game -> m ()
draw console game@(Game _ heading _ score) = do
  writeLine console ("\nScore: " ++ show score ++ "  Direction: " ++ directionName heading)
  writeLine console "+------------+"
  writeText console (rows game 0)
  writeLine console "+------------+"

play :: Monad m => Console m -> Game -> m ()
play console game@(Game _ heading _ score) = do
  draw console game
  writeText console "Move [w/a/s/d, Enter, q]: "
  input <- readLine console
  case parseCommand input of
    Quit -> writeLine console ("Goodbye. Score: " ++ show score)
    Invalid -> do
      writeLine console "Use w, a, s, d, Enter, or q. No move made."
      play console game
    Forward -> advance heading
    Turn direction -> advance direction
  where
    advance direction = case step direction game of
      Continue next -> play console next
      Lost reason finalScore ->
        writeLine console ("Game over: hit " ++ reason ++ ". Score: " ++ show finalScore)
      Won finalScore ->
        writeLine console ("You filled the board! Score: " ++ show finalScore)

initial :: Game
initial = Game (Snake (Position 4 3) [Position 3 3, Position 2 3]) East (Position 6 3) 0

runGame :: Monad m => Console m -> m ()
runGame console = do
  writeLine console "Snake: @ head, o body, * food. The board is 12 by 8."
  writeLine console "WASD + Enter moves; Enter continues; q quits. Reverse turns are ignored."
  writeLine console "Eat food to grow. Avoid walls and your body. Food uses the first free square."
  play console initial

main :: IO ()
main = runGame Console
  { readLine = getLine
  , writeText = \text -> putStr text >> hFlush stdout
  }
