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
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.ST as ST;
  import qualified Bootstrap.Desugar as Desugar;
  -- Edges point from a declaration to the declarations it needs. Namespace
  -- imports and type observations deliberately do not become value SCC edges.
  data Observation = Observation ([] String) ([] String) ([] String) ([] String);
  lexicalValueName name = if stringLength name >= 11 && eqString (stringSlice name 0 11) "$MLF.Infix." then stringSlice name 11 (stringLength name - 11) else name;
  valueNames (Observation values _ _ _) = values;
  typeNames (Observation _ types _ _) = types;
  constructorNames (Observation _ _ constructors _) = constructors;
  classNames (Observation _ _ _ classes) = classes;
  emptyObservation = Observation [] [] [] [];
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
        merge (Observation [] ((:) n []) [] []) (mergeMany (map observeType args));
      STypeApp a b -> merge (observeType a) (observeType b);
      SForall _ _ a b -> merge (observeType a) (observeType b);
      SQualified predicates body ->
        merge (mergeMany (map observePredicate predicates)) (observeType body);
      _ -> emptyObservation
    };
  observePredicate :: SPredicate -> Observation;
  observePredicate (SPredicate n args) =
    merge (Observation [] [] [] ((:) n [])) (mergeMany (map observeType args));
  observeAnnotation (SAnnotation _ ty) = observeType ty;
  observeRecursiveMode :: RecursiveMode -> Observation;
  observeRecursiveMode mode =
    case mode of {
      InferRecursive -> emptyObservation;
      CheckRecursive annotation -> observeAnnotation annotation
    };
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
        Observation ((:) (lexicalValueName equality) ((:) (lexicalValueName conversion) [])) [] [] [];
      SConstructorPattern n _ -> Observation [] [] ((:) n []) [];
      SNestedPattern n ps ->
        merge (Observation [] [] ((:) n []) []) (mergeMany (map observePattern ps));
      SAnnotatedPattern _ a -> observeAnnotation a;
      _ -> emptyObservation
    };
  observeExpression :: SExpr -> Observation;
  observeExpression expression =
    case expression of {
      SSourceDefinition body -> observeExpression body;
      SCallSite _ _ body -> observeExpression body;
      SSharedBind pattern action body binding failure ->
        merge (observePattern pattern)
          (merge (bindObservation (S.fromList compareString (Desugar.patternVariables pattern)) (observeExpression body))
            (mergeMany (map observeExpression ((:) action ((:) binding ((:) failure []))))));
      SVar n -> Observation ((:) (lexicalValueName n) []) [] [] [];
      SConstructor n -> Observation [] [] ((:) n []) [];
      SLam n a b ->
        merge (observeOptional a) (bindObservation (S.singleton n) (observeExpression b));
      SApp a b -> merge (observeExpression a) (observeExpression b);
      SLet n a b ->
        merge (observeExpression a) (bindObservation (S.singleton n) (observeExpression b));
      SAnn a t -> merge (observeExpression a) (observeAnnotation t);
      SSignature a t -> merge (observeExpression a) (observeAnnotation t);
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
             (\((,) ps b) ->
                merge (mergeMany (map observePattern ps))
                  (bindObservation
                     (S.fromList compareString (concatMap Desugar.patternVariables ps))
                     (observeExpression b)))
             rows);
      SDo _ _ -> observeExpression (Desugar.desugarDo expression);
      SLetRec declarations body ->
        bindObservation (S.fromList compareString (map (\((,,) n _ _) -> n) declarations))
          (merge (observeExpression body)
             (mergeMany
                (map (\((,,) _ mode b) -> merge (observeRecursiveMode mode) (observeExpression b))
                   declarations)));
      SWanted dictionary candidates ->
        Observation (map snd candidates) ((:) dictionary []) [] [];
      SChecked ty b -> merge (observeType ty) (observeExpression b);
      _ -> emptyObservation
    };
  observeDeclaration ((,,) _ annotation body) =
    normalize (merge (observeOptional annotation) (observeExpression body));
  declarationObservations values =
    M.fromList compareString
      (map
         (\declaration ->
            case declaration of {
              (,,) n _ _ -> (,) n (observeDeclaration declaration)
            })
         values);
  declarationEdges values =
    map
      (\declaration ->
         case declaration of {
           (,,) n _ _ -> (,) n (valueNames (observeDeclaration declaration))
         })
      values;
  observeField :: Field -> Observation;
  observeField field =
    case field of {
      Function a b -> merge (observeField a) (observeField b);
      Applied n args ->
        merge (Observation [] ((:) n []) [] []) (mergeMany (map observeField args));
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
         (mergeMany (map (\((,) _ ty) -> observeType ty) methods)));
  observeInstance (SInstanceDecl _ context name head methods) =
    normalize
      (merge (observePredicate (SPredicate name head))
         (merge (mergeMany (map observePredicate context))
            (mergeMany (map (\((,) _ expression) -> observeExpression expression) methods))));
  -- Names are resolved once at the graph boundary. Both the row table and
  -- each edge row are dense immutable vectors. IDs live only in this graph.
  data EdgeSlot = EdgeSlot;
  data Rows d = Rows (V.IndexVec d (V.IndexVec EdgeSlot (V.Index d)));
  data NamedGraph d a = NamedGraph (Map String (V.Index d)) (V.IndexVec d a) (Rows d);
  buildGraph :: forall d a. (a -> String) -> (a -> [] String) ->
                (String -> Maybe (V.Index d)) -> [] a -> NamedGraph d a;
  buildGraph name dependencies missing values =
    let {
      nodes = V.fromList values;
      names = M.fromList compareString (zipWith (\node i -> (,) (name node) i) values (V.indices nodes));
      resolve key = case M.lookup compareString key names of {
        Just i -> Just i;
        Nothing -> missing key
      };
      rows = V.fromList (map (\node -> V.fromList (mapMaybe resolve (dependencies node))) values)
    } in NamedGraph names nodes (Rows rows);
  graphNodes :: forall d a. NamedGraph d a -> V.IndexVec d a;
  graphNodes (NamedGraph _ nodes _) = nodes;
  graphRows :: forall d a. NamedGraph d a -> Rows d;
  graphRows (NamedGraph _ _ rows) = rows;
  graphId :: forall d a. NamedGraph d a -> String -> Maybe (V.Index d);
  graphId (NamedGraph names _ _) name = M.lookup compareString name names;
  neighbors :: forall d. Rows d -> V.Index d -> [] (V.Index d);
  neighbors (Rows rows) i = V.toList (V.at rows i);

  -- Roots and rows have a specified order. The explicit stack avoids native
  -- call-stack growth on deep import chains. Leave prepends to finish order.
  data Visit d = Enter (V.Index d) | Leave (V.Index d);
  finish :: forall s d. Rows d -> V.Builder s d Bool -> [] (Visit d) -> [] (V.Index d) ->
                        ST s ([] (V.Index d));
  finish rows seen pending ordered = case pending of {
    [] -> stReturn ordered;
    (:) (Leave i) rest -> finish rows seen rest ((:) i ordered);
    (:) (Enter i) rest -> stBind (V.get seen i) (\marked ->
      if marked then finish rows seen rest ordered
      else stBind (V.set seen i True) (\_ ->
        finish rows seen (foldr (\j next -> (:) (Enter j) next) ((:) (Leave i) rest)
                            (neighbors rows i)) ordered))
  };
  finishOrder :: forall d. Rows d -> [] (V.Index d) -> [] (V.Index d);
  finishOrder (Rows rows) roots = runST (stBind (V.filled (V.count rows) False) (\seen ->
    finish (Rows rows) seen (map Enter roots) []));

  transposeRows :: forall d. Rows d -> Rows d;
  transposeRows (Rows rows) = runST (stBind (V.filled (V.count rows) []) (\incoming ->
    stBind (ST.map_ (\i -> ST.map_ (\j -> stBind (V.get incoming j) (\old ->
      V.set incoming j ((:) i old))) (V.toList (V.at rows i))) (reverse (V.indices rows))) (\_ ->
    stBind (V.freeze incoming) (\lists ->
      stReturn (Rows (V.fromList (map V.fromList (V.toList lists))))))));
  data Declaration = Declaration;
  data ModuleVertex = ModuleVertex;
  collectGroups :: forall s d. Rows d -> V.Builder s d Bool -> [] (V.Index d) -> [] ([] (V.Index d)) ->
                   ST s ([] ([] (V.Index d)));
  collectGroups rows seen ordered groups = case ordered of {
    [] -> stReturn groups;
    (:) i rest -> stBind (finish rows seen [Enter i] []) (\members ->
      case members of {
        [] -> collectGroups rows seen rest groups;
        (:) _ _ -> collectGroups rows seen rest ((:) members groups)
      })
  };
  -- Repeated keys select the last entry. Roots, outgoing rows and group
  -- members are lexical, independently of source declaration order.
  nameGraph :: forall d. [] ((,) String ([] String)) -> NamedGraph d ((,) String ([] String));
  nameGraph entries = buildGraph fst (\entry -> canonical (snd entry)) (\_ -> Nothing)
                        (M.toList (M.fromList compareString entries));
  declarationGraph :: [] ((,) String ([] String)) -> NamedGraph Declaration ((,) String ([] String));
  declarationGraph = nameGraph;
  moduleGraph :: [] ((,) String ([] String)) -> NamedGraph ModuleVertex ((,) String ([] String));
  moduleGraph = nameGraph;
  components :: [] ((,) String ([] String)) -> [] ([] String);
  components entries = groupNames (declarationGraph entries);
  groupNames :: forall d. NamedGraph d ((,) String ([] String)) -> [] ([] String);
  groupNames graph =
    let {
      nodes = graphNodes graph;
      rows = graphRows graph;
      ordered = finishOrder rows (V.indices nodes);
      groups = runST (stBind (V.filled (V.count nodes) False) (\seen ->
                 collectGroups (transposeRows rows) seen ordered []))
    } in map (\group -> sortBy compareString (map (\i -> fst (V.at nodes i)) group)) groups;
  declarationGroups :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                       Either String ([] ([] String));
  declarationGroups values =
    let {
      names = map (\((,,) n _ _) -> n) values
    } in
    if (length names /= S.size (S.fromList compareString names))
    then Left "duplicate value declaration"
    else Right (components (declarationEdges values))
}
