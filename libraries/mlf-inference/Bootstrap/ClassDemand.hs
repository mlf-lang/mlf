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
  data Universe = Universe Int (IntMap Slot) (IntMap Int) (IntMap (IntMap Int));
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
  universeSeeds :: Universe -> IntMap Int;
  universeSeeds (Universe _ _ seeds _) = seeds;
  universeTransitions :: Universe -> IntMap (IntMap Int);
  universeTransitions (Universe _ _ _ transitions) = transitions;
  nextSlot :: Universe -> Int;
  nextSlot (Universe next _ _ _) = next;
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
  instantiateIn universe use slot =
    do {
      mapping <- require "reachable instantiation" use (universeTransitions universe);
      require "instantiation input slot" slot mapping
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
  transitionCount plan =
    IM.foldl (\count mapping -> count + IM.size mapping) 0
      (universeTransitions (planUniverse plan));

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
         case universe of {
           Universe identity slots origins transitions ->
             let { next = advanceSlot identity } in
             seq next (Universe next
               (IM.insert identity
                 (Slot identity (seedClass seed) (seedOwner seed) (SeedOrigin (seedId seed))) slots)
               (IM.insert (seedId seed) identity origins) transitions)
         })
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
  saturate universe admissible nodes dependents pending values updates =
    case IS.minView pending of {
      Nothing -> Right ((,) values updates);
      Just ((,) identity rest) ->
        do {
          result <- evaluate universe values (IM.get identity nodes);
          let { previous = IM.get identity values };
          ensure (IS.isSubsetOf previous result)
            "class demand: nonmonotone demand equation";
          if IS.eqIntSet previous result
          then saturate universe admissible nodes dependents rest values updates
          else do {
            ensure (IS.isSubsetOf result admissible)
              "class demand: saturation escaped its immutable universe";
            let { next = IM.insert identity result values };
            let { work = IS.union rest (IM.get identity dependents) };
            saturate universe admissible nodes dependents work next (updates + 1)
          }
        }
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
      else do {
        let { dependents = dependentNodes nodes };
        discovered <- discoverUniverse frames seeds uses nodes dependents;
        case discovered of {
          Discovery universe reached _ ->
            do {
              fixed <- saturate universe (IM.keysSet (universeSlots universe))
                nodes dependents (IM.keysSet nodes)
                (IM.map (\_ -> IS.empty) nodes) 0;
              case fixed of {
                (,) values updates ->
                  do {
                    ensure (IM.eqIntMap IS.eqIntSet reached values)
                      "class demand: preallocation and immutable saturation disagree";
                    Right (Plan universe values updates)
                  }
              }
            }
        }
      }
    }
}
