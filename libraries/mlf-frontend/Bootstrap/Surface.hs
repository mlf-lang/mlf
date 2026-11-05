-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Surface where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Data as D;
  valueClosure :: Map String ((,,) String (Maybe SAnnotation) SExpr) ->
                  Set String -> Set String -> Set String;
  valueClosure values seen todo =
    case Set.minView todo of {
      Nothing -> seen;
      Just ((,) name rest) ->
        if Set.member compareString name seen
        then valueClosure values seen rest
        else case M.lookup compareString name values of {
               Nothing -> valueClosure values seen rest;
               Just ((,,) _ _ expression) ->
                 valueClosure values (Set.insert compareString name seen)
                   (Set.union compareString rest
                      (Set.fromList compareString (freeNames expression)))
             }
    };
  closeSourceMethod :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                       Map String ((,,) String (Maybe SAnnotation) SExpr) ->
                       SExpr -> Either String SExpr;
  closeSourceMethod values valueMap expression =
    let {
      needed = valueClosure valueMap Set.empty (Set.fromList compareString (freeNames expression))
    } in
    bindValues
      (map (\((,,) name annotation body) -> (,,) name annotation (SSourceDefinition body))
        (filter (\((,,) name _ _) -> Set.member compareString name needed) values)) expression;
  closeSourceInstance :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                         Map String ((,,) String (Maybe SAnnotation) SExpr) ->
                         SInstanceDecl -> Either String SInstanceDecl;
  closeSourceInstance values valueMap (SInstanceDecl variables context name head methods) =
    do {
      closed <- mapM
        (\method -> do {
          body <- closeSourceMethod values valueMap (snd method);
          Right ((,) (fst method) body)
        }) methods;
      Right (SInstanceDecl variables context name head closed)
    };
  closeSourceInstances :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                          [] SInstanceDecl -> Either String ([] SInstanceDecl);
  closeSourceInstances values instances =
    let {
      valueMap = M.fromList compareString (map (\value -> case value of {
        (,,) name _ _ -> (,) name value
      }) values)
    } in mapM (closeSourceInstance values valueMap) instances;
  patternVariables :: SPattern -> [] String;
  patternVariables = Desugar.patternVariables;
  patternReferences :: SPattern -> [] String;
  patternReferences pattern =
    case pattern of {
      SAsPattern _ inner -> patternReferences inner;
      SLazyPattern inner -> patternReferences inner;
      SOverloadedStringPattern _ equality conversion -> (:) equality ((:) conversion []);
      SNestedPattern _ patterns -> concatMap patternReferences patterns;
      _ -> []
    };
  freeNames :: SExpr -> [] String;
  freeNames e = nubBy eqString (freeNamesRaw e);
  without :: [] String -> [] String -> [] String;
  without names bound = filter (\n -> not (elem eqString n bound)) names;
  freeNamesRaw :: SExpr -> [] String;
  freeNamesRaw e =
    case e of {
      SSourceDefinition body -> freeNamesRaw body;
      SCallSite _ _ body -> freeNamesRaw body;
      SSharedBind pattern action body binding failure ->
        append (patternReferences pattern)
          (append (without (freeNamesRaw body) (patternVariables pattern))
            (concatMap freeNamesRaw ((:) action ((:) binding ((:) failure [])))));
      SVar n -> (:) (Dependency.lexicalValueName n) [];
      SLam n _ b -> without (freeNamesRaw b) ((:) n []);
      SApp a b -> append (freeNamesRaw a) (freeNamesRaw b);
      SLet n a b -> append (freeNamesRaw a) (without (freeNamesRaw b) ((:) n []));
      SAnn a _ -> freeNamesRaw a;
      SSignature a _ -> freeNamesRaw a;
      SCase a branches ->
        append (freeNamesRaw a)
          (concatMap (\(SAlternative p b) -> append (patternReferences p) (without (freeNamesRaw b) (patternVariables p)))
             branches);
      SEquations rows ->
        concatMap (\((,) ps b) -> append (concatMap patternReferences ps) (without (freeNamesRaw b) (concatMap patternVariables ps))) rows;
      SLetRec definitions body ->
        without
          (append (freeNamesRaw body) (concatMap (\((,,) _ _ a) -> freeNamesRaw a) definitions))
          (map (\((,,) n _ _) -> n) definitions);
      SDo _ _ -> freeNamesRaw (Desugar.desugarDo e);
      SChecked _ a -> freeNamesRaw a;
      _ -> []
    };
  function :: [] ((,) ([] SPattern) SExpr) -> SExpr;
  function rows =
    case rows of {
      (:) ((,) patterns body) [] ->
        if all simpleParameter patterns then foldr addParameter body patterns else SEquations rows;
      _ -> SEquations rows
    };
  simpleParameter :: SPattern -> Bool;
  simpleParameter pattern =
    case pattern of {
      SDefaultPattern (Just _) -> True;
      SAnnotatedPattern _ _ -> True;
      _ -> False
    };
  addParameter :: SPattern -> SExpr -> SExpr;
  addParameter pattern body =
    case pattern of {
      SDefaultPattern (Just n) -> SLam n Nothing body;
      SAnnotatedPattern n a -> SLam n (Just a) body;
      _ -> body
    };
  recursiveValues :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                     Either String ([] ((,,) String RecursiveMode SExpr));
  recursiveValues values =
    traverseEither
      (\((,,) n a e) ->
         case a of {
           Nothing -> Right ((,,) n InferRecursive e);
           Just (SAnnotation [] ty) -> Right ((,,) n (CheckRecursive (SAnnotation [] ty)) e);
           _ -> Left ("recursive definition " ++ (n ++ " requires an explicit closed signature"))
         })
      values;
  valueName :: (,,) String (Maybe SAnnotation) SExpr -> String;
  valueName ((,,) n _ _) = n;
  valueBody :: (,,) String (Maybe SAnnotation) SExpr -> SExpr;
  valueBody ((,,) _ _ e) = e;
  bindValues :: [] ((,,) String (Maybe SAnnotation) SExpr) -> SExpr -> Either String SExpr;
  bindValues values body =
    case Dependency.declarationGroups values of {
      Left error -> Left error;
      Right groups -> wrapGroups values (Dependency.declarationEdges values) groups body
    };
  wrapGroups :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                [] ((,) String ([] String)) ->
                [] ([] String) -> SExpr -> Either String SExpr;
  wrapGroups values dependencies groups body =
    wrapIndexed (M.fromList compareString (map (\v -> (,) (valueName v) v) values))
      (M.fromList compareString dependencies)
      groups
      body;
  wrapIndexed :: Map String ((,,) String (Maybe SAnnotation) SExpr) ->
                 Map String ([] String) -> [] ([] String) -> SExpr -> Either String SExpr;
  wrapIndexed values dependencies groups body =
    case groups of {
      [] -> Right body;
      (:) group rest ->
        case wrapIndexed values dependencies rest body of {
          Left error -> Left error;
          Right continuation ->
            let {
              local = map (\n -> M.get compareString n values) group
            } in
            let {
              cyclic =
                ((length group > 1) ||
                 any (\n -> elem eqString n (M.findWithDefault compareString [] n dependencies))
                   group)
            } in
            if cyclic
            then mapEither (\ds -> SLetRec ds continuation) (recursiveValues local)
            else case local of {
                   (:) ((,,) n a e) [] ->
                     Right
                       (SLet n
                          (case a of {
                             Nothing -> e;
                             Just t -> SSignature e t
                           })
                          continuation);
                   _ -> Left "invalid declaration group"
                 }
        }
    };
  lowerSurface :: SProgram -> Either String SProgram;
  lowerSurface program = do {
    env <- D.validateDeclarations (case program of { SProgram ds _ -> ds; SClassProgram ds _ _ _ -> ds });
    case program of {
      SProgram ds e -> mapEither (SProgram ds) (lowerExpressionWithData env e);
      SClassProgram ds cs instances e ->
        do {
          lowered <-
            traverseEither
              (\(SInstanceDecl vars context name types methods) ->
                 do {
                   ms <-
                     traverseEither (\((,) n value) -> mapEither ((,) n) (lowerExpressionWithData env value))
                       methods;
                   Right (SInstanceDecl vars context name types ms)
                 })
              instances;
          body <- lowerExpressionWithData env e;
          Right (SClassProgram ds cs lowered body)
        }
    }
    };
  lowerExpression :: SExpr -> Either String SExpr;
  lowerExpression = lowerExpressionWithData D.emptyDataEnv;
  lowerExpressionWithData :: DataEnv -> SExpr -> Either String SExpr;
  lowerExpressionWithData env original = do {
    shared <- Desugar.lowerSharedDo env original;
    runFresh (Desugar.allNames shared) (lower env (Desugar.desugarDo shared))
  };
  flatPattern :: SPattern -> Bool;
  flatPattern pattern =
    case pattern of {
      SConstructorPattern _ _ -> True;
      SDefaultPattern _ -> True;
      _ -> False
    };
  lower :: DataEnv -> SExpr -> Fresh SExpr;
  lower env expression =
    case expression of {
      SSourceDefinition body -> do { b <- lower env body; freshPure (SSourceDefinition b) };
      SCallSite name location body -> do { b <- lower env body; freshPure (SCallSite name location b) };
      SSharedBind _ _ _ _ _ -> freshFail "internal error: shared do escaped metadata lowering";
      SLam n a b ->
        do {
          body <- lower env b;
          freshPure (SLam n a body)
        };
      SApp a b ->
        do {
          f <- lower env a;
          x <- lower env b;
          freshPure (SApp f x)
        };
      SLet n a b ->
        do {
          value <- lower env a;
          body <- lower env b;
          freshPure (SLet n value body)
        };
      SAnn a ty ->
        do {
          value <- lower env a;
          freshPure (SAnn value ty)
        };
      SSignature a ty ->
        do {
          value <- lower env a;
          freshPure (SSignature value ty)
        };
      SLetRec definitions body ->
        do {
          ds <-
            mapM
              (\((,,) n mode a) ->
                 do {
                   value <- lower env a;
                   freshPure ((,,) n mode value)
                 })
              definitions;
          b <- lower env body;
          freshPure (SLetRec ds b)
        };
      SChecked ty a ->
        do {
          value <- lower env a;
          freshPure (SChecked ty value)
        };
      SEquations [] -> freshFail "function has no equations";
      SEquations rows ->
        let {
          arity =
            case head rows of {
              (,) ps _ -> length ps
            }
        } in
        if not (all (\((,) ps _) -> (length ps == arity)) rows)
        then freshFail "function equations have different arities"
        else do {
               names <- freshNames arity "matchValue";
               body <- matching env (map SVar names) rows;
               freshPure (foldr (\n b -> SLam n Nothing b) body names)
             };
      SCase a branches ->
        do {
          value <- lower env a;
          if all (\(SAlternative p _) -> flatPattern p) branches
          then do {
                 lowered <-
                   mapM
                     (\(SAlternative p b) ->
                        do {
                          body <- lower env b;
                          freshPure (SAlternative p body)
                        })
                     branches;
                 freshPure (SCase value lowered)
               }
          else do {
                 name <- freshName "matchValue";
                 body <-
                   matching env ((:) (SVar name) [])
                     (map (\(SAlternative p b) -> (,) ((:) p []) b) branches);
                 freshPure (SLet name value body)
               }
        };
      SDo _ _ -> lower env (Desugar.desugarDo expression);
      _ -> freshPure expression
    };
  data MatchRow = MatchRow ([] SPattern) SExpr Int;
  matching :: DataEnv -> [] SExpr -> [] ((,) ([] SPattern) SExpr) -> Fresh SExpr;
  matching env values equations =
    if any
         (\((,) patterns _) ->
            let {
              names = concatMap patternVariables patterns
            } in
            (length names /= length (nubBy eqString names)))
         equations
    then freshFail "duplicate pattern variable"
    else do {
           rows <-
             mapM
               (\((,) i ((,) ps b)) ->
                  do {
                    body <- lower env b;
                    freshPure (MatchRow ps body i)
                  })
               (zip (range 0 (length equations - 1)) equations);
           boundValueShared1 <- matrix env values rows;
           case boundValueShared1 of {
             (,) body used ->
               do {
                 if (length (nubBy eqInt used) == length rows)
                 then freshPure body
                 else freshFail "unreachable pattern or function equation"
               }
           }
         };
  wild :: SPattern;
  wild = SDefaultPattern Nothing;
  isVariable :: SPattern -> Bool;
  isVariable pattern =
    case pattern of {
      SDefaultPattern _ -> True;
      SAnnotatedPattern _ _ -> True;
      _ -> False
    };
  bindPattern :: SExpr -> SPattern -> SExpr -> SExpr;
  bindPattern value pattern body =
    case pattern of {
      SDefaultPattern (Just n) -> SLet n value body;
      SAnnotatedPattern n a -> SLet n (SAnn value a) body;
      _ -> body
    };
  constructor :: SPattern -> Maybe ((,) String ([] SPattern));
  constructor pattern =
    case pattern of {
      SConstructorPattern c names -> Just ((,) c (map SDefaultPattern names));
      SNestedPattern c ps -> Just ((,) c ps);
      _ -> Nothing
    };
  replace :: forall a. Int -> [] a -> [] a -> [] a;
  replace column fields values =
    append (take column values) (append fields (drop (column + 1) values));
  rowPatterns :: MatchRow -> [] SPattern;
  rowPatterns (MatchRow ps _ _) = ps;
  matrix :: DataEnv -> [] SExpr -> [] MatchRow -> Fresh ((,) SExpr ([] Int));
  matrix env values rows = do {
    normalized <- mapM (normalizeRow env values) rows;
    matrixReady env values normalized
  };
  normalizeRow :: DataEnv -> [] SExpr -> MatchRow -> Fresh MatchRow;
  normalizeRow env values (MatchRow patterns body rowIndex) = do {
    result <- foldM
      (\((,) done b) ((,) value pattern) -> do {
        normalized <- normalizePattern env value pattern b;
        case normalized of { (,) p rhs -> freshPure ((,) (append done ((:) p [])) rhs) }
      }) ((,) [] body) (zip values patterns);
    case result of { (,) ps b -> freshPure (MatchRow ps b rowIndex) }
  };
  normalizePattern :: DataEnv -> SExpr -> SPattern -> SExpr -> Fresh ((,) SPattern SExpr);
  normalizePattern env value pattern body = case pattern of {
    SAsPattern name inner -> normalizePattern env value inner (SLet name value body);
    SLazyPattern inner -> do { b <- lazyPatternBindings env value inner body; freshPure ((,) wild b) };
    _ -> freshPure ((,) pattern body)
  };
  lazyPatternBindings :: DataEnv -> SExpr -> SPattern -> SExpr -> Fresh SExpr;
  lazyPatternBindings env value pattern body =
    if isVariable pattern then freshPure (bindPattern value pattern body)
    -- Even a lazy pattern with no bindings constrains the scrutinee type and
    -- required dictionaries. Retain let-polymorphism for projected payloads,
    -- but instantiate the match in an undemanded witness use so its ordinary
    -- class obligations cannot disappear when all pattern binders are unused.
    else do {
      name <- freshName "lazyPatternMatch";
      let {
        variables = patternVariables pattern;
        packed = foldr (\n rest -> SApp (SApp (SConstructor "(,)") (SVar n)) rest)
                   (SConstructor "()") variables
      };
      cannotFail <- case Desugar.patternCannotFail env pattern of { Left e -> freshFail e; Right result -> freshPure result };
      let {
        fallback = if cannotFail then [] else
          (:) (SAlternative wild (SApp (SPrimitive PPanic) (SStringLit "Irrefutable pattern failed"))) []
      };
      matched <- lower env (SCase value ((:) (SAlternative pattern packed) fallback));
      bindings <- mapM (\((,) i n) -> do {
        projection <- lazyProjection i (SVar name);
        freshPure ((,) n projection)
      }) (zip (range 0 (length variables - 1)) variables);
      witness <- freshName "lazyPatternWitness";
      freshPure (SLet name matched
        (SApp (SLam witness Nothing (foldr (\((,) n p) b -> SLet n p b) body bindings)) (SVar name)))
    };
  lazyProjection :: Int -> SExpr -> Fresh SExpr;
  lazyProjection i value = do {
    first <- freshName "lazyPatternHead"; rest <- freshName "lazyPatternTail";
    selected <- if i == 0 then freshPure (SVar first) else lazyProjection (i - 1) (SVar rest);
    freshPure (SCase value ((:)
      (SAlternative (SConstructorPattern "(,)" ((:) (Just first) ((:) (Just rest) []))) selected) []))
  };
  matrixReady :: DataEnv -> [] SExpr -> [] MatchRow -> Fresh ((,) SExpr ([] Int));
  matrixReady env values rows =
    case rows of {
      [] -> freshFail "non-exhaustive patterns";
      (:) (MatchRow firstPatterns firstBody firstIndex) _ ->
        if any (\row -> (length (rowPatterns row) /= length values)) rows
        then freshFail "function equations have different arities"
        else if all isVariable firstPatterns
             then freshPure
                    ((,)
                       (foldr (\((,) value pattern) b -> bindPattern value pattern b) firstBody
                          (zip values firstPatterns))
                       ((:) firstIndex []))
             else let {
                    column = length (takeWhile isVariable firstPatterns)
                  } in
                  let {
                    value = index values column
                  } in
                  let {
                    patterns =
                      filter (\p -> not (isVariable p))
                        (map (\row -> index (rowPatterns row) column) rows)
                  } in
                  let {
                    defaults =
                      concatMap
                        (\(MatchRow ps b i) ->
                           let {
                             p = index ps column
                           } in
                           if isVariable p
                           then (:) (MatchRow (replace column [] ps) (bindPattern value p b) i)
                                  []
                           else [])
                        rows
                  } in
                  case head patterns of {
                    SConstructorPattern _ _ ->
                      constructorsMatrix env column value values rows patterns defaults;
                    SNestedPattern _ _ ->
                      constructorsMatrix env column value values rows patterns defaults;
                    SBoolPattern _ ->
                      if not (all isBool patterns)
                      then freshFail "mixed literal pattern types"
                      else do {
                             boundValueShared3 <-
                               literalBranch env column values rows (SBoolPattern True);
                             case boundValueShared3 of {
                               (,) yes usedYes ->
                                 do {
                                   boundValueShared2 <-
                                     literalBranch env column values rows (SBoolPattern False);
                                   case boundValueShared2 of {
                                     (,) no usedNo ->
                                       do {
                                         freshPure
                                           ((,) (choose value yes no) (append usedYes usedNo))
                                       }
                                   }
                                 }
                             }
                           };
                    SIntPattern _ ->
                      literalMatrix env column values rows defaults patterns isInt (SPrimitive PEqInt)
                        (\p ->
                           case p of {
                             SIntPattern n -> SIntLit n;
                             _ -> value
                           });
                    SOverloadedStringPattern _ _ _ ->
                      overloadedStringMatrix env column values rows;
                    SStringPattern _ ->
                      literalMatrix env column values rows defaults patterns isString (SPrimitive PEqString)
                        (\p ->
                           case p of {
                             SStringPattern s -> SStringLit s;
                             _ -> value
                           });
                    _ -> freshFail "invalid pattern matrix"
                  }
    };
  completeConstructorFamily :: DataEnv -> [] String -> Bool;
  completeConstructorFamily env names = case names of {
    [] -> False;
    (:) first _ -> case D.lookupConstructor env first of {
      Left _ -> False;
      Right ((,) declaration _) ->
        all (\c -> elem eqString (D.constructorName c) names) (D.datatypeConstructors declaration) &&
        all (\name -> case D.lookupConstructor env name of {
          Left _ -> False;
          Right ((,) owner _) -> eqString (D.datatypeName owner) (D.datatypeName declaration)
        }) names
    }
  };
  constructorsMatrix :: DataEnv -> Int ->
                        SExpr ->
                        [] SExpr ->
                        [] MatchRow ->
                        [] SPattern -> [] MatchRow -> Fresh ((,) SExpr ([] Int));
  constructorsMatrix env column value values rows patterns defaults =
    if not
         (all
            (\p ->
               case constructor p of {
                 Nothing -> False;
                 Just _ -> True
               })
            patterns)
    then freshFail "mixed constructor and literal patterns"
    else do {
           let {
             names =
               nubBy eqString
                 (map
                    (\p ->
                       case constructor p of {
                         Just ((,) c _) -> c;
                         Nothing -> ""
                       })
                    patterns)
           };
           branches <- mapM (constructorBranch env column value values rows patterns) names;
           fallback <-
             if (null defaults || completeConstructorFamily env names)
             then freshPure []
             else do {
                    boundValueShared4 <- matrix env (replace column [] values) defaults;
                    case boundValueShared4 of {
                      (,) body used ->
                        do {
                          freshPure
                            ((:) ((,) (SAlternative (SDefaultPattern Nothing) body) used) [])
                        }
                    }
                  };
           let {
             alternatives = append branches fallback
           };
           freshPure ((,) (SCase value (map fst alternatives)) (concatMap snd alternatives))
         };
  constructorBranch :: DataEnv -> Int ->
                       SExpr ->
                       [] SExpr ->
                       [] MatchRow ->
                       [] SPattern -> String -> Fresh ((,) SAlternative ([] Int));
  constructorBranch env column value values rows patterns name =
    let {
      arities =
        concatMap
          (\p ->
             case constructor p of {
               Just ((,) n ps) -> if eqString name n then (:) (length ps) [] else [];
               Nothing -> []
             })
          patterns
    } in
    case arities of {
      [] -> freshFail "invalid constructor specialization";
      (:) arity rest ->
        if not (all (eqInt arity) rest)
        then freshFail ("constructor pattern arity mismatch: " ++ name)
        else do {
               names <- freshNames arity "matchValue";
               let {
                 specialized = concatMap (specializeRow column value name arity) rows
               };
               boundValueShared5 <- matrix env (replace column (map SVar names) values) specialized;
               case boundValueShared5 of {
                 (,) body used ->
                   do {
                     freshPure
                       ((,) (SAlternative (SConstructorPattern name (map Just names)) body) used)
                   }
               }
             }
    };
  specializeRow :: Int -> SExpr -> String -> Int -> MatchRow -> [] MatchRow;
  specializeRow column value name arity (MatchRow ps b i) =
    let {
      pattern = index ps column
    } in
    case constructor pattern of {
      Just ((,) n fields) ->
        if eqString name n then (:) (MatchRow (replace column fields ps) b i) [] else [];
      Nothing ->
        if isVariable pattern
        then (:)
               (MatchRow (replace column (replicate arity wild) ps) (bindPattern value pattern b) i)
               []
        else []
    };
  isBool :: SPattern -> Bool;
  isBool p =
    case p of {
      SBoolPattern _ -> True;
      _ -> False
    };
  isInt :: SPattern -> Bool;
  isInt p =
    case p of {
      SIntPattern _ -> True;
      _ -> False
    };
  isString :: SPattern -> Bool;
  isString p =
    case p of {
      SStringPattern _ -> True;
      _ -> False
    };
  -- Unlike primitive literals, two distinct overloaded string spellings can
  -- compare equal. Preserve row order and retry ALL later rows when another
  -- column fails; lexical partitioning here silently changes user Eq behavior.
  -- Scalar fast path avoids a surface node per ordinary source character.
  sourceStringExpression :: SourceString -> SExpr;
  sourceStringExpression literal = case literal of {
    ScalarString text -> SApp (SPrimitive PTextToChars) (SStringLit text);
    CharString codes -> foldr
      (\code rest -> SApp (SApp (SConstructor ":")
        (SApp (SPrimitive PCharFromCode) (SIntLit code))) rest)
      (SConstructor "[]") codes
  };
  eqSourceString :: SourceString -> SourceString -> Bool;
  eqSourceString a b = case a of {
    ScalarString x -> case b of { ScalarString y -> eqString x y; _ -> False };
    CharString x -> case b of { CharString y -> eqList eqInt x y; _ -> False }
  };
  overloadedStringMatrix :: DataEnv -> Int -> [] SExpr -> [] MatchRow -> Fresh ((,) SExpr ([] Int));
  overloadedStringMatrix env column values rows =
    case rows of {
      [] -> freshFail "non-exhaustive patterns";
      (:) (MatchRow patterns body rowIndex) rest ->
        case index patterns column of {
          SOverloadedStringPattern text equality conversion -> do {
            fallbackResult <- matrix env values rest;
            case fallbackResult of {
              (,) fallback usedRest -> do {
                matchedResult <- matrix env values
                  ((:) (MatchRow (replace column ((:) wild []) patterns) body rowIndex)
                    ((:) (MatchRow (replicate (length values) wild) fallback (-1)) []));
                case matchedResult of {
                  (,) matched usedMatch ->
                    freshPure ((,)
                      (choose (SApp (SApp (SVar equality) (index values column))
                                (SApp (SVar conversion) (sourceStringExpression text)))
                         matched fallback)
                      (append (filter (\i -> i /= (-1)) usedMatch) usedRest))
                }
              }
            }
          };
          _ -> freshFail "invalid overloaded string pattern row"
        }
    };
  isOverloadedString :: SPattern -> Bool;
  isOverloadedString p =
    case p of {
      SOverloadedStringPattern _ _ _ -> True;
      _ -> False
    };
  eqLiteral :: SPattern -> SPattern -> Bool;
  eqLiteral p q =
    case p of {
      SIntPattern n ->
        case q of {
          SIntPattern m -> (n == m);
          _ -> False
        };
      SOverloadedStringPattern n eq from ->
        case q of {
          SOverloadedStringPattern m eq2 from2 ->
            (eqSourceString n m && (eqString eq eq2 && eqString from from2));
          _ -> False
        };
      SStringPattern n ->
        case q of {
          SStringPattern m -> eqString n m;
          _ -> False
        };
      SBoolPattern n ->
        case q of {
          SBoolPattern m -> if n then m else not m;
          _ -> False
        };
      _ -> False
    };
  literalBranch :: DataEnv -> Int -> [] SExpr -> [] MatchRow -> SPattern -> Fresh ((,) SExpr ([] Int));
  literalBranch env column values rows literal =
    let {
      value = index values column
    } in
    matrix env (replace column [] values)
      (concatMap
         (\(MatchRow ps b i) ->
            let {
              p = index ps column
            } in
            if (eqLiteral p literal || isVariable p)
            then (:) (MatchRow (replace column [] ps) (bindPattern value p b) i) []
            else [])
         rows);
  literalMatrix :: DataEnv -> Int ->
                   [] SExpr ->
                   [] MatchRow ->
                   [] MatchRow ->
                   [] SPattern ->
                   (SPattern -> Bool) ->
                   SExpr -> (SPattern -> SExpr) -> Fresh ((,) SExpr ([] Int));
  literalMatrix env column values rows defaults patterns predicate equality literalValue =
    if not (all predicate patterns)
    then freshFail "mixed literal pattern types"
    else do {
           fallback <- matrix env (replace column [] values) defaults;
           foldM
             (\((,) rest used) pattern ->
                do {
                  boundValueShared6 <- literalBranch env column values rows pattern;
                  case boundValueShared6 of {
                    (,) body nextUsed ->
                      do {
                        let {
                          condition =
                            SApp (SApp equality (index values column))
                              (literalValue pattern)
                        };
                        freshPure ((,) (choose condition body rest) (append used nextUsed))
                      }
                  }
                })
             fallback
             (reverse (nubBy eqLiteral patterns))
         };
  choose :: SExpr -> SExpr -> SExpr -> SExpr;
  choose condition yes no = SApp (SApp (SApp (SPrimitive PIfThenElse) condition) yes) no
}
