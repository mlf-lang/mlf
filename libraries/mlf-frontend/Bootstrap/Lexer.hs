-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Lexer where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Unicode as U;
  data Token = Token String Int Int Int Int;
  data Cursor = Cursor Int Int Int;
  data Scanned = Scanned ([] Token) Token;
  tokenText :: Token -> String;
  tokenText (Token s _ _ _ _) = s;
  tokenLine :: Token -> Int;
  tokenLine (Token _ n _ _ _) = n;
  tokenColumn :: Token -> Int;
  tokenColumn (Token _ _ n _ _) = n;
  tokenEndLine :: Token -> Int;
  tokenEndLine (Token _ _ _ n _) = n;
  tokenEndColumn :: Token -> Int;
  tokenEndColumn (Token _ _ _ _ n) = n;
  cursorIndex :: Cursor -> Int;
  cursorIndex (Cursor n _ _) = n;
  advance :: Int -> Cursor -> Cursor;
  advance c (Cursor i l n) =
    let {
      nextIndex = (i + 1)
    } in
    let {
      nextLine = if (c == 10) then (l + 1) else l
    } in
    let {
      nextColumn = if (c == 10) then 1 else if (c == 9) then ((n + 8) - ((n - 1) % 8)) else (n + 1)
    } in
    seq nextIndex (seq nextLine (seq nextColumn (Cursor nextIndex nextLine nextColumn)));
  lexError :: String -> Cursor -> String -> String;
  lexError file (Cursor _ line column) message =
    (file ++ (":" ++ (showInt line ++ (":" ++ (showInt column ++ (": " ++ message))))));
  codeAt :: String -> Int -> Int -> Int;
  codeAt source size i = if (i < size) then stringCodeAt source i else (-1);
  isDigit :: Int -> Bool;
  isDigit c = ((c >= 48) && (c <= 57));
  isHexDigit :: Int -> Bool;
  isHexDigit c = (isDigit c || (((c >= 65) && (c <= 70)) || ((c >= 97) && (c <= 102))));
  isIdentChar :: Int -> Bool;
  isIdentChar c = (U.isAlphaNum c || ((c == 95) || (c == 39)));
  isOperator :: Int -> Bool;
  isOperator c =
    elem eqInt c
      ((:) 58
         ((:) 33
            ((:) 35
               ((:) 36
                  ((:) 37
                     ((:) 38
                        ((:) 42
                           ((:) 43
                              ((:) 46
                                 ((:) 47
                                    ((:) 60
                                       ((:) 61
                                          ((:) 62
                                             ((:) 63
                                                ((:) 64
                                                   ((:) 92
                                                      ((:) 94
                                                         ((:) 124
                                                            ((:) 45
                                                               ((:) 126 []))))))))))))))))))));
  starts :: String -> Int -> Int -> Int -> Bool;
  starts source size i c = (codeAt source size i == c);
  skipLine :: String -> Int -> Cursor -> Cursor;
  skipLine source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if ((i >= size) || (codeAt source size i == 10))
    then cursor
    else skipLine source size (advance (codeAt source size i) cursor);
  skipComment :: String -> String -> Int -> Int -> Cursor -> Either String Cursor;
  skipComment file source size depth cursor =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Left (lexError file cursor "unterminated comment")
    else if (starts source size i 123 && starts source size (i + 1) 45)
         then let {
                nextDepth = (depth + 1)
              } in
              seq nextDepth
                (skipComment file source size nextDepth (advance 45 (advance 123 cursor)))
         else if (starts source size i 45 && starts source size (i + 1) 125)
              then let {
                     next = advance 125 (advance 45 cursor)
                   } in
                   if (depth == 1)
                   then Right next
                   else let {
                          nextDepth = (depth - 1)
                        } in
                        seq nextDepth (skipComment file source size nextDepth next)
              else skipComment file source size depth (advance (codeAt source size i) cursor);
  skipWhite :: String -> String -> Int -> Cursor -> Either String Cursor;
  skipWhite file source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Right cursor
    else if U.isSpace (codeAt source size i)
         then skipWhite file source size (advance (codeAt source size i) cursor)
         else if (starts source size i 45 && starts source size (i + 1) 45)
              then skipWhite file source size (skipLine source size cursor)
              else if (starts source size i 123 && starts source size (i + 1) 45)
                   then case skipComment file source size 1 (advance 45 (advance 123 cursor)) of {
                          Left e -> Left e;
                          Right next -> skipWhite file source size next
                        }
                   else Right cursor;
  consumeWhile :: (Int -> Bool) -> String -> Int -> Cursor -> Cursor;
  consumeWhile predicate source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if ((i < size) && predicate (codeAt source size i))
    then consumeWhile predicate source size (advance (codeAt source size i) cursor)
    else cursor;
  scanQuoted :: String -> String -> Int -> Cursor -> Either String Cursor;
  scanQuoted file source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Left (lexError file cursor "unterminated string")
    else if starts source size i 34
         then Right (advance 34 cursor)
         else if starts source size i 92
              then let {
                     next = advance 92 cursor
                   } in
                   let {
                     j = cursorIndex next
                   } in
                   if (j >= size)
                   then Left (lexError file next "unterminated string escape")
                   else if U.isSpace (codeAt source size j)
                        then let {
                               gap = consumeWhile U.isSpace source size next
                             } in
                             if starts source size (cursorIndex gap) 92
                             then scanQuoted file source size (advance 92 gap)
                             else Left (lexError file gap "string gap must end with backslash")
                        else scanQuoted file source size (advance (codeAt source size j) next)
              else if (codeAt source size i <= 26)
                   then Left (lexError file cursor "unescaped control character in string")
                   else scanQuoted file source size (advance (codeAt source size i) cursor);
  -- Source scanning consumes complete control/numeric/gap escapes. The opaque
  -- IR/metadata scanner above retains its existing grammar and representation.
  scanSourceQuoted :: String -> String -> Int -> Cursor -> Either String Cursor;
  scanSourceQuoted file source size cursor =
    let { i = cursorIndex cursor } in
    if i >= size then Left (lexError file cursor "unterminated string")
    else let { c = codeAt source size i } in
      if c == 34 then Right (advance c cursor)
      else if c == 92
      then case sourceEscapeCode source (i + 1) size of {
        Left error -> Left (lexError file cursor error);
        Right ((,) _ next) -> scanSourceQuoted file source size (advanceSourceTo source next cursor)
      }
      else if not (U.isPrint c) then Left (lexError file cursor "unescaped non-printable character in source string")
      else scanSourceQuoted file source size (advance c cursor);
  advanceSourceTo :: String -> Int -> Cursor -> Cursor;
  advanceSourceTo source end cursor =
    if cursorIndex cursor >= end then cursor
    else advanceSourceTo source end (advance (stringCodeAt source (cursorIndex cursor)) cursor);
  scanNumber :: String -> Int -> Cursor -> Cursor;
  scanNumber source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if (starts source size i 48 &&
        (starts source size (i + 1) 120 || starts source size (i + 1) 88))
    then consumeWhile isHexDigit source size
           (advance (codeAt source size (i + 1)) (advance 48 cursor))
    else if (starts source size i 48 &&
             (starts source size (i + 1) 111 || starts source size (i + 1) 79))
         then consumeWhile (\c -> ((c >= 48) && (c <= 55))) source size
                (advance (codeAt source size (i + 1)) (advance 48 cursor))
         else let {
                digits = consumeWhile isDigit source size cursor
              } in
              let {
                j = cursorIndex digits
              } in
              let {
                fraction =
                  if (starts source size j 46 && isDigit (codeAt source size (j + 1)))
                  then consumeWhile isDigit source size (advance 46 digits)
                  else digits
              } in
              let {
                k = cursorIndex fraction
              } in
              if (starts source size k 101 || starts source size k 69)
              then let {
                     exponent = advance (codeAt source size k) fraction
                   } in
                   let {
                     q = cursorIndex exponent
                   } in
                   let {
                     signed =
                       if (starts source size q 43 || starts source size q 45)
                       then advance (codeAt source size q) exponent
                       else exponent
                   } in
                   if isDigit (codeAt source size (cursorIndex signed))
                   then consumeWhile isDigit source size signed
                   else fraction
              else fraction;
  scanTokens :: String -> String -> Either String Scanned;
  scanTokens file source = scanMore file source (stringLength source) (Cursor 0 1 1);
  scanSourceTokens :: String -> String -> Either String Scanned;
  scanSourceTokens file source = scanMoreWith scanSourceQuoted file source (stringLength source) (Cursor 0 1 1);
  scanMore :: String -> String -> Int -> Cursor -> Either String Scanned;
  scanMore = scanMoreWith scanQuoted;
  scanMoreWith :: (String -> String -> Int -> Cursor -> Either String Cursor) ->
                  String -> String -> Int -> Cursor -> Either String Scanned;
  scanMoreWith quoted file source size cursor =
    case skipWhite file source size cursor of {
      Left e -> Left e;
      Right begin ->
        case begin of {
          Cursor i line column ->
            if (i >= size)
            then Right (Scanned [] (Token "" line column line column))
            else let {
                   c = codeAt source size i
                 } in
                 let {
                   next =
                     if (c == 34)
                     then quoted file source size (advance c begin)
                     else Right
                            (if (U.isAlpha c || ((c == 95) || (c == 39)))
                             then consumeWhile isIdentChar source size begin
                             else if isDigit c
                                  then scanNumber source size begin
                                  else if isOperator c
                                       then consumeWhile isOperator source size begin
                                       else advance c begin)
                 } in
                 case next of {
                   Left e -> Left e;
                   Right end ->
                     case end of {
                       Cursor j lastLine lastColumn ->
                         case scanMoreWith quoted file source size end of {
                           Left e -> Left e;
                           Right (Scanned rest finish) ->
                             Right
                               (Scanned
                                  ((:)
                                     (Token (stringSlice source i (j - i)) line column lastLine
                                        lastColumn)
                                     rest)
                                  finish)
                         }
                     }
                 }
        }
    };
  digitValue :: Int -> Int;
  digitValue c =
    if ((c >= 48) && (c <= 57))
    then (c - 48)
    else if ((c >= 65) && (c <= 70))
         then (c - 55)
         else if ((c >= 97) && (c <= 102)) then (c - 87) else (-1);
  readBase :: Int -> String -> Int -> Int -> Either String Int;
  readBase base source index value =
    if (index == stringLength source)
    then Right value
    else let {
           digit = digitValue (stringCodeAt source index)
         } in
         if ((digit < 0) || (digit >= base))
         then Left "invalid integer literal"
         else let {
                nextValue = ((value * base) + digit)
              } in
              seq nextValue (readBase base source (index + 1) nextValue);
  naturalValue :: String -> Either String Int;
  naturalValue source =
    let {
      size = stringLength source
    } in
    if ((size >= 2) &&
        ((stringCodeAt source 0 == 48) &&
         ((stringCodeAt source 1 == 120) || (stringCodeAt source 1 == 88))))
    then if (size == 2) then Left "empty hexadecimal literal" else readBase 16 source 2 0
    else if ((size >= 2) &&
             ((stringCodeAt source 0 == 48) &&
              ((stringCodeAt source 1 == 111) || (stringCodeAt source 1 == 79))))
         then if (size == 2) then Left "empty octal literal" else readBase 8 source 2 0
         else readBase 10 source 0 0;
  isFloating :: String -> Bool;
  isFloating source = stringAny (\c -> ((c == 46) || ((c == 101) || (c == 69)))) source;
  stringAny :: (Int -> Bool) -> String -> Bool;
  stringAny predicate source = stringAnyAt predicate source 0 (stringLength source);
  stringAnyAt :: (Int -> Bool) -> String -> Int -> Int -> Bool;
  stringAnyAt predicate source i size =
    ((i < size) &&
     (predicate (stringCodeAt source i) || stringAnyAt predicate source (i + 1) size));
  -- Source literals carry full Haskell Char values, not opaque UTF-8 Text.
  -- Keep stringValue and its scalar-only clients (metadata/X) unchanged.
  sourceStringValue :: String -> Either String SourceString;
  sourceStringValue source = mapEither joinSourceString (sourceStringChunks source 1 (stringLength source - 1));
  joinSourceString :: [] SourceString -> SourceString;
  joinSourceString chunks =
    if any sourceStringHasCodes chunks
    then CharString (concatMap sourceStringCodes chunks)
    else ScalarString (concatStrings (map sourceStringText chunks));
  sourceStringHasCodes :: SourceString -> Bool;
  sourceStringHasCodes value = case value of { ScalarString _ -> False; CharString _ -> True };
  sourceStringText :: SourceString -> String;
  sourceStringText value = case value of { ScalarString text -> text; CharString _ -> "" };
  sourceStringCodes :: SourceString -> [] Int;
  sourceStringCodes value = case value of {
    CharString codes -> codes;
    ScalarString text -> sourceTextCodes text 0 (stringLength text)
  };
  sourceTextCodes :: String -> Int -> Int -> [] Int;
  sourceTextCodes text i size =
    if i >= size then [] else (:) (stringCodeAt text i) (sourceTextCodes text (i + 1) size);
  sourceStringChunks :: String -> Int -> Int -> Either String ([] SourceString);
  sourceStringChunks source i size =
    if i >= size then Right []
    else if stringCodeAt source i == 92
    then do {
      escaped <- sourceEscapeCode source (i + 1) size;
      case escaped of { (,) code next -> do {
      rest <- sourceStringChunks source next size;
      case code of {
        Nothing -> Right rest;
        Just value -> Right ((:)
          (if value >= 55296 && value <= 57343
           then CharString ((:) value [])
           else ScalarString (stringFromCode value)) rest)
      }
      } }
    }
    else let { end = unescapedEnd source i size; text = stringSlice source i (end - i) } in
      if stringAny (\c -> not (U.isPrint c)) text
      then Left "unescaped non-printable character in source string"
      else mapEither ((:) (ScalarString text)) (sourceStringChunks source end size);
  sourceEscapeCode :: String -> Int -> Int -> Either String ((,) (Maybe Int) Int);
  sourceEscapeCode source i size =
    if i >= size then Left "unterminated string escape"
    else let { c = stringCodeAt source i } in
      if sourceGapSpace c
      then let { end = cursorIndex (consumeWhile sourceGapSpace source size (Cursor i 1 1)) } in
        if end < size && stringCodeAt source end == 92
        then Right ((,) Nothing (end + 1))
        else Left "string gaps support ASCII whitespace and must end with backslash"
      else if U.isSpace c then Left "string gaps support ASCII whitespace only"
      else if isDigit c then sourceEscapedNumber 10 source i size
      else if c == 111 then sourceEscapedNumber 8 source (i + 1) size
      else if c == 120 then sourceEscapedNumber 16 source (i + 1) size
      else mapEither
        (\((,) text next) -> (,)
          (if stringLength text == 0 then Nothing else Just (stringCodeAt text 0)) next)
        (decodeEscape source i size);
  -- Pinned GHC accepts these gaps; Unicode separator gaps are not supported.
  sourceGapSpace :: Int -> Bool;
  sourceGapSpace c = c == 32 || (c >= 9 && c <= 13);
  -- Bound before multiplication: Int wraparound must never admit out-of-range escapes.
  sourceEscapedNumber :: Int -> String -> Int -> Int -> Either String ((,) (Maybe Int) Int);
  sourceEscapedNumber base source i size =
    if i >= size || digitValue (stringCodeAt source i) < 0 || digitValue (stringCodeAt source i) >= base
    then Left "empty numeric escape"
    else sourceEscapeDigits base source i size 0;
  sourceEscapeDigits :: Int -> String -> Int -> Int -> Int -> Either String ((,) (Maybe Int) Int);
  sourceEscapeDigits base source i size value =
    if i >= size then Right ((,) (Just value) i)
    else let { digit = digitValue (stringCodeAt source i) } in
      if digit < 0 || digit >= base then Right ((,) (Just value) i)
      else if value > ((1114111 - digit) / base) then Left "character escape out of range"
      else let { next = value * base + digit } in
        seq next (sourceEscapeDigits base source (i + 1) size next);
  stringValue :: String -> Either String String;
  stringValue source = decodeString source 1 (stringLength source - 1);
  decodeString :: String -> Int -> Int -> Either String String;
  decodeString source i size = mapEither concatStrings (decodeStringChunks source i size);
  decodeStringChunks :: String -> Int -> Int -> Either String ([] String);
  decodeStringChunks source i size =
    if (i >= size)
    then Right []
    else if (stringCodeAt source i == 92)
         then case decodeEscape source (i + 1) size of {
                Left e -> Left e;
                Right ((,) text next) ->
                  case decodeStringChunks source next size of {
                    Left e -> Left e;
                    Right rest -> Right (if (stringLength text == 0) then rest else (:) text rest)
                  }
              }
         else let {
                end = unescapedEnd source i size
              } in
              case decodeStringChunks source end size of {
                Left e -> Left e;
                Right rest -> Right ((:) (stringSlice source i (end - i)) rest)
              };
  unescapedEnd :: String -> Int -> Int -> Int;
  unescapedEnd source i size =
    if ((i >= size) || (stringCodeAt source i == 92)) then i else unescapedEnd source (i + 1) size;
  decodeEscape :: String -> Int -> Int -> Either String ((,) String Int);
  decodeEscape source i size =
    if (i >= size)
    then Left "unterminated string escape"
    else let {
           c = stringCodeAt source i
         } in
         if U.isSpace c
         then let {
                end = cursorIndex (consumeWhile U.isSpace source size (Cursor i 1 1))
              } in
              if ((end < size) && (stringCodeAt source end == 92))
              then Right ((,) "" (end + 1))
              else Left "invalid string gap"
         else if (c == 38)
              then Right ((,) "" (i + 1))
              else if (c == 94)
                   then if ((i + 1) < size)
                        then let {
                               control = stringCodeAt source (i + 1)
                             } in
                             if ((control >= 64) && (control <= 95))
                             then Right ((,) (stringFromCode (control - 64)) (i + 2))
                             else Left "invalid control escape"
                        else Left "incomplete control escape"
                   else if isDigit c
                        then escapedNumber 10 source i size
                        else if (c == 111)
                             then escapedNumber 8 source (i + 1) size
                             else if (c == 120)
                                  then escapedNumber 16 source (i + 1) size
                                  else case simpleEscape c of {
                                         Just result ->
                                           Right ((,) (stringFromCode result) (i + 1));
                                         Nothing -> namedEscape source i size asciiEscapes
                                       };
  simpleEscape :: Int -> Maybe Int;
  simpleEscape c =
    if (c == 97)
    then Just 7
    else if (c == 98)
         then Just 8
         else if (c == 102)
              then Just 12
              else if (c == 110)
                   then Just 10
                   else if (c == 114)
                        then Just 13
                        else if (c == 116)
                             then Just 9
                             else if (c == 118)
                                  then Just 11
                                  else if ((c == 92) || ((c == 34) || (c == 39)))
                                       then Just c
                                       else Nothing;
  escapedNumber :: Int -> String -> Int -> Int -> Either String ((,) String Int);
  escapedNumber base source i size =
    let {
      end =
        cursorIndex
          (consumeWhile (\c -> ((digitValue c >= 0) && (digitValue c < base))) source size
             (Cursor i 1 1))
    } in
    if (end == i)
    then Left "empty numeric escape"
    else case readBase base (stringSlice source i (end - i)) 0 0 of {
           Left e -> Left e;
           Right value ->
             if ((value > 1114111) || ((value >= 55296) && (value <= 57343)))
             then Left "invalid Unicode scalar escape"
             else Right ((,) (stringFromCode value) end)
         };
  namedEscape :: String -> Int -> Int -> [] ((,) String Int) -> Either String ((,) String Int);
  namedEscape source i size names =
    case names of {
      [] -> Left "unknown string escape";
      (:) ((,) name value) rest ->
        let {
          count = stringLength name
        } in
        if (((i + count) <= size) && eqString name (stringSlice source i count))
        then Right ((,) (stringFromCode value) (i + count))
        else namedEscape source i size rest
    };
  asciiEscapes :: [] ((,) String Int);
  asciiEscapes =
    (:) ((,) "NUL" 0)
      ((:) ((,) "SOH" 1)
         ((:) ((,) "STX" 2)
            ((:) ((,) "ETX" 3)
               ((:) ((,) "EOT" 4)
                  ((:) ((,) "ENQ" 5)
                     ((:) ((,) "ACK" 6)
                        ((:) ((,) "BEL" 7)
                           ((:) ((,) "DLE" 16)
                              ((:) ((,) "DC1" 17)
                                 ((:) ((,) "DC2" 18)
                                    ((:) ((,) "DC3" 19)
                                       ((:) ((,) "DC4" 20)
                                          ((:) ((,) "NAK" 21)
                                             ((:) ((,) "SYN" 22)
                                                ((:) ((,) "ETB" 23)
                                                   ((:) ((,) "CAN" 24)
                                                      ((:) ((,) "SUB" 26)
                                                         ((:) ((,) "ESC" 27)
                                                            ((:) ((,) "DEL" 127)
                                                               ((:) ((,) "BS" 8)
                                                                  ((:) ((,) "HT" 9)
                                                                     ((:) ((,) "LF" 10)
                                                                        ((:) ((,) "VT" 11)
                                                                           ((:) ((,) "FF" 12)
                                                                              ((:) ((,) "CR" 13)
                                                                                 ((:)
                                                                                    ((,) "SO" 14)
                                                                                    ((:)
                                                                                       ((,) "SI"
                                                                                          15)
                                                                                       ((:)
                                                                                          ((,) "EM"
                                                                                             25)
                                                                                          ((:)
                                                                                             ((,)
                                                                                                "FS"
                                                                                                28)
                                                                                             ((:)
                                                                                                ((,)
                                                                                                   "GS"
                                                                                                   29)
                                                                                                ((:)
                                                                                                   ((,)
                                                                                                      "RS"
                                                                                                      30)
                                                                                                   ((:)
                                                                                                      ((,)
                                                                                                         "US"
                                                                                                         31)
                                                                                                      ((:)
                                                                                                         ((,)
                                                                                                            "SP"
                                                                                                            32)
                                                                                                         [])))))))))))))))))))))))))))))))));
  -- Syntax selection is per file and precedes ordinary comment elision. The
  -- prologue is inspected without rewriting bytes or moving source positions.
  data SourcePrologue = SourcePrologue (Maybe SourceSyntax) ([] String) Cursor;
  sourceSyntaxName :: SourceSyntax -> String;
  sourceSyntaxName syntax =
    case syntax of {
      LegacyEmlfV1 -> "legacy-emlf-v1";
      SharedHaskellV1 -> "shared-haskell-v1";
      MetadataSyntax -> "internal-metadata-v2"
    };
  isSharedSyntax :: SourceSyntax -> Bool;
  isSharedSyntax syntax =
    case syntax of {
      SharedHaskellV1 -> True;
      LegacyEmlfV1 -> False;
      MetadataSyntax -> False
    };
  textStartsAt :: String -> Int -> String -> Bool;
  textStartsAt text index prefix =
    (((index + stringLength prefix) <= stringLength text) &&
     eqString prefix (stringSlice text index (stringLength prefix)));
  trimSourceSpace :: String -> String;
  trimSourceSpace text =
    let {
      begin = cursorIndex (consumeWhile U.isSpace text (stringLength text) (Cursor 0 1 1))
    } in
    let {
      end = trimSourceEnd text (stringLength text)
    } in
    stringSlice text begin (if (end < begin) then 0 else (end - begin));
  trimSourceEnd :: String -> Int -> Int;
  trimSourceEnd text end =
    if ((end > 0) && U.isSpace (stringCodeAt text (end - 1)))
    then trimSourceEnd text (end - 1)
    else end;
  sourceHasSuffix :: String -> String -> Bool;
  sourceHasSuffix text suffix =
    ((stringLength text >= stringLength suffix) &&
     eqString suffix
       (stringSlice text (stringLength text - stringLength suffix) (stringLength suffix)));
  sourceProfile :: String -> Either String SourceSyntax;
  sourceProfile name =
    if eqString name "legacy-emlf-v1"
    then Right LegacyEmlfV1
    else if eqString name "shared-haskell-v1"
         then Right SharedHaskellV1
         else Left ("unknown source syntax profile: " ++ name);
  sourceSyntax :: String -> String -> Either String SourceSyntax;
  sourceSyntax file source =
    do {
      prologue <- inspectPrologue file source;
      case prologue of {
        SourcePrologue declared _ _ ->
          do {
            syntax <-
              case declared of {
                Just syntax -> Right syntax;
                Nothing ->
                  if sourceHasSuffix file ".hs"
                  then Left (file ++ ": .hs source requires -- mlf:syntax shared-haskell-v1")
                  else Right LegacyEmlfV1
              };
            when (sourceHasSuffix file ".hs" && not (isSharedSyntax syntax))
              (Left (file ++ ": .hs sources require shared-haskell-v1"));
            validateSourceProfile syntax file source prologue;
            Right syntax
          }
      }
    };
  validateProfileSelection :: SourceSyntax -> String -> String -> Either String ();
  validateProfileSelection syntax file source =
    do {
      prologue <- inspectPrologue file source;
      case prologue of {
        SourcePrologue declared _ _ ->
          do {
            case declared of {
              Nothing -> Right ();
              Just actual ->
                unless (eqString (sourceSyntaxName syntax) (sourceSyntaxName actual))
                  (Left (file ++ ": requested syntax disagrees with source marker"))
            };
            validateSourceProfile syntax file source prologue
          }
      }
    };
  sharedExtensions :: [] String;
  sharedExtensions = (:) ("NoImplicitPrelude") ((:) ("NoMonomorphismRestriction") ((:) ("RankNTypes") ((:) ("KindSignatures") ((:) ("FlexibleContexts") ((:) ("FlexibleInstances") ((:) ("MultiParamTypeClasses") ((:) ("OverloadedStrings") ([]))))))));
  validateSourceProfile :: SourceSyntax -> String -> String -> SourcePrologue -> Either String ();
  validateSourceProfile syntax file source (SourcePrologue declared extensions end) =
    if not (isSharedSyntax syntax)
    then Right ()
    else do {
           unless
             ((length extensions == length sharedExtensions) &&
              all (\extension -> elem eqString extension extensions) sharedExtensions)
             (Left
                (file ++
                 ": shared-haskell-v1 requires exactly the approved LANGUAGE extension set"));
           validateSharedSource file source (stringLength source) (Cursor 0 1 1) (cursorIndex end)
         };
  inspectPrologue :: String -> String -> Either String SourcePrologue;
  inspectPrologue file source =
    prologueAt file source (stringLength source) (Cursor 0 1 1) Nothing [];
  prologueAt :: String ->
                String ->
                Int -> Cursor -> Maybe SourceSyntax -> [] String -> Either String SourcePrologue;
  -- Unmarked legacy files treat every block as an ordinary nested comment,
  -- including malformed pragma-shaped comments. Collect permissively here;
  -- only the selected shared profile validates the pragma contract.
  prologueAt file source size cursor declared extensions =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Right (SourcePrologue declared extensions cursor)
    else if U.isSpace (codeAt source size i)
         then prologueAt file source size (advance (codeAt source size i) cursor) declared
                extensions
         else if textStartsAt source i "--"
              then let {
                     end = skipLine source size cursor
                   } in
                   let {
                     text = trimSourceSpace (stringSlice source (i + 2) ((cursorIndex end - i) - 2))
                   } in
                   if textStartsAt text 0 "mlf:syntax"
                   then do {
                          when (isJust declared)
                            (Left (lexError file cursor "duplicate source syntax marker"));
                          syntax <-
                            sourceProfile
                              (trimSourceSpace (stringSlice text 10 (stringLength text - 10)));
                          prologueAt file source size end (Just syntax) extensions
                        }
                   else prologueAt file source size end declared extensions
              else if textStartsAt source i "{-#"
                   then do {
                          end <- skipComment file source size 1 (advance 45 (advance 123 cursor));
                          let {
                            raw = stringSlice source i (cursorIndex end - i)
                          };
                          let {
                            text =
                              if sourceHasSuffix raw "#-}"
                              then trimSourceSpace (stringSlice raw 3 (stringLength raw - 6))
                              else "<invalid pragma>"
                          };
                          let {
                            names =
                              if (textStartsAt text 0 "LANGUAGE " ||
                                  textStartsAt text 0 "LANGUAGE\n")
                              then case pragmaExtensions
                                          (stringSlice text 8 (stringLength text - 8)) of {
                                     Left _ -> (:) "<invalid LANGUAGE pragma>" [];
                                     Right names -> names
                                   }
                              else (:) text []
                          };
                          prologueAt file source size end declared (append extensions names)
                        }
                   else if textStartsAt source i "{-"
                        then do {
                               end <-
                                 skipComment file source size 1 (advance 45 (advance 123 cursor));
                               prologueAt file source size end declared extensions
                             }
                        else Right (SourcePrologue declared extensions cursor);
  pragmaEnd :: String -> String -> Int -> Cursor -> Either String Cursor;
  pragmaEnd file source size cursor =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Left (lexError file cursor "unterminated source pragma")
    else if textStartsAt source i "#-}"
         then Right (advance 125 (advance 45 (advance 35 cursor)))
         else pragmaEnd file source size (advance (codeAt source size i) cursor);
  pragmaExtensions :: String -> Either String ([] String);
  pragmaExtensions text = pragmaExtensionsAt text 0 0;
  pragmaExtensionsAt :: String -> Int -> Int -> Either String ([] String);
  pragmaExtensionsAt text begin i =
    if ((i >= stringLength text) || (stringCodeAt text i == 44))
    then let {
           name = trimSourceSpace (stringSlice text begin (i - begin))
         } in
         if eqString name ""
         then Left "empty LANGUAGE extension"
         else if (i >= stringLength text)
              then Right ((:) name [])
              else mapEither ((:) name) (pragmaExtensionsAt text (i + 1) (i + 1))
    else pragmaExtensionsAt text begin (i + 1);
  validateSharedSource :: String -> String -> Int -> Cursor -> Int -> Either String ();
  validateSharedSource file source size cursor prologueEnd =
    let {
      i = cursorIndex cursor
    } in
    if (i >= size)
    then Right ()
    else let {
           c = codeAt source size i
         } in
         if ((c == 32) || (c == 10))
         then validateSharedSource file source size (advance c cursor) prologueEnd
         else if U.isSpace c
              then Left
                     (lexError file cursor "shared source requires LF and spaces-only whitespace")
              else if textStartsAt source i "--"
                   then if (((i + 2) < size) &&
                            ((codeAt source size (i + 2) /= 32) &&
                             (codeAt source size (i + 2) /= 10)))
                        then Left
                               (lexError file cursor
                                  "shared line comments require a space after --")
                        else let {
                               end = skipLine source size cursor
                             } in
                             let {
                               text =
                                 trimSourceSpace
                                   (stringSlice source (i + 2) ((cursorIndex end - i) - 2))
                             } in
                             if ((i >= prologueEnd) && textStartsAt text 0 "mlf:syntax")
                             then Left
                                    (lexError file cursor
                                       "source syntax marker must occur in the prologue")
                             else validateSharedSource file source size end prologueEnd
                   else if textStartsAt source i "{-#"
                        then if (i >= prologueEnd)
                             then Left
                                    (lexError file cursor
                                       "shared pragmas must occur in the prologue")
                             else do {
                                    end <-
                                      pragmaEnd file source size
                                        (advance 35 (advance 45 (advance 123 cursor)));
                                    validateSharedSource file source size end prologueEnd
                                  }
                        else if textStartsAt source i "{-"
                             then do {
                                    end <-
                                      skipComment file source size 1
                                        (advance 45 (advance 123 cursor));
                                    validateSharedSource file source size end prologueEnd
                                  }
                             else if (c == 34)
                                  then do {
                                         end <- scanSourceQuoted file source size (advance c cursor);
                                         validateSharedString file source (i + 1)
                                           (cursorIndex end - 1);
                                         validateSharedSource file source size end prologueEnd
                                       }
                                  else validateSharedSource file source size (advance c cursor)
                                         prologueEnd;
  validateSharedString :: String -> String -> Int -> Int -> Either String ();
  validateSharedString file source i end =
    case sourceStringChunks source i end of {
      Left error -> Left (file ++ (": " ++ error));
      Right _ -> Right ()
    };
  sharedGapEnd :: String -> Int -> Int -> Either String Int;
  sharedGapEnd source i end =
    if (i >= end)
    then Left "unterminated shared string gap"
    else let {
           c = stringCodeAt source i
         } in
         if ((c == 32) || (c == 10))
         then sharedGapEnd source (i + 1) end
         else if (c == 92) then Right i else Left "shared string gaps allow only spaces and LF";
  sharedIdentifier :: String -> Bool;
  sharedIdentifier text =
    ((stringLength text > 0) &&
     (sharedIdentifierFirst (stringCodeAt text 0) &&
      not
        (stringAny (\c -> not (sharedIdentifierFirst c || (isDigit c || ((c == 95) || (c == 39)))))
           text)));
  sharedIdentifierFirst :: Int -> Bool;
  sharedIdentifierFirst c = (((c >= 65) && (c <= 90)) || ((c >= 97) && (c <= 122)));
  sharedValueOperators :: [] String;
  sharedValueOperators = (:) ("+") ((:) ("-") ((:) ("*") ((:) ("/") ((:) ("%") ((:) ("++") ((:) ("==") ((:) ("/=") ((:) ("<") ((:) ("<=") ((:) (">") ((:) (">=") ((:) ("&&") ((:) ("||") ((:) (">>=") ((:) (">>") ((:) ("<*>") ((:) ("<$") ((:) ("*>") ((:) ("<*") ([]))))))))))))))))))));
  sharedPunctuation :: [] String;
  sharedPunctuation = append ((:) "@" ((:) "~" ((:) "[" ((:) "]" ((:) ":" sharedValueOperators))))) ((:) ("::") ((:) ("->") ((:) ("<-") ((:) ("=>") ((:) ("=") ((:) ("|") ((:) (".") ((:) ("..") ((:) ("\\") ((:) ("(") ((:) (")") ((:) ("{") ((:) ("}") ((:) (";") ((:) (",") ((:) ("_") ([])))))))))))))))));
  sharedQualifiedOperator text =
    stringLength text > 1 && stringCodeAt text 0 == 46 && elem eqString (stringSlice text 1 (stringLength text - 1)) sharedValueOperators;
  validateSharedTokens :: String -> [] Token -> Either String ();
  validateSharedTokens file tokens =
    case tokens of {
      [] -> Right ();
      (:) token rest ->
        do {
          let {
            text = tokenText token
          };
          unless
            (sharedIdentifier text ||
             (elem eqString text sharedPunctuation || sharedQualifiedOperator text ||
              ((stringLength text > 0) &&
               (isDigit (stringCodeAt text 0) || (stringCodeAt text 0 == 34)))))
            (Left
               (file ++
                (":" ++
                 (showInt (tokenLine token) ++
                  (":" ++
                   (showInt (tokenColumn token) ++
                    (": token is outside shared-haskell-v1: " ++ text)))))));
          case rest of {
            (:) next following -> do {
              when (stringLength text > 0 && stringCodeAt text 0 >= 65 && stringCodeAt text 0 <= 90 && (eqString (tokenText next) "." || sharedQualifiedOperator (tokenText next))) (do {
                unless (tokenEndLine token == tokenLine next && tokenEndColumn token == tokenColumn next) (Left (file ++ ": qualified names must not contain whitespace before the dot"));
                when (eqString (tokenText next) ".") (case following of {
                  (:) final _ -> unless (tokenEndLine next == tokenLine final && tokenEndColumn next == tokenColumn final) (Left (file ++ ": qualified names must not contain whitespace after the dot"));
                  [] -> Left (file ++ ": incomplete qualified name")
                })
              });
              when
                ((stringLength text > 0) &&
                 (isDigit (stringCodeAt text 0) &&
                  ((tokenEndLine token == tokenLine next) &&
                   ((tokenEndColumn token == tokenColumn next) &&
                    (sharedIdentifier (tokenText next) || eqString (tokenText next) ".")))))
                (Left (file ++ ": malformed numeric token boundary"))
              };
            _ -> Right ()
          };
          validateSharedTokens file rest
        }
    };
  -- Cache consumers must bind this semantic identity as well as raw source bytes.
  frontendSemanticVersion :: String;
  frontendSemanticVersion = "mlf-frontend/shared-haskell-v1/7";
  builtinInterfaceVersion :: String;
  builtinInterfaceVersion = "mlf-primitive/shared-haskell-v1/9"
}
