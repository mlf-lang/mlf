module HigherOrderSpecialization (higherOrderTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import qualified Backends as B
import qualified MLF.Compiler as C
import qualified MLF.LLVM as LLVM
import qualified MLF.X.Check as Check
import qualified MLF.X.Type as T

higherOrderTests :: B.Backends -> [(String,IO ())]
higherOrderTests backends =
  [("higher-order specialization: " ++ label, do
      compilation <- either (fail . show) pure (C.compile label source)
      ty <- either fail pure (Check.checkClosed (C.compiledTerm compilation))
      unless (T.alphaEq ty (C.inferredType compilation)) (fail "target type changed")
      if label == "primitive-callback" then do
        llvm <- either fail pure (LLVM.emitLLVM (C.compiledTerm compilation))
        unless (not ("call ptr @mlf_application(" `isInfixOf` llvm))
          (fail "known recursive callback still uses generic application")
      else pure ()
      observed <- B.execute backends B.ProgramEntry (B.Input "" False) (C.compiledTerm compilation)
      unless (either (const False) (const True) (B.outcome observed) &&
              B.output observed == expected && null (B.stderrOutput observed) && null (B.remaining observed))
        (fail (show observed)))
  | (label,source,expected) <- cases]

-- Independent output assertions exercise captures, changing recursive
-- callbacks, discarded arguments and both native Integer representations.
cases :: [(String,String,String)]
cases =
  [ ("primitive-callback","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nmain = printInt (loop addInt 0 10)","55\n")
  , ("captured-callback","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nrun offset = loop (\\z n -> z + n + offset) 0 10\nmain = printInt (run (readInt \"3\"))","85\n")
  , ("partial-callback","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nstep bias z n = z + bias + n\nrun bias = loop (step bias) 0 10\nmain = printInt (run 3)","85\n")
  , ("empty-lazy-capture","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nrun bias = loop (\\z n -> z + bias + n) 42 0\nmain = printInt (run (panic \"unused captured value\"))","42\n")
  , ("discarded-callback-argument","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nmain = printInt (loop (\\z n -> n) (panic \"unused accumulator\") 1)","1\n")
  , ("changing-callback","loop : (Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop (\\x -> f x + 1) (f z) (n - 1)\nmain = printInt (loop (\\x -> x + 1) 0 3)","6\n")
  , ("recursive-capture-scope","loop : (Int -> Int) -> Int -> Int\nloop f n = if n == 0 then f 0 else if n == 1 then loop (\\x -> x + n) 0 else loop f (n - 1)\nmain = printInt (loop (\\x -> x + 100) 2)","1\n")
  , ("unbounded-callback-integers","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nmain = printInt (loop addInt 1267650600228229401496703205376 10)","1267650600228229401496703205431\n")
  , ("constructor-callback","data Box = Box Int\nrepeat : (Int -> Box) -> Int -> Box\nrepeat f n = if n == 0 then f 42 else repeat f (n - 1)\nmain = case repeat Box 3 of Box n -> printInt n","42\n")
  , ("lazy-constructor-callback","data Box = Box Int Int\nrepeat : (Int -> Box) -> Int -> Box\nrepeat f n = if n == 0 then f 42 else repeat f (n - 1)\nmain = case repeat (Box (panic \"unused constructor field\")) 3 of Box _ n -> printInt n","42\n")
  , ("escaping-original-worker","loop : (Int -> Int -> Int) -> Int -> Int -> Int\nloop f z n = if n == 0 then z else loop f (f z n) (n - 1)\nchoose flag a b = if flag then a else b\nmain = printInt (loop addInt 0 10 + (choose (eqString \"a\" \"a\") loop (\\f z n -> z)) (\\z n -> z + n) 0 7)","83\n")
  ]
