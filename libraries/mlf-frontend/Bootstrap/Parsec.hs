-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Parsec where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Lexer;
  data ParseState = ParseState String (List Token) Token SourceSyntax;
  data PResult a = PSuccess a ParseState Bool | PFailure String ParseState Bool;
  data Parser a = Parser (ParseState -> PResult a);
  pRun :: forall a. Parser a -> ParseState -> PResult a;
  pRun (Parser action) state = action state;
  pPure :: forall a. a -> Parser a;
  pPure value = Parser (\state -> PSuccess value state False);
  pBind :: forall a b. Parser a -> (a -> Parser b) -> Parser b;
  pBind parser next =
    Parser
      (\state ->
         case pRun parser state of {
           PFailure message end consumed -> PFailure message end consumed;
           PSuccess value middle consumed ->
             case pRun (next value) middle of {
               PSuccess result end consumedNext -> PSuccess result end (consumed || consumedNext);
               PFailure message end consumedNext -> PFailure message end (consumed || consumedNext)
             }
         });
  pMap :: forall a b. (a -> b) -> Parser a -> Parser b;
  pMap f parser = pBind parser (\a -> pPure (f a));
  pThen :: forall a b. Parser a -> Parser b -> Parser b;
  pThen first second = pBind first (\ignored -> second);
  pBefore :: forall a b. Parser a -> Parser b -> Parser a;
  pBefore first second = pBind first (\a -> pThen second (pPure a));
  pFail :: forall a. String -> Parser a;
  pFail message = Parser (\state -> PFailure message state False);
  pChoice :: forall a. Parser a -> Parser a -> Parser a;
  pChoice first second =
    Parser
      (\state ->
         case pRun first state of {
           PFailure firstError firstState False ->
             case pRun second state of {
               PFailure secondError secondState False ->
                 if (stateOffset firstState > stateOffset secondState)
                 then PFailure firstError firstState False
                 else PFailure secondError secondState False;
               result -> result
             };
           result -> result
         });
  pChoices :: forall a. List (Parser a) -> Parser a;
  pChoices parsers =
    case parsers of {
      Nil -> pFail "no matching alternative";
      Cons parser Nil -> parser;
      Cons parser rest -> pChoice parser (pChoices rest)
    };
  pTry :: forall a. Parser a -> Parser a;
  pTry parser =
    Parser
      (\state ->
         case pRun parser state of {
           PFailure message end _ -> PFailure message end False;
           result -> result
         });
  pLook :: forall a. Parser a -> Parser a;
  pLook parser =
    Parser
      (\state ->
         case pRun parser state of {
           PSuccess value _ _ -> PSuccess value state False;
           result -> result
         });
  pNot :: forall a. Parser a -> Parser Unit;
  pNot parser =
    Parser
      (\state ->
         case pRun parser state of {
           PSuccess _ _ _ -> PFailure "unexpected token" state False;
           PFailure _ _ _ -> PSuccess Unit state False
         });
  pMany :: forall a. Parser a -> Parser (List a);
  pMany parser = pChoice (pBind parser (\a -> pMap (Cons a) (pMany parser))) (pPure Nil);
  pSome :: forall a. Parser a -> Parser (List a);
  pSome parser = pBind parser (\a -> pMap (Cons a) (pMany parser));
  pOptional :: forall a. Parser a -> Parser (Maybe a);
  pOptional parser = pChoice (pMap Just parser) (pPure Nothing);
  pOption :: forall a. a -> Parser a -> Parser a;
  pOption value parser = pChoice parser (pPure value);
  pSepBy :: forall a b. Parser a -> Parser b -> Parser (List a);
  pSepBy parser separator = pChoice (pSepBy1 parser separator) (pPure Nil);
  pSepBy1 :: forall a b. Parser a -> Parser b -> Parser (List a);
  pSepBy1 parser separator = pBind parser (\a -> pMap (Cons a) (pMany (pThen separator parser)));
  pSepEndBy :: forall a b. Parser a -> Parser b -> Parser (List a);
  pSepEndBy parser separator = pChoice (pSepEndBy1 parser separator) (pPure Nil);
  pSepEndBy1 :: forall a b. Parser a -> Parser b -> Parser (List a);
  pSepEndBy1 parser separator =
    pBind parser
      (\a ->
         pChoice (pThen separator (pMap (Cons a) (pSepEndBy parser separator)))
           (pPure (Cons a Nil)));
  pBetween :: forall a b c. Parser a -> Parser b -> Parser c -> Parser c;
  pBetween begin end parser = pThen begin (pBefore parser end);
  pParens :: forall a. Parser a -> Parser a;
  pParens parser = pBetween (pToken "(") (pToken ")") parser;
  pBraces :: forall a. Parser a -> Parser a;
  pBraces parser = pBetween (pToken "{") (pToken "}") parser;
  pState :: Parser ParseState;
  pState = Parser (\state -> PSuccess state state False);
  stateToken :: ParseState -> Token;
  stateToken (ParseState _ tokens finish _) =
    case tokens of {
      Nil -> finish;
      Cons t _ -> t
    };
  stateOffset :: ParseState -> Int;
  stateOffset state =
    let {
      token = stateToken state
    } in
    ((tokenLine token * 1000000) + tokenColumn token);
  stateError :: ParseState -> String -> String;
  stateError (ParseState file tokens finish _) message =
    let {
      token =
        case tokens of {
          Nil -> finish;
          Cons t _ -> t
        }
    } in
    (file ++
     (":" ++
      (showInt (tokenLine token) ++ (":" ++ (showInt (tokenColumn token) ++ (": " ++ message))))));
  pSatisfy :: (String -> Bool) -> String -> Parser String;
  pSatisfy predicate expected =
    Parser
      (\state ->
         case state of {
           ParseState file tokens finish syntax ->
             case tokens of {
               Nil -> PFailure ("unexpected end of input; expected " ++ expected) state False;
               Cons t rest ->
                 if predicate (tokenText t)
                 then PSuccess (tokenText t) (ParseState file rest finish syntax) True
                 else PFailure ("unexpected " ++ (tokenText t ++ ("; expected " ++ expected))) state
                        False
             }
         });
  pToken :: String -> Parser String;
  pToken spelling = pSatisfy (eqString spelling) spelling;
  pEof :: Parser Unit;
  pEof =
    Parser
      (\state ->
         case state of {
           ParseState _ tokens _ _ ->
             case tokens of {
               Nil -> PSuccess Unit state False;
               Cons t _ ->
                 PFailure ("unexpected " ++ (tokenText t ++ "; expected end of input")) state False
             }
         });
  pEither :: forall a. Either String a -> Parser a;
  pEither result =
    case result of {
      Left message -> pFail message;
      Right a -> pPure a
    };
  runParser :: forall a. Parser a -> String -> Scanned -> Either String a;
  runParser = runParserWithProfile LegacyEmlfV1;
  runParserWithProfile :: forall a. SourceSyntax ->
                                    Parser a -> String -> Scanned -> Either String a;
  runParserWithProfile syntax parser file (Scanned tokens finish) =
    case pRun (pBefore parser pEof) (ParseState file tokens finish syntax) of {
      PFailure message state _ -> Left (stateError state message);
      PSuccess a _ _ -> Right a
    };
  pChainl :: forall a. Parser a -> Parser (a -> a -> a) -> Parser a;
  pChainl parser operator = pBind parser (\a -> pChainlRest parser operator a);
  pChainlRest :: forall a. Parser a -> Parser (a -> a -> a) -> a -> Parser a;
  pChainlRest parser operator a =
    pChoice (pBind operator (\f -> pBind parser (\b -> pChainlRest parser operator (f a b))))
      (pPure a);
  pChainr :: forall a. Parser a -> Parser (a -> a -> a) -> Parser a;
  pChainr parser operator =
    pBind parser
      (\a -> pChoice (pBind operator (\f -> pMap (f a) (pChainr parser operator))) (pPure a));
  instance Functor Parser where {
    fmap function action = pBind action (\value -> pPure (function value))
  };
  instance Applicative Parser where {
    pure = pPure;
    (<*>) action argument =
      pBind action (\function -> pBind argument (\value -> pPure (function value)))
  };
  instance Monad Parser where {
    (>>=) = pBind
  };
  -- Literal symbols in the seed's grammar may consume an operator prefix.
  -- This preserves compact lambdas such as lambda-dot-minus without changing
  -- the reserved-operator boundary rules used by arithmetic and case arrows.
  pSymbolPrefix :: String -> Parser String;
  pSymbolPrefix symbol =
    Parser
      (\state ->
         case state of {
           ParseState file tokens finish syntax ->
             case tokens of {
               Cons (Token text line column endLine endColumn) rest ->
                 let {
                   size = stringLength symbol
                 } in
                 if ((stringLength text >= size) && eqString symbol (stringSlice text 0 size))
                 then let {
                        remaining =
                          if (stringLength text == size)
                          then rest
                          else Cons
                                 (Token (stringSlice text size (stringLength text - size)) line
                                    (column + size)
                                    endLine
                                    endColumn)
                                 rest
                      } in
                      PSuccess symbol (ParseState file remaining finish syntax) True
                 else PFailure ("expected " ++ symbol) state False;
               Nil -> PFailure ("expected " ++ symbol) state False
             }
         });
  pSourceSyntax :: Parser SourceSyntax;
  pSourceSyntax =
    Parser
      (\state ->
         case state of {
           ParseState _ _ _ syntax -> PSuccess syntax state False
         });
  pBySyntax :: forall a. Parser a -> Parser a -> Parser a;
  pBySyntax shared legacy =
    pBind pSourceSyntax
      (\syntax ->
         case syntax of {
           SharedHaskellV1 -> shared;
           LegacyEmlfV1 -> legacy;
           MetadataSyntax -> legacy
         })
}
