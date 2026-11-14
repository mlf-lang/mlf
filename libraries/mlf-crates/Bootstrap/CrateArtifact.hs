-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CrateArtifact where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Fresh as Fresh;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.SourceEquality as Equality;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.QueryGraph as QueryGraph;
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
    LegacyCrateObject CrateInterface ([] Separate.UnitObject) |
    EnvelopeCrateObject Bool CrateInterface ([] Separate.UnitObject) |
    OpenCrateObject CrateInterface Open.Package;
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
  objectInterface (EnvelopeCrateObject _ i _) = i;
  objectInterface (OpenCrateObject i _) = i;
  objectFragments (CrateObject _ fs) = fs;
  objectFragments (LegacyCrateObject _ fs) = fs;
  objectFragments (EnvelopeCrateObject _ _ fs) = fs;
  objectFragments (OpenCrateObject _ _) = panic "open crate requires explicit fragment references";
  definitionName :: String -> Modules.Entity -> String;
  definitionName identity = definitionNameEncoded (Separate.encoded identity);
  ordinaryDefinitionName :: String -> Modules.Entity -> String;
  ordinaryDefinitionName identity = ordinaryDefinitionNameEncoded (Separate.encoded identity);
  -- Partial application shares the immutable crate prefix across its exports.
  -- The ordinary encoder and complete entity identity remain unchanged.
  definitionNameEncoded :: String -> Modules.Entity -> String;
  definitionNameEncoded encodedIdentity entity =
    case Separate.managedBuiltinName entity of {
      Just name -> name;
      Nothing -> ordinaryDefinitionNameEncoded encodedIdentity entity
    };
  ordinaryDefinitionNameEncoded :: String -> Modules.Entity -> String;
  ordinaryDefinitionNameEncoded encodedIdentity entity =
    if (eqString (Modules.owner entity) "Prelude" || Modules.isRole Modules.BuiltinType entity)
    then Separate.stableName entity
    else ((if ((Modules.compareSpace (Modules.space entity) Modules.Types == 0) ||
               (case Modules.role entity of {
                  Modules.Constructor _ -> True;
                  _ -> False
                }))
           then "Module_"
           else "module_") ++
          (encodedIdentity ++
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
      publicNames = Set.fromList compareString (map (definitionNameEncoded (Separate.encoded (crateId iface))) exported)
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
  primitiveEntitySet :: Set Modules.Entity;
  primitiveEntitySet = Set.fromList Modules.compareEntity
    (append Modules.primitiveEntities Modules.sharedPrimitiveEntities);
  isPrimitiveEntity entity = Set.member Modules.compareEntity entity primitiveEntitySet;
  -- Independent interface readers have no resolver. Bind their stable keys
  -- once to interface-local slots and check the declaration role in that table.
  data TermExport = PublishedValue | PublishedMethod;
  data ExportTerms = ExportTerms (Map String ([] (V.Index Declaration)))
    (V.IndexVec Declaration TermExport);
  exportTerms iface = let {
    entries = append (map (\((,) n _) -> (,) n PublishedValue) (crateBindings iface))
      (concatMap (\klass -> map (\((,) n _) -> (,) n PublishedMethod) (Classes.classMethods klass)) (crateClasses iface));
    roles = V.fromList (map snd entries);
    slots = M.fromListWith compareString append (zipWith (\((,) n _) i -> (,) n [i]) entries (V.indices roles))
  } in ExportTerms slots roles;
  hasExportTerm (ExportTerms slots roles) key role = any
    (\i -> case (,) role (V.at roles i) of {
      (,) PublishedValue PublishedValue -> True; (,) PublishedMethod PublishedMethod -> True; _ -> False
    }) (M.findWithDefault compareString [] key slots);
  data ExportInventory = ExportInventory ExportTerms (Set String) (Set String) (Set String);
  exportInventory iface = ExportInventory (exportTerms iface)
    (Set.fromList compareString (map D.datatypeName (crateData iface)))
    (Set.fromList compareString (map Classes.className (crateClasses iface)))
    (Set.fromList compareString
       (concatMap (\d -> map D.constructorName (D.datatypeConstructors d)) (crateData iface)));
  validateOwnExport iface = validateOwnExportNamed (definitionName (crateId iface)) iface;
  validateOwnExportNamed nameOf iface (ExportInventory terms datatypes classes constructors) entity =
    if (isPrimitiveEntity entity || not (elem eqString (Modules.owner entity) (crateModules iface)))
    then Right ()
    else do {
           let {
             name = nameOf entity
           };
           let {
             declared =
               case Modules.role entity of {
                 Modules.Value -> hasExportTerm terms name PublishedValue;
                 Modules.Datatype -> Set.member compareString name datatypes;
                 Modules.Class -> Set.member compareString name classes;
                 Modules.Constructor _ -> Set.member compareString name constructors;
                 Modules.Method _ -> hasExportTerm terms name PublishedMethod;
                 _ -> False
               }
           };
           ensure declared ("crate exports an undeclared entity: " ++ Modules.label entity)
         };
  builtinCrateIdentity :: String;
  builtinCrateIdentity = "mlf:builtin-shared-haskell-v1:13";
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
      traverseEither (validateOwnExportNamed (definitionNameEncoded (Separate.encoded (crateId iface))) iface (exportInventory iface))
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
  -- Each summary is derived from this admission's actual object body. The
  -- unchanged canonical encoder remains the independent serialized authority.
  data FingerprintRecord = FingerprintRecord ([] String) ([] String)
    Separate.FingerprintEncoding Separate.FingerprintEncoding;
  fingerprintRecords pool textPool fragments done = case fragments of {
    [] -> (,) pool (reverse done);
    (:) fragment rest -> case rememberTypes pool (Separate.unitData (Separate.objectInterface fragment)) of {
      (,) afterHeader header -> case rememberTypes afterHeader (Separate.objectContext fragment) of {
        (,) afterBody body -> let {
          encodedPair = Separate.encodingChunks textPool
            (Pretty.termChunks 0 (Separate.objectBody fragment) []) Separate.encodingEmpty;
          encoded = snd encodedPair;
          iface = Separate.withInterfaceData (Separate.objectInterface fragment) []
            (Separate.encodingFingerprint encoded);
          headerEncoding = Separate.encodingInterface (fst encodedPair) iface;
          contents = Separate.encodingPack [Separate.encodingText "MLFF-2",
            snd headerEncoding, encoded]
        } in fingerprintRecords afterBody (fst headerEncoding) rest ((:) (FingerprintRecord header body contents encoded) done)
      }
    }
  };
  fingerprintPooled fragments = case fingerprintRecords M.empty M.empty fragments [] of {
    (,) inventory records -> let {
      declarations = Set.toList (Set.fromList compareString (concatMap (map snd) (M.elems inventory)));
      numbers = M.fromList compareString (zip declarations (range 0 (length declarations - 1)));
      references = \texts -> Separate.encodingText
        (Separate.pack (map (\text -> showInt (M.get compareString text numbers)) texts));
      encode = \(FingerprintRecord header body contents _) ->
        Separate.encodingPack [references header, references body, contents];
      encoded = Separate.encodingPack [Separate.encodingText (Separate.pack declarations),
        Separate.encodingPack (map encode records)]
    } in (,) (Separate.encodingFingerprint encoded)
      (map (\(FingerprintRecord _ _ _ body) -> body) records)
  };
  fragmentFingerprint fragments = Separate.fingerprint (encodePooledPayload fragments);
  objectFingerprint object =
    case object of {
      CrateObject _ fragments -> fragmentFingerprint fragments;
      LegacyCrateObject _ fragments -> legacyFragmentFingerprint fragments;
      EnvelopeCrateObject legacy _ fragments -> if legacy then legacyFragmentFingerprint fragments else fragmentFingerprint fragments;
      OpenCrateObject _ package -> Open.packageHash package
    };
  withObjectFingerprint (CrateInterface n deps modules exports imports ds cs instances lowered bindings entry _ protection) digest =
    CrateInterface n deps modules exports imports ds cs instances lowered bindings entry digest protection;
  -- Derive the binary object's checksum from exact canonical field summaries.
  -- Compatibility callers can still demand the pooled text independently.
  makeObjectWithPayload :: CrateInterface -> [] Separate.UnitObject -> (,) CrateObject String;
  makeObjectWithPayload iface fragments =
    (,) (CrateObject (withObjectFingerprint iface (fst (fingerprintPooled fragments))) fragments)
      (encodePooledPayload fragments);
  makeObject iface fragments = fst (makeObjectWithPayload iface fragments);
  -- Prelude has one shared crate identity even when several independent leaf
  -- crates use it. Its bootstrap object is translated once; user crates still
  -- compile their own declarations through the ordinary SCC query pipeline.
  declarationVariableReads source = let {
    child = declarationVariableReads;
    join = Set.unions X.compareName
  } in case source of {
    XVarTerm name -> Set.singleton name;
    XAbs _ _ body -> child body;
    XApp a b -> join [child a, child b];
    XTypeAbs _ _ body -> child body;
    XTypeApp body _ -> child body;
    XLet _ rhs body -> join [child rhs, child body];
    XLetRec definitions body -> join ((:) (child body)
      (map (\((,,) _ _ rhs) -> child rhs) definitions));
    XCase subject _ alternatives -> join ((:) (child subject)
      (map (\(XAlternative _ body) -> child body) alternatives));
    XWithData _ body -> child body;
    _ -> Set.empty
  };

 flattenDeclarationEntries :: Map XName XType -> XTerm -> Either String ([] ((,,) XName XType XTerm));
 flattenDeclarationEntries schemes term = case term of {
  XLet name rhs rest -> do {
   ty <- maybe (Left "missing actual scheme") Right (M.lookup X.compareName name schemes);
   tail <- flattenDeclarationEntries schemes rest;
   Right ((:) ((,,) name ty rhs) tail)
  };
  XLetRec entries rest -> mapEither (append entries) (flattenDeclarationEntries schemes rest);
  XConstructor "()" [] -> Right [];
  _ -> Left "unsupported checked builtin declaration spine"
 };
 splitClosedDeclarationObject original = do {
  let { iface = objectInterface original;
    originalLayouts = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (datatypePart d)) (crateLoweredData iface)) };
  linkCrate (interfaceMap [iface]) originalLayouts (FragmentState 0 M.empty [] [] Set.empty) original;
  old <- case objectFragments original of { [unit] -> Checked.check (Separate.objectTerm unit); _ -> Left "expected original one-fragment builtin" };
  bindings <- Checked.declarationBindings old;
  let { schemes = M.fromList X.compareName bindings;
    expression = Checked.term old;
    declarations = case expression of { XWithData ds _ -> ds; _ -> [] };
    body = case expression of { XWithData _ value -> value; value -> value } };
  entries <- flattenDeclarationEntries schemes body;
  let { names = M.fromList X.compareName (map (\((,,) n _ _) -> (,) n (X.nameHint n)) entries);
    keyed = M.fromList compareString (map (\entry@((,,) n _ _) -> (,) (X.nameHint n) entry) entries);
    deps = \rhs -> mapMaybe (\n -> M.lookup X.compareName n names) (Set.toList (declarationVariableReads rhs));
    groups = Dependency.components (map (\((,,) n _ rhs) -> (,) (X.nameHint n) (deps rhs)) entries) };
  units <- traverseEither (\((,) index keys) -> do {
   values <- traverseEither (\key -> maybe (Left "missing SCC key") Right (M.lookup compareString key keyed)) keys;
   let { own = Set.fromList X.compareName (map (\((,,) n _ _) -> n) values);
     refs = Set.unions X.compareName (map (\((,,) _ _ rhs) -> declarationVariableReads rhs) values);
     imports = filter (\n -> not (Set.member X.compareName n own) && M.member X.compareName n names) (Set.toList refs) };
   params <- traverseEither (\n -> mapEither ((,) n) (maybe (Left "missing imported scheme") Right (M.lookup X.compareName n schemes))) imports;
   let { term = XWithData declarations (foldr (\((,) n ty) rest -> XAbs n ty rest)
     (XLetRec values (XConstructor "()" [])) params) };
   Checked.check term;
   let { unit = Separate.UnitInterface ("MLF.Split.C" ++ Separate.encodedFrom (crateId iface) 0 ++ ".SCC" ++ showInt index) [] [] declarations [] []
     (map (\((,,) n ty _) -> (,) (X.nameHint n) (Separate.normalType ty)) values) (Separate.fingerprint (Pretty.prettyTerm term)) };
   Right (Separate.UnitObject unit term)
  }) (zip (range 0 (length groups - 1)) groups);
  let { object = makeObject iface units; actual = objectInterface object;
    layouts = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (datatypePart d)) declarations) };
  decodedInterface <- decodeInterface (encodeInterface actual);
  ensure (eqString (encodeInterface decodedInterface) (encodeInterface actual)) "split declaration interface changed on roundtrip";
  decoded <- decodeObject decodedInterface (encodeObject object);
  ensure (eqString (encodeObject decoded) (encodeObject object)) "split declaration object changed on roundtrip";
  linkCrate (interfaceMap [decodedInterface]) layouts (FragmentState 0 M.empty [] [] Set.empty) decoded;
  Right decoded
 };
  builtinPrelude =
    do {
      let {
        identity = builtinCrateIdentity
      };
      resolution <-
        Modules.resolveCrateDefinitions NoImplicitPrelude M.empty (definitionName identity)
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
      let { bindings = Modules.boundIn resolution modules; closeLocal = Surface.closeResolvedInstance (Surface.helperScope bindings) };
      instances <-
        traverseEither
          (\((,) owner inst) ->
             do {
               closed <- closeLocal inst;
               Right ((,) (instanceName identity owner (Modules.instanceValue resolution inst)) closed)
             })
          (Modules.resolvedInstanceRows resolution);
      body <- Surface.bindResolved bindings (SConstructor "()");
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
      splitClosedDeclarationObject object
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
                   ((:) (Separate.pack (map encodeFragment fragments)) []))));
      EnvelopeCrateObject legacy iface fragments -> encodeObjectWithInterface
        (if legacy then LegacyCrateObject iface fragments else CrateObject iface fragments) interfaceText;
      OpenCrateObject iface package -> Separate.pack ["MLFCO-OPEN-1",interfaceText,Open.packageHash package]
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
  decodeTypePool :: String -> Either String (IntMap DataDecl);
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
      Right (IM.fromList (zip (range 0 (length declarations - 1)) declarations))
    };
  decodeTypeReferences :: IntMap DataDecl -> String -> Either String ([] DataDecl);
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
             case IM.lookup index pool of {
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
  decodePooledFragments :: IntMap DataDecl ->
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
    let {
      decodeCarried pool parts payload start objectsDone recordsDone =
        if (start == stringLength payload)
        then Right ((,) (reverse objectsDone) (reverse recordsDone))
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
                           Separate.decodeContextualObjectAfterWithCanonical
                             (contextState parts bodyData)
                             headerData
                             bodyData
                             contents
                             (\fragment canonical ->
                                decodeCarried pool parts payload next
                                  ((:) fragment objectsDone)
                                  ((:) ((,) fragment canonical) recordsDone))
                         };
                       _ -> Left "malformed pooled crate inference fragment"
                     }
                   }
               }
             };
      poolCarried pool records done =
        case records of {
          [] -> (,) pool (reverse done);
          (:) ((,) fragment canonical) rest ->
            case rememberTypes pool (Separate.unitData (Separate.objectInterface fragment)) of {
              (,) afterHeader header ->
                case rememberTypes afterHeader (Separate.objectContext fragment) of {
                  (,) afterBody body ->
                    poolCarried afterBody rest
                      ((:) (PoolRecord header body canonical) done)
                }
            }
        };
      encodeCarried carriedRecords =
        case poolCarried M.empty carriedRecords [] of {
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
        }
    } in
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
                     (IM.elems pool))
            };
            decoded <- decodeCarried pool parts bodies 0 [] [];
            case decoded of {
              (,) fragments records ->
                do {
                  ensure (eqString payload (encodeCarried records))
                    "noncanonical pooled crate object";
                  Right fragments
                }
            }
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
  linkFragment allowedLayouts allowedSymbols ownSchemes state fragment =
    linkFragmentWithEncoding allowedLayouts allowedSymbols ownSchemes state ((,) fragment Nothing);
  linkFragmentWithEncoding allowedLayouts allowedSymbols ownSchemes state fragment =
    linkFragmentWithContexts (Checked.contextPool []) allowedLayouts allowedSymbols ownSchemes state fragment;
  linkFragmentWithContexts contexts allowedLayouts allowedSymbols ownSchemes state fragment =
    mapEither fst (linkFragmentWithSpine contexts allowedLayouts allowedSymbols ownSchemes state
      (Left "ordinary fragment linking has no composition receipt") fragment);
  linkFragmentWithSpine contexts allowedLayouts allowedSymbols ownSchemes (FragmentState serial available bodies allData groups) proof ((,) fragment encoded) =
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
      checked <- case fragment of {
        Separate.UnitObject _ term -> Checked.checkWithContexts contexts term;
        Separate.CheckedUnitObject _ checked -> Right checked
      };
      let { evidence = Checked.freshFragment serial checked };
      boundValueShared59 <- Right ((,,) (Checked.freshSerial evidence) (Checked.freshTerm evidence)
        (mapEither (map (\((,) n ty) -> (,) n (Separate.normalType ty))) (Checked.freshBindings evidence)));
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
                 (case encoded of {
                    Nothing -> Separate.fingerprintAfter
                      (contextState allowedLayouts (Separate.objectContext fragment))
                      (Pretty.prettyTerm (Separate.objectBody fragment));
                    Just summary -> Separate.encodingAfter
                      (contextState allowedLayouts (Separate.objectContext fragment)) summary
                  })
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
                  Checked.validateContext contexts ds;
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
                    nextProof = bindEither proof (\spine -> Checked.appendFreshSpine spine evidence);
                    ordinaryBody = Separate.mapTerm (\n -> M.findWithDefault X.compareName n n substitution)
                      (\a -> a) implementation;
                    linked = case nextProof of {
                      Left _ -> ordinaryBody;
                      Right spine -> case Checked.latestSpineBody spine of {
                        Nothing -> ordinaryBody;
                        Just body -> body
                      }
                    }
                  };
                  combined <- foldEither Separate.mergeDeclaration allData ds;
                  let {
                    newBindings =
                      M.fromList compareString
                        (map (\((,) n ty) -> (,) (X.nameHint n) ((,) n ty)) own)
                  };
                  Right ((,)
                    (FragmentState next (M.union compareString newBindings available)
                       ((:) linked bodies)
                       combined
                       (Set.insert compareString (Separate.unitName recorded) groups)) nextProof)
                }
            }
          }
      }
    };
  linkCrate interfaces allowedLayouts state object =
    mapEither fst (linkCrateWithSpine interfaces allowedLayouts
      ((,) state (Left "ordinary crate linking has no composition receipt")) object);
  linkCrateWithSpineV1 interfaces allowedLayouts ((,) state initialProof) object =
    do {
      let {
        iface = objectInterface object
      };
      let {
        fragments = objectFragments object
      };
      validateInterface iface;
      let { prepared = case object of {
        CrateObject _ _ -> let { pair = fingerprintPooled fragments }
          in (,) (fst pair) (zip fragments (map Just (snd pair)));
        LegacyCrateObject _ _ -> (,) (objectFingerprint object) (map (\fragment -> (,) fragment Nothing) fragments);
        EnvelopeCrateObject _ _ _ -> panic "crate envelope bounded link guard invariant";
        OpenCrateObject _ _ -> panic "open crate link dispatch invariant"
      } };
      ensure (eqString (fst prepared) (crateObjectFingerprint iface))
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
      let { contexts = Checked.contextPool (map Separate.objectContext fragments) };
      linked <- foldEither (\((,) current proof) fragment ->
        linkFragmentWithSpine contexts allowedLayouts allowedSymbols ownSchemes current proof fragment
      ) ((,) state initialProof) (snd prepared);
      let { after = fst linked };
      let {
        own =
          filter (\n -> not (Set.member compareString n before)) (M.keys (fragmentBindings after))
      };
      ensure (eqList eqString (sortStrings own) (sortStrings (map fst (crateBindings iface))))
        "crate object declaration inventory mismatch";
      Right ((,) after (snd linked))
    };
  selectFragmentClosure selected present fragments = do {
    result <- foldEither (\((,) needed chosen) pair -> let {
      fragment = fst pair;
      iface = Separate.objectInterface fragment;
      provided = map fst (Separate.unitBindings iface)
    } in if any (\key -> Set.member compareString key needed) provided then do {
      let { parameters = Separate.splitParameters (Separate.objectBody fragment) };
      let { dependencies = map (compose X.nameHint fst) (fst parameters);
        remaining = foldl (\keys key -> Set.delete compareString key keys) needed provided };
      Right ((,) (Set.union compareString remaining (Set.fromList compareString dependencies)) ((:) pair chosen))
    } else Right ((,) needed chosen)) ((,) (Set.fromList compareString selected) []) (reverse fragments);
    ensure (all (\key -> Set.member compareString key present) (Set.toList (fst result))) "selected crate symbols have unresolved dependencies";
    Right (snd result)
  };
  linkSelectedCrateWithSpineV1 selected interfaces allowedLayouts ((,) state initialProof) object =
    do {
      let {
        iface = objectInterface object
      };
      let {
        fragments = objectFragments object
      };
      validateInterface iface;
      let { prepared = case object of {
        CrateObject _ _ -> let { pair = fingerprintPooled fragments }
          in (,) (fst pair) (zip fragments (map Just (snd pair)));
        LegacyCrateObject _ _ -> (,) (objectFingerprint object) (map (\fragment -> (,) fragment Nothing) fragments);
        EnvelopeCrateObject _ _ _ -> panic "crate envelope bounded link guard invariant";
        OpenCrateObject _ _ -> panic "open crate link dispatch invariant"
      } };
      ensure (eqString (fst prepared) (crateObjectFingerprint iface))
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
      let { contexts = Checked.contextPool (map Separate.objectContext fragments) };
      uniqueNames "crate inference fragment" (map (compose Separate.unitName Separate.objectInterface) fragments);
      traverseEither (\fragment -> let { recorded = Separate.objectInterface fragment } in
        ensure (null (Separate.unitClasses recorded) && null (Separate.unitInstances recorded) && null (Separate.unitExports recorded))
          "inference fragment contains source visibility metadata") fragments;
      ensure (all (\key -> not (Set.member compareString key before)) (map fst (crateBindings iface)))
        "crate selected inventory overlaps existing bindings";
      chosen <- selectFragmentClosure selected before (snd prepared);
      uniqueNames "crate fragment binding" (concatMap (compose (map fst) (compose Separate.unitBindings Separate.objectInterface)) fragments);
      ensure (sameSchemes (concatMap (compose Separate.unitBindings Separate.objectInterface) fragments) (crateBindings iface))
        "crate object declaration inventory mismatch";
      linked <- foldEither (\((,) current proof) fragment ->
        linkFragmentWithSpine contexts allowedLayouts allowedSymbols ownSchemes current proof fragment
      ) ((,) state initialProof) chosen;
      let { after = fst linked };
      let {
        own =
          filter (\n -> not (Set.member compareString n before)) (M.keys (fragmentBindings after))
      };
      ensure (eqList eqString (sortStrings own) (sortStrings (concatMap (compose (map fst) (compose Separate.unitBindings (compose Separate.objectInterface fst))) chosen)))
        "crate object declaration inventory mismatch";
      Right ((,) after (snd linked))
    };
  entrySignatures entry bindings =
    filter
      (\((,) name _) ->
         (eqString name entry ||
          (startsWith "select_" name || (startsWith "super_" name || startsWith "instance_" name))))
      bindings;
  -- A closed monotype has no type instantiation or dictionary application at
  -- the entry use. The linked binding already carries the checked type; keep
  -- the import-boundary checks, but do not infer fake declarations for it.
  directEntryType dictionaries ty = case ty of {
    XCon name arguments -> not (M.member compareString name dictionaries) &&
      all (directEntryType dictionaries) arguments;
    XArrow argument result -> directEntryType dictionaries argument &&
      directEntryType dictionaries result;
    XApply function argument -> directEntryType dictionaries function &&
      directEntryType dictionaries argument;
    _ -> False
  };
  -- Preserve the old import adapter's rejection of noncanonical legacy
  -- schemes (including dead quantifiers). Bounded schemes use inference.
  directEntryImport ty = case ty of {
    XVar _ -> True;
    XArrow a b -> directEntryImport a && directEntryImport b;
    XCon _ arguments -> all directEntryImport arguments;
    XApply f a -> directEntryImport f && directEntryImport a;
    XForall variable XBot body -> Set.member T.compareTyVar variable (T.freeVars body) && directEntryImport body;
    XForall variable (XBotKind _) body -> Set.member T.compareTyVar variable (T.freeVars body) && directEntryImport body;
    _ -> False
  };
  directEntry signatures available entry = do {
    _ <- traverseEither (\((,) name expected) ->
      case M.lookup compareString name available of {
        Nothing -> Left ("missing entry symbol: " ++ name);
        Just ((,) _ actual) -> ensure (T.alphaEq expected actual)
          ("entry parameter type mismatch: " ++ name)
      }) (M.toList signatures);
    case M.lookup compareString entry available of {
      Nothing -> Left ("missing entry symbol: " ++ entry);
      Just ((,) name _) -> Right (XVarTerm name)
    }
  };
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
             importDictionaries n = if eqString (stringSlice n 0 7) "module_" then dictionaries else M.empty;
             conventions = M.mapWithKey (\n ty -> Separate.importClasses (importDictionaries n) ty) signatures;
             externals =
               M.mapWithKey
                 (\n ty ->
                    Separate.sourceScheme (importDictionaries n) ty)
                 signatures
           };
           case M.lookup compareString entry signatures of {
             Just ty -> if directEntryType dictionaries ty && all (compose directEntryImport snd) (M.toList signatures)
               then directEntry signatures available entry
               else inferEntry serial interfaces available entry visibleInstances signatures conventions externals;
             Nothing -> inferEntry serial interfaces available entry visibleInstances signatures conventions externals
           }
         };
  inferEntry serial interfaces available entry visibleInstances signatures conventions externals = do {
           let { classes = concatMap crateClasses interfaces };
           lowered <-
             Classes.lowerSeparateClassesWithImports conventions externals (map fst visibleInstances)
               (SClassProgram (concatMap crateData interfaces) classes (map snd visibleInstances)
                  (SVar entry));
           compiled <- mapLeft Compiler.prettyError (Compiler.finishCompilation lowered);
           Separate.removeEntryParameters signatures available
             (snd (Separate.freshObject serial (Compiler.compiledTerm compiled)))
         };
  linkCheckedObjectsV1 objects root = linkCheckedObjectsV1From
    (FragmentState 0 M.empty [] [] Set.empty) [] objects root;
  -- Compiler-owned closed spines can seed linking after exact installed-image
  -- admission. Ordinary artifact APIs always start with the empty state above.
  -- The complete assembled term still receives the final independent check.
  linkCheckedObjectsV1From = linkCheckedObjectsV1Using finishLinkedState;
  linkCheckedObjectsV1Using finish initial prelinked objects root =
    do {
      let {
        interfaces = append prelinked (map objectInterface objects)
      };
      uniqueNames "object identity" (map crateId interfaces);
      ensure (all (compose null crateDependencies) prelinked)
        "prelinked crate must have no dependencies";
      let {
        byName = interfaceMap interfaces
      };
      ordered <- dependencyClosure byName [] [] ((:) root []);
      let { ready = map crateId prelinked };
      ensure (all (\identity -> elem eqString identity (map crateId ordered)) ready)
        "prelinked crate is outside the dependency closure";
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
      program <- openProgramFrom ready ordered objectMap root;
      state <-
        foldEither
          (\s i ->
             case M.lookup compareString (crateId i) objectMap of {
               Nothing -> Left "missing crate object";
               Just o -> linkProgramCrate program byName layouts s o
             })
          initial
          (filter (\iface -> not (elem eqString (crateId iface) ready)) ordered);
      let {
        rootInterface = M.findWithDefault compareString (panic "missing root crate") root byName
      };
      entry <-
        linkEntry (fragmentSerial state) ordered rootInterface (fragmentBindings state)
          (crateEntry rootInterface);
      finish state entry
    };
  finishLinkedState state entry = do {
    body <- foldEither (\body declarations -> Separate.graft declarations body) entry
      (fragmentBodies state);
    Checked.check (XWithData (fragmentData state) body)
  };
  linkObjects objects root = mapEither Checked.term (linkCheckedObjects objects root);
  binaryInterfaceFields :: CrateInterface -> Structure.CrateInterfaceFields;
  binaryInterfaceFields (CrateInterface a b c d e f g h i j k l m) =
    Structure.CrateInterfaceFields a b c d e f g h i j k l m;
  fromBinaryInterfaceFields :: Structure.CrateInterfaceFields -> Either String CrateInterface;
  fromBinaryInterfaceFields (Structure.CrateInterfaceFields a b c d e f g h i j k l m) = do {
    let { iface = CrateInterface a b c d e f g h i j k l m };
    _ <- traverseEither (\((,,) name path semantic) ->
      ensure (stringLength name > 0 && stringLength semantic > 0 && Host.absolutePath path)
        "crate dependency metadata path must be absolute") b;
    Storage.admit [Storage.AdmitData True f, Storage.AdmitClasses g,
      Storage.AdmitInstances h, Storage.AdmitData True i, Storage.AdmitBindings j];
    validateInterface iface;
    Right iface
  };
  binaryObjectFields :: CrateObject -> Structure.CrateObjectFields;
  binaryObjectFields object = Structure.CrateObjectFields
    (envelopeLegacyObject object)
    (binaryInterfaceFields (objectInterface object)) (objectFragments object);
  decodeBinaryInterface :: W.Graph -> Either String CrateInterface;
  decodeBinaryInterface graph = case W.graphRoots graph of {
    [value] -> bindEither (Structure.fromGraphCrateInterfaceFields graph value) fromBinaryInterfaceFields;
    _ -> Left "malformed binary crate metadata roots"
  };
  decodeBinaryObject :: CrateInterface -> W.Graph -> Either String CrateObject;
  decodeBinaryObject expected graph = case W.graphRoots graph of {
    [value] -> do {
      fields <- Structure.fromGraphCrateObjectFields graph value;
      case fields of { Structure.CrateObjectFields legacy metadata raw -> do {
        actual <- fromBinaryInterfaceFields metadata;
        validateInterface expected;
        ensure (eqString (crateId actual) (crateId expected)) "crate object identity mismatch";
        ensure (eqString (encodeInterface actual) (encodeInterface expected))
          "crate object metadata mismatch";
        fragments <- traverseEither Storage.checkUnit raw;
        -- Preserve global datatype-name consistency from the old pooled and
        -- legacy decoders, without reparsing the implementation's pretty text.
        initial <- if legacy then poolDeclarations M.empty (crateLoweredData expected)
          else Right ((,) M.empty []);
        _ <- foldEither (\pool fragment -> do {
          header <- poolDeclarations pool (Separate.unitData (Separate.objectInterface fragment));
          body <- poolDeclarations (fst header) (Separate.objectContext fragment);
          Right (fst body)
        }) (fst initial) fragments;
        let { object = if legacy then LegacyCrateObject expected fragments
                     else CrateObject expected fragments };
        ensure (eqString (objectFingerprint object) (crateObjectFingerprint expected))
          "crate object checksum mismatch";
        Right object
      } }
    };
    _ -> Left "malformed binary crate object roots"
  };
  readInterface path = do {
    input <- Storage.read 3 path;
    ioReturn (mapLeft (\error -> path ++ ": " ++ error)
      (bindEither input (\decoded -> case decoded of {
        Storage.LegacyText text -> decodeInterface text;
        Storage.BinaryInput roots -> decodeBinaryInterface roots
      })))
  };
  readObjectV1 path iface = do {
    input <- Storage.read 4 path;
    ioReturn (mapLeft (\error -> path ++ ": " ++ error)
      (bindEither input (\decoded -> case decoded of {
        Storage.LegacyText text -> decodeObject iface text;
        Storage.BinaryInput roots -> decodeBinaryObject iface roots
      })))
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
              mapM (\((,) metadata iface) ->
                readObjectWithInterfaces (map snd interfaces) (objectPath metadata) iface) interfaces;
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
  -- Public IO() wrappers retain their existing signature. The Either entry is
  -- also available to callers that propagate structured publication failures.
  writeObjectEitherV1 :: String -> CrateObject -> IO (Either String ());
  writeObjectEitherV1 prefix object =
    if Storage.hasNul prefix 0 then ioReturn (Left "file path contains NUL") else do {
      body <- Storage.writeAtomic 4 (prefix ++ ".mlfco")
        [Structure.toCrateObjectFields (binaryObjectFields object)];
      case body of {
        Left error -> ioReturn (Left error);
        Right _ -> Storage.writeAtomic 3 (prefix ++ ".mlfci")
          [Structure.toCrateInterfaceFields (binaryInterfaceFields (objectInterface object))]
      }
    };
  writeObjectAtomicEither :: String -> CrateObject -> IO (Either String ());
  writeObjectAtomicEither prefix object = writeObjectEither prefix object;
  writeObjectWithPayloadEither :: String -> CrateObject -> String -> IO (Either String ());
  writeObjectWithPayloadEither prefix object payload = writeObjectEither prefix object;
  writeObject prefix object = do {
    written <- writeObjectEither prefix object;
    case written of {
      Left error -> ioError (userError (textToChars error));
      Right _ -> ioReturn ()
    }
  };
  -- The paired text remains only the existing semantic-fingerprint authority
  -- in makeObjectWithPayload. It is never stored as a binary payload or parsed
  -- back into an AST. Do not force a caller's unused payload argument.
  writeObjectWithPayload :: String -> CrateObject -> String -> IO ();
  writeObjectWithPayload prefix object payload = writeObject prefix object;
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
         ((:) ("interface " ++ semanticFingerprint iface) (append dependencies modules)));

  -- BEGIN N7 CRATE ENVELOPE ADDITIONS
  -- This marker selects a policy; it is never typing/checksum authority.
  envelopeLegacyObject object = case object of {
    LegacyCrateObject _ _ -> True;
    EnvelopeCrateObject legacy _ _ -> legacy;
    _ -> False
  };
  envelopeMarked object = case object of { EnvelopeCrateObject _ _ _ -> True; _ -> False };
  -- N7 crate-only inline envelope. CANDIDATE resource class: no claim of
  -- native/RSS/CPU qualification. Old v1 APIs/defaults remain independent.
  -- No chunk can reset the cumulative physical, expanded or rendered budgets.
  data CrateEnvelopeLimits = CrateEnvelopeLimits Int Int Int Int Int Int;
  crateEnvelopeLimits :: CrateEnvelopeLimits;
  crateEnvelopeLimits = CrateEnvelopeLimits 16777216 536870912 553648128 256 65536 536870912;
  envelopeMaxNodes (CrateEnvelopeLimits n _ _ _ _ _) = n;
  envelopeMaxText (CrateEnvelopeLimits _ t _ _ _ _) = t;
  envelopeMaxWork (CrateEnvelopeLimits _ _ w _ _ _) = w;
  envelopeMaxChunks (CrateEnvelopeLimits _ _ _ k _ _) = k;
  envelopeMaxFragments (CrateEnvelopeLimits _ _ _ _ f _) = f;
  envelopeMaxRender (CrateEnvelopeLimits _ _ _ _ _ r) = r;
  envelopeValidLimits limits =
    envelopeMaxNodes limits >= 0 && envelopeMaxNodes limits <= 2147483647 &&
    envelopeMaxText limits >= 0 && envelopeMaxText limits <= 2147483647 &&
    envelopeMaxWork limits >= 0 && envelopeMaxWork limits <= 2147483647 &&
    envelopeMaxChunks limits >= 1 && envelopeMaxChunks limits <= 256 &&
    envelopeMaxFragments limits >= 0 && envelopeMaxFragments limits <= 65536 &&
    envelopeMaxRender limits >= 0 && envelopeMaxRender limits <= 536870912;
  envelopeMagic :: String;
  envelopeMagic = "MLFCR2\r\n";
  envelopeAdd label limit old amount =
    if old < 0 || amount < 0 || old > limit || amount > limit - old
    then Left ("crate envelope " ++ label ++ " limit exceeded (used=" ++ showInt old
      ++ ", next=" ++ showInt amount ++ ", max=" ++ showInt limit ++ ")")
    else let { next = old + amount } in seq next (Right next);
  envelopeMultiply label limit a b =
    if a < 0 || b < 0 then Left ("crate envelope " ++ label ++ " overflow")
    else if a == 0 || b == 0 then Right 0
    else if a > limit / b then Left ("crate envelope " ++ label ++ " limit exceeded")
    else Right (a * b);
  data EnvelopeEntry = EnvelopeEntry Int Int Int Int Int;
  envelopeEntryOffset (EnvelopeEntry offset _ _ _ _) = offset;
  envelopeEntryLength (EnvelopeEntry _ size _ _ _) = size;
  envelopeEntryFirst (EnvelopeEntry _ _ first _ _) = first;
  envelopeEntryCount (EnvelopeEntry _ _ _ count _) = count;
  envelopeEntrySchema (EnvelopeEntry _ _ _ _ schema) = schema;
  data EnvelopeHeader = EnvelopeHeader Int Int Int Bool Int;
  envelopeMatchPrefix bytes text count index =
    if index == count then ioReturn True else do {
      value <- readByteArray bytes index;
      if value /= stringCodeAt text index then ioReturn False
      else envelopeMatchPrefix bytes text count (index + 1)
    };
  -- The unique five-byte family prefix cannot be a canonical old text frame.
  -- A recognized family is committed to this decoder, including truncations.
  envelopeHasFamily bytes = do {
    size <- lengthByteArray bytes;
    if size < 5 then ioReturn False else envelopeMatchPrefix bytes envelopeMagic 5 0
  };
  envelopeChecksum bytes size = envelopeChecksumAt bytes size 0 4294967295;
  envelopeChecksumAt bytes size index crc =
    if index == size then ioReturn (xorInt crc 4294967295) else do {
      value <- if index >= 60 && index < 64 then ioReturn 0 else readByteArray bytes index;
      let { next = W.crcByte crc value };
      seq next (envelopeChecksumAt bytes size (index + 1) next)
    };
  envelopeReadHeader limits actual = do {
    version <- W.getBits 32; flags <- W.getBits 32; schema <- W.getBits 32;
    headerBytes <- W.getBits 32; total <- W.getBits 32; chunks <- W.getBits 32;
    fragments <- W.getBits 32; directory <- W.getBits 32; entryBytes <- W.getBits 32;
    directoryBytes <- W.getBits 32; payload <- W.getBits 32; legacy <- W.getBits 32;
    reserved <- W.getBits 32; crc <- W.getBits 32;
    W.checkRead (version == 2) "unsupported crate envelope version";
    W.checkRead (flags == 0 && reserved == 0) "unknown crate envelope flags";
    W.checkRead (schema == 4) "crate envelope schema mismatch";
    W.checkRead (headerBytes == 64 && directory == 64 && entryBytes == 32)
      "crate envelope header layout mismatch";
    W.checkRead (total == actual && total <= Storage.maxBytes)
      "crate envelope file length mismatch";
    W.checkRead (chunks >= 1 && chunks <= envelopeMaxChunks limits &&
      chunks <= (actual - 64) / 112) "crate envelope chunk count limit exceeded";
    W.checkRead (fragments <= envelopeMaxFragments limits &&
      (if fragments == 0 then chunks == 1 else chunks >= 2 && chunks - 1 <= fragments))
      "crate envelope fragment count mismatch";
    W.checkRead (directoryBytes == chunks * 32 && payload == 64 + directoryBytes && payload <= actual)
      "crate envelope directory length mismatch";
    W.checkRead (legacy == 0 || legacy == 1) "crate envelope legacy flag mismatch";
    W.returnRead (EnvelopeHeader chunks fragments payload (legacy == 1) crc)
  };
  envelopeReadEntries total chunks fragments index offset first done =
    if index == chunks then do {
      W.checkRead (offset == total && first == fragments) "crate envelope coverage mismatch";
      W.returnRead (reverse done)
    } else do {
      role <- W.getBits 32; ordinal <- W.getBits 32; start <- W.getBits 32;
      size <- W.getBits 32; beginning <- W.getBits 32; count <- W.getBits 32;
      schema <- W.getBits 32; reserved <- W.getBits 32;
      W.checkRead (ordinal == index && reserved == 0) "crate envelope directory order mismatch";
      W.checkRead (start == offset && offset <= total && size >= 80 && size <= total - offset)
        "crate envelope region length mismatch";
      W.checkRead (if index == 0 then role == 0 && schema == 3 && beginning == 0 && count == 0
        else role == 1 && schema == 4 && beginning == first && count > 0 && count <= fragments - first)
        "crate envelope chunk role or fragment range mismatch";
      envelopeReadEntries total chunks fragments (index + 1) (offset + size) (first + count)
        ((:) (EnvelopeEntry offset size first count schema) done)
    };
  envelopeCopyBytes source sourceOffset target targetOffset count index =
    if index == count then ioReturn () else do {
      value <- readByteArray source (sourceOffset + index);
      writeByteArray target (targetOffset + index) value;
      envelopeCopyBytes source sourceOffset target targetOffset count (index + 1)
    };
  envelopeRegion :: ByteArray -> Int -> Int -> IO (Either String ByteArray);
  envelopeRegion bytes offset size = do {
    total <- lengthByteArray bytes;
    if offset < 0 || size < 0 || offset > total || size > total - offset || size > Storage.maxBytes
    then ioReturn (Left "crate envelope region out of range") else do {
      region <- newByteArray size 0;
      envelopeCopyBytes bytes offset region 0 size 0;
      ioReturn (Right region)
    }
  };
  data EnvelopeResources = EnvelopeResources Int Int Int Int Int Int Int Int Int;
  envelopeEmptyResources = EnvelopeResources 0 0 0 0 0 0 0 0 0;
  envelopeCharge limits metadata stats (EnvelopeResources bytes nodes edges symbols symbolBytes occurrences text depth chunks) = do {
    nextBytes <- envelopeAdd "wire bytes" Storage.maxBytes bytes (W.resourceBytes stats);
    nextNodes <- envelopeAdd "physical nodes" (W.maxNodes W.defaultLimits) nodes (W.resourceNodes stats);
    nextEdges <- envelopeAdd "physical edges" (W.maxEdges W.defaultLimits) edges (W.resourceEdges stats);
    nextSymbols <- envelopeAdd "symbols" (W.maxSymbols W.defaultLimits) symbols (W.resourceSymbols stats);
    nextSymbolBytes <- envelopeAdd "symbol bytes" (W.maxTotalSymbolBytes W.defaultLimits) symbolBytes (W.resourceSymbolBytes stats);
    nextOccurrences <- envelopeAdd "expanded occurrences" (envelopeMaxNodes limits) occurrences (W.resourceExpandedNodes stats);
    nextText <- envelopeAdd "expanded text" (envelopeMaxText limits) text (W.resourceExpandedTextBytes stats);
    _ <- envelopeAdd "expanded work" (envelopeMaxWork limits) nextOccurrences nextText;
    nextChunks <- envelopeAdd "chunks" (envelopeMaxChunks limits) chunks 1;
    let { nextDepth = max depth (W.resourceDepth stats + 1) };
    ensure (nextDepth <= W.maxDepth W.defaultLimits) "crate envelope reconstructed depth limit exceeded";
    Right (EnvelopeResources nextBytes nextNodes nextEdges nextSymbols nextSymbolBytes
      nextOccurrences nextText nextDepth nextChunks)
  };
  envelopeFinishResources limits fragments (EnvelopeResources bytes nodes edges symbols symbolBytes occurrences text depth chunks) = do {
    let { bodies = chunks - 1; logical = occurrences - bodies + 3 };
    ensure (logical >= 0 && logical <= envelopeMaxNodes limits)
      "crate envelope logical occurrence limit exceeded";
    _ <- envelopeAdd "logical work" (envelopeMaxWork limits) logical text;
    _ <- envelopeAdd "file bytes" Storage.maxBytes bytes (64 + 32 * chunks);
    ensure (max 2 depth <= W.maxDepth W.defaultLimits) "crate envelope reconstructed depth limit exceeded";
    ensure (fragments >= 0 && fragments <= envelopeMaxFragments limits &&
      (if fragments == 0 then bodies == 0 else bodies >= 1 && bodies <= fragments))
      "crate envelope fragment count mismatch";
    Right ()
  };
  envelopeRawInterface (Structure.CrateInterfaceFields a b c d e f g h i j k l m) =
    CrateInterface a b c d e f g h i j k l m;
  envelopeRawList graph index = do {
    decoded <- Structure.decodeGraphValue (Structure.ShapeList Structure.ShapeRawUnitObject) graph index;
    Structure.expectList Structure.expectRawUnitObject decoded
  };
  envelopeDecodeChunks limits bytes entries resources metadata previousWork reversed = case entries of {
    [] -> ioReturn (Right ((,,) metadata (reverse reversed) resources));
    (:) entry rest -> do {
      copied <- envelopeRegion bytes (envelopeEntryOffset entry) (envelopeEntryLength entry);
      case copied of {
        Left message -> ioReturn (Left message);
        Right region -> do {
          decoded <- W.decodeGraph W.defaultLimits (envelopeEntrySchema entry) region;
          case decoded of {
            Left message -> ioReturn (Left message);
            Right graph -> case (do {
              stats <- W.graphResourceStats graph;
              next <- envelopeCharge limits (envelopeEntrySchema entry == 3) stats resources;
              case W.graphRoots graph of {
                [root] -> if envelopeEntrySchema entry == 3 then do {
                  fields <- Structure.fromGraphCrateInterfaceFields graph root;
                  Right ((,,,) next (Just (envelopeRawInterface fields)) [] 0)
                } else do {
                  raw <- envelopeRawList graph root;
                  count <- W.boundedLength (envelopeEntryCount entry) raw;
                  ensure (count == envelopeEntryCount entry) "crate envelope decoded fragment count mismatch";
                  if previousWork == 0 then Right () else case raw of {
                    [] -> Left "crate envelope empty body chunk";
                    (:) first _ -> do {
                      measured <- W.planMeasured W.defaultLimits [Structure.toRawUnitObject first];
                      case measured of { (,) _ firstStats ->
                        ensure (W.resourceExpandedWork firstStats > W.maxExpandedWork W.defaultLimits - previousWork)
                          "noncanonical crate envelope partition" }
                    }
                  };
                  Right ((,,,) next metadata raw (W.resourceExpandedWork stats))
                };
                _ -> Left "crate envelope inner root count mismatch"
              }
            }) of {
              Left message -> ioReturn (Left message);
              Right ((,,,) next iface raw nextWork) -> envelopeDecodeChunks limits bytes rest next iface nextWork
                (append (reverse raw) reversed)
            }
          }
        }
      }
    }
  };
  -- Counts in headers are untrusted preflight claims, subsequently checked
  -- by each unchanged decoder. Summing them now bounds cumulative node/edge/
  -- symbol allocation before any graph is built. UTF8 symbol bytes are not a
  -- v1 header field; their exact global charge follows ordinary symbol decode.
  envelopePreflightHeaders bytes entries nodes edges symbols = case entries of {
    [] -> ioReturn (Right ());
    (:) entry rest -> do {
      header <- W.runSection bytes (envelopeEntryOffset entry + 8) 72
        (W.getHeader W.defaultLimits (envelopeEntrySchema entry) (envelopeEntryLength entry));
      case header of {
        Left message -> ioReturn (Left message);
        Right (W.Header (W.Layout _ symbolCount _ nodeCount _ _ edgeCount roots _ _ _ _) _) ->
          case (do {
            ensure (roots == 1) "crate envelope inner root count mismatch";
            nextNodes <- envelopeAdd "preflight physical nodes" (W.maxNodes W.defaultLimits) nodes nodeCount;
            nextEdges <- envelopeAdd "preflight physical edges" (W.maxEdges W.defaultLimits) edges edgeCount;
            nextSymbols <- envelopeAdd "preflight symbols" (W.maxSymbols W.defaultLimits) symbols symbolCount;
            Right ((,,) nextNodes nextEdges nextSymbols)
          }) of {
            Left message -> ioReturn (Left message);
            Right ((,,) nextNodes nextEdges nextSymbols) ->
              envelopePreflightHeaders bytes rest nextNodes nextEdges nextSymbols
          }
      }
    }
  };
  envelopeDecode limits expected bytes = catchIOError (envelopeDecodeChecked limits expected bytes)
    (\error -> ioReturn (Left ("crate envelope decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  envelopeDecodeChecked limits expected bytes = do {
    size <- lengthByteArray bytes;
    if not (envelopeValidLimits limits) then ioReturn (Left "invalid crate envelope limits")
    else if size < 64 || size > Storage.maxBytes then ioReturn (Left "crate envelope truncated header or file limit exceeded")
    else do {
      matched <- envelopeMatchPrefix bytes envelopeMagic 8 0;
      if not matched then ioReturn (Left "crate envelope magic mismatch") else do {
        header <- W.runSection bytes 8 56 (envelopeReadHeader limits size);
        case header of {
          Left message -> ioReturn (Left message);
          Right (EnvelopeHeader chunks fragments payload legacy expectedCRC) -> do {
            directory <- W.runSection bytes 64 (chunks * 32)
              (envelopeReadEntries size chunks fragments 0 payload 0 []);
            case directory of {
              Left message -> ioReturn (Left message);
              Right entries -> do {
                crc <- envelopeChecksum bytes size;
                if crc /= expectedCRC then ioReturn (Left "crate envelope checksum mismatch") else do {
                  preflight <- envelopePreflightHeaders bytes entries 0 0 0;
                  case preflight of {
                    Left message -> ioReturn (Left message);
                    Right _ -> do {
                      decoded <- envelopeDecodeChunks limits bytes entries envelopeEmptyResources Nothing 0 [];
                      ioReturn (bindEither decoded (\((,,) metadata raw resources) -> do {
                        envelopeFinishResources limits fragments resources;
                        case metadata of {
                          Nothing -> Left "crate envelope metadata missing";
                          Just actual -> envelopeAdmit limits legacy expected actual raw
                        }
                      }))
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  };
  -- This walk only selects the route. Any uncertainty/invalid scalar returns
  -- to the original v1 planner, preserving its diagnostic/acceptance domain.
  -- No new envelope limit, fragment count, or renderer runs before selection.
  envelopeAboveOldWork roots = not (envelopeFitsOldWork [roots] (W.maxExpandedWork W.defaultLimits))
    && envelopeOldWork [roots] 0;
  -- One UTF-8 scalar occupies at most four bytes. If even this upper bound
  -- fits, the exact selector cannot pick the envelope. On uncertainty keep
  -- its original byte count and failure order.
  envelopeFitsOldWork pending remaining = case pending of {
    [] -> True;
    (:) values rest -> case values of {
      [] -> envelopeFitsOldWork rest remaining;
      (:) value more -> if remaining <= 0 then False else let {
        tail = (:) more rest; next = remaining - 1
      } in case value of {
        W.VNode _ children -> envelopeFitsOldWork ((:) children tail) next;
        W.VText text -> let { n = stringLength text } in
          n <= next / 4 && n <= W.maxSymbolBytes W.defaultLimits / 4
            && envelopeFitsOldWork tail (next - 4 * n);
        _ -> envelopeFitsOldWork tail next
      }
    }
  };
  envelopeOldWork pending work = case pending of {
    [] -> False;
    (:) values more -> case values of {
      [] -> envelopeOldWork more work;
      (:) value rest -> if work >= W.maxExpandedWork W.defaultLimits then True else
        let { next = work + 1 } in case value of {
          W.VNode _ children -> envelopeOldWork ((:) children ((:) rest more)) next;
          W.VText text -> case W.utf8Size (W.maxSymbolBytes W.defaultLimits) text of {
            Left _ -> False;
            Right bytes -> if bytes > W.maxExpandedWork W.defaultLimits - next then True
              else envelopeOldWork ((:) rest more) (next + bytes)
          };
          _ -> envelopeOldWork ((:) rest more) next
        }
    }
  };
  data EnvelopeChunkPlan = EnvelopeChunkPlan Int Int W.Tables W.ResourceStats;
  envelopePlanStats (EnvelopeChunkPlan _ _ _ stats) = stats;
  envelopePlanCount (EnvelopeChunkPlan _ count _ _) = count;
  envelopePlanSchema (EnvelopeChunkPlan schema _ _ _) = schema;
  envelopeBodyValue raw = Structure.toList Structure.toRawUnitObject raw;
  envelopePlanChunk schema count roots = do {
    measured <- W.planMeasured W.defaultLimits roots;
    case measured of { (,) tables stats -> Right (EnvelopeChunkPlan schema count tables stats) }
  };
  -- Deterministic maximal contiguous groups by original expanded WORK.
  -- Exact final groups are independently planned under every original limit.
  -- Each fragment is measured once; no repeated whole-prefix retry loop.
  envelopePlanBodies limits raw active activeCount activeWork done count occurrences text resources = case raw of {
    [] -> if activeCount == 0 then Right ((,) (reverse done) resources) else do {
      chunk <- envelopePlanChunk 4 activeCount [envelopeBodyValue (reverse active)];
      final <- envelopeCharge limits False (envelopePlanStats chunk) resources;
      Right ((,) (reverse ((:) chunk done)) final)
    };
    (:) fragment rest -> do {
      nextCount <- envelopeAdd "fragments" (envelopeMaxFragments limits) count 1;
      measured <- W.planMeasured W.defaultLimits [Structure.toRawUnitObject fragment];
      case measured of { (,) _ stats -> do {
        ensure (W.resourceExpandedWork stats < W.maxExpandedWork W.defaultLimits &&
          W.resourceDepth stats < W.maxDepth W.defaultLimits)
          "crate envelope fragment does not fit its list wrapper";
        nextOccurrences <- envelopeAdd "logical occurrences" (envelopeMaxNodes limits) occurrences (W.resourceExpandedNodes stats);
        nextText <- envelopeAdd "logical text" (envelopeMaxText limits) text (W.resourceExpandedTextBytes stats);
        _ <- envelopeAdd "logical work" (envelopeMaxWork limits) nextOccurrences nextText;
        if W.resourceExpandedWork stats <= W.maxExpandedWork W.defaultLimits - activeWork
        then envelopePlanBodies limits rest ((:) fragment active) (activeCount + 1)
          (activeWork + W.resourceExpandedWork stats) done nextCount nextOccurrences nextText resources
        else do {
          ensure (activeCount > 0) "crate envelope oversized singleton fragment";
          chunk <- envelopePlanChunk 4 activeCount [envelopeBodyValue (reverse active)];
          charged <- envelopeCharge limits False (envelopePlanStats chunk) resources;
          envelopePlanBodies limits rest [fragment] 1 (1 + W.resourceExpandedWork stats)
            ((:) chunk done) nextCount nextOccurrences nextText charged
        }
      } }
    }
  };
  envelopePlan limits object = do {
    ensure (envelopeValidLimits limits) "invalid crate envelope limits";
    metadata <- envelopePlanChunk 3 0 [Structure.toCrateInterfaceFields
      (binaryInterfaceFields (objectInterface object))];
    initial <- envelopeCharge limits True (envelopePlanStats metadata) envelopeEmptyResources;
    initialOccurrences <- envelopeAdd "logical occurrences" (envelopeMaxNodes limits) 3
      (W.resourceExpandedNodes (envelopePlanStats metadata));
    planned <- envelopePlanBodies limits (objectFragments object) [] 0 1 [] 0
      initialOccurrences (W.resourceExpandedTextBytes (envelopePlanStats metadata)) initial;
    case planned of { (,) bodies resources -> do {
      let { chunks = (:) metadata bodies };
      count <- W.boundedLength (envelopeMaxFragments limits) (objectFragments object);
      envelopeFinishResources limits count resources;
      Right ((,) chunks count)
    } }
  };
  envelopeWriteDirectory bytes chunks index offset first position = case chunks of {
    [] -> ioReturn position;
    (:) chunk rest -> let {
      size = W.resourceBytes (envelopePlanStats chunk);
      count = envelopePlanCount chunk;
      schema = envelopePlanSchema chunk
    } in do {
      next <- W.putWords bytes position [if index == 0 then 0 else 1,index,offset,size,first,count,schema,0];
      envelopeWriteDirectory bytes rest (index + 1) (offset + size) (first + count) next
    }
  };
  envelopeEncodeChunks bytes offset chunks = case chunks of {
    [] -> ioReturn (Right offset);
    (:) (EnvelopeChunkPlan schema _ tables stats) rest -> case W.layout W.defaultLimits tables of {
      Left message -> ioReturn (Left message);
      Right geometry -> do {
        encoded <- W.encodeTables schema geometry tables;
        case encoded of {
          Left message -> ioReturn (Left message);
          Right region -> do {
            size <- lengthByteArray region;
            if size /= W.resourceBytes stats then ioReturn (Left "crate envelope planned size mismatch") else do {
              envelopeCopyBytes region 0 bytes offset size 0;
              envelopeEncodeChunks bytes (offset + size) rest
            }
          }
        }
      }
    }
  };
  envelopeEncode limits object = catchIOError (envelopeEncodeChecked limits object)
    (\error -> ioReturn (Left ("crate envelope encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  envelopeEncodeChecked limits object = case envelopePlan limits object of {
    Left message -> ioReturn (Left message);
    Right ((,) chunks fragments) -> case envelopeAdmit limits
      (envelopeLegacyObject object)
      (objectInterface object) (objectInterface object) (objectFragments object) of {
      Left message -> ioReturn (Left message);
      Right _ -> let {
        count = length chunks; payload = 64 + count * 32;
        total = payload + foldlStrict (\n chunk -> n + W.resourceBytes (envelopePlanStats chunk)) 0 chunks
      } in do {
        bytes <- newByteArray total 0;
        magicEnd <- W.putText bytes 0 envelopeMagic 0;
        headerEnd <- W.putWords bytes magicEnd [2,0,4,64,total,count,fragments,64,32,count * 32,payload,
          if (envelopeLegacyObject object) then 1 else 0,0,0];
        directoryEnd <- envelopeWriteDirectory bytes chunks 0 payload 0 headerEnd;
        if directoryEnd /= payload * 8 then ioReturn (Left "crate envelope directory size mismatch") else do {
          encoded <- envelopeEncodeChunks bytes payload chunks;
          case encoded of {
            Left message -> ioReturn (Left message);
            Right end -> if end /= total then ioReturn (Left "crate envelope output size mismatch") else do {
              crc <- envelopeChecksum bytes total;
              _ <- W.putBits bytes 480 32 crc;
              ioReturn (Right bytes)
            }
          }
        }
      }
    }
  };
  -- The reader ledger reserves every specified serialization pass before
  -- rendering/checking. Reservation bounds may conservatively exceed actual
  -- scalar/UTF8 output; exact summaries must remain within those reservations.
  data EnvelopeRenderBudget = EnvelopeRenderBudget Int Int Int Int Int Int;
  envelopeEmptyRenderBudget = EnvelopeRenderBudget 0 0 0 0 0 0;
  envelopeBounds scalars bytes = Storage.RenderBounds scalars bytes;
  envelopeZeroBounds = envelopeBounds 0 0;
  envelopeFullBounds limits = envelopeBounds (envelopeMaxRender limits) (envelopeMaxRender limits);
  envelopeChargeRender :: CrateEnvelopeLimits -> Int -> Storage.RenderBounds -> EnvelopeRenderBudget -> Either String EnvelopeRenderBudget;
  envelopeChargeRender limits role bounds (EnvelopeRenderBudget us ub os ob ms mb) = do {
    let { scalars = Storage.renderBoundScalars bounds; bytes = Storage.renderBoundUtf8 bounds;
          totalScalars = us + os + ms; totalBytes = ub + ob + mb;
          domain = if role == 0 then "unit " else if role == 1 then "object " else "metadata " };
    _ <- envelopeAdd (domain ++ "rendered scalar reservation") (envelopeMaxRender limits) totalScalars scalars;
    _ <- envelopeAdd (domain ++ "rendered UTF8 reservation") (envelopeMaxRender limits) totalBytes bytes;
    Right (if role == 0 then EnvelopeRenderBudget (us + scalars) (ub + bytes) os ob ms mb
      else if role == 1 then EnvelopeRenderBudget us ub (os + scalars) (ob + bytes) ms mb
      else EnvelopeRenderBudget us ub os ob (ms + scalars) (mb + bytes))
  };
  envelopeBoundsAdd limits left right = do {
    scalars <- envelopeAdd "rendered scalar bound" (envelopeMaxRender limits)
      (Storage.renderBoundScalars left) (Storage.renderBoundScalars right);
    bytes <- envelopeAdd "rendered UTF8 bound" (envelopeMaxRender limits)
      (Storage.renderBoundUtf8 left) (Storage.renderBoundUtf8 right);
    Right (envelopeBounds scalars bytes)
  };
  envelopeBoundsTimes limits count bounds = do {
    scalars <- envelopeMultiply "rendered scalar bound" (envelopeMaxRender limits) count (Storage.renderBoundScalars bounds);
    bytes <- envelopeMultiply "rendered UTF8 bound" (envelopeMaxRender limits) count (Storage.renderBoundUtf8 bounds);
    Right (envelopeBounds scalars bytes)
  };
  envelopeDecimalDigits value = if value < 10 then 1 else 1 + envelopeDecimalDigits (value / 10);
  envelopeTextBounds limits text = do {
    bytes <- W.utf8Size (envelopeMaxRender limits) text;
    ensure (stringLength text <= envelopeMaxRender limits) "crate envelope rendered scalar bound limit exceeded";
    Right (envelopeBounds (stringLength text) bytes)
  };
  envelopePackBounds limits fields = foldEither (\acc field -> do {
    let { prefix = envelopeDecimalDigits (Storage.renderBoundScalars field) + 1 };
    framed <- envelopeBoundsAdd limits (envelopeBounds prefix prefix) field;
    envelopeBoundsAdd limits acc framed
  }) envelopeZeroBounds fields;
  envelopeBoundsWithin bounds summary =
    ensure (Storage.renderSummaryScalars summary <= Storage.renderBoundScalars bounds &&
      Storage.renderSummaryUtf8 summary <= Storage.renderBoundUtf8 bounds)
      "crate envelope rendered summary exceeds reservation";
  envelopeLiteral limits text = do {
    bounds <- envelopeTextBounds limits text;
    Storage.v2SummaryText bounds text
  };
  envelopeDigest summary = Separate.encodingFingerprint (Storage.renderSummaryEncoding summary);
  -- Exact canonical metadata projection, not pretty/alpha/hash equality.
  data EnvelopeCompareTask = EnvelopeCompareOne W.Value W.Value | EnvelopeCompareMany ([] W.Value) ([] W.Value);
  envelopeEqualTasks :: Int -> [] EnvelopeCompareTask -> Either String ();
  envelopeEqualTasks remaining tasks = case tasks of {
    [] -> Right ();
    (:) task rest -> case task of {
      EnvelopeCompareMany left right -> case left of {
        [] -> case right of { [] -> envelopeEqualTasks remaining rest; _ -> Left "crate object metadata mismatch" };
        (:) a more -> case right of {
          [] -> Left "crate object metadata mismatch";
          (:) b tail -> envelopeEqualTasks remaining
            ((:) (EnvelopeCompareOne a b) ((:) (EnvelopeCompareMany more tail) rest))
        }
      };
      EnvelopeCompareOne a b -> if remaining <= 0 then Left "crate envelope metadata comparison limit exceeded"
        else case a of {
          W.VInt x -> case b of { W.VInt y -> if x == y then envelopeEqualTasks (remaining - 1) rest else Left "crate object metadata mismatch"; _ -> Left "crate object metadata mismatch" };
          W.VBits x -> case b of { W.VBits y -> if x == y then envelopeEqualTasks (remaining - 1) rest else Left "crate object metadata mismatch"; _ -> Left "crate object metadata mismatch" };
          W.VText x -> case b of { W.VText y -> if eqString x y then envelopeEqualTasks (remaining - 1) rest else Left "crate object metadata mismatch"; _ -> Left "crate object metadata mismatch" };
          W.VNode tag fields -> case b of {
            W.VNode other children -> if tag == other then envelopeEqualTasks (remaining - 1)
              ((:) (EnvelopeCompareMany fields children) rest) else Left "crate object metadata mismatch";
            _ -> Left "crate object metadata mismatch"
          }
        }
    }
  };
  envelopeExactMetadata expected actual = do {
    ensure (eqString (crateId expected) (crateId actual)) "crate object identity mismatch";
    let { a = Structure.toCrateInterfaceFields (binaryInterfaceFields expected);
          b = Structure.toCrateInterfaceFields (binaryInterfaceFields actual) };
    _ <- W.planMeasured W.defaultLimits [a];
    envelopeEqualTasks (W.maxExpandedWork W.defaultLimits) [EnvelopeCompareOne a b]
  };
  -- Named metadata rendering/materialization results are charged individually.
  -- Internal builder/concatenation copies are a separate residency obligation,
  -- not an unexplained multiplicative allowance. No pretty/name construction
  -- occurs while deriving these reservations from the actual admitted fields.
  envelopeBoundsSum limits values = foldEither (envelopeBoundsAdd limits) envelopeZeroBounds values;
  envelopeEncodedTextBounds limits text = do {
    _ <- W.utf8Size (envelopeMaxRender limits) text;
    -- A Unicode scalar is <=1114111: at most7 decimal digits plus '_'.
    count <- envelopeMultiply "metadata encoded scalar text" (envelopeMaxRender limits) 8 (stringLength text);
    Right (envelopeBounds count count)
  };
  envelopeDefinitionReservation limits encodedIdentity entity = do {
    key <- Storage.v2Measure (envelopeMaxRender limits) (envelopeMaxRender limits) (Storage.V2Entity entity);
    encodedCount <- envelopeMultiply "metadata encoded entity key" (envelopeMaxRender limits) 8
      (Storage.renderBoundScalars key);
    let { encodedKey = envelopeBounds encodedCount encodedCount };
    -- Ordinary names use a7-character prefix plus 'z_'; stable-name and
    -- managed-builtin branches are bounded by the same key-based allowance.
    name <- envelopeBoundsSum limits [envelopeBounds 9 9,encodedIdentity,encodedKey];
    envelopeBoundsSum limits [key,encodedKey,name]
  };
  envelopeInstancePrefixReservation limits encodedIdentity owner = do {
    encodedOwner <- envelopeEncodedTextBounds limits owner;
    prefix <- envelopeBoundsSum limits [envelopeBounds 13 13,encodedIdentity,encodedOwner];
    produced <- envelopeBoundsSum limits [encodedIdentity,encodedOwner,prefix];
    -- startsWith may slice an untrusted instance symbol. Even if it cannot
    -- match this ASCII prefix, its first prefixLength scalars can be4-byte UTF8.
    sliceBytes <- envelopeMultiply "metadata instance comparison slice" (envelopeMaxRender limits) 4
      (Storage.renderBoundScalars prefix);
    scan <- envelopeBoundsAdd limits produced
      (envelopeBounds (Storage.renderBoundScalars prefix) sliceBytes);
    Right ((,,) scan (Storage.renderBoundScalars produced) (Storage.renderBoundScalars prefix))
  };
  envelopeInstanceOwnerReservations limits encodedIdentity modules = foldEither
    (\((,,) total maxProduced maxPrefix) owner -> do {
      measured <- envelopeInstancePrefixReservation limits encodedIdentity owner;
      case measured of { (,,) scan produced prefix -> do {
        next <- envelopeBoundsAdd limits total scan;
        Right ((,,) next (max maxProduced produced) (max maxPrefix prefix))
      } }
    }) ((,,) envelopeZeroBounds 0 0) modules;
  envelopeInstanceNameReservation limits maxProduced maxPrefix entry = do {
    -- Separate.prettyInstance ignores method bodies, just like V2Instance;
    -- stripInstance therefore leaves the exact rendered domain unchanged.
    rendered <- Storage.v2Measure (envelopeMaxRender limits) (envelopeMaxRender limits)
      (Storage.V2Instance (snd entry));
    -- fingerprint has two <=10-digit nonnegative residues and one '-'.
    -- Encoding those <=21 scalars is conservatively <=168 ASCII characters.
    name <- envelopeAdd "metadata instance name" (envelopeMaxRender limits) maxPrefix 168;
    envelopeBoundsSum limits [rendered,envelopeBounds 21 21,envelopeBounds 168 168,
      envelopeBounds maxProduced maxProduced,envelopeBounds name name]
  };
  envelopeMetadataValidationBounds limits iface = do {
    identity <- envelopeEncodedTextBounds limits (crateId iface);
    let { ownExports = filter (\entity -> not (isPrimitiveEntity entity) &&
            elem eqString (Modules.owner entity) (crateModules iface)) (concatMap snd (crateExports iface)) };
    exports <- foldEither (\total entity -> do {
      rendered <- envelopeDefinitionReservation limits identity entity;
      envelopeBoundsAdd limits total rendered
    }) (if null ownExports then envelopeZeroBounds else identity) ownExports;
    instances <- W.boundedLength (W.maxEdges W.defaultLimits) (crateInstances iface);
    ownerReservations <- if instances == 0 then Right ((,,) envelopeZeroBounds 0 0)
      else envelopeInstanceOwnerReservations limits identity (crateModules iface);
    instanceBounds <- case ownerReservations of { (,,) scans maxProduced maxPrefix -> do {
      repeated <- envelopeBoundsTimes limits instances scans;
      foldEither (\total entry -> do {
        rendered <- envelopeInstanceNameReservation limits maxProduced maxPrefix entry;
        envelopeBoundsAdd limits total rendered
      }) repeated (crateInstances iface)
    } };
    entryBounds <- if eqString (crateEntry iface) "" then Right envelopeZeroBounds
      else foldEither (\total owner -> do {
        rendered <- envelopeDefinitionReservation limits identity
          (Modules.Entity owner "<crate-entry>" Modules.Value);
        -- entryOwner invokes definitionName rather than the shared-prefix
        -- export helper, so encoded identity is produced for every candidate.
        one <- envelopeBoundsAdd limits identity rendered;
        envelopeBoundsAdd limits total one
      }) envelopeZeroBounds (crateModules iface);
    let { fixedSlice = stringLength "mlf:builtin-shared-haskell-v1:";
          sliced = if stringLength (crateId iface) >= fixedSlice then fixedSlice else 0 };
    envelopeBoundsSum limits [exports,instanceBounds,entryBounds,envelopeBounds sliced (4 * sliced)]
  };
  envelopeMetadataBounds limits iface = do {
    one <- envelopeMetadataValidationBounds limits iface;
    -- fromBinaryInterfaceFields validates actual; validateInterface validates
    -- expected. Exact structural pairing was checked before either call.
    envelopeBoundsTimes limits 2 one
  };
  data EnvelopeDeclaration = EnvelopeDeclaration DataDecl String Storage.RenderSummary;
  data EnvelopeDeclarationPool = EnvelopeDeclarationPool
    (Map String ([] EnvelopeDeclaration)) (Map String ((,) String Storage.RenderSummary))
    (Map String String) Int Int Int Int;
  envelopeEmptyDeclarationPool = EnvelopeDeclarationPool M.empty M.empty M.empty 0 0 0 0;
  envelopeFindDeclaration declaration entries = case entries of {
    [] -> Nothing;
    (:) (EnvelopeDeclaration saved text summary) rest ->
      if Equality.eqDataDecl declaration saved then Just ((,) text summary)
      else envelopeFindDeclaration declaration rest
  };
  envelopeRememberDeclaration limits declaration pool budget = case pool of {
    EnvelopeDeclarationPool typed texts names count memoCount scalars bytes ->
      let { name = D.datatypeName declaration; previous = M.findWithDefault compareString [] name typed } in
      case envelopeFindDeclaration declaration previous of {
        Just ((,) text _) -> Right ((,,) pool budget text);
        Nothing -> do {
          -- Scratch must be reserved BEFORE a canonical declaration String is formed.
          bounds <- Storage.v2MeasureDeclaration 16777216 16777216 declaration;
          nextBudget <- envelopeChargeRender limits 2 bounds budget;
          rendered <- Storage.v2RenderDeclarationText bounds declaration;
          case rendered of { (,) text summary -> do {
            envelopeBoundsWithin bounds summary;
            case M.lookup compareString name names of {
              Nothing -> Right ();
              Just expected -> ensure (eqString text expected) ("inconsistent crate datatype context: " ++ name)
            };
            nextMemoCount <- envelopeAdd "declaration memo entries" 65536 memoCount 1;
            let { canonical = case M.lookup compareString text texts of {
                    Just shared -> shared; Nothing -> (,) text summary } };
            admitted <- case M.lookup compareString text texts of {
              Just _ -> Right ((,,,) texts count scalars bytes);
              Nothing -> do {
                nextCount <- envelopeAdd "declaration pool entries" 65536 count 1;
                nextScalars <- envelopeAdd "declaration pool scalars" 134217728 scalars (Storage.renderSummaryScalars summary);
                nextBytes <- envelopeAdd "declaration pool UTF8 bytes" 134217728 bytes (Storage.renderSummaryUtf8 summary);
                Right ((,,,) (M.insert compareString text canonical texts) nextCount nextScalars nextBytes)
              }
            };
            case admitted of { (,,,) nextTexts nextCount nextScalars nextBytes ->
              let { nextTyped = M.insert compareString name ((:) (EnvelopeDeclaration declaration (fst canonical) (snd canonical)) previous) typed;
                    nextNames = M.insert compareString name (fst canonical) names } in
              Right ((,,) (EnvelopeDeclarationPool nextTyped nextTexts nextNames nextCount nextMemoCount nextScalars nextBytes)
                nextBudget (fst canonical))
            }
          } }
        }
      }
  };
  envelopeRememberDeclarations limits declarations pool budget done = case declarations of {
    [] -> Right ((,,) pool budget (reverse done));
    (:) declaration rest -> do {
      remembered <- envelopeRememberDeclaration limits declaration pool budget;
      case remembered of { (,,) next after text ->
        envelopeRememberDeclarations limits rest next after ((:) text done) }
    }
  };
  data EnvelopeFragmentRecord = EnvelopeFragmentRecord Separate.UnitObject ([] String) ([] String)
    Storage.RenderBounds Storage.RenderBounds Storage.RenderBounds Storage.RenderBounds;
  envelopePrepareFragments limits legacy raw pool budget done = case raw of {
    [] -> Right ((,,) pool budget (reverse done));
    (:) fragment rest -> do {
      header <- envelopeRememberDeclarations limits (Separate.unitData (Separate.objectInterface fragment)) pool budget [];
      case header of { (,,) headerPool headerBudget headerRefs -> do {
        body <- envelopeRememberDeclarations limits (Separate.objectContext fragment) headerPool headerBudget [];
        case body of { (,,) nextPool nextBudget bodyRefs -> do {
          full <- Storage.v2MeasureTerm (envelopeMaxRender limits) (envelopeMaxRender limits) (Separate.objectTerm fragment);
          charged <- envelopeChargeRender limits 0 full nextBudget;
          contextBound <- envelopePrefixBounds limits nextPool (Separate.objectContext fragment);
          bodyBound <- envelopeBodyBounds full contextBound;
          let { headerIface = if legacy then Separate.objectInterface fragment
                else Separate.withInterfaceData (Separate.objectInterface fragment) [] "0000000000-0000000000" };
          iface <- Storage.v2MeasureUnitInterface (envelopeMaxRender limits) (envelopeMaxRender limits) headerIface;
          prefix <- if legacy then Storage.v2MeasureUnitInterfacePrefix
            (envelopeMaxRender limits) (envelopeMaxRender limits) headerIface else Right envelopeZeroBounds;
          prefixCharged <- if legacy then envelopeChargeRender limits 2 prefix charged else Right charged;
          envelopePrepareFragments limits legacy rest nextPool prefixCharged
            ((:) (EnvelopeFragmentRecord fragment headerRefs bodyRefs full bodyBound iface prefix) done)
        } }
      } }
    }
  };
  envelopeDeclarationTexts (EnvelopeDeclarationPool _ texts _ _ _ _ _) = M.keys texts;
  envelopeDeclarationSummary :: EnvelopeDeclarationPool -> String -> Either String Storage.RenderSummary;
  envelopeDeclarationSummary (EnvelopeDeclarationPool _ texts _ _ _ _ _) text = case M.lookup compareString text texts of {
    Nothing -> Left "crate envelope declaration summary missing";
    Just ((,) _ summary) -> Right summary
  };
  envelopeReferenceBounds limits numbers texts = do {
    entries <- traverseEither (\text -> case M.lookup compareString text numbers of {
      Nothing -> Left "crate envelope declaration reference missing";
      Just index -> let { count = envelopeDecimalDigits index } in Right (envelopeBounds count count)
    }) texts;
    envelopePackBounds limits entries
  };
  envelopeRecordBounds limits legacy numbers (EnvelopeFragmentRecord fragment header body full bodyBound iface prefix) =
    if legacy then do {
      tag <- envelopeTextBounds limits "MLFO-1";
      name <- envelopeTextBounds limits (Separate.unitName (Separate.objectInterface fragment));
      object <- envelopePackBounds limits [tag,name,envelopeBounds 21 21,full];
      envelopePackBounds limits [iface,object]
    } else do {
      headerRefs <- envelopeReferenceBounds limits numbers header;
      bodyRefs <- envelopeReferenceBounds limits numbers body;
      tag <- envelopeTextBounds limits "MLFF-2";
      contents <- envelopePackBounds limits [tag,iface,bodyBound];
      envelopePackBounds limits [headerRefs,bodyRefs,contents]
    };
  envelopeObjectBounds limits legacy pool numbers records = do {
    encodedRecords <- traverseEither (envelopeRecordBounds limits legacy numbers) records;
    packedRecords <- envelopePackBounds limits encodedRecords;
    if legacy then Right packedRecords else do {
      declarations <- traverseEither (envelopeTextBounds limits) (envelopeDeclarationTexts pool);
      packedDeclarations <- envelopePackBounds limits declarations;
      envelopePackBounds limits [packedDeclarations,packedRecords]
    }
  };
  envelopeRenderReferences limits numbers texts = do {
    bounds <- envelopeReferenceBounds limits numbers texts;
    encoded <- traverseEither (\text -> case M.lookup compareString text numbers of {
      Nothing -> Left "crate envelope declaration reference missing";
      Just index -> envelopeLiteral limits (showInt index)
    }) texts;
    Storage.v2SummaryPack bounds encoded
  };
  envelopeCheckRecord limits legacy pool numbers record = case record of {
    EnvelopeFragmentRecord fragment headerRefs bodyRefs full bodyBound ifaceBound prefixBound -> do {
      checked <- Storage.v2CheckUnit full fragment;
      case checked of { (,) admitted fullSummary -> do {
        bodySummary <- envelopeActualBodySummary limits pool full fragment fullSummary;
        envelopeBoundsWithin bodyBound bodySummary;
        bounds <- envelopeRecordBounds limits legacy numbers record;
        summary <- if legacy then do {
          iface <- Storage.v2RenderUnitInterface ifaceBound (Separate.objectInterface fragment);
          prefix <- Storage.v2RenderUnitInterfacePrefix prefixBound (Separate.objectInterface fragment);
          tag <- envelopeLiteral limits "MLFO-1";
          name <- envelopeLiteral limits (Separate.unitName (Separate.objectInterface fragment));
          digest <- envelopeLiteral limits (envelopeDigest prefix);
          let { objectFields = [tag,name,digest,fullSummary] };
          objectBounds <- envelopePackBounds limits [envelopeBounds 6 6,
            envelopeBounds (Storage.renderSummaryScalars name) (Storage.renderSummaryUtf8 name),
            envelopeBounds 21 21,full];
          object <- Storage.v2SummaryPack objectBounds objectFields;
          Storage.v2SummaryPack bounds [iface,object]
        } else do {
          let { body = bodySummary;
                stripped = Separate.withInterfaceData (Separate.objectInterface fragment) [] (envelopeDigest body) };
          iface <- Storage.v2RenderUnitInterface ifaceBound stripped;
          tag <- envelopeLiteral limits "MLFF-2";
          contentsBounds <- envelopePackBounds limits [envelopeBounds 6 6,ifaceBound,bodyBound];
          contents <- Storage.v2SummaryPack contentsBounds [tag,iface,body];
          header <- envelopeRenderReferences limits numbers headerRefs;
          context <- envelopeRenderReferences limits numbers bodyRefs;
          Storage.v2SummaryPack bounds [header,context,contents]
        };
        envelopeBoundsWithin bounds summary;
        Right ((,,) admitted summary (Storage.renderSummaryEncoding bodySummary))
      } }
    }
  };
  data EnvelopeAdmission = EnvelopeAdmission CrateObject EnvelopeDeclarationPool
    ([] ((,) Separate.UnitObject (Maybe Separate.FingerprintEncoding))) EnvelopeRenderBudget String;
  envelopeAdmissionObject (EnvelopeAdmission object _ _ _ _) = object;
  envelopeAdmissionPool (EnvelopeAdmission _ pool _ _ _) = pool;
  envelopeAdmissionFragments (EnvelopeAdmission _ _ fragments _ _) = fragments;
  envelopeAdmissionBudget (EnvelopeAdmission _ _ _ budget _) = budget;
  envelopeAdmissionFingerprint (EnvelopeAdmission _ _ _ _ digest) = digest;
  envelopeAdmit limits legacy expected actual raw =
    mapEither envelopeAdmissionObject (envelopeAdmitDetailed limits legacy expected actual raw);
  envelopeAdmitDetailed limits legacy expected actual raw = do {
    envelopeExactMetadata expected actual;
    metadataBounds <- envelopeMetadataBounds limits actual;
    metadataBudget <- envelopeChargeRender limits 2 metadataBounds envelopeEmptyRenderBudget;
    -- Reserve checksum display Strings BEFORE any unit/record/object checking.
    -- Per actual bounded fragment: checkUnit, record body/interface digest,
    -- and a possible linked-fragment digest. Per artifact: whole digest twice
    -- plus one cached semantic digest. Read/write/selected conservatively use
    -- the same3F+3 allowance; no hidden fixed overhead outside the R cap.
    fragmentCount <- W.boundedLength (envelopeMaxFragments limits) raw;
    fragmentDigests <- envelopeMultiply "checksum display count" 2147483647 3 fragmentCount;
    digestCount <- envelopeAdd "checksum display count" 2147483647 fragmentDigests 3;
    digestBytes <- envelopeMultiply "checksum display reservation" (envelopeMaxRender limits) 21 digestCount;
    initialBudget <- envelopeChargeRender limits 2 (envelopeBounds digestBytes digestBytes) metadataBudget;
    initial <- if legacy then envelopeRememberDeclarations limits (crateLoweredData expected)
      envelopeEmptyDeclarationPool initialBudget []
      else Right ((,,) envelopeEmptyDeclarationPool initialBudget []);
    prepared <- case initial of { (,,) pool budget _ ->
      envelopePrepareFragments limits legacy raw pool budget [] };
    case prepared of { (,,) pool budget records -> do {
      let { declarations = envelopeDeclarationTexts pool;
            numbers = M.fromList compareString (zip declarations (range 0 (length declarations - 1))) };
      objectBounds <- envelopeObjectBounds limits legacy pool numbers records;
      finalBudget <- envelopeChargeRender limits 1 objectBounds budget;
      -- Every rendering reservation is now global and complete. No untrusted
      -- pretty/checkUnit/fingerprint path precedes its relevant reservation.
      seq finalBudget (Right ());
      _ <- fromBinaryInterfaceFields (binaryInterfaceFields actual);
      validateInterface expected;
      admitted <- traverseEither (envelopeCheckRecord limits legacy pool numbers) records;
      let { fragments = map (\((,,) fragment _ _) -> fragment) admitted;
            summaries = map (\((,,) _ summary _) -> summary) admitted;
            encodedBodies = map (\((,,) fragment _ body) -> (,) fragment (Just body)) admitted };
      recordBounds <- traverseEither (envelopeRecordBounds limits legacy numbers) records;
      packedBounds <- envelopePackBounds limits recordBounds;
      packed <- Storage.v2SummaryPack packedBounds summaries;
      complete <- if legacy then Right packed else do {
        declarationSummaries <- traverseEither (envelopeDeclarationSummary pool) declarations;
        declarationBounds <- traverseEither (envelopeTextBounds limits) declarations;
        poolBounds <- envelopePackBounds limits declarationBounds;
        poolSummary <- Storage.v2SummaryPack poolBounds declarationSummaries;
        Storage.v2SummaryPack objectBounds [poolSummary,packed]
      };
      envelopeBoundsWithin objectBounds complete;
      ensure (eqString (envelopeDigest complete) (crateObjectFingerprint expected)) "crate object checksum mismatch";
      Right (EnvelopeAdmission (EnvelopeCrateObject legacy expected fragments) pool encodedBodies finalBudget (envelopeDigest complete))
    } }
  };
  -- Same two rolling hashes, not a new checksum. These summaries are derived
  -- only inside admission from the actual independently checked full term and
  -- its exact ORIGINAL ordered root declaration prefix. Reappend is an
  -- arithmetic invariant, never evidence that an arbitrary caller's text matches.
  data EnvelopeSummaryParts = EnvelopeSummaryParts Int Int Int Int Int Int Int;
  envelopeSummaryParts summary = case summary of {
    Storage.RenderSummary scalars bytes encoding -> case encoding of {
      Separate.FingerprintEncoding count pa pb a b -> do {
        ensure (scalars >= 0 && bytes >= scalars && count == scalars &&
          pa > 0 && pa < 2147483647 && pb > 0 && pb < 2147483629 &&
          a >= 0 && a < 2147483647 && b >= 0 && b < 2147483629 &&
          pa == Separate.fingerprintPower 65599 count 2147483647 &&
          pb == Separate.fingerprintPower 131 count 2147483629)
          "crate envelope noncanonical fingerprint summary";
        seq scalars (seq bytes (seq count (seq pa (seq pb (seq a (seq b
          (Right (EnvelopeSummaryParts scalars bytes count pa pb a b))))))))
      }
    }
  };
  envelopeSameEncoding left right = case left of {
    Separate.FingerprintEncoding n pa pb a b -> case right of {
      Separate.FingerprintEncoding m qa qb c d -> n == m && pa == qa && pb == qb && a == c && b == d
    }
  };
  envelopePeelSummary full prefix = do {
    fullParts <- envelopeSummaryParts full;
    prefixParts <- envelopeSummaryParts prefix;
    case fullParts of { EnvelopeSummaryParts ns nb _ _ _ a b -> case prefixParts of {
      EnvelopeSummaryParts ps pb _ _ _ x y -> do {
        ensure (ps <= ns && pb <= nb) "crate envelope fingerprint prefix exceeds full term";
        let { count = ns - ps; bytes = nb - pb;
              powerA = Separate.fingerprintPower 65599 count 2147483647;
              powerB = Separate.fingerprintPower 131 count 2147483629;
              removedA = (x * powerA) % 2147483647;
              removedB = (y * powerB) % 2147483629;
              bodyA = (a + 2147483647 - removedA) % 2147483647;
              bodyB = (b + 2147483629 - removedB) % 2147483629;
              encoded = Separate.FingerprintEncoding count powerA powerB bodyA bodyB;
              result = Storage.RenderSummary count bytes encoded };
        _ <- envelopeSummaryParts result;
        let { rejoined = Separate.encodingAppend (Storage.renderSummaryEncoding prefix) encoded };
        ensure (envelopeSameEncoding rejoined (Storage.renderSummaryEncoding full) &&
          Storage.renderSummaryUtf8 prefix + bytes == Storage.renderSummaryUtf8 full)
          "crate envelope fingerprint prefix recomposition mismatch";
        Right result
      }
    } }
  };
  envelopeKnownDeclaration :: EnvelopeDeclarationPool -> DataDecl -> Either String ((,) String Storage.RenderSummary);
  envelopeKnownDeclaration pool declaration = case pool of {
    EnvelopeDeclarationPool typed _ _ _ _ _ _ ->
      case envelopeFindDeclaration declaration
        (M.findWithDefault compareString [] (D.datatypeName declaration) typed) of {
        Nothing -> Left "crate envelope actual declaration is absent from its bounded pool";
        Just value -> Right value
      }
  };
  envelopePrefixBounds limits pool declarations = foldEither (\acc declaration -> do {
    known <- envelopeKnownDeclaration pool declaration;
    let { summary = snd known };
    line <- envelopeBoundsAdd limits
      (envelopeBounds (Storage.renderSummaryScalars summary) (Storage.renderSummaryUtf8 summary))
      (envelopeBounds 1 1);
    envelopeBoundsAdd limits acc line
  }) envelopeZeroBounds declarations;
  envelopeBodyBounds full prefix = do {
    let { fs = Storage.renderBoundScalars full; fb = Storage.renderBoundUtf8 full;
          ps = Storage.renderBoundScalars prefix; pb = Storage.renderBoundUtf8 prefix };
    ensure (ps <= fs && pb <= fb) "crate envelope declaration prefix exceeds full render reservation";
    Right (envelopeBounds (fs - ps) (fb - pb))
  };
  envelopeActualPrefix limits pool fullBounds declarations = do {
    empty <- envelopeLiteral limits "";
    newline <- envelopeLiteral limits "\n";
    foldEither (\acc declaration -> do {
      known <- envelopeKnownDeclaration pool declaration;
      line <- Storage.v2SummaryAppend fullBounds (snd known) newline;
      Storage.v2SummaryAppend fullBounds acc line
    }) empty declarations
  };
  envelopeActualBodySummary limits pool fullBounds fragment full = case Separate.objectTerm fragment of {
    XWithData declarations _ -> do {
      prefix <- envelopeActualPrefix limits pool fullBounds declarations;
      envelopePeelSummary full prefix
    };
    _ -> Right full
  };
  -- Marked direct-link preparation always repeats physical/graph/resource and
  -- semantic admission. The constructor is provenance, never a receipt. These
  -- internal values are consumed by this call, not accepted from a caller.
  data EnvelopeLinkState proof = EnvelopeLinkState FragmentState proof
    EnvelopeDeclarationPool EnvelopeRenderBudget;
  envelopePrepareMarkedLink limits object = do {
    ensure (envelopeMarked object) "crate envelope link requires marked provenance";
    _ <- envelopePlan limits object;
    envelopeAdmitDetailed limits (envelopeLegacyObject object) (objectInterface object)
      (objectInterface object) (objectFragments object)
  };
  envelopeDeclarationRefs :: EnvelopeDeclarationPool -> [] DataDecl -> Either String ([] String);
  envelopeDeclarationRefs pool declarations = traverseEither
    (\declaration -> mapEither fst (envelopeKnownDeclaration pool declaration)) declarations;
  envelopeSameDeclarations :: EnvelopeDeclarationPool -> [] DataDecl -> [] DataDecl -> Either String Bool;
  envelopeSameDeclarations pool actual expected = do {
    left <- envelopeDeclarationRefs pool actual;
    right <- envelopeDeclarationRefs pool expected;
    Right (eqList eqString (sortStrings left) (sortStrings right))
  };
  envelopeContextState limits pool declarations = do {
    summary <- envelopeActualPrefix limits pool (envelopeFullBounds limits) declarations;
    Right (Separate.encodingState ((,) 0 1) (Storage.renderSummaryEncoding summary))
  };
  -- Incoming dependency-state declarations remain in their old host domain.
  -- Only a same-name declaration actually compared by this marked operation is
  -- admitted into its exact memo and charged before canonical text is formed.
  envelopeAdmitAdditionalDeclaration limits declaration pool budget = case pool of {
    EnvelopeDeclarationPool typed _ _ _ _ _ _ ->
      case envelopeFindDeclaration declaration
        (M.findWithDefault compareString [] (D.datatypeName declaration) typed) of {
        Just known -> Right ((,,) pool budget (fst known));
        Nothing -> do {
          _ <- W.planMeasured W.defaultLimits [Structure.toDataDecl declaration];
          envelopeRememberDeclaration limits declaration pool budget
        }
      }
  };
  envelopeMergeDeclaration limits pool budget declarations declaration =
    case filter (\other -> eqString (D.datatypeName other) (D.datatypeName declaration)) declarations of {
      [] -> Right ((,,) pool budget (snoc declarations declaration));
      (:) other [] -> do {
        remembered <- envelopeAdmitAdditionalDeclaration limits other pool budget;
        case remembered of { (,,) next charged otherText -> do {
          actual <- envelopeKnownDeclaration next declaration;
          ensure (eqString otherText (fst actual)) ("conflicting module datatype: " ++ D.datatypeName declaration);
          Right ((,,) next charged declarations)
        } }
      };
      _ -> Left ("conflicting module datatype: " ++ D.datatypeName declaration)
    };
  envelopeMergeDeclarations limits pool budget declarations additions =
    foldEither (\((,,) current charged ds) declaration ->
      envelopeMergeDeclaration limits current charged ds declaration)
      ((,,) pool budget declarations) additions;
  envelopeLinkFragmentWithSpine limits contexts allowedLayouts allowedSymbols ownSchemes
    (EnvelopeLinkState (FragmentState serial available bodies allData groups) proof pool budget) ((,) fragment encoded) =
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
      checked <- case fragment of {
        Separate.UnitObject _ term -> Checked.checkWithContexts contexts term;
        Separate.CheckedUnitObject _ checked -> Right checked
      };
      let { evidence = Checked.freshFragment serial checked };
      boundValueShared59 <- Right ((,,) (Checked.freshSerial evidence) (Checked.freshTerm evidence)
        (mapEither (map (\((,) n ty) -> (,) n (Separate.normalType ty))) (Checked.freshBindings evidence)));
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
            ensure (eqList Equality.eqDataDecl ds (Separate.objectContext fragment))
              "crate envelope freshening changed its datatype context";
            same <- envelopeSameDeclarations pool ds (Separate.unitData recorded);
            ensure same
              "inference fragment datatype context mismatch";
            traverseEither
              (\declaration ->
                 case M.lookup compareString (D.datatypeName declaration) allowedLayouts of {
                   Nothing ->
                     Left
                       ("inference fragment has an undeclared datatype: " ++
                        D.datatypeName declaration);
                   Just actual -> do {
                     known <- envelopeKnownDeclaration pool declaration;
                     ensure (eqString (fst known) (fst actual))
                       ("inference fragment datatype layout mismatch: " ++ D.datatypeName declaration)
                   }
                 })
              ds;
            prefixState <- envelopeContextState limits pool (Separate.objectContext fragment);
            bodyEncoding <- case encoded of {
              Nothing -> Left "crate envelope checked body summary missing";
              Just summary -> Right summary
            };
            ensure (eqString (Separate.encodingAfter prefixState bodyEncoding)
              (Separate.unitObjectFingerprint recorded)) "inference fragment checksum mismatch";
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
                  Checked.validateContext contexts ds;
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
                    nextProof = bindEither proof (\spine -> Checked.appendFreshSpine spine evidence);
                    ordinaryBody = Separate.mapTerm (\n -> M.findWithDefault X.compareName n n substitution)
                      (\a -> a) implementation;
                    linked = case nextProof of {
                      Left _ -> ordinaryBody;
                      Right spine -> case Checked.latestSpineBody spine of {
                        Nothing -> ordinaryBody;
                        Just body -> body
                      }
                    }
                  };
                  merged <- envelopeMergeDeclarations limits pool budget allData ds;
                  case merged of { (,,) nextPool nextBudget combined -> do {
                  let {
                    newBindings =
                      M.fromList compareString
                        (map (\((,) n ty) -> (,) (X.nameHint n) ((,) n ty)) own)
                  };
                  Right (EnvelopeLinkState
                    (FragmentState next (M.union compareString newBindings available)
                       ((:) linked bodies)
                       combined
                       (Set.insert compareString (Separate.unitName recorded) groups)) nextProof nextPool nextBudget)
                  } }
                }
            }
          }
      }
    };
  envelopeLinkCrateWithSpine interfaces allowedLayouts state object = do {
    admission <- envelopePrepareMarkedLink crateEnvelopeLimits object;
    result <- envelopeLinkCrateWithSpinePrepared interfaces allowedLayouts state admission;
    case result of { EnvelopeLinkState after proof _ _ -> Right ((,) after proof) }
  };
  envelopeLinkCrateWithSpinePrepared interfaces allowedLayouts ((,) state initialProof) admission =
    do {
      let { object = envelopeAdmissionObject admission };
      let {
        iface = objectInterface object
      };
      let {
        fragments = objectFragments (envelopeAdmissionObject admission)
      };
      let { prepared = (,) (envelopeAdmissionFingerprint admission) (envelopeAdmissionFragments admission) };
      ensure (eqString (fst prepared) (crateObjectFingerprint iface))
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
      let { contexts = Checked.contextPool (map Separate.objectContext fragments) };
      linked <- foldEither (\current fragment ->
        envelopeLinkFragmentWithSpine crateEnvelopeLimits contexts allowedLayouts allowedSymbols ownSchemes current fragment
      ) (EnvelopeLinkState state initialProof (envelopeAdmissionPool admission) (envelopeAdmissionBudget admission)) (snd prepared);
      case linked of { EnvelopeLinkState after nextProof _ _ -> do {
      let {
        own =
          filter (\n -> not (Set.member compareString n before)) (M.keys (fragmentBindings after))
      };
      ensure (eqList eqString (sortStrings own) (sortStrings (map fst (crateBindings iface))))
        "crate object declaration inventory mismatch";
      Right linked
      } }
    };
  envelopeLinkSelectedCrateWithSpine selected interfaces allowedLayouts state object = do {
    admission <- envelopePrepareMarkedLink crateEnvelopeLimits object;
    result <- envelopeLinkSelectedCrateWithSpinePrepared selected interfaces allowedLayouts state admission;
    case result of { EnvelopeLinkState after proof _ _ -> Right ((,) after proof) }
  };
  envelopeLinkSelectedCrateWithSpinePrepared selected interfaces allowedLayouts ((,) state initialProof) admission =
    do {
      let { object = envelopeAdmissionObject admission };
      let {
        iface = objectInterface object
      };
      let {
        fragments = objectFragments (envelopeAdmissionObject admission)
      };
      let { prepared = (,) (envelopeAdmissionFingerprint admission) (envelopeAdmissionFragments admission) };
      ensure (eqString (fst prepared) (crateObjectFingerprint iface))
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
      let { contexts = Checked.contextPool (map Separate.objectContext fragments) };
      uniqueNames "crate inference fragment" (map (compose Separate.unitName Separate.objectInterface) fragments);
      traverseEither (\fragment -> let { recorded = Separate.objectInterface fragment } in
        ensure (null (Separate.unitClasses recorded) && null (Separate.unitInstances recorded) && null (Separate.unitExports recorded))
          "inference fragment contains source visibility metadata") fragments;
      ensure (all (\key -> not (Set.member compareString key before)) (map fst (crateBindings iface)))
        "crate selected inventory overlaps existing bindings";
      chosen <- selectFragmentClosure selected before (snd prepared);
      uniqueNames "crate fragment binding" (concatMap (compose (map fst) (compose Separate.unitBindings Separate.objectInterface)) fragments);
      ensure (sameSchemes (concatMap (compose Separate.unitBindings Separate.objectInterface) fragments) (crateBindings iface))
        "crate object declaration inventory mismatch";
      linked <- foldEither (\current fragment ->
        envelopeLinkFragmentWithSpine crateEnvelopeLimits contexts allowedLayouts allowedSymbols ownSchemes current fragment
      ) (EnvelopeLinkState state initialProof (envelopeAdmissionPool admission) (envelopeAdmissionBudget admission)) chosen;
      case linked of { EnvelopeLinkState after nextProof _ _ -> do {
      let {
        own =
          filter (\n -> not (Set.member compareString n before)) (M.keys (fragmentBindings after))
      };
      ensure (eqList eqString (sortStrings own) (sortStrings (concatMap (compose (map fst) (compose Separate.unitBindings (compose Separate.objectInterface fst))) chosen)))
        "crate object declaration inventory mismatch";
      Right linked
      } }
    };
  -- Closed, same-domain semantic metadata hashing
  -- for marked artifacts. A budget belongs to one marked artifact/operation;
  -- it is NOT a bound on an arbitrary dependency-file closure's total RSS.
  -- Exact entity text is materialized once, after reservation, only because
  -- the old ABI sorts by entityEncoding text. The root remains a summary.
  envelopeEntityKey limits budget entity = do {
    bounds <- Storage.v2Measure (envelopeMaxRender limits) (envelopeMaxRender limits) (Storage.V2Entity entity);
    charged <- envelopeChargeRender limits 2 bounds budget;
    let { text = Separate.entityEncoding entity };
    actual <- envelopeTextBounds limits text;
    ensure (Storage.renderBoundScalars actual <= Storage.renderBoundScalars bounds &&
      Storage.renderBoundUtf8 actual <= Storage.renderBoundUtf8 bounds)
      "crate envelope entity key exceeds reservation";
    Right ((,) charged ((,) entity text))
  };
  envelopeEntityKeys limits budget entities done = case entities of {
    [] -> Right ((,) budget (reverse done));
    (:) entity rest -> do {
      result <- envelopeEntityKey limits budget entity;
      case result of { (,) next keyed -> envelopeEntityKeys limits next rest ((:) keyed done) }
    }
  };
  envelopeExportKeys limits budget exports done = case exports of {
    [] -> Right ((,) budget (sortPairs (reverse done)));
    (:) ((,) owner entities) rest -> do {
      result <- envelopeEntityKeys limits budget entities [];
      case result of { (,) next keyed ->
        let { ordered = sortBy (\a b -> compareString (snd a) (snd b)) keyed } in
        envelopeExportKeys limits next rest ((:) ((,) owner ordered) done)
      }
    }
  };
  envelopeEncodedIdentity limits budget identity = do {
    bound <- envelopeMultiply "semantic identity rendering" (envelopeMaxRender limits) 8 (stringLength identity);
    charged <- envelopeChargeRender limits 2 (envelopeBounds bound bound) budget;
    let { encoded = Separate.encoded identity };
    ensure (stringLength encoded <= bound) "crate envelope encoded identity exceeds reservation";
    Right ((,) charged encoded)
  };
  envelopePublicName limits budget encodedIdentity entity key = do {
    encodedKey <- envelopeMultiply "semantic entity name" (envelopeMaxRender limits) 8 (stringLength key);
    bound <- envelopeAdd "semantic entity name" (envelopeMaxRender limits) encodedKey (stringLength encodedIdentity + 128);
    -- Separate.encoded(key), or the stable branch's encoded owner/spelling,
    -- is a materialized temporary in addition to the final generated name.
    reservation <- envelopeBoundsAdd limits (envelopeBounds encodedKey encodedKey) (envelopeBounds bound bound);
    charged <- envelopeChargeRender limits 2 reservation budget;
    let { name = case Separate.managedBuiltinName entity of {
      Just builtin -> builtin;
      Nothing -> if eqString (Modules.owner entity) "Prelude" || Modules.isRole Modules.BuiltinType entity
        then Separate.stableName entity
        else (if Modules.compareSpace (Modules.space entity) Modules.Types == 0 ||
          (case Modules.role entity of { Modules.Constructor _ -> True; _ -> False })
          then "Module_" else "module_") ++ encodedIdentity ++ "z_" ++ Separate.encoded key
    } };
    actual <- envelopeTextBounds limits name;
    ensure (Storage.renderBoundScalars actual <= bound && Storage.renderBoundUtf8 actual <= bound)
      "crate envelope public name exceeds reservation";
    Right ((,) charged name)
  };
  envelopePublicNames limits budget encodedIdentity keyed done = case keyed of {
    [] -> Right ((,) budget (Set.fromList compareString (reverse done)));
    (:) ((,) entity key) rest -> do {
      result <- envelopePublicName limits budget encodedIdentity entity key;
      case result of { (,) next name -> envelopePublicNames limits next encodedIdentity rest ((:) name done) }
    }
  };
  envelopeSourceMetadataTask declarations classes instances = Storage.V2Many
    (append (concatMap (\declaration -> [Storage.V2Declaration declaration,Storage.V2Text "\n"]) (sortData declarations))
      (append (concatMap (\klass -> [Storage.V2Class klass,Storage.V2Text "\n"]) (sortClasses classes))
        (concatMap (\entry -> [Storage.V2Instance (snd entry),Storage.V2Text "\n"]) (sortPairs instances))));
  envelopeSemanticTask iface keyedExports publicNames =
    let {
      exported = concatMap (map fst) (map snd keyedExports);
      public = filter (\entry -> Set.member compareString (fst entry) publicNames) (crateBindings iface);
      exports = Storage.V2Pack (map (\((,) owner entries) -> Storage.V2Pack
        [Storage.V2Text owner,Storage.V2Pack (map (compose Storage.V2Text snd) entries)]) keyedExports);
      imports = Storage.V2Pack (map (\((,) owner names) -> Storage.V2Pack
        [Storage.V2Text owner,Storage.V2Pack (map Storage.V2Text (sortStrings names))]) (sortPairs (crateImports iface)));
      layouts = Storage.V2Many (concatMap (\declaration -> [Storage.V2Declaration declaration,Storage.V2Text "\n"])
        (sortData (crateLoweredData iface)));
      bindings = Storage.V2Pack (map Storage.V2InterfaceBinding (sortPairs public));
      protection = Storage.V2Pack (map (\((,) name protected) -> Storage.V2Pack
        [Storage.V2Text name,Storage.V2Text (if protected then "true" else "false")])
        (sortPairs (filter (\entry -> Set.member compareString (fst entry) publicNames) (crateProtection iface))));
      dependencies = Storage.V2Pack (if any (\entity -> not (elem eqString (Modules.owner entity) (crateModules iface))) exported
        then map (\((,,) name _ semantic) -> Storage.V2Pack [Storage.V2Text name,Storage.V2Text semantic])
          (sortDependencies (crateDependencies iface)) else [])
    } in Storage.V2Pack [Storage.V2Text "MLF-CRATE-SEMANTICS-5",Storage.V2Text (crateId iface),exports,imports,
      envelopeSourceMetadataTask (crateData iface) (crateClasses iface) (crateInstances iface),
      Storage.V2Pack (map (compose Storage.V2Text fst) (sortPairs (crateInstances iface))),
      layouts,bindings,protection,dependencies];
  envelopeSemanticFingerprint limits budget iface = do {
    keyed <- envelopeExportKeys limits budget (crateExports iface) [];
    case keyed of { (,) afterKeys exports -> do {
      identity <- envelopeEncodedIdentity limits afterKeys (crateId iface);
      case identity of { (,) afterIdentity encodedIdentity -> do {
        names <- envelopePublicNames limits afterIdentity encodedIdentity (concatMap snd exports) [];
        case names of { (,) afterNames publicNames -> do {
          let { task = envelopeSemanticTask iface exports publicNames };
          bounds <- Storage.v2Measure (envelopeMaxRender limits) (envelopeMaxRender limits) task;
          charged <- envelopeChargeRender limits 2 bounds afterNames;
          summary <- Storage.v2Render bounds task;
          envelopeBoundsWithin bounds summary;
          Right ((,) charged (envelopeDigest summary))
        } }
      } }
    } }
  };
  -- Mixed object linking carries provenance from the actual object table.
  -- A separately supplied metadata map does not manufacture this association.
  -- Each marked artifact retains ONE admission/pool/render ledger through all
  -- object-derived serialization phases. Legacy artifacts retain old policies.
  data EnvelopeLinkArtifact = EnvelopeLinkArtifact EnvelopeAdmission (Maybe String);
  envelopeReplaceAdmission pool budget (EnvelopeAdmission object _ fragments _ digest) =
    EnvelopeAdmission object pool fragments budget digest;
  envelopeLinkAdmission (EnvelopeLinkArtifact admission _) = admission;
  envelopeCollectLinkAdmissions objectMap ordered done = case ordered of {
    [] -> Right done;
    (:) iface rest -> case M.lookup compareString (crateId iface) objectMap of {
      Nothing -> Left "missing crate object";
      Just object -> if envelopeMarked object then do {
        admission <- envelopePrepareMarkedLink crateEnvelopeLimits object;
        envelopeCollectLinkAdmissions objectMap rest
          (M.insert compareString (crateId iface) (EnvelopeLinkArtifact admission Nothing) done)
      } else envelopeCollectLinkAdmissions objectMap rest done
    }
  };
  envelopeDependencyFingerprint table actual = case M.lookup compareString (crateId actual) table of {
    Nothing -> Right ((,) table (semanticFingerprint actual));
    Just (EnvelopeLinkArtifact admission cached) -> do {
      -- Identity lookup selects an entry; exact projection establishes pairing.
      envelopeExactMetadata (objectInterface (envelopeAdmissionObject admission)) actual;
      case cached of {
        Just digest -> Right ((,) table digest);
        Nothing -> do {
          encoded <- envelopeSemanticFingerprint crateEnvelopeLimits (envelopeAdmissionBudget admission) actual;
          case encoded of { (,) budget digest ->
            let { next = envelopeReplaceAdmission (envelopeAdmissionPool admission) budget admission } in
            Right ((,) (M.insert compareString (crateId actual)
              (EnvelopeLinkArtifact next (Just digest)) table) digest)
          }
        }
      }
    }
  };
  envelopeValidateDependencies interfaces table iface = foldEither
    (\current dependency -> case M.lookup compareString (dependencyId dependency) interfaces of {
      Nothing -> Left ("missing crate dependency: " ++ dependencyId dependency);
      Just actual -> do {
        ensure (eqString (crateId actual) (dependencyId dependency)) "crate dependency identity mismatch";
        encoded <- envelopeDependencyFingerprint current actual;
        case encoded of { (,) next digest -> do {
          ensure (eqString (dependencySemantic dependency) digest)
            ("stale crate dependency interface: " ++ crateId iface ++ " requires a different " ++
             dependencyId dependency ++ "; recompile " ++ crateId iface);
          Right next
        } }
      }
    }) table (crateDependencies iface);
  envelopeRememberLinkDeclaration table owner declaration = case M.lookup compareString owner table of {
    Nothing -> Left "crate envelope declaration owner is not admitted";
    Just (EnvelopeLinkArtifact admission digest) -> do {
      -- Generated or inherited declaration ASTs have not necessarily occurred in
      -- the wire graph. Apply unchanged single-graph admission before rendering;
      -- retained canonical text/memo and render work share the artifact ledger.
      remembered <- envelopeAdmitAdditionalDeclaration crateEnvelopeLimits declaration
        (envelopeAdmissionPool admission) (envelopeAdmissionBudget admission);
      case remembered of { (,,) pool budget text -> do {
        known <- envelopeKnownDeclaration pool declaration;
        let { next = envelopeReplaceAdmission pool budget admission };
        Right ((,,) (M.insert compareString owner (EnvelopeLinkArtifact next digest) table) text (snd known))
      } }
    }
  };
  envelopeGeneratedOwners table interfaces = foldl
    (\owners iface -> if M.member compareString (crateId iface) table then
      foldl (\current name -> M.insert compareString name (crateId iface) current) owners
        (append (map D.datatypeName (crateData iface))
          (map (\klass -> "Dict_" ++ Classes.className klass) (crateClasses iface)))
      else owners) M.empty interfaces;
  envelopeGeneratedTexts owners table declarations done = case declarations of {
    [] -> Right ((,) table (reverse done));
    (:) declaration rest -> case M.lookup compareString (D.datatypeName declaration) owners of {
      Nothing -> envelopeGeneratedTexts owners table rest ((:) (D.prettyDeclaration declaration) done);
      Just owner -> do {
        remembered <- envelopeRememberLinkDeclaration table owner declaration;
        case remembered of { (,,) next text _ -> envelopeGeneratedTexts owners next rest ((:) text done) }
      }
    }
  };
  envelopeRecordedTexts table interfaces done = case interfaces of {
    [] -> Right ((,) table (reverse done));
    (:) iface rest -> if M.member compareString (crateId iface) table then do {
      result <- foldEither (\((,) current texts) declaration -> do {
        remembered <- envelopeRememberLinkDeclaration current (crateId iface) declaration;
        case remembered of { (,,) next text _ -> Right ((,) next ((:) text texts)) }
      }) ((,) table done) (crateLoweredData iface);
      case result of { (,) next texts -> envelopeRecordedTexts next rest texts }
    } else envelopeRecordedTexts table rest
      (foldl (\texts declaration -> (:) (D.prettyDeclaration declaration) texts) done (crateLoweredData iface))
  };
  envelopeValidateLayouts table interfaces = do {
    -- This introduced routing map materializes its OWN Dict_ keys, distinct
    -- from lowerer internals and later entry/Prelude dictionary-name passes.
    reserved <- envelopeReserveSourceNames 0 1 table;
    lowered <- Classes.lowerSeparateClasses M.empty
      (concatMap (\iface -> map fst (crateInstances iface)) interfaces)
      (SClassProgram (concatMap crateData interfaces) (concatMap crateClasses interfaces)
        (concatMap (\iface -> map snd (crateInstances iface)) interfaces) (SConstructor "()"));
    expected <- case fst lowered of { SProgram declarations _ -> Right declarations;
      _ -> Left "invalid crate class metadata" };
    let { recorded = concatMap crateLoweredData interfaces;
          owners = envelopeGeneratedOwners reserved interfaces };
    expectedTexts <- envelopeGeneratedTexts owners reserved expected [];
    case expectedTexts of { (,) afterExpected left -> do {
      recordedTexts <- envelopeRecordedTexts afterExpected interfaces [];
      case recordedTexts of { (,) afterRecorded right -> do {
        ensure (eqList eqString (sortStrings left) (sortStrings right))
          "crate lowered datatype metadata mismatch";
        _ <- D.validateDeclarations recorded;
        Right afterRecorded
      } }
    } }
  };
  envelopeDatatypePart pool declaration = do {
    known <- envelopeKnownDeclaration pool declaration;
    newline <- envelopeLiteral crateEnvelopeLimits "\n";
    line <- Storage.v2SummaryAppend (envelopeFullBounds crateEnvelopeLimits) (snd known) newline;
    case Storage.renderSummaryEncoding line of {
      Separate.FingerprintEncoding _ pa pb a b -> Right ((,) (fst known) ((,,,) pa pb a b))
    }
  };
  envelopeLayoutMap table interfaces = foldEither
    (\layouts iface -> foldEither (\current declaration -> do {
      part <- case M.lookup compareString (crateId iface) table of {
        Nothing -> Right (datatypePart declaration);
        Just artifact -> envelopeDatatypePart (envelopeAdmissionPool (envelopeLinkAdmission artifact)) declaration
      };
      Right (M.insert compareString (D.datatypeName declaration) part current)
    }) layouts (crateLoweredData iface)) M.empty interfaces;
  -- linkEntry repeats instanceOwner's encoded module-prefix scans and root
  -- entryOwner's generated name comparisons. Charge before the old entry
  -- semantic checker is invoked, not after its temporary names are formed.
  envelopeEntryOwnerBounds limits root iface = do {
    identity <- envelopeMultiply "entry identity encoding" (envelopeMaxRender limits) 8 (stringLength (crateId iface));
    modules <- foldEither (\sum owner -> do {
      encoded <- envelopeMultiply "entry module encoding" (envelopeMaxRender limits) 8 (stringLength owner);
      prefix <- envelopeAdd "entry instance prefix" (envelopeMaxRender limits) identity (encoded + 128);
      envelopeAdd "entry prefix scans" (envelopeMaxRender limits) sum prefix
    }) 0 (crateModules iface);
    instances <- W.boundedLength (W.maxEdges W.defaultLimits) (crateInstances iface);
    instanceBytes <- envelopeMultiply "entry instance owner scans" (envelopeMaxRender limits) instances modules;
    entryBytes <- if eqString root (crateId iface) then foldEither (\sum owner -> do {
      key <- Storage.v2Measure (envelopeMaxRender limits) (envelopeMaxRender limits)
        (Storage.V2Entity (Modules.Entity owner "<crate-entry>" Modules.Value));
      encoded <- envelopeMultiply "entry entity encoding" (envelopeMaxRender limits) 8 (Storage.renderBoundScalars key);
      name <- envelopeAdd "entry generated name" (envelopeMaxRender limits) identity (encoded + 128);
      -- entityEncoding temporary text and final encoded name both materialize.
      total <- envelopeAdd "entry key and name" (envelopeMaxRender limits) name (Storage.renderBoundUtf8 key);
      envelopeAdd "entry owner scans" (envelopeMaxRender limits) sum total
    }) 0 (crateModules iface) else Right 0;
    total <- envelopeAdd "entry owner formatting" (envelopeMaxRender limits) instanceBytes entryBytes;
    -- Reserve the encoded scalar temporaries as well as final owner/name
    -- strings. Logical-byte bounds do not claim boxed String allocation size.
    materialized <- envelopeMultiply "entry owner formatting temporaries" (envelopeMaxRender limits) 3 total;
    -- entrySignatures tests select_(7), super_(6), instance_(9); the selected
    -- sourceScheme map tests stringSlice name0 7 again. Charge all four sites
    -- for EVERY actual binding, a superset of short-circuited/selected/deduped
    -- cases. Failing prefix slices can contain4-byte Unicode scalars.
    bindings <- W.boundedLength (W.maxEdges W.defaultLimits) (crateBindings iface);
    sliceScalars <- envelopeMultiply "entry binding-prefix slice scalars" (envelopeMaxRender limits) 29 bindings;
    sliceBytes <- envelopeMultiply "entry binding-prefix slice UTF8" (envelopeMaxRender limits) 116 bindings;
    envelopeBoundsAdd limits (envelopeBounds materialized materialized) (envelopeBounds sliceScalars sliceBytes)
  };
  envelopePrechargeEntry root table interfaces = foldEither
    (\current iface -> case M.lookup compareString (crateId iface) current of {
      Nothing -> Right current;
      Just (EnvelopeLinkArtifact admission digest) -> do {
        owners <- envelopeEntryOwnerBounds crateEnvelopeLimits root iface;
        generated <- envelopeSourceNameBounds crateEnvelopeLimits 1 1 iface;
        bounds <- envelopeBoundsAdd crateEnvelopeLimits owners generated;
        budget <- envelopeChargeRender crateEnvelopeLimits 2 bounds (envelopeAdmissionBudget admission);
        Right (M.insert compareString (crateId iface)
          (EnvelopeLinkArtifact (envelopeReplaceAdmission (envelopeAdmissionPool admission) budget admission) digest) current)
      }
    }) table interfaces;
  envelopeLinkCheckedObjects objects root = do {
    uniqueNames "object identity" (map (\object -> crateId (objectInterface object)) objects);
    let { interfaces = map objectInterface objects;
          byName = interfaceMap interfaces;
          objectMap = M.fromList compareString (map (\object -> (,) (crateId (objectInterface object)) object) objects) };
    ordered <- dependencyClosure byName [] [] [root];
    initial <- envelopeCollectLinkAdmissions objectMap ordered M.empty;
    dependencies <- foldEither (envelopeValidateDependencies byName) initial ordered;
    _ <- traverseEither (validateExportBoundary byName) ordered;
    layoutsChecked <- envelopeValidateLayouts dependencies ordered;
    layouts <- envelopeLayoutMap layoutsChecked ordered;
    program <- openProgram ordered objectMap root;
    linked <- foldEither (\((,) state table) iface ->
      case M.lookup compareString (crateId iface) objectMap of {
        Nothing -> Left "missing crate object";
        Just object -> case M.lookup compareString (crateId iface) table of {
          Nothing -> mapEither (\next -> (,) next table) (linkProgramCrate program byName layouts state object);
          Just (EnvelopeLinkArtifact admission digest) -> do {
            result <- envelopeLinkCrateWithSpinePrepared byName layouts
              ((,) state (Left "ordinary crate linking has no composition receipt")) admission;
            case result of { EnvelopeLinkState next _ pool budget ->
              Right ((,) next (M.insert compareString (crateId iface)
                (EnvelopeLinkArtifact (envelopeReplaceAdmission pool budget admission) digest) table))
            }
          }
        }
      }) ((,) (FragmentState 0 M.empty [] [] Set.empty) layoutsChecked) ordered;
    case linked of { (,) state table -> do {
      let { rootInterface = M.findWithDefault compareString (panic "missing root crate") root byName };
      -- Empty entry returns before all owner scans in the original function.
      charged <- if eqString (crateEntry rootInterface) "" then Right table
        else envelopePrechargeEntry root table ordered;
      seq charged (Right ());
      entry <- linkEntry (fragmentSerial state) ordered rootInterface (fragmentBindings state) (crateEntry rootInterface);
      body <- foldEither (\body declarations -> Separate.graft declarations body) entry (fragmentBodies state);
      Checked.check (XWithData (fragmentData state) body)
    } }
  };
  -- Safe object-known entrypoints. No caller-supplied EnvelopeAdmission,
  -- summary, marker-only receipt or mutable metadata/provenance pairing is
  -- accepted as authority. Every call starts with the actual objects and owns
  -- fresh graph/semantic admission through its metadata and linking operation.
  -- Callers retain their exact legacy-only bodies; these APIs cover mixed/v2.
  -- Repeated public calls deliberately repeat admission and have separate
  -- per-operation ledgers; they are not an aggregate dependency-closure cap.
  data EnvelopeKnownObjects = EnvelopeKnownObjects ([] CrateInterface)
    (Map String CrateInterface) (Map String CrateObject)
    (Map String EnvelopeLinkArtifact)
    (Map String ((,) String ((,,,) Int Int Int Int)));
  envelopePrepareKnownObjects objects roots checkLegacyInterfaces = do {
    uniqueNames "object identity" (map (\object -> crateId (objectInterface object)) objects);
    let { interfaces = map objectInterface objects;
          byName = interfaceMap interfaces;
          objectMap = M.fromList compareString (map (\object -> (,) (crateId (objectInterface object)) object) objects) };
    ordered <- dependencyClosure byName [] [] roots;
    initial <- envelopeCollectLinkAdmissions objectMap ordered M.empty;
    _ <- if checkLegacyInterfaces then traverseEither (\iface ->
      if M.member compareString (crateId iface) initial then Right () else validateInterface iface) ordered
      else Right [];
    dependencies <- foldEither (envelopeValidateDependencies byName) initial ordered;
    _ <- traverseEither (validateExportBoundary byName) ordered;
    checked <- envelopeValidateLayouts dependencies ordered;
    layouts <- envelopeLayoutMap checked ordered;
    Right (EnvelopeKnownObjects ordered byName objectMap checked layouts)
  };
  envelopeFoldKnownObjects prepared initial = case prepared of {
    EnvelopeKnownObjects ordered byName objectMap admissions layouts ->
      foldEither (\((,,) state proof table) iface -> case M.lookup compareString (crateId iface) objectMap of {
        Nothing -> Left "missing crate object";
        Just object -> case M.lookup compareString (crateId iface) table of {
          Nothing -> do {
            result <- linkCrateWithSpine byName layouts ((,) state proof) object;
            Right ((,,) (fst result) (snd result) table)
          };
          Just (EnvelopeLinkArtifact admission digest) -> do {
            result <- envelopeLinkCrateWithSpinePrepared byName layouts ((,) state proof) admission;
            case result of { EnvelopeLinkState next nextProof pool budget ->
              Right ((,,) next nextProof (M.insert compareString (crateId iface)
                (EnvelopeLinkArtifact (envelopeReplaceAdmission pool budget admission) digest) table))
            }
          }
        }
      }) ((,,) (fst initial) (snd initial) admissions) ordered
  };
  linkKnownObjectsWithSpine objects roots initial = do {
    prepared <- envelopePrepareKnownObjects objects roots False;
    linked <- envelopeFoldKnownObjects prepared initial;
    case linked of { (,,) state proof _ -> Right ((,) state proof) }
  };
  linkKnownSelectedObjectWithSpine selected object initial = do {
    prepared <- envelopePrepareKnownObjects [object] [crateId (objectInterface object)] True;
    case prepared of { EnvelopeKnownObjects _ byName _ table layouts ->
      case M.lookup compareString (crateId (objectInterface object)) table of {
        Nothing -> linkSelectedCrateWithSpine selected byName layouts initial object;
        Just artifact -> do {
          linked <- envelopeLinkSelectedCrateWithSpinePrepared selected byName layouts initial
            (envelopeLinkAdmission artifact);
          case linked of { EnvelopeLinkState state proof _ _ -> Right ((,) state proof) }
        }
      }
    }
  };
  validateKnownObjectHeaders objects roots = do {
    _ <- envelopePrepareKnownObjects objects roots True;
    Right ()
  };
  -- Exact ordered merge: retain the first AST, including non-textual schema
  -- distinctions, and compare canonical TEXT on a same-name hit. Marked input
  -- text is freshly interned before this loop; legacy text keeps its old domain.
  envelopeKnownDeclarationMerge declarations texts declaration text =
    case filter (\other -> eqString (D.datatypeName other) (D.datatypeName declaration)) declarations of {
      [] -> Right ((,) (snoc declarations declaration)
        (M.insert compareString (D.datatypeName declaration) text texts));
      (:) _ [] -> case M.lookup compareString (D.datatypeName declaration) texts of {
        Nothing -> Left "crate envelope merged declaration text missing";
        Just previous -> do {
          ensure (eqString previous text) ("conflicting module datatype: " ++ D.datatypeName declaration);
          Right ((,) declarations texts)
        }
      };
      _ -> Left ("conflicting module datatype: " ++ D.datatypeName declaration)
    };
  envelopeMergeKnownObjectDeclarations objects table = do {
    -- Preserve CALLER object order, not dependency order, as the old native
    -- declaration fold does. Validated layouts already preserve multisets.
    result <- foldEither (\state object -> foldEither (\current declaration -> do {
      text <- case M.lookup compareString (crateId (objectInterface object)) table of {
        Nothing -> Right (D.prettyDeclaration declaration);
        Just artifact -> mapEither fst (envelopeKnownDeclaration
          (envelopeAdmissionPool (envelopeLinkAdmission artifact)) declaration)
      };
      envelopeKnownDeclarationMerge (fst current) (snd current) declaration text
    }) state (crateLoweredData (objectInterface object))) ((,) [] M.empty) objects;
    Right (fst result)
  };
  knownObjectDeclarations objects = do {
    prepared <- envelopePrepareKnownObjects objects (map (compose crateId objectInterface) objects) True;
    case prepared of { EnvelopeKnownObjects _ _ _ table _ ->
      envelopeMergeKnownObjectDeclarations objects table }
  };
  -- Native library composition owns ONE admission and budget through spine
  -- linking AND caller-order declaration merge. Do not compose two separately
  -- reset512Mi public operations while describing them as this single ledger.
  linkKnownObjectsWithSpineAndDeclarations objects roots initial = do {
    prepared <- envelopePrepareKnownObjects objects roots False;
    linked <- envelopeFoldKnownObjects prepared initial;
    case linked of { (,,) state proof table -> do {
      -- Require every supplied marked object to have been selected by roots;
      -- otherwise its lowered data has no admission in this operation.
      ensure (all (\object -> not (envelopeMarked object) ||
        M.member compareString (crateId (objectInterface object)) table) objects)
        "crate envelope native declaration object is outside selected roots";
      declarations <- envelopeMergeKnownObjectDeclarations objects table;
      Right ((,) ((,) state proof) declarations)
    } }
  };
  -- Fixed future sourceSchemeIn name-materialization pass, derived from actual
  -- admitted binding types. Every XVar/XForall creates at most21 ASCII scalars
  -- ('a' plus an Int64 decimal token), including the unchanged wrapping ID
  -- arithmetic. Boxed String copies and inferred/generated ASTs are not byte-
  -- for-byte RSS promises. No caller-supplied occurrence count is accepted.
  envelopeSourceNameOccurrences limits pending visited names = case pending of {
    [] -> Right names;
    (:) values rest -> case values of {
      [] -> envelopeSourceNameOccurrences limits rest visited names;
      (:) ty more -> do {
        next <- envelopeAdd "source scheme type occurrences" (envelopeMaxNodes limits) visited 1;
        case ty of {
          XVar _ -> do {
            count <- envelopeAdd "source scheme generated names" (envelopeMaxNodes limits) names 1;
            envelopeSourceNameOccurrences limits ((:) more rest) next count
          };
          XForall _ bound body -> do {
            count <- envelopeAdd "source scheme generated names" (envelopeMaxNodes limits) names 1;
            envelopeSourceNameOccurrences limits ((:) [bound,body] ((:) more rest)) next count
          };
          XArrow a b -> envelopeSourceNameOccurrences limits ((:) [a,b] ((:) more rest)) next names;
          XApply a b -> envelopeSourceNameOccurrences limits ((:) [a,b] ((:) more rest)) next names;
          XCon _ arguments -> envelopeSourceNameOccurrences limits ((:) arguments ((:) more rest)) next names;
          _ -> envelopeSourceNameOccurrences limits ((:) more rest) next names
        }
      }
    }
  };
  envelopeSourceNameBounds limits schemePasses dictionaryPasses iface = do {
    occurrences <- envelopeSourceNameOccurrences limits [map snd (crateBindings iface)] 0 0;
    oneScheme <- envelopeMultiply "source scheme generated-name scalars" (envelopeMaxRender limits) 21 occurrences;
    schemes <- envelopeMultiply "source scheme materialization passes" (envelopeMaxRender limits) schemePasses oneScheme;
    oneDictionary <- foldEither (\total klass -> do {
      bytes <- W.utf8Size (envelopeMaxRender limits) (Classes.className klass);
      name <- envelopeAdd "dictionary name prefix" (envelopeMaxRender limits) bytes 5;
      envelopeAdd "dictionary names" (envelopeMaxRender limits) total name
    }) 0 (crateClasses iface);
    dictionaries <- envelopeMultiply "dictionary name materialization passes" (envelopeMaxRender limits) dictionaryPasses oneDictionary;
    total <- envelopeAdd "source metadata generated-name reservation" (envelopeMaxRender limits) schemes dictionaries;
    -- UTF8 dominates scalar count, so this conservative equal pair covers both.
    Right (envelopeBounds total total)
  };
  envelopeReserveSourceNames schemePasses dictionaryPasses table =
    foldEither (\current entry -> case snd entry of {
      EnvelopeLinkArtifact admission digest -> do {
        let { iface = objectInterface (envelopeAdmissionObject admission) };
        bounds <- envelopeSourceNameBounds crateEnvelopeLimits schemePasses dictionaryPasses iface;
        budget <- envelopeChargeRender crateEnvelopeLimits 2 bounds (envelopeAdmissionBudget admission);
        Right (M.insert compareString (fst entry)
          (EnvelopeLinkArtifact (envelopeReplaceAdmission (envelopeAdmissionPool admission) budget admission) digest) current)
      }
    }) table (M.toList table);
  envelopeReserveKnownSourceNames schemePasses dictionaryPasses prepared = case prepared of {
    EnvelopeKnownObjects ordered byName objects table layouts -> do {
      reserved <- envelopeReserveSourceNames schemePasses dictionaryPasses table;
      Right (EnvelopeKnownObjects ordered byName objects reserved layouts)
    }
  };
  -- Fixed Prelude continuation: prepareObject calls prepareMetadata once and
  -- checkCompilerPrelude calls it again; each has two Dict_ construction sites
  -- and one sourceExternals map. Reserve FOUR/TWO before either continuation.
  -- Fixed primitive entities/builtin identity used by nameOf are not supplied
  -- by the object. Existing entry/compiler/type-check operations remain guarded.
  linkKnownPreludeObjectWithSpine object initial = do {
    prepared <- envelopePrepareKnownObjects [object] [crateId (objectInterface object)] True;
    reserved <- envelopeReserveKnownSourceNames 2 4 prepared;
    linked <- envelopeFoldKnownObjects reserved initial;
    case linked of { (,,) state proof _ -> Right ((,) state proof) }
  };
  -- A complete new-family match commits to the envelope parser. Legacy/v1
  -- decode receives the same immutable snapshot, never a second path read.
  readObject :: String -> CrateInterface -> IO (Either String CrateObject);
  readObject path iface = readObjectWithOpenReader readOpenObject path iface;
  -- A portable release supplies verified interfaces, not filesystem locations.
  -- Only open objects use this context; closed-family admission is unchanged.
  readObjectWithDependencies :: String -> CrateInterface -> [] CrateInterface ->
    IO (Either String CrateObject);
  readObjectWithDependencies path iface dependencies =
    readObjectWithOpenReader
      (\bytes expected -> decodeOpenObject bytes expected
        (validateOpenDependencies expected dependencies)) path iface;
  -- Existing bundle callers supply an inventory that may include this root.
  -- Select its closure, then use the same strict portable dependency admission.
  readObjectWithInterfaces :: [] CrateInterface -> String -> CrateInterface -> IO (Either String CrateObject);
  readObjectWithInterfaces available = readObjectWithOpenReader
    (\bytes iface -> decodeOpenObject bytes iface (openInterfaceDependencies available iface));
  openInterfaceDependencies :: [] CrateInterface -> CrateInterface -> Either String ([] CrateInterface);
  openInterfaceDependencies available iface = do {
    uniqueNames "supplied crate identity" (map crateId available);
    mapM_ validateInterface available;
    let { supplied = interfaceMap available };
    case M.lookup compareString (crateId iface) supplied of {
      Nothing -> Right ();
      Just actual -> ensure (eqString (encodeInterface actual) (encodeInterface iface))
        "open crate supplied root metadata mismatch"
    };
    closure <- dependencyClosure supplied [crateId iface] [] (map dependencyId (crateDependencies iface));
    validateOpenDependencies iface closure
  };
  readObjectWithOpenReader ::
    (ByteArray -> CrateInterface -> IO (Either String CrateObject)) ->
    String -> CrateInterface -> IO (Either String CrateObject);
  readObjectWithOpenReader openReader path iface = do {
    raw <- Storage.readRaw path;
    result <- case raw of {
      Left message -> ioReturn (Left message);
      Right bytes -> do {
        open <- Open.packageFamily bytes;
        recognized <- envelopeHasFamily bytes;
        if open then openReader bytes iface
        else if recognized then envelopeDecode crateEnvelopeLimits iface bytes else do {
          input <- Storage.decode 4 bytes;
          ioReturn (bindEither input (\decoded -> case decoded of {
            Storage.LegacyText text -> decodeObject iface text;
            Storage.BinaryInput graph -> decodeBinaryObject iface graph
          }))
        }
      }
    };
    ioReturn (mapLeft (\message -> path ++ ": " ++ message) result)
  };
  writeObjectEither :: String -> CrateObject -> IO (Either String ());
  writeObjectEither prefix object =
    if Storage.hasNul prefix 0 then ioReturn (Left "file path contains NUL") else do {
      let { path = prefix ++ ".mlfco"; destination = if Host.absolutePath path then path else "./" ++ path };
      isDirectory <- directoryExists destination;
      if isDirectory then ioReturn (Left "artifact destination is a directory") else case object of {
        OpenCrateObject iface package -> writeOpenObject prefix iface package;
        _ -> writeClosedObjectEither prefix object
      }
    };
  writeClosedObjectEither prefix object =
    if Storage.hasNul prefix 0 then ioReturn (Left "file path contains NUL") else do {
      let { path = prefix ++ ".mlfco"; destination = if Host.absolutePath path then path else "./" ++ path };
      isDirectory <- directoryExists destination;
      if isDirectory then ioReturn (Left "artifact destination is a directory")
      else if not (envelopeMarked object) && not (envelopeAboveOldWork [Structure.toCrateObjectFields (binaryObjectFields object)])
      then writeObjectEitherV1 prefix object
      else do {
        encoded <- envelopeEncode crateEnvelopeLimits object;
        case encoded of {
          Left message -> ioReturn (Left message);
          Right bytes -> do {
            written <- Storage.writeRawAtomic path bytes;
            case written of {
              Left message -> ioReturn (Left message);
              Right _ -> Storage.writeAtomic 3 (prefix ++ ".mlfci")
                [Structure.toCrateInterfaceFields (binaryInterfaceFields (objectInterface object))]
            }
          }
        }
      }
    };
  linkCrateWithSpine interfaces allowedLayouts state object =
    if openMarked object then linkOpenCrate Nothing interfaces allowedLayouts state object
    else if envelopeMarked object then envelopeLinkCrateWithSpine interfaces allowedLayouts state object
    else linkCrateWithSpineV1 interfaces allowedLayouts state object;
  linkSelectedCrateWithSpine selected interfaces allowedLayouts state object =
    if openMarked object then linkOpenCrate (Just selected) interfaces allowedLayouts state object
    else if envelopeMarked object then envelopeLinkSelectedCrateWithSpine selected interfaces allowedLayouts state object
    else linkSelectedCrateWithSpineV1 selected interfaces allowedLayouts state object;
  linkCheckedObjects objects root =
    if any envelopeMarked objects then envelopeLinkCheckedObjects objects root
    else linkCheckedObjectsV1 objects root;
  -- END N7 CRATE ENVELOPE ADDITIONS
  -- Freshly inspect the actual input; neither its constructor nor an earlier
  -- admission is authority for this operation. Existing input/expansion and
  -- admission limits remain unchanged.
  checkObjectEncodingInput :: CrateObject -> Either String ();
  checkObjectEncodingInput object = if openMarked object then validateInterface (objectInterface object) else do {
    _ <- envelopePlan crateEnvelopeLimits object;
    _ <- envelopeAdmitDetailed crateEnvelopeLimits (envelopeLegacyObject object)
      (objectInterface object) (objectInterface object) (objectFragments object);
    Right ()
  };
  -- Compare the original complete encodings after checking both originals.
  -- This is not a cumulative bound on subsequent formatter allocation or CPU;
  -- original formatter execution remains subject to the process resource guards.
  equalObjectEncodingsChecked :: CrateObject -> CrateObject -> Either String Bool;
  equalObjectEncodingsChecked expected actual = do {
    checkObjectEncodingInput expected;
    checkObjectEncodingInput actual;
    let { same =
      eqString (encodeInterface (objectInterface expected))
        (encodeInterface (objectInterface actual)) &&
      eqString (encodeObject expected) (encodeObject actual) };
    seq same (Right same)
  };
  openMarked object = case object of { OpenCrateObject _ _ -> True; _ -> False };
  -- Explicit adapter for old native prepared-library literals. Production
  -- query/object IO and reference linking never enter this compatibility path.
  legacyObject object = case object of {
    OpenCrateObject iface package -> makeObject iface (map (\((,) name fragment) -> let {
      term = Open.closedTerm fragment;
      metadata = Separate.UnitInterface name [] [] (Open.declarations (Open.context fragment)) [] []
        (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) (Open.bindings fragment))
        (Separate.fingerprint (Pretty.prettyTerm term))
    } in Separate.UnitObject metadata term) (Open.packageFragments package));
    _ -> object
  };
  -- Physical metadata paths are relocatable. The exact semantic interface,
  -- including contracts and ownership, is bound independently of those paths.
  openMetadata iface = QueryGraph.hashValue (Structure.toCrateInterfaceFields
    (binaryInterfaceFields (case iface of {
      CrateInterface n deps ms es is ds cs ins layouts bs entry _ protected ->
        CrateInterface n (map (\((,,) key _ semantic) -> (,,) key "" semantic) deps)
          ms es is ds cs ins layouts bs entry "open-object" protected
    })));
  openPackageMetadata iface dependencies = do {
    own <- openMetadata iface;
    imported <- mapM openMetadata (sortBy (\a b -> compareString (crateId a) (crateId b)) dependencies);
    ioReturn (do { root <- own; closure <- sequenceEither imported;
      Right (Separate.pack ((:) root closure)) })
  };
  makeOpenObject iface dependencies fragments = do {
    metadata <- openPackageMetadata iface dependencies;
    compatibility <- Open.compatibilityIdentity;
    case do { digest <- metadata; identity <- compatibility; Right ((,) digest identity) } of {
    Left e -> ioReturn (Left e); Right ((,) digest compiler) -> do {
      packed <- Open.makePackage compiler digest fragments;
      ioReturn (mapEither (\package -> OpenCrateObject
        (withObjectFingerprint iface (Open.packageHash package)) package) packed)
    } }
  };
  writeOpenObject prefix iface package = do {
    actual <- openMetadata iface;
    case do { digest <- actual;
      manifest <- Separate.unpack (Open.packageMetadata package);
      ensure ((case manifest of { (:) root _ -> eqString root digest; [] -> False }) &&
        eqString (crateObjectFingerprint iface) (Open.packageHash package)) "open object interface association changed";
      validateInterface iface
    } of {
      Left e -> ioReturn (Left e);
      Right _ -> do {
        written <- Storage.writeRawAtomic (prefix ++ ".mlfco") (Open.packageBytes package);
        case written of { Left e -> ioReturn (Left e); Right _ ->
          Storage.writeAtomic 3 (prefix ++ ".mlfci") [Structure.toCrateInterfaceFields (binaryInterfaceFields iface)] }
      }
    }
  };
  -- Reject ambiguous or overbroad supplied contexts before building their map.
  -- The root in the initial trail also rejects dependency cycles through it.
  validateOpenDependencies :: CrateInterface -> [] CrateInterface ->
    Either String ([] CrateInterface);
  validateOpenDependencies iface dependencies = do {
    uniqueNames "open dependency identity" (map crateId dependencies);
    ensure (not (any (\dependency -> eqString (crateId dependency) (crateId iface)) dependencies))
      "open crate dependency context contains its root";
    validateInterface iface;
    _ <- traverseEither validateInterface dependencies;
    let { byName = interfaceMap dependencies };
    closure <- dependencyClosure byName [crateId iface] []
      (map dependencyId (crateDependencies iface));
    ensure (length closure == length dependencies)
      "open crate dependency context contains unreachable crates";
    _ <- traverseEither (validateDependencies byName) ((:) iface closure);
    _ <- traverseEither (validateExportBoundary byName) ((:) iface closure);
    Right closure
  };
  readOpenObject :: ByteArray -> CrateInterface -> IO (Either String CrateObject);
  readOpenObject bytes iface = do {
    dependencies <- loadInterfaces (map dependencyPath (crateDependencies iface));
    decodeOpenObject bytes iface (bindEither dependencies
      (\imported -> validateOpenDependencies iface (map snd imported)))
  };
  -- Keep load errors and compatibility lookup in the ordinary reader's order.
  decodeOpenObject :: ByteArray -> CrateInterface -> Either String ([] CrateInterface) ->
    IO (Either String CrateObject);
  decodeOpenObject bytes iface dependencies = do {
    compatibility <- Open.compatibilityIdentity;
    case do {
      imported <- dependencies;
      compiler <- compatibility;
      validateInterface iface;
      validateDependencies (interfaceMap imported) iface;
      Right ((,) compiler ((:) iface imported))
    } of {
      Left e -> ioReturn (Left e);
      Right ((,) compiler interfaces) -> do {
        metadata <- openPackageMetadata iface (filter (\i -> not (eqString (crateId i) (crateId iface))) interfaces);
        loaded <- case metadata of { Left e -> ioReturn (Left e); Right digest ->
          Open.readPackage bytes (crateObjectFingerprint iface) compiler digest
          (M.fromList compareString (map (\((,) name ty) -> (,) name (Separate.normalType ty))
            (concatMap crateBindings interfaces)))
          (M.fromList compareString (map (\d -> (,) (D.datatypeName d) d)
            (concatMap crateLoweredData interfaces))) };
        ioReturn (do {
          package <- loaded;
          let { actual = concatMap (\((,) _ fragment) -> map
            (\((,) n ty) -> (,) (X.nameHint n) ty) (Open.bindings fragment)) (Open.packageFragments package) };
          mapM_ (\((,) owner fragment) -> let {
            keys = sortStrings (map (compose X.nameHint fst) (Open.bindings fragment))
          } in ensure (openGroupOwnerMatches (crateId iface) keys owner)
            "open crate fragment owner mismatch") (Open.packageFragments package);
          uniqueNames "open crate binding" (map fst actual);
          ensure (eqList Separate.sameSignature actual (crateBindings iface)) "open crate ownership/type inventory mismatch";
          Right (OpenCrateObject iface package)
        })
      }
    }
  };
  openGroupOwnerMatches crate keys owner = not (null keys) &&
    (eqString owner (Separate.openGroupName crate keys) ||
     eqString owner (Separate.queryGroupName crate (sortStrings keys)));
  -- Object files name declarations by stable, crate-qualified identities. Only
  -- this link owns the slots below. Never reuse a producer's resolver slot.
  data OpenUnit = OpenUnit;
  data IndexedFragment = IndexedFragment String Open.Fragment ([] (V.Index Declaration))
    ([] (V.Index Declaration));
  data OpenIndex = OpenIndex (Map String (V.Index Declaration))
    (V.IndexVec OpenUnit IndexedFragment) (IntMap (V.Index OpenUnit)) (Map String ([] (V.Index OpenUnit)));
  openDecl ids name = case M.lookup compareString name ids of {
    Just slot -> Right slot; Nothing -> Left ("unresolved crate symbol: " ++ name)
  };
  openIndex interfaces objects = do {
    let { definitions = concatMap crateBindings interfaces; keys = map fst definitions };
    uniqueNames "crate symbol" keys;
    let { ids = M.fromList compareString (zip keys (map V.fromInt (range 0 (length keys - 1))));
          byName = interfaceMap interfaces;
          collect object = case object of {
            OpenCrateObject iface package -> do {
              validateInterface iface;
              ensure (eqString (crateObjectFingerprint iface) (Open.packageHash package)) "open crate object checksum mismatch";
              deps <- dependencyClosure byName [crateId iface] [] (map dependencyId (crateDependencies iface));
              let { fs = Open.packageFragments package; actual = concatMap (compose Open.bindings snd) fs;
                    schemes = map (\((,) n ty) -> (,) (X.nameHint n) ty) actual;
                    allowed = Set.fromList compareString (map fst (concatMap crateBindings ((:) iface deps))) };
              uniqueNames "open crate fragment" (map fst fs);
              uniqueNames "open crate binding" (map fst schemes);
              ensure (sameSchemes schemes (crateBindings iface)) "open crate declaration inventory mismatch";
              rows <- traverseEither (\((,) group fragment) -> do {
                let { parameters = map (compose X.nameHint fst) (Open.parameters fragment) };
                uniqueNames "open fragment parameter" parameters;
                ensure (all (\key -> Set.member compareString key allowed) parameters)
                  "open fragment dependency outside crate boundary";
                inputs <- traverseEither (openDecl ids) parameters;
                outputs <- traverseEither (compose (openDecl ids) (compose X.nameHint fst)) (Open.bindings fragment);
                Right (IndexedFragment group fragment inputs outputs)
              }) fs;
              Right ((,) (crateId iface) rows)
            };
            _ -> Right ((,) (crateId (objectInterface object)) [])
          } };
    groups <- traverseEither collect objects;
    let { rows = V.fromList (concatMap snd groups); slots = V.indices rows;
          owners = IM.fromList (concatMap (\i -> case V.at rows i of {
            IndexedFragment _ _ _ outputs -> map (\d -> (,) (V.toInt d) i) outputs
          }) slots);
          partition remaining pairs = case pairs of {
            [] -> []; (:) ((,) owner fs) rest -> let { count = length fs } in
              (:) ((,) owner (take count remaining)) (partition (drop count remaining) rest)
          } };
    Right (OpenIndex ids rows owners (M.fromList compareString (partition slots groups)))
  };
  selectOpenFragments (OpenIndex ids rows producerOf _) selected = do {
    roots <- traverseEither (openDecl ids) selected;
    let { visit seen pending = case pending of {
            [] -> seen;
            (:) d rest -> case IM.lookup (V.toInt d) producerOf of {
              Nothing -> visit seen rest;
              Just producer -> if IS.member (V.toInt producer) seen then visit seen rest else case V.at rows producer of {
                IndexedFragment _ _ inputs _ -> visit (IS.insert (V.toInt producer) seen) (append inputs rest)
              }
            }
          } };
    Right (visit IS.empty roots)
  };
  -- Closed object formats link their entire bodies. In a mixed session, keep
  -- every export of their open dependencies available for those bodies.
  openProgram ordered objectMap root = openProgramFrom [] ordered objectMap root;
  openProgramFrom prelinked ordered objectMap root = do {
    objects <- traverseEither (\i -> case M.lookup compareString (crateId i) objectMap of {
      Nothing -> Left "missing crate object"; Just object -> Right object
    }) (filter (\iface -> not (elem eqString (crateId iface) prelinked)) ordered);
    if not (any openMarked objects) then Right Nothing else do {
    index <- openIndex ordered objects;
    let { byName = interfaceMap ordered; rootIface = M.findWithDefault compareString (panic "missing root crate") root byName;
          entry = crateEntry rootIface;
          closed = filter (\object -> not (openMarked object)) objects };
    chosen <- if eqString entry "" then Right Nothing else do {
      opaque <- traverseEither (\object -> dependencyClosure byName [] []
        (map dependencyId (crateDependencies (objectInterface object)))) closed;
      let { support = map fst (entrySignatures entry (concatMap crateBindings ordered));
            required = concatMap (compose (map fst) crateBindings) (concat opaque) };
      mapEither Just (selectOpenFragments index (append support required))
    };
    Right (Just ((,) index chosen))
  } };
  linkProgramCrate program interfaces layouts state object = case (,) program object of {
    (,) (Just ((,) index chosen)) (OpenCrateObject iface _) -> linkIndexedCrate index chosen layouts state iface;
    _ -> linkCrate interfaces layouts state object
  };
  linkOpenCrate :: Maybe ([] String) -> Map String CrateInterface -> Map String ((,) String ((,,,) Int Int Int Int)) ->
    (,) FragmentState (Either String Checked.LinkedSpine) -> CrateObject ->
    Either String ((,) FragmentState (Either String Checked.LinkedSpine));
  linkOpenCrate selected interfaces allowedLayouts ((,) state _) object = do {
    let { iface = objectInterface object };
    deps <- dependencyClosure interfaces [crateId iface] [] (map dependencyId (crateDependencies iface));
    index <- openIndex ((:) iface deps) [object];
    chosen <- case selected of { Nothing -> Right Nothing; Just keys -> do {
      let { own = M.fromList compareString (crateBindings iface) };
      ensure (all (\k -> M.member compareString k own || M.member compareString k (fragmentBindings state)) keys)
        "selected open crate symbols have unresolved dependencies";
      -- An incoming legacy state may contain symbols outside this object's declared imports.
      mapEither Just (selectOpenFragments index (filter (\k -> M.member compareString k own) keys))
    } };
    linked <- linkIndexedCrate index chosen allowedLayouts state iface;
    Right ((,) linked (Left "open fragment linking requires final program composition check"))
  };
  linkIndexedCrate (OpenIndex ids rows _ crates) chosen layouts
      starting@(FragmentState _ available _ _ _) iface = do {
    let { units = M.findWithDefault compareString [] (crateId iface) crates;
          selected = case chosen of { Nothing -> units; Just wanted -> filter (\i -> IS.member (V.toInt i) wanted) units };
          current = IM.fromList (mapMaybe (\((,) name binding) -> case M.lookup compareString name ids of { Nothing -> Nothing; Just d -> Just ((,) (V.toInt d) binding) }) (M.toList available)) };
    result <- foldEither (\state i -> linkOpenFragment layouts state (V.at rows i)) ((,) current starting) selected;
    Right (snd result)
  };
  linkOpenFragment allowedLayouts ((,) indexed (FragmentState serial available bodies allData groups))
      (IndexedFragment group fragment parameters members) = do {
    ensure (not (Set.member compareString group groups)) "duplicate crate inference fragment";
    let { renamed = Open.fresh serial fragment; fresh = snd renamed;
      ds = Open.declarations (Open.context fresh) };
    mapM_ (\d -> case M.lookup compareString (D.datatypeName d) allowedLayouts of {
      Nothing -> Left ("open fragment has undeclared datatype: " ++ D.datatypeName d);
      Just expected -> ensure (eqString (D.prettyDeclaration d) (fst expected)) "open fragment datatype layout mismatch"
    }) ds;
    replacements <- traverseEither (\((,) d ((,) n ty)) -> case IM.lookup (V.toInt d) indexed of {
      Nothing -> Left ("unresolved crate symbol: " ++ X.nameHint n);
      Just ((,) actual expected) -> do {
        ensure (T.alphaEq ty expected) ("open fragment import type mismatch: " ++ X.nameHint n);
        Right ((,) n actual)
      }
    }) (zip parameters (Open.parameters fresh));
    let { provided = zip members (Open.bindings fresh) };
    ensure (all (\entry -> not (IM.member (V.toInt (fst entry)) indexed)) provided) "duplicate crate symbol";
    let { substitution = M.fromList X.compareName replacements;
      linked = Separate.mapTerm (\n -> M.findWithDefault X.compareName n n substitution) (\a -> a) (Open.body fresh);
      updated = foldlStrict (\table ((,) d binding) -> IM.insert (V.toInt d) binding table) indexed provided;
      added = M.fromList compareString (map (\((,) n ty) -> (,) (X.nameHint n) ((,) n ty)) (Open.bindings fresh)) };
    combined <- foldEither Separate.mergeDeclaration allData ds;
    Right ((,) updated (FragmentState (fst renamed) (M.union compareString added available) ((:) linked bodies)
      combined (Set.insert compareString group groups)))
  };
}
