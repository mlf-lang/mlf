-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Evidence where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Pretty as Pretty;
  sameRole :: EvidenceRole -> EvidenceRole -> Bool;
  sameRole GivenEvidence GivenEvidence = True;
  sameRole SuperclassEvidence SuperclassEvidence = True;
  sameRole InstanceEvidence InstanceEvidence = True;
  sameRole _ _ = False;
  data EvidenceFailure = NoEntailment String | InvalidEvidence String;
  evidenceFailureMessage :: EvidenceFailure -> String;
  evidenceFailureMessage failure = case failure of {
    NoEntailment message -> message;
    InvalidEvidence message -> message
  };
  resolveDictionary :: DataEnv -> Map XTyVar XType ->
    [] ((,,) EvidenceRole XName XType) -> XType -> Either String XTerm;
  resolveDictionary datatypes gamma candidates wanted =
    case resolveDictionaryDetailed datatypes gamma candidates wanted of {
      Left failure -> Left (evidenceFailureMessage failure);
      Right term -> Right term
    };
  resolveDictionaryDetailed :: DataEnv ->
                       Map XTyVar XType ->
                       [] ((,,) EvidenceRole XName XType) -> XType -> Either EvidenceFailure XTerm;
  resolveDictionaryDetailed datatypes gamma candidates =
    dictionaryResolver datatypes gamma candidates (\_ -> candidatePairs InstanceEvidence candidates);
  -- Keep the complete environment for the independent proof checker. For a
  -- repeated scope, its types, superclass closure and checker are shared.
  candidateTerms candidates =
    M.fromList X.compareName (map (\((,,) _ name ty) -> (,) name ty) candidates);
  dictionaryResolver datatypes gamma candidates instances =
    proveDictionary datatypes gamma (candidatePairs GivenEvidence candidates)
      (candidatePairs SuperclassEvidence candidates) instances
      (Check.checkerIn datatypes (XEnv gamma (candidateTerms candidates)));
  proveDictionary datatypes gamma givens selectors instances checked = let {
    seeds = map (\((,) name ty) -> (,,) (XVarTerm name) ty Set.empty) givens;
    proofs = closeGivenWith datatypes gamma selectors [] seeds
  } in \wanted -> do {
    term <- searchWith datatypes gamma givens instances proofs [] wanted;
    actual <- case checked of {
      Left message -> Left (InvalidEvidence message);
      Right check -> case check term of {
        Left message -> Left (InvalidEvidence message);
        Right ty -> Right ty
      }
    };
    unless (T.alphaEq actual wanted) (Left (InvalidEvidence "dictionary evidence has the wrong type"));
    Right term
  };
  -- Two visibly different constructor heads cannot unify. Flexible or
  -- application-shaped heads remain available for every lookup. A bucket
  -- affects only instance search, which requires exactly one matching row.
  indexedResolver datatypes gamma candidates = dictionaryResolver datatypes gamma candidates
    (instanceLookup (candidatePairs InstanceEvidence candidates));
  instanceLookup instances = let {
    concrete ty = case ty of {
      XCon cls ((:) (XCon constructor _) _) -> Just ((,) cls constructor);
      _ -> Nothing
    };
    compareKey ((,) c t) ((,) d u) = let { order = compareString c d } in
      if order == 0 then compareString t u else order;
    group ordinal rows index rest = case rows of {
      [] -> (,) (M.map reverse index) (reverse rest);
      (:) pair remaining -> let {
        row = (,) ordinal pair;
        next = ordinal + 1;
        head = snd (arguments (snd (quantifiers (snd pair))))
      } in seq next (case concrete head of {
        Just key -> let { updated = M.insertWith compareKey append key [row] index } in
          seq updated (group next remaining updated rest);
        Nothing -> group next remaining index ((:) row rest)
      })
    };
    grouped = group 0 instances M.empty [];
    forGoal goal = case concrete goal of {
      Nothing -> instances;
      Just key -> let { bucket = M.findWithDefault compareKey [] key (fst grouped) } in
        map snd (mergeBy (\a b -> compareInt (fst a) (fst b)) bucket (snd grouped))
    }
  } in forGoal;
  -- This resolver belongs to one immutable module scope in one solved graph.
  -- Its ordering and membership are independent of a request's type binders
  -- and lexical parameters. Only those parameters change on scope entry.
  scopedResolver datatypes globals = let {
    instances = instanceLookup (candidatePairs InstanceEvidence globals);
    givens = candidatePairs GivenEvidence globals;
    selectors = candidatePairs SuperclassEvidence globals;
    terms = candidateTerms globals;
    inTypes gamma = let {
      check = Check.checkerWithEarlierBindings datatypes (XEnv gamma terms);
      base = proveDictionary datatypes gamma givens selectors instances (check M.empty)
    } in \locals -> case locals of {
      [] -> base;
      _ -> let { localInstances = candidatePairs InstanceEvidence locals } in
        proveDictionary datatypes gamma
          (append (candidatePairs GivenEvidence locals) givens)
          (append (candidatePairs SuperclassEvidence locals) selectors)
          (\goal -> append localInstances (instances goal))
          (check (candidateTerms locals))
    };
    closed = inTypes M.empty
  } in \gamma -> if M.null gamma then closed else inTypes gamma;
  givenSeeds :: [] ((,,) EvidenceRole XName XType) -> [] ((,,) XTerm XType (Set XName));
  givenSeeds [] = [];
  givenSeeds ((:) ((,,) role name ty) rest) =
    if sameRole role GivenEvidence
    then (:) ((,,) (XVarTerm name) ty Set.empty) (givenSeeds rest)
    else givenSeeds rest;
  candidatePairs role candidates =
    map
      (\candidate ->
         case candidate of {
           (,,) _ name ty -> (,) name ty
         })
      (filter
         (\candidate ->
            case candidate of {
              (,,) r _ _ -> sameRole role r
            })
         candidates);
  search :: DataEnv -> Map XTyVar XType ->
    [] ((,,) EvidenceRole XName XType) -> [] ((,) XTerm XType) ->
    [] XType -> XType -> Either String XTerm;
  search datatypes gamma candidates proofs seen goal =
    case searchDetailed datatypes gamma candidates proofs seen goal of {
      Left failure -> Left (evidenceFailureMessage failure);
      Right term -> Right term
    };
  searchDetailed :: DataEnv ->
            Map XTyVar XType ->
            [] ((,,) EvidenceRole XName XType) ->
            [] ((,) XTerm XType) -> [] XType -> XType -> Either EvidenceFailure XTerm;
  searchDetailed datatypes gamma candidates = searchWith datatypes gamma
    (candidatePairs GivenEvidence candidates) (\_ -> candidatePairs InstanceEvidence candidates);
  searchWith datatypes gamma givens instances proofs seen goal =
    if any (T.alphaEq goal) seen
    then Left (NoEntailment ("cyclic dictionary resolution: " ++ Pretty.prettyType goal))
    else case matching datatypes gamma givens goal of {
           (:) ((,) term []) _ -> Right term;
           _ ->
             case find (\proof -> T.alphaEq goal (snd proof)) proofs of {
               Just proof -> Right (fst proof);
               Nothing ->
                 case matching datatypes gamma (instances goal) goal of {
                   [] ->
                     Left
                       (NoEntailment ("no instance or given constraint for " ++
                        (Pretty.prettyType goal ++ "; ambiguous uses need a type annotation")));
                   (:) ((,) term context) [] ->
                     foldM
                       (\f predicate ->
                          do {
                            proof <-
                              searchWith datatypes gamma givens instances proofs ((:) goal seen) predicate;
                            Right (XApp f proof)
                          })
                       term
                       context;
                   _ -> Left (NoEntailment ("overlapping dictionary instances: " ++ Pretty.prettyType goal))
                 }
             }
         };
  closeGiven :: DataEnv ->
                Map XTyVar XType ->
                [] ((,,) EvidenceRole XName XType) ->
                [] XType -> [] ((,,) XTerm XType (Set XName)) -> [] ((,) XTerm XType);
  closeGiven datatypes gamma candidates = closeGivenWith datatypes gamma
    (candidatePairs SuperclassEvidence candidates);
  closeGivenWith _ _ _ _ [] = [];
  closeGivenWith datatypes gamma available seen ((:) ((,,) proof ty path) rest) =
    if any (T.alphaEq ty) seen
    then closeGivenWith datatypes gamma available seen rest
    else let {
           selectors =
             filter (\candidate -> not (Set.member X.compareName (fst candidate) path))
               available
         } in
         let {
           projections = catMaybes (map (projectGiven datatypes gamma proof ty path) selectors)
         } in
         (:) ((,) proof ty)
           (closeGivenWith datatypes gamma available ((:) ty seen) (append rest projections));
  superclassArgument :: forall a p. [] a -> p -> Either String a;
  superclassArgument context _ =
    case context of {
      (:) argument [] -> Right argument;
      _ -> Left "superclass selectors require exactly one dictionary"
    };
  projectGiven :: DataEnv ->
                  Map XTyVar XType ->
                  XTerm ->
                  XType -> Set XName -> (,) XName XType -> Maybe ((,,) XTerm XType (Set XName));
  projectGiven datatypes gamma proof ty path candidate =
    case specializeAt datatypes gamma superclassArgument ty candidate of {
      Left _ -> Nothing;
      Right ((,,) selector context result) ->
        case context of {
          (:) argument [] ->
            if T.alphaEq argument ty
            then Just
                   ((,,) (XApp selector proof) result
                      (Set.insert X.compareName (fst candidate) path))
            else Nothing;
          _ -> Nothing
        }
    };
  matches :: DataEnv ->
             Map XTyVar XType ->
             [] ((,,) EvidenceRole XName XType) ->
             EvidenceRole -> XType -> [] ((,) XTerm ([] XType));
  matches datatypes gamma candidates role goal =
    matching datatypes gamma (candidatePairs role candidates) goal;
  matching datatypes gamma pairs goal = catMaybes (map (specialize datatypes gamma goal) pairs);
  specialize :: DataEnv ->
                Map XTyVar XType -> XType -> (,) XName XType -> Maybe ((,) XTerm ([] XType));
  specialize datatypes gamma goal candidate =
    case specializeAt datatypes gamma (\_ head -> Right head) goal candidate of {
      Left _ -> Nothing;
      Right ((,,) term context _) -> Just ((,) term context)
    };
  bottomKind :: XType -> Maybe Kind;
  bottomKind XBot = Just Star;
  bottomKind (XBotKind kind) = Just kind;
  bottomKind _ = Nothing;
  quantifiers :: XType -> (,) ([] ((,) XTyVar Kind)) XType;
  quantifiers ty =
    case ty of {
      XForall variable bound body ->
        case bottomKind bound of {
          Nothing -> (,) [] ty;
          Just kind ->
            let {
              rest = quantifiers body
            } in
            (,) ((:) ((,) variable kind) (fst rest)) (snd rest)
        };
      _ -> (,) [] ty
    };
  arguments :: XType -> (,) ([] XType) XType;
  arguments (XArrow domain result) =
    let {
      rest = arguments result
    } in
    (,) ((:) domain (fst rest)) (snd rest);
  arguments ty = (,) [] ty;
  freshVariables :: Int -> Int -> Set XTyVar -> [] XTyVar;
  freshVariables count candidate occupied =
    if (count <= 0)
    then []
    else let {
           variable = XTyVar candidate
         } in
         if Set.member T.compareTyVar variable occupied
         then freshVariables count (candidate - 1) occupied
         else (:) variable (freshVariables (count - 1) (candidate - 1) occupied);
  replaceType variables fresh types ty =
    let {
      renamed =
        foldl
          (\body binding ->
             case binding of {
               (,) ((,) variable _) name -> T.substitute variable (XVar name) body
             })
          ty
          (zip variables fresh)
    } in
    foldl (\body binding -> T.substitute (fst binding) (snd binding) body) renamed
      (zip fresh types);
  specializeAt :: DataEnv ->
                  Map XTyVar XType ->
                  ([] XType -> XType -> Either String XType) ->
                  XType -> (,) XName XType -> Either String ((,,) XTerm ([] XType) XType);
  specializeAt datatypes gamma select actual candidate =
    case candidate of {
      (,) name scheme ->
        do {
          let {
            quantified = quantifiers scheme
          };
          let {
            variables = fst quantified
          };
          let {
            body = snd quantified
          };
          let {
            decomposed = arguments body
          };
          let {
            context = fst decomposed
          };
          let {
            head = snd decomposed
          };
          let {
            flexible = M.fromList T.compareTyVar variables
          };
          pattern <- select context head;
          substitution <- match datatypes gamma flexible M.empty pattern actual;
          types <-
            mapM
              (\variable ->
                 case M.lookup T.compareTyVar (fst variable) substitution of {
                   Nothing -> Left "undetermined instance parameter";
                   Just ty -> Right ty
                 })
              variables;
          let {
            occupied = foldl (Set.union T.compareTyVar) (T.allVars body) (map T.allVars types)
          };
          let {
            fresh = freshVariables (length variables) (-1) occupied
          };
          let {
            replace = replaceType variables fresh types
          };
          let {
            term =
              foldl (\function argument -> X.instantiate function (X.typeApplication argument))
                (XVarTerm name)
                types
          };
          Right ((,,) term (map replace context) (replace head))
        }
    };
  match :: DataEnv ->
           Map XTyVar XType ->
           Map XTyVar Kind ->
           Map XTyVar XType -> XType -> XType -> Either String (Map XTyVar XType);
  match datatypes gamma flexible substitution pattern actual =
    case pattern of {
      XVar variable ->
        case M.lookup T.compareTyVar variable flexible of {
          Just expectedKind ->
            do {
              kind <- T.kindOf datatypes gamma actual;
              unless (K.eqKind kind expectedKind) (Left "instance parameter kind mismatch");
              case M.lookup T.compareTyVar variable substitution of {
                Nothing -> Right (M.insert T.compareTyVar variable actual substitution);
                Just previous ->
                  if T.alphaEq previous actual
                  then Right substitution
                  else Left "instance parameter mismatch"
              }
            };
          Nothing -> matchStructure datatypes gamma flexible substitution pattern actual
        };
      _ -> matchStructure datatypes gamma flexible substitution pattern actual
    };
  matchStructure :: DataEnv ->
                    Map XTyVar XType ->
                    Map XTyVar Kind ->
                    Map XTyVar XType -> XType -> XType -> Either String (Map XTyVar XType);
  matchStructure datatypes gamma flexible substitution pattern actual =
    if (T.alphaEq pattern actual &&
        not
          (any (\variable -> M.member T.compareTyVar variable flexible)
             (Set.toList (T.freeVars pattern))))
    then Right substitution
    else case pattern of {
           XCon c xs ->
             case actual of {
               XCon d ys ->
                 if (eqString c d && (length xs == length ys))
                 then foldM
                        (\current pair ->
                           match datatypes gamma flexible current (fst pair) (snd pair))
                        substitution
                        (zip xs ys)
                 else matchApplication datatypes gamma flexible substitution pattern actual;
               _ -> matchApplication datatypes gamma flexible substitution pattern actual
             };
           XArrow a b ->
             case actual of {
               XArrow c d ->
                 do {
                   current <- match datatypes gamma flexible substitution a c;
                   match datatypes gamma flexible current b d
                 };
               _ -> matchApplication datatypes gamma flexible substitution pattern actual
             };
           _ -> matchApplication datatypes gamma flexible substitution pattern actual
         };
  matchApplication :: DataEnv ->
                      Map XTyVar XType ->
                      Map XTyVar Kind ->
                      Map XTyVar XType -> XType -> XType -> Either String (Map XTyVar XType);
  matchApplication datatypes gamma flexible substitution pattern actual =
    case T.applicationView pattern of {
      Nothing -> Left "instance head does not match";
      Just ((,) f a) ->
        case T.applicationView actual of {
          Nothing -> Left "instance head does not match";
          Just ((,) g b) ->
            do {
              current <- match datatypes gamma flexible substitution f g;
              match datatypes gamma flexible current a b
            }
        }
    }
}
