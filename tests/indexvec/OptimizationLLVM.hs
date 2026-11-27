{-# LANGUAGE OverloadedStrings #-}
module OptimizationLLVM (run, main) where

import Control.Monad (forM_, unless)
import Data.List (find)
import qualified Data.Map.Lazy as Map
import qualified Data.Set as Set
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.LLVM.Optimize as O
import qualified Bootstrap.Map as M
import qualified Bootstrap.Primitive as P
import qualified Bootstrap.Set as S
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as H

check :: (Eq a, Show a) => String -> a -> a -> IO ()
check label expected actual = unless (expected == actual) $
  fail (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)

name :: H.Int -> T.XName
name i = T.XName i "same spelling"

var :: H.Int -> T.XErased
var = T.XEVar . name

prim :: T.Primitive -> [T.XErased] -> T.XErased
prim p = foldl T.XEApp (T.XEPrimitive p)

type Prefix = ([T.XName], Bool)

observe :: Prefix -> ([(H.Int, String)], Bool)
observe (names, complete) = (map (\(T.XName i hint) -> (i, H.unpack hint)) names, complete)

actual :: A.EntryDemand -> Prefix
actual d = (A.demandNames d, A.demandComplete d)

-- The simple list model deliberately retains the previous merge rule. Its
-- identity test does not use the production IntSet or demand representation.
merge :: Prefix -> Prefix -> Prefix
merge first@(names, complete) next
  | complete = (names ++ filter (\n -> O.nameId n `notElem` map O.nameId names) (fst next), snd next)
  | otherwise = first

barrier :: Prefix -> Prefix
barrier (names, _) = (names, False)

-- Independent host interpreter of the entry-prefix contract. All expression
-- forms go through it, including unknown calls, recursive lets and branches.
reference :: Map.Map H.Int A.WorkerFunction -> Map.Map H.Int Prefix -> T.XErased -> Prefix
reference fs local term = case term of
  T.XEVar n | Map.member (O.nameId n) fs -> ([], True)
            | otherwise -> Map.findWithDefault ([n], True) (O.nameId n) local
  T.XEAbs _ _ -> ([], True)
  T.XEInt _ -> ([], True)
  T.XEDouble _ -> ([], True)
  T.XEBool _ -> ([], True)
  T.XEString _ -> ([], True)
  T.XEPrimitive _ -> ([], True)
  T.XEConstructor _ -> ([], True)
  T.XEEvidenceHole _ -> ([], False)
  T.XELet n rhs body -> reference fs (Map.insert (O.nameId n) (go rhs) local) body
  T.XELetRec bindings body -> reference fs
    (foldr (\(n, _) -> Map.insert (O.nameId n) ([], False)) local bindings) body
  T.XECase subject [T.XErasedAlternative (T.XDefaultPattern binder) body] -> case binder of
    T.Nothing -> go body
    T.Just n -> reference fs (Map.insert (O.nameId n) (go subject) local) body
  T.XECase subject _ -> barrier (go subject)
  T.XEApp _ _ -> application term []
  where
    go = reference fs local
    application (T.XEApp f arg) args = application f (arg:args)
    application (T.XEPrimitive T.PIfThenElse) [condition, _, _] = barrier (go condition)
    application (T.XEPrimitive T.PSeq) [first, next] = merge (go first) (go next)
    application (T.XEPrimitive p) args
      | fromIntegral (length args) < P.primitiveArity p = ([], True)
      | fromIntegral (length args) /= P.primitiveArity p || not (P.primitiveStrict p) = ([], False)
      | otherwise = let prefix = foldr (merge . go) ([], True) args in
          if total p then prefix else barrier prefix
    application (T.XEConstructor _) _ = ([], True)
    application (T.XEVar n) args = case Map.lookup (O.nameId n) fs of
      Nothing -> barrier (go (T.XEVar n))
      Just worker
        | length args < length (A.parameters worker) -> ([], True)
        | length args /= length (A.parameters worker) -> ([], False)
        | otherwise -> foldr (merge . selected worker args)
            ([], A.demandComplete (A.entrySummary worker)) (A.entryOrder worker)
    application f _ = barrier (go f)
    selected worker args n = case find ((== O.nameId n) . O.nameId . fst) (zip (A.parameters worker) args) of
      Just (_, arg) -> go arg
      Nothing | O.nameId n `elem` map O.nameId (A.captures worker) -> go (T.XEVar n)
              | otherwise -> ([], False)
    total p = case p of
      T.PAddInt -> True
      T.PSubInt -> True
      T.PAndInt -> True
      T.PEqInt -> True
      T.PLtInt -> True
      _ -> False

mergeChecks :: IO ()
mergeChecks = do
  let a = T.XName 1 "first hint"
      b = T.XName 1 "second hint"
      leaves = [(xs, complete) | xs <- [[], [a], [b, name 2], [name 2, a, b],
                      [name minBound, name maxBound, name (-1), name 0]], complete <- [True, False]]
      demand (xs, complete) = A.EntryDemand xs complete
  forM_ [(x,y,z) | x <- leaves, y <- leaves, z <- leaves] $ \(x,y,z) -> do
    check "demand merge keeps order, hints, raw duplicates and barriers"
      (observe (merge (merge x y) z))
      (observe (actual (A.appendDemand (A.appendDemand (demand x) (demand y)) (demand z))))
    check "right-associated demand merge has the same ordered result"
      (observe (merge x (merge y z)))
      (observe (actual (A.appendDemand (demand x) (A.appendDemand (demand y) (demand z)))))
  check "an incomplete prefix never inspects the next summary"
    (observe ([a], False))
    (observe (actual (A.appendDemand (A.EntryDemand [a] False) (error "unreachable demand"))))
  check "the first demand does not inspect the following summary" [1]
    (take 1 (map O.nameId (A.demandNames (A.appendDemand (A.EntryDemand [a] True)
      (error "following summary is not needed for the first name")))))
  check "a later concatenation does not inspect summaries past its requested prefix" [1,2]
    (take 2 (map O.nameId (A.demandNames (A.appendDemand (A.EntryDemand [a] True)
      (A.appendDemand (A.EntryDemand [name 2] True) (error "past requested prefix"))))))
  check "a partial following leaf exposes its new name before its tail" [1,2]
    (take 2 (map O.nameId (A.demandNames (A.appendDemand (A.EntryDemand [a] True)
      (A.EntryDemand (name 2 : error "past following leaf prefix") True)))))
  forM_ [True, False] $ \complete ->
    check "an empty legacy prefix preserves the next completeness flag"
      (observe ([], complete))
      (observe (actual (A.appendDemand (A.EntryDemand [] True) (A.EntryDemand [] complete))))
  check "barrier preserves an indexed prefix and suppresses following work"
    (observe ([a, name 2], False))
    (observe (actual (A.appendDemand (A.barrierAfter (A.appendDemand
      (A.EntryDemand [a] True) (A.EntryDemand [b, name 2] True))) (error "past barrier"))))
  forM_ leaves $ \(xs, _) -> forM_ leaves $ \(ys, _) ->
    check "standalone appendNames retains the legacy identity rule"
      (observe (fst (merge (xs, True) (ys, True)), True))
      (observe (A.appendNames xs ys, True))

entryChecks :: IO ()
entryChecks = do
  let worker = A.WorkerFunction [name 7, name 8] (var 7) [name 2] S.empty
        (A.EntryDemand [name 8, name 2, name 7] False)
      completeWorker = A.WorkerFunction [name 7] (var 7) [] S.empty (A.EntryDemand [name 7] True)
      fs = M.fromList O.compareName [(name 99, worker), (name 100, completeWorker)]
      hostFs = Map.fromList [(99, worker), (100, completeWorker)]
      add a b = prim T.PAddInt [a,b]
      divide a b = prim T.PQuotInt [a,b]
      defaultCase n rhs body = T.XECase rhs [T.XErasedAlternative (T.XDefaultPattern n) body]
      atoms = [var 1, var 2, var 99, T.XEInt 0, T.XEDouble 1, T.XEBool True, T.XEString "text",
               T.XEPrimitive T.PSeq, T.XEConstructor "Pair", T.XEEvidenceHole 1, T.XEAbs (name 1) (var 2)]
      forms = atoms ++ concat
        [[add a b, divide a b, prim T.PSeq [a,b], prim T.PIfThenElse [a,b,var 4],
          T.XELet (name 1) a b, T.XELetRec [(name 1,a)] b,
          defaultCase T.Nothing a b, defaultCase (T.Just (name 1)) a b,
          T.XECase a [], T.XECase a [T.XErasedAlternative (T.XConstructorPattern "Pair" []) b],
          T.XEApp (var 11) a, T.XEApp a b, foldl T.XEApp (var 99) [a,b],
          T.XEApp (var 99) a, foldl T.XEApp (var 99) [a,b,var 4], T.XEApp (var 100) a,
          prim T.PAddInt [a], prim T.PAddInt [a,b,var 4], prim T.PIOReturn [a],
          T.XEApp (T.XEConstructor "Pair") a] | a <- atoms, b <- atoms]
      verify term = do
        check "general entry-demand agrees with the list contract"
          (observe (reference hostFs Map.empty term)) (observe (actual (A.entryDemand fs M.empty term)))
        verifySuffix term (A.letBodyDemands fs term)
      verifySuffix term (A.LetDemands demand rest) = do
        check "every cached lexical suffix agrees with the independent contract"
          (observe (reference hostFs Map.empty term)) (observe (actual demand))
        case (term,rest) of
          (T.XELet _ _ body,T.Just next) -> verifySuffix body next
          (T.XELet _ _ _,_) -> fail "cached let suffix is missing"
          (_,T.Nothing) -> pure ()
          _ -> fail "cached let suffix extends past the spine"
      wrappers term = [term, add term (var 4), add (var 4) term,
                       T.XELet (name 1) term (add (var 1) (add (var 2) (var 1))),
                       T.XELet (name 1) term (T.XELet (name 2) (var 1) (add (var 2) (var 1)))]
  mapM_ verify (concatMap wrappers forms)
  let ids d = map O.nameId (A.demandNames d)
      variables = map var [1..4096]
      balanced [] = T.XEInt 0
      balanced [x] = x
      balanced xs = let (left,right) = splitAt (length xs `div` 2) xs in add (balanced left) (balanced right)
  forM_ [balanced variables, foldl add (T.XEInt 0) variables, foldr add (T.XEInt 0) variables] $ \term ->
    check "large balanced and skewed demands retain source order" [1..4096] (ids (A.entryDemand M.empty M.empty term))
  -- Each alias has two references to the preceding summary. Expanding the
  -- summary as a plain tree would require 2^256 leaves for two final names.
  let depth = 256
      chain bind first = foldr (\i body -> bind (name (1000+i))
          (if i == 1 then first else add (var (999+i)) (var (999+i))) body)
        (var (1000+depth)) [1..depth]
      bindDefault n rhs body = defaultCase (T.Just n) rhs body
  forM_ [T.XELet, bindDefault] $ \bind -> do
    check "shared let and default-case alias summaries stay finite and ordered" [1,2]
      (ids (A.entryDemand M.empty M.empty (chain bind (add (var 1) (var 2)))))
    forM_ [(add (T.XEInt 1) (T.XEInt 2), True), (divide (T.XEInt 1) (T.XEInt 0), False)] $ \(first, complete) ->
      check "closed shared aliases retain empty prefixes without expanding the DAG"
        (observe ([], complete))
        (observe (actual (A.entryDemand M.empty M.empty (chain bind first))))

-- A deliberately unindexed capture fixed point: recompute every lexical
-- free set and every worker on every round. The oracle uses host Set/Map and
-- does not rely on captureIndexed, neededFree or the production worklist.
free :: T.XErased -> Set.Set H.Int
free term = case term of
  T.XEVar n -> Set.singleton (O.nameId n)
  T.XEAbs n body -> Set.delete (O.nameId n) (free body)
  T.XEApp f arg -> Set.union (free f) (free arg)
  T.XELet n rhs body -> Set.union (free rhs) (Set.delete (O.nameId n) (free body))
  T.XELetRec bindings body -> Set.difference (Set.unions (free body:map (free . snd) bindings))
    (Set.fromList (map (O.nameId . fst) bindings))
  T.XECase subject alternatives -> Set.unions (free subject:map arm alternatives)
  _ -> Set.empty
  where
    arm (T.XErasedAlternative pattern body) = Set.difference (free body) (Set.fromList (bound pattern))
    bound (T.XDefaultPattern n) = optional n
    bound (T.XConstructorPattern _ ns) = concatMap optional ns
    optional T.Nothing = []
    optional (T.Just n) = [O.nameId n]

captureReference :: [(T.XName, A.WorkerFunction)] -> Map.Map H.Int (Set.Set H.Int)
captureReference workers = fixed (Map.fromList [(O.nameId n, Set.fromList (map O.nameId (A.captures f))) | (n,f) <- workers])
  where
    fixed previous =
      let current = Map.fromList [(O.nameId n, Set.difference
            (Set.unions [Map.findWithDefault (Set.singleton v) v previous | v <- Set.toList (free (A.functionBody f))])
            (Set.fromList (map O.nameId (A.parameters f)))) | (n,f) <- workers]
      in if current == previous then current else fixed current

captureChecks :: IO ()
captureChecks = do
  let worker i args body = (name i, A.WorkerFunction (map name args) body []
          (S.singleton (name 555)) (A.EntryDemand [name 556] False))
      pair a b = T.XEApp a b
      fixtures =
        [[worker i [] (var (if i == 64 then 1000 else i+1)) | i <- [1..64]],
         [worker 1 [] (pair (var 2) (var 3)), worker 2 [] (var 4), worker 3 [] (var 4), worker 4 [] (var 1000)],
         [worker 1 [] (pair (var 2) (var 1000)), worker 2 [] (pair (var 3) (var 1001)), worker 3 [] (var 1)],
         [worker 1 [] (var 2), worker 2 [1000] (pair (var 1) (var 1000)), worker 3 [] (var 1001)],
         [worker 1 [10] (T.XELet (name 12) (var 11) (pair (var 12) (var 10))),
          worker 2 [] (T.XECase (var 1) [T.XErasedAlternative
            (T.XConstructorPattern "Pair" [T.Just (name 30),T.Nothing]) (pair (var 30) (var 31))])]]
  forM_ fixtures $ \workers -> do
    let result = A.captureFixed (M.fromList O.compareName workers)
        captured = Map.fromList [(O.nameId n, Set.fromList (map O.nameId (A.captures f))) | (n,f) <- M.toList result]
    check "capture worklist agrees with whole-table fixed point" (captureReference workers) captured
    forM_ workers $ \(n, original) -> case M.lookup O.compareName n result of
      T.Nothing -> fail "capture propagation lost a worker"
      T.Just updated -> do
        check "capture propagation retains parameters" (map O.nameId (A.parameters original)) (map O.nameId (A.parameters updated))
        check "capture propagation retains bodies" True (X.equalErased (A.functionBody original) (A.functionBody updated))
        check "capture propagation retains strict facts" (map O.nameId (S.toList (A.strict original))) (map O.nameId (S.toList (A.strict updated)))
        check "capture propagation retains entry order and completeness" (observe (actual (A.entrySummary original))) (observe (actual (A.entrySummary updated)))

-- Evaluate each body against the preceding host Map until the whole table
-- stops changing. Prefixes, strict sets and hints all come from the list
-- interpreter above, independently of the production propagation and index.
demandReference :: Map.Map H.Int A.WorkerFunction -> Map.Map H.Int A.WorkerFunction
demandReference previous =
  let step f =
        let allowed = map O.nameId (A.parameters f ++ A.captures f)
            (names,complete) = reference previous Map.empty (A.functionBody f)
            kept = filter ((`elem` allowed) . O.nameId) names
        in A.WorkerFunction (A.parameters f) (A.functionBody f) (A.captures f)
             (S.fromList O.compareName kept) (A.EntryDemand kept complete)
      key f = (map O.nameId (A.entryOrder f), A.demandComplete (A.entrySummary f))
      next = Map.map step previous
  in if Map.map key previous == Map.map key next then previous else demandReference next

demandFixedChecks :: IO ()
demandFixedChecks = do
  let worker i args body = (name i, A.WorkerFunction (map name args) body [] S.empty (A.EntryDemand [] False))
      call i = foldl T.XEApp (var i)
      chain n = [worker i [-i] (if i == n then var (-i) else call (i+1) [var (-i)]) | i <- [1..n]]
      -- g is bound inside the caller, so a free-variable index misses its edge.
      nested = T.XELet (name 2) (T.XEAbs (name 102) (var 102)) (call 2 [var 101])
      subject term = T.XECase term [T.XErasedAlternative (T.XDefaultPattern (T.Just (name 800))) (var 800)]
      cap hint = T.XName 900 hint
      seeded i body captured = (name i, A.WorkerFunction [name (-i)] body captured
                                 (S.singleton (name 555)) (A.EntryDemand [cap "old"] True))
      captures = [seeded 3 (T.XEVar (cap "new")) [cap "new"],
                  seeded 2 (call 3 [var (-2)]) [cap "outer"],
                  seeded 1 (call 2 [var (-1)]) [cap "outer"]]
      unused = error "worker demand forced an unused AST subtree"
      lazyWorkers =
        [worker 1 [101] (T.XELet (name 801) unused (var 101)),
         worker 2 [] (call 3 [unused]), worker 3 [301] (T.XEInt 0),
         worker 4 [] (prim T.PSeq [T.XEEvidenceHole 1,unused]),
         worker 5 [] (prim T.PIfThenElse [T.XEBool False,unused,unused]),
         worker 6 [] (T.XEApp (T.XEConstructor "Box") unused),
         worker 7 [] (prim T.PAddInt [unused]),
         worker 8 [] (T.XECase unused [T.XErasedAlternative (T.XDefaultPattern T.Nothing) (T.XEInt 0)]),
         worker 9 [] (call 9000 [unused])]
      fixtures =
        [[], chain 1, chain 48, lazyWorkers, [worker 1 [101] nested, worker 2 [102] (var 102)],
         [worker 1 [101,102] (T.XELet (name 801) (call 3 [var 101]) (call 2 [var 801, var 102])),
          worker 2 [201,202] (call 4 [var 202,var 201]),
          worker 3 [301] (subject (call 5 [var 301])),
          worker 4 [401,402] (prim T.PAddInt [var 401,var 402]), worker 5 [501] (var 501)],
         [worker 1 [101,102] (prim T.PSeq [var 101,call 2 [var 102,var 101]]),
          worker 2 [201,202] (prim T.PSeq [var 201,call 1 [var 202,var 201]])],
         [worker 1 [101] (call 2 [var 101]), worker 2 [201] (call 3 [var 201]),
          worker 3 [301] (T.XEInt 1), worker 4 [] (call 1 []),
          worker 5 [] (call 1 [T.XEInt 0,T.XEInt 0])],
         captures, captures ++ [(name (i+10), f) | (i, rhs) <- zip [1..5] [12,13,14,15,0],
           let (_,f) = worker (i+10) [-i] (if rhs == 0 then var (-i) else call rhs [var (-i)])]]
      facts f = (observe (actual (A.entrySummary f)), observe (S.toList (A.strict f), True))
  forM_ fixtures $ \workers -> do
    let expected = demandReference (Map.fromList [(O.nameId k, f) | (k, f) <- workers])
        result = M.toList (A.demandFixed (M.fromList O.compareName workers))
    check "demand worklist preserves each worker's ordered prefix, hints, completeness and strict set"
      (Map.toList (Map.map facts expected)) [(O.nameId k, facts f) | (k,f) <- result]

run :: IO ()
run = mergeChecks >> entryChecks >> captureChecks >> demandFixedChecks

main :: IO ()
main = run >> putStrLn "LLVM ordered demand and capture controls passed"
