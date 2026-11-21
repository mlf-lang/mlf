-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- The private KeyIndex lookup/insertion below is adapted from Bootstrap.IntMap.
-- Adapted from containers-0.8.1 Data.IntMap.Internal (lazy values).
-- Copyright (c) Daan Leijen 2002; Andriy Palamarchuk 2008; wren romano 2016.
-- BSD-3-Clause; see tools/release/licenses/containers-0.8.1.txt.
-- The Glasgow Haskell Compiler License
--
-- Copyright 2004, The University Court of the University of Glasgow.
-- All rights reserved.
--
-- Redistribution and use in source and binary forms, with or without
-- modification, are permitted provided that the following conditions are met:
--
-- - Redistributions of source code must retain the above copyright notice,
-- this list of conditions and the following disclaimer.
--
-- - Redistributions in binary form must reproduce the above copyright notice,
-- this list of conditions and the following disclaimer in the documentation
-- and/or other materials provided with the distribution.
--
-- - Neither name of the University nor the names of its contributors may be
-- used to endorse or promote products derived from this software without
-- specific prior written permission.
--
-- THIS SOFTWARE IS PROVIDED BY THE UNIVERSITY COURT OF THE UNIVERSITY OF
-- GLASGOW AND THE CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
-- INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
-- FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
-- UNIVERSITY COURT OF THE UNIVERSITY OF GLASGOW OR THE CONTRIBUTORS BE LIABLE
-- FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
-- DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
-- SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
-- CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
-- LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
-- OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
-- DAMAGE.
module Bootstrap.Bitstream (
  Value(..), AtomShapes(..), encodeAtoms, encodeRootsWithAtoms, Limits(..), Entry(..), Symbol(..),
  Tables(..), Layout(..), Cursor(..), Read(..),
  Header(..), Parsed(..), CanonicalTask(..),
  planRootBounded, encodeRootBounded, decodeGraphRootBounded,
  defaultLimits, maxBytes, maxSymbols, maxSymbolBytes, maxTotalSymbolBytes,
  maxNodes, maxEdges, maxDepth, maxExpandedWork, validLimits, magic,
  hasMagicPrefix, hasMagic, matchMagic, entryKind, compareIds, compareEntry,
  charge, boundedLength, boundedLengthAt, scalar, scalarBytes, utf8Size,
  utf8SizeAt, entryEdges, takeIds, plan,
  zigzag, unzigzag, varBytes, referenceWidth, bytesForBits, symbolSize,
  nodeBits, layout, putBits, putVar, putScalar, putText, putSymbols,
  putReferences, putEntry, putEntries, putWords, putHeader, crcNibble,
  crcByte, checksum, checksumAt, encode, encodeChecked, encodeTables,
  returnRead, bindRead, failRead, checkRead, liftEither, getBits, getBitsAt,
  remainingBits, getVar, getVarAt, getNat, finishSection, runSection,
  getHeader, getContinuation, getUtf8, getUtf8At, strictUtf8,
  strictUtf8Checked, getSymbols, getSymbolsAt, parsedEntry, parsedValue,
  parsedDepth, parsedWork, getChildIds, getEntry, buildChildren, buildParsed,
  getNodes, getNodesAt, getRoots, getRootsAt, canonicalGraph, canonicalTasks,
  collectRoots, decode, decodeChecked, decodeTables,
  Graph, GraphNode(..), decodeGraph, decodeGraphWithText, decodeGraphWithGate,
  firstShortTextMatches, graphRoots, graphNodeCount, lookupGraphNode,
  ResourceStats, planMeasured, planGraph, GraphPlan, prepareGraphPlan, prepareGraphPlanWithAtoms, realizeGraphPlan, graphNodeDepth, graphResourceStats, graphExpandedWork,
  resourceBytes, resourceNodes, resourceEdges, resourceSymbols,
  resourceSymbolBytes, resourceDepth, resourceMaxSymbolBytes,
  resourceExpandedNodes, resourceExpandedTextBytes, resourceExpandedWork) where {
  import MLF.Primitive;
  import Bootstrap.Types hiding (Graph(..));
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntTree as KeyBits;
  import qualified Bootstrap.IndexVec as V;

  -- The schema above this layer owns constructor tags and field types. VBits
  -- is an arbitrary Int64 bit pattern, not a nonnegative numeric quantity.
  data Value = VInt Int | VBits Int | VText String | VNode Int ([] Value);
  data Limits = Limits Int Int Int Int Int Int Int Int;
  defaultLimits :: Limits;
  defaultLimits = Limits 268435456 1048576 16777216 134217728
    4194304 16777216 16384 67108864;
  maxBytes :: Limits -> Int;
  maxBytes (Limits x _ _ _ _ _ _ _) = x;
  maxSymbols :: Limits -> Int;
  maxSymbols (Limits _ x _ _ _ _ _ _) = x;
  maxSymbolBytes :: Limits -> Int;
  maxSymbolBytes (Limits _ _ x _ _ _ _ _) = x;
  maxTotalSymbolBytes :: Limits -> Int;
  maxTotalSymbolBytes (Limits _ _ _ x _ _ _ _) = x;
  maxNodes :: Limits -> Int;
  maxNodes (Limits _ _ _ _ x _ _ _) = x;
  maxEdges :: Limits -> Int;
  maxEdges (Limits _ _ _ _ _ x _ _) = x;
  maxDepth :: Limits -> Int;
  maxDepth (Limits _ _ _ _ _ _ x _) = x;
  maxExpandedWork :: Limits -> Int;
  maxExpandedWork (Limits _ _ _ _ _ _ _ x) = x;
  validLimits :: Limits -> Bool;
  validLimits (Limits bytes symbols single total nodes edges depth work) =
    bytes >= 80 && bytes <= 2147483647 &&
    symbols >= 0 && symbols <= 2147483647 &&
    single >= 0 && single <= total && total <= bytes &&
    nodes >= 0 && nodes <= 2147483647 &&
    edges >= 0 && edges <= 2147483647 &&
    depth >= 1 && depth <= 65536 && work >= 0 && work <= 2147483647;
  -- Aggregate root work is an explicit caller policy. Keep it in the
  -- same narrow nonnegative range as the existing codec work limit.
  validRootBudget :: Int -> Bool;
  validRootBudget work = work >= 0 && work <= 2147483647;
  withExpandedWork :: Limits -> Int -> Limits;
  withExpandedWork (Limits bytes symbols single total nodes edges depth _) work =
    Limits bytes symbols single total nodes edges depth work;
  magic :: String;
  magic = "MLFBIN\r\n";
  hasMagicPrefix :: String -> Bool;
  hasMagicPrefix text = stringLength text >= 8 && eqString (stringSlice text 0 8) magic;
  hasMagic :: ByteArray -> IO Bool;
  hasMagic bytes = do {
    size <- lengthByteArray bytes;
    if size < 8 then ioReturn False else matchMagic bytes 0
  };
  matchMagic :: ByteArray -> Int -> IO Bool;
  matchMagic bytes position =
    if position == 8 then ioReturn True else do {
      byte <- readByteArray bytes position;
      if byte == stringCodeAt magic position
      then matchMagic bytes (position + 1) else ioReturn False
    };

  -- Full shallow keys, never hash-only admission. IDs in an ENode are
  -- already interned child IDs, so key equality is structural equality.
  data Entry = EInt Int | EBits Int | EText Int | ENode Int ([] Int);
  data Symbol = Symbol String Int;
  entryKind :: Entry -> Int;
  entryKind entry = case entry of {
    EInt _ -> 0; EBits _ -> 1; EText _ -> 2; ENode _ _ -> 3
  };
  compareIds :: [] Int -> [] Int -> Int;
  compareIds left right = case left of {
    [] -> case right of { [] -> 0; _ -> (-1) };
    (:) a more -> case right of {
      [] -> 1;
      (:) b rest -> let { c = compareInt a b } in
        if c == 0 then compareIds more rest else c
    }
  };
  compareEntry :: Entry -> Entry -> Int;
  compareEntry left right =
    let { kind = compareInt (entryKind left) (entryKind right) } in
    if kind /= 0 then kind else case left of {
      EInt a -> case right of { EInt b -> compareInt a b; _ -> 0 };
      EBits a -> case right of { EBits b -> compareInt a b; _ -> 0 };
      EText a -> case right of { EText b -> compareInt a b; _ -> 0 };
      ENode tag ids -> case right of {
        ENode other rest -> let { c = compareInt tag other } in
          if c == 0 then compareIds ids rest else c;
        _ -> 0
      }
    };
  data SymbolState = Symbols (Map String ((,) Int Int)) ([] Symbol) Int Int;
  data NodeState = Nodes NodeIndex ([] Entry) Int Int AtomIds (KeyIndex (V.IndexVec Int Entry));
  -- A node with newest child c cannot have appeared before ordinal c+1.
  -- If it appears at c+1, that exact entry is its index; all other parents
  -- still use the ordinary full-key index. The page directory contains the
  -- same admitted entries used for emission, in reverse order within a page.
  pushNode keys entry entries nextCount edges saved pages = let {
    next = (:) entry entries;
    completePage = andInt nextCount 63 == 0;
    block = shiftRInt (nextCount - 1) 6;
    following = if completePage then keyInsert block (V.fromList (take 64 next)) pages else pages
  } in seq following (Nodes keys next nextCount edges saved following);
  plannedEntry ordinal count entries pages = let {
    block = shiftRInt ordinal 6;
    active = shiftRInt (count - 1) 6;
    fromTail list offset = case list of {
      (:) first more -> if offset == 0 then first else fromTail more (offset - 1);
      [] -> panic "missing ordinal in writer tail"
    }
  } in if block == active then fromTail entries (count - 1 - ordinal)
    else case keyLookup block pages of {
      Just page -> V.at page (V.fromInt (63 - andInt ordinal 63));
      Nothing -> panic "missing ordinal in writer directory"
    };
  internPlanned entry keys count entries pages = let {
    child = case entry of { ENode _ [a] -> a; ENode _ [a,b] -> max a b; _ -> (-1) };
    ordinal = child + 1
  } in if child < 0 then internNodeKey entry keys else
    if ordinal == count then MissingNode (\_ -> keys)
    else if compareEntry (plannedEntry ordinal count entries pages) entry == 0 then ExistingNode ordinal
    else internNodeKey entry keys;
  -- Descriptors name common generated shapes. A hit reuses only a
  -- completely admitted node with the same tags and scalar payloads.
  data AtomShapes = AtomShapes Int Int Int Int Int | NamedAtomShapes Int Int Int Int Int Int |
    WithGroundProofTags AtomShapes Int Int Int Int Int | WithProofCompositions AtomShapes;
  data ProofAtoms = NoProofAtoms | ProofAtoms Int Int Int Int Int (Maybe ((,,) String Int Int)) ProofCache;
  data NamedAtoms = NoNamedAtoms | NamedAtoms Int (Map String ((,) Int Int));
  data AtomIds = NoAtomIds | AtomIds Int Int Int Int Int
    (Maybe ((,) Int Int)) (IntMap ((,,) String Int Int)) NamedAtoms ProofAtoms;
  emptyAtomIds shapes = case shapes of {
    AtomShapes n pair p opcode empty -> AtomIds n pair p opcode empty Nothing IM.empty NoNamedAtoms NoProofAtoms;
    NamedAtomShapes n pair p opcode empty named ->
      AtomIds n pair p opcode empty Nothing IM.empty (NamedAtoms named M.empty) NoProofAtoms;
    WithGroundProofTags other thenTag inner bottom ctor elim -> case emptyAtomIds other of {
      AtomIds n pair p opcode empty prim names named _ -> AtomIds n pair p opcode empty prim names named
        (ProofAtoms thenTag inner bottom ctor elim Nothing NoProofCache);
      NoAtomIds -> NoAtomIds
    };
    -- A legacy descriptor keeps its original demand for every field.
    WithProofCompositions shapes -> case emptyAtomIds shapes of {
      AtomIds n np p op empty prim names named (ProofAtoms t i b c e previous _) ->
        AtomIds n np p op empty prim names named (ProofAtoms t i b c e previous EmptyProofCache);
      other -> other
    }
  };
  -- A hash narrows structural lookup; it never establishes equality. Exact
  -- collisions use the original balanced map, so even deliberately colliding
  -- inputs retain logarithmic bucket lookup instead of a linear chain.
  data EntryBucket = UniqueEntry Entry Int | CollidingEntries (Map Entry Int);
  -- Canonical-node interning needs exact lookup and insertion, never rank or
  -- cardinality. Keep only Patricia prefixes and lazy payloads in this private
  -- index; physical node counts remain in NodeState and the codec limits.
  data KeyIndex a = KeyEmpty | KeyTip Int a | KeyBranch Int (KeyIndex a) (KeyIndex a);
  keyTip :: forall a. Int -> a -> KeyIndex a;
  keyTip key value = seq key (KeyTip key value);
  keyBranch :: forall a. Int -> KeyIndex a -> KeyIndex a -> KeyIndex a;
  keyBranch prefix left right = seq prefix (seq left (seq right (KeyBranch prefix left right)));
  keyLink :: forall a. Int -> KeyIndex a -> Int -> KeyIndex a -> KeyIndex a;
  keyLink a left b right = let { prefix = KeyBits.mask a (KeyBits.branchMask a b) } in
    if KeyBits.left a prefix then keyBranch prefix left right else keyBranch prefix right left;
  keyLookup :: forall a. Int -> KeyIndex a -> Maybe a;
  keyLookup key tree = case tree of {
    KeyEmpty -> Nothing;
    KeyTip previous value -> if key == previous then Just value else Nothing;
    KeyBranch prefix left right ->
      if KeyBits.left key prefix then keyLookup key left else keyLookup key right
  };
  keyInsert :: forall a. Int -> a -> KeyIndex a -> KeyIndex a;
  keyInsert key value tree = case tree of {
    KeyEmpty -> keyTip key value;
    KeyTip previous old -> if key == previous then keyTip key value
      else keyLink key (keyTip key value) previous tree;
    KeyBranch prefix left right ->
      if KeyBits.nomatch key prefix then keyLink key (keyTip key value) prefix tree
      else if KeyBits.left key prefix then keyBranch prefix (keyInsert key value left) right
      else keyBranch prefix left (keyInsert key value right)
  };
  data EntryIndex = EntryIndex (KeyIndex EntryBucket);
  data EntryLookup = ExistingEntry Int | MissingEntry (Int -> EntryIndex);
  emptyEntryIndex = EntryIndex KeyEmpty;
  mixEntry hash word = xorInt (hash * 1099511628211) word;
  entryHash entry = case entry of {
    EInt value -> mixEntry 1 value;
    EBits value -> mixEntry 2 value;
    EText value -> mixEntry 3 value;
    ENode tag children -> foldlStrict mixEntry (mixEntry 4 tag) children
  };
  internIndexed entry index = internIndexedAt (entryHash entry) entry index;
  internIndexedAt hash entry (EntryIndex buckets) =
    let { insert bucket = EntryIndex (keyInsert hash bucket buckets) } in
    case keyLookup hash buckets of {
      Nothing -> MissingEntry (\value -> insert (UniqueEntry entry value));
      Just (UniqueEntry old value) -> if compareEntry entry old == 0 then ExistingEntry value
        else MissingEntry (\next -> insert (CollidingEntries
          (M.insert compareEntry entry next (M.singleton old value))));
      Just (CollidingEntries entries) -> case intern compareEntry entry entries of {
        Found value -> ExistingEntry value;
        Inserted fill -> MissingEntry (\value -> insert (CollidingEntries (fill value)))
      }
    };
  -- Scalar keys and bounded shallow constructors have an exact integer
  -- identity. Other constructors keep hash-narrowed, full-key comparison.
  -- Packed keys use two arity bits, disjoint fixed-width tag/child fields,
  -- and at most 63 bits. These are indexes only; wire entries are unchanged.
  data NodeIndex = NodeIndex (KeyIndex Int) (KeyIndex Int) (KeyIndex Int) (KeyIndex Int) EntryIndex;
  data NodeLookup = ExistingNode Int | MissingNode (Int -> NodeIndex);
  emptyNodeIndex = NodeIndex KeyEmpty KeyEmpty KeyEmpty KeyEmpty emptyEntryIndex;
  shortNodeKey tag children =
    if tag < 0 || tag >= 65536 then Nothing else case children of {
      [] -> Just (shiftLInt tag 2);
      [a] -> if a >= 0 && a < 4194304
        then Just (orInt 1 (orInt (shiftLInt tag 2) (shiftLInt a 18))) else Nothing;
      [a,b] -> if a >= 0 && a < 4194304 && b >= 0 && b < 4194304
        then Just (orInt 2 (orInt (shiftLInt tag 2) (orInt (shiftLInt a 18) (shiftLInt b 40)))) else Nothing;
      [a,b,c] -> if tag < 1024 && a >= 0 && a < 131072 && b >= 0 && b < 131072 && c >= 0 && c < 131072
        then Just (orInt 3 (orInt (shiftLInt tag 2)
          (orInt (shiftLInt a 12) (orInt (shiftLInt b 29) (shiftLInt c 46))))) else Nothing;
      _ -> Nothing
    };
  internNodeKey entry (NodeIndex ints bits texts short constructors) = case entry of {
    EInt key -> case keyLookup key ints of {
      Just value -> ExistingNode value;
      Nothing -> MissingNode (\value -> NodeIndex (keyInsert key value ints) bits texts short constructors)
    };
    EBits key -> case keyLookup key bits of {
      Just value -> ExistingNode value;
      Nothing -> MissingNode (\value -> NodeIndex ints (keyInsert key value bits) texts short constructors)
    };
    EText key -> case keyLookup key texts of {
      Just value -> ExistingNode value;
      Nothing -> MissingNode (\value -> NodeIndex ints bits (keyInsert key value texts) short constructors)
    };
    ENode tag children -> case shortNodeKey tag children of {
      Just key -> case keyLookup key short of {
        Just value -> ExistingNode value;
        Nothing -> MissingNode (\value -> NodeIndex ints bits texts (keyInsert key value short) constructors)
      };
      Nothing -> case internIndexed entry constructors of {
        ExistingEntry value -> ExistingNode value;
        MissingEntry following -> MissingNode (\value -> NodeIndex ints bits texts short (following value))
      }
    }
  };
  data PlanState = PlanState SymbolState NodeState Int;
  data Tables = Tables ([] Symbol) ([] Entry) ([] Int) Int Int Int Int;
  data EncodeTask = EncodeValues Int ([] Value) | EncodeOne Int Value | EncodeClose Int Int | EncodeRemember Int ([] Value) |
    EncodeRight Int Int Value | EncodePair Int Int | EncodeComposition ([] Value);
  charge :: Limits -> Int -> PlanState -> Either String PlanState;
  charge limits amount (PlanState symbols nodes work) =
    if amount < 0 || amount > maxExpandedWork limits - work
    then Left "binary expanded-work limit exceeded"
    else let { next = work + amount } in seq next (Right (PlanState symbols nodes next));
  boundedLength :: forall a. Int -> [] a -> Either String Int;
  boundedLength limit values = boundedLengthAt limit 0 values;
  boundedLengthAt :: forall a. Int -> Int -> [] a -> Either String Int;
  boundedLengthAt limit count values = case values of {
    [] -> Right count;
    (:) _ rest -> if count >= limit then Left "binary list count limit exceeded"
      else let { next = count + 1 } in seq next (boundedLengthAt limit next rest)
  };
  scalar :: Int -> Bool;
  scalar code = code >= 0 && code <= 1114111 && (code < 55296 || code > 57343);
  scalarBytes :: Int -> Int;
  scalarBytes code = if code < 128 then 1 else if code < 2048 then 2
    else if code < 65536 then 3 else 4;
  utf8Size :: Int -> String -> Either String Int;
  utf8Size limit text =
    if stringLength text > limit then Left "binary symbol byte limit exceeded"
    else let { bytes = stringUtf8Length text } in
      if bytes > limit then Left "binary symbol byte limit exceeded" else Right bytes;
  utf8SizeAt :: Int -> String -> Int -> Int -> Either String Int;
  utf8SizeAt limit text position size =
    if position == stringLength text then Right size else
    let { code = stringCodeAt text position } in
    if not (scalar code) then Left "binary symbol contains a non-scalar code point"
    else let { count = scalarBytes code } in
      if count > limit - size then Left "binary symbol byte limit exceeded"
      else let { next = size + count } in
        seq next (utf8SizeAt limit text (position + 1) next);
  -- One search returns the existing value or the map extended at its actual
  -- insertion point. Both trees use the same total comparison as the reader.
  data Interned k v = Found v | Inserted (v -> Map k v);
  intern :: forall k v. (k -> k -> Int) -> k -> Map k v -> Interned k v;
  intern cmp key tree = case tree of {
    MapEmpty -> Inserted (M.singleton key);
    MapNode _ k v l r -> let { order = cmp key k } in
      if order < 0 then case intern cmp key l of {
        Found old -> Found old; Inserted fill -> Inserted (\new -> M.balance k v (fill new) r)
      } else if order > 0 then case intern cmp key r of {
        Found old -> Found old; Inserted fill -> Inserted (\new -> M.balance k v l (fill new))
      } else Found v
  };
  -- A symbol and its EText node enter the plan together. Repeated text can
  -- reuse that node directly, but every occurrence still charges its bytes.
  -- Intern directly into the remaining explicit task stack. A successful
  -- node needs no intermediate Either/pair for the planner to unpack.
  planText :: Limits -> [] EncodeTask -> [] Int -> String -> PlanState ->
    Either String ((,) ([] Int) PlanState);
  planText limits tasks stack text (PlanState (Symbols names symbols count total)
      nodes@(Nodes keys entries nodeCount edges saved pages) work) =
    if stringLength text > maxSymbolBytes limits then Left "binary symbol byte limit exceeded"
    else case intern compareString text names of {
      Found ((,) bytes nodeId) -> do {
        next <- charge limits bytes (PlanState (Symbols names symbols count total) nodes work);
        planId limits tasks stack nodeId next
      };
      Inserted following -> do {
        ensure (count < maxSymbols limits) "binary symbol count limit exceeded";
        size <- utf8Size (maxSymbolBytes limits) text;
        ensure (size <= maxTotalSymbolBytes limits - total) "binary total symbol byte limit exceeded";
        let {
          nextCount = count + 1;
          nextTotal = total + size;
          nextSymbols = Symbols (following ((,) size nodeCount))
            ((:) (Symbol text size) symbols) nextCount nextTotal
        };
        charged <- seq nextCount (seq nextTotal (charge limits size (PlanState nextSymbols nodes work)));
        ensure (nodeCount < maxNodes limits) "binary node count limit exceeded";
        let { nextNodeCount = nodeCount + 1;
          nextNodes = pushNode keys (EText count) entries nextNodeCount edges saved pages };
        case charged of { PlanState _ _ nextWork ->
          seq nextNodeCount (planId limits tasks stack nodeCount
            (PlanState nextSymbols nextNodes nextWork)) }
      }
    };
  entryEdges :: Entry -> Int;
  entryEdges entry = case entry of { ENode _ children -> length children; _ -> 0 };
  planEntry :: Limits -> [] EncodeTask -> [] Int -> Entry -> PlanState ->
    Either String ((,) ([] Int) PlanState);
  planEntry limits tasks stack entry state@(PlanState symbols (Nodes keys entries count edges saved pages) work) =
    case internPlanned entry keys count entries pages of {
      ExistingNode index -> planId limits tasks stack index state;
      MissingNode following -> do {
        ensure (count < maxNodes limits) "binary node count limit exceeded";
        let { arity = entryEdges entry };
        ensure (arity <= maxEdges limits - edges) "binary edge count limit exceeded";
        let {
          nextCount = count + 1;
          nextEdges = edges + arity;
          nextNodes = pushNode (following count) entry entries nextCount nextEdges saved pages
        };
        seq nextCount (seq nextEdges (planId limits tasks stack count
          (PlanState symbols nextNodes work)))
      }
    };
  takeIds :: Int -> [] Int -> [] Int -> Either String ((,) ([] Int) ([] Int));
  takeIds count stack acc = if count == 0 then Right ((,) acc stack) else case stack of {
    [] -> Left "binary encoder internal reference stack underflow";
    (:) index rest -> takeIds (count - 1) rest ((:) index acc)
  };
  plan :: Limits -> [] Value -> Either String Tables;
  plan = planWith NoAtomIds;
  planWith initial limits roots = do {
    ensure (validLimits limits) "invalid binary codec limits";
    rootCount <- boundedLength (min (maxEdges limits) (maxExpandedWork limits)) roots;
    planned <- planTasks limits ((:) (EncodeValues 1 roots) []) []
      (PlanState (Symbols M.empty [] 0 0) (Nodes emptyNodeIndex [] 0 0 initial KeyEmpty) 0);
    case planned of {
      (,) stack (PlanState (Symbols _ symbols symbolCount _) (Nodes _ entries nodeCount edges _ _) _) ->
        Right (Tables (reverse symbols) (reverse entries) (reverse stack)
          symbolCount nodeCount rootCount edges)
    }
  };
  -- Each root keeps the original subtree-work limit. Symbol/node
  -- interning and all physical counts remain global across the whole plan.
  -- The second result is exact expanded work, including every repeated root,
  -- child and text occurrence. This does not materialize an auxiliary Graph.
  planRootBounded :: Limits -> Int -> [] Value -> Either String ((,) Tables Int);
  planRootBounded = planRootsWith NoAtomIds;
  planRootsWith initial limits aggregate roots = do {
    ensure (validLimits limits) "invalid binary codec limits";
    ensure (validRootBudget aggregate) "invalid binary root-work budget";
    rootCount <- boundedLength (min (maxEdges limits) aggregate) roots;
    planned <- planRootsBounded limits aggregate roots []
      (PlanState (Symbols M.empty [] 0 0) (Nodes emptyNodeIndex [] 0 0 initial KeyEmpty) 0);
    case planned of {
      (,,) stack
        (PlanState (Symbols _ symbols symbolCount _) (Nodes _ entries nodeCount edges _ _) _)
        remaining ->
          let { used = aggregate - remaining } in
          seq used (Right ((,)
            (Tables (reverse symbols) (reverse entries) (reverse stack)
              symbolCount nodeCount rootCount edges)
            used))
    }
  };
  planRootsBounded :: Limits -> Int -> [] Value -> [] Int -> PlanState ->
    Either String ((,,) ([] Int) PlanState Int);
  planRootsBounded limits remaining roots stack (PlanState symbols nodes _) =
    case roots of {
      [] -> Right ((,,) stack (PlanState symbols nodes 0) remaining);
      (:) root rest -> do {
        let { rootLimits =
          withExpandedWork limits (min (maxExpandedWork limits) remaining) };
        planned <- planTasks rootLimits ((:) (EncodeOne 1 root) []) stack
          (PlanState symbols nodes 0);
        case planned of {
          (,) nextStack (PlanState nextSymbols nextNodes used) ->
            let { nextRemaining = remaining - used } in
            seq nextRemaining (planRootsBounded limits nextRemaining rest nextStack
              (PlanState nextSymbols nextNodes 0))
        }
      }
    };
  rememberAtom tag children index saved = case saved of {
    NoAtomIds -> saved;
    AtomIds nameTag namePair primTag opcodeTag emptyTag prim names named proofs -> let {
      save primitive bindings atoms = AtomIds nameTag namePair primTag opcodeTag emptyTag primitive bindings atoms proofs;
      ordinary = if tag == primTag then case children of {
        [VNode inner [VInt code],VNode tailTag []] -> if inner == opcodeTag && tailTag == emptyTag
          then save (Just ((,) code index)) names named else saved;
        _ -> saved
      } else if tag == nameTag then case children of {
        [VNode inner [VInt binding,VText hint]] -> if inner /= namePair || binding < 0 || binding >= 64 then saved
          else save prim (IM.insert binding ((,,) hint (stringUtf8Length hint) index) names) named;
        _ -> saved
      } else case named of {
        NamedAtoms namedTag table -> if tag /= namedTag || M.size table >= 64 then saved else case children of {
          [VText text,VNode tailTag []] -> if tailTag == emptyTag then save prim names
            (NamedAtoms namedTag (M.insert compareString text ((,) (stringUtf8Length text) index) table)) else saved;
          _ -> saved
        };
        NoNamedAtoms -> saved
      }
    } in case proofs of {
      ProofAtoms thenTag inner bottom ctor elim _ cache -> if tag /= thenTag then ordinary else case children of {
        [first,end] -> case proofField inner bottom ctor first of {
          Just ((,) text args) -> if atomEmpty emptyTag args && atomEmpty elim end then
            AtomIds nameTag namePair primTag opcodeTag emptyTag prim names named
              (ProofAtoms thenTag inner bottom ctor elim (Just ((,,) text (stringUtf8Length text) index)) cache)
            else ordinary;
          Nothing -> ordinary
        };
        _ -> ordinary
      };
      NoProofAtoms -> ordinary
    }
  };
  -- A miss follows ordinary planning. Keeping the shape tests separate also
  -- preserves its demand order on an ill-formed nested value: check the tag,
  -- then the complete field spine, then the fields from left to right.
  atomInteger tag node = case node of {
    VNode actual args -> if actual /= tag then Nothing else case args of {
      [field] -> case field of { VInt code -> Just code; _ -> Nothing };
      _ -> Nothing
    };
    _ -> Nothing
  };
  atomEmpty tag node = case node of {
    VNode actual fields -> actual == tag && null fields;
    _ -> False
  };
  atomNameFields tag node = case node of {
    VNode actual args -> if actual /= tag then Nothing else case args of {
      [left,right] -> case left of { VInt binding -> Just ((,) binding right); _ -> Nothing };
      _ -> Nothing
    };
    _ -> Nothing
  };
  -- A ground argument is encoded as Then (Inner (Bottom (Con name []))) Elim.
  -- Return the name and its still-lazy argument-list node. The writer must
  -- account for the UTF-8 payload before it can examine either trailing node.
  proofField inner bottom ctor first = let {
    child expected value next = case value of {
      VNode tag args -> if tag /= expected || tag < 0 || tag > 2147483647 then Nothing else case args of {
        [field] -> next field; _ -> Nothing
      };
      _ -> Nothing
    }
  } in child inner first (\p -> child bottom p (\ty -> case ty of {
    VNode tag fields -> if tag /= ctor || tag < 0 || tag > 2147483647 then Nothing else case fields of {
      [field,args] -> case field of { VText name -> Just ((,) name args); _ -> Nothing };
      _ -> Nothing
    };
    _ -> Nothing
  }));
  -- Describe only a previously admitted subtree, up to three composition
  -- levels (eight complete arguments). Cache both the exact grouping and
  -- the last elementary atom the ordinary traversal would leave available.
  data ProofKey = ProofLeaf String | ProofPair ProofKey ProofKey;
  data ProofSize = ProofSize ProofKey Int Int Int String;
  data ProofCache = NoProofCache | EmptyProofCache |
    LastProof ProofKey Int Int Int Int ((,,) String Int Int);
  captureProof thenTag inner bottom ctor empty elim = let {
    child room node = case node of {
      VNode tag fields -> if tag == thenTag then capture room fields else Nothing;
      _ -> Nothing
    };
    capture room fields = case fields of {
      [a,b] -> case proofField inner bottom ctor a of {
        Just ((,) name args) -> if atomEmpty empty args && atomEmpty elim b then
          Just (ProofSize (ProofLeaf name) 5 7 (7 + stringUtf8Length name) name) else Nothing;
        Nothing -> if room == 0 then Nothing else case child (room - 1) a of {
          Nothing -> Nothing;
          Just (ProofSize x dx nx wx _) -> case child (room - 1) b of {
            Nothing -> Nothing;
            Just (ProofSize y dy ny wy last) ->
              Just (ProofSize (ProofPair x y) (1 + max dx dy) (1 + nx + ny) (1 + wx + wy) last)
          }
        }
      };
      _ -> Nothing
    }
  } in capture 3;
  matchesProof thenTag inner bottom ctor empty elim = let {
    child key node = case node of {
      VNode actual fields -> actual == thenTag && same key fields;
      _ -> False
    };
    same key fields = case fields of {
      [a,b] -> case key of {
        ProofPair x y -> child x a && child y b;
        ProofLeaf expected -> case proofField inner bottom ctor a of {
          Just ((,) name args) -> eqString expected name && atomEmpty empty args && atomEmpty elim b;
          Nothing -> False
        }
      };
      _ -> False
    }
  } in same;
  rememberComposition children identity saved = case saved of {
    AtomIds n np p op empty prim names named (ProofAtoms t i b c e previous cache) -> case previous of {
      -- An admitted leaf has already demanded all six proof tags. With
      -- distinct tags, at least three descendant tags took the ordinary
      -- atom path on its first admission, so its root descriptors are also
      -- known. A colliding schema stays on the original traversal.
      Just last@((,,) lastName _ _) -> let {
        roles = [t,i,b,c,e,empty];
        allowed role = role /= n && role /= p &&
          (case named of { NoNamedAtoms -> True; NamedAtoms k _ -> role /= k });
        usable = length (nubBy (==) roles) == 6 && all allowed roles;
        store value = AtomIds n np p op empty prim names named (ProofAtoms t i b c e previous value)
      } in if not usable then store NoProofCache else case captureProof t i b c empty e children of {
        Just (ProofSize key@(ProofPair _ _) height nodes work lastLeaf) ->
          if eqString lastName lastLeaf then store (LastProof key height nodes work identity last) else saved;
        _ -> saved
      };
      Nothing -> saved
    };
    _ -> saved
  };
  tryAtom limits depth tag children stack rest state@(PlanState symbols (Nodes keys entries count edges saved pages) work) ordinary =
    case saved of {
      NoAtomIds -> ordinary rest;
      AtomIds nameTag namePair primitiveTag opcodeTag emptyTag primitive names named proofs -> let {
        isNamed = case named of { NamedAtoms namedTag _ -> tag == namedTag; NoNamedAtoms -> False };
        available = maxExpandedWork limits - work;
        -- Even a miss must be able to admit three descendants, four distinct
        -- nodes (including the root), and three edges before speculating.
        enoughRoom = maxDepth limits >= 2 && depth <= maxDepth limits - 2 && available >= 3 &&
          maxNodes limits - count >= 4 && maxEdges limits - edges >= 3;
        remember = ordinary ((:) (EncodeRemember tag children) rest);
        reuse amount index = do {
          next <- charge limits amount state;
          planId limits rest stack index next
        };
        usePrimitive first second = case primitive of {
          Nothing -> remember;
          Just ((,) expected index) -> case atomInteger opcodeTag first of {
            Just code -> if code == expected && atomEmpty emptyTag second then reuse 3 index else remember;
            Nothing -> remember
          }
        };
        useName first = case atomNameFields namePair first of {
          Nothing -> remember;
          Just ((,) binding text) -> case IM.lookup binding names of {
            Nothing -> remember;
            Just ((,,) expected bytes index) -> if bytes > available - 3 then ordinary rest else case text of {
              VText hint -> if eqString expected hint then reuse (3 + bytes) index else remember;
              _ -> remember
            }
          }
        };
        useNamed first second = case first of {
          VText text -> case named of {
            NamedAtoms _ table -> case M.lookup compareString text table of {
              Nothing -> remember;
              Just ((,) bytes index) -> if bytes > available - 2 then ordinary rest
                else if atomEmpty emptyTag second then reuse (2 + bytes) index else remember
            };
            NoNamedAtoms -> ordinary rest
          };
          _ -> remember
        };
        -- Check room for the whole shape before looking into it. Only an
        -- already admitted name may skip the six descendant node charges.
        compound inner bottom ctor elim cache first = case cache of {
          NoProofCache -> ordinary rest;
          _ -> case first of {
            VNode firstTag _ -> if firstTag /= tag then ordinary rest else let {
              record = ordinary ((:) (EncodeComposition children) rest)
            } in case cache of {
              LastProof key height size cost identity last ->
                if height > maxDepth limits - depth + 1 || size > maxNodes limits - count ||
                    size - 1 > maxEdges limits - edges || cost - 1 > available then ordinary rest
                else if matchesProof tag inner bottom ctor emptyTag elim key children then let {
                  atoms = AtomIds nameTag namePair primitiveTag opcodeTag emptyTag primitive names named
                    (ProofAtoms tag inner bottom ctor elim (Just last) cache)
                } in do {
                  next <- charge limits (cost - 1) (PlanState symbols (Nodes keys entries count edges atoms pages) work);
                  planId limits rest stack identity next
                } else record;
              _ -> record
            };
            _ -> ordinary rest
          }
        };
        tryProof inner bottom ctor elim previous cache = case children of {
          [first,end] -> case proofField inner bottom ctor first of {
            Nothing -> compound inner bottom ctor elim cache first;
            Just ((,) name args) -> case previous of {
              Nothing -> remember;
              Just ((,,) expected bytes index) -> if bytes > available - 6 then ordinary rest
                else if not (eqString expected name) then remember
                else if atomEmpty emptyTag args && atomEmpty elim end then reuse (6 + bytes) index
                else ordinary rest
            }
          };
          _ -> ordinary rest
        };
        ordinaryAtoms = if (tag /= primitiveTag && tag /= nameTag && not isNamed) || not enoughRoom then ordinary rest else do {
          let { cap = min (maxEdges limits) (maxExpandedWork limits - 1) };
          arity <- boundedLength cap children;
          if tag == primitiveTag && arity == 2 then case children of {
            [first,second] -> usePrimitive first second; _ -> ordinary rest
          } else if tag == nameTag && arity == 1 then case children of {
            [first] -> useName first; _ -> ordinary rest
          } else if isNamed && arity == 2 then case children of {
            [first,second] -> useNamed first second; _ -> ordinary rest
          } else ordinary rest
        }
      } in case proofs of {
        ProofAtoms thenTag inner bottom ctor elim previous cache -> if tag == thenTag &&
          depth <= maxDepth limits - 4 && available >= 6 && maxNodes limits - count >= 7 &&
          maxEdges limits - edges >= 6 then tryProof inner bottom ctor elim previous cache else ordinaryAtoms;
        NoProofAtoms -> ordinaryAtoms
      }
    };
  -- Explicit tasks keep valid deep ASTs off the language call stack. Work
  -- is charged on every input occurrence, including repeated subgraphs.
  planTasks :: Limits -> [] EncodeTask -> [] Int -> PlanState -> Either String ((,) ([] Int) PlanState);
  planTasks limits tasks stack state = case tasks of {
    [] -> Right ((,) stack state);
    (:) task rest -> let {
      -- An atom remembered by the ordinary scheduler leaves its ID on the stack.
      resume = case stack of {
        (:) index remaining -> planId limits tasks remaining index state;
        [] -> Left "binary encoder internal reference stack underflow"
      }
    } in case task of {
      EncodeComposition children -> case (,) stack state of {
        (,) ((:) index _) (PlanState symbols (Nodes keys entries count edges saved pages) work) -> let {
          atoms = rememberComposition children index saved
        } in seq atoms (planTasks limits rest stack (PlanState symbols (Nodes keys entries count edges atoms pages) work));
        _ -> Left "binary reference stack underflow"
      };
      EncodeRemember tag children -> case (,) stack state of {
        (,) ((:) index _) (PlanState symbols (Nodes keys entries count edges saved pages) work) -> let {
          atoms = rememberAtom tag children index saved
        } in seq atoms (planTasks limits rest stack (PlanState symbols (Nodes keys entries count edges atoms pages) work));
        _ -> Left "binary reference stack underflow"
      };
      EncodeValues depth values -> case values of {
        [] -> planTasks limits rest stack state;
        (:) value more -> planTasks limits
          ((:) (EncodeOne depth value) ((:) (EncodeValues depth more) rest)) stack state
      };
      EncodeClose tag 1 -> case stack of {
        (:) child restStack -> planEntry limits rest restStack (ENode tag [child]) state;
        [] -> Left "binary encoder internal reference stack underflow"
      };
      EncodeClose tag 2 -> case stack of {
        (:) right ((:) left restStack) -> planEntry limits rest restStack (ENode tag [left,right]) state;
        _ -> Left "binary encoder internal reference stack underflow"
      };
      EncodeClose tag arity -> do {
        parts <- takeIds arity stack [];
        case parts of {
          (,) children remaining -> planEntry limits rest remaining (ENode tag children) state
        }
      };
      EncodeOne depth value -> planOne limits depth value rest stack state;
      EncodeRight _ _ _ -> resume;
      EncodePair _ _ -> resume
    }
  };
  -- For a binary node, the admitted left ID travels with its pending close.
  -- Each child still enters the depth, work and atom checks in source order.
  planId :: Limits -> [] EncodeTask -> [] Int -> Int -> PlanState -> Either String ((,) ([] Int) PlanState);
  planId limits tasks stack index state = case tasks of {
    (:) (EncodeRight depth tag right) rest ->
      planOne limits depth right ((:) (EncodePair tag index) rest) stack state;
    (:) (EncodePair tag left) rest -> planEntry limits rest stack (ENode tag [left,index]) state;
    (:) (EncodeClose tag 1) rest -> planEntry limits rest stack (ENode tag [index]) state;
    _ -> planTasks limits tasks ((:) index stack) state
  };
  planOne :: Limits -> Int -> Value -> [] EncodeTask -> [] Int -> PlanState -> Either String ((,) ([] Int) PlanState);
  planOne limits depth value rest stack state = do {
    ensure (depth <= maxDepth limits) "binary graph depth limit exceeded";
    charged <- charge limits 1 state;
    case value of {
      VNode tag children -> do {
        ensure (tag >= 0 && tag <= 2147483647) "binary constructor tag out of range";
        let { childrenWith following = let {
          cap = min (maxEdges limits) (maxExpandedWork limits - 1);
          walk arity = planTasks limits ((:) (EncodeValues (depth + 1) children)
            ((:) (EncodeClose tag arity) following)) stack charged
        } in if cap < 2 then do { arity <- boundedLength cap children; walk arity }
          else case children of {
            [] -> planEntry limits following stack (ENode tag []) charged;
            [a] -> planOne limits (depth + 1) a ((:) (EncodeClose tag 1) following) stack charged;
            [a,b] -> planOne limits (depth + 1) a
              ((:) (EncodeRight (depth + 1) tag b) following) stack charged;
            (:) _ ((:) _ ((:) _ more)) -> if cap == 2 then Left "binary list count limit exceeded"
              else do { arity <- boundedLengthAt cap 3 more; walk arity }
          }
        } in tryAtom limits depth tag children stack rest charged childrenWith
      };
      VText text -> planText limits rest stack text charged;
      VInt valueInt -> planEntry limits rest stack (EInt valueInt) charged;
      VBits bits -> planEntry limits rest stack (EBits bits) charged
    }
  };

  zigzag :: Int -> Int;
  zigzag value = xorInt (shiftLInt value 1) (shiftRInt value 63);
  unzigzag :: Int -> Int;
  unzigzag bits = xorInt (unsignedShiftRInt bits 1) (0 - andInt bits 1);
  varBytes :: Int -> Int;
  varBytes bits = if unsignedLtInt bits 128 then 1 else 1 + varBytes (unsignedShiftRInt bits 7);
  referenceWidth :: Int -> Int;
  referenceWidth count = if count <= 1 then 1 else 64 - countLeadingZerosInt (count - 1);
  bytesForBits :: Int -> Int;
  bytesForBits bits = (bits + 7) / 8;
  symbolSize :: Symbol -> Int;
  symbolSize (Symbol _ size) = varBytes size + size;
  nodeBits :: Int -> Int -> Entry -> Int;
  nodeBits nodeWidth symbolWidth entry = 2 + case entry of {
    EInt value -> 8 * varBytes (zigzag value);
    EBits _ -> 64;
    EText _ -> symbolWidth;
    ENode tag children -> let { count = length children } in
      8 * (varBytes tag + varBytes count) + count * nodeWidth
  };
  -- All measurement intermediates are <= 2^40 under validLimits. The final
  -- allocation is checked against maxBytes before newByteArray is called.
  data Layout = Layout Int Int Int Int Int Int Int Int Int Int Int Int;
  layout :: Limits -> Tables -> Either String Layout;
  layout limits (Tables symbols nodes roots symbolCount nodeCount rootCount edges) =
    let {
      nodeWidth = referenceWidth nodeCount;
      symbolWidth = referenceWidth symbolCount;
      symbolLength = foldlStrict (\total symbol -> total + symbolSize symbol) 0 symbols;
      nodeLength = bytesForBits (foldlStrict (\total entry -> total + nodeBits nodeWidth symbolWidth entry) 0 nodes);
      rootLength = bytesForBits (rootCount * nodeWidth);
      nodeOffset = 80 + symbolLength;
      rootOffset = nodeOffset + nodeLength;
      total = rootOffset + rootLength
    } in
    if total > maxBytes limits then Left "binary file byte limit exceeded"
    else Right (Layout total symbolCount symbolLength nodeCount nodeOffset nodeLength
      edges rootCount rootOffset rootLength nodeWidth symbolWidth);

  -- The writer owns its zero-filled buffer exclusively. Bits are little-endian
  -- within bytes; no intermediate list of output bytes or textual envelope.
  putBits :: ByteArray -> Int -> Int -> Int -> IO Int;
  putBits bytes position width bits =
    if width == 0 then ioReturn position else do {
      let {
        offset = position % 8;
        take = min width (8 - offset);
        mask = shiftLInt 1 take - 1;
        piece = shiftLInt (andInt bits mask) offset;
        byteIndex = position / 8
      };
      if take == 8 then writeByteArray bytes byteIndex piece else do {
        previous <- readByteArray bytes byteIndex;
        writeByteArray bytes byteIndex (orInt previous piece)
      };
      putBits bytes (position + take) (width - take) (unsignedShiftRInt bits take)
    };
  putVar :: ByteArray -> Int -> Int -> IO Int;
  putVar bytes position bits = do {
    let { final = unsignedLtInt bits 128; byte = orInt (andInt bits 127) (if final then 0 else 128) };
    next <- putBits bytes position 8 byte;
    if final then ioReturn next else putVar bytes next (unsignedShiftRInt bits 7)
  };
  putScalar :: ByteArray -> Int -> Int -> IO Int;
  putScalar bytes position code =
    if code < 128 then putBits bytes position 8 code
    else if code < 2048 then do {
      next <- putBits bytes position 8 (orInt 192 (unsignedShiftRInt code 6));
      putBits bytes next 8 (orInt 128 (andInt code 63))
    } else if code < 65536 then do {
      next <- putBits bytes position 8 (orInt 224 (unsignedShiftRInt code 12));
      more <- putBits bytes next 8 (orInt 128 (andInt (unsignedShiftRInt code 6) 63));
      putBits bytes more 8 (orInt 128 (andInt code 63))
    } else do {
      next <- putBits bytes position 8 (orInt 240 (unsignedShiftRInt code 18));
      more <- putBits bytes next 8 (orInt 128 (andInt (unsignedShiftRInt code 12) 63));
      last <- putBits bytes more 8 (orInt 128 (andInt (unsignedShiftRInt code 6) 63));
      putBits bytes last 8 (orInt 128 (andInt code 63))
    };
  putText :: ByteArray -> Int -> String -> Int -> IO Int;
  putText bytes position text index =
    if position >= 0 && position % 8 == 0 then putAlignedText bytes (position / 8) text index
    else if index == stringLength text then ioReturn position else do {
      next <- putScalar bytes position (stringCodeAt text index);
      putText bytes next text (index + 1)
    };
  putAlignedText bytes byteIndex text index =
    if index == stringLength text then ioReturn (byteIndex * 8) else let {
      code = stringCodeAt text index
    } in if code < 128 then do {
      writeByteArray bytes byteIndex code;
      putAlignedText bytes (byteIndex + 1) text (index + 1)
    } else do {
      next <- putScalar bytes (byteIndex * 8) code;
      putAlignedText bytes (next / 8) text (index + 1)
    };
  putSymbols :: ByteArray -> Int -> [] Symbol -> IO Int;
  putSymbols bytes position symbols = case symbols of {
    [] -> ioReturn position;
    (:) (Symbol text size) rest -> do {
      next <- putVar bytes position size;
      more <- putText bytes next text 0;
      putSymbols bytes more rest
    }
  };
  putReferences :: ByteArray -> Int -> Int -> [] Int -> IO Int;
  putReferences bytes position width references = case references of {
    [] -> ioReturn position;
    (:) index rest -> do {
      next <- putBits bytes position width index;
      putReferences bytes next width rest
    }
  };
  putEntry :: ByteArray -> Int -> Int -> Int -> Entry -> IO Int;
  putEntry bytes position nodeWidth symbolWidth entry = do {
    next <- putBits bytes position 2 (entryKind entry);
    case entry of {
      EInt value -> putVar bytes next (zigzag value);
      EBits bits -> putBits bytes next 64 bits;
      EText index -> putBits bytes next symbolWidth index;
      ENode tag children -> do {
        more <- putVar bytes next tag;
        last <- putVar bytes more (length children);
        putReferences bytes last nodeWidth children
      }
    }
  };
  putEntries :: ByteArray -> Int -> Int -> Int -> [] Entry -> IO Int;
  putEntries bytes position nodeWidth symbolWidth entries = case entries of {
    [] -> ioReturn position;
    (:) entry rest -> do {
      next <- putEntry bytes position nodeWidth symbolWidth entry;
      putEntries bytes next nodeWidth symbolWidth rest
    }
  };
  putWords :: ByteArray -> Int -> [] Int -> IO Int;
  putWords bytes position words = case words of {
    [] -> ioReturn position;
    (:) word rest -> do {
      next <- putBits bytes position 32 word;
      putWords bytes next rest
    }
  };
  putHeader :: ByteArray -> Int -> Layout -> IO Int;
  putHeader bytes schema (Layout total symbols symbolLength nodes nodeOffset nodeLength
      edges roots rootOffset rootLength nodeWidth symbolWidth) = do {
    next <- putText bytes 0 magic 0;
    putWords bytes next ((:) 1 ((:) 0 ((:) schema ((:) 80 ((:) total
      ((:) symbols ((:) 80 ((:) symbolLength ((:) nodes ((:) nodeOffset ((:) nodeLength
      ((:) edges ((:) roots ((:) rootOffset ((:) rootLength ((:) nodeWidth
      ((:) symbolWidth ((:) 0 []))))))))))))))))))
  };

  -- CRC32/ISO-HDLC. This detects corruption only; it is not a signature,
  -- MAC or content-addressing substitute. Header checksum bytes 76..79 are
  -- treated as zero, binding every other header byte and every payload byte.
  crcNibble :: Int -> Int;
  crcNibble value = case andInt value 15 of {
    0 -> 0; 1 -> 498536548; 2 -> 997073096; 3 -> 651767980;
    4 -> 1994146192; 5 -> 1802195444; 6 -> 1303535960; 7 -> 1342533948;
    8 -> 3988292384; 9 -> 4027552580; 10 -> 3604390888; 11 -> 3412177804;
    12 -> 2607071920; 13 -> 2262029012; 14 -> 2685067896; _ -> 3183342108
  };
  crcByte :: Int -> Int -> Int;
  crcByte previous byte =
    let { start = xorInt previous byte;
          first = xorInt (unsignedShiftRInt start 4) (crcNibble start) } in
    xorInt (unsignedShiftRInt first 4) (crcNibble first);
  checksum :: ByteArray -> Int -> IO Int;
  checksum bytes size = if size >= 16384 then checksumFour bytes size
    else if size < 1024 then checksumAt bytes size 0 4294967295 else do {
    table <- newIntArray 256 0;
    buildCRCTable table 0;
    checksumBytes table bytes size 0 4294967295
  };
  -- Four reflected CRC tables advance four bytes at once. Each table is
  -- derived from the existing byte recurrence, and the wire checksum field
  -- remains logically zero. Small buffers keep their cheaper one-table path.
  checksumFour bytes size = do {
    table <- newIntArray 1024 0;
    buildCRCFour table 0;
    crc <- crcFourRange table bytes size 0 4294967295;
    ioReturn (xorInt crc 4294967295)
  };
  buildCRCFour table index = if index == 256 then ioReturn () else do {
    let { a = crcByte 0 index; b = crcByte a 0; c = crcByte b 0; d = crcByte c 0 };
    writeIntArray table index a;
    writeIntArray table (256 + index) b;
    writeIntArray table (512 + index) c;
    writeIntArray table (768 + index) d;
    buildCRCFour table (index + 1)
  };
  crcFourWord bytes position = if position == 76 then ioReturn 0 else do {
    a <- readByteArray bytes position;
    b <- readByteArray bytes (position + 1);
    c <- readByteArray bytes (position + 2);
    d <- readByteArray bytes (position + 3);
    ioReturn (orInt a (orInt (shiftLInt b 8) (orInt (shiftLInt c 16) (shiftLInt d 24))))
  };
  crcFourRange table bytes size position crc =
    if size - position < 4 then crcRange table bytes size position crc else do {
      word <- crcFourWord bytes position;
      let { value = xorInt crc word };
      a <- readIntArray table (768 + andInt value 255);
      b <- readIntArray table (512 + andInt (unsignedShiftRInt value 8) 255);
      c <- readIntArray table (256 + andInt (unsignedShiftRInt value 16) 255);
      d <- readIntArray table (unsignedShiftRInt value 24);
      let { next = xorInt a (xorInt b (xorInt c d)) };
      seq next (crcFourRange table bytes size (position + 4) next)
    };
  -- CRC is linear over XOR. The one-byte remainder is crcByte 0 index,
  -- while every higher input bit shifts down by eight positions.
  buildCRCTable table index = if index == 256 then ioReturn () else do {
    writeIntArray table index (crcByte 0 index);
    buildCRCTable table (index + 1)
  };
  advanceCRC :: IntArray -> Int -> Int -> IO Int;
  advanceCRC table crc byte = do {
    remainder <- readIntArray table (andInt (xorInt crc byte) 255);
    ioReturn (xorInt (unsignedShiftRInt crc 8) remainder)
  };
  checksumBytes table bytes size position crc = do {
    rest <- crcRange table bytes size position crc;
    ioReturn (xorInt rest 4294967295)
  };
  crcRange :: IntArray -> ByteArray -> Int -> Int -> Int -> IO Int;
  crcRange table bytes end position crc =
    if position == end then ioReturn crc else do {
      byte <- if position >= 76 && position < 80 then ioReturn 0 else readByteArray bytes position;
      next <- advanceCRC table crc byte;
      seq next (crcRange table bytes end (position + 1) next)
    };
  checksumAt :: ByteArray -> Int -> Int -> Int -> IO Int;
  checksumAt bytes size position crc =
    if position == size then ioReturn (xorInt crc 4294967295) else do {
      byte <- if position >= 76 && position < 80 then ioReturn 0 else readByteArray bytes position;
      let { next = crcByte crc byte };
      seq next (checksumAt bytes size (position + 1) next)
    };
  encode :: Limits -> Int -> [] Value -> IO (Either String ByteArray);
  encode = encodeUsing NoAtomIds;
  encodeAtoms shapes = encodeUsing (emptyAtomIds shapes);
  encodeUsing initial limits schema roots = catchIOError (encodeCheckedWith initial limits schema roots)
    (\error -> ioReturn (Left ("binary encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  encodeRootBounded :: Limits -> Int -> Int -> [] Value -> IO (Either String ByteArray);
  encodeRootBounded = encodeRootsUsing NoAtomIds;
  encodeRootsWithAtoms shapes = encodeRootsUsing (emptyAtomIds shapes);
  encodeRootsUsing initial limits aggregate schema roots = catchIOError
    (encodeRootCheckedWith initial limits aggregate schema roots)
    (\error -> ioReturn (Left ("binary encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  encodeRootBoundedChecked :: Limits -> Int -> Int -> [] Value -> IO (Either String ByteArray);
  encodeRootBoundedChecked = encodeRootCheckedWith NoAtomIds;
  encodeRootCheckedWith initial limits aggregate schema roots =
    if schema < 0 || schema > 2147483647 then ioReturn (Left "binary schema ID out of range")
    else case planRootsWith initial limits aggregate roots of {
      Left message -> ioReturn (Left message);
      Right ((,) tables _) -> case layout limits tables of {
        Left message -> ioReturn (Left message);
        Right geometry -> encodeTablesOwned schema geometry tables
      }
    };
  encodeChecked :: Limits -> Int -> [] Value -> IO (Either String ByteArray);
  encodeChecked = encodeCheckedWith NoAtomIds;
  encodeCheckedWith initial limits schema roots =
    if schema < 0 || schema > 2147483647 then ioReturn (Left "binary schema ID out of range")
    else case planWith initial limits roots of {
      Left message -> ioReturn (Left message);
      Right tables -> case layout limits tables of {
        Left message -> ioReturn (Left message);
        Right geometry -> encodeTablesOwned schema geometry tables
      }
    };
  -- The owned encoder can retain a partially filled byte across fields.
  -- Flush each complete byte once; public putBits keeps its read/modify/write
  -- semantics for callers writing into an existing buffer. The continuation
  -- carries byte index, occupied bits and pending byte without an IO tuple.
  -- Planning has admitted finite field values. Force the computed byte here
  -- so each step carries a scalar instead of a thunk capturing the bit state.
  -- At most 56 source bits plus seven pending bits fit in a nonnegative
  -- Int64. Merge once, then flush complete bytes without rebuilding each
  -- byte from the original field. Wider fields retain the bounded split.
  packedBits bytes index used pending width bits next =
    if width == 0 then next index used pending
    else if width <= 56 then let {
      mask = shiftLInt 1 width - 1;
      field = orInt pending (shiftLInt (andInt bits mask) used)
    } in seq field (packedField bytes index (used + width) field next)
    else let {
      room = 8 - used;
      amount = min room width;
      mask = shiftLInt 1 amount - 1;
      byte = orInt pending (shiftLInt (andInt bits mask) used)
    } in seq byte (if width < room then next index (used + width) byte else do {
      writeByteArray bytes index byte;
      packedBits bytes (index + 1) 0 0 (width - room) (unsignedShiftRInt bits room) next
    });
  packedField bytes index width bits next =
    if width >= 16 then do {
      writeByteArray bytes index (andInt bits 255);
      writeByteArray bytes (index + 1) (andInt (unsignedShiftRInt bits 8) 255);
      let { rest = unsignedShiftRInt bits 16 };
      seq rest (packedField bytes (index + 2) (width - 16) rest next)
    } else if width < 8 then next index width bits else do {
      writeByteArray bytes index (andInt bits 255);
      let { rest = unsignedShiftRInt bits 8 };
      seq rest (packedField bytes (index + 1) (width - 8) rest next)
    };
  -- A varint emits an already bounded byte. Across any pending-bit offset,
  -- that byte flushes exactly one output byte and preserves the offset.
  -- Avoid reentering the general-width writer for its remaining high bits.
  packedByte bytes index used pending bits next = let {
    byte = andInt (orInt pending (shiftLInt bits used)) 255;
    following = unsignedShiftRInt bits (8 - used)
  } in seq byte (do {
    writeByteArray bytes index byte;
    seq following (next (index + 1) used following)
  });
  -- The final varint byte can use the caller's continuation directly.
  packedVar bytes index used pending bits next =
    if unsignedLtInt bits 128 then packedByte bytes index used pending bits next
    else packedByte bytes index used pending (orInt (andInt bits 127) 128)
      (\i u p -> packedVar bytes i u p (unsignedShiftRInt bits 7) next);
  -- Two bounded references fit the general writer's 56-bit field. Keep the
  -- low reference within its own width, including when testing raw values.
  packedRefs bytes width references index used pending next = case references of {
    [] -> next index used pending;
    (:) first more -> case more of {
      [] -> packedBits bytes index used pending width first next;
      (:) second rest -> if width > 0 && width <= 28 then let {
        low = andInt first (shiftLInt 1 width - 1);
        pair = orInt low (shiftLInt second width)
      } in packedBits bytes index used pending (width + width) pair
        (\i u p -> packedRefs bytes width rest i u p next)
      else packedBits bytes index used pending width first
        (\i u p -> packedRefs bytes width more i u p next)
    }
  };
  -- An owned node's kind, tag varint and arity are contiguous little-endian
  -- fields. When the tag takes one or two bytes and arity takes one, append
  -- the entire header before emitting the children.
  -- Most constructor entries fit in one machine field, including their
  -- references. Put their complete little-endian field through one flush.
  -- Wider entries use the same split header and reference writer.
  packedEntry bytes nodeWidth symbolWidth entry index used pending next = let {
    field width value = packedBits bytes index used pending width value next;
    old = packedEntryFields bytes nodeWidth symbolWidth entry index used pending next;
    var x = orInt (orInt (andInt x 127) 128) (shiftLInt (unsignedShiftRInt x 7) 8);
    node tag arity = orInt 3 (orInt (shiftLInt tag 2) (shiftLInt arity 10))
  } in case entry of {
    ENode tag children -> if unsignedLtInt tag 128 then case children of {
      [a,b] -> if nodeWidth <= 19 then let {
        mask = shiftLInt 1 nodeWidth - 1;
        refs = orInt (andInt a mask) (shiftLInt b nodeWidth)
      } in field (18 + nodeWidth + nodeWidth)
        (orInt (node tag 2) (shiftLInt refs 18)) else old;
      [a] -> if nodeWidth <= 38 then field (18 + nodeWidth) (orInt (node tag 1) (shiftLInt a 18)) else old;
      _ -> old
    } else old;
    EInt value -> let { x = zigzag value } in if unsignedLtInt x 128 then field 10 (shiftLInt x 2)
      else if unsignedLtInt x 16384 then field 18 (shiftLInt (var x) 2) else old;
    EText symbol -> field (2 + symbolWidth) (orInt 2 (shiftLInt symbol 2));
    EBits _ -> old
  };
  packedEntryFields bytes nodeWidth symbolWidth entry index used pending next = case entry of {
    ENode tag children -> let {
      arity = length children;
      refs = \i u p -> packedRefs bytes nodeWidth children i u p next
    } in if unsignedLtInt tag 16384 && arity < 128 then let {
      single = tag < 128;
      arityShift = if single then 10 else 18;
      encoded = if single then tag else
        orInt (orInt (andInt tag 127) 128) (shiftLInt (unsignedShiftRInt tag 7) 8);
      header = orInt 3 (orInt (shiftLInt encoded 2) (shiftLInt arity arityShift))
    } in packedBits bytes index used pending (arityShift + 8) header refs
    else packedBits bytes index used pending 2 3 (\i u p ->
      packedVar bytes i u p tag (\j v q -> packedVar bytes j v q arity refs));
    EInt value -> packedBits bytes index used pending 2 0 (\i u p ->
      packedVar bytes i u p (zigzag value) next);
    EBits bits -> packedBits bytes index used pending 2 1 (\i u p ->
      packedBits bytes i u p 64 bits next);
    EText symbol -> packedBits bytes index used pending 2 2 (\i u p ->
      packedBits bytes i u p symbolWidth symbol next)
  };
  packedEntries bytes nodeWidth symbolWidth entries index used pending next = case entries of {
    [] -> next index used pending;
    (:) entry rest -> packedEntry bytes nodeWidth symbolWidth entry index used pending
      (\i u p -> packedEntries bytes nodeWidth symbolWidth rest i u p next)
  };
  packedFinish bytes index used pending = do {
    if used == 0 then ioReturn () else writeByteArray bytes index pending;
    ioReturn (index * 8 + used)
  };
  encodeTables :: Int -> Layout -> Tables -> IO (Either String ByteArray);
  encodeTables schema geometry tables = case geometry of {
    Layout total _ _ _ nodeOffset _ _ _ rootOffset _ nodeWidth symbolWidth ->
      case tables of {
        Tables symbols entries roots _ _ _ _ -> do {
          bytes <- newByteArray total 0;
          headerEnd <- putHeader bytes schema geometry;
          symbolEnd <- putSymbols bytes 640 symbols;
          nodeEnd <- putEntries bytes (nodeOffset * 8) nodeWidth symbolWidth entries;
          rootEnd <- putReferences bytes (rootOffset * 8) nodeWidth roots;
          if headerEnd /= 640 || symbolEnd /= nodeOffset * 8 ||
             bytesForBits nodeEnd /= rootOffset || bytesForBits rootEnd /= total
          then ioReturn (Left "binary encoder internal measured-size mismatch") else do {
            crc <- checksum bytes total;
            end <- putBits bytes 608 32 crc;
            ioReturn (Right bytes)
          }
        }
      }
  };

  encodeTablesOwned :: Int -> Layout -> Tables -> IO (Either String ByteArray);
  encodeTablesOwned schema geometry tables = case geometry of {
    Layout total _ _ _ nodeOffset _ _ _ rootOffset _ nodeWidth symbolWidth ->
      case tables of {
        Tables symbols entries roots _ _ _ _ -> do {
          let { bulk = total <= 4194304 };
          bytes <- if bulk then byteArrayFromString (concatStringList
            ((:) (zeroText 80) (append (symbolChunks symbols) [zeroText (total - nodeOffset)])))
            else newByteArray total 0;
          headerEnd <- putHeader bytes schema geometry;
          symbolEnd <- if bulk then putOwnedSymbolSizes bytes 640 symbols
            else putOwnedSymbols bytes 640 symbols;
          nodeEnd <- packedEntries bytes nodeWidth symbolWidth entries nodeOffset 0 0 (packedFinish bytes);
          rootEnd <- packedRefs bytes nodeWidth roots rootOffset 0 0 (packedFinish bytes);
          if headerEnd /= 640 || symbolEnd /= nodeOffset * 8 ||
             bytesForBits nodeEnd /= rootOffset || bytesForBits rootEnd /= total
          then ioReturn (Left "binary encoder internal measured-size mismatch") else do {
            -- This private plan owns an array of exactly total bytes. The raw
            -- checksum entry still supports caller-specified prefix lengths.
            crc <- if total >= 1024 then byteArrayCRC32 bytes 76 4 else checksum bytes total;
            end <- putBits bytes 608 32 crc;
            ioReturn (Right bytes)
          }
        }
      }
  };

  -- A completed plan owns valid scalar text and its exact UTF-8 lengths.
  -- Encode that text in one bulk conversion, leaving zero-filled slots for
  -- the binary header, lengths and nodes. Bound the extra temporary text to
  -- 4 MiB; larger plans retain the streaming writer and its allocation bound.
  zeroText count = if count == 0 then "" else if count == 1 then stringFromCode 0
    else let { half = zeroText (count / 2); both = half ++ half }
      in if count % 2 == 0 then both else both ++ stringFromCode 0;
  symbolChunks symbols = case symbols of {
    [] -> [];
    (:) (Symbol text size) rest -> (:) (zeroText (varBytes size)) ((:) text (symbolChunks rest))
  };
  -- Symbol prefixes begin on a byte boundary in the completed owned layout.
  putOwnedSymbolSizes bytes position symbols = case symbols of {
    [] -> ioReturn position;
    (:) (Symbol _ size) rest ->
      packedVar bytes (position / 8) 0 0 size (\index _ _ ->
        putOwnedSymbolSizes bytes ((index + size) * 8) rest)
  };

  -- The owned writer follows a completed finite plan. Keep its loop decisions
  -- inside the IO action, so the host can tail-call through the state token.
  -- The exported raw writers retain their action-construction demand behavior.
  putOwnedText bytes byteIndex text index = ioBind (ioReturn ()) (\_ ->
    if index == stringLength text then ioReturn (byteIndex * 8) else let {
      code = stringCodeAt text index
    } in if code < 128 then do {
      writeByteArray bytes byteIndex code;
      putOwnedText bytes (byteIndex + 1) text (index + 1)
    } else do {
      next <- putScalar bytes (byteIndex * 8) code;
      putOwnedText bytes (next / 8) text (index + 1)
    });
  putOwnedSymbols bytes position symbols = case symbols of {
    [] -> ioReturn position;
    (:) (Symbol text size) rest ->
      packedVar bytes (position / 8) 0 0 size (\index _ _ -> do {
        more <- putOwnedText bytes index text 0;
        putOwnedSymbols bytes more rest
      })
  };

  data Cursor = Cursor ByteArray Int Int;
  data Read a = Read (Cursor -> IO (Either String ((,) a Cursor)));
  returnRead :: forall a. a -> Read a;
  returnRead value = Read (\cursor -> ioReturn (Right ((,) value cursor)));
  bindRead :: forall a b. Read a -> (a -> Read b) -> Read b;
  bindRead (Read action) next = Read (\cursor -> do {
    result <- action cursor;
    case result of {
      Left message -> ioReturn (Left message);
      Right ((,) value more) -> case next value of { Read following -> following more }
    }
  });
  instance Functor Read where {
    fmap function action = bindRead action (\value -> returnRead (function value))
  };
  instance Applicative Read where {
    pure = returnRead;
    (<*>) action argument = bindRead action (\function ->
      bindRead argument (\value -> returnRead (function value)))
  };
  instance Monad Read where { (>>=) = bindRead };
  failRead :: forall a. String -> Read a;
  failRead message = Read (\_ -> ioReturn (Left message));
  checkRead :: Bool -> String -> Read ();
  checkRead condition message = if condition then returnRead () else failRead message;
  liftEither :: forall a. Either String a -> Read a;
  liftEither result = case result of { Left message -> failRead message; Right value -> returnRead value };
  getBits :: Int -> Read Int;
  getBits width = Read (\cursor -> case cursor of {
    Cursor bytes position end ->
      if width < 0 || width > 64 || width > end - position
      then ioReturn (Left "truncated binary bitstream")
      else if position >= 0 && width > 0 && width <= 16
        then getSmallBits bytes position end width
      else getBitsAt bytes position end width 0 0
  });
  -- Tags, varint bytes and ordinary node IDs occupy at most three bytes.
  -- Keep the section check above and read exactly the same bytes in order,
  -- avoiding a fresh recursive IO result/cursor for each partial byte.
  getSmallBits bytes position end width = do {
    let { index = position / 8; offset = position % 8;
      available = 8 - offset; mask = shiftLInt 1 width - 1 };
    first <- readByteArray bytes index;
    second <- if width > available then readByteArray bytes (index + 1) else ioReturn 0;
    third <- if width > available + 8 then readByteArray bytes (index + 2) else ioReturn 0;
    let { bits = orInt (unsignedShiftRInt first offset)
      (orInt (shiftLInt second available) (shiftLInt third (available + 8)));
      result = andInt bits mask };
    seq result (ioReturn (Right ((,) result (Cursor bytes (position + width) end))))
  };
  getBitsAt :: ByteArray -> Int -> Int -> Int -> Int -> Int -> IO (Either String ((,) Int Cursor));
  getBitsAt bytes position end remaining consumed result =
    if remaining == 0 then ioReturn (Right ((,) result (Cursor bytes position end))) else do {
      let { offset = position % 8; take = min remaining (8 - offset); mask = shiftLInt 1 take - 1 };
      byte <- readByteArray bytes (position / 8);
      let { piece = andInt (unsignedShiftRInt byte offset) mask;
            next = orInt result (shiftLInt piece consumed) };
      seq next (getBitsAt bytes (position + take) end (remaining - take) (consumed + take) next)
    };
  remainingBits :: Read Int;
  remainingBits = Read (\cursor -> case cursor of {
    Cursor _ position end -> ioReturn (Right ((,) (end - position) cursor))
  });
  getVar :: Read Int;
  getVar = getVarAt 0 0;
  getVarAt :: Int -> Int -> Read Int;
  getVarAt index result = do {
    byte <- getBits 8;
    let { payload = andInt byte 127; continuing = andInt byte 128 /= 0 };
    checkRead (index < 9 || (not continuing && payload <= 1)) "binary varint overflows 64 bits";
    checkRead (continuing || index == 0 || payload /= 0) "noncanonical binary varint";
    let { next = orInt result (shiftLInt payload (index * 7)) };
    if continuing then seq next (getVarAt (index + 1) next) else returnRead next
  };
  getNat :: Int -> Read Int;
  getNat bound = do {
    value <- getVar;
    checkRead (value >= 0 && value <= bound) "binary unsigned quantity exceeds its limit";
    returnRead value
  };
  finishSection :: Read ();
  finishSection = do {
    remaining <- remainingBits;
    checkRead (remaining < 8) "binary section length/count mismatch";
    padding <- getBits remaining;
    checkRead (padding == 0) "nonzero binary section padding"
  };
  runSection :: forall a. ByteArray -> Int -> Int -> Read a -> IO (Either String a);
  runSection bytes offset size action = case bindRead action (\value -> do {
    finishSection; returnRead value
  }) of {
    Read parse -> do {
      result <- parse (Cursor bytes (offset * 8) ((offset + size) * 8));
      ioReturn (mapEither fst result)
    }
  };
  data Header = Header Layout Int;
  getHeader :: Limits -> Int -> Int -> Read Header;
  getHeader limits schema actualSize = do {
    version <- getBits 32;
    flags <- getBits 32;
    storedSchema <- getBits 32;
    headerSize <- getBits 32;
    total <- getBits 32;
    symbols <- getBits 32;
    symbolOffset <- getBits 32;
    symbolLength <- getBits 32;
    nodes <- getBits 32;
    nodeOffset <- getBits 32;
    nodeLength <- getBits 32;
    edges <- getBits 32;
    roots <- getBits 32;
    rootOffset <- getBits 32;
    rootLength <- getBits 32;
    nodeWidth <- getBits 32;
    symbolWidth <- getBits 32;
    crc <- getBits 32;
    checkRead (version == 1) "unsupported binary format version";
    checkRead (flags == 0) "unknown binary mandatory flags";
    checkRead (storedSchema == schema) "binary artifact schema mismatch";
    checkRead (headerSize == 80 && total == actualSize) "binary file/header length mismatch";
    checkRead (symbols <= maxSymbols limits && nodes <= maxNodes limits &&
      edges <= maxEdges limits && roots <= maxEdges limits) "binary table count limit exceeded";
    checkRead (symbolOffset == 80 && nodeOffset == 80 + symbolLength &&
      rootOffset == nodeOffset + nodeLength && total == rootOffset + rootLength)
      "binary sections overlap, have gaps, or contain trailing bytes";
    checkRead (symbols <= symbolLength && bytesForBits (nodes * 2) <= nodeLength)
      "binary section count exceeds its byte length";
    checkRead (nodeWidth == referenceWidth nodes && symbolWidth == referenceWidth symbols)
      "noncanonical binary reference width";
    checkRead (rootLength == bytesForBits (roots * nodeWidth)) "binary root section length mismatch";
    returnRead (Header (Layout total symbols symbolLength nodes nodeOffset nodeLength
      edges roots rootOffset rootLength nodeWidth symbolWidth) crc)
  };

  -- UTF-8 is decoded without a permissive host replacement-character path.
  -- Reject overlong encodings, isolated continuations, surrogates and >U+10FFFF.
  getContinuation :: Int -> Int -> Read Int;
  getContinuation remaining code = if remaining == 0 then returnRead code else do {
    byte <- getBits 8;
    checkRead (byte >= 128 && byte <= 191) "invalid binary UTF-8 continuation";
    getContinuation (remaining - 1) (orInt (shiftLInt code 6) (andInt byte 63))
  };
  getUtf8 :: Int -> Read String;
  getUtf8 size = getUtf8At size [];
  getUtf8With hints size = Read (\cursor -> case cursor of { Cursor bytes position end ->
    let { ordinary = \ignored -> case getUtf8At size [] of { Read parse -> parse cursor } } in
    if position < 0 || position % 8 /= 0 || size < 0 || size > (end - position) / 8
    then ordinary () else do {
      let { start = position / 8 };
      text <- case find (\hint -> stringLength hint == size) hints of {
        Just hint -> do {
          matches <- sameAscii bytes start hint size 0;
          if matches then ioReturn (Just hint) else alignedAscii bytes start (start + size) []
        };
        Nothing -> alignedAscii bytes start (start + size) []
      };
      case text of {
        Nothing -> ordinary ();
        Just value -> ioReturn (Right ((,) value (Cursor bytes (position + size * 8) end)))
      }
    }
  });
  -- A hint only supplies storage. Every byte must equal a canonical ASCII
  -- scalar from that text; a mismatch takes the independent ordinary path.
  sameAscii bytes start hint size index = if index == size then ioReturn True else do {
    byte <- readByteArray bytes (start + index);
    if byte < 128 && byte == stringCodeAt hint index then sameAscii bytes start hint size (index + 1)
    else ioReturn False
  };
  -- Scan in wire order. A malformed prefix cannot allocate a list for an
  -- unread suffix. Non-ASCII falls back to the strict scalar decoder.
  alignedAscii bytes index end chars =
    if index == end then ioReturn (Just (textFromChars (reverse chars))) else do {
      code <- readByteArray bytes index;
      if code < 128 then alignedAscii bytes (index + 1) end ((:) (charFromCode code) chars)
      else ioReturn Nothing
    };
  -- Both readers use the same scalar widths, leading-bit masks and canonical
  -- range checks. Continuations must be 10xxxxxx and stay inside this symbol.
  utf8Width :: Int -> Int;
  utf8Width byte = if byte < 128 then 1 else if byte >= 194 && byte <= 223 then 2
    else if byte >= 224 && byte <= 239 then 3 else if byte >= 240 && byte <= 244 then 4 else 0;
  utf8Lead :: Int -> Int -> Int;
  utf8Lead byte width = andInt byte (unsignedShiftRInt 127 width);
  canonicalScalar :: Int -> Int -> Bool;
  canonicalScalar width code = (width < 3 || code >= 2048) && (width < 4 || code >= 65536) && scalar code;
  getUtf8At :: Int -> [] Char -> Read String;
  getUtf8At remaining chars =
    if remaining == 0 then returnRead (textFromChars (reverse chars)) else do {
      first <- getBits 8;
      if first < 128 then getUtf8At (remaining - 1) ((:) (charFromCode first) chars) else do {
        let { width = utf8Width first };
        checkRead (width > 0) "invalid binary UTF-8 leading byte";
        checkRead (remaining >= width) "truncated binary UTF-8 scalar";
        code <- getContinuation (width - 1) (utf8Lead first width);
        checkRead (canonicalScalar width code) "noncanonical binary UTF-8 scalar";
        getUtf8At (remaining - width) ((:) (charFromCode code) chars)
      }
    };
  -- Legacy dispatch may need a strict UTF-8 bridge after raw bounded IO.
  -- The storage layer must check hasMagic FIRST: a recognized new-format
  -- file that fails decode must never be retried as legacy textual input.
  strictUtf8 :: Int -> ByteArray -> IO (Either String String);
  strictUtf8 limit bytes = catchIOError (strictUtf8Checked limit bytes)
    (\error -> ioReturn (Left ("binary UTF-8 IO failure: " ++ textFromChars (ioeGetErrorString error))));
  strictUtf8Checked :: Int -> ByteArray -> IO (Either String String);
  strictUtf8Checked limit bytes =
    if limit < 0 || limit > 2147483647 then ioReturn (Left "invalid UTF-8 byte limit") else do {
      size <- lengthByteArray bytes;
      if size > limit then ioReturn (Left "UTF-8 file byte limit exceeded")
      else runSection bytes 0 size (getUtf8 size)
    };
  getSymbols :: Limits -> Int -> Read (IntMap Symbol);
  getSymbols limits count = getSymbolsAt limits count 0 0 M.empty IM.empty;
  getSymbolsAt :: Limits -> Int -> Int -> Int -> Map String Int -> IntMap Symbol -> Read (IntMap Symbol);
  getSymbolsAt = getSymbolsWith [];
  getSymbolsWith hints limits count index total names symbols =
    if index == count then returnRead symbols else do {
      size <- getNat (maxSymbolBytes limits);
      remaining <- remainingBits;
      checkRead (size <= remaining / 8) "truncated binary symbol";
      checkRead (size <= maxTotalSymbolBytes limits - total) "binary total symbol byte limit exceeded";
      text <- getUtf8With hints size;
      nextNames <- case intern compareString text names of {
        Found _ -> failRead "duplicate binary symbol"; Inserted fill -> returnRead (fill index)
      };
      let { nextTotal = total + size;
            nextSymbols = IM.insert index (Symbol text size) symbols };
      seq nextTotal (seq nextNames (seq nextSymbols
        (getSymbolsWith hints limits count (index + 1) nextTotal nextNames nextSymbols)))
    };

  -- Resource summaries are separate from codec limits. In particular these
  -- helpers do not change defaultLimits or the legacy expanded-work policy.
  -- N counts every expanded node occurrence; T counts UTF-8 text bytes at
  -- every occurrence. The validated legacy work measure is exactly N + T.
  data ResourceStats = ResourceStats Int Int Int Int Int Int Int Int Int Int;
  resourceBytes :: ResourceStats -> Int;
  resourceBytes (ResourceStats x _ _ _ _ _ _ _ _ _) = x;
  resourceNodes :: ResourceStats -> Int;
  resourceNodes (ResourceStats _ x _ _ _ _ _ _ _ _) = x;
  resourceEdges :: ResourceStats -> Int;
  resourceEdges (ResourceStats _ _ x _ _ _ _ _ _ _) = x;
  resourceSymbols :: ResourceStats -> Int;
  resourceSymbols (ResourceStats _ _ _ x _ _ _ _ _ _) = x;
  resourceSymbolBytes :: ResourceStats -> Int;
  resourceSymbolBytes (ResourceStats _ _ _ _ x _ _ _ _ _) = x;
  resourceDepth :: ResourceStats -> Int;
  resourceDepth (ResourceStats _ _ _ _ _ x _ _ _ _) = x;
  resourceMaxSymbolBytes :: ResourceStats -> Int;
  resourceMaxSymbolBytes (ResourceStats _ _ _ _ _ _ x _ _ _) = x;
  resourceExpandedNodes :: ResourceStats -> Int;
  resourceExpandedNodes (ResourceStats _ _ _ _ _ _ _ x _ _) = x;
  resourceExpandedTextBytes :: ResourceStats -> Int;
  resourceExpandedTextBytes (ResourceStats _ _ _ _ _ _ _ _ x _) = x;
  resourceExpandedWork :: ResourceStats -> Int;
  resourceExpandedWork (ResourceStats _ _ _ _ _ _ _ _ _ x) = x;

  -- Int is the same signed Int64 on both hosts. Check before arithmetic,
  -- including layout bit totals, rather than relying on host Integer or a
  -- particular default limit. A Graph accepted under ANY validLimits is
  -- supported: counts/work <= 2^31-1, depth <= 65536, layout bits < 2^40.
  measuredAdd :: Int -> Int -> Either String Int;
  measuredAdd left right =
    if left < 0 || right < 0 || right > 9223372036854775807 - left
    then Left "binary resource addition overflow"
    else let { result = left + right } in seq result (Right result);
  measuredMultiply :: Int -> Int -> Either String Int;
  measuredMultiply left right =
    if left < 0 || right < 0 then Left "binary resource multiplication overflow"
    else if left == 0 || right == 0 then Right 0
    else if left > 9223372036854775807 / right
      then Left "binary resource multiplication overflow"
      else let { result = left * right } in seq result (Right result);
  measuredBytesForBits :: Int -> Either String Int;
  measuredBytesForBits bits = do {
    padded <- measuredAdd bits 7;
    Right (padded / 8)
  };

  -- These two entry points own the original planner and layout. No public
  -- Tables value is admitted as a Graph: the table-to-graph helper is private
  -- and receives only the canonical, bounded output of this planner.
  planMeasured :: Limits -> [] Value -> Either String ((,) Tables ResourceStats);
  planMeasured limits roots = do {
    tables <- plan limits roots;
    geometry <- layout limits tables;
    graph <- graphFromPlan limits tables;
    stats <- graphResourceStats graph;
    case geometry of {
      Layout total _ _ _ _ _ _ _ _ _ _ _ -> do {
        ensure (resourceBytes stats == total) "binary resource layout mismatch";
        Right ((,) tables stats)
      }
    }
  };
  planGraph :: Limits -> [] Value -> Either String Graph;
  planGraph limits roots = bindEither (prepareGraphPlan limits roots) realizeGraphPlan;
  -- The constructor stays private. Only a successful plan and layout can
  -- supply the exact tables subsequently used for canonical graph admission.
  data GraphPlan = GraphPlan Limits Tables;
  prepareGraphPlan :: Limits -> [] Value -> Either String GraphPlan;
  prepareGraphPlan = prepareGraphWith NoAtomIds;
  prepareGraphPlanWithAtoms :: AtomShapes -> Limits -> [] Value -> Either String GraphPlan;
  prepareGraphPlanWithAtoms shapes = prepareGraphWith (emptyAtomIds shapes);
  prepareGraphWith initial limits roots = do {
    tables <- planWith initial limits roots;
    geometry <- layout limits tables;
    seq geometry (Right (GraphPlan limits tables))
  };
  realizeGraphPlan :: GraphPlan -> Either String Graph;
  realizeGraphPlan (GraphPlan limits tables) = graphFromPlan limits tables;
  graphNodeDepth :: Graph -> Int -> Either String Int;
  graphNodeDepth graph index = case graph of {
    Graph nodes _ -> case IM.lookup index nodes of {
      Nothing -> Left "binary graph node index out of range";
      Just parsed -> Right (parsedDepth parsed)
    };
    DenseGraph nodes _ _ -> case denseLookup nodes index of {
      Nothing -> Left "binary graph node index out of range";
      Just (DenseInput _ depth _ _) -> Right depth
    }
  };
  -- Only plan/prepareGraphPlan can call this private path. Their first-use
  -- traversal interns each symbol and entry once, creates a node only after
  -- its children, charges every expanded occurrence, and checks depth, table
  -- counts and byte limits. Disk bytes always go through the separate decoder.
  graphFromPlan :: Limits -> Tables -> Either String Graph;
  graphFromPlan limits (Tables symbols entries roots symbolCount _ rootCount _) = do {
    let { table = IM.fromDistinctAscList (zip (range 0 (symbolCount - 1)) symbols) };
    nodes <- materializeEntries limits table entries 0 IM.empty;
    graphPlanRoots limits nodes rootCount roots 0 0;
    Right (Graph nodes roots)
  };
  materializeEntries limits symbols entries index nodes = case entries of {
    [] -> Right nodes;
    (:) entry rest -> do {
      parsed <- buildParsed limits symbols nodes entry;
      let { next = IM.insert index parsed nodes } in
        seq next (materializeEntries limits symbols rest (index + 1) next)
    }
  };
  graphPlanRoots :: Limits -> IntMap Parsed -> Int -> [] Int -> Int -> Int -> Either String ();
  graphPlanRoots limits nodes count roots index work = case roots of {
    [] -> ensure (index == count) "binary root count mismatch";
    (:) root rest -> do {
      ensure (index < count) "binary root count mismatch";
      case IM.lookup root nodes of {
        Nothing -> Left "binary root reference out of range";
        Just parsed -> do {
          ensure (parsedWork parsed <= maxExpandedWork limits - work)
            "binary expanded root-work limit exceeded";
          nextIndex <- measuredAdd index 1;
          nextWork <- measuredAdd work (parsedWork parsed);
          graphPlanRoots limits nodes count rest nextIndex nextWork
        }
      }
    }
  };

  -- One memo entry per physical node; each edge occurrence adds that child's
  -- memo once. The Value field is inspected only for a physical text leaf,
  -- never recursively. Repeated roots are counted just like repeated edges.
  data NodeResources = NodeResources Int Int;
  -- Expanded N/T; physical edges/symbols/text bytes/symbol-section bytes;
  -- node bits excluding text-reference payloads (whose width is known later).
  data NodeMeasurement = NodeMeasurement Int Int Int Int Int Int Int;
  -- Memo; physical edges/symbols/text bytes/largest text/symbol-section bytes;
  -- node bits excluding text-reference payloads; maximum validated depth.
  data ResourceState = ResourceState (IntMap NodeResources) Int Int Int Int Int Int Int;
  measureReferences :: IntMap NodeResources -> [] Int -> Int -> Int -> Int -> Either String ((,,) Int Int Int);
  measureReferences memo references nodes text count = case references of {
    [] -> Right ((,,) nodes text count);
    (:) index rest -> case IM.lookup index memo of {
      Nothing -> Left "binary resource reference has no preceding node";
      Just (NodeResources childNodes childText) -> do {
        nextNodes <- measuredAdd nodes childNodes;
        nextText <- measuredAdd text childText;
        nextCount <- measuredAdd count 1;
        measureReferences memo rest nextNodes nextText nextCount
      }
    }
  };
  measureParsed :: Int -> IntMap NodeResources -> Parsed -> Either String NodeMeasurement;
  measureParsed nodeWidth memo (Parsed entry value _ _) = case entry of {
    EInt integer -> do {
      payload <- measuredMultiply 8 (varBytes (zigzag integer));
      bits <- measuredAdd 2 payload;
      Right (NodeMeasurement 1 0 0 0 0 0 bits)
    };
    EBits _ -> Right (NodeMeasurement 1 0 0 0 0 0 66);
    EText _ -> case value of {
      VText text -> do {
        size <- utf8Size 2147483647 text;
        symbolLength <- measuredAdd (varBytes size) size;
        Right (NodeMeasurement 1 size 0 1 size symbolLength 2)
      };
      VInt _ -> Left "binary graph internal text-node invariant failure";
      VBits _ -> Left "binary graph internal text-node invariant failure";
      VNode _ _ -> Left "binary graph internal text-node invariant failure"
    };
    ENode tag children -> do {
      totals <- measureReferences memo children 1 0 0;
      case totals of {
        (,,) nodes text arity -> do {
          prefixBytes <- measuredAdd (varBytes tag) (varBytes arity);
          prefixBits <- measuredMultiply 8 prefixBytes;
          childBits <- measuredMultiply arity nodeWidth;
          payload <- measuredAdd prefixBits childBits;
          bits <- measuredAdd 2 payload;
          Right (NodeMeasurement nodes text arity 0 0 0 bits)
        }
      }
    }
  };
  measureGraphNodes :: IntMap Parsed -> Int -> Int -> Int -> ResourceState -> Either String ResourceState;
  measureGraphNodes nodes count nodeWidth index state =
    if index == count then Right state else case state of {
      ResourceState memo edges symbols symbolBytes largest symbolLength nodeBits depth ->
        case IM.lookup index nodes of {
          Nothing -> Left "binary resource graph node index gap";
          Just parsed -> do {
            measurement <- measureParsed nodeWidth memo parsed;
            case measurement of {
              NodeMeasurement expandedNodes expandedText arity texts bytes wireBytes bits -> do {
                work <- measuredAdd expandedNodes expandedText;
                ensure (work == parsedWork parsed) "binary resource expanded-work mismatch";
                nextEdges <- measuredAdd edges arity;
                nextSymbols <- measuredAdd symbols texts;
                nextSymbolBytes <- measuredAdd symbolBytes bytes;
                nextSymbolLength <- measuredAdd symbolLength wireBytes;
                nextNodeBits <- measuredAdd nodeBits bits;
                nextIndex <- measuredAdd index 1;
                let { nextLargest = max largest bytes;
                      nextDepth = max depth (parsedDepth parsed);
                      nextMemo = IM.insert index (NodeResources expandedNodes expandedText) memo };
                seq nextLargest (seq nextDepth (seq nextMemo
                  (measureGraphNodes nodes count nodeWidth nextIndex
                    (ResourceState nextMemo nextEdges nextSymbols nextSymbolBytes nextLargest
                      nextSymbolLength nextNodeBits nextDepth))))
              }
            }
          }
        }
    };
  -- Both graph constructors are private and contain summaries checked by
  -- the planner or wire decoder. A consumer needing only total expanded work
  -- can sum root summaries without rebuilding the complete resource report.
  -- Repeated roots are charged repeatedly, including shared descendants.
  graphExpandedWork :: Graph -> Either String Int;
  graphExpandedWork graph = graphRootWork graph (graphRoots graph) 0;
  graphRootWork graph roots total = case roots of {
    [] -> Right total;
    (:) index rest -> do {
      work <- case graph of {
        Graph nodes _ -> case IM.lookup index nodes of {
          Nothing -> Left "binary resource root has no node";
          Just parsed -> Right (parsedWork parsed)
        };
        DenseGraph nodes _ _ -> case denseLookup nodes index of {
          Nothing -> Left "binary resource root has no node";
          Just (DenseInput _ _ used _) -> Right used
        }
      };
      next <- measuredAdd total work;
      graphRootWork graph rest next
    }
  };
  graphResourceStats :: Graph -> Either String ResourceStats;
  graphResourceStats graph = graphResourceStatsFrom (graphMap graph) (graphRoots graph);
  graphResourceStatsFrom :: IntMap Parsed -> [] Int -> Either String ResourceStats;
  graphResourceStatsFrom nodes roots = do {
    let { count = IM.size nodes; nodeWidth = referenceWidth count };
    measured <- measureGraphNodes nodes count nodeWidth 0
      (ResourceState IM.empty 0 0 0 0 0 0 0);
    case measured of {
      ResourceState memo edges symbols symbolBytes largest symbolLength nodeBits depth -> do {
        rootTotals <- measureReferences memo roots 0 0 0;
        case rootTotals of {
          (,,) expandedNodes expandedText rootCount -> do {
            work <- measuredAdd expandedNodes expandedText;
            textBits <- measuredMultiply symbols (referenceWidth symbols);
            allNodeBits <- measuredAdd nodeBits textBits;
            nodeLength <- measuredBytesForBits allNodeBits;
            rootBits <- measuredMultiply rootCount nodeWidth;
            rootLength <- measuredBytesForBits rootBits;
            nodeOffset <- measuredAdd 80 symbolLength;
            rootOffset <- measuredAdd nodeOffset nodeLength;
            total <- measuredAdd rootOffset rootLength;
            Right (ResourceStats total count edges symbols symbolBytes depth largest
              expandedNodes expandedText work)
          }
        }
      }
    }
  };

  -- Parsed values share their children. Depth/work summaries are computed
  -- once per node and checked before exposing any root to an AST adapter.
  data Parsed = Parsed Entry Value Int Int;
  -- A Graph is validated raw syntax, never checked typing evidence. Its
  -- constructor is deliberately hidden. Typed adapters memoize by their
  -- expected shape and these canonical node IDs, preserving actual sharing
  -- instead of repeatedly reconstructing a shared subtree through Value.
  data DecodeId = DecodeId;
  data Graph = Graph (IntMap Parsed) ([] Int) | DenseGraph (V.IndexVec DecodeId DenseInput) ([] Int) (V.IndexVec DecodeId Parsed);
  data GraphNode = GInt Int | GBits Int | GText String | GNode Int ([] Int);
  graphRoots :: Graph -> [] Int;
  graphRoots graph = case graph of { Graph _ roots -> roots; DenseGraph _ roots _ -> roots };
  graphNodeCount :: Graph -> Int;
  graphNodeCount graph = case graph of { Graph nodes _ -> IM.size nodes; DenseGraph nodes _ _ -> V.count nodes };
  graphMap :: Graph -> IntMap Parsed;
  graphMap graph = case graph of {
    Graph nodes _ -> nodes;
    DenseGraph _ _ nodes -> IM.fromDistinctAscList (zip (range 0 (V.count nodes - 1)) (V.toList nodes))
  };
  denseLookup :: forall a. V.IndexVec DecodeId a -> Int -> Maybe a;
  denseLookup nodes index =
    if index < 0 || index >= V.count nodes then Nothing else Just (V.at nodes (V.fromInt index));
  graphParsed :: Graph -> Int -> Maybe Parsed;
  graphParsed graph index = case graph of {
    Graph nodes _ -> IM.lookup index nodes; DenseGraph _ _ nodes -> denseLookup nodes index
  };
  lookupGraphNode :: Graph -> Int -> Either String GraphNode;
  lookupGraphNode graph index = case graph of {
    Graph _ _ -> case graphParsed graph index of {
      Nothing -> Left "binary graph node index out of range";
      Just (Parsed entry value _ _) -> case entry of {
        EInt integer -> Right (GInt integer);
        EBits bits -> Right (GBits bits);
        ENode tag children -> Right (GNode tag children);
        EText _ -> case value of {
          VText text -> Right (GText text);
          _ -> Left "binary graph internal text-node invariant failure"
        }
      }
    };
    DenseGraph nodes _ _ -> case denseLookup nodes index of {
      Nothing -> Left "binary graph node index out of range";
      Just (DenseInput entry _ _ text) -> case entry of {
        EInt integer -> Right (GInt integer);
        EBits bits -> Right (GBits bits);
        ENode tag children -> Right (GNode tag children);
        EText _ -> Right (GText text)
      }
    }
  };
  parsedEntry :: Parsed -> Entry;
  parsedEntry (Parsed entry _ _ _) = entry;
  parsedValue :: Parsed -> Value;
  parsedValue (Parsed _ value _ _) = value;
  parsedDepth :: Parsed -> Int;
  parsedDepth (Parsed _ _ depth _) = depth;
  parsedWork :: Parsed -> Int;
  parsedWork (Parsed _ _ _ work) = work;
  getChildIds :: Int -> Int -> Int -> [] Int -> Read ([] Int);
  getChildIds width parent remaining acc =
    if remaining == 0 then returnRead (reverse acc) else do {
      index <- getChildId width parent;
      getChildIds width parent (remaining - 1) ((:) index acc)
    };
  getChildId width parent = do {
    index <- getBits width;
    checkRead (index < parent) "binary node has a forward, cyclic, or out-of-range reference";
    returnRead index
  };
  getEntry :: Limits -> Int -> Int -> Int -> Int -> Int -> Read Entry;
  getEntry limits nodeWidth symbolWidth parent symbols remainingEdges = do {
    kind <- getBits 2;
    if kind == 0 then do { bits <- getVar; returnRead (EInt (unzigzag bits)) }
    else if kind == 1 then do { bits <- getBits 64; returnRead (EBits bits) }
    else if kind == 2 then do {
      symbol <- getBits symbolWidth;
      checkRead (symbol < symbols) "binary symbol reference out of range";
      returnRead (EText symbol)
    } else do {
      tag <- getNat 2147483647;
      arity <- getNat remainingEdges;
      remaining <- remainingBits;
      checkRead (arity <= remaining / nodeWidth) "truncated binary child references";
      -- Short nodes can build the final list in wire order. Each reference
      -- must pass its backward bound before reading the following field.
      let { child = getChildId nodeWidth parent };
      case arity of {
        0 -> returnRead (ENode tag []);
        1 -> do { a <- child; returnRead (ENode tag [a]) };
        2 -> do { a <- child; b <- child; returnRead (ENode tag [a,b]) };
        3 -> do { a <- child; b <- child; c <- child; returnRead (ENode tag [a,b,c]) };
        _ -> do { children <- getChildIds nodeWidth parent arity []; returnRead (ENode tag children) }
      }
    }
  };
  buildChildren :: Limits -> IntMap Parsed -> [] Int -> [] Value -> Int -> Int -> Either String ((,,) ([] Value) Int Int);
  buildChildren limits nodes children values depth work = case children of {
    [] -> Right ((,,) (reverse values) depth work);
    (:) index rest -> case IM.lookup index nodes of {
      Nothing -> Left "binary child reference has no preceding node";
      Just child -> do {
        ensure (parsedWork child <= maxExpandedWork limits - work) "binary expanded-work limit exceeded";
        let { nextDepth = max depth (parsedDepth child + 1); nextWork = work + parsedWork child };
        ensure (nextDepth <= maxDepth limits) "binary graph depth limit exceeded";
        seq nextDepth (seq nextWork (buildChildren limits nodes rest
          ((:) (parsedValue child) values) nextDepth nextWork))
      }
    }
  };
  buildParsed :: Limits -> IntMap Symbol -> IntMap Parsed -> Entry -> Either String Parsed;
  buildParsed limits symbols nodes entry = case entry of {
    EInt value -> if maxExpandedWork limits < 1 then Left "binary expanded-work limit exceeded"
      else Right (Parsed entry (VInt value) 1 1);
    EBits bits -> if maxExpandedWork limits < 1 then Left "binary expanded-work limit exceeded"
      else Right (Parsed entry (VBits bits) 1 1);
    EText index -> case IM.lookup index symbols of {
      Nothing -> Left "binary symbol reference has no symbol";
      Just (Symbol text size) -> if size >= maxExpandedWork limits
        then Left "binary expanded-work limit exceeded"
        else Right (Parsed entry (VText text) 1 (1 + size))
    };
    ENode tag children -> do {
      ensure (maxExpandedWork limits >= 1) "binary expanded-work limit exceeded";
      built <- buildChildren limits nodes children [] 1 1;
      case built of { (,,) values depth work -> Right (Parsed entry (VNode tag values) depth work) }
    }
  };
  getNodes :: Limits -> Layout -> IntMap Symbol -> Read (IntMap Parsed);
  getNodes limits (Layout _ symbolCount _ count _ _ edges _ _ _ nodeWidth symbolWidth) symbols =
    getNodesAt limits symbols symbolCount count nodeWidth symbolWidth 0 0 edges M.empty IM.empty;
  getNodesAt :: Limits -> IntMap Symbol -> Int -> Int -> Int -> Int -> Int -> Int -> Int -> Map Entry Int -> IntMap Parsed -> Read (IntMap Parsed);
  getNodesAt limits symbols symbolCount count nodeWidth symbolWidth index nextSymbol remainingEdges keys nodes =
    if index == count then do {
      checkRead (remainingEdges == 0) "binary edge count mismatch";
      checkRead (nextSymbol == symbolCount) "unused binary symbol table entries";
      returnRead nodes
    } else do {
      entry <- getEntry limits nodeWidth symbolWidth index symbolCount remainingEdges;
      nextKeys <- case intern compareEntry entry keys of {
        Found _ -> failRead "duplicate binary structural node"; Inserted fill -> returnRead (fill index)
      };
      followingSymbol <- case entry of {
        EText symbol -> do {
          checkRead (symbol == nextSymbol) "noncanonical binary symbol first-use order";
          returnRead (nextSymbol + 1)
        };
        _ -> returnRead nextSymbol
      };
      parsed <- liftEither (buildParsed limits symbols nodes entry);
      let { nextNodes = IM.insert index parsed nodes;
            nextEdges = remainingEdges - entryEdges entry };
      seq nextKeys (seq nextNodes (seq nextEdges
        (getNodesAt limits symbols symbolCount count nodeWidth symbolWidth (index + 1)
          followingSymbol nextEdges nextKeys nextNodes)))
    };
  getRoots :: Limits -> IntMap Parsed -> Int -> Int -> Read ([] Int);
  getRoots limits nodes width count = getRootsAt limits nodes width count 0 [];
  getRootsAt :: Limits -> IntMap Parsed -> Int -> Int -> Int -> [] Int -> Read ([] Int);
  getRootsAt limits nodes width remaining work roots =
    if remaining == 0 then returnRead (reverse roots) else do {
      index <- getBits width;
      case IM.lookup index nodes of {
        Nothing -> failRead "binary root reference out of range";
        Just root -> do {
          checkRead (parsedWork root <= maxExpandedWork limits - work) "binary expanded root-work limit exceeded";
          let { nextWork = work + parsedWork root };
          seq nextWork (getRootsAt limits nodes width (remaining - 1) nextWork ((:) index roots))
        }
      }
    };
  data CanonicalTask = WalkIds ([] Int) | CloseId Int;
  canonicalGraph :: IntMap Parsed -> Int -> [] Int -> Either String ();
  canonicalGraph nodes count roots = canonicalTasks nodes count 0 ((:) (WalkIds roots) []);
  canonicalTasks :: IntMap Parsed -> Int -> Int -> [] CanonicalTask -> Either String ();
  canonicalTasks nodes count next tasks = case tasks of {
    [] -> ensure (next == count) "unused binary node table entries";
    (:) task rest -> case task of {
      CloseId index -> if index /= next then Left "noncanonical binary node postorder"
        else canonicalTasks nodes count (next + 1) rest;
      WalkIds references -> case references of {
        [] -> canonicalTasks nodes count next rest;
        (:) index more -> if index < next
          then canonicalTasks nodes count next ((:) (WalkIds more) rest)
          else case IM.lookup index nodes of {
            Nothing -> Left "binary graph contains an absent node";
            Just parsed -> case parsedEntry parsed of {
              ENode _ children -> canonicalTasks nodes count next
                ((:) (WalkIds children) ((:) (CloseId index) ((:) (WalkIds more) rest)));
              _ -> canonicalTasks nodes count next ((:) (CloseId index) ((:) (WalkIds more) rest))
            }
          }
      }
    }
  };
  collectRoots :: IntMap Parsed -> [] Int -> [] Value -> Either String ([] Value);
  collectRoots nodes roots values = case roots of {
    [] -> Right (reverse values);
    (:) index rest -> case IM.lookup index nodes of {
      Nothing -> Left "binary root has no decoded node";
      Just parsed -> collectRoots nodes rest ((:) (parsedValue parsed) values)
    }
  };
  collectGraphRoots :: Graph -> [] Int -> [] Value -> Either String ([] Value);
  collectGraphRoots graph roots values = case roots of {
    [] -> Right (reverse values);
    (:) index rest -> case graphParsed graph index of {
      Nothing -> Left "binary root has no decoded node";
      Just parsed -> collectGraphRoots graph rest ((:) (parsedValue parsed) values)
    }
  };
  decode :: Limits -> Int -> ByteArray -> IO (Either String ([] Value));
  decode limits schema bytes = catchIOError (decodeChecked limits schema bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  decodeChecked :: Limits -> Int -> ByteArray -> IO (Either String ([] Value));
  decodeChecked limits schema bytes = do {
    graph <- decodeGraphChecked [] limits schema bytes;
    ioReturn (bindEither graph (\value -> collectGraphRoots value (graphRoots value) []))
  };
  decodeGraph :: Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraph = decodeGraphWithText [];
  -- Node summaries still use the original per-root limit. Only the
  -- root-section sum uses aggregate, before any Graph reaches an adapter.
  decodeGraphRootBounded :: Limits -> Int -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraphRootBounded limits aggregate schema bytes = catchIOError
    (decodeGraphAfterHeaderRootBounded [] limits aggregate schema
      (\_ _ -> ioReturn (Right ())) bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  decodeGraphWithText :: [] String -> Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraphWithText hints limits schema bytes = catchIOError (decodeGraphChecked hints limits schema bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  -- The header bounds the complete input, including its four-byte checksum
  -- field. Check integrity before allocating symbol or node tables. Public
  -- prefix checksums can also operate on a portion of a larger byte array.
  checkedGraphTables :: [] String -> Limits -> Int -> ByteArray -> Int -> Layout -> Int -> IO (Either String Graph);
  checkedGraphTables hints limits aggregate bytes size geometry expectedCRC = seq hints (do {
    actual <- if size >= 1024 then byteArrayCRC32 bytes 76 4 else checksum bytes size;
    if actual /= expectedCRC then ioReturn (Left "binary checksum mismatch")
    else decodeGraphTables hints limits aggregate bytes geometry
  });
  decodeGraphChecked :: [] String -> Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraphChecked hints limits schema bytes =
    decodeGraphAfterHeader hints limits schema (\_ _ -> ioReturn (Right ())) bytes;
  -- A schema can reject from bounded framing before CRC/table allocation.
  -- Passing the gate still runs the ordinary checksum and canonical graph reader.
  decodeGraphWithGate :: Limits -> Int -> (ByteArray -> Layout -> IO (Either String ())) ->
    ByteArray -> IO (Either String Graph);
  decodeGraphWithGate limits schema gate bytes = catchIOError
    (decodeGraphAfterHeader [] limits schema gate bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  -- The geometry comes from getHeader. A short symbol has a one-byte length.
  firstShortTextMatches :: ByteArray -> Layout -> String -> IO Bool;
  firstShortTextMatches bytes (Layout _ count section _ _ _ _ _ _ _ _ _) expected =
    let { n = stringLength expected } in
    if count == 0 || n >= 128 || section < n + 1 then ioReturn False else do {
      size <- readByteArray bytes 80;
      if size == n then sameAscii bytes 81 expected n 0 else ioReturn False
    };
  decodeGraphAfterHeader hints limits schema gate bytes =
    decodeGraphAfterHeaderRootBounded hints limits (maxExpandedWork limits) schema gate bytes;
  decodeGraphAfterHeaderRootBounded :: [] String -> Limits -> Int -> Int ->
    (ByteArray -> Layout -> IO (Either String ())) -> ByteArray -> IO (Either String Graph);
  decodeGraphAfterHeaderRootBounded hints limits aggregate schema gate bytes =
    if not (validLimits limits) then ioReturn (Left "invalid binary codec limits")
    else if not (validRootBudget aggregate) then ioReturn (Left "invalid binary root-work budget")
    else if schema < 0 || schema > 2147483647 then ioReturn (Left "binary schema ID out of range")
    else do {
      size <- lengthByteArray bytes;
      if size < 80 || size > maxBytes limits then ioReturn (Left "binary file byte limit exceeded or truncated header")
      else do {
        recognized <- hasMagic bytes;
        if not recognized then ioReturn (Left "binary magic mismatch") else do {
          header <- runSection bytes 8 72 (getHeader limits schema size);
          case header of {
            Left message -> ioReturn (Left message);
            Right (Header geometry expectedCRC) -> do {
              allowed <- gate bytes geometry;
              case allowed of {
                Left message -> ioReturn (Left message);
                Right () -> checkedGraphTables hints limits aggregate bytes size geometry expectedCRC
              }
            }
          }
        }
      }
    };
  decodeTables :: Limits -> ByteArray -> Layout -> IO (Either String ([] Value));
  -- This low-level compatibility API accepts caller-supplied Layout values.
  -- Keep its historical incremental checks and allocation behavior.
  decodeTables limits bytes geometry = do {
    graph <- decodeGraphTablesUsing decodeNodesAndRoots [] limits (maxExpandedWork limits) bytes geometry;
    ioReturn (bindEither graph (\value -> collectGraphRoots value (graphRoots value) []))
  };
  decodeGraphTables :: [] String -> Limits -> Int -> ByteArray -> Layout -> IO (Either String Graph);
  decodeGraphTables hints limits aggregate bytes geometry =
    decodeGraphTablesUsing decodeDenseNodesAndRoots hints limits aggregate bytes geometry;
  decodeGraphTablesUsing :: (Limits -> Int -> ByteArray -> Layout -> IntMap Symbol -> IO (Either String Graph)) ->
    [] String -> Limits -> Int -> ByteArray -> Layout -> IO (Either String Graph);
  decodeGraphTablesUsing decodeNodes hints limits aggregate bytes geometry = case geometry of {
    Layout _ symbolCount symbolLength _ _ _ _ _ _ _ _ _ -> do {
      symbolResult <- runSection bytes 80 symbolLength (getSymbolsWith (filter (\t -> stringLength t >= 256) (take 9 hints)) limits symbolCount 0 0 M.empty IM.empty);
      case symbolResult of {
        Left message -> ioReturn (Left message);
        Right symbols -> decodeNodes limits aggregate bytes geometry symbols
      }
    }
  };
  decodeNodesAndRoots :: Limits -> Int -> ByteArray -> Layout -> IntMap Symbol -> IO (Either String Graph);
  decodeNodesAndRoots limits aggregate bytes geometry symbols = case geometry of {
    Layout _ _ _ nodeCount nodeOffset nodeLength _ rootCount rootOffset rootLength nodeWidth _ -> do {
      nodeResult <- runSection bytes nodeOffset nodeLength (getNodes limits geometry symbols);
      case nodeResult of {
        Left message -> ioReturn (Left message);
        Right nodes -> do {
          rootResult <- runSection bytes rootOffset rootLength (getRoots (withExpandedWork limits aggregate) nodes nodeWidth rootCount);
          case rootResult of {
            Left message -> ioReturn (Left message);
            Right roots -> ioReturn (do {
              canonicalGraph nodes nodeCount roots;
              Right (Graph nodes roots)
            })
          }
        }
      }
    }
  };
  -- The verified wire layout supplies exact dense slots. Keep the mutable
  -- builder inside decoding and publish only its frozen, checked snapshot.
  data DenseInput = DenseInput Entry Int Int String;
  liftReadIO :: forall a. IO a -> Read a;
  liftReadIO action = Read (\cursor -> do {
    value <- action; ioReturn (Right ((,) value cursor))
  });
  -- Keep every read of one entry and its write in the same world-state
  -- action, rather than crossing the IO boundary for each child edge.
  denseChildrenMeta :: Limits -> V.FixedBuilder IOWorld DecodeId DenseInput -> [] Int -> Int -> Int -> ST IOWorld (Either String ((,) Int Int));
  denseChildrenMeta limits nodes children depth work = case children of {
    [] -> stReturn (Right ((,) depth work));
    (:) index rest -> stBind (V.fixedGet nodes (V.fromInt index)) (\checked ->
      case checked of { DenseInput _ childDepth childWork _ ->
        if childWork > maxExpandedWork limits - work then stReturn (Left "binary expanded-work limit exceeded")
        else let { nextDepth = max depth (childDepth + 1); nextWork = work + childWork } in
          if nextDepth > maxDepth limits then stReturn (Left "binary graph depth limit exceeded")
          else seq nextDepth (seq nextWork (denseChildrenMeta limits nodes rest nextDepth nextWork))
      })
  };
  denseInsert :: Limits -> IntMap Symbol -> V.FixedBuilder IOWorld DecodeId DenseInput -> Int -> Entry -> ST IOWorld (Either String ());
  denseInsert limits symbols nodes index entry =
    let { write depth work text = stBind (V.fixedSet nodes (V.fromInt index) (DenseInput entry depth work text))
            (\_ -> stReturn (Right ())) } in
    case entry of {
      EInt _ -> if maxExpandedWork limits < 1 then stReturn (Left "binary expanded-work limit exceeded") else write 1 1 "";
      EBits _ -> if maxExpandedWork limits < 1 then stReturn (Left "binary expanded-work limit exceeded") else write 1 1 "";
      EText symbol -> case IM.lookup symbol symbols of {
        Nothing -> stReturn (Left "binary symbol reference has no symbol");
        Just (Symbol text size) -> if size >= maxExpandedWork limits
          then stReturn (Left "binary expanded-work limit exceeded") else write 1 (1 + size) text
      };
      ENode _ children -> if maxExpandedWork limits < 1 then stReturn (Left "binary expanded-work limit exceeded")
        else stBind (denseChildrenMeta limits nodes children 1 1) (\measured -> case measured of {
          Left message -> stReturn (Left message);
          Right ((,) depth work) -> write depth work ""
        })
    };
  getDenseNodes :: Limits -> Layout -> IntMap Symbol -> V.FixedBuilder IOWorld DecodeId DenseInput -> Read ();
  getDenseNodes limits (Layout _ symbolCount _ count _ _ edges _ _ _ nodeWidth symbolWidth) symbols nodes =
    getDenseNodesAt limits symbols nodes symbolCount count nodeWidth symbolWidth 0 0 edges emptyEntryIndex;
  getDenseNodesAt :: Limits -> IntMap Symbol -> V.FixedBuilder IOWorld DecodeId DenseInput -> Int -> Int -> Int -> Int -> Int -> Int -> Int -> EntryIndex -> Read ();
  getDenseNodesAt limits symbols nodes symbolCount count nodeWidth symbolWidth index nextSymbol remainingEdges keys =
    if index == count then do {
      checkRead (remainingEdges == 0) "binary edge count mismatch";
      checkRead (nextSymbol == symbolCount) "unused binary symbol table entries";
      returnRead ()
    } else do {
      entry <- getEntry limits nodeWidth symbolWidth index symbolCount remainingEdges;
      nextKeys <- case internIndexed entry keys of {
        ExistingEntry _ -> failRead "duplicate binary structural node"; MissingEntry fill -> returnRead (fill index)
      };
      followingSymbol <- case entry of {
        EText symbol -> do {
          checkRead (symbol == nextSymbol) "noncanonical binary symbol first-use order";
          returnRead (nextSymbol + 1)
        };
        _ -> returnRead nextSymbol
      };
      stored <- liftReadIO (stToIO (denseInsert limits symbols nodes index entry));
      _ <- liftEither stored;
      let { nextEdges = remainingEdges - entryEdges entry };
      seq nextKeys (seq nextEdges
        (getDenseNodesAt limits symbols nodes symbolCount count nodeWidth symbolWidth (index + 1)
          followingSymbol nextEdges nextKeys))
    };
  denseChildren :: forall s. V.Builder s DecodeId Parsed -> [] Int -> [] Value -> ST s ([] Value);
  denseChildren nodes children acc = case children of {
    [] -> stReturn (reverse acc);
    (:) index rest -> stBind (V.get nodes (V.fromInt index)) (\child ->
      seq child (denseChildren nodes rest ((:) (parsedValue child) acc)))
  };
  denseFill :: forall s. V.Builder s DecodeId Parsed -> Int -> [] DenseInput -> ST s ();
  denseFill nodes index entries = case entries of {
    [] -> stReturn ();
    (:) (DenseInput entry depth work text) rest ->
      let { finish value = stBind (V.set nodes (V.fromInt index) (Parsed entry value depth work)) (\_ ->
              denseFill nodes (index + 1) rest) } in
      case entry of {
        EInt n -> finish (VInt n);
        EBits n -> finish (VBits n);
        EText _ -> finish (VText text);
        ENode tag children -> stBind (denseChildren nodes children []) (\values -> finish (VNode tag values))
      }
  };
  denseMaterialize :: [] DenseInput -> V.IndexVec DecodeId Parsed;
  denseMaterialize entries = runST (stBind (V.filled (length entries) (panic "uninitialized binary graph node")) (\nodes ->
    stBind (denseFill nodes 0 entries) (\_ -> V.freeze nodes)));
  getDenseRoots :: Limits -> V.IndexVec DecodeId DenseInput -> Int -> Int -> Read ([] Int);
  getDenseRoots limits nodes width count = getDenseRootsAt limits nodes width count 0 [];
  getDenseRootsAt :: Limits -> V.IndexVec DecodeId DenseInput -> Int -> Int -> Int -> [] Int -> Read ([] Int);
  getDenseRootsAt limits nodes width remaining work roots =
    if remaining == 0 then returnRead (reverse roots) else do {
      index <- getBits width;
      case denseLookup nodes index of {
        Nothing -> failRead "binary root reference out of range";
        Just (DenseInput _ _ rootWork _) -> do {
          checkRead (rootWork <= maxExpandedWork limits - work) "binary expanded root-work limit exceeded";
          let { nextWork = work + rootWork };
          seq nextWork (getDenseRootsAt limits nodes width (remaining - 1) nextWork ((:) index roots))
        }
      }
    };
  canonicalDense :: V.IndexVec DecodeId DenseInput -> [] Int -> Either String ();
  canonicalDense nodes roots = canonicalDenseTasks nodes 0 ((:) (WalkIds roots) []);
  canonicalDenseTasks :: V.IndexVec DecodeId DenseInput -> Int -> [] CanonicalTask -> Either String ();
  canonicalDenseTasks nodes next tasks = case tasks of {
    [] -> ensure (next == V.count nodes) "unused binary node table entries";
    (:) task rest -> case task of {
      CloseId index -> if index /= next then Left "noncanonical binary node postorder"
        else canonicalDenseTasks nodes (next + 1) rest;
      WalkIds references -> case references of {
        [] -> canonicalDenseTasks nodes next rest;
        (:) index more -> if index < next
          then canonicalDenseTasks nodes next ((:) (WalkIds more) rest)
          else case denseLookup nodes index of {
            Nothing -> Left "binary graph contains an absent node";
            Just (DenseInput entry _ _ _) -> case entry of {
              ENode _ children -> canonicalDenseTasks nodes next
                ((:) (WalkIds children) ((:) (CloseId index) ((:) (WalkIds more) rest)));
              _ -> canonicalDenseTasks nodes next ((:) (CloseId index) ((:) (WalkIds more) rest))
            }
          }
      }
    }
  };
  decodeDenseNodesAndRoots :: Limits -> Int -> ByteArray -> Layout -> IntMap Symbol -> IO (Either String Graph);
  decodeDenseNodesAndRoots limits aggregate bytes geometry symbols = case geometry of {
    Layout _ _ _ nodeCount nodeOffset nodeLength _ rootCount rootOffset rootLength nodeWidth _ -> do {
      builder <- stToIO (V.fixedFilled nodeCount (panic "uninitialized binary graph node"));
      result <- runSection bytes nodeOffset nodeLength (getDenseNodes limits geometry symbols builder);
      case result of {
        Left message -> ioReturn (Left message);
        Right _ -> do {
          inputs <- stToIO (V.fixedFreeze builder);
          let { nodes = denseMaterialize (V.toList inputs) };
          rootResult <- runSection bytes rootOffset rootLength (getDenseRoots (withExpandedWork limits aggregate) inputs nodeWidth rootCount);
          case rootResult of {
            Left message -> ioReturn (Left message);
            Right roots -> ioReturn (do {
              canonicalDense inputs roots;
              Right (DenseGraph inputs roots nodes)
            })
          }
        }
      }
    }
  };

}
