-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Elaborate where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Evidence as Evidence;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Pretty as Pretty;
  isFlexible :: Flag -> Bool;
  isFlexible Flexible = True;
  isFlexible Rigid = False;
  sameParent parent maybe =
    case maybe of {
      Nothing -> False;
      Just identity -> (parent == identity)
    };
  -- A finished graph is immutable. Share its translated types and ordered
  -- bounds across resolution, elaboration and final checking. Map values are
  -- lazy, so preparing the table does not demand unused types or bounds.
  data TypeCell = TypeCell Node XType ([] ((,) XTyVar XType));
  data TypeContext = TypeContext Graph (IntMap XType) (IntMap ([] ((,) XTyVar XType))) IntSet |
    DenseTypeContext Graph Int Int (Int -> Maybe TypeCell) TypeContext;
  contextGraph :: TypeContext -> Graph;
  contextGraph (TypeContext graph _ _ _) = graph;
  contextGraph (DenseTypeContext graph _ _ _ _) = graph;
  prepareTypes :: Graph -> TypeContext;
  prepareTypes = prepareTypesWith Nothing;
  prepareSolvedTypes :: Solver -> TypeContext;
  prepareSolvedTypes solver = prepareTypesWith (Just (Solver.bindingChildren solver)) (Solver.solverGraph solver);
  -- Only the finished solver route owns canonical live IDs disjoint from
  -- aliases. Store the lazy translation and its bounds once per live slot.
  prepareValidatedSolvedTypes :: Solver -> TypeContext;
  prepareValidatedSolvedTypes solved = let {
    graph = Solver.solverGraph solved;
    nodes = G.nodes graph;
    count = IM.size nodes;
    bindings = Solver.bindingChildren solved;
    order = boundOrder graph;
    sparse = prepareTypesUsing (Just bindings) order graph;
    dense low high = let {
      result = DenseTypeContext graph low high
        (runST (stBind (newSTArray (high - low + 1) Nothing)
          (\table -> stBind (fillTypeCells low result order bindings (IM.toList nodes) table)
            (\_ -> freezeSTArray table)))) sparse
    } in result
  } in if count < 128 then sparse else case (,) (IM.lookupMin nodes) (IM.lookupMax nodes) of {
    (,) (Just ((,) low _)) (Just ((,) high _)) ->
      let { space = high - low } in
      if space >= 0 && space <= 262144 && space <= 3 * count then dense low high else sparse;
    _ -> sparse
  };
  fillTypeCells :: forall s. Int -> TypeContext -> BoundOrder -> IntMap IntSet -> [] ((,) Int Node)
    -> STArray s (Maybe TypeCell) -> ST s ();
  fillTypeCells low context order bindings entries table = case entries of {
    [] -> stReturn ();
    (:) ((,) n node) rest -> let {
      cell = TypeCell node (typeAtNode context n node) (boundsAtIndexedUsing order context bindings n node)
    } in stBind (writeSTArray table (n - low) (Just cell)) (\_ -> fillTypeCells low context order bindings rest table)
  };
  readTypeCell context n = case context of {
    DenseTypeContext _ low high cell _ ->
      if low <= n && n <= high then cell (n - low) else Nothing;
    _ -> Nothing
  };
  lookupTypeCell context graph n = case readTypeCell context n of {
    Just cell -> Just ((,) n cell);
    Nothing -> let { live = G.resolve graph n } in mapOptional ((,) live) (readTypeCell context live)
  };
  prepareTypesWith :: Maybe (IntMap IntSet) -> Graph -> TypeContext;
  prepareTypesWith bindings graph = prepareTypesUsing bindings (boundOrder graph) graph;
  prepareTypesUsing :: Maybe (IntMap IntSet) -> BoundOrder -> Graph -> TypeContext;
  prepareTypesUsing bindings order graph =
    let {
      context :: TypeContext;
      context =
        TypeContext graph (IM.mapWithKey renderType (G.nodes graph))
          (IM.mapWithKey renderBounds (G.nodes graph))
          (IS.fromList
             (concatMap (\v -> if isFlexible (G.flag v) then maybeToList (G.binder v) else [])
                (IM.elems (G.nodes graph))));
      -- The traversal already has the node. Raw contexts can still contain
      -- alias keys, so those use the resolving queries.
      renderType n node = if IM.notMember n (G.links graph)
        then typeAtNode context n node else typeAtRaw context n;
      renderBounds n node = case bindings of {
        Nothing -> if IM.notMember n (G.links graph)
          then boundsAtNode context n node else boundsAtRaw context n;
        Just children -> boundsAtIndexedUsing order context children n node
      }
    } in
    context;
  typeAtIn :: TypeContext -> Int -> XType;
  typeAtIn (TypeContext graph types bounds parents) identity =
    IM.get (G.resolve graph identity) types;
  typeAtIn context@(DenseTypeContext graph _ _ _ sparse) identity = case lookupTypeCell context graph identity of {
    Just ((,) _ (TypeCell _ ty _)) -> ty;
    Nothing -> typeAtIn sparse identity
  };
  boundsAtIn :: TypeContext -> Int -> [] ((,) XTyVar XType);
  boundsAtIn (TypeContext graph types bounds parents) identity =
    IM.get (G.resolve graph identity) bounds;
  boundsAtIn context@(DenseTypeContext graph _ _ _ sparse) identity = case lookupTypeCell context graph identity of {
    Just ((,) _ (TypeCell _ _ bounds)) -> bounds;
    Nothing -> boundsAtIn sparse identity
  };
  boundsAtRepresentative (TypeContext _ _ bounds _) identity = IM.get identity bounds;
  boundsAtRepresentative context@(DenseTypeContext _ _ _ _ sparse) identity = case readTypeCell context identity of {
    Just (TypeCell _ _ bounds) -> bounds;
    Nothing -> boundsAtRepresentative sparse identity
  };
  -- Flexible graph nodes become target binders; rigid bounds remain structure.
  typeAtRaw :: TypeContext -> Int -> XType;
  typeAtRaw context identity = let {
    graph = contextGraph context;
    resolved = G.resolve graph identity
  } in typeAtNode context resolved (G.nodeAtRepresentative graph resolved resolved);
  typeAtNode :: TypeContext -> Int -> Node -> XType;
  typeAtNode context identity node =
    let {
      structure =
        case G.tag node of {
          GBot -> XBot;
          GBotK kind -> T.bottomKind kind;
          GArr a b -> XArrow (childTypeIn context a) (childTypeIn context b);
          GCon constructor parameters -> XCon constructor (map (childTypeIn context) parameters);
          GTyCon constructor _ -> XCon constructor [];
          GSkolem skolem _ -> XVar (XTyVar skolem);
          GTyApp f a -> T.apply (childTypeIn context f) (childTypeIn context a);
          GGen _ -> panic "typeAt: a gen node is not a type"
        }
    } in
    foldr (\bound body -> XForall (fst bound) (snd bound) body) structure
      (boundsAtRepresentative context identity);
  childTypeIn :: TypeContext -> Int -> XType;
  childTypeIn (TypeContext graph types _ _) identity = let {
    representative = G.resolve graph identity
  } in if isFlexible (G.flag (G.nodeAtRepresentative graph identity representative))
    then XVar (XTyVar representative)
    else IM.get representative types;
  childTypeIn context@(DenseTypeContext graph _ _ _ sparse) identity = case lookupTypeCell context graph identity of {
    Just ((,) live (TypeCell node ty _)) -> if isFlexible (G.flag node) then XVar (XTyVar live) else ty;
    Nothing -> childTypeIn sparse identity
  };
  referenceIn :: TypeContext -> Int -> XType;
  referenceIn context identity =
    let {
      graph = contextGraph context
    } in
    let {
      node = G.nodeAt graph identity
    } in
    let {
      generalized =
        case G.binder node of {
          Nothing -> False;
          Just parent ->
            case G.tag (G.nodeAt graph parent) of {
              GGen _ -> True;
              _ -> False
            }
        }
    } in
    if (isFlexible (G.flag node) && generalized)
    then XVar (XTyVar (G.resolve graph identity))
    else typeAtIn context identity;
  boundsAtRaw :: TypeContext -> Int -> [] ((,) XTyVar XType);
  boundsAtRaw context parent = boundsAtNode context parent (G.nodeAt (contextGraph context) parent);
  boundRoot :: Int -> Node -> Int;
  boundRoot parent node = case G.tag node of { GGen root -> root; _ -> parent };
  -- A single forest postorder is reusable only inside an unshared subtree.
  -- A node with several incoming type edges may start such a subtree, but
  -- any shared strict descendant requires the original root-local DFS order.
  -- Gen payload edges are entry points, not incoming type edges. Starting at
  -- structural roots ensures that a descendant with one incoming edge cannot
  -- have been visited before its parent. The lazy certificate table shares
  -- overlapping subtree checks; neither it nor the ranks is needed for an
  -- empty or singleton bound query.
  data BoundOrder = BoundOrder (IntMap Bool) (IntMap Int);
  boundOrder :: Graph -> BoundOrder;
  boundOrder graph = let {
    nodes = IM.filter (\node -> not (G.isGen (G.tag node))) (G.nodes graph);
    incoming = foldlStrict
      (\table node -> foldlStrict
        (\next child -> IM.insertWith (\_ _ -> False) (G.resolve graph child) True next)
        table (G.children (G.tag node))) IM.empty (IM.elems nodes);
    trees = IM.mapWithKey (\_ node -> all unshared (G.children (G.tag node))) nodes;
    unshared child = let { live = G.resolve graph child } in
      IM.findWithDefault False live incoming && IM.findWithDefault False live trees;
    roots = filter (\n -> IM.notMember n incoming) (IM.keys nodes);
    visited = foldlStrict (G.orderedVisitReverse graph) ((,) IS.empty []) roots;
    ordered = reverse (snd visited);
    ranks = IM.fromList (zip ordered (range 0 (length ordered - 1)))
  } in BoundOrder trees ranks;
  orderedBoundCandidates :: BoundOrder -> Graph -> Int -> IntSet -> [] Int;
  orderedBoundCandidates order graph root candidates = case IS.toList candidates of {
    [] -> [];
    (:) one [] -> (:) one [];
    several -> case order of { BoundOrder trees ranks ->
      if IM.findWithDefault False root trees then
        map snd (sortBy (\a b -> compareInt (fst a) (fst b))
          (map (\n -> (,) (IM.get n ranks) n) several))
      else filter (\identity -> IS.member identity candidates) (G.orderedBelow graph root)
    }
  };
  -- A solved, normalized graph certifies that a type binder reaches its
  -- children, and normalization makes unreachable Gen children rigid. Use
  -- the checked reverse index to answer empty and singleton bounds directly.
  -- Several bounds still follow the structural postorder used by elaboration.
  boundsAtIndexed :: TypeContext -> IntMap IntSet -> Int -> Node -> [] ((,) XTyVar XType);
  boundsAtIndexed context = boundsAtIndexedUsing (boundOrder (contextGraph context)) context;
  boundsAtIndexedUsing :: BoundOrder -> TypeContext -> IntMap IntSet -> Int -> Node -> [] ((,) XTyVar XType);
  boundsAtIndexedUsing order context children parent node = let {
    graph = contextGraph context;
    eligible identity = let {
      child = case readTypeCell context identity of {
        Just (TypeCell value _ _) -> value; Nothing -> IM.get identity (G.nodes graph)
      }
    } in isFlexible (G.flag child) && not (G.isGen (G.tag child));
    candidates = IS.filter eligible (IM.findWithDefault IS.empty parent children);
    ordered = orderedBoundCandidates order graph (boundRoot parent node) candidates
  } in map (\identity -> (,) (XTyVar identity) (typeAtIn context identity)) ordered;
  boundsAtNode :: TypeContext -> Int -> Node -> [] ((,) XTyVar XType);
  boundsAtNode context parent node =
    case context of {
      TypeContext graph types bounds parents ->
        if IS.notMember parent parents
        then []
        else let { resolvedParent = G.resolve graph parent } in
             map (\identity -> (,) (XTyVar identity) (typeAtIn context identity))
               (filter
                  (\identity ->
                     (sameParent resolvedParent (G.binder (G.nodeAt graph identity)) &&
                      isFlexible (G.flag (G.nodeAt graph identity))))
                  (G.orderedBelow graph (boundRoot parent node)));
      DenseTypeContext _ _ _ _ sparse -> boundsAtNode sparse parent node
    };
  schemeTypeIn context gen =
    let {
      graph = contextGraph context
    } in
    foldr (\bound body -> XForall (fst bound) (snd bound) body)
      (referenceIn context (G.genRoot graph gen))
      (boundsAtIn context gen);
  nodeConstructorKind node =
    case G.tag node of {
      GTyCon name kind -> Just ((,) name kind);
      _ -> Nothing
    };
  graphDatatypes graph =
    D.withKinds (catMaybes (map nodeConstructorKind (IM.elems (G.nodes graph))));
  extendEnvironment outer bounds =
    foldl (\env bound -> M.insert T.compareTyVar (fst bound) (snd bound) env) outer bounds;
  -- All proof checks still check the input type and the computation. Lexical
  -- extensions can keep the earlier scope's validation: a fresh key cannot
  -- affect the kinds of any earlier, closed-over bounds.
  data ElaborationScope = ElaborationScope DataEnv (Map XTyVar XType) (Either String ());
  elaborationScope :: DataEnv -> Map XTyVar XType -> ElaborationScope;
  elaborationScope datatypes types =
    ElaborationScope datatypes types (Check.validateTypeEnv datatypes types);
  elaborationTypes :: ElaborationScope -> Map XTyVar XType;
  elaborationTypes (ElaborationScope _ types _) = types;
  extendElaborationScope :: ElaborationScope -> [] ((,) XTyVar XType) -> ElaborationScope;
  extendElaborationScope = foldlStrict extendElaborationBound;
  extendElaborationBound :: ElaborationScope -> (,) XTyVar XType -> ElaborationScope;
  extendElaborationBound (ElaborationScope datatypes types checked) ((,) variable bound) = let {
    extended = M.insert T.compareTyVar variable bound types;
    ordinary = Check.validateTypeEnv datatypes extended;
    admitted = case checked of {
      Left _ -> ordinary;
      Right _ -> case M.lookup T.compareTyVar variable types of {
        Just _ -> ordinary;
        Nothing -> case Check.wellFormedIn datatypes types bound of {
          Right _ -> Right (); Left _ -> ordinary
        }
      }
    }
  } in seq extended (ElaborationScope datatypes extended admitted);
  checkElaborationComputation :: ElaborationScope -> XComputation -> XType -> Either String XType;
  checkElaborationComputation (ElaborationScope datatypes types checked) proof source = do {
    checked;
    Check.checkComputationScoped datatypes types proof source
  };
  isRefl :: XComputation -> Bool;
  isRefl XRefl = True;
  isRefl _ = False;
  proveInstance targetGraph image env source target =
    proveInstanceWithIn (graphDatatypes targetGraph) (prepareTypes targetGraph) image env source
      target;
  proveInstanceWithIn :: DataEnv ->
                         TypeContext ->
                         (Int -> Int) ->
                         Map XTyVar XType -> XType -> XType -> Either String XComputation;
  proveInstanceWithIn datatypes context image env source target =
    proveInstanceUsing datatypes (graphReplacementIn context image) env source target;
  proveInstanceWithScope :: DataEnv -> TypeContext -> (Int -> Int) ->
    ElaborationScope -> XType -> XType -> Either String XComputation;
  proveInstanceWithScope datatypes context image =
    proveInstanceUsingScope datatypes (graphReplacementIn context image);
  graphReplacementIn context image gamma variable =
    do {
      let {
        targetGraph = contextGraph context
      };
      let {
        identity = image (T.tyVarId variable)
      };
      unless (IM.member identity (G.nodes targetGraph))
        (Left ("instance lost node provenance: " ++ showInt (T.tyVarId variable)));
      Right
        (if M.member T.compareTyVar (XTyVar identity) gamma
         then XVar (XTyVar identity)
         else typeAtIn context identity)
    };
  -- The declaration retains its own forall identities, including unused
  -- binders. Only free references denote shared datatype-parameter graph
  -- nodes; substituting by source spelling would lose shadowing and kinds.
  declaredTypeIn :: TypeContext -> IntSet -> XType -> XType;
  declaredTypeIn context local ty =
    case ty of {
      XVar variable ->
        if IS.member (T.tyVarId variable) local then ty
        else referenceIn context (T.tyVarId variable);
      XArrow a b -> XArrow (declaredTypeIn context local a) (declaredTypeIn context local b);
      XCon name arguments -> XCon name (map (declaredTypeIn context local) arguments);
      XApply f a -> T.apply (declaredTypeIn context local f) (declaredTypeIn context local a);
      XForall variable bound body ->
        XForall variable (declaredTypeIn context local bound)
          (declaredTypeIn context (IS.insert (T.tyVarId variable) local) body);
      _ -> ty
    };
  declaredReplacementIn context kinds gamma variable =
    let { graph = contextGraph context } in
    let { identity = G.resolve graph (T.tyVarId variable) } in
    if IM.member identity (G.nodes graph)
    then graphReplacementIn context (\n -> n) gamma variable
    else case M.lookup T.compareTyVar variable kinds of {
      Just kind -> Right (T.bottomKind kind);
      Nothing -> Left ("declared field lost type provenance: " ++ showInt (T.tyVarId variable))
    };
  -- Vacuous leading binders are removed explicitly, before the generic proof
  -- considers target abstractions. In particular forall b.a -> a must retain
  -- the shared external a, not attempt to instantiate it to its bound.
  dropUnusedLeading :: XType -> XComputation;
  dropUnusedLeading ty =
    case ty of {
      XForall variable _ body ->
        let { inner = dropUnusedLeading body } in
        if Set.member T.compareTyVar variable (T.freeVars body)
        then if isRefl inner then XRefl else XOuter variable inner
        else X.compose XElim inner;
      _ -> XRefl
    };
  declaredFieldComputationIn :: TypeContext -> DataEnv -> Map XTyVar XType ->
                                XType -> Int -> Either String XComputation;
  declaredFieldComputationIn context datatypes env =
    declaredFieldComputationScoped context datatypes (elaborationScope datatypes env);
  declaredFieldComputationScoped :: TypeContext -> DataEnv -> ElaborationScope ->
    XType -> Int -> Either String XComputation;
  declaredFieldComputationScoped context datatypes scope declaration source = do {
    let { actual = declaredTypeIn context IS.empty declaration };
    case declaration of {
      -- Bare parameter fields carry the exact case-substituted identity. Their
      -- copied interface must differ only by alpha-renaming, never by opening
      -- an abstract bound or inventing an adapter for a monomorphic fallback.
      XVar _ -> do {
        unless (T.alphaEq actual (schemeTypeIn context source))
          (Left "projected field differs from its exact case type");
        checked <- checkElaborationComputation scope XRefl actual;
        unless (T.alphaEq checked (schemeTypeIn context source))
          (Left "projected field evidence has the wrong target");
        Right XRefl
      };
      _ -> do {
        let { prefix = dropUnusedLeading actual };
        normalized <- checkElaborationComputation scope prefix actual;
        let { kinds = M.fromList T.compareTyVar (fst (Evidence.quantifiers actual)) };
        proof <- proveInstanceUsingScope datatypes (declaredReplacementIn context kinds) scope
          normalized (schemeTypeIn context source);
        let { combined = X.compose prefix proof };
        checked <- checkElaborationComputation scope combined actual;
        unless (T.alphaEq checked (schemeTypeIn context source))
          (Left "declared field evidence has the wrong target");
        Right combined
      }
    }
  };
  -- Explicit signatures can retain unused binders or a different forall order.
  -- All adaptations use the same independently checked atomic computations.
  proveInstanceUsing :: DataEnv ->
                        (Map XTyVar XType -> XTyVar -> Either String XType) ->
                        Map XTyVar XType -> XType -> XType -> Either String XComputation;
  proveInstanceUsing datatypes replacement env =
    proveInstanceUsingScope datatypes replacement (elaborationScope datatypes env);
  proveInstanceUsingScope :: DataEnv ->
    (Map XTyVar XType -> XTyVar -> Either String XType) ->
    ElaborationScope -> XType -> XType -> Either String XComputation;
  proveInstanceUsingScope datatypes replacement scope source target =
    do {
      computation <- prove datatypes replacement (elaborationTypes scope) source target;
      actual <- checkElaborationComputation scope computation source;
      unless (T.alphaEq actual target) (Left "instance evidence has the wrong target");
      Right computation
    };
  prove :: DataEnv ->
           (Map XTyVar XType -> XTyVar -> Either String XType) ->
           Map XTyVar XType -> XType -> XType -> Either String XComputation;
  prove datatypes replacement gamma source target =
    if T.alphaEq source target
    then Right XRefl
    else case source of {
           XBot -> Right (XBottom target);
           XBotKind _ -> Right (XBottom target);
           _ ->
             case target of {
               XVar variable ->
                 case M.lookup T.compareTyVar variable gamma of {
                   Nothing -> Left ("missing target abstraction: " ++ showInt (T.tyVarId variable));
                   Just bound ->
                     do {
                       computation <- prove datatypes replacement gamma source bound;
                       Right (X.compose computation (XHyp variable))
                     }
                 };
               XForall variable bound body ->
                 do {
                   computation <-
                     prove datatypes replacement (M.insert T.compareTyVar variable bound gamma)
                       source
                       body;
                   kind <- T.kindOf datatypes gamma bound;
                   let {
                     intro =
                       if K.eqKind kind Star then XIntro variable else XIntroKind variable kind
                   };
                   let {
                     strengthening =
                       if T.alphaEq bound (T.bottomKind kind) then XRefl else XInner (XBottom bound)
                   };
                   Right (X.compose (X.compose intro strengthening) (XOuter variable computation))
                 };
               _ -> eliminate datatypes replacement gamma source target
             }
         };
  eliminate :: DataEnv ->
               (Map XTyVar XType -> XTyVar -> Either String XType) ->
               Map XTyVar XType -> XType -> XType -> Either String XComputation;
  eliminate datatypes replacement gamma source target =
    case source of {
      XForall variable bound body ->
        do {
          argument <- replacement gamma variable;
          first <- prove datatypes replacement gamma bound argument;
          rest <- prove datatypes replacement gamma (T.substitute variable argument body) target;
          Right (X.compose (X.compose (if isRefl first then XRefl else XInner first) XElim) rest)
        };
      _ ->
        Left
          ("no permitted instance from " ++
           (Pretty.prettyType source ++ (" to " ++ Pretty.prettyType target)))
    };
  structuralPairs :: GTag -> GTag -> [] ((,) Int Int);
  structuralPairs (GArr a b) (GArr c d) = (:) ((,) a c) ((:) ((,) b d) []);
  structuralPairs (GTyApp a b) (GTyApp c d) = (:) ((,) a c) ((:) ((,) b d) []);
  structuralPairs (GCon c xs) (GCon d ys) =
    if (eqString c d && (length xs == length ys)) then zip xs ys else [];
  structuralPairs _ _ = [];
  correspondence :: Graph -> IntSet -> IntMap Int -> [] ((,) Int Int) -> IntMap Int;
  correspondence _ _ images [] = images;
  correspondence graph seen images ((:) ((,) original target) rest) =
    let {
      a = G.resolve graph original
    } in
    let {
      b = G.resolve graph target
    } in
    if IS.member a seen
    then correspondence graph seen images rest
    else let {
           pairs = structuralPairs (G.tag (G.nodeAtRepresentative graph a a)) (G.tag (G.nodeAtRepresentative graph b b))
         } in
         correspondence graph (IS.insert a seen) (IM.insert a b images) (append pairs rest);
  -- Every fast correspondence is checked. Failed candidates use the final
  -- presolution's frontier-first expansion to retain graph provenance.
  edgeComputationIn :: TypeContext ->
                       DataEnv -> Solver -> Map XTyVar XType -> Edge -> Either String XComputation;
  edgeComputationIn context datatypes solver env =
    edgeComputationScoped context datatypes solver (elaborationScope datatypes env);
  edgeComputationScoped :: TypeContext -> DataEnv -> Solver -> ElaborationScope ->
    Edge -> Either String XComputation;
  edgeComputationScoped context datatypes solver scope edge =
    let {
      graph = Solver.solverGraph solver
    } in
    let {
      target = G.resolve graph (C.toNode edge)
    } in
    let {
      source = schemeTypeIn context (C.fromGen edge)
    } in
    let {
      targetType = referenceIn context target
    } in
    if T.alphaEq source targetType
    then Right XRefl
    else let {
           positions =
             correspondence graph IS.empty IM.empty
               ((:) ((,) (G.genRoot graph (C.fromGen edge)) target) [])
         } in
         let {
           directImage =
             \identity -> IM.findWithDefault identity (G.resolve graph identity) positions
         } in
         case proveInstanceWithScope datatypes context directImage scope source targetType of {
           Right proof -> Right proof;
           Left _ ->
             do {
               witness <- Solver.witness (C.fromGen edge) target solver;
               let {
                 copies = fst witness
               };
               let {
                 solved = Solver.solverGraph (snd witness)
               };
               let {
                 image = \identity -> G.resolve solved (IM.findWithDefault identity identity copies)
               };
               proveInstanceWithScope datatypes context image scope source targetType
             }
         };
  candidateTypeIn context candidate =
    let {
      graph = contextGraph context
    } in
    case candidate of {
      EvidenceBinding role name identity polymorphic ->
        (,,) role name
          (if polymorphic then schemeTypeIn context identity else referenceIn context identity);
      DeclaredEvidenceBinding role name declaration ->
        (,,) role name (declaredTypeIn context IS.empty declaration)
    };
  resolveEvidence graph typed = resolveEvidenceIn (prepareTypes graph) typed;
  resolveEvidenceIn context typed =
    resolveWithinIn context (graphDatatypes (contextGraph context)) M.empty typed;
  resolveWithinIn :: TypeContext ->
                     DataEnv -> Map XTyVar XType -> Typed -> Either String (IntMap XTerm);
  resolveWithinIn context datatypes outer typed =
    resolveRequests context datatypes Nothing IM.empty IM.empty (evidenceRequests context outer [] typed []);
  -- The graph is immutable during resolution. Rows with the same identity
  -- and binding mode denote the same translated type. Check the whole
  -- ordered authorization, including target name hints used in artifacts.
  sameGraphCandidate (EvidenceBinding role name identity poly)
                     (EvidenceBinding other target source polymorphic) =
    Evidence.sameRole role other && identity == source && (if poly then polymorphic else not polymorphic) &&
      X.equalName name target && eqString (X.nameHint name) (X.nameHint target);
  sameGraphCandidate _ _ = False;
  data EvidenceContext = EvidenceContext (Map XTyVar XType) ([] ((,,) EvidenceRole XName XType));
  data EvidenceInventory = ExplicitEvidence ([] EvidenceBinding) | ScopedEvidence ResolvedCandidateEnvironment;
  resolveRequests context datatypes previous modules results requests = case requests of {
    [] -> Right results;
    (:) ((,,) gen (EvidenceContext env locals) inventory) rest -> let {
      wanted = referenceIn context (G.genRoot (contextGraph context) gen);
      finish answer lastScope scopes = case answer of {
        Left failure -> Left (Evidence.evidenceFailureMessage failure);
        Right term -> let { next = IM.insertWith (\_ old -> old) gen term results }
          in seq next (resolveRequests context datatypes lastScope scopes next rest)
      }
    } in case inventory of {
      -- Constraint generation allocates the token when it resolves this
      -- module's binding identities. The memo belongs to this solved graph.
      ScopedEvidence (ResolvedCandidateEnvironment token bindings) ->
        case IM.lookup token modules of {
          Just resolve -> finish (resolve env locals wanted) previous modules;
          Nothing -> let {
            resolve = Evidence.scopedResolver datatypes (map (candidateTypeIn context) bindings);
            scopes = IM.insert token resolve modules
          } in seq scopes (finish (resolve env locals wanted) previous scopes)
        };
      ExplicitEvidence candidates -> let {
        types = map (candidateTypeIn context) candidates;
        fresh = Evidence.indexedResolver datatypes M.empty types;
        start = finish (fresh wanted) (Just ((,) candidates fresh)) modules
      } in if M.null env then case previous of {
        Just ((,) scope resolve) -> if eqList sameGraphCandidate candidates scope
          then finish (resolve wanted) previous modules else start;
        Nothing -> start
      } else finish (Evidence.resolveDictionaryDetailed datatypes env types wanted) previous modules
    }
  };
  -- A given frame declares the complete local inventory, including an
  -- explicitly empty frame. Siblings always resume their enclosing frame.
  evidenceRequests context outer locals typed rest = let {
    gen = C.generalization typed;
    env = extendEnvironment outer (boundsAtIn context gen);
    visit givens form rest = let { child = evidenceRequests context env givens } in case form of {
      FWithGivens bindings body -> visit (map (candidateTypeIn context) bindings) body rest;
      FScopedEvidence scope -> (:) ((,,) gen (EvidenceContext env givens) (ScopedEvidence scope)) rest;
      FEvidence candidates -> (:) ((,,) gen (EvidenceContext env givens) (ExplicitEvidence candidates)) rest;
      FLambda _ _ body _ -> child body rest;
      FBindDictionaries _ body _ -> child body rest;
      FApply a b _ _ -> child a (child b rest);
      FApplyVariable _ _ argument _ -> child argument rest;
      FApplyDictionaries _ _ _ -> rest;
      FApplyGroundDictionaries _ _ arguments -> foldr (\((,) argument _) tail -> child argument tail) rest arguments;
      FApplyPrimitive _ _ arguments -> foldr (\operand tail -> case operand of {
        PrimitiveUse argument _ -> child argument tail;
        ClosedPrimitiveForm current -> visit givens current tail
      }) rest arguments;
      FPrimitiveStringConversion _ _ _ dictionary _ _ -> child dictionary rest;
      FIntStringCalls _ worker value _ _ arms fallback _ ->
        child worker (child value (foldr (\(StringCallArm _ _ argument _ _) tail -> child argument tail)
          (child fallback rest) arms));
      FBinding _ a b _ -> child a (child b rest);
      FMatch scrutinee _ branches -> child scrutinee
        (foldr (\(Branch _ body _) more -> child body more) rest branches);
      FRecursive definitions body _ -> child body
        (foldr (\(RecursiveDefinition _ _ rhs _ closure) more -> case closure of {
          Nothing -> child rhs more;
          Just (RecursiveClosure group _) -> evidenceRequests context
            (extendEnvironment env (boundsAtIn context group)) givens rhs more
        }) rest definitions);
      FChecked variables body _ -> evidenceRequests context
        (extendEnvironment env
          (map (\variable -> (,) (fst variable) (T.bottomKind (snd variable))) variables))
        givens body rest;
      _ -> rest
    }
  } in visit locals (C.rawForm typed) rest;
  elaborate graph typed =
    do {
      evidence <- resolveEvidence graph typed;
      elaborateResolved graph evidence typed
    };
  elaborateResolved :: Graph -> IntMap XTerm -> Typed -> Either String XTerm;
  elaborateResolved graph evidence typed =
    do {
      solver <- Solver.prepare graph;
      elaborateWithinIn (prepareTypes graph) (graphDatatypes graph) evidence solver M.empty typed
    };
  -- The checked compiler can retain its finished solver through normalization.
  -- Legacy graph entry points above still prepare and validate their own input.
  elaboratePrepared :: Solver -> IntMap XTerm -> Typed -> Either String XTerm;
  elaboratePrepared solver evidence typed =
    elaboratePreparedIn (prepareTypes (Solver.solverGraph solver)) solver evidence typed;
  elaboratePreparedIn :: TypeContext -> Solver -> IntMap XTerm -> Typed -> Either String XTerm;
  elaboratePreparedIn context solver evidence typed =
    elaborateWithinIn context (graphDatatypes (contextGraph context)) evidence solver M.empty typed;
  instantiateEdgeIn context datatypes solver env =
    instantiateEdgeScoped context datatypes solver (elaborationScope datatypes env);
  instantiateEdgeScoped :: TypeContext -> DataEnv -> Solver -> ElaborationScope ->
    XTerm -> Edge -> Either String XTerm;
  instantiateEdgeScoped context datatypes solver scope term edge =
    do {
      proof <- edgeComputationScoped context datatypes solver scope edge;
      Right (X.instantiate term proof)
    };
  elaborateEdgeIn :: TypeContext ->
                     DataEnv ->
                     IntMap XTerm ->
                     Solver -> Map XTyVar XType -> Typed -> Edge -> Either String XTerm;
  elaborateEdgeIn context datatypes evidence solver env =
    elaborateEdgeScoped context datatypes evidence solver (elaborationScope datatypes env);
  elaborateEdgeScoped :: TypeContext -> DataEnv -> IntMap XTerm -> Solver ->
    ElaborationScope -> Typed -> Edge -> Either String XTerm;
  elaborateEdgeScoped context datatypes evidence solver scope typed edge = do {
    term <- elaborateWithinScoped context datatypes evidence solver scope typed;
    instantiateEdgeScoped context datatypes solver scope term edge
  };
  elaborateWithinIn :: TypeContext -> DataEnv -> IntMap XTerm -> Solver ->
    Map XTyVar XType -> Typed -> Either String XTerm;
  elaborateWithinIn context datatypes evidence solver outer =
    elaborateWithinScoped context datatypes evidence solver (elaborationScope datatypes outer);
  elaborateWithinScoped :: TypeContext -> DataEnv -> IntMap XTerm -> Solver ->
    ElaborationScope -> Typed -> Either String XTerm;
  elaborateWithinScoped context datatypes evidence solver outer typed =
    do {
      let {
        graph = contextGraph context
      };
      let {
        gen = C.generalization typed
      };
      let {
        bounds = boundsAtIn context gen
      };
      let {
        scope = extendElaborationScope outer bounds
      };
      let {
        child = elaborateWithinScoped context datatypes evidence solver scope
      };
      let {
        childEdge = elaborateEdgeScoped context datatypes evidence solver scope
      };
      let { dictionary = case IM.lookup gen evidence of {
        Nothing -> Left "unresolved dictionary evidence";
        Just term -> Right term
      } };
      let { elaborateForm current = case current of {
          FWithGivens _ enclosed -> elaborateForm enclosed;
          FVariable name Nothing -> Right (XVarTerm name);
          FVariable name (Just edge) ->
            instantiateEdgeScoped context datatypes solver scope (XVarTerm name) edge;
          FDeclaredVariable name declaration edge -> do {
            proof <- declaredFieldComputationScoped context datatypes scope declaration (C.fromGen edge);
            instantiateEdgeScoped context datatypes solver scope (X.instantiate (XVarTerm name) proof) edge
          };
          FLambda name domain body edge ->
            do {
              body' <- childEdge body edge;
              Right (XAbs name (referenceIn context domain) body')
            };
          FBindDictionaries args body edge -> do {
            term <- childEdge body edge;
            Right (foldr (\((,) name domain) b -> XAbs name (referenceIn context domain) b) term args)
          };
          FApply a b ea eb ->
            do {
              a' <- childEdge a ea;
              b' <- childEdge b eb;
              Right (XApp a' b')
            };
          FApplyVariable name use argument proof -> do {
            function <- instantiateEdgeScoped context datatypes solver scope (XVarTerm name) use;
            operand <- childEdge argument proof;
            Right (XApp function operand)
          };
          FApplyDictionaries f proof arguments -> do {
            function <- instantiateEdgeScoped context datatypes solver scope (XVarTerm f) proof;
            Right (foldl (\value name -> XApp value (XVarTerm name)) function arguments)
          };
          FApplyGroundDictionaries f proof arguments -> do {
            function <- instantiateEdgeScoped context datatypes solver scope (XVarTerm f) proof;
            operands <- mapM (\((,) argument edge) -> childEdge argument edge) arguments;
            Right (foldl XApp function operands)
          };
          FApplyPrimitive primitive types arguments -> do {
            operands <- mapM (\operand -> case operand of {
              PrimitiveUse argument proof -> childEdge argument proof;
              ClosedPrimitiveForm current -> elaborateForm current
            }) arguments;
            Right (foldl XApp (XPrimitive primitive (map (referenceIn context) types)) operands)
          };
          FPrimitiveStringConversion primitive selector domain dictionary use text -> do {
            value <- childEdge dictionary use;
            let { convert = X.instantiate (XVarTerm selector) (X.typeApplication domain);
                  chars = XApp (XPrimitive PTextToChars []) (XStringTerm text) };
            Right (XApp (XPrimitive primitive []) (XApp (XApp convert value) chars))
          };
          FIntStringCalls operator worker value valueProof result arms fallback restProof -> do {
            word <- child worker;
            subject <- childEdge value valueProof;
            let { arm (StringCallArm key text argument operand proof) = do {
              function <- instantiateEdgeScoped context datatypes solver scope (XVarTerm operator) proof;
              selected <- childEdge argument operand;
              let { test = XApp (XApp (XPrimitive PEqInt []) subject) (XIntTerm key);
                    branch = XApp (XApp function selected) (XStringTerm text) };
              Right (XApp (XApp (XPrimitive PIfThenElse [referenceIn context result]) test) branch)
            } };
            branches <- mapM arm arms;
            fallback' <- childEdge fallback restProof;
            Right (XLet operator word (foldr XApp fallback' branches))
          };
          FBinding name a b edge ->
            do {
              a' <- child a;
              b' <- childEdge b edge;
              Right (XLet name a' b')
            };
          FCoercion name domain codomain ->
            do {
              let {
                local = boundsAtIn context (G.genRoot graph gen)
              };
              let {
                nested = extendElaborationScope scope local;
                gamma = elaborationTypes nested
              };
              let {
                domainType = referenceIn context domain
              };
              let {
                result =
                  if M.member T.compareTyVar (XTyVar (G.resolve graph codomain)) gamma
                  then XVar (XTyVar (G.resolve graph codomain))
                  else typeAtIn context codomain
              };
              proof <-
                proveInstanceWithScope datatypes context (\identity -> identity) nested domainType
                  result;
              Right
                (foldr (\bound inner -> XTypeAbs (fst bound) (snd bound) inner)
                   (XAbs name domainType (X.instantiate (XVarTerm name) proof))
                   local)
            };
          FIntegerLiteral n -> Right (XIntTerm n);
          FDoubleLiteral n -> Right (XDoubleTerm n);
          FBooleanLiteral b -> Right (XBoolTerm b);
          FStringLiteral text -> Right (XStringTerm text);
          FPrimitive p identities -> Right (XPrimitive p (map (referenceIn context) identities));
          FConstructor constructor identities ->
            Right (XConstructor constructor (map (referenceIn context) identities));
          FMatch scrutinee edge branches ->
            do {
              a <- childEdge scrutinee edge;
              branches' <-
                mapM
                  (\branch ->
                     case branch of {
                       Branch pattern body branchEdge ->
                         do {
                           body' <- childEdge body branchEdge;
                           Right (XAlternative pattern body')
                         }
                     })
                  branches;
              Right (XCase a (referenceIn context (G.genRoot graph gen)) branches')
            };
          FRecursive definitions body edge ->
            do {
              definitions' <-
                mapM
                  (\definition ->
                     case definition of {
                       RecursiveDefinition name declaration rhs rhsEdge closure ->
                         do {
                           rhs' <- case closure of {
                             Nothing -> childEdge rhs rhsEdge;
                             Just (RecursiveClosure group copies) ->
                               elaborateRecursiveScoped context datatypes evidence solver scope
                                 group copies declaration rhs rhsEdge
                           };
                           Right ((,,) name (schemeTypeIn context declaration) rhs')
                         }
                     })
                  definitions;
              body' <- childEdge body edge;
              Right (XLetRec definitions' body')
            };
          FEvidence _ -> dictionary;
          FScopedEvidence _ -> dictionary;
          FChecked variables body edge ->
            do {
              let {
                local =
                  extendElaborationScope scope
                    (map (\variable -> (,) (fst variable) (T.bottomKind (snd variable))) variables)
              };
              body' <- elaborateWithinScoped context datatypes evidence solver local body;
              proof <- edgeComputationScoped context datatypes solver local edge;
              let {
                abstracted =
                  foldr
                    (\variable inner -> XTypeAbs (fst variable) (T.bottomKind (snd variable)) inner)
                    (X.instantiate body' proof)
                    variables
              };
              let {
                actual =
                  foldr
                    (\variable inner -> XForall (fst variable) (T.bottomKind (snd variable)) inner)
                    (referenceIn context (C.toNode edge))
                    variables
              };
              let {
                expected = referenceIn context (G.genRoot graph gen)
              };
              let {
                positions = checkedCorrespondence graph (C.toNode edge) (G.genRoot graph gen)
              };
              let {
                kinds = M.fromList T.compareTyVar variables
              };
              adaptation <-
                proveInstanceUsingScope datatypes (checkedReplacementIn context positions kinds) scope
                  actual
                  expected;
              Right (X.instantiate abstracted adaptation)
            }
        } };
      body <- elaborateForm (C.rawForm typed);
      Right (foldr (\bound inner -> XTypeAbs (fst bound) (snd bound) inner) body bounds)
    };
  -- Projection replacements are planned in telescope order. In particular,
  -- dropping a peer-only bounded variable uses its CURRENT substituted bound,
  -- not a graph readback containing already-eliminated variables.
  recursiveReplacementIn context copies bounds gamma variable =
    do {
      replacements <- foldM
        (\known bound -> do {
           let { name = fst bound };
           value <- case IM.lookup (T.tyVarId name) copies of {
             Just target -> graphReplacementIn context (\_ -> target) gamma name;
             Nothing -> Right (foldl
               (\ty entry -> T.substitute (fst entry) (snd entry) ty) (snd bound) known)
           };
           Right (append known ((:) ((,) name value) []))
         }) [] bounds;
      case M.lookup T.compareTyVar variable (M.fromList T.compareTyVar replacements) of {
        Just value -> Right value;
        Nothing -> graphReplacementIn context
          (\identity -> IM.findWithDefault identity identity copies) gamma variable
      }
    };
  elaborateRecursiveIn context datatypes evidence solver env =
    elaborateRecursiveScoped context datatypes evidence solver (elaborationScope datatypes env);
  elaborateRecursiveScoped :: TypeContext -> DataEnv -> IntMap XTerm -> Solver ->
    ElaborationScope -> Int -> IntMap Int -> Int -> Typed -> Edge -> Either String XTerm;
  elaborateRecursiveScoped context datatypes evidence solver scope group copies declaration rhs edge =
    do {
      let { bounds = boundsAtIn context group };
      let { local = extendElaborationScope scope bounds };
      value <- elaborateEdgeScoped context datatypes evidence solver local rhs edge;
      let {
        source = foldr (\bound body -> XForall (fst bound) (snd bound) body)
          (referenceIn context (C.toNode edge)) bounds
      };
      let {
        abstracted = foldr (\bound body -> XTypeAbs (fst bound) (snd bound) body) value bounds
      };
      proof <- proveInstanceUsingScope datatypes (recursiveReplacementIn context copies bounds) scope
        source (schemeTypeIn context declaration);
      Right (X.instantiate abstracted proof)
    };
  checkedReplacementIn context positions kinds gamma variable =
    let {
      graph = contextGraph context
    } in
    case IM.lookup (T.tyVarId variable) positions of {
      Just identity ->
        Right
          (if M.member T.compareTyVar (XTyVar identity) gamma
           then XVar (XTyVar identity)
           else typeAtIn context identity);
      Nothing ->
        case M.lookup T.compareTyVar variable kinds of {
          Just kind -> Right (T.bottomKind kind);
          Nothing ->
            let {
              identity = G.resolve graph (T.tyVarId variable)
            } in
            if IM.member identity (G.nodes graph)
            then Right
                   (if M.member T.compareTyVar (XTyVar identity) gamma
                    then XVar (XTyVar identity)
                    else typeAtIn context identity)
            else Left ("checked declaration lost type provenance: " ++ showInt (T.tyVarId variable))
        }
    };
  checkedCorrespondence graph source target =
    checkedPositions graph IS.empty IM.empty ((:) ((,) source target) []);
  checkedPositions :: Graph -> IntSet -> IntMap Int -> [] ((,) Int Int) -> IntMap Int;
  checkedPositions _ _ images [] = images;
  checkedPositions graph seen images ((:) ((,) source target) rest) =
    let {
      a = G.resolve graph source
    } in
    let {
      b = G.resolve graph target
    } in
    if IS.member a seen
    then checkedPositions graph seen images rest
    else let {
           inserted = IM.insert a b images
         } in
         let {
           withSkolem =
             case G.tag (G.nodeAtRepresentative graph a a) of {
               GSkolem identity _ -> IM.insert identity b inserted;
               _ -> inserted
             }
         } in
         let {
           pairs = structuralPairs (G.tag (G.nodeAtRepresentative graph a a)) (G.tag (G.nodeAtRepresentative graph b b))
         } in
         checkedPositions graph (IS.insert a seen) withSkolem (append pairs rest);
  -- Public compatibility entry points used by graph-level callers.
  typeAt :: Graph -> Int -> XType;
  typeAt graph identity = typeAtIn (prepareTypes graph) identity;
  reference :: Graph -> Int -> XType;
  reference graph identity = referenceIn (prepareTypes graph) identity;
  boundsAt :: Graph -> Int -> [] ((,) XTyVar XType);
  boundsAt graph identity = boundsAtIn (prepareTypes graph) identity;
  schemeType :: Graph -> Int -> XType;
  schemeType graph identity = schemeTypeIn (prepareTypes graph) identity
}
