-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.LazyProducer where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.Optimize as O;
  import qualified Bootstrap.LLVM.Argument as G;
  -- Certificates retain ORIGINAL ASTs/patterns. No strict mask is rewritten.
  data Terminal = SelfCall ([] XErased) | Escape String ([] XErased) Int;
  data Prefix = PrefixCase XErased ([] ((,) XPattern Prefix)) |
                PrefixForce XErased | PrefixEscape Terminal;
  data DeferredCase = DeferredCase XErased ([] ((,) XPattern Terminal));
  data ProducerPlan = ProducerPlan XName XName Int XName XErased ([] XName) Prefix DeferredCase;
  worker :: ProducerPlan -> XName;
  worker (ProducerPlan n formal index binder rhs captures prefix deferred) = n;
  parameter :: ProducerPlan -> XName;
  parameter (ProducerPlan n formal index binder rhs captures prefix deferred) = formal;
  parameterIndex :: ProducerPlan -> Int;
  parameterIndex (ProducerPlan n formal index binder rhs captures prefix deferred) = index;
  recipeBinder :: ProducerPlan -> XName;
  recipeBinder (ProducerPlan n formal index binder rhs captures prefix deferred) = binder;
  recipe :: ProducerPlan -> XErased;
  recipe (ProducerPlan n formal index binder rhs captures prefix deferred) = rhs;
  recipeCaptures :: ProducerPlan -> [] XName;
  recipeCaptures (ProducerPlan n formal index binder rhs captures prefix deferred) = captures;
  prefix :: ProducerPlan -> Prefix;
  prefix (ProducerPlan n formal index binder rhs captures prefix deferred) = prefix;
  deferred :: ProducerPlan -> DeferredCase;
  deferred (ProducerPlan n formal index binder rhs captures prefix deferred) = deferred;
  -- Exact reconstruction retains complete original branch bodies for
  -- caseScope's A.needed/F-driven field loading; no extra field reads needed.
  terminalExpression :: XName -> Terminal -> XErased;
  terminalExpression name terminal = case terminal of {
    SelfCall args -> L.foldl XEApp (XEVar name) args;
    Escape constructor fields index -> L.foldl XEApp (XEConstructor constructor) fields
  };
  prefixExpression :: XName -> Prefix -> XErased;
  prefixExpression name certificate = case certificate of {
    PrefixCase subject branches -> XECase subject
      (L.map (\entry -> case entry of {
        (,) pattern next -> XErasedAlternative pattern (prefixExpression name next)
      }) branches);
    PrefixForce original -> original;
    PrefixEscape terminal -> terminalExpression name terminal
  };
  deferredExpression :: XName -> DeferredCase -> XErased;
  deferredExpression name (DeferredCase subject branches) = XECase subject
    (L.map (\entry -> case entry of {
      (,) pattern terminal -> XErasedAlternative pattern (terminalExpression name terminal)
    }) branches);
  independent :: Map XName A.WorkerFunction -> XName -> XErased -> Bool;
  independent functions name expression =
    G.boundedNeeds functions expression && L.not (S.member O.compareName name (A.needed functions expression));
  checkedPattern :: Map String ((,) Int Int) -> XPattern -> Bool;
  checkedPattern constructors pattern = case pattern of {
    XDefaultPattern optional -> True;
    XConstructorPattern name fields -> case M.lookup compareString name constructors of {
      Nothing -> False;
      Just ((,) tag arity) -> (tag >= 0) && (L.length fields == arity)
    }
  };
  -- Exactly one DIRECT occurrence; all other fields exclude implicit captures.
  fieldIndex :: Map XName A.WorkerFunction -> XName -> [] XErased -> Int -> Maybe Int -> Maybe Int;
  fieldIndex functions name fields index found = case fields of {
    [] -> found;
    (:) field rest -> case field of {
      XEVar other -> if O.eqName name other
                    then case found of {
                      Just previous -> Nothing;
                      Nothing -> fieldIndex functions name rest (index + 1) (Just index)
                    }
                    else if independent functions name field
                         then fieldIndex functions name rest (index + 1) found else Nothing;
      _ -> if independent functions name field
           then fieldIndex functions name rest (index + 1) found else Nothing
    }
  };
  escape :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> XErased -> Maybe Terminal;
  escape constructors functions name expression = case O.applications expression of {
    (,) (XEConstructor constructor) fields -> case M.lookup compareString constructor constructors of {
      Nothing -> Nothing;
      Just ((,) tag arity) ->
        if ((tag < 0) || (L.not (G.boundedLength 8 fields) || (L.length fields /= arity)))
        then Nothing
        else case fieldIndex functions name fields 0 Nothing of {
          Nothing -> Nothing;
          Just index -> Just (Escape constructor fields index)
        }
    };
    _ -> Nothing
  };
  forceSeam :: Map XName A.WorkerFunction -> XName -> XErased -> Bool;
  forceSeam functions formal expression = case O.applications expression of {
    (,) (XEPrimitive PIfThenElse) ((:) condition ((:) yes ((:) no []))) -> case condition of {
      XELet alias (XEVar value) body ->
        O.eqName formal value && S.member O.compareName alias (A.demanded functions body);
      _ -> False
    };
    _ -> False
  };
  prefixBranches :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Int ->
                    [] XErasedAlternative -> Maybe ([] ((,) XPattern Prefix));
  prefixBranches constructors functions formal depth branches = case branches of {
    [] -> Just [];
    (:) (XErasedAlternative pattern body) rest ->
      if L.not (checkedPattern constructors pattern) then Nothing
      else case inferPrefix constructors functions formal depth body of {
        Nothing -> Nothing;
        Just first -> case prefixBranches constructors functions formal depth rest of {
          Nothing -> Nothing;
          Just next -> Just ((:) ((,) pattern first) next)
        }
      }
  };
  inferPrefix :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Int -> XErased -> Maybe Prefix;
  inferPrefix constructors functions formal depth expression =
    if forceSeam functions formal expression then Just (PrefixForce expression)
    else case expression of {
      XECase subject branches ->
        if ((depth <= 0) || (L.null branches ||
             (L.not (G.boundedLength 8 branches) || L.not (independent functions formal subject))))
        then Nothing
        else case prefixBranches constructors functions formal (depth - 1) branches of {
          Nothing -> Nothing;
          Just result -> Just (PrefixCase subject result)
        };
      _ -> case escape constructors functions formal expression of {
        Nothing -> Nothing;
        Just terminal -> Just (PrefixEscape terminal)
      }
    };
  terminalCost :: Terminal -> Int;
  terminalCost terminal = case terminal of {
    SelfCall args -> 1 + L.length args + L.sum (L.map (\arg -> 512 - O.remainingSize 512 arg) args);
    Escape constructor fields index -> 1 + L.length fields + L.sum (L.map (\arg -> 512 - O.remainingSize 512 arg) fields)
  };
  -- Exact erased-node prefix cost: case/terminal application spines count.
  -- Force counts if primitive + three applications + full condition, but
  -- excludes its post-force yes/no continuations (bounded by body512).
  prefixCost :: Prefix -> Int;
  prefixCost certificate = case certificate of {
    PrefixCase subject branches -> 1 + (512 - O.remainingSize 512 subject) + L.sum (L.map (\entry -> prefixCost (L.snd entry)) branches);
    PrefixForce expression -> case O.applications expression of {
      (,) head ((:) condition rest) -> 4 + (512 - O.remainingSize 512 condition);
      _ -> 513
    };
    PrefixEscape terminal -> terminalCost terminal
  };
  forceExpressions :: Prefix -> [] XErased;
  forceExpressions certificate = case certificate of {
    PrefixCase subject branches -> L.concatMap (\entry -> forceExpressions (L.snd entry)) branches;
    PrefixForce expression -> (:) expression [];
    PrefixEscape terminal -> []
  };
  selfTerminal :: Map XName A.WorkerFunction -> XName -> XName -> Int -> XErased -> Maybe Terminal;
  selfTerminal functions name binder index expression = case O.applications expression of {
    (,) (XEVar target) args ->
      if L.not (O.eqName name target && independent functions binder (XEVar target)) then Nothing
      else case M.lookup O.compareName name functions of {
        Nothing -> Nothing;
        Just function ->
          if (L.length args /= L.length (A.parameters function)) then Nothing
          else case fieldIndex functions binder args 0 Nothing of {
            Just actual -> if (actual == index) then Just (SelfCall args) else Nothing;
            Nothing -> Nothing
          }
      };
    _ -> Nothing
  };
  deferredBranches :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> XName -> Int ->
                      [] XErasedAlternative -> Maybe ([] ((,) XPattern Terminal));
  deferredBranches constructors functions name binder index branches = case branches of {
    [] -> Just [];
    (:) (XErasedAlternative pattern body) rest ->
      if L.not (checkedPattern constructors pattern) then Nothing
      else let { selected = case selfTerminal functions name binder index body of {
                   Just terminal -> Just terminal;
                   Nothing -> escape constructors functions binder body
                 }
               } in case selected of {
        Nothing -> Nothing;
        Just terminal -> case deferredBranches constructors functions name binder index rest of {
          Nothing -> Nothing;
          Just next -> Just ((:) ((,) pattern terminal) next)
        }
      }
  };
  hasSelf :: [] ((,) XPattern Terminal) -> Bool;
  hasSelf branches = L.any (\entry -> case L.snd entry of { SelfCall args -> True; _ -> False }) branches;
  inferDeferred :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> XName -> Int -> XErased -> Maybe DeferredCase;
  inferDeferred constructors functions name binder index expression = case expression of {
    XECase subject branches ->
      if (L.null branches || (L.not (G.boundedLength 8 branches) || L.not (independent functions binder subject)))
      then Nothing
      else case deferredBranches constructors functions name binder index branches of {
        Just result -> if hasSelf result then Just (DeferredCase subject result) else Nothing;
        Nothing -> Nothing
      };
    _ -> Nothing
  };
  isSuspended :: XErased -> Bool;
  isSuspended expression = case expression of {
    XEVar name -> False; XEInt n -> False; XEDouble n -> False; XEBool b -> False;
    XEString s -> False; XEPrimitive p -> False; XEConstructor c -> False; XEAbs n b -> False;
    XELetRec definitions body -> False;
    _ -> case O.applications expression of { (,) (XEConstructor constructor) args -> False; _ -> True }
  };
  pureRecipe :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XErased -> Bool;
  pureRecipe constructors functions expression = case G.safetyScan constructors functions expression of {
    Nothing -> False;
    Just edges -> case G.safetyCollect constructors functions (S.toList edges) 64 8192 M.empty of {
      Nothing -> False;
      Just graph -> True
    }
  };
  data RecipeSite = RecipeSite XName XErased ([] XName) DeferredCase;
  recipeSite :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> XName -> Int ->
                XName -> XErased -> XErased -> Maybe RecipeSite;
  recipeSite constructors functions name formal index binder rhs body =
    if (L.not (G.boundedTree 64 rhs && isSuspended rhs) ||
        (L.not (G.boundedNeeds functions rhs) || S.member O.compareName binder (A.demanded functions body)))
    then Nothing
    else let { captures = S.toList (A.needed functions rhs) } in
      if ((L.length captures /= 2) ||
          (L.not (L.any (O.eqName formal) captures) || L.any (O.eqName binder) captures))
      then Nothing
      else if L.not (pureRecipe constructors functions rhs) then Nothing
      else case inferDeferred constructors functions name binder index body of {
        Nothing -> Nothing;
        Just certificate -> Just (RecipeSite binder rhs captures certificate)
      };
  -- Search only evaluated continuation structure below the force seam.
  -- Never descend into a let RHS, lambda, recursive group, call or field.
  sites :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> XName -> Int -> XErased -> [] RecipeSite;
  sites constructors functions name formal index expression = case expression of {
    XELet binder rhs body ->
      let { rest = sites constructors functions name formal index body } in
      case recipeSite constructors functions name formal index binder rhs body of {
        Nothing -> rest;
        Just site -> (:) site rest
      };
    XECase subject branches -> L.concatMap (\(XErasedAlternative pattern body) -> sites constructors functions name formal index body) branches;
    _ -> case O.applications expression of {
      (,) (XEPrimitive PIfThenElse) ((:) condition ((:) yes ((:) no []))) ->
        L.append (sites constructors functions name formal index yes) (sites constructors functions name formal index no);
      _ -> []
    }
  };
  inferParameter :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> A.WorkerFunction ->
                    XName -> Int -> Maybe ProducerPlan;
  inferParameter constructors functions name function formal index =
    if S.member O.compareName formal (A.strict function) then Nothing
    else case inferPrefix constructors functions formal 4 (A.functionBody function) of {
      Nothing -> Nothing;
      Just certificate ->
        if (prefixCost certificate > 64) then Nothing
        else case forceExpressions certificate of {
          (:) continuation [] -> case sites constructors functions name formal index continuation of {
            (:) (RecipeSite binder rhs captures deferred) [] ->
              Just (ProducerPlan name formal index binder rhs captures certificate deferred);
            _ -> Nothing
          };
          _ -> Nothing
        }
    };
  inferParameters :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> A.WorkerFunction ->
                     [] XName -> Int -> Maybe ProducerPlan;
  inferParameters constructors functions name function remaining index = case remaining of {
    [] -> Nothing;
    (:) formal rest -> case inferParameter constructors functions name function formal index of {
      Just result -> Just result;
      Nothing -> inferParameters constructors functions name function rest (index + 1)
    }
  };
  infer :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> XName -> Maybe ProducerPlan;
  infer constructors functions name =
    if (M.size functions > 4096) then Nothing
    else case M.lookup O.compareName name functions of {
      Nothing -> Nothing;
      Just function ->
        if L.not (G.boundedTree 512 (A.functionBody function) &&
                  (G.boundedLength 16 (A.parameters function) && G.boundedLength 512 (A.captures function)))
        then Nothing
        else if L.not (G.canonicalSafe constructors functions name) then Nothing
        else inferParameters constructors functions name function (A.parameters function) 0
    };
  planVisit :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName ->
               [] ((,) XName A.WorkerFunction) -> Int -> Int -> Set XName -> Map XName ProducerPlan -> Map XName ProducerPlan;
  planVisit constructors functions excluded entries attempts remainingNodes binders admitted =
    if ((attempts <= 0) || (M.size admitted >= 32)) then admitted
    else case entries of {
      [] -> admitted;
      (:) ((,) name function) rest ->
        if S.member O.compareName name excluded
        then planVisit constructors functions excluded rest attempts remainingNodes binders admitted
        else case infer constructors functions name of {
          Nothing -> planVisit constructors functions excluded rest (attempts - 1) remainingNodes binders admitted;
          Just info -> let { cost = 512 - O.remainingSize 512 (A.functionBody function) } in
            if ((cost > remainingNodes) || S.member O.compareName (recipeBinder info) binders)
            then planVisit constructors functions excluded rest (attempts - 1) remainingNodes binders admitted
            else planVisit constructors functions excluded rest (attempts - 1) (remainingNodes - cost)
              (S.insert O.compareName (recipeBinder info) binders)
              (M.insert O.compareName name info admitted)
        }
    };
  -- Supplied exclusions include numeric/result/incompatible entry families.
  -- ST uses unchanged separate routing; the pure safety whitelist rejects
  -- ST/IO/run/bind primitives. A dynamic state-worker cache is NOT a proof.
  -- No emitter-time inference, new modes, or cross-product clone discovery.
  plan :: Map String ((,) Int Int) -> Map XName A.WorkerFunction -> Set XName -> XErased -> Map XName ProducerPlan;
  plan constructors functions excluded term =
    if ((M.size functions > 4096) || L.not (G.boundedTree 262144 term)) then M.empty
    else planVisit constructors functions excluded (M.toList functions) 256 8192 S.empty M.empty
}
