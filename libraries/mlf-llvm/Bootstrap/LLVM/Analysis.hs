-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Analysis where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.LLVM.Optimize as O;
  -- Native worker information is computed by two monotone fixed points.
  data WorkerFunction = WorkerFunction ([] XName) XErased ([] XName) (Set XName) EntryDemand;
  parameters :: WorkerFunction -> [] XName;
  parameters (WorkerFunction args body captured demanded entry) = args;
  functionBody :: WorkerFunction -> XErased;
  functionBody (WorkerFunction args body captured demanded entry) = body;
  captures :: WorkerFunction -> [] XName;
  captures (WorkerFunction args body captured demanded entry) = captured;
  strict :: WorkerFunction -> Set XName;
  strict (WorkerFunction args body captured demanded entry) = demanded;
  entrySummary :: WorkerFunction -> EntryDemand;
  entrySummary (WorkerFunction args body captured demanded entry) = entry;
  entryOrder :: WorkerFunction -> [] XName;
  entryOrder f = demandNames (entrySummary f);
  needed :: Map XName WorkerFunction -> XErased -> Set XName;
  needed functions expression = neededFree functions (O.free expression);
  neededFree functions names = S.unions O.compareName (L.map (neededName functions) (S.toList names));
  neededName :: Map XName WorkerFunction -> XName -> Set XName;
  neededName functions name =
    case M.lookup O.compareName name functions of {
      Nothing -> S.singleton name;
      Just f -> S.fromList O.compareName (captures f)
    };
  children :: XErased -> [] XErased;
  children expression =
    case expression of {
      XEAbs n b -> (:) b [];
      XEApp f a -> (:) f ((:) a []);
      XELet n a b -> (:) a ((:) b []);
      XELetRec ds b ->
        (:) b
          (L.map
             (\entry ->
                case entry of {
                  (,) n a -> a
                })
             ds);
      XECase s branches ->
        (:) s
          (L.map
             (\branch ->
                case branch of {
                  XErasedAlternative p b -> b
                })
             branches);
      _ -> []
    };
  bindings :: XErased -> [] ((,) XName XErased);
  bindings expression =
    case expression of {
      XELet name a b -> (:) ((,) name a) [];
      XELetRec ds b -> ds;
      _ -> []
    };
  collectBinding :: (,) XName XErased -> Map XName WorkerFunction -> Map XName WorkerFunction;
  collectBinding ((,) name rhs) fs =
    case O.lambdas rhs of {
      (,) [] body -> fs;
      (,) args body -> M.insert O.compareName name (WorkerFunction args body [] S.empty (EntryDemand [] False)) fs
    };
  collect :: XErased -> Map XName WorkerFunction;
  collect expression =
    M.unions O.compareName
      ((:) (L.foldr collectBinding M.empty (bindings expression))
         (L.map collect (children expression)));
  -- A callback may contain another callback as an argument. Analyze their
  -- bodies inside out so outer lambdas can use the inner lexical free set.
  -- Repeated binder identities in open input take the ordinary syntax path.
  lambdaBodies pending reversed = case pending of {
    [] -> reversed;
    (:) term rest -> case term of {
      XEAbs binder body -> lambdaBodies ((:) body rest) ((:) ((,) binder body) reversed);
      _ -> lambdaBodies (L.append (children term) rest) reversed
    }
  };
  lambdaFreeTable :: XErased -> Map XName (Maybe (Set XName));
  lambdaFreeTable expression = L.foldlStrict addLambdaFree M.empty (lambdaBodies [expression] []);
  addLambdaFree table ((,) binder body) = case M.lookup O.compareName binder table of {
    Just _ -> M.insert O.compareName binder Nothing table;
    Nothing -> let { names = nestedFree table body } in
      seq (S.size names) (M.insert O.compareName binder (Just names) table)
  };
  nestedFree table term = case term of {
    XEAbs binder body -> case M.lookup O.compareName binder table of {
      Just (Just names) -> S.delete O.compareName binder names;
      _ -> O.freeWith (nestedFree table) term
    };
    _ -> O.freeWith (nestedFree table) term
  };
  lambdaNeeded functions table binder body = S.delete O.compareName binder
    (case M.lookup O.compareName binder table of {
      Just (Just names) -> neededFree functions names;
      _ -> needed functions body
    });
  sameNames :: [] XName -> [] XName -> Bool;
  sameNames a b =
    case a of {
      [] -> L.null b;
      (:) n rest ->
        case b of {
          [] -> False;
          (:) m tail -> (O.eqName n m && sameNames rest tail)
        }
    };
  sameFunction :: WorkerFunction -> WorkerFunction -> Bool;
  sameFunction (WorkerFunction args body captured demanded entry) (WorkerFunction args2 body2 captured2 demanded2 entry2) =
    (sameNames args args2 &&
     (sameNames captured captured2 &&
      (sameNames (S.toList demanded) (S.toList demanded2) &&
       (sameDemand entry entry2 && X.equalErased body body2))));
  sameFunctions :: [] ((,) XName WorkerFunction) -> [] ((,) XName WorkerFunction) -> Bool;
  sameFunctions a b =
    case a of {
      [] -> L.null b;
      (:) ((,) n f) rest ->
        case b of {
          [] -> False;
          (:) ((,) m g) tail -> (O.eqName n m && (sameFunction f g && sameFunctions rest tail))
        }
    };
  -- Bodies and parameters stay fixed during capture propagation. Cache their
  -- lexical free names once; each iteration only changes the capture lists.
  captureFixed :: Map XName WorkerFunction -> Map XName WorkerFunction;
  captureFixed fs =
    captureIndexed
      (M.map
         (\f -> (,) (S.toList (O.free (functionBody f))) (S.fromList O.compareName (parameters f)))
         fs)
      fs;
  captureIndexed :: Map XName ((,) ([] XName) (Set XName)) ->
                    Map XName WorkerFunction -> Map XName WorkerFunction;
  captureIndexed inputs fs = let {
    callers = M.foldlWithKeyStrict addCaller M.empty inputs;
    addCaller index caller ((,) names _) = L.foldlStrict
      (\tree name -> if M.member O.compareName name fs
        then M.insertWith O.compareName L.append name [caller] tree else tree) index names;
    -- Store only changed capture sets. Unchanged workers keep their initial
    -- captures; lexical names outside the worker table still capture themselves.
    neededSet previous name = case M.lookup O.compareName name previous of {
      Just captured -> captured;
      Nothing -> neededName fs name
    };
    unchanged previous name captured = case M.lookup O.compareName name previous of {
      Just old -> S.eqSet O.eqName old captured;
      Nothing -> case captures (M.get O.compareName name fs) of {
        [] -> S.null captured;
        old -> sameNames old (S.toList captured)
      }
    };
    propagate previous pending = let {
      update ((,) current dirty) name = case M.get O.compareName name inputs of {
        (,) names parameterNames -> let {
          captured = S.difference O.compareName
            (S.unions O.compareName (L.map (neededSet previous) names)) parameterNames
        } in if unchanged previous name captured then (,) current dirty else let {
          next = M.insert O.compareName name captured current;
          dependents = M.findWithDefault O.compareName [] name callers;
          affected = L.foldlStrict (\set caller -> S.insert O.compareName caller set) dirty dependents
        } in seq next (seq affected ((,) next affected))
      }
    } in case L.foldlStrict update ((,) previous S.empty) pending of {
      (,) current dirty -> if S.null dirty then current else propagate current (S.toList dirty)
    };
    publish table name captured = M.adjust O.compareName
      (\f -> WorkerFunction (parameters f) (functionBody f) (S.toList captured)
        (strict f) (entrySummary f)) name table
  } in M.foldlWithKeyStrict publish fs (propagate M.empty (M.keys fs));
  -- A dependency is recorded when a saturated call reads its callee's
  -- summary. Later rounds can expose further calls in arguments and let
  -- bindings; add those edges before scheduling the next round.
  demandFixed :: Map XName WorkerFunction -> Map XName WorkerFunction;
  demandFixed fs = let {
    observe previous old = let {
      observation = entryDemandUsing previous M.empty (functionBody old);
      demand = restrictWorkerDemand old (observedValue observation);
      fresh = WorkerFunction (parameters old) (functionBody old) (captures old)
        (S.fromList O.compareName (demandNames demand)) demand;
      different = L.not (sameDemand (entrySummary old) demand);
      -- Parameter hints never escape a call, but captured names can be
      -- forwarded verbatim even when the numeric prefix stays the same.
      forwardsCapture = L.not (L.null (demandNames demand)) && L.not (L.null (captures old))
    } in (,,,) fresh (observedCalls observation) different (different || forwardsCapture);
    propagate previous callers observations publish = let {
      record ((,,) index changed touched) name ((,,,) _ callees different notify) = let {
        addCaller tree callee = M.insertWith O.compareName (S.union O.compareName) callee (S.singleton name) tree;
        nextIndex = L.foldlStrict addCaller index (S.toList callees);
        affected = if notify then (:) name touched else touched;
        advanced = different || changed
      } in seq nextIndex (seq advanced (seq affected ((,,) nextIndex advanced affected)));
      next = publish (M.map (\((,,,) fresh _ _ _) -> fresh) observations)
    } in case M.foldlWithKeyStrict record ((,,) callers False []) observations of {
      (,,) index changed touched -> if changed then let {
        dirty = L.foldlStrict
          (\names callee -> S.union O.compareName names (M.findWithDefault O.compareName S.empty callee index))
          S.empty touched;
        pending = M.fromDistinctAscList (L.map
          (\name -> (,) name (observe next (M.get O.compareName name next))) (S.toList dirty))
      } in if S.null dirty then next else
        propagate next index pending (\updates -> M.union O.compareName updates next)
      else previous
    }
  } in propagate fs M.empty (M.map (observe fs) fs) (\updates -> updates);
  workerDemand :: Map XName WorkerFunction -> WorkerFunction -> EntryDemand;
  workerDemand fs f = restrictWorkerDemand f (entryDemand fs M.empty (functionBody f));
  restrictWorkerDemand :: WorkerFunction -> EntryDemand -> EntryDemand;
  restrictWorkerDemand f demand = let {
    allowed = S.fromList O.compareName (L.append (parameters f) (captures f))
  } in indexedDemand
       (nameSequence (L.filter (\name -> S.member O.compareName name allowed) (demandNames demand)))
       (demandComplete demand);
  analyze :: XErased -> Map XName WorkerFunction;
  analyze expression = demandFixed (captureFixed (collect expression));
  -- The prefix is an ordered sequence of variable forces, not an unordered
  -- eventual-strictness set. Complete means the expression reaches WHNF after
  -- these forces and certified total operations; otherwise the prefix stops
  -- at a possibly failing operation, branch, or unknown call.
  -- Concatenation preserves force order without copying the left prefix.
  -- Lexical aliases share a flattened leaf, so traversing a concatenation
  -- never expands their summary DAG. Identity sets are demanded only after
  -- a leaf's names: asking for a prefix must not inspect a later summary.
  -- Keep the list constructor for callers supplying a summary; its order
  -- and duplicate entries survive.
  data DemandSequence = DemandLeaf IntSet ([] XName) |
    DemandAppend DemandSequence DemandSequence;
  data EntryDemand = EntryDemand ([] XName) Bool |
    IndexedDemand DemandSequence ([] XName) Bool;
  demandNames :: EntryDemand -> [] XName;
  demandNames demand = case demand of {
    EntryDemand names _ -> names;
    IndexedDemand _ names _ -> names
  };
  demandComplete :: EntryDemand -> Bool;
  demandComplete demand = case demand of {
    EntryDemand _ complete -> complete;
    IndexedDemand _ _ complete -> complete
  };
  nameSequence :: [] XName -> DemandSequence;
  nameSequence names = DemandLeaf (IS.fromList (L.map O.nameId names)) names;
  demandSequence :: EntryDemand -> DemandSequence;
  demandSequence demand = case demand of {
    EntryDemand names _ -> nameSequence names;
    IndexedDemand sequence _ _ -> sequence
  };
  sharedDemand :: EntryDemand -> EntryDemand;
  sharedDemand demand = indexedDemand (nameSequence (demandNames demand)) (demandComplete demand);
  indexedDemand :: DemandSequence -> Bool -> EntryDemand;
  indexedDemand sequence complete =
    IndexedDemand sequence (sequenceNames IS.empty [sequence]) complete;
  sequenceNames :: IntSet -> [] DemandSequence -> [] XName;
  sequenceNames seen pending = case pending of {
    [] -> [];
    (:) sequence rest -> case sequence of {
      DemandAppend first next -> sequenceNames seen ((:) first ((:) next rest));
      DemandLeaf identities names -> let {
        -- Check this whole leaf against the earlier leaves, not against its
        -- own entries. This is exactly appendNames even for supplied repeats.
        emit remaining = case remaining of {
          [] -> sequenceNames (IS.union seen identities) rest;
          (:) name tail -> if IS.member (O.nameId name) seen then emit tail else (:) name (emit tail)
        }
      } in emit names
    }
  };
  sameDemand :: EntryDemand -> EntryDemand -> Bool;
  sameDemand a b = sameNames (demandNames a) (demandNames b) &&
    demandComplete a == demandComplete b;
  -- Let RHSs may be evaluated only at the next demand, not anywhere in a
  -- worker prefix: doing so could cross an earlier failure in that prefix.
  demanded :: Map XName WorkerFunction -> XErased -> Set XName;
  demanded fs expression = case demandNames (entryDemand fs M.empty expression) of {
    (:) first rest -> S.singleton first;
    [] -> S.empty
  };
  entryTotalPrimitive :: Primitive -> Bool;
  entryTotalPrimitive p = case p of {
    PAddInt -> True;
    PSubInt -> True;
    PAndInt -> True;
    PEqInt -> True;
    PLtInt -> True;
    _ -> False
  };
  barrierAfter :: EntryDemand -> EntryDemand;
  barrierAfter demand = case demand of {
    EntryDemand names _ -> EntryDemand names False;
    IndexedDemand sequence names _ -> IndexedDemand sequence names False
  };
  appendNames :: [] XName -> [] XName -> [] XName;
  appendNames first next = let { identities = IS.fromList (L.map O.nameId first) } in
    L.append first (L.filter (\name -> L.not (IS.member (O.nameId name) identities)) next);
  appendDemand :: EntryDemand -> EntryDemand -> EntryDemand;
  appendDemand first next =
    if demandComplete first
    then let { left = demandSequence first; right = demandSequence next } in
      indexedDemand
        (case left of {
          -- Shared closed aliases must collapse without expanding their DAG.
          -- Inspect only the left sequence, so the first force stays lazy in
          -- the following summary and in its cached identity set.
          DemandLeaf _ [] -> right;
          _ -> DemandAppend left right
        })
        (demandComplete next)
    else first;
  -- Share summaries only along this lexical let spine. Each summary describes
  -- its body with open names, independent of the emitter's current WHNF facts.
  data LetDemands = LetDemands EntryDemand (Maybe LetDemands);
  letBodyDemands :: Map XName WorkerFunction -> XErased -> LetDemands;
  letBodyDemands fs term = case term of {
    XELet binder rhs body -> let {
      rest = letBodyDemands fs body;
      entry = case rest of { LetDemands demand _ -> demand }
    } in LetDemands (bindDemand binder (entryDemand fs M.empty rhs) entry) (Just rest);
    _ -> LetDemands (entryDemand fs M.empty term) Nothing
  };
  -- Substitute at the first force. A partial RHS cuts off later forces,
  -- and appendDemand removes repeated names shared with either neighbor.
  bindDemand :: XName -> EntryDemand -> EntryDemand -> EntryDemand;
  bindDemand binder rhs demand = case L.break (O.eqName binder) (demandNames demand) of {
    (,) before ((:) _ after) ->
      appendDemand (EntryDemand before True) (appendDemand rhs (EntryDemand after (demandComplete demand)));
    _ -> demand
  };
  -- The ordinary analysis returns an ordered prefix. Fixed-point analysis
  -- also records the worker summaries consulted to produce it. Both use
  -- the same evaluator, including its barrier and lexical sharing rules.
  class DemandOperations d where {
    plainEntry :: [] XName -> Bool -> d;
    shareEntry :: d -> d;
    barrierEntry :: d -> d;
    appendEntry :: d -> d -> d;
    calledEntry :: XName -> d -> d
  };
  instance DemandOperations EntryDemand where {
    plainEntry = EntryDemand;
    shareEntry = sharedDemand;
    barrierEntry = barrierAfter;
    appendEntry = appendDemand;
    calledEntry _ demand = demand
  };
  data ObservedDemand = ObservedDemand EntryDemand (Set XName);
  observedValue (ObservedDemand value _) = value;
  observedCalls (ObservedDemand _ calls) = calls;
  instance DemandOperations ObservedDemand where {
    plainEntry names complete = ObservedDemand (EntryDemand names complete) S.empty;
    shareEntry value = ObservedDemand (sharedDemand (observedValue value)) (observedCalls value);
    barrierEntry value = ObservedDemand (barrierAfter (observedValue value)) (observedCalls value);
    appendEntry first next = let { demand = observedValue first } in
      if demandComplete demand then ObservedDemand (appendDemand demand (observedValue next))
        (S.union O.compareName (observedCalls first) (observedCalls next)) else first;
    calledEntry name value = ObservedDemand (observedValue value) (S.insert O.compareName name (observedCalls value))
  };
  entryDemand :: Map XName WorkerFunction -> Map XName EntryDemand -> XErased -> EntryDemand;
  entryDemand = entryDemandUsing;
  entryDemandUsing :: forall d. DemandOperations d => Map XName WorkerFunction -> Map XName d -> XErased -> d;
  entryDemandUsing fs local expression = case expression of {
    XEVar name ->
      if M.member O.compareName name fs then plainEntry [] True
      else case M.lookup O.compareName name local of {
        Just demand -> demand;
        Nothing -> plainEntry ((:) name []) True
      };
    XEInt _ -> plainEntry [] True;
    XEDouble _ -> plainEntry [] True;
    XEBool _ -> plainEntry [] True;
    XEString _ -> plainEntry [] True;
    XEPrimitive _ -> plainEntry [] True;
    XEConstructor _ -> plainEntry [] True;
    XEAbs _ _ -> plainEntry [] True;
    XELet name rhs body ->
      -- Lazy shared summaries preserve aliases without reanalyzing a closed
      -- RHS at each use or visiting an unused binding.
      entryDemandUsing fs (M.insert O.compareName name (shareEntry (entryDemandUsing fs local rhs)) local) body;
    XELetRec bindings body ->
      entryDemandUsing fs
        (L.foldr (\binding rest -> case binding of {
          (,) name rhs -> M.insert O.compareName name (plainEntry [] False) rest
        }) local bindings) body;
    XECase subject ((:) (XErasedAlternative (XDefaultPattern optional) body) []) ->
      case optional of {
        Nothing -> entryDemandUsing fs local body;
        Just name -> entryDemandUsing fs
          (M.insert O.compareName name (shareEntry (entryDemandUsing fs local subject)) local) body
      };
    XECase subject alternatives -> barrierEntry (entryDemandUsing fs local subject);
    XEApp _ _ -> entryApplicationUsing fs local expression;
    _ -> plainEntry [] False
  };
  entryArguments :: Map XName WorkerFunction -> Map XName EntryDemand -> [] XErased -> EntryDemand;
  entryArguments = entryArgumentsUsing;
  entryArgumentsUsing :: forall d. DemandOperations d => Map XName WorkerFunction -> Map XName d -> [] XErased -> d;
  entryArgumentsUsing fs local arguments = case arguments of {
    [] -> plainEntry [] True;
    (:) first rest -> appendEntry (entryDemandUsing fs local first) (entryArgumentsUsing fs local rest)
  };
  entryWorkerArgument :: Map XName WorkerFunction -> Map XName EntryDemand ->
                         WorkerFunction -> [] XErased -> XName -> EntryDemand;
  entryWorkerArgument = entryWorkerArgumentUsing;
  entryWorkerArgumentUsing :: forall d. DemandOperations d => Map XName WorkerFunction -> Map XName d ->
                         WorkerFunction -> [] XErased -> XName -> d;
  entryWorkerArgumentUsing fs local function arguments selected =
    case L.find (\binding -> O.eqName selected (L.fst binding))
           (L.zip (parameters function) arguments) of {
      Just ((,) name argument) -> entryDemandUsing fs local argument;
      Nothing ->
        if L.elem O.eqName selected (captures function)
        then entryDemandUsing fs local (XEVar selected)
        else plainEntry [] False
    };
  entryWorkerArguments :: Map XName WorkerFunction -> Map XName EntryDemand ->
                          WorkerFunction -> [] XErased -> [] XName -> EntryDemand;
  entryWorkerArguments = entryWorkerArgumentsUsing;
  entryWorkerArgumentsUsing :: forall d. DemandOperations d => Map XName WorkerFunction -> Map XName d ->
                          WorkerFunction -> [] XErased -> [] XName -> d;
  entryWorkerArgumentsUsing fs local function arguments names = case names of {
    [] -> plainEntry [] (demandComplete (entrySummary function));
    (:) first rest -> appendEntry
      (entryWorkerArgumentUsing fs local function arguments first)
      (entryWorkerArgumentsUsing fs local function arguments rest)
  };
  entryApplication :: Map XName WorkerFunction -> Map XName EntryDemand -> XErased -> EntryDemand;
  entryApplication = entryApplicationUsing;
  entryApplicationUsing :: forall d. DemandOperations d => Map XName WorkerFunction -> Map XName d -> XErased -> d;
  entryApplicationUsing fs local expression = case O.applications expression of {
    (,) (XEPrimitive PIfThenElse) ((:) condition ((:) yes ((:) no []))) ->
      barrierEntry (entryDemandUsing fs local condition);
    (,) (XEPrimitive PSeq) ((:) first ((:) rest [])) ->
      appendEntry (entryDemandUsing fs local first) (entryDemandUsing fs local rest);
    (,) (XEPrimitive p) arguments ->
      if L.length arguments < P.primitiveArity p then plainEntry [] True
      else if L.length arguments /= P.primitiveArity p then plainEntry [] False
      else if L.not (P.primitiveStrict p) then plainEntry [] False
      else let { demand = entryArgumentsUsing fs local arguments } in
        if entryTotalPrimitive p then demand else barrierEntry demand;
    (,) (XEConstructor name) arguments -> plainEntry [] True;
    (,) (XEVar name) arguments -> case M.lookup O.compareName name fs of {
      Just function ->
        if L.length arguments < L.length (parameters function) then plainEntry [] True
        else if L.length arguments /= L.length (parameters function) then plainEntry [] False
        else calledEntry name (entryWorkerArgumentsUsing fs local function arguments (entryOrder function));
      Nothing -> barrierEntry (entryDemandUsing fs local (XEVar name))
    };
    (,) function arguments -> barrierEntry (entryDemandUsing fs local function)
  }
}
