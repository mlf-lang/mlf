-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Parser where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Lexer;
  import Bootstrap.Parsec;
  import Bootstrap.Layout;
  import qualified Bootstrap.Unicode as U;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Desugar as Desugar;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Std as SharedSyntax;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Map as M;
  data Top = DataTop DataDecl | ClassTop SClassDecl | InstanceTop SInstanceDecl | ValueTop Value;
  data SharedStatement =
    SharedBind SPattern SExpr SourceSpan |
    SharedThen SExpr |
    SharedLet ([] ((,,) String (Maybe SAnnotation) SExpr));
  data ListQualifier =
    ListGenerator SPattern SExpr |
    ListGuard SExpr |
    ListLet ([] ((,,) String (Maybe SAnnotation) SExpr));
  data Value =
    Signature String SAnnotation | Equation String ([] SPattern) (Maybe SAnnotation) SExpr;
  reservedWords :: [] String;
  reservedWords =
    (:) "data"
      ((:) "class"
         ((:) "instance"
            ((:) "where"
               ((:) "case"
                  ((:) "of"
                     ((:) "do"
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
                                                      ((:) "True"
                                                         ((:) "False"
                                                            ((:) "bot"
                                                               ((:) "module"
                                                                  ((:) "import"
                                                                     [])))))))))))))))))))));
  -- Resolve the fixed vocabulary once for each syntax profile. A token now
  -- needs one membership test, rather than composing three list searches.
  legacyReservedSet = Set.fromList compareString reservedWords;
  sharedReservedSet = Set.fromList compareString
    (append (filter (\word -> not (elem eqString word sharedOrdinaryLegacyWords)) reservedWords)
      sharedReservedWords);
  sharedOperatorSet = Set.fromList compareString sharedValueOperators;
  identifier :: Parser String;
  identifier = namedIdentifier U.isAlpha "identifier";
  upperIdentifier :: Parser String;
  upperIdentifier = namedIdentifier U.isUpper "constructor name";
  lowerIdentifier :: Parser String;
  lowerIdentifier = namedIdentifier U.isLower "variable name";
  namedIdentifier :: (Int -> Bool) -> String -> Parser String;
  namedIdentifier predicate expected =
    pTry
      (do {
         name <- pSatisfy (\n -> ((stringLength n > 0) && predicate (stringCodeAt n 0))) expected;
         shared <- pBySyntax (pPure True) (pPure False);
         if Set.member compareString name (if shared then sharedReservedSet else legacyReservedSet)
         then pFail ("unexpected reserved word " ++ name)
         else if (shared && not (sharedIdentifier name))
              then pFail "shared source identifiers must be ASCII"
              else pPure name
       });
  upperReference :: Parser String;
  upperReference =
    qualified (pChoices ((:) upperIdentifier ((:) (pToken "True") ((:) (pToken "False") []))));
  locatedReference :: Parser String -> Parser SExpr;
  locatedReference parser = pBind (pWithSpan parser) referenceAt;
  referenceAt located = do {
    syntax <- pSourceSyntax;
    case located of {
      (,) location name -> case syntax of {
        MetadataSyntax -> pPure (SVar name);
        _ -> pPure (SCallSite (referenceLeaf name) location (SVar name))
      }
    }
  };
  -- Select the token while the cursor is current. Delayed coordinate reads
  -- then retain its token alone, even when they outlive the parser.
  referenceToken :: Parser Token;
  referenceToken = Parser (\state -> case state of {
    ParseState _ ((:) token _) _ _ _ _ _ -> PSuccess token state False;
    ParseState _ [] finish _ _ _ _ -> PSuccess finish state False
  });
  -- The final identifier consumes one whole token; a successful qualifier
  -- consumes an identifier followed by a dot. Capture those token endpoints
  -- as the grammar runs, without measuring both remaining token lists.
  locatedLowerReference = do {
    original <- pState;
    first <- referenceToken;
    result <- pTry (qualifiedWith (\prefixes ((,) token suffix) ->
      (,) token (qualifiedName prefixes suffix)) (do {
        final <- referenceToken;
        suffix <- lowerIdentifier;
        pPure ((,) final suffix)
      }));
    case original of { ParseState file _ _ _ sourceModule sourcePackage _ ->
      let { final = fst result } in
      referenceAt ((,) (SourceSpan sourcePackage sourceModule file (tokenLine first) (tokenColumn first)
        (tokenEndLine final) (tokenEndColumn final)) (snd result))
    }
  };
  lowerReference :: Parser String;
  lowerReference = pTry (qualified lowerIdentifier);
  qualified :: Parser String -> Parser String;
  qualified = qualifiedWith qualifiedName;
  qualifiedName prefixes name = foldr (\prefix suffix -> prefix ++ ("." ++ suffix)) name prefixes;
  qualifiedWith build final = do {
    prefixes <- pMany (pTry (pBefore upperIdentifier (pToken ".")));
    item <- final;
    pPure (build prefixes item)
  };
  moduleName :: Parser String;
  moduleName = pMap (intercalate ".") (pSepBy1 upperIdentifier (pToken "."));
  parseExpr :: String -> String -> Either String SExpr;
  parseExpr file source = parseLayout False expr file source;
  parseAnnotation :: String -> Either String SAnnotation;
  parseAnnotation source =
    case scanTokens "<type>" source of {
      Left e -> Left e;
      Right tokens -> runParser annotation "<type>" tokens
    };
  parseLayout :: forall a. Bool -> Parser a -> String -> String -> Either String a;
  parseLayout program parser file source =
    case layoutTokensWithScanner scanSourceTokens program file source of {
      Left e -> Left e;
      Right tokens -> runParser parser file tokens
    };
  parseModule :: String -> String -> Either String SourceModule;
  parseModule = parseModuleInPackage "main";
  parseModuleInPackage :: String -> String -> String -> Either String SourceModule;
  parseModuleInPackage sourcePackage file source =
    do {
      syntax <- sourceSyntax file source;
      parseModuleSelectedInPackage sourcePackage syntax file source
    };
  -- Artifact metadata uses legacy quantification/annotation grammar but wired
  -- canonical type names. This profile is never selected by a source marker.
  parseMetadataModule :: String -> String -> Either String SourceModule;
  parseMetadataModule file source = do {
    tokens <- layoutTokensWithProfile MetadataSyntax True file source;
    runParserWithProfile MetadataSyntax (sourceModule file) file tokens
  };
  sourceOrMetadata :: forall a. Parser a -> Parser a -> Parser a;
  sourceOrMetadata source metadata = do {
    syntax <- pSourceSyntax;
    case syntax of { MetadataSyntax -> metadata; _ -> source }
  };
  metadataAtom :: forall a. (String -> a) -> Parser a -> Parser a;
  metadataAtom construct fallback = do {
    syntax <- pSourceSyntax;
    case syntax of {
      MetadataSyntax -> pChoice (pTry (pMap construct metadataBuiltinName)) fallback;
      _ -> fallback
    }
  };
  metadataBuiltinName :: Parser String;
  metadataBuiltinName =
    pChoice (pThen (pToken "[") (pThen (pToken "]") (pPure "[]")))
      (pParens (do {
        commas <- pMany (pToken ",");
        if null commas then pPure "()" else sourceTupleName (1 + length commas)
      }));
  parseModuleWithProfile :: SourceSyntax -> String -> String -> Either String SourceModule;
  parseModuleWithProfile = parseModuleWithProfileInPackage "main";
  parseModuleWithProfileInPackage :: String -> SourceSyntax -> String -> String -> Either String SourceModule;
  parseModuleWithProfileInPackage sourcePackage syntax file source =
    do {
      validateProfileSelection syntax file source;
      parseModuleSelectedInPackage sourcePackage syntax file source
    };
  -- Both callers have validated this immutable source against its profile:
  -- discovery also checks the filename and marker, explicit selection checks
  -- agreement with the marker. Do not repeat the complete source scan here.
  parseModuleSelectedInPackage sourcePackage syntax file source =
    do {
      tokens <- layoutTokensWithProfile syntax True file source;
      result <- runParserWithProfileInPackage sourcePackage syntax
        (sourceModuleWith (equationExpressionWith True) file) file tokens;
      when (eqString (moduleIdentity result) "MLF.Primitive")
        (Left "MLF.Primitive is a reserved native builtin module");
      if isSharedSyntax syntax
      then do {
             when (eqString (moduleIdentity result) "Prelude") (Left "Prelude is reserved for the legacy guest builtin; shared source uses MLF.Primitive");
             -- groupValues has checked names and shared annotations have empty
             -- existential binder lists, so every dependency group is bindable.
             validateSharedModuleSyntax result;
             Right result
           }
      else Right result
    };
  parseProgram :: String -> String -> Either String SProgram;
  parseProgram file source =
    case parseModule file source of {
      Left e -> Left e;
      Right m ->
        case m of {
          SourceModule _ name _ imports _ _ _ _ _ _ ->
            case name of {
              Just _ ->
                Left
                  "use parseModule and module-aware compilation for module declarations or imports";
              Nothing ->
                if null imports
                then standaloneProgram m
                else Left
                       "use parseModule and module-aware compilation for module declarations or imports"
            }
        }
    };
  moduleIdentity :: SourceModule -> String;
  moduleIdentity (SourceModule _ name _ _ _ _ _ _ _ _) =
    case name of {
      Nothing -> "Main";
      Just n -> n
    };
  standaloneProgram :: SourceModule -> Either String SProgram;
  standaloneProgram (SourceModule _ _ _ _ datatypes classes instances values body _) =
    let {
      entry =
        case body of {
          Just e -> Right e;
          Nothing ->
            if any (\((,,) n _ _) -> eqString n "main") values
            then Right (SVar "main")
            else Left "a declaration-only program needs a main binding"
        }
    } in
    case entry of {
      Left e -> Left e;
      Right e ->
        case Surface.bindValues values e of {
          Left error -> Left error;
          Right expression ->
            case Surface.closeSourceInstances values instances of {
              Left error -> Left error;
              Right closed ->
                Right
                  (if (null classes && null closed)
                   then SProgram datatypes expression
                   else SClassProgram datatypes classes closed expression)
            }
        }
    };
  sourceModule :: String -> Parser SourceModule;
  sourceModule = sourceModuleWith equationExpression;
  sourceModuleWith rhs file =
    do {
      syntax <- pSourceSyntax;
      header <-
        pOptional
          (pThen (pToken "module")
             (do {
                name <- moduleName;
                exports <- pOptional (pParens (pSepEndBy (exportItem True) (pToken ",")));
                pToken "where";
                pPure ((,) name exports)
              }));
      pSetSourceModule (case header of { Just ((,) name _) -> name; Nothing -> "Main" });
      pBraces
        (do {
           imports <- pMany (pBefore importDeclaration separator);
           declarations <- pMany (pBefore (topDeclarationWith rhs) separator);
           values <-
             pEither
               (groupValues
                  (concatMap
                     (\d ->
                        case d of {
                          ValueTop value -> (:) value [];
                          _ -> []
                        })
                     declarations));
           body <- pOptional expr;
           let {
             hasHeader =
               case header of {
                 Just _ -> True;
                 Nothing -> False
               }
           };
           let {
             hasBody =
               case body of {
                 Just _ -> True;
                 Nothing -> False
               }
           };
           if (hasHeader && hasBody)
           then pFail "named modules contain declarations only; define main for the entry point"
           else pPure
                  (SourceModule file
                     (case header of {
                        Nothing -> Nothing;
                        Just ((,) name _) -> Just name
                      })
                     (case header of {
                        Nothing -> Nothing;
                        Just ((,) _ exports) -> exports
                      })
                     imports
                     (concatMap
                        (\d ->
                           case d of {
                             DataTop a -> (:) a [];
                             _ -> []
                           })
                        declarations)
                     (concatMap
                        (\d ->
                           case d of {
                             ClassTop a -> (:) a [];
                             _ -> []
                           })
                        declarations)
                     (concatMap
                        (\d ->
                           case d of {
                             InstanceTop a -> (:) a [];
                             _ -> []
                           })
                        declarations)
                     values
                     body
                     syntax)
         })
    };
  separator :: Parser String;
  separator = pChoice (pToken ";") (pLook (pToken "}"));
  exportItem :: Bool -> Parser Export;
  exportItem exporting =
    pChoices
      ((:)
         (if exporting
          then pMap ExportModule (pThen (pToken "module") moduleName)
          else pFail "module export")
         ((:) (pMap ExportValue (if exporting then valueReference else bindingName))
            ((:)
               (do {
                  name <- if exporting then upperReference else upperIdentifier;
                  members <-
                    pOption Abstract
                      (pParens
                         (pChoice (pMap (\_ -> AllMembers) (pToken ".."))
                            (pMap Members (pSepEndBy exportMember (pToken ",")))));
                  pPure (ExportType name members)
                })
               [])));
  exportMember :: Parser String;
  exportMember = pChoices ((:) identifier ((:) (pParens operatorName) ((:) (pToken "True") ((:) (pToken "False") []))));
  importDeclaration :: Parser Import;
  importDeclaration =
    do {
      pToken "import";
      onlyQualified <- pOption False (pMap (\_ -> True) (pToken "qualified"));
      name <- moduleName;
      alias <- pOptional (pThen (pToken "as") moduleName);
      selection <-
        pOption Everything
          (pChoice (pMap Hiding (pThen (pToken "hiding") importItems)) (pMap Only importItems));
      pPure (Import name onlyQualified alias selection)
    };
  importItems :: Parser ([] Export);
  importItems = pParens (pSepEndBy (exportItem False) (pToken ","));
  topDeclaration :: Parser Top;
  topDeclaration = topDeclarationWith equationExpression;
  topDeclarationWith rhs =
    pChoices
      ((:) (pMap DataTop dataDeclaration)
         ((:) (pMap ClassTop classDeclaration)
            ((:) (pMap InstanceTop instanceDeclaration)
               ((:) (pMap ValueTop (valueDeclarationWith rhs)) []))));
  valueDeclaration :: Parser Value;
  valueDeclaration = valueDeclarationWith equationExpression;
  valueDeclarationWith rhs =
    pChoice
      (pTry
         (do {
            name <- bindingName;
            annotationSymbol;
            ty <- annotation;
            pLook (pChoice (pToken ";") (pToken "}"));
            pPure (Signature name ty)
          }))
      (equationWith rhs);
  equation :: Parser Value;
  equation = equationWith equationExpression;
  equationWith rhs =
    do {
      boundValueShared1 <- bindingHead;
      case boundValueShared1 of {
        (,,) name args ty ->
          do {
            body <-
              pChoice (pThen (pToken "=") rhs)
                (pBySyntax (pFail "guarded equations are outside shared-haskell-v1; use ordinary if/case") (pBind (pSome (guardBranch "=")) (\rows -> pEither (guarded rows))));
            pPure (Equation name args ty body)
          }
      }
    };
  bindingHead :: Parser ((,,) String ([] SPattern) (Maybe SAnnotation));
  bindingHead =
    do {
      result <-
        pTry
          (do {
             name <- bindingName;
             args <- pMany patternAtom;
             ty <- pBySyntax (pPure Nothing) (pOptional (pThen annotationSymbol annotation));
             pLook (pChoice (pToken "=") (pToken "|"));
             pPure ((,,) name args ty)
           });
      case result of {
        (,,) _ args _ ->
          let {
            names = concatMap Surface.patternVariables args
          } in
          if (length names == Set.size (Set.fromList compareString names))
          then pPure result
          else pFail "duplicate function parameter"
      }
    };
  groupValues :: [] Value -> Either String ([] ((,,) String (Maybe SAnnotation) SExpr));
  groupValues declarations =
    case collectValues Nothing declarations of {
      Left e -> Left e;
      Right values ->
        let {
          names = map (\((,,) n _ _) -> n) values
        } in
        if (length names == Set.size (Set.fromList compareString names))
        then Right values
        else Left "function equations must be contiguous; duplicate value declaration"
    };
  collectValues :: Maybe ((,) String SAnnotation) ->
                   [] Value -> Either String ([] ((,,) String (Maybe SAnnotation) SExpr));
  collectValues signature values =
    case values of {
      [] ->
        case signature of {
          Nothing -> Right [];
          Just ((,) n _) ->
            Left ("unexpected end of declarations; signature without a definition: " ++ n)
        };
      (:) (Signature n ty) rest ->
        case signature of {
          Just _ -> Left ("duplicate signature for " ++ n);
          Nothing -> collectValues (Just ((,) n ty)) rest
        };
      (:) (Equation name args inline body) rest ->
        let {
          ty =
            case signature of {
              Nothing -> Right inline;
              Just ((,) signedName signedType) ->
                if not (eqString signedName name)
                then Left ("expected a definition of " ++ signedName)
                else case inline of {
                       Just _ -> Left ("duplicate signature for " ++ name);
                       Nothing -> Right (Just signedType)
                     }
            }
        } in
        case ty of {
          Left e -> Left e;
          Right resultType ->
            case span
                   (\v ->
                      case v of {
                        Equation n _ _ _ -> eqString n name;
                        _ -> False
                      })
                   rest of {
              (,) more remaining ->
                let {
                  rows =
                    (:) ((,) args body)
                      (map
                         (\v ->
                            case v of {
                              Equation _ ps _ rhs -> (,) ps rhs;
                              _ -> (,) [] body
                            })
                         more)
                } in
                if any
                     (\v ->
                        case v of {
                          Equation _ _ (Just _) _ -> True;
                          _ -> False
                        })
                     more
                then Left ("duplicate signature for " ++ name)
                else if (not (null more) && null args)
                     then Left "multiple equations require function parameters"
                     else if any (\((,) ps _) -> (length ps /= length args)) rows
                          then Left "function equations have different arities"
                          else case collectValues Nothing remaining of {
                                 Left e -> Left e;
                                 Right suffix ->
                                   Right
                                     ((:) ((,,) name resultType (Surface.function rows)) suffix)
                               }
            }
        }
    };
  valueBlock :: Parser ([] ((,,) String (Maybe SAnnotation) SExpr));
  valueBlock =
    pBind
      (pBySyntax (pBraces (pSepEndBy1 valueDeclaration (pToken ";")))
         (pChoice (pBraces (pSepEndBy1 valueDeclaration (pToken ";")))
            (pMap (\v -> (:) v []) equation)))
      (\values -> pEither (groupValues values));
  bindLocal :: Bool -> [] ((,,) String (Maybe SAnnotation) SExpr) -> SExpr -> Parser SExpr;
  bindLocal recursive values body =
    if recursive
    then pMap (\ds -> SLetRec ds body) (pEither (Surface.recursiveValues values))
    else pPure (foldr (\((,,) n a e) b -> SLet n (annotateMaybe e a) b) body values);
  -- Declaration and instance-method signatures must not become expression coercions.
  annotateMaybe :: SExpr -> Maybe SAnnotation -> SExpr;
  annotateMaybe expression ty =
    case ty of {
      Nothing -> expression;
      Just a -> SSignature expression a
    };
  parameter :: Parser ((,) String Kind);
  parameter =
    pChoice
      (pParens
         (do {
            n <- lowerIdentifier;
            annotationSymbol;
            k <- kindParser;
            pPure ((,) n k)
          }))
      (pMap (\n -> (,) n Star) lowerIdentifier);
  kindParser :: Parser Kind;
  kindParser =
    pChainr (pChoice (pMap (\_ -> Star) (pToken "*")) (pParens kindParser))
      (pMap (\_ -> KArrow) (pToken "->"));
  predicate :: Parser SPredicate;
  predicate =
    do {
      n <- upperReference;
      args <- if (eqString (referenceLeaf n) "HasCallStack" || eqString n "MLFHasCallStack")
              then pMany typeAtom else pSome typeAtom;
      pPure (SPredicate n args)
    };
  context :: Parser ([] SPredicate);
  context =
    pTry
      (pBefore
         (pChoice (pParens (pSepBy1 predicate (pToken ","))) (pMap (\p -> (:) p []) predicate))
         (pToken "=>"));
  classDeclaration :: Parser SClassDecl;
  classDeclaration =
    do {
      pToken "class";
      supers <- pOption [] context;
      name <- upperIdentifier;
      params <- pSome parameter;
      pToken "where";
      methods <-
        pBraces
          (pSepEndBy
             (do {
                n <- bindingName;
                annotationSymbol;
                t <- typ;
                pPure ((,) n t)
              })
             (pToken ";"));
      pPure (SClassDecl name params supers methods)
    };
  instanceDeclaration :: Parser SInstanceDecl;
  instanceDeclaration =
    do {
      pToken "instance";
      vars <- pOption [] (pThen (pToken "forall") (pBefore (pSome parameter) (pToken ".")));
      givens <- pOption [] context;
      name <- upperReference;
      headType <- pSome typeAtom;
      pToken "where";
      declarations <- pBraces (pSepEndBy valueDeclaration (pToken ";"));
      pBySyntax
        (if any
              (\declaration ->
                 case declaration of {
                   Signature _ _ -> True;
                   _ -> False
                 })
              declarations
         then pFail "instance signatures are outside shared-haskell-v1"
         else pPure ())
        (pPure ());
      methods <- pEither (instanceMethods declarations);
      pPure (SInstanceDecl vars givens name headType methods)
    };
  instanceMethods :: [] Value -> Either String ([] ((,) String SExpr));
  instanceMethods declarations =
    if all
         (\v ->
            case v of {
              Equation _ [] _ _ -> True;
              _ -> False
            })
         declarations
    then Right
           (map
              (\v ->
                 case v of {
                   Equation n _ a e -> (,) n (annotateMaybe e a);
                   _ -> (,) "" (SVar "")
                 })
              declarations)
    else case groupValues declarations of {
           Left e -> Left e;
           Right values -> Right (map (\((,,) n a e) -> (,) n (annotateMaybe e a)) values)
         };
  -- A complete equation made of first-order syntax can be read from its
  -- token spine in one pass. Delimiters remain for the enclosing grammar.
  -- Retrying at the equation boundary limits a near miss to one extra scan.
  equationExpression = equationExpressionWith False;
  -- The general constructor alternatives compare token offsets while
  -- choosing a diagnostic. Only source scanned by the module reader has
  -- fully defined token positions. Manual token streams retain that demand.
  equationExpressionWith scanned = Parser (\state -> case state of {
    ParseState file tokens end SharedHaskellV1 owner packageName previous -> let {
      appendAtom prior atom = case prior of { Nothing -> atom; Just f -> SApp f atom };
      -- Several nested applications can end at consecutive closing tokens.
      -- Collapse these frames directly, retaining the first following token.
      close known groups body lastSlot remaining = case groups of {
        [] -> Nothing;
        (:) parent outer -> let { next = appendAtom parent body } in seq next (case remaining of {
          (:) (Token name _ _ _ _) more -> if eqString name ")" then close known outer next remaining more
            else scan known outer (Just next) lastSlot remaining;
          [] -> finishAt outer (Just next) lastSlot []
        })
      };
      scan known groups current endpoint remaining = case remaining of {
        [] -> finishAt groups current endpoint remaining;
        (:) (Token name sl sc el ec) more -> let {
          size = stringLength name;
          code = if size > 0 then stringCodeAt name 0 else (-1);
          put names atom = let { next = appendAtom current atom } in seq next (scan names groups (Just next) remaining more)
        } in if size == 1 && code == 40 then scan known ((:) current groups) Nothing remaining more
          else if size == 1 && code == 41 then case current of {
            Just body -> close known groups body remaining more; Nothing -> Nothing
          } else if size == 1 && (code == 59 || code == 125) then finishAt groups current endpoint remaining
          else if (code >= 97 && code <= 122) || (scanned && code >= 65 && code <= 90) then let {
            lower = code >= 97;
            -- Variables retain each occurrence's call site. Constructors
            -- have no call-site wrapper in the shared expression grammar.
            reference names leaf = put names (if lower
              then SCallSite name (SourceSpan packageName owner file sl sc el ec) leaf else leaf)
          } in case M.lookup compareString name known of {
            Just leaf -> reference known leaf;
            Nothing -> if sharedIdentifier name && not (Set.member compareString name sharedReservedSet) then let {
              leaf = if lower then SVar name else SConstructor (sharedSourceName name);
              next = if M.size known < 64 then M.insert compareString name leaf known else known
            } in reference next leaf else Nothing
          }
          else if isDigit code then case naturalValue name of {
            Right number -> put known (SIntLit number); Left _ -> Nothing
          } else Nothing
      };
      finishAt groups current endpoint remaining = case (,) groups current of {
        (,) [] (Just body) -> Just (PSuccess body
          (ParseState file remaining end SharedHaskellV1 owner packageName endpoint) True);
        _ -> Nothing
      }
    } in case scan M.empty [] Nothing previous tokens of { Just result -> result; Nothing -> pRun expr state };
    _ -> pRun expr state
  });
  expr :: Parser SExpr;
  expr = do {
    start <- pState;
    e <- pBySyntax sharedApplyExpr disjunction;
    pOption e (do {
      annotationSymbol;
      -- Only a signature can retain this range. The required type consumes
      -- at least one whole token and supplies the expression's final token.
      located <- pSpanStartingAt start annotation;
      syntax <- pSourceSyntax;
      case located of { (,) location a -> let { expression = SAnn e a } in case syntax of {
        MetadataSyntax -> pPure expression;
        _ -> if annotationHasManagedStack a then pPure (SCallSite "an expression type signature" location expression)
             else pPure expression
      } }
    })
  };
  annotationHasManagedStack :: SAnnotation -> Bool;
  annotationHasManagedStack (SAnnotation _ ty) = typeHasManagedStack ty;
  typeHasManagedStack :: SType -> Bool;
  typeHasManagedStack ty = case ty of {
    SForall _ _ _ body -> typeHasManagedStack body;
    SQualified predicates body ->
      any (\(SPredicate name _) -> eqString (referenceLeaf name) "HasCallStack" || eqString name "MLFHasCallStack") predicates || typeHasManagedStack body;
    _ -> False
  };
  annotationSymbol :: Parser String;
  annotationSymbol = pBySyntax (pToken "::") (pChoice (pToken "::") (pToken ":"));
  -- Legacy single-colon annotations remain a fallback for syntax that cannot
  -- form a complete canonical pattern/expression (for example forall/arrow).
  -- Ambiguous value or pattern annotations use ::; constructor case is not a
  -- discriminator between a type and a cons tail.
  legacyAnnotation :: Parser SAnnotation;
  legacyAnnotation =
    pTry
      (do {
         a <- annotation;
         case a of {
           SAnnotation variables ty ->
             if (null (freeTypeNames variables ty) || (explicitType ty || not (null variables)))
             then pPure ()
             else pFail "list tail"
         };
         end <- pState;
         if elem eqString (tokenText (stateToken end))
              ((:) "|"
                 ((:) "="
                    ((:) ""
                       ((:) ")"
                          ((:) "]"
                             ((:) "}"
                                ((:) ","
                                   ((:) ";"
                                      ((:) "in"
                                         ((:) "then"
                                            ((:) "else" ((:) "of" ((:) "where" [])))))))))))))
         then pPure ()
         else pFail "end of annotation";
         pPure a
       });
  freeTypeNames :: [] String -> SType -> [] String;
  freeTypeNames bound ty =
    case ty of {
      STVar n -> if elem eqString n bound then [] else (:) n [];
      SArrow a b -> append (freeTypeNames bound a) (freeTypeNames bound b);
      STypeApp a b -> append (freeTypeNames bound a) (freeTypeNames bound b);
      SCon _ args -> concatMap (freeTypeNames bound) args;
      SForall _ n lower body ->
        append (freeTypeNames bound lower) (freeTypeNames ((:) n bound) body);
      SQualified predicates body ->
        append (concatMap (\(SPredicate _ args) -> concatMap (freeTypeNames bound) args) predicates)
          (freeTypeNames bound body);
      _ -> []
    };
  explicitType :: SType -> Bool;
  explicitType ty =
    case ty of {
      SArrow _ _ -> True;
      SForall _ _ _ _ -> True;
      SQualified _ _ -> True;
      SBottom -> True;
      SBottomKind _ -> True;
      SCon _ args -> any explicitType args;
      STypeApp a b -> (explicitType a || explicitType b);
      _ -> False
    };
  disjunction :: Parser SExpr;
  disjunction =
    pChainr conjunction (pMap (\_ a b -> conditional a (SBoolLit True) b) (pToken "||"));
  conjunction :: Parser SExpr;
  conjunction =
    pChainr comparison (pMap (\_ a b -> conditional a b (SBoolLit False)) (pToken "&&"));
  comparison :: Parser SExpr;
  comparison =
    do {
      a <- concatenation;
      pOption a
        (do {
           operator <- comparisonOperator;
           b <- concatenation;
           next <- pOptional (pLook comparisonOperator);
           case next of {
             Nothing -> pPure ();
             Just _ -> pFail "ambiguous use of a non-associative comparison operator"
           };
           pPure (operator a b)
         })
    };
  comparisonOperator :: Parser (SExpr -> SExpr -> SExpr);
  comparisonOperator =
    pChoices
      ((:) (pMap (\_ -> namedOperator "==") (pToken "=="))
         ((:) (pMap (\_ -> namedOperator "/=") (pToken "/="))
            ((:) (pMap (\_ -> primitive2 PLtInt) (pToken "<"))
               ((:) (pMap (\_ a b -> notValue (primitive2 PLtInt b a)) (pToken "<="))
                  ((:) (pMap (\_ a b -> primitive2 PLtInt b a) (pToken ">"))
                     ((:) (pMap (\_ a b -> notValue (primitive2 PLtInt a b)) (pToken ">="))
                        []))))));
  concatenation :: Parser SExpr;
  concatenation = do {
    first <- addition;
    pChoice
      (pThen (pToken "++") (pMap (primitive2 PConcatString first) concatenation))
      (pBySyntax (pPure first)
        (pChoice
          (pTry (do {
            pToken ":";
            rest <- concatenation;
            legacyConsBoundary;
            pPure (consExpression first rest)
          }))
          (pPure first)))
  };
  -- A successful prefix of a type is not a complete expression: in
  -- x : Int -> Int, for example, the arrow forces annotation fallback. The
  -- lower-precedence expression operators are legitimate cons boundaries.
  legacyConsBoundary :: Parser ();
  legacyConsBoundary = do {
    state <- pState;
    if elem eqString (tokenText (stateToken state))
      ((:) "" ((:) ")" ((:) "]" ((:) "}" ((:) "," ((:) ";"
        ((:) "in" ((:) "then" ((:) "else" ((:) "of" ((:) "where"
        ((:) "|" ((:) "=" ((:) "::" ((:) "==" ((:) "/="
        ((:) "<" ((:) "<=" ((:) ">" ((:) ">=" ((:) "&&" ((:) "||" []))))))))))))))))))))))
    then pPure () else pFail "end of cons expression"
  };
  consExpression :: SExpr -> SExpr -> SExpr;
  consExpression a b = SApp (SApp (SConstructor ":") a) b;
  addition :: Parser SExpr;
  addition =
    pChainl multiplication
      (pChoice (pMap (\_ -> primitive2 PAddInt) (pToken "+"))
         (pMap (\_ -> primitive2 PSubInt) (pToken "-")));
  multiplication :: Parser SExpr;
  multiplication =
    pChainl prefixed
      (pChoices
         ((:) (pMap (\_ -> primitive2 PMulInt) (pToken "*"))
            ((:) (pMap (\_ -> primitive2 PQuotInt) (pToken "/"))
               ((:) (pMap (\_ -> primitive2 PRemInt) (pToken "%")) []))));
  prefixed :: Parser SExpr;
  prefixed = pBySyntax operand legacyPrefixed;
  legacyPrefixed :: Parser SExpr;
  legacyPrefixed =
    do {
      sign <-
        pOptional
          (pChoice (pMap (\_ -> negateValue) (pToken "-"))
             (pMap (\_ -> positiveValue) (pToken "+")));
      value <- operand;
      pPure
        (case sign of {
           Nothing -> value;
           Just f -> f value
         })
    };
  operand :: Parser SExpr;
  operand =
    pChoices ((:) letExpr ((:) lambda ((:) caseExpr ((:) ifExpr ((:) application [])))));
  application :: Parser SExpr;
  application = Parser (\state -> case pRun atom state of {
    PFailure message end used -> PFailure message end used;
    PSuccess first next used -> applicationArguments first next used
  });
  -- A closing delimiter ends the argument list. For other tokens, preserve
  -- the consumed flag and error state of the atom parser.
  closesExpression text = eqString text ")" || eqString text "," || eqString text ";" ||
    eqString text "]" || eqString text "}";
  applicationArguments :: SExpr -> ParseState -> Bool -> PResult SExpr;
  applicationArguments function state used = case state of {
    ParseState _ [] _ _ _ _ _ -> PSuccess function state used;
    ParseState _ ((:) token _) _ _ _ _ _ -> let { text = tokenText token } in
      if closesExpression text
      then PSuccess function state used else case pRun atom state of {
        PFailure message end True -> PFailure message end True;
        PFailure _ _ False -> PSuccess function state used;
        PSuccess argument next more -> applicationArguments (SApp function argument) next (used || more)
      }
  };
  primitive2 :: Primitive -> SExpr -> SExpr -> SExpr;
  primitive2 primitive a b = SApp (SApp (SPrimitive primitive) a) b;
  conditional :: SExpr -> SExpr -> SExpr -> SExpr;
  conditional condition yes no = SApp (primitive2 PIfThenElse condition yes) no;
  notValue :: SExpr -> SExpr;
  notValue a = conditional a (SBoolLit False) (SBoolLit True);
  negateValue :: SExpr -> SExpr;
  negateValue a =
    case a of {
      SIntLit n -> SIntLit (0 - n);
      SDoubleLit n -> SDoubleLit (mulDouble (SharedSyntax.negateDouble 1.0) n);
      _ -> primitive2 PSubInt (SIntLit 0) a
    };
  positiveValue :: SExpr -> SExpr;
  positiveValue a =
    case a of {
      SIntLit _ -> a;
      SDoubleLit _ -> a;
      _ -> primitive2 PAddInt (SIntLit 0) a
    };
  ifExpr :: Parser SExpr;
  ifExpr =
    do {
      pToken "if";
      pChoice
        (pBySyntax (pFail "shared guard-if syntax is not supported")
           (pBind (pBraces (pSepEndBy (guardBranch "->") (pToken ";")))
              (\rows -> pEither (guarded rows))))
        (do {
           condition <- expr;
           pToken "then";
           yes <- expr;
           pToken "else";
           no <- expr;
           pPure (conditional condition yes no)
         })
    };
  -- Guards are total Boolean decisions within one RHS, not pattern-matrix rows.
  -- Recognize otherwise only immediately before the delimiter: existing names
  -- and applications such as otherwise x remain ordinary Boolean expressions.
  guardBranch :: String -> Parser ((,) (Maybe SExpr) SExpr);
  guardBranch delimiter =
    do {
      pToken "|";
      condition <-
        pChoice
          (pMap (\_ -> Nothing) (pTry (pBefore (pToken "otherwise") (pLook (pToken delimiter)))))
          (pMap Just expr);
      pSatisfy (eqString delimiter) (delimiter ++ " after guard condition");
      body <- expr;
      pPure ((,) condition body)
    };
  guarded :: [] ((,) (Maybe SExpr) SExpr) -> Either String SExpr;
  guarded rows =
    case rows of {
      [] -> Left "guard block requires a final otherwise branch";
      (:) ((,) Nothing body) [] -> Right body;
      (:) ((,) Nothing _) _ -> Left "otherwise must be the final guard branch";
      (:) ((,) (Just condition) body) rest ->
        mapEither (conditional condition body) (guarded rest)
    };
  letExpr :: Parser SExpr;
  letExpr =
    do {
      pToken "let";
      recursive <- pBySyntax (pPure True) (pOption False (pMap (\_ -> True) (pToken "rec")));
      values <- valueBlock;
      pToken "in";
      body <- expr;
      pBySyntax (pEither (Surface.bindValues values body)) (bindLocal recursive values body)
    };
  lambda :: Parser SExpr;
  lambda =
    do {
      pBySyntax (pToken "\\") (pChoice (pSymbolPrefix "\\") (pSymbolPrefix "λ"));
      args <- pSome patternAtom;
      pBySyntax (pToken "->") (pChoice (pSymbolPrefix "->") (pSymbolPrefix "."));
      body <- expr;
      let {
        names = concatMap Surface.patternVariables args
      };
      if (length names == Set.size (Set.fromList compareString names))
      then pPure (Surface.function ((:) ((,) args body) []))
      else pFail "duplicate pattern variable"
    };
  caseExpr :: Parser SExpr;
  caseExpr =
    do {
      pToken "case";
      scrutinee <- expr;
      pToken "of";
      alternatives <- pBraces (pSepEndBy1 alternative (pToken ";"));
      pPure (SCase scrutinee alternatives)
    };
  alternative :: Parser SAlternative;
  alternative =
    do {
      pattern <- patternP;
      pToken "->";
      value <- expr;
      pPure (SAlternative pattern value)
    };
  patternP :: Parser SPattern;
  patternP = sourceOrMetadata
    (pChainr patternApplication
      (pMap (\_ a b -> constructorPattern ":" ((:) a ((:) b []))) (pToken ":")))
    legacyPattern;
  legacyPattern :: Parser SPattern;
  legacyPattern =
    pChainr patternApplication
      (pMap (\_ a b -> constructorPattern "Cons" ((:) a ((:) b []))) (pToken ":"));
  patternApplication :: Parser SPattern;
  patternApplication =
    pChoice
      (pTry
         (do {
            name <- sourceOrMetadata
              (pChoice upperReference (pTry canonicalPatternName)) upperReference;
            fields <- pMany patternAtom;
            sourceOrMetadata (pPure (constructorPattern (sharedSourceName name) fields)) (pPure (constructorPattern name fields))
          }))
      patternAtom;
  canonicalPatternName :: Parser String;
  canonicalPatternName = pChoice (pTry metadataBuiltinName)
    (pParens (pThen (pToken ":") (pPure ":")));
  constructorPattern :: String -> [] SPattern -> SPattern;
  constructorPattern name fields =
    if (eqString name "True" && null fields)
    then SBoolPattern True
    else if (eqString name "False" && null fields)
         then SBoolPattern False
         else if all
                   (\p ->
                      case p of {
                        SDefaultPattern _ -> True;
                        _ -> False
                      })
                   fields
              then SConstructorPattern name
                     (map
                        (\p ->
                           case p of {
                             SDefaultPattern n -> n;
                             _ -> Nothing
                           })
                        fields)
              else SNestedPattern name fields;
  patternAtom :: Parser SPattern;
  patternAtom = sourceOrMetadata sharedPatternAtom legacyPatternAtom;
  sharedPatternAtom :: Parser SPattern;
  sharedPatternAtom = Parser (\state -> let {
    ordinary = pRun generalSharedPatternAtom state
  } in case state of {
    ParseState file tokens@((:) (Token name _ _ _ _) rest) end SharedHaskellV1 owner pkg _ -> let {
      accept variable = PSuccess (SDefaultPattern variable)
        (ParseState file rest end SharedHaskellV1 owner pkg tokens) True;
      first = if stringLength name == 0 then 0 else stringCodeAt name 0;
      asPattern = case rest of {
        (:) (Token next _ _ _ _) _ -> eqString next "@";
        [] -> False
      }
    } in if eqString name "_" then accept Nothing
      else if first >= 97 && first <= 122 && sharedIdentifier name &&
              not (Set.member compareString name sharedReservedSet || asPattern)
      then accept (Just name) else ordinary;
    _ -> ordinary
  });
  generalSharedPatternAtom =
    pChoice (pTry (do {
      name <- lowerIdentifier;
      pToken "@";
      pMap (SAsPattern name) sharedPatternAtom
    }))
    (pChoice (pThen (pToken "~") (pMap SLazyPattern sharedPatternAtom)) sharedBasicPatternAtom);
  sharedBasicPatternAtom :: Parser SPattern;
  sharedBasicPatternAtom =
    pChoices
      ((:)
         (pParens
            (pChoice
              (pTry (pBefore
                (pChoice (pMap SIntPattern (pThen (pToken "-") (pMap (\n -> (0 - n)) naturalLiteral)))
                  (pBind (collectionItems ")" patternP)
                    (sourceTupleValue (SConstructorPattern "()" []) constructorPattern)))
                (pLook (pToken ")"))))
              (pBySyntax (pFail "typed patterns are outside shared-haskell-v1") annotatedVariable)))
         ((:)
            (pMap (foldr (\a b -> constructorPattern ":" ((:) a ((:) b [])))
                         (constructorPattern "[]" []))
               (pThen (pToken "[") (pBefore (collectionItems "]" patternP) (pToken "]"))))
            ((:) (pBySyntax (pMap (\b -> SConstructorPattern (sharedSourceName (if b then "True" else "False")) []) booleanLiteral) (pMap SBoolPattern booleanLiteral))
               ((:) (pMap (\text -> SOverloadedStringPattern text "$MLF.Primitive.==" "$MLF.Primitive.fromString") sourceStringLiteral)
               ((:) (pBySyntax (pMap SIntPattern naturalLiteral) (pMap SIntPattern (pTry integerLiteral)))
                  ((:) (pMap (\n -> SConstructorPattern (sharedSourceName n) []) upperReference)
                     ((:) (pMap SDefaultPattern patternField) [])))))));
  legacyPatternAtom :: Parser SPattern;
  legacyPatternAtom =
    pChoices
      ((:)
         (pParens
            (pChoice annotatedVariable
               (pBind (collectionItems ")" patternP)
                  (tupleValue (SConstructorPattern "()" []) constructorPattern))))
         ((:)
            (pMap
               (foldr (\a b -> constructorPattern "Cons" ((:) a ((:) b [])))
                  (constructorPattern "Nil" []))
               (pThen (pToken "[") (pBefore (collectionItems "]" patternP) (pToken "]"))))
            ((:) (pMap SBoolPattern booleanLiteral)
               ((:) (pMap SIntPattern (pTry integerLiteral))
                  ((:) (pMap SStringPattern stringLiteral)
                     ((:) (pMap (\n -> SConstructorPattern n []) upperReference)
                        ((:) (pMap SDefaultPattern patternField) [])))))));
  annotatedVariable :: Parser SPattern;
  annotatedVariable =
    pTry
      (do {
         n <- annotatedName;
         a <- pChoice (pThen (pToken "::") annotation) (pThen (pToken ":") legacyAnnotation);
         pLook (pToken ")");
         pPure (SAnnotatedPattern n a)
       });
  annotatedName :: Parser String;
  annotatedName = pChoice lowerIdentifier (pParens annotatedName);
  patternField :: Parser (Maybe String);
  patternField = pChoice (pMap (\_ -> Nothing) (pToken "_")) (pMap Just lowerIdentifier);
  doExpr :: Parser SExpr;
  doExpr = sourceOrMetadata sharedDoExpr legacyDoExpr;
  legacyDoExpr :: Parser SExpr;
  legacyDoExpr =
    do {
      pToken "do";
      statements <- pMap concat (pBraces (pSepEndBy1 statement (pToken ";")));
      case reverse statements of {
        (:) (SDoThen result) rest -> pPure (SDo (reverse rest) result);
        _ -> pFail "a do block must end with an expression"
      }
    };
  statement :: Parser ([] SStatement);
  statement =
    pChoices
      ((:)
         (pTry
            (do {
               p <- patternP;
               pToken "<-";
               e <- expr;
               pPure ((:) (SDoBind p e) [])
             }))
         ((:) (pTry doLet) ((:) (pMap (\e -> (:) (SDoThen e) []) expr) [])));
  doLet :: Parser ([] SStatement);
  doLet =
    do {
      pToken "let";
      recursive <- pOption False (pMap (\_ -> True) (pToken "rec"));
      values <- valueBlock;
      pLook (pChoice (pToken ";") (pToken "}"));
      if recursive
      then pMap (\ds -> (:) (SDoLetRec ds) []) (pEither (Surface.recursiveValues values))
      else pPure (map (\((,,) n a e) -> SDoLet n a e) values)
    };
  atom :: Parser SExpr;
  atom = sourceOrMetadata sharedAtom legacyAtom;
  sharedAtom :: Parser SExpr;
  -- An ordinary lower-case identifier can only succeed as a reference.
  -- Keep the full alternative ordering for reserved words and failed parses.
  sharedAtom = Parser (\state -> case state of {
    ParseState file ((:) (Token text sl sc el ec) _) _ syntax sourceModule sourcePackage _ -> let {
      first = stringCodeAt text 0
    } in if stringLength text > 0 && first >= 97 && first <= 122
      then case pRun lowerIdentifier state of {
        PSuccess name end used -> let {
          value = SVar name;
          location = SourceSpan sourcePackage sourceModule file sl sc el ec
        } in PSuccess (case syntax of {
          MetadataSyntax -> value;
          SharedHaskellV1 -> SCallSite name location value;
          LegacyEmlfV1 -> SCallSite (referenceLeaf name) location value
        }) end used;
        _ -> pRun sharedAtomChoices state
      } else if stringLength text > 0 && first >= 48 && first <= 57
        then case pRun (pChoice (pMap SDoubleLit doubleLiteral) (pMap SIntLit naturalLiteral)) state of {
          success@(PSuccess _ _ _) -> success;
          _ -> pRun sharedAtomChoices state
        } else pRun sharedAtomChoices state;
    _ -> pRun sharedAtomChoices state
  });
  groupedExpression = pBind (collectionItems ")" expr)
    (sourceTupleValue (SConstructor "()") (\name fields -> foldl SApp (SConstructor name) fields));
  parenthesizedAtom = Parser (\state -> case state of {
    ParseState _ ((:) token _) _ _ _ _ _ -> let { text = tokenText token; first = stringCodeAt text 0 } in
      if stringLength text > 0 && ((first >= 97 && first <= 122) || (first >= 48 && first <= 57) ||
        first == 40 || first == 41) then pRun groupedExpression state else pRun parenthesizedAtomChoices state;
    _ -> pRun parenthesizedAtomChoices state
  });
  parenthesizedAtomChoices = pChoices [
    pMap (\_ -> SConstructor ":") (pToken ":"),
    pBind (pSome (pToken ",")) (\commas -> pMap SConstructor (sourceTupleName (1 + length commas))),
    pTry parenthesizedOperatorReference,
    pTry (pMap SIntLit (pThen (pToken "-") (pMap (\n -> 0 - n) naturalLiteral))),
    groupedExpression];
  sharedAtomChoices =
    pChoices
      ((:)
         (pParens parenthesizedAtom)
         ((:)
            sharedListExpression
            ((:) doExpr
               ((:) (pBySyntax (pMap (\b -> SConstructor (sharedSourceName (if b then "True" else "False"))) booleanLiteral) (pMap SBoolLit booleanLiteral))
                  ((:) (pMap SDoubleLit doubleLiteral)
                     ((:) (pMap SIntLit naturalLiteral)
                        ((:) (pMap (\text -> SApp (SVar "$MLF.Primitive.fromString")
                                  (Surface.sourceStringExpression text)) sourceStringLiteral)
                           ((:) locatedLowerReference
                              ((:) (pThen (pNot (pTry operatorReference)) (pMap (\name -> SConstructor (sharedSourceName name)) upperReference)) [])))))))));
  sourceConsExpression :: SExpr -> SExpr -> SExpr;
  sourceConsExpression a b = SApp (SApp (SConstructor ":") a) b;
  -- Open-ended source ranges enumerate machine Ints. Stop at the last
  -- representable element, including when the last step would overflow.
  openRange :: SExpr -> Maybe SExpr -> SExpr;
  openRange first second = let {
    item = SVar "$rangeItem";
    empty = SConstructor "[]";
    lastInt = SIntLit 9223372036854775807;
    recur = SApp (SVar "$rangeLoop");
    loop start body = SLetRec [("$rangeLoop", InferRecursive, SLam "$rangeItem" Nothing body)]
      (recur start)
  } in case second of {
    Nothing -> loop first
      (conditional (primitive2 PEqInt item lastInt)
        (sourceConsExpression item empty)
        (sourceConsExpression item (recur (primitive2 PAddInt item (SIntLit 1)))));
    Just next -> let {
      toInteger = SApp (SPrimitive PIntToInteger);
      start = SVar "$rangeStart";
      step = SVar "$rangeStep";
      descending = SVar "$rangeDescending";
      firstInt = SIntLit (0 - 9223372036854775807 - 1);
      pastBound = conditional descending
        (primitive2 PLtInteger item (toInteger firstInt))
        (primitive2 PLtInteger (toInteger lastInt) item)
    } in
      SLet "$rangeStart" (toInteger first)
        (SLet "$rangeStep" (primitive2 PSubInteger (toInteger next) start)
          (SLet "$rangeDescending" (primitive2 PLtInteger step (toInteger (SIntLit 0)))
            (loop start (conditional pastBound empty
              (sourceConsExpression (SApp (SPrimitive PIntegerToInt) item)
                (recur (primitive2 PAddInteger item step)))))))
  };
  sharedListExpression :: Parser SExpr;
  sharedListExpression = pBetween (pToken "[") (pToken "]") (pChoice
    (pThen (pLook (pToken "]")) (pPure (SConstructor "[]")))
    (do {
      first <- expr;
      pChoices [
        pThen (pToken "|") (do {
          qualifiers <- pSepBy1 listQualifier (pToken ",");
          pEither (lowerListQualifiers qualifiers (sourceConsExpression first (SConstructor "[]")))
        }),
        pMap (\_ -> openRange first Nothing) (pToken ".."),
        pThen (pToken ",") (do {
          second <- collectionElement "]" expr;
          pChoice (pMap (\_ -> openRange first (Just second)) (pToken ".."))
            (pMap (foldr sourceConsExpression (SConstructor "[]"))
              (pMap (\rest -> first : second : rest) (collectionRest "]" expr)))
        }),
        pPure (sourceConsExpression first (SConstructor "[]"))]
    }));
  listQualifier :: Parser ListQualifier;
  listQualifier = pChoices [
    pBind (pTry (pBefore patternP (pToken "<-"))) (\pattern -> pMap (ListGenerator pattern) expr),
    pTry (do {
      pToken "let";
      values <- valueBlock;
      pLook (pChoice (pToken ",") (pToken "]"));
      pPure (ListLet values)
    }),
    pMap ListGuard expr];
  -- Use the wired list Monad and the same pattern lowering as shared do.
  -- A refutable generator skips the element using an empty list fallback.
  lowerListQualifiers :: [] ListQualifier -> SExpr -> Either String SExpr;
  lowerListQualifiers qualifiers result = case qualifiers of {
    [] -> Right result;
    (:) qualifier rest -> do {
      continuation <- lowerListQualifiers rest result;
      case qualifier of {
        ListGenerator pattern source -> Right (SSharedBind pattern source continuation
          (SVar "$MLF.Primitive.>>=") (SConstructor "[]"));
        ListGuard condition -> Right (conditional condition continuation (SConstructor "[]"));
        ListLet values -> Surface.bindValues values continuation
      }
    }
  };
  legacyAtom :: Parser SExpr;
  legacyAtom =
    pChoices
      ((:)
         (pParens
            (pChoice (pTry parenthesizedOperatorReference) (pBind (collectionItems ")" expr)
               (tupleValue (SConstructor "()")
                  (\name fields -> foldl SApp (SConstructor name) fields)))))
         ((:)
            (pMap (foldr consExpression (SConstructor "Nil"))
               (pThen (pToken "[") (pBefore (collectionItems "]" expr) (pToken "]"))))
            ((:) doExpr
               ((:) (pMap SBoolLit booleanLiteral)
                  ((:) (pMap SDoubleLit doubleLiteral)
                     ((:) (pMap SIntLit naturalLiteral)
                        ((:) (pMap SStringLit stringLiteral)
                           ((:) locatedLowerReference
                              ((:) (pMap SConstructor upperReference) [])))))))));
  -- Nonempty collections never admit a trailing comma or tuple sections.
  -- The separator check also gives ranges/comprehensions a direct diagnostic.
  collectionItems :: forall a. String -> Parser a -> Parser ([] a);
  collectionItems closing item =
    pChoice (pThen (pLook (pToken closing)) (pPure []))
      (do {
         first <- item;
         rest <- collectionRest closing item;
         pPure ((:) first rest)
       });
  collectionRest :: forall a. String -> Parser a -> Parser ([] a);
  collectionRest closing item =
    do {
      state <- pState;
      let {
        next = tokenText (stateToken state)
      };
      if eqString next "|"
      then pFail "list comprehensions are not supported"
      else if eqString next ".."
           then pFail "list ranges are not supported"
           else if eqString next ","
                then do {
                       pToken ",";
                       value <- collectionElement closing item;
                       rest <- collectionRest closing item;
                       pPure ((:) value rest)
                     }
                else pPure []
    };
  collectionElement :: forall a. String -> Parser a -> Parser a;
  collectionElement closing item = do {
    end <- pState;
    if eqString (tokenText (stateToken end)) closing
    then pFail "trailing comma or missing collection element"
    else item
  };
  sourceTupleName :: Int -> Parser String;
  sourceTupleName arity =
    if arity >= 2 && arity <= 64
    then pPure ("(" ++ (foldr (++) "" (replicate (arity - 1) ",") ++ ")"))
    else pFail "tuple arity must be between 2 and 64";
  sourceTupleValue :: forall a. a -> (String -> [] a -> a) -> [] a -> Parser a;
  sourceTupleValue unit construct values =
    case values of {
      [] -> pPure unit;
      (:) value [] -> pPure value;
      _ -> pMap (\name -> construct name values) (sourceTupleName (length values))
    };
  tupleValue :: forall a. a -> (String -> [] a -> a) -> [] a -> Parser a;
  tupleValue = sourceTupleValue;
  booleanLiteral :: Parser Bool;
  booleanLiteral =
    pBySyntax (pChoice (pMap (\_ -> True) (pToken "True")) (pMap (\_ -> False) (pToken "False")))
      legacyBooleanLiteral;
  legacyBooleanLiteral :: Parser Bool;
  legacyBooleanLiteral =
    pChoice (pMap (\_ -> True) (pChoice (pToken "true") (pToken "True")))
      (pMap (\_ -> False) (pChoice (pToken "false") (pToken "False")));
  naturalLiteral :: Parser Int;
  naturalLiteral =
    pBind
      (pSatisfy
         (\s ->
            ((stringLength s > 0) &&
             (isDigit (stringCodeAt s 0) &&
              not
                (isFloating s &&
                 not
                   ((stringLength s > 1) &&
                    ((stringCodeAt s 1 == 120) || (stringCodeAt s 1 == 88)))))))
         "integer")
      (\s -> pEither (naturalValue s));
  integerLiteral :: Parser Int;
  integerLiteral =
    do {
      sign <- pOption 1 (pChoice (pMap (\_ -> (-1)) (pToken "-")) (pMap (\_ -> 1) (pToken "+")));
      value <- naturalLiteral;
      pPure (sign * value)
    };
  doubleLiteral :: Parser Double;
  doubleLiteral =
    pTry
      (do {
         spelling <-
           pSatisfy
             (\s ->
                ((stringLength s > 0) &&
                 (isDigit (stringCodeAt s 0) &&
                  (isFloating s &&
                   not
                     ((stringLength s > 1) &&
                      ((stringCodeAt s 1 == 120) || (stringCodeAt s 1 == 88)))))))
             "Double";
         let {
           value = readDouble spelling
         };
         if ((andInt (doubleToBits value) 9218868437227405312) == 9218868437227405312)
         then pFail "non-finite Double literal"
         else pPure value
       });
  sourceStringLiteral :: Parser SourceString;
  sourceStringLiteral =
    pBind (pSatisfy (\s -> ((stringLength s > 0) && (stringCodeAt s 0 == 34))) "string literal")
      (\s -> pEither (sourceStringValue s));
  stringLiteral :: Parser String;
  stringLiteral =
    pBind (pSatisfy (\s -> ((stringLength s > 0) && (stringCodeAt s 0 == 34))) "string literal")
      (\s -> pEither (stringValue s));
  annotation :: Parser SAnnotation;
  annotation =
    pBySyntax
      (do {
         ty <- typ;
         pEither (validateSharedScheme ty);
         pPure (SAnnotation [] ty)
       })
      legacyAnnotationParser;
  legacyAnnotationParser :: Parser SAnnotation;
  legacyAnnotationParser =
    do {
      variables <- pOption [] (pThen (pToken "exists") (pBefore (pSome identifier) (pToken ".")));
      if (length variables /= length (nubBy eqString variables))
      then pFail "duplicate existential variable"
      else pMap (SAnnotation variables) typ
    };
  typ :: Parser SType;
  typ =
    pChoices
      ((:) quantified
         ((:)
            (do {
               ps <- context;
               body <- typ;
               pPure (SQualified ps body)
             })
            ((:) (pChainr typeApp (pMap (\_ -> SArrow) (pToken "->"))) [])));
  quantified :: Parser SType;
  quantified =
    do {
      pToken "forall";
      binders <- pSome typeBinder;
      pToken ".";
      body <- typ;
      pPure (foldr (\((,,) f n b) t -> SForall f n b t) body binders)
    };
  typeBinder :: Parser ((,,) Flag String SType);
  typeBinder =
    pBySyntax
      (pChoice
         (pParens
            (do {
               name <- lowerIdentifier;
               pToken "::";
               k <- kindParser;
               pPure
                 ((,,) Flexible name
                    (case k of {
                       Star -> SBottom;
                       _ -> SBottomKind k
                     }))
             }))
         (pMap (\name -> (,,) Flexible name SBottom) lowerIdentifier))
      legacyTypeBinder;
  legacyTypeBinder :: Parser ((,,) Flag String SType);
  legacyTypeBinder =
    pChoice
      (pParens
         (do {
            name <- identifier;
            bound <-
              pOptional
                (pChoice
                   (pMap
                      (\k ->
                         (,) Flexible
                           (case k of {
                              Star -> SBottom;
                              _ -> SBottomKind k
                            }))
                      (pThen annotationSymbol kindParser))
                   (do {
                      flag <-
                        pChoice (pMap (\_ -> Flexible) (pChoice (pToken ">=") (pToken ">")))
                          (pMap (\_ -> Rigid) (pToken "="));
                      ty <- typ;
                      pPure ((,) flag ty)
                    }));
            pPure
              (case bound of {
                 Nothing -> (,,) Flexible name SBottom;
                 Just ((,) flag ty) -> (,,) flag name ty
               })
          }))
      (pMap (\name -> (,,) Flexible name SBottom) identifier);
  typeApp :: Parser SType;
  typeApp =
    pMap
      (\types ->
         case types of {
           [] -> SBottom;
           (:) first rest -> foldl applyType first rest
         })
      (pSome typeAtom);
  applyType :: SType -> SType -> SType;
  applyType f a =
    case f of {
      SCon n args -> SCon n (append args ((:) a []));
      _ -> STypeApp f a
    };
  typeAtom :: Parser SType;
  typeAtom = metadataAtom (\name -> SCon name []) ordinaryTypeAtom;
  ordinaryTypeAtom :: Parser SType;
  ordinaryTypeAtom =
    pBySyntax
      (pChoices
         ((:) (pParens (pChoice
                          (pBind (pSome (pToken ",")) (\commas -> pMap (\n -> SCon n []) (sourceTupleName (1 + length commas))))
                          (pBind (collectionItems ")" typ) (sourceTupleValue (SCon "()" []) SCon))))
            ((:) (pThen (pToken "[") (pBefore
                      (pChoice (pThen (pLook (pToken "]")) (pPure (SCon "[]" [])))
                         (pMap (\ty -> SCon "[]" ((:) ty [])) typ)) (pToken "]")))
               ((:) (pMap STVar lowerIdentifier)
                  ((:) (pMap (\n -> SCon (sharedSourceName n) []) upperReference) [])))))
      legacyTypeAtom;
  legacyTypeAtom :: Parser SType;
  legacyTypeAtom =
    pChoices ((:) sourceTupleTypeAtom ((:) sourceListTypeAtom
      ((:) (pMap (\_ -> SBottom) (pChoice (pToken "bot") (pToken "⊥")))
        ((:) (pMap STVar lowerIdentifier)
          ((:) (pMap (\n -> SCon n []) upperReference) [])))));
  sourceTupleTypeAtom :: Parser SType;
  sourceTupleTypeAtom = pParens (pChoice
    (pBind (pSome (pToken ","))
      (\commas -> pMap (\n -> SCon n []) (sourceTupleName (1 + length commas))))
    (pBind (collectionItems ")" typ) (sourceTupleValue (SCon "()" []) SCon)));
  sourceListTypeAtom :: Parser SType;
  sourceListTypeAtom = pThen (pToken "[") (pBefore
    (pChoice (pThen (pLook (pToken "]")) (pPure (SCon "[]" [])))
      (pMap (\ty -> SCon "[]" ((:) ty [])) typ)) (pToken "]"));
  -- Reserved Boolean spellings are parsed in declarations so semantic validation
  -- can report the same inference rejection as the maintained seed compiler.
  declarationIdentifier :: Parser String;
  declarationIdentifier =
    pChoices ((:) upperIdentifier ((:) (pToken "True") ((:) (pToken "False") [])));
  dataDeclaration :: Parser DataDecl;
  dataDeclaration =
    do {
      pToken "data";
      name <- declarationIdentifier;
      parameters <- pMany parameter;
      state <- pState;
      let {
        next = tokenText (stateToken state)
      };
      if elem eqString next reservedWords
      then pFail ("unexpected reserved word " ++ next)
      else pPure ();
      pToken "=";
      constructors <-
        pSepBy1
          (do {
             n <- declarationIdentifier;
             fields <- pMany fieldAtom;
             pPure (ConstructorDecl n fields)
           })
          (pToken "|");
      pPure
        (if all
              (\((,) _ k) ->
                 case k of {
                   Star -> True;
                   _ -> False
                 })
              parameters
         then DataDecl name (map (\((,) n _) -> n) parameters) constructors
         else DataDeclK name parameters constructors)
    };
  fieldType :: Parser Field;
  fieldType =
    pChoice
      (do {
         pToken "forall";
         binders <- pSome parameter;
         pToken ".";
         body <- fieldType;
         pPure (foldr (\((,) n k) b -> Quantified n k b) body binders)
       })
      (pChainr fieldApplication (pMap (\_ -> Function) (pToken "->")));
  fieldApplication :: Parser Field;
  fieldApplication =
    pMap
      (\fields ->
         case fields of {
           [] -> Parameter "";
           (:) first rest -> foldl applyField first rest
         })
      (pSome fieldAtom);
  applyField :: Field -> Field -> Field;
  applyField f a =
    case f of {
      Applied n fields -> Applied n (append fields ((:) a []));
      _ -> Application f a
    };
  fieldAtom :: Parser Field;
  fieldAtom = sourceOrMetadata
    (pChoice (pTry (pMap (\name -> Applied name []) metadataBuiltinName)) ordinaryFieldAtom)
    (metadataAtom (\name -> Applied name []) ordinaryFieldAtom);
  ordinaryFieldAtom :: Parser Field;
  ordinaryFieldAtom =
    pBySyntax
      (pChoices
         ((:) (pParens (pBind (collectionItems ")" fieldType)
                         (sourceTupleValue (Applied "()" []) Applied)))
            ((:) (pMap (\ty -> Applied "[]" ((:) ty []))
                     (pThen (pToken "[") (pBefore fieldType (pToken "]"))))
               ((:) (pMap (\n -> Applied (sharedSourceName n) []) upperReference)
                  ((:) (pMap Parameter lowerIdentifier) [])))))
      legacyFieldAtom;
  legacyFieldAtom :: Parser Field;
  legacyFieldAtom =
    pChoices
      ((:)
         (pParens (pBind (collectionItems ")" fieldType) (sourceTupleValue (Applied "()" []) Applied)))
         ((:)
            (pMap (\ty -> Applied "[]" ((:) ty []))
               (pThen (pToken "[") (pBefore fieldType (pToken "]"))))
            ((:) (pMap (\n -> Applied n []) upperReference)
               ((:) (pMap Parameter lowerIdentifier) []))));
  sharedOrdinaryLegacyWords :: [] String;
  sharedOrdinaryLegacyWords = (:) "rec" ((:) "exists" ((:) "true" ((:) "false" ((:) "bot" []))));
  sharedReservedWords :: [] String;
  sharedReservedWords =
    (:) "type"
      ((:) "newtype"
         ((:) "deriving"
            ((:) "default" ((:) "infix" ((:) "infixl" ((:) "infixr" ((:) "foreign" [])))))));
  referenceLeaf :: String -> String;
  referenceLeaf name = referenceLeafAt name (stringLength name - 1);
  referenceLeafAt :: String -> Int -> String;
  referenceLeafAt name i =
    if (i < 0)
    then name
    else if (stringCodeAt name i == 46)
         then stringSlice name (i + 1) ((stringLength name - i) - 1)
         else referenceLeafAt name (i - 1);
  validateSharedBinding :: String -> Either String ();
  validateSharedBinding _ = Right ();
  validateSharedScheme :: SType -> Either String ();
  validateSharedScheme ty =
    do {
      unless (null (freeTypeNames [] ty))
        (Left "shared signatures require explicit forall for every free type variable");
      validateSharedType True ty
    };
  validateSharedType :: Bool -> SType -> Either String ();
  validateSharedType outer ty =
    case ty of {
      SForall flag name bound body ->
        do {
          case flag of {
            Rigid -> Left "rigid quantifiers are outside shared-haskell-v1";
            Flexible -> Right ()
          };
          case bound of {
            SBottom -> Right ();
            SBottomKind _ -> Right ();
            _ -> Left "bounded quantifiers are outside shared-haskell-v1"
          };
          validateSharedType outer body
        };
      SQualified predicates body ->
        do {
          unless outer (Left "nested qualified types are outside shared-haskell-v1");
          mapM_ (\(SPredicate _ arguments) -> mapM_ validateSharedMonotype arguments) predicates;
          validateSharedType False body
        };
      SArrow a b ->
        do {
          validateSharedType False a;
          validateSharedType False b
        };
      SCon _ arguments -> mapM_ validateSharedMonotype arguments;
      STypeApp f a ->
        do {
          validateSharedType False f;
          validateSharedMonotype a
        };
      STVar _ -> Right ();
      _ -> Left "bottom types are outside shared-haskell-v1"
    };
  validateSharedMonotype :: SType -> Either String ();
  validateSharedMonotype ty =
    case ty of {
      SForall _ _ _ _ -> Left "impredicative type arguments are outside shared-haskell-v1";
      SQualified _ _ -> Left "qualified type arguments are outside shared-haskell-v1";
      SArrow a b ->
        do {
          validateSharedMonotype a;
          validateSharedMonotype b
        };
      STypeApp a b ->
        do {
          validateSharedMonotype a;
          validateSharedMonotype b
        };
      SCon _ arguments -> mapM_ validateSharedMonotype arguments;
      STVar _ -> Right ();
      _ -> Left "bottom types are outside shared-haskell-v1"
    };
  validateSharedModule :: SourceModule -> Either String ();
  validateSharedModule source =
    do {
      validateSharedModuleSyntax source;
      case source of {
        SourceModule _ _ _ _ _ _ _ values _ _ -> do {
          Surface.bindValues values (SConstructor "()");
          Right ()
        }
      }
    };
  validateSharedModuleSyntax :: SourceModule -> Either String ();
  validateSharedModuleSyntax (SourceModule file name exports imports datatypes classes instances values body _) =
    do {
      unless (isJust name && not (isJust body))
        (Left (file ++ ": shared source requires a named declaration-only module"));
      mapM_ validateSharedImport imports;
      case exports of {
        Nothing -> Right ();
        Just items -> mapM_ validateSharedExport items
      };
      mapM_ validateSharedDatatype datatypes;
      mapM_
        (\((,,) n _ expression) ->
           do {
             validateSharedBinding n;
             validateSharedExpression expression
           })
        values;
      mapM_
        (\(SClassDecl _ parameters supers methods) ->
           do {
             mapM_ (\(SPredicate _ args) -> mapM_ validateSharedMonotype args) supers;
             mapM_
               (\((,) n ty) ->
                  do {
                    validateSharedBinding n;
                    validateSharedType False ty;
                    unless (null (freeTypeNames (map fst parameters) ty))
                      (Left "unbound type variable in shared class method")
                  })
               methods
           })
        classes;
      mapM_
        (\(SInstanceDecl _ context _ head methods) ->
           do {
             mapM_ (\(SPredicate _ args) -> mapM_ validateSharedMonotype args) context;
             mapM_ validateSharedMonotype head;
             mapM_ (\((,) _ expression) -> validateSharedExpression expression) methods
           })
        instances
    };
  validateSharedImportItem :: Export -> Either String ();
  validateSharedImportItem _ = Right ();
  validateSharedImport :: Import -> Either String ();
  validateSharedImport (Import name _ _ _) = do {
    when (eqString name "Prelude") (Left "shared source uses the standard MLF.Primitive facade; legacy Prelude is outside shared-haskell-v1");
    when (textStartsAt name 0 "MLF.Host.")
      (Left "shared modules use MLF.Primitive rather than host adapter internals")
  };
  validateSharedExport :: Export -> Either String ();
  validateSharedExport _ = Right ();
  validateSharedPattern :: SPattern -> Either String ();
  validateSharedPattern pattern =
    do {
      mapM_ validateSharedBinding (Surface.patternVariables pattern);
      case pattern of {
        SStringPattern _ -> Left "string patterns are outside shared-haskell-v1";
        SAnnotatedPattern _ _ -> Left "typed patterns are outside shared-haskell-v1";
        SNestedPattern _ patterns -> mapM_ validateSharedPattern patterns;
        _ -> Right ()
      }
    };
  validateSharedExpression :: SExpr -> Either String ();
  validateSharedExpression expression =
    case expression of {
      SCallSite _ _ body -> validateSharedExpression body;
      SSharedBind pattern action continuation bind failure -> do {
        validateSharedPattern pattern;
        mapM_ validateSharedExpression ((:) action ((:) continuation ((:) bind ((:) failure []))))
      };
      SVar _ -> Right ();
      SBindDictionaries _ _ -> Left "dictionary binders are reserved for class translation";
      SLam name annotation body ->
        do {
          validateSharedBinding name;
          when (isJust annotation) (Left "typed lambda patterns are outside shared-haskell-v1");
          validateSharedExpression body
        };
      SApp a b ->
        do {
          validateSharedExpression a;
          validateSharedExpression b
        };
      SLet name a b ->
        do {
          validateSharedBinding name;
          validateSharedExpression a;
          validateSharedExpression b
        };
      SAnn e (SAnnotation variables ty) ->
        do {
          unless (null variables) (Left "existential annotations are outside shared-haskell-v1");
          validateSharedScheme ty;
          validateSharedExpression e
        };
      SSignature e (SAnnotation variables ty) ->
        do {
          unless (null variables) (Left "existential annotations are outside shared-haskell-v1");
          validateSharedScheme ty;
          validateSharedExpression e
        };
      SCase value branches ->
        do {
          validateSharedExpression value;
          mapM_
            (\(SAlternative pattern body) ->
               do {
                 validateSharedPattern pattern;
                 validateSharedExpression body
               })
            branches
        };
      SEquations rows ->
        mapM_
          (\((,) patterns body) ->
             do {
               mapM_ validateSharedPattern patterns;
               validateSharedExpression body
             })
          rows;
      SLetRec definitions body ->
        do {
          mapM_
            (\((,,) name mode value) ->
               do {
                 validateSharedBinding name;
                 validateSharedRecursiveMode mode;
                 validateSharedExpression value
               })
            definitions;
          validateSharedExpression body
        };
      SDo _ _ -> Left "internal error: shared do was not normalized";
      _ -> Right ()
    };
  validateSharedRecursiveMode :: RecursiveMode -> Either String ();
  validateSharedRecursiveMode mode =
    case mode of {
      InferRecursive -> Right ();
      CheckRecursive (SAnnotation variables ty) ->
        do {
          unless (null variables) (Left "existential annotations are outside shared-haskell-v1");
          validateSharedScheme ty
        }
    };
  sharedDoExpr :: Parser SExpr;
  sharedDoExpr =
    do {
      pToken "do";
      statements <- pBraces (pSepEndBy1 sharedStatement (pToken ";"));
      case reverse statements of {
        (:) (SharedThen result) rest ->
          pEither
            (runFresh (append (Desugar.allNames result) (concatMap sharedStatementNames rest))
               (lowerSharedStatements (reverse rest) result));
        _ -> pFail "a shared do block must end with an expression"
      }
    };
  sharedStatement :: Parser SharedStatement;
  sharedStatement =
    pChoices
      ((:)
         (pTry
            (do {
               located <- pWithSpan (do {
                 pattern <- patternP;
                 pToken "<-";
                 value <- expr;
                 pPure ((,) pattern value)
               });
               case located of {
                 (,) location ((,) pattern value) -> pPure (SharedBind pattern value location)
               }
             }))
         ((:)
            (pTry
               (do {
                  pToken "let";
                  values <- valueBlock;
                  pLook (pChoice (pToken ";") (pToken "}"));
                  pPure (SharedLet values)
                }))
            ((:) (pMap SharedThen expr) [])));
  sharedStatementNames :: SharedStatement -> [] String;
  sharedStatementNames statement =
    case statement of {
      SharedBind pattern value _ ->
        append (Desugar.patternVariables pattern) (Desugar.allNames value);
      SharedThen value -> Desugar.allNames value;
      SharedLet values -> concatMap (\((,,) n _ value) -> (:) n (Desugar.allNames value)) values
    };
  lowerSharedStatements :: [] SharedStatement -> SExpr -> Fresh SExpr;
  lowerSharedStatements statements result =
    case statements of {
      [] -> freshPure result;
      (:) statement rest ->
        do {
          continuation <- lowerSharedStatements rest result;
          case statement of {
            SharedLet values ->
              case Surface.bindValues values continuation of {
                Left error -> freshFail error;
                Right body -> freshPure body
              };
            SharedBind pattern value location ->
              freshPure (SSharedBind pattern value continuation
                (SVar "$MLF.Primitive.>>=")
                (SApp (SCallSite "a do statement" location (SVar "$MLF.Primitive.fail"))
                  (SApp (SPrimitive PTextToChars) (SStringLit "Pattern match failure in do expression"))));
            SharedThen value ->
              freshPure (SApp (SApp (SVar "$MLF.Primitive.>>") value) continuation)
          }
        }
    };
  validateSharedDatatype :: DataDecl -> Either String ();
  validateSharedDatatype declaration =
    case declaration of {
      DataDecl _ _ constructors -> mapM_ validateSharedConstructor constructors;
      DataDeclK _ _ constructors -> mapM_ validateSharedConstructor constructors
    };
  validateSharedConstructor :: ConstructorDecl -> Either String ();
  validateSharedConstructor (ConstructorDecl _ fields) = mapM_ (validateSharedField True) fields;
  validateSharedField :: Bool -> Field -> Either String ();
  validateSharedField polymorphic field =
    case field of {
      Quantified _ _ body ->
        if polymorphic
        then validateSharedField True body
        else Left "impredicative datatype fields are outside shared-haskell-v1";
      Function a b ->
        do {
          validateSharedField polymorphic a;
          validateSharedField polymorphic b
        };
      Applied _ fields -> mapM_ (validateSharedField False) fields;
      Application a b ->
        do {
          validateSharedField False a;
          validateSharedField False b
        };
      Parameter _ -> Right ()
    };

  -- Only this fixed operator vocabulary is supported. The bindings themselves
  -- resolve normally; these are the ordinary facade fixities, not primitives.
  operatorName :: Parser String;
  operatorName = pSatisfy (\name -> Set.member compareString name sharedOperatorSet) "supported value operator";
  operatorReference :: Parser String;
  operatorReference = operatorReferenceWith qualifiedName operatorName;
  operatorReferenceWith build suffix = do {
    prefixes <- pMany (pTry (pBefore upperIdentifier (pSymbolPrefix ".")));
    item <- suffix;
    pPure (build prefixes item)
  };
  -- Both prefix and infix references consume the final operator token in full.
  -- Save its endpoint while parsing, including a suffix split from ".+", so a
  -- short reference never measures the two unconsumed token-list suffixes.
  operatorReferenceSpan :: Parser ((,) SourceSpan String);
  operatorReferenceSpan = do {
    original <- pState;
    first <- referenceToken;
    located <- operatorReferenceWith (\prefixes ((,) final name) ->
      (,) final (qualifiedName prefixes name)) (do {
        final <- referenceToken;
        name <- operatorName;
        pPure ((,) final name)
      });
    case original of { ParseState file _ _ _ sourceModule sourcePackage _ ->
      let { final = fst located } in
      pPure ((,) (SourceSpan sourcePackage sourceModule file (tokenLine first) (tokenColumn first)
        (tokenEndLine final) (tokenEndColumn final)) (snd located))
    }
  };
  parenthesizedOperatorReference :: Parser SExpr;
  parenthesizedOperatorReference = pBind
    (pBefore operatorReferenceSpan (pLook (pToken ")"))) referenceAt;
  bindingName :: Parser String;
  bindingName = pChoice lowerIdentifier (pParens operatorName);
  valueReference :: Parser String;
  valueReference = pChoice lowerReference (pParens operatorReference);
  sharedInfix :: [] String -> Parser String;
  sharedInfix choices = pTry (do {
    name <- operatorReference;
    if elem eqString (referenceLeaf name) choices then pPure name else pFail "operator at another precedence"
  });
  namedOperator name a b = SApp (SApp (SVar (sourceOperatorName name)) a) b;
  sourceOperatorName :: String -> String;
  sourceOperatorName name =
    if elem eqString (referenceLeaf name) ((:) "==" ((:) "/=" []))
    then name else "$MLF.Infix." ++ name;
  sharedSourceName name = if elem eqString name ((:) "True" ((:) "False" [])) then "$MLF.Source." ++ name else name;
  -- A successful infix ends at the operator token, including the suffix
  -- left when a qualifier consumes the dot of a combined token such as ".+".
  sharedOperatorParser choices = pTry (do {
    located <- operatorReferenceSpan;
    case located of { (,) location operator -> let { leaf = referenceLeaf operator } in
      if elem eqString leaf choices then pPure (\a b ->
        SApp (SApp (SCallSite leaf location (SVar (sourceOperatorName operator))) a) b)
      else pFail "operator at another precedence"
    }
  });
  sharedApplyExpr :: Parser SExpr;
  sharedApplyExpr = pChainr sharedBindExpr (sharedOperatorParser ["$"]);
  sharedBindExpr :: Parser SExpr;
  sharedBindExpr = pBind operand (\first -> Parser (\state -> case state of {
    ParseState _ [] _ _ _ _ _ -> PSuccess first state False;
    ParseState _ ((:) token _) _ _ _ _ _ -> if closesExpression (tokenText token)
      then PSuccess first state False else pRun (sharedAfterOperand first) state
  }));
  -- The first operand is already parsed. Resume at the tightest level when
  -- the next token can continue an expression.
  sharedAfterOperand first = do {
    product <- sharedMultiplyTail first;
    sum <- sharedAddTail product;
    joined <- sharedConcatTail sum;
    compared <- sharedLevel4Tail joined;
    conjunction <- sharedAndTail compared;
    disjunction <- sharedOrTail conjunction;
    pChainlRest sharedOrExpr (sharedOperatorParser [">>=",">>"]) disjunction
  };
  sharedRightTail parser operator first =
    pChoice (pBind operator (\f -> pMap (f first) parser)) (pPure first);
  sharedOrExpr :: Parser SExpr;
  sharedOrExpr = pBind sharedAndExpr sharedOrTail;
  sharedOrTail first = sharedRightTail sharedOrExpr (sharedOperatorParser ["||"]) first;
  sharedAndExpr :: Parser SExpr;
  sharedAndExpr = pBind sharedLevel4 sharedAndTail;
  sharedAndTail first = sharedRightTail sharedAndExpr (sharedOperatorParser ["&&"]) first;
  sharedComparisons :: [] String;
  sharedComparisons = (:) ("==") ((:) ("/=") ((:) ("<") ((:) ("<=") ((:) (">") ((:) (">=") ([]))))));
  sharedLevel4Operators :: [] String;
  sharedLevel4Operators = append sharedComparisons ((:) "<*>" ((:) "<$" ((:) "*>" ((:) "<*" []))));
  sharedLevel4 :: Parser SExpr;
  sharedLevel4 = pBind sharedConcatExpr sharedLevel4Tail;
  sharedLevel4Tail first = do {
    rest <- pMany (do { op <- sharedInfix sharedLevel4Operators; value <- sharedConcatExpr; pPure ((,) op value) });
    when (length rest > 1 && any (\entry -> elem eqString (referenceLeaf (fst entry)) sharedComparisons) rest)
      (pFail "ambiguous use of a non-associative comparison operator");
    pPure (foldl (\left entry -> namedOperator (fst entry) left (snd entry)) first rest)
  };
  sharedConcatExpr :: Parser SExpr;
  sharedConcatExpr = pBind sharedAddExpr sharedConcatTail;
  sharedConcatTail first = sharedRightTail sharedConcatExpr
    (pChoice (pMap (\_ -> sourceConsExpression) (pToken ":")) (sharedOperatorParser ["++"])) first;
  sharedAddExpr :: Parser SExpr;
  sharedAddExpr = pBind sharedMultiplyExpr sharedAddTail;
  sharedAddTail first = pChainlRest sharedMultiplyExpr (sharedOperatorParser ["+","-"]) first;
  sharedMultiplyExpr :: Parser SExpr;
  sharedMultiplyExpr = pBind operand sharedMultiplyTail;
  sharedMultiplyTail first = pChainlRest operand (sharedOperatorParser ["*","/","%"]) first
}
