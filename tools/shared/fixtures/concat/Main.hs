{-# LANGUAGE ScopedTypeVariables #-}
module Main where

import Prelude
import qualified Control.Exception as Exception
import Control.Monad (forM_, unless)
import System.Mem (performGC)
import qualified Bootstrap.Primitive as Metadata
import qualified Bootstrap.Runtime as Runtime
import qualified Bootstrap.Std as S
import qualified Bootstrap.Types as T
import qualified ConcatReference as Reference
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

assert :: Bool -> String -> IO ()
assert condition message = unless condition (error message)

engines :: [(String, [B.String] -> B.String)]
engines = [("stdlib", S.concatStrings), ("primitive", P.concatStringList),
           ("frozen-balanced", Reference.concatStrings)]

literalCases :: [([String], String)]
literalCases =
  [([], ""), ([""], ""), (["", "", ""], ""), (["single"], "single"),
   (["a", "b"], "ab"), (["a", "b", "c"], "abc"),
   (["", "a", "", "b", ""], "ab"), (["α", "β"], "αβ"),
   (["A", "😀", "Z"], "A😀Z"), (["\0"], "\0"),
   (["a\0", "\0b"], "a\0\0b"), (["\127", "\128"], "\127\128"),
   (["e", "\769"], "e\769"), (["\1114111", "\0"], "\1114111\0"),
   (["α😀", "", "\0", "z"], "α😀\0z"),
   (["last", "", ""], "last")]

finiteCases :: [[String]]
finiteCases = concat [sequence (replicate n ["", "a", "α", "😀", "\0", "ab"]) | n <- [0..4]]

largeCases :: [[String]]
largeCases =
  [replicate 65536 "", replicate 16385 "a",
   replicate 16384 "α😀\0", [replicate 100000 'x'],
   [replicate 50000 'a', "α\0😀", replicate 50000 'z']]

checkText :: String -> B.String -> String -> IO ()
checkText label actual expected = do
  assert (B.unpack actual == expected) (label ++ ": text differs")
  assert (P.stringLength actual == toInteger (length expected)) (label ++ ": scalar length differs")
  forM_ (zip [0..] expected) $ \(index, character) ->
    assert (P.stringCodeAt actual index == toInteger (fromEnum character))
      (label ++ ": scalar differs at " ++ show index)

bottom :: String -> a
bottom message = Exception.throw (Exception.ErrorCall message)

-- Preserve a worker boundary around the larger strict expression; inlining
-- these cases into the call site would miss premature suffix evaluation.
{-# NOINLINE appendJoined #-}
appendJoined :: ([B.String] -> B.String) -> [B.String] -> B.String -> B.String
appendJoined join pieces suffix = P.concatString (join pieces) suffix

demandCases :: ([B.String] -> B.String) -> [(String, Either String Bool, Bool)]
demandCases join =
  [("list-bottom", Left "list-first", demand (bottom "list-first")),
   ("head-before-tail", Left "head-first", demand (bottom "head-first" : bottom "tail-second")),
   ("tail-required", Left "tail-required", demand (B.literal "a" : bottom "tail-required")),
   ("second-before-tail", Left "second-first",
    demand (B.literal "a" : bottom "second-first" : bottom "tail-second")),
   ("third-before-tail", Left "third-first",
    demand (B.literal "a" : B.literal "b" : bottom "third-first" : bottom "tail-second")),
   ("empty-before-second", Left "second-first",
    demand (B.literal "" : bottom "second-first" : bottom "tail-second")),
   ("singleton-bottom", Left "singleton-required", demand [bottom "singleton-required"]),
   ("empty-pair-tail", Left "tail-required",
    demand (B.literal "" : B.literal "" : bottom "tail-required")),
   ("strict-string-left", Left "string-left",
    demand [P.concatString (bottom "string-left") (bottom "string-right")]),
   ("outer-head-before-suffix", Left "head-first",
    P.stringLength (appendJoined join [bottom "head-first"] (bottom "suffix-second")) == 0),
   ("outer-tail-before-suffix", Left "tail-first",
    P.stringLength (appendJoined join (B.literal "a" : bottom "tail-first")
      (bottom "suffix-second")) == 0),
   ("unused-result", Right True, let unused = join (bottom "unused-list") in True),
   ("untaken-result", Right True,
    if False then demand (bottom "untaken-list") else True)]
  where demand fragments = P.stringLength (join fragments) == 0

observe :: Bool -> IO (Either String Bool)
observe value = do
  result <- Exception.try (Exception.evaluate value)
  case result of
    Left (exception :: Exception.ErrorCall) -> pure (Left (Exception.displayException exception))
    Right answer -> pure (Right answer)

metadataCases :: [(String, Bool)]
metadataCases =
  [("new opcode", Metadata.primitiveCode T.PConcatStringList == 107),
   ("previous opcode", Metadata.primitiveCode T.PIOErrorWithStack == 106),
   ("name", B.unpack (Metadata.primitiveName T.PConcatStringList) == "concatStringList"),
   ("arity", Metadata.primitiveArity T.PConcatStringList == 1),
   ("strict operand", Metadata.primitiveStrict T.PConcatStringList),
   ("signature", case Metadata.primitiveSignature T.PConcatStringList of
      ([], T.Function (T.Applied list [T.Applied input []]) (T.Applied output [])) ->
        map B.unpack [list, input, output] == ["[]", "String", "String"]
      _ -> False),
   ("name lookup", case Metadata.lookupTargetPrimitive (B.literal "concatStringList") of
      T.Just T.PConcatStringList -> True
      _ -> False),
   ("append-only opcode inventory", map Metadata.primitiveCode Metadata.allPrimitives == [0..107])]

-- The interpreter's RString constructor can be WHNF while its payload is
-- bottom. Source panic alone exercises Either failure and misses this case.
interpreterPayloadCases :: [(String, Either String Bool, Bool)]
interpreterPayloadCases =
  [("payload before tail Left", Left "payload-first",
    case Runtime.runtimeStringChunks
      (T.Right (Runtime.RConstructor (B.literal ":")
        [T.Right (Runtime.RString (bottom "payload-first")), T.Left (B.literal "tail-second")])) [] of
      T.Left _ -> False
      T.Right _ -> True),
   ("valid payload preserves tail Left", Right True,
    case Runtime.runtimeStringChunks
      (T.Right (Runtime.RConstructor (B.literal ":")
        [T.Right (Runtime.RString (B.literal "a")), T.Left (B.literal "tail-required")])) [] of
      T.Left message -> B.unpack message == "tail-required"
      T.Right _ -> False),
   ("canonical payload order", Right True,
    case Runtime.runtimeStringChunks
      (T.Right (Runtime.RConstructor (B.literal ":")
        [T.Right (Runtime.RString (B.literal "a")),
         T.Right (Runtime.RConstructor (B.literal ":")
           [T.Right (Runtime.RString (B.literal "α")),
            T.Right (Runtime.RConstructor (B.literal "[]") [])])])) [] of
      T.Left _ -> False
      T.Right pieces -> map B.unpack pieces == ["a", "α"])]

main :: IO ()
main = do
  forM_ metadataCases $ \(label, condition) -> assert condition ("metadata: " ++ label)
  forM_ interpreterPayloadCases $ \(label, expected, value) -> do
    actual <- observe value
    assert (actual == expected)
      ("interpreter payload " ++ label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
  forM_ engines $ \(name, join) -> do
    forM_ (zip [0 :: Int ..] literalCases) $ \(index, (pieces, expected)) ->
      checkText (name ++ " literal " ++ show index) (join (map B.literal pieces)) expected
    forM_ (zip [0 :: Int ..] finiteCases) $ \(index, pieces) ->
      checkText (name ++ " finite " ++ show index) (join (map B.literal pieces)) (concat pieces)
    forM_ (zip [0 :: Int ..] largeCases) $ \(index, pieces) -> do
      let actual = join (map B.literal pieces)
      _ <- Exception.evaluate (P.stringLength actual)
      performGC
      checkText (name ++ " large " ++ show index) actual (concat pieces)
    forM_ (demandCases join) $ \(label, expected, value) -> do
      actual <- observe value
      assert (actual == expected)
        (name ++ " demand " ++ label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
  putStrLn "PASS concat-engines 3"
  putStrLn ("PASS concat-metadata " ++ show (length metadataCases))
  putStrLn ("PASS concat-interpreter-payload " ++ show (length interpreterPayloadCases))
  putStrLn ("PASS concat-literals " ++ show (length literalCases))
  putStrLn ("PASS concat-finite " ++ show (length finiteCases))
  putStrLn ("PASS concat-large " ++ show (length largeCases))
  putStrLn ("PASS concat-demand " ++ show (length (demandCases S.concatStrings)))
  putStrLn "String-list concatenation semantic audit passed"
