-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.NativeArtifact where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Bitstream as Bytes;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.NativeCrate as NativeCrate;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  import qualified Package.Release as Release;

  crateFormat :: String;
  crateFormat = "MLF-NATIVE-CRATE-1";
  exportAbi :: String;
  exportAbi = NativeCrate.nativeABI;
  reportFormat :: String;
  reportFormat = "MLF-NATIVE-PROGRAM-1";
  pinnedPlanFormat :: String;
  pinnedPlanFormat = "MLF-PINNED-NATIVE-DEPENDENCIES-1";

  -- Interfaces are keyed by logical crate ID in the handoff. Their digests
  -- and the optional checked body come from the same admitted producer proof.
  pinnedRow :: [] ((,) String Artifact.CrateInterface) -> String -> J.Json -> J.Json -> J.Json;
  pinnedRow graphRows metadata inputs native = let {
    checked = J.get "checked_closure" inputs;
    member ((,) path iface) = if J.has path checked then Just (J.object
      [(,) "crate_id" (J.str (Artifact.crateId iface)), (,) "sha256" (J.get path checked)]) else Nothing;
    file path digest = J.object [(,) "path" (J.str path), (,) "sha256" digest];
    interfaces = S.sortBy (\a b -> compareString (J.getText "crate_id" "" a) (J.getText "crate_id" "" b))
      (S.mapMaybe member graphRows);
    object = J.getText "path" "" native;
    body = Artifact.objectPath metadata
  } in J.object [(,) "crate_id" (J.get "crate_id" native), (,) "identity" (J.get "identity" native),
    (,) "interfaces" (J.array interfaces),
    (,) "contract" (file (O.parent object ++ "/contract.json") (J.get "contract_sha256" native)),
    (,) "object" (file object (J.get "sha256" native)), (,) "checked" (file body (J.get body checked))];

  -- Clang supplies both values for the actual code generation flags. An
  -- absent/ambiguous target header makes this target ineligible for reuse.
  llvmHeader :: String -> String -> Either String String;
  llvmHeader key llvm = let {
    prefix = key ++ " = \"";
    rows = S.filter (O.starts prefix) (S.map O.trim (O.lines llvm))
  } in case rows of {
    [row] -> if O.ends "\"" row && stringLength row > stringLength prefix + 1
      then Right (stringSlice row (stringLength prefix) (stringLength row - stringLength prefix - 1))
      else Left ("invalid Clang " ++ key);
    _ -> Left ("missing or ambiguous Clang " ++ key)
  };

  targetConfig :: J.Json -> [] String -> J.Json -> String -> Either String J.Json;
  targetConfig tools flags profile llvm = do {
    triple <- llvmHeader "target triple" llvm;
    layout <- llvmHeader "target datalayout" llvm;
    let { fields = O.words "compiler clang implementation-identity system machine native_environment runtime gmp windows" };
    Right (J.Object (S.append
      [(,) "target_triple" (J.str triple), (,) "data_layout" (J.str layout),
       (,) "runtime_abi" (J.str LLVM.runtimeAbi), (,) "primitive_abi" (J.str Lexer.primitiveAbi),
       (,) "builtin_interface" (J.str Lexer.builtinInterfaceVersion),
       (,) "export_abi" (J.str exportAbi), (,) "flags" (J.stringArray flags), (,) "profile" profile]
      (S.map (\key -> (,) key (J.get key tools)) (S.filter (\key -> J.has key tools) fields))))
  };

  producerInputsFromProof :: J.Json -> String -> J.Json -> J.Json;
  producerInputsFromProof target identity proof = J.object
    [(,) "crate_id" (J.str identity), (,) "target" target, (,) "checked_closure" proof];

  digestFile :: String -> IO (Either String String);
  digestFile path = do {
    exists <- fileExists path;
    if S.not exists then ioReturn (Left ("missing artifact file: " ++ path)) else do {
      digest <- fileDigest path;
      ioReturn (if Release.validDigest digest then Right digest else Left ("cannot hash artifact file: " ++ path))
    }
  };

  -- The admitted graph is dependency-first. Hash each checked pair once for
  -- the whole target and union already computed proofs through diamond imports.
  producerInputsFor :: J.Json -> [] ((,) String Artifact.CrateInterface) -> IO (Either String ([] ((,) String J.Json)));
  producerInputsFor target interfaces = collectInputs target M.empty [] interfaces;
  collectInputs :: J.Json -> Map String (Map String J.Json) -> [] ((,) String J.Json) ->
    [] ((,) String Artifact.CrateInterface) -> IO (Either String ([] ((,) String J.Json)));
  collectInputs target done results interfaces = case interfaces of {
    [] -> ioReturn (Right (S.reverse results));
    (:) ((,) path iface) rest -> do {
      let { object = Artifact.objectPath path; identity = Artifact.crateId iface };
      metadataHash <- digestFile path;
      bodyHash <- digestFile object;
      let { checked = do {
        metadata <- metadataHash;
        body <- bodyHash;
        dependencies <- S.traverseEither (\dep -> case M.lookup compareString (Artifact.dependencyId dep) done of {
          Nothing -> Left ("missing checked dependency: " ++ Artifact.dependencyId dep);
          Just proof -> Right proof
        }) (Artifact.crateDependencies iface);
        let { own = M.fromList compareString [(,) path (J.str metadata), (,) object (J.str body)] };
        Right (M.unions compareString ((:) own dependencies))
      } };
      case checked of {
        Left message -> ioReturn (Left message);
        Right proof -> collectInputs target (M.insert compareString identity proof done)
          ((:) ((,) path (producerInputsFromProof target identity (J.Object (M.toList proof)))) results) rest
      }
    }
  };
  producerInputs :: J.Json -> String -> IO (Either String J.Json);
  producerInputs target metadata = do {
    loaded <- Artifact.loadInterfaces [metadata];
    case loaded of {
      Left message -> ioReturn (Left message);
      Right interfaces -> do {
        inputs <- producerInputsFor target interfaces;
        path <- canonicalPath metadata;
        ioReturn (S.bindEither inputs (\rows -> case S.lookup eqString path rows of {
          Nothing -> Left ("missing native producer root: " ++ metadata);
          Just root -> Right root
        }))
      }
    }
  };

  nonempty :: J.Json -> Bool;
  nonempty value = case value of { J.String text -> stringLength text > 0; _ -> False };
  natural :: J.Json -> Bool;
  natural value = case value of {
    J.Number text -> stringLength text > 0 && S.all (\i -> let { c = stringCodeAt text i } in
      c >= 48 && c <= 57) (S.range 0 (stringLength text - 1));
    _ -> False
  };
  validSlots :: J.Json -> Bool;
  validSlots value = case value of {
    J.Array slots -> let {
      valid = S.mapIndexed (\index row -> case row of {
        J.Object _ -> J.equal (J.get "slot" row) (J.num index) && nonempty (J.get "key" row) && nonempty (J.get "type" row);
        _ -> False
      }) slots;
      keys = S.map (J.getText "key" "") slots
    } in S.and valid && S.eqList eqString keys (Set.toList (Set.fromList compareString keys));
    _ -> False
  };
  validTags :: J.Json -> Bool;
  validTags value = case value of {
    J.Array rows -> let {
      valid row = case row of {
        J.Object _ -> nonempty (J.get "name" row) && natural (J.get "tag" row) && natural (J.get "arity" row);
        _ -> False
      };
      unique keys = Set.size (Set.fromList compareString keys) == S.length rows
    } in S.all valid rows &&
      unique (S.map (J.getText "name" "") rows) &&
      unique (S.map (\row -> J.render (J.get "tag" row)) rows);
    _ -> False
  };

  validateContract :: String -> String -> String -> J.Json -> Either String J.Json;
  validateContract runtime identity symbol contract = case contract of {
    J.Object _ -> do {
      let { expected = [(,) "format" crateFormat, (,) "export_abi" exportAbi, (,) "runtime_abi" runtime,
                         (,) "crate_id" identity, (,) "identity" symbol] };
      S.ensure (Release.validDigest symbol && S.all (\((,) key value) ->
        J.equal (J.get key contract) (J.str value)) expected) "native compiler contract identity or ABI mismatch";
      case J.get "status" contract of {
        J.String "eligible" -> S.ensure (validSlots (J.get "exports" contract) &&
          validSlots (J.get "imports" contract) && validTags (J.get "constructor_tags" contract))
          "invalid native export, import or constructor layout";
        J.String "unsupported" -> S.ensure (nonempty (J.get "reason" contract)) "missing native eligibility reason";
        _ -> Left "invalid native compiler contract status"
      };
      Right contract
    };
    _ -> Left "expected native compiler contract"
  };

  readJson :: String -> IO (Either String J.Json);
  readJson path = do {
    exists <- fileExists path;
    if S.not exists then ioReturn (Left ("missing native receipt: " ++ path)) else do {
      text <- readFile path;
      ioReturn (S.mapLeft (\message -> path ++ ": " ++ message) (J.parse text))
    }
  };

  -- The driver's content-addressed artifact action owns the directory, performs
  -- atomic publication and verifies its file stamp. Derive paths from that
  -- directory; no serialized receipt can redirect the linker to another file.
  artifactReceipt :: String -> J.Json -> String -> IO (Either String ((,) J.Json J.Json));
  artifactReceipt directory inputs symbol = do {
    let { manifest = directory ++ "/contract.json"; object = directory ++ "/unit.o";
          identity = J.getText "crate_id" "" inputs;
          runtime = J.getText "runtime_abi" "" (J.get "target" inputs) };
    parsed <- readJson manifest;
    case S.bindEither parsed (validateContract runtime identity symbol) of {
      Left message -> ioReturn (Left message);
      Right contract -> do {
        contractHash <- digestFile manifest;
        let { eligible = J.equal (J.get "status" contract) (J.str "eligible") };
        objectHash <- if eligible then digestFile object else ioReturn (Right "");
        ioReturn (do {
          digest <- contractHash;
          machine <- objectHash;
          S.ensure (S.not eligible || S.not (eqString machine "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"))
            "native library object is empty";
          let { common = [(,) "status" (J.get "status" contract), (,) "crate_id" (J.str identity),
                           (,) "identity" (J.str symbol), (,) "contract_sha256" (J.str digest)];
                evidence = if eligible then [(,) "sha256" (J.str machine)] else [(,) "reason" (J.get "reason" contract)];
                fields = S.append common evidence;
                receipt = J.Object (S.append [(,) "format" (J.str "MLF-NATIVE-ARTIFACT-1"), (,) "inputs" inputs] fields);
                selection = J.set "contract" contract (J.Object (if eligible then (:) ((,) "path" (J.str object)) fields else fields)) };
          Right ((,) receipt selection)
        })
      }
    }
  };

  publish :: String -> J.Json -> String -> IO (Either String J.Json);
  publish directory inputs symbol = do {
    result <- artifactReceipt directory inputs symbol;
    case result of {
      Left message -> ioReturn (Left message);
      Right ((,) receipt row) -> do {
        -- Detect changes between capturing the producer identity and compiling.
        matches <- S.mapM (\((,) path expected) -> do {
          actual <- digestFile path;
          ioReturn (S.either (\_ -> False) (\digest -> J.equal expected (J.str digest)) actual)
        }) (J.items (J.get "checked_closure" inputs));
        if S.and matches then do { J.write (directory ++ "/native.json") receipt; ioReturn (Right row) }
        else ioReturn (Left "checked crate inputs changed during native compilation")
      }
    }
  };
  admit :: String -> J.Json -> String -> IO (Either String J.Json);
  admit directory inputs symbol = do {
    saved <- readJson (directory ++ "/native.json");
    case saved of {
      Left message -> ioReturn (Left message);
      Right receipt -> do {
        result <- artifactReceipt directory inputs symbol;
        ioReturn (S.bindEither result (\((,) expected selection) -> do {
          S.ensure (J.equal receipt expected) "native receipt differs from checked producer inputs, compiler contract or object digest";
          Right selection
        }))
      }
    }
  };

  data Pinned = Pinned String String (Maybe ((,) String String)) (Either String ((,) J.Json ((,) String String)));
  pinnedCrate :: Pinned -> String;
  pinnedCrate (Pinned owner _ _ _) = owner;
  pinnedIdentity :: Pinned -> String;
  pinnedIdentity (Pinned _ symbol _ _) = symbol;
  pinnedChecked :: Pinned -> Maybe ((,) String String);
  pinnedChecked (Pinned _ _ checked _) = checked;
  pinnedContract :: Pinned -> Either String J.Json;
  pinnedContract (Pinned _ _ _ result) = S.mapEither S.fst result;
  pinnedObject :: Pinned -> ((,) String String);
  pinnedObject (Pinned _ _ _ result) = S.either (\_ -> panic "unselected native object") S.snd result;

  -- Hash and decode the same snapshot. Caller-supplied expected hashes are
  -- independent of these files, including the initial hash of the plan itself.
  pinnedJson :: String -> String -> IO (Either String J.Json);
  pinnedJson path expected = if S.not (Release.validDigest expected)
    then ioReturn (Left ("invalid expected SHA-256: " ++ path)) else do {
      raw <- Storage.readRaw path;
      case raw of {
        Left message -> ioReturn (Left (path ++ ": " ++ message));
        Right bytes -> do {
          actual <- byteArrayDigest bytes;
          if S.not (eqString expected actual) then ioReturn (Left ("SHA-256 mismatch: " ++ path)) else do {
            decoded <- Bytes.strictUtf8 Storage.maxBytes bytes;
            ioReturn (S.mapLeft (\message -> path ++ ": " ++ message) (S.bindEither decoded J.parse))
          }
        }
      }
    };

  pinText :: String -> J.Json -> Either String String;
  pinText key value = case value of {
    J.Object _ -> case J.get key value of {
      J.String text -> if stringLength text > 0 then Right text else Left ("empty native pin field: " ++ key);
      _ -> Left ("missing native pin field: " ++ key)
    };
    _ -> Left "expected pinned dependency object"
  };
  pinHash :: J.Json -> Either String String;
  pinHash value = do {
    digest <- pinText "sha256" value;
    S.ensure (Release.validDigest digest) "invalid SHA-256 in native dependency pin";
    Right digest
  };
  filePin :: J.Json -> Either String ((,) String String);
  filePin value = do {
    path <- pinText "path" value;
    S.ensure (Host.absolutePath path && S.not (Storage.hasNul path 0)) "native dependency pin needs an absolute path";
    hash <- pinHash value;
    Right ((,) path hash)
  };

  -- The target file is supplied by the caller for this emission; its digest
  -- binds the Clang probe (including cross targets) and producer provenance
  -- to the authorized plan. Check the ABI and the compiler actually running.
  activeTarget :: String -> String -> IO (Either String ());
  activeTarget path expected = do {
    result <- pinnedJson path expected;
    case S.bindEither result (\target -> do {
      triple <- pinText "target_triple" target;
      layout <- pinText "data_layout" target;
      S.ensure (O.starts "e-" layout || O.starts "E-" layout) ("invalid LLVM data layout for " ++ triple);
      let { abi = [(,) "runtime_abi" LLVM.runtimeAbi, (,) "primitive_abi" Lexer.primitiveAbi,
                    (,) "builtin_interface" Lexer.builtinInterfaceVersion, (,) "export_abi" exportAbi] };
      S.ensure (S.all (\((,) key value) -> J.equal (J.get key target) (J.str value)) abi) "pinned native target ABI mismatch";
      _ <- pinHash (J.get "clang" target);
      pinHash (J.get "compiler" target)
    }) of {
      Left reason -> ioReturn (Left reason);
      Right compilerHash -> do {
        executable <- getExecutablePath;
        actual <- digestFile executable;
        ioReturn (S.bindEither actual (\digest -> S.ensure (eqString compilerHash digest) "pinned native compiler digest mismatch"))
      }
    }
  };

  headerProof :: (,) String Artifact.CrateInterface -> IO ((,) String (Either String String));
  headerProof ((,) path admitted) = do {
    raw <- Storage.readRaw path;
    result <- case raw of {
      Left message -> ioReturn (Left message);
      Right bytes -> do {
        digest <- byteArrayDigest bytes;
        decoded <- Artifact.decodeInterfaceBytes bytes;
        ioReturn (S.bindEither decoded (\iface -> do {
          S.ensure (Artifact.sameAdmittedInterface admitted iface) ("checked interface changed during native admission: " ++ path);
          Right digest
        }))
      }
    };
    ioReturn ((,) (Artifact.crateId admitted) result)
  };

  interfacePins :: J.Json -> Either String (Map String String);
  interfacePins row = case J.get "interfaces" row of {
    J.Array interfaces -> S.foldEither (\pins entry -> do {
      owner <- pinText "crate_id" entry;
      hash <- pinHash entry;
      S.ensure (S.not (M.member compareString owner pins)) "duplicate checked interface in native pin";
      Right (M.insert compareString owner hash pins)
    }) M.empty interfaces;
    _ -> Left "native dependency is missing its checked interface closure"
  };
  checkInterfaces :: Map String Artifact.CrateInterface -> Map String (Either String String) ->
    String -> J.Json -> Either String ();
  checkInterfaces graph hashes owner row = do {
    pins <- interfacePins row;
    closure <- Artifact.dependencyClosure graph [] [] [owner];
    S.ensure (M.size pins == S.length closure) "native dependency interface inventory differs from checked closure";
    _ <- S.traverseEither (\iface -> let { key = Artifact.crateId iface } in do {
      actual <- S.fromMaybe (Left ("missing checked interface snapshot: " ++ key)) (M.lookup compareString key hashes);
      S.ensure (S.maybe False (eqString actual) (M.lookup compareString key pins)) ("native dependency interface digest mismatch: " ++ key)
    }) closure;
    Right ()
  };

  -- The object is a binary file with no crate syntax. Read failures are local
  -- eligibility misses just like digest mismatches, including raced removal.
  verifyObject :: ((,) String String) -> IO (Either String ());
  verifyObject ((,) path expected) = do {
    (,) error bytes <- readByteFileOrError path 1152921504606846975;
    if S.not (eqString error "") then ioReturn (Left (path ++ ": " ++ error)) else do {
      size <- lengthByteArray bytes;
      actual <- byteArrayDigest bytes;
      ioReturn (S.ensure (size > 0 && eqString expected actual) ("native object SHA-256 mismatch: " ++ path))
    }
  };

  readProvider :: Either String () -> Map String Artifact.CrateInterface -> Map String (Either String String) ->
    (,) String J.Json -> IO Pinned;
  readProvider target graph hashes ((,) owner row) = do {
    let { symbol = S.either (\_ -> "") S.id (pinText "identity" row);
          checked = if J.has "checked" row then S.either (\_ -> Nothing) Just (filePin (J.get "checked" row)) else Nothing;
          prepare = do {
            target;
            checkInterfaces graph hashes owner row;
            contract <- filePin (J.get "contract" row);
            object <- filePin (J.get "object" row);
            Right ((,) contract object)
          } };
    result <- case prepare of {
      Left message -> ioReturn (Left message);
      Right ((,) ((,) path hash) object) -> do {
        saved <- pinnedJson path hash;
        case S.bindEither saved (validateContract LLVM.runtimeAbi owner symbol) of {
          Left message -> ioReturn (Left message);
          Right contract -> if S.not (J.equal (J.get "status" contract) (J.str "eligible"))
            then ioReturn (Left (J.getText "reason" "unsupported native crate" contract)) else do {
              verified <- verifyObject object;
              ioReturn (S.mapEither (\_ -> (,) contract object) verified)
            }
        }
      }
    };
    ioReturn (Pinned owner symbol checked result)
  };

  readPinnedPlan :: String -> String -> String -> [] ((,) String Artifact.CrateInterface) ->
    IO (Either String ([] Pinned));
  readPinnedPlan path digest target rows = do {
    plan <- pinnedJson path digest;
    let { graph = Artifact.interfaceMap (S.map S.snd rows);
          parse value = do {
            format <- pinText "format" value;
            S.ensure (eqString format pinnedPlanFormat) "unknown pinned native dependency plan";
            targetHash <- pinText "target_sha256" value;
            providers <- case J.get "dependencies" value of {
              J.Array entries -> S.traverseEither (\row -> S.mapEither (\owner -> (,) owner row) (pinText "crate_id" row)) entries;
              _ -> Left "expected pinned native dependency array"
            };
            S.ensure (M.size (M.fromList compareString providers) == S.length providers) "duplicate pinned native dependency";
            Right ((,) targetHash providers)
          } };
    case S.bindEither plan parse of {
      Left message -> ioReturn (Left message);
      Right ((,) targetHash providers) -> do {
        current <- activeTarget target targetHash;
        let { owners = S.filter (\owner -> M.member compareString owner graph) (S.map S.fst providers);
              required = S.bindEither current (\_ -> Artifact.dependencyClosure graph [] [] owners);
              wanted = Set.fromList compareString (S.either (\_ -> []) (S.map Artifact.crateId) required) };
        proofs <- S.mapM headerProof (S.filter (\((,) _ iface) -> Set.member compareString (Artifact.crateId iface) wanted) rows);
        admitted <- S.mapM (readProvider current graph (M.fromList compareString proofs)) providers;
        ioReturn (Right admitted)
      }
    }
  }
}
