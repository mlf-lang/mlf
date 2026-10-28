-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CrateArtifact where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Fresh as Fresh;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.SourceEquality as Equality;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Separate as Separate;
  -- Source visibility, the closed linking inventory, and checked SCC fragments
  -- have deliberately separate representations. Dependencies refer to metadata
  -- files, so inference never needs to open an upstream implementation object.
  data CrateInterface =
    CrateInterface String ([] ((,,) String String String)) ([] String) ([]
                                                                              ((,) String
                                                                               ([]
                                                                                Modules.Entity))) ([]
                                                                                                   ((,)
                                                                                                    String
                                                                                                    ([]
                                                                                                     String))) ([]
                                                                                                                DataDecl) ([]
                                                                                                                           SClassDecl) ([]
                                                                                                                                        ((,)
                                                                                                                                         String
                                                                                                                                         SInstanceDecl)) ([]
                                                                                                                                                          DataDecl) ([]
                                                                                                                                                                     ((,)
                                                                                                                                                                      String
                                                                                                                                                                      XType)) String String ([] ((,) String Bool));
  data CrateObject =
    CrateObject CrateInterface ([] Separate.UnitObject) |
    LegacyCrateObject CrateInterface ([] Separate.UnitObject);
  crateId (CrateInterface n _ _ _ _ _ _ _ _ _ _ _ _) = n;
  crateDependencies (CrateInterface _ ds _ _ _ _ _ _ _ _ _ _ _) = ds;
  crateModules (CrateInterface _ _ ms _ _ _ _ _ _ _ _ _ _) = ms;
  crateExports (CrateInterface _ _ _ es _ _ _ _ _ _ _ _ _) = es;
  crateImports (CrateInterface _ _ _ _ is _ _ _ _ _ _ _ _) = is;
  crateData (CrateInterface _ _ _ _ _ ds _ _ _ _ _ _ _) = ds;
  crateClasses (CrateInterface _ _ _ _ _ _ cs _ _ _ _ _ _) = cs;
  crateInstances (CrateInterface _ _ _ _ _ _ _ is _ _ _ _ _) = is;
  crateLoweredData (CrateInterface _ _ _ _ _ _ _ _ ds _ _ _ _) = ds;
  crateBindings (CrateInterface _ _ _ _ _ _ _ _ _ bs _ _ _) = bs;
  crateEntry (CrateInterface _ _ _ _ _ _ _ _ _ _ e _ _) = e;
  crateObjectFingerprint (CrateInterface _ _ _ _ _ _ _ _ _ _ _ h _) = h;
  crateProtection (CrateInterface _ _ _ _ _ _ _ _ _ _ _ _ protection) = protection;
  objectInterface (CrateObject i _) = i;
  objectInterface (LegacyCrateObject i _) = i;
  objectFragments (CrateObject _ fs) = fs;
  objectFragments (LegacyCrateObject _ fs) = fs;
  definitionName identity entity =
    case Separate.managedBuiltinName entity of {
      Just name -> name;
      Nothing -> ordinaryDefinitionName identity entity
    };
  ordinaryDefinitionName identity entity =
    if (eqString (Modules.owner entity) "Prelude" || Modules.isRole Modules.BuiltinType entity)
    then Separate.stableName entity
    else ((if ((Modules.compareSpace (Modules.space entity) Modules.Types == 0) ||
               (case Modules.role entity of {
                  Modules.Constructor _ -> True;
                  _ -> False
                }))
           then "Module_"
           else "module_") ++
          (Separate.encoded identity ++
           ("z_" ++ Separate.encoded (Separate.entityEncoding entity))));
  startsWith prefix text =
    ((stringLength text >= stringLength prefix) &&
     eqString prefix (stringSlice text 0 (stringLength prefix)));
  instancePrefix identity owner =
    ("instance_" ++ (Separate.encoded identity ++ ("z_" ++ (Separate.encoded owner ++ "z_"))));
  instanceName identity owner inst =
    (instancePrefix identity owner ++
     Separate.encoded
       (Separate.fingerprint (Separate.prettyInstance (Separate.stripInstance inst))));
  instanceOwner iface symbol =
    case filter (\owner -> startsWith (instancePrefix (crateId iface) owner) symbol)
           (crateModules iface) of {
      (:) owner [] -> Right owner;
      _ -> Left ("instance dictionary has no unique owning module: " ++ symbol)
    };
  entryOwner :: CrateInterface -> Either String String;
  entryOwner iface =
    case filter
           (\owner ->
              eqString
                (definitionName (crateId iface)
                   (Modules.Entity owner "<crate-entry>" Modules.Value))
                (crateEntry iface))
           (crateModules iface) of {
      (:) owner [] -> Right owner;
      _ -> Left "crate entry has no unique owning module"
    };
  sortStrings xs = sortBy compareString xs;
  sortPairs xs = sortBy (\a b -> compareString (fst a) (fst b)) xs;
  sortDependencies xs = sortBy (\((,,) a _ _) ((,,) b _ _) -> compareString a b) xs;
  sortEntities xs =
    sortBy (\a b -> compareString (Separate.entityEncoding a) (Separate.entityEncoding b)) xs;
  sortData xs = sortBy (\a b -> compareString (D.datatypeName a) (D.datatypeName b)) xs;
  sortClasses xs = sortBy (\a b -> compareString (Classes.className a) (Classes.className b)) xs;
  encodeBindings bs =
    Separate.pack
      (map
         (\((,) n ty) ->
            Separate.pairEncoding ((,) n (Pretty.prettyType (Separate.normalType ty))))
         (sortPairs bs));
  sourceMetadata ds cs instances =
    unlines
      (append (map D.prettyDeclaration (sortData ds))
         (append (map Separate.prettyClass (sortClasses cs))
            (map (\p -> Separate.prettyInstance (snd p)) (sortPairs instances))));
  encodeExports es =
    Separate.pack
      (map
         (\((,) n entities) ->
            Separate.pairEncoding
              ((,) n (Separate.pack (map Separate.entityEncoding (sortEntities entities)))))
         (sortPairs es));
  encodeImports is =
    Separate.pack
      (map
         (\((,) n imports) -> Separate.pairEncoding ((,) n (Separate.pack (sortStrings imports))))
         (sortPairs is));
  encodeDependency ((,,) name path semantic) =
    Separate.pack ((:) name ((:) path ((:) semantic [])));
  -- The ABI excludes object checksums and private value contracts. Facades with
  -- foreign exports additionally retain stable dependency semantic identities,
  -- so protection-only changes propagate without depending on relocated paths.
  semanticFingerprint iface =
    let {
      exported = concatMap snd (crateExports iface)
    } in
    let {
      publicNames = Set.fromList compareString (map (definitionName (crateId iface)) exported)
    } in
    let {
      public = filter (\p -> Set.member compareString (fst p) publicNames) (crateBindings iface)
    } in
    let {
      fields =
        (:) "MLF-CRATE-SEMANTICS-5"
          ((:) (crateId iface)
             ((:) (encodeExports (crateExports iface))
                ((:) (encodeImports (crateImports iface))
                   ((:)
                      (sourceMetadata (crateData iface) (crateClasses iface) (crateInstances iface))
                      ((:) (Separate.pack (map fst (sortPairs (crateInstances iface))))
                         ((:)
                            (unlines (map D.prettyDeclaration (sortData (crateLoweredData iface))))
                            ((:) (encodeBindings public) [])))))))
    } in
    Separate.fingerprint (Separate.pack
      (append fields ((:) (encodeProtection
        (filter (\entry -> Set.member compareString (fst entry) publicNames) (crateProtection iface)))
        ((:) (Separate.pack (if any (\entity -> not (elem eqString (Modules.owner entity) (crateModules iface))) exported
          then map (\((,,) name _ semantic) -> Separate.pack [name, semantic])
            (sortDependencies (crateDependencies iface)) else [])) []))));
  encodeProtection values = Separate.pack (map
    (\((,) name protected) -> Separate.pack [name, if protected then "true" else "false"])
    (sortPairs values));
  decodeProtection :: String -> Either String ([] ((,) String Bool));
  decodeProtection value = do {
    fields <- Separate.unpack value;
    traverseEither (\field -> do {
      pair <- Separate.unpack field;
      case pair of {
        [name, flag] ->
          if eqString flag "true" then Right ((,) name True)
          else if eqString flag "false" then Right ((,) name False)
          else Left "malformed crate protection flag";
        _ -> Left "malformed crate protection entry"
      }
    }) fields
  };
  interfaceFields iface =
    snoc (rawInterfaceFields iface) (encodeProtection (crateProtection iface));
  rawInterfaceFields iface =
    (:) "MLFCI-5"
      ((:) (crateId iface)
         ((:) (Separate.pack (map encodeDependency (sortDependencies (crateDependencies iface))))
            ((:) (Separate.pack (sortStrings (crateModules iface)))
               ((:) (encodeExports (crateExports iface))
                  ((:) (encodeImports (crateImports iface))
                     ((:)
                        (sourceMetadata (crateData iface) (crateClasses iface)
                           (crateInstances iface))
                        ((:) (Separate.pack (map fst (sortPairs (crateInstances iface))))
                           ((:)
                              (unlines
                                 (map D.prettyDeclaration (sortData (crateLoweredData iface))))
                              ((:) (encodeBindings (crateBindings iface))
                                 ((:) (crateEntry iface)
                                    ((:) (crateObjectFingerprint iface) [])))))))))));
  encodeInterface iface =
    let {
      fields = interfaceFields iface
    } in
    Separate.pack (snoc fields (Separate.fingerprint (Separate.pack fields)));
  decodeDependency text =
    do {
      fields <- Separate.unpack text;
      case fields of {
        (:) name ((:) path ((:) semantic [])) ->
          do {
            ensure
              ((stringLength name > 0) && ((stringLength semantic > 0) && Host.absolutePath path))
              "crate dependency metadata path must be absolute";
            Right ((,,) name path semantic)
          };
        _ -> Left "malformed crate dependency"
      }
    };
  decodeExports text =
    do {
      entries <- Separate.unpack text;
      traverseEither
        (\entry ->
           do {
             boundValueShared1 <- Separate.decodePair entry;
             case boundValueShared1 of {
               (,) n encoded ->
                 do {
                   fields <- Separate.unpack encoded;
                   entities <- traverseEither Separate.decodeEntity fields;
                   ensure
                     (length entities == Set.size (Set.fromList Modules.compareEntity entities))
                     "duplicate crate export entity";
                   Right ((,) n entities)
                 }
             }
           })
        entries
    };
  decodeImports text =
    do {
      entries <- Separate.unpack text;
      traverseEither
        (\entry ->
           do {
             boundValueShared2 <- Separate.decodePair entry;
             case boundValueShared2 of {
               (,) n encoded ->
                 do {
                   imports <- Separate.unpack encoded;
                   ensure (length imports == length (nubBy eqString imports))
                     "duplicate crate module reach entry";
                   Right ((,) n imports)
                 }
             }
           })
        entries
    };
  decodeBindings text =
    do {
      entries <- Separate.unpack text;
      traverseEither
        (\entry ->
           do {
             boundValueShared3 <- Separate.decodePair entry;
             case boundValueShared3 of {
               (,) n t ->
                 do {
                   ty <- XP.parseType t;
                   Right ((,) n ty)
                 }
             }
           })
        entries
    };
  uniqueNames label names =
    ensure (length names == Set.size (Set.fromList compareString names))
      ("duplicate crate " ++ label);
  isPrimitiveEntity entity =
    any (\e -> (Modules.compareEntity e entity == 0))
      (append Modules.primitiveEntities Modules.sharedPrimitiveEntities);
  data ExportInventory =
    ExportInventory (Set String) (Set String) (Set String) (Set String) (Set String);
  exportInventory iface =
    ExportInventory (Set.fromList compareString (map fst (crateBindings iface)))
      (Set.fromList compareString (map D.datatypeName (crateData iface)))
      (Set.fromList compareString (map Classes.className (crateClasses iface)))
      (Set.fromList compareString
         (concatMap (\d -> map D.constructorName (D.datatypeConstructors d)) (crateData iface)))
      (Set.fromList compareString
         (concatMap (\c -> map fst (Classes.classMethods c)) (crateClasses iface)));
  validateOwnExport iface (ExportInventory values datatypes classes constructors methods) entity =
    if (isPrimitiveEntity entity || not (elem eqString (Modules.owner entity) (crateModules iface)))
    then Right ()
    else do {
           let {
             name = definitionName (crateId iface) entity
           };
           let {
             declared =
               case Modules.role entity of {
                 Modules.Value -> Set.member compareString name values;
                 Modules.Datatype -> Set.member compareString name datatypes;
                 Modules.Class -> Set.member compareString name classes;
                 Modules.Constructor _ -> Set.member compareString name constructors;
                 Modules.Method _ -> Set.member compareString name methods;
                 _ -> False
               }
           };
           ensure declared ("crate exports an undeclared entity: " ++ Modules.label entity)
         };
  builtinCrateIdentity :: String;
  builtinCrateIdentity = "mlf:builtin-shared-haskell-v1:9";
  validateBuiltinOwnership iface =
    if (any Modules.isBuiltinModule (crateModules iface) ||
        ((stringLength (crateId iface) >= stringLength "mlf:builtin-shared-haskell-v1:") &&
         eqString (stringSlice (crateId iface) 0 (stringLength "mlf:builtin-shared-haskell-v1:"))
           "mlf:builtin-shared-haskell-v1:"))
    then do {
           ensure (eqString (crateId iface) builtinCrateIdentity)
             "stale or forged builtin crate identity";
           ensure (eqList eqString (sortStrings (crateModules iface)) ["MLF.Primitive", "Prelude"])
             "builtin crate must own exactly Prelude and MLF.Primitive"
         }
    else Right ();
  validateInterface iface =
    do {
      validateBuiltinOwnership iface;
      ensure
        ((stringLength (crateId iface) > 0) && (stringLength (crateObjectFingerprint iface) > 0))
        "incomplete crate metadata";
      uniqueNames "dependency" (map (\((,,) n _ _) -> n) (crateDependencies iface));
      uniqueNames "dependency path" (map (\((,,) _ path _) -> path) (crateDependencies iface));
      uniqueNames "module" (crateModules iface);
      uniqueNames "module exports" (map fst (crateExports iface));
      uniqueNames "module reach" (map fst (crateImports iface));
      uniqueNames "binding" (map fst (crateBindings iface));
      uniqueNames "binding protection" (map fst (crateProtection iface));
      ensure (eqList eqString (sortStrings (map fst (crateProtection iface)))
        (sortStrings (map fst (crateBindings iface))))
        "crate protection inventory differs from owned bindings";
      uniqueNames "instance" (map fst (crateInstances iface));
      uniqueNames "datatype" (map D.datatypeName (crateLoweredData iface));
      ensure (not (any (\((,,) n _ _) -> eqString n (crateId iface)) (crateDependencies iface)))
        ("cyclic crate dependency: " ++ crateId iface);
      ensure
        (eqList eqString (sortStrings (map fst (crateExports iface)))
           (sortStrings (crateModules iface)))
        "crate export inventory differs from owned modules";
      ensure
        (eqList eqString (sortStrings (map fst (crateImports iface)))
           (sortStrings (crateModules iface)))
        "crate module reach inventory differs from owned modules";
      traverseEither Separate.validModuleName (crateModules iface);
      traverseEither (\((,) _ modules) -> traverseEither Separate.validModuleName modules)
        (crateImports iface);
      traverseEither (validateOwnExport iface (exportInventory iface))
        (concatMap snd (crateExports iface));
      traverseEither
        (\((,) n ty) ->
           ensure ((stringLength n > 0) && Set.null (T.freeVars ty))
             ("crate binding has an open type: " ++ n))
        (crateBindings iface);
      traverseEither
        (\((,) n inst) ->
           do {
             owner <- instanceOwner iface n;
             ensure (eqString n (instanceName (crateId iface) owner inst))
               "unstable crate instance identity"
           })
        (crateInstances iface);
      ensure
        (eqString (crateEntry iface) "" ||
         M.member compareString (crateEntry iface) (M.fromList compareString (crateBindings iface)))
        "crate entry is not an owned binding";
      if eqString (crateEntry iface) ""
      then Right ()
      else mapEither (\_ -> ()) (entryOwner iface)
    };
  decodeInterface :: String -> Either String CrateInterface;
  decodeInterface input = do {
    fields <- Separate.unpack input;
    case fields of {
      [tag, identity, deps, modules, exports, imports, metadata, instanceNames,
       layouts, bindings, entry, bodyHash, protectionField, checksum] -> do {
        ensure (eqString tag "MLFCI-5") "unsupported crate metadata epoch (expected MLFCI-5)";
        ensure (eqString checksum (Separate.fingerprint (Separate.pack (interfacePrefix fields))))
          "crate metadata checksum mismatch";
        dependencies <- bindEither (Separate.unpack deps) (traverseEither decodeDependency);
        owned <- Separate.unpack modules;
        exported <- decodeExports exports;
        reach <- decodeImports imports;
        source <- Parser.parseMetadataModule "<crate metadata>"
          ("module CrateMetadata where {\n" ++ metadata ++ "\n}");
        lowered <- Parser.parseMetadataModule "<crate layout metadata>"
          ("module CrateLayouts where {\n" ++ layouts ++ "\n}");
        names <- Separate.unpack instanceNames;
        schemes <- decodeBindings bindings;
        protection <- decodeProtection protectionField;
        ensure (length names == length (Modules.sourceInstances source))
          "crate instance metadata count mismatch";
        ensure (null (Modules.sourceValues source) && null (Modules.sourceImports source) &&
          null (Modules.sourceValues lowered) && null (Modules.sourceImports lowered) &&
          null (Modules.sourceClasses lowered) && null (Modules.sourceInstances lowered))
          "crate metadata contains executable declarations";
        let { iface = CrateInterface identity dependencies owned exported reach
          (Modules.sourceDatatypes source) (Modules.sourceClasses source)
          (zip names (map Separate.stripInstance (Modules.sourceInstances source)))
          (Modules.sourceDatatypes lowered) schemes entry bodyHash protection };
        validateInterface iface;
        -- The checksum above authenticates the decoded prefix. Full canonical
        -- byte equality below also requires that prefix to equal interfaceFields;
        -- therefore its already-verified checksum is the canonical checksum.
        -- Keep the complete input comparison: field equality alone would admit
        -- noncanonical length framing, even with a valid prefix checksum.
        ensure (eqString input (Separate.pack (snoc (interfaceFields iface) checksum)))
          "noncanonical crate metadata";
        Right iface
      };
      _ -> Left "unsupported or malformed crate metadata (expected MLFCI-5)"
    }
  };
  interfacePrefix :: [] String -> [] String;
  interfacePrefix fields =
    case fields of {
      [] -> [];
      (:) a [] -> [];
      (:) a rest -> (:) a (interfacePrefix rest)
    };
  encodeFragment fragment =
    Separate.pairEncoding
      ((,) (Separate.encodeInterface (Separate.objectInterface fragment))
         (Separate.encodeObject fragment));
  -- Hash the same length-framed bytes without retaining one concatenated copy
  -- of every checked fragment and its datatype context.
  fingerprintPartFrom :: String -> Int -> Int -> Int -> (,) Int Int;
  fingerprintPartFrom text index a b =
    if (index == stringLength text)
    then (,) a b
    else let {
           code = stringCodeAt text index
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (fingerprintPartFrom text (index + 1) nextA nextB));
  fragmentFingerprintFrom :: [] Separate.UnitObject -> Int -> Int -> String;
  fragmentFingerprintFrom fragments a b =
    case fragments of {
      [] -> (showInt a ++ ("-" ++ showInt b));
      (:) fragment rest ->
        let {
          text = encodeFragment fragment
        } in
        case fingerprintPartFrom (showInt (stringLength text) ++ ":") 0 a b of {
          (,) prefixA prefixB ->
            case fingerprintPartFrom text 0 prefixA prefixB of {
              (,) nextA nextB -> seq nextA (seq nextB (fragmentFingerprintFrom rest nextA nextB))
            }
        }
    };
  legacyFragmentFingerprint fragments = fragmentFingerprintFrom fragments 0 1;
  -- Datatype contexts occur in thousands of SCC headers and payloads. Store
  -- each canonical declaration once, retaining separate ordered references for
  -- the header and payload so inconsistent objects remain invalid.
  data PoolRecord = PoolRecord ([] String) ([] String) String;
  typePoolText :: DataDecl -> [] ((,) DataDecl String) -> Maybe String;
  typePoolText declaration entries =
    case entries of {
      [] -> Nothing;
      (:) ((,) saved text) rest ->
        if Equality.eqDataDecl declaration saved then Just text else typePoolText declaration rest
    };
  rememberType :: Map String ([] ((,) DataDecl String)) ->
                  DataDecl -> (,) (Map String ([] ((,) DataDecl String))) String;
  rememberType pool declaration =
    let {
      name = D.datatypeName declaration
    } in
    let {
      entries = M.findWithDefault compareString [] name pool
    } in
    case typePoolText declaration entries of {
      Just text -> (,) pool text;
      Nothing ->
        let {
          text = D.prettyDeclaration declaration
        } in
        (,) (M.insert compareString name ((:) ((,) declaration text) entries) pool) text
    };
  rememberTypes :: Map String ([] ((,) DataDecl String)) ->
                   [] DataDecl -> (,) (Map String ([] ((,) DataDecl String))) ([] String);
  rememberTypes pool declarations =
    case declarations of {
      [] -> (,) pool [];
      (:) declaration rest ->
        case rememberType pool declaration of {
          (,) next text ->
            case rememberTypes next rest of {
              (,) final texts -> (,) final ((:) text texts)
            }
        }
    };
  poolRecords :: Map String ([] ((,) DataDecl String)) ->
                 [] Separate.UnitObject ->
                 [] PoolRecord ->
                 (,) (Map String ([] ((,) DataDecl String))) ([] PoolRecord);
  poolRecords pool fragments done =
    case fragments of {
      [] -> (,) pool (reverse done);
      (:) fragment rest ->
        case rememberTypes pool (Separate.unitData (Separate.objectInterface fragment)) of {
          (,) afterHeader header ->
            case rememberTypes afterHeader (Separate.objectContext fragment) of {
              (,) afterBody body ->
                poolRecords afterBody rest
                  ((:) (PoolRecord header body (Separate.encodeContextualObject fragment)) done)
            }
        }
    };
  encodePoolRecord :: Map String Int -> PoolRecord -> String;
  encodePoolRecord numbers (PoolRecord header body contents) =
    let {
      references =
        \texts -> Separate.pack (map (\text -> showInt (M.get compareString text numbers)) texts)
    } in
    Separate.pack ((:) (references header) ((:) (references body) ((:) contents [])));
  encodePooledPayload :: [] Separate.UnitObject -> String;
  encodePooledPayload fragments =
    case poolRecords M.empty fragments [] of {
      (,) inventory records ->
        let {
          declarations =
            Set.toList (Set.fromList compareString (concatMap (map snd) (M.elems inventory)))
        } in
        let {
          numbers = M.fromList compareString (zip declarations (range 0 (length declarations - 1)))
        } in
        Separate.pack
          ((:) (Separate.pack declarations)
             ((:) (Separate.pack (map (encodePoolRecord numbers) records)) []))
    };
  fragmentFingerprint fragments = Separate.fingerprint (encodePooledPayload fragments);
  objectFingerprint object =
    case object of {
      CrateObject _ fragments -> fragmentFingerprint fragments;
      LegacyCrateObject _ fragments -> legacyFragmentFingerprint fragments
    };
  withObjectFingerprint (CrateInterface n deps modules exports imports ds cs instances lowered bindings entry _ protection) digest =
    CrateInterface n deps modules exports imports ds cs instances lowered bindings entry digest protection;
  -- Pair only the finalized immutable fragments with their exact pooled text.
  -- Callers needing both the checksum and final object bytes can share this
  -- computation; ordinary object callers retain the same lazy interface.
  makeObjectWithPayload :: CrateInterface -> [] Separate.UnitObject -> (,) CrateObject String;
  makeObjectWithPayload iface fragments =
    let {
      payload = encodePooledPayload fragments
    } in
    (,) (CrateObject (withObjectFingerprint iface (Separate.fingerprint payload)) fragments)
      payload;
  makeObject iface fragments = fst (makeObjectWithPayload iface fragments);
  -- Prelude has one shared crate identity even when several independent leaf
  -- crates use it. Its bootstrap object is translated once; user crates still
  -- compile their own declarations through the ordinary SCC query pipeline.
  builtinPrelude =
    do {
      let {
        identity = builtinCrateIdentity
      };
      resolution <-
        Modules.resolveCrate NoImplicitPrelude M.empty (definitionName identity)
          ((:) Modules.preludeSource ((:) Modules.primitiveSource []));
      let {
        modules = Modules.resolvedCrateModules resolution
      };
      sourceData <- D.canonicalSourceDeclarations []
        (concatMap (\r -> Modules.renamedDatatypes (Modules.resolvedContents r)) modules);
      classes <- Classes.canonicalSourceClasses Set.empty sourceData []
        (concatMap (\r -> Modules.renamedClasses (Modules.resolvedContents r)) modules);
      let {
        values = concatMap (\r -> Modules.renamedValues (Modules.resolvedContents r)) modules
      };
      instances <-
        traverseEither
          (\((,) owner inst) ->
             do {
               closed <- Separate.closeInstance values inst;
               Right ((,) (instanceName identity owner inst) closed)
             })
          (Modules.resolvedCrateInstances resolution);
      body <- Surface.bindValues values (SConstructor "()");
      let { protectionConfig = Just ((,) M.empty (map fst instances)) };
      protection <- Classes.withValidatedClasses protectionConfig Set.empty M.empty Nothing
        sourceData classes (map snd instances) body
        (\base declarations -> do {
          inventory <- Classes.prepareClassesBody protectionConfig Set.empty M.empty Nothing
            sourceData (map snd instances) base declarations;
          Fresh.freshLift (Classes.inventorySourceProtection inventory instances values)
        });
      lowered <-
        Classes.lowerSeparateClasses M.empty (map fst instances)
          (SClassProgram sourceData classes (map snd instances) body);
      compiled <- mapLeft Compiler.prettyError (Compiler.finishCompilation lowered);
      let {
        term = Compiler.compiledTerm compiled
      };
      let {
        datatypes =
          case term of {
            XWithData ds _ -> ds;
            _ -> []
          }
      };
      let {
        implementation =
          case term of {
            XWithData _ b -> b;
            b -> b
          }
      };
      dataEnv <- D.validateDeclarations datatypes;
      actualBindings <- Separate.collectBindings dataEnv (XEnv M.empty M.empty) implementation;
      let {
        bindings =
          Separate.sortBindings
            (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) actualBindings)
      };
      bindingProtection <- traverseEither
        (\((,) name _) -> case M.lookup compareString name protection of {
          Just flag -> Right ((,) name flag);
          Nothing -> Left ("builtin binding lacks source protection provenance: " ++ name)
        }) bindings;
      exports <-
        traverseEither
          (\r ->
             mapEither
               (\scope ->
                  (,) (Modules.moduleIdentity (Modules.resolvedSource r))
                    (Set.toList (Modules.visible scope)))
               (Modules.resolvedExports NoImplicitPrelude r))
          modules;
      let {
        fragmentInterface =
          Separate.UnitInterface "Bootstrap.BuiltinPrelude" [] [] datatypes [] [] bindings
            (Separate.fingerprint (Pretty.prettyTerm term))
      };
      let {
        iface =
          CrateInterface identity [] ((:) "Prelude" ((:) "MLF.Primitive" [])) exports
            (map (\((,) name reach) -> (,) name (Set.toList reach))
               (M.toList (Modules.resolvedCrateReach resolution)))
            sourceData
            classes
            (map (\((,) n inst) -> (,) n (Separate.stripInstance inst)) instances)
            datatypes
            bindings
            ""
            "pending"
            bindingProtection
      };
      let {
        object = makeObject iface ((:) (Separate.UnitObject fragmentInterface term) [])
      };
      validateInterface (objectInterface object);
      Right object
    };
  -- The supplied interface text must be the encoding of this immutable iface.
  -- This helper shares bytes, not a digest inferred from different text.
  encodePooledObject :: CrateInterface -> String -> String -> String;
  encodePooledObject iface interfaceText payload =
    Separate.pack
      ((:) "MLFCO-2"
         ((:) (crateId iface)
            ((:) (Separate.fingerprint interfaceText) ((:) payload []))));
  encodeObjectWithInterface :: CrateObject -> String -> String;
  encodeObjectWithInterface object interfaceText =
    case object of {
      CrateObject iface fragments ->
        encodePooledObject iface interfaceText (encodePooledPayload fragments);
      LegacyCrateObject iface fragments ->
        Separate.pack
          ((:) "MLFCO-1"
             ((:) (crateId iface)
                ((:) (Separate.fingerprint interfaceText)
                   ((:) (Separate.pack (map encodeFragment fragments)) []))))
    };
  encodeObject object = encodeObjectWithInterface object (encodeInterface (objectInterface object));
  -- Canonical framing can be checked at the input offsets. It does not require
  -- serializing a second copy of the complete implementation object.
  canonicalFieldFrom :: String -> Int -> Either String ((,) String Int);
  canonicalFieldFrom text start =
    do {
      let {
        end = Separate.digitEnd text start
      };
      ensure
        ((end > start) &&
         (((end - start) <= 9) && ((end < stringLength text) && (stringCodeAt text end == 58))))
        "malformed crate object framing";
      ensure (((end - start) == 1) || (stringCodeAt text start /= 48))
        "noncanonical crate object framing";
      let {
        count = readInt (stringSlice text start (end - start))
      };
      ensure (count <= ((stringLength text - end) - 1)) "truncated crate object";
      Right ((,) (stringSlice text (end + 1) count) ((end + 1) + count))
    };
  canonicalFieldsFrom :: String -> Int -> Either String ([] String);
  canonicalFieldsFrom text start =
    if (start == stringLength text)
    then Right []
    else do {
           boundValueShared31 <- canonicalFieldFrom text start;
           case boundValueShared31 of {
             (,) field next ->
               do {
                 rest <- canonicalFieldsFrom text next;
                 Right ((:) field rest)
               }
           }
         };
  canonicalFields text = canonicalFieldsFrom text 0;
  decodeFragment text =
    do {
      fields <- canonicalFields text;
      boundValueShared32 <-
        case fields of {
          (:) metadata ((:) body []) -> Right ((,) metadata body);
          _ -> Left "malformed crate fragment"
        };
      case boundValueShared32 of {
        (,) metadata body ->
          do {
            iface <- Separate.decodeInterface metadata;
            fragment <- Separate.decodeObject iface body;
            ensure (eqString text (encodeFragment fragment)) "noncanonical crate fragment";
            Right fragment
          }
      }
    };
  -- Repeated contexts share canonical declaration nodes. The interface and
  -- independently checked payload retain their own declaration lists; sharing
  -- replaces a node only after its canonical layout agrees with the pool.
  poolDeclarations :: Map String ((,) String DataDecl) ->
                      [] DataDecl ->
                      Either String ((,) (Map String ((,) String DataDecl)) ([] DataDecl));
  poolDeclarations pool declarations =
    case declarations of {
      [] -> Right ((,) pool []);
      (:) declaration rest ->
        do {
          let {
            name = D.datatypeName declaration
          };
          let {
            encoded = D.prettyDeclaration declaration
          };
          boundValueShared34 <-
            case M.lookup compareString name pool of {
              Nothing ->
                Right
                  ((,) (M.insert compareString name ((,) encoded declaration) pool) declaration);
              Just ((,) expected shared) ->
                do {
                  ensure (eqString encoded expected)
                    ("inconsistent crate datatype context: " ++ name);
                  Right ((,) pool shared)
                }
            };
          case boundValueShared34 of {
            (,) next shared ->
              do {
                boundValueShared33 <- poolDeclarations next rest;
                case boundValueShared33 of {
                  (,) final pooled ->
                    do {
                      Right ((,) final ((:) shared pooled))
                    }
                }
              }
          }
        }
    };
  poolFragment pool fragment =
    do {
      let {
        iface = Separate.objectInterface fragment
      };
      boundValueShared37 <- poolDeclarations pool (Separate.unitData iface);
      case boundValueShared37 of {
        (,) afterHeader declarations ->
          do {
            boundValueShared36 <-
              case Separate.objectTerm fragment of {
                XWithData context body ->
                  do {
                    boundValueShared35 <- poolDeclarations afterHeader context;
                    case boundValueShared35 of {
                      (,) afterBody shared ->
                        do {
                          Right ((,) afterBody (XWithData shared body))
                        }
                    }
                  };
                term -> Right ((,) afterHeader term)
              };
            case boundValueShared36 of {
              (,) final term ->
                do {
                  let {
                    shared =
                      Separate.UnitInterface (Separate.unitName iface)
                        (Separate.unitDependencies iface)
                        (Separate.unitExports iface)
                        declarations
                        (Separate.unitClasses iface)
                        (Separate.unitInstances iface)
                        (Separate.unitBindings iface)
                        (Separate.unitObjectFingerprint iface)
                  };
                  Right ((,) final (Separate.UnitObject shared term))
                }
            }
          }
      }
    };
  decodeFragmentsFrom :: String ->
                         Int ->
                         Map String ((,) String DataDecl) ->
                         [] Separate.UnitObject -> Either String ([] Separate.UnitObject);
  decodeFragmentsFrom payload start pool done =
    if (start == stringLength payload)
    then Right (reverse done)
    else do {
           boundValueShared39 <- canonicalFieldFrom payload start;
           case boundValueShared39 of {
             (,) text next ->
               do {
                 decoded <- decodeFragment text;
                 boundValueShared38 <- poolFragment pool decoded;
                 case boundValueShared38 of {
                   (,) pooled fragment ->
                     do {
                       decodeFragmentsFrom payload next pooled ((:) fragment done)
                     }
                 }
               }
           }
         };
  decodeTypePool :: String -> Either String (Map Int DataDecl);
  decodeTypePool input =
    do {
      texts <- canonicalFields input;
      ensure (eqList eqString texts (sortStrings texts)) "noncanonical crate datatype pool order";
      source <-
        Parser.parseMetadataModule "<crate datatype pool>"
          ("module CrateDataPool where {\n" ++ (unlines texts ++ "\n}"));
      ensure
        (null (Modules.sourceValues source) &&
         (null (Modules.sourceImports source) &&
          (null (Modules.sourceClasses source) && null (Modules.sourceInstances source))))
        "crate datatype pool contains executable declarations";
      let {
        declarations = Modules.sourceDatatypes source
      };
      ensure (eqList eqString texts (map D.prettyDeclaration declarations))
        "noncanonical crate datatype pool declaration";
      uniqueNames "pooled datatype" (map D.datatypeName declarations);
      Right (M.fromList compareInt (zip (range 0 (length declarations - 1)) declarations))
    };
  decodeTypeReferences :: Map Int DataDecl -> String -> Either String ([] DataDecl);
  decodeTypeReferences pool input =
    do {
      references <- canonicalFields input;
      traverseEither
        (\reference ->
           do {
             ensure
               ((stringLength reference > 0) &&
                ((stringLength reference <= 9) &&
                 (Separate.digitEnd reference 0 == stringLength reference)))
               "invalid crate datatype pool reference";
             let {
               index = readInt reference
             };
             ensure (eqString reference (showInt index))
               "noncanonical crate datatype pool reference";
             case M.lookup compareInt index pool of {
               Nothing -> Left "crate datatype pool reference is out of bounds";
               Just declaration -> Right declaration
             }
           })
        references
    };
  datatypePart :: DataDecl -> (,) String ((,,,) Int Int Int Int);
  datatypePart declaration =
    let {
      text = D.prettyDeclaration declaration
    } in
    (,) text (Separate.fingerprintPart (text ++ "\n"));
  contextState :: Map String ((,) String ((,,,) Int Int Int Int)) -> [] DataDecl -> (,) Int Int;
  contextState parts declarations =
    foldlStrict
      (\state declaration ->
         Separate.fingerprintAppend state
           (snd (M.get compareString (D.datatypeName declaration) parts)))
      ((,) 0 1)
      declarations;
  decodePooledFragments :: Map Int DataDecl ->
                           Map String ((,) String ((,,,) Int Int Int Int)) ->
                           String ->
                           Int ->
                           [] Separate.UnitObject -> Either String ([] Separate.UnitObject);
  decodePooledFragments pool parts payload start done =
    if (start == stringLength payload)
    then Right (reverse done)
    else do {
           boundValueShared40 <- canonicalFieldFrom payload start;
           case boundValueShared40 of {
             (,) record next ->
               do {
                 fields <- canonicalFields record;
                 case fields of {
                   (:) header ((:) body ((:) contents [])) ->
                     do {
                       headerData <- decodeTypeReferences pool header;
                       bodyData <- decodeTypeReferences pool body;
                       fragment <-
                         Separate.decodeContextualObjectAfter (contextState parts bodyData)
                           headerData
                           bodyData
                           contents;
                       decodePooledFragments pool parts payload next ((:) fragment done)
                     };
                   _ -> Left "malformed pooled crate inference fragment"
                 }
               }
           }
         };
  decodePooledPayload :: String -> Either String ([] Separate.UnitObject);
  decodePooledPayload payload =
    do {
      fields <- canonicalFields payload;
      case fields of {
        (:) declarations ((:) bodies []) ->
          do {
            pool <- decodeTypePool declarations;
            let {
              parts =
                M.fromList compareString
                  (map
                     (\declaration -> (,) (D.datatypeName declaration) (datatypePart declaration))
                     (M.elems pool))
            };
            fragments <- decodePooledFragments pool parts bodies 0 [];
            ensure (eqString payload (encodePooledPayload fragments))
              "noncanonical pooled crate object";
            Right fragments
          };
        _ -> Left "malformed pooled crate object payload"
      }
    };
  decodeObjectFields iface fields =
    do {
      let {
        matchValueShared42 = fields
      } in
      case matchValueShared42 of {
        (:) matchValueShared43 matchValueShared44 ->
          if MLF.Primitive.eqString matchValueShared43 "MLFCO-2"
          then case matchValueShared44 of {
                 (:) matchValueShared51 matchValueShared52 ->
                   case matchValueShared52 of {
                     (:) matchValueShared53 matchValueShared54 ->
                       case matchValueShared54 of {
                         (:) matchValueShared55 matchValueShared56 ->
                           case matchValueShared56 of {
                             [] ->
                               let {
                                 identity = matchValueShared51
                               } in
                               let {
                                 metadataHash = matchValueShared53
                               } in
                               let {
                                 payload = matchValueShared55
                               } in
                               do {
                                 ensure (eqString identity (crateId iface))
                                   "crate object identity mismatch";
                                 ensure
                                   (eqString metadataHash
                                      (Separate.fingerprint (encodeInterface iface)))
                                   "crate object metadata mismatch";
                                 ensure
                                   (eqString (Separate.fingerprint payload)
                                      (crateObjectFingerprint iface))
                                   "crate object checksum mismatch";
                                 fragments <- decodePooledPayload payload;
                                 Right (CrateObject iface fragments)
                               };
                             _ ->
                               Left
                                 "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                           };
                         _ ->
                           Left
                             "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                       };
                     _ -> Left "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                   };
                 _ -> Left "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
               }
          else if MLF.Primitive.eqString matchValueShared43 "MLFCO-1"
               then case matchValueShared44 of {
                      (:) matchValueShared45 matchValueShared46 ->
                        case matchValueShared46 of {
                          (:) matchValueShared47 matchValueShared48 ->
                            case matchValueShared48 of {
                              (:) matchValueShared49 matchValueShared50 ->
                                case matchValueShared50 of {
                                  [] ->
                                    let {
                                      identity = matchValueShared45
                                    } in
                                    let {
                                      metadataHash = matchValueShared47
                                    } in
                                    let {
                                      payload = matchValueShared49
                                    } in
                                    do {
                                      ensure (eqString identity (crateId iface))
                                        "crate object identity mismatch";
                                      ensure
                                        (eqString metadataHash
                                           (Separate.fingerprint (encodeInterface iface)))
                                        "crate object metadata mismatch";
                                      ensure
                                        (eqString (Separate.fingerprint payload)
                                           (crateObjectFingerprint iface))
                                        "crate object checksum mismatch";
                                      boundValueShared41 <-
                                        poolDeclarations M.empty (crateLoweredData iface);
                                      case boundValueShared41 of {
                                        (,) pool _ ->
                                          do {
                                            fragments <- decodeFragmentsFrom payload 0 pool [];
                                            Right (LegacyCrateObject iface fragments)
                                          }
                                      }
                                    };
                                  _ ->
                                    Left
                                      "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                                };
                              _ ->
                                Left
                                  "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                            };
                          _ ->
                            Left
                              "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                        };
                      _ ->
                        Left "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
                    }
               else Left "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)";
        _ -> Left "unsupported or malformed crate object (expected MLFCO-2 or MLFCO-1)"
      }
    };
  decodeObject iface input = bindEither (canonicalFields input) (decodeObjectFields iface);
  dependencyId ((,,) n _ _) = n;
  dependencyPath ((,,) _ path _) = path;
  dependencySemantic ((,,) _ _ semantic) = semantic;
  interfaceMap interfaces = M.fromList compareString (map (\i -> (,) (crateId i) i) interfaces);
  dependencyClosure :: Map String CrateInterface ->
                       [] String ->
                       [] CrateInterface -> [] String -> Either String ([] CrateInterface);
  dependencyClosure interfaces trail done pending =
    case pending of {
      [] -> Right done;
      (:) n rest ->
        if elem eqString n trail
        then Left ("cyclic crate dependencies: " ++ intercalate " -> " (snoc trail n))
        else if any (\i -> eqString n (crateId i)) done
             then dependencyClosure interfaces trail done rest
             else case M.lookup compareString n interfaces of {
                    Nothing -> Left ("missing crate metadata: " ++ n);
                    Just iface ->
                      do {
                        earlier <-
                          dependencyClosure interfaces (snoc trail n) done
                            (map dependencyId (crateDependencies iface));
                        dependencyClosure interfaces trail (snoc earlier iface) rest
                      }
                  }
    };
  -- Source-free relinking must retain the namespace/instance contract under
  -- which this crate was resolved, including explicit constructor/type
  -- imports which do not become term parameters. Body and private value
  -- changes are excluded from this semantic fingerprint. A fresh consumer
  -- can publish updated dependency metadata while reusing its SCC queries.
  validateDependencies interfaces iface =
    traverseEither
      (\dependency ->
         case M.lookup compareString (dependencyId dependency) interfaces of {
           Nothing -> Left ("missing crate dependency: " ++ dependencyId dependency);
           Just actual ->
             do {
               ensure (eqString (crateId actual) (dependencyId dependency))
                 "crate dependency identity mismatch";
               ensure (eqString (dependencySemantic dependency) (semanticFingerprint actual))
                 ("stale crate dependency interface: " ++
                  (crateId iface ++
                   (" requires a different " ++
                    (dependencyId dependency ++ ("; recompile " ++ crateId iface)))))
             }
         })
      (crateDependencies iface);
  validateExportBoundary interfaces iface =
    do {
      let {
        dependencies =
          catMaybes
            (map (\d -> M.lookup compareString (dependencyId d) interfaces)
               (crateDependencies iface))
      };
      let {
        accessible = concatMap (\i -> concatMap snd (crateExports i)) dependencies
      };
      traverseEither
        (\entity ->
           ensure
             (isPrimitiveEntity entity ||
              (elem eqString (Modules.owner entity) (crateModules iface) ||
               any (\e -> (Modules.compareEntity e entity == 0)) accessible))
             ("crate reexports an entity outside its dependency boundary: " ++
              Modules.label entity))
        (concatMap snd (crateExports iface))
    };
  -- Recreate dictionary layouts from source headers, independently of object
  -- text. A forged source signature cannot authorize an unrelated nominal ABI.
  validateLayouts interfaces =
    do {
      boundValueShared57 <-
        Classes.lowerSeparateClasses M.empty
          (concatMap (\i -> map fst (crateInstances i)) interfaces)
          (SClassProgram (concatMap crateData interfaces) (concatMap crateClasses interfaces)
             (concatMap (\i -> map snd (crateInstances i)) interfaces)
             (SConstructor "()"));
      case boundValueShared57 of {
        (,) program _ ->
          do {
            expected <-
              case program of {
                SProgram ds _ -> Right ds;
                _ -> Left "invalid crate class metadata"
              };
            let {
              recorded = concatMap crateLoweredData interfaces
            };
            ensure
              (eqList eqString (sortStrings (map D.prettyDeclaration expected))
                 (sortStrings (map D.prettyDeclaration recorded)))
              "crate lowered datatype metadata mismatch";
            D.validateDeclarations recorded
          }
      }
    };
  sameSchemes actual expected =
    eqList Separate.sameSignature (Separate.sortBindings actual) (Separate.sortBindings expected);
  sameDeclarations actual expected =
    eqList eqString (sortStrings (map D.prettyDeclaration actual))
      (sortStrings (map D.prettyDeclaration expected));
  data FragmentState =
    FragmentState Int (Map String ((,) XName XType)) ([] XTerm) ([] DataDecl) (Set String);
  fragmentBindings (FragmentState _ available _ _ _) = available;
  fragmentSerial (FragmentState serial _ _ _ _) = serial;
  fragmentBodies (FragmentState _ _ bodies _ _) = bodies;
  fragmentData (FragmentState _ _ _ ds _) = ds;
  -- Reuse only an opaque successful independent check. Raw fragments still check here.
  linkFragment allowedLayouts allowedSymbols ownSchemes (FragmentState serial available bodies allData groups) fragment =
    do {
      let {
        recorded = Separate.objectInterface fragment
      };
      ensure (not (Set.member compareString (Separate.unitName recorded) groups))
        "duplicate crate inference fragment";
      ensure
        (null (Separate.unitClasses recorded) &&
         (null (Separate.unitInstances recorded) && null (Separate.unitExports recorded)))
        "inference fragment contains source visibility metadata";
      checked <- Separate.objectChecked fragment;
      boundValueShared59 <- Right (Separate.freshCheckedObject serial checked);
      case boundValueShared59 of {
        (,,) next fresh checkedBindings ->
          do {
            let {
              extracted =
                case fresh of {
                  XWithData ds b -> (,) ds b;
                  term -> (,) [] term
                }
            };
            let {
              ds = fst extracted
            };
            ensure (sameDeclarations ds (Separate.unitData recorded))
              "inference fragment datatype context mismatch";
            traverseEither
              (\declaration ->
                 case M.lookup compareString (D.datatypeName declaration) allowedLayouts of {
                   Nothing ->
                     Left
                       ("inference fragment has an undeclared datatype: " ++
                        D.datatypeName declaration);
                   Just actual ->
                     ensure (eqString (D.prettyDeclaration declaration) (fst actual))
                       ("inference fragment datatype layout mismatch: " ++
                        D.datatypeName declaration)
                 })
              ds;
            ensure
              (eqString
                 (Separate.fingerprintAfter
                    (contextState allowedLayouts (Separate.objectContext fragment))
                    (Pretty.prettyTerm (Separate.objectBody fragment)))
                 (Separate.unitObjectFingerprint recorded))
              "inference fragment checksum mismatch";
            boundValueShared58 <- Right (Separate.splitParameters (snd extracted));
            case boundValueShared58 of {
              (,) parameters implementation ->
                do {
                  uniqueNames "fragment parameter" (map (\p -> X.nameHint (fst p)) parameters);
                  ensure
                    (all (\p -> Set.member compareString (X.nameHint (fst p)) allowedSymbols)
                       parameters)
                    "crate fragment imports a symbol outside its dependency boundary";
                  replacements <-
                    traverseEither
                      (\((,) n ty) ->
                         case M.lookup compareString (X.nameHint n) available of {
                           Nothing -> Left ("unresolved crate symbol: " ++ X.nameHint n);
                           Just ((,) actual expected) ->
                             do {
                               ensure (T.alphaEq ty expected)
                                 ("crate import scheme mismatch: " ++ X.nameHint n);
                               Right ((,) n actual)
                             }
                         })
                      parameters;
                  D.validateDeclarations ds;
                  own <- checkedBindings;
                  let {
                    actual = map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) own
                  };
                  ensure (sameSchemes actual (Separate.unitBindings recorded))
                    "crate fragment binding scheme mismatch";
                  traverseEither
                    (\((,) n ty) ->
                       case M.lookup compareString n ownSchemes of {
                         Nothing -> Left ("fragment binding is not owned by crate: " ++ n);
                         Just expected ->
                           ensure (T.alphaEq ty expected)
                             ("crate object binding scheme mismatch: " ++ n)
                       })
                    actual;
                  uniqueNames "fragment binding" (map fst actual);
                  ensure (all (\((,) n _) -> not (M.member compareString n available)) actual)
                    "duplicate crate symbol";
                  let {
                    substitution = M.fromList X.compareName replacements
                  };
                  let {
                    linked =
                      Separate.mapTerm (\n -> M.findWithDefault X.compareName n n substitution)
                        (\a -> a)
                        implementation
                  };
                  combined <- foldEither Separate.mergeDeclaration allData ds;
                  let {
                    newBindings =
                      M.fromList compareString
                        (map (\((,) n ty) -> (,) (X.nameHint n) ((,) n ty)) own)
                  };
                  Right
                    (FragmentState next (M.union compareString newBindings available)
                       ((:) linked bodies)
                       combined
                       (Set.insert compareString (Separate.unitName recorded) groups))
                }
            }
          }
      }
    };
  linkCrate interfaces allowedLayouts state object =
    do {
      let {
        iface = objectInterface object
      };
      let {
        fragments = objectFragments object
      };
      validateInterface iface;
      ensure (eqString (objectFingerprint object) (crateObjectFingerprint iface))
        "crate fragment inventory checksum mismatch";
      dependencies <-
        dependencyClosure interfaces ((:) (crateId iface) []) []
          (map dependencyId (crateDependencies iface));
      let {
        allowedSymbols =
          Set.fromList compareString (map fst (concatMap crateBindings ((:) iface dependencies)))
      };
      let {
        before = Set.fromList compareString (M.keys (fragmentBindings state))
      };
      let {
        ownSchemes = M.fromList compareString (crateBindings iface)
      };
      after <- foldEither (linkFragment allowedLayouts allowedSymbols ownSchemes) state fragments;
      let {
        own =
          filter (\n -> not (Set.member compareString n before)) (M.keys (fragmentBindings after))
      };
      ensure (eqList eqString (sortStrings own) (sortStrings (map fst (crateBindings iface))))
        "crate object declaration inventory mismatch";
      Right after
    };
  entrySignatures entry bindings =
    filter
      (\((,) name _) ->
         (eqString name entry ||
          (startsWith "select_" name || (startsWith "super_" name || startsWith "instance_" name))))
      bindings;
  -- Entry inference instantiates one already checked value. Its closed
  -- implementation dependencies are linked above and need no fake source
  -- parameters here. Keep every generated selector/dictionary external so
  -- class translation cannot regenerate an existing support definition.
  linkEntry serial interfaces root available entry =
    if eqString entry ""
    then Right (XConstructor "()" [])
    else do {
           ensure (M.member compareString entry available) ("crate has no entry symbol: " ++ entry);
           let {
             classes = concatMap crateClasses interfaces
           };
           owner <- entryOwner root;
           let {
             reach =
               (:) owner
                 (M.findWithDefault compareString [] owner
                    (M.fromList compareString (crateImports root)))
           };
           instances <-
             mapEither concat
               (traverseEither
                  (\iface ->
                     traverseEither
                       (\entry ->
                          do {
                            moduleName <- instanceOwner iface (fst entry);
                            Right ((,) moduleName entry)
                          })
                       (crateInstances iface))
                  interfaces);
           let {
             visibleInstances =
               map snd (filter (\((,) moduleName _) -> elem eqString moduleName reach) instances)
           };
           let {
             dictionaries =
               M.fromList compareString
                 (map (\c -> (,) ("Dict_" ++ Classes.className c) (Classes.className c)) classes)
           };
           let {
             signatures =
               M.fromList compareString (entrySignatures entry (concatMap crateBindings interfaces))
           };
           let {
             externals =
               M.mapWithKey
                 (\n ty ->
                    Separate.sourceScheme
                      (if eqString (stringSlice n 0 7) "module_" then dictionaries else M.empty)
                      ty)
                 signatures
           };
           lowered <-
             Classes.lowerSeparateClasses externals (map fst visibleInstances)
               (SClassProgram (concatMap crateData interfaces) classes (map snd visibleInstances)
                  (SVar entry));
           compiled <- mapLeft Compiler.prettyError (Compiler.finishCompilation lowered);
           Separate.removeEntryParameters signatures available
             (snd (Separate.freshObject serial (Compiler.compiledTerm compiled)))
         };
  linkCheckedObjects objects root =
    do {
      uniqueNames "object identity" (map (\o -> crateId (objectInterface o)) objects);
      let {
        interfaces = map objectInterface objects
      };
      let {
        byName = interfaceMap interfaces
      };
      ordered <- dependencyClosure byName [] [] ((:) root []);
      traverseEither (validateDependencies byName) ordered;
      traverseEither (validateExportBoundary byName) ordered;
      dataEnv <- validateLayouts ordered;
      let {
        layouts =
          M.fromList compareString
            (map (\d -> (,) (D.datatypeName d) (datatypePart d))
               (concatMap crateLoweredData ordered))
      };
      let {
        objectMap =
          M.fromList compareString (map (\o -> (,) (crateId (objectInterface o)) o) objects)
      };
      state <-
        foldEither
          (\s i ->
             case M.lookup compareString (crateId i) objectMap of {
               Nothing -> Left "missing crate object";
               Just o -> linkCrate byName layouts s o
             })
          (FragmentState 0 M.empty [] [] Set.empty)
          ordered;
      let {
        rootInterface = M.findWithDefault compareString (panic "missing root crate") root byName
      };
      entry <-
        linkEntry (fragmentSerial state) ordered rootInterface (fragmentBindings state)
          (crateEntry rootInterface);
      body <-
        foldEither (\body declarations -> Separate.graft declarations body) entry
          (fragmentBodies state);
      Checked.check (XWithData (fragmentData state) body)
    };
  linkObjects objects root = mapEither Checked.term (linkCheckedObjects objects root);
  readInterface path =
    do {
      input <- Separate.readStrict path;
      ioReturn (mapLeft (\e -> (path ++ (": " ++ e))) (bindEither input decodeInterface))
    };
  readObject path iface =
    do {
      input <- Separate.readStrict path;
      ioReturn (mapLeft (\e -> (path ++ (": " ++ e))) (bindEither input (decodeObject iface)))
    };
  objectPath path = (stringSlice path 0 (stringLength path - 6) ++ ".mlfco");
  loadGraph :: [] String ->
               [] ((,) String CrateInterface) ->
               [] String -> IO (Either String ([] ((,) String CrateInterface)));
  loadGraph trail done paths =
    case paths of {
      [] -> ioReturn (Right done);
      (:) requested rest ->
        do {
          present <- fileExists requested;
          if not present
          then ioReturn (Left ("crate metadata does not exist: " ++ requested))
          else do {
                 path <- canonicalPath requested;
                 if elem eqString path trail
                 then ioReturn
                        (Left
                           ("cyclic crate metadata paths: " ++
                            intercalate " -> " (snoc trail path)))
                 else if any (\p -> eqString path (fst p)) done
                      then loadGraph trail done rest
                      else do {
                             read <- readInterface path;
                             case read of {
                               Left e -> ioReturn (Left e);
                               Right iface ->
                                 if any (\p -> eqString (crateId (snd p)) (crateId iface)) done
                                 then ioReturn
                                        (Left
                                           ("duplicate crate identity from different metadata paths: " ++
                                            crateId iface))
                                 else do {
                                        children <-
                                          loadGraph (snoc trail path) done
                                            (map dependencyPath (crateDependencies iface));
                                        case bindEither children
                                               (\xs ->
                                                  do {
                                                    validateDependencies (interfaceMap (map snd xs))
                                                      iface;
                                                    validateExportBoundary
                                                      (interfaceMap (map snd xs))
                                                      iface;
                                                    Right xs
                                                  }) of {
                                          Left e -> ioReturn (Left e);
                                          Right xs ->
                                            loadGraph trail (snoc xs ((,) path iface)) rest
                                        }
                                      }
                             }
                           }
               }
        }
    };
  loadInterfaces paths = loadGraph [] [] paths;
  linkCheckedFile path =
    do {
      loaded <- loadInterfaces ((:) path []);
      case loaded of {
        Left e -> ioReturn (Left e);
        Right interfaces ->
          do {
            objects <-
              mapM (\((,) metadata iface) -> readObject (objectPath metadata) iface) interfaces;
            ioReturn
              (bindEither (sequenceEither objects)
                 (\os ->
                    case reverse interfaces of {
                      [] -> Left "no root crate metadata";
                      (:) ((,) _ root) _ -> linkCheckedObjects os (crateId root)
                    }))
          }
      }
    };
  linkFile path =
    do {
      linked <- linkCheckedFile path;
      ioReturn (mapEither Checked.term linked)
    };
  writeObject prefix object =
    let {
      interfaceText = encodeInterface (objectInterface object)
    } in
    do {
      writeFile (prefix ++ ".mlfco") (encodeObjectWithInterface object interfaceText);
      writeFile (prefix ++ ".mlfci") interfaceText;
      ioReturn ()
    };
  -- Only the new-object producer passes the exact paired payload obtained from
  -- makeObjectWithPayload. Loaded/legacy objects keep the general writer; no
  -- inference result or independently supplied checksum licenses text reuse.
  writeObjectWithPayload :: String -> CrateObject -> String -> IO ();
  writeObjectWithPayload prefix object payload =
    let {
      interfaceText = encodeInterface (objectInterface object);
      objectText = case object of {
        CrateObject iface _ -> encodePooledObject iface interfaceText payload;
        LegacyCrateObject _ _ -> encodeObjectWithInterface object interfaceText
      }
    } in
    do {
      -- Keep the constructor case inside the lazy contents: filename checks
      -- must still precede demand of the object or its paired payload.
      writeFile (prefix ++ ".mlfco") objectText;
      writeFile (prefix ++ ".mlfci") interfaceText;
      ioReturn ()
    };
  showInterfaceFile path =
    do {
      read <- readInterface path;
      ioReturn (mapEither renderInterface read)
    };
  renderInterface iface =
    let {
      dependencies =
        map (\((,,) n p h) -> ("dependency " ++ (n ++ (" " ++ (p ++ (" " ++ h))))))
          (crateDependencies iface)
    } in
    let {
      modules =
        concatMap
          (\((,) n entities) ->
             (:) ("module " ++ n) (map (\e -> ("  export " ++ Modules.label e)) entities))
          (crateExports iface)
    } in
    unlines
      ((:) ("crate " ++ crateId iface)
         ((:) ("interface " ++ semanticFingerprint iface) (append dependencies modules)))
}
