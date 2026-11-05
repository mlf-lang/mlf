-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Result where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.Optimize as O;
  -- A descriptor is (constructor name, (actual runtime tag, field count)).
  -- Fields remain LAZY pointers. No demand or canonical-pointer fact is added.
  data ResultInfo = ResultInfo ([] ((,) String ((,) Int Int))) ([] XName);
  data ReturnSummary = ReturnSummary (Map String ((,) Int Int)) (Set XName);
  data ReturnGraph = ReturnGraph (Map XName ReturnSummary) (Map String ((,) Int Int));
  alternatives :: ResultInfo -> [] ((,) String ((,) Int Int));
  alternatives (ResultInfo constructors names) = constructors;
  workers :: ResultInfo -> [] XName;
  workers (ResultInfo constructors names) = names;
  memberWorker :: ResultInfo -> XName -> Bool;
  memberWorker info name = L.any (O.eqName name) (workers info);
  descriptor :: ResultInfo -> String -> Maybe ((,) Int Int);
  descriptor info name = descriptorIn name (alternatives info);
  descriptorIn :: String -> [] ((,) String ((,) Int Int)) -> Maybe ((,) Int Int);
  descriptorIn name entries = case entries of {
    [] -> Nothing;
    (:) ((,) key value) rest -> if eqString name key then Just value else descriptorIn name rest
  };
  relevantSum :: ResultInfo -> Bool;
  relevantSum info = case alternatives info of {
    (:) ((,) first ((,) firstTag firstArity)) ((:) ((,) second ((,) secondTag secondArity)) []) ->
      ((firstTag /= secondTag) &&
       (((firstArity == 0) && (secondArity == 1)) ||
        ((firstArity == 1) && (secondArity == 0))));
    _ -> False
  };
  summaryConstructors :: ReturnSummary -> Map String ((,) Int Int);
  summaryConstructors (ReturnSummary constructors calls) = constructors;
  summaryCalls :: ReturnSummary -> Set XName;
  summaryCalls (ReturnSummary constructors calls) = calls;
  distinctTags :: Map String ((,) Int Int) -> Bool;
  distinctTags constructors = case M.toList constructors of {
    [] -> True;
    (:) first [] -> True;
    (:) ((,) first ((,) firstTag firstArity)) ((:) ((,) second ((,) secondTag secondArity)) []) ->
      (firstTag /= secondTag);
    _ -> False
  };
  mergeSummary :: ReturnSummary -> ReturnSummary -> Maybe ReturnSummary;
  mergeSummary left right =
    let { constructors = M.union compareString (summaryConstructors left) (summaryConstructors right);
          calls = S.union O.compareName (summaryCalls left) (summaryCalls right)
        } in
    if ((M.size constructors <= 2) && ((S.size calls <= 64) && distinctTags constructors))
    then Just (ReturnSummary constructors calls)
    else Nothing;
  -- Only RETURN POSITIONS constrain the result. Scrutinees, conditions,
  -- let RHSs and constructor payloads keep ordinary evaluation/ABI behavior.
  scan :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XErased -> Maybe ReturnSummary;
  scan constructors functions expression = case expression of {
    XELet name value body -> scan constructors functions body;
    XELetRec bindings body -> Nothing;
    XECase subject branches -> case branches of {
      [] -> Nothing;
      _ -> scanBranches constructors functions branches (ReturnSummary M.empty S.empty)
    };
    XEVar name -> Nothing;
    _ -> case O.applications expression of {
      (,) (XEConstructor name) arguments -> case M.lookup compareString name constructors of {
        Just ((,) tag arity) ->
          if ((tag >= 0) &&
              (((arity == 0) || (arity == 1)) && (L.length arguments == arity)))
          then Just (ReturnSummary (M.singleton name ((,) tag arity)) S.empty)
          else Nothing;
        Nothing -> Nothing
      };
      (,) (XEPrimitive PIfThenElse) ((:) condition ((:) yes ((:) no []))) ->
        case scan constructors functions yes of {
          Nothing -> Nothing;
          Just left -> case scan constructors functions no of {
            Nothing -> Nothing;
            Just right -> mergeSummary left right
          }
        };
      (,) (XEVar name) arguments -> case M.lookup O.compareName name functions of {
        Just function ->
          if (L.length arguments == L.length (A.parameters function))
          then Just (ReturnSummary M.empty (S.singleton name))
          else Nothing;
        Nothing -> Nothing
      };
      _ -> Nothing
    }
  };
  scanBranches :: Map String ((,) Int Int) -> Map XName A.WorkerFunction ->
                  [] XErasedAlternative -> ReturnSummary -> Maybe ReturnSummary;
  scanBranches constructors functions branches accumulated = case branches of {
    [] -> Just accumulated;
    (:) (XErasedAlternative pattern body) rest -> case scan constructors functions body of {
      Nothing -> Nothing;
      Just found -> case mergeSummary accumulated found of {
        Nothing -> Nothing;
        Just next -> scanBranches constructors functions rest next
      }
    }
  };
  -- Each reachable return-call worker is scanned at most once. Reject the
  -- complete closure on budget exhaustion: never accept a truncated graph.
  collect :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> [] XName ->
             Int -> Int -> Map XName ReturnSummary -> Map String ((,) Int Int) -> Maybe ReturnGraph;
  collect constructors functions pending functionBudget nodeBudget graph allConstructors = case pending of {
    [] -> Just (ReturnGraph graph allConstructors);
    (:) name rest ->
      if M.member O.compareName name graph
      then collect constructors functions rest functionBudget nodeBudget graph allConstructors
      else if (functionBudget <= 0)
           then Nothing
           else case M.lookup O.compareName name functions of {
             Nothing -> Nothing;
             Just function ->
               let { body = A.functionBody function;
                     remaining = O.remainingSize 512 body;
                     cost = 512 - remaining
                   } in
               if ((remaining < 0) || (cost > nodeBudget))
               then Nothing
               else case scan constructors functions body of {
                 Nothing -> Nothing;
                 Just found ->
                   let { joined = M.union compareString allConstructors (summaryConstructors found) } in
                   if ((M.size joined > 2) || L.not (distinctTags joined))
                   then Nothing
                   else collect constructors functions
                          (L.append (S.toList (summaryCalls found)) rest)
                          (functionBudget - 1) (nodeBudget - cost)
                          (M.insert O.compareName name found graph) joined
               }
           }
  };
  factsFor :: Map XName (Set String) -> XName -> Set String;
  factsFor facts name = M.findWithDefault O.compareName S.empty name facts;
  nextFacts :: Map XName (Set String) -> ReturnSummary -> Set String;
  nextFacts facts summary =
    S.union compareString
      (S.fromList compareString (M.keys (summaryConstructors summary)))
      (S.unions compareString (L.map (factsFor facts) (S.toList (summaryCalls summary))));
  sameNames :: Set String -> Set String -> Bool;
  sameNames left right = L.eqList eqString (S.toList left) (S.toList right);
  productive :: Map XName (Set String) -> Bool;
  productive facts = L.all (\entry -> L.not (S.null (L.snd entry))) (M.toList facts);
  solve :: Int -> Map XName ReturnSummary -> Map XName (Set String) -> Bool;
  solve fuel graph facts =
    if (fuel <= 0) then False
    else let { next = M.map (nextFacts facts) graph } in
      if M.eqMap O.eqName sameNames facts next
      then productive next
      else solve (fuel - 1) graph next;
  infer :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Maybe ResultInfo;
  infer constructors functions root =
    case collect constructors functions ((:) root []) 64 8192 M.empty M.empty of {
      Nothing -> Nothing;
      Just (ReturnGraph graph allConstructors) ->
        if M.null allConstructors
        then Nothing
        else let {
          initial = M.map
            (\summary -> S.fromList compareString (M.keys (summaryConstructors summary))) graph
        } in
        if solve (M.size graph + 1) graph initial
        then Just (ResultInfo (M.toList allConstructors) (M.keys graph))
        else Nothing
    };
  -- Reserve a whole validated closure atomically. Shared callees count once.
  reserve :: Map XName A.WorkerFunction -> [] XName -> Set XName -> Int -> Maybe ((,) (Set XName) Int);
  reserve functions names admitted remainingNodes = case names of {
    [] -> Just ((,) admitted remainingNodes);
    (:) name rest ->
      if S.member O.compareName name admitted
      then reserve functions rest admitted remainingNodes
      else if (S.size admitted >= 32)
           then Nothing
           else case M.lookup O.compareName name functions of {
             Nothing -> Nothing;
             Just function ->
               let { remaining = O.remainingSize 512 (A.functionBody function);
                     cost = 512 - remaining
                   } in
               if ((remaining < 0) || (cost > remainingNodes))
               then Nothing
               else reserve functions rest (S.insert O.compareName name admitted) (remainingNodes - cost)
           }
  };
  planVisit :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName ->
               [] ((,) XName A.WorkerFunction) -> Int -> Set XName -> Int ->
               Map XName ResultInfo -> Map XName ResultInfo;
  planVisit constructors functions excluded entries attempts admitted remainingNodes roots =
    if (attempts <= 0) then roots
    else case entries of {
      [] -> roots;
      (:) ((,) name function) rest ->
        if S.member O.compareName name excluded
        then planVisit constructors functions excluded rest attempts admitted remainingNodes roots
        else if (O.remainingSize 512 (A.functionBody function) < 0)
             then planVisit constructors functions excluded rest attempts admitted remainingNodes roots
             else case scan constructors functions (A.functionBody function) of {
               Nothing -> planVisit constructors functions excluded rest attempts admitted remainingNodes roots;
               Just summary -> case infer constructors functions name of {
                 Nothing -> planVisit constructors functions excluded rest (attempts - 1) admitted remainingNodes roots;
                 Just info ->
                   if (relevantSum info &&
                       L.all (\worker -> L.not (S.member O.compareName worker excluded)) (workers info))
                   then case reserve functions (workers info) admitted remainingNodes of {
                     Nothing -> planVisit constructors functions excluded rest (attempts - 1) admitted remainingNodes roots;
                     Just ((,) nextWorkers nextNodes) ->
                       planVisit constructors functions excluded rest (attempts - 1) nextWorkers nextNodes
                         (M.insert O.compareName name info roots)
                   }
                   else planVisit constructors functions excluded rest (attempts - 1) admitted remainingNodes roots
               }
             }
    };
  -- Immutable root plan, computed before any private clone is emitted.
  -- Driver work is also bounded: <=4096 existing workers, <=256 graph trials.
  -- Constructor tags are global identities, so a shared subset-return callee
  -- has the same aggregate ABI under every admitted root descriptor.
  plan :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName -> Map XName ResultInfo;
  plan constructors functions excluded =
    if (M.size functions > 4096)
    then M.empty
    else planVisit constructors functions excluded (M.toList functions) 256 S.empty 8192 M.empty
}
