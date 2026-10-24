-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Json where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Set as Set;
  import qualified Package.OS as O;
  data Json =
    Object (List (Pair String Json)) |
    Array (List Json) |
    String String |
    Number String |
    Boolean Bool |
    Null;
  object xs = Object xs;
  array xs = Array xs;
  str x = String x;
  num x = Number (showInt x);
  empty = Object Nil;
  items value =
    case value of {
      Object xs -> xs;
      _ -> panic "expected JSON object"
    };
  values value =
    case value of {
      Array xs -> xs;
      _ -> panic "expected JSON array"
    };
  text value =
    case value of {
      String x -> x;
      _ -> panic "expected JSON string"
    };
  bool value =
    case value of {
      Boolean x -> x;
      _ -> panic "expected JSON boolean"
    };
  strings value = S.map text (values value);
  stringArray xs = Array (S.map String xs);
  get key value = S.fromMaybe Null (S.lookup eqString key (items value));
  has key value = S.isJust (S.lookup eqString key (items value));
  getOr key fallback value = S.fromMaybe fallback (S.lookup eqString key (items value));
  getText key fallback value = text (getOr key (String fallback) value);
  getBool key fallback value = bool (getOr key (Boolean fallback) value);
  getObject key value = getOr key empty value;
  getStrings key value = strings (getOr key (Array Nil) value);
  set key item value =
    Object
      (Cons (Pair key item)
         (S.filter (\entry -> S.not (eqString (S.fst entry) key)) (items value)));
  add key item value = set key (Array (S.snoc (values (getOr key (Array Nil) value)) item)) value;
  quote text = ("\"" ++ (quoteAt text 0 ++ "\""));
  quoteAt :: String -> Int -> String;
  quoteAt text i = quoteChunks text i i Nil;
  -- Slice unescaped runs once; balanced chunk joining avoids repeatedly copying
  -- a growing string, including long source paths and declaration identities.
  quoteChunks :: String -> Int -> Int -> List String -> String;
  quoteChunks text start i chunks =
    if (i >= stringLength text)
    then S.concatStrings (S.reverse (Cons (stringSlice text start (i - start)) chunks))
    else let {
           n = stringCodeAt text i
         } in
         if ((n == 34) || ((n == 92) || (n < 32)))
         then let {
                escaped =
                  if (n == 34)
                  then "\\\""
                  else if (n == 92)
                       then "\\\\"
                       else ("\\u00" ++
                             (O.char "0123456789abcdef" (quotInt n 16) ++
                              O.char "0123456789abcdef" (remInt n 16)))
              } in
              quoteChunks text (i + 1) (i + 1)
                (Cons escaped (Cons (stringSlice text start (i - start)) chunks))
         else quoteChunks text start (i + 1) chunks;
  render :: Json -> String;
  render value =
    case value of {
      Object xs ->
        ("{" ++
         (S.intercalate ","
            (S.map (\entry -> (quote (S.fst entry) ++ (":" ++ render (S.snd entry))))
               (S.sortBy (\a b -> compareString (S.fst a) (S.fst b)) xs)) ++
          "}"));
      Array xs -> ("[" ++ (S.intercalate "," (S.map render xs) ++ "]"));
      String text -> quote text;
      Number text -> text;
      Boolean b -> if b then "true" else "false";
      Null -> "null"
    };
  equal a b = eqString (render a) (render b);
  space n = ((n == 32) || ((n == 9) || ((n == 10) || (n == 13))));
  skip :: String -> Int -> Int;
  skip source i =
    if ((i < stringLength source) && space (stringCodeAt source i)) then skip source (i + 1) else i;
  failure i = Left ("invalid JSON at offset " ++ showInt i);
  at source i code = ((i < stringLength source) && (stringCodeAt source i == code));
  startsAt source i token = startsAtFrom source i token 0;
  startsAtFrom :: String -> Int -> String -> Int -> Bool;
  startsAtFrom source i token j =
    ((j >= stringLength token) ||
     (at source (i + j) (stringCodeAt token j) && startsAtFrom source i token (j + 1)));
  parse source =
    do {
      boundValueShared1 <- parseAt source (skip source 0);
      case boundValueShared1 of {
        Pair value end ->
          do {
            if (skip source end == stringLength source) then Right value else failure end
          }
      }
    };
  parseAt :: String -> Int -> Either String (Pair Json Int);
  parseAt source i =
    if (i >= stringLength source)
    then failure i
    else let {
           c = stringCodeAt source i
         } in
         if (c == 123)
         then objectAt source (skip source (i + 1)) Nil
         else if (c == 91)
              then arrayAt source (skip source (i + 1)) Nil
              else if (c == 34)
                   then do {
                          boundValueShared2 <- stringAt source (i + 1) "";
                          case boundValueShared2 of {
                            Pair value next ->
                              do {
                                Right (Pair (String value) next)
                              }
                          }
                        }
                   else if startsAt source i "true"
                        then Right (Pair (Boolean True) (i + 4))
                        else if startsAt source i "false"
                             then Right (Pair (Boolean False) (i + 5))
                             else if startsAt source i "null"
                                  then Right (Pair Null (i + 4))
                                  else numberAt source i;
  stringAt :: String -> Int -> String -> Either String (Pair String Int);
  stringAt source i acc = stringChunksAt source i i (Cons acc Nil);
  stringChunksAt :: String -> Int -> Int -> List String -> Either String (Pair String Int);
  stringChunksAt source start i chunks =
    if (i >= stringLength source)
    then failure i
    else let {
           c = stringCodeAt source i
         } in
         if (c == 34)
         then Right
                (Pair
                   (S.concatStrings
                      (S.reverse (Cons (stringSlice source start (i - start)) chunks)))
                   (i + 1))
         else if (c < 32)
              then failure i
              else if (c == 92)
                   then do {
                          boundValueShared3 <- escapedAt source (i + 1);
                          case boundValueShared3 of {
                            Pair escaped next ->
                              do {
                                stringChunksAt source next next
                                  (Cons escaped
                                     (Cons (stringSlice source start (i - start)) chunks))
                              }
                          }
                        }
                   else stringChunksAt source start (i + 1) chunks;
  escapeAt :: String -> Int -> String -> Either String (Pair String Int);
  escapeAt source i acc =
    do {
      boundValueShared4 <- escapedAt source i;
      case boundValueShared4 of {
        Pair escaped next ->
          do {
            stringChunksAt source next next (Cons escaped (Cons acc Nil))
          }
      }
    };
  escapedAt :: String -> Int -> Either String (Pair String Int);
  escapedAt source i =
    if (i >= stringLength source)
    then failure i
    else let {
           c = stringCodeAt source i
         } in
         if (c == 117)
         then do {
                code <- hexAt source (i + 1) 4 0;
                if ((code >= 55296) && (code <= 56319))
                then if startsAt source (i + 5) "\\u"
                     then do {
                            low <- hexAt source (i + 7) 4 0;
                            if ((low >= 56320) && (low <= 57343))
                            then Right
                                   (Pair
                                      (stringFromCode
                                         (((65536 + ((code - 55296) * 1024)) + low) - 56320))
                                      (i + 11))
                            else failure i
                          }
                     else failure i
                else if ((code >= 56320) && (code <= 57343))
                     then failure i
                     else Right (Pair (stringFromCode code) (i + 5))
              }
         else if ((c == 34) || ((c == 92) || (c == 47)))
              then Right (Pair (stringFromCode c) (i + 1))
              else if ((c == 98) || ((c == 102) || ((c == 110) || ((c == 114) || (c == 116)))))
                   then Right
                          (Pair
                             (stringFromCode
                                (if (c == 98)
                                 then 8
                                 else if (c == 102)
                                      then 12
                                      else if (c == 110) then 10 else if (c == 114) then 13 else 9))
                             (i + 1))
                   else failure i;
  hexAt :: String -> Int -> Int -> Int -> Either String Int;
  hexAt source i remaining value =
    if (remaining == 0)
    then Right value
    else if (i >= stringLength source)
         then failure i
         else let {
                c = stringCodeAt source i
              } in
              let {
                n =
                  if ((c >= 48) && (c <= 57))
                  then (c - 48)
                  else if ((c >= 65) && (c <= 70))
                       then (c - 55)
                       else if ((c >= 97) && (c <= 102)) then (c - 87) else (0 - 1)
              } in
              if (n < 0)
              then failure i
              else hexAt source (i + 1) (remaining - 1) ((value * 16) + n);
  digit source i =
    ((i < stringLength source) && ((stringCodeAt source i >= 48) && (stringCodeAt source i <= 57)));
  digits :: String -> Int -> Int;
  digits source i = if digit source i then digits source (i + 1) else i;
  numberAt :: String -> Int -> Either String (Pair Json Int);
  numberAt source i =
    let {
      start = if at source i 45 then (i + 1) else i
    } in
    if S.not (digit source start)
    then failure i
    else let {
           whole = if (stringCodeAt source start == 48) then (start + 1) else digits source start
         } in
         let {
           frac =
             if at source whole 46
             then if digit source (whole + 1) then digits source (whole + 1) else (0 - 1)
             else whole
         } in
         if (frac < 0)
         then failure i
         else let {
                power = (at source frac 101 || at source frac 69)
              } in
              let {
                expStart = (frac + (if power then 1 else 0))
              } in
              let {
                expDigit =
                  if (power && (at source expStart 43 || at source expStart 45))
                  then (expStart + 1)
                  else expStart
              } in
              if (power && S.not (digit source expDigit))
              then failure i
              else let {
                     end = if power then digits source expDigit else frac
                   } in
                   Right (Pair (Number (stringSlice source i (end - i))) end);
  objectAt :: String -> Int -> List (Pair String Json) -> Either String (Pair Json Int);
  objectAt source i acc =
    if at source i 125
    then Right (Pair (Object (S.reverse acc)) (i + 1))
    else objectEntry source i acc;
  objectEntry :: String -> Int -> List (Pair String Json) -> Either String (Pair Json Int);
  objectEntry source i acc =
    objectEntries source i acc (Set.fromList compareString (S.map S.fst acc));
  objectEntries :: String ->
                   Int -> List (Pair String Json) -> Set String -> Either String (Pair Json Int);
  objectEntries source i acc seen =
    if S.not (at source i 34)
    then failure i
    else do {
           boundValueShared6 <- stringAt source (i + 1) "";
           case boundValueShared6 of {
             Pair key next ->
               do {
                 if Set.member compareString key seen
                 then Left ("duplicate JSON key: " ++ key)
                 else do {
                        let {
                          colon = skip source next
                        };
                        if S.not (at source colon 58)
                        then failure colon
                        else do {
                               boundValueShared5 <- parseAt source (skip source (colon + 1));
                               case boundValueShared5 of {
                                 Pair value end ->
                                   do {
                                     let {
                                       stop = skip source end
                                     };
                                     let {
                                       result = Cons (Pair key value) acc
                                     };
                                     if at source stop 125
                                     then Right (Pair (Object (S.reverse result)) (stop + 1))
                                     else if at source stop 44
                                          then objectEntries source (skip source (stop + 1)) result
                                                 (Set.insert compareString key seen)
                                          else failure stop
                                   }
                               }
                             }
                      }
               }
           }
         };
  arrayAt :: String -> Int -> List Json -> Either String (Pair Json Int);
  arrayAt source i acc =
    if at source i 93
    then Right (Pair (Array (S.reverse acc)) (i + 1))
    else arrayEntry source i acc;
  arrayEntry :: String -> Int -> List Json -> Either String (Pair Json Int);
  arrayEntry source i acc =
    do {
      boundValueShared7 <- parseAt source i;
      case boundValueShared7 of {
        Pair value next ->
          do {
            let {
              stop = skip source next
            };
            if at source stop 93
            then Right (Pair (Array (S.reverse (Cons value acc))) (stop + 1))
            else if at source stop 44
                 then arrayEntry source (skip source (stop + 1)) (Cons value acc)
                 else failure stop
          }
      }
    };
  read path =
    do {
      present <- fileExists path;
      O.require present ("missing JSON file: " ++ path);
      source <- readFile path;
      case parse source of {
        Left error -> O.fatal (path ++ (": " ++ error));
        Right value -> ioReturn value
      }
    };
  write path value = O.writeAtomic path (render value ++ "\n");
  fields value allowed context =
    case value of {
      Object xs ->
        S.mapM_
          (\entry ->
             O.require (S.elem eqString (S.fst entry) allowed)
               (context ++ (": unknown field " ++ S.fst entry)))
          xs;
      _ -> O.fatal (context ++ " must be an object")
    }
}
