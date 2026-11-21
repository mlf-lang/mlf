-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CrateGraph where {
  import MLF.Primitive;
  import qualified Bootstrap.SourceEquality as E;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.CrateQuery as Q;
  import qualified Bootstrap.QueryGraph as G;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as A;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Evidence as Evidence;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Surface as Surface;

  data ContractHash = ContractHash W.Value String;
  data InferenceCaches = InferenceCaches (Map String Open.Environment) (Map String Open.Fragment)
    (Map String ((,) String ByteArray)) (Maybe ContractHash) (Maybe LoweredSyntax);
  data State = State G.Session Source.CheckedContracts
    InferenceCaches ([] ((,,) String Open.Fragment ([] (V.Index Declaration)))) Int Int ([] Q.GroupResult) (Maybe IntArray);
  -- This bounded memo belongs to one compilation. A template is an abstract,
  -- already checked implementation, not a saved result for a declaration ID.
  -- The key includes current datatype-node hashes, closed dependency schemes,
  -- and a deliberately small resolved source grammar. No generalizer is
  -- replaced: the first occurrence still uses ordinary MLF inference.
  templateExpression globals names depth expression = let {
    child = templateExpression globals names depth;
    variable slot = Right (Q.node "variable" [showInt slot]);
    lambda scope name body = mapEither (\text -> Q.node "lambda" [text])
      (templateExpression scope (M.insert compareString name depth names) (depth + 1) body)
  } in case expression of {
    SGlobal identity _ -> case M.lookup compareInt (V.toInt identity) globals of {
      Just slot -> variable slot; Nothing -> Left "template has an unknown declaration reference"
    };
    SVar name -> case M.lookup compareString name names of {
      Just slot -> variable slot; Nothing -> Left "template needs resolved external references"
    };
    SDeclScope [identity] (SLam name Nothing body) -> do {
      ensure (not (M.member compareInt (V.toInt identity) globals)) "template binder identity is already in scope";
      lambda (M.insert compareInt (V.toInt identity) depth globals) name body
    };
    SLam name Nothing body -> lambda globals name body;
    SApp function argument -> do {
      f <- child function; a <- child argument; Right (Q.node "application" [f,a])
    };
    SChecked ty body -> do {
      _ <- Inference.monomorphicType ty;
      value <- child body;
      Right (Q.node "checked" [Q.encodeType ty,value])
    };
    SPrimitive _ -> Right (Q.encodeExpression expression);
    SIntLit _ -> Right (Q.encodeExpression expression);
    SBoolLit _ -> Right (Q.encodeExpression expression);
    SStringLit _ -> Right (Q.encodeExpression expression);
    _ -> Left "expression is outside the inference-template grammar"
  };
  inferenceTemplateKey context parameters members = case members of {
    [(,) owner ((,,) _ annotation body)] -> do {
      signature <- case annotation of {
        Nothing -> do {
          ensure (not (null parameters)) "unsigned template needs a dependency";
          Right Nothing
        };
        Just written -> do {
          ensure (not (null parameters)) "signed template needs a dependency";
          _ <- Inference.monomorphicAnnotation written;
          Right (Just (Q.encodeAnnotation written))
        }
      };
      let { ids = map (compose V.toInt (\((,,) i _ _) -> i)) parameters;
        globals = M.fromList compareInt (zip ids (range 0 (length ids - 1)));
        names = map (\((,,) _ name _) -> name) parameters };
      ensure (M.size globals == length parameters && M.size (M.fromList compareString (zip names ids)) == length parameters)
        "duplicate template parameter";
      ensure (not (M.member compareInt (V.toInt owner) globals)) "template imports its own owner";
      _ <- foldM Inference.mergeExternal M.empty (map (\((,,) _ name ty) -> (,) name ty) parameters);
      source <- templateExpression globals M.empty (length parameters) body;
      let { fields = [context,Q.list (\((,,) _ _ ty) -> Q.encodeXType (Separate.normalType ty)) parameters,source] };
      Right (case signature of {
        Nothing -> Q.node "checked-inference-template-1" fields;
        Just written -> Q.node "checked-signed-inference-template-1" ((:) written fields)
      })
    };
    _ -> Left "template requires one nonrecursive definition"
  };
  attachInferenceTemplate declarations parameters members template = case (,) members (Open.bindings template) of {
    (,) [(,) _ ((,,) name annotation _)] [(,) owner expected] -> do {
      case annotation of {
        Nothing -> Right ();
        Just written -> do {
          declared <- Inference.monomorphicAnnotation written;
          ensure (T.alphaEq declared expected) "template declaration signature mismatch"
        }
      };
      let { old = Open.parameters template };
      ensure (eqList (\a b -> eqString (Q.encodeDatatype a) (Q.encodeDatatype b))
        declarations (Open.declarations (Open.context template))) "template datatype environment mismatch";
      ensure (length old == length parameters && all (\((,) ((,) _ a) ((,,) _ _ b)) -> T.alphaEq a b) (zip old parameters))
        "template dependency scheme mismatch";
      let { names = M.fromList compareInt ((:) ((,) (X.nameId owner) name)
          (zipWith (\((,) n _) ((,,) _ hint _) -> (,) (X.nameId n) hint) old parameters)) };
      ensure (M.size names == length parameters + 1) "template identities overlap";
      let { checked = Open.withNameHints names template };
      ensure (case Open.bindings checked of {
        [(,) n ty] -> eqString name (X.nameHint n) && T.alphaEq expected ty; _ -> False
      }) "template changed its exported type";
      Right checked
    };
    _ -> Left "template ownership mismatch"
  };
  compileIndexedMemo context templates group parameters declarations members =
    compileIndexedMemoWithKey (inferenceTemplateKey context parameters members)
      templates group parameters declarations members;
  compileIndexedMemoWithKey key templates group parameters declarations members = do {
    let { reused = do {
        identity <- key;
        template <- case M.lookup compareString identity templates of {
          Just value -> Right value; Nothing -> Left "no checked inference template"
        };
        attachInferenceTemplate declarations parameters members template
      } };
    case reused of {
      Right fragment -> Right ((,) fragment templates);
      Left _ -> do {
        fragment <- Inference.compileOpenGroupIndexed group parameters declarations members;
        let { ordered = eqList eqString (map (compose X.nameHint fst) (Open.parameters fragment))
              (map (\((,,) _ name _) -> name) parameters);
          next = case key of {
            Right identity -> if ordered && M.size templates < 64 then M.insert compareString identity fragment templates else templates;
            Left _ -> templates
          } };
        Right ((,) fragment next)
      }
    }
  };
  -- A template's private disk payload uses local parameter/owner names. The
  -- declaration-specific source key and read edges remain in the query graph.
  -- Its full structural key binds the payload to the resolved source grammar,
  -- dependency schemes and datatype versions. Loading authenticates the saved
  -- checked fragment and permits only consistent hint changes after matching
  -- the current parameter schemes and declaration; explicit audit also checks
  -- the renamed proof semantically.
  data TemplateInfo = TemplateInfo String
    ([] ((,,) (V.Index Declaration) String XType))
    ([] ((,) (V.Index Declaration) ((,,) String (Maybe SAnnotation) SExpr)))
    ([] ((,,) (V.Index Declaration) String XType))
    ([] ((,) (V.Index Declaration) ((,,) String (Maybe SAnnotation) SExpr)));
  -- Limit speculative template construction per declaration. A larger body
  -- still goes through ordinary checked inference and its own raw query.
  templateNodesLeft remaining expression =
    if remaining <= 0 then 0 else let { next = remaining - 1 } in case expression of {
      SApp f a -> templateNodesLeft (templateNodesLeft next f) a;
      SDeclScope _ body -> templateNodesLeft next body;
      SLam _ _ body -> templateNodesLeft next body;
      SChecked _ body -> templateNodesLeft next body;
      _ -> next
    };
  retainedTemplateKey context parameters members = do {
    case members of {
      [(,) _ ((,,) _ _ body)] -> ensure (templateNodesLeft 257 body > 0) "inference template exceeds the retained node budget";
      _ -> Left "template requires one nonrecursive definition"
    };
    identity <- inferenceTemplateKey context parameters members;
    ensure (stringUtf8Length identity <= 65536) "inference template exceeds the retained key budget";
    Right identity
  };
  templateInfo context slots prepared = templateInfoFor context (Source.indexedMembers slots prepared)
    (Source.expectedParameters slots prepared);
  templateInfoFor context indexed parameters = do {
    members <- indexed;
    identity <- retainedTemplateKey context parameters members;
    let { canonicalParameters = zipWith (\index ((,,) i _ ty) ->
            (,,) i ("templateParameter" ++ showInt index) (Separate.normalType ty))
          (range 0 (length parameters - 1)) parameters };
    case members of {
      [(,) owner ((,,) _ annotation body)] ->
        Right (TemplateInfo identity parameters members canonicalParameters
          [(,) owner ((,,) "templateOwner" annotation body)]);
      _ -> Left "template ownership mismatch"
    }
  };
  templateReferences :: String -> [] ((,) String String);
  templateReferences identity = [(,) "checked-inference-template-1" identity];
  templateValue declarations info fragment = case info of {
    TemplateInfo identity _ _ parameters members -> do {
      renamed <- attachInferenceTemplate declarations parameters members fragment;
      canonical <- Source.canonicalCheckedOpen renamed;
      Right (rawValue (templateReferences identity) "template" canonical)
    }
  };
  rawValueFor info declarations references group fragment = case info of {
    Right template -> templateValue declarations template fragment;
    Left _ -> Right (rawValue references group fragment)
  };
  -- Reproduce the committed encoding during ICH validation. An admitted
  -- ordinary body may belong to a valid pre-spine generation.
  checkedRawHash expected info declarations references group fragment = let {
    previous = case rawValueFor info declarations references group fragment of {
      Left e -> ioReturn (Left e); Right value -> G.hashValue value
    }
  } in case info of {
    Right _ -> previous;
    Left _ -> do {
      hashed <- G.hashValue (checkedRawValue references group fragment);
      case hashed of {
        Right digest -> if eqString digest expected then ioReturn hashed
          else previous;
        Left _ -> ioReturn hashed
      }
    }
  };
  recordRaw info declarations cached wanted reads references group fragment session =
    case info of {
      Left _ -> do {
        recorded <- G.record wanted reads True (checkedRawValue references group fragment) session;
        ioReturn (mapEither (\entry -> (,) entry cached) recorded)
      };
      Right template@(TemplateInfo identity _ _ _ _) -> do {
        encoded <- case M.lookup compareString identity cached of {
          Just payload -> ioReturn (Right payload);
          Nothing -> case templateValue declarations template fragment of {
            Left e -> ioReturn (Left e); Right value -> G.encodeHashed value
          }
        };
        ioReturn (mapEither (\payload -> let {
          digest = fst payload; bytes = snd payload;
          next = if M.size cached < 64 then M.insert compareString identity payload cached else cached
        } in (,) (G.recordDigest wanted reads (Just digest) digest (Just bytes) session) next) encoded)
      }
    };
  loadRaw info declarations path digest references group env slots prepared owners names =
    case info of {
      Left _ -> Open.decodeTrustedIds path digest references "raw" group env
        (Source.expectedParameters slots prepared) (zip owners names);
      Right (TemplateInfo identity parameters members canonicalParameters canonicalMembers) -> do {
        loaded <- Open.decodeTrustedIds path digest (templateReferences identity) "raw" "template" env
          canonicalParameters (map (\((,) i ((,,) name _ _)) -> (,) i name) canonicalMembers);
        ioReturn (do {
          template <- loaded;
          renamed <- attachInferenceTemplate declarations parameters members template;
          canonical <- Source.canonicalCheckedOpen renamed;
          Source.validatePreparedOpen slots prepared canonical;
          Right canonical
        })
      }
    };
  bindingKey scope i = G.key "Binding" (Source.declStable scope i);
  requireBindings scope ids = requireNodes (map (bindingKey scope) ids);
  -- In-memory SCC queries use the full ordered member list. Packing its
  -- stable definitions is the boundary to the generation and receipt formats.
  data GroupQuery = PreparedQuery | ScopeInventoryQuery | ScopeQuery | InferQuery | FinishQuery;
  groupQueryKind :: GroupQuery -> String;
  groupQueryKind kind = case kind of {
    PreparedQuery -> "Prepared"; ScopeInventoryQuery -> "ScopeInventory";
    ScopeQuery -> "Scope"; InferQuery -> "InferScc"; FinishQuery -> "FinishScc"
  };
  groupIdentity slots = Separate.pack (map (Source.declStable (Source.slotScope slots)) (Source.memberIds slots));
  groupKey kind slots = G.key (groupQueryKind kind) (groupIdentity slots);
  datatypeKey name = G.key "Datatype" name;
  contractValue contract = W.VNode 420
    [A.toXType (Separate.normalType (Source.contractType contract)),
     A.toList A.toText (Source.contractClasses contract),A.toBool (Source.contractProtected contract)];
  -- Each input is refreshed once from current source/checked metadata. Derived
  -- nodes have explicit edges back to that authority, including empty scopes.
  input identity value session = G.record (G.inputKey identity) [] False value session;
  recordInput identity value session = do {
    encoded <- G.encodeHashed value;
    ioReturn (mapEither (\((,) digest _) -> let {
      leaf = G.recordDigest (G.inputKey identity) [] Nothing digest Nothing session
    } in snd (G.recordDigest identity [G.edge (fst leaf)] Nothing digest Nothing (snd leaf))) encoded)
  };
  recordInitialBindings scope values session = case values of {
    [] -> ioReturn (Right session);
    (:) ((,) i contract) rest -> do {
      recorded <- recordInput (bindingKey scope i) (contractValue contract) session;
      case recorded of { Left e -> ioReturn (Left e); Right final -> recordInitialBindings scope rest final }
    }
  };
  -- Only observed imported contracts need graph nodes. Keep the immutable
  -- initial inventory separate from subsequently inferred declarations so a
  -- missing local producer can never be replaced by an input leaf.
  demandBindings scope initial ids session = case ids of {
    [] -> ioReturn (Right session);
    (:) identity rest -> if M.member compareString (bindingKey scope identity) (G.currentNodes session)
      then demandBindings scope initial rest session else case M.lookup Source.compareDecl identity initial of {
        Nothing -> ioReturn (Left "query dependency is not available");
        Just contract -> do {
          recorded <- recordInitialBindings scope [(,) identity contract] session;
          case recorded of { Left e -> ioReturn (Left e); Right next -> demandBindings scope initial rest next }
        }
      }
  };
  demandInputs scope initial ids declarations session = do {
    bindings <- demandBindings scope initial ids session;
    case bindings of { Left e -> ioReturn (Left e); Right ready ->
      recordDatatypes (filter (\d -> not (M.member compareString (datatypeKey (D.datatypeName d)) (G.currentNodes ready))) declarations) ready }
  };
  recordDatatypes values session = case values of {
    [] -> ioReturn (Right session);
    (:) declaration rest -> do {
      let { wanted = datatypeKey (D.datatypeName declaration); value = Open.declarationValue declaration };
      recorded <- recordInput wanted value session;
      case recorded of { Left e -> ioReturn (Left e); Right final -> recordDatatypes rest final }
    }
  };
  requireNodes wanted session = traverseEither (\identity ->
    case M.lookup compareString identity (G.currentNodes session) of {
      Just node -> Right node; Nothing -> Left ("query dependency is not available: " ++ identity)
    }) wanted;
  candidateMetadata protected ((,,) role name _) = Q.node "candidate"
    [Q.encodeRole role,name,Q.boolean (elem eqString name protected)];
  -- One preceding finite syntax pair, never a declaration identity or a
  -- checked result. SourceKey retains exact encoded leaves, including double
  -- bits, annotations, roles and spans. Current definition identities and
  -- metadata are supplied separately for every Prepared input.
  -- Keep one previous normalized lowered group per compilation. Original syntax
  -- carries changing source locations and is always encoded afresh. A hit must
  -- preserve every encoded field, including IEEE bits; declaration identities
  -- and current authority metadata are never supplied by this memo.
  -- Bound retained key nodes/scalars/depth and final text on each miss.
  data LoweredSyntax = LoweredSyntax ([] ((,,) String (Maybe SAnnotation) SExpr)) String;
  samePreparedMembers = eqList (E.eqTriple eqString (eqMaybe E.eqSAnnotation) E.eqSExprBits);
  boundedPreparedKey depth nodes scalars key =
    if depth > 32 || nodes <= 0 then Nothing else case key of {
      Q.KeyText text -> let { size = stringLength text } in
        if size > scalars then Nothing else Just ((,) (nodes - 1) (scalars - size));
      Q.KeyFields fields -> boundedPreparedFields (depth + 1) (nodes - 1) scalars fields;
      Q.KeyScope _ -> Nothing
    };
  boundedPreparedFields depth nodes scalars fields = case fields of {
    [] -> Just ((,) nodes scalars);
    (:) field rest -> case boundedPreparedKey depth nodes scalars field of {
      Nothing -> Nothing;
      Just ((,) more remaining) -> boundedPreparedFields depth more remaining rest
    }
  };
  smallPreparedKey key = case boundedPreparedKey 1 256 16384 key of {
    Nothing -> False; Just _ -> True
  };
  preparedLocation fuel body = if fuel <= 0 then Nothing else case body of {
    SCallSite _ span _ -> Just span;
    SLam _ _ e -> preparedLocation (fuel - 1) e;
    SApp f _ -> preparedLocation (fuel - 1) f;
    -- A constructor can head a large tree without a recorded call site.
    -- An empty origin still preserves each foreign span in full.
    SConstructor _ -> Just (SourceSpan "" "" "" 0 0 0 0);
    SDeclScope _ e -> preparedLocation (fuel - 1) e;
    SChecked _ e -> preparedLocation (fuel - 1) e;
    _ -> Nothing
  };
  -- A large application tree can repeat one file origin at every reference.
  -- P3 writes a preorder tree with delta coordinates and a bounded spelling
  -- table. P4 also pools constructor names. P5 records the difference
  -- between successive signed integer literals. Every version keeps the
  -- ordinary encoding of syntax outside these tables in an x leaf.
  -- Debit the old wire size as we go. For each admitted subtree its child's
  -- decimal length and colon fit in nine bytes. An oversized original still
  -- enters the ordinary planner and receives the same limit diagnostic.
  compactOrigin original fallback lowered names metadata = case original of {
    [(,,) name annotation body] -> if templateNodesLeft 257 body > 0 then fallback
      else case preparedLocation 64 body of {
        Nothing -> fallback;
        Just span@(SourceSpan pkg mod file _ _ _ _) -> let {
          limit = preparedFieldLimit;
          annotated = Q.optional Q.encodeAnnotation annotation;
          originBytes = stringUtf8Length (Q.node "source-span" [pkg,mod,file]);
          prefix = Separate.pack [pkg,mod,file,name,annotated];
          restFits = compactPreparedLimits &&
            fitsPreparedFields 250 (limit - stringUtf8Length preparedVersion) ((:) lowered (append names metadata));
          start = limit - 18 - stringUtf8Length (Q.node "member" [name,annotated])
        } in if restFits then case packedOrigin span originBytes start body prefix of {
          Nothing -> fallback;
          Just text -> if stringUtf8Length text <= limit then text else fallback
        } else fallback
      };
    _ -> fallback
  };
  -- Both fields can use a compact spelling only when their ordinary form
  -- is within the public writer's resource limits.
  preparedFieldLimit :: Int;
  preparedFieldLimit = 16777216;
  compactPreparedLimits = let { limits = W.defaultLimits } in
    smallRebuiltLimits limits && W.maxBytes limits >= 67108864 &&
    W.maxSymbolBytes limits >= preparedFieldLimit && W.maxTotalSymbolBytes limits >= 33554432 &&
    W.maxExpandedWork limits >= 33554688;
  remainingPreparedBytes slots budget fields = if budget < 0 then Nothing else case fields of {
    [] -> Just budget;
    (:) field rest -> if slots <= 0 then Nothing else
      remainingPreparedBytes (slots - 1) (budget - stringUtf8Length field) rest
  };
  fitsPreparedFields slots budget fields = case remainingPreparedBytes slots budget fields of {
    Just _ -> True; Nothing -> False
  };
  -- Frame each member subtree once. The inline evidence scope preserves the
  -- ordinary field spelling used by the prepared-declaration fingerprint.
  preparedSyntax previous original lowered = let {
    members = Q.keyList (Q.memberKey Q.inlineScopeKey);
    first = Q.renderKey M.empty (members original);
    fresh = let {
      key = members lowered;
      second = Q.renderKey M.empty key;
      cached = if smallPreparedKey key && stringLength second <= 65536
        then Just (LoweredSyntax lowered second) else Nothing
    } in (,,) first second cached
  } in case previous of {
    Just (LoweredSyntax old second) ->
      if samePreparedMembers old lowered then (,,) first second previous else fresh;
    Nothing -> fresh
  };
  preparedValue slots prepared = fst (preparedValueCached Nothing slots prepared);
  preparedValueCached = preparedWith preparedTree;
  preparedVersion :: String;
  preparedVersion = "prepared-declarations-1";
  preparedTree names original lowered metadata = W.VNode 421
    [W.VText preparedVersion,A.toList A.toText names,W.VText original,W.VText lowered,A.toList A.toText metadata];
  -- A lowered field can be reconstructed from a single original by dropping
  -- call sites in applications and lambdas, and optionally restoring one
  -- checked type. All other leaves keep their complete ordinary encoding.
  matchedLower original lowered = case original of {
    SCallSite _ _ body -> matchedLower body lowered;
    SApp a b -> case lowered of { SApp c d -> matchedLower a c && matchedLower b d; _ -> False };
    SLam name ann body -> case lowered of { SLam other annotation inner ->
      eqString name other && eqMaybe E.eqSAnnotation ann annotation && matchedLower body inner; _ -> False };
    _ -> E.eqSExprBits original lowered
  };
  -- Signed coordinates wrap in the same 64-bit domain as SourceSpan. The
  -- low six bits of each ASCII code are data; bit six marks a following group.
  -- For the common same-line span just two small differences are emitted.
  coordinateAlphabet :: V.IndexVec Int String;
  coordinateAlphabet = V.fromList (map stringFromCode (range 0 127));
  coordinateChunks number chunks = let {
    unsigned value rest = let { next = unsignedShiftRInt value 6;
      digit = andInt value 63;
      char i = V.at coordinateAlphabet (V.fromInt i)
    } in if next == 0 then (:) (char digit) rest
      else unsigned next ((:) (char (orInt digit 64)) rest)
  } in unsigned (xorInt (shiftLInt number 1) (shiftRInt number 63)) chunks;
  -- Charge an upper bound on the ordinary framed decimal coordinate.
  positionBytes :: Int -> Int;
  positionBytes n = if n < 0 then 23 else if n < 10 then 3 else if n < 100 then 4
    else if n < 1000 then 5 else if n < 10000 then 6 else if n < 100000 then 7
    else if n < 1000000 then 8 else 23;
  -- The first 64 spellings are defined by a length-framed literal, in order
  -- of first use. Later uses occupy one ASCII scalar. After the table fills,
  -- every unregistered spelling remains a literal. Retain the ordinary framed
  -- byte length alongside the code for admission of the original field.
  positionSymbol spelling names = case M.lookup compareString spelling names of {
    Just ((,) code bytes) -> (,,) code bytes names;
    Nothing -> let {
      framed = Separate.pack [spelling]; bytes = stringUtf8Length framed;
      literal = V.at coordinateAlphabet (V.fromInt 127) ++ framed;
      count = M.size names;
      table = if count < 64 then M.insert compareString spelling
        ((,) (V.at coordinateAlphabet (V.fromInt count)) bytes) names else names
    } in (,,) literal bytes table
  };
  -- The same preorder writer accepts raw declarations or canonical syntax.
  -- Application children and source wrappers stay in their parent's scope.
  -- Save a continuation only where the projection changes, at binders or
  -- forms delegated to the general canonicalizer.
  data OriginScope = WrittenOrigin | SourceOrigin
    (V.Index Declaration -> V.Index Declaration) (Map String String) Int (Map String String) Int;
  data PreparedConstructor = PreparedConstructor Int String String String;
  data CachedLocation = CachedLocation String | CachedLocationLeaf String String String Int String String;
  locationFragment cached = case cached of {
    CachedLocation site -> site; CachedLocationLeaf site _ _ _ _ _ -> site
  };
  packedOrigin = packedOriginIn WrittenOrigin;
  packedOriginIn initialScope origin originBytes initialBudget tree header = let {
    -- Joining bounded pages releases framed source locations as soon as their
    -- ordinary byte costs have been charged. Keep the initial fields lazy
    -- until all nodes have been admitted.
    pageNodes :: Int;
    pageNodes = 128;
    -- A page holds at most 128 syntax nodes. Append its fields in logical
    -- order so producing a page never allocates another reversed list.
    coordinate number tail = let {
      bytes value = let { rest = unsignedShiftRInt value 6; digit = andInt value 63 } in
        if rest == 0 then (:) (V.at coordinateAlphabet (V.fromInt digit)) tail
        else (:) (V.at coordinateAlphabet (V.fromInt (orInt digit 64))) (bytes rest)
    } in bytes (xorInt (shiftLInt number 1) (shiftRInt number 63));
    integerCost n = let { width = Storage.v2IntLength n } in 9 + width + (if width < 10 then 2 else 3);
    integerField prior n tail = let { previous = case prior of { Just value -> value; Nothing -> 0 };
      delta = n - previous
    } in case delta of {
      0 -> (:) "=" tail; 1 -> (:) "+" tail;
      _ -> if delta == (-1) then (:) "-" tail else (:) "I" (coordinate delta tail)
    };
    scan scope outer = let {
      collect budget pending chunks pages slots line column names locations constructors previousInteger = if budget < 0 then Nothing else case pending of {
      [] -> case outer of {
        (:) ((,) previous items) more -> scan previous more budget items chunks pages slots line column names locations constructors previousInteger;
        [] -> let {
          finalPages = if slots == pageNodes then pages else (:) (concatStringList (chunks [])) pages;
          version = case previousInteger of {
            Just _ -> "P5"; Nothing -> if M.size constructors == 0 then "P3" else "P4"
          }
        } in Just (concatStringList ((:) version ((:) header (reverse finalPages))))
      };
      (:) expr rest -> if slots == 0 then let {
          page = concatStringList (chunks [])
        } in seq page (collect budget pending id ((:) page pages) pageNodes line column names locations constructors previousInteger) else let {
        next cost emit items = collect (budget - cost) items (compose chunks emit) pages (slots - 1) line column names locations constructors previousInteger;
        named tag spelling overhead = case positionSymbol spelling names of { (,,) code bytes table ->
          collect (budget - overhead - bytes) rest (\tail -> chunks ((:) tag ((:) code tail))) pages (slots - 1) line column table locations constructors previousInteger
        };
        -- An application and its constructor occupy consecutive preorder nodes.
        -- Keep the ordinary charge for each and reuse their encoded prefix.
        constructor name leading items = seq scope (let {
          charge = 25 * leading;
          withPrefix text = case leading of { 0 -> text; 1 -> "a" ++ text; _ -> "aa" ++ text };
          emit cost field saved = collect (budget - charge - cost) items
            (\tail -> chunks ((:) field tail)) pages (slots - leading - 1) line column names locations saved previousInteger
        } in case M.lookup compareString name constructors of {
          Just (PreparedConstructor cost bare unary binary) ->
            emit cost (case leading of { 0 -> bare; 1 -> unary; _ -> binary }) constructors;
          Nothing -> let {
            text = Q.encodeExpression (SConstructor name); cost = stringUtf8Length text
          } in if M.size constructors >= 32 || stringLength name > 4096
            then emit cost (withPrefix ("x" ++ Separate.pack [text])) constructors
            else let {
              code = "c" ++ V.at coordinateAlphabet (V.fromInt (M.size constructors));
              saved = M.insert compareString name (PreparedConstructor cost code ("a" ++ code) ("aa" ++ code)) constructors
            } in emit cost (withPrefix ("C" ++ Separate.pack [name])) saved
        });
        enter nested = scan nested (case rest of { [] -> outer; _ -> (:) ((,) scope rest) outer });
        ordinary value = let { text = Q.encodeExpression value } in
          next (stringUtf8Length text) (\tail -> (:) "x" ((:) (Separate.pack [text]) tail)) rest
      } in case expr of {
        SApp f a -> let {
          single = next 25 ((:) "a") ((:) f ((:) a rest));
          -- The original writer consumes the first application before it
          -- inspects the function. Stay within that page and budget.
          applied prefix spelling overhead = case positionSymbol spelling names of {
            (,,) code bytes table -> collect (budget - 25 - overhead - bytes) ((:) a rest)
              (\tail -> chunks ((:) prefix ((:) code tail))) pages (slots - 2) line column table locations constructors previousInteger
          }
        } in if slots < 2 || budget < 25 then single else case f of {
          SApp g b -> let {
            args = (:) b ((:) a rest);
            pair = collect (budget - 50) ((:) g args) (\tail -> chunks ((:) "aa" tail))
              pages (slots - 2) line column names locations constructors previousInteger
          } in if slots < 3 || budget < 50 then pair else case g of {
            SConstructor name -> constructor name 2 args; _ -> pair
          };
          SConstructor name -> constructor name 1 ((:) a rest);
          SVar name -> applied "av" (case scope of {
            WrittenOrigin -> name; SourceOrigin _ env _ _ _ -> Q.canonicalReference env name
          }) 10;
          SGlobal i _ -> case scope of {
            SourceOrigin rank _ _ _ _ -> applied "av" (Q.ordinalToken (rank i)) 10;
            WrittenOrigin -> single
          };
          SPrimitive p -> applied "ap" (Primitive.primitiveName p) 11;
          _ -> single
        };
        SLam n ann b -> case scope of {
          WrittenOrigin -> let { fields = Separate.pack [n,Q.optional Q.encodeAnnotation ann] } in
            next (17 + stringUtf8Length fields) (\tail -> (:) "l" ((:) fields tail)) ((:) b rest);
          SourceOrigin rank env depth types typeDepth -> let {
            local = "local:" ++ showInt depth;
            fields = Separate.pack [local,Q.optional Q.encodeAnnotation (Separate.mapMaybeValue (Q.canonicalAnnotation types typeDepth) ann)];
            child = SourceOrigin rank (M.insert compareString n local env) (depth + 1) types typeDepth
          } in enter child (budget - 17 - stringUtf8Length fields) [b] (\tail -> chunks ((:) "l" ((:) fields tail)))
            pages (slots - 1) line column names locations constructors previousInteger
        };
        SCallSite label span@(SourceSpan pkg mod file sl sc el ec) body -> case origin of {
          SourceSpan p m f _ _ _ _ -> if eqString pkg p && eqString mod m && eqString file f then case positionSymbol label names of { (,,) code nameBytes table -> let {
            short = line == sl && sl == el;
            complete tail = let {
              width = coordinate (ec - sc) tail;
              endLine = if short then width else coordinate (el - sl) width;
              startColumn = coordinate (sc - column) endLine;
              startLine = if short then startColumn else coordinate (sl - line) startColumn
            } in (:) (if short then "d" else "D") ((:) code startLine);
            cost = 29 + originBytes + nameBytes +
              positionBytes sl + positionBytes sc + positionBytes el + positionBytes ec;
            next emit known = collect (budget - cost) ((:) body rest) (compose chunks emit) pages (slots - 1) sl sc table known constructors previousInteger;
            offset = sc - column; width = ec - sc;
            -- Only back-references have a one-scalar spelling. Definitions
            -- include their framed text and always go through the general path.
            small = short && offset >= (0 - 64) && offset < 64 && width >= (0 - 64) && width < 64 &&
              stringLength code == 1;
            key = (stringCodeAt code 0 * 128 + offset + 64) * 128 + width + 64;
            -- A resolved leaf immediately following this location has a stable
            -- code once its spelling is interned. Keep at most one such pair
            -- per existing location. Binders still supply their current name.
            reuse cached = let {
              single = next ((:) (locationFragment cached)) locations;
              both leafCost fragment withApps saved = let {
                remaining = budget - cost - leafCost;
                resume = collect remaining rest (\tail -> chunks ((:) fragment tail))
                  pages (slots - 2) sl sc table saved constructors previousInteger
              } in if slots < 3 || remaining < 0 then resume else case rest of {
                -- A literal argument follows its function or an earlier argument
                -- in preorder. Keep the page boundary and the ordinary node cost.
                (:) (SIntLit n) more -> collect (remaining - integerCost n) more
                  (\tail -> chunks ((:) fragment (integerField previousInteger n tail)))
                  pages (slots - 3) sl sc table saved constructors (Just n);
                -- A cached located reference can precede a curried application.
                -- Preserve the page and the two ordinary application charges,
                -- including the point where the ordinary writer inspects its head.
                (:) (SApp function argument) more -> if slots < 4 || remaining < 25 then resume
                  else case function of {
                    SApp head first -> let {
                      pair = collect (remaining - 50) ((:) head ((:) first ((:) argument more)))
                        (\tail -> chunks ((:) withApps tail)) pages (slots - 4)
                        sl sc table saved constructors previousInteger
                    } in if slots < 5 || remaining < 50 then pair else case head of {
                      SConstructor _ -> resume; _ -> pair
                    };
                    _ -> resume
                  };
                _ -> resume
              };
              leaf tag spelling overhead = case cached of {
                CachedLocationLeaf _ previous name leafCost field withApps ->
                  if eqString tag previous && eqString spelling name then both leafCost field withApps locations else single;
                CachedLocation site -> case M.lookup compareString spelling table of {
                  Nothing -> single;
                  Just ((,) leafCode bytes) -> let {
                    leafCost = overhead + bytes;
                    field = concatStringList [site,tag,leafCode];
                    withApps = field ++ "aa";
                    saved = IM.insert key (CachedLocationLeaf site tag spelling leafCost field withApps) locations
                  } in both leafCost field withApps saved
                }
              }
            } in if slots < 2 || budget < cost then single else case body of {
              SVar name -> leaf "v" (case scope of { WrittenOrigin -> name;
                SourceOrigin _ env _ _ _ -> Q.canonicalReference env name }) 10;
              SPrimitive primitive -> leaf "p" (Primitive.primitiveName primitive) 11;
              SGlobal i _ -> case scope of { WrittenOrigin -> single;
                SourceOrigin rank _ _ _ _ -> leaf "v" (Q.ordinalToken (rank i)) 10 };
              _ -> single
            }
          } in if not small then next complete locations else case IM.lookup key locations of {
            Just cached -> reuse cached;
            Nothing -> if IM.size locations >= 256 then next complete locations else let {
              fragment = concatStringList (complete [])
            } in next ((:) fragment) (IM.insert key (CachedLocation fragment) locations)
          } }
            else let { fields = Separate.pack [label,Q.encodeSourceSpan span] } in
              next (20 + stringUtf8Length fields) (\tail -> (:) "S" ((:) fields tail)) ((:) body rest)
        };
        SVar n -> named "v" (case scope of {
          WrittenOrigin -> n; SourceOrigin _ env _ _ _ -> Q.canonicalReference env n
        }) 10;
        SGlobal i _ -> case scope of {
          SourceOrigin rank _ _ _ _ -> named "v" (Q.ordinalToken (rank i)) 10;
          WrittenOrigin -> ordinary expr
        };
        SConstructor name -> constructor name 0 rest;
        SPrimitive p -> named "p" (Primitive.primitiveName p) 11;
        -- The previous literal follows preorder across page and scope boundaries.
        -- Modular subtraction is reversible across both signed Int endpoints.
        -- Charge its ordinary decimal field before admitting the next node.
        SIntLit n -> collect (budget - integerCost n) rest (compose chunks (integerField previousInteger n)) pages
          (slots - 1) line column names locations constructors (Just n);
        _ -> case scope of {
          WrittenOrigin -> ordinary expr;
          SourceOrigin rank env depth types typeDepth ->
            enter WrittenOrigin budget [Q.canonicalExpressionWith rank env depth types typeDepth expr]
              chunks pages slots line column names locations constructors previousInteger
        }
      }
      }
    } in collect
  } in scan initialScope [] initialBudget [tree] id [] pageNodes 0 0 M.empty IM.empty M.empty Nothing;
  matchingSourceMembers original lowered = case (,) original lowered of {
    (,) [(,,) name annotation body] [(,,) other next candidate] ->
      templateNodesLeft 257 body <= 0 && eqString name other && eqMaybe E.eqSAnnotation annotation next &&
        (case candidate of {
          SChecked ty inner -> null (Q.leadingTypes ty) && matchedLower body inner;
          _ -> matchedLower body candidate
        });
    _ -> False
  };
  relativePrepared original lowered names metadata = relativePreparedWith False original lowered names metadata;
  relativePreparedWith = relativePreparedUsing packedOrigin;
  relativePreparedUsing pack matched original lowered names metadata = case (,) original lowered of {
    (,) [(,,) name annotation body] [(,,) nextName nextAnnotation candidate] ->
      if templateNodesLeft 257 body > 0 || not (eqString name nextName && eqMaybe E.eqSAnnotation annotation nextAnnotation)
      then Nothing else case preparedLocation 64 body of {
        Nothing -> Nothing;
        Just span@(SourceSpan pkg mod file _ _ _ _) -> let {
          checked = case candidate of { SChecked ty inner -> (,) ("D1c" ++ Separate.pack [Q.encodeType ty]) inner; _ -> (,) "D1i" candidate };
          descriptor = fst checked; normalized = snd checked; caption = Q.optional Q.encodeAnnotation annotation;
          maxField = preparedFieldLimit;
          preamble = Separate.pack [pkg,mod,file,name,caption];
          originBytes = stringUtf8Length (Q.node "source-span" [pkg,mod,file]);
          -- Removing wrappers only shortens scalar length prefixes. Reserve
          -- the checked wrapper's own tag and field and the maximum prefix
          -- growth in its surrounding member and member-list.
          budget = maxField - 82 - stringUtf8Length descriptor - stringUtf8Length preparedVersion -
            stringUtf8Length (Q.node "member" [name,caption])
        } in if not compactPreparedLimits then Nothing else case remainingPreparedBytes 249 budget (append names metadata) of {
          Nothing -> Nothing;
          Just available -> if not (matched || matchedLower body normalized) then Nothing else
            case pack span originBytes available body preamble of {
              Just text -> if stringUtf8Length text <= maxField then Just ((,) text descriptor) else Nothing;
              Nothing -> Nothing
            }
        }
      };
    _ -> Nothing
  };
  preparedWith = preparedUsing Q.referenceTableUsing;
  preparedUsing readTable create previous slots prepared = let {
    source = Source.groupOriginal prepared;
    checked = Source.groupMembers prepared;
    sameSource = matchingSourceMembers source checked;
    -- The two projections have identical ordered value references when the
    -- lowered body just erases location wrappers. The final occurrence
    -- already comes from the lowered member.
    table = readTable slots prepared (if sameSource then checked else append source checked);
    member = Q.referenceMember table;
    token = Q.referenceToken table;
    candidate protected ((,,) role n _) = Q.node "candidate"
      [Q.encodeRole role,token n,Q.boolean (elem eqString n protected)];
    original = map member source;
    lowered = map member checked;
    names = Q.referenceDefinitions table;
    metadata = Q.sourceGroupMetadataWith token candidate prepared;
    pack = case source of {
      [(,,) _ annotation raw] -> case table of { Q.ReferenceTable _ globals ranks ->
        Q.memberTypeScope annotation (\types typeDepth ->
          let { scope = SourceOrigin (\i -> M.get Source.compareDecl i ranks) globals 0 types typeDepth } in
          \origin bytes budget _ header -> packedOriginIn scope origin bytes budget raw header)
      };
      _ -> packedOrigin
    }
  } in case relativePreparedUsing pack sameSource original lowered names metadata of {
    -- A relative pair has at least 257 syntax nodes on the original
    -- application/lambda spine. Dropping a location wrapper preserves its
    -- subtree; the lowered key therefore exceeds the 256-node retention limit.
    Just ((,) source relative) -> (,) (create names source relative metadata) Nothing;
    Nothing -> case preparedSyntax previous original lowered of { (,,) first second cached ->
      (,) (create names (compactOrigin original first second names metadata) second metadata) cached
    }
  };
  -- Rebuilt inputs/receipts have no disk payload. Preserve the wire planner's exact
  -- scalar, depth, work and allocation bounds, but hash their complete framed
  -- text directly instead of writing a binary envelope and CRC just to discard
  -- it. Counts delimit the two lists; framing retains every string boundary.
  rebuiltFields :: W.Value -> Either String ([] String);
  rebuiltFields value = case value of {
    W.VNode 421 [W.VText version, definitions, W.VText original, W.VText lowered, metadata] -> do {
      names <- A.fromList A.fromText definitions;
      fields <- A.fromList A.fromText metadata;
      Right (preparedFrames version names original lowered fields)
    };
    W.VNode 427 [W.VText group, W.VText fragment, bindings] -> do {
      contracts <- A.fromList (A.fromPair A.fromText A.fromText) bindings;
      Right (append ["MLF-FINISH-RECEIPT-TEXT-1",group,fragment,showInt (length contracts)]
        (concatMap (\((,) name digest) -> [name,digest]) contracts))
    };
    W.VNode 422 inventory -> do {
      fields <- traverseEither A.fromText inventory;
      Right (append ["MLF-SCOPE-INVENTORY-TEXT-1",showInt (length fields)] fields)
    };
    W.VNode 423 [W.VNode 422 inventory, dependencies] -> do {
      fields <- traverseEither A.fromText inventory;
      reads <- A.fromList (A.fromPair A.fromText A.fromText) dependencies;
      Right (append ["MLF-SCOPE-READS-TEXT-1",showInt (length fields)]
        (append fields ((:) (showInt (length reads))
          (concatMap (\((,) name digest) -> [name,digest]) reads))))
    };
    _ -> Left "not a rebuilt text value"
  };
  preparedFrames version names original lowered metadata =
    append ["MLF-PREPARED-INPUT-TEXT-1",version,showInt (length names)]
      (append names (append [original,lowered,showInt (length metadata)] metadata));
  framedSize limit total fields = case fields of {
    [] -> Just total;
    (:) field rest -> let { size = stringLength field;
      cost = stringLength (showInt size) + 1 + size } in
      if cost > limit - total then Nothing else framedSize limit (total + cost) rest
  };
  -- These internal receipts contain only text leaves and constructor nodes.
  -- A small unfolded tree gives conservative bounds without interning it:
  -- 256 nodes/255 edges, 8 levels, at most 65536 UTF-8 bytes and 65792 work.
  -- Even charging each text as a distinct symbol and every reference as eight
  -- bits leaves the complete envelope below 80000 bytes. Larger or differently
  -- shaped values keep the exact planner and its diagnostics.
  smallRebuiltLimits limits =
    W.validLimits limits && W.maxBytes limits >= 80000 &&
    W.maxSymbols limits >= 256 && W.maxSymbolBytes limits >= 65536 &&
    W.maxTotalSymbolBytes limits >= 65536 && W.maxNodes limits >= 256 &&
    W.maxEdges limits >= 256 && W.maxDepth limits >= 8 &&
    W.maxExpandedWork limits >= 65792;
  smallRebuiltValue value = smallRebuiltLimits W.defaultLimits &&
    case smallRebuiltTree 1 256 16384 value of { Just _ -> True; Nothing -> False };
  smallRebuiltTree depth nodes scalars value =
    if depth > 8 || nodes == 0 then Nothing else case value of {
      W.VText text -> let { size = stringLength text } in
        if size > scalars then Nothing else Just ((,) (nodes - 1) (scalars - size));
      W.VNode tag children -> if tag < 0 || tag > 2147483647 then Nothing
        else smallRebuiltChildren (depth + 1) (nodes - 1) scalars children;
      _ -> Nothing
    };
  smallRebuiltChildren depth nodes scalars values = case values of {
    [] -> Just ((,) nodes scalars);
    (:) value rest -> case smallRebuiltTree depth nodes scalars value of {
      Nothing -> Nothing;
      Just ((,) more remaining) -> smallRebuiltChildren depth more remaining rest
    }
  };
  validateRebuiltValue value = if smallRebuiltValue value then Right ()
    else mapEither (\_ -> ()) (W.prepareGraphPlan W.defaultLimits [value]);
  hashRebuiltValue value = case validateRebuiltValue value of {
    Left message -> ioReturn (Left message);
    Right _ -> case rebuiltFields value of {
      Left _ -> G.hashValue value;
      Right fields -> case framedSize (W.maxBytes W.defaultLimits / 4) 0 fields of {
        Nothing -> G.hashValue value;
        Just _ -> hashTextFields fields
      }
    }
  };
  hashTextFields :: ([] String) -> IO (Either String String);
  hashTextFields fields = do {
    digest <- Q.sourceInputHash (Separate.pack fields);
    ioReturn (if G.validHash digest then Right digest else Left "query input SHA failed")
  };
  smallPreparedTexts nodes scalars fields = case fields of {
    [] -> Just ((,) nodes scalars);
    (:) text rest -> let { n = stringLength text } in
      if nodes <= 0 || n > scalars then Nothing
      else smallPreparedTexts (nodes - 1) (scalars - n) rest
  };
  hashPrepared names original lowered metadata = let {
    -- At most 256 tree nodes and 256 framed fields. A scalar costs at most
    -- four UTF-8 bytes. The marker, two decimal counts and all field prefixes
    -- fit in 4096 bytes (at most nine bytes per prefix). Under compact limits
    -- these bounds admit both the ordinary wire tree and the framed digest.
    -- Smaller limit configurations retain the 65536-byte text budget.
    scalarLimit = if compactPreparedLimits then (preparedFieldLimit - 4096) / 4 else 16384;
    small = smallRebuiltLimits W.defaultLimits &&
      case smallPreparedTexts 253 (scalarLimit - stringLength preparedVersion) names of {
        Nothing -> False;
        Just ((,) left scalars) -> case smallPreparedTexts left scalars [original,lowered] of {
          Nothing -> False; Just ((,) more budget) ->
            more > 0 && isJust (smallPreparedTexts (more - 1) budget metadata)
        }
      }
  } in if small then hashTextFields (preparedFrames preparedVersion names original lowered metadata)
    else hashRebuiltValue (preparedTree names original lowered metadata);
  recordRebuilt identity reads value session = do {
    hashed <- hashRebuiltValue value;
    ioReturn (mapEither (\digest -> G.recordDigest identity reads Nothing digest Nothing session) hashed)
  };
  -- Retain only the preceding validated value in each of the two scope lanes.
  -- Structural equality is bounded by that admitted tree and allocates no
  -- encoding of the new value before its bounds check. Each provider supplies
  -- current reads; only identical constant-scope records share a session node.
  data RebuiltHash = RebuiltHash W.Value String;
  sameRebuiltText old value = case (,) old value of {
    (,) (W.VText a) (W.VText b) -> eqString a b;
    (,) (W.VNode a xs) (W.VNode b ys) -> a == b && eqList sameRebuiltText xs ys;
    _ -> False
  };
  hashRebuiltCached previous value = case previous of {
    Just (RebuiltHash old digest) -> if sameRebuiltText old value
      then ioReturn (Right ((,) digest previous)) else hashRebuiltFresh value;
    Nothing -> hashRebuiltFresh value
  };
  hashRebuiltFresh value = do {
    hashed <- hashRebuiltValue value;
    ioReturn (mapEither (\digest -> (,) digest (Just (RebuiltHash value digest))) hashed)
  };
  recordRebuiltCached = recordScopeCached False;
  recordScopeCached shared previous identity reads value session = do {
    hashed <- hashRebuiltCached previous value;
    ioReturn (mapEither (\((,) digest cached) -> let {
      fresh = G.QueryNode identity digest reads Nothing;
      recorded = if shared then case M.lookup compareString identity (G.currentNodes session) of {
        Just old -> if G.sameNode old fresh then (,) old session
          else G.recordDigest identity reads Nothing digest Nothing session;
        Nothing -> G.recordDigest identity reads Nothing digest Nothing session
      } else G.recordDigest identity reads Nothing digest Nothing session
    } in (,) recorded cached) hashed)
  };
  -- Emptiness is supplied anew by each prepared group. The shared input is a
  -- constant authority, never a stand-in for the first declaration. A group
  -- that acquires candidates uses its own inventory/scope keys immediately;
  -- Prepared and Evidence retain their declaration/site identities. Reuse
  -- also compares current reads, so an old shared scope kept live by another
  -- group cannot hide a change to this group's authority.
  emptyScopeInventory value = case value of { W.VNode 422 [] -> True; _ -> False };
  emptyInventoryKey = G.inputKey (G.key "EmptyScopeInventory" "");
  emptyScopeKey = G.key "EmptyScope" "";
  preparedInput slots prepared session = do {
    answer <- preparedInputCached Nothing slots prepared session;
    ioReturn (mapEither fst answer)
  };
  preparedInputCached = preparedInputReading Q.referenceTableUsing;
  preparedInputReading readTable previous slots prepared session =
    case preparedUsing readTable hashPrepared previous slots prepared of { (,) action cached -> do {
      answer <- action;
      ioReturn (mapEither (\digest -> (,) (G.recordDigest (G.inputKey (groupKey PreparedQuery slots))
        [] Nothing digest Nothing session) cached) answer)
    } };
  scopeInventory prepared = case Source.groupAuthority prepared of {
    Nothing -> W.VNode 422 [];
    Just (Source.RootAuthority _ _ _ candidates protected) -> W.VNode 422
      (map (\candidate -> W.VText (candidateMetadata protected candidate)) candidates)
  };
  scopeValue prepared dependencies = W.VNode 423
    [scopeInventory prepared,A.toList (A.toPair A.toText A.toText) (map G.edge dependencies)];
  rawValue = rawValueWith Open.encodeRaw;
  checkedRawValue = rawValueWith Open.encodeCheckedRaw;
  rawValueWith :: (W.Value -> String -> String -> Open.Fragment -> W.Value) -> [] ((,) String String) -> String -> Open.Fragment -> W.Value;
  rawValueWith encode references group fragment = encode
    (A.toList (A.toPair A.toText A.toText) references) "raw" group fragment;
  compile = compileWithData Q.requiredDataIn;
  compileFile = compileUsing Dependency.fileValueOccurrences Q.requiredFileDataIn;
  compileWithData = compileUsing (Dependency.valueOccurrences True);
  compileUsing occurrences selectData verify crateId compilerHash cacheDir imports protected originalPlan =
    case do {
      (,) plan open <- Source.protectedQueryPlan originalPlan protected;
      inventory <- Q.prepareData (Source.planData plan);
      types <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings imports);
      contracts <- Source.initialContracts plan types protected;
      (,) checked steps <- open contracts;
      Right ((,,,) plan inventory checked steps)
    } of {
      Left e -> ioReturn (Left e);
      Right ((,,,) plan inventory checked steps) -> startUsing occurrences selectData verify crateId compilerHash cacheDir
        "source" inventory (Source.planData plan) checked steps
    };
  -- The already-lowered fallback has no unsigned-root evidence finalization.
  -- It still uses the same open bodies, dependency graph and crate transaction.
  -- Preserve its existing conservative (protected, no source-class slots)
  -- calling contract, including mixed source/dictionary recursive groups.
  -- Standalone named callers own no resolver or class-lowering table.
  compileLowered verify crateId compilerHash cacheDir imports datatypes members =
    case Dependency.declarationGroups members of {
      Left e -> ioReturn (Left e);
      Right groups -> let {
        names = map Source.sourceName members; base = Dependency.symbols (map (\n -> (,) n False) names);
        ids = V.indices (Dependency.symbolNodes base);
        scope = Source.declarationScope base ids [] (concatMap (compose (map fst) Separate.unitBindings) imports)
      } in case traverseEither (traverseEither (Source.requireDecl scope)) groups of {
        Left e -> ioReturn (Left e); Right grouped -> startLowered scope (zip ids members) grouped
          verify crateId compilerHash cacheDir imports datatypes
      }
    };
  -- Only actual resolved inputs enter this boundary. Class lowering has
  -- already allocated all selectors and dictionaries. The fallback uses
  -- that exact table and traverses the final, rewritten expression edges.
  compileLoweredIn lowered verify crateId compilerHash cacheDir imports = case Inference.loweredDeclarationTable lowered of {
    Nothing -> ioReturn (Left "resolved lowered group has no declaration table");
    Just generation -> let { entries = Inference.loweredIdValues lowered;
      scope = Source.loweredScope generation (map fst entries)
    } in case Surface.indexedMemberGroups entries of {
      Left e -> ioReturn (Left e);
      Right grouped -> startLowered scope entries grouped verify crateId compilerHash cacheDir imports
        (Inference.loweredData lowered)
    }
  };
  startLowered scope entries grouped verify crateId compilerHash cacheDir imports datatypes = case do {
    inventory <- Q.prepareData datatypes;
    types <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings imports);
    checked <- Source.installContracts scope (M.map (\ty -> Source.SourceContract ty [] True) types);
    let { values = M.fromList Source.compareDecl entries;
      prepare ids _ = do {
        members <- traverseEither (\i -> case M.lookup Source.compareDecl i values of {
          Just member -> Right member; Nothing -> Left "lowered query member disappeared"
        }) ids;
        Right (Source.PreparedGroup members members [] M.empty
          (map (\i -> (,,) (Source.declName scope i) [] True) ids) Nothing [])
      }
    };
    Right ((,,) inventory checked (map (\ids -> (,) ids (prepare ids)) grouped))
  } of { Left e -> ioReturn (Left e); Right ((,,) inventory checked steps) ->
    start verify crateId compilerHash cacheDir "lowered" inventory datatypes checked steps
  };
  start = startWithData Q.requiredDataIn;
  startWithData = startUsing (Dependency.valueOccurrences True);
  startUsing occurrences selectData verify crateId compilerHash cacheDir flavor inventory datatypes contracts groups = do {
        statistics <- G.profile;
        graphStarted <- G.clock statistics;
        auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
        started <- G.begin (cacheDir ++ "/query-graph-v3")
          (Separate.pack [crateId,compilerHash,Q.sourceQueryFormat,"open-fragment-checker-1/finish-receipt-1",flavor]);
        case started of { Left e -> ioReturn (Left e); Right session -> do {
          let { initial = case contracts of { Source.CheckedContracts _ indexed _ -> indexed } };
          G.elapsed statistics 0 graphStarted;
          runGroupsReading occurrences selectData verify (eqString auditSetting "1") (Separate.compactOpenGroupName crateId) inventory initial ((,) Nothing Nothing) groups
            (State session contracts (InferenceCaches M.empty M.empty M.empty Nothing Nothing) [] 0 0 [] statistics)
        } }
    };
  runGroups verify audit crateId = runGroupsWithOwner verify audit (Separate.compactOpenGroupName crateId);
  runGroupsWithOwner = runGroupsUsing Q.requiredDataIn;
  runGroupsUsing = runGroupsReading (Dependency.valueOccurrences True);
  runGroupsReading occurrences selectData verify audit groupName inventory initial scopeHashes groups state = case groups of {
    [] -> ioReturn (Right state);
    (:) ((,) owners prepare) rest -> case state of {
      State session contracts (InferenceCaches contexts templates payloads contractHash preparedCache) objects inferred reused reports statistics ->
        let { scope = Source.checkedScope contracts; names = map (Source.declName scope) owners } in
        case bindEither (prepare contracts) (Source.slotPreparedWith (occurrences False) contracts owners) of {
          Left e -> ioReturn (Left e);
          Right ((,) slots prepared) -> do {
            let { declarations = selectData inventory (Source.groupMembers prepared)
                    (append (Source.groupBindings prepared) (Source.groupCandidateBindings prepared));
              group = groupName names;
              rawKey = groupKey InferQuery slots };
            graphStarted <- G.clock statistics;
            source <- do {
              demanded <- demandInputs scope initial (append (Source.candidateIds slots) (Source.parameterIds slots)) declarations session;
              case demanded of { Left e -> ioReturn (Left e); Right current ->
                preparedInputReading (Q.referenceTableReading (occurrences True)) preparedCache slots prepared current }
            };
            case source of { Left e -> ioReturn (Left e); Right ((,) ((,) sourceNode first) nextPreparedCache) -> do {
              let { inventoryValue = scopeInventory prepared;
                sharedInventory = emptyScopeInventory inventoryValue;
                sharedScope = sharedInventory && null (Source.candidateIds slots);
                inventoryKey = if sharedInventory then emptyInventoryKey else G.inputKey (groupKey ScopeInventoryQuery slots);
                scopeKey = if sharedScope then emptyScopeKey else groupKey ScopeQuery slots };
              scopeInput <- recordScopeCached sharedInventory (fst scopeHashes) inventoryKey [] inventoryValue first;
              case scopeInput of { Left e -> ioReturn (Left e); Right ((,) ((,) scopeLeaf second) inventoryHash) ->
                case do {
                  candidateNodes <- requireBindings scope (Source.candidateIds slots) second;
                  bindingNodes <- requireBindings scope (Source.parameterIds slots) second;
                  dataNodes <- requireNodes (map (compose datatypeKey D.datatypeName) declarations) second;
                  Right ((,,) candidateNodes bindingNodes dataNodes)
                } of {
                  Left e -> ioReturn (Left e);
                  Right ((,,) candidateNodes bindingNodes dataNodes) -> do {
                    scoped <- recordScopeCached sharedScope (snd scopeHashes) scopeKey
                      ((:) (G.edge scopeLeaf) (map G.edge candidateNodes))
                      (scopeValue prepared candidateNodes) second;
                    case scoped of { Left e -> ioReturn (Left e); Right ((,) ((,) scopeNode third) scopeHash) -> do {
                      let { dataIdentity = Separate.pack (map G.nodeHash dataNodes);
                        environment = case M.lookup compareString dataIdentity contexts of {
                          Just env -> Right env; Nothing -> Open.environment declarations } };
                      case environment of { Left e -> ioReturn (Left e); Right env -> do {
                        let { currentContexts = M.insert compareString dataIdentity env contexts;
                          indexed = Source.indexedMembers slots prepared;
                          currentParameters = Source.expectedParameters slots prepared;
                          template = if Source.usesIndexedTerms scope then templateInfoFor dataIdentity indexed currentParameters
                            else Left "template needs indexed declarations";
                          references = append (map G.edge bindingNodes) (map G.edge dataNodes);
                          reads = append [G.edge sourceNode,G.edge scopeNode] references;
                          validated = G.validateExpected rawKey reads third;
                          previous = fst validated; active = snd validated };
                        seq previous (G.elapsed statistics 0 graphStarted);
                        loadStarted <- G.clock statistics;
                        cached <- case previous of {
                          Nothing -> ioReturn (Left "query is dirty");
                          Just node -> case G.nodePayload node of {
                            Nothing -> ioReturn (Left "query result is absent");
                            Just digest -> do {
                              loaded <- loadRaw template declarations (G.payloadPath active digest) digest
                                references group env slots prepared owners names;
                              case loaded of {
                                Left e -> ioReturn (Left e);
                                Right fragment -> do {
                                  fingerprint <- if verify then checkedRawHash digest template declarations references group fragment
                                    else ioReturn (Right digest);
                                  ioReturn (do {
                                    actual <- fingerprint;
                                    ensure (eqString actual digest) "source query ICH verification failed";
                                    if audit then do {
                                      checked <- Open.audit fragment;
                                      Source.validatePreparedOpen slots prepared checked;
                                      Right checked
                                    } else Right fragment
                                  })
                                }
                              }
                            }
                          }
                        };
                        seq cached (G.elapsed statistics 1 loadStarted);
                        inferStarted <- G.clock statistics;
                        let { hit = case cached of { Right _ -> True; Left _ -> False };
                          raw = case cached of {
                            Right fragment -> Right ((,) fragment templates);
                            Left _ -> do {
                              inferredResult <- if Source.usesIndexedTerms scope then case template of {
                                -- templateInfo already resolved these immutable members,
                                -- parameters and their complete structural key above.
                                Right (TemplateInfo identity parameters members _ _) ->
                                  compileIndexedMemoWithKey (Right identity) templates group parameters declarations members;
                                Left reason -> do {
                                  members <- indexed;
                                  compileIndexedMemoWithKey (Left reason) templates group currentParameters declarations members
                                }
                              } else mapEither (\fragment -> (,) fragment templates) (Inference.compileOpenGroup group
                                [Q.dependencyInterface (Source.groupBindings prepared)] declarations (Source.groupMembers prepared));
                              canonical <- Source.canonicalCheckedOpen (fst inferredResult);
                              Source.validatePreparedOpen slots prepared canonical;
                              Right ((,) canonical (snd inferredResult))
                            }
                          } };
                        case raw of { Left e -> ioReturn (Left e); Right ((,) fragment nextTemplates) -> do {
                          recorded <- if hit then case previous of {
                            Just node -> ioReturn (Right ((,) ((,) node active) payloads));
                            Nothing -> ioReturn (Left "missing validated source query")
                          } else recordRaw template declarations payloads rawKey reads references group fragment active;
                          G.elapsed statistics 2 inferStarted;
                          finishStarted <- G.clock statistics;
                          case recorded of { Left e -> ioReturn (Left e); Right ((,) ((,) rawNode fourth) nextPayloads) ->
                            case Source.prepareOpenFinish slots contracts prepared fragment of {
                              Left e -> ioReturn (Left e);
                              Right finish -> do {
                                evidence <- resolveRequests env slots ((:) (G.edge scopeNode) (map G.edge dataNodes))
                                  (Source.openFinishRequests finish) fourth;
                                case evidence of { Left e -> ioReturn (Left e); Right ((,,) answers evidenceReads afterEvidence) ->
                                case Source.completeOpenFinish contracts finish answers of {
                                Left e -> ioReturn (Left e);
                                Right (Source.OpenFinalGroup body delta) -> do {
                                let { final = Source.openFinalObject fragment body };
                                demanded <- case Source.finalParameterIds slots contracts final of {
                                  Left e -> ioReturn (Left e);
                                  Right ids -> do {
                                    loaded <- demandBindings scope initial ids afterEvidence;
                                    ioReturn (bindEither loaded (\current -> mapEither (\nodes -> (,) nodes current)
                                      (requireBindings scope ids current)))
                                  }
                                };
                                case demanded of {
                                Left e -> ioReturn (Left e);
                                Right ((,) finalBindings afterInputs) -> do {
                                let { bindingEdges = map G.edge finalBindings;
                                  finalRefs = append bindingEdges (map G.edge dataNodes);
                                  reads = append [G.edge rawNode,G.edge sourceNode,G.edge scopeNode]
                                    (append evidenceReads bindingEdges) };
                                content <- finishContentHashFor (verify || audit) template declarations group body final rawNode references finalRefs;
                                supplied <- case content of { Left e -> ioReturn (Left e); Right hash ->
                                  recordCheckedFinish contractHash slots group hash body rawNode references finalRefs
                                    evidenceReads delta reads afterInputs };
                                case supplied of { Left e -> ioReturn (Left e); Right ((,) next nextContractHash) -> do {
                                    G.elapsed statistics 3 finishStarted;
                                    runGroupsReading occurrences selectData verify audit groupName inventory initial ((,) inventoryHash scopeHash) rest
                                      (State next (Source.publishContracts contracts delta) (InferenceCaches currentContexts nextTemplates nextPayloads nextContractHash nextPreparedCache)
                                        ((:) ((,,) group final (map fst delta)) objects)
                                        (inferred + if hit then 0 else 1) (reused + if hit then 1 else 0)
                                        ((:) (Q.GroupResult group names hit
                                          (Separate.fingerprint (Q.list Q.encodeSourceContract (map (\((,) i c) -> (,) (Source.declName scope i) c) (sortedDelta slots delta))))
                                          (G.nodeHash rawNode)) reports) statistics)
                                  } }
                                }
                                }
                                }
                                } }
                              }
                            }
                          }
                        } }
                      } }
                    } }
                  }
                }
              }
            } }
          }
        }
    }
  };
  -- One canonical content address for a fragment and its ordered environment,
  -- regardless of how it was produced. KeepRawBody proves the body is exactly
  -- the one obtained from InferScc. A changed environment invalidates reuse.
  finishContentHash recheck group body final rawNode rawRefs finalRefs =
    finishContentHashFor recheck (Left "ordinary fragment") [] group body final rawNode rawRefs finalRefs;
  finishContentHashFor recheck template declarations group body final rawNode rawRefs finalRefs =
    let { same = case body of {
      Source.KeepRawBody -> eqList (eqPair eqString eqString) rawRefs finalRefs;
      Source.AdaptedBody _ -> False
    }; rawHash = G.nodeHash rawNode } in
    if same && not recheck then ioReturn (Right rawHash) else do {
      hashed <- if same then checkedRawHash rawHash template declarations finalRefs group final
        else G.hashValue (rawValue finalRefs group final);
      ioReturn (do { digest <- hashed;
        ensure (not same || eqString digest rawHash) "retained final fragment SHA mismatch";
        Right digest })
    };
  -- The generation binds the FinishScc key and ordered reads to this small
  -- value. Reconstruct it from current checked results, so neither a swapped
  -- receipt nor a stale index row can supply a result hash. Exported contracts
  -- share the same canonical content hashes as their Binding nodes.
  sortedDelta slots = sortBy (\a b -> compareString (Source.declName (Source.slotScope slots) (fst a))
    (Source.declName (Source.slotScope slots) (fst b)));
  -- One successfully encoded, immutable contract value belongs to this run.
  -- Exact Value equality reuses its canonical digest; names and dependency
  -- reads are recorded independently for every declaration. Only a bounded
  -- tree is retained, so deep or large contracts keep the ordinary encoder.
  contractHashBudget depth remaining value =
    if depth > 16 || remaining <= 0 then Nothing else case value of {
      W.VNode _ children -> contractHashChildren (depth + 1) (remaining - 1) children;
      W.VText text -> if stringLength text <= 256 then Just (remaining - 1) else Nothing;
      _ -> Just (remaining - 1)
    };
  contractHashChildren depth remaining values = case values of {
    [] -> Just remaining;
    (:) value rest -> case contractHashBudget depth remaining value of {
      Nothing -> Nothing;
      Just next -> contractHashChildren depth next rest
    }
  };
  sameContractValue left right = case (,) left right of {
    (,) (W.VInt a) (W.VInt b) -> a == b;
    (,) (W.VBits a) (W.VBits b) -> a == b;
    (,) (W.VText a) (W.VText b) -> eqString a b;
    (,) (W.VNode a xs) (W.VNode b ys) -> a == b && eqList sameContractValue xs ys;
    _ -> False
  };
  hashContractCached previous value = case previous of {
    Just (ContractHash old digest) -> if sameContractValue old value
      then ioReturn (Right ((,) digest previous)) else hashContractFresh value;
    Nothing -> hashContractFresh value
  };
  hashContractFresh value = do {
    hashed <- G.hashValue value;
    ioReturn (mapEither (\digest -> (,) digest (case contractHashBudget 1 128 value of {
      Just _ -> Just (ContractHash value digest); Nothing -> Nothing
    })) hashed)
  };
  encodeContractsCached previous entries = case entries of {
    [] -> ioReturn (Right ((,) [] previous));
    (:) ((,) i contract) rest -> do {
      hashed <- hashContractCached previous (contractValue contract);
      case hashed of {
        Left message -> ioReturn (Left message);
        Right ((,) digest next) -> do {
          following <- encodeContractsCached next rest;
          ioReturn (mapEither (\((,) values final) -> (,) ((:) ((,) i digest) values) final) following)
        }
      }
    }
  };
  -- A singleton, unadapted result has no separate final body to persist.
  -- Its Binding records every dependency of the finalization provider, not
  -- just the raw result hash. Metadata-only edits remain observable even when
  -- they leave the raw body/result hash unchanged. All checking and content
  -- verification above have already run; other groups retain FinishScc.
  recordCheckedFinish previous slots group fragmentHash body rawNode rawRefs finalRefs evidence delta reads session =
    case (,,) body delta evidence of {
      (,,) Source.KeepRawBody [((,) i contract)] [] ->
        if eqString fragmentHash (G.nodeHash rawNode) && eqList (eqPair eqString eqString) rawRefs finalRefs
        then do {
          hashed <- hashContractCached previous (contractValue contract);
          ioReturn (mapEither (\((,) digest next) -> (,) (snd (G.recordDigest
            (bindingKey (Source.slotScope slots) i) reads Nothing digest Nothing session)) next) hashed)
        } else recordFinishCached previous slots group fragmentHash delta reads session;
      _ -> recordFinishCached previous slots group fragmentHash delta reads session
    };
  recordFinish slots group fragmentHash delta reads session = do {
    result <- recordFinishCached Nothing slots group fragmentHash delta reads session;
    ioReturn (mapEither fst result)
  };
  recordFinishCached previous slots group fragmentHash delta reads session = do {
    encoded <- encodeContractsCached previous (sortedDelta slots delta);
    case encoded of { Left e -> ioReturn (Left e); Right ((,) entries nextHash) -> do {
      let { scope = Source.slotScope slots; contracts = map (\((,) i digest) -> (,) (Source.declName scope i) digest) entries;
        receipt = W.VNode 427 [W.VText group,W.VText fragmentHash,A.toList (A.toPair A.toText A.toText) contracts];
        binding dependency current ((,) i digest) = snd (G.recordDigest (bindingKey scope i)
          [dependency] Nothing digest Nothing current) };
      -- These values are rebuilt from current checked contracts on every run.
      -- Only InferScc and Evidence payloads are read from disk. Keep all value
      -- hashes and dependency edges in the generation, without unused files.
      recorded <- recordRebuilt (groupKey FinishQuery slots) reads receipt session;
      ioReturn (mapEither (\((,) finish next) ->
        (,) (foldlStrict (binding (G.edge finish)) next entries) nextHash) recorded)
    } }
  };
  checkedResult (State session contracts _ objects inferred reused reports _) =
    (,,,) (reverse objects) (Q.QueryReport inferred reused (reverse reports)) contracts session;
  result state = case checkedResult state of { (,,,) fragments report contracts session ->
    (,,,) (map (\((,,) n f _) -> (,) n f) fragments) report (Source.checkedNamed contracts) session
  };
  statistics (State _ _ _ _ _ _ _ stats) = stats;
  data EvidenceQuery = EvidenceQuery Source.GroupSlots Int XType;
  evidenceKey (EvidenceQuery slots site goal) = G.key "Evidence"
    (Separate.pack [groupIdentity slots,showInt site,Pretty.prettyType (Separate.normalType goal)]);
  -- Resolve the checked boundary's candidate binders once, in the exact
  -- declared order. Negative identities in the payload are evidence-local
  -- ordinals, never the compilation's numeric declaration slots.
  evidenceNames slots candidates = do {
    let { ids = Source.candidateIds slots; scope = Source.slotScope slots };
    ensure (length ids == length candidates) "evidence candidate inventory changed";
    traverseEither (\((,) index ((,) i candidate)) -> do {
      let { name = Boundary.candidateName candidate; stable = Source.declStable scope i };
      ensure (eqString (X.nameHint name) (Source.declName scope i)) "evidence candidate declaration mismatch";
      Right ((,) name (XName (0 - index - 1) stable))
    }) (zip (range 0 (length ids - 1)) (zip ids candidates))
  };
  evidenceValue goal references aliases answer = let {
    names = M.fromList X.compareName aliases;
    canonical = mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n names) (\a -> a)) answer
  } in W.VNode 426 [A.toXType (Separate.normalType goal),
    A.toList (A.toPair A.toText A.toText) references,A.toMaybe A.toXTerm canonical];
  decodeEvidence graph goal references aliases = do {
    root <- case W.graphRoots graph of { [root] -> Right root; _ -> Left "evidence root count" };
    value <- W.lookupGraphNode graph root;
    case value of {
      W.GNode 426 [g,rs,p] -> do {
        savedGoal <- A.fromGraphXType graph g;
        ensure (T.alphaEq savedGoal goal) "evidence goal changed";
        raw <- A.decodeGraphValue (A.ShapeList (A.ShapePair A.ShapeText A.ShapeText)) graph rs;
        savedReferences <- A.expectList (A.expectPair A.expectText A.expectText) raw;
        ensure (eqList (eqPair eqString eqString) savedReferences references) "evidence environment changed";
        decoded <- A.decodeGraphValue (A.ShapeMaybe A.ShapeXTerm) graph p;
        proof <- A.expectMaybe A.expectXTerm decoded;
        let { replacements = M.fromList X.compareName (map (\((,) a b) -> (,) b a) aliases) };
        Right (mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n replacements) (\a -> a)) proof)
      };
      _ -> Left "invalid stable evidence record"
    }
  };
  resolveRequests env slots dependencies requests session = case requests of {
    [] -> ioReturn (Right ((,,) [] [] session));
    (:) ((,,) ordinal goal candidates) rest -> case evidenceNames slots candidates of {
      Left e -> ioReturn (Left e); Right aliases -> do {
      let { wanted = evidenceKey (EvidenceQuery slots ordinal goal);
        validated = G.validate wanted session; previous = fst validated; current = snd validated };
      cached <- case previous of {
        Nothing -> ioReturn (Left "dirty evidence query");
        Just node -> case G.nodePayload node of {
          Nothing -> ioReturn (Left "missing evidence payload");
          Just digest -> do {
            read <- G.readValue (G.payloadPath current digest) (Just digest);
            ioReturn (bindEither read (\graph -> decodeEvidence graph goal dependencies aliases))
          }
        }
      };
      let { answer = case cached of {
        Right value -> Right value;
        Left _ -> case Evidence.resolveDictionaryDetailed (Open.dataEnvironment env) M.empty
          (map Boundary.candidateTriple candidates) goal of {
          Left (Evidence.NoEntailment _) -> Right Nothing;
          Left (Evidence.InvalidEvidence message) -> Left message;
          Right proof -> Right (Just proof)
        }
      } };
      case answer of { Left e -> ioReturn (Left e); Right proof -> do {
        recorded <- case cached of {
          Right _ -> case previous of {
            Just node -> ioReturn (Right ((,) node current));
            Nothing -> ioReturn (Left "evidence validation invariant")
          };
          Left _ -> G.record wanted dependencies True (evidenceValue goal dependencies aliases proof) current
        };
        case recorded of { Left e -> ioReturn (Left e); Right ((,) node next) -> do {
          tail <- resolveRequests env slots dependencies rest next;
          ioReturn (mapEither (\((,,) answers edges final) ->
            (,,) ((:) ((,) ordinal proof) answers) ((:) (G.edge node) edges) final) tail)
        } }
      } }
    } }
  };
  -- The standalone source-root boundary publishes only after every SCC has
  -- completed. CrateSession uses compile/result and owns the later IO boundary.
  compileSourceGroups verify crateId directory imports protected plan = do {
    let { cache = Q.cachePath directory };
    code <- Q.cacheCommand ["/bin/mkdir","-p",cache];
    if code /= 0 then ioReturn (Left "cannot create source query directory") else do {
      lock <- acquireFileLock (cache ++ "/.lock");
      computed <- catchIOError (do {
        executable <- getExecutablePath;
        compiler <- fileDigest executable;
        run <- compile verify crateId compiler cache imports protected plan;
        case run of { Left e -> ioReturn (Left e); Right state -> case result state of {
          (,,,) objects report contracts session -> do {
            published <- G.publish session;
            ioReturn (mapEither (\_ -> (,,) objects report contracts) published)
          }
        } }
      }) (\e -> ioReturn (Left (textFromChars (ioeGetErrorString e))));
      releaseFileLock lock;
      ioReturn computed
    }
  }
}
