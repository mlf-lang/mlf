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
                       List (Triple EvidenceRole XName XType) -> XType -> Either String XTerm;
  resolveDictionary datatypes gamma candidates wanted =
    do {
      let {
        proofs = closeGiven datatypes gamma candidates Nil (givenSeeds candidates)
      };
      term <- search datatypes gamma candidates proofs Nil wanted;
      let {
        terms =
          M.fromList X.compareName
            (map
               (\candidate ->
                  case candidate of {
                    Triple _ name ty -> Pair name ty
                  })
               candidates)
      };
      actual <- Check.inferWithData datatypes (XEnv gamma terms) term;
      unless (T.alphaEq actual wanted) (Left "dictionary evidence has the wrong type");
      Right term
    };
  givenSeeds :: List (Triple EvidenceRole XName XType) -> List (Triple XTerm XType (Set XName));
  givenSeeds Nil = Nil;
  givenSeeds (Cons (Triple role name ty) rest) =
    if sameRole role GivenEvidence
    then Cons (Triple (XVarTerm name) ty Set.empty) (givenSeeds rest)
    else givenSeeds rest;
  candidatePairs role candidates =
    map
      (\candidate ->
         case candidate of {
           Triple _ name ty -> Pair name ty
         })
      (filter
         (\candidate ->
            case candidate of {
              Triple r _ _ -> sameRole role r
            })
         candidates);
  search :: DataEnv ->
            Map XTyVar XType ->
            List (Triple EvidenceRole XName XType) ->
            List (Pair XTerm XType) -> List XType -> XType -> Either String XTerm;
  search datatypes gamma candidates proofs seen goal =
    if any (T.alphaEq goal) seen
    then Left ("cyclic dictionary resolution: " ++ Pretty.prettyType goal)
    else case matches datatypes gamma candidates GivenEvidence goal of {
           Cons (Pair term Nil) _ -> Right term;
           _ ->
             case find (\proof -> T.alphaEq goal (snd proof)) proofs of {
               Just proof -> Right (fst proof);
               Nothing ->
                 case matches datatypes gamma candidates InstanceEvidence goal of {
                   Nil ->
                     Left
                       ("no instance or given constraint for " ++
                        (Pretty.prettyType goal ++ "; ambiguous uses need a type annotation"));
                   Cons (Pair term context) Nil ->
                     foldM
                       (\f predicate ->
                          do {
                            proof <-
                              search datatypes gamma candidates proofs (Cons goal seen) predicate;
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
                List (Triple EvidenceRole XName XType) ->
                List XType -> List (Triple XTerm XType (Set XName)) -> List (Pair XTerm XType);
  closeGiven _ _ _ _ Nil = Nil;
  closeGiven datatypes gamma candidates seen (Cons (Triple proof ty path) rest) =
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
         Cons (Pair proof ty)
           (closeGiven datatypes gamma candidates (Cons ty seen) (append rest projections));
  superclassArgument :: forall a p. List a -> p -> Either String a;
  superclassArgument context _ =
    case context of {
      Cons argument Nil -> Right argument;
      _ -> Left "superclass selectors require exactly one dictionary"
    };
  projectGiven :: DataEnv ->
                  Map XTyVar XType ->
                  XTerm ->
                  XType -> Set XName -> Pair XName XType -> Maybe (Triple XTerm XType (Set XName));
  projectGiven datatypes gamma proof ty path candidate =
    case specializeAt datatypes gamma superclassArgument ty candidate of {
      Left _ -> Nothing;
      Right (Triple selector context result) ->
        case context of {
          Cons argument Nil ->
            if T.alphaEq argument ty
            then Just
                   (Triple (XApp selector proof) result
                      (Set.insert X.compareName (fst candidate) path))
            else Nothing;
          _ -> Nothing
        }
    };
  matches :: DataEnv ->
             Map XTyVar XType ->
             List (Triple EvidenceRole XName XType) ->
             EvidenceRole -> XType -> List (Pair XTerm (List XType));
  matches datatypes gamma candidates role goal =
    catMaybes (map (specialize datatypes gamma goal) (candidatePairs role candidates));
  specialize :: DataEnv ->
                Map XTyVar XType -> XType -> Pair XName XType -> Maybe (Pair XTerm (List XType));
  specialize datatypes gamma goal candidate =
    case specializeAt datatypes gamma (\_ head -> Right head) goal candidate of {
      Left _ -> Nothing;
      Right (Triple term context _) -> Just (Pair term context)
    };
  bottomKind :: XType -> Maybe Kind;
  bottomKind XBot = Just Star;
  bottomKind (XBotKind kind) = Just kind;
  bottomKind _ = Nothing;
  quantifiers :: XType -> Pair (List (Pair XTyVar Kind)) XType;
  quantifiers ty =
    case ty of {
      XForall variable bound body ->
        case bottomKind bound of {
          Nothing -> Pair Nil ty;
          Just kind ->
            let {
              rest = quantifiers body
            } in
            Pair (Cons (Pair variable kind) (fst rest)) (snd rest)
        };
      _ -> Pair Nil ty
    };
  arguments :: XType -> Pair (List XType) XType;
  arguments (XArrow domain result) =
    let {
      rest = arguments result
    } in
    Pair (Cons domain (fst rest)) (snd rest);
  arguments ty = Pair Nil ty;
  freshVariables :: Int -> Int -> Set XTyVar -> List XTyVar;
  freshVariables count candidate occupied =
    if (count <= 0)
    then Nil
    else let {
           variable = XTyVar candidate
         } in
         if Set.member T.compareTyVar variable occupied
         then freshVariables count (candidate - 1) occupied
         else Cons variable (freshVariables (count - 1) (candidate - 1) occupied);
  replaceType variables fresh types ty =
    let {
      renamed =
        foldl
          (\body binding ->
             case binding of {
               Pair (Pair variable _) name -> T.substitute variable (XVar name) body
             })
          ty
          (zip variables fresh)
    } in
    foldl (\body binding -> T.substitute (fst binding) (snd binding) body) renamed
      (zip fresh types);
  specializeAt :: DataEnv ->
                  Map XTyVar XType ->
                  (List XType -> XType -> Either String XType) ->
                  XType -> Pair XName XType -> Either String (Triple XTerm (List XType) XType);
  specializeAt datatypes gamma select actual candidate =
    case candidate of {
      Pair name scheme ->
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
          Right (Triple term (map replace context) (replace head))
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
      Just (Pair f a) ->
        case T.applicationView actual of {
          Nothing -> Left "instance head does not match";
          Just (Pair g b) ->
            do {
              current <- match datatypes gamma flexible substitution f g;
              match datatypes gamma flexible current a b
            }
        }
    }
}
