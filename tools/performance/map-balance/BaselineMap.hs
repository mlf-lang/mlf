-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module BaselineMap where {
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
  fromList cmp entries =
    S.foldlStrict
      (\tree entry ->
         case entry of {
           (,) k v -> insert cmp k v tree
         })
      empty
      entries;
  fromListWith :: forall k v. (k -> k -> Int) -> (v -> v -> v) -> [] ((,) k v) -> Map k v;
  fromListWith cmp combine entries =
    S.foldlStrict
      (\tree entry ->
         case entry of {
           (,) k v -> insertWith cmp combine k v tree
         })
      empty
      entries;
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
  -- Insert only the smaller input. In particular, accumulating singleton sets
  -- must not rebuild the growing left map at every union. The right-input
  -- worker retains the left key representative and combine argument order.
  unionWith cmp combine a b =
    case a of {
      MapEmpty -> b;
      MapNode _ _ _ _ _ -> case b of {
        MapEmpty -> a;
        MapNode _ _ _ _ _ ->
          if size a <= size b
          then foldlWithKeyStrict (\tree k v -> insertWith cmp combine k v tree) b a
          else foldlWithKeyStrict (\tree k v -> insertRightWith cmp combine k v tree) a b
      }
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
