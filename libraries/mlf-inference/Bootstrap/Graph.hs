-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Graph where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntTree as IT;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.ST as ST;
  -- Persistent graph operations. Identities are retained through aliases, while
  -- permissions are always checked on the immutable graph before unification.
  nodes :: Graph -> IntMap Node;
  nodes (Graph ns ls fresh) = ns;
  links :: Graph -> IntMap Int;
  links (Graph ns ls fresh) = ls;
  nextId :: Graph -> Int;
  nextId (Graph ns ls fresh) = fresh;
  tag :: Node -> GTag;
  tag (Node t b f) = t;
  binder :: Node -> Maybe Int;
  binder (Node t b f) = b;
  flag :: Node -> Flag;
  flag (Node t b f) = f;
  -- Pair fields used as strict-state accumulators must be evaluated before the
  -- next fold step; forcing only the Pair constructor leaves a deferred spine.
  strictPair :: forall a b. a -> b -> (,) a b;
  strictPair a b = seq a (seq b ((,) a b));
  -- Match the seed's strict graph records without making general-purpose maps
  -- strict in their values (recursive runtime environments require lazy values).
  forceIntMap :: forall a. IntMap a -> ();
  forceIntMap (IntMap tree) = seq tree ();
  forceTag :: GTag -> ();
  forceTag t =
    case t of {
      GArr a b -> seq a (seq b ());
      GTyApp a b -> seq a (seq b ());
      GGen n -> seq n ();
      _ -> ()
    };
  mkNode :: GTag -> Maybe Int -> Flag -> Node;
  mkNode t b f = seq (forceTag t) (seq b (seq f (Node t b f)));
  strictNode :: Node -> Node;
  -- Preserve the record after forcing its required fields. Reconstructing the
  -- same Node here allocated a second record at every graph-map boundary.
  strictNode node =
    case node of {
      Node t b f -> seq (forceTag t) (seq b (seq f node))
    };
  mkGraph :: IntMap Node -> IntMap Int -> Int -> Graph;
  mkGraph ns aliases fresh =
    seq (forceIntMap ns) (seq (forceIntMap aliases) (seq fresh (Graph ns aliases fresh)));
  strictGraph :: Graph -> Graph;
  strictGraph graph =
    case graph of {
      Graph ns aliases fresh -> seq (forceIntMap ns) (seq (forceIntMap aliases) (seq fresh graph))
    };
  insertNodeMap :: Int -> Node -> IntMap Node -> IntMap Node;
  insertNodeMap n value ns =
    let {
      strict = strictNode value
    } in
    seq strict (IM.insert n strict ns);
  nodesFromList :: [] ((,) Int Node) -> IntMap Node;
  nodesFromList entries =
    L.foldlStrict
      (\ns ->
         \entry ->
           case entry of {
             (,) n value -> insertNodeMap n value ns
           })
      IM.empty
      entries;
  -- Linear construction when identities are already strictly ascending. Unlike
  -- the generic lazy map builder, every graph node retains strictNode's demand.
  nodesFromDistinctAscList :: [] ((,) Int Node) -> IntMap Node;
  nodesFromDistinctAscList entries =
    seq (L.length entries)
      (case L.foldlStrict
        (\state -> \entry -> case entry of {
          (,) key value -> seq (strictNode value) (IM.ascInsert state entry)
        }) IM.NoState entries of {
        IM.NoState -> IM.empty;
        IM.State key value stack -> IM.wrap (IM.ascLinkStack stack key (IM.tip key value))
      });
  mapNodeTree :: (Int -> Node -> Node) -> IntMapTree Node -> IntMapTree Node;
  mapNodeTree action tree =
    case tree of {
      IntMapNil -> IntMapNil;
      IntMapTip key value ->
        let { result = strictNode (action key value) } in
        seq result (IM.tip key result);
      IntMapBin count prefix left right ->
        let { leftTree = mapNodeTree action left; rightTree = mapNodeTree action right } in
        seq leftTree (seq rightTree (IntMapBin count prefix leftTree rightTree))
    };
  mapNodesWithKey :: (Int -> Node -> Node) -> IntMap Node -> IntMap Node;
  mapNodesWithKey action (IntMap tree) =
    let {
      result = mapNodeTree action tree
    } in
    seq result (IntMap result);
  mapNodes :: (Node -> Node) -> IntMap Node -> IntMap Node;
  mapNodes action ns = mapNodesWithKey (\n -> \value -> action value) ns;
  emptyGraph :: Graph;
  emptyGraph = mkGraph IM.empty IM.empty 0;
  bindE :: forall a b. Either String a -> (a -> Either String b) -> Either String b;
  bindE value action =
    case value of {
      Left message -> Left message;
      Right result -> action result
    };
  mapE :: forall a b. (a -> Either String b) -> [] a -> Either String ([] b);
  mapE action values =
    case values of {
      [] -> Right [];
      (:) value rest ->
        bindE (action value)
          (\result -> bindE (mapE action rest) (\results -> Right ((:) result results)))
    };
  mapE_ :: forall a b. (a -> Either String b) -> [] a -> Either String ();
  mapE_ action values =
    case values of {
      [] -> Right ();
      (:) value rest -> bindE (action value) (\ignored -> mapE_ action rest)
    };
  foldE :: forall a b. (a -> b -> Either String a) -> a -> [] b -> Either String a;
  foldE action initial values =
    case values of {
      [] -> Right initial;
      (:) value rest -> bindE (action initial value) (\next -> foldE action next rest)
    };
  check :: Bool -> String -> Either String ();
  check condition message = if condition then Right () else Left message;
  equalKind :: Kind -> Kind -> Bool;
  equalKind left right =
    case left of {
      Star ->
        case right of {
          Star -> True;
          KArrow _ _ -> False
        };
      KArrow a b ->
        case right of {
          Star -> False;
          KArrow c d -> (equalKind a c && equalKind b d)
        }
    };
  equalFlag :: Flag -> Flag -> Bool;
  equalFlag a b =
    case a of {
      Flexible ->
        case b of {
          Flexible -> True;
          Rigid -> False
        };
      Rigid ->
        case b of {
          Flexible -> False;
          Rigid -> True
        }
    };
  equalMaybeInt :: Maybe Int -> Maybe Int -> Bool;
  equalMaybeInt a b =
    case a of {
      Nothing ->
        case b of {
          Nothing -> True;
          Just _ -> False
        };
      Just x ->
        case b of {
          Nothing -> False;
          Just y -> (x == y)
        }
    };
  equalPermission :: Permission -> Permission -> Bool;
  equalPermission a b =
    case a of {
      Green ->
        case b of {
          Green -> True;
          _ -> False
        };
      Orange ->
        case b of {
          Orange -> True;
          _ -> False
        };
      Red ->
        case b of {
          Red -> True;
          _ -> False
        };
      Inert ->
        case b of {
          Inert -> True;
          _ -> False
        }
    };
  equalInts :: [] Int -> [] Int -> Bool;
  equalInts xs ys =
    case xs of {
      [] ->
        case ys of {
          [] -> True;
          (:) _ _ -> False
        };
      (:) x rest ->
        case ys of {
          [] -> False;
          (:) y tail -> ((x == y) && equalInts rest tail)
        }
    };
  equalTag :: GTag -> GTag -> Bool;
  equalTag a b =
    case a of {
      GBot ->
        case b of {
          GBot -> True;
          _ -> False
        };
      GBotK k ->
        case b of {
          GBotK l -> equalKind k l;
          _ -> False
        };
      GArr x y ->
        case b of {
          GArr z w -> ((x == z) && (y == w));
          _ -> False
        };
      GCon c xs ->
        case b of {
          GCon d ys -> (eqString c d && equalInts xs ys);
          _ -> False
        };
      GTyCon c k ->
        case b of {
          GTyCon d l -> (eqString c d && equalKind k l);
          _ -> False
        };
      GSkolem c k ->
        case b of {
          GSkolem d l -> ((c == d) && equalKind k l);
          _ -> False
        };
      GTyApp x y ->
        case b of {
          GTyApp z w -> ((x == z) && (y == w));
          _ -> False
        };
      GGen x ->
        case b of {
          GGen y -> (x == y);
          _ -> False
        }
    };
  equalNode :: Node -> Node -> Bool;
  equalNode (Node t b f) (Node u c h) = (equalTag t u && (equalMaybeInt b c && equalFlag f h));
  prettyKind :: Kind -> String;
  prettyKind kind =
    case kind of {
      Star -> "*";
      KArrow a b ->
        ((case a of {
            Star -> "*";
            KArrow x y -> ("(" ++ (prettyKind a ++ ")"))
          }) ++
         (" -> " ++ prettyKind b))
    };
  -- Graph unification diagnostics use the seed's derived Kind representation.
  kindDescription :: Kind -> String;
  kindDescription kind =
    case kind of {
      Star -> "Star";
      KArrow a b -> ("KArrow " ++ (kindArgumentDescription a ++ (" " ++ kindArgumentDescription b)))
    };
  kindArgumentDescription :: Kind -> String;
  kindArgumentDescription kind =
    case kind of {
      Star -> "Star";
      KArrow a b -> ("(" ++ (kindDescription kind ++ ")"))
    };
  applyKind :: Kind -> Kind -> Either String Kind;
  applyKind function argument =
    case function of {
      Star -> Left "invalid type constructor arity: a type of kind * cannot be applied";
      KArrow domain result ->
        if equalKind domain argument
        then Right result
        else Left
               ("kind mismatch: expected " ++
                (prettyKind domain ++ (", got " ++ prettyKind argument)))
    };
  mapMaybeInt :: (Int -> Int) -> Maybe Int -> Maybe Int;
  mapMaybeInt f value =
    case value of {
      Nothing -> Nothing;
      Just n -> Just (f n)
    };
  freshId :: Graph -> (,) Int Graph;
  freshId (Graph ns ls fresh) = (,) fresh (mkGraph ns ls (L.advanceIdentity fresh 1));
  resolve :: Graph -> Int -> Int;
  resolve graph identity =
    case IM.lookup identity (links graph) of {
      Nothing -> identity;
      Just representative -> resolve graph representative
    };
  nodeAt :: Graph -> Int -> Node;
  nodeAt graph identity =
    case IM.lookup (resolve graph identity) (nodes graph) of {
      Nothing -> panic ("missing graph node " ++ showInt identity);
      Just node -> node
    };
  require :: Graph -> Int -> Either String Node;
  require graph identity =
    case IM.lookup (resolve graph identity) (nodes graph) of {
      Nothing -> Left ("missing graph node " ++ showInt identity);
      Just node -> Right node
    };
  setNode :: Int -> Node -> Graph -> Graph;
  setNode identity node graph =
    mkGraph (insertNodeMap (resolve graph identity) node (nodes graph)) (links graph)
      (nextId graph);
  newNode :: GTag -> Maybe Int -> Flag -> Graph -> (,) Int Graph;
  newNode t b f graph =
    case freshId graph of {
      (,) identity next -> (,) identity (setNode identity (mkNode t b f) next)
    };
  children :: GTag -> [] Int;
  children t =
    case t of {
      GBot -> [];
      GBotK _ -> [];
      GArr a b -> (:) a ((:) b []);
      GCon c ns -> ns;
      GTyCon _ _ -> [];
      GSkolem _ _ -> [];
      GTyApp f a -> (:) f ((:) a []);
      GGen n -> (:) n []
    };
  mapTag :: (Int -> Int) -> GTag -> GTag;
  mapTag f t =
    case t of {
      GBot -> GBot;
      GBotK k -> GBotK k;
      GArr a b -> GArr (f a) (f b);
      GCon c ns -> GCon c (L.map f ns);
      GTyCon c k -> GTyCon c k;
      GSkolem n k -> GSkolem n k;
      GTyApp a b -> GTyApp (f a) (f b);
      GGen n -> GGen (f n)
    };
  bottomTag :: Kind -> GTag;
  bottomTag kind =
    case kind of {
      Star -> GBot;
      _ -> GBotK kind
    };
  isBottom :: GTag -> Bool;
  isBottom t =
    case t of {
      GBot -> True;
      GBotK _ -> True;
      _ -> False
    };
  isGen :: GTag -> Bool;
  isGen t =
    case t of {
      GGen _ -> True;
      _ -> False
    };
  genRoot :: Graph -> Int -> Int;
  genRoot graph identity =
    case tag (nodeAt graph identity) of {
      GGen root -> resolve graph root;
      _ -> panic "internal invariant: expected a generalization node"
    };
  -- A cache is shared across all roots, but only completed nodes are inserted.
  kindVisit :: Graph -> IntSet -> IntMap Kind -> Int -> Either String ((,) Kind (IntMap Kind));
  kindVisit graph path known original =
    let {
      identity = resolve graph original
    } in
    case IM.lookup identity known of {
      Just kind -> Right ((,) kind known);
      Nothing ->
        if IS.member identity path
        then Left "infinite type (occurs check)"
        else bindE (require graph identity)
               (\node ->
                  bindE (kindTag graph (IS.insert identity path) known (tag node))
                    (\answer ->
                       case answer of {
                         (,) kind cache -> Right ((,) kind (IM.insert identity kind cache))
                       }))
    };
  kindTag :: Graph -> IntSet -> IntMap Kind -> GTag -> Either String ((,) Kind (IntMap Kind));
  kindTag graph path known t =
    case t of {
      GBot -> Right ((,) Star known);
      GBotK k -> Right ((,) k known);
      GTyCon c k -> Right ((,) k known);
      GSkolem n k -> Right ((,) k known);
      GGen n -> kindVisit graph path known n;
      GArr a b ->
        bindE (kindVisit graph path known a)
          (\first ->
             case first of {
               (,) ka next ->
                 bindE (kindVisit graph path next b)
                   (\second ->
                      case second of {
                        (,) kb final ->
                          if (equalKind ka Star && equalKind kb Star)
                          then Right ((,) Star final)
                          else Left "function types require kind * arguments"
                      })
             });
      GCon c ns ->
        bindE
          (foldE
             (\cache ->
                \n ->
                  bindE (kindVisit graph path cache n)
                    (\answer ->
                       case answer of {
                         (,) kind next ->
                           if equalKind kind Star
                           then Right next
                           else Left "legacy type constructor has a non-* argument"
                       }))
             known
             ns)
          (\cache -> Right ((,) Star cache));
      GTyApp f a ->
        bindE (kindVisit graph path known f)
          (\first ->
             case first of {
               (,) kf next ->
                 bindE (kindVisit graph path next a)
                   (\second ->
                      case second of {
                        (,) ka final -> bindE (applyKind kf ka) (\kind -> Right ((,) kind final))
                      })
             })
    };
  kindsAt :: Graph -> [] Int -> Either String (IntMap Kind);
  kindsAt graph starts =
    foldE
      (\known ->
         \identity ->
           bindE (kindVisit graph IS.empty known identity)
             (\answer ->
                case answer of {
                  (,) kind cache -> Right cache
                }))
      IM.empty
      starts;
  kindAt :: Graph -> Int -> Either String Kind;
  kindAt graph start =
    bindE (kindVisit graph IS.empty IM.empty start)
      (\answer ->
         case answer of {
           (,) kind cache -> Right kind
         });
  reachableVisit :: Graph -> IntSet -> [] Int -> IntSet;
  reachableVisit graph seen pending =
    case pending of {
      [] -> seen;
      (:) original rest ->
        let {
          identity = resolve graph original
        } in
        if IS.member identity seen
        then reachableVisit graph seen rest
        else reachableVisit graph (IS.insert identity seen)
               (L.append (children (tag (nodeAt graph identity))) rest)
    };
  reachable :: Graph -> Int -> IntSet;
  reachable graph start = reachableVisit graph IS.empty ((:) start []);
  -- Validation asks about one node. Match the seed's visited search, stopping
  -- at the first successful path instead of materializing every descendant.
  containsVisit :: Graph -> Int -> IntSet -> [] Int -> Bool;
  containsVisit graph wanted seen pending =
    case pending of {
      [] -> False;
      (:) original rest ->
        let {
          identity = resolve graph original
        } in
        if (identity == wanted)
        then True
        else if IS.member identity seen
             then containsVisit graph wanted seen rest
             else containsVisit graph wanted (IS.insert identity seen)
                    (L.append (children (tag (nodeAt graph identity))) rest)
    };
  structurallyContains :: Graph -> Int -> Int -> Bool;
  structurallyContains graph parent target =
    containsVisit graph (resolve graph target) IS.empty ((:) parent []);
  underBinderStep :: Graph -> Int -> Maybe Int -> Bool;
  underBinderStep graph wanted current =
    case current of {
      Nothing -> False;
      Just parent ->
        if (resolve graph parent == wanted)
        then True
        else underBinderStep graph wanted (binder (nodeAt graph parent))
    };
  underBinder :: Graph -> Int -> Int -> Bool;
  underBinder graph identity ancestor =
    underBinderStep graph (resolve graph ancestor) (binder (nodeAt graph identity));
  bindingChildrenMap :: Graph -> IntMap ([] Int);
  bindingChildrenMap graph =
    L.foldlStrict
      (\table ->
         \entry ->
           case entry of {
             (,) n v ->
               case binder v of {
                 Nothing -> table;
                 Just parent ->
                   let {
                     previous = IM.findWithDefault [] parent table
                   } in
                   seq previous (IM.insert parent ((:) n previous) table)
               }
           })
      IM.empty
      (IM.toList (nodes graph));
  inertVisit :: Graph -> IntMap ([] Int) -> IntMap Bool -> Int -> (,) Bool (IntMap Bool);
  -- A bottom is never inert. Match the seed's short-circuiting conjunction:
  -- even constructing the binding index is unnecessary for this query.
  inertVisit graph descendants known identity =
    case IM.lookup identity known of {
      Just answer -> (,) answer known;
      Nothing ->
        if isBottom (tag (nodeAt graph identity))
        then strictPair False (IM.insert identity False known)
        else let {
               flexibleChildren =
                 L.filter (\child -> equalFlag (flag (nodeAt graph child)) Flexible)
                   (IM.findWithDefault [] identity descendants)
             } in
             case L.foldlStrict
                    (\state ->
                       \child ->
                         case state of {
                           (,) answer cache ->
                             if answer
                             then case inertVisit graph descendants cache child of {
                                    (,) childAnswer next -> strictPair childAnswer next
                                  }
                             else state
                         })
                    ((,) True known)
                    flexibleChildren of {
               (,) answer cache -> strictPair answer (IM.insert identity answer cache)
             }
    };
  inertNodes :: Graph -> IntMap Bool;
  inertNodes graph =
    let {
      descendants = bindingChildrenMap graph
    } in
    L.foldlStrict
      (\known ->
         \n ->
           case inertVisit graph descendants known n of {
             (,) answer cache -> cache
           })
      IM.empty
      (IM.keys (nodes graph));
  inert :: Graph -> Int -> Bool;
  inert graph original =
    case inertVisit graph (bindingChildrenMap graph) IM.empty (resolve graph original) of {
      (,) answer known -> answer
    };
  flexiblePath :: Graph -> Int -> Bool;
  flexiblePath graph identity =
    case nodeAt graph identity of {
      Node (GGen root) b f -> True;
      Node t b Rigid -> False;
      Node t b Flexible ->
        case b of {
          Nothing -> True;
          Just parent -> flexiblePath graph parent
        }
    };
  flexiblePathVisit :: Graph -> IntMap Bool -> Int -> (,) Bool (IntMap Bool);
  flexiblePathVisit graph known identity =
    case IM.lookup identity known of {
      Just answer -> (,) answer known;
      Nothing ->
        let {
          answer =
            case nodeAt graph identity of {
              Node (GGen root) b f -> (,) True known;
              Node t b Rigid -> (,) False known;
              Node t b Flexible ->
                case b of {
                  Nothing -> (,) True known;
                  Just parent -> flexiblePathVisit graph known parent
                }
            }
        } in
        case answer of {
          (,) value cache -> strictPair value (IM.insert identity value cache)
        }
    };
  permissions :: Graph -> IntMap Permission;
  permissions graph =
    let {
      inertness = inertNodes graph
    } in
    let {
      paths =
        L.foldlStrict
          (\known ->
             \n ->
               case flexiblePathVisit graph known n of {
                 (,) answer cache -> cache
               })
          IM.empty
          (IM.keys (nodes graph))
    } in
    IM.mapWithKey
      (\n ->
         \v ->
           if IM.findWithDefault False n inertness
           then Inert
           else if equalFlag (flag v) Rigid
                then Orange
                else if IM.findWithDefault False n paths then Green else Red)
      (nodes graph);
  permission :: Graph -> Int -> Permission;
  permission graph identity =
    if inert graph identity
    then Inert
    else if equalFlag (flag (nodeAt graph identity)) Rigid
         then Orange
         else if flexiblePath graph identity then Green else Red;
  -- Validating the binding tree before using ancestry makes sparse identities
  -- and disconnected cycles as safe as dense source-generated graphs.
  bindingVisitIndexed :: IntMap ([] Int) ->
                         Int ->
                         (,) Int (IntMap ((,) Int Int)) -> (,) Int (IntMap ((,) Int Int));
  bindingVisitIndexed descendants identity state =
    case state of {
      (,) start known ->
        case L.foldlStrict (\current -> \n -> bindingVisitIndexed descendants n current)
               (strictPair (start + 1) known)
               (IM.findWithDefault [] identity descendants) of {
          (,) end final -> strictPair end (IM.insert identity (strictPair start end) final)
        }
    };
  bindingVisit :: Graph ->
                  Int -> (,) Int (IntMap ((,) Int Int)) -> (,) Int (IntMap ((,) Int Int));
  bindingVisit graph identity state = bindingVisitIndexed (bindingChildrenMap graph) identity state;
  bindingIntervals :: Graph -> Either String (IntMap ((,) Int Int));
  bindingIntervals graph =
    let {
      roots =
        L.filter
          (\entry ->
             case entry of {
               (,) n v -> equalMaybeInt (binder v) Nothing
             })
          (IM.toList (nodes graph))
    } in
    case roots of {
      (:) ((,) root node) [] ->
        bindE
          (mapE_
             (\entry ->
                case entry of {
                  (,) n v ->
                    case binder v of {
                      Nothing -> Right ();
                      Just b -> check (IM.member b (nodes graph)) "missing binder"
                    }
                })
             (IM.toList (nodes graph)))
          (\ignored ->
             case bindingVisit graph root ((,) 0 IM.empty) of {
               (,) count intervals ->
                 if (count == IM.size (nodes graph))
                 then Right intervals
                 else Left "cyclic binding tree"
             });
      _ -> Left "graph must have one binding root"
    };
  intervalContains :: IntMap ((,) Int Int) -> Int -> Int -> Bool;
  intervalContains intervals ancestor identity =
    case IM.lookup ancestor intervals of {
      Nothing -> False;
      Just ((,) start end) ->
        case IM.lookup identity intervals of {
          Nothing -> False;
          Just ((,) position ignored) -> ((start <= position) && (position < end))
        }
    };
  validateNodeBinder :: Graph -> (,) Int Node -> Either String ();
  validateNodeBinder graph ((,) identity node) =
    case binder node of {
      Nothing -> check (isGen (tag node)) "binding root must be a gen node";
      Just parent ->
        bindE (require graph parent)
          (\p ->
             if (isGen (tag p) ||
                 L.any (\child -> (resolve graph child == identity)) (children (tag p)))
             then Right ()
             else check (structurallyContains graph parent identity)
                    "a type binder must structurally contain its node")
    };
  validateChild :: Graph -> IntMap ((,) Int Int) -> Int -> Int -> Either String ();
  validateChild graph intervals parent child =
    bindE (require graph child)
      (\node ->
         if isGen (tag node)
         then Left "gen nodes cannot be structural children"
         else case binder node of {
                Nothing -> Left "structural child has no binder";
                Just b -> check (intervalContains intervals b parent) "ill-dominated type graph"
              });
  validateEdges :: Graph -> IntMap ((,) Int Int) -> (,) Int Node -> Either String ();
  validateEdges graph intervals ((,) identity node) =
    if (isGen (tag node) && L.not (equalFlag (flag node) Flexible))
    then Left "gen nodes must be flexible"
    else bindE (mapE_ (validateChild graph intervals identity) (children (tag node)))
           (\ignored -> Right ());
  -- A bounded span keeps local scratch storage proportional to the graph even
  -- when public graph identities span the full signed 64-bit domain.
  denseDisjoint :: forall a b. IntMap a -> IntMap b -> Bool;
  denseDisjoint left right =
    case left of {
      IntMap leftTree ->
        case right of {
          IntMap rightTree ->
            if (IM.size left <= IM.size right)
            then denseNoKeys leftTree rightTree
            else denseNoKeys rightTree leftTree
        }
    };
  denseNoKeys :: forall a b. IntMapTree a -> IntMapTree b -> Bool;
  denseNoKeys smaller larger =
    case smaller of {
      IntMapNil -> True;
      IntMapTip key value -> L.not (IM.memberTree key larger);
      IntMapBin count prefix left right -> denseNoKeys left larger && denseNoKeys right larger
    };
  denseBounds :: Graph -> Maybe ((,) Int Int);
  denseBounds graph =
    case IM.lookupMin (nodes graph) of {
      Nothing -> Nothing;
      Just ((,) low first) ->
        case IM.lookupMax (nodes graph) of {
          Nothing -> Nothing;
          Just ((,) high last) ->
            -- A mathematical span of at least 2^63 wraps negative. It cannot
            -- qualify for bounded scratch storage, even when the keys fit.
            if (((high - low) >= 0) && ((high - low) <= (8 * IM.size (nodes graph))) &&
                denseDisjoint (nodes graph) (links graph))
            then Just ((,) low high)
            else Nothing
        }
    };
  readDense :: forall s a. Int -> STArray s a -> Int -> ST s a;
  readDense low array identity = readSTArray array (identity - low);
  writeDense :: forall s a. Int -> STArray s a -> Int -> a -> ST s ();
  writeDense low array identity value = writeSTArray array (identity - low) value;
  -- The seed uses unboxed scratch integers. Keep that demand explicit while
  -- the general STArray facility correctly retains lazy arbitrary element types.
  writeDenseInt :: forall s. Int -> STArray s Int -> Int -> Int -> ST s ();
  writeDenseInt low array identity value = seq value (writeDense low array identity value);
  validateGraph :: Graph -> Either String ();
  validateGraph graph =
    case denseBounds graph of {
      Nothing -> validateSparse graph;
      Just ((,) low high) -> validateDense graph low high
    };
  data DenseValidation s =
    DenseValidation Graph Int Int (STArray s (Maybe Node)) (STArray s ([] Int)) (STArray s
                                                                                   Int) (STArray s
                                                                                         Kind) (STArray
                                                                                                s
                                                                                                Int) (STArray
                                                                                                      s
                                                                                                      Int) (STArray
                                                                                                            s
                                                                                                            Int);
  validateDense :: Graph -> Int -> Int -> Either String ();
  validateDense graph low high = runST (denseValidation graph low high);
  denseValidation :: forall s. Graph -> Int -> Int -> ST s (Either String ());
  denseValidation graph low high =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count Nothing)
      (\table ->
         stBind (newSTArray count [])
           (\descendants ->
              stBind (newSTArray count 0)
                (\colours ->
                   stBind (newSTArray count Star)
                     (\kinds ->
                        stBind (newSTArray count (0 - 1))
                          (\starts ->
                             stBind (newSTArray count (0 - 1))
                               (\ends ->
                                  stBind (newSTArray count (0 - 1))
                                    (\visited ->
                                       let {
                                         state =
                                           DenseValidation graph low high table descendants colours
                                             kinds
                                             starts
                                             ends
                                             visited
                                       } in
                                       let {
                                         entries = IM.toList (nodes graph)
                                       } in
                                       stBind (denseLoadValidation low table entries)
                                         (\loaded -> denseValidateEntries state entries))))))));
  denseGetNode :: forall s. DenseValidation s -> Int -> ST s (Maybe Node);
  denseGetNode (DenseValidation graph low high table descendants colours kinds starts ends visited) n =
    if ((n < low) || (high < n)) then stReturn Nothing else readDense low table n;
  denseRequire :: forall s. DenseValidation s -> Int -> ST s (Either String Node);
  denseRequire state n =
    stBind (denseGetNode state n)
      (\answer ->
         case answer of {
           Nothing -> ST.failE ("missing graph node " ++ showInt n);
           Just value -> ST.pureE value
         });
  denseCheckBinder :: forall s. DenseValidation s -> (,) Int Node -> ST s (Either String ());
  denseCheckBinder state ((,) n v) =
    case binder v of {
      Nothing -> ST.pureE ();
      Just b ->
        stBind (denseGetNode state b)
          (\answer ->
             case answer of {
               Nothing -> ST.failE "missing binder";
               Just ignored -> ST.pureE ()
             })
    };
  denseAddDescendant :: forall s. DenseValidation s -> (,) Int Node -> ST s ();
  denseAddDescendant (DenseValidation graph low high table descendants colours kinds starts ends visited) ((,) n v) =
    case binder v of {
      Nothing -> stReturn ();
      Just b ->
        stBind (readDense low descendants b)
          (\previous -> writeDense low descendants b ((:) n previous))
    };
  denseBindingVisit :: forall s. DenseValidation s -> Int -> Int -> ST s Int;
  denseBindingVisit state n position =
    case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited ->
        stBind (writeDenseInt low starts n position)
          (\ignored ->
             stBind (readDense low descendants n)
               (\children ->
                  stBind (denseBindingChildren state (position + 1) children)
                    (\end -> stBind (writeDenseInt low ends n end) (\written -> stReturn end))))
    };
  denseContains :: forall s. DenseValidation s -> Int -> Int -> ST s Bool;
  denseContains (DenseValidation graph low high table descendants colours kinds starts ends visited) ancestor n =
    stBind (readDense low starts ancestor)
      (\a ->
         stBind (readDense low ends ancestor)
           (\b -> stBind (readDense low starts n) (\p -> stReturn ((a <= p) && (p < b)))));
  denseStructurally :: forall s. DenseValidation s ->
                                 Int -> Int -> [] Int -> ST s (Either String Bool);
  denseStructurally state wanted stamp pending =
    case pending of {
      [] -> ST.pureE False;
      (:) original rest ->
        case state of {
          DenseValidation graph low high table descendants colours kinds starts ends visited ->
            let {
              n = resolve graph original
            } in
            if (n == wanted)
            then ST.pureE True
            else ST.bindE (denseRequire state n)
                   (\v ->
                      stBind (readDense low visited n)
                        (\mark ->
                           if (mark == stamp)
                           then denseStructurally state wanted stamp rest
                           else stBind (writeDenseInt low visited n stamp)
                                  (\written ->
                                     denseStructurally state wanted stamp
                                       (L.append (children (tag v)) rest))))
        }
    };
  denseValidateEntries :: forall s. DenseValidation s ->
                                    [] ((,) Int Node) -> ST s (Either String ());
  denseValidateEntries state entries =
    case L.filter
           (\entry ->
              case entry of {
                (,) n v ->
                  case binder v of {
                    Nothing -> True;
                    Just ignored -> False
                  }
              })
           entries of {
      (:) ((,) root value) [] ->
        ST.bindE (denseCheckBinders state entries)
          (\binders ->
             stBind (denseAddDescendants state entries)
               (\loaded ->
                  stBind (denseBindingVisit state root 0)
                    (\count ->
                       if (count == L.length entries)
                       then denseKindEntries state entries
                       else ST.failE "cyclic binding tree")));
      _ -> ST.failE "graph must have one binding root"
    };
  -- Each structural edge is checked even if the child's kind is already cached.
  denseChild :: forall s. DenseValidation s -> Int -> Int -> ST s (Either String Kind);
  denseChild state parent original =
    case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited ->
        let {
          n = resolve graph original
        } in
        ST.bindE (denseRequire state n)
          (\v ->
             if isGen (tag v)
             then ST.failE "gen nodes cannot be structural children"
             else case binder v of {
                    Nothing -> ST.failE "structural child has no binder";
                    Just b ->
                      stBind (denseContains state b parent)
                        (\dominated ->
                           if dominated
                           then denseKind state n v
                           else ST.failE "ill-dominated type graph")
                  })
    };
  denseKindBinder :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String ());
  denseKindBinder state n v =
    case binder v of {
      Nothing -> ST.check (isGen (tag v)) "binding root must be a gen node";
      Just b ->
        ST.bindE (denseRequire state b)
          (\parent ->
             if isGen (tag parent)
             then ST.pureE ()
             else case state of {
                    DenseValidation graph low high table descendants colours kinds starts ends visited ->
                      if L.any (\child -> (resolve graph child == n)) (children (tag parent))
                      then ST.pureE ()
                      else stBind (readDense low starts n)
                             (\stamp ->
                                ST.bindE (denseStructurally state n stamp ((:) b []))
                                  (\found ->
                                     ST.check found
                                       "a type binder must structurally contain its node"))
                  })
    };
  denseKind :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String Kind);
  denseKind state n v =
    case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited ->
        stBind (readDense low colours n)
          (\colour ->
             if (colour == 1)
             then ST.failE "infinite type (occurs check)"
             else if (colour == 2)
                  then ST.liftE (readDense low kinds n)
                  else stBind (writeDenseInt low colours n 1)
                         (\active ->
                            ST.bindE (denseKindBinder state n v)
                              (\bound ->
                                 ST.bindE (denseTagKind state n v)
                                   (\kind ->
                                      stBind (writeDense low kinds n kind)
                                        (\stored ->
                                           stBind (writeDenseInt low colours n 2)
                                             (\complete -> ST.pureE kind))))))
    };
  denseTagKind :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String Kind);
  denseTagKind state n v =
    case tag v of {
      GBot -> ST.pureE Star;
      GBotK kind -> ST.pureE kind;
      GTyCon name kind -> ST.pureE kind;
      GSkolem identity kind -> ST.pureE kind;
      GGen child ->
        if equalFlag (flag v) Flexible
        then denseChild state n child
        else ST.failE "gen nodes must be flexible";
      GArr a b ->
        ST.bindE (denseChild state n a)
          (\ka ->
             ST.bindE (denseChild state n b)
               (\kb ->
                  if (equalKind ka Star && equalKind kb Star)
                  then ST.pureE Star
                  else ST.failE "function types require kind * arguments"));
      GCon name children ->
        ST.bindE (denseChildKinds state n children)
          (\kinds ->
             if L.all (\kind -> equalKind kind Star) kinds
             then ST.pureE Star
             else ST.failE "legacy type constructor has a non-* argument");
      GTyApp function argument ->
        ST.bindE (denseChild state n function)
          (\kf -> ST.bindE (denseChild state n argument) (\ka -> stReturn (applyKind kf ka)))
    };
  validateSparse :: Graph -> Either String ();
  validateSparse graph =
    bindE (kindsAt graph (IM.keys (nodes graph)))
      (\kinds ->
         bindE (bindingIntervals graph)
           (\intervals ->
              bindE (mapE_ (validateNodeBinder graph) (IM.toList (nodes graph)))
                (\ignored ->
                   bindE (mapE_ (validateEdges graph intervals) (IM.toList (nodes graph)))
                     (\ignored2 -> Right ()))));
  tagDescription :: GTag -> String;
  tagDescription t =
    case t of {
      GBot -> "Bot";
      GBotK kind -> ("BotK (" ++ (prettyKind kind ++ ")"));
      GArr a b -> ("Arr " ++ (showInt a ++ (" " ++ showInt b)));
      GCon name arguments ->
        ("Con \"" ++ (name ++ ("\" [" ++ (L.intercalate "," (L.map showInt arguments) ++ "]"))));
      GTyCon name kind -> ("TyCon \"" ++ (name ++ ("\" (" ++ (prettyKind kind ++ ")"))));
      GSkolem identity kind ->
        ("Skolem " ++ (showInt identity ++ (" (" ++ (prettyKind kind ++ ")"))));
      GTyApp f a -> ("TyApp " ++ (showInt f ++ (" " ++ showInt a)));
      GGen n -> ("Gen " ++ showInt n)
    };
  typeMismatch :: GTag -> GTag -> Either String ((,) GTag ([] ((,) Int Int)));
  typeMismatch a b =
    Left ("type constructor mismatch: " ++ (tagDescription a ++ (" versus " ++ tagDescription b)));
  tagEquations :: GTag -> GTag -> Either String ((,) GTag ([] ((,) Int Int)));
  tagEquations a b =
    if (isGen a || isGen b)
    then Left "cannot unify generalization nodes"
    else if isBottom a
         then Right ((,) b [])
         else if isBottom b
              then Right ((,) a [])
              else case a of {
                     GArr x y ->
                       case b of {
                         GArr z w -> Right ((,) a ((:) ((,) x z) ((:) ((,) y w) [])));
                         _ -> typeMismatch a b
                       };
                     GCon c xs ->
                       case b of {
                         GCon d ys ->
                           if (eqString c d && (L.length xs == L.length ys))
                           then Right ((,) a (L.zip xs ys))
                           else typeMismatch a b;
                         _ -> typeMismatch a b
                       };
                     GTyCon c k ->
                       case b of {
                         GTyCon d l ->
                           if (eqString c d && equalKind k l)
                           then Right ((,) a [])
                           else typeMismatch a b;
                         _ -> typeMismatch a b
                       };
                     GSkolem c k ->
                       case b of {
                         GSkolem d l ->
                           if ((c == d) && equalKind k l)
                           then Right ((,) a [])
                           else typeMismatch a b;
                         _ -> typeMismatch a b
                       };
                     GTyApp f x ->
                       case b of {
                         GTyApp h y -> Right ((,) a ((:) ((,) f h) ((:) ((,) x y) [])));
                         _ -> typeMismatch a b
                       };
                     _ -> typeMismatch a b
                   };
  firstOrder :: IntMap Kind -> Graph -> (,) Int Int -> Either String Graph;
  firstOrder kinds graph ((,) left right) =
    let {
      a = resolve graph left
    } in
    let {
      b = resolve graph right
    } in
    if (a == b)
    then Right graph
    else case IM.lookup a kinds of {
           Nothing -> Left "missing unification kind";
           Just ka ->
             case IM.lookup b kinds of {
               Nothing -> Left "missing unification kind";
               Just kb ->
                 if L.not (equalKind ka kb)
                 then Left
                        ("kind mismatch during unification: " ++
                         (kindDescription ka ++ (" versus " ++ kindDescription kb)))
                 else bindE (tagEquations (tag (nodeAt graph a)) (tag (nodeAt graph b)))
                        (\answer ->
                           case answer of {
                             (,) newTag equations ->
                               let {
                                 winner = if (a < b) then a else b
                               } in
                               let {
                                 loser = if (a < b) then b else a
                               } in
                               let {
                                 old = nodeAt graph a
                               } in
                               let {
                                 next =
                                   mkGraph
                                     (insertNodeMap winner (mkNode newTag (binder old) (flag old))
                                        (IM.delete loser (nodes graph)))
                                     (IM.insert loser winner (links graph))
                                     (nextId graph)
                               } in
                               foldE (firstOrder kinds) next equations
                           })
             }
         };
  canonicalize :: Graph -> Graph;
  canonicalize graph =
    mkGraph
      (mapNodes (\node -> mkNode (mapTag (resolve graph) (tag node)) (binder node) (flag node))
         (nodes graph))
      (links graph)
      (nextId graph);
  equationNodes :: (,) Int Int -> [] Int;
  equationNodes ((,) a b) = (:) a ((:) b []);
  -- This query is used only after complete validation, on an alias-free graph
  -- whose distinct ascending enumeration agrees with ordered-map lookup.
  -- Validation already establishes the *-kind premises of arrows and legacy
  -- constructors. Higher-kinded nodes, Gen roots and applications retain their
  -- explicit kinds. Type-application graphs keep the existing shared kind cache,
  -- avoiding repeated traversal of shared higher-kinded subgraphs.
  validatedKind :: Graph -> Int -> Either String Kind;
  validatedKind graph identity =
    bindE (require graph identity)
      (\node ->
         case tag node of {
           GBot -> Right Star;
           GBotK kind -> Right kind;
           GTyCon name kind -> Right kind;
           GSkolem identity kind -> Right kind;
           GArr a b -> Right Star;
           GCon name arguments -> Right Star;
           GGen root -> validatedKind graph root;
           GTyApp function argument -> kindAt graph identity
         });
  simpleKindTag :: Node -> Bool;
  simpleKindTag node =
    case tag node of {
      GTyApp function argument -> False;
      _ -> True
    };
  orderedSimpleKinds :: [] ((,) Int Node) -> Bool;
  orderedSimpleKinds entries =
    case entries of {
      [] -> True;
      (:) ((,) first node) rest -> (simpleKindTag node && orderedSimpleKindsAfter first rest)
    };
  orderedSimpleKindsAfter :: Int -> [] ((,) Int Node) -> Bool;
  orderedSimpleKindsAfter previous entries =
    case entries of {
      [] -> True;
      (:) ((,) next node) rest ->
        ((previous < next) && (simpleKindTag node && orderedSimpleKindsAfter next rest))
    };
  -- Signed-order payload traversal plus a linear proof of every routing edge.
  -- This replaces the temporary ascending-entry list and also rejects forged
  -- prefixes whose sorted leaves would otherwise hide a missing-child error.
  simpleKindTree :: IntMapTree Node -> Bool;
  simpleKindTree tree = case tree of {
    IntMapNil -> True;
    IntMapTip key node -> simpleKindTag node;
    IntMapBin count prefix left right ->
      let { reversed = IT.signBranch prefix;
            first = if reversed then right else left;
            second = if reversed then left else right } in
      prefix /= 0 && IM.childRouting (L.not reversed) prefix first && simpleKindTree first &&
      IM.childRouting reversed prefix second && simpleKindTree second
  };
  simpleKinds :: IntMap Node -> Bool;
  simpleKinds (IntMap tree) = simpleKindTree tree;
  firstOrderValidated :: Graph -> Graph -> (,) Int Int -> Either String Graph;
  firstOrderValidated original graph ((,) left right) =
    let {
      a = resolve graph left
    } in
    let {
      b = resolve graph right
    } in
    if (a == b)
    then Right graph
    else bindE (validatedKind original a)
           (\ka ->
              bindE (validatedKind original b)
                (\kb ->
                   if L.not (equalKind ka kb)
                   then Left
                          ("kind mismatch during unification: " ++
                           (kindDescription ka ++ (" versus " ++ kindDescription kb)))
                   else bindE (tagEquations (tag (nodeAt graph a)) (tag (nodeAt graph b)))
                          (\answer ->
                             case answer of {
                               (,) newTag equations ->
                                 let {
                                   winner = if (a < b) then a else b
                                 } in
                                 let {
                                   loser = if (a < b) then b else a
                                 } in
                                 let {
                                   old = nodeAt graph a
                                 } in
                                 let {
                                   next =
                                     mkGraph
                                       (insertNodeMap winner (mkNode newTag (binder old) (flag old))
                                          (IM.delete loser (nodes graph)))
                                       (IM.insert loser winner (links graph))
                                       (nextId graph)
                                 } in
                                 foldE (firstOrderValidated original) next equations
                             })));
  checkedFirstOrder :: [] ((,) Int Int) -> Graph -> Either String Graph;
  -- The preceding eager kind traversal checks every input identity before
  -- any merge. Preserve that error priority even when an earlier pair would
  -- fail constructor/kind equality. All structural premises were validated.
  checkedFirstOrder equations before =
    if (IM.null (links before) && simpleKinds (nodes before))
    then bindE
           (mapE_ (\n -> bindE (require before n) (\ignored -> Right ()))
              (L.concatMap equationNodes equations))
           (\checked -> foldE (firstOrderValidated before) before equations)
    else bindE (kindsAt before (L.concatMap equationNodes equations))
           (\kinds -> foldE (firstOrder kinds) before equations);
  unify :: [] ((,) Int Int) -> Graph -> Either String Graph;
  unify equations before =
    bindE (validateGraph before)
      (\ignored ->
         bindE (checkedFirstOrder equations before)
           (\skeleton ->
              bindE (rebind before (canonicalize skeleton))
                (\rebuilt -> bindE (validateGraph rebuilt) (\verified -> Right rebuilt))));
  graftedNodes :: Graph -> Graph -> IntSet;
  graftedNodes old skeleton =
    L.foldlStrict
      (\seen ->
         \entry ->
           case entry of {
             (,) n v ->
               if isBottom (tag v)
               then reachableVisit skeleton seen (children (tag (nodeAt skeleton n)))
               else seen
           })
      IS.empty
      (IM.toList (nodes old));
  classesIndex :: Graph -> Graph -> IntMap ([] Int);
  classesIndex old skeleton =
    L.foldlStrict
      (\classes -> \n -> IM.insertWith L.append (resolve skeleton n) ((:) n []) classes)
      IM.empty
      (IM.keys (nodes old));
  parentsIndex :: Graph -> IntMap IntSet;
  parentsIndex graph =
    L.foldlStrict
      (\index ->
         \entry ->
           case entry of {
             (,) parent node ->
               L.foldlStrict
                 (\known ->
                    \child ->
                      let {
                        identity = resolve graph child
                      } in
                      let {
                        parents = IS.insert parent (IM.findWithDefault IS.empty identity known)
                      } in
                      seq parents (IM.insert identity parents known))
                 index
                 (children (tag node))
           })
      IM.empty
      (IM.toList (nodes graph));
  flagsIndex :: Graph -> IntMap ([] Int) -> IntMap Flag;
  flagsIndex old classes =
    IM.map
      (\members ->
         if L.any (\n -> equalFlag (flag (nodeAt old n)) Rigid) members then Rigid else Flexible)
      classes;
  candidateIndex :: Graph ->
                    Graph -> IntMap ([] Int) -> IntMap IntSet -> IntSet -> IntMap ([] Int);
  candidateIndex old skeleton classes parents grafted =
    IM.mapWithKey
      (\n ->
         \members ->
           let {
             originalParents =
               L.foldlStrict
                 (\seen ->
                    \member ->
                      case binder (nodeAt old member) of {
                        Nothing -> seen;
                        Just b -> IS.insert (resolve skeleton b) seen
                      })
                 IS.empty
                 members
           } in
           IS.toList
             (if IS.member n grafted
              then IS.union originalParents (IM.findWithDefault IS.empty n parents)
              else originalParents))
      classes;
  bindingPath :: IntMap (Maybe Int) -> Int -> [] Int;
  bindingPath tree identity =
    case IM.lookup identity tree of {
      Nothing -> (:) identity [];
      Just Nothing -> (:) identity [];
      Just (Just parent) -> (:) identity (bindingPath tree parent)
    };
  commonAncestor :: IntMap (Maybe Int) -> [] Int -> Either String (Maybe Int);
  commonAncestor tree candidates =
    case candidates of {
      [] -> Right Nothing;
      (:) first rest ->
        case L.find
               (\candidate ->
                  L.all
                    (\other ->
                       L.any (\ancestor -> (ancestor == candidate)) (bindingPath tree other))
                    rest)
               (bindingPath tree first) of {
          Nothing -> Left "binders have no common ancestor";
          Just ancestor -> Right (Just ancestor)
        }
    };
  buildBindingTree :: IntMap ([] Int) ->
                      IntMap ([] Int) ->
                      Int ->
                      IntMap (Maybe Int) ->
                      IntMap Int -> IntSet -> Either String (IntMap (Maybe Int));
  buildBindingTree candidates dependents total tree counts ready =
    case IS.minView ready of {
      Nothing ->
        if (IM.size tree == total)
        then Right tree
        else Left "cyclic structure/binding dependencies";
      Just ((,) identity remaining) ->
        bindE (commonAncestor tree (IM.findWithDefault [] identity candidates))
          (\parent ->
             case L.foldlStrict releaseDependency ((,) counts remaining)
                    (IM.findWithDefault [] identity dependents) of {
               (,) nextCounts nextReady ->
                 buildBindingTree candidates dependents total (IM.insert identity parent tree)
                   nextCounts
                   nextReady
             })
    };
  releaseDependency :: (,) (IntMap Int) IntSet -> Int -> (,) (IntMap Int) IntSet;
  releaseDependency ((,) counts ready) child =
    let {
      count = (IM.get child counts - 1)
    } in
    strictPair (IM.insert child count counts)
      (if (count == 0) then IS.insert child ready else ready);
  rebuildBinders :: IntMap ([] Int) -> IntMap IntSet -> Either String (IntMap (Maybe Int));
  rebuildBinders candidates dependencies =
    let {
      counts = IM.map IS.size dependencies
    } in
    let {
      ready = IS.fromList (IM.keys (IM.filter (\n -> (n == 0)) counts))
    } in
    let {
      dependents =
        L.foldlStrict
          (\index ->
             \entry ->
               case entry of {
                 (,) n ds ->
                   L.foldlStrict
                     (\known -> \dependency -> IM.insertWith L.append dependency ((:) n []) known)
                     index
                     (IS.toList ds)
               })
          IM.empty
          (IM.toList dependencies)
    } in
    buildBindingTree candidates dependents (IM.size candidates) IM.empty counts ready;
  raisedBinderClimb :: Graph -> Graph -> Int -> Maybe Int -> Either String (Maybe Int);
  raisedBinderClimb old skeleton wanted current =
    case current of {
      Nothing -> Left "a node's binder cannot be lowered";
      Just parent ->
        if (resolve skeleton parent == wanted)
        then Right (Just parent)
        else raisedBinderClimb old skeleton wanted (binder (nodeAt old parent))
    };
  raisedBinder :: Graph ->
                  Graph ->
                  IntMap (Maybe Int) -> (,) Int Node -> Either String ((,) Int (Maybe Int));
  raisedBinder old skeleton tree ((,) n v) =
    case IM.lookup (resolve skeleton n) tree of {
      Nothing -> Left "missing rebuilt binder";
      Just Nothing -> Right ((,) n Nothing);
      Just (Just wanted) ->
        bindE (raisedBinderClimb old skeleton wanted (binder v)) (\parent -> Right ((,) n parent))
    };
  checkOriginalPermission :: Graph ->
                             IntMap Permission ->
                             IntMap Permission ->
                             IntMap Flag ->
                             IntMap (Maybe Int) -> (,) Int Node -> Either String ();
  checkOriginalPermission skeleton oldPermissions raisedPermissions newFlags up ((,) identity node) =
    let {
      oldPermission = IM.get identity oldPermissions
    } in
    let {
      raisedPermission = IM.get identity raisedPermissions
    } in
    let {
      image = resolve skeleton identity
    } in
    let {
      lifted = IM.findWithDefault Nothing identity up
    } in
    if (isBottom (tag node) &&
        (L.not (isBottom (tag (nodeAt skeleton identity))) &&
         L.not (equalPermission oldPermission Green)))
    then Left "cannot instantiate a rigid or protected type variable"
    else if (equalPermission oldPermission Red && L.not (equalMaybeInt (binder node) lifted))
         then Left "cannot raise a protected type variable"
         else if (equalPermission raisedPermission Red &&
                  L.not (equalFlag (flag node) (IM.get image newFlags)))
              then Left "cannot weaken a protected type variable"
              else Right ();
  checkMergePairs :: IntMap Permission -> IntMap (Maybe Int) -> [] Int -> Either String ();
  checkMergePairs raisedPermissions up members =
    case members of {
      [] -> Right ();
      (:) first rest ->
        bindE
          (mapE_
             (\other ->
                if (equalMaybeInt (IM.findWithDefault Nothing first up)
                      (IM.findWithDefault Nothing other up) &&
                    (equalPermission (IM.get first raisedPermissions) Red ||
                     equalPermission (IM.get other raisedPermissions) Red))
                then Left "cannot merge distinct protected type variables"
                else Right ())
             rest)
          (\ignored -> checkMergePairs raisedPermissions up rest)
    };
  rebind :: Graph -> Graph -> Either String Graph;
  rebind old skeleton =
    case denseBounds old of {
      Nothing -> rebindSparse old skeleton;
      Just ((,) low high) -> rebindDense old skeleton low high
    };
  -- All tables share an offset. Graph identities themselves remain arbitrary
  -- precision; the dense guard limits only the number of allocated cells.
  data DenseRebinding s =
    DenseRebinding Graph Graph Int Int (STArray s (Maybe Node)) (STArray s (Maybe Node)) (STArray s
                                                                                          Int) (STArray
                                                                                                s
                                                                                                ([]
                                                                                                 Int)) (STArray
                                                                                                        s
                                                                                                        Flag) (STArray
                                                                                                               s
                                                                                                               ([]
                                                                                                                Int)) (STArray
                                                                                                                       s
                                                                                                                       (Maybe
                                                                                                                        Int)) (STArray
                                                                                                                               s
                                                                                                                               Int) (STArray
                                                                                                                                     s
                                                                                                                                     Int) (STArray
                                                                                                                                           s
                                                                                                                                           Int) (STArray
                                                                                                                                                 s
                                                                                                                                                 (Maybe
                                                                                                                                                  Int)) (STArray
                                                                                                                                                         s
                                                                                                                                                         (Maybe
                                                                                                                                                          Int));
  rebindDense :: Graph -> Graph -> Int -> Int -> Either String Graph;
  rebindDense old skeleton low high = runST (denseRebinding old skeleton low high);
  denseRebinding :: forall s. Graph -> Graph -> Int -> Int -> ST s (Either String Graph);
  denseRebinding old skeleton low high =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count Nothing)
      (\oldNodes ->
         stBind (newSTArray count Nothing)
           (\newNodes ->
              stBind (newSTArray count 0)
                (\images ->
                   stBind (newSTArray count [])
                     (\classes ->
                        stBind (newSTArray count Flexible)
                          (\flags ->
                             stBind (newSTArray count [])
                               (\parents ->
                                  stBind (newSTArray count Nothing)
                                    (\tree ->
                                       stBind (newSTArray count 0)
                                         (\depths ->
                                            stBind (newSTArray count 0)
                                              (\colours ->
                                                 stBind (newSTArray count 0)
                                                   (\grafted ->
                                                      stBind (newSTArray count Nothing)
                                                        (\oldBinders ->
                                                           stBind (newSTArray count Nothing)
                                                             (\raised ->
                                                                let {
                                                                  state =
                                                                    DenseRebinding old skeleton low
                                                                      high
                                                                      oldNodes
                                                                      newNodes
                                                                      images
                                                                      classes
                                                                      flags
                                                                      parents
                                                                      tree
                                                                      depths
                                                                      colours
                                                                      grafted
                                                                      oldBinders
                                                                      raised
                                                                } in
                                                                let {
                                                                  originals = IM.toList (nodes old)
                                                                } in
                                                                let {
                                                                  remaining =
                                                                    IM.toList (nodes skeleton)
                                                                } in
                                                                stBind
                                                                  (denseLoadOriginals state
                                                                     originals)
                                                                  (\loadedOld ->
                                                                     stBind
                                                                       (denseLoadRemainings state
                                                                          remaining)
                                                                       (\loadedNew ->
                                                                          stBind
                                                                            (denseMarkOriginals
                                                                               state
                                                                               originals)
                                                                            (\marked ->
                                                                               ST.bindE
                                                                                 (densePlaceEntries
                                                                                    state
                                                                                    remaining)
                                                                                 (\placed ->
                                                                                    ST.bindE
                                                                                      (denseFinalNodes
                                                                                         state
                                                                                         remaining)
                                                                                      (\final ->
                                                                                         ST.bindE
                                                                                           (denseRaiseOriginals
                                                                                              state
                                                                                              originals)
                                                                                           (\up ->
                                                                                              stBind
                                                                                                (newDensePermissions
                                                                                                   low
                                                                                                   high
                                                                                                   oldNodes
                                                                                                   oldBinders
                                                                                                   originals)
                                                                                                (\oldPermissions ->
                                                                                                   stBind
                                                                                                     (newDensePermissions
                                                                                                        low
                                                                                                        high
                                                                                                        oldNodes
                                                                                                        raised
                                                                                                        originals)
                                                                                                     (\raisedPermissions ->
                                                                                                        ST.bindE
                                                                                                          (denseCheckOriginals
                                                                                                             state
                                                                                                             oldPermissions
                                                                                                             raisedPermissions
                                                                                                             originals)
                                                                                                          (\checked ->
                                                                                                             ST.bindE
                                                                                                               (denseCheckMergeEntries
                                                                                                                  low
                                                                                                                  classes
                                                                                                                  raised
                                                                                                                  raisedPermissions
                                                                                                                  remaining)
                                                                                                               (\merged ->
                                                                                                                  ST.pureE
                                                                                                                    (mkGraph
                                                                                                                       (nodesFromDistinctAscList
                                                                                                                          final)
                                                                                                                       (links
                                                                                                                          skeleton)
                                                                                                                       (nextId
                                                                                                                          skeleton))))))))))))))))))))))));
  denseTableNode :: forall s. Int -> STArray s (Maybe Node) -> Int -> ST s Node;
  denseTableNode low table n =
    stBind (readDense low table n)
      (\entry ->
         case entry of {
           Nothing -> panic ("missing graph node " ++ showInt n);
           Just v -> stReturn v
         });
  denseLoadOriginal :: forall s. DenseRebinding s -> (,) Int Node -> ST s ();
  denseLoadOriginal state ((,) n v) =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        let {
          image = resolve skeleton n
        } in
        stBind (writeDense low oldNodes n (Just v))
          (\node ->
             stBind (writeDense low oldBinders n (binder v))
               (\bound ->
                  stBind (writeDense low images n image)
                    (\mapped ->
                       stBind (readDense low classes image)
                         (\previous ->
                            stBind (writeDense low classes image ((:) n previous))
                              (\added ->
                                 if equalFlag (flag v) Rigid
                                 then writeDense low flags image Rigid
                                 else stReturn ())))))
    };
  denseLoadRemaining :: forall s. DenseRebinding s -> (,) Int Node -> ST s ();
  denseLoadRemaining state ((,) n v) =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (writeDense low newNodes n (Just v))
          (\node -> denseLoadParents low parents n (children (tag v)))
    };
  -- The visited array marks a union of graft descendants once, including when
  -- many old bottom nodes become aliases of the same representative.
  denseMarkOriginal :: forall s. DenseRebinding s -> (,) Int Node -> ST s ();
  denseMarkOriginal state ((,) n v) =
    if L.not (isBottom (tag v))
    then stReturn ()
    else case state of {
           DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
             stBind (readDense low images n)
               (\image ->
                  stBind (denseTableNode low newNodes image)
                    (\result -> denseMarks state (children (tag result))))
         };
  denseMark :: forall s. DenseRebinding s -> Int -> ST s ();
  denseMark state n =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low grafted n)
          (\seen ->
             if (seen == 0)
             then stBind (writeDenseInt low grafted n 1)
                    (\marked ->
                       stBind (denseTableNode low newNodes n)
                         (\v -> denseMarks state (children (tag v))))
             else stReturn ())
    };
  denseCandidates :: forall s. DenseRebinding s -> [] Int -> ST s ([] Int);
  denseCandidates state members =
    case members of {
      [] -> stReturn [];
      (:) n rest ->
        case state of {
          DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
            stBind (readDense low oldBinders n)
              (\original ->
                 case original of {
                   Nothing -> denseCandidates state rest;
                   Just b ->
                     stBind (readDense low images b)
                       (\image ->
                          stBind (denseCandidates state rest)
                            (\remaining -> stReturn ((:) image remaining)))
                 })
        }
    };
  denseParent :: forall s. DenseRebinding s -> Int -> ST s (Either String Int);
  denseParent state n =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low tree n)
          (\parent ->
             case parent of {
               Nothing -> ST.failE "binders have no common ancestor";
               Just b -> ST.pureE b
             })
    };
  denseCommon :: forall s. DenseRebinding s -> Int -> Int -> ST s (Either String Int);
  denseCommon state a b =
    if (a == b)
    then ST.pureE a
    else case state of {
           DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
             stBind (readDense low depths a)
               (\da ->
                  stBind (readDense low depths b)
                    (\db ->
                       if (db < da)
                       then ST.bindE (denseParent state a) (\p -> denseCommon state p b)
                       else if (da < db)
                            then ST.bindE (denseParent state b) (\q -> denseCommon state a q)
                            else ST.bindE (denseParent state a)
                                   (\p ->
                                      ST.bindE (denseParent state b)
                                        (\q -> denseCommon state p q))))
         };
  denseCommonMany :: forall s. DenseRebinding s -> [] Int -> ST s (Either String (Maybe Int));
  denseCommonMany state candidates =
    case candidates of {
      [] -> ST.pureE Nothing;
      (:) first rest ->
        ST.bindE (denseCommonFold state first rest) (\parent -> ST.pureE (Just parent))
    };
  densePlace :: forall s. DenseRebinding s -> Int -> ST s (Either String ());
  densePlace state n =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low colours n)
          (\colour ->
             if (colour == 1)
             then ST.failE "cyclic structure/binding dependencies"
             else if (colour == 2)
                  then ST.pureE ()
                  else stBind (writeDenseInt low colours n 1)
                         (\active ->
                            stBind (readDense low grafted n)
                              (\graft ->
                                 stBind (readDense low parents n)
                                   (\ps ->
                                      stBind (readDense low classes n)
                                        (\members ->
                                           stBind (denseCandidates state members)
                                             (\originals ->
                                                let {
                                                  candidates =
                                                    L.append originals
                                                      (if (graft == 0) then [] else ps)
                                                } in
                                                ST.bindE (densePlaces state candidates)
                                                  (\placedCandidates ->
                                                     ST.bindE (densePlaces state ps)
                                                       (\placedParents ->
                                                          ST.bindE
                                                            (denseCommonMany state candidates)
                                                            (\parent ->
                                                               stBind
                                                                 (case parent of {
                                                                    Nothing -> stReturn 0;
                                                                    Just p ->
                                                                      stBind
                                                                        (readDense low depths p)
                                                                        (\depth ->
                                                                           stReturn (depth + 1))
                                                                  })
                                                                 (\depth ->
                                                                    stBind
                                                                      (writeDense low tree n parent)
                                                                      (\bound ->
                                                                         stBind
                                                                           (writeDenseInt low depths
                                                                              n
                                                                              depth)
                                                                           (\measured ->
                                                                              stBind
                                                                                (writeDenseInt low
                                                                                   colours
                                                                                   n
                                                                                   2)
                                                                                (\complete ->
                                                                                   ST.pureE
                                                                                     ())))))))))))))
    };
  denseFinalNode :: forall s. DenseRebinding s ->
                              (,) Int Node -> ST s (Either String ((,) Int Node));
  denseFinalNode state ((,) n v) =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low tree n)
          (\parent ->
             stBind (readDense low flags n)
               (\newFlag ->
                  ST.pureE
                    ((,) n
                       (if (equalMaybeInt parent (binder v) && equalFlag newFlag (flag v))
                        then v
                        else mkNode (tag v) parent newFlag))))
    };
  denseClimb :: forall s. DenseRebinding s -> Int -> Maybe Int -> ST s (Either String (Maybe Int));
  denseClimb state wanted current =
    case current of {
      Nothing -> ST.failE "a node's binder cannot be lowered";
      Just b ->
        case state of {
          DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
            stBind (readDense low images b)
              (\image ->
                 if (image == wanted)
                 then ST.pureE (Just b)
                 else stBind (readDense low oldBinders b)
                        (\parent -> denseClimb state wanted parent))
        }
    };
  denseRaiseOriginal :: forall s. DenseRebinding s -> (,) Int Node -> ST s (Either String ());
  denseRaiseOriginal state ((,) n v) =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low images n)
          (\image ->
             stBind (readDense low tree image)
               (\wanted ->
                  ST.bindE
                    (case wanted of {
                       Nothing -> ST.pureE Nothing;
                       Just parent -> denseClimb state parent (binder v)
                     })
                    (\up -> ST.liftE (writeDense low raised n up))))
    };
  -- Permission components are memoized on demand, matching the seed's lazy
  -- immutable array knot without exporting mutable state out of runST.
  data DensePermissions s =
    DensePermissions Int (STArray s (Maybe Node)) (STArray s (Maybe Int)) (STArray s
                                                                           ([] Int)) (STArray s
                                                                                        Int) (STArray
                                                                                              s
                                                                                              Int) (STArray
                                                                                                    s
                                                                                                    (Maybe
                                                                                                     Permission));
  newDensePermissions :: forall s. Int ->
                                   Int ->
                                   STArray s (Maybe Node) ->
                                   STArray s (Maybe Int) ->
                                   [] ((,) Int Node) -> ST s (DensePermissions s);
  newDensePermissions low high table binding entries =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count [])
      (\descendants ->
         stBind (newSTArray count (0 - 1))
           (\inertness ->
              stBind (newSTArray count (0 - 1))
                (\paths ->
                   stBind (newSTArray count Nothing)
                     (\permissions ->
                        stBind (densePermissionChildren low binding descendants entries)
                          (\loaded ->
                             stReturn
                               (DensePermissions low table binding descendants inertness paths
                                  permissions))))));
  denseAllInert :: forall s. DensePermissions s -> [] Int -> ST s Bool;
  denseAllInert state pending =
    case pending of {
      [] -> stReturn True;
      (:) n rest ->
        stBind (denseInert state n)
          (\answer -> if answer then denseAllInert state rest else stReturn False)
    };
  denseInert :: forall s. DensePermissions s -> Int -> ST s Bool;
  denseInert state n =
    case state of {
      DensePermissions low table binding descendants inertness paths permissions ->
        stBind (readDense low inertness n)
          (\cached ->
             if (cached >= 0)
             then stReturn (cached == 1)
             else stBind (denseTableNode low table n)
                    (\v ->
                       stBind
                         (if isBottom (tag v)
                          then stReturn False
                          else stBind (readDense low descendants n)
                                 (\descendants -> denseAllInert state descendants))
                         (\answer ->
                            stBind (writeDenseInt low inertness n (if answer then 1 else 0))
                              (\stored -> stReturn answer))))
    };
  denseFlexiblePath :: forall s. DensePermissions s -> Int -> ST s Bool;
  denseFlexiblePath state n =
    case state of {
      DensePermissions low table binding descendants inertness paths permissions ->
        stBind (readDense low paths n)
          (\cached ->
             if (cached >= 0)
             then stReturn (cached == 1)
             else stBind (denseTableNode low table n)
                    (\v ->
                       stBind
                         (if isGen (tag v)
                          then stReturn True
                          else if equalFlag (flag v) Rigid
                               then stReturn False
                               else stBind (readDense low binding n)
                                      (\parent ->
                                         case parent of {
                                           Nothing -> stReturn True;
                                           Just b -> denseFlexiblePath state b
                                         }))
                         (\answer ->
                            stBind (writeDenseInt low paths n (if answer then 1 else 0))
                              (\stored -> stReturn answer))))
    };
  densePermission :: forall s. DensePermissions s -> Int -> ST s Permission;
  densePermission state n =
    case state of {
      DensePermissions low table binding descendants inertness paths permissions ->
        stBind (readDense low permissions n)
          (\cached ->
             case cached of {
               Just value -> stReturn value;
               Nothing ->
                 stBind (denseInert state n)
                   (\inert ->
                      stBind
                        (if inert
                         then stReturn Inert
                         else stBind (denseTableNode low table n)
                                (\v ->
                                   if equalFlag (flag v) Rigid
                                   then stReturn Orange
                                   else stBind (denseFlexiblePath state n)
                                          (\flexible ->
                                             stReturn (if flexible then Green else Red))))
                        (\answer ->
                           stBind (writeDense low permissions n (Just answer))
                             (\stored -> stReturn answer)))
             })
    };
  denseCheckOriginal :: forall s. DenseRebinding s ->
                                  DensePermissions s ->
                                  DensePermissions s -> (,) Int Node -> ST s (Either String ());
  denseCheckOriginal state oldPermissions raisedPermissions ((,) n v) =
    case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low images n)
          (\image ->
             ST.bindE
               (if L.not (isBottom (tag v))
                then ST.pureE ()
                else stBind (denseTableNode low newNodes image)
                       (\result ->
                          if isBottom (tag result)
                          then ST.pureE ()
                          else stBind (densePermission oldPermissions n)
                                 (\permission ->
                                    ST.check (equalPermission permission Green)
                                      "cannot instantiate a rigid or protected type variable")))
               (\instantiated ->
                  stBind (readDense low raised n)
                    (\up ->
                       ST.bindE
                         (if equalMaybeInt (binder v) up
                          then ST.pureE ()
                          else stBind (densePermission oldPermissions n)
                                 (\permission ->
                                    ST.check (L.not (equalPermission permission Red))
                                      "cannot raise a protected type variable"))
                         (\lifted ->
                            stBind (readDense low flags image)
                              (\newFlag ->
                                 if equalFlag (flag v) newFlag
                                 then ST.pureE ()
                                 else stBind (densePermission raisedPermissions n)
                                        (\permission ->
                                           ST.check (L.not (equalPermission permission Red))
                                             "cannot weaken a protected type variable"))))))
    };
  denseCheckMerges :: forall s. Int ->
                                STArray s (Maybe Int) ->
                                DensePermissions s -> [] Int -> ST s (Either String ());
  denseCheckMerges low raised permissions members =
    case members of {
      [] -> ST.pureE ();
      (:) first rest ->
        ST.bindE (denseCheckMergeRest low raised permissions first rest)
          (\checked -> denseCheckMerges low raised permissions rest)
    };
  rebindSparse :: Graph -> Graph -> Either String Graph;
  -- raisedBinder retains the ascending identity from nodes old.
  rebindSparse old skeleton =
    let {
      classes = classesIndex old skeleton
    } in
    let {
      parents = parentsIndex skeleton
    } in
    let {
      newFlags = flagsIndex old classes
    } in
    let {
      grafted = graftedNodes old skeleton
    } in
    let {
      candidates = candidateIndex old skeleton classes parents grafted
    } in
    let {
      dependencies =
        IM.mapWithKey
          (\n -> \cs -> IS.union (IS.fromList cs) (IM.findWithDefault IS.empty n parents))
          candidates
    } in
    bindE (rebuildBinders candidates dependencies)
      (\tree ->
         bindE (mapE (raisedBinder old skeleton tree) (IM.toList (nodes old)))
           (\raisedPairs ->
              let {
                up = IM.fromDistinctAscList raisedPairs
              } in
              let {
                raised =
                  mkGraph
                    (mapNodesWithKey
                       (\n -> \v -> mkNode (tag v) (IM.findWithDefault Nothing n up) (flag v))
                       (nodes old))
                    (links old)
                    (nextId old)
              } in
              let {
                oldPermissions = permissions old
              } in
              let {
                raisedPermissions = permissions raised
              } in
              bindE
                (mapE_
                   (checkOriginalPermission skeleton oldPermissions raisedPermissions newFlags up)
                   (IM.toList (nodes old)))
                (\ignored ->
                   bindE (mapE_ (checkMergePairs raisedPermissions up) (IM.elems classes))
                     (\ignored2 ->
                        Right
                          (mkGraph
                             (mapNodesWithKey
                                (\n ->
                                   \v ->
                                     mkNode (tag v) (IM.findWithDefault Nothing n tree)
                                       (IM.get n newFlags))
                                (nodes skeleton))
                             (links skeleton)
                             (nextId skeleton))))));
  insideScope :: Graph ->
                 Int -> IntMap ((,) Int Int) -> IntMap Bool -> Int -> (,) Bool (IntMap Bool);
  insideScope graph generalization intervals known identity =
    case IM.lookup identity known of {
      Just answer -> (,) answer known;
      Nothing ->
        let {
          answer =
            case binder (nodeAt graph identity) of {
              Nothing -> (,) False known;
              Just parent ->
                let {
                  p = resolve graph parent
                } in
                let {
                  gen = resolve graph generalization
                } in
                if (p == gen)
                then (,) True known
                else if (IM.member gen intervals && IM.member p intervals)
                     then (,) (intervalContains intervals gen p) known
                     else insideScope graph generalization intervals known p
            }
        } in
        case answer of {
          (,) value cache -> strictPair value (IM.insert identity value cache)
        }
    };
  expansionVisitCached :: Graph ->
                          Int ->
                          IntMap ((,) Int Int) ->
                          (,) IntSet (IntMap Bool) -> [] Int -> (,) IntSet (IntMap Bool);
  expansionVisitCached graph generalization intervals state pending =
    case pending of {
      [] -> state;
      (:) original rest ->
        case state of {
          (,) seen scopes ->
            let {
              identity = resolve graph original
            } in
            if IS.member identity seen
            then expansionVisitCached graph generalization intervals state rest
            else case insideScope graph generalization intervals scopes identity of {
                   (,) local known ->
                     expansionVisitCached graph generalization intervals
                       ((,) (IS.insert identity seen) known)
                       (L.append (if local then children (tag (nodeAt graph identity)) else [])
                          rest)
                 }
        }
    };
  expansionVisit :: Graph -> Int -> IntSet -> [] Int -> IntSet;
  expansionVisit graph generalization seen pending =
    case expansionVisitCached graph generalization IM.empty ((,) seen IM.empty) pending of {
      (,) visited scopes -> visited
    };
  allocateCopiesUnordered :: Graph -> [] Int -> (,) (IntMap Int) Graph;
  allocateCopiesUnordered graph originals =
    L.foldlStrict
      (\state ->
         \original ->
           case state of {
             (,) copies current ->
               case freshId current of {
                 (,) fresh next ->
                   seq fresh (strictPair (IM.insert original fresh copies) (strictGraph next))
               }
           })
      ((,) IM.empty graph)
      originals;
  -- Expansion visits enumerate distinct ascending identities. Allocate the
  -- corresponding contiguous fresh range and balanced map directly, instead
  -- of rebuilding a graph wrapper and inserting into the copy map per identity.
  -- The general public helper retains the preceding fold for other list orders.
  ascendingCopyIdentities :: [] Int -> Bool;
  ascendingCopyIdentities originals =
    case originals of {
      [] -> True;
      (:) first rest -> ascendingCopyIdentitiesAfter first rest
    };
  ascendingCopyIdentitiesAfter :: Int -> [] Int -> Bool;
  ascendingCopyIdentitiesAfter previous originals =
    case originals of {
      [] -> True;
      (:) n rest -> ((previous < n) && ascendingCopyIdentitiesAfter n rest)
    };
  freshCopyEntries :: Int -> [] Int -> [] ((,) Int Int);
  freshCopyEntries first originals =
    case originals of {
      [] -> [];
      (:) original rest ->
        seq first ((:) ((,) original first) (freshCopyEntries (L.advanceIdentity first 1) rest))
    };
  allocateCopies :: Graph -> [] Int -> (,) (IntMap Int) Graph;
  allocateCopies graph originals =
    case originals of {
      [] -> (,) IM.empty graph;
      (:) _ _ ->
        if L.not (ascendingCopyIdentities originals)
        then allocateCopiesUnordered graph originals
        else let {
               first = nextId graph
             } in
             let {
               entries = freshCopyEntries first originals
             } in
             let {
               copied = IM.fromDistinctAscList entries
             } in
             let {
               next = mkGraph (nodes graph) (links graph) (L.advanceIdentity first (L.length originals))
             } in
             seq first (strictPair copied (strictGraph next))
    };
  copyIdentity :: Graph -> IntMap Int -> Int -> Int;
  copyIdentity graph copies identity =
    let {
      canonical = resolve graph identity
    } in
    IM.findWithDefault canonical canonical copies;
  expansionNode :: Graph ->
                   Int -> Int -> Int -> IntMap Int -> IntMap Kind -> IntMap Bool -> Int -> Node;
  expansionNode graph generalization destination source copies kinds scopes identity =
    let {
      node = nodeAt graph identity
    } in
    let {
      copy = copyIdentity graph copies
    } in
    let {
      root = copy source
    } in
    if L.not (IM.findWithDefault False identity scopes)
    then mkNode (bottomTag (IM.get identity kinds)) (Just destination) Flexible
    else if (identity == source)
         then mkNode (mapTag copy (tag node)) (Just destination) Flexible
         else mkNode (mapTag copy (tag node))
                (mapMaybeInt
                   (\parent ->
                      if (resolve graph parent == resolve graph generalization)
                      then root
                      else copy parent)
                   (binder node))
                (flag node);
  expand :: Int ->
            Int ->
            Graph -> Either String ((,) ((,,) Int (IntMap Int) ([] ((,) Int Int))) Graph);
  expand generalization destination graph =
    expandWithScopes IM.empty generalization destination graph;
  expandWithScopes :: IntMap ((,) Int Int) ->
                      Int ->
                      Int ->
                      Graph ->
                      Either String ((,) ((,,) Int (IntMap Int) ([] ((,) Int Int))) Graph);
  expandWithScopes intervals generalization destination graph =
    let {
      source = genRoot graph generalization
    } in
    case expansionVisitCached graph generalization intervals ((,) IS.empty IM.empty)
           ((:) source []) of {
      (,) visited scopes ->
        let {
          originals = IS.toList visited
        } in
        bindE (kindsAt graph originals)
          (\kinds ->
             case allocateCopies graph originals of {
               (,) copies allocated ->
                 let {
                   copy = copyIdentity graph copies
                 } in
                 let {
                   result =
                     L.foldlStrict
                       (\current ->
                          \n ->
                            setNode (copy n)
                              (expansionNode graph generalization destination source copies kinds
                                 scopes
                                 n)
                              current)
                       allocated
                       originals
                 } in
                 let {
                   frontier = L.filter (\n -> L.not (IM.findWithDefault False n scopes)) originals
                 } in
                 Right
                   ((,) ((,,) (copy source) copies (L.map (\n -> (,) n (copy n)) frontier))
                      result)
             })
    };
  -- Freeze one solved recursive member without instantiating its environment.
  -- Unlike expansion, the traversal's outer frontier retains its identities:
  -- copying it to fresh bottoms would let later uses generalize captured types.
  -- The destination identity has been reserved with freshId, but has no node
  -- yet. Install its GGen atomically with the completed root, so intermediate
  -- solver flushes never have to validate an unfinished export scheme.
  materializeExport :: Int ->
                       Int ->
                       Int ->
                       Int ->
                       Graph -> Either String ((,) ((,) Int (IntMap Int)) Graph);
  materializeExport generalization selected destination parent graph =
    bindE (validateGraph graph)
      (\valid ->
         bindE (require graph generalization)
           (\groupNode ->
              bindE (require graph parent)
                (\parentNode ->
                   bindE (require graph selected)
                     (\sourceNode ->
                        let {
                          group = resolve graph generalization;
                          source = resolve graph selected;
                          outer = resolve graph parent
                        } in
                        bindE
                          (check
                             (isGen (tag groupNode) && isGen (tag parentNode) &&
                              equalMaybeInt (mapMaybeInt (resolve graph) (binder groupNode)) (Just outer))
                             "recursive export requires a group under its parent gen")
                          (\scopeChecked ->
                             bindE
                               (check
                                  (IM.notMember destination (nodes graph) &&
                                   IM.notMember destination (links graph) &&
                                   (destination < nextId graph) &&
                                   L.all (\n -> (n < nextId graph))
                                     (L.append (IM.keys (nodes graph)) (IM.keys (links graph))))
                                  "recursive export requires a reserved destination and valid fresh counter")
                               (\destinationChecked ->
                                  bindE
                                    (check (L.not (isGen (tag sourceNode)))
                                       "recursive export root must be a type node")
                                    (\sourceChecked ->
                                       materializeExportIn graph group source destination outer)))))));
  materializeExportIn :: Graph ->
                         Int ->
                         Int ->
                         Int ->
                         Int -> Either String ((,) ((,) Int (IntMap Int)) Graph);
  materializeExportIn graph generalization source destination parent =
    case expansionVisitCached graph generalization IM.empty ((,) IS.empty IM.empty)
           ((:) source []) of {
      (,) visited scopes ->
        let {
          originals = L.filter (\n -> IM.findWithDefault False n scopes) (IS.toList visited)
        } in
        -- Shared member roots start directly group-bound; solving can only
        -- raise their binder. A nested root is not a completed member interface.
        bindE
          (check
             (L.not (IM.findWithDefault False source scopes) ||
              equalMaybeInt (mapMaybeInt (resolve graph) (binder (nodeAt graph source)))
                (Just generalization))
             "recursive export root must be group-bound or external")
          (\rootChecked ->
             case allocateCopies graph originals of {
               (,) copies allocated ->
                 bindE (mapE_ (validateExportCopy graph generalization source copies) originals)
                   (\copiesChecked ->
                      let {
                        copy = copyIdentity graph copies;
                        result =
                          L.foldlStrict
                            (\current ->
                               \n ->
                                 setNode (copy n)
                                   (exportNode graph generalization destination source copies n)
                                   current)
                            allocated
                            originals;
                        exported =
                          setNode destination (mkNode (GGen (copy source)) (Just parent) Flexible)
                            result
                      } in
                      bindE (validateGraph exported)
                        (\verified -> Right ((,) ((,) (copy source) copies) exported)))
             })
    };
  validateExportCopy :: Graph -> Int -> Int -> IntMap Int -> Int -> Either String ();
  validateExportCopy graph generalization source copies identity =
    let {
      copy = IM.get identity copies
    } in
    bindE
      (check (IM.notMember copy (nodes graph) && IM.notMember copy (links graph))
         "recursive export fresh identities overlap the source graph")
      (\freshChecked ->
         if (identity == source)
         then Right ()
         else case binder (nodeAt graph identity) of {
                Nothing -> Left "recursive export lost a local binder";
                Just owner ->
                  let {
                    canonical = resolve graph owner
                  } in
                  check ((canonical == generalization) || IM.member canonical copies)
                    "recursive export is not closed under local binders"
              });
  exportNode :: Graph -> Int -> Int -> Int -> IntMap Int -> Int -> Node;
  exportNode graph generalization destination source copies identity =
    let {
      node = nodeAt graph identity;
      copy = copyIdentity graph copies;
      owner =
        if (identity == source)
        then Just destination
        else mapMaybeInt
               (\p -> if (resolve graph p == generalization) then copy source else copy p)
               (binder node)
    } in
    mkNode (mapTag copy (tag node)) owner (flag node);
  -- Inspect the exact raw interface, never a normalized unfinished graph or
  -- the structural lower bound of a flexible/abstract parameter.
  knownFieldInterface :: Graph -> Int -> Either String Bool;
  knownFieldInterface graph original =
    bindE (require graph original)
      (\node -> bindE (kindAt graph original)
        (\kind -> bindE (check (equalKind kind Star) "pattern field must have kind *")
          (\checked ->
            if L.not (equalFlag (flag node) Rigid) then Right False
            else case tag node of {
              GSkolem _ _ -> Right False;
              GGen _ -> Left "pattern field must be a type node";
              GBot -> Right True;
              GBotK _ -> Right True;
              _ -> Right (L.any (fieldQuantifier graph (resolve graph original))
                (orderedBelow graph original))
            })));
  fieldQuantifier :: Graph -> Int -> Int -> Bool;
  fieldQuantifier graph root identity =
    let { node = nodeAt graph identity } in
    equalFlag (flag node) Flexible &&
    equalMaybeInt (mapMaybeInt (resolve graph) (binder node)) (Just root) &&
    (case tag node of { GGen _ -> False; GSkolem _ _ -> False; _ -> True }) &&
    L.not (inert graph identity);
  -- A field proxy already exists in the scope tree. Only its structural root
  -- is replaced; the original parameter and every external frontier identity
  -- are untouched. The returned map is the complete fresh-copy receipt.
  materializeField :: Int -> Int -> Graph -> Either String ((,) (IntMap Int) Graph);
  materializeField original destination graph =
    bindE (validateGraph graph)
      (\valid -> bindE
        (check
          (L.all (\n -> n < nextId graph && IM.notMember n (links graph)) (IM.keys (nodes graph)) &&
           L.all (\n -> n < nextId graph) (IM.keys (links graph)))
          "pattern projection requires a valid fresh identity counter")
        (\freshChecked -> materializeFieldIn original destination graph));
  -- Trusted solver entry: prepare has checked graph/counter invariants, and
  -- each prior solver operation preserves them. The case audits its output.
  materializeFieldIn :: Int -> Int -> Graph -> Either String ((,) (IntMap Int) Graph);
  materializeFieldIn original destination graph =
    bindE (knownFieldInterface graph original)
      (\eligible -> bindE (check eligible "pattern field has no known polymorphic interface")
        (\checked -> bindE (require graph destination)
          (\proxy ->
            let { source = resolve graph original; target = resolve graph destination } in
            bindE
              (check
                (case tag proxy of {
                  GGen root -> resolve graph root == source &&
                    L.not (underBinder graph source target);
                  _ -> False
                }) "pattern projection requires its original external-root proxy")
              (\proxyChecked ->
                case expansionVisitCached graph source IM.empty
                  ((,) (IS.singleton source) (IM.singleton source True))
                  (children (tag (nodeAt graph source))) of {
                  (,) visited scopes ->
                    let { originals = L.filter (\n -> IM.findWithDefault False n scopes)
                      (IS.toList visited) } in
                    case allocateCopies graph originals of {
                      (,) copies allocated ->
                        bindE (mapE_ (validateFieldCopy graph source copies) originals)
                          (\copiesChecked ->
                            let { copy = copyIdentity graph copies } in
                            let { copied = L.foldlStrict
                              (\current n -> setNode (copy n)
                                (fieldCopyNode graph source target copies n) current)
                              allocated originals } in
                            Right ((,) copies (setNode target
                              (mkNode (GGen (copy source)) (binder proxy) (flag proxy)) copied)))
                    }
                }))));
  validateFieldCopy :: Graph -> Int -> IntMap Int -> Int -> Either String ();
  validateFieldCopy graph source copies identity =
    let { node = nodeAt graph identity; copy = IM.get identity copies } in
    bindE
      (check (IM.notMember copy (nodes graph) && IM.notMember copy (links graph))
        "pattern projection fresh identities overlap the source graph")
      (\freshChecked -> bindE
        (check (case tag node of { GGen _ -> False; GSkolem _ _ -> False; _ -> True })
          "pattern projection cannot copy scope or abstract identities")
        (\tagChecked ->
          if identity == source then Right ()
          else case binder node of {
            Nothing -> Left "pattern projection lost a local binder";
            Just owner -> check (IM.member (resolve graph owner) copies)
              "pattern projection is not closed under local binders"
          }));
  fieldCopyNode :: Graph -> Int -> Int -> IntMap Int -> Int -> Node;
  fieldCopyNode graph source destination copies identity =
    let { node = nodeAt graph identity; copy = copyIdentity graph copies } in
    if identity == source
    then mkNode (mapTag copy (tag node)) (Just destination) Flexible
    else mkNode (mapTag copy (tag node)) (mapMaybeInt copy (binder node)) (flag node);
  schemeOrExistential :: Graph -> Int -> Node -> Bool;
  schemeOrExistential graph identity node =
    case binder node of {
      Nothing -> False;
      Just parent ->
        case tag (nodeAt graph parent) of {
          GGen root ->
            ((identity == resolve graph root) || L.not (IS.member identity (reachable graph root)));
          _ -> False
        }
    };
  normalize :: Graph -> Graph;
  -- Solver.finishNormalized reuses validation across this transformation:
  -- only non-Gen flags may change; identities, tags and binders stay intact.
  normalize graph =
    case denseBounds graph of {
      Nothing -> normalizeSparse graph;
      Just ((,) low high) -> normalizeDense graph low high
    };
  normalizeSparse :: Graph -> Graph;
  -- Several nodes can share a generalization binder. Keep its structural
  -- closure lazy and share it for this immutable graph, rather than rebuilding
  -- the same reachability set for each existential check.
  normalizeSparse graph =
    let {
      inertness = inertNodes graph
    } in
    let {
      scopes =
        IM.map
          (\v ->
             case tag v of {
               GGen root -> reachable graph root;
               _ -> IS.empty
             })
          (nodes graph)
    } in
    let {
      scheme =
        \n v ->
          case binder v of {
            Nothing -> False;
            Just parent ->
              case tag (nodeAt graph parent) of {
                GGen root ->
                  ((n == resolve graph root) ||
                   L.not (IS.member n (IM.get (resolve graph parent) scopes)));
                _ -> False
              }
          }
    } in
    mkGraph
      (mapNodesWithKey
         (\n ->
            \v ->
              if isGen (tag v)
              then v
              else if (IM.findWithDefault False n inertness || scheme n v)
                   then mkNode (tag v) (binder v) Rigid
                   else v)
         (nodes graph))
      (links graph)
      (nextId graph);
  -- Normalize dense graphs with bounded scratch arrays. Only flags may change;
  -- the persistent sparse path remains available for arbitrary identity spans.
  data DenseNormalization s =
    DenseNormalization Graph Int (STArray s (Maybe Node)) (STArray s ([] Int)) (STArray s
                                                                                  Int) (STArray s
                                                                                        Int) (STArray
                                                                                              s
                                                                                              Bool) (STArray
                                                                                                     s
                                                                                                     ([]
                                                                                                      Int));
  normalizeDense :: Graph -> Int -> Int -> Graph;
  normalizeDense graph low high =
    runST
      (let {
         count = ((high - low) + 1)
       } in
       stBind (newSTArray count Nothing)
         (\table ->
            stBind (newSTArray count [])
              (\descendants ->
                 stBind (newSTArray count (0 - 1))
                   (\inertness ->
                      stBind (newSTArray count (low - 1))
                        (\seen ->
                           stBind (newSTArray count False)
                             (\rigid ->
                                stBind (newSTArray count [])
                                  (\candidates ->
                                     let {
                                       state =
                                         DenseNormalization graph low table descendants inertness
                                           seen
                                           rigid
                                           candidates
                                     } in
                                     let {
                                       entries = IM.toList (nodes graph)
                                     } in
                                     stBind (normalLoad state entries)
                                       (\loaded ->
                                          stBind (normalGather state entries)
                                            (\gathered ->
                                               stBind (normalScopes state entries)
                                                 (\marked ->
                                                    stBind (normalResults state entries)
                                                      (\result ->
                                                         stReturn
                                                           (mkGraph
                                                              (nodesFromDistinctAscList result)
                                                              (links graph)
                                                              (nextId graph)))))))))))));
  normalLoad :: forall s. DenseNormalization s -> [] ((,) Int Node) -> ST s ();
  normalLoad state entries =
    case entries of {
      [] -> stReturn ();
      (:) ((,) n v) rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            stBind (writeDense low table n (Just v))
              (\loaded ->
                 stBind
                   (if equalFlag (flag v) Rigid
                    then stReturn ()
                    else case binder v of {
                           Nothing -> stReturn ();
                           Just parent ->
                             stBind (readDense low descendants parent)
                               (\previous -> writeDense low descendants parent ((:) n previous))
                         })
                   (\added -> normalLoad state rest))
        }
    };
  normalInert :: forall s. DenseNormalization s -> Int -> ST s Bool;
  normalInert state n =
    case state of {
      DenseNormalization graph low table descendants inertness seen rigid candidates ->
        stBind (readDense low inertness n)
          (\known ->
             if (known >= 0)
             then stReturn (known == 1)
             else stBind (denseTableNode low table n)
                    (\v ->
                       stBind
                         (if isBottom (tag v)
                          then stReturn False
                          else stBind (readDense low descendants n) (normalAllInert state))
                         (\answer ->
                            stBind (writeDenseInt low inertness n (if answer then 1 else 0))
                              (\stored -> stReturn answer))))
    };
  normalAllInert :: forall s. DenseNormalization s -> [] Int -> ST s Bool;
  normalAllInert state pending =
    case pending of {
      [] -> stReturn True;
      (:) n rest ->
        stBind (normalInert state n)
          (\answer -> if answer then normalAllInert state rest else stReturn False)
    };
  normalGather :: forall s. DenseNormalization s -> [] ((,) Int Node) -> ST s ();
  normalGather state entries =
    case entries of {
      [] -> stReturn ();
      (:) ((,) n v) rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            stBind
              (if (isGen (tag v) || equalFlag (flag v) Rigid)
               then stReturn ()
               else stBind (normalInert state n)
                      (\inert ->
                         if inert
                         then writeDense low rigid n True
                         else case binder v of {
                                Nothing -> stReturn ();
                                Just parent ->
                                  stBind (denseTableNode low table parent)
                                    (\scope ->
                                       case tag scope of {
                                         GGen root ->
                                           if (n == resolve graph root)
                                           then writeDense low rigid n True
                                           else stBind (readDense low candidates parent)
                                                  (\previous ->
                                                     writeDense low candidates parent
                                                       ((:) n previous));
                                         _ -> stReturn ()
                                       })
                              }))
              (\gathered -> normalGather state rest)
        }
    };
  normalScopes :: forall s. DenseNormalization s -> [] ((,) Int Node) -> ST s ();
  normalScopes state entries =
    case entries of {
      [] -> stReturn ();
      (:) ((,) n v) rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            stBind
              (case tag v of {
                 GGen root ->
                   stBind (readDense low candidates n)
                     (\pending ->
                        if L.null pending
                        then stReturn ()
                        else stBind (normalReach state n ((:) root []))
                               (\visited -> normalExistentials state n pending));
                 _ -> stReturn ()
               })
              (\marked -> normalScopes state rest)
        }
    };
  normalReach :: forall s. DenseNormalization s -> Int -> [] Int -> ST s ();
  normalReach state stamp pending =
    case pending of {
      [] -> stReturn ();
      (:) original rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            let {
              n = resolve graph original
            } in
            stBind (readDense low seen n)
              (\previous ->
                 if (previous == stamp)
                 then normalReach state stamp rest
                 else stBind (writeDenseInt low seen n stamp)
                        (\marked ->
                           stBind (denseTableNode low table n)
                             (\v -> normalReach state stamp (L.append (children (tag v)) rest))))
        }
    };
  normalExistentials :: forall s. DenseNormalization s -> Int -> [] Int -> ST s ();
  normalExistentials state stamp pending =
    case pending of {
      [] -> stReturn ();
      (:) n rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            stBind (readDense low seen n)
              (\visited ->
                 stBind (writeDense low rigid n (visited /= stamp))
                   (\marked -> normalExistentials state stamp rest))
        }
    };
  normalResults :: forall s. DenseNormalization s ->
                             [] ((,) Int Node) -> ST s ([] ((,) Int Node));
  normalResults state entries =
    case entries of {
      [] -> stReturn [];
      (:) ((,) n v) rest ->
        case state of {
          DenseNormalization graph low table descendants inertness seen rigid candidates ->
            stBind (readDense low rigid n)
              (\changed ->
                 stBind (normalResults state rest)
                   (\tail ->
                      stReturn
                        ((:) ((,) n (if changed then mkNode (tag v) (binder v) Rigid else v))
                           tail)))
        }
    };
  -- Reverse accumulation makes the postorder traversal linear in its output.
  -- The public accumulator helper retains its forward-prefix contract.
  orderedVisitReverse :: Graph -> (,) IntSet ([] Int) -> Int -> (,) IntSet ([] Int);
  orderedVisitReverse graph ((,) seen order) original =
    let {
      identity = resolve graph original
    } in
    if IS.member identity seen
    then (,) seen order
    else case L.foldl (orderedVisitReverse graph) ((,) (IS.insert identity seen) order)
                (children (tag (nodeAt graph identity))) of {
           (,) visited result -> (,) visited ((:) identity result)
         };
  orderedVisit :: Graph -> (,) IntSet ([] Int) -> Int -> (,) IntSet ([] Int);
  orderedVisit graph ((,) seen prefix) original =
    case orderedVisitReverse graph ((,) seen []) original of {
      (,) visited result -> (,) visited (L.append prefix (L.reverse result))
    };
  orderedBelow :: Graph -> Int -> [] Int;
  orderedBelow graph root =
    case orderedVisitReverse graph ((,) IS.empty []) root of {
      (,) seen order -> L.reverse order
    };
  -- Direct loops keep the state operations visible to checked native lowering.
  -- They preserve the corresponding ST library traversal order and error stops.
  denseLoadValidation :: forall s. Int ->
                                   STArray s (Maybe Node) -> [] ((,) Int Node) -> ST s ();
  denseLoadValidation low table values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind
          (case entry of {
             (,) n v -> writeDense low table n (Just v)
           })
          (\ignored -> denseLoadValidation low table rest)
    };
  denseCheckBinders :: forall s. DenseValidation s ->
                                 [] ((,) Int Node) -> ST s (Either String ());
  denseCheckBinders state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE (denseCheckBinder state entry) (\ignored -> denseCheckBinders state rest)
    };
  denseAddDescendants :: forall s. DenseValidation s -> [] ((,) Int Node) -> ST s ();
  denseAddDescendants state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (denseAddDescendant state entry) (\ignored -> denseAddDescendants state rest)
    };
  denseKindEntries :: forall s. DenseValidation s ->
                                [] ((,) Int Node) -> ST s (Either String ());
  denseKindEntries state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (case entry of {
             (,) n v -> denseKind state n v
           })
          (\ignored -> denseKindEntries state rest)
    };
  denseBindingChildren :: forall s. DenseValidation s -> Int -> [] Int -> ST s Int;
  denseBindingChildren state position children =
    case children of {
      [] -> stReturn position;
      (:) child rest ->
        stBind (denseBindingVisit state child position)
          (\next -> denseBindingChildren state next rest)
    };
  denseChildKinds :: forall s. DenseValidation s ->
                               Int -> [] Int -> ST s (Either String ([] Kind));
  denseChildKinds state n values =
    case values of {
      [] -> ST.pureE [];
      (:) entry rest ->
        ST.bindE (denseChild state n entry)
          (\answer ->
             ST.bindE (denseChildKinds state n rest) (\answers -> ST.pureE ((:) answer answers)))
    };
  denseLoadOriginals :: forall s. DenseRebinding s -> [] ((,) Int Node) -> ST s ();
  denseLoadOriginals state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (denseLoadOriginal state entry) (\ignored -> denseLoadOriginals state rest)
    };
  denseLoadRemainings :: forall s. DenseRebinding s -> [] ((,) Int Node) -> ST s ();
  denseLoadRemainings state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (denseLoadRemaining state entry) (\ignored -> denseLoadRemainings state rest)
    };
  denseMarkOriginals :: forall s. DenseRebinding s -> [] ((,) Int Node) -> ST s ();
  denseMarkOriginals state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (denseMarkOriginal state entry) (\ignored -> denseMarkOriginals state rest)
    };
  densePlaceEntries :: forall s. DenseRebinding s ->
                                 [] ((,) Int Node) -> ST s (Either String ());
  densePlaceEntries state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (case entry of {
             (,) n v -> densePlace state n
           })
          (\ignored -> densePlaceEntries state rest)
    };
  denseFinalNodes :: forall s. DenseRebinding s ->
                               [] ((,) Int Node) -> ST s (Either String ([] ((,) Int Node)));
  denseFinalNodes state values =
    case values of {
      [] -> ST.pureE [];
      (:) entry rest ->
        ST.bindE (denseFinalNode state entry)
          (\answer ->
             ST.bindE (denseFinalNodes state rest) (\answers -> ST.pureE ((:) answer answers)))
    };
  denseRaiseOriginals :: forall s. DenseRebinding s ->
                                   [] ((,) Int Node) -> ST s (Either String ());
  denseRaiseOriginals state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE (denseRaiseOriginal state entry) (\ignored -> denseRaiseOriginals state rest)
    };
  denseCheckOriginals :: forall s. DenseRebinding s ->
                                   DensePermissions s ->
                                   DensePermissions s ->
                                   [] ((,) Int Node) -> ST s (Either String ());
  denseCheckOriginals state oldPermissions raisedPermissions values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE (denseCheckOriginal state oldPermissions raisedPermissions entry)
          (\ignored -> denseCheckOriginals state oldPermissions raisedPermissions rest)
    };
  denseCheckMergeEntries :: forall s. Int ->
                                      STArray s ([] Int) ->
                                      STArray s (Maybe Int) ->
                                      DensePermissions s ->
                                      [] ((,) Int Node) -> ST s (Either String ());
  denseCheckMergeEntries low classes raised raisedPermissions values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (case entry of {
             (,) n v ->
               stBind (readDense low classes n)
                 (\members -> denseCheckMerges low raised raisedPermissions members)
           })
          (\ignored -> denseCheckMergeEntries low classes raised raisedPermissions rest)
    };
  denseLoadParents :: forall s. Int -> STArray s ([] Int) -> Int -> [] Int -> ST s ();
  denseLoadParents low parents n values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind
          (stBind (readDense low parents entry)
             (\previous -> writeDense low parents entry ((:) n previous)))
          (\ignored -> denseLoadParents low parents n rest)
    };
  denseMarks :: forall s. DenseRebinding s -> [] Int -> ST s ();
  denseMarks state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest -> stBind (denseMark state entry) (\ignored -> denseMarks state rest)
    };
  densePlaces :: forall s. DenseRebinding s -> [] Int -> ST s (Either String ());
  densePlaces state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest -> ST.bindE (densePlace state entry) (\ignored -> densePlaces state rest)
    };
  denseCommonFold :: forall s. DenseRebinding s -> Int -> [] Int -> ST s (Either String Int);
  denseCommonFold state initial values =
    case values of {
      [] -> ST.pureE initial;
      (:) value rest ->
        ST.bindE (denseCommon state initial value) (\next -> denseCommonFold state next rest)
    };
  densePermissionChildren :: forall s. Int ->
                                       STArray s (Maybe Int) ->
                                       STArray s ([] Int) -> [] ((,) Int Node) -> ST s ();
  densePermissionChildren low binding descendants values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind
          (case entry of {
             (,) n v ->
               if equalFlag (flag v) Rigid
               then stReturn ()
               else stBind (readDense low binding n)
                      (\parent ->
                         case parent of {
                           Nothing -> stReturn ();
                           Just b ->
                             stBind (readDense low descendants b)
                               (\previous -> writeDense low descendants b ((:) n previous))
                         })
           })
          (\ignored -> densePermissionChildren low binding descendants rest)
    };
  denseCheckMergeRest :: forall s. Int ->
                                   STArray s (Maybe Int) ->
                                   DensePermissions s ->
                                   Int -> [] Int -> ST s (Either String ());
  denseCheckMergeRest low raised permissions first values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (stBind (readDense low raised first)
             (\a ->
                stBind (readDense low raised entry)
                  (\b ->
                     if L.not (equalMaybeInt a b)
                     then ST.pureE ()
                     else stBind (densePermission permissions first)
                            (\pa ->
                               if equalPermission pa Red
                               then ST.failE "cannot merge distinct protected type variables"
                               else stBind (densePermission permissions entry)
                                      (\pb ->
                                         ST.check (L.not (equalPermission pb Red))
                                           "cannot merge distinct protected type variables")))))
          (\ignored -> denseCheckMergeRest low raised permissions first rest)
    }
}
