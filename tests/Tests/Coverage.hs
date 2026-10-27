-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.Coverage where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  -- Execution evidence never reads the reviewed inventory. The parent validates
  -- the completed report against that separate file and the child's exit status.
  fields values = J.Object values;
  pair key value = (,) key value;
  event suite kind values =
    fields
      ((:) (pair "schema_version" (J.num 1))
         ((:) (pair "suite" (J.str suite)) ((:) (pair "event" (J.str kind)) values)));
  append suite kind values =
    do {
      path <- getEnv "MLF_TEST_COVERAGE_REPORT";
      if eqString path ""
      then return ()
      else do {
             previous <- readFile path;
             writeFile path (previous ++ (J.render (event suite kind values) ++ "\n"))
           }
    };
  begin suite full =
    do {
      path <- getEnv "MLF_TEST_COVERAGE_REPORT";
      if eqString path ""
      then return ()
      else writeFile path
             (J.render
                (event suite "start"
                   ((:) (pair "scope" (J.str (if full then "full" else "partial"))) [])) ++
              "\n")
    };
  passed suite identity =
    append suite "case"
      ((:) (pair "id" (J.str identity)) ((:) (pair "status" (J.str "passed")) []));
  alias suite identity canonical =
    append suite "alias"
      ((:) (pair "id" (J.str identity))
         ((:) (pair "canonical" (J.str canonical)) ((:) (pair "status" (J.str "passed")) [])));
  metric suite name value =
    append suite "metric" ((:) (pair "name" (J.str name)) ((:) (pair "value" (J.num value)) []));
  parse text = S.mapM J.parse (S.filter (\line -> (stringLength line > 0)) (O.lines text));
  kind name row = eqString (J.getText "event" "" row) name;
  finish suite =
    do {
      path <- getEnv "MLF_TEST_COVERAGE_REPORT";
      if eqString path ""
      then return ()
      else do {
             text <- readFile path;
             rows <-
               case parse text of {
                 Left error -> O.fatal error;
                 Right rows -> return rows
               };
             append suite "summary"
               ((:) (pair "complete" (J.Boolean True))
                  ((:) (pair "executions" (J.num (S.length (S.filter (kind "case") rows))))
                     ((:) (pair "aliases" (J.num (S.length (S.filter (kind "alias") rows))))
                        ((:) (pair "metrics" (J.num (S.length (S.filter (kind "metric") rows))))
                           []))))
           }
    };
  -- Count completed callback invocations, not the length of the planned inputs.
  count :: forall a. (a -> IO ()) -> [] a -> Int -> IO Int;
  count action inputs total =
    case inputs of {
      [] -> return total;
      (:) value rest ->
        do {
          action value;
          let {
            next = (total + 1)
          };
          seq next (count action rest next)
        }
    };
  mapCounted :: forall a. String -> String -> (a -> IO ()) -> [] a -> IO ();
  mapCounted suite name action inputs =
    do {
      completed <- count action inputs 0;
      metric suite name completed
    };
  forCounted :: forall a. String -> String -> [] a -> (a -> IO ()) -> IO ();
  forCounted suite name inputs action = mapCounted suite name action inputs;
  ensure condition message = if condition then Right () else Left message;
  sameStrings a b = S.eqList eqString (S.sortBy compareString a) (S.sortBy compareString b);
  unique values = (S.length values == S.length (S.nubBy eqString values));
  keys wanted value = sameStrings wanted (S.map S.fst (J.items value));
  strictStrings value =
    case value of {
      J.Array entries ->
        S.all
          (\entry ->
             case entry of {
               J.String text -> (stringLength text > 0);
               _ -> False
             })
          entries;
      _ -> False
    };
  natural value =
    case value of {
      J.Number text ->
        ((stringLength text > 0) &&
         S.all
           (\i ->
              let {
                code = stringCodeAt text i
              } in
              ((code >= 48) && (code <= 57)))
           (S.range 0 (stringLength text - 1)));
      _ -> False
    };
  validShape row =
    let {
      common = O.words "schema_version suite event"
    } in
    let {
      extra =
        if kind "start" row
        then O.words "scope"
        else if kind "case" row
             then O.words "id status"
             else if kind "alias" row
                  then O.words "id canonical status"
                  else if kind "metric" row
                       then O.words "name value"
                       else if kind "summary" row
                            then O.words "complete executions aliases metrics"
                            else []
    } in
    (S.not (S.null extra) && keys (S.append common extra) row);
  aliasOrder :: [] String -> [] J.Json -> Either String ();
  aliasOrder completed rows =
    case rows of {
      [] -> Right ();
      (:) row rest ->
        if kind "case" row
        then aliasOrder ((:) (J.getText "id" "" row) completed) rest
        else if kind "alias" row
             then do {
                    ensure (S.elem eqString (J.getText "canonical" "" row) completed)
                      "coverage alias lacks an earlier completed canonical execution";
                    aliasOrder completed rest
                  }
             else aliasOrder completed rest
    };
  validate :: J.Json -> String -> String -> Either String J.Json;
  validate inventory suite text = validateScope "full" inventory suite text;
  -- Focused package phases have no aliases or generated-loop metrics. Their
  -- expected IDs are a reviewed-inventory projection, never child output. The
  -- ordinary full validator remains strict and cannot accept this report.
  validateSelection :: J.Json -> String -> [] String -> String -> Either String J.Json;
  validateSelection inventory suite selected text =
    do {
      ensure (J.has suite (J.get "suites" inventory)) "unknown selected coverage suite";
      let {
        source = J.get suite (J.get "suites" inventory)
      };
      let {
        all = J.getStrings "executions" source
      };
      ensure
        (S.not (S.null selected) &&
         (unique selected && S.all (\name -> S.elem eqString name all) selected))
        "invalid selected coverage IDs";
      ensure
        (S.null (J.items (J.get "aliases" source)) && S.null (J.items (J.get "metrics" source)))
        "selected coverage requires a flat execution inventory";
      let {
        projected = J.set "executions" (J.stringArray selected) source
      };
      let {
        expected = J.set "suites" (J.set suite projected (J.get "suites" inventory)) inventory
      };
      validateScope "partial" expected suite text
    };
  -- A selected family can own aliases and counted generated inputs. The parent
  -- supplies this projection from reviewed source metadata, never child output.
  -- Validate both its membership in the full inventory and its actual partial
  -- report; full qualification still uses validate's unchanged full scope.
  projectionObject value =
    case value of {
      J.Object _ -> True;
      _ -> False
    };
  projectionString value =
    case value of {
      J.String _ -> True;
      _ -> False
    };
  -- Guard the unchanged full validator's typed getters before delegating the
  -- partial path to it. A malformed row must produce Left rather than panic.
  projectionReportShape row =
    case row of {
      J.Object _ ->
        (projectionString (J.get "event" row) &&
         (projectionString (J.get "suite" row) &&
          (if kind "start" row
           then projectionString (J.get "scope" row)
           else if kind "case" row
                then (projectionString (J.get "id" row) && projectionString (J.get "status" row))
                else if kind "alias" row
                     then (projectionString (J.get "id" row) &&
                           (projectionString (J.get "canonical" row) &&
                            projectionString (J.get "status" row)))
                     else if kind "metric" row
                          then (projectionString (J.get "name" row) && natural (J.get "value" row))
                          else if kind "summary" row
                               then S.all (\name -> natural (J.get name row))
                                      (O.words "executions aliases metrics")
                               else False)));
      _ -> False
    };
  validateProjection :: J.Json -> String -> J.Json -> String -> Either String J.Json;
  validateProjection inventory suite projected text =
    do {
      ensure (projectionObject inventory) "reviewed coverage inventory must be an object";
      ensure
        (J.equal (J.get "schema_version" inventory) (J.num 1) &&
         projectionObject (J.get "suites" inventory))
        "missing or unsupported reviewed coverage inventory";
      ensure (J.has suite (J.get "suites" inventory)) "missing reviewed coverage suite";
      let {
        source = J.get suite (J.get "suites" inventory)
      };
      projectionEntry source;
      projectionEntry projected;
      let {
        sourceExecutions = J.getStrings "executions" source
      };
      let {
        selected = J.getStrings "executions" projected
      };
      let {
        selectedAliases = J.items (J.get "aliases" projected)
      };
      let {
        selectedMetrics = J.items (J.get "metrics" projected)
      };
      ensure (S.not (S.null selected && (S.null selectedAliases && S.null selectedMetrics)))
        "empty coverage projection";
      ensure (S.all (\identity -> S.elem eqString identity sourceExecutions) selected)
        "projected execution is not in the reviewed inventory";
      ensure
        (S.all
           (\((,) name value) ->
              (J.has name (J.get "aliases" source) &&
               J.equal value (J.get name (J.get "aliases" source))))
           selectedAliases)
        "projected alias differs from the reviewed inventory";
      ensure
        (S.all
           (\((,) name value) ->
              (J.has name (J.get "metrics" source) &&
               J.equal value (J.get name (J.get "metrics" source))))
           selectedMetrics)
        "projected metric differs from the reviewed inventory";
      rows <- parse text;
      ensure (S.all projectionReportShape rows) "coverage report contains malformed field types";
      let {
        expected = J.set "suites" (J.set suite projected (J.get "suites" inventory)) inventory
      };
      validateScope "partial" expected suite text
    };
  projectionEntry :: J.Json -> Either String ();
  projectionEntry entry =
    do {
      ensure (projectionObject entry) "coverage projection inventory must be an object";
      ensure
        (keys (O.words "executions aliases metrics") entry &&
         strictStrings (J.get "executions" entry))
        "invalid coverage projection inventory";
      let {
        executions = J.getStrings "executions" entry
      };
      let {
        aliases = J.get "aliases" entry
      };
      let {
        metrics = J.get "metrics" entry
      };
      ensure (unique executions) "duplicate projected execution";
      ensure (projectionObject aliases) "invalid projected alias inventory";
      ensure (projectionObject metrics) "invalid projected metric inventory";
      ensure (unique (S.map S.fst (J.items aliases)) && unique (S.map S.fst (J.items metrics)))
        "duplicate projected alias or metric";
      ensure
        (S.all
           (\((,) name value) ->
              ((stringLength name > 0) &&
               (S.not (S.elem eqString name executions) &&
                (case value of {
                   J.String canonical -> S.elem eqString canonical executions;
                   _ -> False
                 }))))
           (J.items aliases))
        "projected alias lacks a selected canonical execution";
      ensure
        (S.all (\((,) name value) -> ((stringLength name > 0) && natural value)) (J.items metrics))
        "projected metrics must be natural numbers"
    };
  validateScope :: String -> J.Json -> String -> String -> Either String J.Json;
  validateScope scope inventory suite text =
    do {
      ensure
        (J.equal (J.get "schema_version" inventory) (J.num 1) &&
         J.has suite (J.get "suites" inventory))
        "missing or unsupported reviewed coverage inventory";
      let {
        expected = J.get suite (J.get "suites" inventory)
      };
      let {
        wanted = J.getStrings "executions" expected
      };
      let {
        wantedAliases = J.getObject "aliases" expected
      };
      let {
        wantedMetrics = J.getObject "metrics" expected
      };
      ensure
        (keys (O.words "executions aliases metrics") expected &&
         (strictStrings (J.get "executions" expected) && unique wanted))
        "invalid reviewed execution inventory";
      ensure
        (case J.get "aliases" expected of {
           J.Object _ -> True;
           _ -> False
         })
        "invalid reviewed alias inventory";
      ensure
        (case J.get "metrics" expected of {
           J.Object _ -> True;
           _ -> False
         })
        "invalid reviewed metric inventory";
      ensure
        (S.all (\((,) name value) -> ((stringLength name > 0) && natural value))
           (J.items wantedMetrics))
        "reviewed metrics must be natural numbers";
      ensure
        (S.all
           (\((,) name value) ->
              ((stringLength name > 0) &&
               (S.not (S.elem eqString name wanted) &&
                (case value of {
                   J.String canonical -> S.elem eqString canonical wanted;
                   _ -> False
                 }))))
           (J.items wantedAliases))
        "invalid reviewed canonical aliases";
      rows <- parse text;
      ensure (S.length rows >= 2) "coverage report is empty or truncated";
      ensure
        (S.all
           (\row ->
              (validShape row &&
               (J.equal (J.get "schema_version" row) (J.num 1) &&
                eqString (J.getText "suite" "" row) suite)))
           rows)
        "coverage row has wrong schema, suite or fields";
      let {
        first = S.head rows
      };
      let {
        last = S.last rows
      };
      ensure
        (kind "start" first &&
         (eqString (J.getText "scope" "" first) scope &&
          (S.length (S.filter (kind "start") rows) == 1)))
        "coverage report has the wrong scope or an invalid start";
      ensure
        (kind "summary" last &&
         (J.equal (J.get "complete" last) (J.Boolean True) &&
          (S.length (S.filter (kind "summary") rows) == 1)))
        "coverage report is incomplete or has multiple summaries";
      let {
        executed = S.filter (kind "case") rows
      };
      let {
        aliases = S.filter (kind "alias") rows
      };
      let {
        metrics = S.filter (kind "metric") rows
      };
      let {
        identities = S.map (J.getText "id" "") executed
      };
      let {
        aliasIds = S.map (J.getText "id" "") aliases
      };
      let {
        metricNames = S.map (J.getText "name" "") metrics
      };
      ensure (unique (S.append identities aliasIds) && sameStrings identities wanted)
        "missing, duplicate or unknown executed case";
      ensure
        (S.all (\row -> eqString (J.getText "status" "" row) "passed") (S.append executed aliases))
        "coverage contains a failed or unknown outcome";
      ensure
        (sameStrings aliasIds (S.map S.fst (J.items wantedAliases)) &&
         S.all
           (\row -> J.equal (J.get "canonical" row) (J.get (J.getText "id" "" row) wantedAliases))
           aliases)
        "coverage alias inventory changed";
      aliasOrder [] rows;
      ensure
        (unique metricNames &&
         (sameStrings metricNames (S.map S.fst (J.items wantedMetrics)) &&
          S.all
            (\row -> J.equal (J.get "value" row) (J.get (J.getText "name" "" row) wantedMetrics))
            metrics))
        "coverage metrics changed or are missing or duplicated";
      ensure
        (J.equal (J.get "executions" last) (J.num (S.length executed)) &&
         (J.equal (J.get "aliases" last) (J.num (S.length aliases)) &&
          J.equal (J.get "metrics" last) (J.num (S.length metrics))))
        "coverage summary differs from actual events";
      return
        (fields
           ((:) (pair "schema_version" (J.num 1))
              ((:) (pair "suite" (J.str suite))
                 ((:) (pair "executions" (J.num (S.length executed)))
                    ((:) (pair "aliases" (J.num (S.length aliases)))
                       ((:)
                          (pair "metrics"
                             (fields
                                (S.map (\row -> pair (J.getText "name" "" row) (J.get "value" row))
                                   metrics)))
                          []))))))
    }
}
