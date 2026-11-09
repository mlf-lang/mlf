-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Parser where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import Bootstrap.Lexer;
  import Bootstrap.Parsec;
  import qualified Bootstrap.Unicode as U;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.Kind as K;
  parseAll :: forall a. Parser a -> String -> String -> Either String a;
  parseAll parser file input =
    case scanTokens file input of {
      Left e -> Left e;
      Right scanned -> runParser parser file scanned
    };
  parseTerm :: String -> String -> Either String XTerm;
  parseTerm file input = parseAll wholeTerm file input;
  parseType :: String -> Either String XType;
  parseType input = parseAll typ "<xMLF type>" input;
  parseComputation :: String -> Either String XComputation;
  parseComputation input = parseAll computation "<xMLF computation>" input;
  wholeTerm :: Parser XTerm;
  wholeTerm =
    do {
      ds <- pMany (pBefore declaration (pToken ";"));
      body <- term;
      pPure (if L.null ds then body else XWithData ds body)
    };
  reservedWords :: [] String;
  reservedWords =
    (:) "data"
      ((:) "construct"
         ((:) "primitive"
            ((:) "case"
               ((:) "return"
                  ((:) "of"
                     ((:) "let"
                        ((:) "letrec"
                           ((:) "in"
                              ((:) "forall"
                                 ((:) "true"
                                    ((:) "false"
                                       ((:) "True"
                                          ((:) "False"
                                             ((:) "bot"
                                                ((:) "id"
                                                   ((:) "hyp"
                                                      ((:) "inner"
                                                         ((:) "outer"
                                                            ((:) "elim"
                                                               ((:) "intro"
                                                                  []))))))))))))))))))));
  identifier :: Parser String;
  identifier =
    pSatisfy
      (\s ->
         ((stringLength s > 0) &&
          (U.isAlpha (stringCodeAt s 0) && L.not (L.elem eqString s reservedWords))))
      "identifier";
  upperIdentifier :: Parser String;
  upperIdentifier = pChoice (pTry builtinConstructorName) ordinaryUpperIdentifier;
  builtinConstructorName :: Parser String;
  builtinConstructorName =
    pChoice (pThen (pToken "[") (pThen (pToken "]") (pPure "[]")))
      (pChoice (pToken ":")
        (pParens (do {
          commas <- pMany (pToken ",");
          if L.length commas <= 63
          then pPure ("(" ++ (L.foldr (++) "" commas ++ ")"))
          else pFail "tuple arity must be at most 64"
        })));
  ordinaryUpperIdentifier :: Parser String;
  ordinaryUpperIdentifier =
    pTry
      (do {
         s <- pLook identifier;
         if U.isUpper (stringCodeAt s 0) then identifier else pFail "expected constructor name"
       });
  decimal :: String -> Either String Int;
  decimal s =
    if ((stringLength s == 0) || L.not (allDigits s 0))
    then Left "expected decimal identity"
    else let {
           n = readInt s
         } in
         if (n > 9223372036854775807)
         then Left "identity is outside the supported integer range"
         else Right n;
  allDigits :: String -> Int -> Bool;
  allDigits s i =
    if (i >= stringLength s) then True else (isDigit (stringCodeAt s i) && allDigits s (i + 1));
  typeVariable :: Parser XTyVar;
  typeVariable =
    do {
      s <- identifier;
      let {
        count = stringLength s
      };
      if ((count >= 2) && ((stringCodeAt s 0 == 97) || (stringCodeAt s 0 == 122)))
      then do {
             n <- pEither (decimal (stringSlice s 1 (count - 1)));
             pPure (XTyVar (if (stringCodeAt s 0 == 122) then (0 - n) else n))
           }
      else pFail "expected a type identity such as a12 (or z12 for a fresh negative identity)"
    };
  termVariable :: Parser XName;
  termVariable =
    do {
      s <- identifier;
      let {
        count = stringLength s
      };
      let {
        separator = identitySeparator s (count - 1)
      };
      if ((separator > 0) && ((separator < (count - 1)) && (stringCodeAt s separator == 95)))
      then do {
             n <- pEither (decimal (stringSlice s (separator + 1) ((count - separator) - 1)));
             pPure (XName n (stringSlice s 0 separator))
           }
      else pFail "expected a term identity such as x_12"
    };
  identitySeparator :: String -> Int -> Int;
  identitySeparator s i =
    if ((i >= 0) && isDigit (stringCodeAt s i)) then identitySeparator s (i - 1) else i;
  typ :: Parser XType;
  typ = pChoice quantified (pChainr typeApplicationP (pMap (\_ -> XArrow) (pToken "->")));
  quantified :: Parser XType;
  quantified =
    do {
      pToken "forall";
      boundValueShared1 <-
        pChoice
          (pParens
             (do {
                a <- typeVariable;
                pToken ">=";
                b <- typ;
                pPure ((,) a b)
              }))
          (pMap (\a -> (,) a XBot) typeVariable);
      case boundValueShared1 of {
        (,) a bound ->
          do {
            pToken ".";
            pMap (XForall a bound) typ
          }
      }
    };
  typeApplicationP :: Parser XType;
  typeApplicationP =
    do {
      first <- typeAtom;
      rest <- pMany typeAtom;
      pPure (L.foldl T.apply first rest)
    };
  typeAtom :: Parser XType;
  typeAtom =
    pChoice (pTry (pMap (\c -> XCon c []) builtinConstructorName))
      (pChoice (pParens typ)
      (pChoice
         (do {
            pToken "bot";
            pOption XBot (pBetween (pToken "[") (pToken "]") (pMap T.bottomKind kindParser))
          })
         (pChoice (pMap (\c -> XCon c []) ordinaryUpperIdentifier) (pMap XVar typeVariable))));
  kindParser :: Parser Kind;
  kindParser =
    pChainr (pChoice (pMap (\_ -> Star) (pToken "*")) (pParens kindParser))
      (pMap (\_ -> KArrow) (pToken "->"));
  term :: Parser XTerm;
  term = pChoice letP (pChoice recP (pChoice typeAbsP (pChoice absP (pChoice caseP applicationP))));
  applicationP :: Parser XTerm;
  applicationP =
    do {
      first <- postfix;
      rest <- pMany postfix;
      pPure (L.foldl XApp first rest)
    };
  recP :: Parser XTerm;
  recP =
    do {
      pToken "letrec";
      bs <- pBraces (pSepEndBy1 binding (pToken ";"));
      pToken "in";
      pMap (XLetRec bs) term
    };
  binding :: Parser ((,,) XName XType XTerm);
  binding =
    do {
      n <- termVariable;
      pToken ":";
      t <- typ;
      pToken "=";
      a <- term;
      pPure ((,,) n t a)
    };
  letP :: Parser XTerm;
  letP =
    do {
      pToken "let";
      n <- termVariable;
      pToken "=";
      a <- term;
      pToken "in";
      pMap (XLet n a) term
    };
  typeAbsP :: Parser XTerm;
  typeAbsP =
    do {
      pToken "/\\";
      boundValueShared2 <-
        pParens
          (do {
             a <- typeVariable;
             pToken ">=";
             b <- typ;
             pPure ((,) a b)
           });
      case boundValueShared2 of {
        (,) a b ->
          do {
            pToken "->";
            pMap (XTypeAbs a b) term
          }
      }
    };
  absP :: Parser XTerm;
  absP =
    do {
      pToken "\\";
      boundValueShared3 <-
        pParens
          (do {
             n <- termVariable;
             pToken ":";
             t <- typ;
             pPure ((,) n t)
           });
      case boundValueShared3 of {
        (,) n t ->
          do {
            pToken "->";
            pMap (XAbs n t) term
          }
      }
    };
  caseP :: Parser XTerm;
  caseP =
    do {
      pToken "case";
      scrutinee <- term;
      pToken "return";
      result <- typ;
      pToken "of";
      pMap (XCase scrutinee result) (pBraces (pSepEndBy1 alternative (pToken ";")))
    };
  alternative :: Parser XAlternative;
  alternative =
    do {
      p <- patternP;
      pToken "->";
      pMap (XAlternative p) term
    };
  patternP :: Parser XPattern;
  patternP =
    pChoice
      (do {
         c <- upperIdentifier;
         pMap (XConstructorPattern c) (pMany patternField)
       })
      (pMap XDefaultPattern patternField);
  patternField :: Parser (Maybe XName);
  patternField = pChoice (pMap (\_ -> Nothing) (pToken "_")) (pMap Just termVariable);
  postfix :: Parser XTerm;
  postfix =
    do {
      a <- atom;
      ps <- pMany (pBetween (pToken "[") (pToken "]") computation);
      pPure (L.foldl XTypeApp a ps)
    };
  atom :: Parser XTerm;
  atom =
    pChoice (pParens term)
      (pChoice (pMap (\_ -> XBoolTerm True) (pToken "true"))
         (pChoice (pMap (\_ -> XBoolTerm False) (pToken "false"))
            (pChoice (pMap XDoubleTerm doubleLiteral)
               (pChoice (pMap XIntTerm integerLiteral)
                  (pChoice (pMap XStringTerm stringLiteral)
                     (pChoice primitiveTerm
                        (pChoice constructorTerm (pMap XVarTerm termVariable))))))));
  primitiveTerm :: Parser XTerm;
  primitiveTerm =
    do {
      pToken "primitive";
      n <- identifier;
      case P.lookupTargetPrimitive n of {
        Nothing -> pFail ("unknown primitive: " ++ n);
        Just p -> pMap (XPrimitive p) (pParens (pSepBy typ (pToken ",")))
      }
    };
  constructorTerm :: Parser XTerm;
  constructorTerm =
    do {
      pToken "construct";
      c <- upperIdentifier;
      pMap (XConstructor c) (pParens (pSepBy typ (pToken ",")))
    };
  integerLiteral :: Parser Int;
  integerLiteral =
    do {
      negative <-
        pOption False (pChoice (pMap (\_ -> True) (pToken "-")) (pMap (\_ -> False) (pToken "+")));
      s <-
        pSatisfy
          (\s ->
             ((stringLength s > 0) && (isDigit (stringCodeAt s 0) && L.not (decimalFloating s))))
          "integer";
      n <- pEither (naturalValue s);
      pPure (if negative then (0 - n) else n)
    };
  doubleLiteral :: Parser Double;
  doubleLiteral = pChoice specialDoubleLiteral finiteDoubleLiteral;
  -- Preserve the target printer's non-finite literals until the independent
  -- checker rejects them. Source-language literals still require finite values.
  specialDoubleLiteral :: Parser Double;
  specialDoubleLiteral =
    pTry
      (do {
         negative <-
           pOption False
             (pChoice (pMap (\_ -> True) (pToken "-")) (pMap (\_ -> False) (pToken "+")));
         bits <-
           pChoice (pMap (\_ -> 9221120237041090560) (pToken "NaN"))
             (pMap (\_ -> 9218868437227405312) (pToken "Infinity"));
         pPure (doubleFromBits (bits + (if negative then 9223372036854775808 else 0)))
       });
  finiteDoubleLiteral :: Parser Double;
  finiteDoubleLiteral =
    pTry
      (do {
         sign <- pOption "" (pChoice (pToken "-") (pToken "+"));
         s <-
           pSatisfy
             (\s -> ((stringLength s > 0) && (isDigit (stringCodeAt s 0) && decimalFloating s)))
             "Double";
         let {
           n = readDouble (sign ++ s)
         };
         if (remInt (quotInt (doubleToBits n) 4503599627370496) 2048 == 2047)
         then pFail "non-finite Double literal"
         else pPure n
       });
  decimalFloating s =
    (isFloating s &&
     L.not
       ((stringLength s >= 2) &&
        ((stringCodeAt s 0 == 48) && ((stringCodeAt s 1 == 120) || (stringCodeAt s 1 == 88)))));
  stringLiteral :: Parser String;
  stringLiteral =
    do {
      s <- pSatisfy (\s -> ((stringLength s > 0) && (stringCodeAt s 0 == 34))) "string";
      pEither (stringValue s)
    };
  computation :: Parser XComputation;
  computation = pChainl computationAtom (pMap (\_ -> XThen) (pToken ";"));
  computationAtom :: Parser XComputation;
  computationAtom =
    pChoice (pParens computation)
      (pChoice (pMap (\_ -> XRefl) (pToken "id"))
         (pChoice (pMap XBottom (pThen (pToken "bot") (pParens typ)))
            (pChoice (pMap XHyp (pThen (pToken "hyp") (pParens typeVariable)))
               (pChoice (pMap XInner (pThen (pToken "inner") (pParens computation)))
                  (pChoice outerP (pChoice (pMap (\_ -> XElim) (pToken "elim")) introP))))));
  outerP :: Parser XComputation;
  outerP =
    pThen (pToken "outer")
      (pParens
         (do {
            a <- typeVariable;
            pToken ",";
            pMap (XOuter a) computation
          }));
  introP :: Parser XComputation;
  introP =
    pThen (pToken "intro")
      (pParens
         (do {
            a <- typeVariable;
            pOption (XIntro a) (pThen (pToken ":") (pMap (XIntroKind a) kindParser))
          }));
  -- Data binders are schematic names, not target identities. Their reserved
  -- words intentionally differ from the computation grammar above.
  dataReserved :: [] String;
  dataReserved =
    (:) "data"
      ((:) "class"
         ((:) "instance"
            ((:) "where"
               ((:) "case"
                  ((:) "of"
                     ((:) "let"
                        ((:) "rec"
                           ((:) "in"
                              ((:) "if"
                                 ((:) "then"
                                    ((:) "else"
                                       ((:) "forall"
                                          ((:) "exists"
                                             ((:) "true"
                                                ((:) "false"
                                                   ((:) "bot"
                                                      ((:) "module"
                                                         ((:) "import" []))))))))))))))))));
  dataName :: Parser String;
  dataName =
    pSatisfy
      (\s ->
         ((stringLength s > 0) &&
          (U.isAlpha (stringCodeAt s 0) && L.not (L.elem eqString s dataReserved))))
      "data name";
  upperDataName :: Parser String;
  upperDataName =
    pChoice (pTry builtinConstructorName)
      (pTry
        (do {
           s <- pLook dataName;
           if U.isUpper (stringCodeAt s 0) then dataName else pFail "expected uppercase data name"
         }));
  lowerDataName :: Parser String;
  lowerDataName =
    pTry
      (do {
         s <- pLook dataName;
         if U.isLower (stringCodeAt s 0)
         then dataName
         else pFail "expected lowercase type parameter"
       });
  declaration :: Parser DataDecl;
  declaration =
    do {
      pToken "data";
      n <- upperDataName;
      ps <- pMany parameter;
      pToken "=";
      cs <- pSepBy1 constructorDeclaration (pToken "|");
      pPure
        (if L.all (\p -> K.eqKind (L.snd p) Star) ps
         then DataDecl n (L.map L.fst ps) cs
         else DataDeclK n ps cs)
    };
  constructorDeclaration :: Parser ConstructorDecl;
  constructorDeclaration =
    do {
      c <- upperDataName;
      pMap (ConstructorDecl c) (pMany fieldAtom)
    };
  parameter :: Parser ((,) String Kind);
  parameter =
    pChoice
      (pParens
         (do {
            n <- lowerDataName;
            pToken ":";
            pMap ((,) n) kindParser
          }))
      (pMap (\n -> (,) n Star) lowerDataName);
  fieldType :: Parser Field;
  fieldType =
    pChoice quantifiedField (pChainr fieldApplication (pMap (\_ -> Function) (pToken "->")));
  quantifiedField :: Parser Field;
  quantifiedField =
    do {
      pToken "forall";
      bs <- pSome parameter;
      pToken ".";
      b <- fieldType;
      pPure (L.foldr (\p body -> Quantified (L.fst p) (L.snd p) body) b bs)
    };
  fieldApplication :: Parser Field;
  fieldApplication =
    do {
      first <- fieldAtom;
      rest <- pMany fieldAtom;
      pPure (L.foldl applyField first rest)
    };
  applyField (Applied c args) a = Applied c (L.append args ((:) a []));
  applyField f a = Application f a;
  fieldAtom :: Parser Field;
  fieldAtom =
    pChoice (pTry (pMap (\c -> Applied c []) builtinConstructorName))
      (pChoice (pParens fieldType)
        (pChoice (pMap (\c -> Applied c []) upperDataName) (pMap Parameter lowerDataName)))
}
