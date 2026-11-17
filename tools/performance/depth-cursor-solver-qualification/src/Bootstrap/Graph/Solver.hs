-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Graph.Solver where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntRank as Rank;
  import qualified Bootstrap.Graph as G;
  -- The incremental solver projects a component closed under both directions
  -- of type structure and binding. Generalization scopes are retained with
  -- their common ancestors; unused scope roots have private bottom witnesses.
  solverGraph :: Solver -> Graph;
  solverGraph (Solver graph parents descendants scopes) = graph;
  graph :: Solver -> Graph;
  graph solver = solverGraph solver;
  structuralParents :: Solver -> IntMap IntSet;
  structuralParents (Solver graph parents descendants scopes) = parents;
  bindingChildren :: Solver -> IntMap IntSet;
  bindingChildren (Solver graph parents descendants scopes) = descendants;
  scopeIndex :: Solver -> ScopeIndex;
  scopeIndex (Solver graph parents descendants scopes) = scopes;
  scopeIntervals :: ScopeIndex -> IntMap ((,) Int Int);
  scopeIntervals (ScopeIndex intervals jumps) = intervals;
  forceIntSet :: IntSet -> ();
  forceIntSet (IntSet tree) = seq tree ();
  strictScopes :: ScopeIndex -> ScopeIndex;
  -- The scope index is immutable across component updates. Force its required
  -- fields without allocating another wrapper for every added/removed node.
  strictScopes scopes =
    case scopes of {
      ScopeIndex intervals jumps -> seq (G.forceIntMap intervals) (seq jumps scopes)
    };
  mkSolver :: Graph -> IntMap IntSet -> IntMap IntSet -> ScopeIndex -> Solver;
  mkSolver current parents descendants scopes =
    let {
      strict = G.strictGraph current
    } in
    let {
      strictIndex = strictScopes scopes
    } in
    seq strict
      (seq (G.forceIntMap parents)
         (seq (G.forceIntMap descendants)
            (seq strictIndex (Solver strict parents descendants strictIndex))));
  withGraph :: Graph -> Solver -> Solver;
  withGraph graph (Solver old parents descendants scopes) =
    mkSolver graph parents descendants scopes;
  insertIndex :: Int -> Int -> IntMap IntSet -> IntMap IntSet;
  insertIndex key value (IntMap tree) = IM.wrap (insertIndexTree key value tree);
  -- One Patricia traversal updates a reverse edge. Changed set roots remain
  -- strict, while unrelated map values retain their existing laziness.
  insertIndexTree :: Int -> Int -> IntMapTree IntSet -> IntMapTree IntSet;
  insertIndexTree key value tree =
    IM.alterTree
      (\previous ->
        let { updated = case previous of {
          Nothing -> IS.singleton value;
          Just old -> IS.insert value old
        } } in
        seq (forceIntSet updated) (Just updated)) key tree;
  removeIndex :: Int -> Int -> IntMap IntSet -> IntMap IntSet;
  removeIndex key value (IntMap tree) = IM.wrap (removeIndexTree key value tree);
  removeIndexTree :: Int -> Int -> IntMapTree IntSet -> IntMapTree IntSet;
  removeIndexTree key value tree =
    IM.alterTree
      (\previous -> case previous of {
        Nothing -> Nothing;
        Just old -> let { remaining = IS.delete value old } in
          if IS.size remaining == 0 then Nothing else Just remaining
      }) key tree;
  addNode :: Solver -> (,) Int Node -> Solver;
  addNode (Solver graph parents descendants scopes) ((,) n v) =
    mkSolver graph
      (L.foldlStrict (\index -> \child -> insertIndex child n index) parents (G.children (G.tag v)))
      (case G.binder v of {
         Nothing -> descendants;
         Just parent -> insertIndex parent n descendants
       })
      scopes;
  removeNode :: Solver -> (,) Int Node -> Solver;
  removeNode (Solver graph parents descendants scopes) ((,) n v) =
    mkSolver graph
      (L.foldlStrict (\index -> \child -> removeIndex child n index) parents (G.children (G.tag v)))
      (case G.binder v of {
         Nothing -> descendants;
         Just parent -> removeIndex parent n descendants
       })
      scopes;
  scopeVisit :: IntMap ([] Int) ->
                (,) Int (IntMap ((,) Int Int)) -> Int -> (,) Int (IntMap ((,) Int Int));
  scopeVisit descendants ((,) start intervals) n =
    case L.foldlStrict (scopeVisit descendants) (G.strictPair (start + 1) intervals)
           (IM.findWithDefault [] n descendants) of {
      (,) end final -> G.strictPair end (IM.insert n (G.strictPair start end) final)
    };
  scopeLevels :: Int -> Int;
  scopeLevels count = if (count <= 1) then 1 else (1 + scopeLevels (quotInt count 2 + remInt count 2));
  scopeJumps :: Int -> IntMap Int -> [] (IntMap Int);
  scopeJumps count parents =
    if (count <= 0)
    then []
    else (:) parents (scopeJumps (count - 1) (IM.map (\n -> IM.get n parents) parents));
  indexScopes :: Graph -> ScopeIndex;
  indexScopes graph =
    let {
      gens = IM.filter (\v -> G.isGen (G.tag v)) (G.nodes graph)
    } in
    let {
      parents =
        IM.mapWithKey
          (\n ->
             \v ->
               case G.binder v of {
                 Nothing -> n;
                 Just b -> G.resolve graph b
               })
          gens
    } in
    let {
      descendants =
        L.foldlStrict
          (\table ->
             \entry ->
               case entry of {
                 (,) n p ->
                   if (n == p)
                   then table
                   else let {
                          previous = IM.findWithDefault [] p table
                        } in
                        seq previous (IM.insert p ((:) n previous) table)
               })
          IM.empty
          (IM.toList parents)
    } in
    let {
      roots =
        L.map
          (\entry ->
             case entry of {
               (,) n p -> n
             })
          (L.filter
             (\entry ->
                case entry of {
                  (,) n p -> (n == p)
                })
             (IM.toList parents))
    } in
    case L.foldlStrict (scopeVisit descendants) ((,) 0 IM.empty) roots of {
      (,) count intervals -> ScopeIndex intervals (scopeJumps (scopeLevels (IM.size gens)) parents)
    };
  scopeContains :: ScopeIndex -> Int -> Int -> Bool;
  scopeContains (ScopeIndex intervals jumps) a b = G.intervalContains intervals a b;
  scopeLCA :: ScopeIndex -> Int -> Int -> Int;
  scopeLCA (ScopeIndex intervals jumps) a b =
    let {
      scopes = ScopeIndex intervals jumps
    } in
    if scopeContains scopes a b
    then a
    else if scopeContains scopes b a
         then b
         else case jumps of {
                [] -> panic "empty scope ancestry index";
                (:) parents rest ->
                  IM.get
                    (L.foldr
                       (\level ->
                          \n ->
                            let {
                              parent = IM.get n level
                            } in
                            if scopeContains scopes parent b then n else parent)
                       a
                       jumps)
                    parents
              };
  sortScopes :: ScopeIndex -> IntSet -> [] Int;
  -- Cache each immutable interval key once, as the seed's sortOn does.
  sortScopes (ScopeIndex intervals jumps) seeds =
    let {
      keyed = L.map (\n -> (,) (L.fst (IM.get n intervals)) n) (IS.toList seeds)
    } in
    L.map L.snd (L.sortBy (\a -> \b -> L.compareInt (L.fst a) (L.fst b)) keyed);
  scopeRoot :: ScopeIndex -> Int -> Int;
  scopeRoot (ScopeIndex intervals jumps) n =
    case jumps of {
      [] -> panic "empty scope ancestry index";
      _ -> IM.get n (L.last jumps)
    };
  projectScopes :: ScopeIndex -> IntSet -> IntMap (Maybe Int);
  projectScopes scopes seeds =
    let {
      boundary = sortScopes scopes seeds
    } in
    let {
      adjacent = L.zip boundary (L.drop 1 boundary)
    } in
    let {
      closure =
        L.foldlStrict
          (\seen ->
             \entry ->
               case entry of {
                 (,) a b -> IS.insert (scopeLCA scopes a b) seen
               })
          seeds
          adjacent
    } in
    let {
      allScopes =
        L.foldlStrict (\seen -> \n -> IS.insert (scopeRoot scopes n) seen) closure boundary
    } in
    let {
      ordered = sortScopes scopes allScopes
    } in
    case L.foldlStrict (attachScope scopes) ((,) [] IM.empty) ordered of {
      (,) ancestors parents -> parents
    };
  attachScope :: ScopeIndex ->
                 (,) ([] Int) (IntMap (Maybe Int)) ->
                 Int -> (,) ([] Int) (IntMap (Maybe Int));
  attachScope scopes ((,) ancestors parents) n =
    let {
      enclosing = L.dropWhile (\a -> L.not (scopeContains scopes a n)) ancestors
    } in
    let {
      parent =
        case enclosing of {
          [] -> Nothing;
          (:) p rest -> Just p
        }
    } in
    seq parent (G.strictPair ((:) n enclosing) (IM.insert n parent parents));
  prepare :: Graph -> Either String Solver;
  prepare input =
    G.bindE (G.validateGraph input)
      (\ignored ->
         if L.any (\n -> IM.member n (G.links input)) (IM.keys (G.nodes input))
         then Left "live graph identities cannot also be aliases"
         else if L.any (\n -> (n >= G.nextId input)) (IM.keys (G.nodes input))
              then Left "fresh identity counter overlaps graph nodes"
              else if L.any (\n -> (n >= G.nextId input)) (IM.keys (G.links input))
                   then Left "fresh identity counter overlaps graph aliases"
                   else let {
                          canonical = G.canonicalize input
                        } in
                        Right
                          (L.foldlStrict addNode
                             (mkSolver canonical IM.empty IM.empty (indexScopes canonical))
                             (IM.toList (G.nodes canonical))));
  equalIntervals :: IntMap ((,) Int Int) -> IntMap ((,) Int Int) -> Bool;
  equalIntervals a b =
    IM.eqIntMap
      (\p ->
         \q ->
           case p of {
             (,) x y ->
               case q of {
                 (,) z w -> ((x == z) && (y == w))
               }
           })
      a
      b;
  equalScopes :: ScopeIndex -> ScopeIndex -> Bool;
  equalScopes (ScopeIndex first left) (ScopeIndex second right) =
    (equalIntervals first second && L.eqList (IM.eqIntMap (\a -> \b -> (a == b))) left right);
  -- Check both directions instead of constructing a second persistent index.
  -- Ordered enumeration and root cardinalities preserve eqIntMap/eqIntSet's
  -- observable checks, including malformed, empty and duplicate index entries.
  ascending :: [] Int -> Bool;
  ascending keys =
    case keys of {
      [] -> True;
      (:) first rest -> ascendingAfter first rest
    };
  ascendingAfter :: Int -> [] Int -> Bool;
  ascendingAfter previous keys =
    case keys of {
      [] -> True;
      (:) first rest -> ((previous < first) && ascendingAfter first rest)
    };
  indexEntryAgrees :: Graph -> Bool -> (,) Int IntSet -> Bool;
  indexEntryAgrees current structural ((,) target sources) =
    let {
      entries = IS.toList sources
    } in
    ((IS.size sources == L.length entries) &&
     (L.not (L.null entries) &&
      (ascending entries &&
       L.all
         (\source ->
            case IM.lookup source (G.nodes current) of {
              Nothing -> False;
              Just node ->
                if structural
                then L.any (\child -> (child == target)) (G.children (G.tag node))
                else case G.binder node of {
                       Nothing -> False;
                       Just parent -> (parent == target)
                     }
            })
         entries)));
  indexAgrees :: Graph -> Bool -> IntMap IntSet -> Bool;
  indexAgrees current structural index =
    let {
      entries = IM.toList index
    } in
    ((IM.size index == L.length entries) &&
     (ascending (L.map L.fst entries) && L.all (indexEntryAgrees current structural) entries));
  nodeIndexed :: IntMap IntSet -> IntMap IntSet -> (,) Int Node -> Bool;
  nodeIndexed parents descendants ((,) n node) =
    (L.all (\child -> IS.member n (IM.findWithDefault IS.empty child parents))
       (G.children (G.tag node)) &&
     (case G.binder node of {
        Nothing -> True;
        Just parent -> IS.member n (IM.findWithDefault IS.empty parent descendants)
      }));
  -- For distinct graph identities, membership of every required edge plus
  -- equal cardinalities proves equality of the two finite edge sets. Audit
  -- index ordering, recorded sizes and nonempty buckets before counting; this
  -- retains the malformed-index checks without a second graph lookup per edge.
  ascendingNodes :: [] ((,) Int Node) -> Bool;
  ascendingNodes entries =
    case entries of {
      [] -> True;
      (:) ((,) n _) rest -> ascendingNodesAfter n rest
    };
  ascendingNodesAfter :: Int -> [] ((,) Int Node) -> Bool;
  ascendingNodesAfter previous entries =
    case entries of {
      [] -> True;
      (:) ((,) n _) rest -> ((previous < n) && ascendingNodesAfter n rest)
    };
  indexCardinality :: IntMap IntSet -> Maybe Int;
  indexCardinality index =
    let {
      entries = IM.toList index
    } in
    if ((IM.size index == L.length entries) && ascending (L.map L.fst entries))
    then indexCardinalityFrom 0 entries
    else Nothing;
  indexCardinalityFrom :: Int -> [] ((,) Int IntSet) -> Maybe Int;
  indexCardinalityFrom total entries =
    case entries of {
      [] -> Just total;
      (:) ((,) _ sources) rest ->
        let {
          members = IS.toList sources
        } in
        if ((IS.size sources == L.length members) && (L.not (L.null members) && ascending members))
        then let {
               next = (total + IS.size sources)
             } in
             seq next (indexCardinalityFrom next rest)
        else Nothing
    };
  distinctChildCount :: [] Int -> Int;
  distinctChildCount children =
    case children of {
      [] -> 0;
      (:) _ [] -> 1;
      (:) a ((:) b []) -> if (a == b) then 1 else 2;
      _ -> IS.size (IS.fromList children)
    };
  requiredCardinalities :: [] ((,) Int Node) -> (,) Int Int;
  requiredCardinalities entries =
    L.foldlStrict
      (\((,) structural binding) ((,) _ node) ->
         let {
           nextStructural = (structural + distinctChildCount (G.children (G.tag node)))
         } in
         let {
           nextBinding =
             (binding +
              (case G.binder node of {
                 Nothing -> 0;
                 Just _ -> 1
               }))
         } in
         seq nextStructural (seq nextBinding ((,) nextStructural nextBinding)))
      ((,) 0 0)
      entries;
  indicesAgree :: Graph -> IntMap IntSet -> IntMap IntSet -> Bool;
  -- Preserve the preceding audit for manually forged non-BST node maps.
  indicesAgree current parents descendants =
    let {
      entries = IM.toList (G.nodes current)
    } in
    if L.not (ascendingNodes entries)
    then (indexAgrees current True parents &&
          (indexAgrees current False descendants &&
           L.all (nodeIndexed parents descendants) entries))
    else case indexCardinality parents of {
           Nothing -> False;
           Just structural ->
             case indexCardinality descendants of {
               Nothing -> False;
               Just binding ->
                 case requiredCardinalities entries of {
                   (,) expectedStructural expectedBinding ->
                     ((structural == expectedStructural) &&
                      ((binding == expectedBinding) &&
                       L.all (nodeIndexed parents descendants) entries))
                 }
             }
         };
  -- The complete graph check in finish establishes a binding tree whose
  -- Gen nodes form this ancestry forest. Validate the stored DFS intervals
  -- against the exact original child/root order, and validate jump levels by
  -- their defining recurrence. No expected interval/jump trees are allocated.
  -- Exact map keys and recorded root sizes are checked, including forged maps.
  equalScopeLevel :: IntMap Int -> IntMap Int -> Bool;
  equalScopeLevel previous next =
    ((IM.size previous == IM.size next) &&
     equalScopeEntries previous (IM.toList previous) (IM.toList next));
  equalScopeEntries :: IntMap Int -> [] ((,) Int Int) -> [] ((,) Int Int) -> Bool;
  equalScopeEntries previous before after =
    case before of {
      [] -> L.null after;
      (:) ((,) n parent) rest ->
        case after of {
          [] -> False;
          (:) ((,) m ancestor) tail ->
            ((n == m) &&
             ((IM.get parent previous == ancestor) && equalScopeEntries previous rest tail))
        }
    };
  scopeLevelCount :: IntMap Int -> Int -> [] (IntMap Int) -> Bool;
  scopeLevelCount previous remaining levels =
    if (remaining == 0)
    then L.null levels
    else case levels of {
           [] -> False;
           (:) next rest ->
             (equalScopeLevel previous next && scopeLevelCount next (remaining - 1) rest)
         };
  scopeCheckedVisit :: IntMap ([] Int) -> IntMap ((,) Int Int) -> Int -> Int -> Maybe Int;
  scopeCheckedVisit descendants intervals position n =
    case IM.lookup n intervals of {
      Nothing -> Nothing;
      Just ((,) start end) ->
        if (start /= position)
        then Nothing
        else case scopeCheckedChildren descendants intervals (position + 1)
                    (IM.findWithDefault [] n descendants) of {
               Nothing -> Nothing;
               Just actualEnd -> if (actualEnd == end) then Just end else Nothing
             }
    };
  scopeCheckedChildren :: IntMap ([] Int) ->
                          IntMap ((,) Int Int) -> Int -> [] Int -> Maybe Int;
  scopeCheckedChildren descendants intervals position children =
    case children of {
      [] -> Just position;
      (:) child rest ->
        case scopeCheckedVisit descendants intervals position child of {
          Nothing -> Nothing;
          Just next -> scopeCheckedChildren descendants intervals next rest
        }
    };
  scopesAgreeValidated :: Graph -> ScopeIndex -> Bool;
  -- Preserve the general audit on a graph outside the validated Gen
  -- forest precondition, including its existing failure behavior.
  scopesAgreeValidated graph actual =
    case actual of {
      ScopeIndex intervals levels ->
        let {
          gens = L.filter (\((,) _ node) -> G.isGen (G.tag node)) (IM.toList (G.nodes graph))
        } in
        let {
          parents =
            L.map
              (\((,) n node) ->
                 (,) n
                   (case G.binder node of {
                      Nothing -> n;
                      Just parent -> G.resolve graph parent
                    }))
              gens
        } in
        let {
          names = L.map L.fst parents
        } in
        let {
          count = L.length parents
        } in
        if L.not (ascending names)
        then equalScopes actual (indexScopes graph)
        else case levels of {
               [] -> False;
               (:) first rest ->
                 if ((IM.size first /= count) ||
                     L.not
                       (L.eqList (\((,) n p) ((,) m q) -> ((n == m) && (p == q)))
                          (IM.toList first)
                          parents))
                 then False
                 else if L.not (L.all (\((,) _ parent) -> IM.member parent first) parents)
                      then equalScopes actual (indexScopes graph)
                      else if ((IM.size intervals /= count) ||
                               L.not (L.eqList eqInt (IM.keys intervals) names))
                           then False
                           else let {
                                  descendants =
                                    L.foldlStrict
                                      (\table ((,) n parent) ->
                                         if (n == parent)
                                         then table
                                         else let {
                                                previous = IM.findWithDefault [] parent table
                                              } in
                                              seq previous
                                                (IM.insert parent ((:) n previous) table))
                                      IM.empty
                                      parents
                                } in
                                let {
                                  roots =
                                    L.map L.fst
                                      (L.filter (\((,) n parent) -> (n == parent)) parents)
                                } in
                                case scopeCheckedChildren descendants intervals 0 roots of {
                                  Nothing -> False;
                                  Just actualCount ->
                                    ((actualCount == count) &&
                                     scopeLevelCount first (scopeLevels count - 1) rest)
                                }
             }
    };
  finish :: Solver -> Either String Graph;
  finish solver =
    G.bindE (G.validateGraph (graph solver))
      (\ignored ->
         let {
           current = graph solver
         } in
         let {
           parents = structuralParents solver
         } in
         let {
           descendants = bindingChildren solver
         } in
         if (indicesAgree current parents descendants &&
             scopesAgreeValidated current (scopeIndex solver))
         then Right current
         else Left "incremental graph index disagrees with the graph");
  -- Normalization only changes flags on non-Gen nodes. It preserves every tag,
  -- structural edge, binder, identity and alias, and leaves Gen flags unchanged.
  -- These are exactly the facts checked by validateGraph and the reverse/scope
  -- index audit in finish, so the checked result remains valid after normalization.
  finishNormalized :: Solver -> Either String Solver;
  finishNormalized solver =
    G.bindE (finish solver) (\checked -> Right (withGraph (G.normalize checked) solver));
  -- Collect scope boundaries while inspecting each newly discovered node.
  -- The identity has just been resolved, so a second alias lookup is redundant.
  componentScopesVisit :: Solver ->
                          IntSet -> IntSet -> [] Int -> Either String ((,) IntSet IntSet);
  componentScopesVisit solver seen scopes pending =
    case pending of {
      [] -> Right ((,) seen scopes);
      (:) original rest ->
        let {
          currentGraph = graph solver
        } in
        let {
          n = G.resolve currentGraph original
        } in
        if IS.member n seen
        then componentScopesVisit solver seen scopes rest
        else case IM.lookup n (G.nodes currentGraph) of {
               Nothing -> Left ("missing graph node " ++ showInt n);
               Just node ->
                 let {
                   boundary = G.isGen (G.tag node)
                 } in
                 let {
                   connected =
                     if boundary
                     then rest
                     else L.append (G.children (G.tag node))
                            (L.append (L.maybeToList (G.binder node))
                               (L.append
                                  (IS.toList
                                     (IM.findWithDefault IS.empty n (structuralParents solver)))
                                  (L.append
                                     (IS.toList
                                        (IM.findWithDefault IS.empty n (bindingChildren solver)))
                                     rest)))
                 } in
                 componentScopesVisit solver (IS.insert n seen)
                   (if boundary then IS.insert n scopes else scopes)
                   connected
             }
    };
  -- Prepared solver graphs keep canonical live fields; callers resolve only
  -- incoming external equation identities before entering this traversal.
  -- Keep the nodes already read while discovering a canonical component.
  -- The projection uses this same immutable view, including scope ancestors.
  componentCanonicalNodesVisit :: Solver ->
                                  IntMap Node ->
                                  IntSet -> [] Int -> Either String ((,) (IntMap Node) IntSet);
  componentCanonicalNodesVisit solver seen scopes pending =
    case pending of {
      [] -> Right ((,) seen scopes);
      (:) original rest ->
        let {
          currentGraph = graph solver
        } in
        let {
          n = original
        } in
        if IM.member n seen
        then componentCanonicalNodesVisit solver seen scopes rest
        else case IM.lookup n (G.nodes currentGraph) of {
               Nothing -> Left ("missing graph node " ++ showInt n);
               Just node ->
                 let {
                   boundary = G.isGen (G.tag node)
                 } in
                 let {
                   connected =
                     if boundary
                     then rest
                     else L.append (G.children (G.tag node))
                            (L.append (L.maybeToList (G.binder node))
                               (L.append
                                  (IS.toList
                                     (IM.findWithDefault IS.empty n (structuralParents solver)))
                                  (L.append
                                     (IS.toList
                                        (IM.findWithDefault IS.empty n (bindingChildren solver)))
                                     rest)))
                 } in
                 componentCanonicalNodesVisit solver (IM.insert n node seen)
                   (if boundary then IS.insert n scopes else scopes)
                   connected
             }
    };
  componentVisit :: Solver -> IntSet -> [] Int -> Either String IntSet;
  componentVisit solver seen pending =
    G.bindE (componentScopesVisit solver seen IS.empty pending)
      (\((,) connected scopes) -> Right connected);
  component :: Solver -> [] Int -> Either String IntSet;
  component solver starts = componentVisit solver IS.empty starts;
  componentScopes :: Solver -> [] Int -> Either String ((,) IntSet IntSet);
  componentScopes solver starts = componentScopesVisit solver IS.empty IS.empty starts;
  -- The ordered component set already stores subtree cardinalities. Its ranks
  -- and selection are the two inverse compact renamings; avoid constructing two
  -- more persistent maps for every local unification. Identities remain Int.
  rankIdentity :: forall a. Int -> Int -> Rank.MapIndex a -> Int;
  rankIdentity wanted offset tree =
    case Rank.mapRank wanted offset tree of {
      Nothing -> panic "map key not found";
      Just position -> position
    };
  rankSetIdentity :: Int -> Rank.SetIndex -> Int;
  rankSetIdentity wanted tree =
    case Rank.setRank wanted tree of {
      Nothing -> panic "map key not found";
      Just position -> position
    };
  compactIdentity :: Graph -> IntSet -> Int -> Int;
  compactIdentity graph selected original =
    rankSetIdentity (G.resolve graph original) (Rank.indexSet selected);
  projectedBinder :: Graph -> IntSet -> IntMap (Maybe Int) -> Int -> Node -> Maybe Int;
  projectedBinder graph forward scopes n node =
    G.mapMaybeInt (compactIdentity graph forward)
      (if G.isGen (G.tag node) then IM.get n scopes else G.binder node);
  localNode :: Graph -> IntSet -> IntMap (Maybe Int) -> IntMap Int -> Int -> Node -> Node;
  localNode graph forward scopes stubs n node =
    G.mkNode
      (case IM.lookup n stubs of {
         Just stub -> GGen stub;
         Nothing -> G.mapTag (compactIdentity graph forward) (G.tag node)
       })
      (projectedBinder graph forward scopes n node)
      (G.flag node);
  -- The originals enumerate the selected set in ascending order. Their
  -- compact identities are consecutive positions; field identities still pass
  -- through the alias-resolving rank lookup in localNode.
  projectNodes :: Graph ->
                  IntSet ->
                  IntMap (Maybe Int) ->
                  IntMap Int -> Int -> [] ((,) Int Node) -> [] ((,) Int Node);
  projectNodes graph selected scopes stubs position originals =
    case originals of {
      [] -> [];
      (:) ((,) n node) rest ->
        (:) ((,) position (localNode graph selected scopes stubs n node))
          (projectNodes graph selected scopes stubs (position + 1) rest)
    };
  compactCanonical :: IntSet -> Int -> Int;
  compactCanonical selected identity = rankSetIdentity identity (Rank.indexSet selected);
  localCanonicalNode :: Rank.MapIndex Node -> IntMap (Maybe Int) -> IntMap Int -> Int -> Node -> Node;
  localCanonicalNode forward scopes stubs n node =
    G.mkNode
      (case IM.lookup n stubs of {
         Just stub -> GGen stub;
         Nothing -> G.mapTag (\n -> rankIdentity n 0 forward) (G.tag node)
       })
      (G.mapMaybeInt (\n -> rankIdentity n 0 forward)
         (if G.isGen (G.tag node) then IM.get n scopes else G.binder node))
      (G.flag node);
  projectCanonicalNodes :: Rank.MapIndex Node ->
                           IntMap (Maybe Int) ->
                           IntMap Int -> Int -> [] ((,) Int Node) -> [] ((,) Int Node);
  projectCanonicalNodes selected scopes stubs position originals =
    case originals of {
      [] -> [];
      (:) ((,) n node) rest ->
        (:) ((,) position (localCanonicalNode selected scopes stubs n node))
          (projectCanonicalNodes selected scopes stubs (position + 1) rest)
    };
  matchesNode :: IntMap Node -> Int -> Node -> Bool;
  matchesNode table n node =
    case IM.lookup n table of {
      Nothing -> False;
      Just other -> G.equalNode node other
    };
  selectIdentity :: forall a. Int -> Rank.MapIndex a -> Either String Int;
  selectIdentity position tree =
    case Rank.mapSelect position tree of {
      Nothing -> Left "scope placeholder escaped local unification";
      Just key -> Right key
    };
  originalIdentity :: IntSet -> Int -> Either String Int;
  originalIdentity selected n =
    case Rank.setSelect n (Rank.indexSet selected) of {
      Nothing -> Left "scope placeholder escaped local unification";
      Just key -> Right key
    };
  traverseTag :: (Int -> Either String Int) -> GTag -> Either String GTag;
  traverseTag action t =
    case t of {
      GArr a b -> G.bindE (action a) (\x -> G.bindE (action b) (\y -> Right (GArr x y)));
      GCon c ns -> G.bindE (G.mapE action ns) (\xs -> Right (GCon c xs));
      GGen n -> G.bindE (action n) (\x -> Right (GGen x));
      GTyApp a b -> G.bindE (action a) (\x -> G.bindE (action b) (\y -> Right (GTyApp x y)));
      _ -> Right t
    };
  restoreNode :: Graph -> Graph -> IntSet -> (,) Int Node -> Either String ((,) Int Node);
  restoreNode old withAliases backward ((,) n node) =
    G.bindE (originalIdentity backward n)
      (\original -> restoreKnownUsing withAliases (originalIdentity backward)
        original (G.nodeAt old original) node);
  restoreKnownNode :: forall a. Graph ->
                                Rank.MapIndex a -> Int -> Node -> Node -> Either String ((,) Int Node);
  restoreKnownNode withAliases backward original previous node =
    restoreKnownUsing withAliases (\n -> selectIdentity n backward) original previous node;
  restoreKnownUsing :: Graph -> (Int -> Either String Int) ->
                       Int -> Node -> Node -> Either String ((,) Int Node);
  restoreKnownUsing withAliases restore original previous node =
    G.bindE
      (case G.tag previous of {
         GGen root -> Right (GGen (G.resolve withAliases root));
         _ -> traverseTag restore (G.tag node)
       })
      (\restoredTag ->
         G.bindE
           (if G.isGen (G.tag previous)
            then Right (G.binder previous)
            else case G.binder node of {
                   Nothing -> Right Nothing;
                   Just b -> G.bindE (restore b) (\parent -> Right (Just parent))
                 })
           (\restoredBinder ->
              Right ((,) original (G.mkNode restoredTag restoredBinder (G.flag node)))));
  -- Both lists are ascending and distinct. Local keys are positions in originals;
  -- skip deleted positions and reuse the saved identity and original node. Field
  -- identities still use the checked inverse, and Gen roots still resolve aliases.
  restoreProjectedNodes :: forall a. Graph ->
                                     Rank.MapIndex a ->
                                     Int ->
                                     [] ((,) Int Node) ->
                                     [] ((,) Int Node) -> Either String ([] ((,) Int Node));
  restoreProjectedNodes withAliases backward position originals solved =
    case solved of {
      [] -> Right [];
      (:) ((,) n node) remaining ->
        case originals of {
          [] -> Left "scope placeholder escaped local unification";
          (:) ((,) original previous) rest ->
            if (n < position)
            then Left "scope placeholder escaped local unification"
            else if (n > position)
                 then restoreProjectedNodes withAliases backward (position + 1) rest solved
                 else G.bindE (restoreKnownNode withAliases backward original previous node)
                        (\restored ->
                           G.bindE
                             (restoreProjectedNodes withAliases backward (position + 1) rest
                                remaining)
                             (\following -> Right ((:) restored following)))
        }
    };
  restoreAliases :: forall a. Rank.MapIndex a -> (,) Int Int -> Either String ((,) Int Int);
  restoreAliases backward ((,) a b) =
    G.bindE (selectIdentity a backward)
      (\left -> G.bindE (selectIdentity b backward) (\right -> Right ((,) left right)));
  checkPreservedScope :: Graph ->
                         Graph ->
                         Rank.MapIndex Node -> IntMap (Maybe Int) -> (,) Int Node -> Either String ();
  checkPreservedScope original solved forward scopes ((,) n node) =
    if L.not (G.isGen (G.tag node))
    then Right ()
    else case IM.lookup (rankIdentity (G.resolve original n) 0 forward) (G.nodes solved) of {
           Nothing -> Left "local unification changed a generalization scope";
           Just next ->
             let {
               projected =
                 G.mapMaybeInt (\identity -> rankIdentity (G.resolve original identity) 0 forward)
                   (IM.get n scopes)
             } in
             G.check
               (G.equalMaybeInt (G.binder next) projected &&
                G.equalFlag (G.flag next) (G.flag node))
               "local unification changed a generalization scope"
         };
  -- Both lists enumerate distinct identities in ascending order. Compare them
  -- once, rather than building a temporary map and doing three lookup passes.
  -- The three result lists retain the original removal/insertion order.
  projectionChanges :: [] ((,) Int Node) ->
                       [] ((,) Int Node) ->
                       (,,) ([] ((,) Int Node)) ([] ((,) Int Node)) ([] Int);
  projectionChanges before after =
    case before of {
      [] -> (,,) [] after [];
      (:) ((,) n v) rest ->
        case after of {
          [] -> (,,) before [] (L.map L.fst before);
          (:) ((,) m w) tail ->
            if (n < m)
            then case projectionChanges rest after of {
                   (,,) removed changed deleted ->
                     (,,) ((:) ((,) n v) removed) changed ((:) n deleted)
                 }
            else if (n > m)
                 then case projectionChanges before tail of {
                        (,,) removed changed deleted ->
                          (,,) removed ((:) ((,) m w) changed) deleted
                      }
                 else if G.equalNode v w
                      then projectionChanges rest tail
                      else case projectionChanges rest tail of {
                             (,,) removed changed deleted ->
                               (,,) ((:) ((,) n v) removed) ((:) ((,) m w) changed) deleted
                           }
        }
    };
  -- Only changed edges affect reverse indices. Common children and unchanged
  -- binders retain their existing entries, including when only a flag changes.
  missingChildren :: [] Int -> [] Int -> [] Int;
  missingChildren before after =
    if (L.length after <= 8)
    then L.filter (\n -> L.not (L.elem eqInt n after)) before
    else let {
           present = IS.fromList after
         } in
         L.filter (\n -> L.not (IS.member n present)) before;
  patchNodeEdges :: Int -> Node -> Node -> Solver -> Solver;
  patchNodeEdges n old next solver =
    let {
      before = G.children (G.tag old)
    } in
    let {
      after = G.children (G.tag next)
    } in
    let {
      sameChildren = L.eqList eqInt before after
    } in
    let {
      sameBinder = G.equalMaybeInt (G.binder old) (G.binder next)
    } in
    if (sameChildren && sameBinder)
    then solver
    else let {
           parents =
             if sameChildren
             then structuralParents solver
             else L.foldlStrict (\index -> \child -> insertIndex child n index)
                    (L.foldlStrict (\index -> \child -> removeIndex child n index)
                       (structuralParents solver)
                       (missingChildren before after))
                    (missingChildren after before)
         } in
         let {
           descendants =
             if sameBinder
             then bindingChildren solver
             else let {
                    removed =
                      case G.binder old of {
                        Nothing -> bindingChildren solver;
                        Just parent -> removeIndex parent n (bindingChildren solver)
                      }
                  } in
                  case G.binder next of {
                    Nothing -> removed;
                    Just parent -> insertIndex parent n removed
                  }
         } in
         mkSolver (graph solver) parents descendants (scopeIndex solver);
  patchIndexedNodes :: Solver -> [] ((,) Int Node) -> [] ((,) Int Node) -> Solver;
  patchIndexedNodes solver before after =
    case before of {
      [] -> L.foldlStrict addNode solver after;
      (:) ((,) n v) rest ->
        case after of {
          [] -> L.foldlStrict removeNode solver before;
          (:) ((,) m w) tail ->
            if (n < m)
            then patchIndexedNodes (removeNode solver ((,) n v)) rest after
            else if (n > m)
                 then patchIndexedNodes (addNode solver ((,) m w)) before tail
                 else patchIndexedNodes (patchNodeEdges n v w solver) rest tail
        }
    };
  restoreProjection :: Solver ->
                       [] ((,) Int Node) -> Rank.MapIndex Node -> Int -> Graph -> Either String Solver;
  -- Compact identities and their inverse both preserve ascending order.
  restoreProjection solver originals backward count solved =
    G.bindE (G.mapE (restoreAliases backward) (IM.toList (G.links solved)))
      (\aliases ->
         let {
           originalGraph = graph solver
         } in
         let {
           withAliases =
             G.mkGraph (G.nodes originalGraph)
               (IM.union (IM.fromDistinctAscList aliases) (G.links originalGraph))
               (G.nextId originalGraph)
         } in
         G.bindE
           (restoreProjectedNodes withAliases backward 0 originals
              (L.filter
                 (\entry ->
                    case entry of {
                      (,) n v -> (n < count)
                    })
                 (IM.toList (G.nodes solved))))
           (\restored ->
              case projectionChanges originals restored of {
                (,,) removedNodes changedNodes deleted ->
                  let {
                    retained =
                      L.foldlStrict (\ns -> \n -> IM.delete n ns) (G.nodes originalGraph) deleted
                  } in
                  let {
                    updated =
                      L.foldlStrict
                        (\ns ->
                           \entry ->
                             case entry of {
                               (,) n v -> G.insertNodeMap n v ns
                             })
                        retained
                        changedNodes
                  } in
                  let {
                    patched = G.mkGraph updated (G.links withAliases) (G.nextId originalGraph)
                  } in
                  let {
                    indexed = patchIndexedNodes solver removedNodes changedNodes
                  } in
                  Right (withGraph patched indexed)
              }));
  unifyDistinct :: [] ((,) Int Int) -> Solver -> Either String Solver;
  -- Original positions precede the fresh placeholder positions.
  unifyDistinct equations solver =
    G.bindE
      (componentCanonicalNodesVisit solver IM.empty IS.empty
         (L.map (G.resolve (graph solver)) (L.concatMap G.equationNodes equations)))
      (\((,) connected boundaries) ->
         let {
           old = graph solver
         } in
         let {
           scopes = projectScopes (scopeIndex solver) boundaries
         } in
         let {
           selected =
             L.foldlStrict
               (\found n ->
                  if IM.member n found then found else IM.insert n (IM.get n (G.nodes old)) found)
               connected
               (IM.keys scopes)
         } in
         let {
           originals = IM.toList selected
         } in
         let {
           count = L.length originals
         } in
         let {
           forward =
             Rank.indexMap selected
         } in
         let {
           backward = forward
         } in
         let {
           compact = \n -> rankIdentity (G.resolve old n) 0 forward
         } in
         let {
           hiddenRoots =
             L.filter
               (\entry ->
                  case entry of {
                    (,) n v ->
                      case G.tag v of {
                        GGen root -> L.not (IM.member root selected);
                        _ -> False
                      }
                  })
               originals
         } in
         let {
           stubIds = L.range count ((count + L.length hiddenRoots) - 1)
         } in
         let {
           stubs =
             IM.fromDistinctAscList
               (L.zip
                  (L.map
                     (\entry ->
                        case entry of {
                          (,) n v -> n
                        })
                     hiddenRoots)
                  stubIds)
         } in
         let {
           existing = projectCanonicalNodes forward scopes stubs 0 originals
         } in
         let {
           placeholders =
             L.map
               (\entry ->
                  case entry of {
                    (,) original stub ->
                      (,) stub (G.mkNode GBot (Just (rankIdentity original 0 forward)) Flexible)
                  })
               (IM.toList stubs)
         } in
         let {
           local =
             G.mkGraph (G.nodesFromDistinctAscList (L.append existing placeholders)) IM.empty
               (count + L.length hiddenRoots)
         } in
         G.bindE
           (G.unify
              (L.map
                 (\entry ->
                    case entry of {
                      (,) a b -> (,) (compact a) (compact b)
                    })
                 equations)
              local)
           (\solved ->
              G.bindE
                (G.mapE_
                   (\stub ->
                      G.check
                        (matchesNode (G.nodes solved) stub (G.nodeAt local stub) &&
                         (G.resolve solved stub == stub))
                        "local unification changed a hidden scope root")
                   (IM.elems stubs))
                (\checkedStubs ->
                   G.bindE (G.mapE_ (checkPreservedScope old solved forward scopes) originals)
                     (\checkedScopes ->
                        restoreProjection solver originals backward count solved))));
  solverUnify :: [] ((,) Int Int) -> Solver -> Either String Solver;
  solverUnify equations solver =
    let {
      old = graph solver
    } in
    let {
      canonical =
        L.map
          (\entry ->
             case entry of {
               (,) a b -> (,) (G.resolve old a) (G.resolve old b)
             })
          equations
    } in
    G.bindE
      (G.mapE_ (\n -> G.check (IM.member n (G.nodes old)) ("missing graph node " ++ showInt n))
         (L.concatMap G.equationNodes canonical))
      (\checked ->
         let {
           pending =
             L.filter
               (\entry ->
                  case entry of {
                    (,) a b -> L.not (a == b)
                  })
               canonical
         } in
         case pending of {
           [] -> Right solver;
           (:) first rest -> unifyDistinct pending solver
         });
  unify :: [] ((,) Int Int) -> Solver -> Either String Solver;
  unify equations solver = solverUnify equations solver;
  expanded :: Int ->
              Int -> Solver -> Either String ((,,,) Int (IntMap Int) ([] ((,) Int Int)) Solver);
  expanded source target solver =
    let {
      old = graph solver
    } in
    case IM.lookup (G.resolve old source) (G.nodes old) of {
      Nothing -> Left "missing instance source";
      Just sourceNode ->
        if L.not (G.isGen (G.tag sourceNode))
        then Left "instance source must be a gen node"
        else case IM.lookup (G.resolve old target) (G.nodes old) of {
               Nothing -> Left "missing instance target";
               Just targetNode ->
                 case G.binder targetNode of {
                   Nothing -> Left "instance target has no binder";
                   Just destination ->
                     G.bindE
                       (G.expandWithScopes (scopeIntervals (scopeIndex solver)) source destination
                          old)
                       (\answer ->
                          case answer of {
                            (,) ((,,) root copies frontier) next ->
                              let {
                                fresh = allocatedNodes (G.nextId old) (G.nextId next) (G.nodes next)
                              } in
                              Right
                                ((,,,) root copies frontier
                                   (L.foldlStrict addNode (withGraph next solver) fresh))
                          })
                 }
             }
    };
  -- Expansion only allocates within this interval. Lookups preserve ascending
  -- identity order and skip gaps without traversing the pre-existing graph.
  allocatedNodes :: Int -> Int -> IntMap Node -> [] ((,) Int Node);
  allocatedNodes first stop nodes =
    if (first >= stop)
    then []
    else case IM.lookup first nodes of {
           Nothing -> allocatedNodes (first + 1) stop nodes;
           Just node -> (:) ((,) first node) (allocatedNodes (first + 1) stop nodes)
         };
  projectField :: Int -> Int -> Solver -> Either String ((,) (IntMap Int) Solver);
  projectField source destination solver =
    projectFieldUsing G.materializeField source destination solver;
  projectFieldUsing :: (Int -> Int -> Graph -> Either String ((,) (IntMap Int) Graph)) ->
                       Int -> Int -> Solver -> Either String ((,) (IntMap Int) Solver);
  projectFieldUsing materialize source destination solver =
    let { old = graph solver; target = G.resolve old destination } in
    G.bindE (materialize source target old)
      (\((,) copies next) ->
        let {
          fresh = allocatedNodes (G.nextId old) (G.nextId next) (G.nodes next);
          indexed = L.foldlStrict addNode
            (removeNode solver ((,) target (G.nodeAt old target)))
            ((:) ((,) target (G.nodeAt next target)) fresh)
        } in
        Right ((,) copies (withGraph next indexed)));
  -- Classify the sealed descriptors against ONE immutable incoming graph.
  -- No branch-body edge, copy, or later argument can reopen this decision.
  projectCaseFields :: [] ((,) Int Int) -> Solver -> Either String Solver;
  projectCaseFields fields solver =
    let { current = graph solver } in
    G.bindE
      (G.mapE (\((,) source destination) ->
        G.bindE (G.require current destination)
          (\proxy -> G.bindE
            (G.check (case G.tag proxy of {
              GGen root -> G.resolve current root == G.resolve current source &&
                L.not (G.underBinder current source destination);
              _ -> False
            }) "pattern projection requires its original external-root proxy")
            (\checked -> G.bindE (G.knownFieldInterface current source)
              (\eligible -> Right (if eligible then Just ((,) source destination) else Nothing)))))
        fields)
      (\classified ->
        case L.catMaybes classified of {
          [] -> Right solver;
          selected -> G.bindE
            (G.foldE (\state ((,) source destination) ->
              G.bindE (projectFieldUsing G.materializeFieldIn source destination state)
                (\answer -> Right (L.snd answer)))
              solver selected)
            (\result -> G.bindE (finish result) (\checked -> Right result))
        });
  instantiate :: Int -> Int -> Solver -> Either String Solver;
  instantiate source target solver =
    G.bindE (expanded source target solver)
      (\answer ->
         case answer of {
           (,,,) root copies frontier next ->
             solverUnify (L.append frontier ((:) ((,) root target) [])) next
         });
  -- A fresh closed expansion into a green bottom only merges its fresh root
  -- with that bottom. Both roots have the same binder and flexible flag;
  -- every other copied binder and flag is unchanged by the general rebinder.
  -- Keep the expansion's identities, allocation budget and root alias exactly,
  -- so this is an exact specialization of instantiate, not type matching.
  -- Like groundGraft, this consumes a Solver established by prepare and kept
  -- valid by solver operations. Independently validate the entire fresh closed
  -- fragment before admitting it; arbitrary forged Solver values are not a
  -- substitute for prepare, and finish still audits the complete final state.
  freshBottomGraft :: Int -> Int -> Int -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  freshBottomGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget } in
    if L.not (L.null frontier) || target >= first || root < first || root == target
    then Nothing
    else case IM.lookup target (G.nodes current) of {
      Nothing -> Nothing;
      Just old -> case G.tag old of {
        GBot -> freshBottomGraftKind first target root old Star solver;
        GBotK kind -> freshBottomGraftKind first target root old kind solver;
        _ -> Nothing
      }
    };
  freshBottomGraftKind :: Int -> Int -> Int -> Node -> Kind -> Solver -> Maybe Solver;
  freshBottomGraftKind first target root old kind solver =
    let {
      current = graph solver;
      directGen = case G.binder old of {
        Nothing -> False;
        Just parent -> case IM.lookup parent (G.nodes current) of {
          Just node -> G.isGen (G.tag node) && G.equalFlag (G.flag node) Flexible;
          Nothing -> False
        }
      }
    } in
    if L.not (green current target) ||
       L.not directGen ||
       L.not (IS.null (IM.findWithDefault IS.empty target (bindingChildren solver)))
    then Nothing
    else case IM.lookup root (G.nodes current) of {
      Nothing -> Nothing;
      Just source ->
        if L.not (G.equalFlag (G.flag source) Flexible) ||
           L.not (G.equalMaybeInt (G.binder source) (G.binder old))
        then Nothing
        else let {
          fresh = allocatedNodes first (G.nextId current) (G.nodes current);
          identities = IS.fromList (L.map L.fst fresh);
          closed = \((,) identity node) ->
            L.not (G.isGen (G.tag node)) &&
            L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
            (if identity == root then True else case G.binder node of {
              Nothing -> False;
              Just parent -> IS.member parent identities
            })
        } in
        if L.not (IS.member root identities && L.all closed fresh &&
          validFreshFragment root (G.binder old) fresh (G.nextId current))
        then Nothing
        else case G.kindAt current root of {
          Left _ -> Nothing;
          Right sourceKind ->
            if L.not (G.equalKind sourceKind kind)
            then Nothing
            else let {
              image = \identity -> if identity == root then target else identity;
              mergedTag = if G.isBottom (G.tag source) then G.tag old else G.tag source;
              replacement = G.mkNode (G.mapTag image mergedTag)
                (G.binder old) (G.flag old);
              descendants = L.map (\((,) identity node) ->
                (,) identity (G.mkNode (G.mapTag image (G.tag node))
                  (G.mapMaybeInt image (G.binder node)) (G.flag node)))
                (L.filter (\((,) identity _) -> identity /= root) fresh);
              updated = G.insertNodeMap target replacement
                (IM.union (G.nodesFromDistinctAscList descendants)
                  (IM.delete root (G.nodes current)));
              next = G.mkGraph updated (IM.insert root target (G.links current))
                (G.nextId current);
              indexed = patchIndexedNodes solver ((:) ((,) target old) fresh)
                ((:) ((,) target replacement) descendants)
            } in Just (withGraph next indexed)
        }
    };
  validFreshFragment :: Int -> Maybe Int -> [] ((,) Int Node) -> Int -> Bool;
  validFreshFragment root parent fresh next = case parent of {
    Nothing -> False;
    Just scope ->
      -- Validation sees the exact copied graph under one Gen anchor. Relabel
      -- only this temporary graph so its old anchor cannot force a sparse
      -- validation path; the returned solver retains all original identities.
      let {
        count = L.length fresh;
        copies = IM.fromList (G.freshCopyEntries 1 (L.map L.fst fresh));
        renaming = IM.insert scope 0 copies;
        known = \((,) identity node) ->
          L.all (\child -> IM.member child renaming) (G.children (G.tag node)) &&
          (case G.binder node of {
            Nothing -> True;
            Just parent -> IM.member parent renaming
          })
      } in
      if IM.size copies /= count || IM.member scope copies ||
         L.not (IM.member root copies && L.all known fresh)
      then False
      else let {
        image = \identity -> IM.get identity renaming;
        entries = L.map (\((,) identity node) ->
          (,) (image identity) (G.mkNode (G.mapTag image (G.tag node))
            (G.mapMaybeInt image (G.binder node)) (G.flag node))) fresh;
        fragment = G.mkGraph
          (IM.insert 0 (G.mkNode (GGen (image root)) Nothing Flexible)
            (G.nodesFromDistinctAscList entries)) IM.empty (count + 1)
      } in case G.validateGraph fragment of {
        Left _ -> False;
        Right _ -> True
      }
  };
  -- External frontier proxies can be removed in the same root graft only
  -- when their original Gen scope already dominates the destination Gen.
  -- The originals then keep their exact binders and flags: every eliminated
  -- proxy is flexible/Green both at its old and its final binder. A non-bottom
  -- final target retains the general simultaneous unifier; doing these merges
  -- eagerly and then allowing arbitrary further rebinding is not licensed.
  frontierBottomGraft :: Int -> Int -> Int -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  frontierBottomGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> Nothing;
      Just old -> case G.binder old of {
        Nothing -> Nothing;
        Just destination -> case IM.lookup destination (G.nodes current) of {
          Nothing -> Nothing;
          Just scope ->
            if L.null frontier || target >= first || root < first ||
               L.not (G.isBottom (G.tag old) && G.equalFlag (G.flag old) Flexible &&
                 G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible) ||
               L.not (IS.null (IM.findWithDefault IS.empty target (bindingChildren solver)))
            then Nothing
            else frontierBottomGraftIn first target destination root old frontier solver
        }
      }
    };
  frontierBottomGraftIn :: Int -> Int -> Int -> Int -> Node -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  frontierBottomGraftIn first target destination root old frontier solver =
    let {
      current = graph solver;
      fresh = allocatedNodes first (G.nextId current) (G.nodes current);
      identities = IS.fromList (L.map L.fst fresh);
      proxies = IM.fromList (L.map (\((,) original proxy) -> (,) proxy original) frontier);
      closed = \((,) identity node) ->
        L.not (G.isGen (G.tag node)) &&
        L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
        (case G.binder node of {
          Nothing -> False;
          Just parent -> parent == destination || IS.member parent identities
        });
      rootOriginal = IM.lookup root proxies;
      rootAllowed = case rootOriginal of {
        Nothing -> True;
        Just original -> original < target && L.length fresh == 1 &&
          (case IM.lookup original (G.nodes current) of {
            Nothing -> False;
            Just node -> L.not (G.isBottom (G.tag node)) || G.equalTag (G.tag node) (G.tag old)
          })
      }
    } in
    if L.not (IS.member root identities && IM.size proxies == L.length frontier &&
      rootAllowed && L.all closed fresh &&
      G.equalMaybeInt (G.binder (G.nodeAt current root)) (Just destination) &&
      G.equalFlag (G.flag (G.nodeAt current root)) Flexible &&
      validFreshFragment root (Just destination) fresh (G.nextId current) &&
      L.all (frontierGraftSource first target destination identities solver) frontier)
    then Nothing
    else case G.kindAt current root of {
      Left _ -> Nothing;
      Right kind -> case G.kindAt current target of {
        Left _ -> Nothing;
        Right expected ->
          if L.not (G.equalKind kind expected) then Nothing else
          let {
            aliases = case rootOriginal of {
              Nothing -> IM.insert root target proxies;
              Just original -> IM.insert target original proxies
            };
            image = \identity -> IM.findWithDefault identity identity aliases;
            rewrite = \node -> G.mkNode (G.mapTag image (G.tag node))
              (G.mapMaybeInt image (G.binder node)) (G.flag node);
            descendants = L.map (\((,) identity node) -> (,) identity (rewrite node))
              (L.filter (\((,) identity _) -> IM.notMember identity aliases) fresh);
            parents = case rootOriginal of {
              Nothing -> [];
              Just _ -> L.map (\identity -> (,) identity (G.nodeAt current identity))
                (IS.toList (IM.findWithDefault IS.empty target (structuralParents solver)))
            };
            replacement = case rootOriginal of {
              Just _ -> [];
              Nothing -> (:) ((,) target (G.mkNode
                (G.mapTag image (G.tag (G.nodeAt current root))) (G.binder old) (G.flag old))) []
            };
            before = IM.fromList (L.append ((:) ((,) target old) fresh) parents);
            after = IM.fromList (L.append replacement
              (L.append descendants (L.map (\((,) identity node) -> (,) identity (rewrite node)) parents)));
            removed = L.foldlStrict (\nodes identity -> IM.delete identity nodes)
              (G.nodes current) (IM.keys aliases);
            next = G.mkGraph (IM.union after removed)
              (IM.union aliases (G.links current)) (G.nextId current);
            indexed = patchIndexedNodes solver (IM.toList before) (IM.toList after)
          } in Just (withGraph next indexed)
      }
    };
  frontierGraftSource :: Int -> Int -> Int -> IntSet -> Solver -> (,) Int Int -> Bool;
  frontierGraftSource first target destination identities solver pair =
    frontierGraftSourceShape first target destination identities solver pair &&
    sameGraftKinds (graph solver) ((:) pair []);
  -- Structural and permission checks do not need a kind traversal. Congruent
  -- reuse checks all pair kinds together after these guards, sharing completed
  -- kind results across every fresh node and existing image.
  frontierGraftSourceShape :: Int -> Int -> Int -> IntSet -> Solver -> (,) Int Int -> Bool;
  frontierGraftSourceShape first target destination identities solver ((,) original proxy) =
    let { current = graph solver } in
    original < first && original /= target && IS.member proxy identities &&
    (case IM.lookup original (G.nodes current) of {
      Nothing -> False;
      Just source -> case IM.lookup proxy (G.nodes current) of {
        Nothing -> False;
        Just copy ->
          L.not (G.isGen (G.tag source)) && G.isBottom (G.tag copy) &&
          (L.not (G.isBottom (G.tag source)) || G.equalTag (G.tag source) (G.tag copy)) &&
          G.equalFlag (G.flag copy) Flexible &&
          G.equalMaybeInt (G.binder copy) (Just destination) &&
          IS.null (IM.findWithDefault IS.empty proxy (bindingChildren solver)) &&
          L.all (\parent -> parent >= first)
            (IS.toList (IM.findWithDefault IS.empty proxy (structuralParents solver))) &&
          IS.notMember target (G.reachableVisit current IS.empty ((:) original [])) &&
          (case G.binder source of {
            Nothing -> False;
            Just parent -> case IM.lookup parent (G.nodes current) of {
              Nothing -> False;
              Just scope -> G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
                scopeContains (scopeIndex solver) parent destination
            }
          })
      }
    });
  sameGraftKinds :: Graph -> [] ((,) Int Int) -> Bool;
  sameGraftKinds current pairs =
    case G.kindsAt current (L.concatMap (\((,) source target) -> (:) source ((:) target [])) pairs) of {
      Left _ -> False;
      Right kinds -> L.all (\((,) source target) ->
        case IM.lookup (G.resolve current source) kinds of {
          Nothing -> False;
          Just kind -> case IM.lookup (G.resolve current target) kinds of {
            Nothing -> False;
            Just expected -> G.equalKind kind expected
          }
        }) pairs
    };
  -- An external root that is already the destination contributes only its
  -- fresh frontier proxy. Both equations identify that proxy with the same
  -- original node; no existing structure, permission or binding can change.
  frontierIdentityGraft :: Int -> Int -> Int -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  frontierIdentityGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget } in
    case frontier of {
      (:) ((,) original proxy) [] ->
        if original /= target || proxy /= root || root < first || target >= first
        then Nothing
        else case IM.lookup target (G.nodes current) of {
          Nothing -> Nothing;
          Just old -> case G.binder old of {
            Nothing -> Nothing;
            Just destination -> case IM.lookup destination (G.nodes current) of {
              Nothing -> Nothing;
              Just scope -> case allocatedNodes first (G.nextId current) (G.nodes current) of {
                (:) ((,) identity copy) [] ->
                  if identity /= root || G.isGen (G.tag old) ||
                     L.not (G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
                       G.isBottom (G.tag copy) && G.equalFlag (G.flag copy) Flexible &&
                       G.equalMaybeInt (G.binder copy) (Just destination) &&
                       (L.not (G.isBottom (G.tag old)) || G.equalTag (G.tag old) (G.tag copy)) &&
                       IS.null (IM.findWithDefault IS.empty root (structuralParents solver)) &&
                       IS.null (IM.findWithDefault IS.empty root (bindingChildren solver)) &&
                       validFreshFragment root (Just destination) ((:) ((,) root copy) []) (G.nextId current))
                  then Nothing
                  else case G.kindAt current target of {
                    Left _ -> Nothing;
                    Right kind -> case G.kindAt current root of {
                      Left _ -> Nothing;
                      Right proxyKind ->
                        if L.not (G.equalKind kind proxyKind) then Nothing else
                        let {
                          next = G.mkGraph (IM.delete root (G.nodes current))
                            (IM.insert root target (G.links current)) (G.nextId current);
                          indexed = patchIndexedNodes solver ((:) ((,) root copy) []) []
                        } in Just (withGraph next indexed)
                    }
                  };
                _ -> Nothing
              }
            }
          }
        };
      _ -> Nothing
    };
  -- A congruent copy may reuse existing nodes only when every fresh node has
  -- one existing image and the existing graph is unchanged. Mapped tags and
  -- binders must match exactly, merged flags must retain the existing flag,
  -- and Flexible nodes under a rigid binder are excluded. A fresh Green bottom
  -- can take the existing type, while fixed external frontier images retain
  -- their independently checked dominating Gen scopes. Shared fresh nodes must
  -- agree on their image; multiple fresh nodes may share one unchanged image.
  -- These guards preserve all rebinding/permission obligations. General
  -- unification remains the fallback for any old-node merge or mutation.
  congruentExpansionMap :: Graph -> Int -> IntMap Int -> [] ((,) Int Int) -> Maybe (IntMap Int);
  congruentExpansionMap current first images pending = case pending of {
    [] -> Just images;
    (:) ((,) source target) rest ->
      if source < first || target >= first then Nothing else
      case IM.lookup source images of {
        Just previous -> if previous == target then congruentExpansionMap current first images rest else Nothing;
        Nothing -> case IM.lookup source (G.nodes current) of {
          Nothing -> Nothing;
          Just copy -> case IM.lookup target (G.nodes current) of {
            Nothing -> Nothing;
            Just old ->
              if G.isGen (G.tag old) || G.isGen (G.tag copy) ||
                 (G.isBottom (G.tag old) && L.not (G.isBottom (G.tag copy)))
              then Nothing
              else case G.tagEquations (G.tag copy) (G.tag old) of {
                Left _ -> Nothing;
                Right ((,) tag pairs) -> congruentExpansionMap current first
                  (IM.insert source target images) (L.append pairs rest)
              }
          }
        }
      }
  };
  congruentExpansionGraft :: Int -> Int -> Int -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  congruentExpansionGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget;
      fresh = allocatedNodes first (G.nextId current) (G.nodes current);
      identities = IS.fromList (L.map L.fst fresh);
      proxies = IM.fromList (L.map (\((,) original proxy) -> (,) proxy original) frontier)
    } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> Nothing;
      Just old -> case G.binder old of {
        Nothing -> Nothing;
        Just destination -> case IM.lookup destination (G.nodes current) of {
          Nothing -> Nothing;
          Just scope ->
            if L.not (G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
              L.all (\((,) identity node) -> L.not (G.isGen (G.tag node)) &&
                L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
                (case G.binder node of { Nothing -> False; Just parent -> parent == destination || IS.member parent identities })) fresh)
            then Nothing else
            case congruentExpansionMap current first proxies ((:) ((,) root target) []) of {
              Nothing -> Nothing;
              Just images ->
                if IM.size images /= L.length fresh ||
                   L.not (validFreshFragment root (Just destination) fresh (G.nextId current) &&
                     L.all (frontierGraftSourceShape first target destination identities solver) frontier)
                then Nothing else
                let { image = \identity -> IM.findWithDefault identity identity images;
                  permitted = \identity -> G.equalFlag (G.flag (G.nodeAt current identity)) Rigid || green current identity;
                  exact = \((,) identity node) ->
                    if IM.member identity proxies then True else
                    let { destination = IM.get identity images; old = G.nodeAt current destination } in
                    G.equalMaybeInt (G.mapMaybeInt image (G.binder node)) (G.binder old) &&
                    (G.equalFlag (G.flag node) Flexible || G.equalFlag (G.flag old) Rigid) &&
                    permitted identity && permitted destination &&
                    (if G.isBottom (G.tag node) then green current identity
                     else G.equalTag (G.mapTag image (G.tag node)) (G.tag old))
                } in
                if L.not (L.all exact fresh) ||
                   L.not (sameGraftKinds current (IM.toList images))
                then Nothing
                else let {
                  remaining = L.foldlStrict (\nodes identity -> IM.delete identity nodes) (G.nodes current) (IM.keys images);
                  next = G.mkGraph remaining (IM.union images (G.links current)) (G.nextId current);
                  indexed = patchIndexedNodes solver fresh []
                } in Just (withGraph next indexed)
            }
        }
      }
    };
  expansionBottomGraft :: Int -> Int -> Int -> [] ((,) Int Int) -> Solver -> Maybe Solver;
  expansionBottomGraft first target root frontier solver =
    let { direct =
      if L.null frontier then freshBottomGraft first target root frontier solver
      else case frontierIdentityGraft first target root frontier solver of {
        Just answer -> Just answer;
        Nothing -> frontierBottomGraft first target root frontier solver
      }
    } in case direct of {
      Just answer -> Just answer;
      Nothing -> congruentExpansionGraft first target root frontier solver
    };
  instantiateWithFreshBottom :: Int -> Int -> Solver -> Either String Solver;
  instantiateWithFreshBottom source target solver =
    G.bindE (expanded source target solver)
      (\answer -> case answer of {
        (,,,) root copies frontier next ->
          case expansionBottomGraft (G.nextId (graph solver)) target root frontier next of {
            Just grafted -> Right grafted;
            Nothing -> solverUnify (L.append frontier ((:) ((,) root target) [])) next
          }
      });
  -- Closed ground types have no frontier and cannot change permissions. Their
  -- exact graft keeps the destination's identity and copies only descendants.
  groundNodes :: Graph -> IntSet -> [] Int -> Maybe IntSet;
  groundNodes current seen pending =
    case pending of {
      [] -> Just seen;
      (:) original rest ->
        let {
          n = G.resolve current original
        } in
        if IS.member n seen
        then groundNodes current seen rest
        else case IM.lookup n (G.nodes current) of {
               Nothing -> Nothing;
               Just node ->
                 case G.tag node of {
                   GBot -> Nothing;
                   GBotK k -> Nothing;
                   GSkolem identity kind -> Nothing;
                   GGen root -> Nothing;
                   t -> groundNodes current (IS.insert n seen) (L.append (G.children t) rest)
                 }
             }
    };
  groundGraft :: Int -> Int -> Solver -> Maybe Solver;
  groundGraft source destination solver =
    let {
      current = graph solver
    } in
    let {
      target = G.resolve current destination
    } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> Nothing;
      Just old ->
        case G.tag old of {
          GBot -> groundGraftKind source target old Star solver;
          GBotK kind -> groundGraftKind source target old kind solver;
          _ -> Nothing
        }
    };
  groundGraftKind :: Int -> Int -> Node -> Kind -> Solver -> Maybe Solver;
  -- Descendants receive increasing fresh identities in list order.
  groundGraftKind source target old kind solver =
    let {
      current = graph solver
    } in
    if L.not (green current target)
    then Nothing
    else case IM.lookup (G.resolve current source) (G.nodes current) of {
           Nothing -> Nothing;
           Just sourceNode ->
             case G.tag sourceNode of {
               GGen originalRoot ->
                 let {
                   root = G.resolve current originalRoot
                 } in
                 case groundNodes current IS.empty ((:) root []) of {
                   Nothing -> Nothing;
                   Just originals ->
                     case G.kindAt current root of {
                       Left message -> Nothing;
                       Right sourceKind ->
                         if L.not (G.equalKind sourceKind kind)
                         then Nothing
                         else let {
                                descendants = IS.toList (IS.delete root originals)
                              } in
                              let {
                                count = L.length descendants
                              } in
                              let {
                                freshLimit = L.advanceIdentity (G.nextId current) count
                              } in
                              let {
                                copies =
                                  IM.insert root target
                                    (IM.fromDistinctAscList
                                       (L.zip descendants
                                          (L.range (G.nextId current)
                                             (freshLimit - 1))))
                              } in
                              let {
                                image = \n -> IM.get (G.resolve current n) copies
                              } in
                              let {
                                replacement =
                                  G.mkNode (G.mapTag image (G.tag (G.nodeAt current root)))
                                    (G.binder old)
                                    (G.flag old)
                              } in
                              let {
                                fresh =
                                  L.map
                                    (\n ->
                                       (,) (image n)
                                         (G.mkNode (G.mapTag image (G.tag (G.nodeAt current n)))
                                            (Just target)
                                            Rigid))
                                    descendants
                              } in
                              let {
                                next =
                                  G.mkGraph
                                    (G.insertNodeMap target replacement
                                       (IM.union (G.nodesFromDistinctAscList fresh)
                                          (G.nodes current)))
                                    (G.links current)
                                    freshLimit
                              } in
                              let {
                                indexed =
                                  L.foldlStrict addNode (removeNode solver ((,) target old))
                                    ((:) ((,) target replacement) fresh)
                              } in
                              Just (withGraph next indexed)
                     }
                 };
               _ -> Nothing
             }
         };
  -- Exact seed groundGraft guard: a flexible chain must reach a Gen. Unlike a
  -- general permission query, a known bottom needs no inertness index, and a
  -- missing binder is not a green graft destination.
  green :: Graph -> Int -> Bool;
  green current identity =
    case G.nodeAt current identity of {
      Node (GGen _) _ _ -> True;
      Node _ parent Flexible ->
        case parent of {
          Nothing -> False;
          Just ancestor -> green current ancestor
        };
      _ -> False
    };
  pairSeen :: Int -> Int -> IntMap IntSet -> Bool;
  pairSeen a b seen = IS.member b (IM.findWithDefault IS.empty a seen);
  insertPair :: Int -> Int -> IntMap IntSet -> IntMap IntSet;
  insertPair a b seen = IM.insert a (IS.insert b (IM.findWithDefault IS.empty a seen)) seen;
  sameGroundShape :: GTag -> GTag -> Maybe ([] ((,) Int Int));
  sameGroundShape a b =
    case a of {
      GTyCon c k ->
        case b of {
          GTyCon d l -> if (eqString c d && G.equalKind k l) then Just [] else Nothing;
          _ -> Nothing
        };
      GArr p q ->
        case b of {
          GArr r s -> Just ((:) ((,) p r) ((:) ((,) q s) []));
          _ -> Nothing
        };
      GTyApp p q ->
        case b of {
          GTyApp r s -> Just ((:) ((,) p r) ((:) ((,) q s) []));
          _ -> Nothing
        };
      GCon c ps ->
        case b of {
          GCon d qs ->
            if (eqString c d && (L.length ps == L.length qs)) then Just (L.zip ps qs) else Nothing;
          _ -> Nothing
        };
      _ -> Nothing
    };
  equalGround :: Graph -> IntMap IntSet -> [] ((,) Int Int) -> Bool;
  equalGround current seen pending =
    case pending of {
      [] -> True;
      (:) ((,) x y) rest ->
        let {
          a = G.resolve current x
        } in
        let {
          b = G.resolve current y
        } in
        if ((a == b) || pairSeen a b seen)
        then equalGround current seen rest
        else case sameGroundShape (G.tag (G.nodeAt current a)) (G.tag (G.nodeAt current b)) of {
               Nothing -> False;
               Just pairs -> equalGround current (insertPair a b seen) (L.append pairs rest)
             }
    };
  groundInstanceVisit :: Graph -> Int -> IntMap IntSet -> IntMap Int -> [] ((,) Int Int) -> Bool;
  groundInstanceVisit current source seen images pending =
    case pending of {
      [] -> True;
      (:) ((,) x y) rest ->
        let {
          a = G.resolve current x
        } in
        let {
          b = G.resolve current y
        } in
        if pairSeen a b seen
        then groundInstanceVisit current source seen images rest
        else case IM.lookup a (G.nodes current) of {
               Nothing -> False;
               Just left ->
                 case IM.lookup b (G.nodes current) of {
                   Nothing -> False;
                   Just right ->
                     case G.tag left of {
                       GBot -> groundInstanceVariable current source seen images rest a b left Star;
                       GBotK kind ->
                         groundInstanceVariable current source seen images rest a b left kind;
                       _ ->
                         case sameGroundShape (G.tag left) (G.tag right) of {
                           Nothing -> False;
                           Just pairs ->
                             groundInstanceVisit current source (insertPair a b seen) images
                               (L.append pairs rest)
                         }
                     }
                 }
             }
    };
  groundInstanceVariable :: Graph ->
                            Int ->
                            IntMap IntSet ->
                            IntMap Int -> [] ((,) Int Int) -> Int -> Int -> Node -> Kind -> Bool;
  groundInstanceVariable current source seen images rest a b node kind =
    if (L.not (G.equalFlag (G.flag node) Flexible) ||
        L.not (G.equalMaybeInt (G.binder node) (Just (G.resolve current source))))
    then False
    else case G.kindAt current b of {
           Left error -> False;
           Right actual ->
             if L.not (G.equalKind actual kind)
             then False
             else case IM.lookup a images of {
                    Nothing ->
                      groundInstanceVisit current source (insertPair a b seen)
                        (IM.insert a b images)
                        rest;
                    Just previous ->
                      (equalGround current IM.empty ((:) ((,) previous b) []) &&
                       groundInstanceVisit current source (insertPair a b seen) images rest)
                  }
         };
  groundInstance :: Graph -> Int -> Int -> Bool;
  groundInstance current source target =
    case IM.lookup (G.resolve current source) (G.nodes current) of {
      Nothing -> False;
      Just node ->
        case G.tag node of {
          GGen root ->
            case groundNodes current IS.empty ((:) target []) of {
              Nothing -> False;
              Just seen ->
                groundInstanceVisit current source IM.empty IM.empty ((:) ((,) root target) [])
            };
          _ -> False
        }
    };
  instantiateClosed :: Int -> Int -> Solver -> Either String Solver;
  instantiateClosed source target solver =
    case groundGraft source target solver of {
      Just grafted -> Right grafted;
      Nothing ->
        if groundInstance (graph solver) source target
        then Right solver
        else instantiateWithFreshBottom source target solver
    };
  witness :: Int -> Int -> Solver -> Either String ((,) (IntMap Int) Solver);
  witness source target solver =
    G.bindE (expanded source target solver)
      (\answer ->
         case answer of {
           (,,,) root copies frontier next ->
             G.bindE (solverUnify frontier next)
               (\frontierSolved ->
                  G.bindE (solverUnify ((:) ((,) root target) []) frontierSolved)
                    (\result -> Right ((,) copies result)))
         })

  ;
  -- A prepared fallback transaction. The two Constraint drivers establish
  -- prepare and preserve its canonical live fields, allocation separation and
  -- complete indexes. Existing public Solver routes retain their P3 behavior.
  -- The full expanded Graph and full local validation are not omitted. Only
  -- fresh intermediate reverse indexes and their component rediscovery are
  -- avoided, after an ordered negative prefix proves every graft must fail.
  expandedGraphPrepared :: Int ->
              Int -> Solver -> Either String ((,,,) Int (IntMap Int) ([] ((,) Int Int)) Graph);
  expandedGraphPrepared source target solver =
    let {
      old = graph solver
    } in
    case IM.lookup (G.resolve old source) (G.nodes old) of {
      Nothing -> Left "missing instance source";
      Just sourceNode ->
        if L.not (G.isGen (G.tag sourceNode))
        then Left "instance source must be a gen node"
        else case IM.lookup (G.resolve old target) (G.nodes old) of {
               Nothing -> Left "missing instance target";
               Just targetNode ->
                 case G.binder targetNode of {
                   Nothing -> Left "instance target has no binder";
                   Just destination ->
                     G.bindE
                       (G.expandWithScopes (scopeIntervals (scopeIndex solver)) source destination
                          old)
                       (\answer ->
                          case answer of {
                            (,) ((,,) root copies frontier) next ->
                              Right ((,,,) root copies frontier next)
                          })
                 }
             }
    };
  forceExpansionChildIds :: [] Int -> ();
  forceExpansionChildIds children = case children of {
    [] -> ();
    (:) child rest -> seq child (forceExpansionChildIds rest)
  };
  forceExpansionEdges :: [] ((,) Int Node) -> ();
  forceExpansionEdges entries = case entries of {
    [] -> ();
    (:) ((,) identity node) rest ->
      seq (forceExpansionChildIds (G.children (G.tag node)))
        (seq (case G.binder node of {
          Nothing -> ();
          Just parent -> seq parent ()
        }) (forceExpansionEdges rest))
  };

  fallbackStageEligible :: Int -> Int -> Int -> [] ((,) Int Int) -> Graph -> Bool;
  fallbackStageEligible first root target frontier current =
    case IM.lookup target (G.nodes current) of {
      Nothing -> False;
      Just old -> L.not (G.isBottom (G.tag old)) &&
        (case frontier of {
          (:) ((,) original proxy) [] ->
            L.not (original == target && proxy == root && root >= first && target < first);
          _ -> True
        })
    };
  -- Never skip an unknown payload comparison to look for a later conflict.
  -- This is the exact safe prefix of congruentExpansionMap, not a type matcher.
  fallbackPrefixRejected :: Graph -> Int -> IntMap Int -> [] ((,) Int Int) -> Bool;
  fallbackPrefixRejected current first images pending = case pending of {
    [] -> False;
    (:) ((,) source target) rest ->
      if source < first || target >= first then False else
      case IM.lookup source images of {
        Just previous -> if previous == target
          then fallbackPrefixRejected current first images rest else True;
        Nothing -> case IM.lookup source (G.nodes current) of {
          Nothing -> False;
          Just copy -> case IM.lookup target (G.nodes current) of {
            Nothing -> False;
            Just old ->
              if G.isGen (G.tag old) || G.isGen (G.tag copy) then False else
              if G.isBottom (G.tag old) && L.not (G.isBottom (G.tag copy)) then True else
              let { next = IM.insert source target images } in
              if G.isBottom (G.tag copy)
              then fallbackPrefixRejected current first next rest
              else case G.tag copy of {
                GArr a b -> case G.tag old of {
                  GArr c d -> fallbackPrefixRejected current first next
                    ((:) ((,) a c) ((:) ((,) b d) rest));
                  _ -> False
                };
                GTyApp a b -> case G.tag old of {
                  GTyApp c d -> fallbackPrefixRejected current first next
                    ((:) ((,) a c) ((:) ((,) b d) rest));
                  _ -> False
                };
                _ -> False
              }
          }
        }
      }
  };
  -- Every fresh node is reachable from copied root and is not a Gen boundary.
  -- Old component entry points cover equations and all external fresh edges.
  -- No Solver containing an expanded Graph with incomplete indexes is built.
  expandedOldSeeds :: Int -> [] ((,) Int Node) -> [] Int;
  expandedOldSeeds first fresh =
    L.concatMap
      (\((,) identity node) -> L.filter (\n -> n < first)
        (L.append (G.children (G.tag node)) (L.maybeToList (G.binder node)))) fresh;
  expandedCompact :: Int -> Int -> Rank.MapIndex Node -> Int -> Int;
  expandedCompact first stop oldSelected identity =
    if identity < first then rankIdentity identity 0 oldSelected
    else if identity < stop then Rank.mapSize oldSelected + (identity - first)
    else panic "map key not found";
  expandedOriginal :: Int -> Int -> Rank.MapIndex Node -> Int -> Either String Int;
  expandedOriginal first count oldSelected position =
    let { oldCount = Rank.mapSize oldSelected } in
    if position < oldCount then selectIdentity position oldSelected
    else if position < count then Right (first + (position - oldCount))
    else Left "scope placeholder escaped local unification";
  projectExpandedNodes :: Int -> Int -> Rank.MapIndex Node -> IntMap (Maybe Int) -> IntMap Int ->
                          Int -> [] ((,) Int Node) -> [] ((,) Int Node);
  projectExpandedNodes first stop selected scopes stubs position originals =
    case originals of {
      [] -> [];
      (:) ((,) n node) rest ->
        let { compact = expandedCompact first stop selected } in
        (:) ((,) position
          (G.mkNode
            (case IM.lookup n stubs of {
              Just stub -> GGen stub;
              Nothing -> G.mapTag compact (G.tag node)
            })
            (G.mapMaybeInt compact
              (if G.isGen (G.tag node) then IM.get n scopes else G.binder node))
            (G.flag node)))
          (projectExpandedNodes first stop selected scopes stubs (position + 1) rest)
    };
  -- Returned local graph/equations are the actual inputs to unchanged G.unify.
  -- Original ascending IDs consist of oldSelected followed by [first,stop).
  preparedFallbackProjection :: Solver -> Graph -> Int -> [] ((,) Int Node) ->
                                [] ((,) Int Int) ->
                                Either String
                                  ((,,,) Graph ([] ((,) Int Int)) ([] ((,) Int Node))
                                    ((,,) (Rank.MapIndex Node) (IntMap (Maybe Int)) (IntMap Int)));
  preparedFallbackProjection solver current first fresh equations =
    G.bindE
      (componentCanonicalNodesVisit solver IM.empty IS.empty
        (L.append (L.filter (\n -> n < first) (L.concatMap G.equationNodes equations))
          (expandedOldSeeds first fresh)))
      (\((,) connected boundaries) ->
        let { scopes = projectScopes (scopeIndex solver) boundaries } in
        let { selected = L.foldlStrict
          (\found n -> if IM.member n found then found
            else IM.insert n (IM.get n (G.nodes current)) found)
          connected (IM.keys scopes) } in
        let { oldOriginals = IM.toList selected } in
        let { originals = L.append oldOriginals fresh } in
        let { count = L.length originals } in
        let { forward = Rank.indexMap selected } in
        let { compact = \n -> expandedCompact first (G.nextId current) forward (G.resolve current n) } in
        let { hiddenRoots = L.filter
          (\((,) n v) -> case G.tag v of {
            GGen root -> L.not (IM.member root selected);
            _ -> False
          }) oldOriginals } in
        let { stubIds = L.range count ((count + L.length hiddenRoots) - 1) } in
        let { stubs = IM.fromDistinctAscList (L.zip (L.map L.fst hiddenRoots) stubIds) } in
        let { existing = projectExpandedNodes first (G.nextId current) forward scopes stubs 0 originals } in
        let { placeholders = L.map
          (\((,) original stub) ->
            (,) stub (G.mkNode GBot (Just (rankIdentity original 0 forward)) Flexible))
          (IM.toList stubs) } in
        let { local = G.mkGraph
          (G.nodesFromDistinctAscList (L.append existing placeholders)) IM.empty
          (count + L.length hiddenRoots) } in
        Right ((,,,) local
          (L.map (\((,) a b) -> (,) (compact a) (compact b)) equations)
          originals ((,,) forward scopes stubs)));
  restoreExpandedKnownNode :: Graph -> (Int -> Either String Int) ->
                              Int -> Node -> Node -> Either String ((,) Int Node);
  restoreExpandedKnownNode withAliases backward original previous node =
    G.bindE
      (case G.tag previous of {
        GGen root -> Right (GGen (G.resolve withAliases root));
        _ -> traverseTag backward (G.tag node)
      })
      (\restoredTag -> G.bindE
        (if G.isGen (G.tag previous) then Right (G.binder previous)
         else case G.binder node of {
           Nothing -> Right Nothing;
           Just b -> G.bindE (backward b) (\parent -> Right (Just parent))
         })
        (\restoredBinder -> Right
          ((,) original (G.mkNode restoredTag restoredBinder (G.flag node)))));
  restoreExpandedNodes :: Graph -> (Int -> Either String Int) -> Int ->
                          [] ((,) Int Node) -> [] ((,) Int Node) ->
                          Either String ([] ((,) Int Node));
  restoreExpandedNodes withAliases backward position originals solved =
    case solved of {
      [] -> Right [];
      (:) ((,) n node) remaining -> case originals of {
        [] -> Left "scope placeholder escaped local unification";
        (:) ((,) original previous) rest ->
          if n < position then Left "scope placeholder escaped local unification"
          else if n > position
          then restoreExpandedNodes withAliases backward (position + 1) rest solved
          else G.bindE (restoreExpandedKnownNode withAliases backward original previous node)
            (\restored -> G.bindE
              (restoreExpandedNodes withAliases backward (position + 1) rest remaining)
              (\following -> Right ((:) restored following)))
      }
    };
  restoreExpandedProjection :: Solver -> Graph -> Int -> [] ((,) Int Node) ->
                               Rank.MapIndex Node -> Int -> Graph -> Either String Solver;
  restoreExpandedProjection solver originalGraph first originals oldSelected count solved =
    let { backward = expandedOriginal first count oldSelected } in
    G.bindE
      (G.mapE (\((,) a b) -> G.bindE (backward a)
        (\left -> G.bindE (backward b) (\right -> Right ((,) left right))))
        (IM.toList (G.links solved)))
      (\aliases ->
        let { withAliases = G.mkGraph (G.nodes originalGraph)
          (IM.union (IM.fromDistinctAscList aliases) (G.links originalGraph))
          (G.nextId originalGraph) } in
        G.bindE
          (restoreExpandedNodes withAliases backward 0 originals
            (L.filter (\((,) n v) -> n < count) (IM.toList (G.nodes solved))))
          (\restored ->
            -- Do not drop fresh equalNode comparisons: their payload demand
            -- and the complete original deletion/insertion order are retained.
            case projectionChanges originals restored of {
              (,,) removedNodes changedNodes deleted ->
                let { retained = L.foldlStrict (\ns n -> IM.delete n ns)
                  (G.nodes originalGraph) deleted } in
                let { updated = L.foldlStrict (\ns ((,) n v) -> G.insertNodeMap n v ns)
                  retained changedNodes } in
                let { patched = G.mkGraph updated (G.links withAliases) (G.nextId originalGraph) } in
                let { indexedOld = patchIndexedNodes solver
                  (L.filter (\((,) n v) -> n < first) removedNodes)
                  (L.filter (\((,) n v) -> n < first) changedNodes) } in
                -- Unchanged fresh survivors also need their FIRST publication.
                -- Deleted fresh edges were never published and are not removed.
                let { indexed = L.foldlStrict addNode indexedOld
                  (L.filter (\((,) n v) -> n >= first) restored) } in
                Right (withGraph patched indexed)
            }));
  unifyPreparedFallback :: [] ((,) Int Int) -> Solver -> Graph -> Int ->
                           [] ((,) Int Node) -> Either String Solver;
  unifyPreparedFallback equations solver current first fresh =
    let { canonical = L.map
      (\((,) a b) -> (,) (G.resolve current a) (G.resolve current b)) equations } in
    G.bindE
      (G.mapE_ (\n -> G.check (IM.member n (G.nodes current))
        ("missing graph node " ++ showInt n)) (L.concatMap G.equationNodes canonical))
      (\checked ->
        let { pending = L.filter (\((,) a b) -> L.not (a == b)) canonical } in
        case pending of {
          [] -> Right (L.foldlStrict addNode (withGraph current solver) fresh);
          (:) head tail -> G.bindE
            (preparedFallbackProjection solver current first fresh pending)
            (\((,,,) local localEquations originals ((,,) forward scopes stubs)) ->
              G.bindE (G.unify localEquations local)
                (\solved -> G.bindE
                  (G.mapE_ (\stub -> G.check
                    (matchesNode (G.nodes solved) stub (G.nodeAt local stub) &&
                      G.resolve solved stub == stub)
                    "local unification changed a hidden scope root") (IM.elems stubs))
                  (\checkedStubs -> G.bindE
                    (G.mapE_ (checkPreservedScope current solved forward scopes) originals)
                    (\checkedScopes -> restoreExpandedProjection solver current first
                      originals forward (L.length originals) solved))))
        });
  instantiateExpandedPrepared :: Int -> Int -> Solver -> Either String Solver;
  instantiateExpandedPrepared source target solver =
    G.bindE (expandedGraphPrepared source target solver)
      (\((,,,) root copies frontier current) ->
        let { first = G.nextId (graph solver);
          fresh = allocatedNodes first (G.nextId current) (G.nodes current);
          indexed = L.foldlStrict addNode (withGraph current solver) fresh;
          equations = L.append frontier ((:) ((,) root target) []);
          fallback = \next -> solverUnify equations next;
          oldTarget = G.resolve current target;
          ordinary = case expansionBottomGraft first target root frontier indexed of {
            Just grafted -> Right grafted;
            Nothing -> fallback indexed
          }
        } in
        seq (G.strictGraph current)
          (if fallbackStageEligible first root oldTarget frontier current
           then seq (forceExpansionEdges fresh)
             (if fallbackPrefixRejected current first
                   (IM.fromList (L.map (\((,) original proxy) -> (,) proxy original) frontier))
                   ((:) ((,) root oldTarget) [])
              then unifyPreparedFallback equations solver current first fresh
              else ordinary)
           else ordinary));
  -- Actual callers complete prepare and solverUnify before this internal fold.
  -- Public instantiateClosed/evaluateStep remain unchanged for arbitrary input.
  -- No reusable certificate survives an operation or accepts a mutated graph.
  instantiateClosedPrepared :: Int -> Int -> Solver -> Either String Solver;
  instantiateClosedPrepared source target solver =
    case groundGraft source target solver of {
      Just grafted -> Right grafted;
      Nothing -> if groundInstance (graph solver) source target
        then Right solver else instantiateExpandedPrepared source target solver
    }
}
