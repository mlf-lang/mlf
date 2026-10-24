{-# LANGUAGE OverloadedStrings #-}
-- Actual MLF inference + interpreter checks, hosted by ordinary GHC.
module Main where
import qualified Data.Time.Clock as Clock
import qualified System.IO as HostIO
import qualified Prelude as P
import Prelude (IO, ($), (.), (==), error, putStrLn)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as B

announce name action = do
  now <- Clock.getCurrentTime
  putStrLn (P.show now P.++ " BEGIN: " P.++ name)
  action
source body = B.literal $ "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule Example where\nimport MLF.Primitive\n" P.++ body P.++ "\n"
run body = case C.compile "Example.hs" (source body) of
  T.Left err -> T.Left (C.prettyError err)
  T.Right result -> let term = C.compiledTerm result in
    case R.prepare P.False term of
      T.Left err -> T.Left err
      T.Right (T.Pair env _) -> R.evaluate env (R.REnv M.empty) (X.erase term)
check name body expected = announce name $ case run body of
  T.Right (R.RInteger actual) | actual == expected -> putStrLn ("pass: " P.++ name)
  T.Left err -> error (name P.++ ": " P.++ B.unpack err)
  _ -> error (name P.++ ": wrong result")
reject name body = announce name $ case run body of
  T.Left _ -> putStrLn ("pass: reject " P.++ name)
  _ -> error (name P.++ ": unexpectedly accepted")
main :: IO ()
main = do
  HostIO.hSetBuffering HostIO.stdout HostIO.LineBuffering
  check "canonical lists and nested pattern" "main = case [20,22] of { x:y:[] -> x + y; _ -> 0 }" 42
  check "cons constructor function" "main = case (:) 42 [] of { x:_ -> x; _ -> 0 }" 42
  check "tuple constructor function" "main = case (,) 20 22 of { (x,y) -> x + y }" 42
  check "tuple unit and explicit types" "f :: (Int, ()) -> Int\nf (x,()) = x\nmain = f (42,())" 42
  check "triple and quad" "main = case ((1,2,3),(4,5,6,7)) of { ((a,b,c),(d,e,f,g)) -> a+b+c+d+e+f+g }" 28
  check "list datatype field" "data Box a = Box [a]\nmain = case Box [42] of { Box (x:_) -> x; _ -> 0 }" 42
  check "opaque text overloaded literal" "main = stringLength (\"hello\" :: String)" 5
  check "ordinary overloaded text pattern" "f :: String -> Int\nf \"hello\" = 42\nf _ = 0\nmain = f \"hello\"" 42
  check "string pattern mismatch" "f :: String -> Int\nf \"hello\" = 42\nf _ = 0\nmain = f \"other\"" 0
  check "[Char] standard IsString input" "main = case (\"a\" :: [Char]) of { c:[] -> charCode c; _ -> 0 }" 97
  check "custom Eq and IsString dictionaries" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 9 }\ninstance Eq Key where { (==) _ _ = True }\nf :: Key -> Int\nf \"not-the-input\" = 42\nf _ = 0\nmain = f (Key 3)" 42
  check "Eq /= minimum default" "data Key = Key Int\ninstance Eq Key where { (/=) _ _ = False }\nmain = if Key 1 == Key 2 then 42 else 0" 42
  check "overlapping custom Eq falls through later columns" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\nf :: Key -> Int -> Int\nf \"a\" 0 = 10\nf \"b\" 1 = 42\nf _ _ = 0\nmain = f (Key 0) 1" 42
  check "same string row retries later column" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\nf :: Key -> Int -> Int\nf \"a\" 0 = 10\nf \"a\" 1 = 42\nf _ _ = 0\nmain = f (Key 0) 1" 42
  check "overloaded row retries nested tuple and list" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\nf :: Key -> (Int, [Int]) -> Int\nf \"a\" (0,[0]) = 10\nf \"b\" (1,[2]) = 42\nf _ _ = 0\nmain = f (Key 0) (1,[2])" 42
  check "overloaded row first match wins" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\nf :: Key -> Int -> Int\nf \"a\" 0 = 10\nf \"b\" 0 = 42\nf _ _ = 0\nmain = f (Key 0) 0" 10
  reject "distinct user List is not builtin list" "data List a = Nil | Cons a (List a)\nf :: List Int -> Int\nf _ = 0\nmain = f [1]"
  reject "missing Eq for string pattern" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\nf :: Key -> Int\nf \"x\" = 1\nf _ = 0\nmain = f (Key 0)"
  putStrLn "item4 source semantics: passed"
