-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.Selection where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  -- Family selection changes scheduling, never the actions or their oracles.
  validId identity =
    ((stringLength identity > 0) &&
     S.all
       (\index ->
          let {
            code = stringCodeAt identity index
          } in
          (((code >= 48) && (code <= 57)) ||
           (((code >= 65) && (code <= 90)) ||
            (((code >= 97) && (code <= 122)) ||
             ((code == 45) || ((code == 46) || ((code == 47) || (code == 95))))))))
       (S.range 0 (stringLength identity - 1)));
  unique values = (S.length values == S.length (S.nubBy eqString values));
  validIds values = (S.not (S.null values) && (unique values && S.all validId values));
  ensure condition message = if condition then Right () else Left message;
  listing :: [] String -> Bool;
  listing args = S.eqList eqString args ((:) "--list-families" []);
  choose :: [] String -> [] String -> Either String ((,) Bool ([] String));
  choose available args =
    do {
      ensure (validIds available) "invalid or empty test family inventory";
      let {
        matchValueShared1 = args
      } in
      case matchValueShared1 of {
        [] -> return ((,) True available);
        (:) matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "--families"
          then let {
                 requested = matchValueShared3
               } in
               do {
                 ensure
                   (validIds requested &&
                    S.all (\identity -> S.elem eqString identity available) requested)
                   "invalid, duplicate or unknown test family selection";
                 return
                   ((,) False
                      (S.filter (\identity -> S.elem eqString identity requested) available))
               }
          else Left "test [--list-families | --families ID ...]";
        _ -> Left "test [--list-families | --families ID ...]"
      }
    };
  scope :: Bool -> String;
  scope full = if full then "full" else "partial";
  event unit name values =
    J.Object
      ((:) ((,) "schema_version" (J.num 1))
         ((:) ((,) "unit" (J.str unit)) ((:) ((,) "event" (J.str name)) values)));
  append unit name values =
    do {
      path <- getEnv "MLF_TEST_FAMILY_REPORT";
      if eqString path ""
      then return ()
      else do {
             previous <- readFile path;
             writeFile path (previous ++ (J.render (event unit name values) ++ "\n"))
           }
    };
  begin :: String -> Bool -> [] String -> IO ();
  begin unit full selected =
    do {
      O.require (validId unit && validIds selected) "invalid family report identity or selection";
      path <- getEnv "MLF_TEST_FAMILY_REPORT";
      if eqString path ""
      then return ()
      else writeFile path
             (J.render
                (event unit "start"
                   ((:) ((,) "scope" (J.str (scope full)))
                      ((:) ((,) "selected" (J.stringArray selected)) []))) ++
              "\n")
    };
  passed :: String -> String -> IO ();
  passed unit identity =
    do {
      O.require (validId unit && validId identity) "invalid completed family identity";
      append unit "family"
        ((:) ((,) "id" (J.str identity)) ((:) ((,) "status" (J.str "passed")) []))
    };
  parse text = S.mapM J.parse (S.filter (\line -> (stringLength line > 0)) (O.lines text));
  kind name row = eqString (J.getText "event" "" row) name;
  finish :: String -> IO ();
  finish unit =
    do {
      path <- getEnv "MLF_TEST_FAMILY_REPORT";
      if eqString path ""
      then return ()
      else do {
             text <- readFile path;
             rows <-
               case parse text of {
                 Left error -> O.fatal error;
                 Right value -> return value
               };
             append unit "summary"
               ((:) ((,) "complete" (J.Boolean True))
                  ((:) ((,) "families" (J.num (S.length (S.filter (kind "family") rows)))) []))
           }
    };
  sameStrings left right =
    S.eqList eqString (S.sortBy compareString left) (S.sortBy compareString right);
  keys wanted value =
    case value of {
      J.Object fields -> sameStrings wanted (S.map S.fst fields);
      _ -> False
    };
  strictIds value =
    case value of {
      J.Array values ->
        S.all
          (\entry ->
             case entry of {
               J.String identity -> validId identity;
               _ -> False
             })
          values;
      _ -> False
    };
  stringValue value =
    case value of {
      J.String _ -> True;
      _ -> False
    };
  validShape row =
    case row of {
      J.Object _ ->
        (stringValue (J.get "event" row) &&
         (stringValue (J.get "unit" row) &&
          (let {
             common = O.words "schema_version unit event"
           } in
           if kind "start" row
           then (keys (S.append common (O.words "scope selected")) row &&
                 (stringValue (J.get "scope" row) && strictIds (J.get "selected" row)))
           else if kind "family" row
                then (keys (S.append common (O.words "id status")) row &&
                      (stringValue (J.get "id" row) && stringValue (J.get "status" row)))
                else if kind "summary" row
                     then keys (S.append common (O.words "complete families")) row
                     else False)));
      _ -> False
    };
  validate :: String -> Bool -> [] String -> String -> Either String J.Json;
  validate unit full expected text =
    do {
      ensure (validId unit && validIds expected) "invalid reviewed family selection";
      rows <- parse text;
      ensure (S.length rows >= 3) "family report is empty or truncated";
      ensure
        (S.all
           (\row ->
              (validShape row &&
               (J.equal (J.get "schema_version" row) (J.num 1) &&
                eqString (J.getText "unit" "" row) unit)))
           rows)
        "family report has wrong schema, unit or fields";
      let {
        first = S.head rows
      };
      let {
        last = S.last rows
      };
      ensure
        (kind "start" first &&
         ((S.length (S.filter (kind "start") rows) == 1) &&
          eqString (J.getText "scope" "" first) (scope full)))
        "family report has wrong scope or an invalid start";
      ensure
        (strictIds (J.get "selected" first) &&
         S.eqList eqString (J.getStrings "selected" first) expected)
        "family report selection differs from the reviewed plan";
      ensure
        (kind "summary" last &&
         ((S.length (S.filter (kind "summary") rows) == 1) &&
          J.equal (J.get "complete" last) (J.Boolean True)))
        "family report is incomplete or has multiple summaries";
      let {
        completed = S.filter (kind "family") rows
      };
      let {
        identities = S.map (J.getText "id" "") completed
      };
      ensure (unique identities && S.eqList eqString identities expected)
        "missing, duplicate, unknown or reordered completed family";
      ensure (S.all (\row -> eqString (J.getText "status" "" row) "passed") completed)
        "family report contains a failed or unknown outcome";
      ensure (J.equal (J.get "families" last) (J.num (S.length completed)))
        "family summary differs from actual completion events";
      return
        (J.Object
           ((:) ((,) "schema_version" (J.num 1))
              ((:) ((,) "unit" (J.str unit))
                 ((:) ((,) "scope" (J.str (scope full)))
                    ((:) ((,) "families" (J.num (S.length completed)))
                       ((:) ((,) "ids" (J.stringArray identities)) []))))))
    }
}
