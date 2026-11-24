-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ClassDemand where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntTree as IT;

  -- Frames denote RHS abstraction regions, not the entire scope of a let.
  -- A child finishes before its parent; an instantiated binding finishes
  -- before the receiving region. Completed siblings use this same order.
  data Frame = Frame Int (Maybe Int) Int;
  data Seed = Seed Int String Int;
  data Use = Use Int Int Int;
  data Demand = Empty | SeedNode Int | UnionNodes ([] Int) |
                RefNode Int | InstantiateNode Int Int;
  -- Origins retain the whole path as a DAG. In particular, two uses of h
  -- inside j remain distinct when both requirements are instantiated at k.
  data Origin = SeedOrigin Int | InstantiatedOrigin Int Int;
  data Slot = Slot Int String Int Origin;
  -- Allocation owns its supply; container cardinality is not an identity.
  data Universe = Universe Int (IntMap Slot) (IntMap Int) (IntMap (IntMap Int)) |
    InheritedUniverse Int (IntMap Slot) (IntMap Int) (IntMap IntSet) |
    SingleCopyUniverse Int (IntMap Slot) (IntMap Int) Int (IntMap Int) (IntMap IntSet);
  data Plan = Plan Universe (IntMap IntSet) Int;
  data Discovery = Discovery Universe (IntMap IntSet) ([] ((,) Int Int));

  frameId :: Frame -> Int;
  frameId (Frame identity _ _) = identity;
  frameParent :: Frame -> Maybe Int;
  frameParent (Frame _ parent _) = parent;
  frameFinish :: Frame -> Int;
  frameFinish (Frame _ _ finish) = finish;
  seedId :: Seed -> Int;
  seedId (Seed identity _ _) = identity;
  seedClass :: Seed -> String;
  seedClass (Seed _ name _) = name;
  seedOwner :: Seed -> Int;
  seedOwner (Seed _ _ owner) = owner;
  useId :: Use -> Int;
  useId (Use identity _ _) = identity;
  useBinding :: Use -> Int;
  useBinding (Use _ binding _) = binding;
  useReceiver :: Use -> Int;
  useReceiver (Use _ _ receiver) = receiver;
  slotId :: Slot -> Int;
  slotId (Slot identity _ _ _) = identity;
  classOf :: Slot -> String;
  classOf (Slot _ name _ _) = name;
  ownerOf :: Slot -> Int;
  ownerOf (Slot _ _ owner _) = owner;
  originOf :: Slot -> Origin;
  originOf (Slot _ _ _ origin) = origin;
  universeSlots :: Universe -> IntMap Slot;
  universeSlots (Universe _ slots _ _) = slots;
  universeSlots (InheritedUniverse _ slots _ _) = slots;
  universeSlots (SingleCopyUniverse _ slots _ _ _ _) = slots;
  universeSeeds :: Universe -> IntMap Int;
  universeSeeds (Universe _ _ seeds _) = seeds;
  universeSeeds (InheritedUniverse _ _ seeds _) = seeds;
  universeSeeds (SingleCopyUniverse _ _ seeds _ _ _) = seeds;
  universeTransitions :: Universe -> IntMap (IntMap Int);
  universeTransitions (Universe _ _ _ transitions) = transitions;
  universeTransitions (InheritedUniverse _ _ _ transitions) = IM.map identityMappings transitions;
  universeTransitions (SingleCopyUniverse _ _ _ use copies inherited) =
    IM.insertWith IM.union use copies (IM.map identityMappings inherited);
  identityMappings inputs =
    IM.fromDistinctAscList (map (\slot -> (,) slot slot) (IS.toAscList inputs));
  nextSlot :: Universe -> Int;
  nextSlot (Universe next _ _ _) = next;
  nextSlot (InheritedUniverse next _ _ _) = next;
  nextSlot (SingleCopyUniverse next _ _ _ _ _) = next;
  emptyUniverse :: Universe;
  emptyUniverse = Universe 0 IM.empty IM.empty IM.empty;
  advanceSlot :: Int -> Int;
  advanceSlot next =
    if next < 0 then panic "identity supply exhausted" else advanceIdentity next 1;
  planUniverse :: Plan -> Universe;
  planUniverse (Plan universe _ _) = universe;
  nodeSets :: Plan -> IntMap IntSet;
  nodeSets (Plan _ values _) = values;
  universeSize :: Plan -> Int;
  universeSize plan = IM.size (universeSlots (planUniverse plan));
  saturationUpdates :: Plan -> Int;
  saturationUpdates (Plan _ _ updates) = updates;

  require :: forall a. String -> Int -> IntMap a -> Either String a;
  require label identity values =
    case IM.lookup identity values of {
      Nothing -> Left ("class demand: unknown " ++ (label ++ (" " ++ showInt identity)));
      Just value -> Right value
    };
  slotsAt :: Plan -> Int -> Either String ([] Int);
  slotsAt plan identity = mapEither IS.toAscList (require "demand node" identity (nodeSets plan));
  slotAt :: Plan -> Int -> Either String Slot;
  slotAt plan identity = require "slot" identity (universeSlots (planUniverse plan));
  slotClass :: Plan -> Int -> Either String String;
  slotClass plan identity = mapEither classOf (slotAt plan identity);
  slotOwner :: Plan -> Int -> Either String Int;
  slotOwner plan identity = mapEither ownerOf (slotAt plan identity);
  slotOrigin :: Plan -> Int -> Either String Origin;
  slotOrigin plan identity = mapEither originOf (slotAt plan identity);
  seedSlot :: Plan -> Int -> Either String Int;
  seedSlot plan identity = require "seed" identity (universeSeeds (planUniverse plan));
  instantiateIn :: Universe -> Int -> Int -> Either String Int;
  instantiateIn universe use slot = case universe of {
    Universe _ _ _ transitions -> do {
      mapping <- require "reachable instantiation" use transitions;
      require "instantiation input slot" slot mapping
    };
    InheritedUniverse _ _ _ transitions -> inheritedInput transitions use slot;
    SingleCopyUniverse _ _ _ copying copies inherited ->
      if use /= copying then inheritedInput inherited use slot
      else case IM.lookup slot copies of {
        Just target -> Right target;
        Nothing -> let { inputs = IM.findWithDefault IS.empty use inherited } in
          checkInheritedInput inputs slot
      }
  };
  inheritedInput transitions use slot = do {
    inputs <- require "reachable instantiation" use transitions;
    checkInheritedInput inputs slot
  };
  checkInheritedInput inputs slot = do {
    ensure (IS.member slot inputs) ("class demand: unknown instantiation input slot " ++ showInt slot);
    Right slot
  };
  instantiateSlot :: Plan -> Int -> Int -> Either String Int;
  instantiateSlot plan use slot = instantiateIn (planUniverse plan) use slot;
  selectedSlotCount :: Plan -> [] Int -> Either String Int;
  selectedSlotCount plan nodes =
    do {
      values <- mapM (\n -> require "demand node" n (nodeSets plan)) nodes;
      Right (IS.size (IS.unions values))
    };
  transitionCount :: Plan -> Int;
  transitionCount plan = case planUniverse plan of {
    Universe _ _ _ transitions -> IM.foldl (\count mapping -> count + IM.size mapping) 0 transitions;
    InheritedUniverse _ _ _ transitions -> IM.foldl (\count inputs -> count + IS.size inputs) 0 transitions;
    SingleCopyUniverse _ _ _ _ copies inherited -> IM.foldl
      (\count inputs -> count + IS.size inputs) (IM.size copies) inherited
  };

  dependencies :: Demand -> [] Int;
  dependencies demand =
    case demand of {
      Empty -> [];
      SeedNode _ -> [];
      UnionNodes nodes -> nodes;
      RefNode node -> (:) node [];
      InstantiateNode _ node -> (:) node []
    };
  validateFrame :: IntMap Frame -> Frame -> Either String ();
  validateFrame frames frame =
    do {
      ensure (frameId frame >= 0 && frameFinish frame >= 0)
        "class demand: negative frame identity or finish rank";
      case frameParent frame of {
        Nothing -> Right ();
        Just identity ->
          do {
            parent <- require "parent frame" identity frames;
            ensure (frameFinish parent > frameFinish frame)
              "class demand: parent frame must finish after its child"
          }
      }
    };
  validateSeed :: IntMap Frame -> Seed -> Either String ();
  validateSeed frames seed =
    do {
      ensure (seedId seed >= 0) "class demand: negative seed identity";
      ensure (not (eqString (seedClass seed) "")) "class demand: empty class identity";
      require "seed owner frame" (seedOwner seed) frames;
      Right ()
    };
  validateUse :: IntMap Frame -> Use -> Either String ();
  validateUse frames use =
    do {
      ensure (useId use >= 0) "class demand: negative use identity";
      binding <- require "binding frame" (useBinding use) frames;
      receiver <- require "receiver frame" (useReceiver use) frames;
      ensure (frameFinish receiver > frameFinish binding)
        "class demand: instantiation receiver must finish after its binding"
    };
  validateNode :: IntMap Seed -> IntMap Use -> IntMap Demand ->
                  (,) Int Demand -> Either String ();
  validateNode seeds uses nodes ((,) identity demand) =
    do {
      ensure (identity >= 0) "class demand: negative demand node identity";
      mapM (\n -> require "demand dependency" n nodes) (dependencies demand);
      case demand of {
        SeedNode seed -> do { require "seed" seed seeds; Right () };
        InstantiateNode use _ -> do { require "use" use uses; Right () };
        _ -> Right ()
      }
    };
  -- Parent ranks strictly increase, so this walk is acyclic after validation.
  beneath :: IntMap Frame -> Int -> Int -> Bool;
  beneath frames owner binding =
    if owner == binding
    then True
    else case frameParent (IM.get owner frames) of {
      Nothing -> False;
      Just parent -> beneath frames parent binding
    };
  dependentNodes :: IntMap Demand -> IntMap IntSet;
  dependentNodes nodes =
    IM.foldlWithKey
      (\result output demand ->
         foldlStrict
           (\current input -> IM.insertWith IS.union input (IS.singleton output) current)
           result (dependencies demand))
      (IM.map (\_ -> IS.empty) nodes) nodes;
  allocateSeeds :: IntMap Seed -> Universe;
  allocateSeeds seeds =
    IM.foldl
      (\universe seed ->
         let { identity = nextSlot universe; next = advanceSlot identity } in
         seq next (Universe next
           (IM.insert identity
             (Slot identity (seedClass seed) (seedOwner seed) (SeedOrigin (seedId seed))) (universeSlots universe))
           (IM.insert (seedId seed) identity (universeSeeds universe)) IM.empty))
      emptyUniverse seeds;
  -- Discovery follows actual seed/node paths. It does not form the unrelated
  -- seed-by-use Cartesian product, which would explode for unused local lets.
  -- A copied token's owner rank strictly increases. Identity transports never
  -- create tokens. With finite uses/ranks, token paths are finite; with finite
  -- demand nodes, each (node, slot) fact is enqueued at most once.
  -- A changing path has at most frameCount - 1 steps, branching over finitely
  -- many syntactic uses. Thus seedCount * sum(useCount ^ k) for those depths
  -- is a coarse finite bound; the worst case is deliberately exponential,
  -- not an unproved polynomial claim. Reachability avoids unrelated paths.
  addFact :: Int -> Int -> Discovery -> Discovery;
  addFact node slot (Discovery universe values pending) =
    let { previous = IM.get node values } in
    if IS.member slot previous
    then Discovery universe values pending
    else Discovery universe (IM.insert node (IS.insert slot previous) values)
      ((:) ((,) node slot) pending);
  allocateAt :: IntMap Frame -> Use -> Int -> Universe -> Either String ((,) Int Universe);
  allocateAt frames use input universe =
    case universe of {
      InheritedUniverse next slots seeds _ ->
        allocateAt frames use input (Universe next slots seeds (universeTransitions universe));
      SingleCopyUniverse next slots seeds _ _ _ ->
        allocateAt frames use input (Universe next slots seeds (universeTransitions universe));
      Universe next slots seeds transitions ->
        let { previous = IM.findWithDefault IM.empty (useId use) transitions } in
        case IM.lookup input previous of {
          Just output -> Right ((,) output universe);
          Nothing ->
            do {
              slot <- require "discovery slot" input slots;
              ensure (beneath frames (ownerOf slot) (useBinding use) ||
                      beneath frames (useBinding use) (ownerOf slot))
                "class demand: unrelated owner escaped into a binding interface";
              if beneath frames (ownerOf slot) (useBinding use)
              then do {
                let { owner = IM.get (ownerOf slot) frames };
                let { receiver = IM.get (useReceiver use) frames };
                ensure (frameFinish receiver > frameFinish owner)
                  "class demand: origin copy did not increase its owner finish rank";
                let { output = next; following = advanceSlot next };
                let {
                  fresh = Slot output (classOf slot) (useReceiver use)
                    (InstantiatedOrigin (useId use) input)
                };
                seq following (Right ((,) output
                  (Universe following (IM.insert output fresh slots) seeds
                    (IM.insert (useId use) (IM.insert input output previous) transitions))))
              }
              else Right ((,) input
                (Universe next slots seeds
                  (IM.insert (useId use) (IM.insert input input previous) transitions)))
            }
        }
    };
  discoverDependent :: IntMap Frame -> IntMap Use -> IntMap Demand ->
                       Int -> Discovery -> Int -> Either String Discovery;
  discoverDependent frames uses nodes slot state output =
    case state of {
      Discovery universe values pending ->
        do {
          transported <-
            case IM.get output nodes of {
              InstantiateNode use _ -> allocateAt frames (IM.get use uses) slot universe;
              RefNode _ -> Right ((,) slot universe);
              UnionNodes _ -> Right ((,) slot universe);
              _ -> Left "class demand: invalid reverse dependency"
            };
          case transported of {
            (,) target next -> Right (addFact output target (Discovery next values pending))
          }
        }
    };
  discover :: IntMap Frame -> IntMap Use -> IntMap Demand -> IntMap IntSet ->
              [] ((,) Int Int) -> Discovery -> Either String Discovery;
  discover frames uses nodes dependents front state =
    case front of {
      [] ->
        case state of {
          Discovery universe values [] -> Right state;
          Discovery universe values pending ->
            discover frames uses nodes dependents (reverse pending)
              (Discovery universe values [])
        };
      (:) ((,) node slot) rest ->
        do {
          next <- foldM (discoverDependent frames uses nodes slot) state
            (IS.toAscList (IM.get node dependents));
          discover frames uses nodes dependents rest next
        }
    };
  discoverUniverse :: IntMap Frame -> IntMap Seed -> IntMap Use -> IntMap Demand ->
                      IntMap IntSet -> Either String Discovery;
  discoverUniverse frames seeds uses nodes dependents =
    let { universe = allocateSeeds seeds } in
    let {
      initial = IM.foldlWithKey
        (\state node demand ->
           case demand of {
             SeedNode seed -> addFact node (IM.get seed (universeSeeds universe)) state;
             _ -> state
           })
        (Discovery universe (IM.map (\_ -> IS.empty) nodes) []) nodes
    } in
    discover frames uses nodes dependents [] initial;

  -- A reference or union with a single productive predecessor forwards each
  -- incoming slot exactly once. Its final set is its predecessor's set. A
  -- productive chain of such aliases ends at a seed, merge or instantiation:
  -- a cycle containing only aliases has no incoming seed.
  productiveNodes dependents pending seen =
    if IS.null pending then seen else let {
      reached = IS.union seen pending;
      next = IS.foldl (\acc n -> IS.union acc (IM.get n dependents)) IS.empty pending
    } in productiveNodes dependents (IS.difference next reached) reached;
  forwardedInput productive node demand =
    if not (IS.member node productive) then Nothing else case demand of {
      RefNode input -> Just input;
      UnionNodes inputs -> let {
        active = IS.fromList (filter (\input -> IS.member input productive) inputs)
      } in if IS.size active == 1 then Just (IS.findMin active) else Nothing;
      _ -> Nothing
    };
  -- The FIFO carries the outgoing edges themselves. A discovered sink has
  -- no later effect; its reachable set is still recorded before this point.
  data DiscoveryEdge = ForwardFact ([] DiscoveryEdge) | MergeFact Int ([] DiscoveryEdge)
    | TransportFact Int Use ([] DiscoveryEdge);
  data DiscoveryWork = DiscoveryWork Int ([] DiscoveryEdge);
  enqueue edges slot pending = case edges of {
    [] -> pending; _ -> (:) (DiscoveryWork slot edges) pending
  };
  -- Each row buffers its last touched bitmap word. Older words remain in
  -- the persistent tree. Revisiting a word resumes from its existing bits.
  data DiscoveryRow = DiscoveryRow Int Int IntSetTree;
  frozenRow (DiscoveryRow prefix bits older) =
    if bits == 0 then IS.wrap older else IS.wrap (IS.insertBM prefix bits older);
  seedRow slot = DiscoveryRow (IT.prefixOf slot) (IT.bitmapOf slot) IntSetNil;
  insertRowSlot slot (DiscoveryRow prefix bits older) = let {
    key = IT.prefixOf slot;
    current = if key == prefix then bits else IS.bitmapAt key older;
    combined = orInt current (IT.bitmapOf slot)
  } in if current == combined then Nothing else let {
    saved = if key == prefix || bits == 0 then older else IS.insertBM prefix bits older
  } in seq key (seq combined (seq saved (Just (DiscoveryRow key combined saved))));
  insertSetSlot slot previous = if IS.member slot previous then Nothing else Just (IS.insert slot previous);
  data DiscoveryIndex = DiscoveryIndex Int (IntMap Int) (IntMap Demand);
  discoverValidated :: IntMap Frame -> IntMap Seed -> IntMap Use -> IntMap Demand ->
                       IntMap IntSet -> Either String Discovery;
  discoverValidated frames seeds uses nodes dependents =
    case (,) (IM.lookupMin nodes) (IM.lookupMax nodes) of {
      (,) (Just ((,) low _)) (Just ((,) high _)) -> let {
        span = high - low;
        count = IM.size nodes
      } in if low >= 0 && span >= 0 && quotInt span 4 < count && span < 1152921504606846975
        then runST (stBind (newSTArray (span + 1) (DiscoveryRow 0 0 IntSetNil))
          (\rows -> let {
            universe = allocateSeeds seeds;
            facts = IM.foldrWithKey (\node demand rest -> case demand of {
              SeedNode seed -> (:) ((,) node (IM.get seed (universeSeeds universe))) rest;
              _ -> rest
            }) [] nodes;
            productive = productiveNodes dependents (seedWork nodes) IS.empty;
            aliases = IM.mapMaybeWithKey (forwardedInput productive) nodes;
            edge output = let { following = IM.get output edges } in
              if IM.member output aliases then ForwardFact following else
              case IM.get output nodes of {
                InstantiateNode use _ -> TransportFact output (IM.get use uses) following;
                _ -> MergeFact output following
              };
            edges = IM.map (\targets -> map edge (IS.toAscList targets)) dependents;
            index = DiscoveryIndex low aliases nodes;
            work = foldr (\((,) node slot) rest -> enqueue (IM.get node edges) slot rest) [] facts
          } in denseSeedFactsWith seedRow low rows facts
            (denseDiscoverWith frozenRow insertRowSlot frames index rows universe work [])))
        else discoverUniverse frames seeds uses nodes dependents;
      _ -> discoverUniverse frames seeds uses nodes dependents
    };
  denseSeedFacts :: forall s a. Int -> STArray s IntSet -> [] ((,) Int Int) -> ST s a -> ST s a;
  denseSeedFacts = denseSeedFactsWith IS.singleton;
  denseSeedFactsWith :: forall s a row. (Int -> row) -> Int -> STArray s row -> [] ((,) Int Int) -> ST s a -> ST s a;
  denseSeedFactsWith seed low rows facts done =
    case facts of {
      [] -> done;
      (:) ((,) node slot) rest -> stBind (writeSTArray rows (node - low) (seed slot))
        (\_ -> denseSeedFactsWith seed low rows rest done)
    };
  denseDiscover :: forall s. IntMap Frame -> DiscoveryIndex -> STArray s IntSet -> Universe ->
                   [] DiscoveryWork -> [] DiscoveryWork -> ST s (Either String Discovery);
  denseDiscover = denseDiscoverWith (\a -> a) insertSetSlot;
  denseDiscoverWith :: forall s row. (row -> IntSet) -> (Int -> row -> Maybe row) ->
    IntMap Frame -> DiscoveryIndex -> STArray s row -> Universe -> [] DiscoveryWork -> [] DiscoveryWork ->
    ST s (Either String Discovery);
  denseDiscoverWith freeze add frames index@(DiscoveryIndex low aliases nodes) rows universe front pending =
    case front of {
      [] -> case pending of {
        [] -> stBind (freezeSTArray rows) (\at -> let {
          stored node = case IM.lookup node aliases of {
            Nothing -> freeze (at (node - low)); Just parent -> stored parent
          }
        } in stReturn (Right (Discovery universe (IM.mapWithKey (\n _ -> stored n) nodes) [])));
        _ -> denseDiscoverWith freeze add frames index rows universe (reverse pending) []
      };
      (:) (DiscoveryWork slot edges) rest ->
        denseDependentsWith freeze add frames index rows universe rest pending slot edges
    };
  denseDependents :: forall s. IntMap Frame -> DiscoveryIndex -> STArray s IntSet -> Universe ->
                     [] DiscoveryWork -> [] DiscoveryWork -> Int -> [] DiscoveryEdge ->
                     ST s (Either String Discovery);
  denseDependents = denseDependentsWith (\a -> a) insertSetSlot;
  denseDependentsWith :: forall s row. (row -> IntSet) -> (Int -> row -> Maybe row) ->
    IntMap Frame -> DiscoveryIndex -> STArray s row -> Universe -> [] DiscoveryWork -> [] DiscoveryWork ->
    Int -> [] DiscoveryEdge -> ST s (Either String Discovery);
  denseDependentsWith freeze add frames index@(DiscoveryIndex low _ _) rows universe rest pending slot outputs =
    case outputs of {
      [] -> denseDiscoverWith freeze add frames index rows universe rest pending;
      (:) edge remaining -> let {
        continue next work = denseDependentsWith freeze add frames index rows next rest work slot remaining;
        record output target next following = stBind (readSTArray rows (output - low))
          (\previous -> case add target previous of {
            Nothing -> continue next pending;
            Just updated -> seq updated (stBind (writeSTArray rows (output - low) updated)
              (\_ -> continue next (enqueue following target pending)))
          })
      } in case edge of {
        ForwardFact following -> continue universe (enqueue following slot pending);
        MergeFact output following -> record output slot universe following;
        TransportFact output use following -> case allocateAt frames use slot universe of {
          Left err -> stReturn (Left err);
          Right ((,) target next) -> record output target next following
        }
      }
    };

  -- This phase receives an immutable, already allocated universe. Every
  -- operation below is set union or transition lookup: no new origin exists
  -- in the fixed-point loop, and missing preallocation is an explicit error.
  evaluate :: Universe -> IntMap IntSet -> Demand -> Either String IntSet;
  evaluate universe values demand =
    case demand of {
      Empty -> Right IS.empty;
      SeedNode seed ->
        do {
          slot <- require "seed" seed (universeSeeds universe);
          Right (IS.singleton slot)
        };
      UnionNodes nodes -> Right (IS.unions (map (\n -> IM.get n values) nodes));
      RefNode node -> Right (IM.get node values);
      InstantiateNode use node ->
        do {
          targets <- mapM (instantiateIn universe use) (IS.toAscList (IM.get node values));
          Right (IS.fromList targets)
        }
    };
  saturate :: Universe -> IntSet -> IntMap Demand -> IntMap IntSet -> IntSet ->
              IntMap IntSet -> Int -> Either String ((,) (IntMap IntSet) Int);
  saturate universe = saturateWith (evaluate universe);
  saturateWith :: (IntMap IntSet -> Demand -> Either String IntSet) ->
    IntSet -> IntMap Demand -> IntMap IntSet -> IntSet -> IntMap IntSet -> Int ->
    Either String ((,) (IntMap IntSet) Int);
  saturateWith evaluateNode admissible nodes dependents pending values updates =
    case IS.minView pending of {
      Nothing -> Right ((,) values updates);
      Just ((,) identity rest) ->
        do {
          result <- evaluateNode values (IM.get identity nodes);
          let { previous = IM.get identity values };
          ensure (IS.isSubsetOf previous result)
            "class demand: nonmonotone demand equation";
          if IS.eqIntSet previous result
          then saturateWith evaluateNode admissible nodes dependents rest values updates
          else do {
            ensure (IS.isSubsetOf result admissible)
              "class demand: saturation escaped its immutable universe";
            let { next = IM.insert identity result values };
            let { work = IS.union rest (IM.get identity dependents) };
            saturateWith evaluateNode admissible nodes dependents work next (updates + 1)
          }
        }
    };
  -- Without instantiation the seed universe is already complete. If each
  -- input precedes its output, the ascending saturation worklist visits
  -- every node once, after all its inputs have reached their final sets.
  -- Keep those sets shared instead of forwarding each slot along every edge.
  orderedEquation node demand = case demand of {
    InstantiateNode _ _ -> False;
    _ -> all (\input -> input < node) (dependencies demand)
  };
  solveOrdered seeds nodes = let {
    universe = allocateSeeds seeds;
    step ((,) values updates) ((,) node demand) = do {
      result <- evaluate universe values demand;
      let { next = IM.insert node result values };
      let { count = if IS.null result then updates else updates + 1 };
      seq next (seq count (Right ((,) next count)))
    }
  } in do {
    (,) values updates <- foldM step ((,) IM.empty 0) (IM.toAscList nodes);
    Right (Plan universe values updates)
  };
  -- An instantiation only copies origins owned by its binding or its subtree.
  -- If every seed owner strictly encloses every binding that is instantiated,
  -- all transports are identities and no other owner can be created. Check
  -- distinct frames, regardless of the number of occurrences or seed slots.
  inheritsEveryOrigin :: IntMap Frame -> IntMap Seed -> IntMap Use -> IntMap Demand -> Bool;
  inheritsEveryOrigin frames seeds uses nodes = let {
    owners = IS.toAscList (IM.foldl (\seen seed -> IS.insert (seedOwner seed) seen) IS.empty seeds);
    bindings = IM.foldl (\seen demand -> case demand of {
      InstantiateNode use _ -> IS.insert (useBinding (IM.get use uses)) seen;
      _ -> seen
    }) IS.empty nodes
  } in IS.foldr (\binding rest ->
    all (\owner -> owner /= binding && beneath frames binding owner) owners && rest) True bindings;
  -- Only seeds can change on empty inputs. Each productive visit schedules
  -- every dependent, so the omitted initial visits cannot affect the update
  -- order or count, even when requirements flow through a cycle.
  seedWork :: IntMap Demand -> IntSet;
  seedWork nodes = IS.fromDistinctAscList (IM.foldrWithKey (\n d rest -> case d of {
    SeedNode _ -> (:) n rest; _ -> rest
  }) [] nodes);
  solveInherited :: IntMap Seed -> IntMap Demand -> IntMap IntSet -> Either String Plan;
  solveInherited seeds nodes dependents = do {
    let { universe = allocateSeeds seeds };
    let { equations = IM.map (\demand -> case demand of {
      InstantiateNode _ input -> RefNode input;
      _ -> demand
    }) nodes };
    (,) values updates <- saturate universe (IM.keysSet (universeSlots universe))
      equations dependents (seedWork nodes) (IM.map (\_ -> IS.empty) nodes) 0;
    -- Every reachable input set is final. Share it across the uses of the
    -- node. A use may occur at several nodes in the general planner API, so
    -- keep the union of its inputs, omitting uses with no reachable slot.
    let { transitions = IM.foldl (\seen demand -> case demand of {
      InstantiateNode use input -> let { slots = IM.get input values } in
        if IS.null slots then seen else IM.insertWith IS.union use slots seen;
      _ -> seen
    }) IM.empty nodes };
    Right (Plan (InheritedUniverse (nextSlot universe) (universeSlots universe)
      (universeSeeds universe) transitions) values updates)
  };
  -- For the single copying output, classifying only owners tells us exactly
  -- which seed owners reach its input. The actual per-slot final calculation
  -- still uses the same ordered worklist.
  copySites :: IntMap Frame -> IntMap Seed -> IntMap Use -> IntMap Demand ->
    IntMap IntSet -> Maybe ([] Int);
  copySites frames seeds uses nodes dependents = let {
    bad = 0 - 1;
    transport use owner = if owner < 0 then owner
      else if beneath frames owner (useBinding use) then useReceiver use
      else if beneath frames (useBinding use) owner then owner else bad;
    evaluateOwners values demand = case demand of {
      Empty -> IS.empty;
      SeedNode seed -> IS.singleton (seedOwner (IM.get seed seeds));
      UnionNodes inputs -> IS.unions (map (\n -> IM.get n values) inputs);
      RefNode input -> IM.get input values;
      InstantiateNode use input -> IS.map (transport (IM.get use uses)) (IM.get input values)
    };
    fixed pending values = case IS.minView pending of {
      Nothing -> values;
      Just ((,) output rest) -> let { next = evaluateOwners values (IM.get output nodes) } in
        if IS.eqIntSet next (IM.get output values) then fixed rest values
        else fixed (IS.union rest (IM.get output dependents)) (IM.insert output next values)
    };
    owners = fixed (seedWork nodes) (IM.map (\_ -> IS.empty) nodes)
  } in if IM.foldr (\owners found -> IS.member bad owners || found) False owners then Nothing
    else Just (IM.foldrWithKey (\n demand rest -> case demand of {
      InstantiateNode use input -> if IS.foldr (\owner exists ->
        beneath frames owner (useBinding (IM.get use uses)) || exists)
        False (IM.get input owners) then (:) n rest else rest;
      _ -> rest
    }) [] nodes);
  -- Walk backwards from the sole copying node's input. Once a seed passes
  -- that node it has another identity and cannot be that seed again. The old
  -- FIFO walk therefore first sees each copied seed in this distance order,
  -- breaking ties by the initial demand node's ascending identity.
  seedDistances :: IntMap Demand -> Int -> Int -> IntMap Int;
  seedDistances nodes copying input = let {
    walk depth pending distances = if IS.null pending then distances else let {
      measured = IS.foldl (\acc node -> IM.insert node depth acc) distances pending;
      advance rest node = foldlStrict (\seen parent ->
        if parent == copying || IM.member parent measured then seen else IS.insert parent seen)
        rest (dependencies (IM.get node nodes));
      next = IS.foldl advance IS.empty pending
    } in walk (depth + 1) next measured
  } in walk 0 (IS.singleton input) IM.empty;
  solveSingleCopy :: IntMap Frame -> IntMap Seed -> IntMap Use -> IntMap Demand ->
    IntMap IntSet -> Int -> Either String Plan;
  solveSingleCopy frames seeds uses nodes dependents copying =
    case IM.get copying nodes of {
      InstantiateNode site input -> do {
        let {
          use = IM.get site uses;
          distances = seedDistances nodes copying input;
          candidates = IM.foldrWithKey (\node demand rest -> case demand of {
            SeedNode seed -> case IM.lookup node distances of {
              Just depth -> if beneath frames (seedOwner (IM.get seed seeds)) (useBinding use)
                then (:) ((,,) depth node seed) rest else rest;
              Nothing -> rest
            };
            _ -> rest
          }) [] nodes;
          before ((,,) distance node _) ((,,) other peer _) =
            if distance == other then compareInt node peer else compareInt distance other;
          copy universe ((,,) _ _ seed) = mapEither snd
            (allocateAt frames use (IM.get seed (universeSeeds universe)) universe);
          equations = IM.mapWithKey (\output demand -> case demand of {
            InstantiateNode _ n -> if output == copying then demand else RefNode n;
            _ -> demand
          }) nodes
        };
        universe <- foldM copy (allocateSeeds seeds) (sortBy before candidates);
        mapping <- require "reachable instantiation" site (universeTransitions universe);
        let {
          evaluateNode values demand = case demand of {
            InstantiateNode _ n -> let { inputs = IM.get n values } in
              Right (IM.foldlWithKey (\slots slot target -> if IS.member slot inputs
                then IS.insert target (IS.delete slot slots) else slots) inputs mapping);
            _ -> evaluate universe values demand
          }
        };
        (,) values updates <- saturateWith evaluateNode (IM.keysSet (universeSlots universe))
          equations dependents (seedWork nodes) (IM.map (\_ -> IS.empty) nodes) 0;
        let {
          copyInputs = IM.keysSet mapping;
          inherited = IM.foldl (\seen demand -> case demand of {
            InstantiateNode use n -> let {
              inputs = IM.get n values;
              live = if use == site then IS.difference inputs copyInputs else inputs
            } in if IS.null live then seen else IM.insertWith IS.union use live seen;
            _ -> seen
          }) IM.empty nodes
        };
        Right (Plan (SingleCopyUniverse (nextSlot universe) (universeSlots universe)
          (universeSeeds universe) site mapping inherited) values updates)
      };
      _ -> Left "class demand: missing copying instantiation"
    };
  solve :: [] Frame -> [] Seed -> [] Use -> IntMap Demand -> Either String Plan;
  solve frameList seedList useList nodes =
    do {
      let { frames = IM.fromList (map (\f -> (,) (frameId f) f) frameList) };
      let { seeds = IM.fromList (map (\s -> (,) (seedId s) s) seedList) };
      let { uses = IM.fromList (map (\u -> (,) (useId u) u) useList) };
      ensure (IM.size frames == length frameList) "class demand: duplicate frame identity";
      ensure (IM.size seeds == length seedList) "class demand: duplicate seed identity";
      ensure (IM.size uses == length useList) "class demand: duplicate use identity";
      ensure (IS.size (IS.fromList (map frameFinish frameList)) == length frameList)
        "class demand: duplicate frame finish rank";
      mapM (validateFrame frames) (IM.elems frames);
      mapM (validateSeed frames) (IM.elems seeds);
      mapM (validateUse frames) (IM.elems uses);
      mapM (validateNode seeds uses nodes) (IM.toAscList nodes);
      -- With no validated seed there can be no reachable fact or origin.
      -- Keep every guard above, including dependency/use validation, but
      -- avoid constructing reverse edges and replaying the empty fixed point.
      -- Retain every demand-node key, even for disconnected empty components.
      if IM.null seeds
      then Right (Plan emptyUniverse
        (IM.map (\_ -> IS.empty) nodes) 0)
      else if IM.foldrWithKey (\n d rest -> orderedEquation n d && rest) True nodes
      then solveOrdered seeds nodes
      else do {
        let { dependents = dependentNodes nodes };
        if inheritsEveryOrigin frames seeds uses nodes
        then solveInherited seeds nodes dependents
        else case copySites frames seeds uses nodes dependents of {
          Just [] -> solveInherited seeds nodes dependents;
          Just [only] -> solveSingleCopy frames seeds uses nodes dependents only;
          _ -> do {
            Discovery universe reached _ <- discoverValidated frames seeds uses nodes dependents;
            (,) values updates <- saturate universe (IM.keysSet (universeSlots universe))
              nodes dependents (seedWork nodes) (IM.map (\_ -> IS.empty) nodes) 0;
            ensure (IM.eqIntMap IS.eqIntSet reached values)
              "class demand: preallocation and immutable saturation disagree";
            Right (Plan universe values updates)
          }
        }
      }
    }
}
