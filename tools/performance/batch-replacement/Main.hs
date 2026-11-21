{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Monad (unless, forM_, when)
import System.Environment (getArgs)
import Data.List (sort, group)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.Data as D
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Compiler as Compiler
import qualified MLF.Host.Base as B
import qualified CandidateOptimize as C
import qualified LegacyOptimize as L
import qualified IOFixture as IOFixture

ensure :: String -> Bool -> IO ()
ensure label result = unless result (fail label)
n :: B.Int -> T.XName
n i = T.XName i "same-hint"
v :: B.Int -> T.XErased
v = T.XEVar . n
app :: T.XErased -> [T.XErased] -> T.XErased
app = foldl T.XEApp
pair :: T.XErased -> T.XErased -> T.XErased
pair a b = app (T.XEConstructor "(,)") [a,b]
p :: T.Primitive -> [T.XErased] -> T.XErased
p = app . T.XEPrimitive
ret :: T.XErased -> T.XErased
ret a = p T.PIOReturn [a]
bind :: T.XErased -> B.Int -> T.XErased -> T.XErased
bind action binder body = p T.PIOBind [action,T.XEAbs (n binder) body]
ident :: B.Int -> T.XErased
ident i = T.XEAbs (n i) (v i)
nameId :: T.XName -> B.Int
nameId (T.XName i _) = i
patternNames :: T.XPattern -> [T.XName]
patternNames (T.XDefaultPattern T.Nothing) = []
patternNames (T.XDefaultPattern (T.Just a)) = [a]
patternNames (T.XConstructorPattern _ xs) = [a | T.Just a <- xs]

-- Independent occurrence scan: no optimizer traversal, free/count helper or
-- cached child projection is used to derive this oracle.
freeIds :: T.XErased -> [B.Int]
freeIds term = case term of
 T.XEVar a -> [nameId a]
 T.XEAbs a b -> filter (/= nameId a) (freeIds b)
 T.XEApp a b -> freeIds a ++ freeIds b
 T.XELet a x b -> freeIds x ++ filter (/= nameId a) (freeIds b)
 T.XELetRec ds b -> filter (`notElem` map (nameId . fst) ds) (concatMap (freeIds . snd) ds ++ freeIds b)
 T.XECase a bs -> freeIds a ++ concat [filter (`notElem` map nameId (patternNames pat)) (freeIds b) | T.XErasedAlternative pat b <- bs]
 _ -> []
counts :: T.XErased -> [(B.Int,B.Int)]
counts term = [(head xs,fromIntegral (min 2 (length xs))) | xs <- group (sort (freeIds term))]
mapCounts :: T.Map T.XName B.Int -> [(B.Int,B.Int)]
mapCounts = sort . map (\(a,b) -> (nameId a,b)) . M.toList
names :: T.XErased -> [(B.Int,String)]
names term = case term of
 T.XEVar a -> [one a]
 T.XEAbs a b -> one a : names b
 T.XEApp a b -> names a ++ names b
 T.XELet a x b -> one a : names x ++ names b
 T.XELetRec ds b -> concat [one a : names x | (a,x) <- ds] ++ names b
 T.XECase a bs -> names a ++ concat [map one (patternNames pat) ++ names b | T.XErasedAlternative pat b <- bs]
 _ -> []
 where one (T.XName i hint) = (i,B.unpack hint)
exact :: T.XErased -> T.XErased -> Bool
exact a b = X.equalErased a b && names a == names b
auditTree :: C.UseTree -> IO ()
auditTree tree = do
 ensure "independently recomputed node counts" (mapCounts (C.useCounts tree) == counts (C.useTerm tree))
 mapM_ auditTree $ case C.useChildren tree of
  C.UseLeaf -> []
  C.UseAbs _ b -> [b]
  C.UseApp a b -> [a,b]
  C.UseLet _ a b -> [a,b]
  C.UseRec ds b -> map snd ds ++ [b]
  C.UseCase a bs -> a : map snd bs

checkTerm :: String -> T.XErased -> IO ()
checkTerm = checkTermParts True True

checkTermParts :: Bool -> Bool -> String -> T.XErased -> IO ()
checkTermParts checkExact checkCounts label term = do
 let seed = L.maxIdentity term + 1000
     (legacy,legacySeed) = L.runFresh (L.passRaw term) seed
     (owned,ownedSeed) = C.runFresh (C.passOwnedRaw term) seed
     (public,publicSeed) = C.runFresh (C.passRaw term) seed
 when checkExact $ do
  ensure (label ++ ": pass exact tree/hints/seed") (exact (L.useTerm legacy) (C.useTerm owned) && legacySeed == ownedSeed)
  ensure (label ++ ": public legacy pass unchanged") (exact (L.useTerm legacy) (C.useTerm public) && legacySeed == publicSeed)
 when checkCounts (auditTree owned)
 when checkExact $ do
  let (legacyWork,lseed) = L.runFresh (L.optimizeWork term) seed
      (ownedWork,cseed) = C.runFresh (C.optimizeOwnedWork term) seed
  ensure (label ++ ": optimizeWork exact tree/hints/seed") (exact legacyWork ownedWork && lseed == cseed)
  ensure (label ++ ": optimize exact tree/hints") (exact (L.optimize term) (C.optimizeOwned term))

-- All generated binders are globally distinct. Leaves deliberately reuse one
-- spelling with several identities; structural equality cannot hide capture.
generated :: [T.XErased]
generated = concat [family k | k <- [0..39]] where
 family k = let base = 100 + k*20
                f = n base
                rhs = ident (base+1)
                call = app (T.XEVar f) [T.XEInt k]
                wrapped body = T.XELet f rhs body
            in [ wrapped call
               , wrapped (pair call (v 9))
               , wrapped (T.XEAbs (n (base+2)) (pair call (v (base+2))))
               , wrapped (T.XELet (n (base+3)) (pair (v 8) call) (v (base+3)))
               , wrapped (T.XELetRec [(n (base+4),pair call (v (base+4)))] (v (base+4)))
               , wrapped (T.XECase (v 7) [T.XErasedAlternative (T.XConstructorPattern "Box" [T.Just (n (base+5))]) (pair call (v (base+5))),T.XErasedAlternative (T.XDefaultPattern T.Nothing) (v 8)])
               , wrapped (pair call call)
               , wrapped (app (T.XEVar f) [v 8])
               , wrapped (app (T.XEVar f) [v 8,T.XEInt k])
               , wrapped (pair (T.XEVar f) (v 8))
               ]

independentChain :: B.Int -> T.XErased
independentChain size = foldr make body [1..size] where
 make i = T.XELet (n i) (ident (10000+i))
 body = foldr pair (T.XEInt 0) [app (v i) [T.XEInt i] | i <- [1..size]]
dependencyChain :: B.Int -> T.XErased
dependencyChain size = foldr make (app (v size) [T.XEInt 0]) [1..size] where
 make i = T.XELet (n i) (T.XEAbs (n (10000+i))
             (if i == 1 then pair (v (10000+i)) (T.XEInt 0)
              else app (v (i-1)) [pair (v (10000+i)) (T.XEInt i)]))

polymorphicChain :: B.Int -> B.Int -> T.XErased
polymorphicChain size copies = foldr definition calls [1..size] where
 definition i body =
  let step = 10000 + i*2; arg = step+1
      previous = if i == 1 then v arg else app (v (i-1)) [v step,v arg]
  in T.XELet (n i) (T.XEAbs (n step) (T.XEAbs (n arg) (app (v step) [previous]))) body
 calls = foldr1 pair [app (v size) [ident (40000+i),T.XEInt i] | i <- [1..copies]]

iterator size callback input = foldr definition (app (v size) [callback,input]) [1..size] where
 definition i body = let step = 10000+i*2; arg = step+1
                         previous = if i == 1 then v arg else app (v (i-1)) [v step,v arg]
                     in T.XELet (n i) (T.XEAbs (n step) (T.XEAbs (n arg) (app (v step) [previous]))) body
lastBody (T.XELet _ _ body) = lastBody body
lastBody body = body

iterationChecks = do
 env <- case D.validateDeclarations [] of
  T.Right result -> pure result
  T.Left message -> fail (B.unpack message)
 let eval = R.evaluate env (R.REnv M.empty)
     integer value = case R.integer (eval value) of
      T.Right result -> pure result
      T.Left message -> fail (B.unpack message)
     boolean value = case R.boolean (eval value) of
      T.Right result -> pure result
      T.Left message -> fail (B.unpack message)
     translate op amount = T.XEAbs (n 40000) (p op [v 40000,T.XEInt amount])
 forM_ [1,2,3,17] $ \count -> forM_ [minBound,maxBound,-3,0,1] $ \amount ->
  forM_ [minBound,maxBound,-1,0,7] $ \input -> forM_ [T.PAddInt,T.PSubInt] $ \op -> do
   let callback = translate op amount
       original = iterator count callback (T.XEInt input)
       folded = C.simplifyIterations M.empty original
       operation = case op of T.PAddInt -> (+); _ -> (-)
       expected = foldl operation input (replicate (fromIntegral count) amount)
   a <- integer original; b <- integer folded; c <- integer (C.optimizeChecked original)
   ensure "iteration arithmetic agrees with repeated wrapped operations" (a == expected && b == expected && c == expected)
   ensure "iteration reduction is actually exercised" (not (exact (lastBody original) (lastBody folded)))
 forM_ [1,2,3,16,129] $ \count -> forM_ [False,True] $ \input -> do
  let callback = T.XEAbs (n 40000) (p T.PIfThenElse [v 40000,T.XEBool False,T.XEBool True])
      original = iterator count callback (T.XEBool input)
      expected = iterate not input !! fromIntegral count
  a <- boolean original; b <- boolean (C.optimizeChecked original)
  ensure "iteration Boolean parity" (a == expected && b == expected)
 let unsupported = [ident 40000,
       T.XEAbs (n 40000) (p T.PQuotInt [v 40000,T.XEInt 2]),
       T.XEAbs (n 40000) (p T.PAddInt [v 40001,T.XEInt 1]),
       T.XEAbs (n 40000) (p T.PNewIntArray [T.XEInt 1,v 40000])]
 forM_ unsupported $ \callback -> do
  let term = iterator 3 callback (T.XEInt 7)
  ensure "unknown, captured and effectful callbacks retain ordinary code" (exact term (C.simplifyIterations M.empty term))
 let summary = M.singleton (n 1) 3
     call = app (v 1) [translate T.PAddInt 1,T.XEInt 7]
     shadowed = [T.XEAbs (n 1) call,T.XELet (n 1) (v 9000) call,
                 T.XELetRec [(n 1,v 9000)] call,
                 T.XECase (v 9000) [T.XErasedAlternative (T.XDefaultPattern (T.Just (n 1))) call]]
 forM_ shadowed $ \term -> ensure "every binding form masks iterator identities"
   (exact term (C.simplifyIterations summary term))
 let over = app (v 2) [app (v 1) [v 2,v 3]]
 case C.iterationBody (M.singleton (n 1) 2147483647) (n 2) (n 3) over of
  T.Nothing -> pure ()
  _ -> fail "iteration count overflow was admitted"
 let poison = iterator 3 (translate T.PAddInt 1) (p T.PPanic [T.XEString "iteration input"])
 forM_ [poison,C.optimizeChecked poison] $ \term -> case R.integer (eval term) of
  T.Left message -> ensure "iteration retains input failure" (message == "iteration input")
  _ -> fail "iteration erased a demanded input failure"
 let lazy = p T.PIfThenElse [T.XEBool False,poison,T.XEInt 42]
 result <- integer (C.optimizeChecked lazy)
 ensure "iteration retains undemanded branch laziness" (result == 42)
 putStrLn "PASS checked-iteration-algebra-and-scopes"

checkPending :: B.Int -> T.XErased -> IO ()
checkPending expected term = do
 let seed = 50000
     (pending,after) = C.runFresh (C.passPendingRaw term) seed
     (legacy,legacyAfter) = L.runFresh (L.passRaw term) seed
     materialized = C.materializePending pending
     C.PendingBody _ replacements _ _ = pending
 ensure "long contiguous chain must accumulate delayed replacements" (M.size replacements == expected)
 ensure "pending materialization exact tree/hints/seed" (exact (C.useTerm materialized) (L.useTerm legacy) && after == legacyAfter)
 ensure "effective pending counts independently recomputed" (mapCounts (C.pendingCounts pending) == counts (C.useTerm materialized))
 auditTree materialized
 forM_ (S.toList (C.pendingCalls pending)) $ \target ->
  forM_ [1..4] $ \arity -> case L.commonCalls target arity (L.useCounts legacy) legacy of
   L.DifferentCalls -> pure ()
   _ -> fail "effective pending witness did not imply legacy DifferentCalls"

witnessChecks :: Bool -> Bool -> IO ()
witnessChecks implication nonvacuity = do
 let target = n 1
     direct = app (v 1) [T.XEInt 0]
     cases = [direct,app direct [v 2],app direct [T.XEInt 3],app (v 1) [v 2,T.XEInt 3],
              pair direct (app (v 1) [v 2]),pair (v 1) direct,
              T.XEAbs target direct,T.XELet target direct direct,
              T.XELet target (T.XEInt 0) direct,
              T.XELetRec [(target,direct)] direct,
              T.XECase direct [T.XErasedAlternative (T.XDefaultPattern (T.Just target)) direct],
              T.XECase (v 2) [T.XErasedAlternative (T.XConstructorPattern "Box" [T.Just target]) direct]]
     trees = cases ++ generated
 when implication $ do
  forM_ trees $ \term -> do
   let owned = C.indexUses term
       legacy = L.indexUses term
   forM_ (S.toList (C.negativeCalls owned)) $ \name ->
    forM_ [1..5] $ \arity -> case L.commonCalls name arity (L.useCounts legacy) legacy of
     L.DifferentCalls -> pure ()
     _ -> fail "negative witness implication"
 when nonvacuity $ do
  ensure "positive direct witness required" (S.member C.compareName target (C.negativeCalls (C.indexUses direct)))
  ensure "later-only nonvariable remains conservative" (not (S.member C.compareName target (C.negativeCalls (C.indexUses (app (v 1) [v 2,T.XEInt 3])))))
  ensure "lambda witness masking" (S.null (C.negativeCalls (C.indexUses (T.XEAbs target direct))))
  ensure "let witness masking" (S.null (C.negativeCalls (C.indexUses (T.XELet target (T.XEInt 0) direct))))
  ensure "recursive witness masking" (S.null (C.negativeCalls (C.indexUses (T.XELetRec [(target,direct)] direct))))
  let success = L.indexUses (app (v 1) [v 2])
  case L.commonCalls target 1 (L.useCounts success) success of
   L.CommonCalls _ -> pure ()
   _ -> fail "inverted witness mutation control requires actual legacy success"

rawLaziness :: IO ()
rawLaziness = do
 let target = n 20
     absentC = C.UseTree (error "candidate absent term") M.empty (error "candidate absent children")
     absentL = L.UseTree (error "legacy absent term") M.empty (error "legacy absent children")
     (ct,cs) = C.runFresh (C.substituteUsed target (error "candidate absent value") absentC) 17
     (lt,ls) = L.runFresh (L.substituteUsed target (error "legacy absent value") absentL) 17
 ensure "raw absent substitute is non-demanding" (M.null (C.useCounts ct) && M.null (L.useCounts lt) && cs == 17 && ls == 17)
 case (C.commonCalls target 1 M.empty absentC,L.commonCalls target 1 M.empty absentL) of
  (C.NoCommonCalls,L.NoCommonCalls) -> pure ()
  _ -> fail "raw absent common call"
 let poisonC = C.UseTree (error "candidate poisoned argument") (M.singleton (n 21) 1) (error "candidate poisoned children")
     poisonL = L.UseTree (error "legacy poisoned argument") (M.singleton (n 21) 1) (error "legacy poisoned children")
     chead = C.indexUses (T.XEVar target)
     lhead = L.indexUses (T.XEVar target)
     ccases = [C.useApp chead poisonC,C.useApp (C.useApp chead (C.indexUses (T.XEInt 0))) poisonC,
               C.useLet (n 22) chead (C.UseTree (error "late candidate term") (M.singleton target 1) (error "late candidate children"))]
     lcases = [L.useApp lhead poisonL,L.useApp (L.useApp lhead (L.indexUses (T.XEInt 0))) poisonL,
               L.useLet (n 22) lhead (L.UseTree (error "late legacy term") (M.singleton target 1) (error "late legacy children"))]
 forM_ (zip ccases lcases) $ \(c,l) ->
  case (C.commonCalls target 2 M.empty c,L.commonCalls target 2 M.empty l) of
   (C.DifferentCalls,L.DifferentCalls) -> pure ()
   _ -> fail "raw common-call short-circuit demand changed"

ioSemantics :: IO ()
ioSemantics = do
 env <- case D.validateDeclarations [] of
  T.Right result -> pure result
  T.Left message -> fail (B.unpack message)
 let plusOne = T.XEAbs (n 1) (p T.PAddInt [v 1,T.XEInt 1])
     repeated = p T.PAddInt [app (v 0) [v 10],app (v 0) [v 10]]
     wrap initial value body = T.XELet (n 10) initial (T.XELet (n 0) value body)
     unused = wrap (p T.PPanic [T.XEString "unused argument"]) plusOne
                 (p T.PIfThenElse [T.XEBool False,ret repeated,ret (T.XEInt 0)])
     failure = wrap (p T.PPanic [T.XEString "late argument"]) plusOne
                 (bind (p T.PPanic [T.XEString "first failure"]) 20 (ret repeated))
     arrays = wrap (T.XEInt 0) (T.XEAbs (n 1) (p T.PNewIntArray [T.XEInt 1,v 1]))
                (bind (app (v 0) [v 10]) 20 (bind (app (v 0) [v 10]) 21
                  (bind (p T.PWriteIntArray [v 20,T.XEInt 0,T.XEInt 42]) 22 (p T.PReadIntArray [v 21,T.XEInt 0]))))
     -- This pair of eligible bindings forces the owned delayed route in a
     -- branch whose panic must remain unobserved. The interpreter returns 0.
     admitted = T.XELet (n 31) (ident 41) (T.XELet (n 32) (ident 42)
                  (p T.PIfThenElse [T.XEBool False,ret (p T.PAddInt [app (v 31) [p T.PPanic [T.XEString "hidden"]],app (v 32) [T.XEInt 7]]),ret (T.XEInt 0)]))
 checkPending 2 admitted
 forM_ [(unused,Nothing),(failure,Just "first failure"),(arrays,Nothing),(admitted,Nothing)] $ \(term,wanted) -> do
  checkTerm "IO exact" term
  forM_ [term,fst (C.runFresh (C.passOwned term) 1000),C.optimizeOwned term] $ \variant -> do
   result <- R.runAction [] env (R.evaluate env (R.REnv M.empty) variant)
   case (result,wanted) of
    (T.Left actual,Just expected) -> ensure "IO exact failure order" (B.unpack actual == expected)
    (T.Right value,Nothing) -> case R.integer value of
     T.Right 0 -> pure ()
     _ -> fail "IO value or fresh execution changed"
    _ -> fail "IO outcome changed"

main :: IO ()
main = do
 selected <- getArgs
 let wanted label = null selected || label `elem` selected
     announce label = when (wanted label) (putStrLn ("PASS " ++ label))
     check label action = when (wanted label) (action >> announce label)
     exactLabel = "exact-pass-optimize-seeds"
     countsLabel = "independent-counts"
     implication = "witness-implication"
     nonvacuity = "witness-nonvacuity"
     term = checkTermParts (wanted exactLabel) (wanted countsLabel)
 check "checked-iteration-algebra-and-scopes" iterationChecks
 when (wanted exactLabel || wanted countsLabel) $ do
  forM_ (zip [0::Int ..] generated) $ \(i,t) -> term ("generated " ++ show i) t
  -- The authored input is shared; the frozen baseline remains the oracle.
  forM_ IOFixture.cases $ \(IOFixture.Case label body _ _) ->
   case Compiler.compile (B.literal (label ++ ".hs")) (IOFixture.source body) of
    T.Left err -> fail (B.unpack (Compiler.prettyError err))
    T.Right result -> term ("authored IO " ++ label) (X.erase (Compiler.compiledTerm result))
  announce exactLabel
  announce countsLabel
 when (wanted implication || wanted nonvacuity) $ do
  witnessChecks (wanted implication) (wanted nonvacuity)
  announce implication
  announce nonvacuity
 check "long-chain-admission" $ do
  forM_ [2,16,128] $ \size -> do
   checkPending size (independentChain size)
   checkPending size (dependencyChain size)
   checkTerm "independent chain" (independentChain size)
   checkTerm "dependent chain" (dependencyChain size)
 check "pending-materialization" $ do
  forM_ [2,3] $ \copies -> forM_ [2,16,128] $ \size -> do
   checkPending size (polymorphicChain size copies)
   checkTerm "polymorphic dependent chain with several instantiations" (polymorphicChain size copies)
  forM_ [4,7] $ \copies -> checkTerm "bounded multiple-copy fallback" (polymorphicChain 16 copies)
 check "fresh-order" $ do
  let ordered = T.XELet (n 1) (ident 11) (T.XELet (n 2) (ident 12)
                   (pair (app (v 1) [T.XEInt 1]) (app (v 2) [T.XEInt 2])))
      (out,after) = C.runFresh (C.passOwned ordered) 100
      expected = pair (app (ident 101) [T.XEInt 1]) (app (ident 100) [T.XEInt 2])
      nativeHints t = case t of
       T.XEAbs a b -> let T.XName i _ = a in T.XEAbs (T.XName i "native") (case b of T.XEVar _ -> T.XEVar (T.XName i "native"); _ -> b)
       T.XEApp a b -> T.XEApp (nativeHints a) (nativeHints b)
       _ -> t
  ensure "inner-before-outer explicit Fresh order" (exact out (nativeHints expected) && after == 102)
 check "unsupported-contexts" $ do
  let large = T.XEAbs (n 40) (foldr pair (v 40) (replicate 50 (v 9)))
      sparse rhs body = T.XELet (n 1) (ident 11) (T.XELet (n 2) rhs (T.XELet (n 3) (ident 13)
                       (pair (app (v 1) [T.XEInt 0]) (pair body (app (v 3) [T.XEInt 0])))))
  forM_ [sparse (ident 12) (pair (app (v 2) [T.XEInt 0]) (app (v 2) [T.XEInt 1])),
         sparse large (app (v 2) [T.XEInt 0]),
         sparse (p T.PAddInt [T.XEInt 1,T.XEInt 2]) (v 2)] (checkTerm "sparse unsupported flush")
 check "common-call-success-fallback" $ do
  let common = T.XELet (n 1) (T.XEAbs (n 11) (pair (v 11) (v 9))) (pair (app (v 1) [v 8]) (app (v 1) [v 8]))
  checkTerm "common success fallback" common
  let (cp,_) = C.runFresh (C.passPendingRaw common) 100
      C.PendingBody _ replacements _ _ = cp
  ensure "common success uses unchanged immediate specialization" (M.null replacements)
  case C.useTerm (C.materializePending cp) of
   T.XELet _ _ _ -> pure ()
   _ -> fail "common success lost lazy let"
 check "public-raw-laziness" $ do
  rawLaziness
 check "io-lazy-semantics" $ do
  ioSemantics
