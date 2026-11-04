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
  import qualified Bootstrap.Resolved as R;
  import qualified Bootstrap.IntSet as IS;
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

  -- Path-based SCCs (Gabow). A positive mark is an open DFS preorder,
  -- zero is unseen, and -1 is closed. Boundaries are candidate SCC roots.
  -- An edge to an open vertex merges all boundaries discovered after it.
  -- Closing a surviving root emits exactly one component, in finish order.
  data ModuleVertex = ModuleVertex;
  componentsById :: forall d. Rows d -> [] (V.Index d) -> [] ([] (V.Index d));
  componentsById (Rows rows) roots = runST (stBind (V.filled (V.count rows) 0) (\marks ->
    scanComponents rows marks 1 (map Enter roots) [] [] []));
  scanComponents :: forall s d. V.IndexVec d (V.IndexVec EdgeSlot (V.Index d)) ->
    V.Builder s d Int -> Int -> [] (Visit d) -> [] (V.Index d) -> [] ((,) (V.Index d) Int) ->
    [] ([] (V.Index d)) -> ST s ([] ([] (V.Index d)));
  scanComponents rows marks serial pending open boundaries groups = case pending of {
    [] -> stReturn (reverse groups);
    (:) (Enter i) rest -> stBind (V.get marks i) (\mark ->
      if mark == 0 then stBind (V.set marks i serial) (\_ ->
        let { next = serial + 1;
              tasks = foldr (\j more -> (:) (Enter j) more) ((:) (Leave i) rest)
                (V.toList (V.at rows i)) } in
        seq next (scanComponents rows marks next tasks ((:) i open) ((:) ((,) i serial) boundaries) groups))
      else scanComponents rows marks serial rest open
        (if mark < 0 then boundaries else dropWhile (\entry -> snd entry > mark) boundaries) groups);
    (:) (Leave i) rest -> case boundaries of {
      (:) ((,) root _) older -> if V.toInt root == V.toInt i
        then stBind (closeComponent marks root open []) (\((,) members remaining) ->
          scanComponents rows marks serial rest remaining older ((:) members groups))
        else scanComponents rows marks serial rest open boundaries groups;
      [] -> panic "missing SCC boundary"
    }
  };
  closeComponent :: forall s d. V.Builder s d Int -> V.Index d -> [] (V.Index d) ->
    [] (V.Index d) -> ST s ((,) ([] (V.Index d)) ([] (V.Index d)));
  closeComponent marks root open members = case open of {
    [] -> panic "missing open SCC root";
    (:) i rest -> stBind (V.set marks i (0 - 1)) (\_ ->
      if V.toInt i == V.toInt root then stReturn ((,) ((:) i members) rest)
      else closeComponent marks root rest ((:) i members))
  };
  -- SCCs close dependency-first. All members of a component share one
  -- immutable reach set. Internal edges still point to empty slots until
  -- the entire component is published; external successors are complete.
  reachTable :: forall d. Rows d -> V.IndexVec d IntSet;
  reachTable rows@(Rows table) = runST (stBind (V.filled (V.count table) IS.empty) (\closed ->
    stBind (ST.map_ (closeReach rows closed) (componentsById rows (V.indices table))) (\_ ->
      V.freeze closed)));
  closeReach :: forall s d. Rows d -> V.Builder s d IntSet -> [] (V.Index d) -> ST s ();
  closeReach rows closed group =
    let { addEdge reached j = stBind (V.get closed j) (\child ->
            let { next = IS.union reached child } in seq next (stReturn next));
          addMember reached i = ST.fold addEdge (IS.insert (V.toInt i) reached) (neighbors rows i)
    } in stBind (ST.fold addMember IS.empty group) (\reached ->
      ST.map_ (\i -> V.set closed i reached) group);
  -- Repeated keys select the last entry. Roots, outgoing rows and group
  -- members are lexical, independently of source declaration order.
  nameGraph :: forall d. [] ((,) String ([] String)) -> NamedGraph d ((,) String ([] String));
  nameGraph entries =
    let { values = M.toList (M.fromList compareString entries);
      nodes = V.fromList values;
      names = M.fromDistinctAscList (zipWith (\entry i -> (,) (fst entry) i) values (V.indices nodes));
      row entry = V.fromList (map V.fromInt (IS.toAscList (foldlStrict (\seen name ->
        case M.lookup compareString name names of {
          Nothing -> seen; Just j -> IS.insert (V.toInt j) seen
        }) IS.empty (snd entry))))
    } in NamedGraph names nodes (Rows (V.fromList (map row values)));
  declarationGraph :: [] ((,) String ([] String)) -> NamedGraph Declaration ((,) String ([] String));
  declarationGraph = nameGraph;
  moduleGraph :: [] ((,) String ([] String)) -> NamedGraph ModuleVertex ((,) String ([] String));
  moduleGraph = nameGraph;
  components :: [] ((,) String ([] String)) -> [] ([] String);
  components entries = case entries of {
    [] -> [];
    [(,) name _] -> [[name]];
    _ -> groupNames (declarationGraph entries)
  };
  groupNames :: forall d. NamedGraph d ((,) String ([] String)) -> [] ([] String);
  groupNames graph =
    let {
      nodes = graphNodes graph;
      rows = graphRows graph;
      groups = componentsById rows (V.indices nodes)
    } in map (\group -> sortBy compareString (map (\i -> fst (V.at nodes i)) group)) groups;
  -- Semantic declaration IDs belong to one resolution. Source occurrences
  -- already carry them. Later class-support bindings extend the same domain.
  data DeclOrder = DeclOrder;
  -- Each slot owns its canonical spelling and stable definition key. A
  -- resolved entity can share its *printed* name with an inactive import.
  -- Only the stable keys cross a resolution or link-session boundary.
  data Symbols = Symbols (V.IndexVec Declaration String) ([] (V.Index Declaration)) IntSet
                         (V.IndexVec Declaration String);
  symbolNodes (Symbols nodes _ _ _) = nodes;
  symbolName symbols = V.at (symbolNodes symbols);
  symbolKey (Symbols _ _ _ keys) = V.at keys;
  symbolKeyIndex table = M.fromList compareString
    (map (\i -> (,) (symbolKey table i) i) (V.indices (symbolNodes table)));
  checkedDeclId :: Symbols -> Int -> Either String (V.Index Declaration);
  checkedDeclId table number =
    if number >= 0 && number < V.count (symbolNodes table) then Right (V.fromInt number)
    else Left "declaration slot out of bounds";
  compareSlots nodes i j = compareString (V.at nodes i) (V.at nodes j);
  symbolsWithKeys entries =
    let { nodes = V.fromList (map (\((,,) name _ _) -> name) entries); indices = V.indices nodes;
          methods = mapMaybe (\((,) ((,,) _ _ method) i) -> if method then Just (V.toInt i) else Nothing)
                      (zip entries indices);
          keys = V.fromList (map (\((,,) _ key _) -> key) entries)
    } in Symbols nodes (sortBy (compareSlots nodes) indices) (IS.fromList methods) keys;
  -- Named adapters and standalone link sessions already have stable names.
  symbols entries = symbolsWithKeys (map (\((,) n m) -> (,,) n n m) entries);
  -- Generated names are qualified by their owner at the lowering boundary.
  -- The returned slots belong to the new snapshot, in the caller's order.
  appendSymbols original@(Symbols nodes order methods keys) names = case names of {
    [] -> (,) original [];
    _ -> let { allNodes = V.fromList (append (V.toList nodes) names);
               allKeys = V.fromList (append (V.toList keys) names);
               extra = map V.fromInt (range (V.count nodes) (V.count allNodes - 1));
               cmp = compareSlots allNodes
         } in (,) (Symbols allNodes (mergeBy cmp order (sortBy cmp extra)) methods allKeys) extra
  };
  extendSymbols table names = fst (appendSymbols table names);
  -- Visibility belongs to the defining declaration. Only active definitions
  -- enter the adapter used by the named surface/class lowering boundary.
  data ValueScopes a = NamedScopes (Map String a) |
    IndexedScopes Bool Symbols (Map String (V.Index Declaration)) (V.IndexVec Declaration (Maybe a));
  indexedScopes symbols entries = let {
    names = M.fromList compareString (map (\((,) i _) -> (,) (symbolName symbols i) i) entries);
    table = runST (stBind (V.filled (V.count (symbolNodes symbols)) Nothing) (\rows ->
      stBind (ST.map_ (\((,) i a) -> V.set rows i (Just a)) entries) (\_ -> V.freeze rows)))
  } in IndexedScopes True symbols names table;
  mapScopes f scopes = case scopes of {
    NamedScopes named -> NamedScopes (M.map f named);
    IndexedScopes top symbols names table -> IndexedScopes top symbols names
      (V.fromList (map (mapOptional f) (V.toList table)))
  };
  namedScopes scopes = case scopes of {
    NamedScopes named -> named;
    IndexedScopes _ _ names table -> M.map (\i -> case V.at table i of {
      Just a -> a; Nothing -> panic "inactive declaration scope"
    }) names
  };
  lookupScope name scopes = case scopes of {
    NamedScopes named -> M.lookup compareString name named;
    IndexedScopes _ _ names table -> case M.lookup compareString name names of {
      Nothing -> Nothing; Just i -> V.at table i
    }
  };
  scopeAt scopes i = case scopes of {
    IndexedScopes _ _ _ table -> V.at table i;
    NamedScopes _ -> panic "named visibility has no declaration IDs"
  };
  nestedScopes scopes = case scopes of {
    IndexedScopes _ symbols names table -> IndexedScopes False symbols names table;
    NamedScopes _ -> scopes
  };
  bindingScope scopes name copied fallback = case scopes of {
    IndexedScopes False _ _ _ -> if copied then fromMaybe fallback (lookupScope name scopes) else fallback;
    _ -> fromMaybe fallback (lookupScope name scopes)
  };
  data Bound = Bound (V.Index Declaration) (Maybe SAnnotation) (R.Expr Declaration);
  boundId (Bound i _ _) = i;
  boundValue symbols (Bound i annotation rhs) = let { name = symbolName symbols } in
    (,,) (name i) annotation (R.namedExpr name rhs);
  data BoundValues = BoundValues Symbols ([] Bound);
  boundValues (BoundValues symbols rows) = map (boundValue symbols) rows;
  boundTable (BoundValues symbols bindings) = runST
    (stBind (V.filled (V.count (symbolNodes symbols)) Nothing) (\slots ->
      stBind (ST.map_ (\b -> V.set slots (boundId b) (Just b)) bindings) (\_ -> V.freeze slots)));
  appendBound (BoundValues old rows) name rhs =
    case appendSymbols old [name] of {
      (,) table [i] -> BoundValues table (append rows [Bound i Nothing rhs]);
      _ -> panic "missing appended declaration slot"
    };
  -- Only later-generated syntax arrives by spelling. Source edges use the
  -- Global leaf of the resolved expression directly.
  namedRank :: V.IndexVec Declaration String -> V.IndexVec DeclOrder (V.Index Declaration) ->
    String -> Maybe (V.Index DeclOrder);
  namedRank nodes order name =
    let { search lo hi = if lo >= hi then Nothing else
            let { mid = lo + quotInt (hi - lo) 2; rank = V.fromInt mid;
                  cmp = compareString name (V.at nodes (V.at order rank)) } in
            if cmp < 0 then search lo mid else if cmp > 0 then search (mid + 1) hi else Just rank
    } in search 0 (V.count order);
  uniqueSlots nodes ordered = case ordered of {
    (:) i rest@((:) j _) -> compareSlots nodes i j /= 0 && uniqueSlots nodes rest;
    _ -> True
  };
  -- Keep the resolver's IDs even when a later selector sorts before a source
  -- declaration. Dense lexical ranks order DFS roots, siblings and members.
  resolvedGroups :: BoundValues -> [] ((,) String ([] String)) -> Map String ((,) String ([] String)) ->
    Map String ([] String) -> Either String ((,) Symbols ([] ([] ((,) (V.Index Declaration) Bool))));
  resolvedGroups bindings generated methods scopes = resolvedGroupsInScopes bindings generated methods (NamedScopes scopes);
  resolvedGroupsInScopes (BoundValues base bound) generated methods scopes = do {
    let { extended = appendSymbols base (map fst generated); symbols = fst extended;
          nodes = symbolNodes symbols; generatedIds = snd extended;
          present = append (map boundId bound) generatedIds;
          active = IS.fromList (map V.toInt present);
          presentId i = IS.member (V.toInt i) active;
          duplicate = if null generated then "duplicate value declaration" else "duplicate source/support binding";
          orderedIds = case symbols of { Symbols _ indices _ _ -> filter presentId indices }
    };
    let { valid i = V.toInt i >= 0 && V.toInt i < V.count (symbolNodes base);
          referencesInRange (Bound i _ rhs) = valid i && all valid (R.references rhs) };
    ensure (all referencesInRange bound) "declaration slot out of bounds";
    ensure (IS.size active == length present && uniqueSlots nodes orderedIds) duplicate;
    let { order = V.fromList orderedIds;
          ranks edits = runST (stBind (V.filled (V.count nodes) Nothing) (\slots ->
            stBind (ST.map_ (\r -> V.set slots (V.at order r) (Just r)) (V.indices order)) (\_ ->
            stBind (ST.map_ (\((,) i target) -> V.set slots i target) edits) (\_ -> V.freeze slots))));
          direct = ranks [];
          byName = namedRank nodes order;
          redirect n = let { i = V.fromInt n } in case M.lookup compareString (V.at nodes i) methods of {
            Nothing -> Nothing; Just ((,) target _) -> Just ((,) i (byName target))
          };
          sourceRanks = if M.null methods then direct else case symbols of {
            Symbols _ _ methodIds _ -> ranks (mapMaybe redirect (IS.toAscList methodIds))
          };
          edgeRow targets = V.fromList (map (\r -> V.at order (V.fromInt r))
            (IS.toAscList (IS.fromList (map V.toInt targets))));
          sourceRow (Bound i _ rhs) = (,) i (edgeRow (append (mapMaybe (V.at sourceRanks) (R.references rhs))
            (mapMaybe byName (fromMaybe [] (case scopes of { NamedScopes values -> M.lookup compareString (V.at nodes i) values; IndexedScopes _ _ _ _ -> scopeAt scopes i })))));
          generatedRow i entry = (,) i (edgeRow (mapMaybe byName (snd entry)));
          rows = runST (stBind (V.filled (V.count nodes) (V.fromList [])) (\slots ->
            stBind (ST.map_ (\((,) i row) -> V.set slots i row)
              (append (map sourceRow bound) (zipWith generatedRow generatedIds generated))) (\_ ->
                stBind (V.freeze slots) (\table -> stReturn (Rows table)))));
          member i = (,) i (any (\j -> V.toInt i == V.toInt j) (neighbors rows i));
          ordered group = map member (sortBy (\i j -> compareString (V.at nodes i) (V.at nodes j)) group)
    };
    Right ((,) symbols (map ordered (componentsById rows (V.toList order))))
  };
  groupSpellings ((,) symbols groups) = map (map (compose (V.at (symbolNodes symbols)) fst)) groups;
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
