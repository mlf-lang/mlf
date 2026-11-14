-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.QueryGraph where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.ST as ST;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as A;
  import qualified Bootstrap.ArtifactStorage as Storage;

  data QueryNode = QueryNode String String ([] ((,) String String)) (Maybe String);
  data Session = Session String String String (Map String QueryNode) (Map String QueryNode)
    (Map String ByteArray);
  key kind identity = Separate.pack [kind,identity];
  nodeKey (QueryNode k _ _ _) = k;
  nodeHash (QueryNode _ h _ _) = h;
  nodeReads (QueryNode _ _ reads _) = reads;
  nodePayload (QueryNode _ _ _ payload) = payload;
  edge node = (,) (nodeKey node) (nodeHash node);
  directory (Session path _ _ _ _ _) = path;
  currentNodes (Session _ _ _ _ nodes _) = nodes;
  payloadPath session digest = directory session ++ "/results/" ++ digest ++ ".mlfqr";
  stagingPath session digest = directory session ++ "/staging/" ++ digest ++ ".mlfqr";
  validHash text = stringLength text == 64 && validHashFrom text 0;
  validHashFrom text index = if index == 64 then True else let { c = stringCodeAt text index } in
    ((c >= 48 && c <= 57) || (c >= 97 && c <= 102)) && validHashFrom text (index + 1);
  command = commandIn "";
  commandIn directory args = do {
    actual <- Host.hostArguments args;
    runProcess directory (concatMapString (\field -> field ++ stringFromCode 0)
      (append ["1800","","",""] actual))
  };
  encodeHashed value = do {
    result <- Storage.encode 6 [value];
    case result of { Left e -> ioReturn (Left e); Right bytes -> do {
      digest <- byteArrayDigest bytes;
      ioReturn (if validHash digest then Right ((,) digest bytes) else Left "query result SHA failed")
    } }
  };
  hashValue value = do {
    encoded <- encodeHashed value;
    ioReturn (mapEither fst encoded)
  };
  begin :: String -> String -> IO (Either String Session);
  begin path configuration = do {
    code <- command ["/bin/mkdir","-p",path ++ "/results",path ++ "/generations",path ++ "/staging"];
    if code /= 0 then ioReturn (Left "cannot create query graph directory") else do {
      let { empty = Session path configuration "" M.empty M.empty M.empty };
      pointer <- readValue (path ++ "/CURRENT") Nothing;
      case pointer of {
        Right graph -> case W.graphRoots graph of {
          [root] -> case A.fromGraphText graph root of {
            Right digest -> if validHash digest then do {
              saved <- readValue (path ++ "/generations/" ++ digest ++ ".mlfqg") (Just digest);
              ioReturn (Right (case saved of {
                Right graph -> case admitIndex configuration graph of {
                  Right ((,) nodes canonical) -> Session path configuration
                    (if canonical then digest else "") nodes M.empty M.empty;
                  Left _ -> empty };
                Left _ -> empty }))
            } else ioReturn (Right empty);
            Left _ -> ioReturn (Right empty)
          };
          _ -> ioReturn (Right empty)
        };
        Left _ -> ioReturn (Right empty)
      }
    }
  };
  readValue path expected = do {
    raw <- Storage.readRaw path;
    case raw of { Left e -> ioReturn (Left e); Right bytes -> do {
      digest <- case expected of { Nothing -> ioReturn ""; Just _ -> byteArrayDigest bytes };
      if (case expected of { Nothing -> True; Just wanted -> eqString digest wanted })
      then W.decodeGraph W.defaultLimits 6 bytes
      else ioReturn (Left "query graph checksum mismatch")
    } }
  };
  -- Inputs are refreshed by their authoritative providers before validation.
  -- An old input with no current value means deletion, never an empty green leaf.
  inputKey identity = key "Input" identity;
  isInput identity = case Separate.unpack identity of {
    Right [kind,_] -> eqString kind "Input";
    _ -> True
  };
  validate wanted session = validateAt S.empty 0 wanted session;
  validateAt visiting depth wanted session@(Session path config generation old current pending) =
    case M.lookup compareString wanted current of {
      Just node -> (,) (Just node) session;
      Nothing -> if depth >= 4096 || S.member compareString wanted visiting || isInput wanted
        then (,) Nothing session else case M.lookup compareString wanted old of {
          Nothing -> (,) Nothing session;
          Just node -> case validateReads (S.insert compareString wanted visiting) (depth + 1)
            (nodeReads node) session of {
            (,) False next -> (,) Nothing next;
            (,) True (Session p c g previous active queued) ->
              (,) (Just node) (Session p c g previous (M.insert compareString wanted node active) queued)
          }
        }
    };
  validateReads visiting depth reads session = case reads of {
    [] -> (,) True session;
    (:) ((,) wanted expected) rest -> case validateAt visiting depth wanted session of {
      (,) Nothing next -> (,) False next;
      (,) (Just node) next -> if eqString (nodeHash node) expected
        then validateReads visiting depth rest next else (,) False next
    }
  };
  -- reads are accumulated by the provider in execution order. Hashes describe
  -- values only: recomputing with different reads may still produce green data.
  -- Retain the immutable encoding used by the hash, not its expanded W.Value.
  -- Publication neither traverses the raw AST again nor encodes it a second time.
  record wanted reads persist value session = do {
    encoded <- encodeHashed value;
    ioReturn (mapEither (\((,) digest bytes) -> recordDigest wanted reads
      (if persist then Just digest else Nothing) digest (if persist then Just bytes else Nothing) session) encoded)
  };
  recordDigest wanted reads location digest value (Session path config generation old current pending) =
    let { fresh = QueryNode wanted digest reads location;
      node = case M.lookup compareString wanted old of {
        Just previous -> if sameNode previous fresh then previous else fresh;
        Nothing -> fresh
      };
      queued = case value of { Nothing -> pending; Just payload -> M.insert compareString digest payload pending } }
    in (,) node (Session path config generation old (M.insert compareString (nodeKey node) node current) queued);
  forget wanted (Session p c g old current queued) = Session p c g old
    (M.delete compareString wanted current) queued;
  encodeNode (QueryNode wanted digest reads location) = W.VNode 410
    [W.VText wanted,W.VText digest,
     A.toList (A.toPair A.toText A.toText) reads,A.toMaybe A.toText location];
  -- Explicit legacy fixture/compatibility writer; production uses typed IDs.
  encodeLegacyIndex config nodes = W.VNode 411
    [W.VText "MLF-CRATE-QUERY-GRAPH-1",W.VText config,A.toList encodeNode (M.elems nodes)];
  -- Generation numbers are local to these four tables. A read must resolve
  -- against its own generation before comparison to the new session's nodes.
  data Address = Address Int String;
  bindingTag :: Int;
  bindingTag = 0;
  inputBindingTag :: Int;
  inputBindingTag = 415;
  preparedTag :: Int;
  preparedTag = 416;
  inventoryTag :: Int;
  inventoryTag = 417;
  scopeTag :: Int;
  scopeTag = 418;
  inferTag :: Int;
  inferTag = 419;
  finishTag :: Int;
  finishTag = 431;
  evidenceTag :: Int;
  evidenceTag = 432;
  datatypeTag :: Int;
  datatypeTag = 433;
  inputDatatypeTag :: Int;
  inputDatatypeTag = 434;
  validDigest digest payload = validHash digest && case payload of {
    Nothing -> True; Just hash -> eqString digest hash
  };
  addressId (Address _ identity) = identity;
  addressTag (Address tag _) = tag;
  isGroup tag = elem (\a b -> a == b) tag [preparedTag,inventoryTag,scopeTag,inferTag,finishTag];
  canonicalFields text = do {
    fields <- Separate.unpack text;
    ensure (eqString (Separate.pack fields) text) "noncanonical query identity";
    Right fields
  };
  parseAddress wanted = do {
    fields <- canonicalFields wanted;
    case fields of {
      [kind,name] -> if eqString kind "Input" then do {
        inner <- canonicalFields name;
        case inner of {
          [leaf,identity] -> if eqString leaf "Binding" then Right (Address inputBindingTag identity)
            else if eqString leaf "Datatype" then Right (Address inputDatatypeTag identity)
            else if eqString leaf "Prepared" then Right (Address preparedTag identity)
            else if eqString leaf "ScopeInventory" then Right (Address inventoryTag identity)
            else Left "unknown input query kind";
          _ -> Left "invalid input query key"
        }
      } else if eqString kind "Binding" then Right (Address bindingTag name)
        else if eqString kind "Datatype" then Right (Address datatypeTag name)
        else if eqString kind "Scope" then Right (Address scopeTag name)
        else if eqString kind "InferScc" then Right (Address inferTag name)
        else if eqString kind "FinishScc" then Right (Address finishTag name)
        else if eqString kind "Evidence" then Right (Address evidenceTag name)
        else Left "unknown query kind";
      _ -> Left "invalid query key"
    }
  };
  validMembers members = not (null members) && all (\name -> not (eqString name "")) members &&
    length members == S.size (S.fromList compareString members);
  membersOf identity = do {
    members <- canonicalFields identity;
    ensure (validMembers members) "invalid query group members";
    Right members
  };
  evidenceParts identity = do {
    fields <- canonicalFields identity;
    case fields of {
      [group,site,goal] -> do {
        ensure (stringLength site > 0 && stringLength site <= 19 &&
          (stringLength site < 19 || compareString site "9223372036854775807" <= 0) &&
          Separate.digitEnd site 0 == stringLength site && eqString (showInt (readInt site)) site &&
          not (eqString goal "")) "invalid evidence descriptor";
        Right ((,,) group (readInt site) goal)
      };
      _ -> Left "invalid evidence descriptor"
    }
  };
  uniqueNames values = S.toList (S.fromList compareString values);
  ranks names = M.fromDistinctAscList (zip names (range 0 (length names - 1)));
  requireKey :: forall a. Map String a -> String -> Either String a;
  requireKey table identity = case M.lookup compareString identity table of {
    Nothing -> Left "unknown snapshot identity"; Just value -> Right value
  };
  encodeIndex config nodes = do {
    let { rows = M.elems nodes };
    addresses <- traverseEither (compose parseAddress nodeKey) rows;
    let { select pred = map addressId (filter (compose pred addressTag) addresses);
      evidence = uniqueNames (select (\tag -> tag == evidenceTag));
      types = uniqueNames (select (\tag -> tag == datatypeTag || tag == inputDatatypeTag)) };
    requests <- traverseEither evidenceParts evidence;
    let { groups = uniqueNames (append (select isGroup) (map (\((,,) g _ _) -> g) requests)) };
    members <- traverseEither membersOf groups;
    let { declarations = uniqueNames (append (select (\tag -> tag == bindingTag || tag == inputBindingTag))
              (concat members));
      declIds = ranks declarations; groupIds = ranks groups; requestIds = ranks evidence; typeIds = ranks types;
      encodeAddress (Address tag name) = do {
        index <- requireKey (if isGroup tag then groupIds else if tag == evidenceTag then requestIds
          else if tag == datatypeTag || tag == inputDatatypeTag then typeIds else declIds) name;
        Right (if tag == bindingTag then W.VInt index else W.VNode tag [W.VInt index])
      };
      encodeGroup names = mapEither (A.toList W.VInt) (traverseEither (requireKey declIds) names);
      encodeEvidence ((,,) group site goal) = mapEither
        (\i -> W.VNode 414 [W.VInt i,W.VInt site,W.VText goal]) (requireKey groupIds group)
    };
    ensure (not (elem eqString "" declarations) && not (elem eqString "" types)) "empty snapshot identity";
    ensure (not (eqString config "")) "empty query graph configuration";
    traverseEither (checkIdentityBudget identityBudget) [declarations,groups,evidence,types,M.keys nodes];
    encodedGroups <- traverseEither encodeGroup members;
    encodedEvidence <- traverseEither encodeEvidence requests;
    keys <- traverseEither encodeAddress addresses;
    let { byKey = M.fromDistinctAscList (zip (M.keys nodes) keys);
      encodeRow ((,) descriptor (QueryNode _ digest edges payload)) = do {
        ensure (validDigest digest payload) "invalid query graph digest";
        reads <- traverseEither (compose (requireKey byKey) fst) edges;
        Right (W.VNode 413 [descriptor,W.VText digest,W.VNode 1 reads,A.toMaybe A.toText payload])
      }
    };
    entries <- traverseEither encodeRow (zip keys rows);
    Right (W.VNode 412 [W.VText "MLF-CRATE-QUERY-GRAPH-2",W.VText config,A.toList W.VText declarations,
      W.VNode 1 encodedGroups,W.VNode 1 encodedEvidence,A.toList W.VText types,W.VNode 1 entries])
  };
  -- Version 2 makes string sharing explicit in the schema, rather than asking
  -- the codec to admit a larger unfolded version-1 value. The dictionary is
  -- sorted, unique and entirely used; rows are ordered by their key IDs.
  -- Hash references retain the provider's expected value, not the target's
  -- current value. Repeated reads, including their order, remain significant.
  data IndexString = IndexString String Bool Int;
  data IndexNode = IndexNode Int Int ([] ((,) Int Int)) (Maybe Int);
  indexKey (IndexNode wanted _ _ _) = wanted;
  indexHash (IndexNode _ digest _ _) = digest;
  indexReads (IndexNode _ _ reads _) = reads;
  indexStrings (QueryNode wanted digest reads location) =
    append [wanted,digest] (append (concatMap (\((,) k h) -> [k,h]) reads)
      (case location of { Nothing -> []; Just value -> [value] }));
  indexString text = do {
    bytes <- W.utf8Size (W.maxSymbolBytes W.defaultLimits) text;
    let { hash = validHash text };
    seq hash (Right (IndexString text hash bytes))
  };
  indexStringText (IndexString text _ _) = text;
  indexStringHash (IndexString _ hash _) = hash;
  indexStringBytes (IndexString _ _ bytes) = bytes;
  indexDictionary strings = do {
    values <- traverseEither indexString strings;
    Right (M.fromDistinctAscList (mapIndexed (,) values))
  };
  encodeIndexV2 config nodes = do {
    -- Bound hostile source rows before any full-string dictionary lookup.
    validateIndexSourceWork (W.maxExpandedWork W.defaultLimits) Storage.maxBytes config (M.elems nodes);
    let { strings = S.toList (S.fromList compareString (concatMap indexStrings (M.elems nodes)));
      ids = M.fromDistinctAscList (mapIndexed (\index text -> (,) text index) strings);
      rows = map (\(QueryNode wanted digest reads location) ->
        IndexNode (M.get compareString wanted ids) (M.get compareString digest ids)
          (map (\((,) k h) -> (,) (M.get compareString k ids) (M.get compareString h ids)) reads)
          (mapOptional (\text -> M.get compareString text ids) location)) (M.elems nodes) };
    dictionary <- indexDictionary strings;
    _ <- validateIndexRows config dictionary rows;
    Right (W.VNode 412 [W.VText "MLF-CRATE-QUERY-GRAPH-2",W.VText config,
      A.toList A.toText strings,A.toList encodeIndexNode rows])
  };
  encodeIndexNode (IndexNode wanted digest reads location) = W.VNode 413
    [W.VInt wanted,W.VInt digest,A.toList (A.toPair A.toInt A.toInt) reads,
      A.toMaybe A.toInt location];
  increasingStrings strings = case strings of {
    [] -> Right ();
    (:) _ [] -> Right ();
    (:) first rest@((:) second _) -> do {
      ensure (compareString first second < 0) "noncanonical query graph dictionary";
      increasingStrings rest
    }
  };
  increasingIndexRows rows = case rows of {
    [] -> Right ();
    (:) _ [] -> Right ();
    (:) first rest@((:) second _) -> do {
      ensure (indexKey first < indexKey second) "duplicate/unordered query node";
      increasingIndexRows rest
    }
  };
  decodeIndexV2 configuration graph format config dictionaryIndex entries = do {
    f <- A.fromGraphText graph format;
    c <- A.fromGraphText graph config;
    ensure (eqString f "MLF-CRATE-QUERY-GRAPH-2" && eqString c configuration) "query graph version mismatch";
    -- readValue already uses defaultLimits. Keep the same work bound even if
    -- this pure helper receives a Graph planned under more permissive limits.
    resources <- W.graphResourceStats graph;
    ensure (W.resourceExpandedWork resources <= W.maxExpandedWork W.defaultLimits) "query index work limit exceeded";
    stringIndices <- listAt graph dictionaryIndex;
    strings <- traverseEither (A.fromGraphText graph) stringIndices;
    increasingStrings strings;
    dictionary <- indexDictionary strings;
    indices <- listAt graph entries;
    rows <- traverseEither (decodeIndexNode graph) indices;
    table <- validateIndexRows configuration dictionary rows;
    -- No string comparison or repeated text validation is needed here.
    -- Canonical dictionary and row order make this a distinct ascending map.
    Right (M.fromDistinctAscList (map (\row ->
      let { node = materializeIndexNode dictionary row } in (,) (nodeKey node) node) (M.elems table)))
  };
  decodeIndexNode graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of {
      W.GNode 413 [k,h,edges,location] -> do {
        wanted <- A.fromGraphInt graph k;
        digest <- A.fromGraphInt graph h;
        indices <- listAt graph edges;
        reads <- traverseEither (decodeIndexRead graph) indices;
        payload <- decodeIndexLocation graph location;
        Right (IndexNode wanted digest reads payload)
      };
      _ -> Left "malformed indexed query node"
    }
  };
  decodeIndexRead graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of {
      W.GNode 2 [k,h] -> do {
        wanted <- A.fromGraphInt graph k;
        digest <- A.fromGraphInt graph h;
        Right ((,) wanted digest)
      };
      _ -> Left "malformed indexed query read"
    }
  };
  decodeIndexLocation graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of {
      W.GNode 4 [] -> Right Nothing;
      W.GNode 5 [h] -> mapEither Just (A.fromGraphInt graph h);
      _ -> Left "malformed indexed query location"
    }
  };
  indexNodeReferences (IndexNode wanted digest reads location) =
    append [wanted,digest] (append (concatMap (\((,) k h) -> [k,h]) reads)
      (case location of { Nothing -> []; Just value -> [value] }));
  checkIndexReference dictionary hash index = do {
    ensure (index >= 0 && index < M.size dictionary) "query string ID out of range";
    ensure (not hash || indexStringHash (M.get compareInt index dictionary)) "invalid query graph digest";
    Right ()
  };
  checkIndexNode dictionary (IndexNode wanted digest reads location) = do {
    checkIndexReference dictionary False wanted;
    checkIndexReference dictionary True digest;
    mapM_ (\((,) k h) -> do {
      checkIndexReference dictionary False k;
      checkIndexReference dictionary True h
    }) reads;
    case location of { Nothing -> Right (); Just h -> checkIndexReference dictionary True h }
  };

  -- The ID grammar remains subject to the codec's original 64 Mi work limit.
  -- A second, query-only policy bounds later string-key Session operations:
  -- each row's inline-string projection is <= 64 Mi work, and the complete
  -- projected index is <= 256 Mi work (Storage.maxBytes, used here as units).
  -- This is deliberately NOT the old whole-index 64 Mi admission policy.
  -- Count each referenced UTF-8 occurrence, without expanding/copying text:
  -- header = 4 + marker/config bytes; row = 5 + key/hash bytes,
  -- each read = 3 + key/hash bytes; Just location adds 1 + hash bytes.
  -- The explicit dictionary is separately charged by the unchanged codec.
  indexCharge remaining amount = do {
    ensure (amount >= 0 && amount <= remaining) "query index referenced-work limit exceeded";
    Right (remaining - amount)
  };

  indexChargeText remaining text = do {
    -- Scalar length is a cheap lower bound; the exact UTF-8 scan is bounded
    -- by the remaining budget and the unchanged per-symbol codec limit.
    _ <- indexCharge remaining (stringLength text);
    bytes <- W.utf8Size (min remaining (W.maxSymbolBytes W.defaultLimits)) text;
    indexCharge remaining bytes
  };
  indexHeaderRemaining limit configuration = do {
    first <- indexCharge limit 4;
    second <- indexChargeText first "MLF-CRATE-QUERY-GRAPH-2";
    indexChargeText second configuration
  };
  indexSourceNodeWork limit (QueryNode wanted digest reads location) = do {
    first <- indexCharge limit 5;
    second <- indexChargeText first wanted;
    third <- indexChargeText second digest;
    fourth <- foldM (\remaining ((,) k h) -> do {
      pair <- indexCharge remaining 3;
      key <- indexChargeText pair k;
      indexChargeText key h
    }) third reads;
    final <- case location of {
      Nothing -> Right fourth;
      Just h -> do { tag <- indexCharge fourth 1; indexChargeText tag h }
    };
    Right (limit - final)
  };
  validateIndexSourceWork nodeLimit totalLimit configuration nodes = do {
    ensure (nodeLimit >= 0 && totalLimit >= 0) "invalid query index work limits";
    first <- indexHeaderRemaining totalLimit configuration;
    _ <- foldM (\remaining node -> do {
      work <- indexSourceNodeWork (min nodeLimit remaining) node;
      indexCharge remaining work
    }) first nodes;
    Right ()
  };

  indexChargeReference dictionary remaining index =
    indexCharge remaining (indexStringBytes (M.get compareInt index dictionary));
  indexNodeWork limit dictionary (IndexNode wanted digest reads location) = do {
    first <- indexCharge limit 5;
    second <- indexChargeReference dictionary first wanted;
    third <- indexChargeReference dictionary second digest;
    fourth <- foldM (\remaining ((,) k h) -> do {
      pair <- indexCharge remaining 3;
      key <- indexChargeReference dictionary pair k;
      indexChargeReference dictionary key h
    }) third reads;
    final <- case location of {
      Nothing -> Right fourth;
      Just h -> do {
        tag <- indexCharge fourth 1;
        indexChargeReference dictionary tag h
      }
    };
    Right (limit - final)
  };
  -- Reference types/ranges are checked before calling this helper. Parameters
  -- expose the exact production boundary logic to small, non-massive tests.
  validateIndexWork nodeLimit totalLimit configuration dictionary rows = do {
    ensure (nodeLimit >= 0 && totalLimit >= 0) "invalid query index work limits";
    third <- indexHeaderRemaining totalLimit configuration;
    _ <- foldM (\remaining row -> do {
      work <- indexNodeWork nodeLimit dictionary row;
      indexCharge remaining work
    }) third rows;
    Right ()
  };

  validateIndexRows configuration dictionary rows = do {
    increasingIndexRows rows;
    mapM_ (checkIndexNode dictionary) rows;
    validateIndexWork (W.maxExpandedWork W.defaultLimits) Storage.maxBytes configuration dictionary rows;
    let { used = S.fromList compareInt (concatMap indexNodeReferences rows);
      table = M.fromDistinctAscList (map (\row -> (,) (indexKey row) row) rows) };
    ensure (S.size used == M.size dictionary) "unused query graph dictionary string";
    mapM_ (\row -> mapM_ (\((,) dependency expected) ->
      case M.lookup compareInt dependency table of {
        Nothing -> Left "unpublished query dependency";
        Just target -> ensure (expected == indexHash target) "query publication has stale dependency version"
      }) (indexReads row)) rows;
    _ <- foldM (\heights row -> mapEither snd
      (indexHeight table S.empty 0 heights (indexKey row))) M.empty rows;
    Right table
  };
  -- Memoize actual subtree height, not just membership in a completed set:
  -- otherwise dependency-first key order can hide a chain longer than 4096.
  indexHeight nodes visiting depth heights wanted = do {
    ensure (depth < 4096) "cyclic/deep query graph";
    case M.lookup compareInt wanted heights of {
      Just height -> do {
        ensure (height <= 4096 - depth) "cyclic/deep query graph";
        Right ((,) height heights)
      };
      Nothing -> do {
        ensure (not (S.member compareInt wanted visiting)) "cyclic/deep query graph";
        node <- case M.lookup compareInt wanted nodes of {
          Just node -> Right node; Nothing -> Left "dangling query graph edge" };
        result <- foldM (\((,) largest done) ((,) dependency _) -> do {
          child <- indexHeight nodes (S.insert compareInt wanted visiting) (depth + 1) done dependency;
          Right ((,) (max largest (fst child)) (snd child))
        }) ((,) 0 heights) (indexReads node);
        let { height = fst result + 1; next = M.insert compareInt wanted height (snd result) };
        seq height (seq next (Right ((,) height next)))
      }
    }
  };
  materializeIndexNode dictionary (IndexNode wanted digest reads location) =
    let { text = \index -> indexStringText (M.get compareInt index dictionary) }
    in QueryNode (text wanted) (text digest)
      (map (\((,) k h) -> (,) (text k) (text h)) reads) (mapOptional text location);

  decodeIndex configuration graph = mapEither fst (admitIndex configuration graph);
  admitIndex configuration graph = do {
    root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "query graph root count" };
    value <- W.lookupGraphNode graph root;
    case value of {
      W.GNode 412 [format,config,declarations,groups,evidence,types,entries] ->
        admitSnapshot configuration graph format config declarations groups evidence types entries;
      -- Older main snapshots use the dictionary-shaped version-2 envelope.
      -- They are admitted independently and republished in the typed format.
      W.GNode 412 [format,config,dictionary,entries] ->
        mapEither (\nodes -> (,) nodes False)
          (decodeIndexV2 configuration graph format config dictionary entries);
      W.GNode 411 [format,config,entries] -> do {
        f <- A.fromGraphText graph format;
        c <- A.fromGraphText graph config;
        ensure (eqString f "MLF-CRATE-QUERY-GRAPH-1" && eqString c configuration) "query graph version mismatch";
        indices <- listAt graph entries;
        -- A physical edge can appear in many read lists. The wire reader has
        -- already proved that every child ID belongs to this graph. Share one
        -- checked pair per ID, keeping its positions in every owner's list.
        let { reads = V.fromList (map (decodeRead graph) (range 0 (W.graphNodeCount graph - 1))) };
        nodes <- traverseEither (decodeNode graph reads) indices;
        let { names = map nodeKey nodes; table = M.fromList compareString (map (\n -> (,) (nodeKey n) n) nodes) };
        ensure (length names == M.size table) "duplicate query node";
        validateClosure table;
        Right ((,) table False)
      };
      _ -> Left "unsupported query graph index"
    }
  };
  data SnapshotDeclaration = SnapshotDeclaration;
  data SnapshotGroup = SnapshotGroup;
  data SnapshotEvidence = SnapshotEvidence;
  data SnapshotDatatype = SnapshotDatatype;
  data SnapshotTables = SnapshotTables (V.IndexVec SnapshotDeclaration String) (V.IndexVec SnapshotGroup String)
    (V.IndexVec SnapshotEvidence String) (V.IndexVec SnapshotDatatype String);
  slot :: forall d. V.IndexVec d String -> Int -> Either String String;
  slot table i = if i < 0 || i >= V.count table then Left "query snapshot slot out of bounds"
    else Right (V.at table (V.fromInt i));
  -- The wire-work budget is checked by Bitstream before admission. Also cap
  -- identity expansion through our own table references before joining text.
  identityBudget = W.maxExpandedWork W.defaultLimits;
  chargeIdentity :: Int -> String -> Either String Int;
  chargeIdentity remaining name = let { cost = stringLength name } in
    if cost > 0 && cost <= remaining then Right (remaining - cost)
      else Left "query snapshot identity work limit exceeded";
  checkIdentityBudget limit names = mapEither (\_ -> ()) (foldM chargeIdentity limit names);
  packLimited fields = do {
    let { fieldSize field = let { n = stringLength field } in n + stringLength (showInt n) + 1 };
    ensure (foldlStrict (\n field -> n + fieldSize field) 0 fields <= identityBudget)
      "query snapshot identity work limit exceeded";
    Right (Separate.pack fields)
  };
  decodeNameTable :: forall d. W.Graph -> Int -> (Int -> Either String String) ->
    Either String (V.IndexVec d String);
  decodeNameTable graph list decode = do {
    entries <- listAt graph list;
    let { collect ((,,) remaining seen names) entry = do {
      name <- decode entry;
      next <- chargeIdentity remaining name;
      ensure (not (S.member compareString name seen)) "duplicate query snapshot identity";
      Right ((,,) next (S.insert compareString name seen) ((:) name names))
    } };
    built <- foldM collect ((,,) identityBudget S.empty []) entries;
    case built of { (,,) _ _ names -> Right (V.fromList (reverse names)) }
  };
  groupAt graph declarations index = do {
    members <- listAt graph index;
    names <- traverseEither (\i -> bindEither (A.fromGraphInt graph i) (slot declarations)) members;
    ensure (validMembers names) "invalid query group members";
    packLimited names
  };
  evidenceAt graph groups index = do {
    node <- W.lookupGraphNode graph index;
    case node of {
      W.GNode 414 [g,s,t] -> do {
        group <- bindEither (A.fromGraphInt graph g) (slot groups);
        site <- A.fromGraphInt graph s;
        goal <- A.fromGraphText graph t;
        ensure (site >= 0 && not (eqString goal "")) "invalid evidence descriptor";
        packLimited [group,showInt site,goal]
      };
      _ -> Left "invalid evidence descriptor"
    }
  };
  descriptorAt graph (SnapshotTables declarations groups evidence types) index = do {
    node <- W.lookupGraphNode graph index;
    let { direct kind table n = bindEither (slot table n) (\name -> packLimited [kind,name]);
      leaf kind table n = bindEither (direct kind table n) (\inner -> packLimited ["Input",inner]) };
    case node of {
      W.GInt n -> direct "Binding" declarations n;
      W.GNode tag [child] -> do {
        n <- A.fromGraphInt graph child;
        if tag == inputBindingTag then leaf "Binding" declarations n
          else if tag == preparedTag then leaf "Prepared" groups n
          else if tag == inventoryTag then leaf "ScopeInventory" groups n
          else if tag == scopeTag then direct "Scope" groups n
          else if tag == inferTag then direct "InferScc" groups n
          else if tag == finishTag then direct "FinishScc" groups n
          else if tag == evidenceTag then direct "Evidence" evidence n
          else if tag == datatypeTag then direct "Datatype" types n
          else if tag == inputDatatypeTag then leaf "Datatype" types n
          else Left "unknown query snapshot kind"
      };
      _ -> Left "invalid query snapshot descriptor"
    }
  };
  data StoredRow = StoredRow Int String String ([] Int) (Maybe String);
  storedAt graph tables index = do {
    value <- W.lookupGraphNode graph index;
    case value of {
      W.GNode 413 [k,h,reads,location] -> do {
        wanted <- descriptorAt graph tables k;
        digest <- A.fromGraphText graph h;
        edges <- listAt graph reads;
        p <- A.decodeGraphValue (A.ShapeMaybe A.ShapeText) graph location;
        payload <- A.expectMaybe A.expectText p;
        ensure (validDigest digest payload) "invalid query graph digest";
        Right (StoredRow k wanted digest edges payload)
      };
      _ -> Left "invalid query snapshot row"
    }
  };
  admitSnapshot configuration graph format config declarations groups evidence types entries = do {
    f <- A.fromGraphText graph format;
    c <- A.fromGraphText graph config;
    ensure (eqString f "MLF-CRATE-QUERY-GRAPH-2" && not (eqString c "") && eqString c configuration) "query graph version mismatch";
    ds <- decodeNameTable graph declarations (A.fromGraphText graph);
    gs <- decodeNameTable graph groups (groupAt graph ds);
    es <- decodeNameTable graph evidence (evidenceAt graph gs);
    ts <- decodeNameTable graph types (A.fromGraphText graph);
    ids <- listAt graph entries;
    let { collect ((,) budget previous) index = do {
      row@(StoredRow _ name _ _ _) <- storedAt graph (SnapshotTables ds gs es ts) index;
      next <- chargeIdentity budget name;
      Right ((,) next ((:) row previous))
    } };
    saved <- foldM collect ((,) identityBudget []) ids;
    let { rows = reverse (snd saved);
      byDescriptor = IM.fromList (map (\(StoredRow k name digest _ _) -> (,) k ((,) name digest)) rows);
      readEdge k = case IM.lookup k byDescriptor of {
        Just edge -> Right edge; Nothing -> Left "unpublished query dependency"
      };
      restore (StoredRow _ name digest edges payload) = do {
        reads <- traverseEither readEdge edges;
        Right (QueryNode name digest reads payload)
      }
    };
    nodes <- traverseEither restore rows;
    let { names = map nodeKey nodes; table = M.fromList compareString (zip names nodes) };
    ensure (length names == M.size table) "duplicate query node";
    validateClosure table;
    Right ((,) table (eqList eqString names (M.keys table)))
  };
  data WireNode = WireNode;
  decodeRead graph index = do {
    value <- A.decodeGraphValue (A.ShapePair A.ShapeText A.ShapeText) graph index;
    pair <- A.expectPair A.expectText A.expectText value;
    ensure (validHash (snd pair)) "invalid query graph digest";
    Right pair
  };
  decodeNode :: W.Graph -> V.IndexVec WireNode (Either String ((,) String String)) -> Int ->
    Either String QueryNode;
  decodeNode graph readTable index = do {
    value <- W.lookupGraphNode graph index;
    case value of {
      W.GNode 410 [k,h,edges,location] -> do {
        wanted <- A.fromGraphText graph k;
        digest <- A.fromGraphText graph h;
        ids <- listAt graph edges;
        reads <- traverseEither (\i -> V.at readTable (V.fromInt i)) ids;
        p <- A.decodeGraphValue (A.ShapeMaybe A.ShapeText) graph location;
        payload <- A.expectMaybe A.expectText p;
        ensure (validDigest digest payload) "invalid query graph digest";
        Right (QueryNode wanted digest reads payload)
      };
      _ -> Left "malformed query graph node"
    }
  };
  listAt graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of { W.GNode 1 entries -> Right entries; _ -> Left "expected query graph list" }
  };
  -- An admitted, canonically ordered generation is already a checked DAG.
  -- Equality covers the full wire row (including read order and location).
  -- Reuse its content address only if every row matches. Results still pass
  -- the same staging and retained-payload checks on every publication.
  sameNode left right = eqString (nodeKey left) (nodeKey right) &&
    eqString (nodeHash left) (nodeHash right) &&
    eqList (eqPair eqString eqString) (nodeReads left) (nodeReads right) &&
    eqMaybe eqString (nodePayload left) (nodePayload right);
  publication config previous old nodes =
    if not (eqString previous "") && M.size old == M.size nodes &&
       eqList sameNode (M.elems old) (M.elems nodes)
    then ioReturn (Right Nothing)
    else case validateClosure nodes of {
      Left e -> ioReturn (Left e);
      Right _ -> case encodeIndex config nodes of {
        Left e -> ioReturn (Left e); Right index -> do {
          encoded <- encodeHashed index;
          ioReturn (mapEither Just encoded)
        }
      }
    };
  publish session@(Session path config previous old nodes pending) = do {
    failpoint <- getEnv "MLF_QUERY_FAILPOINT";
    if eqString failpoint "before-results" then ioReturn (Left "query publication interrupted before results") else do {
      encoded <- publication config previous old nodes;
      case encoded of { Left e -> ioReturn (Left e); Right generation -> do {
        written <- publishValues failpoint session (M.toList pending);
        closure <- case written of { Left e -> ioReturn (Left e); Right _ -> verifyPayloads session (M.elems nodes) };
        case closure of { Left e -> ioReturn (Left e); Right _ -> case generation of {
          Nothing -> ioReturn (Right False);
          Just ((,) digest bytes) -> if eqString digest previous then ioReturn (Right False)
            else if eqString failpoint "before-index" then ioReturn (Left "query publication interrupted before index")
            else do {
              saved <- Storage.writeRawAtomic (path ++ "/generations/" ++ digest ++ ".mlfqg") bytes;
              case saved of { Left e -> ioReturn (Left e); Right _ ->
                if eqString failpoint "before-current" then ioReturn (Left "query publication interrupted before current")
                else do {
                  switched <- Storage.writeAtomic 6 (path ++ "/CURRENT") [W.VText digest];
                  ioReturn (mapEither (\_ -> True) switched)
                }
              }
            }
        } }
      } }
    }
  };
  -- Staging starts only at the caller's successful crate-output boundary.
  -- Every result still enters results/ by same-filesystem rename. A partial
  -- batch is unreachable until CURRENT switches; existing good results stay put.
  publishValues failpoint session values = do {
    staged <- stageValues session values [];
    case staged of { Left e -> ioReturn (Left e); Right paths ->
      if eqString failpoint "after-result-staging"
        then ioReturn (Left "query publication interrupted after result staging")
        else moveResults failpoint session paths
    }
  };
  stageValues session values staged = case values of {
    [] -> ioReturn (Right (reverse staged));
    (:) ((,) digest bytes) rest -> do {
      let { path = payloadPath session digest };
      actual <- existingHash path;
      if eqString actual digest then stageValues session rest staged else do {
        -- mv into results/ must not silently treat a corrupt entry as a directory.
        isDirectory <- directoryExists path;
        if isDirectory then ioReturn (Left "query result destination is a directory") else do {
          let { destination = stagingPath session digest };
          saved <- Storage.writeRaw destination bytes;
          case saved of { Left e -> ioReturn (Left e);
            Right _ -> stageValues session rest
              ((:) ((,) ("staging/" ++ digest ++ ".mlfqr") ("results/" ++ digest ++ ".mlfqr")) staged) }
        }
      }
    }
  };
  -- Bound both argument count and worst-case UTF-8 bytes. Even an unusually
  -- long first path forms a one-file batch, so the split always makes progress.
  moveBatch remaining count paths = case paths of {
    [] -> (,) [] [];
    (:) path rest -> let { cost = 4 * (stringLength (fst path) + 1) } in
      if count == 0 || (count < 64 && cost > remaining) then (,) [] paths else
        let { next = moveBatch (remaining - cost) (count - 1) rest }
        in (,) ((:) path (fst next)) (snd next)
  };
  moveResults :: String -> Session -> [] ((,) String String) -> IO (Either String ());
  moveResults failpoint session paths = case paths of {
    [] -> ioReturn (Right ());
    (:) first rest -> do {
      -- The native Windows helper accepts one source and an exact target file;
      -- POSIX mv also accepts multiple sources followed by their target directory.
      windows <- Host.isWindows;
      let { batch = if windows then (,) [first] rest else moveBatch 32768 64 paths;
        absolute path = if Host.absolutePath path then path else "./" ++ path;
        destinations = if windows then [absolute (snd first)] else ["results"] };
      -- Resolve generated names beneath the same cache directory. Keeping the
      -- common prefix out of argv lets the unchanged byte/count bounds batch
      -- equally well in short and long checkout paths.
      code <- commandIn (directory session) (append ["/bin/mv","-f"]
        (append (map (compose absolute fst) (fst batch)) destinations));
      if code /= 0 then ioReturn (Left "cannot publish query result batch") else
        if eqString failpoint "after-result-batch"
          then ioReturn (Left "query publication interrupted after a result batch")
          else moveResults failpoint session (snd batch)
    }
  };
  data QueryId = QueryId;
  -- Resolve and check each recorded version before cycle detection. Dense
  -- ordinals follow the old lexical root order and never enter the index file.
  validateClosure nodes = do {
    let { ordered = M.elems nodes;
      bindings = M.fromDistinctAscList (zipWith (\entry n ->
        (,) (fst entry) ((,) (V.fromInt n) (nodeHash (snd entry))))
        (M.toList nodes) (range 0 (M.size nodes - 1)));
      resolve ((,) key digest) = case M.lookup compareString key bindings of {
        Nothing -> Left "unpublished query dependency";
        Just ((,) i actual) -> if eqString digest actual then Right i
          else Left "query publication has stale dependency version"
      }
    };
    rows <- traverseEither (\node -> traverseEither resolve (nodeReads node)) ordered;
    let { edges = V.fromList rows } in runST (stBind (V.filled (V.count edges) Unseen) (\marks ->
      ST.mapE_ (visit edges marks 0) (V.indices edges)))
  };
  -- Memoize the longest suffix, since a previously visited short path can
  -- also be reached from a longer prefix in a different lexical DFS root.
  data Colour = Unseen | Visiting | Done Int;
  visit :: forall s. V.IndexVec QueryId ([] (V.Index QueryId)) -> V.Builder s QueryId Colour ->
    Int -> V.Index QueryId -> ST s (Either String Int);
  visit rows marks depth i = stBind (V.get marks i) (\colour -> case colour of {
    Done height -> if depth + height <= 4096 then ST.pureE height else ST.failE "cyclic/deep query graph";
    Visiting -> ST.failE "cyclic/deep query graph";
    Unseen -> if depth >= 4096 then ST.failE "cyclic/deep query graph"
      else stBind (V.set marks i Visiting) (\_ ->
        let { child longest target = ST.bindE (visit rows marks (depth + 1) target)
               (\height -> let { next = max longest (height + 1) } in seq next (ST.pureE next)) }
        in ST.bindE (ST.foldE child 1 (V.at rows i)) (\height ->
          stBind (V.set marks i (Done height)) (\_ -> ST.pureE height)))
  });
  verifyPayloads :: Session -> [] QueryNode -> IO (Either String ());
  verifyPayloads session@(Session _ _ _ _ _ pending) nodes =
    verifyPayloadsAfter session (S.fromList compareString (M.keys pending)) nodes;
  verifyPayloadsAfter :: Session -> Set String -> [] QueryNode -> IO (Either String ());
  verifyPayloadsAfter session checked nodes = case nodes of {
    [] -> ioReturn (Right ());
    (:) node rest -> case nodePayload node of {
      Nothing -> verifyPayloadsAfter session checked rest;
      Just digest -> if S.member compareString digest checked then verifyPayloadsAfter session checked rest else do {
        actual <- existingHash (payloadPath session digest);
        if eqString actual digest then verifyPayloadsAfter session (S.insert compareString digest checked) rest
        else ioReturn (Left "query publication has a missing/corrupt retained result")
      }
    }
  };
  existingHash path = do {
    exists <- fileExists path;
    if exists then fileDigest path else ioReturn ""
  };
  -- Optional phase clocks are kept outside deterministic output/query hashes.
  profile = do {
    enabled <- getEnv "MLF_QUERY_PROFILE";
    if eqString enabled "1" then do { counters <- newIntArray 6 0; ioReturn (Just counters) }
    else ioReturn Nothing
  };
  clock settings = case settings of {
    Nothing -> ioReturn 0;
    Just _ -> do {
      reply <- processSupervisor "MLF-PROCESS-1\0clock\0";
      if stringLength reply >= 4 && eqString (stringSlice reply 0 2) "0\0"
        then ioReturn (readInt (stringSlice reply 2 (stringLength reply - 3)))
        else panic "query profiling clock unavailable"
    }
  };
  elapsed settings index start = case settings of {
    Nothing -> ioReturn ();
    Just counters -> do {
      finish <- clock settings;
      previous <- readIntArray counters index;
      writeIntArray counters index (previous + finish - start)
    }
  };
  writeProfile path settings = case settings of {
    Nothing -> ioReturn ();
    Just counters -> do {
      values <- mapM (readIntArray counters) [0,1,2,3,4,5];
      writeFile path ("{" ++ intercalate "," (map (\((,) name value) ->
        "\"" ++ name ++ "\":" ++ showInt value)
        (zip ["graph_ms","load_ms","infer_ms","finish_ms","output_ms","publish_ms"] values)) ++ "}\n")
    }
  }
}
