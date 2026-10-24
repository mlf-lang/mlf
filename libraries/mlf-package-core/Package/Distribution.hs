-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Distribution where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Release as R;
  -- Distribution is a text envelope, not an archive with producer-selected
  -- paths. Only release.json and validated digest-key artifact pairs are written.
  alphanumeric c =
    (((c >= 48) && (c <= 57)) || (((c >= 65) && (c <= 90)) || ((c >= 97) && (c <= 122))));
  identifier text =
    ((stringLength text > 0) &&
     (alphanumeric (stringCodeAt text 0) &&
      S.all
        (\i ->
           let {
             c = stringCodeAt text i
           } in
           (alphanumeric c || ((c == 45) || ((c == 46) || (c == 95)))))
        (S.range 0 (stringLength text - 1))));
  validRepository text =
    case O.split 47 text of {
      (:) owner ((:) repository []) -> (identifier owner && identifier repository);
      _ -> False
    };
  validTag text =
    ((stringLength text > 0) &&
     (alphanumeric (stringCodeAt text 0) &&
      (S.not (eqString text "latest") &&
       S.all
         (\i ->
            let {
              c = stringCodeAt text i
            } in
            (alphanumeric c ||
             ((c == 45) || ((c == 46) || ((c == 95) || ((c == 47) || (c == 43)))))))
         (S.range 0 (stringLength text - 1)))));
  validateDependency dependency =
    do {
      let {
        source = J.get "github" dependency
      };
      J.fields source (O.words "repository tag asset") "GitHub release source";
      repository <- R.fieldText "repository" source;
      tag <- R.fieldText "tag" source;
      asset <- R.fieldText "asset" source;
      manifest <- R.fieldText "sha256" dependency;
      digest <- R.fieldText "asset_sha256" dependency;
      O.require (validRepository repository) "GitHub release repository must be OWNER/REPOSITORY";
      O.require (validTag tag) "GitHub release requires an explicit tag without option syntax";
      O.require (identifier asset && O.ends ".mlfr" asset)
        "GitHub release asset must be a literal .mlfr filename";
      O.require (R.validDigest manifest && R.validDigest digest)
        "GitHub release requires manifest and asset lowercase SHA-256 pins"
    };
  readPayload directory row =
    do {
      let {
        key = R.rowKey row
      };
      let {
        prefix = R.bundlePrefix directory key
      };
      metadata <- readFile (prefix ++ ".mlfci");
      object <- readFile (prefix ++ ".mlfco");
      ioReturn
        (J.Object
           ((:) ((,) "key" (J.str key))
              ((:) ((,) "metadata" (J.str metadata)) ((:) ((,) "object" (J.str object)) []))))
    };
  pack :: String -> String -> IO J.Json;
  pack directory output =
    do {
      source <- canonicalPath directory;
      manifest <- R.readManifest source;
      digest <- fileDigest (source ++ "/release.json");
      O.require
        ((stringLength output > 0) &&
         (S.not (S.elem eqString (O.base output) (O.words ". ..")) &&
          S.not (eqString (O.base output) "")))
        "invalid release asset output";
      O.mkdir (O.parent output);
      parent <- canonicalPath (O.parent output);
      let {
        destination = O.join parent (O.base output)
      };
      let {
        work = (destination ++ ".work")
      };
      lock <- acquireFileLock (destination ++ ".lock");
      occupied <- fileExists destination;
      directoryOccupied <- directoryExists destination;
      stagingFile <- fileExists work;
      stagingDirectory <- directoryExists work;
      O.require (S.not (occupied || (directoryOccupied || (stagingFile || stagingDirectory))))
        "release asset output or staging path already exists";
      R.stageBundle source work manifest;
      saved <- R.readPinnedManifest work digest;
      manifestText <- readFile (work ++ "/release.json");
      crates <- S.mapM (readPayload work) (R.rows saved);
      R.readPinnedManifest work digest;
      let {
        envelope =
          J.Object
            ((:) ((,) "format" (J.num 1))
               ((:) ((,) "manifest" (J.str manifestText))
                  ((:) ((,) "crates" (J.Array crates)) [])))
      };
      J.write (work ++ "/package.mlfr") envelope;
      asset <- fileDigest (work ++ "/package.mlfr");
      O.move (work ++ "/package.mlfr") destination;
      O.remove work;
      releaseFileLock lock;
      ioReturn
        (J.Object
           ((:) ((,) "sha256" (J.str digest)) ((:) ((,) "asset_sha256" (J.str asset)) [])))
    };
  unpack asset destination expected =
    do {
      envelope <- J.read asset;
      J.fields envelope (O.words "format manifest crates") "checked release asset";
      O.require (J.equal (J.get "format" envelope) (J.num 1))
        "unsupported checked release asset format";
      manifestText <- R.fieldText "manifest" envelope;
      manifest <- R.checked (J.parse manifestText);
      R.validateShape manifest;
      crates <-
        case J.get "crates" envelope of {
          J.Array entries -> ioReturn entries;
          _ -> O.fatal "release asset crates must be an array"
        };
      S.mapM_
        (\entry ->
           do {
             J.fields entry (O.words "key metadata object") "release asset crate";
             key <- R.fieldText "key" entry;
             R.fieldText "metadata" entry;
             R.fieldText "object" entry;
             O.require (R.validKey key) "invalid release asset crate key"
           })
        crates;
      let {
        actualKeys = S.map R.rowKey crates
      };
      O.require
        (R.unique actualKeys &&
         S.eqList eqString (S.sortBy compareString actualKeys)
           (S.sortBy compareString (S.map R.rowKey (R.rows manifest))))
        "release asset crate inventory mismatch";
      let {
        temporary = (O.parent destination ++ "/manifest.json")
      };
      writeFile temporary manifestText;
      digest <- fileDigest temporary;
      O.require (eqString digest expected) "release asset manifest SHA-256 mismatch";
      O.mkdir destination;
      O.move temporary (destination ++ "/release.json");
      S.mapM_
        (\entry ->
           do {
             let {
               prefix = R.bundlePrefix destination (R.rowKey entry)
             };
             O.mkdir (O.parent prefix);
             writeFile (prefix ++ ".mlfci") (J.getText "metadata" "" entry);
             writeFile (prefix ++ ".mlfco") (J.getText "object" "" entry)
           })
        crates;
      R.readPinnedManifest destination expected
    };
  validAsset path expected =
    do {
      present <- fileExists path;
      if S.not present
      then ioReturn False
      else do {
             actual <- fileDigest path;
             ioReturn (eqString actual expected)
           }
    };
  validCachedPath path =
    (eqString path "bundle/release.json" ||
     (let {
        matchValueShared1 = O.split 47 path
      } in
      case matchValueShared1 of {
        (:) matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "bundle"
          then case matchValueShared3 of {
                 (:) matchValueShared4 matchValueShared5 ->
                   if MLF.Primitive.eqString matchValueShared4 "crates"
                   then case matchValueShared5 of {
                          (:) matchValueShared6 matchValueShared7 ->
                            case matchValueShared7 of {
                              (:) matchValueShared8 matchValueShared9 ->
                                case matchValueShared9 of {
                                  [] ->
                                    let {
                                      key = matchValueShared6
                                    } in
                                    let {
                                      name = matchValueShared8
                                    } in
                                    (R.validKey key &&
                                     S.elem eqString name (O.words "unit.mlfci unit.mlfco"));
                                  _ -> False
                                };
                              _ -> False
                            };
                          _ -> False
                        }
                   else False;
                 _ -> False
               }
          else False;
        _ -> False
      }));
  validBundle destination expected =
    do {
      present <- fileExists (destination ++ "/files.json");
      if S.not present
      then ioReturn False
      else do {
             text <- readFile (destination ++ "/files.json");
             case J.parse text of {
               Left _ -> ioReturn False;
               Right receipt ->
                 case receipt of {
                   J.Object _ ->
                     if S.not
                          (J.equal (J.get "format" receipt) (J.num 1) &&
                           J.equal (J.get "manifest_sha256" receipt) (J.str expected))
                     then ioReturn False
                     else case J.get "files" receipt of {
                            J.Object files ->
                              if (S.null files ||
                                  (S.not
                                     (S.any (\entry -> eqString (S.fst entry) "bundle/release.json")
                                        files) ||
                                   S.not (S.all (\entry -> validCachedPath (S.fst entry)) files)))
                              then ioReturn False
                              else do {
                                     checks <-
                                       S.mapM
                                         (\((,) path digest) ->
                                            case digest of {
                                              J.String hash ->
                                                validAsset (destination ++ ("/" ++ path)) hash;
                                              _ -> ioReturn False
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
  saveBundleReceipt destination manifest expected =
    do {
      let {
        paths =
          (:) "bundle/release.json"
            (S.concatMap
               (\row ->
                  let {
                    prefix = ("bundle/crates/" ++ (R.rowKey row ++ "/unit"))
                  } in
                  (:) (prefix ++ ".mlfci") ((:) (prefix ++ ".mlfco") []))
               (R.rows manifest))
      };
      hashes <-
        S.mapM
          (\path ->
             do {
               digest <- fileDigest (destination ++ ("/" ++ path));
               ioReturn ((,) path (J.str digest))
             })
          paths;
      J.write (destination ++ "/files.json")
        (J.Object
           ((:) ((,) "format" (J.num 1))
              ((:) ((,) "manifest_sha256" (J.str expected))
                 ((:) ((,) "files" (J.Object hashes)) []))))
    };
  fetch :: J.Json -> J.Json -> IO String;
  fetch options dependency =
    do {
      validateDependency dependency;
      let {
        digest = J.getText "asset_sha256" "" dependency
      };
      let {
        expected = J.getText "sha256" "" dependency
      };
      let {
        requested = J.getText "cache-dir" ".mlf-build/cache" options
      };
      O.mkdir (requested ++ "/.downloads");
      cache <- canonicalPath requested;
      O.mkdir (cache ++ "/.locks");
      let {
        destination = (cache ++ ("/.downloads/" ++ digest))
      };
      let {
        scratch = (destination ++ ".staging")
      };
      let {
        asset = (destination ++ "/package.mlfr")
      };
      lock <- acquireFileLock (cache ++ ("/.locks/download-" ++ digest));
      retained <- validAsset asset digest;
      complete <- if retained then validBundle destination expected else ioReturn False;
      if complete
      then do {
             R.readPinnedManifest (destination ++ "/bundle") expected;
             ioReturn ()
           }
      else do {
             O.require (retained || S.not (J.getBool "offline" False options))
               "offline cache miss or corrupt GitHub release asset";
             O.mkdir scratch;
             work <- O.temporaryDirectory scratch (destination ++ ".work-");
             let {
               downloaded = (work ++ "/package.mlfr")
             };
             if retained
             then O.copy asset downloaded
             else do {
                    gh <- O.which "gh";
                    let {
                      source = J.get "github" dependency
                    };
                    let {
                      argv =
                        (:) gh
                          ((:) "release"
                             ((:) "download"
                                ((:) (J.getText "tag" "" source)
                                   ((:) "--repo"
                                      ((:) ("github.com/" ++ J.getText "repository" "" source)
                                         ((:) "--pattern"
                                            ((:) (J.getText "asset" "" source)
                                               ((:) "--output" ((:) downloaded [])))))))))
                    };
                    code <- O.exec "" argv "" "" "" (readInt (J.getText "timeout" "1800" options));
                    O.require (code == 0) "GitHub release asset download failed"
                  };
             verified <- validAsset downloaded digest;
             O.require verified "GitHub release asset SHA-256 mismatch";
             manifest <- unpack downloaded (work ++ "/bundle") expected;
             verifiedAfter <- validAsset downloaded digest;
             O.require verifiedAfter "GitHub release asset changed during extraction";
             saveBundleReceipt work manifest expected;
             O.remove destination;
             O.move work destination
           };
      releaseFileLock lock;
      ioReturn (destination ++ "/bundle/release.json")
    }
}
