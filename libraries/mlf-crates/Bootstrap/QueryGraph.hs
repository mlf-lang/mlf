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
  command args = do {
    actual <- Host.hostArguments args;
    runProcess "" (concatMapString (\field -> field ++ stringFromCode 0)
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
    let { node = QueryNode wanted digest reads location;
      queued = case value of { Nothing -> pending; Just payload -> M.insert compareString digest payload pending } }
    in (,) node (Session path config generation old (M.insert compareString wanted node current) queued);
  forget wanted (Session p c g old current queued) = Session p c g old
    (M.delete compareString wanted current) queued;
  encodeNode (QueryNode wanted digest reads location) = W.VNode 410
    [W.VText wanted,W.VText digest,
     A.toList (A.toPair A.toText A.toText) reads,A.toMaybe A.toText location];
  encodeIndex config nodes = W.VNode 411
    [W.VText "MLF-CRATE-QUERY-GRAPH-1",W.VText config,A.toList encodeNode (M.elems nodes)];
  decodeIndex configuration graph = mapEither fst (admitIndex configuration graph);
  admitIndex configuration graph = do {
    root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "query graph root count" };
    value <- W.lookupGraphNode graph root;
    case value of {
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
        Right ((,) table (eqList eqString names (M.keys table)))
      };
      _ -> Left "unsupported query graph index"
    }
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
        ensure (validHash digest &&
          (case payload of { Nothing -> True; Just hash -> eqString digest hash })) "invalid query graph digest";
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
      Right _ -> do {
        encoded <- encodeHashed (encodeIndex config nodes);
        ioReturn (mapEither Just encoded)
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
            Right _ -> stageValues session rest ((:) ((,) destination path) staged) }
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
        destinations = if windows then [absolute (snd first)] else [absolute (directory session ++ "/results")] };
      code <- command (append ["/bin/mv","-f"]
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
  data Colour = Unseen | Visiting | Done;
  visit :: forall s. V.IndexVec QueryId ([] (V.Index QueryId)) -> V.Builder s QueryId Colour ->
    Int -> V.Index QueryId -> ST s (Either String ());
  visit rows marks depth i = stBind (V.get marks i) (\colour -> case colour of {
    Done -> ST.pureE ();
    Visiting -> ST.failE "cyclic/deep query graph";
    Unseen -> if depth >= 4096 then ST.failE "cyclic/deep query graph"
      else stBind (V.set marks i Visiting) (\_ ->
        ST.bindE (ST.mapE_ (visit rows marks (depth + 1)) (V.at rows i)) (\_ ->
          ST.liftE (V.set marks i Done)))
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
