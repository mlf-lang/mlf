-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Release where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  -- Release objects retain the ordinary checked compiler format. Only dependency
  -- locations change: portable locations name pairs of SHA256 digests, and the
  -- receiver reconstructs absolute locations in its own immutable store.
  virtualPath key = ("/__mlf_release__/" ++ (key ++ "/unit.mlfci"));
  pairKey metadata object = (metadata ++ object);
  hex text =
    S.all
      (\i ->
         let {
           c = stringCodeAt text i
         } in
         (((c >= 48) && (c <= 57)) || ((c >= 97) && (c <= 102))))
      (S.range 0 (stringLength text - 1));
  validDigest text = ((stringLength text == 64) && hex text);
  validKey text = ((stringLength text == 128) && hex text);
  checked :: forall a. Either String a -> IO a;
  checked result =
    case result of {
      Left message -> O.fatal message;
      Right value -> ioReturn value
    };
  fieldText name value =
    case J.get name value of {
      J.String text -> ioReturn text;
      _ -> O.fatal ("release field must be a string: " ++ name)
    };
  fieldStrings name value =
    case J.get name value of {
      J.Array values ->
        S.mapM
          (\item ->
             case item of {
               J.String text -> ioReturn text;
               _ -> O.fatal ("release field must contain strings: " ++ name)
             })
          values;
      _ -> O.fatal ("release field must be an array: " ++ name)
    };
  unique values = (S.length values == S.length (S.nubBy eqString values));
  rowKey row = J.getText "key" "" row;
  rowIdentity row = J.getText "identity" "" row;
  rows manifest = J.values (J.get "crates" manifest);
  rootKey manifest = J.getText "root" "" manifest;
  libraryIdentity manifest =
    (J.getText "name" "" manifest ++ ("/" ++ (J.getText "version" "" manifest ++ "/library")));
  bundlePrefix directory key = (directory ++ ("/crates/" ++ (key ++ "/unit")));
  rootInterface manifest interfaces =
    S.fromMaybe (panic "validated release root is absent")
      (S.lookup eqString (rootKey manifest) interfaces);
  validateShape manifest =
    do {
      J.fields manifest
        (O.words "format name version compiler_sha256 no_prelude root modules crates")
        "release manifest";
      O.require (J.equal (J.get "format" manifest) (J.num 1))
        "unsupported checked package release format";
      name <- fieldText "name" manifest;
      version <- fieldText "version" manifest;
      compiler <- fieldText "compiler_sha256" manifest;
      root <- fieldText "root" manifest;
      modules <- fieldStrings "modules" manifest;
      O.require ((stringLength name > 0) && (stringLength version > 0))
        "release package identity is empty";
      O.require (validDigest compiler && validKey root) "invalid release compiler or root digest";
      case J.get "no_prelude" manifest of {
        J.Boolean _ -> ioReturn ();
        _ -> O.fatal "release no_prelude must be boolean"
      };
      O.require
        (S.not (S.null modules) && (unique modules && S.not (S.elem eqString "Prelude" modules)))
        "invalid release module inventory";
      entries <-
        case J.get "crates" manifest of {
          J.Array entries -> ioReturn entries;
          _ -> O.fatal "release crates must be an array"
        };
      O.require (S.not (S.null entries)) "release contains no checked crates";
      S.mapM_
        (\row ->
           do {
             J.fields row (O.words "key identity metadata_sha256 object_sha256") "release crate";
             key <- fieldText "key" row;
             identity <- fieldText "identity" row;
             metadata <- fieldText "metadata_sha256" row;
             object <- fieldText "object_sha256" row;
             O.require
               ((stringLength identity > 0) &&
                (validDigest metadata &&
                 (validDigest object && eqString key (pairKey metadata object))))
               "invalid release crate identity or digest"
           })
        entries;
      O.require (unique (S.map rowKey entries) && unique (S.map rowIdentity entries))
        "duplicate release crate identity or digest";
      O.require (S.elem eqString root (S.map rowKey entries))
        "release root is absent from crate inventory"
    };
  -- Do not follow an artifact symlink outside the selected bundle, even if the
  -- external file happens to have the advertised digest.
  verifyFile directory path expected =
    do {
      present <- fileExists path;
      O.require present ("missing release artifact: " ++ path);
      actualPath <- canonicalPath path;
      O.require (O.starts (O.normalize directory ++ "/") (O.normalize actualPath))
        "release artifact escapes its bundle";
      digest <- fileDigest path;
      O.require (eqString digest expected) ("release artifact digest mismatch: " ++ path)
    };
  bundleInterfaces directory manifest =
    S.mapM
      (\row ->
         do {
           let {
             prefix = bundlePrefix directory (rowKey row)
           };
           verifyFile directory (prefix ++ ".mlfci") (J.getText "metadata_sha256" "" row);
           verifyFile directory (prefix ++ ".mlfco") (J.getText "object_sha256" "" row);
           decoded <- Artifact.readInterface (prefix ++ ".mlfci");
           iface <- checked decoded;
           O.require (eqString (Artifact.crateId iface) (rowIdentity row))
             "release crate identity does not match metadata";
           O.require (eqString (Artifact.crateEntry iface) "")
             "release contains an executable crate";
           ioReturn ((,) (rowKey row) iface)
         })
      (rows manifest);
  validateClosure manifest interfaces =
    do {
      let {
        byName = Artifact.interfaceMap (S.map S.snd interfaces)
      };
      let {
        names = S.map (\((,) key iface) -> (,) (Artifact.crateId iface) key) interfaces
      };
      S.ensure (unique (S.concatMap (\((,) _ iface) -> Artifact.crateModules iface) interfaces))
        "release module belongs to multiple crates";
      S.ensure
        (S.all
           (\((,) _ iface) ->
              (S.not (S.elem eqString "Prelude" (Artifact.crateModules iface)) ||
               eqString (Artifact.crateId iface) "mlf:builtin-prelude:1"))
           interfaces)
        "release contains a noncanonical Prelude owner";
      S.traverseEither
        (\((,) _ iface) ->
           do {
             S.traverseEither
               (\((,,) identity path _) ->
                  case S.lookup eqString identity names of {
                    Nothing -> Left ("release is missing dependency " ++ identity);
                    Just key ->
                      S.ensure (eqString path (virtualPath key))
                        "release contains a nonportable dependency location"
                  })
               (Artifact.crateDependencies iface);
             Artifact.validateDependencies byName iface;
             Artifact.validateExportBoundary byName iface
           })
        interfaces;
      let {
        root = rootInterface manifest interfaces
      };
      S.ensure (eqString (Artifact.crateId root) (libraryIdentity manifest))
        "release root does not match package name and version";
      S.ensure
        (S.eqList eqString (S.sortBy compareString (Artifact.crateModules root))
           (S.sortBy compareString (J.getStrings "modules" manifest)))
        "release module inventory does not match checked metadata";
      closure <- Artifact.dependencyClosure byName [] [] ((:) (Artifact.crateId root) []);
      S.ensure (S.length closure == S.length interfaces) "release contains unreachable crates";
      Artifact.validateLayouts closure;
      Right ()
    };
  readManifest :: String -> IO J.Json;
  readManifest directory =
    do {
      canonical <- canonicalPath directory;
      manifest <- J.read (canonical ++ "/release.json");
      validateShape manifest;
      interfaces <- bundleInterfaces canonical manifest;
      checked (validateClosure manifest interfaces);
      ioReturn manifest
    };
  verifyManifestDigest directory expected =
    do {
      O.require (validDigest expected) "invalid release manifest SHA-256 pin";
      actual <- fileDigest (O.join directory "release.json");
      O.require (eqString actual expected) "release manifest SHA-256 mismatch"
    };
  readPinnedManifest :: String -> String -> IO J.Json;
  readPinnedManifest directory expected =
    do {
      verifyManifestDigest directory expected;
      manifest <- readManifest directory;
      verifyManifestDigest directory expected;
      ioReturn manifest
    };
  verifyBundle :: String -> J.Json -> IO ();
  verifyBundle directory saved =
    do {
      current <- readManifest directory;
      O.require (J.equal current saved) "release manifest changed during build/test"
    };
  relocateInterface locations iface =
    do {
      dependencies <-
        S.traverseEither
          (\((,,) identity _ semantic) ->
             case S.lookup eqString identity locations of {
               Nothing -> Left ("release dependency is missing: " ++ identity);
               Just path -> Right ((,,) identity path semantic)
             })
          (Artifact.crateDependencies iface);
      case iface of {
        Artifact.CrateInterface identity _ modules exports imports datatypes classes instances layouts bindings entry fingerprint ->
          Right
            (Artifact.CrateInterface identity dependencies modules exports imports datatypes classes
               instances
               layouts
               bindings
               entry
               fingerprint)
      }
    };
  relocateObject locations object =
    do {
      iface <- relocateInterface locations (Artifact.objectInterface object);
      case object of {
        Artifact.CrateObject _ fragments -> Right (Artifact.CrateObject iface fragments);
        Artifact.LegacyCrateObject _ fragments -> Right (Artifact.LegacyCrateObject iface fragments)
      }
    };
  readObjects directory manifest interfaces =
    S.mapM
      (\((,) key iface) ->
         do {
           decoded <- Artifact.readObject (bundlePrefix directory key ++ ".mlfco") iface;
           object <- checked decoded;
           ioReturn object
         })
      interfaces;
  publishRows :: String ->
                 [] ((,) String String) ->
                 [] J.Json -> [] Artifact.CrateObject -> IO ([] J.Json);
  publishRows work locations done objects =
    case objects of {
      [] -> ioReturn done;
      (:) object rest ->
        do {
          portable <- checked (relocateObject locations object);
          let {
            temporary = (work ++ "/crates/pending")
          };
          O.mkdir temporary;
          Artifact.writeObject (temporary ++ "/unit") portable;
          metadata <- fileDigest (temporary ++ "/unit.mlfci");
          body <- fileDigest (temporary ++ "/unit.mlfco");
          let {
            key = pairKey metadata body
          };
          let {
            identity = Artifact.crateId (Artifact.objectInterface portable)
          };
          let {
            row =
              J.Object
                ((:) ((,) "key" (J.str key))
                   ((:) ((,) "identity" (J.str identity))
                      ((:) ((,) "metadata_sha256" (J.str metadata))
                         ((:) ((,) "object_sha256" (J.str body)) []))))
          };
          O.move temporary (work ++ ("/crates/" ++ key));
          publishRows work (S.snoc locations ((,) identity (virtualPath key))) (S.snoc done row)
            rest
        }
    };
  publish :: String -> String -> Bool -> String -> String -> String -> IO ();
  publish metadata compiler noPrelude name version output =
    do {
      O.require (validDigest compiler) "invalid release compiler digest";
      loaded <- Artifact.loadInterfaces ((:) metadata []);
      interfaces <- checked loaded;
      O.require (S.not (S.null interfaces)) "cannot release an empty crate graph";
      let {
        root = S.snd (S.last interfaces)
      };
      O.require (eqString (Artifact.crateId root) (name ++ ("/" ++ (version ++ "/library"))))
        "release root does not match package identity";
      O.require (S.all (\((,) _ iface) -> eqString (Artifact.crateEntry iface) "") interfaces)
        "only library crates can be released";
      objects <-
        S.mapM
          (\((,) path iface) ->
             do {
               decoded <- Artifact.readObject (Artifact.objectPath path) iface;
               checked decoded
             })
          interfaces;
      checked (Artifact.linkCheckedObjects objects (Artifact.crateId root));
      O.require
        ((stringLength output > 0) &&
         S.not (S.elem eqString (O.base output) ((:) "" ((:) "." ((:) ".." [])))))
        "invalid release output directory";
      O.mkdir (O.parent output);
      parent <- canonicalPath (O.parent output);
      let {
        destination = O.join parent (O.base output)
      };
      let {
        work = (destination ++ ".work")
      };
      lock <- acquireFileLock (destination ++ ".lock");
      occupied <- directoryExists destination;
      occupiedFile <- fileExists destination;
      workExists <- directoryExists work;
      workFile <- fileExists work;
      O.require (S.not (occupied || (occupiedFile || (workExists || workFile))))
        "release output or staging path already exists";
      O.mkdir (work ++ "/crates");
      entries <- publishRows work [] [] objects;
      let {
        manifest =
          J.Object
            ((:) ((,) "format" (J.num 1))
               ((:) ((,) "name" (J.str name))
                  ((:) ((,) "version" (J.str version))
                     ((:) ((,) "compiler_sha256" (J.str compiler))
                        ((:) ((,) "no_prelude" (J.Boolean noPrelude))
                           ((:) ((,) "root" (J.str (rowKey (S.last entries))))
                              ((:)
                                 ((,) "modules"
                                    (J.stringArray
                                       (S.sortBy compareString (Artifact.crateModules root))))
                                 ((:) ((,) "crates" (J.Array entries)) []))))))))
      };
      J.write (work ++ "/release.json") manifest;
      readManifest work;
      O.move work destination;
      releaseFileLock lock
    };
  localPrefix cache compiler row =
    if eqString (rowIdentity row) "mlf:builtin-prelude:1"
    then (cache ++ ("/.queries/builtin-prelude/" ++ (compiler ++ "/unit")))
    else (cache ++ ("/.releases/" ++ (compiler ++ ("/" ++ (rowKey row ++ "/unit")))));
  localPaths cache compiler manifest =
    S.concatMap
      (\row ->
         let {
           prefix = localPrefix cache compiler row
         } in
         (:) (prefix ++ ".mlfci") ((:) (prefix ++ ".mlfco") []))
      (rows manifest);
  receiptValid path digest validator expected =
    do {
      present <- fileExists path;
      if S.not present
      then ioReturn False
      else do {
             text <- readFile path;
             case J.parse text of {
               Left _ -> ioReturn False;
               Right receipt ->
                 case receipt of {
                   J.Object _ ->
                     if S.not
                          (J.equal (J.get "release" receipt) (J.str digest) &&
                           (J.equal (J.get "validator_sha256" receipt) (J.str validator) &&
                            J.equal (J.get "format" receipt) (J.num 1)))
                     then ioReturn False
                     else case J.get "files" receipt of {
                            J.Object files ->
                              if S.not
                                   (S.eqList eqString (S.sortBy compareString (S.map S.fst files))
                                      (S.sortBy compareString expected))
                              then ioReturn False
                              else do {
                                     checks <-
                                       S.mapM
                                         (\((,) file hash) ->
                                            do {
                                              present <- fileExists file;
                                              if S.not present
                                              then ioReturn False
                                              else do {
                                                     actual <- fileDigest file;
                                                     ioReturn (J.equal hash (J.str actual))
                                                   }
                                            })
                                         files;
                                     ioReturn (S.and checks)
                                   };
                            _ -> ioReturn False
                          };
                   _ -> ioReturn False
                 }
             }
           }
    };
  verifyPrelude object =
    if S.not (eqString (Artifact.crateId (Artifact.objectInterface object)) "mlf:builtin-prelude:1")
    then ioReturn ()
    else do {
           builtin <- checked Artifact.builtinPrelude;
           O.require
             (eqString (Artifact.encodeInterface (Artifact.objectInterface builtin))
                (Artifact.encodeInterface (Artifact.objectInterface object)) &&
              eqString (Artifact.encodeObject builtin) (Artifact.encodeObject object))
             "release contains a noncanonical builtin Prelude"
         };
  installObject prefix object =
    do {
      O.mkdir (O.parent prefix);
      lock <- acquireFileLock (prefix ++ ".lock");
      O.writeAtomic (prefix ++ ".mlfco") (Artifact.encodeObject object);
      O.writeAtomic (prefix ++ ".mlfci")
        (Artifact.encodeInterface (Artifact.objectInterface object));
      releaseFileLock lock
    };
  -- Decode only this private copy: hashing a producer's file and reopening it
  -- must not allow changed bytes to acquire a local validation receipt.
  stageBundle bundle destination manifest =
    do {
      O.remove destination;
      O.mkdir destination;
      O.copy (bundle ++ "/release.json") (destination ++ "/release.json");
      S.mapM_
        (\row ->
           do {
             let {
               key = rowKey row
             };
             let {
               source = bundlePrefix bundle key
             };
             let {
               target = bundlePrefix destination key
             };
             O.copy (source ++ ".mlfci") (target ++ ".mlfci");
             O.copy (source ++ ".mlfco") (target ++ ".mlfco")
           })
        (rows manifest)
    };
  materialize :: String -> String -> String -> Bool -> IO String;
  materialize directory cacheDirectory compiler noPrelude =
    do {
      digest <- fileDigest (O.join directory "release.json");
      materializePinned directory digest cacheDirectory compiler noPrelude
    };
  materializePinned :: String -> String -> String -> String -> Bool -> IO String;
  materializePinned directory digest cacheDirectory compiler noPrelude =
    do {
      bundle <- canonicalPath directory;
      manifest <- readPinnedManifest bundle digest;
      O.require (eqString (J.getText "compiler_sha256" "" manifest) compiler)
        "release compiler digest does not match selected compiler";
      O.require
        (if noPrelude
         then J.getBool "no_prelude" False manifest
         else S.not (J.getBool "no_prelude" False manifest))
        "release Prelude mode does not match target";
      manager <- getExecutablePath;
      validator <- fileDigest manager;
      O.mkdir cacheDirectory;
      cache <- canonicalPath cacheDirectory;
      O.mkdir (cache ++ "/.locks");
      O.mkdir (cache ++ "/.releases/verified");
      lock <- acquireFileLock (cache ++ ("/.locks/release-" ++ digest));
      let {
        receipt = (cache ++ ("/.releases/verified/" ++ (digest ++ ("-" ++ (validator ++ ".json")))))
      };
      let {
        scratch = (cache ++ ("/.releases/staging/" ++ (digest ++ ("-" ++ validator))))
      };
      let {
        expected = localPaths cache compiler manifest
      };
      let {
        rootRow =
          S.fromMaybe (panic "validated release root is absent")
            (S.find (\row -> eqString (rowKey row) (rootKey manifest)) (rows manifest))
      };
      let {
        root = localPrefix cache compiler rootRow
      };
      reusable <- receiptValid receipt digest validator expected;
      if reusable
      then ioReturn ()
      else do {
             O.mkdir scratch;
             staging <- O.temporaryDirectory scratch (scratch ++ "/work-");
             stageBundle bundle staging manifest;
             stagedManifest <- readPinnedManifest staging digest;
             interfaces <- bundleInterfaces staging stagedManifest;
             objects <- readObjects staging stagedManifest interfaces;
             checked (Artifact.linkCheckedObjects objects (libraryIdentity manifest));
             S.mapM_ verifyPrelude objects;
             readPinnedManifest staging digest;
             let {
               locations =
                 S.map (\row -> (,) (rowIdentity row) (localPrefix cache compiler row ++ ".mlfci"))
                   (rows manifest)
             };
             relocated <- checked (S.traverseEither (relocateObject locations) objects);
             S.mapM_
               (\object ->
                  do {
                    let {
                      identity = Artifact.crateId (Artifact.objectInterface object)
                    };
                    let {
                      path =
                        S.fromMaybe (panic "validated release location is absent")
                          (S.lookup eqString identity locations)
                    };
                    installObject (stringSlice path 0 (stringLength path - 6)) object
                  })
               relocated;
             linked <- Artifact.linkCheckedFile (root ++ ".mlfci");
             checked linked;
             hashes <-
               S.mapM
                 (\path ->
                    do {
                      hash <- fileDigest path;
                      ioReturn ((,) path (J.str hash))
                    })
                 expected;
             verifyManifestDigest bundle digest;
             currentValidator <- fileDigest manager;
             O.require (eqString validator currentValidator)
               "release validator changed during import";
             O.remove staging;
             J.write receipt
               (J.Object
                  ((:) ((,) "format" (J.num 1))
                     ((:) ((,) "release" (J.str digest))
                        ((:) ((,) "validator_sha256" (J.str validator))
                           ((:) ((,) "files" (J.Object hashes)) [])))))
           };
      verifyManifestDigest bundle digest;
      releaseFileLock lock;
      ioReturn (O.parent root)
    }
}
