{-# OPTIONS_GHC -O0 #-}
module Tests (main) where
import Prelude
import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless)
import Data.Char (chr, ord)
import GHC.Conc (pseq)
import System.Timeout (timeout)
import qualified MLF.Host.Base as Base (HostError(..), literal)
import qualified MLF.Primitive as P
import qualified Oracle as O
import qualified Probe

type Step = Integer -> Integer -> Integer
type Route = (String, Integer, Integer, Step)
mA, mB :: Integer
mA = 2147483647
mB = 2147483629
routes :: [Route]
routes = [("stepA",65599,mA,Probe.stepA), ("namedA",65599,mA,Probe.namedA),
          ("stepB",131,mB,Probe.stepB), ("namedB",131,mB,Probe.namedB),
          ("unmatchedMultiplier",65598,mA,Probe.unmatchedMultiplier),
          ("unmatchedModulus",65599,2147483646,Probe.unmatchedModulus)]

assert :: String -> Bool -> IO ()
assert label condition = unless condition (errorWithoutStackTrace ("FAIL " ++ label))
pass :: String -> IO ()
pass label = putStrLn ("PASS " ++ label)
panic :: String -> a
panic = P.panic . Base.literal

-- Catch ONLY the public MLF HostError. Other failures, including a timeout's
-- private asynchronous exception, must propagate rather than look like a pass.
observe :: Integer -> IO (Either Base.HostError Integer)
observe value = try (evaluate value)
expectHost :: String -> String -> Integer -> IO ()
expectHost label wanted value = do
  result <- timeout 2000000 (observe value)
  case result of
    Just (Left (Base.HostError message)) -> assert (label ++ ": exact HostError") (message == wanted)
    Just (Right _) -> assert (label ++ ": unexpectedly returned") False
    Nothing -> assert (label ++ ": unexpected timeout") False
expectTimeout :: String -> Integer -> IO ()
expectTimeout label value = do
  result <- timeout 250000 (observe value)
  case result of
    Nothing -> pure ()
    Just (Left (Base.HostError message)) ->
      errorWithoutStackTrace ("FAIL " ++ label ++ ": wrong HostError " ++ show message)
    Just (Right _) -> assert (label ++ ": unexpectedly returned") False

-- Allocating, non-cyclic pure divergence, so the bounded observation can receive
-- an async timeout; do not use a black-holed CAF that raises NonTermination.
{-# NOINLINE diverge #-}
diverge :: Integer -> Integer
diverge n = n `pseq` diverge (n + 1)

states :: [Integer]
states = [-(2^1024),-(2^128),-(2^63)-1,-(2^63),-(2^63)+1,
          -(mA+1),-mA,-(mA-1),-(mB+1),-mB,-(mB-1),-2,-1,0,1,2,
          mB-1,mB,mB+1,mA-1,mA,mA+1,2^63-1,2^63,2^63+1,2^128,2^1024]
codes :: [Integer]
codes = [-(2^1024),-(2^128),-(2^63)-1,-(2^63),-1,0,1,
         0x7f,0x80,0x7ff,0x800,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,
         0xe000,0xffff,0x10000,0x10ffff,0x110000,2^63-1,2^63,2^128,2^1024]

-- Fixed arithmetic generator: no host RNG and no candidate operation supplies
-- any input or expected result. Ten state modes x ten code modes repeat 25 times.
corpus :: [(Integer,Integer)]
corpus = take 2500 (go 0 1729)
  where
    next x = (1103515245*x + 12345) `rem` 2147483648
    go index seed =
      let z = next seed; w = next z
          ss = [z `rem` mA,negate (z `rem` mA),mA+z,2^63+z,-(2^63)-z,
                2^128+z,-(2^128)-z,2^1024+z,-(2^1024)-z,z `rem` mB]
          cs = [w `rem` 0x110000,negate (w `rem` 0x110000),w,2^128+w,-(2^128)-w,
                2^1024+w,-(2^1024)-w,0xd800+w `rem` 0x800,0x110000+w,0]
      in (ss !! (index `rem` 10),cs !! ((index `quot` 10) `rem` 10)) : go (index+1) w

checkPairs :: String -> [(Integer,Integer)] -> IO ()
checkPairs group pairs = forM_ routes $ \(name,k,m,actual) ->
  forM_ (zip [0::Int ..] pairs) $ \(i,(state,code)) -> do
    expected <- evaluate (O.step k m state code)
    observed <- evaluate (actual state code)
    assert (group ++ "/" ++ name ++ "/" ++ show i) (observed == expected)

finiteValues :: IO ()
finiteValues = do
  assert "boundary inventory" (length states == 27 && length codes == 25)
  checkPairs "boundary" [(state,code) | state <- states, code <- codes]
  pass "fingerprint 675 boundary pairs x 6 public Probe routes"
  assert "deterministic corpus inventory" (length corpus == 2500)
  checkPairs "corpus" corpus
  pass "fingerprint 2500 deterministic pairs x 6 public Probe routes"
  forM_ routes $ \(name,k,m,actual) -> do
    assert (name ++ ": literal negative state remainder") (actual (-1) 0 == negate k)
    assert (name ++ ": literal negative code remainder") (actual 0 (-1) == -1)
    assert (name ++ ": not mathematical mod") (actual (-1) 0 /= m-k)
  assert "literal A multiplier" (Probe.stepA 1 0 == 65599 && Probe.namedA 1 0 == 65599)
  assert "literal B multiplier" (Probe.stepB 1 0 == 131 && Probe.namedB 1 0 == 131)
  assert "unmatched multiplier remains distinct" (Probe.unmatchedMultiplier 1 0 == 65598)
  assert "unmatched modulus remains distinct" (Probe.unmatchedModulus 0 (mA-1) == 0 &&
                                               Probe.stepA 0 (mA-1) == mA-1)
  pass "fingerprint signed rem and literal cross-rule nonmatching constants"

-- Invalid text scalars are NOT converted to MLF text. Host Char deliberately
-- admits surrogates; code arithmetic is not Unicode/text validation.
streams :: [(String,[Integer])]
streams = [("ascii",map (toInteger . ord) "mlf-crates: fingerprint 0/1"),
           ("unicode-scalars",[0,65,0x7f,0x80,0x7ff,0x800,0xd7ff,0xe000,0xffff,0x10000,0x10ffff]),
           ("host-surrogate-codes",[0xd800,0xdbff,0xdc00,0xdfff]),
           ("noncanonical-integers",[-(2^1024),-(2^128),-1,0,0x110000,2^128,2^1024]),
           ("deterministic-512",take 512 (map (\x -> x `rem` 0x110001)
                                      (iterate (\x -> (1664525*x+1013904223) `rem` (2^32)) 12345)))]
streamStates :: [Integer]
streamStates = [-(2^128),-1,0,1,mA-1,mA,mB-1,mB,2^128]
checkStreams :: IO ()
checkStreams = do
  assert "stream inventory" (length streams == 5 && length streamStates == 9)
  forM_ [0,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,0x10ffff] $ \code -> do
    assert "host Char code agrees with literal integer" (P.charCode (chr (fromInteger code)) == code)
    assert "public Char roundtrip agrees with literal integer" (P.charCode (P.charFromCode code) == code)
  forM_ routes $ \(name,k,m,actual) -> forM_ streams $ \(streamName,values) ->
    forM_ streamStates $ \initial -> do
      let expected = O.checksum k m initial values
          observed = scanl actual initial values
      assert ("every checksum prefix/" ++ name ++ "/" ++ streamName ++ "/" ++ show initial)
             (observed == expected)
  pass "fingerprint 270 checksum streams every prefix and host Char code boundaries"

allDemandRoutes :: [(String,Step)]
allDemandRoutes = concatMap (\(name,k,m,actual) -> [(name,actual),("oracle/"++name,O.step k m)]) routes
checkPanics :: IO ()
checkPanics = do
  forM_ allDemandRoutes $ \(name,actual) -> do
    expectHost (name ++ "/state-before-code") "state-first" (actual (panic "state-first") (panic "code-second"))
    expectHost (name ++ "/canonical-code") "code-second" (actual 0 (panic "code-second"))
    expectHost (name ++ "/negative-state-code") "code-second" (actual (-1) (panic "code-second"))
    expectHost (name ++ "/huge-positive-state-code") "code-second" (actual (2^1024) (panic "code-second"))
    expectHost (name ++ "/huge-negative-state-code") "code-second" (actual (-(2^1024)) (panic "code-second"))
  pass "fingerprint 60 exact HostError priority and noncanonical fallback probes"

checkPartial :: IO ()
checkPartial = do
  let primitiveAliases = [("addInt",P.addInt),("operator+",(P.+)),("mulInt",P.mulInt),
                         ("operator*",(P.*)),("remInt",P.remInt),("operator%",(P.%))]
      functions = allDemandRoutes ++ primitiveAliases
  assert "partial-application inventory" (length functions == 18)
  forM_ functions $ \(name,actual) -> do
    observed <- timeout 2000000 (try (evaluate (actual (panic "partial-state"))) ::
                                IO (Either Base.HostError (Integer -> Integer)))
    case observed of
      Just (Right _) -> pure ()
      _ -> assert (name ++ ": partial application must not demand state") False
    expectHost (name ++ "/applied-partial") "partial-state" (actual (panic "partial-state") 0)
  pass "fingerprint 18 partial applications lazy until second operand"

checkOrdinaryDivision :: IO ()
checkOrdinaryDivision = do
  let operations = [("remInt",P.remInt,O.remInt),("operator%",(P.%),O.remInt),
                    ("quotInt",P.quotInt,O.quotInt),("operator/",(P./),O.quotInt)]
      numerators = [-(2^128),-7,-1,0,1,7,2^128]
      divisors = [-mA,-mB,-7,-1,1,7,mA,mB]
  forM_ operations $ \(name,actual,expected) -> do
    forM_ numerators $ \n -> forM_ divisors $ \d ->
      assert (name ++ ": ordinary signed division/remainder") (actual n d == expected n d)
    forM_ [("candidate",actual),("oracle",expected)] $ \(side,op) -> do
      expectHost (name ++ side ++ "/zero") "integer division by zero" (op 7 0)
      expectHost (name ++ side ++ "/negative-zero") "integer division by zero" (op (-7) 0)
      expectHost (name ++ side ++ "/numerator-before-zero") "numerator-first" (op (panic "numerator-first") 0)
      expectHost (name ++ side ++ "/both-panic") "numerator-first"
                 (op (panic "numerator-first") (panic "divisor-second"))
      expectHost (name ++ side ++ "/divisor-panic") "divisor-second" (op (2^1024) (panic "divisor-second"))
  pass "fingerprint 224 ordinary signed divisions and 40 exact zero-divisor demand probes"

checkDivergence :: IO ()
checkDivergence = do
  forM_ (zip [1::Integer ..] allDemandRoutes) $ \(i,(name,actual)) ->
    expectTimeout (name ++ "/state-diverges-before-code-panic")
                  (actual (diverge (i*10)) (panic "code-second"))
  pass "TIMEOUT fingerprint 12 state-divergence before code-panic observations"
  forM_ (zip [1::Integer ..] allDemandRoutes) $ \(i,(name,actual)) ->
    expectHost (name ++ "/state-panic-before-code-diverges") "state-first"
               (actual (panic "state-first") (diverge (i*10+1)))
  pass "TIMEOUT fingerprint 12 state-panic wins before code-divergence observations"
  forM_ (zip [1::Integer ..] allDemandRoutes) $ \(i,(name,actual)) ->
    expectTimeout (name ++ "/canonical-code-diverges") (actual 0 (diverge (i*10+2)))
  pass "TIMEOUT fingerprint 12 canonical-state code-divergence observations"
  forM_ (zip [1::Integer ..] allDemandRoutes) $ \(i,(name,actual)) ->
    expectTimeout (name ++ "/noncanonical-code-diverges") (actual (2^1024) (diverge (i*10+3)))
  pass "TIMEOUT fingerprint 12 noncanonical-state code-divergence observations"

main :: IO ()
main = do
  finiteValues
  checkStreams
  checkPanics
  checkPartial
  checkOrdinaryDivision
  checkDivergence
  pass "fingerprint finite independent controls complete; no universal equivalence or speed claim"
