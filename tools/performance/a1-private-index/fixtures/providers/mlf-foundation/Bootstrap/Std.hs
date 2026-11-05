-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Std where {
  import MLF.Primitive;
  import Bootstrap.Types;
  id :: forall a. a -> a;
  id x = x;
  const :: forall a b. a -> b -> a;
  const x y = x;
  flip :: forall a b c. (a -> b -> c) -> b -> a -> c;
  flip f y x = f x y;
  compose :: forall b c a. (b -> c) -> (a -> b) -> a -> c;
  compose f g x = f (g x);
  fst :: forall a b. (,) a b -> a;
  fst ((,) a b) = a;
  snd :: forall a b. (,) a b -> b;
  snd ((,) a b) = b;
  uncurry :: forall a b c. (a -> b -> c) -> (,) a b -> c;
  uncurry f ((,) a b) = f a b;
  curry :: forall a b c. ((,) a b -> c) -> a -> b -> c;
  curry f a b = f ((,) a b);
  first :: forall a b c. (a -> b) -> (,) a c -> (,) b c;
  first f ((,) a c) = (,) (f a) c;
  second :: forall a b c. (a -> b) -> (,) c a -> (,) c b;
  second f ((,) c a) = (,) c (f a);
  not :: Bool -> Bool;
  not x = if x then False else True;
  and :: [] Bool -> Bool;
  and xs =
    case xs of {
      [] -> True;
      (:) x rest -> (x && and rest)
    };
  or :: [] Bool -> Bool;
  or xs =
    case xs of {
      [] -> False;
      (:) x rest -> (x || or rest)
    };
  compareInt :: Int -> Int -> Int;
  compareInt a b = if (a < b) then (0 - 1) else if (a == b) then 0 else 1;
  min :: Int -> Int -> Int;
  min a b = if (a < b) then a else b;
  max :: Int -> Int -> Int;
  max a b = if (a < b) then b else a;
  abs :: Int -> Int;
  abs a = if (a < 0) then (0 - a) else a;
  negateInt :: Int -> Int;
  negateInt a = (0 - a);
  signum :: Int -> Int;
  signum a = compareInt a 0;
  null :: forall a. [] a -> Bool;
  null xs =
    case xs of {
      [] -> True;
      (:) x rest -> False
    };
  length :: forall a. [] a -> Int;
  length xs = lengthAcc 0 xs;
  lengthAcc :: forall a. Int -> [] a -> Int;
  lengthAcc n xs =
    case xs of {
      [] -> n;
      (:) x rest ->
        let {
          next = (n + 1)
        } in
        seq next (lengthAcc next rest)
    };
  singleton :: forall a. a -> [] a;
  singleton x = (:) x [];
  append :: forall a. [] a -> [] a -> [] a;
  append xs ys =
    case xs of {
      [] -> ys;
      (:) x rest -> (:) x (append rest ys)
    };
  snoc :: forall a. [] a -> a -> [] a;
  snoc xs x = append xs ((:) x []);
  map :: forall a b. (a -> b) -> [] a -> [] b;
  map f xs =
    case xs of {
      [] -> [];
      (:) x rest -> (:) (f x) (map f rest)
    };
  foldr :: forall a b. (a -> b -> b) -> b -> [] a -> b;
  foldr f z xs =
    case xs of {
      [] -> z;
      (:) x rest -> f x (foldr f z rest)
    };
  foldl :: forall b a. (b -> a -> b) -> b -> [] a -> b;
  foldl f z xs =
    case xs of {
      [] -> z;
      (:) x rest -> foldl f (f z x) rest
    };
  foldlStrict :: forall b a. (b -> a -> b) -> b -> [] a -> b;
  foldlStrict f z xs =
    case xs of {
      [] -> z;
      (:) x rest ->
        let {
          next = f z x
        } in
        seq next (foldlStrict f next rest)
    };
  reverse :: forall a. [] a -> [] a;
  reverse xs = foldl (\acc x -> (:) x acc) [] xs;
  concat :: forall a. [] ([] a) -> [] a;
  concat xs = foldr append [] xs;
  concatMap :: forall a b. (a -> [] b) -> [] a -> [] b;
  concatMap f xs = foldr (\x rest -> append (f x) rest) [] xs;
  filter :: forall a. (a -> Bool) -> [] a -> [] a;
  filter p xs =
    case xs of {
      [] -> [];
      (:) x rest -> if p x then (:) x (filter p rest) else filter p rest
    };
  partition :: forall a. (a -> Bool) -> [] a -> (,) ([] a) ([] a);
  partition p xs =
    case xs of {
      [] -> (,) [] [];
      (:) x rest ->
        case partition p rest of {
          (,) yes no -> if p x then (,) ((:) x yes) no else (,) yes ((:) x no)
        }
    };
  any :: forall a. (a -> Bool) -> [] a -> Bool;
  any f xs =
    case xs of {
      [] -> False;
      (:) x rest -> (f x || any f rest)
    };
  all :: forall a. (a -> Bool) -> [] a -> Bool;
  all f xs =
    case xs of {
      [] -> True;
      (:) x rest -> (f x && all f rest)
    };
  find :: forall a. (a -> Bool) -> [] a -> Maybe a;
  find p xs =
    case xs of {
      [] -> Nothing;
      (:) x rest -> if p x then Just x else find p rest
    };
  elem :: forall a. (a -> a -> Bool) -> a -> [] a -> Bool;
  elem eq x xs = any (eq x) xs;
  notElem :: forall a. (a -> a -> Bool) -> a -> [] a -> Bool;
  notElem eq x xs = not (elem eq x xs);
  lookup :: forall a b. (a -> a -> Bool) -> a -> [] ((,) a b) -> Maybe b;
  lookup eq k xs =
    case xs of {
      [] -> Nothing;
      (:) ((,) key value) rest -> if eq k key then Just value else lookup eq k rest
    };
  head :: forall a. [] a -> a;
  head xs =
    case xs of {
      [] -> panic "head: empty list";
      (:) x rest -> x
    };
  tail :: forall a. [] a -> [] a;
  tail xs =
    case xs of {
      [] -> panic "tail: empty list";
      (:) x rest -> rest
    };
  last :: forall a. [] a -> a;
  last xs =
    case xs of {
      [] -> panic "last: empty list";
      (:) x rest -> if null rest then x else last rest
    };
  init :: forall a. [] a -> [] a;
  init xs =
    case xs of {
      [] -> panic "init: empty list";
      (:) x rest -> if null rest then [] else (:) x (init rest)
    };
  index :: forall a. [] a -> Int -> a;
  index xs n =
    if (n < 0)
    then panic "index: negative index"
    else case xs of {
           [] -> panic "index: out of bounds";
           (:) x rest -> if (n == 0) then x else index rest (n - 1)
         };
  at :: forall a. Int -> [] a -> Maybe a;
  at n xs =
    if (n < 0)
    then Nothing
    else case xs of {
           [] -> Nothing;
           (:) x rest -> if (n == 0) then Just x else at (n - 1) rest
         };
  take :: forall a. Int -> [] a -> [] a;
  take n xs =
    if (n <= 0)
    then []
    else case xs of {
           [] -> [];
           (:) x rest -> (:) x (take (n - 1) rest)
         };
  drop :: forall a. Int -> [] a -> [] a;
  drop n xs =
    if (n <= 0)
    then xs
    else case xs of {
           [] -> [];
           (:) x rest -> drop (n - 1) rest
         };
  splitAt :: forall a. Int -> [] a -> (,) ([] a) ([] a);
  splitAt n xs =
    if (n <= 0)
    then (,) [] xs
    else case xs of {
           [] -> (,) [] [];
           (:) x rest ->
             case splitAt (n - 1) rest of {
               (,) before after -> (,) ((:) x before) after
             }
         };
  takeWhile :: forall a. (a -> Bool) -> [] a -> [] a;
  takeWhile p xs =
    case xs of {
      [] -> [];
      (:) x rest -> if p x then (:) x (takeWhile p rest) else []
    };
  dropWhile :: forall a. (a -> Bool) -> [] a -> [] a;
  dropWhile p xs =
    case xs of {
      [] -> [];
      (:) x rest -> if p x then dropWhile p rest else xs
    };
  span :: forall a. (a -> Bool) -> [] a -> (,) ([] a) ([] a);
  span p xs =
    case xs of {
      [] -> (,) [] [];
      (:) x rest ->
        if p x
        then case span p rest of {
               (,) before after -> (,) ((:) x before) after
             }
        else (,) [] xs
    };
  break :: forall a. (a -> Bool) -> [] a -> (,) ([] a) ([] a);
  break p xs = span (\x -> not (p x)) xs;
  replicate :: forall a. Int -> a -> [] a;
  replicate n x = if (n <= 0) then [] else (:) x (replicate (n - 1) x);
  range :: Int -> Int -> [] Int;
  range first last = if (first > last) then [] else (:) first (range (first + 1) last);
  iterate :: forall a. (a -> a) -> a -> [] a;
  iterate f x = (:) x (iterate f (f x));
  repeat :: forall a. a -> [] a;
  repeat x = (:) x (repeat x);
  zip :: forall a b. [] a -> [] b -> [] ((,) a b);
  zip xs ys =
    case xs of {
      [] -> [];
      (:) x rest ->
        case ys of {
          [] -> [];
          (:) y resty -> (:) ((,) x y) (zip rest resty)
        }
    };
  zipWith :: forall a b c. (a -> b -> c) -> [] a -> [] b -> [] c;
  zipWith f xs ys =
    case xs of {
      [] -> [];
      (:) x rest ->
        case ys of {
          [] -> [];
          (:) y resty -> (:) (f x y) (zipWith f rest resty)
        }
    };
  unzip :: forall a b. [] ((,) a b) -> (,) ([] a) ([] b);
  unzip xs =
    foldr
      (\p result ->
         case p of {
           (,) a b ->
             case result of {
               (,) as bs -> (,) ((:) a as) ((:) b bs)
             }
         })
      ((,) [] [])
      xs;
  mapIndexed :: forall a b. (Int -> a -> b) -> [] a -> [] b;
  mapIndexed f xs = zipWith f (range 0 (length xs - 1)) xs;
  intersperse :: forall a. a -> [] a -> [] a;
  intersperse sep xs =
    case xs of {
      [] -> [];
      (:) x rest ->
        case rest of {
          [] -> (:) x [];
          (:) y ys -> (:) x ((:) sep (intersperse sep rest))
        }
    };
  intercalate :: String -> [] String -> String;
  intercalate sep xs = concatStrings (intersperse sep xs);
  -- Join through the general primitive so contiguous UTF-8 fragments are
  -- copied once. It preserves the original head-before-tail demand order.
  concatStrings :: [] String -> String;
  concatStrings xs = concatStringList xs;
  concatStringPairs :: [] String -> [] String;
  concatStringPairs xs =
    case xs of {
      [] -> [];
      (:) first rest ->
        seq first
          (case rest of {
             [] -> (:) first [];
             (:) second tail ->
               let {
                 joined = concatString first second
               } in
               seq joined ((:) joined (concatStringPairs tail))
           })
    };
  unwords :: [] String -> String;
  unwords xs = intercalate " " xs;
  unlines :: [] String -> String;
  unlines xs = concatStrings (map (\s -> (s ++ "\n")) xs);
  sum :: [] Int -> Int;
  sum xs = foldl addInt 0 xs;
  product :: [] Int -> Int;
  product xs = foldl mulInt 1 xs;
  nubBy :: forall a. (a -> a -> Bool) -> [] a -> [] a;
  nubBy eq xs = nubSeen eq [] xs;
  nubSeen :: forall a. (a -> a -> Bool) -> [] a -> [] a -> [] a;
  nubSeen eq seen xs =
    case xs of {
      [] -> [];
      (:) x rest ->
        if elem eq x seen then nubSeen eq seen rest else (:) x (nubSeen eq ((:) x seen) rest)
    };
  deleteBy :: forall a. (a -> a -> Bool) -> a -> [] a -> [] a;
  deleteBy eq wanted xs =
    case xs of {
      [] -> [];
      (:) x rest -> if eq wanted x then rest else (:) x (deleteBy eq wanted rest)
    };
  sortBy :: forall a. (a -> a -> Int) -> [] a -> [] a;
  sortBy cmp xs =
    if (length xs < 2)
    then xs
    else case splitAt (quotInt (length xs) 2) xs of {
           (,) as bs -> mergeBy cmp (sortBy cmp as) (sortBy cmp bs)
         };
  mergeBy :: forall a. (a -> a -> Int) -> [] a -> [] a -> [] a;
  mergeBy cmp xs ys =
    case xs of {
      [] -> ys;
      (:) x restx ->
        case ys of {
          [] -> xs;
          (:) y resty ->
            if (cmp x y <= 0) then (:) x (mergeBy cmp restx ys) else (:) y (mergeBy cmp xs resty)
        }
    };
  eqList :: forall a. (a -> a -> Bool) -> [] a -> [] a -> Bool;
  eqList eq xs ys =
    case xs of {
      [] -> null ys;
      (:) x rest ->
        case ys of {
          [] -> False;
          (:) y resty -> (eq x y && eqList eq rest resty)
        }
    };
  compareList :: forall a. (a -> a -> Int) -> [] a -> [] a -> Int;
  compareList cmp xs ys =
    case xs of {
      [] -> if null ys then 0 else (0 - 1);
      (:) x rest ->
        case ys of {
          [] -> 1;
          (:) y resty ->
            let {
              c = cmp x y
            } in
            if (c == 0) then compareList cmp rest resty else c
        }
    };
  maybe :: forall b a. b -> (a -> b) -> Maybe a -> b;
  maybe fallback f value =
    case value of {
      Nothing -> fallback;
      Just x -> f x
    };
  fromMaybe :: forall a. a -> Maybe a -> a;
  fromMaybe fallback value = maybe fallback id value;
  isJust :: forall a. Maybe a -> Bool;
  isJust value =
    case value of {
      Nothing -> False;
      Just x -> True
    };
  isNothing :: forall a. Maybe a -> Bool;
  isNothing value = not (isJust value);
  fromJust :: forall a. Maybe a -> a;
  fromJust value =
    case value of {
      Nothing -> panic "fromJust: Nothing";
      Just x -> x
    };
  maybeToList :: forall a. Maybe a -> [] a;
  maybeToList value = maybe [] singleton value;
  listToMaybe :: forall a. [] a -> Maybe a;
  listToMaybe xs =
    case xs of {
      [] -> Nothing;
      (:) x rest -> Just x
    };
  mapMaybe :: forall a b. (a -> Maybe b) -> [] a -> [] b;
  mapMaybe f xs = concatMap (\x -> maybeToList (f x)) xs;
  catMaybes :: forall a. [] (Maybe a) -> [] a;
  catMaybes xs = mapMaybe id xs;
  mapOptional :: forall a b. (a -> b) -> Maybe a -> Maybe b;
  mapOptional f x = maybe Nothing (\a -> Just (f a)) x;
  bindMaybe :: forall a b. Maybe a -> (a -> Maybe b) -> Maybe b;
  bindMaybe x f = maybe Nothing f x;
  eqMaybe :: forall a. (a -> a -> Bool) -> Maybe a -> Maybe a -> Bool;
  eqMaybe eq a b =
    case a of {
      Nothing -> isNothing b;
      Just x ->
        case b of {
          Nothing -> False;
          Just y -> eq x y
        }
    };
  compareMaybe :: forall a. (a -> a -> Int) -> Maybe a -> Maybe a -> Int;
  compareMaybe cmp a b =
    case a of {
      Nothing -> if isNothing b then 0 else (0 - 1);
      Just x ->
        case b of {
          Nothing -> 1;
          Just y -> cmp x y
        }
    };
  either :: forall e b a. (e -> b) -> (a -> b) -> Either e a -> b;
  either failure success value =
    case value of {
      Left e -> failure e;
      Right x -> success x
    };
  bindEither :: forall e a b. Either e a -> (a -> Either e b) -> Either e b;
  bindEither value next =
    case value of {
      Left e -> Left e;
      Right x -> next x
    };
  eitherBind :: forall e a b. Either e a -> (a -> Either e b) -> Either e b;
  eitherBind value next = bindEither value next;
  mapEither :: forall a b e. (a -> b) -> Either e a -> Either e b;
  mapEither f value = bindEither value (\x -> Right (f x));
  mapLeft :: forall e f a. (e -> f) -> Either e a -> Either f a;
  mapLeft f value =
    case value of {
      Left e -> Left (f e);
      Right x -> Right x
    };
  isLeft :: forall e a. Either e a -> Bool;
  isLeft value =
    case value of {
      Left e -> True;
      Right x -> False
    };
  isRight :: forall e a. Either e a -> Bool;
  isRight value = not (isLeft value);
  traverseEither :: forall a e b. (a -> Either e b) -> [] a -> Either e ([] b);
  traverseEither f xs =
    case xs of {
      [] -> Right [];
      (:) x rest -> bindEither (f x) (\y -> mapEither ((:) y) (traverseEither f rest))
    };
  foldEither :: forall b a e. (b -> a -> Either e b) -> b -> [] a -> Either e b;
  foldEither f z xs =
    case xs of {
      [] -> Right z;
      (:) x rest -> bindEither (f z x) (\next -> foldEither f next rest)
    };
  sequenceEither :: forall e a. [] (Either e a) -> Either e ([] a);
  sequenceEither xs = traverseEither id xs;
  ensure :: Bool -> String -> Either String ();
  ensure condition message = if condition then Right () else Left message;
  instance forall e. Functor (Either e) where {
    fmap function action = bindEither action (\value -> Right (function value))
  };
  instance forall e. Applicative (Either e) where {
    pure = Right;
    (<*>) action argument =
      bindEither action (\function -> bindEither argument (\value -> Right (function value)))
  };
  instance forall e. Monad (Either e) where {
    (>>=) = bindEither
  };
  instance Functor Maybe where {
    fmap function action = bindMaybe action (\value -> Just (function value))
  };
  instance Applicative Maybe where {
    pure = Just;
    (<*>) action argument =
      bindMaybe action (\function -> bindMaybe argument (\value -> Just (function value)))
  };
  instance Monad Maybe where {
    (>>=) = bindMaybe
  };
  mapM :: forall (m :: (* -> *)) a b. (Monad m) => (a -> m b) -> [] a -> m ([] b);
  mapM f xs =
    case xs of {
      [] -> return [];
      (:) x rest ->
        do {
          y <- f x;
          ys <- mapM f rest;
          return ((:) y ys)
        }
    };
  mapM_ :: forall (m :: (* -> *)) a b. (Monad m) => (a -> m b) -> [] a -> m ();
  mapM_ f xs =
    case xs of {
      [] -> return ();
      (:) x rest ->
        do {
          f x;
          mapM_ f rest
        }
    };
  forM :: forall (m :: (* -> *)) a b. (Monad m) => [] a -> (a -> m b) -> m ([] b);
  forM xs f = mapM f xs;
  forM_ :: forall (m :: (* -> *)) a b. (Monad m) => [] a -> (a -> m b) -> m ();
  forM_ xs f = mapM_ f xs;
  foldM :: forall (m :: (* -> *)) b a. (Monad m) => (b -> a -> m b) -> b -> [] a -> m b;
  foldM f z xs =
    case xs of {
      [] -> return z;
      (:) x rest ->
        do {
          next <- f z x;
          foldM f next rest
        }
    };
  sequence :: forall (m :: (* -> *)) a. (Monad m) => [] (m a) -> m ([] a);
  sequence xs = mapM id xs;
  when :: forall (m :: (* -> *)). (Monad m) => Bool -> m () -> m ();
  when condition action = if condition then action else return ();
  unless :: forall (m :: (* -> *)). (Monad m) => Bool -> m () -> m ();
  unless condition action = when (not condition) action;
  compareKind :: Kind -> Kind -> Int;
  compareKind a b =
    case a of {
      Star ->
        case b of {
          Star -> 0;
          KArrow x y -> (0 - 1)
        };
      KArrow x y ->
        case b of {
          Star -> 1;
          KArrow z w ->
            let {
              c = compareKind x z
            } in
            if (c == 0) then compareKind y w else c
        }
    };
  eqKind :: Kind -> Kind -> Bool;
  eqKind a b = (compareKind a b == 0);
  equalKind :: Kind -> Kind -> Bool;
  equalKind a b = eqKind a b;
  compareFlag :: Flag -> Flag -> Int;
  compareFlag a b =
    case a of {
      Flexible ->
        case b of {
          Flexible -> 0;
          Rigid -> (0 - 1)
        };
      Rigid ->
        case b of {
          Flexible -> 1;
          Rigid -> 0
        }
    };
  eqFlag :: Flag -> Flag -> Bool;
  eqFlag a b = (compareFlag a b == 0);
  equalFlag :: Flag -> Flag -> Bool;
  equalFlag a b = eqFlag a b;
  nameId :: XName -> Int;
  nameId (XName i hint) = i;
  nameHint :: XName -> String;
  nameHint (XName i hint) = hint;
  tyVarId :: XTyVar -> Int;
  tyVarId (XTyVar i) = i;
  compareName :: XName -> XName -> Int;
  compareName a b = compareInt (nameId a) (nameId b);
  eqName :: XName -> XName -> Bool;
  eqName a b = (nameId a == nameId b);
  compareTyVar :: XTyVar -> XTyVar -> Int;
  compareTyVar a b = compareInt (tyVarId a) (tyVarId b);
  eqTyVar :: XTyVar -> XTyVar -> Bool;
  eqTyVar a b = (tyVarId a == tyVarId b);
  comparePair :: forall a b. (a -> a -> Int) -> (b -> b -> Int) -> (,) a b -> (,) a b -> Int;
  comparePair ca cb ((,) a b) ((,) x y) =
    let {
      c = ca a x
    } in
    if (c == 0) then cb b y else c;
  eqPair :: forall a b. (a -> a -> Bool) -> (b -> b -> Bool) -> (,) a b -> (,) a b -> Bool;
  eqPair ea eb ((,) a b) ((,) x y) = (ea a x && eb b y);
  concatMapString :: forall a. (a -> String) -> [] a -> String;
  concatMapString f xs = concatStrings (map f xs);
  negateDouble :: Double -> Double;
  negateDouble value =
    let {
      bits = doubleToBits value
    } in
    doubleFromBits
      (if (bits < 9223372036854775808)
       then (bits + 9223372036854775808)
       else (bits - 9223372036854775808))
}
