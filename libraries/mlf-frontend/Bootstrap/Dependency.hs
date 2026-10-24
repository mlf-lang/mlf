-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Dependency where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Desugar as Desugar;
  -- Edges point from a declaration to the declarations it needs. Namespace
  -- imports and type observations deliberately do not become value SCC edges.
  data Observation = Observation (List String) (List String) (List String) (List String);
  lexicalValueName name = if stringLength name >= 11 && eqString (stringSlice name 0 11) "$MLF.Infix." then stringSlice name 11 (stringLength name - 11) else name;
  valueNames (Observation values _ _ _) = values;
  typeNames (Observation _ types _ _) = types;
  constructorNames (Observation _ _ constructors _) = constructors;
  classNames (Observation _ _ _ classes) = classes;
  emptyObservation = Observation Nil Nil Nil Nil;
  merge (Observation a b c d) (Observation w x y z) =
    Observation (append a w) (append b x) (append c y) (append d z);
  mergeMany observations = foldlStrict merge emptyObservation observations;
  canonical names = S.toList (S.fromList compareString names);
  normalize (Observation a b c d) =
    Observation (canonical a) (canonical b) (canonical c) (canonical d);
  without values bound = filter (\n -> not (S.member compareString n bound)) values;
  bindObservation bound (Observation values types constructors classes) =
    Observation (without values bound) types constructors classes;
  observeType :: SType -> Observation;
  observeType ty =
    case ty of {
      SArrow a b -> merge (observeType a) (observeType b);
      SCon n args ->
        merge (Observation Nil (Cons n Nil) Nil Nil) (mergeMany (map observeType args));
      STypeApp a b -> merge (observeType a) (observeType b);
      SForall _ _ a b -> merge (observeType a) (observeType b);
      SQualified predicates body ->
        merge (mergeMany (map observePredicate predicates)) (observeType body);
      _ -> emptyObservation
    };
  observePredicate :: SPredicate -> Observation;
  observePredicate (SPredicate n args) =
    merge (Observation Nil Nil Nil (Cons n Nil)) (mergeMany (map observeType args));
  observeAnnotation (SAnnotation _ ty) = observeType ty;
  observeOptional value =
    case value of {
      Nothing -> emptyObservation;
      Just a -> observeAnnotation a
    };
  observePattern :: SPattern -> Observation;
  observePattern pattern =
    case pattern of {
      SAsPattern _ inner -> observePattern inner;
      SLazyPattern inner -> observePattern inner;
      SOverloadedStringPattern _ equality conversion ->
        Observation (Cons (lexicalValueName equality) (Cons (lexicalValueName conversion) Nil)) Nil Nil Nil;
      SConstructorPattern n _ -> Observation Nil Nil (Cons n Nil) Nil;
      SNestedPattern n ps ->
        merge (Observation Nil Nil (Cons n Nil) Nil) (mergeMany (map observePattern ps));
      SAnnotatedPattern _ a -> observeAnnotation a;
      _ -> emptyObservation
    };
  observeExpression :: SExpr -> Observation;
  observeExpression expression =
    case expression of {
      SCallSite _ _ body -> observeExpression body;
      SSharedBind pattern action body binding failure ->
        merge (observePattern pattern)
          (merge (bindObservation (S.fromList compareString (Desugar.patternVariables pattern)) (observeExpression body))
            (mergeMany (map observeExpression (Cons action (Cons binding (Cons failure Nil))))));
      SVar n -> Observation (Cons (lexicalValueName n) Nil) Nil Nil Nil;
      SConstructor n -> Observation Nil Nil (Cons n Nil) Nil;
      SLam n a b ->
        merge (observeOptional a) (bindObservation (S.singleton n) (observeExpression b));
      SApp a b -> merge (observeExpression a) (observeExpression b);
      SLet n a b ->
        merge (observeExpression a) (bindObservation (S.singleton n) (observeExpression b));
      SAnn a t -> merge (observeExpression a) (observeAnnotation t);
      SCase a branches ->
        merge (observeExpression a)
          (mergeMany
             (map
                (\(SAlternative p b) ->
                   merge (observePattern p)
                     (bindObservation (S.fromList compareString (Desugar.patternVariables p))
                        (observeExpression b)))
                branches));
      SEquations rows ->
        mergeMany
          (map
             (\(Pair ps b) ->
                merge (mergeMany (map observePattern ps))
                  (bindObservation
                     (S.fromList compareString (concatMap Desugar.patternVariables ps))
                     (observeExpression b)))
             rows);
      SDo _ _ -> observeExpression (Desugar.desugarDo expression);
      SLetRec declarations body ->
        bindObservation (S.fromList compareString (map (\(Triple n _ _) -> n) declarations))
          (merge (observeExpression body)
             (mergeMany
                (map (\(Triple _ a b) -> merge (observeAnnotation a) (observeExpression b))
                   declarations)));
      SWanted dictionary candidates ->
        Observation (map snd candidates) (Cons dictionary Nil) Nil Nil;
      SChecked ty b -> merge (observeType ty) (observeExpression b);
      _ -> emptyObservation
    };
  observeDeclaration (Triple _ annotation body) =
    normalize (merge (observeOptional annotation) (observeExpression body));
  declarationObservations values =
    M.fromList compareString
      (map
         (\declaration ->
            case declaration of {
              Triple n _ _ -> Pair n (observeDeclaration declaration)
            })
         values);
  declarationEdges values =
    map
      (\declaration ->
         case declaration of {
           Triple n _ _ -> Pair n (valueNames (observeDeclaration declaration))
         })
      values;
  observeField :: Field -> Observation;
  observeField field =
    case field of {
      Function a b -> merge (observeField a) (observeField b);
      Applied n args ->
        merge (Observation Nil (Cons n Nil) Nil Nil) (mergeMany (map observeField args));
      Application a b -> merge (observeField a) (observeField b);
      Quantified _ _ body -> observeField body;
      _ -> emptyObservation
    };
  observeDatatype declaration =
    let {
      constructors =
        case declaration of {
          DataDecl _ _ cs -> cs;
          DataDeclK _ _ cs -> cs
        }
    } in
    normalize
      (mergeMany (concatMap (\(ConstructorDecl _ fields) -> map observeField fields) constructors));
  observeClass (SClassDecl _ _ supers methods) =
    normalize
      (merge (mergeMany (map observePredicate supers))
         (mergeMany (map (\(Pair _ ty) -> observeType ty) methods)));
  observeInstance (SInstanceDecl _ context name head methods) =
    normalize
      (merge (observePredicate (SPredicate name head))
         (merge (mergeMany (map observePredicate context))
            (mergeMany (map (\(Pair _ expression) -> observeExpression expression) methods))));
  data Visit = Enter String | Leave String;
  -- Kosaraju with indexed adjacency maps and explicit work lists. Each vertex
  -- and edge is visited a constant number of times; map/set work is logarithmic.
  -- Sorting roots, edges and component members makes source ordering irrelevant.
  adjacency :: List (Pair String (List String)) -> Map String (List String);
  adjacency entries =
    let {
      names = S.fromList compareString (map fst entries)
    } in
    M.fromList compareString
      (map
         (\(Pair n deps) -> Pair n (canonical (filter (\d -> S.member compareString d names) deps)))
         entries);
  transpose :: Map String (List String) -> Map String (List String);
  transpose graph =
    M.map canonical
      (foldlStrict
         (\acc entry ->
            foldlStrict
              (\state dependency ->
                 M.insertWith compareString append dependency (Cons (fst entry) Nil) state)
              acc
              (snd entry))
         (M.map (\_ -> Nil) graph)
         (M.toList graph));
  finish :: Map String (List String) ->
            Set String -> List Visit -> List String -> Pair (Set String) (List String);
  finish graph seen pending ordered =
    case pending of {
      Nil -> Pair seen ordered;
      Cons (Leave n) rest -> finish graph seen rest (Cons n ordered);
      Cons (Enter n) rest ->
        if S.member compareString n seen
        then finish graph seen rest ordered
        else let {
               dependencies = M.findWithDefault compareString Nil n graph
             } in
             finish graph (S.insert compareString n seen)
               (foldr (\d next -> Cons (Enter d) next) (Cons (Leave n) rest) dependencies)
               ordered
    };
  collect :: Map String (List String) ->
             Set String -> List String -> List String -> Pair (Set String) (List String);
  collect graph seen pending members =
    case pending of {
      Nil -> Pair seen (sortBy compareString members);
      Cons n rest ->
        if S.member compareString n seen
        then collect graph seen rest members
        else collect graph (S.insert compareString n seen)
               (append (M.findWithDefault compareString Nil n graph) rest)
               (Cons n members)
    };
  collectGroups :: Map String (List String) ->
                   Set String -> List String -> List (List String) -> List (List String);
  collectGroups graph seen ordered groups =
    case ordered of {
      Nil -> groups;
      Cons n rest ->
        if S.member compareString n seen
        then collectGroups graph seen rest groups
        else case collect graph seen (Cons n Nil) Nil of {
               Pair next members -> collectGroups graph next rest (Cons members groups)
             }
    };
  components :: List (Pair String (List String)) -> List (List String);
  components entries =
    let {
      graph = adjacency entries
    } in
    let {
      ordered = snd (finish graph S.empty (map Enter (M.keys graph)) Nil)
    } in
    collectGroups (transpose graph) S.empty ordered Nil;
  declarationGroups :: List (Triple String (Maybe SAnnotation) SExpr) ->
                       Either String (List (List String));
  declarationGroups values =
    let {
      names = map (\(Triple n _ _) -> n) values
    } in
    if (length names /= S.size (S.fromList compareString names))
    then Left "duplicate value declaration"
    else Right (components (declarationEdges values))
}
