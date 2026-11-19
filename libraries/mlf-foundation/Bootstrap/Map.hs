-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Map where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  -- Persistent size-balanced ordered maps. Comparators return negative/zero/positive.
  -- Match Data.Map.Lazy: force the shape and keys, but keep stored values lazy.
  node :: forall k v. Int -> k -> v -> Map k v -> Map k v -> Map k v;
  node n k v l r = seq n (seq k (seq l (seq r (MapNode n k v l r))));
  empty :: forall k v. Map k v;
  empty = MapEmpty;
  singleton :: forall k v. k -> v -> Map k v;
  singleton key value = node 1 key value MapEmpty MapEmpty;
  null :: forall k v. Map k v -> Bool;
  null tree =
    case tree of {
      MapEmpty -> True;
      MapNode n k v l r -> False
    };
  size :: forall k v. Map k v -> Int;
  size tree =
    case tree of {
      MapEmpty -> 0;
      MapNode n k v l r -> n
    };
  bin :: forall k v. k -> v -> Map k v -> Map k v -> Map k v;
  bin k v l r = node ((1 + size l) + size r) k v l r;
  balance :: forall k v. k -> v -> Map k v -> Map k v -> Map k v;
  balance k v l r =
    let {
      leftSize = size l
    } in
    let {
      rightSize = size r
    } in
    let {
      total = (leftSize + rightSize)
    } in
    if (total <= 1)
    then node (1 + total) k v l r
    -- Keep the original ordered tests for all cached sizes. The larger-side
    -- shortcut assumed unbounded arithmetic, which Int64 no longer provides.
    else if (rightSize > (3 * leftSize))
         then rotateL k v l r
         else if (leftSize > (3 * rightSize)) then rotateR k v l r else node (1 + total) k v l r;
  rotateL :: forall k v. k -> v -> Map k v -> Map k v -> Map k v;
  rotateL k v l r =
    case r of {
      MapEmpty -> bin k v l r;
      MapNode n rk rv rl rr ->
        if (size rl < (2 * size rr))
        then bin rk rv (bin k v l rl) rr
        else case rl of {
               MapEmpty -> bin rk rv (bin k v l MapEmpty) rr;
               MapNode m rlk rlv rll rlr -> bin rlk rlv (bin k v l rll) (bin rk rv rlr rr)
             }
    };
  rotateR :: forall k v. k -> v -> Map k v -> Map k v -> Map k v;
  rotateR k v l r =
    case l of {
      MapEmpty -> bin k v l r;
      MapNode n lk lv ll lr ->
        if (size lr < (2 * size ll))
        then bin lk lv ll (bin k v lr r)
        else case lr of {
               MapEmpty -> bin lk lv ll (bin k v MapEmpty r);
               MapNode m lrk lrv lrl lrr -> bin lrk lrv (bin lk lv ll lrl) (bin k v lrr r)
             }
    };
  lookup :: forall k v. (k -> k -> Int) -> k -> Map k v -> Maybe v;
  lookup cmp wanted tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l r ->
        let {
          c = cmp wanted k
        } in
        if (c < 0) then lookup cmp wanted l else if (c > 0) then lookup cmp wanted r else Just v
    };
  findWithDefault :: forall k v. (k -> k -> Int) -> v -> k -> Map k v -> v;
  findWithDefault cmp fallback key tree = S.fromMaybe fallback (lookup cmp key tree);
  get :: forall k v. (k -> k -> Int) -> k -> Map k v -> v;
  get cmp key tree =
    case lookup cmp key tree of {
      Nothing -> panic "map key not found";
      Just value -> value
    };
  -- Preserve the input map's order and build an answer only when its key is
  -- requested. Each visited branch and its answer are shared in this scope.
  lookupProjected :: forall k a b. (k -> k -> Int) -> (k -> a -> b) -> Map k a -> k -> Maybe b;
  lookupProjected cmp answer tree = case tree of {
    MapEmpty -> \_ -> Nothing;
    MapNode _ key value left right -> let {
      below = lookupProjected cmp answer left; above = lookupProjected cmp answer right;
      found = Just (answer key value)
    } in \wanted -> let { order = cmp wanted key } in
      if order < 0 then below wanted else if order > 0 then above wanted else found
  };
  -- For a map ordered by a signed identity, project each stored identity
  -- once and pass the requested integer through the visited search path.
  -- A miss visits only its search path. Answer payloads remain lazy.
  lookupProjectedId :: forall k a b. (k -> Int) -> (k -> a -> b) -> Map k a -> k -> Maybe b;
  lookupProjectedId identity answer tree = let {
    search entries = case entries of {
      MapEmpty -> \_ -> Nothing;
      MapNode _ key value left right -> let {
        stored = identity key; below = search left; above = search right;
        found = Just (answer key value)
      } in \wanted -> if wanted < stored then below wanted else if wanted == stored then found else above wanted
    };
    read = search tree
  } in seq read (\key -> read (identity key));
  member :: forall k v. (k -> k -> Int) -> k -> Map k v -> Bool;
  member cmp key tree = S.isJust (lookup cmp key tree);
  notMember :: forall k v. (k -> k -> Int) -> k -> Map k v -> Bool;
  notMember cmp key tree = S.not (member cmp key tree);
  insert :: forall k v. (k -> k -> Int) -> k -> v -> Map k v -> Map k v;
  insert cmp key value tree = insertWith cmp (\new old -> new) key value tree;
  insertWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> k -> v -> Map k v -> Map k v;
  insertWith cmp combine key value tree =
    case tree of {
      MapEmpty -> singleton key value;
      MapNode n k v l r ->
        let {
          c = cmp key k
        } in
        if (c < 0)
        then balance k v (insertWith cmp combine key value l) r
        else if (c > 0)
             then balance k v l (insertWith cmp combine key value r)
             else node n key (combine value v) l r
    };
  insertWithKey :: forall k v. (k -> k -> Int) ->
                               (k -> v -> v -> v) -> k -> v -> Map k v -> Map k v;
  insertWithKey cmp combine key value tree = insertWith cmp (combine key) key value tree;
  adjust :: forall k v. (k -> k -> Int) -> (v -> v) -> k -> Map k v -> Map k v;
  adjust cmp f key tree = adjustWithKey cmp (\k v -> f v) key tree;
  adjustWithKey :: forall k v. (k -> k -> Int) -> (k -> v -> v) -> k -> Map k v -> Map k v;
  adjustWithKey cmp f key tree =
    case tree of {
      MapEmpty -> MapEmpty;
      MapNode n k v l r ->
        let {
          c = cmp key k
        } in
        if (c < 0)
        then node n k v (adjustWithKey cmp f key l) r
        else if (c > 0) then node n k v l (adjustWithKey cmp f key r) else node n k (f k v) l r
    };
  alter :: forall k v. (k -> k -> Int) -> (Maybe v -> Maybe v) -> k -> Map k v -> Map k v;
  alter cmp f key tree =
    case f (lookup cmp key tree) of {
      Nothing -> delete cmp key tree;
      Just value -> insert cmp key value tree
    };
  update :: forall k v. (k -> k -> Int) -> (v -> Maybe v) -> k -> Map k v -> Map k v;
  update cmp f key tree = alter cmp (\old -> S.bindMaybe old f) key tree;
  delete :: forall k v. (k -> k -> Int) -> k -> Map k v -> Map k v;
  delete cmp key tree =
    case tree of {
      MapEmpty -> MapEmpty;
      MapNode n k v l r ->
        let {
          c = cmp key k
        } in
        if (c < 0)
        then balance k v (delete cmp key l) r
        else if (c > 0) then balance k v l (delete cmp key r) else glue l r
    };
  glue :: forall k v. Map k v -> Map k v -> Map k v;
  glue l r =
    if null l
    then r
    else if null r
         then l
         else if (size l > size r)
              then case maxViewWithKey l of {
                     Nothing -> r;
                     Just ((,) ((,) key value) rest) -> balance key value rest r
                   }
              else case minViewWithKey r of {
                     Nothing -> l;
                     Just ((,) ((,) key value) rest) -> balance key value l rest
                   };
  minViewWithKey :: forall k v. Map k v -> Maybe ((,) ((,) k v) (Map k v));
  minViewWithKey tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l r ->
        case minViewWithKey l of {
          Nothing -> Just ((,) ((,) k v) r);
          Just ((,) entry rest) -> Just ((,) entry (balance k v rest r))
        }
    };
  maxViewWithKey :: forall k v. Map k v -> Maybe ((,) ((,) k v) (Map k v));
  maxViewWithKey tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l r ->
        case maxViewWithKey r of {
          Nothing -> Just ((,) ((,) k v) l);
          Just ((,) entry rest) -> Just ((,) entry (balance k v l rest))
        }
    };
  lookupMin :: forall k v. Map k v -> Maybe ((,) k v);
  lookupMin tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v MapEmpty r -> Just ((,) k v);
      MapNode n k v l r -> lookupMin l
    };
  lookupMax :: forall k v. Map k v -> Maybe ((,) k v);
  lookupMax tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l MapEmpty -> Just ((,) k v);
      MapNode n k v l r -> lookupMax r
    };
  findMin :: forall k v. Map k v -> (,) k v;
  findMin tree =
    case lookupMin tree of {
      Nothing -> panic "findMin: empty map";
      Just entry -> entry
    };
  findMax :: forall k v. Map k v -> (,) k v;
  findMax tree =
    case lookupMax tree of {
      Nothing -> panic "findMax: empty map";
      Just entry -> entry
    };
  lookupLE :: forall k v. (k -> k -> Int) -> k -> Map k v -> Maybe ((,) k v);
  lookupLE cmp key tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l r ->
        let {
          c = cmp key k
        } in
        if (c < 0)
        then lookupLE cmp key l
        else if (c == 0)
             then Just ((,) k v)
             else case lookupLE cmp key r of {
                    Nothing -> Just ((,) k v);
                    Just result -> Just result
                  }
    };
  lookupGE :: forall k v. (k -> k -> Int) -> k -> Map k v -> Maybe ((,) k v);
  lookupGE cmp key tree =
    case tree of {
      MapEmpty -> Nothing;
      MapNode n k v l r ->
        let {
          c = cmp key k
        } in
        if (c > 0)
        then lookupGE cmp key r
        else if (c == 0)
             then Just ((,) k v)
             else case lookupGE cmp key l of {
                    Nothing -> Just ((,) k v);
                    Just result -> Just result
                  }
    };
  foldrWithKey :: forall k v a. (k -> v -> a -> a) -> a -> Map k v -> a;
  foldrWithKey f z tree =
    case tree of {
      MapEmpty -> z;
      MapNode n k v l r -> foldrWithKey f (f k v (foldrWithKey f z r)) l
    };
  foldlWithKey :: forall a k v. (a -> k -> v -> a) -> a -> Map k v -> a;
  foldlWithKey f z tree =
    case tree of {
      MapEmpty -> z;
      MapNode n k v l r -> foldlWithKey f (f (foldlWithKey f z l) k v) r
    };
  -- Map construction needs each intermediate shape, but not its stored values.
  -- Keep the public lazy folds above and below available for other accumulators.
  foldlWithKeyStrict :: forall a k v. (a -> k -> v -> a) -> a -> Map k v -> a;
  foldlWithKeyStrict f z tree =
    case tree of {
      MapEmpty -> z;
      MapNode n k v l r ->
        let {
          left = foldlWithKeyStrict f z l
        } in
        seq left
          (let {
             next = f left k v
           } in
           seq next (foldlWithKeyStrict f next r))
    };
  foldr :: forall v a k. (v -> a -> a) -> a -> Map k v -> a;
  foldr f z tree = foldrWithKey (\k v acc -> f v acc) z tree;
  foldl :: forall a v k. (a -> v -> a) -> a -> Map k v -> a;
  foldl f z tree = foldlWithKey (\acc k v -> f acc v) z tree;
  mapWithKey :: forall k a b. (k -> a -> b) -> Map k a -> Map k b;
  mapWithKey f tree =
    case tree of {
      MapEmpty -> MapEmpty;
      MapNode n k v l r -> node n k (f k v) (mapWithKey f l) (mapWithKey f r)
    };
  map :: forall a b k. (a -> b) -> Map k a -> Map k b;
  map f tree = mapWithKey (\k v -> f v) tree;
  toList :: forall k v. Map k v -> [] ((,) k v);
  toList tree = entriesInto [] tree;
  entriesInto :: forall k v. [] ((,) k v) -> Map k v -> [] ((,) k v);
  entriesInto rest tree =
    case tree of {
      MapEmpty -> rest;
      MapNode n key value left right ->
        entriesInto ((:) ((,) key value) (entriesInto rest right)) left
    };
  toAscList :: forall k v. Map k v -> [] ((,) k v);
  toAscList tree = toList tree;
  keys :: forall k v. Map k v -> [] k;
  keys tree = keysInto [] tree;
  keysInto :: forall k v. [] k -> Map k v -> [] k;
  keysInto rest tree =
    case tree of {
      MapEmpty -> rest;
      MapNode n key value left right -> keysInto ((:) key (keysInto rest right)) left
    };
  elems :: forall k v. Map k v -> [] v;
  elems tree = valuesInto [] tree;
  valuesInto :: forall k v. [] v -> Map k v -> [] v;
  valuesInto rest tree =
    case tree of {
      MapEmpty -> rest;
      MapNode n key value left right -> valuesInto ((:) value (valuesInto rest right)) left
    };
  keysSet :: forall k v. Map k v -> Set k;
  keysSet tree =
    let {
      result = map (\v -> ()) tree
    } in
    seq result (Set result);
  fromList :: forall k v. (k -> k -> Int) -> [] ((,) k v) -> Map k v;
  fromList cmp entries = fromDistinctAscList (fromListMergeRuns cmp (fromListRuns cmp entries));
  -- Merge already ordered lists before allocating the final balanced map.
  -- Equal keys keep the later run's key and lazy value. fromListWith remains
  -- separate because arbitrary value combinations need not be associative.
  fromListRuns :: forall k v. (k -> k -> Int) -> [] ((,) k v) -> [] ([] ((,) k v));
  fromListRuns cmp entries = case entries of {
    [] -> [];
    (:) ((,) key value) rest -> seq key (fromListRunStart cmp key value rest)
  };
  fromListRunStart :: forall k v. (k -> k -> Int) -> k -> v -> [] ((,) k v) -> [] ([] ((,) k v));
  fromListRunStart cmp key value entries = case entries of {
    [] -> [[((,) key value)]];
    (:) ((,) nextKey nextValue) rest -> let { order = cmp nextKey key } in
      if order == 0 then seq nextKey (fromListRunStart cmp nextKey nextValue rest)
      else if order > 0 then seq nextKey
        (fromListRunAscending cmp [((,) key value)] nextKey nextValue rest)
      else seq nextKey
        (fromListRunDescending cmp [((,) key value)] nextKey nextValue rest)
  };
  fromListRunAscending :: forall k v. (k -> k -> Int) -> [] ((,) k v) -> k -> v ->
    [] ((,) k v) -> [] ([] ((,) k v));
  fromListRunAscending cmp reversed key value entries = case entries of {
    [] -> [S.reverse ((:) ((,) key value) reversed)];
    (:) ((,) nextKey nextValue) rest -> let { order = cmp nextKey key } in
      if order < 0 then
        (:) (S.reverse ((:) ((,) key value) reversed))
          (fromListRuns cmp entries)
      else if order == 0 then seq nextKey
        (fromListRunAscending cmp reversed nextKey nextValue rest)
      else seq nextKey
        (fromListRunAscending cmp ((:) ((,) key value) reversed) nextKey nextValue rest)
  };
  fromListRunDescending :: forall k v. (k -> k -> Int) -> [] ((,) k v) -> k -> v ->
    [] ((,) k v) -> [] ([] ((,) k v));
  fromListRunDescending cmp reversed key value entries = case entries of {
    [] -> [((:) ((,) key value) reversed)];
    (:) ((,) nextKey nextValue) rest -> let { order = cmp nextKey key } in
      if order > 0 then
        (:) (((:) ((,) key value) reversed)) (fromListRuns cmp entries)
      else if order == 0 then seq nextKey
        (fromListRunDescending cmp reversed nextKey nextValue rest)
      else seq nextKey
        (fromListRunDescending cmp ((:) ((,) key value) reversed) nextKey nextValue rest)
  };
  fromListMergeRuns :: forall k v. (k -> k -> Int) -> [] ([] ((,) k v)) -> [] ((,) k v);
  fromListMergeRuns cmp runs = case runs of {
    [] -> [];
    (:) only [] -> only;
    _ -> fromListMergeRuns cmp (fromListMergePairs cmp runs)
  };
  fromListMergePairs :: forall k v. (k -> k -> Int) -> [] ([] ((,) k v)) -> [] ([] ((,) k v));
  fromListMergePairs cmp runs = case runs of {
    [] -> [];
    (:) only [] -> [only];
    (:) earlier ((:) later rest) -> (:) (fromListMergeEntries cmp earlier later) (fromListMergePairs cmp rest)
  };
  fromListMergeEntries :: forall k v. (k -> k -> Int) -> [] ((,) k v) ->
    [] ((,) k v) -> [] ((,) k v);
  fromListMergeEntries cmp earlier later = case earlier of {
    [] -> later;
    (:) first rest -> case later of {
      [] -> earlier;
      (:) second tail -> let { order = cmp (S.fst first) (S.fst second) } in
        if order < 0 then (:) first (fromListMergeEntries cmp rest later)
        else if order > 0 then (:) second (fromListMergeEntries cmp earlier tail)
        else (:) second (fromListMergeEntries cmp rest tail)
    }
  };
  fromListWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> [] ((,) k v) -> Map k v;
  -- A sorted prefix needs one comparison per incoming key and one final node
  -- per distinct key. Preserve the newest equivalent key representative and
  -- the lazy combine(new,old) value. Once ordering breaks, use ordinary insert.
  fromListWith cmp combine entries = case entries of {
    [] -> empty;
    (:) ((,) key value) rest -> seq key (fromListAscending cmp combine [] key value rest)
  };
  fromListAscending :: forall k v. (k -> k -> Int) -> (v -> v -> v) ->
    [] ((,) k v) -> k -> v -> [] ((,) k v) -> Map k v;
  fromListAscending cmp combine reversed key value entries = case entries of {
    [] -> fromDistinctAscList (S.reverse ((:) ((,) key value) reversed));
    (:) ((,) nextKey nextValue) rest -> let { order = cmp nextKey key } in
      if order < 0 then fromListInsert cmp combine
        (fromDistinctAscList (S.reverse ((:) ((,) key value) reversed))) entries
      else if order == 0 then seq nextKey
        (fromListAscending cmp combine reversed nextKey (combine nextValue value) rest)
      else seq nextKey (fromListAscending cmp combine ((:) ((,) key value) reversed) nextKey nextValue rest)
  };
  fromListInsert :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> Map k v ->
    [] ((,) k v) -> Map k v;
  fromListInsert cmp combine initial entries = S.foldlStrict
    (\tree entry -> case entry of { (,) k v -> insertWith cmp combine k v tree }) initial entries;
  fromDistinctAscList :: forall k v. [] ((,) k v) -> Map k v;
  fromDistinctAscList entries = S.fst (buildAsc (S.length entries) entries);
  buildAsc :: forall k v. Int -> [] ((,) k v) -> (,) (Map k v) ([] ((,) k v));
  buildAsc n entries =
    if (n <= 0)
    then (,) MapEmpty entries
    else case buildAsc (quotInt n 2) entries of {
           (,) left rest ->
             case rest of {
               [] -> (,) left [];
               (:) ((,) key value) tail ->
                 case buildAsc ((n - quotInt n 2) - 1) tail of {
                   (,) right after -> (,) (bin key value left right) after
                 }
             }
         };
  union :: forall k v. (k -> k -> Int) -> Map k v -> Map k v -> Map k v;
  union cmp a b = unionWith cmp (\left right -> left) a b;
  unionWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> Map k v -> Map k v -> Map k v;
  -- Split the right tree around each left root, then join already ordered
  -- subtrees. Duplicate keys retain the left representative and lazy value.
  unionWith cmp combine a b = case a of {
    MapEmpty -> b;
    MapNode _ key value left right -> case b of {
      MapEmpty -> a;
      MapNode _ other rhs MapEmpty MapEmpty -> insertRightWith cmp combine other rhs a;
      _ -> case a of {
        MapNode _ _ _ MapEmpty MapEmpty -> insertWith cmp combine key value b;
        _ -> case unionSplit cmp key b of {
          (,,) before found after -> unionJoin key
            (case found of { Nothing -> value; Just old -> combine value old })
            (unionWith cmp combine left before) (unionWith cmp combine right after)
        }
      }
    }
  };
  unionSplit :: forall k v. (k -> k -> Int) -> k -> Map k v ->
    (,,) (Map k v) (Maybe v) (Map k v);
  unionSplit cmp key tree = case tree of {
    MapEmpty -> (,,) MapEmpty Nothing MapEmpty;
    MapNode _ k v l r -> let { order = cmp key k } in
      if order < 0 then case unionSplit cmp key l of {
        (,,) before found after -> let { greater = unionJoin k v after r } in
          seq greater ((,,) before found greater)
      } else if order > 0 then case unionSplit cmp key r of {
        (,,) before found after -> let { lesser = unionJoin k v l before } in
          seq lesser ((,,) lesser found after)
      } else (,,) l (Just v) r
  };
  -- Both inputs are valid maps and all left keys precede key, which precedes
  -- all right keys. Descend the larger side before restoring the balance.
  unionJoin :: forall k v. k -> v -> Map k v -> Map k v -> Map k v;
  unionJoin key value left right = case left of {
    MapEmpty -> insertLeast key value right;
    MapNode leftSize lk lv ll lr -> case right of {
      MapEmpty -> insertGreatest key value left;
      MapNode rightSize rk rv rl rr ->
        if rightSize > 3 * leftSize then balance rk rv (unionJoin key value left rl) rr
        else if leftSize > 3 * rightSize then balance lk lv ll (unionJoin key value lr right)
        else bin key value left right
    }
  };
  insertLeast :: forall k v. k -> v -> Map k v -> Map k v;
  insertLeast key value tree = case tree of {
    MapEmpty -> singleton key value;
    MapNode _ k v l r -> balance k v (insertLeast key value l) r
  };
  insertGreatest :: forall k v. k -> v -> Map k v -> Map k v;
  insertGreatest key value tree = case tree of {
    MapEmpty -> singleton key value;
    MapNode _ k v l r -> balance k v l (insertGreatest key value r)
  };
  insertRightWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> k -> v -> Map k v -> Map k v;
  insertRightWith cmp combine key value tree =
    case tree of {
      MapEmpty -> singleton key value;
      MapNode n k v l r ->
        let { c = cmp key k } in
        if c < 0 then balance k v (insertRightWith cmp combine key value l) r
        else if c > 0 then balance k v l (insertRightWith cmp combine key value r)
        else node n k (combine v value) l r
    };
  unions :: forall k v. (k -> k -> Int) -> [] (Map k v) -> Map k v;
  unions cmp trees = S.foldlStrict (union cmp) empty trees;
  unionsWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> [] (Map k v) -> Map k v;
  unionsWith cmp combine trees = S.foldlStrict (unionWith cmp combine) empty trees;
  difference :: forall k a b. (k -> k -> Int) -> Map k a -> Map k b -> Map k a;
  difference cmp a b = foldlWithKeyStrict (\tree k v -> delete cmp k tree) a b;
  intersection :: forall k a b. (k -> k -> Int) -> Map k a -> Map k b -> Map k a;
  intersection cmp a b = intersectionWith cmp (\left right -> left) a b;
  intersectionWith :: forall k a b c. (k -> k -> Int) ->
                                      (a -> b -> c) -> Map k a -> Map k b -> Map k c;
  intersectionWith cmp combine a b =
    foldlWithKeyStrict
      (\tree k v ->
         case lookup cmp k b of {
           Nothing -> tree;
           Just w -> insert cmp k (combine v w) tree
         })
      empty
      a;
  filterWithKey :: forall k v. (k -> v -> Bool) -> Map k v -> Map k v;
  filterWithKey predicate tree =
    fromDistinctAscList
      (S.filter
         (\entry ->
            case entry of {
              (,) k v -> predicate k v
            })
         (toList tree));
  filter :: forall v k. (v -> Bool) -> Map k v -> Map k v;
  filter predicate tree = filterWithKey (\k v -> predicate v) tree;
  mapMaybeWithKey :: forall k a b. (k -> a -> Maybe b) -> Map k a -> Map k b;
  mapMaybeWithKey f tree =
    fromDistinctAscList
      (S.mapMaybe
         (\entry ->
            case entry of {
              (,) k v -> S.mapOptional ((,) k) (f k v)
            })
         (toList tree));
  mapMaybe :: forall a b k. (a -> Maybe b) -> Map k a -> Map k b;
  mapMaybe f tree = mapMaybeWithKey (\k v -> f v) tree;
  mapKeys :: forall j k v. (j -> j -> Int) -> (k -> j) -> Map k v -> Map j v;
  mapKeys cmp f tree =
    fromList cmp
      (S.map
         (\entry ->
            case entry of {
              (,) k v -> (,) (f k) v
            })
         (toList tree));
  splitLookup :: forall k v. (k -> k -> Int) ->
                             k -> Map k v -> (,,) (Map k v) (Maybe v) (Map k v);
  splitLookup cmp key tree =
    (,,) (filterWithKey (\k v -> (cmp k key < 0)) tree) (lookup cmp key tree)
      (filterWithKey (\k v -> (cmp k key > 0)) tree);
  eqMap :: forall k v. (k -> k -> Bool) -> (v -> v -> Bool) -> Map k v -> Map k v -> Bool;
  eqMap ek ev a b = ((size a == size b) && S.eqList (S.eqPair ek ev) (toList a) (toList b));
  valid :: forall k v. (k -> k -> Int) -> Map k v -> Bool;
  valid cmp tree = validBetween cmp Nothing Nothing tree;
  validBetween :: forall k v. (k -> k -> Int) -> Maybe k -> Maybe k -> Map k v -> Bool;
  validBetween cmp lower upper tree =
    case tree of {
      MapEmpty -> True;
      MapNode n k v l r ->
        ((n == ((1 + size l) + size r)) &&
         (S.maybe True (\key -> (cmp key k < 0)) lower &&
          (S.maybe True (\key -> (cmp k key < 0)) upper &&
           ((((size l + size r) <= 1) || ((size l <= (3 * size r)) && (size r <= (3 * size l)))) &&
            (validBetween cmp lower (Just k) l && validBetween cmp (Just k) upper r)))))
    }
}
