module Main where
import qualified DemandScope as F
import qualified PrimitiveShadow as S
import qualified Comments as C
import qualified NegativeDouble as D
import qualified Bootstrap.Std as B
import qualified MLF.Primitive as P
import Control.Exception (SomeException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import System.Exit (exitFailure)
check name expected actual = do
  result <- try (evaluate actual) :: IO (Either SomeException Integer)
  case result of
    Right value | value == expected -> putStrLn ("PASS " ++ name ++ " = " ++ show value)
    _ -> putStrLn ("FAIL " ++ name ++ ": " ++ show result) >> exitFailure
main = do
  let poisonedTail = P.Cons "b" (error "tail")
      tests = [("poison-case",2,F.poisonCase poisonedTail),
        ("poison-equation",2,F.poisonEquation poisonedTail),
        ("poison-lambda",2,F.poisonLambda poisonedTail),
        ("first-row-demand",1,F.firstRowDemand (P.Cons (error "head") P.Nil)),
        ("fallback-alias",2,F.fallbackAlias poisonedTail),
        ("nested-outer",2,F.nestedOuter (P.Pair poisonedTail (error "unused outer field"))),
        ("outer-capture",42,F.outerCapture),
        ("function-capture",12,F.functionCapture),
        ("repeated-shadows",3,F.repeatedShadows),
        ("sequential-forward",7,F.sequentialForward),
        ("inner-binder",7,F.innerBinder),
        ("case-binder",8,F.caseBinder),
        ("do-shadow",42,F.doShadow),
        ("do-continuation",42,F.doContinuation),
        ("do-ignored-payload",42,F.doIgnoredPayload),
        ("closed-recursion",42,F.closedRecursion),
        ("mutual-recursion",42,F.mutualRecursion)]
  forM_ tests (\(name,expected,actual) -> check name expected actual)
  failure <- try (evaluate (F.poisonCase (P.Cons "a" (error "required-tail")))) :: IO (Either SomeException Integer)
  case failure of
    Left e | "required-tail" `isInfixOf` show e -> putStrLn "PASS required-tail-demand"
    _ -> putStrLn ("FAIL required-tail-demand: " ++ show failure) >> exitFailure
  check "shadow-string-equality" 2 S.shadowStringEquality
  check "shadow-int-equality" 2 S.shadowIntEquality
  unless (C.gapped == "text" && C.after == "-- still only data" && C.escaped == "quote: \" -- data") (putStrLn "FAIL comment/string preservation" >> exitFailure)
  putStrLn "PASS comment/string preservation"
  check "negative-zero-bits" 9223372036854775808 (P.doubleToBits D.negativeZero)
  check "negative-one-bits" 13830554455654793216 (P.doubleToBits D.negativeOne)
  check "negative-zero-roundtrip" 0 (P.doubleToBits (B.negateDouble D.negativeZero))
  check "renamed-negateInt" (-42) (B.negateInt 42)

  let unbox (F.Box value) = value
  check "standard-fmap" 42 (unbox (fmap (+1) (F.Box 41)))
  check "standard-pure" 42 (unbox (pure 42 :: F.Box Integer))
  check "standard-applicative" 42 (unbox (F.Box (+1) <*> F.Box 41))
  check "standard-return-default" 42 (unbox (return 42 :: F.Box Integer))
  check "standard-bind-compatibility" 42 (unbox (P.bind (F.Box 41) (\x -> F.Box (x+1))))
  check "standard-sequence-default-demand" 42 (unbox (F.Box (error "discarded payload") >> F.Box 42))
  check "standard-apply-function-payload-lazy" 42 (unbox (F.Box (const 42) <*> F.Box (error "unused argument")))
