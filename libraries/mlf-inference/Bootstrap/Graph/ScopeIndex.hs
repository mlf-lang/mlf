-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Graph.ScopeIndex where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Graph as G;
  scopeVisit :: IntMap ([] Int) -> Int ->
    (,,) Int Int (IntMap ((,) Int Int)) -> Int -> (,,) Int Int (IntMap ((,) Int Int));
  scopeVisit descendants depth ((,,) start deepest intervals) n =
    case L.foldlStrict (scopeVisit descendants (depth + 1)) ((,,) (start + 1) (L.max deepest depth) intervals)
           (IM.findWithDefault [] n descendants) of {
      (,,) end height final ->
        let { updated = IM.insert n (G.strictPair start end) final } in
        seq end (seq height (seq updated ((,,) end height updated)))
    };
  scopeLevels :: Int -> Int;
  scopeLevels count = if (count <= 1) then 1 else (1 + scopeLevels (quotInt count 2 + remInt count 2));
  scopeJumps :: Int -> IntMap Int -> [] (IntMap Int);
  scopeJumps count parents =
    if (count <= 0)
    then []
    else (:) parents (scopeJumps (count - 1) (IM.map (\n -> IM.get n parents) parents));
  -- In a complete single-root scope tree, a jump that has reached the
  -- root never changes. Keep those Patricia branches across later levels.
  rootedScopeJumps :: Int -> Int -> IntMap Int -> [] (IntMap Int);
  rootedScopeJumps count root parents@(IntMap tree) = let {
    advance branch = case branch of {
      IntMapNil -> Nothing;
      IntMapTip key parent ->
        if parent == root then Nothing else let { next = IM.get parent parents } in
          seq next (Just (IntMapTip key next));
      IntMapBin size prefix left right -> case (,) (advance left) (advance right) of {
        (,) Nothing Nothing -> Nothing;
        (,) (Just a) Nothing -> Just (IntMapBin size prefix a right);
        (,) Nothing (Just b) -> Just (IntMapBin size prefix left b);
        (,) (Just a) (Just b) -> Just (IntMapBin size prefix a b)
      }
    };
    more = if count <= 1 then [] else case advance tree of {
      Nothing -> L.replicate (count - 1) parents;
      Just next -> rootedScopeJumps (count - 1) root (IM.wrap next)
    }
  } in if count <= 0 then [] else (:) parents more;
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
    -- The largest jump only needs to reach the root from the deepest scope.
    case L.foldlStrict (scopeVisit descendants 0) ((,,) 0 0 IM.empty) roots of {
      (,,) _ depth intervals -> let { levels = scopeLevels depth } in ScopeIndex intervals (case roots of {
        (:) root [] -> if IM.size intervals == IM.size parents then rootedScopeJumps levels root parents
          else scopeJumps levels parents;
        _ -> scopeJumps levels parents
      })
    };
  scopeContains :: ScopeIndex -> Int -> Int -> Bool;
  scopeContains (ScopeIndex intervals jumps) a b = G.intervalContains intervals a b;
  intervalIncludes :: (,) Int Int -> Int -> Bool;
  intervalIncludes ((,) start end) position = start <= position && position < end;
  containsScopeStart :: Maybe ((,) Int Int) -> Maybe ((,) Int Int) -> Bool;
  containsScopeStart ancestor child = case ancestor of {
    Nothing -> False;
    Just interval -> case child of {
      Nothing -> False;
      Just ((,) start _) -> intervalIncludes interval start
    }
  };
  scopeLCA :: ScopeIndex -> Int -> Int -> Int;
  scopeLCA (ScopeIndex intervals jumps) a b = scopeLCAWithIntervals intervals jumps a b
    (IM.lookup a intervals) (IM.lookup b intervals);
  scopeLCAWithIntervals :: IntMap ((,) Int Int) -> [] (IntMap Int) -> Int -> Int ->
    Maybe ((,) Int Int) -> Maybe ((,) Int Int) -> Int;
  scopeLCAWithIntervals intervals jumps a b first second =
    if containsScopeStart first second then a
    else if containsScopeStart second first then b
    else case jumps of {
      [] -> panic "empty scope ancestry index";
      (:) parents _ -> let {
        containsSecond n = containsScopeStart (IM.lookup n intervals) second;
        parent = IM.get a parents
      } in
      -- Once neither endpoint contains the other, an enclosing immediate
      -- parent is the lowest common ancestor.
      if containsSecond parent then parent
      else IM.get (L.foldr (\level n -> let { ancestor = IM.get n level } in
        if containsSecond ancestor then n else ancestor) a jumps) parents
    };
  data ScopeEntry = ScopeEntry Int ((,) Int Int);
  scopeEntryIdentity :: ScopeEntry -> Int;
  scopeEntryIdentity (ScopeEntry n _) = n;
  compareScopeEntries :: ScopeEntry -> ScopeEntry -> Int;
  compareScopeEntries (ScopeEntry a ((,) left _)) (ScopeEntry b ((,) right _)) =
    if left == right then L.compareInt a b else L.compareInt left right;
  orderedScopeEntries :: IntMap ((,) Int Int) -> IntSet -> [] ScopeEntry;
  orderedScopeEntries intervals seeds = L.sortBy compareScopeEntries
    (L.map (\n -> ScopeEntry n (IM.get n intervals)) (IS.toList seeds));
  sortScopes :: ScopeIndex -> IntSet -> [] Int;
  sortScopes (ScopeIndex intervals _) seeds = L.map scopeEntryIdentity (orderedScopeEntries intervals seeds);
  scopeRoot :: ScopeIndex -> Int -> Int;
  scopeRoot (ScopeIndex _ jumps) = case jumps of {
    [] -> \_ -> panic "empty scope ancestry index";
    _ -> let { roots = L.last jumps } in \n -> IM.get n roots
  };
  projectScopes :: ScopeIndex -> IntSet -> IntMap (Maybe Int);
  -- The sorted boundary carries its intervals through the adjacent LCA pass
  -- and ancestor stack. Merge in just the added common ancestors and roots.
  projectScopes scopes@(ScopeIndex intervals jumps) seeds =
    let {
      boundary = orderedScopeEntries intervals seeds;
      adjacent = L.zip boundary (L.drop 1 boundary);
      closure = L.foldlStrict
        (\seen ((,) (ScopeEntry a first) (ScopeEntry b second)) ->
          IS.insert (scopeLCAWithIntervals intervals jumps a b (Just first) (Just second)) seen)
        seeds adjacent;
      root = scopeRoot scopes;
      allScopes = L.foldlStrict (\seen (ScopeEntry n _) -> IS.insert (root n) seen) closure boundary;
      added = orderedScopeEntries intervals (IS.difference allScopes seeds);
      ordered = L.mergeBy compareScopeEntries boundary added
    } in case L.foldlStrict attachScopeEntry ((,) [] IM.empty) ordered of {
      (,) _ parents -> parents
    };
  attachScopeEntry :: (,) ([] ScopeEntry) (IntMap (Maybe Int)) -> ScopeEntry ->
    (,) ([] ScopeEntry) (IntMap (Maybe Int));
  attachScopeEntry ((,) ancestors parents) scope@(ScopeEntry n ((,) start _)) =
    let {
      enclosing = L.dropWhile (\(ScopeEntry _ interval) -> L.not (intervalIncludes interval start)) ancestors;
      parent = case enclosing of {
        [] -> Nothing;
        (:) (ScopeEntry p _) _ -> Just p
      }
    } in seq parent (G.strictPair ((:) scope enclosing) (IM.insert n parent parents));
}
