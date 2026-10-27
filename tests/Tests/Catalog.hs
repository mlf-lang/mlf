-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.Catalog where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  groups =
    O.words
      "language code-generation runtime-library packages-build distribution bootstrap test-infrastructure";
  levels = O.words "component integration system";
  inputs = O.words "fixed exhaustive seeded-random transformed fault-injected";
  oracles =
    O.words "fixed-expected independent-reference differential metamorphic contract fixed-point";
  purposes = O.words "regression conformance robustness performance reproducibility";
  techniques =
    O.words "regression property-based differential metamorphic fault-injection fixed-point";
  campaigns = O.words "unit packages backends port parity self-host";
  unitIds =
    O.words
      "core figure12 regex harness test-framework package-integration package-distribution backends port parity self-host";
  migrated = O.words "core harness backends port";
  campaignIds name =
    if eqString name "unit"
    then O.words "regex harness test-framework core figure12"
    else if eqString name "packages"
         then O.words "package-integration package-distribution"
         else if S.elem eqString name (O.words "backends port parity self-host")
              then (:) name []
              else [];
  ensure condition message = if condition then Right () else Left message;
  sameSet left right =
    S.eqList eqString (S.sortBy compareString left) (S.sortBy compareString right);
  unique values = (S.length values == S.length (S.nubBy eqString values));
  keys names value =
    case value of {
      J.Object rows -> sameSet names (S.map S.fst rows);
      _ -> False
    };
  nonemptyString value =
    case value of {
      J.String text -> (stringLength text > 0);
      _ -> False
    };
  stringList value =
    case value of {
      J.Array rows -> S.all nonemptyString rows;
      _ -> False
    };
  validLabels allowed value =
    (stringList value &&
     (let {
        names = J.strings value
      } in
      (S.not (S.null names) &&
       (unique names && S.all (\name -> S.elem eqString name allowed) names))));
  validId name =
    ((stringLength name > 0) &&
     S.all
       (\i ->
          let {
            code = stringCodeAt name i
          } in
          (((code >= 48) && (code <= 57)) ||
           (((code >= 65) && (code <= 90)) ||
            (((code >= 97) && (code <= 122)) ||
             S.elem eqInt code ((:) 45 ((:) 46 ((:) 47 ((:) 95 []))))))))
       (S.range 0 (stringLength name - 1)));
  natural value =
    case value of {
      J.Number text ->
        ((stringLength text > 0) &&
         S.all
           (\i ->
              let {
                c = stringCodeAt text i
              } in
              ((c >= 48) && (c <= 57)))
           (S.range 0 (stringLength text - 1)));
      _ -> False
    };
  units catalog = J.values (J.get "units" catalog);
  families catalog = J.values (J.get "families" catalog);
  identity entry = J.getText "id" "" entry;
  unitName entry = J.getText "unit" "" entry;
  forUnit catalog name = S.filter (\entry -> eqString (unitName entry) name) (families catalog);
  forCampaign catalog name =
    S.concatMap (forUnit catalog) (J.getStrings name (J.get "campaigns" catalog));
  family catalog name =
    S.fromMaybe J.empty (S.find (\entry -> eqString (identity entry) name) (families catalog));
  tags entry =
    S.append
      ((:) ("group:" ++ J.getText "group" "" entry)
         ((:) ("level:" ++ J.getText "level" "" entry) []))
      (S.concatMap
         (\((,) field prefix) -> S.map (\name -> (prefix ++ name)) (J.getStrings field entry))
         ((:) ((,) "inputs" "input:")
            ((:) ((,) "oracles" "oracle:") ((:) ((,) "purposes" "purpose:") []))));
  descriptor entry = J.set "tags" (J.stringArray (tags entry)) entry;
  batches selected =
    let {
      names = S.nubBy eqString (S.map unitName selected)
    } in
    let {
      both =
        S.all (\name -> S.elem eqString name names)
          (O.words "package-integration package-distribution")
    } in
    S.map
      (\name ->
         if (both && eqString name "package-integration")
         then (,) "packages"
                (S.filter
                   (\entry ->
                      S.elem eqString (unitName entry)
                        (O.words "package-integration package-distribution"))
                   selected)
         else (,) name (S.filter (\entry -> eqString (unitName entry) name) selected))
      (S.filter (\name -> S.not (both && eqString name "package-distribution")) names);
  suiteName name =
    if S.elem eqString name (O.words "package-integration package-distribution")
    then "packages"
    else name;
  coverageFamilies selected =
    S.filter (\entry -> eqString (J.getText "kind" "" (J.get "evidence" entry)) "coverage")
      selected;
  combine field selected =
    S.concatMap (\entry -> J.getStrings field (J.get "evidence" entry)) selected;
  combineObject field selected =
    J.Object (S.concatMap (\entry -> J.items (J.get field (J.get "evidence" entry))) selected);
  projection inventory suite selected =
    let {
      source = J.get suite (J.get "suites" inventory)
    } in
    let {
      wanted = combine "executions" selected
    } in
    let {
      aliases = S.map S.fst (J.items (combineObject "aliases" selected))
    } in
    let {
      metrics = S.map S.fst (J.items (combineObject "metrics" selected))
    } in
    J.Object
      ((:)
         ((,) "executions"
            (J.stringArray
               (S.filter (\name -> S.elem eqString name wanted)
                  (J.getStrings "executions" source))))
         ((:)
            ((,) "aliases"
               (J.Object
                  (S.filter (\((,) name _) -> S.elem eqString name aliases)
                     (J.items (J.get "aliases" source)))))
            ((:)
               ((,) "metrics"
                  (J.Object
                     (S.filter (\((,) name _) -> S.elem eqString name metrics)
                        (J.items (J.get "metrics" source)))))
               [])));
  matrixRows selected =
    S.sum
      (S.map
         (\entry ->
            case J.get "rows" (J.get "evidence" entry) of {
              J.Number text -> readInt text;
              _ -> 0
            })
         selected);
  fixtures selected = S.map (J.getText "fixture" "") selected;
  validate :: J.Json -> Either String ();
  validate catalog =
    do {
      ensure
        (keys
           (O.words
              "schema_version granularity groups levels inputs oracles purposes profiles campaigns units families")
           catalog &&
         J.equal (J.get "schema_version" catalog) (J.num 2))
        "invalid test catalog schema";
      ensure (J.equal (J.get "granularity" catalog) (J.str "verified-case-or-family"))
        "unsupported catalog granularity";
      S.mapM_
        (\((,) field allowed) ->
           ensure
             (stringList (J.get field catalog) &&
              (unique (J.getStrings field catalog) && sameSet (J.getStrings field catalog) allowed))
             ("catalog vocabulary changed: " ++ field))
        ((:) ((,) "groups" groups)
           ((:) ((,) "levels" levels)
              ((:) ((,) "inputs" inputs)
                 ((:) ((,) "oracles" oracles)
                    ((:) ((,) "purposes" purposes)
                       ((:) ((,) "profiles" (O.words "smoke full stress release")) []))))));
      ensure
        (case J.get "units" catalog of {
           J.Array _ -> True;
           _ -> False
         })
        "catalog units must be an array";
      S.mapM_
        (\entry ->
           ensure
             (keys (O.words "id name") entry &&
              (nonemptyString (J.get "id" entry) && nonemptyString (J.get "name" entry)))
             "invalid execution unit")
        (units catalog);
      ensure
        (sameSet (S.map identity (units catalog)) unitIds &&
         unique (S.map identity (units catalog)))
        "catalog execution units changed";
      ensure
        (case J.get "families" catalog of {
           J.Array rows -> S.not (S.null rows);
           _ -> False
         })
        "catalog families must be a nonempty array";
      let {
        entries = families catalog
      };
      S.mapM_
        (\entry ->
           do {
             ensure
               (case entry of {
                  J.Object _ -> True;
                  _ -> False
                })
               "family must be an object";
             ensure
               (S.all (\field -> nonemptyString (J.get field entry))
                  (O.words "id unit name group level"))
               "family identity and classification must be strings";
             let {
               name = unitName entry
             };
             ensure
               (keys
                  (S.append (O.words "id unit name group level inputs oracles purposes evidence")
                     (if eqString name "port" then (:) "fixture" [] else []))
                  entry)
               "invalid family fields";
             ensure
               (validId (identity entry) &&
                (O.starts (name ++ "/") (identity entry) &&
                 (nonemptyString (J.get "name" entry) && S.elem eqString name unitIds)))
               "invalid family identity or execution unit";
             ensure
               (S.elem eqString (J.getText "group" "" entry) groups &&
                S.elem eqString (J.getText "level" "" entry) levels)
               "invalid primary group or test level";
             ensure
               (validLabels inputs (J.get "inputs" entry) &&
                (validLabels oracles (J.get "oracles" entry) &&
                 validLabels purposes (J.get "purposes" entry)))
               "invalid input, oracle or purpose labels";
             let {
               evidence = J.get "evidence" entry
             };
             ensure
               (case evidence of {
                  J.Object _ -> nonemptyString (J.get "kind" evidence);
                  _ -> False
                })
               "family evidence must be an object with a kind";
             let {
               kind = J.getText "kind" "" evidence
             };
             if S.elem eqString name (O.words "backends port")
             then do {
                    ensure
                      (eqString kind "matrix" &&
                       (keys (O.words "kind rows fixtures labels") evidence &&
                        (natural (J.get "rows" evidence) &&
                         (natural (J.get "fixtures" evidence) &&
                          stringList (J.get "labels" evidence)))))
                      "invalid matrix family evidence";
                    ensure
                      (S.not (S.null (J.getStrings "labels" evidence)) &&
                       (S.length (J.getStrings "labels" evidence) ==
                        readInt
                          (case J.get "fixtures" evidence of {
                             J.Number text -> text;
                             _ -> "-1"
                           })))
                      "matrix fixture labels or counts changed";
                    if eqString name "port"
                    then ensure
                           (nonemptyString (J.get "fixture" entry) &&
                            (J.equal (J.get "rows" evidence) (J.num 1) &&
                             (J.equal (J.get "fixtures" evidence) (J.num 1) &&
                              J.equal (J.get "labels" evidence)
                                (J.Array ((:) (J.get "fixture" entry) [])))))
                           "invalid port family"
                    else Right ()
                  }
             else if S.elem eqString name (O.words "parity self-host")
                  then ensure (eqString kind "unit" && keys ((:) "kind" []) evidence)
                         "invalid whole-unit family evidence"
                  else do {
                         ensure
                           (eqString kind "coverage" &&
                            (keys (O.words "kind executions aliases metrics") evidence &&
                             (stringList (J.get "executions" evidence) &&
                              unique (J.getStrings "executions" evidence))))
                           "invalid structural family evidence";
                         ensure
                           (case J.get "aliases" evidence of {
                              J.Object _ -> True;
                              _ -> False
                            })
                           "family aliases must be an object";
                         ensure
                           (case J.get "metrics" evidence of {
                              J.Object _ -> True;
                              _ -> False
                            })
                           "family metrics must be an object";
                         ensure
                           (S.not
                              (S.null (J.getStrings "executions" evidence) &&
                               (S.null (J.items (J.get "aliases" evidence)) &&
                                S.null (J.items (J.get "metrics" evidence)))))
                           "empty test family evidence"
                       }
           })
        entries;
      ensure (unique (S.map identity entries)) "duplicate test family ID";
      ensure (sameSet (S.nubBy eqString (S.map unitName entries)) unitIds)
        "catalog omits an execution unit";
      S.mapM_
        (\name ->
           ensure (S.length (forUnit catalog name) == 1)
             ("execution unit requires one complete family: " ++ name))
        (S.filter (\name -> S.not (S.elem eqString name migrated)) unitIds);
      ensure (sameSet (S.nubBy eqString (S.map (J.getText "group" "") entries)) groups)
        "catalog omits a primary group";
      let {
        mapping = J.get "campaigns" catalog
      };
      ensure (keys campaigns mapping) "catalog campaign inventory changed";
      S.mapM_
        (\name ->
           ensure
             (stringList (J.get name mapping) &&
              S.eqList eqString (J.getStrings name mapping) (campaignIds name))
             ("catalog changed preserved campaign: " ++ name))
        campaigns;
      ensure
        ((matrixRows (forUnit catalog "backends") == 583) &&
         (S.sum
            (S.map
               (\entry ->
                  readInt
                    (case J.get "fixtures" (J.get "evidence" entry) of {
                       J.Number text -> text;
                       _ -> "0"
                     }))
               (forUnit catalog "backends")) ==
          531))
        "backend family partition changed";
      ensure (unique (combine "labels" (forUnit catalog "backends")))
        "duplicate backend fixture label";
      ensure
        ((S.length (forUnit catalog "port") == 25) &&
         ((matrixRows (forUnit catalog "port") == 25) &&
          unique (fixtures (forUnit catalog "port"))))
        "port family partition changed"
    };
  validateInventory :: J.Json -> J.Json -> Either String ();
  validateInventory catalog inventory =
    do {
      validate catalog;
      ensure
        (case inventory of {
           J.Object _ -> J.equal (J.get "schema_version" inventory) (J.num 1);
           _ -> False
         })
        "unsupported coverage inventory";
      ensure
        (case J.get "suites" inventory of {
           J.Object _ -> True;
           _ -> False
         })
        "coverage suites must be an object";
      ensure
        (keys (O.words "core harness regex figure12 test-framework packages")
           (J.get "suites" inventory))
        "coverage suite inventory changed";
      S.mapM_
        (\suite ->
           do {
             let {
               chosen =
                 S.filter (\entry -> eqString (suiteName (unitName entry)) suite)
                   (coverageFamilies (families catalog))
             };
             let {
               source = J.get suite (J.get "suites" inventory)
             };
             ensure
               (keys (O.words "executions aliases metrics") source &&
                stringList (J.get "executions" source))
               "invalid reviewed suite inventory";
             ensure
               (case J.get "aliases" source of {
                  J.Object _ -> True;
                  _ -> False
                })
               "invalid reviewed aliases";
             ensure
               (case J.get "metrics" source of {
                  J.Object _ -> True;
                  _ -> False
                })
               "invalid reviewed metrics";
             ensure
               (unique (combine "executions" chosen) &&
                sameSet (combine "executions" chosen) (J.getStrings "executions" source))
               ("family execution partition changed: " ++ suite);
             S.mapM_
               (\field ->
                  do {
                    let {
                      declared = combineObject field chosen
                    };
                    let {
                      original = J.get field source
                    };
                    ensure
                      (unique (S.map S.fst (J.items declared)) &&
                       (sameSet (S.map S.fst (J.items declared)) (S.map S.fst (J.items original)) &&
                        S.all (\((,) name value) -> J.equal value (J.get name original))
                          (J.items declared)))
                      ("family " ++ (field ++ (" partition changed: " ++ suite)))
                  })
               (O.words "aliases metrics")
           })
        (O.words "core harness regex figure12 test-framework packages")
    };
  legacyMatches entry method =
    if eqString method "regression"
    then S.elem eqString method (J.getStrings "purposes" entry)
    else if eqString method "property-based"
         then S.any (\name -> S.elem eqString name (J.getStrings "inputs" entry))
                (O.words "exhaustive seeded-random")
         else if eqString method "differential"
              then S.any (\name -> S.elem eqString name (J.getStrings "oracles" entry))
                     (O.words "independent-reference differential")
              else if eqString method "metamorphic"
                   then S.elem eqString method (J.getStrings "oracles" entry)
                   else if eqString method "fault-injection"
                        then S.elem eqString "fault-injected" (J.getStrings "inputs" entry)
                        else (eqString method "fixed-point" &&
                              S.elem eqString method (J.getStrings "oracles" entry));
  select :: J.Json -> J.Json -> Either String ([] J.Json);
  select catalog settings =
    do {
      validate catalog;
      ensure
        (case settings of {
           J.Object _ -> True;
           _ -> False
         })
        "test selectors must be an object";
      S.mapM_
        (\field ->
           ensure (S.not (J.has field settings) || nonemptyString (J.get field settings))
             ("invalid test selector: " ++ field))
        (O.words "group level unit campaign");
      S.mapM_
        (\field ->
           ensure
             (S.not (J.has field settings) ||
              (stringList (J.get field settings) && S.not (S.null (J.getStrings field settings))))
             ("invalid test selector: " ++ field))
        (O.words "inputs oracles purposes techniques families");
      let {
        campaign = J.getText "campaign" "" settings
      };
      ensure (eqString campaign "" || S.elem eqString campaign campaigns) "unknown test campaign";
      S.mapM_
        (\((,,) field vocabulary label) ->
           ensure (S.all (\name -> S.elem eqString name vocabulary) (J.getStrings field settings))
             ("unknown " ++ label))
        ((:) ((,,) "inputs" inputs "input method")
           ((:) ((,,) "oracles" oracles "test oracle")
              ((:) ((,,) "purposes" purposes "test purpose")
                 ((:) ((,,) "techniques" techniques "legacy technique")
                    ((:) ((,,) "families" (S.map identity (families catalog)) "test family")
                       [])))));
      S.mapM_
        (\((,) field vocabulary) ->
           ensure
             (S.not (J.has field settings) ||
              S.elem eqString (J.getText field "" settings) vocabulary)
             ("unknown test " ++ field))
        ((:) ((,) "group" groups) ((:) ((,) "level" levels) ((:) ((,) "unit" unitIds) [])));
      ensure (unique (J.getStrings "families" settings)) "duplicate family selector";
      let {
        available = if eqString campaign "" then families catalog else forCampaign catalog campaign
      };
      let {
        chosen =
          S.filter
            (\entry ->
               (S.all
                  (\field ->
                     (S.not (J.has field settings) ||
                      eqString (J.getText field "" entry) (J.getText field "" settings)))
                  (O.words "group level unit") &&
                (S.all
                   (\field ->
                      S.all (\name -> S.elem eqString name (J.getStrings field entry))
                        (J.getStrings field settings))
                   (O.words "inputs oracles purposes") &&
                 (S.all (legacyMatches entry) (J.getStrings "techniques" settings) &&
                  (S.not (J.has "families" settings) ||
                   S.elem eqString (identity entry) (J.getStrings "families" settings))))))
            available
      };
      ensure (S.not (S.null chosen)) "no cases or test families matched selection";
      return chosen
    };
  selection catalog selected =
    J.Object
      ((:) ((,) "granularity" (J.get "granularity" catalog))
         ((:) ((,) "families" (J.Array (S.map descriptor selected)))
            ((:) ((,) "units" (J.stringArray (S.nubBy eqString (S.map unitName selected))))
               [])));
  load root =
    do {
      catalog <- J.read (root ++ "/tests/test-catalog.json");
      inventory <- J.read (root ++ "/tests/golden/unit-inventory.json");
      case validateInventory catalog inventory of {
        Left error -> O.fatal error;
        Right _ -> return catalog
      }
    };
  add config name value =
    J.set name (J.stringArray (S.snoc (J.getStrings name config) value)) config;
  single config field value =
    do {
      ensure ((stringLength value > 0) && S.not (J.has field config))
        ("empty or duplicate " ++ (field ++ " selector"));
      return (J.set field (J.str value) config)
    };
  option config flag value =
    if S.elem eqString flag (O.words "--group --category")
    then single config "group" value
    else if eqString flag "--level"
         then single config "level" value
         else if eqString flag "--unit"
              then single config "unit" value
              else if eqString flag "--campaign"
                   then single config "campaign" value
                   else if eqString flag "--family"
                        then Right (add config "families" value)
                        else if eqString flag "--input"
                             then Right (add config "inputs" value)
                             else if eqString flag "--oracle"
                                  then Right (add config "oracles" value)
                                  else if eqString flag "--purpose"
                                       then Right (add config "purposes" value)
                                       else if eqString flag "--technique"
                                            then Right (add config "techniques" value)
                                            else Left "unknown test selection option";
  selector flag =
    S.elem eqString flag
      (O.words
         "--group --category --level --unit --campaign --family --input --oracle --purpose --technique");
  hasSelection settings =
    S.any (\field -> J.has field settings)
      (O.words "group level unit campaign families inputs oracles purposes techniques");
  parse :: J.Json -> [] String -> Either String J.Json;
  parse config args =
    let {
      matchValueShared1 = args
    } in
    case matchValueShared1 of {
      [] -> Right config;
      (:) matchValueShared2 matchValueShared3 ->
        if MLF.Primitive.eqString matchValueShared2 "--list"
        then let {
               rest = matchValueShared3
             } in
             parse config rest
        else if MLF.Primitive.eqString matchValueShared2 "--format"
             then case matchValueShared3 of {
                    (:) matchValueShared6 matchValueShared7 ->
                      let {
                        value = matchValueShared6
                      } in
                      let {
                        rest = matchValueShared7
                      } in
                      do {
                        ensure (S.elem eqString value (O.words "text json"))
                          "catalog format must be text or json";
                        parse (J.set "format" (J.str value) config) rest
                      };
                    _ ->
                      Left
                        "catalog [--group NAME] [--level NAME] [--input NAME] [--oracle NAME] [--purpose NAME] [--family ID] [--unit NAME] [--campaign NAME] [--format text|json]"
                  }
             else case matchValueShared3 of {
                    (:) matchValueShared4 matchValueShared5 ->
                      let {
                        value = matchValueShared4
                      } in
                      let {
                        rest = matchValueShared5
                      } in
                      let {
                        flag = matchValueShared2
                      } in
                      do {
                        ensure (selector flag && (stringLength value > 0))
                          "invalid catalog selector";
                        updated <- option config flag value;
                        parse updated rest
                      };
                    _ ->
                      Left
                        "catalog [--group NAME] [--level NAME] [--input NAME] [--oracle NAME] [--purpose NAME] [--family ID] [--unit NAME] [--campaign NAME] [--format text|json]"
                  };
      _ ->
        Left
          "catalog [--group NAME] [--level NAME] [--input NAME] [--oracle NAME] [--purpose NAME] [--family ID] [--unit NAME] [--campaign NAME] [--format text|json]"
    };
  main args =
    do {
      settings <-
        case parse J.empty args of {
          Left error -> O.fatal error;
          Right value -> return value
        };
      root <- canonicalPath ".";
      catalog <- load root;
      chosen <-
        case select catalog settings of {
          Left error -> O.fatal error;
          Right value -> return value
        };
      if eqString (J.getText "format" "text" settings) "json"
      then putStrLn
             (J.render
                (J.set "schema_version" (J.num 2)
                   (J.set "event" (J.str "catalog") (selection catalog chosen))))
      else do {
             putStrLn "Test catalog (independently selectable cases and complete test families)";
             S.mapM_
               (\entry ->
                  putStrLn
                    (identity entry ++
                     ("\t" ++
                      (J.getText "name" "" entry ++ ("\t" ++ S.intercalate " " (tags entry))))))
               chosen
           }
    }
}
