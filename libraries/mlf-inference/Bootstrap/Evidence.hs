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
  resolveDictionary :: DataEnv ->
                       Map XTyVar XType ->
                       [] ((,,) EvidenceRole XName XType) -> XType -> Either String XTerm;
  resolveDictionary datatypes gamma candidates wanted =
    do {
      let {
        proofs = closeGiven datatypes gamma candidates [] (givenSeeds candidates)
      };
      term <- search datatypes gamma candidates proofs [] wanted;
      let {
        terms =
          M.fromList X.compareName
            (map
               (\candidate ->
                  case candidate of {
                    (,,) _ name ty -> (,) name ty
                  })
               candidates)
      };
      actual <- Check.inferWithData datatypes (XEnv gamma terms) term;
      unless (T.alphaEq actual wanted) (Left "dictionary evidence has the wrong type");
      Right term
    };
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
  search :: DataEnv ->
            Map XTyVar XType ->
            [] ((,,) EvidenceRole XName XType) ->
            [] ((,) XTerm XType) -> [] XType -> XType -> Either String XTerm;
  search datatypes gamma candidates proofs seen goal =
    if any (T.alphaEq goal) seen
    then Left ("cyclic dictionary resolution: " ++ Pretty.prettyType goal)
    else case matches datatypes gamma candidates GivenEvidence goal of {
           (:) ((,) term []) _ -> Right term;
           _ ->
             case find (\proof -> T.alphaEq goal (snd proof)) proofs of {
               Just proof -> Right (fst proof);
               Nothing ->
                 case matches datatypes gamma candidates InstanceEvidence goal of {
                   [] ->
                     Left
                       ("no instance or given constraint for " ++
                        (Pretty.prettyType goal ++ "; ambiguous uses need a type annotation"));
                   (:) ((,) term context) [] ->
                     foldM
                       (\f predicate ->
                          do {
                            proof <-
                              search datatypes gamma candidates proofs ((:) goal seen) predicate;
                            Right (XApp f proof)
                          })
                       term
                       context;
                   _ -> Left ("overlapping dictionary instances: " ++ Pretty.prettyType goal)
                 }
             }
         };
  closeGiven :: DataEnv ->
                Map XTyVar XType ->
                [] ((,,) EvidenceRole XName XType) ->
                [] XType -> [] ((,,) XTerm XType (Set XName)) -> [] ((,) XTerm XType);
  closeGiven _ _ _ _ [] = [];
  closeGiven datatypes gamma candidates seen ((:) ((,,) proof ty path) rest) =
    if any (T.alphaEq ty) seen
    then closeGiven datatypes gamma candidates seen rest
    else let {
           selectors =
             filter (\candidate -> not (Set.member X.compareName (fst candidate) path))
               (candidatePairs SuperclassEvidence candidates)
         } in
         let {
           projections = catMaybes (map (projectGiven datatypes gamma proof ty path) selectors)
         } in
         (:) ((,) proof ty)
           (closeGiven datatypes gamma candidates ((:) ty seen) (append rest projections));
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
    catMaybes (map (specialize datatypes gamma goal) (candidatePairs role candidates));
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
