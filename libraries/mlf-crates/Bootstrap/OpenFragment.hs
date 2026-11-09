-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.OpenFragment
  (Environment, environment, declarations, dataEnvironment, Fragment, check, fromChecked,
   parameters, body, bindings, usedParameters, context, fingerprint,
   normalize, encodeBody, decodeTrusted, decodeTrustedIds, audit, closedTerm, fresh,
   Package, makePackage, readPackage, packageFragments, packageBytes,
   packageHash, packageMetadata, packageFamily, declarationValue, compatibilityIdentity) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.ArtifactStorage as Storage;

  -- Environments and receipts are immutable. The constructor is private;
  -- decoding below is the only trusted-disk admission, after a byte SHA match.
  data Environment = Environment ([] DataDecl) DataEnv;
  environment ds = mapEither (Environment ds) (D.validateDeclarations ds);
  -- DataDecl and an all-Star DataDeclK denote the same declaration. Bound
  -- parameter spellings and saturated application syntax are not identities.
  canonicalField scope depth field = case field of {
    Parameter name -> Parameter (M.findWithDefault compareString name name scope);
    Function a b -> Function (canonicalField scope depth a) (canonicalField scope depth b);
    Applied name arguments -> Applied name (map (canonicalField scope depth) arguments);
    Application a b -> let { function = canonicalField scope depth a; argument = canonicalField scope depth b }
      in case function of { Applied name args -> Applied name (snoc args argument); _ -> Application function argument };
    Quantified name kind body -> let { fresh = "type:" ++ showInt depth } in
      Quantified fresh kind (canonicalField (M.insert compareString name fresh scope) (depth + 1) body)
  };
  canonicalDeclaration declaration = let {
    binders = D.datatypeBinders declaration;
    normalized = map (\((,) index ((,) _ kind)) -> (,) ("type:" ++ showInt index) kind)
      (zip (range 0 (length binders - 1)) binders);
    scope = M.fromList compareString (zip (map fst binders) (map fst normalized))
  } in DataDeclK (D.datatypeName declaration) normalized (map (\(ConstructorDecl name fields) ->
    ConstructorDecl name (map (canonicalField scope (length binders)) fields)) (D.datatypeConstructors declaration));
  declarationValue declaration = Structure.toDataDecl (canonicalDeclaration declaration);
  declarations (Environment ds _) = ds;
  dataEnvironment (Environment _ ds) = ds;
  data Fragment = Fragment Environment ([] ((,) XName XType)) XTerm
    ([] ((,) XName XType)) ([] XName) String;
  context (Fragment env _ _ _ _ _) = env;
  parameters (Fragment _ ps _ _ _ _) = ps;
  body (Fragment _ _ term _ _ _) = term;
  bindings (Fragment _ _ _ bs _ _) = bs;
  usedParameters (Fragment _ _ _ _ used _) = used;
  fingerprint (Fragment _ _ _ _ _ stamp) = stamp;
  stamp env ps term bs = Separate.fingerprint (Separate.pack
    [Separate.pack (map (compose D.prettyDeclaration canonicalDeclaration) (declarations env)),
     Separate.pack (map (\((,) n ty) -> Separate.pack [showInt (X.nameId n), X.nameHint n, Pretty.prettyType (Separate.normalType ty)]) ps),
     Pretty.prettyTerm term,
     Separate.pack (map (\((,) n ty) -> Separate.pack [X.nameHint n, Pretty.prettyType (Separate.normalType ty)]) bs)]);
  make env ps term bs = Fragment env ps term bs
    (Boundary.nubNames (Boundary.freeNames term)) (stamp env ps term bs);
  check :: Environment -> [] ((,) XName XType) -> XTerm -> Either String Fragment;
  check env@(Environment _ ds) ps term = do {
    let { names = map fst ps };
    ensure (length names == length (nubBy X.equalName names)) "duplicate open-fragment parameter";
    let { scope = XEnv M.empty (M.fromList X.compareName ps) };
    mapM_ (Check.termType ds M.empty) (map snd ps);
    answer <- Check.inferDeclarationSpine ds scope term;
    owned <- snd answer;
    ensure (all (\p -> S.null (T.freeVars (snd p))) owned) "open fragment exports an open type";
    Right (make env ps term owned)
  };
  fromChecked checked = do {
    let { source = Checked.term checked;
      parts = case source of { XWithData ds term -> (,) ds term; term -> (,) [] term };
      split = Separate.splitParameters (snd parts) };
    env <- environment (fst parts);
    owned <- Checked.declarationBindings checked;
    Right (make env (fst split) (snd split) owned)
  };
  -- Compatibility/export adapter only. Query IO and the new crate format use
  -- body and explicit references directly, never this materialization.
  closedTerm fragment = XWithData (declarations (context fragment))
    (foldr (\((,) n ty) rest -> XAbs n ty rest) (body fragment) (parameters fragment));
  normalize fragment term = check (context fragment) (parameters fragment) term;
  audit fragment = do {
    checked <- check (context fragment) (parameters fragment) (body fragment);
    ensure (eqString (fingerprint checked) (fingerprint fragment)) "open fragment audit mismatch";
    Right checked
  };
  -- Injective alpha-renaming preserves this exact checked environment/body.
  -- Imported identities participate even if the body never uses them.
  fresh serial fragment = let {
    ids = IS.toList (foldl (\seen p -> IS.insert (X.nameId (fst p)) seen)
      (Separate.termIdentities (body fragment) IS.empty) (parameters fragment));
    replacements = IM.fromList (zip ids (range serial (advanceIdentity serial (length ids) - 1)));
    name = \(XName n hint) -> XName (IM.get n replacements) hint;
    variable = \(XTyVar n) -> XTyVar (IM.get n replacements);
    ps = map (\((,) n ty) -> (,) (name n) ty) (parameters fragment);
    term = Separate.mapTerm name variable (body fragment);
    bs = map (\((,) n ty) -> (,) (name n) (Separate.normalType ty)) (bindings fragment);
    renamed = Fragment (context fragment) ps term bs
      (map name (usedParameters fragment)) (stamp (context fragment) ps term bs)
  } in (,) (advanceIdentity serial (length ids)) renamed;
  -- The environment and external types are supplied from verified shared
  -- dependency nodes. This record contains their local identities, not copies.
  encodeBody stage name fragment = W.VNode 400
    [W.VText stage, W.VText name, W.VText (fingerprint fragment),
     Structure.toList (Structure.toPair Structure.toXName (\p -> W.VText p))
       (map (\((,) n _) -> (,) n (X.nameHint n)) (parameters fragment)),
     Structure.toXTerm (body fragment),
     Structure.toList (Structure.toPair Structure.toXName Structure.toXType) (bindings fragment),
     Structure.toList Structure.toXName (usedParameters fragment)];
  -- A reader cannot attach a claimed type to an AST. It must acquire the
  -- immutable bytes whose SHA came from the trusted generation/object index.
  -- The compatibility caller supplies stable names only. Number its whole
  -- expected interface once. The query driver supplies its actual slots.
  decodeTrusted path expected references stage name env parameters members = let {
    start = length parameters;
    slots = map V.fromInt (range 0 (start + length members - 1));
    ps = zipWith (\i ((,) key ty) -> (,,) i key ty) slots parameters
  } in decodeTrustedIds path expected references stage name env ps (zip (drop start slots) members);
  decodeTrustedIds :: String -> String -> [] ((,) String String) -> String -> String -> Environment ->
    [] ((,,) (V.Index Declaration) String XType) -> [] ((,) (V.Index Declaration) String) ->
    IO (Either String Fragment);
  decodeTrustedIds path expected references stage name env expectedParameters expectedMembers = do {
    acquired <- Storage.readRaw path;
    case acquired of {
      Left message -> ioReturn (Left message);
      Right bytes -> do {
        actual <- byteArrayDigest bytes;
        if not (eqString actual expected) then ioReturn (Left "open fragment payload SHA mismatch") else do {
          decoded <- W.decodeGraph W.defaultLimits 6 bytes;
          ioReturn (do {
            graph <- decoded;
            root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "open fragment root count" };
            envelope <- W.lookupGraphNode graph root;
            record <- case envelope of {
              W.GNode 425 [rs,record] -> do {
                values <- Structure.decodeGraphValue
                  (Structure.ShapeList (Structure.ShapePair Structure.ShapeText Structure.ShapeText)) graph rs;
                saved <- Structure.expectList (Structure.expectPair Structure.expectText Structure.expectText) values;
                ensure (eqList (eqPair eqString eqString) saved references) "open fragment environment version mismatch";
                Right record
              };
              _ -> Left "open fragment environment record missing"
            };
            value <- W.lookupGraphNode graph record;
            case value of {
              W.GNode 400 [s,n,h,ps,t,bs,uses] -> do {
                savedStage <- textAt graph s;
                savedName <- textAt graph n;
                savedStamp <- textAt graph h;
                ensure (eqString savedStage stage && eqString savedName name) "open fragment stage/owner mismatch";
                rawParameters <- decodedList
                  (Structure.ShapePair Structure.ShapeXName Structure.ShapeText) graph ps;
                pairs <- traverseEither (Structure.expectPair Structure.expectXName Structure.expectText) rawParameters;
                ensure (length pairs == length expectedParameters) "open fragment dependency inventory mismatch";
                let { ids = append (map (\((,,) i _ _) -> V.toInt i) expectedParameters)
                        (map (compose V.toInt fst) expectedMembers) };
                ensure (IS.size (IS.fromList ids) == length ids) "duplicate open fragment declaration";
                typed <- traverseEither (\((,) ((,) binder key) ((,,) _ stable ty)) -> do {
                  ensure (eqString (X.nameHint binder) key) "open fragment parameter identity mismatch";
                  ensure (eqString key stable) "open fragment dependency inventory mismatch";
                  Right ((,) binder ty)
                }) (zip pairs expectedParameters);
                term <- Structure.fromGraphXTerm graph t;
                ownedValues <- decodedList
                  (Structure.ShapePair Structure.ShapeXName Structure.ShapeXType) graph bs;
                owned <- traverseEither (Structure.expectPair Structure.expectXName Structure.expectXType) ownedValues;
                ensure (eqList eqString (sortBy compareString (map (compose X.nameHint fst) owned))
                  (sortBy compareString (map snd expectedMembers))) "open fragment member inventory mismatch";
                usedValues <- decodedList Structure.ShapeXName graph uses;
                used <- traverseEither Structure.expectXName usedValues;
                validateBinders typed owned used;
                let { result = Fragment env typed term owned used savedStamp };
                -- ICH verification is serialization/fingerprint verification,
                -- independent of the explicit semantic-audit operation.
                Right result
              };
              _ -> Left "unsupported open fragment record"
            }
          })
        }
      }
    }
  };
  -- XName IDs are fragment-local. A used reference must identify the same
  -- binder and carry its recorded hint; the hint alone never binds an XName.
  validateBinders parameters owned used = let {
    ps = map fst parameters;
    names = append ps (map fst owned);
    byId = IM.fromList (map (\n -> (,) (X.nameId n) (X.nameHint n)) ps);
    usedIds = IS.fromList (map X.nameId used);
    matches n = case IM.lookup (X.nameId n) byId of {
      Just key -> eqString key (X.nameHint n); Nothing -> False
    }
  } in do {
    ensure (length names == IS.size (IS.fromList (map X.nameId names))) "duplicate open fragment binder";
    ensure (length used == IS.size usedIds && all matches used) "open fragment free-reference inventory mismatch"
  };
  decodedList shape graph index = do {
    decoded <- Structure.decodeGraphValue (Structure.ShapeList shape) graph index;
    Structure.expectList (\value -> Right value) decoded
  };
  textAt graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of { W.GText text -> Right text; _ -> Left "expected open fragment text" }
  };
  data Package = Package String ([] ((,) String Fragment)) ByteArray String;
  packageMetadata (Package metadata _ _ _) = metadata;
  packageFragments (Package _ fragments _ _) = fragments;
  packageBytes (Package _ _ bytes _) = bytes;
  packageHash (Package _ _ _ digest) = digest;
  packageFormat :: String;
  packageFormat = "MLF-OPEN-CRATE-1/checker-1";
  -- packageFormat remains part of the existing semantic checker identity.
  -- Storage framing has an independent version.
  wireFormat8 :: String;
  wireFormat8 = "MLF-OPEN-CRATE-2/checker-1";
  -- Candidate engineering resource class; qualification is required.
  packageWorkLimit :: Int;
  packageWorkLimit = Storage.maxBytes;
  -- The distinct binary schema is a committed dispatch, never a fallback to
  -- an older parser after corruption of an open object.
  packageSchema bytes = do {
    size <- lengthByteArray bytes;
    magic <- W.hasMagic bytes;
    if not magic || size < 20 then ioReturn 0 else do {
      a <- readByteArray bytes 16; b <- readByteArray bytes 17;
      c <- readByteArray bytes 18; d <- readByteArray bytes 19;
      ioReturn (if b == 0 && c == 0 && d == 0 then a else 0)
    }
  };
  packageFamily bytes = do {
    schema <- packageSchema bytes;
    ioReturn (schema == 7 || schema == 8)
  };
  bindingReference ((,) n _) = Structure.toXName n;
  encodeFinal ((,) name fragment) = W.VNode 401
    [Structure.toText name, Structure.toText (fingerprint fragment),
     Structure.toList Structure.toText (map D.datatypeName (declarations (context fragment))),
     Structure.toList bindingReference (parameters fragment), Structure.toXTerm (body fragment),
     Structure.toList bindingReference (bindings fragment),
     Structure.toList Structure.toXName (usedParameters fragment)];
  hashSyntax value = do {
    encoded <- Storage.encode 6 [value];
    case encoded of { Left e -> ioReturn (Left e); Right bytes -> do {
      digest <- byteArrayDigest bytes; ioReturn (Right digest)
    } }
  };
  -- Formal artifacts are shared by emlf, package tools and library generators.
  -- Their executable hashes differ even in one build. The artifact ABI/checker
  -- version and actual builtin dictionary identify their shared interpretation;
  -- local query caches separately bind the complete producer executable SHA.
  -- Bump packageFormat whenever a checked-artifact invariant changes.
  compatibilityIdentity = hashSyntax (W.VNode 431
    [Structure.toText "MLF/shared-haskell-v1",Structure.toText packageFormat,
     Structure.toList Structure.toDataDecl D.builtinDeclarations]);
  referenceHashes encode values = do {
    hashes <- mapM (\((,) key value) -> do {
      digest <- hashSyntax (encode value);
      ioReturn (mapEither ((,) key) digest)
    }) values;
    ioReturn (sequenceEither hashes)
  };

  -- The returned remainder is derived from the SAME plan that is encoded.
  -- Single-reference limits remain defaultLimits; aggregate is remaining.
  hashSyntaxBudget remaining value =
    catchIOError (hashSyntaxBudgetChecked remaining value)
      (\error -> ioReturn (Left
        ("binary encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  hashSyntaxBudgetChecked remaining value =
    case W.planRootBounded W.defaultLimits remaining [value] of {
      Left message -> ioReturn (Left message);
      Right ((,) tables used) ->
        if used < 0 || used > remaining
        then ioReturn (Left "open crate reference-work accounting mismatch")
        else case W.layout W.defaultLimits tables of {
          Left message -> ioReturn (Left message);
          Right geometry -> do {
            encoded <- W.encodeTables 6 geometry tables;
            case encoded of {
              Left message -> ioReturn (Left message);
              Right bytes -> do {
                digest <- byteArrayDigest bytes;
                let { next = remaining - used };
                seq next (ioReturn (Right ((,) digest next)))
              }
            }
          }
        }
    };

  referenceHashesBudget encode entries remaining reversed =
    case entries of {
      [] -> ioReturn (Right ((,) (reverse reversed) remaining));
      (:) ((,) key value) rest -> do {
        hashed <- hashSyntaxBudget remaining (encode value);
        case hashed of {
          Left message -> ioReturn (Left message);
          Right ((,) digest next) ->
            seq next (referenceHashesBudget encode rest next
              ((:) ((,) key digest) reversed))
        }
      }
    };

  -- One map is also the duplicate-reference check. Its values are the same
  -- verified shared external values, not copies decoded from the package.
  validateReferencesBudget encode available references remaining checked =
    case references of {
      [] -> ioReturn (Right ((,) checked remaining));
      (:) ((,) name expected) rest ->
        if M.member compareString name checked
        then ioReturn (Left "duplicate open crate reference")
        else case M.lookup compareString name available of {
          Nothing -> ioReturn (Left ("missing open crate reference: " ++ name));
          Just value -> do {
            hashed <- hashSyntaxBudget remaining (encode value);
            case hashed of {
              Left message -> ioReturn (Left message);
              Right ((,) actual next) ->
                if not (eqString actual expected)
                then ioReturn (Left ("open crate dependency changed: " ++ name))
                else let {
                  following = M.insert compareString name value checked
                } in seq next (seq following
                  (validateReferencesBudget encode available rest next following))
            }
          }
        }
    };

  -- Reading a recognized schema never retries a different parser.
  -- Both selected readers authenticate the complete original byte snapshot.
  readPackage bytes expected compiler metadata allBindings allDeclarations = do {
    schema <- packageSchema bytes;
    if schema == 8
    then readPackage8 bytes expected compiler metadata allBindings allDeclarations
    else if schema == 7
    then readPackage7 bytes expected compiler metadata allBindings allDeclarations
    else ioReturn (Left "unsupported open crate schema")
  };

  data PackageHeader8 = PackageHeader8 W.Graph
    ([] ((,) String String)) ([] ((,) String String)) ([] Int) Int;
  readPackage8 bytes expected compiler metadata allBindings allDeclarations = do {
    auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
    digest <- byteArrayDigest bytes;
    if not (eqString digest expected)
    then ioReturn (Left "open crate SHA mismatch")
    else do {
      decoded <- W.decodeGraphRootBounded
        W.defaultLimits packageWorkLimit 8 bytes;
      case do {
        graph <- decoded;
        roots <- case W.graphRoots graph of {
          [] -> Left "open crate root count";
          (:) header entries -> Right ((,) header entries)
        };
        case roots of {
          (,) header entries -> do {
            value <- W.lookupGraphNode graph header;
            case value of {
              W.GNode 432 [f,c,m,b,d,k] -> do {
                format <- textAt graph f;
                identity <- textAt graph c;
                association <- textAt graph m;
                ensure (eqString format wireFormat8 &&
                  eqString identity compiler)
                  "open crate checker/compiler version mismatch; rebuild object";
                ensure (eqString association metadata)
                  "open crate interface mismatch";
                countNode <- W.lookupGraphNode graph k;
                savedCount <- case countNode of {
                  W.GInt count -> Right count;
                  _ -> Left "invalid open crate fragment count"
                };
                count <- W.boundedLength
                  (W.maxEdges W.defaultLimits - 1) entries;
                ensure (savedCount == count)
                  "open crate fragment count mismatch";
                bindings <- referenceList graph b;
                declarations <- referenceList graph d;
                stats <- W.graphResourceStats graph;
                let { used = W.resourceExpandedWork stats };
                ensure (used >= 0 && used <= packageWorkLimit)
                  "open crate package-work accounting mismatch";
                let { remaining = packageWorkLimit - used };
                seq remaining
                  (Right (PackageHeader8 graph bindings declarations entries remaining))
              };
              _ -> Left "invalid open crate header"
            }
          }
        }
      } of {
        Left message -> ioReturn (Left message);
        Right (PackageHeader8 graph references dataReferences entries remaining) -> do {
          bs <- validateReferencesBudget
            Structure.toXType allBindings references remaining M.empty;
          case bs of {
            Left message -> ioReturn (Left message);
            Right ((,) checkedBindings afterBindings) -> do {
              ds <- validateReferencesBudget declarationValue
                allDeclarations dataReferences afterBindings M.empty;
              case ds of {
                Left message -> ioReturn (Left message);
                Right ((,) checkedDeclarations _) -> ioReturn (do {
                  -- Validate all record envelopes/metadata first.
                  let { rows = M.toList checkedBindings; types = V.fromList (map snd rows);
                    table = M.fromDistinctAscList (zip (map fst rows) (V.indices types)) };
                  prepared <- prepareFinals8 graph ((,) table types)
                    checkedDeclarations M.empty S.empty entries;
                  -- This is a fresh graph-local typed memo, never reusable
                  -- with another graph. The typed 64Mi work limit is unchanged.
                  decodedBodies <- Structure.decodeGraphMany
                    Structure.ShapeXTerm graph (map finalBodyIndex8 prepared);
                  bodies <- traverseEither Structure.expectXTerm decodedBodies;
                  fragments <- restoreFinals8 prepared bodies;
                  let { usedKeys = S.fromList compareString (concatMap (\((,) _ fragment) ->
                    map (compose X.nameHint fst) (append (parameters fragment) (bindings fragment))) fragments) };
                  ensure (S.size usedKeys == length rows) "open crate binding reference inventory mismatch";
                  if eqString auditSetting "1"
                    then mapM_ (compose audit snd) fragments
                    else Right ();
                  Right (Package metadata fragments bytes digest)
                })
              }
            }
          }
        }
      }
    }
  };

  data PackageFinalFields8 = PackageFinalFields8 String String Environment
    ([] ((,) XName XType)) Int ([] ((,) XName XType)) ([] XName);
  finalBodyIndex8 (PackageFinalFields8 _ _ _ _ index _ _) = index;

  prepareFinals8 graph types declarations contexts seen entries =
    case entries of {
      [] -> Right [];
      (:) index rest -> do {
        value <- W.lookupGraphNode graph index;
        case value of {
          W.GNode 401 [n,h,ds,ps,t,bs,uses] -> do {
            name <- textAt graph n;
            savedStamp <- textAt graph h;
            ensure (not (S.member compareString name seen))
              "duplicate open crate fragment";
            rawData <- decodedList Structure.ShapeText graph ds;
            names <- traverseEither Structure.expectText rawData;
            let { identity = Separate.pack names };
            env <- case M.lookup compareString identity contexts of {
              Just env -> Right env;
              Nothing -> do {
                values <- traverseEither
                  (\key -> case M.lookup compareString key declarations of {
                    Just declaration -> Right declaration;
                    Nothing -> Left "open crate datatype reference out of scope"
                  }) names;
                environment values
              }
            };
            params <- finalBindings graph types ps;
            owned <- finalBindings graph types bs;
            usedValues <- decodedList Structure.ShapeXName graph uses;
            used <- traverseEither Structure.expectXName usedValues;
            validateBinders params owned used;
            next <- prepareFinals8 graph types declarations
              (M.insert compareString identity env contexts)
              (S.insert compareString name seen) rest;
            Right ((:)
              (PackageFinalFields8 name savedStamp env params t owned used)
              next)
          };
          _ -> Left "invalid final open crate fragment"
        }
      }
    };

  restoreFinals8 :: [] PackageFinalFields8 -> [] XTerm ->
    Either String ([] ((,) String Fragment));
  restoreFinals8 prepared bodies = case prepared of {
    [] -> case bodies of {
      [] -> Right [];
      _ -> Left "open crate decoded body count mismatch"
    };
    (:) (PackageFinalFields8 name savedStamp env params _ owned used) rest ->
      case bodies of {
        [] -> Left "open crate decoded body count mismatch";
        (:) source more -> do {
          ensure (eqString savedStamp (stamp env params source owned))
            "open crate fragment fingerprint mismatch";
          next <- restoreFinals8 rest more;
          Right ((:) ((,) name
            (Fragment env params source owned used savedStamp)) next)
        }
      }
  };

  -- Keep the last lazy value, matching Map.fromList, for repeated references.
  referenceTable :: forall a. [] ((,) String a) -> Map String a;
  referenceTable entries = foldlStrict (\table ((,) key value) ->
    if M.member compareString key table then table
    else M.insert compareString key value table) M.empty (reverse entries);
  makePackage compiler metadata fragments = do {
    let {
      ps = M.toList (referenceTable (concatMap
        (\((,) _ f) -> map
          (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty))
          (append (parameters f) (bindings f))) fragments));
      ds = M.toList (referenceTable (concatMap
        (\((,) _ f) -> map (\d -> (,) (D.datatypeName d) d)
          (declarations (context f))) fragments))
    };
    case W.boundedLength (W.maxEdges W.defaultLimits - 1) fragments of {
      Left message -> ioReturn (Left message);
      Right count -> do {
        bh <- referenceHashesBudget Structure.toXType ps packageWorkLimit [];
        case bh of {
          Left message -> ioReturn (Left message);
          Right ((,) b afterBindings) -> do {
            dh <- referenceHashesBudget declarationValue ds afterBindings [];
            case dh of {
              Left message -> ioReturn (Left message);
              Right ((,) d remaining) -> do {
                let {
                  header = W.VNode 432
                    [Structure.toText wireFormat8, Structure.toText compiler,
                     Structure.toText metadata,
                     Structure.toList
                       (Structure.toPair Structure.toText Structure.toText) b,
                     Structure.toList
                       (Structure.toPair Structure.toText Structure.toText) d,
                     W.VInt count];
                  roots = (:) header (map encodeFinal fragments)
                };
                encoded <- W.encodeRootBounded W.defaultLimits remaining 8 roots;
                case encoded of {
                  Left message -> ioReturn (Left message);
                  Right bytes -> do {
                    digest <- byteArrayDigest bytes;
                    ioReturn (Right (Package metadata fragments bytes digest))
                  }
                }
              }
            }
          }
        }
      }
    }
  };
  -- Only an acquired immutable object snapshot, its paired interface checksum,
  -- and checked dependency metadata can restore final receipts. No AST enters.
  readPackage7 bytes expected compiler metadata allBindings allDeclarations = do {
    auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
    digest <- byteArrayDigest bytes;
    if not (eqString digest expected) then ioReturn (Left "open crate SHA mismatch") else do {
      decoded <- W.decodeGraph W.defaultLimits 7 bytes;
      case do {
        graph <- decoded;
        root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "open crate root count" };
        value <- W.lookupGraphNode graph root;
        case value of {
          W.GNode 430 [f,c,m,b,d,fs] -> do {
            format <- textAt graph f; identity <- textAt graph c; association <- textAt graph m;
            ensure (eqString format packageFormat && eqString identity compiler) "open crate checker/compiler version mismatch; rebuild object";
            ensure (eqString association metadata) "open crate interface mismatch";
            bindingRefs <- referenceList graph b;
            declarations <- referenceList graph d;
            entries <- nodeList graph fs;
            Right ((,,,) graph bindingRefs declarations entries)
          };
          _ -> Left "invalid open crate header"
        }
      } of {
        Left e -> ioReturn (Left e);
        Right ((,,,) graph bindingRefs declarations entries) -> do {
          bs <- validateReferences Structure.toXType allBindings bindingRefs;
          ds <- validateReferences declarationValue allDeclarations declarations;
          ioReturn (do {
            checkedBindings <- bs; checkedDeclarations <- ds;
            let { rows = M.toList checkedBindings; types = V.fromList (map snd rows);
              table = M.fromDistinctAscList (zip (map fst rows) (V.indices types)) };
            fragments <- decodeFinals graph ((,) table types) checkedDeclarations M.empty entries;
            let { usedKeys = S.fromList compareString (concatMap (\((,) _ fragment) ->
              map (compose X.nameHint fst) (append (parameters fragment) (bindings fragment))) fragments) };
            ensure (S.size usedKeys == length rows) "open crate binding reference inventory mismatch";
            ensure (length fragments == length (nubBy eqString (map fst fragments))) "duplicate open crate fragment";
            if eqString auditSetting "1" then mapM_ (compose audit snd) fragments else Right ();
            Right (Package metadata fragments bytes digest)
          })
        }
      }
    }
  };
  referenceList graph index = do {
    values <- Structure.decodeGraphValue (Structure.ShapeList
      (Structure.ShapePair Structure.ShapeText Structure.ShapeText)) graph index;
    rows <- Structure.expectList (Structure.expectPair Structure.expectText Structure.expectText) values;
    ensure (ascending (map fst rows)) "duplicate or unordered open crate reference";
    Right rows
  };
  ascending names = case names of {
    (:) a rest@((:) b _) -> compareString a b < 0 && ascending rest;
    _ -> True
  };
  nodeList graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of { W.GNode 1 entries -> Right entries; _ -> Left "expected open crate list" }
  };
  validateReferences encode available references = do {
    checked <- mapM (\((,) name expected) -> case M.lookup compareString name available of {
      Nothing -> ioReturn (Left ("missing open crate reference: " ++ name));
      Just value -> do {
        actual <- hashSyntax (encode value);
        ioReturn (do { digest <- actual;
          ensure (eqString digest expected) ("open crate dependency changed: " ++ name);
          Right ((,) name value) })
      }
    }) references;
    ioReturn (do {
      values <- sequenceEither checked;
      ensure (length values == length (nubBy eqString (map fst values))) "duplicate open crate reference";
      Right (M.fromList compareString values)
    })
  };
  decodeFinals graph types declarations contexts entries = case entries of {
    [] -> Right [];
    (:) index rest -> do {
      value <- W.lookupGraphNode graph index;
      case value of {
        W.GNode 401 [n,h,ds,ps,t,bs,uses] -> do {
          name <- textAt graph n; savedStamp <- textAt graph h;
          rawData <- decodedList Structure.ShapeText graph ds;
          names <- traverseEither Structure.expectText rawData;
          let { identity = Separate.pack names };
          env <- case M.lookup compareString identity contexts of {
            Just env -> Right env;
            Nothing -> do {
              values <- traverseEither (\key -> case M.lookup compareString key declarations of {
                Just d -> Right d; Nothing -> Left "open crate datatype reference out of scope" }) names;
              environment values
            }
          };
          params <- finalBindings graph types ps;
          owned <- finalBindings graph types bs;
          source <- Structure.fromGraphXTerm graph t;
          usedValues <- decodedList Structure.ShapeXName graph uses;
          used <- traverseEither Structure.expectXName usedValues;
          validateBinders params owned used;
          -- Final objects retain the checked fingerprint of their own ordered
          -- parameter list. The public interface only describes all exports.
          ensure (eqString savedStamp (stamp env params source owned)) "open crate fragment fingerprint mismatch";
          let { fragment = Fragment env params source owned used savedStamp };
          next <- decodeFinals graph types declarations (M.insert compareString identity env contexts) rest;
          Right ((:) ((,) name fragment) next)
        };
        _ -> Left "invalid final open crate fragment"
      }
    }
  };
  finalBindings :: W.Graph -> (,) (Map String (V.Index Declaration))
    (V.IndexVec Declaration XType) -> Int -> Either String ([] ((,) XName XType));
  finalBindings graph ((,) slots types) index = do {
    raw <- decodedList Structure.ShapeXName graph index;
    names <- traverseEither Structure.expectXName raw;
    aligned <- traverseEither (\name -> case M.lookup compareString (X.nameHint name) slots of {
      Just i -> Right ((,) name i); Nothing -> Left "open crate binding reference out of scope"
    }) names;
    ensure (IS.size (IS.fromList (map (compose V.toInt snd) aligned)) == length aligned)
      "duplicate open crate binding reference";
    Right (map (\((,) name i) -> (,) name (V.at types i)) aligned)
  }
}
