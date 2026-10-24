-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Layout where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Lexer;
  data LayoutKind = LayoutTop | LayoutBlock | LayoutBindings;
  data LayoutMark = LetMark | IfMark;
  data Frame = Layout LayoutKind Int | Explicit String | Marker LayoutMark Int;
  data Pending = Open LayoutKind | AfterLet Int;
  layoutTokens :: Bool -> String -> String -> Either String Scanned;
  layoutTokens program file source =
    case scanTokens file source of {
      Left e -> Left e;
      Right (Scanned tokens finish) ->
        let {
          first =
            case tokens of {
              Nil -> finish;
              Cons t _ -> t
            }
        } in
        let {
          implicit =
            (program &&
             (not (eqString (tokenText first) "{") && not (eqString (tokenText first) "module")))
        } in
        let {
          frames =
            if implicit
            then Cons (Layout LayoutTop (lineIndent source (tokenLine first))) Nil
            else Nil
        } in
        let {
          arranged = arrange frames Nothing Nothing tokens finish
        } in
        Right (Scanned (if implicit then Cons (virtual "{" first) arranged else arranged) finish)
    };
  lineIndent :: String -> Int -> Int;
  lineIndent source line = indentAt source (stringLength source) line 0 1 1;
  indentAt :: String -> Int -> Int -> Int -> Int -> Int -> Int;
  indentAt source size target i line column =
    if (i >= size)
    then column
    else let {
           c = stringCodeAt source i
         } in
         if (line < target)
         then indentAt source size target (i + 1) (if (c == 10) then (line + 1) else line) 1
         else if ((c == 32) || (c == 13))
              then let {
                     nextColumn = (column + 1)
                   } in
                   seq nextColumn (indentAt source size target (i + 1) line nextColumn)
              else if (c == 9)
                   then let {
                          nextColumn = ((column + 8) - ((column - 1) % 8))
                        } in
                        seq nextColumn (indentAt source size target (i + 1) line nextColumn)
                   else column;
  virtual :: String -> Token -> Token;
  virtual text (Token _ line column _ _) = Token text line column line column;
  punctuation :: String -> Token -> List Token;
  punctuation text token = punctuationAt text token 0 (stringLength text);
  punctuationAt :: String -> Token -> Int -> Int -> List Token;
  punctuationAt text token i size =
    if (i >= size)
    then Nil
    else Cons (virtual (stringFromCode (stringCodeAt text i)) token)
           (punctuationAt text token (i + 1) size);
  arrange :: List Frame -> Maybe Pending -> Maybe Token -> List Token -> Token -> List Token;
  arrange frames pending previous tokens finish =
    case tokens of {
      Nil ->
        let {
          opening =
            case pending of {
              Just (Open _) -> "{}";
              _ -> ""
            }
        } in
        punctuation (opening ++ closes frames) finish;
      Cons t ts ->
        case pending of {
          Just (AfterLet line) ->
            if eqString (tokenText t) "rec"
            then Cons t (arrange frames (Just (AfterLet (tokenEndLine t))) (Just t) ts finish)
            else if eqString (tokenText t) "{"
                 then Cons t (nextToken t ts finish (pushToken t frames))
                 else if (tokenLine t > line)
                      then opened LayoutBindings frames previous t ts finish
                      else normal frames previous t ts finish;
          Just (Open kind) ->
            if eqString (tokenText t) "{"
            then Cons t (nextToken t ts finish (pushToken t frames))
            else opened kind frames previous t ts finish;
          Nothing -> normal frames previous t ts finish
        }
    };
  nextToken :: Token -> List Token -> Token -> List Frame -> List Token;
  -- A braced guard-if closes at }, so it must not intercept an enclosing
  -- ordinary if's then/else (which may also close an implicit do block).
  nextToken token rest finish stack =
    let {
      scoped =
        if eqString (tokenText token) "if"
        then case rest of {
               Cons next _ ->
                 if eqString (tokenText next) "{"
                 then case stack of {
                        Cons (Marker IfMark _) outer -> outer;
                        _ -> stack
                      }
                 else stack;
               _ -> stack
             }
        else stack
    } in
    arrange scoped (keyword token) (Just token) rest finish;
  previousText :: Maybe Token -> String;
  previousText previous =
    case previous of {
      Nothing -> "";
      Just t -> tokenText t
    };
  continuation :: String -> String -> Bool;
  continuation token previous =
    (elem eqString token continuationTokens || elem eqString previous continuationPrevious);
  continuationTokens :: List String;
  continuationTokens =
    Cons "]"
      (Cons ","
         (Cons "in"
            (Cons "then"
               (Cons "else"
                  (Cons "of" (Cons "where" (Cons "|" (Cons ")" (Cons "}" (Cons ";" Nil))))))))));
  continuationPrevious :: List String;
  continuationPrevious =
    Cons "::"
      (Cons ","
         (Cons "in"
            (Cons "then"
               (Cons "else"
                  (Cons "="
                     (Cons "->"
                        (Cons "<-"
                           (Cons ":"
                              (Cons "|"
                                 (Cons "+"
                                    (Cons "-"
                                       (Cons "*"
                                          (Cons "/"
                                             (Cons "%"
                                                (Cons "++"
                                                   (Cons "&&"
                                                      (Cons "||"
                                                         (Cons "=="
                                                            (Cons "/="
                                                               (Cons "<"
                                                                  (Cons "<="
                                                                     (Cons ">"
                                                                        (Cons ">="
                                                                           Nil)))))))))))))))))))))));
  opened :: LayoutKind -> List Frame -> Maybe Token -> Token -> List Token -> Token -> List Token;
  opened kind stack previous token rest finish =
    let {
      column = tokenColumn token
    } in
    if (not (isTop kind) && not (deeper column stack))
    then case offside column (continuation (tokenText token) (previousText previous))
                (previousText previous)
                stack of {
           Pair prefix remaining ->
             append (punctuation ("{}" ++ prefix) token)
               (Cons token (nextToken token rest finish (pushToken token remaining)))
         }
    else Cons (virtual "{" token)
           (Cons token
              (nextToken token rest finish (pushToken token (Cons (Layout kind column) stack))));
  isTop :: LayoutKind -> Bool;
  isTop kind =
    case kind of {
      LayoutTop -> True;
      _ -> False
    };
  normal :: List Frame -> Maybe Token -> Token -> List Token -> Token -> List Token;
  normal stack previous token rest finish =
    let {
      text = tokenText token
    } in
    let {
      closing =
        if eqString text "in"
        then closeMark LetMark False stack
        else if eqString text "then"
             then closeMark IfMark True stack
             else if eqString text "else"
                  then closeMark IfMark False stack
                  else if eqString text ")"
                       then closeExplicit "(" stack
                       else if eqString text "]"
                            then closeExplicit "[" stack
                            else if eqString text ","
                                 then closeCollection stack
                                 else if eqString text "}"
                                      then closeExplicit "{" stack
                                      else if eqString text ";"
                                           then Pair "" (dropInline stack)
                                           else Pair "" stack
    } in
    case closing of {
      Pair ending closed ->
        let {
          newLine =
            case previous of {
              Nothing -> False;
              Just old -> ((tokenEndLine old < tokenLine token) && not (eqString (tokenText old) ";" || eqString (tokenText old) "{"))
            }
        } in
        let {
          closingToken = (eqString text ")" || (eqString text "]" || eqString text "}"))
        } in
        let {
          result =
            if (newLine && not closingToken)
            then offside (tokenColumn token) (continuation text (previousText previous))
                   (previousText previous)
                   closed
            else Pair "" closed
        } in
        case result of {
          Pair separator scoped ->
            append (punctuation (ending ++ separator) token)
              (Cons token
                 (nextToken token rest finish
                    (if closingToken then scoped else pushToken token scoped)))
        }
    };
  pushToken :: Token -> List Frame -> List Frame;
  pushToken token frames =
    let {
      text = tokenText token
    } in
    if (eqString text "(" || (eqString text "[" || eqString text "{"))
    then Cons (Explicit text) frames
    else if eqString text "let"
         then Cons (Marker LetMark (tokenColumn token)) frames
         else if eqString text "if"
              then Cons (Marker IfMark (tokenColumn token)) frames
              else frames;
  keyword :: Token -> Maybe Pending;
  keyword token =
    let {
      text = tokenText token
    } in
    if (eqString text "do" || (eqString text "of" || eqString text "where"))
    then Just (Open LayoutBlock)
    else if eqString text "let" then Just (AfterLet (tokenEndLine token)) else Nothing;
  deeper :: Int -> List Frame -> Bool;
  deeper column frames =
    case frames of {
      Cons (Layout _ indent) _ -> (column > indent);
      Cons (Marker _ _) rest -> deeper column rest;
      _ -> True
    };
  offside :: Int -> Bool -> String -> List Frame -> Pair String (List Frame);
  offside column continued previous frames =
    case frames of {
      Cons (Layout _ indent) rest ->
        if (column < indent)
        then case offside column continued "}" rest of {
               Pair prefix remaining -> Pair ("}" ++ prefix) remaining
             }
        else if ((column == indent) &&
                 (not continued && not (eqString previous ";" || eqString previous "{")))
             then Pair ";" frames
             else Pair "" frames;
      Cons (Marker _ indent) rest ->
        if ((column <= indent) && not continued)
        then offside column continued previous rest
        else Pair "" frames;
      _ -> Pair "" frames
    };
  dropInline :: List Frame -> List Frame;
  dropInline frames =
    case frames of {
      Cons (Marker _ _) rest -> dropInline rest;
      _ -> frames
    };
  eqMark :: LayoutMark -> LayoutMark -> Bool;
  eqMark a b =
    case a of {
      LetMark ->
        case b of {
          LetMark -> True;
          _ -> False
        };
      IfMark ->
        case b of {
          IfMark -> True;
          _ -> False
        }
    };
  closeMark :: LayoutMark -> Bool -> List Frame -> Pair String (List Frame);
  closeMark wanted keep frames =
    case searchMark wanted keep frames of {
      Nothing -> Pair "" frames;
      Just result -> result
    };
  searchMark :: LayoutMark -> Bool -> List Frame -> Maybe (Pair String (List Frame));
  searchMark wanted keep frames =
    case frames of {
      Cons (Marker mark column) rest ->
        if eqMark mark wanted
        then Just (Pair "" (if keep then frames else rest))
        else searchMark wanted keep rest;
      Cons (Layout _ _) rest ->
        case searchMark wanted keep rest of {
          Nothing -> Nothing;
          Just (Pair prefix remaining) -> Just (Pair ("}" ++ prefix) remaining)
        };
      _ -> Nothing
    };
  closeExplicit :: String -> List Frame -> Pair String (List Frame);
  closeExplicit wanted frames =
    case searchExplicit wanted frames of {
      Nothing -> Pair "" frames;
      Just result -> result
    };
  searchExplicit :: String -> List Frame -> Maybe (Pair String (List Frame));
  searchExplicit wanted frames =
    case frames of {
      Cons (Explicit delimiter) rest ->
        if eqString delimiter wanted then Just (Pair "" rest) else Nothing;
      Cons (Layout _ _) rest ->
        case searchExplicit wanted rest of {
          Nothing -> Nothing;
          Just (Pair prefix remaining) -> Just (Pair ("}" ++ prefix) remaining)
        };
      Cons (Marker _ _) rest -> searchExplicit wanted rest;
      _ -> Nothing
    };
  closeCollection :: List Frame -> Pair String (List Frame);
  closeCollection frames =
    case searchCollection frames of {
      Nothing -> Pair "" frames;
      Just result -> result
    };
  searchCollection :: List Frame -> Maybe (Pair String (List Frame));
  searchCollection frames =
    case frames of {
      Cons (Explicit delimiter) _ ->
        if (eqString delimiter "(" || eqString delimiter "[")
        then Just (Pair "" frames)
        else Nothing;
      Cons (Layout _ _) rest ->
        case searchCollection rest of {
          Nothing -> Nothing;
          Just (Pair prefix remaining) -> Just (Pair ("}" ++ prefix) remaining)
        };
      Cons (Marker _ _) rest -> searchCollection rest;
      _ -> Nothing
    };
  closes :: List Frame -> String;
  closes frames =
    case frames of {
      Nil -> "";
      Cons (Layout _ _) rest -> ("}" ++ closes rest);
      Cons _ rest -> closes rest
    };
  -- The shared dialect deliberately accepts canonical layout only. Local lets
  -- and inline blocks are explicit; all remaining layout blocks must begin on
  -- the next line. These checks reject cases needing Haskell's parse-error
  -- layout closure rather than interpreting them with the legacy heuristics.
  layoutTokensWithProfile :: SourceSyntax -> Bool -> String -> String -> Either String Scanned;
  layoutTokensWithProfile syntax program file source =
    if not (isSharedSyntax syntax)
    then layoutTokens program file source
    else do {
           boundValueShared1 <- scanTokens file source;
           case boundValueShared1 of {
             Scanned tokens finish ->
               do {
                 validateSharedTokens file tokens;
                 validateSharedLayout file tokens;
                 arranged <- layoutTokens program file source;
                 case arranged of {
                   Scanned ordered _ -> validateSharedArranged file Nil Nothing ordered
                 };
                 Right arranged
               }
           }
         };
  validateSharedLayout :: String -> List Token -> Either String Unit;
  validateSharedLayout file tokens =
    case tokens of {
      Nil -> Right Unit;
      Cons token rest ->
        do {
          let {
            text = tokenText token
          };
          case rest of {
            Cons next _ ->
              if eqString text "let"
              then unless (eqString (tokenText next) "{")
                     (Left (file ++ ": shared let groups require explicit braces"))
              else if elem eqString text (Cons "do" (Cons "of" (Cons "where" Nil)))
                   then unless
                          (eqString (tokenText next) "{" || (tokenLine next > tokenEndLine token))
                          (Left (file ++ ": inline shared blocks require explicit braces"))
                   else Right Unit;
            _ -> Right Unit
          };
          validateSharedLayout file rest
        }
    };
  virtualToken :: Token -> Bool;
  virtualToken token =
    ((tokenLine token == tokenEndLine token) && (tokenColumn token == tokenEndColumn token));
  sharedOperator :: String -> Bool;
  sharedOperator text =
    elem eqString text
      (Cons "+"
         (Cons "-"
            (Cons "*"
               (Cons "/"
                  (Cons "%"
                     (Cons "++"
                        (Cons "=="
                           (Cons "/="
                              (Cons "<"
                                 (Cons "<="
                                    (Cons ">"
                                       (Cons ">="
                                          (Cons "&&"
                                             (Cons "||" (Cons "::" (Cons "|" Nil))))))))))))))));
  validateSharedArranged :: String -> List Frame -> Maybe Token -> List Token -> Either String Unit;
  validateSharedArranged file frames previous tokens =
    case tokens of {
      Nil -> Right Unit;
      Cons token rest ->
        do {
          let {
            text = tokenText token
          };
          let {
            virtual = virtualToken token
          };
          let {
            newLine =
              case previous of {
                Nothing -> False;
                Just old -> ((tokenEndLine old < tokenLine token) && not (eqString (tokenText old) ";" || eqString (tokenText old) "{"))
              }
          };
          case frames of {
            Cons (Layout _ indent) _ ->
              when
                (not virtual && (newLine && (tokenColumn token <= indent)))
                (Left
                   (file ++
                    ": shared continuation lines must be indented beyond their declaration or statement"));
            _ -> Right Unit
          };
          when (virtual && (eqString text "}" && closedByExplicitBrace token rest))
            (Left
               (file ++
                ": an explicit brace cannot close an implicit shared layout block; use explicit braces for the nested block"));
          let {
            nextFrames =
              if eqString text "{"
              then Cons (if virtual then Layout LayoutBlock (tokenColumn token) else Explicit "{")
                     frames
              else if eqString text "("
                   then Cons (Explicit "(") frames
                   else if (eqString text "}" || eqString text ")")
                        then case frames of {
                               Nil -> Nil;
                               Cons _ outer -> outer
                             }
                        else frames
          };
          validateSharedArranged file nextFrames (Just token) rest
        }
    };
  closedByExplicitBrace :: Token -> List Token -> Bool;
  closedByExplicitBrace closing tokens =
    case tokens of {
      Cons next rest ->
        if ((tokenLine next /= tokenLine closing) || (tokenColumn next /= tokenColumn closing))
        then False
        else if virtualToken next
             then closedByExplicitBrace closing rest
             else eqString (tokenText next) "}";
      Nil -> False
    }
}
