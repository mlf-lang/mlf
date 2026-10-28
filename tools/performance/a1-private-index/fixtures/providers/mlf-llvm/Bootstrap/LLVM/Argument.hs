-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Argument where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.Optimize as O;
  import qualified Bootstrap.Primitive as P;
  -- Private argument ABI: actual tag plus two LAZY pointers. Original
  -- WorkerFunction/strict masks are read only; neither branch is specialized away.
  data ArgumentInfo = ArgumentInfo XName Int ([] ((,) String ((,) Int Int)));
  parameter :: ArgumentInfo -> XName;
  parameter (ArgumentInfo name index constructors) = name;
  parameterIndex :: ArgumentInfo -> Int;
  parameterIndex (ArgumentInfo name index constructors) = index;
  alternatives :: ArgumentInfo -> [] ((,) String ((,) Int Int));
  alternatives (ArgumentInfo name index constructors) = constructors;
  descriptor :: ArgumentInfo -> String -> Maybe ((,) Int Int);
  descriptor info constructor = M.lookup compareString constructor (M.fromList compareString (alternatives info));
  indexOf :: XName -> [] XName -> Int -> Maybe Int;
  indexOf wanted names index = case names of {
    [] -> Nothing;
    (:) name rest -> if O.eqName wanted name then Just index else indexOf wanted rest (index + 1)
  };
  boundedLength :: forall a. Int -> [] a -> Bool;
  boundedLength remaining values = case values of {
    [] -> True;
    (:) value rest -> if (remaining <= 0) then False else boundedLength (remaining - 1) rest
  };
  -- Erased expression-node counts do NOT count pattern binder lists. Keep
  -- a separate metadata budget and consume it before O.free/A.needed.
  -- Independent budgets preserve the existing exact expression-node limits.
  consumeMetadata :: forall a. Int -> [] a -> Maybe Int;
  consumeMetadata budget entries = case entries of {
    [] -> Just budget;
    (:) entry rest -> if (budget <= 0) then Nothing else consumeMetadata (budget - 1) rest
  };
  treeBudget :: Int -> Int -> XErased -> Maybe ((,) Int Int);
  treeBudget nodes metadata expression =
    if (nodes <= 0) then Nothing
    else let { rest = nodes - 1 } in case expression of {
      XEAbs name body -> if (metadata <= 0) then Nothing else treeBudget rest (metadata - 1) body;
      XEApp fun arg -> treeThen (treeBudget rest metadata fun) arg;
      XELet name rhs body ->
        if (metadata <= 0) then Nothing else treeThen (treeBudget rest (metadata - 1) rhs) body;
      XELetRec bindings body -> case treeBudget rest metadata body of {
        Nothing -> Nothing;
        Just ((,) n m) -> treeBindings n m bindings
      };
      XECase subject branches -> case treeBudget rest metadata subject of {
        Nothing -> Nothing;
        Just ((,) n m) -> treeBranches n m branches
      };
      _ -> Just ((,) rest metadata)
    };
  treeThen :: Maybe ((,) Int Int) -> XErased -> Maybe ((,) Int Int);
  treeThen budget expression = case budget of {
    Nothing -> Nothing;
    Just ((,) n m) -> treeBudget n m expression
  };
  treeBindings :: Int -> Int -> [] ((,) XName XErased) -> Maybe ((,) Int Int);
  treeBindings nodes metadata bindings = case bindings of {
    [] -> Just ((,) nodes metadata);
    (:) ((,) name rhs) rest ->
      if (metadata <= 0) then Nothing
      else case treeBudget nodes (metadata - 1) rhs of {
        Nothing -> Nothing;
        Just ((,) n m) -> treeBindings n m rest
      }
  };
  treeBranches :: Int -> Int -> [] XErasedAlternative -> Maybe ((,) Int Int);
  treeBranches nodes metadata branches = case branches of {
    [] -> Just ((,) nodes metadata);
    (:) (XErasedAlternative pattern body) rest ->
      let { budget = case pattern of {
              XConstructorPattern constructor fields -> consumeMetadata metadata fields;
              XDefaultPattern Nothing -> Just metadata;
              XDefaultPattern (Just name) -> if (metadata <= 0) then Nothing else Just (metadata - 1)
            }
          } in
      case budget of {
        Nothing -> Nothing;
        Just available -> case treeBudget nodes available body of {
          Nothing -> Nothing;
          Just ((,) n m) -> treeBranches n m rest
        }
      }
  };
  boundedTree :: Int -> XErased -> Bool;
  boundedTree budget expression = case treeBudget budget budget expression of {
    Nothing -> False;
    Just remaining -> True
  };
  -- A.needed follows lifted worker capture summaries. Bound their size BEFORE
  -- invoking it so an otherwise small branch cannot import unbounded metadata.
  boundedNeeds :: Map XName A.WorkerFunction -> XErased -> Bool;
  boundedNeeds functions body = boundedTree 512 body && L.all
    (\name -> case M.lookup O.compareName name functions of {
       Nothing -> True;
       Just function -> boundedLength 512 (A.captures function)
     }) (S.toList (O.free body));
  checkedAlternative :: Map String ((,) Int Int) -> XErasedAlternative -> Maybe ((,) String ((,) Int Int));
  checkedAlternative constructors alternative = case alternative of {
    XErasedAlternative (XConstructorPattern name fields) body ->
      case M.lookup compareString name constructors of {
        Just ((,) tag arity) ->
          if ((tag >= 0) && (((arity == 0) || (arity == 2)) && (L.length fields == arity)))
          then Just ((,) name ((,) tag arity)) else Nothing;
        Nothing -> Nothing
      };
    _ -> Nothing
  };
  branchFree :: Map XName A.WorkerFunction -> XName -> XErasedAlternative -> Bool;
  branchFree functions selected (XErasedAlternative pattern body) =
    boundedNeeds functions body && L.not (S.member O.compareName selected (A.needed functions body));
  infer :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Maybe ArgumentInfo;
  infer constructors functions name = case M.lookup O.compareName name functions of {
    Nothing -> Nothing;
    Just function ->
      if (L.not (boundedTree 512 (A.functionBody function)) ||
          (L.not (boundedLength 16 (A.parameters function)) ||
           L.not (boundedLength 512 (A.captures function)))) then Nothing
      else case A.functionBody function of {
        XECase (XEVar selected) ((:) first ((:) second [])) ->
          if L.not (S.member O.compareName selected (A.strict function)) then Nothing
          else case indexOf selected (A.parameters function) 0 of {
            Nothing -> Nothing;
            Just index -> case checkedAlternative constructors first of {
              Nothing -> Nothing;
              Just left -> case checkedAlternative constructors second of {
                Nothing -> Nothing;
                Just right -> case ((,) left right) of {
                  (,) ((,) leftName ((,) leftTag leftArity)) ((,) rightName ((,) rightTag rightArity)) ->
                    if ((leftTag /= rightTag) &&
                        (((leftArity == 0) && (rightArity == 2)) || ((leftArity == 2) && (rightArity == 0))) &&
                        (branchFree functions selected first && branchFree functions selected second))
                    then Just (ArgumentInfo selected index ((:) left ((:) right []))) else Nothing
                }
              }
            }
          };
        _ -> Nothing
      }
  };
  -- This guard does not evaluate fields or chase variables/lets/conditionals.
  freshFields :: ArgumentInfo -> XErased -> Maybe ((,) Int ([] XErased));
  freshFields info expression = case O.applications expression of {
    (,) (XEConstructor name) fields -> case descriptor info name of {
      Nothing -> Nothing;
      Just ((,) tag arity) -> if (L.length fields == arity) then Just ((,) tag fields) else Nothing
    };
    _ -> Nothing
  };
  -- Enumerate bounded consumer candidates before allocating clone budget.
  candidatesVisit :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName ->
                     [] ((,) XName A.WorkerFunction) -> Int -> Map XName ArgumentInfo -> Map XName ArgumentInfo;
  candidatesVisit constructors functions excluded entries attempts found =
    if (attempts <= 0) then found
    else case entries of {
      [] -> found;
      (:) ((,) name function) rest ->
        if S.member O.compareName name excluded
        then candidatesVisit constructors functions excluded rest attempts found
        else case A.functionBody function of {
          XECase (XEVar selected) ((:) first ((:) second [])) ->
            case infer constructors functions name of {
              Nothing -> candidatesVisit constructors functions excluded rest (attempts - 1) found;
              Just info -> candidatesVisit constructors functions excluded rest (attempts - 1)
                             (M.insert O.compareName name info found)
            };
          _ -> candidatesVisit constructors functions excluded rest attempts found
        }
    };
  candidates :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName -> Map XName ArgumentInfo;
  candidates constructors functions excluded =
    if (M.size functions > 4096) then M.empty
    else candidatesVisit constructors functions excluded (M.toList functions) 256 M.empty;
  freshCall :: Map XName A.WorkerFunction -> Map XName ArgumentInfo -> XErased -> [] XErased -> Maybe XName;
  freshCall functions possible head args = case head of {
    XEVar name -> case M.lookup O.compareName name possible of {
      Nothing -> Nothing;
      Just info -> case M.lookup O.compareName name functions of {
        Nothing -> Nothing;
        Just function ->
          if (L.length args /= L.length (A.parameters function)) then Nothing
          else case L.at (parameterIndex info) args of {
            Nothing -> Nothing;
            Just argument -> case freshFields info argument of {
              Nothing -> Nothing;
              Just fields -> Just name
            }
          }
      }
    };
    _ -> Nothing
  };
  -- Visit application spines ONCE (head plus arguments), not every prefix.
  -- The complete tree is size-checked before visiting; overflow returns no plan.
  freshTargetsVisit :: Map XName A.WorkerFunction -> Map XName ArgumentInfo -> XErased -> Set XName -> Set XName;
  freshTargetsVisit functions possible expression found = case expression of {
    XEApp fun arg -> case O.applications expression of {
      (,) head args ->
        let { next = case freshCall functions possible head args of {
                       Nothing -> found;
                       Just name -> S.insert O.compareName name found
                     }
            } in
        L.foldl (\acc child -> freshTargetsVisit functions possible child acc)
          (freshTargetsVisit functions possible head next) args
    };
    _ -> L.foldl (\acc child -> freshTargetsVisit functions possible child acc) found (A.children expression)
  };
  freshTargets :: Map XName A.WorkerFunction -> Map XName ArgumentInfo -> XErased -> Maybe (Set XName);
  freshTargets functions possible term =
    if L.not (boundedTree 262144 term) then Nothing
    else Just (freshTargetsVisit functions possible term S.empty);
  -- Canonical-entry safety is deliberately first-order. These primitives do
  -- not invoke functional operands; effect bind/run/foreign primitives reject.
  safePrimitive :: Primitive -> Bool;
  safePrimitive primitive = case primitive of {
    PIfThenElse -> True; PSeq -> True; PPanic -> True;
    PLtInt -> True; PEqInt -> True; PAddInt -> True; PSubInt -> True; PMulInt -> True;
    PTextFromChars -> True; PTextToChars -> True;
    _ -> False
  };
  mergeEdges :: Maybe (Set XName) -> Maybe (Set XName) -> Maybe (Set XName);
  mergeEdges left right = case left of {
    Nothing -> Nothing;
    Just a -> case right of { Nothing -> Nothing; Just b -> Just (S.union O.compareName a b) }
  };
  scanMany :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> [] XErased -> Maybe (Set XName);
  scanMany constructors functions expressions = case expressions of {
    [] -> Just S.empty;
    (:) expression rest -> mergeEdges (safetyScan constructors functions expression) (scanMany constructors functions rest)
  };
  scanBindings :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> [] ((,) XName XErased) -> Maybe (Set XName);
  scanBindings constructors functions bindings = case bindings of {
    [] -> Just S.empty;
    (:) ((,) name rhs) rest ->
      mergeEdges
        (if M.member O.compareName name functions
         then Just (S.singleton name) else safetyScan constructors functions rhs)
        (scanBindings constructors functions rest)
  };
  safetyScan :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XErased -> Maybe (Set XName);
  safetyScan constructors functions expression = case expression of {
    XELet name rhs body ->
      mergeEdges
        (if M.member O.compareName name functions
         then Just (S.singleton name) else safetyScan constructors functions rhs)
        (safetyScan constructors functions body);
    XELetRec bindings body ->
      mergeEdges (scanBindings constructors functions bindings) (safetyScan constructors functions body);
    XEAbs name body -> Nothing;
    XEVar name -> if M.member O.compareName name functions then Nothing else Just S.empty;
    XEPrimitive primitive -> Nothing;
    XEConstructor name -> case M.lookup compareString name constructors of {
      Just ((,) tag arity) -> if ((tag >= 0) && (arity == 0)) then Just S.empty else Nothing;
      Nothing -> Nothing
    };
    XEApp fun arg -> case O.applications expression of {
      (,) head args ->
        let { edges = case head of {
                XEVar name -> case M.lookup O.compareName name functions of {
                  Nothing -> Nothing;
                  Just function ->
                    if (boundedLength 16 (A.parameters function) &&
                        (L.length args == L.length (A.parameters function)))
                    then Just (S.singleton name) else Nothing
                };
                XEPrimitive primitive ->
                  if (safePrimitive primitive && (L.length args == P.primitiveArity primitive))
                  then Just S.empty else Nothing;
                XEConstructor name -> case M.lookup compareString name constructors of {
                  Just ((,) tag arity) ->
                    if ((tag >= 0) && (L.length args == arity)) then Just S.empty else Nothing;
                  Nothing -> Nothing
                };
                _ -> Nothing
              }
            } in
        mergeEdges edges (scanMany constructors functions args)
    };
    _ -> scanMany constructors functions (A.children expression)
  };
  -- Local worker definitions become explicit graph nodes; O.free would hide
  -- their names and incorrectly miss cycles through those local helpers.
  safetyCollect :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> [] XName ->
                   Int -> Int -> Map XName (Set XName) -> Maybe (Map XName (Set XName));
  safetyCollect constructors functions pending remainingFunctions remainingNodes graph = case pending of {
    [] -> Just graph;
    (:) name rest ->
      if M.member O.compareName name graph
      then safetyCollect constructors functions rest remainingFunctions remainingNodes graph
      else if (remainingFunctions <= 0) then Nothing
      else case M.lookup O.compareName name functions of {
        Nothing -> Nothing;
        Just function ->
          if L.not (boundedTree 512 (A.functionBody function) &&
                    (boundedLength 16 (A.parameters function) && boundedLength 512 (A.captures function)))
          then Nothing
          else let { cost = 512 - O.remainingSize 512 (A.functionBody function) } in
            if (cost > remainingNodes) then Nothing
            else case safetyScan constructors functions (A.functionBody function) of {
              Nothing -> Nothing;
              Just edges -> safetyCollect constructors functions (L.append (S.toList edges) rest)
                (remainingFunctions - 1) (remainingNodes - cost)
                (M.insert O.compareName name edges graph)
            }
      }
  };
  -- Graph is already complete and bounded. Does a different reached worker
  -- return to root? If so root's SCC has more than one node and rejects.
  reaches :: Map XName (Set XName) -> XName -> [] XName -> Set XName -> Bool;
  reaches graph target pending seen = case pending of {
    [] -> False;
    (:) name rest ->
      if O.eqName name target then True
      else if S.member O.compareName name seen then reaches graph target rest seen
      else case M.lookup O.compareName name graph of {
        Nothing -> True;
        Just edges -> reaches graph target (L.append (S.toList edges) rest) (S.insert O.compareName name seen)
      }
  };
  canonicalSafe :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Bool;
  canonicalSafe constructors functions name =
    if (M.size functions > 4096) then False
    else case safetyCollect constructors functions ((:) name []) 64 8192 M.empty of {
      Nothing -> False;
      Just graph -> L.all
        (\other -> O.eqName other name || L.not (reaches graph name ((:) other []) S.empty))
        (M.keys graph)
    };
  filterCanonical :: Map String ((,) Int Int) -> Map XName A.WorkerFunction ->
                     Map XName ArgumentInfo -> Set XName -> Map XName ArgumentInfo;
  filterCanonical constructors functions possible profitable =
    M.fromList O.compareName
      (L.filter (\entry -> case entry of {
        (,) name info -> S.member O.compareName name profitable && canonicalSafe constructors functions name
      }) (M.toList possible));
  reserve :: Map XName A.WorkerFunction -> Set XName -> [] ((,) XName ArgumentInfo) -> Int ->
             Map XName ArgumentInfo -> Map XName ArgumentInfo;
  reserve functions profitable entries remainingNodes admitted =
    if (M.size admitted >= 32) then admitted
    else case entries of {
      [] -> admitted;
      (:) ((,) name info) rest ->
        if L.not (S.member O.compareName name profitable)
        then reserve functions profitable rest remainingNodes admitted
        else case M.lookup O.compareName name functions of {
          Nothing -> reserve functions profitable rest remainingNodes admitted;
          Just function -> let { cost = 512 - O.remainingSize 512 (A.functionBody function) } in
            if (cost > remainingNodes)
            then reserve functions profitable rest remainingNodes admitted
            else reserve functions profitable rest (remainingNodes - cost)
                   (M.insert O.compareName name info admitted)
        }
    };
  -- Whole exact lowered term is required, including top-level fresh calls.
  plan :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName -> XErased -> Map XName ArgumentInfo;
  plan constructors functions excluded term =
    if (M.size functions > 4096) then M.empty
    else let { possible = candidates constructors functions excluded } in
      case freshTargets functions possible term of {
        Nothing -> M.empty;
        Just profitable -> reserve functions profitable
          (M.toList (filterCanonical constructors functions possible profitable)) 8192 M.empty
      }
}
