-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.CompilerTests where {
  import MLF.Primitive;
  import qualified Tests.BuildReceipts as BuildReceipts;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as Map;
  import qualified Bootstrap.Set as Set;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Build as B;
  import qualified Package.Command as C;
  import qualified Package.Verification as V;
  import qualified Package.Manifest as M;
  import qualified Tests.Coverage as Coverage;
  import qualified Tests.TestDrivers as TD;
  import qualified Tests.TestSources as TS;
  import qualified Tests.Catalog as Catalog;
  import qualified Tests.Selection as Selection;
  import qualified Tests.CorePartitions as CorePartitions;
  import qualified Test.Assert as TestAssert;
  import qualified Test.Case as TestCase;
  import qualified Test.Runner as TestRunner;
  -- Build and execute native MLF tests; preserved oracle data and test-only
  -- checking modules remain independent of the candidate compiler.
  data TestContext = TestContext String String String ([] String) String String;
  root :: TestContext -> String;
  root (TestContext r _ _ _ _ _) = r;
  output :: TestContext -> String;
  output (TestContext _ d _ _ _ _) = d;
  compiler :: TestContext -> String;
  compiler (TestContext _ _ c _ _ _) = c;
  runtimeProfiles :: TestContext -> [] String;
  runtimeProfiles (TestContext _ _ _ profiles _ _) = profiles;
  sharedCache :: TestContext -> String;
  sharedCache (TestContext _ _ _ _ cache _) = cache;
  packageManager :: TestContext -> String;
  packageManager (TestContext _ _ _ _ _ manager) = manager;
  cacheOptions :: TestContext -> [] String;
  cacheOptions c =
    if eqString (sharedCache c) "" then [] else (:) "--cache-dir" ((:) (sharedCache c) []);
  report :: TestContext -> String;
  report c = (output c ++ "/verification.json");
  record :: TestContext -> String -> J.Json -> IO ();
  record c key value =
    do {
      saved <- J.read (report c);
      J.write (report c) (J.set key value saved)
    };
  run :: TestContext -> [] String -> IO ();
  run c argv =
    do {
      putStrLn ("+ " ++ S.intercalate " " argv);
      code <- O.exec (root c) argv "" "" "" 1800;
      O.require (code == 0)
        ("compiler test command failed (" ++ (showInt code ++ ("): " ++ S.intercalate " " argv)))
    };
  query :: TestContext -> [] String -> IO String;
  query c argv = B.raw (output c) argv;
  capture :: TestContext -> [] String -> String -> IO ();
  capture c argv destination = captureWithin c argv destination 1800;
  captureWithin :: TestContext -> [] String -> String -> Int -> IO ();
  captureWithin c argv destination seconds =
    do {
      let {
        errors = (destination ++ ".stderr")
      };
      putStrLn ("+ " ++ S.intercalate " " argv);
      code <- O.exec (root c) argv "" destination errors seconds;
      if (code == 0)
      then ioReturn ()
      else do {
             text <- readFile errors;
             O.fatal ("compiler test command failed (" ++ (showInt code ++ ("): " ++ text)))
           }
    };
  walk :: String -> IO ([] String);
  walk path =
    do {
      present <- fileExists path;
      if present
      then ioReturn ((:) path [])
      else do {
             names <- O.entries path;
             nested <-
               S.mapM (\name -> walk (O.join path name))
                 (S.filter
                    (\name ->
                       S.not
                         (S.elem eqString name
                            (O.words ".mlf-build .git dist-newstyle __pycache__")))
                    names);
             ioReturn (S.concat nested)
           }
    };
  sources :: String -> IO J.Json;
  sources r =
    do {
      nested <-
        S.mapM (\dir -> walk (r ++ ("/" ++ dir)))
          (O.words "scripts runtime bootstrap package libraries examples benchmarks tests testing");
      let {
        paths =
          S.filter
            (\p ->
               (O.starts (r ++ "/benchmarks/") p ||
                S.any (\suffix -> O.ends suffix p)
                  (O.words ".hs .emlf .c .h .ps1 .sh .expected .json .jsonl .gz")))
            (S.concat nested)
      };
      hashes <-
        B.hashFiles (S.append paths ((:) (r ++ "/mlfpkg") ((:) (r ++ "/mlf-package.json") [])));
      ioReturn
        (J.Object
           (S.map (\entry -> (,) (O.relative r (S.fst entry)) (S.snd entry)) (J.items hashes)))
    };
  clearDrivers :: IO ();
  clearDrivers =
    S.mapM_ unsetEnv
      (O.words
         "MLF_BENCH_SPLIT_RUNTIME MLF_MOCK_FAIL_SUPERVISOR MLF_BENCH_STREAM_LINK MLF_MOCK_FAIL_RUNTIME MLF_BENCH_STREAM_LLVM MLF_BENCH_MLF_CLANG MLF_MOCK_FAST_FRONTEND MLF_BOOTSTRAP_INTERPRETER MLF_BOOTSTRAP_LLVM MLF_BOOTSTRAP_TIMEOUT_SECONDS MLF_TEST_TRACE MLF_TEST_FAIL_WRITE MLF_LLVM_TEST_ABI MLF_LLVM_TEST_CFLAGS MLF_LLVM_TEST_LIBS MLF_LLVM_TEST_OPT MLF_TEST_PORT_TARGETS MLF_TEST_PORT_TARGETS_SHA256");
  nativeFlags :: TestContext -> IO ([] String);
  nativeFlags c =
    do {
      windows <- O.isWindows;
      text <- query c ((:) "pkg-config" (O.words "--cflags --libs gmp"));
      extra <-
        do {
          prefix <- getEnv "MLF_GC_PREFIX";
          if eqString prefix ""
          then do {
                 flags <- query c ((:) "pkg-config" (O.words "--cflags --libs bdw-gc"));
                 ioReturn (B.flags flags)
               }
          else do {
                 actual <- canonicalPath prefix;
                 system <- query c (O.words "uname -s");
                 let {
                   library = (actual ++ (if windows then "/lib/libgc.dll.a" else "/lib/libgc.a"))
                 };
                 ioReturn
                   ((:) ("-I" ++ (actual ++ "/include"))
                      ((:) library
                         (if eqString (O.trim system) "Linux" then (:) "-ldl" [] else [])))
               }
        };
      ioReturn
        (S.append (B.flags text)
           (S.append extra (if windows then O.words "-lshell32 -Wl,--stack,268435456" else [])))
    };
  stack :: TestContext -> IO ([] String);
  stack c =
    do {
      system <- query c (O.words "uname -s");
      ioReturn
        (if eqString (O.trim system) "Darwin" then (:) "-Wl,-stack_size,0x10000000" [] else [])
    };
  compileRuntime :: TestContext -> [] String -> Bool -> String -> IO ();
  compileRuntime c flags trace name =
    do {
      let {
        interpose =
          if trace
          then O.words
                 "-Dgetline=mlf_test_getline -Dfwrite=mlf_test_fwrite -Dfputc=mlf_test_fputc -Dfflush=mlf_test_fflush"
          else []
      };
      run c
        (S.append (O.words "clang -O2 -std=c11 -Wall -Wextra -Werror")
           (S.append (S.filter (O.starts "-I") flags)
              (S.append []
                 (S.append interpose
                    ((:) "-c"
                       ((:) (root c ++ "/runtime/mlf_runtime.c")
                          ((:) "-o" ((:) (output c ++ ("/" ++ name)) []))))))))
    };
  link :: TestContext -> String -> [] String -> [] String -> String -> [] String -> IO ();
  link c ir objects flags binary extra =
    run c
      (S.append (O.words "clang -O2 -Wno-override-module")
         (S.append ((:) ir objects)
            (S.append flags (S.append ((:) "-lm" extra) ((:) "-o" ((:) binary []))))));
  -- Build each selected target set once so shared dependencies form one DAG.
  -- Execution remains sequential because suites deliberately mutate process-wide
  -- environment variables and use shared native fixture work directories.
  nativeTests :: TestContext -> [] String -> IO ();
  -- A failure before the manager writes a report must not retain an older pass.
  -- Keep every invocation's report, including a failed build, before another
  -- package-manager invocation can replace the canonical report.
  nativeTests c targets =
    do {
      O.require (S.not (S.null targets) && Selection.unique targets)
        "invalid native test target batch";
      jobs <- O.envDefault "MLF_TEST_BUILD_JOBS" "1";
      O.require (S.elem eqString jobs (O.words "1 2")) "MLF_TEST_BUILD_JOBS must be 1 or 2";
      let {
        manager = packageManager c
      };
      let {
        build = (output c ++ "/suite-build")
      };
      invocation <- O.temporaryDirectory (output c) (output c ++ "/suite-build-invocation-");
      let {
        args =
          S.concat
            ((:) ((:) manager [])
               ((:) ((:) "--manifest" ((:) (root c ++ "/tests/mlf-package.json") []))
                  ((:) ((:) "--compiler" ((:) (compiler c) []))
                     ((:) ((:) "--runtime" ((:) (root c ++ "/runtime/mlf_runtime.c") []))
                        ((:) ((:) "--build-dir" ((:) build []))
                           ((:)
                              (S.append (cacheOptions c)
                                 (S.append (O.words "--timeout 21600")
                                    ((:) "--jobs"
                                       ((:) jobs
                                          ((:) "build"
                                             (S.concatMap
                                                (\target -> (:) "--target" ((:) target []))
                                                targets))))))
                              []))))))
      };
      let {
        current = (build ++ "/build-report.json")
      };
      O.remove current;
      putStrLn ("+ " ++ S.intercalate " " args);
      code <- O.exec (root c) args "" "" "" 21600;
      let {
        retained = (invocation ++ "/build-report.json")
      };
      present <- fileExists current;
      digest <-
        if present
        then do {
               O.copy current retained;
               fileDigest retained
             }
        else return "";
      saved <- J.read (report c);
      let {
        receipt =
          B.info
            ((:) ((,) "path" (J.str retained))
               ((:) ((,) "sha256" (J.str digest))
                  ((:) ((,) "targets" (J.stringArray targets))
                     ((:) ((,) "jobs" (J.num (readInt jobs)))
                        ((:) ((,) "exit_code" (J.num code))
                           ((:) ((,) "command" (J.stringArray args)) []))))))
      };
      record c "suite_builds"
        (BuildReceipts.appendSuiteBuildReceipt saved receipt);
      O.require ((code == 0) && present) ("native test build failed (" ++ (showInt code ++ ")"));
      binaries <-
        S.mapM
          (\target ->
             do {
               binary <- O.executable (build ++ ("/bin/" ++ target));
               hash <- fileDigest binary;
               return ((,) target (B.obj2 "path" (J.str binary) "sha256" (J.str hash)))
             })
          targets;
      currentReport <- J.read (report c);
      let {
        prepared =
          S.foldl (\all ((,) name value) -> J.set name value all)
            (J.getObject "prepared_suite_targets" currentReport)
            binaries
      };
      record c "prepared_suite_targets" prepared
    };
  nativeTest :: TestContext -> String -> IO String;
  nativeTest c target =
    do {
      saved <- J.read (report c);
      if J.has target (J.getObject "prepared_suite_targets" saved)
      then return ()
      else nativeTests c ((:) target []);
      current <- J.read (report c);
      let {
        prepared = J.get target (J.get "prepared_suite_targets" current)
      };
      let {
        binary = J.getText "path" "" prepared
      };
      hash <- fileDigest binary;
      O.require (eqString hash (J.getText "sha256" "" prepared))
        (target ++ ": prepared test executable changed");
      return binary
    };
  transports :: TestContext -> IO ();
  transports c =
    do {
      S.mapM_
        (\((,) source target) ->
           run c
             (S.append (O.words "clang -O2 -std=c11 -Wall -Wextra -Werror")
                ((:) (root c ++ ("/tests/native/" ++ source))
                   ((:) "-o" ((:) (output c ++ ("/" ++ target)) [])))))
        ((:) ((,) "binary_files.c" "binary-files")
           ((:) ((,) "host_support.c" "host-support") []));
      setEnv "MLF_TEST_BINARY_FILES" (output c ++ "/binary-files");
      setEnv "MLF_TEST_HOST_SUPPORT" (output c ++ "/host-support");
      setEnv "MLF_TEST_WORK" (output c);
      setEnv "MLF_TEST_ROOT" (output c)
    };
  suite :: TestContext -> String -> [] String -> IO ();
  suite c target expectations = suiteArgs c target [] expectations;
  suiteArgs :: TestContext -> String -> [] String -> [] String -> IO ();
  suiteArgs c target args expectations = suiteArgsChecked c target args expectations Nothing;
  familyReport :: TestContext -> String -> String -> Bool -> [] String -> String -> IO ();
  familyReport c key unit full expected path =
    do {
      text <- readFile path;
      checked <-
        case Selection.validate unit full expected text of {
          Left error -> O.fatal (unit ++ (": " ++ error));
          Right value -> return value
        };
      hash <- fileDigest path;
      saved <- J.read (report c);
      record c "family_reports"
        (J.set key
           (J.set "path" (J.str path)
              (J.set "sha256" (J.str hash) (J.set "result" checked J.empty)))
           (J.getObject "family_reports" saved))
    };
  suiteArgsChecked :: TestContext ->
                      String -> [] String -> [] String -> Maybe J.Json -> IO ();
  suiteArgsChecked c target args expectations selected =
    suiteArgsEvidence c target args expectations selected Nothing;
  caseReport :: String -> IO J.Json;
  caseReport path =
    do {
      text <- readFile path;
      rows <- case S.mapM J.parse (O.nonempty (O.lines text)) of {
                Left message -> O.fatal (path ++ (": " ++ message));
                Right value -> return value
              };
      O.require (S.length rows >= 3) (path ++ ": incomplete framework report");
      let {
        start = S.head rows;
        summary = S.head (S.reverse rows);
        observations = S.take (S.length rows - 2) (S.drop 1 rows);
        planned = J.getStrings "ids" start;
        actual = S.map (J.getText "id" "") observations
      };
      O.require
        (eqString (J.getText "event" "" start) "start" &&
         eqString (J.getText "event" "" summary) "summary" &&
         S.all (\row -> J.equal (J.get "schema_version" row) (J.num 1)) rows &&
         J.equal (J.get "complete" summary) (J.Boolean True) &&
         J.equal (J.get "selected" summary) (J.num (S.length planned)) &&
         J.equal (J.get "executed" summary) (J.num (S.length actual)) &&
         J.equal (J.get "failed" summary) (J.num 0) &&
         Catalog.unique planned && S.eqList eqString planned actual &&
         S.all (\row -> eqString (J.getText "event" "" row) "case" &&
                        eqString (J.getText "status" "" row) "passed") observations)
        (path ++ ": framework report did not pass its exact plan");
      digest <- fileDigest path;
      return (J.set "case_report" (J.str path)
               (J.set "case_report_sha256" (J.str digest)
                  (J.set "framework_case_ids" (J.stringArray actual) J.empty)))
    };
  coreRegistryDiscovery :: TestContext -> String -> String -> IO ((,) Int J.Json);
  coreRegistryDiscovery c target binary =
    do {
      let {
        contractPath = root c ++ "/tests/golden/core-registry-contract.json";
        path = output c ++ ("/" ++ (target ++ ".inventory.json"));
        families = if eqString target "core" then CorePartitions.familyNames
                   else CorePartitions.forTarget target
      };
      contract <- J.read contractPath;
      contractDigest <- fileDigest contractPath;
      capture c ((:) binary (O.words "--list --format json")) path;
      text <- readFile path;
      total <- case Coverage.validateRegistryDiscovery contract families text of {
        Left message -> O.fatal (target ++ (": " ++ message));
        Right value -> return value
      };
      digest <- fileDigest path;
      return ((,) total (J.set "path" (J.str path)
        (J.set "sha256" (J.str digest)
          (J.set "contract_path" (J.str contractPath)
            (J.set "contract_sha256" (J.str contractDigest) J.empty)))))
    };
  suiteArgsEvidence :: TestContext ->
                       String ->
                       [] String -> [] String -> Maybe J.Json -> Maybe ([] String) -> IO ();
  suiteArgsEvidence c target args expectations selected wantedFamilies =
    do {
      binary <- nativeTest c target;
      binaryHash <- fileDigest binary;
      let {
        log = (output c ++ ("/" ++ (target ++ ".log")))
      };
      let {
        shard = S.elem eqString target CorePartitions.targets
      };
      let {
        unit = if shard then "core" else target
      };
      (,) registryTotal registry <- if eqString unit "core" then coreRegistryDiscovery c target binary
                                   else return ((,) 0 J.empty);
      let {
        structural =
          (shard ||
           S.elem eqString target (O.words "harness test-framework core figure12 packages regex"))
      };
      let {
        coverage = (output c ++ ("/" ++ (target ++ ".coverage.jsonl")))
      };
      if structural
      then do {
             writeFile coverage "";
             setEnv "MLF_TEST_COVERAGE_REPORT" coverage
           }
      else unsetEnv "MLF_TEST_COVERAGE_REPORT";
      let {
        familyPath = (output c ++ ("/" ++ (target ++ ".families.jsonl")))
      };
      let {
        tracked = (shard || S.elem eqString target (O.words "core harness"))
      };
      expectedFamilies <-
        if tracked
        then do {
               catalog <- Catalog.load (root c);
               writeFile familyPath "";
               setEnv "MLF_TEST_FAMILY_REPORT" familyPath;
               return
                 (case wantedFamilies of {
                    Just names -> names;
                    Nothing -> S.map Catalog.identity (Catalog.forUnit catalog unit)
                  })
             }
        else do {
               unsetEnv "MLF_TEST_FAMILY_REPORT";
               return []
             };
      let {
        casePath = output c ++ ("/" ++ (target ++ ".cases.jsonl"));
        legacyFamilyArgs = case args of { (:) "--families" _ -> True; _ -> False };
        command = if structural && S.not legacyFamilyArgs then S.append args ((:) "--report" ((:) casePath [])) else args
      };
      if structural then do { writeFile casePath ""; setEnv "MLF_TEST_CASE_REPORT" casePath }
      else unsetEnv "MLF_TEST_CASE_REPORT";
      capture c ((:) binary command) log;
      unsetEnv "MLF_TEST_CASE_REPORT";
      observedCases <- if structural then caseReport casePath else ioReturn J.empty;
      cases <- if eqString unit "core" then do {
        contract <- J.read (J.getText "contract_path" "" registry);
        text <- readFile casePath;
        case Coverage.validateRegistryCases contract expectedFamilies registryTotal text of {
          Left message -> O.fatal (target ++ (": " ++ message));
          Right _ -> return ()
        };
        currentContract <- fileDigest (J.getText "contract_path" "" registry);
        currentInventory <- fileDigest (J.getText "path" "" registry);
        O.require (eqString currentContract (J.getText "contract_sha256" "" registry) &&
                   eqString currentInventory (J.getText "sha256" "" registry))
          "Core registry inventory changed during execution";
        return (J.set "registry_inventory" registry observedCases)
      } else return observedCases;
      currentBinaryHash <- fileDigest binary;
      O.require (eqString binaryHash currentBinaryHash)
        (target ++ ": test executable changed during validation");
      unsetEnv "MLF_TEST_COVERAGE_REPORT";
      unsetEnv "MLF_TEST_FAMILY_REPORT";
      if tracked
      then familyReport c target unit
             (case selected of {
                Nothing -> True;
                Just _ -> False
              })
             expectedFamilies
             familyPath
      else ioReturn ();
      text <- readFile log;
      O.require (S.all (\expected -> contains expected text) expectations)
        (target ++ ": preserved coverage summary is missing");
      evidence <-
        if structural
        then do {
               let {
                 inventoryPath = (root c ++ "/tests/golden/unit-inventory.json")
               };
               inventory <- J.read inventoryPath;
               actual <- readFile coverage;
               let {
                 validation =
                   case selected of {
                     Nothing -> Coverage.validate inventory unit actual;
                     Just projection -> Coverage.validateProjection inventory unit projection actual
                   }
               };
               checked <-
                 case validation of {
                   Left error -> O.fatal (target ++ (": " ++ error));
                   Right value -> return value
                 };
               digest <- fileDigest coverage;
               inventoryDigest <- fileDigest inventoryPath;
               let {
                 result =
                   J.set "scope"
                     (J.str
                        (case selected of {
                           Nothing -> "full";
                           Just _ -> "partial"
                         }))
                     (J.set "coverage_report_sha256" (J.str digest)
                        (J.set "coverage_inventory_sha256" (J.str inventoryDigest)
                           (J.set "coverage_result" checked J.empty)))
               };
               return
                 (case selected of {
                    Nothing -> result;
                    Just projection -> J.set "selected_coverage" projection result
                  })
             }
        else return J.empty;
      hash <- fileDigest log;
      saved <- J.read (report c);
      record c "suites"
        (J.set target
           (J.set "binary_sha256" (J.str binaryHash)
              (J.set "log_sha256" (J.str hash)
                 (J.set "coverage" (J.stringArray expectations)
                    (J.Object (S.append (J.items cases) (J.items evidence))))))
           (J.getObject "suites" saved));
      putStr (O.drop (S.max 0 (stringLength text - 2000)) text)
    };
  core :: TestContext -> Bool -> [] J.Json -> IO ();
  -- Unit has already prepared the complete batch; focused core builds only
  -- the compilation closures that own at least one requested family.
  core c full entries =
    do {
      catalog <- Catalog.load (root c);
      case CorePartitions.validate (S.map Catalog.identity (Catalog.forUnit catalog "core")) of {
        Left error -> O.fatal error;
        Right _ -> return ()
      };
      let {
        identities = S.map Catalog.identity entries
      };
      let {
        targets = CorePartitions.selectedTargets identities
      };
      O.require
        (S.not (S.null targets) &&
         (S.not full || S.eqList eqString identities CorePartitions.familyNames))
        "invalid core aggregate selection";
      inventory <- J.read (root c ++ "/tests/golden/unit-inventory.json");
      saved <- J.read (report c);
      if BuildReceipts.preparedSuiteTargets saved targets
      then return ()
      else nativeTests c targets;
      S.mapM_
        (\target ->
           do {
             let {
               selected =
                 S.filter
                   (\entry ->
                      S.elem eqString (Catalog.identity entry) (CorePartitions.forTarget target))
                   entries
             };
             let {
               wanted = S.map Catalog.identity selected
             };
             suiteArgsEvidence c target ((:) "--families" wanted) []
               (Just (Catalog.projection inventory "core" selected))
               (Just wanted)
           })
        targets;
      aggregateCore c full entries targets inventory
    };
  aggregateCore :: TestContext -> Bool -> [] J.Json -> [] String -> J.Json -> IO ();
  -- The aggregate is derived from the validated child bodies, never planned
  -- case IDs. Retain and bind every partial receipt before creating full scope.
  aggregateCore c full entries targets inventory =
    do {
      saved <- J.read (report c);
      let {
        identities = S.map Catalog.identity entries;
        caseIds = S.concatMap
          (\target -> J.getStrings "framework_case_ids" (J.get target (J.get "suites" saved)))
          targets
      };
      O.require (S.not (S.null caseIds) && Catalog.unique caseIds &&
                 (S.not full || S.length caseIds == 759))
        "Core physical registries did not form the reviewed case inventory";
      pieces <-
        S.mapM
          (\target ->
             do {
               let {
                 evidence = J.get target (J.get "suites" saved)
               };
               let {
                 coveragePath = (output c ++ ("/" ++ (target ++ ".coverage.jsonl")))
               };
               let {
                 familiesPath = (output c ++ ("/" ++ (target ++ ".families.jsonl")))
               };
               coverageHash <- fileDigest coveragePath;
               familyHash <- fileDigest familiesPath;
               O.require
                 (eqString coverageHash (J.getText "coverage_report_sha256" "" evidence) &&
                  eqString familyHash
                    (J.getText "sha256" "" (J.get target (J.get "family_reports" saved))))
                 "core partial evidence changed before aggregation";
               coverageText <- readFile coveragePath;
               familyText <- readFile familiesPath;
               coverageRows <-
                 case Coverage.parse coverageText of {
                   Left error -> O.fatal error;
                   Right rows -> return rows
                 };
               familyRows <-
                 case Selection.parse familyText of {
                   Left error -> O.fatal error;
                   Right rows -> return rows
                 };
               log <- readFile (output c ++ ("/" ++ (target ++ ".log")));
               return
                 ((,,)
                    (S.filter
                       (\row -> S.not (Coverage.kind "start" row || Coverage.kind "summary" row))
                       coverageRows)
                    (S.map (J.getText "id" "") (S.filter (Selection.kind "family") familyRows))
                    log)
             })
          targets;
      let {
        body = S.concatMap (\((,,) rows _ _) -> rows) pieces
      };
      let {
        completed = S.concatMap (\((,,) _ names _) -> names) pieces
      };
      case CorePartitions.validateCompleted identities completed of {
        Left error -> O.fatal error;
        Right _ -> return ()
      };
      let {
        executions = S.length (S.filter (Coverage.kind "case") body)
      };
      let {
        aliases = S.length (S.filter (Coverage.kind "alias") body)
      };
      let {
        metrics = S.length (S.filter (Coverage.kind "metric") body)
      };
      let {
        start =
          Coverage.event "core" "start" ((:) ((,) "scope" (J.str (Selection.scope full))) [])
      };
      let {
        finish =
          Coverage.event "core" "summary"
            ((:) ((,) "complete" (J.Boolean True))
               ((:) ((,) "executions" (J.num executions))
                  ((:) ((,) "aliases" (J.num aliases))
                     ((:) ((,) "metrics" (J.num metrics)) []))))
      };
      let {
        coverage = S.unlines (S.map J.render ((:) start (S.snoc body finish)))
      };
      let {
        projection = Catalog.projection inventory "core" entries
      };
      checked <-
        case if full
             then Coverage.validate inventory "core" coverage
             else Coverage.validateProjection inventory "core" projection coverage of {
          Left error -> O.fatal error;
          Right value -> return value
        };
      let {
        coveragePath = (output c ++ "/core.coverage.jsonl")
      };
      writeFile coveragePath coverage;
      coverageHash <- fileDigest coveragePath;
      inventoryHash <- fileDigest (root c ++ "/tests/golden/unit-inventory.json");
      let {
        familyPath = (output c ++ "/core.families.jsonl")
      };
      let {
        familyStart =
          Selection.event "core" "start"
            ((:) ((,) "scope" (J.str (Selection.scope full)))
               ((:) ((,) "selected" (J.stringArray identities)) []))
      };
      let {
        orderedCompleted =
          S.concatMap (\expected -> S.filter (eqString expected) completed) identities
      };
      let {
        familyBody =
          S.map
            (\identity ->
               Selection.event "core" "family"
                 ((:) ((,) "id" (J.str identity)) ((:) ((,) "status" (J.str "passed")) [])))
            orderedCompleted
      };
      let {
        familyFinish =
          Selection.event "core" "summary"
            ((:) ((,) "complete" (J.Boolean True))
               ((:) ((,) "families" (J.num (S.length completed))) []))
      };
      writeFile familyPath
        (S.unlines (S.map J.render ((:) familyStart (S.snoc familyBody familyFinish))));
      familyReport c "core" "core" full identities familyPath;
      let {
        summary = (showInt executions ++ " checks; 0 failures")
      };
      let {
        log =
          (S.intercalate "" (S.map (\((,,) _ _ text) -> text) pieces) ++
           ("Core aggregate: " ++ (summary ++ "\n")))
      };
      writeFile (output c ++ "/core.log") log;
      logHash <- fileDigest (output c ++ "/core.log");
      let {
        components =
          J.Object (S.map (\target -> (,) target (J.get target (J.get "suites" saved))) targets)
      };
      let {
        evidence =
          B.info
            ((:) ((,) "scope" (J.str (Selection.scope full)))
               ((:) ((,) "aggregate" (J.Boolean True))
                  ((:) ((,) "targets" (J.stringArray targets))
                     ((:) ((,) "components" components)
                        ((:) ((,) "log_sha256" (J.str logHash))
                           ((:) ((,) "coverage_report_sha256" (J.str coverageHash))
                              ((:) ((,) "coverage_inventory_sha256" (J.str inventoryHash))
                                 ((:) ((,) "coverage_result" checked)
                                    ((:) ((,) "coverage" (J.stringArray ((:) summary [])))
                                       [])))))))))
      };
      current <- J.read (report c);
      record c "suites"
        (J.set "core" (if full then evidence else J.set "selected_coverage" projection evidence)
           (J.getObject "suites" current));
      putStrLn ("Core aggregate: " ++ summary)
    };
  unit :: TestContext -> IO ();
  -- Run native toolchain/runtime probes first, then every original suite action.
  unit c =
    do {
      transports c;
      nativeTests c
        (S.append (O.words "regex harness int-set-unions test-framework")
           (S.snoc CorePartitions.targets "figure12"));
      suite c "regex" ((:) "regular-expression tests passed" []);
      suite c "harness"
        ((:) "Native benchmark/bootstrap/release harness tests passed"
           ((:) "2 native cache regression checks passed" []));
      unions <- nativeTest c "int-set-unions";
      suiteArgs c "test-framework"
        ((:) "--verify-cli" ((:) (output c ++ "/framework-cli") ((:) unions [])))
        ((:) "Test framework contracts passed" ((:) "Test framework CLI contracts passed" []));
      catalog <- Catalog.load (root c);
      core c True (Catalog.forUnit catalog "core");
      suite c "figure12"
        ((:) "43/43 expressions match regression expectations; 0 failures"
           ((:) "41 distinct Figure12 executions"
              ((:) "36 supplementary checks; 0 failures" [])))
    };
  buildRunnerTests :: TestContext -> IO ();
  buildRunnerTests c =
    do {
      windows <- O.isWindows;
      let {
        suffix = if windows then ".exe" else ""
      };
      let {
        flags = if windows then (:) "-municode" [] else []
      };
      S.mapM_
        (\name ->
           run c
             (S.append (O.words "clang -O2 -std=c11 -Wall -Wextra -Werror")
                (S.append flags
                   ((:) (root c ++ ("/tests/native/" ++ (O.replace "-" "_" name ++ ".c")))
                      ((:) "-o" ((:) (output c ++ ("/" ++ (name ++ suffix))) []))))))
        (O.words "build-runner-fixture build-runner-tests");
      let {
        manager = packageManager c
      };
      configuredRunner <- O.envDefault "MLF_BUILD_RUNNER" (O.parent manager ++ "/mlf-build-runner");
      runner <- O.executable configuredRunner;
      let {
        log = (output c ++ "/build-runner.log")
      };
      capture c
        ((:) (output c ++ ("/build-runner-tests" ++ suffix))
           ((:) runner
              ((:) (output c ++ ("/build-runner-fixture" ++ suffix))
                 ((:) (output c ++ "/build-runner-work") []))))
        log;
      text <- readFile log;
      let {
        expectation = "22 native build runner tests passed"
      };
      O.require (contains expectation text) "build runner lifecycle coverage summary is missing";
      hash <- fileDigest log;
      saved <- J.read (report c);
      record c "suites"
        (J.set "build-runner"
           (B.obj2 "log_sha256" (J.str hash) "coverage" (J.stringArray ((:) expectation [])))
           (J.getObject "suites" saved));
      putStr text
    };
  packages :: TestContext -> IO ();
  packages c =
    do {
      buildRunnerTests c;
      setEnv "MLF_TEST_WORK" (output c);
      setEnv "MLF_TEST_ROOT" (output c);
      suite c "packages"
        ((:) "22 package resolver tests passed"
           ((:) "29 package integration cases passed"
              ((:) "Build scheduler integration tests passed"
                 ((:) "1 target dependency integration test passed"
                    ((:) "28 checked package release cases passed" [])))))
    };
  testBuilder :: TestContext -> String -> IO B.Builder;
  -- Build.create fingerprints the executable actually running its build/cache
  -- code. Here that is the campaign runner, distinct from the package manager
  -- used for nested CLI builds and recorded separately in verification.json.
  testBuilder c name =
    do {
      graph <- M.load (root c ++ "/mlf-package.json");
      let {
        options =
          B.info
            ((:) ((,) "compiler" (J.str (compiler c)))
               ((:) ((,) "runtime" (J.str (root c ++ "/runtime/mlf_runtime.c")))
                  ((:) ((,) "cache-dir" (J.str (sharedCache c)))
                     ((:) ((,) "timeout" (J.str "21600")) []))))
      };
      configured <- C.configureGC (root c) options;
      B.create graph configured (output c ++ ("/" ++ name))
    };
  driverIR :: TestContext -> B.Builder -> String -> IO String;
  -- Share the verified source frontend output. The crate-linked interpreter
  -- regressed the nested compiler workloads despite identical fixture targets.
  driverIR c builder name =
    do {
      let {
        entry = (root c ++ ("/bootstrap/" ++ (name ++ ".emlf")))
      };
      let {
        roots = TS.packageRoots (B.graph builder)
      };
      inputs <- TS.sourceInputs roots entry;
      let {
        identity =
          B.info
            ((:) ((,) "format" (J.num 2))
               ((:) ((,) "compiler" (J.get "compiler" (B.tools builder)))
                  ((:) ((,) "manager" (J.get "manager" (B.tools builder)))
                     ((:) ((,) "source_inputs" inputs)
                        ((:) ((,) "entry" (J.str entry))
                           ((:) ((,) "frontend" (J.str "source --emit-llvm-gc")) []))))))
      };
      B.cached builder ("source " ++ (name ++ " LLVM")) identity
        (\work ->
           do {
             ignored <-
               B.capture builder (root c)
                 (S.append ((:) (compiler c) [])
                    (S.append (S.concatMap (\path -> (:) "-i" ((:) path [])) roots)
                       ((:) "--emit-llvm-gc" ((:) entry []))))
                 ""
                 (work ++ "/program.ll");
             text <- readFile (work ++ "/program.ll");
             O.require (stringLength text > 0) "test driver emitted empty LLVM"
           })
    };
  prepareDrivers :: TestContext -> Bool -> IO ([] String);
  prepareDrivers c portFixtures =
    do {
      builder <- testBuilder c "driver-build";
      flags <- nativeFlags c;
      native <- TD.nativeIdentity builder (S.append flags ((:) "-lm" []));
      let {
        cflags =
          S.append (O.words "-O2 -std=c11 -Wall -Wextra -Werror") (S.filter (O.starts "-I") flags)
      };
      let {
        runtimeSource = (root c ++ "/runtime/mlf_runtime.c")
      };
      let {
        runtimeInputs = J.get "runtime" (B.tools builder)
      };
      runtime <- TD.cObject builder native runtimeSource runtimeInputs cflags;
      O.copy (runtime ++ "/object.o") (output c ++ "/runtime.o");
      traced <-
        if portFixtures
        then return ""
        else do {
               let {
                 interpose =
                   O.words
                     "-Dgetline=mlf_test_getline -Dfwrite=mlf_test_fwrite -Dfputc=mlf_test_fputc -Dfflush=mlf_test_fflush"
               };
               artifact <-
                 TD.cObject builder native runtimeSource runtimeInputs (S.append cflags interpose);
               O.copy (artifact ++ "/object.o") (output c ++ "/runtime-traced.o");
               return artifact
             };
      let {
        traceSource = (root c ++ "/tests/native/native_trace.c")
      };
      traceInputs <- B.hashFiles ((:) traceSource []);
      trace <-
        TD.cObject builder native traceSource traceInputs
          (O.words "-O2 -std=c11 -Wall -Wextra -Werror");
      O.copy (trace ++ "/object.o") (output c ++ "/trace.o");
      extra <- stack c;
      drivers <-
        S.mapM
          (\name ->
             do {
               let {
                 ir = (output c ++ ("/" ++ (name ++ ".ll")))
               };
               emitted <- driverIR c builder name;
               O.copy (emitted ++ "/program.ll") ir;
               object <- B.nativeLLVMObject builder emitted;
               let {
                 objects =
                   if eqString name "RuntimeDriver"
                   then (:) (traced ++ "/object.o") ((:) (trace ++ "/object.o") [])
                   else (:) (runtime ++ "/object.o") []
               };
               linked <-
                 TD.linkObject builder native object objects (S.append flags ((:) "-lm" extra));
               binary <- O.executable (output c ++ ("/" ++ name));
               O.copy (B.executable builder (linked ++ "/program")) binary;
               hash <- fileDigest binary;
               llvm <- fileDigest ir;
               receipts <-
                 S.mapM
                   (\((,) key artifact) ->
                      do {
                        saved <- TD.receipt builder artifact;
                        return ((,) key saved)
                      })
                   ((:) ((,) "llvm" emitted)
                      ((:) ((,) "object" object)
                         ((:) ((,) "linked" linked)
                            ((:)
                               ((,) "runtime"
                                  (if eqString name "RuntimeDriver" then traced else runtime))
                               (if eqString name "RuntimeDriver"
                                then (:) ((,) "trace" trace) []
                                else [])))));
               return
                 ((,) name
                    (J.set "artifacts" (J.Object receipts)
                       (J.set "frontend" (J.str "source")
                          (B.obj2 "sha256" (J.str hash) "llvm_sha256" (J.str llvm)))))
             })
          (if portFixtures then (:) "LLVMDriver" [] else O.words "RuntimeDriver LLVMDriver");
      B.copyWindowsFiles builder (output c);
      B.finish builder;
      buildHash <- fileDigest (B.reportPath builder);
      record c "driver_build"
        (B.obj2 "path" (J.str (B.reportPath builder)) "sha256" (J.str buildHash));
      record c "drivers" (J.Object drivers);
      return (S.append flags extra)
    };
  matrices :: TestContext -> String -> Bool -> IO ();
  matrices c binary portFixtures =
    matrixSuite c binary portFixtures (if portFixtures then 25 else 593)
      ((:)
         (if portFixtures
          then "25 MLF port fixtures; 0 failures"
          else "541 shared IO/prelude/backend fixtures; 0 failures")
         []);
  matrixSuite :: TestContext -> String -> Bool -> Int -> [] String -> IO ();
  matrixSuite c binary portFixtures expectedRows expectations =
    matrixSuiteArgs c binary portFixtures expectedRows expectations [] Nothing;
  matrixSuiteArgs :: TestContext ->
                     String ->
                     Bool -> Int -> [] String -> [] String -> Maybe ([] J.Json) -> IO ();
  matrixSuiteArgs c binary portFixtures expectedRows expectations arguments selected =
    do {
      previousHeap <- getEnv "GC_INITIAL_HEAP_SIZE";
      previousDivisor <- getEnv "GC_FREE_SPACE_DIVISOR";
      requestedDivisor <- getEnv "MLF_TEST_MATRIX_GC_DIVISOR";
      divisor <-
        case V.matrixCollectionDivisor requestedDivisor of {
          Left message -> O.fatal message;
          Right value -> ioReturn value
        };
      let {
        unit =
          if portFixtures
          then "port"
          else if ((expectedRows == 593) || S.isJust selected) then "backends" else ""
      };
      expectedEntries <-
        if eqString unit ""
        then return []
        else case selected of {
               Just entries -> return entries;
               Nothing ->
                 do {
                   catalog <- Catalog.load (root c);
                   return (Catalog.forUnit catalog unit)
                 }
             };
      let {
        expectedFamilies = S.map Catalog.identity expectedEntries
      };
      flags <- if (expectedRows == 0) then return [] else prepareDrivers c portFixtures;
      if portFixtures
      then unsetEnv "MLF_BOOTSTRAP_INTERPRETER"
      else setEnv "MLF_BOOTSTRAP_INTERPRETER" (output c ++ "/RuntimeDriver");
      setEnv "MLF_BOOTSTRAP_LLVM" (output c ++ "/LLVMDriver");
      setEnv "MLF_BOOTSTRAP_COMPILER" (compiler c);
      setEnv "MLF_BOOTSTRAP_TIMEOUT_SECONDS" "1800";
      S.mapM_
        (\abi ->
           do {
             setEnv "MLF_LLVM_TEST_ABI" abi;
             let {
               initialHeap = "8388608"
             };
             setEnv "GC_INITIAL_HEAP_SIZE" initialHeap;
             setEnv "GC_FREE_SPACE_DIVISOR" divisor;
             let {
               flagsFile = (output c ++ "/link-flags.bin")
             };
             writeFile flagsFile (O.pack flags);
             setEnv "MLF_TEST_LINK_FLAGS_FILE" flagsFile;
             let {
               directory = (output c ++ ("/matrix-" ++ abi))
             };
             O.mkdir directory;
             if (expectedRows == 0)
             then ioReturn ()
             else if portFixtures
                  then compileRuntime c flags True ("matrix-" ++ (abi ++ "/runtime.o"))
                  else O.copy (output c ++ "/runtime-traced.o") (directory ++ "/runtime.o");
             let {
               log = (output c ++ ("/" ++ (abi ++ ".log")))
             };
             let {
               familyPath = (output c ++ ("/" ++ (abi ++ ".families.jsonl")))
             };
             if eqString unit ""
             then unsetEnv "MLF_TEST_FAMILY_REPORT"
             else do {
                    writeFile familyPath "";
                    setEnv "MLF_TEST_FAMILY_REPORT" familyPath
                  };
             let {
               selectedFixtures =
                 case selected of {
                   Nothing -> Nothing;
                   Just entries -> Just (Catalog.fixtures entries)
                 }
             };
             if portFixtures then validatePreparedPortNames c selectedFixtures else ioReturn ();
             let {
               casePath = output c ++ ("/" ++ (abi ++ ".cases.jsonl"));
               trackCases = S.not (eqString unit "") || expectedRows == 12 && S.not portFixtures
             };
             if trackCases then do { writeFile casePath ""; setEnv "MLF_TEST_CASE_REPORT" casePath }
             else unsetEnv "MLF_TEST_CASE_REPORT";
             captureWithin c ((:) binary arguments) log (if portFixtures then 18000 else 14400);
             unsetEnv "MLF_TEST_CASE_REPORT";
             cases <- if trackCases then caseReport casePath else ioReturn J.empty;
             if portFixtures then validatePreparedPortNames c selectedFixtures else ioReturn ();
             unsetEnv "MLF_TEST_FAMILY_REPORT";
             if eqString unit ""
             then ioReturn ()
             else familyReport c (unit ++ (":" ++ abi)) unit (S.not (S.isJust selected))
                    expectedFamilies
                    familyPath;
             text <- readFile log;
             let {
               rows = S.filter (O.starts "Backend matrix: ") (O.lines text)
             };
             let {
               backendNames = if portFixtures then (:) "llvm" [] else O.words "interpreter llvm"
             };
             let {
               validation =
                 if (expectedRows > 0)
                 then V.validateMatrixAudit expectedRows backendNames text
                 else do {
                        case selected of {
                          Nothing -> Left "empty full backend matrix";
                          Just entries ->
                            do {
                              Catalog.ensure
                                (S.not (S.null entries) &&
                                 ((Catalog.matrixRows entries == 0) &&
                                  S.all (\entry -> eqString (Catalog.unitName entry) "backends")
                                    entries))
                                "invalid zero-row family selection";
                              Catalog.ensure
                                (S.eqList eqString rows
                                   ((:)
                                      "Backend matrix: 0 rows x 2 backends; no missing executions"
                                      []))
                                "component-only backend matrix differs"
                            }
                        }
                      }
             };
             case validation of {
               Left message -> O.fatal message;
               Right _ -> ioReturn ()
             };
             rowEvidence <-
               if eqString unit ""
               then return J.empty
               else do {
                      let {
                        path = (directory ++ "/rows.jsonl")
                      };
                      raw <- readFile path;
                      actual <-
                        case S.mapM J.parse (O.nonempty (O.lines raw)) of {
                          Left error -> O.fatal error;
                          Right value -> return value
                        };
                      case Catalog.validateMatrixRows portFixtures expectedEntries actual of {
                        Left message -> O.fatal message;
                        Right _ -> return ()
                      };
                      digest <- fileDigest path;
                      return
                        (J.set "row_report" (J.str path)
                           (J.set "row_report_sha256" (J.str digest) J.empty))
                    };
             O.require (S.all (\expected -> contains expected text) expectations)
               "native fixture coverage changed";
             hash <- fileDigest log;
             let {
               row =
                 J.set "scope" (J.str (if S.isJust selected then "partial" else "full"))
                   (J.set "backend_names" (J.stringArray backendNames)
                      (J.Object
                         (S.append (S.append (J.items cases) (J.items rowEvidence))
                            (J.items
                               (B.info
                                  ((:)
                                     ((,) "rows"
                                        (J.num (readInt (S.index (O.words (S.head rows)) 2))))
                                     ((:) ((,) "backends" (J.num (S.length backendNames)))
                                        ((:) ((,) "cli_compiler" (J.str (compiler c)))
                                           ((:) ((,) "log_sha256" (J.str hash))
                                              ((:)
                                                 ((,) "gc_initial_heap_bytes"
                                                    (J.num (readInt initialHeap)))
                                                 ((:)
                                                    ((,) "gc_free_space_divisor"
                                                       (J.num (readInt divisor)))
                                                    [])))))))))))
             };
             saved <- J.read (report c);
             preparedHash <- getEnv "MLF_TEST_PORT_TARGETS_SHA256";
             record c "matrices"
               (J.set abi
                  (if portFixtures
                   then J.set "prepared_targets_sha256" (J.str preparedHash) row
                   else row)
                  (J.getObject "matrices" saved));
             putStr (O.drop (S.max 0 (stringLength text - 2000)) text)
           })
        (runtimeProfiles c);
      clearDrivers;
      S.mapM_ (\((,) name value) -> if eqString value "" then unsetEnv name else setEnv name value)
        ((:) ((,) "GC_INITIAL_HEAP_SIZE" previousHeap)
           ((:) ((,) "GC_FREE_SPACE_DIVISOR" previousDivisor) []))
    };
  backends :: TestContext -> IO ();
  backends c =
    do {
      transports c;
      binary <- nativeTest c "backends";
      matrices c binary False
    };
  prSmoke :: TestContext -> IO ();
  prSmoke c =
    do {
      transports c;
      nativeTests c (O.words "int-set-unions test-framework figure12 pr-smoke");
      suite c "figure12"
        ((:) "43/43 expressions match regression expectations; 0 failures"
           ((:) "41 distinct Figure12 executions"
              ((:) "36 supplementary checks; 0 failures" [])));
      unions <- nativeTest c "int-set-unions";
      unionHash <- fileDigest unions;
      suiteArgs c "test-framework"
        ((:) "--verify-cli" ((:) (output c ++ "/framework-cli") ((:) unions [])))
        ((:) "Test framework contracts passed" ((:) "Test framework CLI contracts passed" []));
      currentUnionHash <- fileDigest unions;
      O.require (eqString unionHash currentUnionHash)
        "focused test executable changed during validation";
      record c "focused_suite"
        (B.info
           ((:) ((,) "name" (J.str "int-set-unions"))
              ((:) ((,) "binary_sha256" (J.str unionHash)) [])));
      binary <- nativeTest c "pr-smoke";
      matrixSuite c binary False 12
        ["4 independent target controls; 0 failures", "12 PR smoke backend fixtures; 0 failures"];
      smokePackage c
    };
  smokePackage :: TestContext -> IO ();
  -- Mutate a private copy so checkout sources and their recorded hashes stay fixed.
  smokePackage c =
    do {
      let {
        directory = (output c ++ "/package-smoke")
      };
      O.remove directory;
      O.mkdir directory;
      let {
        app = (directory ++ "/app")
      };
      run c ((:) "/bin/cp" ((:) "-R" ((:) (root c ++ "/examples/packages") ((:) app []))));
      O.remove (app ++ "/.mlf-build");
      let {
        manager = packageManager c
      };
      let {
        build = (directory ++ "/build")
      };
      let {
        argv =
          (:) manager
            ((:) "--manifest"
               ((:) (app ++ "/mlf-package.json")
                  ((:) "--compiler"
                     ((:) (compiler c)
                        ((:) "--runtime"
                           ((:) (root c ++ "/runtime/mlf_runtime.c")
                              ((:) "--build-dir"
                                 ((:) build (O.words "--timeout 1800 test --target hello")))))))))
      };
      initial <- smokePackageRun c argv build (directory ++ "/initial.log");
      let {
        initialBuilds = J.values (J.get "builds" initial)
      };
      O.require
        (S.not (S.null initialBuilds) &&
         S.all (\row -> S.not (J.getBool "cached" True row)) initialBuilds)
        "first smoke package test reused an artifact";
      cached <- smokePackageRun c argv build (directory ++ "/cached.log");
      let {
        cachedBuilds = J.values (J.get "builds" cached)
      };
      O.require (S.not (S.null cachedBuilds) && S.all (J.getBool "cached" False) cachedBuilds)
        "unchanged smoke package test missed cache";
      let {
        source = (app ++ "/message/Message.emlf")
      };
      original <- readFile source;
      let {
        needle = "render (Message text) = text"
      };
      O.require (contains needle original) "smoke package dependency fixture changed";
      writeFile source (O.replace needle "render (Message text) = text ++ \" updated\"" original);
      manifest <- J.read (app ++ "/mlf-package.json");
      let {
        cases = J.getObject "tests" manifest
      };
      let {
        changedCase =
          J.set "stdout" (J.str "Hello, local packages! updated\n") (J.get "hello" cases)
      };
      J.write (app ++ "/mlf-package.json")
        (J.set "tests" (J.set "hello" changedCase cases) manifest);
      changed <- smokePackageRun c argv build (directory ++ "/changed.log");
      let {
        targets =
          S.filter
            (\row ->
               eqString (J.getText "kind" "" row) "executable local-packages-example:test-hello")
            (J.values (J.get "builds" changed))
      };
      O.require
        ((S.length targets == 1) && S.all (\row -> S.not (J.getBool "cached" True row)) targets)
        "dependency edit did not rebuild the smoke package executable";
      evidence <-
        S.mapM
          (\name ->
             do {
               let {
                 path = (directory ++ ("/" ++ (name ++ ".log")))
               };
               hash <- fileDigest path;
               ioReturn ((,) name (J.str hash))
             })
          (O.words "initial cached changed");
      record c "package_smoke"
        (J.set "backends" (J.stringArray (O.words "interpreter llvm"))
           (J.set "cases" (J.num 3) (J.Object evidence)));
      putStrLn "3 PR smoke package checks on interpreter and LLVM; 0 failures"
    };
  smokePackageRun :: TestContext -> [] String -> String -> String -> IO J.Json;
  smokePackageRun c argv build log =
    do {
      capture c argv log;
      saved <- J.read (build ++ "/build-report.json");
      let {
        tests = J.values (J.get "tests" saved)
      };
      O.require
        (J.getBool "complete" False saved &&
         ((S.length tests == 1) &&
          S.all
            (\row ->
               (eqString (J.getText "name" "" row) "hello" &&
                (J.getBool "passed" False row &&
                 J.equal (J.get "backends" row) (J.stringArray (O.words "interpreter llvm")))))
            tests))
        "smoke package test did not complete both backends";
      ioReturn saved
    };
  port :: TestContext -> IO ();
  port c =
    do {
      transports c;
      references <- nativeTest c "references";
      setEnv "MLF_TEST_REFERENCES" references;
      binary <- nativeTest c "port";
      preparePort c binary;
      matrices c binary True
    };
  preparePort :: TestContext -> String -> IO ();
  preparePort c binary = preparePortNames c binary Nothing;
  preparePortNames :: TestContext -> String -> Maybe ([] String) -> IO ();
  preparePortNames c binary selected = preparePortSelection c binary selected "all";
  preparePortShard :: TestContext -> String -> String -> IO ();
  preparePortShard c binary shard = preparePortSelection c binary Nothing shard;
  preparePortSelection :: TestContext -> String -> Maybe ([] String) -> String -> IO ();
  -- These three fixtures retain large, independently checked target forms.
  -- Fresh small-host profiling reduced SolverReuse from 2531s to 943s with
  -- divisor 4; keep the ordinary policy for the other fixtures and builds.
  -- The transport manifest keeps its stable schema and full source provenance;
  -- only the cache identity above uses the new dependency-specific format.
  preparePortSelection c binary selected shard =
    do {
      builder <- testBuilder c "port-preparation";
      originalCollection <- getEnv "GC_FREE_SPACE_DIVISOR";
      requestedCollection <- getEnv "MLF_TEST_MATRIX_GC_DIVISOR";
      memoryCollection <-
        case V.matrixCollectionDivisor requestedCollection of {
          Left message -> O.fatal message;
          Right value -> ioReturn value
        };
      let {
        baselineCollection = if eqString originalCollection "" then "1" else originalCollection
      };
      let {
        listing = (output c ++ "/port-fixtures.txt")
      };
      capture c ((:) binary ((:) "--list" [])) listing;
      listingText <- readFile listing;
      let {
        available = O.words listingText
      };
      O.require ((S.length available == 25) && (S.length (S.nubBy eqString available) == 25))
        "port fixture preparation coverage changed";
      O.require
        (S.elem eqString shard (O.words "all StateTypes SolverReuse InferenceConformance other"))
        "unknown port preparation shard";
      let {
        heavy = O.words "StateTypes SolverReuse InferenceConformance"
      };
      let {
        names =
          if eqString shard "all"
          then case selected of {
                 Nothing -> available;
                 Just chosen -> chosen
               }
          else S.filter
                 (\name ->
                    if eqString shard "other"
                    then S.not (S.elem eqString name heavy)
                    else eqString name shard)
                 available
      };
      O.require
        (S.not (S.null names) &&
         (Catalog.unique names && S.all (\name -> S.elem eqString name available) names))
        "invalid focused port preparation";
      O.require
        (eqString shard "all" || (S.length names == (if eqString shard "other" then 22 else 1)))
        "port preparation shard coverage differs";
      let {
        selectedScope = if eqString shard "all" then selected else Just names
      };
      saved <- J.read (report c);
      identity <- portTargetIdentity builder binary;
      targets <-
        S.mapM
          (\name ->
             do {
               let {
                 collection =
                   if S.elem eqString name heavy then memoryCollection else baselineCollection
               };
               setEnv "GC_FREE_SPACE_DIVISOR" collection;
               target <- preparePortTarget c builder binary name;
               ioReturn (J.set "gc_free_space_divisor" (J.str collection) target)
             })
          names;
      if eqString originalCollection ""
      then unsetEnv "GC_FREE_SPACE_DIVISOR"
      else setEnv "GC_FREE_SPACE_DIVISOR" originalCollection;
      B.finish builder;
      let {
        manifest = (output c ++ "/prepared-port.json")
      };
      let {
        prepared =
          J.set "format" (J.num 1)
            (J.set "sources" (J.get "sources" saved) (J.set "targets" (J.Array targets) identity))
      };
      J.write manifest
        (case selectedScope of {
           Nothing -> prepared;
           Just names ->
             J.set "scope" (J.str "partial")
               (J.set "selected_fixtures" (J.stringArray names) prepared)
         });
      hash <- fileDigest manifest;
      setEnv "MLF_TEST_PORT_TARGETS" manifest;
      setEnv "MLF_TEST_PORT_TARGETS_SHA256" hash;
      let {
        targetHashes =
          J.Object
            (S.map (\row -> (,) (J.getText "fixture" "" row) (J.get "target_sha256" row)) targets)
      };
      let {
        collections =
          J.Object
            (S.map (\row -> (,) (J.getText "fixture" "" row) (J.get "gc_free_space_divisor" row))
               targets)
      };
      record c "prepared_port"
        (J.set "collection_policies" collections
           (J.set "target_hashes" targetHashes
              (B.info
                 ((:) ((,) "manifest" (J.str manifest))
                    ((:) ((,) "sha256" (J.str hash))
                       ((:) ((,) "targets" (J.num (S.length targets)))
                          ((:) ((,) "build_report" (J.str (B.reportPath builder))) [])))))));
      validatePreparedPortNames c selectedScope
    };
  portTargetIdentity :: B.Builder -> String -> IO J.Json;
  portTargetIdentity builder binary =
    do {
      checkerHash <- fileDigest binary;
      ioReturn
        (B.info
           ((:) ((,) "format" (J.num 2))
              ((:) ((,) "compiler" (J.get "compiler" (B.tools builder)))
                 ((:) ((,) "manager" (J.get "manager" (B.tools builder)))
                    ((:) ((,) "checker_sha256" (J.str checkerHash)) [])))))
    };
  preparePortTarget :: TestContext -> B.Builder -> String -> String -> IO J.Json;
  -- Match PortSuite.prepareFixture's source entry and ordered include roots.
  -- Discovery and the preparation child must resolve relative imports from the
  -- same working directory, including the loader's final implicit '.' root.
  preparePortTarget c builder binary name =
    do {
      working <- canonicalPath ".";
      O.require (eqString working (root c))
        "port source discovery must run from the preparation working directory";
      identity <- portTargetIdentity builder binary;
      inputs <-
        TS.sourceInputs (TS.portRoots (B.graph builder)) ("bootstrap/tests/" ++ (name ++ ".emlf"));
      collection <- getEnv "GC_FREE_SPACE_DIVISOR";
      let {
        targetIdentity =
          J.set "gc_free_space_divisor" (J.str collection)
            (J.set "source_inputs" inputs (J.set "fixture" (J.str name) identity))
      };
      artifact <-
        B.cachedChecked builder ("checked port target " ++ name) targetIdentity
          (\directory ->
             do {
               let {
                 target = (directory ++ "/unit.xmlf")
               };
               present <- fileExists target;
               receipt <- fileExists (target ++ ".checks.json");
               if (present && receipt)
               then do {
                      hash <- fileDigest target;
                      checks <- J.read (target ++ ".checks.json");
                      ioReturn (V.validPortTargetChecks name hash checks)
                    }
               else ioReturn False
             })
          (\work ->
             do {
               ignored <-
                 B.capture builder (root c)
                   ((:) binary ((:) "--prepare" ((:) name ((:) (work ++ "/unit.xmlf") []))))
                   ""
                   "";
               ioReturn ()
             });
      let {
        target = (artifact ++ "/unit.xmlf")
      };
      hash <- fileDigest target;
      checksHash <- fileDigest (target ++ ".checks.json");
      ioReturn
        (J.set "source_inputs" inputs
           (B.info
              ((:) ((,) "fixture" (J.str name))
                 ((:) ((,) "target" (J.str target))
                    ((:) ((,) "target_sha256" (J.str hash))
                       ((:) ((,) "checks_sha256" (J.str checksHash)) []))))))
    };
  validatePreparedPort :: TestContext -> IO ();
  validatePreparedPort c = validatePreparedPortNames c Nothing;
  validatePreparedPortNames :: TestContext -> Maybe ([] String) -> IO ();
  validatePreparedPortNames c selected =
    do {
      path <- getEnv "MLF_TEST_PORT_TARGETS";
      expected <- getEnv "MLF_TEST_PORT_TARGETS_SHA256";
      hash <- fileDigest path;
      O.require (eqString hash expected) "prepared port manifest changed between layouts";
      manifest <- J.read path;
      let {
        targets = J.values (J.get "targets" manifest)
      };
      let {
        names = S.map (J.getText "fixture" "") targets
      };
      O.require (Catalog.unique names && J.equal (J.get "format" manifest) (J.num 1))
        "invalid prepared port manifest";
      case selected of {
        Nothing ->
          O.require
            ((S.length targets == 25) && eqString (J.getText "scope" "full" manifest) "full")
            "prepared full port targets missing";
        Just expected ->
          O.require
            (S.not (S.null expected) &&
             (Catalog.sameSet names expected &&
              (J.equal (J.get "selected_fixtures" manifest) (J.stringArray expected) &&
               eqString (J.getText "scope" "" manifest) "partial")))
            "prepared focused port targets differ"
      };
      S.mapM_
        (\row ->
           do {
             let {
               target = J.getText "target" "" row
             };
             hash <- fileDigest target;
             checksHash <- fileDigest (target ++ ".checks.json");
             checks <- J.read (target ++ ".checks.json");
             O.require
               (eqString hash (J.getText "target_sha256" "" row) &&
                (eqString checksHash (J.getText "checks_sha256" "" row) &&
                 V.validPortTargetChecks (J.getText "fixture" "" row) hash checks))
               "prepared port target/check receipt changed between layouts"
           })
        targets
    };
  shellQuote :: String -> String;
  shellQuote text = ("'" ++ (O.replace "'" "'\\''" text ++ "'"));
  contains :: String -> String -> Bool;
  contains needle text = S.not (eqString text (O.replace needle "" text));
  -- The exported corpus prescribes acceptance, rejection phase/diagnostic,
  -- checked target type and (where applicable) exact output for both backends.
  parity :: TestContext -> IO ();
  parity c = parityWith c "" [];
  parityWith :: TestContext -> String -> [] String -> IO ();
  parityWith c buildReceipt args =
    case TestRunner.parse args of {
      Left message -> O.fatal message;
      Right options -> if TestRunner.listing options
        then parityList c args
        else do {
          if S.null (TestRunner.selectors options) then return () else record c "scope" (J.str "partial");
          parityCampaign c buildReceipt args
        }
    };
  parityRows path =
    do {
      source <- readFile path;
      S.mapM (\line -> case J.parse line of {
        Left error -> O.fatal error;
        Right row -> return row
      }) (O.nonempty (O.lines source))
    };
  parityList c args =
    do {
      rows <- parityRows (root c ++ "/tests/golden/parity/manifest.jsonl");
      record c "scope" (J.str "inventory");
      code <- TestRunner.run args (S.map (\row -> parityEntry row (TestAssert.succeed ())) rows);
      if code == 0 then return () else exitWith code
    };
  parityHelpers :: TestContext -> String -> IO ((,) String String);
  parityHelpers c buildReceipt =
    if eqString buildReceipt ""
    then do {
      nativeTests c (O.words "corpus check-target");
      exporter <- nativeTest c "corpus";
      checker <- nativeTest c "check-target";
      return ((,) exporter checker)
    }
    else do {
      attempt <- O.temporaryDirectory (output c) (output c ++ "/hosted-parity-helpers-");
      let {
        directory = attempt ++ "/build";
        program = root c ++ "/tools/shared/prepare_parity.py";
        receiptPath = directory ++ "/receipt.json"
      };
      buildHash <- fileDigest buildReceipt;
      programHash <- fileDigest program;
      run c ["python3", "-B", program, "--build-receipt", buildReceipt, "--output", directory];
      receipt <- J.read receiptPath;
      currentBuildHash <- fileDigest buildReceipt;
      currentProgramHash <- fileDigest program;
      O.require (J.getBool "complete" False receipt &&
        eqString buildHash (J.getText "build_receipt_sha256" "" receipt) &&
        eqString buildHash currentBuildHash && eqString programHash currentProgramHash)
        "hosted parity helper build receipt changed or is incomplete";
      exporter <- parityHelper directory receipt "corpus";
      checker <- parityHelper directory receipt "check-target";
      receiptHash <- fileDigest receiptPath;
      record c "parity_helpers" (B.info
        [(,) "host" (J.str "GHC"), (,) "receipt" (J.str receiptPath),
         (,) "receipt_sha256" (J.str receiptHash), (,) "preparer_sha256" (J.str programHash),
         (,) "outputs" (J.getObject "outputs" receipt)]);
      return ((,) exporter checker)
    };
  parityHelper :: String -> J.Json -> String -> IO String;
  parityHelper directory receipt name = do {
    let {
      path = directory ++ "/bin/" ++ name;
      product = J.getObject name (J.getObject "outputs" receipt)
    };
    executable <- O.executable path;
    hash <- fileDigest executable;
    O.require (eqString path executable && eqString executable (J.getText "path" "" product) &&
      eqString hash (J.getText "sha256" "" product))
      ("hosted parity helper changed: " ++ name);
    return executable
  };
  parityCampaign c buildReceipt args =
    do {
      helpers <- parityHelpers c buildReceipt;
      let {
        corpus = output c ++ "/corpus";
        exporter = S.fst helpers;
        checker = S.snd helpers
      };
      run c [exporter, corpus];
      rows <- parityRows (corpus ++ "/manifest.jsonl");
      O.require (S.all (\row -> J.equal (J.get "schema_version" row) (J.num 1)) rows)
        "unsupported parity schema";
      S.mapM_ (\category -> O.require
        (S.any (\row -> eqString (J.getText "category" "" row) category) rows)
        ("parity corpus lacks " ++ category))
        (O.words "figure12 hm-exhaustive hm-generated annotations readability state modules examples benchmarks");
      O.require (S.all (\row ->
        if J.getBool "expected_accept" False row
        then stringLength (O.trim (J.getText "expected_type" "" row)) > 0
        else stringLength (O.trim (J.getText "expected_phase" "" row)) > 0 &&
          S.not (J.has "expected_stdout" row)) rows)
        "parity case lacks a prescribed type or rejection phase, or expects output from a rejection";
      let {
        a8 =
          S.fromMaybe (panic "missing Figure12 A8")
            (S.find (\row -> eqString (J.getText "id" "" row) "figure12-A8") rows)
      };
      O.require
        (S.not (J.getBool "expected_accept" True a8) &&
         eqString (J.getText "expected_phase" "" a8) "Inference")
        "A8 must be rejected by inference";
      let {
        moduleRows = S.filter (\row -> eqString (J.getText "category" "" row) "modules") rows
      };
      O.require
        (S.any (\row -> (J.getBool "no_prelude" False row && J.getBool "expected_accept" False row))
           moduleRows)
        "module corpus lacks explicit prelude coverage";
      O.require
        (S.all
           (\row ->
              (J.getBool "expected_accept" False row ||
               ((stringLength (J.getText "expected_phase" "" row) > 0) &&
                (stringLength (O.trim (J.getText "expected_error_contains" "" row)) > 0))))
           moduleRows)
        "module rejection lacks a prescribed phase or diagnostic";
      let {
        inventory = S.map (\row -> parityEntry row (TestAssert.succeed ())) rows
      };
      case TestRunner.plan args inventory of {
        Left message -> O.fatal message;
        Right ((,) options chosen) -> do {
          let {
            full = S.length chosen == S.length rows && S.null (TestRunner.selectors options);
            selectedIds = Set.fromList compareString (S.map TestCase.id chosen);
            selected = S.filter
              (\row -> Set.member compareString (parityIdentity row) selectedIds)
              rows
          };
          do {
            let {
              campaignArgs =
                if eqString (TestRunner.report options) ""
                then S.append args ((:) "--report" ((:) (output c ++ "/parity-report.jsonl") []))
                else args
            };
            TestRunner.saveReport
              (case TestRunner.parse campaignArgs of { Left message -> panic message; Right parsed -> parsed })
              (TestRunner.prefix "start" ++ (TestRunner.selectionFields (S.length rows) (S.length chosen) ++
                (",\"ids\":" ++ (TestRunner.strings (S.map TestCase.id chosen) ++ "}\n"))));
            if full then return () else record c "scope" (J.str "partial");
            O.mkdir (output c ++ "/parity");
            (,,) targets canonical aliases <- parityPlan c corpus 0 Map.empty Map.empty [] [] selected;
            checkCrateCycleOracles c corpus checker rows selectedIds;
            sourceResults <- parityBatch c "compile" (compiler c) "--test-parity-batch" targets;
            checks <- S.mapM
              (\target -> do {
                writeFile (J.getText "stem" "" target ++ ".type") (J.getText "expected_type" "" target);
                return target
              })
              (S.filter (parityShouldCheck sourceResults) targets);
            checked <- parityBatch c "independent-check" checker "--batch" checks;
            let {
              selectedRuntime = S.length (S.filter (J.has "expected_stdout") selected)
            };
            flags <-
              if selectedRuntime == 0 then return [] else do {
                options <- nativeFlags c;
                compileRuntime c options False "runtime.o";
                return options
              };
            let {
              actual = S.map (\row -> parityEntry row
                (case Map.lookup compareString (parityIdentity row) canonical of {
                   Nothing -> TestAssert.fail "case has no selected compilation";
                   Just target -> parityCase c flags row target sourceResults checked
                 })) rows
            };
            status <- TestRunner.run campaignArgs actual;
            if status == 0 then return () else exitWith status;
            manifestHash <- fileDigest (corpus ++ "/manifest.jsonl");
            let {
              selectedAccepted = S.length (S.filter (J.getBool "expected_accept" False) selected);
              referenceChecks = S.length (S.filter (J.has "expected_reference_target") selected);
              stats = B.info
                [ (,) "cases" (J.num (S.length selected))
                , (,) "accepted" (J.num selectedAccepted)
                , (,) "rejected" (J.num (S.length selected - selectedAccepted))
                , (,) "runtime_rows" (J.num selectedRuntime)
                , (,) "runtime_executions" (J.num (selectedRuntime * 2))
                , (,) "source_compilations" (J.num (S.length targets))
                , (,) "shared_source_cases" (J.num (S.length aliases))
                , (,) "shared_cases" (J.Array aliases)
                , (,) "independent_target_checks" (J.num (S.length checks + referenceChecks))
                , (,) "manifest_sha256" (J.str manifestHash)
                , (,) "case_report" (J.str (if eqString (TestRunner.report options) ""
                     then output c ++ "/parity-report.jsonl" else TestRunner.report options))
                ]
            };
            record c "parity" stats;
            if TestRunner.json options then return () else
              putStrLn ("Parity: " ++ (showInt (S.length selected) ++
                (" cases; " ++ (showInt (S.length targets) ++
                  (" source compilations; " ++ (showInt (S.length aliases) ++
                    " identical input/oracle cases shared"))))))
          }
        }
      }
    };
  parityIdentity row = "parity/" ++ J.getText "id" "" row;
  parityEntry row body =
    TestCase.test (parityIdentity row) (J.getText "label" (parityIdentity row) row)
      ["family:parity/" ++ J.getText "category" "" row] body;
  parityPlan c corpus index byInput byId targets aliases rows = case rows of {
    [] -> return ((,,) (S.reverse targets) byId (S.reverse aliases));
    (:) row rest -> do {
      let {
        shareable = V.canShareParity row;
        identity = parityIdentity row;
        path = corpus ++ ("/" ++ J.getText "source_path" "" row)
      };
      source <- if shareable then readFile path else return "";
      let {
        key = V.parityExecutionKey row source
      };
      case if shareable then Map.lookup compareString key byInput else Nothing of {
        Just target -> do {
          sourceHash <- fileDigest path;
          let {
            alias = B.info
              [ (,) "id" (J.get "id" row)
              , (,) "index" (J.num index)
              , (,) "canonical_id" (J.get "id" target)
              , (,) "canonical_index" (J.get "index" target)
              , (,) "source_sha256" (J.str sourceHash)
              , (,) "expected_accept" (J.get "expected_accept" row)
              ]
          };
          parityPlan c corpus (index + 1) byInput
            (Map.insert compareString identity target byId) targets ((:) alias aliases) rest
        };
        Nothing -> do {
          let {
            target = J.set "stem" (J.str (output c ++ ("/parity/" ++ showInt index)))
              (J.set "index" (J.num index)
                (J.set "source" (J.str path)
                  (J.set "include_dirs" (J.stringArray
                    (S.map (\dir -> corpus ++ ("/" ++ dir)) (J.getStrings "include_dirs" row))) row)));
            next = if shareable then Map.insert compareString key target byInput else byInput
          };
          parityPlan c corpus (index + 1) next (Map.insert compareString identity target byId)
            ((:) target targets) aliases rest
        }
      }
    }
  };
  parityBatch c stage binary flag rows =
    if S.null rows then return Map.empty else do {
      let {
        stem = output c ++ ("/parity/" ++ stage);
        request = stem ++ ".json"
      };
      J.write request (J.Array rows);
      status <- O.exec (root c) [binary, flag, request] "" (stem ++ ".jsonl") (stem ++ ".stderr") 7200;
      raw <- readFile (stem ++ ".jsonl");
      results <- S.mapM (\line -> case J.parse line of {
        Left message -> O.fatal (stage ++ (": " ++ message));
        Right result -> return result
      }) (O.nonempty (O.lines raw));
      O.require (status == 0) (stage ++ (" batch exited " ++ (showInt status ++ ("; see " ++ stem))));
      O.require (S.eqList eqString (S.map (J.getText "id" "") rows) (S.map (J.getText "id" "") results))
        (stage ++ " batch changed, duplicated, or omitted case results");
      return (Map.fromList compareString (S.map (\row -> (,) (J.getText "id" "" row) row) results))
    };
  parityShouldCheck compiled row =
    J.getBool "expected_accept" False row &&
      J.equal (J.get "compile_exit"
        (S.fromMaybe J.empty (Map.lookup compareString (J.getText "id" "" row) compiled))) (J.num 0);
  -- The expected result is a fixed integer literal, never a type obtained from
  -- the candidate. Check both the reference xMLF and every emitted candidate
  -- target against the independently prescribed Int oracle.
  checkCrateCycleOracles :: TestContext -> String -> String -> [] J.Json -> Set String -> IO ();
  checkCrateCycleOracles c corpus checker rows selected =
    do {
      let {
        references = S.filter (J.has "expected_reference_target") rows;
        identities = S.map (J.getText "id" "") references;
        referencePath = "oracle/crate-module-cycles/int42.xmlf"
      };
      O.require (S.length identities == 2 &&
        S.all (\identity -> S.elem eqString identity identities) ["module-reject-000025", "module-reject-000026"])
        "missing or duplicate crate-cycle reference cases";
      reference <- readFile (corpus ++ ("/" ++ referencePath));
      O.require (eqString reference "42\n") "crate-cycle reference target changed";
      S.mapM_ (\row -> do {
        O.require (eqString (J.getText "category" "" row) "modules" &&
          J.getBool "expected_accept" False row &&
          eqString (J.getText "expected_type" "" row) "Int" &&
          eqString (J.getText "expected_reference_target" "" row) referencePath)
          "crate-cycle acceptance, type or reference changed";
        let { stem = output c ++ ("/parity/oracle-" ++ J.getText "id" "" row) };
        writeFile (stem ++ ".type") "Int";
        status <- O.exec (root c) [checker, corpus ++ ("/" ++ referencePath), stem ++ ".type"]
          "" (stem ++ ".out") (stem ++ ".err") 1800;
        O.require (status == 0) "independent crate-cycle reference typing failed"
      }) (S.filter (\row -> Set.member compareString (parityIdentity row) selected) references)
    };
  parityCase c flags row target sourceResults checked =
    let {
      identity = J.getText "id" "" target;
      stem = J.getText "stem" "" target;
      compiled = S.fromMaybe J.empty (Map.lookup compareString identity sourceResults);
      independent = S.fromMaybe J.empty (Map.lookup compareString identity checked);
      accept = J.getBool "expected_accept" False row
    } in
    do {
      error <- TestAssert.liftIO (readFile (stem ++ ".stderr"));
      TestAssert.assert (J.equal (J.get "compile_exit" compiled) (J.num (if accept then 0 else 1)))
        ("acceptance mismatch: " ++ error);
      if accept
      then do {
        selfError <- TestAssert.liftIO (readFile (stem ++ ".self.err"));
        independentError <- TestAssert.liftIO (readFile (stem ++ ".check.err"));
        TestAssert.assert (J.equal (J.get "candidate_check_exit" compiled) (J.num 0))
          ("candidate target check failed: " ++ selfError);
        TestAssert.assert (J.equal (J.get "independent_check_exit" independent) (J.num 0))
          ("independent target check failed: " ++ independentError)
      }
      else do {
        targetText <- TestAssert.liftIO (readFile (stem ++ ".xmlf"));
        TestAssert.equal eqString (\text -> text) "rejected input emitted a target" "" targetText;
        let {
          phase = J.getText "expected_phase" "" row;
          reason = J.getText "expected_error_contains" "" row
        };
        TestAssert.assert (eqString phase "" || O.starts (phase ++ ":") error)
          ("wrong rejection phase: " ++ error);
        TestAssert.assert (eqString reason "" || contains reason error)
          ("wrong rejection diagnostic: " ++ error)
      };
      if J.has "expected_stdout" row
      then do {
        TestAssert.assert accept "rejected corpus row has runtime expectation";
        let {
          source = J.getText "source" "" target;
          prefix = S.append
            (if J.getBool "no_prelude" False row then [compiler c, "--no-prelude"] else [compiler c])
            (S.concatMap (\path -> ["-i", path]) (J.getStrings "include_dirs" target))
        };
        TestAssert.liftIO (writeFile (stem ++ ".stdin") (J.getText "expected_stdin" "" row));
        interpreter <- TestAssert.liftIO (parityOutput c row (S.append prefix ["--run", source]) stem "interpreter");
        generated <- TestAssert.liftIO
          (O.exec (root c) (S.append prefix ["--emit-llvm", source]) "" (stem ++ ".ll") (stem ++ ".llvm.err") 1800);
        llvm <- if generated == 0
          then do {
            binary <- TestAssert.liftIO (O.executable (stem ++ ".native"));
            linked <- TestAssert.liftIO (O.exec (root c)
              (S.append (O.words "clang -O2 -Wno-override-module")
                (S.append [stem ++ ".ll", output c ++ "/runtime.o"] (S.append flags ["-lm", "-o", binary])))
              "" (stem ++ ".link.out") (stem ++ ".link.err") 1800);
            if linked == 0 then TestAssert.liftIO (parityOutput c row [binary] stem "llvm")
            else do {
              diagnostics <- TestAssert.liftIO (readFile (stem ++ ".link.err"));
              TestAssert.succeed (Just ("LLVM link failed: " ++ diagnostics))
            }
          }
          else do {
            diagnostics <- TestAssert.liftIO (readFile (stem ++ ".llvm.err"));
            TestAssert.succeed (Just ("LLVM emission failed: " ++ diagnostics))
          };
        let {
          errors = S.catMaybes [interpreter, llvm]
        };
        TestAssert.assert (S.null errors) (S.intercalate "; " errors)
      }
      else TestAssert.succeed ()
    };
  parityOutput c row argv stem backend =
    do {
      let {
        outPath = stem ++ ("." ++ (backend ++ ".out"));
        errPath = stem ++ ("." ++ (backend ++ ".err"))
      };
      code <- O.exec (root c) argv (stem ++ ".stdin") outPath errPath 1800;
      out <- readFile outPath;
      err <- readFile errPath;
      return (if code == 0 && eqString out (J.getText "expected_stdout" "" row) &&
                 eqString err (J.getText "expected_stderr" "" row)
              then Nothing
              else Just (backend ++ (" output/status mismatch (" ++
                 (showInt code ++ ("); see " ++ (outPath ++ (" and " ++ errPath)))))))
    };
  findArtifact :: String -> String -> [] String -> IO String;
  findArtifact hash cache names =
    case names of {
      [] -> O.fatal "cannot find the package artifact that produced the candidate";
      (:) name rest ->
        do {
          let {
            binary = (cache ++ ("/" ++ (name ++ "/program")))
          };
          present <- fileExists binary;
          irPresent <- fileExists (O.parent binary ++ "/program.ll");
          valid <-
            if (present && irPresent) then B.cacheValid (O.parent binary) name else ioReturn False;
          if valid
          then do {
                 actual <- fileDigest binary;
                 if eqString actual hash
                 then ioReturn (O.parent binary)
                 else findArtifact hash cache rest
               }
          else findArtifact hash cache rest
        }
    };
  selfHostEvents :: TestContext -> String;
  selfHostEvents c = output c ++ "/self-host.events.jsonl";
  selfHostEvent :: TestContext -> J.Json -> IO ();
  selfHostEvent c event =
    do {
      suite <- getEnv "MLF_TEST_SUITE";
      path <- getEnv "MLF_TEST_EVENTS";
      let {
        append = \target -> do {
          present <- fileExists target;
          previous <- if present then readFile target else ioReturn "";
          writeFile target (previous ++ (J.render event ++ "\n"))
        }
      };
      append (selfHostEvents c);
      if eqString suite "self-host-native" && S.not (eqString path "")
      then append path
      else ioReturn ()
    };
  selfHostId :: String -> String;
  selfHostId name = "self-host/posix/" ++ name;
  selfHostStart :: TestContext -> String -> IO ();
  selfHostStart c identity =
    selfHostEvent c (B.info ((:) ((,) "start" (J.str (selfHostId identity))) []));
  selfHostObservation :: TestContext -> String -> Bool -> J.Json -> IO ();
  selfHostObservation c identity passed detail =
    selfHostEvent c
      (B.info ((:) ((,) "id" (J.str (selfHostId identity)))
        ((:) ((,) "status" (J.str (if passed then "pass" else "fail")))
          ((:) ((,) "detail" detail) []))));
  selfHost :: TestContext -> IO ();
  -- A shared store can contain equal native binaries from different LLVM
  -- inputs. Select the candidate's actual producer, not the first hash match.
  selfHost c =
    do {
      let {
        manager = packageManager c
      };
      writeFile (selfHostEvents c) "";
      selfHostStart c "candidate-provenance";
      hash <- fileDigest (compiler c);
      producer <-
        O.envDefault "MLF_BUILD_REPORT" (O.parent (O.parent (compiler c)) ++ "/build-report.json");
      present <- fileExists producer;
      if present then ioReturn () else selfHostObservation c "candidate-provenance" False (J.str producer);
      O.require present "candidate package build report is missing";
      let {
        provenance = (output c ++ "/candidate-build-report.json")
      };
      O.copy producer provenance;
      produced <- J.read provenance;
      graph <- M.load (root c ++ "/mlf-package.json");
      snapshot <- M.snapshot graph;
      let {
        authentic = J.getBool "complete" False produced &&
          eqString (J.getText "implementation" "" produced) "MLF" &&
          J.equal snapshot (J.get "packages" produced)
      };
      if authentic then ioReturn () else selfHostObservation c "candidate-provenance" False (J.str provenance);
      O.require authentic "candidate build source provenance differs";
      let {
        cache = J.getText "cache_directory" (sharedCache c) produced
      };
      let {
        names =
          S.nubBy eqString
            (S.map (J.getText "key" "")
               (S.filter (\row -> eqString (J.getText "kind" "" row) "executable mlf-compiler:emlf")
                  (J.values (J.get "builds" produced))))
      };
      original <- findArtifact hash cache names;
      provenanceHash <- fileDigest provenance;
      record c "candidate_artifact"
        (B.info
           ((:) ((,) "directory" (J.str original))
              ((:) ((,) "key" (J.str (O.relative cache original)))
                 ((:) ((,) "build_report" (J.str provenance))
                    ((:) ((,) "build_report_sha256" (J.str provenanceHash)) [])))));
      selfHostObservation c "candidate-provenance" True
        (B.info ((:) ((,) "compiler_sha256" (J.str hash)) ((:) ((,) "build_report_sha256" (J.str provenanceHash)) [])));
      selfHostStart c "native-toolchain";
      stamp <- J.read (original ++ "/artifact.json");
      let {
        inputs = J.get "inputs" stamp
      };
      let {
        profile = J.getObject "native-pgo" inputs
      };
      O.require
        (S.null (J.items profile) ||
         (eqString (J.getText "mode" "" profile) "use" &&
          eqString (J.getText "target" "" profile) "emlf"))
        "self-host requires an ordinary or profile-use compiler";
      B.verifyPgo profile;
      let {
        toolchain = J.get "toolchain" inputs
      };
      let {
        cc = J.get "clang" toolchain
      };
      ccHash <- fileDigest (J.getText "path" "" cc);
      let { sameClang = eqString ccHash (J.getText "sha256" "" cc) };
      selfHostObservation c "native-toolchain" sameClang
        (B.info ((:) ((,) "clang_sha256" (J.str ccHash)) ((:) ((,) "native_pgo" profile) [])));
      O.require sameClang "self-host native compiler changed";
      let {
        profileArgs =
          if S.null (J.items profile)
          then []
          else S.append (O.words "--pgo-target emlf --pgo-use")
                 ((:) (J.getText "path" "" (J.get "profile" profile)) [])
      };
      let {
        nativeArgs = (:) "--clang" ((:) (J.getText "path" "" cc) profileArgs)
      };
      let {
        next = (output c ++ "/next-stage")
      };
      selfHostStart c "fresh-rebuild";
      O.remove next;
      let {
        argv =
          (:) manager
            (S.append (O.words "--timeout 21600 --compiler")
             ((:) (compiler c)
                ((:) "--build-dir"
                   ((:) next
                      ((:) "--cache-dir"
                         ((:) (next ++ "/cache") (S.append nativeArgs (O.words "build --target emlf"))))))))
      };
      putStrLn ("+ " ++ S.intercalate " " argv);
      code <- O.exec (root c) argv "" "" "" 21600;
      if code == 0 then ioReturn () else selfHostObservation c "fresh-rebuild" False
        (B.info ((:) ((,) "exit_code" (J.num code)) []));
      O.require (code == 0) ("self-host compiler build failed (" ++ (showInt code ++ ")"));
      saved <- J.read (next ++ "/build-report.json");
      let { complete = J.getBool "complete" False saved };
      if complete then ioReturn () else selfHostObservation c "fresh-rebuild" False (J.str (next ++ "/build-report.json"));
      O.require complete "next-stage package build incomplete";
      let {
        row =
          S.fromMaybe (panic "missing next compiler artifact")
            (S.find (\row -> eqString (J.getText "kind" "" row) "executable mlf-compiler:emlf")
               (J.values (J.get "builds" saved)))
      };
      let { fresh = S.not (J.getBool "cached" True row) };
      selfHostObservation c "fresh-rebuild" fresh
        (B.info ((:) ((,) "build_report" (J.str (next ++ "/build-report.json"))) ((:) ((,) "cached" (J.get "cached" row)) [])));
      O.require fresh "next compiler reused a previous build";
      selfHostStart c "producer-chain";
      managerHash <- fileDigest manager;
      let {
        producedBy = J.get "toolchain" saved;
        bound = eqString hash (J.getText "sha256" "" (J.get "compiler" producedBy)) &&
          eqString managerHash (J.getText "sha256" "" (J.get "manager" producedBy))
      };
      selfHostObservation c "producer-chain" bound producedBy;
      O.require bound "next stage did not use the selected compiler and manager";
      let {
        ir = (next ++ ("/cache/" ++ (J.getText "key" "" row ++ "/program.ll")))
      };
      selfHostStart c "llvm-fixed-point";
      old <- fileDigest (original ++ "/program.ll");
      new <- fileDigest ir;
      let { llvmFixed = eqString old new };
      selfHostObservation c "llvm-fixed-point" llvmFixed
        (B.info ((:) ((,) "candidate_sha256" (J.str old)) ((:) ((,) "rebuilt_sha256" (J.str new)) [])));
      O.require llvmFixed "package self-build did not reach an LLVM fixed point";
      selfHostStart c "binary-fixed-point";
      binary <- fileDigest (next ++ "/bin/emlf");
      B.verifyPgo profile;
      let { binaryFixed = eqString hash binary };
      selfHostObservation c "binary-fixed-point" binaryFixed
        (B.info ((:) ((,) "candidate_sha256" (J.str hash)) ((:) ((,) "rebuilt_sha256" (J.str binary)) [])));
      O.require binaryFixed "package self-build did not reach a native binary fixed point";
      eventsHash <- fileDigest (selfHostEvents c);
      record c "self_host_cases"
        (B.info ((:) ((,) "path" (J.str (selfHostEvents c))) ((:) ((,) "sha256" (J.str eventsHash)) [])));
      record c "native_pgo" profile;
      record c "fixed_point"
        (B.info
           ((:) ((,) "llvm_sha256" (J.str new))
              ((:) ((,) "next_compiler_sha256" (J.str binary))
                 ((:) ((,) "reused_candidate_build" (J.get "cached" row)) []))))
    };
  -- Campaign-specific options stay outside the generic package-manager CLI.
  selectedUnit :: TestContext -> String -> [] J.Json -> IO ();
  selectedUnit c name entries =
    if eqString name "backends"
    then do {
           transports c;
           binary <- nativeTest c "backends";
           matrixSuiteArgs c binary False (Catalog.matrixRows entries) []
             ((:) "--families" (S.map Catalog.identity entries))
             (Just entries)
         }
    else if eqString name "port"
         then do {
                transports c;
                references <- nativeTest c "references";
                setEnv "MLF_TEST_REFERENCES" references;
                binary <- nativeTest c "port";
                preparePortNames c binary (Just (Catalog.fixtures entries));
                matrixSuiteArgs c binary True (Catalog.matrixRows entries) []
                  ((:) "--families" (S.map Catalog.identity entries))
                  (Just entries)
              }
         else if eqString name "parity"
              then parity c
              else if eqString name "self-host"
                   then selfHost c
                   else if S.elem eqString name (O.words "package-integration package-distribution")
                        then do {
                               inventory <- J.read (root c ++ "/tests/golden/unit-inventory.json");
                               let {
                                 distribution = eqString name "package-distribution"
                               };
                               if distribution then ioReturn () else buildRunnerTests c;
                               setEnv "MLF_TEST_WORK" (output c);
                               setEnv "MLF_TEST_ROOT" (output c);
                               let {
                                 expectations =
                                   if distribution
                                   then (:) "28 checked package release cases passed" []
                                   else (:) "22 package resolver tests passed"
                                          ((:) "29 package integration cases passed"
                                             ((:) "Build scheduler integration tests passed"
                                                ((:) "1 target dependency integration test passed"
                                                   [])))
                               };
                               suiteArgsChecked c "packages"
                                 ((:) (if distribution then "--releases" else "--integration") [])
                                 expectations
                                 (Just (Catalog.projection inventory "packages" entries))
                             }
                        else do {
                               transports c;
                               if eqString name "core"
                               then core c False entries
                               else if eqString name "harness"
                                    then do {
                                           inventory <-
                                             J.read (root c ++ "/tests/golden/unit-inventory.json");
                                           let {
                                             ids = S.map Catalog.identity entries
                                           };
                                           suiteArgsEvidence c name ((:) "--families" ids) []
                                             (Just (Catalog.projection inventory name entries))
                                             (Just ids)
                                         }
                                    else if eqString name "test-framework"
                                         then do {
                                                unions <- nativeTest c "int-set-unions";
                                                suiteArgs c "test-framework"
                                                  ((:) "--verify-cli"
                                                     ((:) (output c ++ "/framework-cli")
                                                        ((:) unions [])))
                                                  []
                                              }
                                         else suite c name []
                             };
  selectedUnits :: TestContext -> [] J.Json -> IO ();
  selectedUnits c selected =
    S.mapM_
      (\((,) name entries) ->
         do {
           let {
             directory = (output c ++ ("/selected/" ++ name))
           };
           O.mkdir directory;
           let {
             child =
               TestContext (root c) directory (compiler c) (runtimeProfiles c) (sharedCache c)
                 (packageManager c)
           };
           parent <- J.read (report c);
           let {
             identity =
               J.Object
                 (S.filter
                    (\((,) key _) ->
                       S.elem eqString key
                         (O.words
                            "implementation compiler compiler_sha256 manager manager_sha256 runner runner_sha256 build_runner_sha256 sources requested_profiles"))
                    (J.items parent))
           };
           let {
             metadata =
               J.set "families" (J.Array (S.map Catalog.descriptor entries))
                 (J.set "units" (J.stringArray (S.nubBy eqString (S.map Catalog.unitName entries)))
                    (J.get "test_catalog" parent))
           };
           J.write (report child)
             (J.set "test_catalog" metadata
                (J.set "scope" (J.str "partial")
                   (J.set "group" (J.str "selected-unit")
                      (J.set "complete" (J.Boolean False) identity))));
           if eqString name "packages" then packages child else selectedUnit child name entries;
           record child "complete" (J.Boolean True);
           result <- J.read (report child);
           digest <- fileDigest (report child);
           current <- J.read (report c);
           let {
             receipt =
               J.set "families" (J.stringArray (S.map Catalog.identity entries))
                 (B.info
                    ((:) ((,) "path" (J.str (report child)))
                       ((:) ((,) "sha256" (J.str digest))
                          ((:)
                             ((,) "units"
                                (J.stringArray (S.nubBy eqString (S.map Catalog.unitName entries))))
                             []))))
           };
           record c "selected_units" (J.set name receipt (J.getObject "selected_units" current));
           if J.has "suites" result
           then do {
                  let {
                    merged =
                      S.foldl
                        (\saved ((,) suite evidence) ->
                           J.set suite (J.set "directory" (J.str directory) evidence) saved)
                        (J.getObject "suites" current)
                        (J.items (J.get "suites" result))
                  };
                  record c "suites" merged
                }
           else ioReturn ()
         })
      (Catalog.batches selected);
  options :: J.Json -> [] String -> IO ((,) J.Json ([] String));
  options config args =
    do {
      boundValueShared9 <- C.options config args;
      case boundValueShared9 of {
        (,) configured remaining ->
          do {
            let {
              matchValueShared2 = remaining
            } in
            case matchValueShared2 of {
              (:) matchValueShared3 matchValueShared4 ->
                if MLF.Primitive.eqString matchValueShared3 "--manager"
                then case matchValueShared4 of {
                       (:) matchValueShared7 matchValueShared8 ->
                         let {
                           value = matchValueShared7
                         } in
                         let {
                           rest = matchValueShared8
                         } in
                         options (J.set "manager" (J.str value) configured) rest;
                       _ -> ioReturn ((,) configured remaining)
                     }
                else case matchValueShared4 of {
                       (:) matchValueShared5 matchValueShared6 ->
                         let {
                           value = matchValueShared5
                         } in
                         let {
                           rest = matchValueShared6
                         } in
                         let {
                           flag = matchValueShared3
                         } in
                         if eqString flag "--compiler-receipt"
                         then options (J.set "compiler-receipt" (J.str value) configured) rest
                         else if Catalog.selector flag
                         then do {
                                next <-
                                  case Catalog.option configured flag value of {
                                    Left error -> O.fatal error;
                                    Right value -> return value
                                  };
                                options next rest
                              }
                         else ioReturn ((,) configured remaining);
                       _ -> ioReturn ((,) configured remaining)
                     };
              _ -> ioReturn ((,) configured remaining)
            }
          }
      }
    };
  parityArguments args = case args of {
    [] -> (,) [] [];
    (:) "--list" rest -> case parityArguments rest of {
      (,) config testArgs -> (,) config ((:) "--list" testArgs)
    };
    (:) flag ((:) value rest) -> case parityArguments rest of {
      (,) config testArgs ->
        if S.elem eqString flag (O.words "--exact --filter --tag --format --report")
        then (,) config ((:) flag ((:) value testArgs))
        else (,) ((:) flag ((:) value config)) testArgs
    };
    _ -> (,) args []
  };
  parityProducer c hash settings =
    do {
      identity <- query c [compiler c, "--implementation-identity"];
      let {
        path = J.getText "compiler-receipt" "" settings
      };
      if eqString path ""
      then record c "parity_producer"
        (B.info [(,) "identity" (J.str (O.trim identity)), (,) "compiler_sha256" (J.str hash)])
      else do {
        receipt <- J.read path;
        let {
          product = J.getObject "emlf" (J.getObject "outputs" receipt)
        };
        O.require (eqString (O.trim identity) "MLF/shared-haskell-v1 GHC" &&
          J.getBool "complete" False receipt && S.not (J.getBool "typecheck_only" True receipt) &&
          eqString (J.getText "producer_host" "" receipt) "GHC" &&
          eqString (J.getText "optimization" "" receipt) "0" &&
          eqString (J.getText "sha256" "" product) hash &&
          eqString (J.getText "path" "" product) (compiler c))
          "parity requires an authenticated GHC -O0 compiler";
        receiptHash <- fileDigest path;
        record c "parity_producer" (B.info
          [ (,) "identity" (J.str (O.trim identity))
          , (,) "compiler_sha256" (J.str hash)
          , (,) "optimization" (J.str "0")
          , (,) "build_receipt_sha256" (J.str receiptHash)
          ])
      }
    };
  main :: [] String -> IO ();
  main args =
    let {
      matchValueShared11 = args
    } in
    case matchValueShared11 of {
      (:) matchValueShared12 matchValueShared13 ->
        if MLF.Primitive.eqString matchValueShared12 "catalog"
        then let {
               rest = matchValueShared13
             } in
             Catalog.main rest
        else let {
               rest = matchValueShared13
             } in
             let {
               group = matchValueShared12
             } in
             do {
               let {
                 split = if eqString group "parity" then parityArguments rest else (,) rest []
               };
               boundValueShared10 <- options J.empty (S.fst split);
               case boundValueShared10 of {
                 (,) settings remaining ->
                   do {
                     O.require
                       (S.null remaining &&
                        (J.has "compiler" settings &&
                         (J.has "manager" settings && J.has "build-dir" settings)))
                       "compiler-tests GROUP --compiler TOOL --manager TOOL --build-dir DIRECTORY";
                     O.require
                       (S.elem eqString group
                          (O.words
                             "unit packages self-host parity backends backend-prepare port pr-smoke select port-prepare-StateTypes port-prepare-SolverReuse port-prepare-InferenceConformance port-prepare-other"))
                       "unknown compiler test group";
                     let {
                       hasSelection = Catalog.hasSelection settings
                     };
                     O.require
                       (if eqString group "select" then hasSelection else S.not hasSelection)
                       "metadata/family selectors require select; select requires at least one selector";
                     root <- canonicalPath ".";
                     catalog <- Catalog.load root;
                     selected <-
                       if eqString group "select"
                       then case Catalog.select catalog settings of {
                              Left error -> O.fatal error;
                              Right value -> return value
                            }
                       else return
                              (if S.elem eqString group (O.words "pr-smoke backend-prepare")
                               then []
                               else Catalog.forCampaign catalog group);
                     profile <- getEnv "MLF_TEST_RUNTIME_PROFILE";
                     O.require
                       (eqString profile "" || S.elem eqString profile ((:) "compact-gc" []))
                       "invalid runtime profile; expected compact-gc";
                     let {
                       profiles =
                         if (S.elem eqString group (O.words "port backends pr-smoke") ||
                             S.any
                               (\entry ->
                                  S.elem eqString (Catalog.unitName entry)
                                    (O.words "port backends"))
                               selected)
                         then (:) "compact-gc" []
                         else []
                     };
                     let {
                       directory = J.getText "build-dir" "" settings
                     };
                     O.mkdir directory;
                     out <- canonicalPath directory;
                     compiler <- canonicalPath (J.getText "compiler" "" settings);
                     manager <- canonicalPath (J.getText "manager" "" settings);
                     let {
                       defaultCache =
                         if eqString group "self-host"
                         then (O.parent (O.parent compiler) ++ "/cache")
                         else (O.parent out ++ "/mlf-test-suite/cache")
                     };
                     let {
                       requestedCache = J.getText "cache-dir" defaultCache settings
                     };
                     O.mkdir requestedCache;
                     cache <- canonicalPath requestedCache;
                     let {
                       c = TestContext root out compiler profiles cache manager
                     };
                     sourceHashes <- sources root;
                     hash <- fileDigest compiler;
                     managerHash <- fileDigest manager;
                     runner <- getExecutablePath;
                     runnerHash <- fileDigest runner;
                     configuredBuildRunner <-
                       O.envDefault "MLF_BUILD_RUNNER" (O.parent manager ++ "/mlf-build-runner");
                     buildRunner <- O.executable configuredBuildRunner;
                     buildRunnerHash <- fileDigest buildRunner;
                     let {
                       identity =
                         B.info
                           ((:) ((,) "complete" (J.Boolean False))
                              ((:) ((,) "implementation" (J.str "MLF"))
                                 ((:) ((,) "group" (J.str group))
                                    ((:) ((,) "compiler" (J.str compiler))
                                       ((:) ((,) "compiler_sha256" (J.str hash))
                                          ((:) ((,) "sources" sourceHashes) []))))))
                     };
                     let {
                       campaignIdentity =
                         J.set "runner_sha256" (J.str runnerHash)
                           (J.set "runner" (J.str runner)
                              (J.set "requested_profiles" (J.stringArray profiles)
                                 (J.set "manager_sha256" (J.str managerHash)
                                    (J.set "manager" (J.str manager) identity))))
                     };
                     J.write (report c)
                       (J.set "build_runner_sha256" (J.str buildRunnerHash) campaignIdentity);
                     catalogHash <- fileDigest (root ++ "/tests/test-catalog.json");
                     record c "scope"
                       (J.str
                          (if eqString group "select"
                           then "partial"
                           else if eqString group "pr-smoke"
                                then "smoke"
                                else if eqString group "backend-prepare" || O.starts "port-prepare-" group
                                     then "preparation"
                                     else "full"));
                     record c "test_catalog"
                       (J.set "path" (J.str (root ++ "/tests/test-catalog.json"))
                          (J.set "sha256" (J.str catalogHash)
                             (Catalog.selection catalog selected)));
                     setEnv "MLF_PACKAGE_MANAGER" manager;
                     clearDrivers;
                     unsetEnv "MLF_TEST_COVERAGE_REPORT";
                     unsetEnv "MLF_TEST_FAMILY_REPORT";
                     setEnv "MLF_BOOTSTRAP_COMPILER" compiler;
                     path <- getEnv "PATH";
                     windows <- O.isWindows;
                     setEnv "PATH" (O.parent compiler ++ ((if windows then ";" else ":") ++ path));
                     if eqString group "backend-prepare"
                     then do { _ <- prepareDrivers c False; return () }
                     else if eqString group "select"
                     then selectedUnits c selected
                     else if eqString group "self-host"
                          then selfHost c
                          else do {
                                 if eqString group "packages"
                                 then packages c
                                 else if eqString group "unit"
                                      then unit c
                                      else if eqString group "port"
                                           then port c
                                           else if eqString group "backends"
                                                then backends c
                                                else if eqString group "pr-smoke"
                                                     then prSmoke c
                                                     else if eqString group "parity"
                                                          then do {
                                                            parityProducer c hash settings;
                                                            parityWith c (J.getText "compiler-receipt" "" settings) (S.snd split)
                                                          }
                                                          else if O.starts "port-prepare-" group
                                                               then do {
                                                                      binary <- nativeTest c "port";
                                                                      preparePortShard c binary
                                                                        (O.drop 13 group)
                                                                    }
                                                               else O.fatal
                                                                      "unknown compiler test group"
                               };
                     after <- sources root;
                     O.require (J.equal sourceHashes after)
                       "compiler/test sources changed during validation";
                     current <- fileDigest compiler;
                     O.require (eqString hash current) "compiler changed during validation";
                     currentManager <- fileDigest manager;
                     O.require (eqString managerHash currentManager)
                       "package manager changed during validation";
                     currentRunner <- fileDigest runner;
                     O.require (eqString runnerHash currentRunner)
                       "compiler test runner changed during validation";
                     currentBuildRunner <- fileDigest buildRunner;
                     O.require (eqString buildRunnerHash currentBuildRunner)
                       "build runner changed during validation";
                     record c "complete" (J.Boolean True);
                     if eqString group "parity" &&
                       (case TestRunner.parse (S.snd split) of { Left _ -> False; Right options -> TestRunner.json options })
                     then return ()
                     else putStrLn ("Compiler package " ++ (group ++ " passed"))
                   }
               }
             };
      [] -> O.fatal "missing compiler test group"
    }
}
