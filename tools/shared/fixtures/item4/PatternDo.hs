{-# LANGUAGE OverloadedStrings #-}
-- Actual MLF inference + interpreter checks, hosted by ordinary GHC.
module Main where
import qualified Data.Time.Clock as Clock
import qualified Data.List as L
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
rejectConstraint name body expected = announce name $ case C.compile "Example.hs" (source body) of
  T.Left (T.CompileError T.Resolution message) | contains expected (B.unpack message) -> putStrLn ("pass: reject " P.++ name)
  T.Left err -> error (name P.++ ": wrong failure " P.++ B.unpack (C.prettyError err))
  T.Right _ -> error (name P.++ ": unexpectedly accepted")
rejectInference name body expected = announce name $ case C.compile "Example.hs" (source body) of
  T.Left (T.CompileError T.Inference message) | contains expected (B.unpack message) -> putStrLn ("pass: reject " P.++ name)
  T.Left err -> error (name P.++ ": wrong failure " P.++ B.unpack (C.prettyError err))
  T.Right _ -> error (name P.++ ": unexpectedly accepted")
contains needle text = P.any (L.isPrefixOf needle) (L.tails text)
fails name body expected = announce name $ case run body of
  T.Left message | B.unpack message == expected -> putStrLn ("pass: " P.++ name)
  T.Left message -> error (name P.++ ": wrong failure " P.++ B.unpack message)
  _ -> error (name P.++ ": unexpectedly succeeded")
moduleSource name exports body = B.literal $ "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule " P.++ name P.++ exports P.++ " where\nimport MLF.Primitive\n" P.++ body P.++ "\n"
familySources = M.singleton "Family" (T.Pair "Family.hs" (moduleSource "Family" " (Choice(Only), makeOther)" "data Choice = Only | Other\nmakeOther = Other"))
familyCompile body = C.compileModules familySources "Example.hs" (source ("import qualified Family as F\n" P.++ body))
checkFamily name body expected = announce name $ case familyCompile body of
  T.Left err -> error (name P.++ ": " P.++ B.unpack (C.prettyError err))
  T.Right result -> case R.prepare P.False (C.compiledTerm result) of
    T.Left err -> error (B.unpack err)
    T.Right (T.Pair env _) -> case R.evaluate env (R.REnv M.empty) (X.erase (C.compiledTerm result)) of
      T.Right (R.RInteger actual) | actual == expected -> putStrLn ("pass: " P.++ name)
      _ -> error (name P.++ ": wrong result")
rejectFamily name body phase expected = announce name $ case familyCompile body of
  T.Left (T.CompileError actual message) | C.prettyPhase actual == C.prettyPhase phase P.&& contains expected (B.unpack message) -> putStrLn ("pass: reject " P.++ name)
  T.Left err -> error (name P.++ ": wrong failure " P.++ B.unpack (C.prettyError err))
  T.Right _ -> error (name P.++ ": unexpectedly accepted")
main :: IO ()
main = do
  HostIO.hSetBuffering HostIO.stdout HostIO.LineBuffering
  check "tuple does not need MonadFail" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { (x,y) <- Box (20,22); pure (x+y) })" 42
  check "unit does not need MonadFail" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { () <- Box (); pure 42 })" 42
  check "single constructor does not need MonadFail" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata One a = One a\nmain = unBox (do { One x <- Box (One 42); pure x })" 42
  rejectConstraint "list requires MonadFail" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { x:_ <- Box [42]; pure x })" "MonadFail"
  rejectConstraint "nested refutable requires MonadFail" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { (Just x,_) <- Box (Just 42,()); pure x })" "MonadFail"
  check "custom failure dispatch" "data Result a = Good a | Failed [Char]\ninstance Functor Result where { fmap f (Good x) = Good (f x); fmap _ (Failed e) = Failed e }\ninstance Applicative Result where { pure = Good; (<*>) (Good f) (Good x) = Good (f x); (<*>) (Failed e) _ = Failed e; (<*>) _ (Failed e) = Failed e }\ninstance Monad Result where { (>>=) (Good x) f = f x; (>>=) (Failed e) _ = Failed e }\ninstance MonadFail Result where { fail = Failed }\nmain = case (do { x:_ <- Good []; pure x }) of { Failed _ -> 42; Good x -> x }" 42
  check "success bypasses failure" "data Result a = Good a | Failed [Char]\ninstance Functor Result where { fmap f (Good x) = Good (f x); fmap _ (Failed e) = Failed e }\ninstance Applicative Result where { pure = Good; (<*>) (Good f) (Good x) = Good (f x); (<*>) (Failed e) _ = Failed e; (<*>) _ (Failed e) = Failed e }\ninstance Monad Result where { (>>=) (Good x) f = f x; (>>=) (Failed e) _ = Failed e }\ninstance MonadFail Result where { fail = Failed }\nmain = case (do { x:_ <- Good [42]; pure x }) of { Failed _ -> 0; Good x -> x }" 42
  check "string do failure" "data Result a = Good a | Failed [Char]\ninstance Functor Result where { fmap f (Good x) = Good (f x); fmap _ (Failed e) = Failed e }\ninstance Applicative Result where { pure = Good; (<*>) (Good f) (Good x) = Good (f x); (<*>) (Failed e) _ = Failed e; (<*>) _ (Failed e) = Failed e }\ninstance Monad Result where { (>>=) (Good x) f = f x; (>>=) (Failed e) _ = Failed e }\ninstance MonadFail Result where { fail = Failed }\nmain = case (do { \"a\" <- Good (\"b\" :: String); pure 0 }) of { Failed _ -> 42; Good x -> x }" 42
  check "lazy failed pattern unused" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { ~(Just x) <- Box Nothing; pure 42 })" 42
  fails "lazy pattern demanded" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { ~(Just x) <- Box Nothing; pure x })" "Irrefutable pattern failed"
  check "nested lazy boundary remains delayed" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { ~(Just x, ~(Just y)) <- Box (Just 1,Nothing); pure x })" 1
  fails "lazy whole matching checks strict sibling" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { ~(Just x,Just y) <- Box (Just 1,Nothing); pure x })" "Irrefutable pattern failed"
  check "as outside lazy permits original value" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { whole@(~(Just x)) <- Box Nothing; pure (case whole of { Nothing -> 42; Just _ -> 0 }) })" 42
  fails "as inside lazy waits for match" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\ndata Maybe a = Nothing | Just a\nmain = unBox (do { ~whole@(Just x) <- Box Nothing; pure (case whole of { Nothing -> 42; Just _ -> 0 }) })" "Irrefutable pattern failed"
  check "wildcard bind avoids demand" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { _ <- Box (panic \"unused\"); pure 42 })" 42
  fails "ordinary tuple bind demands scrutinee" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { (x,y) <- Box (panic \"tuple demanded\"); pure 42 })" "tuple demanded"
  checkFamily "hidden constructor retains wildcard fallback" "f F.Only 0 = 10\nf _ 1 = 42\nf _ _ = 0\nmain = f F.makeOther 1" 42
  rejectFamily "hidden constructor keeps do refutable" "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nunBox (Box x) = x\nmain = unBox (do { F.Only <- Box F.makeOther; pure 42 })" T.Resolution "MonadFail"
  rejectFamily "genuinely nonexhaustive qualified family rejected" "main = case F.makeOther of { F.Only -> 42 }" T.Inference "non-exhaustive case"
  check "prefix list constructor pattern" "head ((:) x xs) = x\nhead [] = 0\nmain = head ((:) 42 [])" 42
  check "prefix tuple constructor pattern" "fst ((,) x y) = x\nmain = fst ((,) 42 0)" 42
  check "prefix collection datatype fields" "data Holds = Holds ([] Int) ((,) Int Int)\nmain = case Holds [42] (1,2) of { Holds (x:_) _ -> x; Holds [] _ -> 0 }" 42
  rejectInference "zero-bind lazy constructor preserves nominal constraint" "data Maybe a = Nothing | Just a\nmain = case (42 :: Int) of { ~(Just _) -> 42 }" "type constructor mismatch"
  rejectInference "zero-bind lazy unit preserves nominal constraint" "main = case (42 :: Int) of { ~() -> 42 }" "type constructor mismatch"
  rejectConstraint "zero-bind lazy string still requires Eq" "data Key = Key\ninstance IsString Key where { fromString _ = Key }\nmain = case Key of { ~\"x\" -> 42 }" "Eq"
  check "zero-bind lazy failure is never demanded" "data Maybe a = Nothing | Just a\nmain = case (Nothing :: Maybe Int) of { ~(Just _) -> 42 }" 42
  check "zero-bind lazy scrutinee is never demanded" "data Maybe a = Nothing | Just a\nmain = case (panic \"unused\" :: Maybe Int) of { ~(Just _) -> 42 }" 42
  rejectInference "zero-bind lazy constructor arity is checked" "data Maybe a = Nothing | Just a\nmain = case (Nothing :: Maybe Int) of { ~(Just _ _) -> 42 }" "constructor pattern arity mismatch"
  rejectConstraint "unused as-binder lazy string still requires Eq" "data Key = Key\ninstance IsString Key where { fromString _ = Key }\nmain = case Key of { ~whole@\"x\" -> 42 }" "Eq"
  check "lazy string retains inferred constraints without demanding methods" "data Key = Key\ninstance IsString Key where { fromString _ = panic \"conversion not demanded\" }\ninstance Eq Key where { (==) _ _ = panic \"equality not demanded\" }\nf x = case x of { ~\"x\" -> 42 }\nmain = f Key" 42
  rejectConstraint "bound-unused field lazy string still requires Eq" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\nmain = case (Key 0,1) of { ~(\"x\",y) -> 42 }" "Eq"
  rejectConstraint "lazy string still requires IsString" "data Key = Key\ninstance Eq Key where { (==) _ _ = True }\nmain = case Key of { ~\"x\" -> 42 }" "IsString"
  check "lazy rank-polymorphic datatype field stays polymorphic" "data Poly = Poly (forall a. a -> a)\nmain = case Poly (\\x -> x) of { ~(Poly f) -> if f True then f 42 else 0 }" 42
  check "MLF polymorphic tuple payload remains generalizable" "main = case ((\\x -> x),1) of { ~(f,y) -> if f True then f 42 else 0 }" 42
  putStrLn "item4 patterned do: passed"
