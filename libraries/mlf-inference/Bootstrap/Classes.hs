-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Classes where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as I;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Kinding as K;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.X.Pretty as Pretty;
  data Info = Info SClassDecl String String ([] ((,) String String)) ([] String);
  data InstanceHead = HVar String | HCon String ([] InstanceHead);
  -- Managed implicit evidence is deliberately not a class or an instance.
  callStackPredicate :: String;
  callStackPredicate = "MLFHasCallStack";
  callStackEvidenceType :: SType;
  callStackEvidenceType = SCon "MLFStackEvidence" [];
  callStackScopeKey :: String;
  callStackScopeKey = "$managedCallStack";
  isCallStackPredicate :: SPredicate -> Bool;
  isCallStackPredicate (SPredicate name _) = eqString name callStackPredicate;
  methodEvidenceType :: SType -> Either String SType;
  methodEvidenceType ty =
    case ty of {
      SForall flag name bound body ->
        mapEither (SForall flag name bound) (methodEvidenceType body);
      SQualified predicates body ->
        do {
          traverseEither
            (\(SPredicate name arguments) ->
               ensure (eqString name callStackPredicate && null arguments)
                 "only managed HasCallStack constraints are supported in class methods")
            predicates;
          result <- methodEvidenceType body;
          Right (foldr (\_ rest -> SArrow callStackEvidenceType rest) result predicates)
        };
      _ -> do {
             ensure (not (qualified ty))
               "managed method constraints must occur outside the method body type";
             Right ty
           }
    };
  -- Preserve the existing class-free MLF path unless managed evidence is used.
  managedType :: SType -> Bool;
  managedType ty = case ty of {
    SQualified ps body -> any isCallStackPredicate ps || managedType body;
    SForall _ _ bound body -> managedType bound || managedType body;
    SArrow a b -> managedType a || managedType b;
    STypeApp a b -> managedType a || managedType b;
    SCon _ args -> any managedType args;
    _ -> False
  };
  managedExpression :: SExpr -> Bool;
  managedExpression expression = case expression of {
    SSourceDefinition body -> managedExpression body;
    SCallSite _ _ body -> managedExpression body;
    SVar name -> eqString name "$MLF.Stack.callStack";
    SLam _ annotation body ->
      (case annotation of { Nothing -> False; Just (SAnnotation _ ty) -> managedType ty }) || managedExpression body;
    SApp a b -> managedExpression a || managedExpression b;
    SLet _ a b -> managedExpression a || managedExpression b;
    SAnn body (SAnnotation _ ty) -> managedType ty || managedExpression body;
    SCase body branches -> managedExpression body || any (\(SAlternative _ rhs) -> managedExpression rhs) branches;
    SLetRec definitions body -> managedExpression body ||
      any (\((,,) _ (SAnnotation _ ty) rhs) -> managedType ty || managedExpression rhs) definitions;
    SChecked ty body -> managedType ty || managedExpression body;
    SDo _ _ -> managedExpression (Desugar.desugarDo expression);
    SEquations rows -> any (\((,) _ body) -> managedExpression body) rows;
    _ -> False
  };
  -- Locations are observable only through managed evidence. The class-free
  -- path removes them without changing annotations or ordinary MLF inference.
  eraseCallSites :: SExpr -> SExpr;
  eraseCallSites expression = case expression of {
    SSourceDefinition body -> eraseCallSites body;
    SCallSite _ _ body -> eraseCallSites body;
    SLam name annotation body -> SLam name annotation (eraseCallSites body);
    SApp a b -> SApp (eraseCallSites a) (eraseCallSites b);
    SLet name a b -> SLet name (eraseCallSites a) (eraseCallSites b);
    SAnn body annotation -> SAnn (eraseCallSites body) annotation;
    SCase body branches -> SCase (eraseCallSites body)
      (map (\(SAlternative pattern rhs) -> SAlternative pattern (eraseCallSites rhs)) branches);
    SLetRec definitions body -> SLetRec
      (map (\((,,) name annotation rhs) -> (,,) name annotation (eraseCallSites rhs)) definitions)
      (eraseCallSites body);
    SChecked ty body -> SChecked ty (eraseCallSites body);
    SDo statements body -> SDo (map eraseStatementCallSites statements) (eraseCallSites body);
    SSharedBind pattern action continuation bindExpression failure ->
      SSharedBind pattern (eraseCallSites action) (eraseCallSites continuation)
        (eraseCallSites bindExpression) (eraseCallSites failure);
    SEquations rows -> SEquations (map (\((,) patterns body) -> (,) patterns (eraseCallSites body)) rows);
    _ -> expression
  };
  eraseStatementCallSites :: SStatement -> SStatement;
  eraseStatementCallSites statement = case statement of {
    SDoBind pattern value -> SDoBind pattern (eraseCallSites value);
    SDoThen value -> SDoThen (eraseCallSites value);
    SDoLet name annotation value -> SDoLet name annotation (eraseCallSites value);
    SDoLetRec definitions -> SDoLetRec
      (map (\((,,) name annotation rhs) -> (,,) name annotation (eraseCallSites rhs)) definitions)
  };
  className :: SClassDecl -> String;
  className (SClassDecl n _ _ _) = n;
  classParameters :: SClassDecl -> [] ((,) String Kind);
  classParameters (SClassDecl _ ps _ _) = ps;
  superclasses :: SClassDecl -> [] SPredicate;
  superclasses (SClassDecl _ _ ps _) = ps;
  classMethods :: SClassDecl -> [] ((,) String SType);
  classMethods (SClassDecl _ _ _ ms) = ms;
  instanceVariables :: SInstanceDecl -> [] ((,) String Kind);
  instanceVariables (SInstanceDecl vs _ _ _ _) = vs;
  instanceContext :: SInstanceDecl -> [] SPredicate;
  instanceContext (SInstanceDecl _ ps _ _ _) = ps;
  instanceClass :: SInstanceDecl -> String;
  instanceClass (SInstanceDecl _ _ c _ _) = c;
  instanceHead :: SInstanceDecl -> [] SType;
  instanceHead (SInstanceDecl _ _ _ ts _) = ts;
  instanceMethods :: SInstanceDecl -> [] ((,) String SExpr);
  instanceMethods (SInstanceDecl _ _ _ _ ms) = ms;
  lookupInfo :: Map String Info -> String -> Either String Info;
  lookupInfo infos name =
    case M.lookup compareString name infos of {
      Nothing -> Left ("unknown class: " ++ name);
      Just info -> Right info
    };
  dictionary :: Map String Info -> SPredicate -> Either String SType;
  dictionary infos (SPredicate name arguments) =
    if eqString name callStackPredicate
    then do {
           ensure (null arguments) "HasCallStack takes no type arguments";
           Right callStackEvidenceType
         }
    else do {
      boundValueShared1 <- lookupInfo infos name;
      case boundValueShared1 of {
        Info _ ty _ _ _ ->
          do {
            Right (SCon ty arguments)
          }
      }
    };
  bottom :: Kind -> SType;
  bottom k =
    case k of {
      Star -> SBottom;
      _ -> SBottomKind k
    };
  quantify :: [] ((,) String Kind) -> SType -> SType;
  quantify variables ty = foldr (\((,) n k) b -> SForall Flexible n (bottom k) b) ty variables;
  freeType :: SType -> [] String;
  freeType ty = sortBy compareString (nubBy eqString (freeTypeRaw ty));
  freeTypeRaw :: SType -> [] String;
  freeTypeRaw ty =
    case ty of {
      STVar a -> (:) a [];
      SArrow a b -> append (freeTypeRaw a) (freeTypeRaw b);
      STypeApp a b -> append (freeTypeRaw a) (freeTypeRaw b);
      SCon _ ts -> concatMap freeTypeRaw ts;
      SForall _ a bound body ->
        append (freeTypeRaw bound) (filter (\n -> not (eqString a n)) (freeTypeRaw body));
      SQualified predicates body ->
        append (freeTypeRaw body)
          (concatMap (\(SPredicate _ args) -> concatMap freeTypeRaw args) predicates);
      _ -> []
    };
  unique :: String -> [] String -> Either String ();
  unique label names =
    ensure (length names == length (nubBy eqString names)) ("duplicate " ++ label);
  scheme :: SType -> (,,) ([] ((,,) Flag String SType)) ([] SPredicate) SType;
  scheme ty =
    case ty of {
      SForall flag name bound body ->
        case scheme body of {
          (,,) variables predicates result ->
            (,,) ((:) ((,,) flag name bound) variables) predicates result
        };
      SQualified predicates body -> (,,) [] predicates body;
      _ -> (,,) [] [] ty
    };
  qualified :: SType -> Bool;
  qualified ty =
    case ty of {
      SQualified _ _ -> True;
      SForall _ _ a b -> (qualified a || qualified b);
      SArrow a b -> (qualified a || qualified b);
      STypeApp a b -> (qualified a || qualified b);
      SCon _ ts -> any qualified ts;
      _ -> False
    };
  translateScheme :: DataEnv -> Map String Info -> SType -> Either String SType;
  translateScheme ds infos ty =
    case scheme ty of {
      (,,) variables predicates body ->
        do {
          ensure (not (qualified body || any (\((,,) _ _ bound) -> qualified bound) variables))
            "class constraints must occur at the outside of a type scheme";
          scope <-
            foldEither
              (\env ((,,) _ a bound) ->
                 do {
                   kind <- K.kindOf ds env bound;
                   Right (M.insert compareString a kind env)
                 })
              M.empty
              variables;
          traverseEither (checkPredicate ds infos scope) predicates;
          args <- traverseEither (dictionary infos) predicates;
          let {
            result =
              foldr (\((,,) flag a bound) rest -> SForall flag a bound rest)
                (foldr SArrow body args)
                variables
          };
          K.annotationType ds M.empty result;
          Right result
        }
    };
  checkPredicate :: DataEnv ->
                    Map String Info -> Map String Kind -> SPredicate -> Either String ();
  checkPredicate ds infos scope (SPredicate name arguments) =
    if eqString name callStackPredicate
    then ensure (null arguments) "HasCallStack takes no type arguments"
    else do {
      boundValueShared2 <- lookupInfo infos name;
      case boundValueShared2 of {
        Info declaration _ _ _ _ ->
          do {
            let {
              parameters = classParameters declaration
            };
            ensure (length arguments == length parameters)
              ("class argument arity mismatch: " ++
               (name ++
                (" expects " ++
                 (showInt (length parameters) ++ (", got " ++ showInt (length arguments))))));
            actual <- traverseEither (K.kindOf ds scope) arguments;
            ensure (eqList eqKind actual (map snd parameters))
              ("class parameter kind mismatch: " ++ name)
          }
      }
    };
  field :: SType -> Either String Field;
  field ty = do { translated <- methodEvidenceType ty; fieldType translated };
  fieldType :: SType -> Either String Field;
  fieldType ty =
    case ty of {
      STVar a -> Right (Parameter a);
      SArrow a b ->
        do {
          x <- fieldType a;
          y <- fieldType b;
          Right (Function x y)
        };
      STypeApp f a ->
        do {
          x <- fieldType f;
          y <- fieldType a;
          Right (Application x y)
        };
      SCon c args -> mapEither (Applied c) (traverseEither fieldType args);
      SForall Flexible a SBottom body -> mapEither (Quantified a Star) (fieldType body);
      SForall Flexible a (SBottomKind k) body -> mapEither (Quantified a k) (fieldType body);
      _ ->
        Left
          "class methods require ordinary forall signatures without bounded or nested class constraints"
    };
  lowerClasses :: SProgram -> Either String ((,) SProgram (Map String String));
  lowerClasses original = lowerClassesWithImports S.empty original;
  lowerClassesWithImports :: Set String ->
                             SProgram -> Either String ((,) SProgram (Map String String));
  lowerClassesWithImports imported original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses imported M.empty Nothing program
    };
  lowerClassesWithScopes :: Map String IntSet ->
                            [] IntSet ->
                            SProgram -> Either String ((,) SProgram (Map String String));
  lowerClassesWithScopes values instances original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses S.empty values (Just instances) program
    };
  lowerCoreClasses :: Set String ->
                      Map String IntSet ->
                      Maybe ([] IntSet) ->
                      SProgram -> Either String ((,) SProgram (Map String String));
  lowerCoreClasses imported valueIndices instanceIndices program =
    lowerCoreClassesWith Nothing imported valueIndices instanceIndices program;
  lowerSeparateClasses externals instanceNames original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds [] [] b;
             _ -> original
           });
      case program of {
        SClassProgram ds [] [] body ->
          if managedExpression body || any managedType (M.elems externals)
          then lowerCoreClassesWith (Just ((,) externals instanceNames)) S.empty M.empty Nothing program
          else let {
            parameters =
              map
                (\((,) n ty) ->
                   (,,) n (SAnnotation [] ty)
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                (M.toList externals)
          } in
          Right
            ((,) (SProgram ds (if null parameters then eraseCallSites body
                               else SLetRec parameters (eraseCallSites body)))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just ((,) externals instanceNames)) S.empty M.empty Nothing program
      }
    };
  -- Crate lowering has a complete declaration/instance inventory, but candidate
  -- visibility remains that of each declaration's defining module. Stable
  -- dictionary names make the lowered declarations reusable inference queries.
  lowerSeparateClassesWithScopes :: Map String SType ->
                                    [] String ->
                                    Map String IntSet ->
                                    [] IntSet ->
                                    SProgram -> Either String ((,) SProgram (Map String String));
  lowerSeparateClassesWithScopes externals instanceNames valueScopes instanceScopes original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds [] [] b;
             _ -> original
           });
      case program of {
        SClassProgram ds [] [] body ->
          if managedExpression body || any managedType (M.elems externals)
          then lowerCoreClassesWith (Just ((,) externals instanceNames)) S.empty valueScopes (Just instanceScopes) program
          else let {
            parameters =
              map
                (\((,) n ty) ->
                   (,,) n (SAnnotation [] ty)
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked crate parameter"))))
                (M.toList externals)
          } in
          Right
            ((,) (SProgram ds (if null parameters then eraseCallSites body
                               else SLetRec parameters (eraseCallSites body)))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just ((,) externals instanceNames)) S.empty valueScopes
            (Just instanceScopes)
            program
      }
    };
  lowerCoreClassesWith :: Maybe ((,) (Map String SType) ([] String)) ->
                          Set String ->
                          Map String IntSet ->
                          Maybe ([] IntSet) ->
                          SProgram -> Either String ((,) SProgram (Map String String));
  lowerCoreClassesWith config imported valueIndices instanceIndices program =
    case program of {
      SProgram ds body ->
        case config of {
          Nothing ->
            if managedExpression body
            then lowerCoreClassesWith config imported valueIndices instanceIndices
                   (SClassProgram ds [] [] body)
            else Right ((,) (SProgram ds (eraseCallSites body)) M.empty);
          Just _ ->
            lowerCoreClassesWith config imported valueIndices instanceIndices
              (SClassProgram ds [] [] body)
        };
      SClassProgram datatypes declarations instances body ->
        withValidatedClasses config imported valueIndices instanceIndices datatypes declarations
          instances body (\base classes ->
            lowerClassesBody config imported valueIndices instanceIndices datatypes instances body
              base classes)
    };
  withValidatedClasses :: forall a.
    Maybe ((,) (Map String SType) ([] String)) -> Set String ->
    Map String IntSet -> Maybe ([] IntSet) -> [] DataDecl -> [] SClassDecl ->
    [] SInstanceDecl -> SExpr -> (DataEnv -> [] SClassDecl -> Fresh a) -> Either String a;
  withValidatedClasses config imported valueIndices instanceIndices datatypes declarations instances body action =
    do {
          case instanceIndices of {
            Nothing -> Right ();
            Just scopes ->
              ensure (length scopes == length instances) "module instance scope count mismatch"
          };
          base <- D.validateDeclarations datatypes;
          unique "class" (map className declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then []
                  else map fst (classMethods d))
               declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then map fst (classMethods d)
                  else [])
               declarations);
          traverseEither
            (\d ->
               do {
                 ensure (not (eqString (className d) callStackPredicate))
                   "HasCallStack is a compiler-managed constraint, not a class";
                 unique "class method" (map fst (classMethods d));
                 unique "class parameter" (map fst (classParameters d));
                 ensure (not (null (classParameters d))) "class must have at least one parameter"
               })
            declarations;
          let {
            classes = map implicitParameters declarations
          };
          let {
            used =
              append (Desugar.allNames body)
                (append
                   (concatMap
                      (\i -> concatMap (\((,) _ e) -> Desugar.allNames e) (instanceMethods i))
                      instances)
                   (append
                      (concatMap
                         (\d ->
                            (:) (D.datatypeName d)
                              (map D.constructorName (D.datatypeConstructors d)))
                         datatypes)
                      (concatMap
                         (\d ->
                            (:) (className d)
                              (append (map fst (classParameters d))
                                 (concatMap (\((,) n ty) -> (:) n (typeNames ty))
                                    (classMethods d))))
                         declarations)))
          };
      runFresh used (action base classes)
    };
  -- Same class/instance validation and Fresh reservation as the existing whole
  -- program route, but stop before source evidence applications are expanded.
  prepareScopedClassInventory :: Map String SType -> [] String -> Map String IntSet ->
                                 [] IntSet -> SProgram -> Either String ClassInventory;
  prepareScopedClassInventory externals instanceNames valueScopes instanceScopes original =
    withScopedClassInventory externals instanceNames valueScopes instanceScopes original freshPure;
  withScopedClassInventory :: forall a. Map String SType -> [] String -> Map String IntSet ->
                              [] IntSet -> SProgram -> (ClassInventory -> Fresh a) -> Either String a;
  withScopedClassInventory externals instanceNames valueScopes instanceScopes original action =
    do {
      surface <- Surface.lowerSurface (case original of {
        SProgram ds body -> SClassProgram ds [] [] body;
        _ -> original
      });
      case surface of {
        SClassProgram ds declarations instances body ->
          withValidatedClasses (Just ((,) externals instanceNames)) S.empty valueScopes
            (Just instanceScopes) ds declarations instances body
            (\base classes -> do {
              inventory <- prepareClassesBody (Just ((,) externals instanceNames)) S.empty
                valueScopes (Just instanceScopes) ds instances base classes;
              action inventory
            });
        _ -> Left "source class inventory requires a class program"
      }
    };
  implicitParameters :: SClassDecl -> SClassDecl;
  implicitParameters (SClassDecl name parameters supers methods) =
    SClassDecl name parameters supers
      (map
         (\((,) n ty) ->
            (,) n
              (quantify
                 (map (\a -> (,) a Star) (Surface.without (freeType ty) (map fst parameters)))
                 ty))
         methods);
  typeNames :: SType -> [] String;
  typeNames ty =
    case ty of {
      STVar n -> (:) n [];
      SCon n ts -> (:) n (concatMap typeNames ts);
      SForall _ n a b -> (:) n (append (typeNames a) (typeNames b));
      SArrow a b -> append (typeNames a) (typeNames b);
      STypeApp a b -> append (typeNames a) (typeNames b);
      SQualified ps t ->
        append (concatMap (\(SPredicate n ts) -> (:) n (concatMap typeNames ts)) ps) (typeNames t);
      _ -> []
    };
  separateName config stable prefix =
    case config of {
      Nothing -> freshName prefix;
      Just _ -> freshPure stable
    };
  -- Prepared class support is immutable; source bodies have not been lowered.
  data ClassInventory = ClassInventory
    ([] DataDecl) DataEnv (Map String Info)
    (Map String ([] ((,) EvidenceRole String)))
    ([] ((,) EvidenceRole String))
    (Map String ((,) String ([] String)))
    ([] ((,,) String SAnnotation SExpr)) (Map String String) (Map String SType);
  prepareClassesBody :: Maybe ((,) (Map String SType) ([] String)) ->
                        Set String -> Map String IntSet -> Maybe ([] IntSet) ->
                        [] DataDecl -> [] SInstanceDecl -> DataEnv -> [] SClassDecl ->
                        Fresh ClassInventory;
  prepareClassesBody config imported valueIndices instanceIndices datatypes instances base classes =
    do {
      entries <-
        mapM
          (\declaration ->
             do {
               dict <-
                 separateName config ("Dict_" ++ className declaration)
                   ("Dict" ++ className declaration);
               ctor <-
                 separateName config ("Make_" ++ className declaration)
                   ("Make" ++ className declaration);
               methods <-
                 mapM
                   (\((,) n _) ->
                      do {
                        selector <-
                          separateName config ("select_" ++ n) ("select" ++ className declaration);
                        freshPure ((,) n selector)
                      })
                   (classMethods declaration);
               supers <-
                 mapM
                   (\i ->
                      separateName config
                        ("super_" ++ (className declaration ++ ("_" ++ showInt i)))
                        "superclass")
                   (range 0 (length (superclasses declaration) - 1));
               freshPure ((,) (className declaration) (Info declaration dict ctor methods supers))
             })
          classes;
      let {
        infos = M.fromList compareString entries
      };
      freshLift (validateClasses base infos);
      dictionaries <-
        freshLift (traverseEither (\entry -> dictionaryDecl infos (snd entry)) entries);
      ds <- freshLift (D.validateDeclarations (append datatypes dictionaries));
      checkedInstances <- freshLift (traverseEither (validateInstance ds infos) instances);
      freshLift (checkOverlap checkedInstances);
      names <-
        case config of {
          Nothing -> mapM (\inst -> freshName "instanceDictionary") checkedInstances;
          Just ((,) _ ns) ->
            do {
              freshLift
                (ensure (length ns == length checkedInstances)
                   "separate instance identity count mismatch");
              freshPure ns
            }
        };
      let {
        supers =
          concatMap (\((,) _ (Info _ _ _ _ ns)) -> map (\n -> (,) SuperclassEvidence n) ns)
            entries
      };
      let {
        globalCandidates = append (map (\n -> (,) InstanceEvidence n) names) supers
      };
      let {
        select = selectCandidates names supers
      };
      let {
        valueScopes = M.map select valueIndices
      };
      let {
        instanceScopes =
          case instanceIndices of {
            Nothing -> replicate (length instances) globalCandidates;
            Just scopes -> map select scopes
          }
      };
      let {
        externalSchemes =
          case config of {
            Nothing -> M.empty;
            Just ((,) es _) -> es
          }
      };
      let {
        baseMethodEnv = M.union compareString (methodBindings imported False entries)
          (methodBindings imported True entries)
      };
      let {
        methodEnv = withExternalOverloads externalSchemes baseMethodEnv
      };
      selectorGroups <- mapM (\entry -> selectorDefinitions infos (snd entry)) entries;
      definitions <-
        mapM
          (\((,) ((,) name inst) available) ->
             instanceDefinition valueScopes ds infos methodEnv name inst available)
          (zip (zip names checkedInstances) instanceScopes);
      let {
        bindings =
          map
            (\((,,) n annotation rhs) ->
               case annotation of {
                 SAnnotation _ ty -> (,,) n annotation (SChecked ty rhs)
               })
            (append (concat selectorGroups) definitions)
      };
      let {
        localBindings =
          filter (\((,,) n _ _) -> not (M.member compareString n externalSchemes)) bindings
      };
      let {
        display = M.insert compareString "MLFStackEvidence" callStackPredicate
          (M.fromList compareString
            (map (\((,) name (Info _ dict _ _ _)) -> (,) dict name) entries))
      };
      freshPure (ClassInventory (append datatypes dictionaries) ds infos valueScopes
        globalCandidates baseMethodEnv localBindings display externalSchemes)
    };
  lowerClassesBody :: Maybe ((,) (Map String SType) ([] String)) ->
                      Set String ->
                      Map String IntSet ->
                      Maybe ([] IntSet) ->
                      [] DataDecl ->
                      [] SInstanceDecl ->
                      SExpr ->
                      DataEnv -> [] SClassDecl -> Fresh ((,) SProgram (Map String String));
  lowerClassesBody config imported valueIndices instanceIndices datatypes instances body base classes =
    do {
      inventory <- prepareClassesBody config imported valueIndices instanceIndices
        datatypes instances base classes;
      finishClassesBody inventory body
    };
  finishClassesBody :: ClassInventory -> SExpr ->
                       Fresh ((,) SProgram (Map String String));
  finishClassesBody (ClassInventory datatypes ds infos valueScopes globalCandidates
                     baseMethodEnv localBindings display externalSchemes) body =
    do {
      let { methodEnv = withExternalOverloads externalSchemes baseMethodEnv };
      boundValueShared3 <- lowerExpr valueScopes ds infos methodEnv globalCandidates body;
      case boundValueShared3 of {
        (,) expression wants ->
          do {
            let {
              result = closeWants infos globalCandidates wants expression
            };
            let {
              inner = if null localBindings then result else SLetRec localBindings result
            };
            externalBindings <-
              mapM
                (\((,) n ty) ->
                   do {
                     translated <- freshLift (translateScheme ds infos ty);
                     freshPure
                       ((,,) n (SAnnotation [] translated)
                          (SChecked translated
                             (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                   })
                (M.toList externalSchemes);
            let {
              output = if null externalBindings then inner else SLetRec externalBindings inner
            };
            freshPure ((,) (SProgram datatypes output) display)
          }
      }
    };
  -- Narrow source-root seam. Eligibility/SCC ownership is supplied separately
  -- by the source scheduler; this function records rather than guesses slots.
  data SourceRootLowering = SourceRootLowering SExpr
    ([] ((,,) String String String)) ([] ((,) EvidenceRole String)) Bool;
  lowerUnsignedSourceRoot :: ClassInventory -> Map String SType -> String -> SExpr ->
                             Fresh SourceRootLowering;
  lowerUnsignedSourceRoot inventory externals name original =
    lowerUnsignedSourceRootWithOverloads inventory
      (withExternalOverloads externals M.empty) name original;
  -- Explicit finalized overload order and checked target types travel together
  -- in the scheduler. This stage needs only the former; inference consumes the
  -- latter directly without guessing qualifications from dictionary arrows.
  lowerUnsignedSourceRootWithOverloads :: ClassInventory ->
    Map String ((,) String ([] String)) -> String -> SExpr -> Fresh SourceRootLowering;
  lowerUnsignedSourceRootWithOverloads inventory overloads name original =
    lowerUnsignedSourceRootProtected inventory overloads M.empty name original;
  lowerUnsignedSourceRootProtected :: ClassInventory ->
    Map String ((,) String ([] String)) -> Map String Bool -> String -> SExpr ->
    Fresh SourceRootLowering;
  lowerUnsignedSourceRootProtected
    (ClassInventory _ ds infos valueScopes _ baseMethodEnv _ _ _) overloads protected name original =
    do {
      body <- freshLift (Surface.lowerExpressionWithData ds original);
      candidates <- freshLift
        (case M.lookup compareString name valueScopes of {
          Nothing -> Left "source root has no authenticated definition scope";
          Just available -> Right available
        });
      let { environment = M.union compareString overloads baseMethodEnv };
      reserveSourceNames ((:) name (append (Desugar.allNames body)
        (append (M.keys environment) (append (map fst (M.elems environment)) (map snd candidates)))));
      let { usesManaged = protectedSourceBody environment protected body };
      lowered <- lowerExpr valueScopes ds infos environment candidates body;
      case lowered of {
        (,) rhs wanted -> do {
          labels <- mapM
            (\((,) binder classIdentity) -> do {
              info <- freshLift (lookupInfo infos classIdentity);
              case info of {
                Info _ dictionaryIdentity _ _ _ ->
                  freshPure ((,,) binder classIdentity dictionaryIdentity)
              }
            }) wanted;
          freshPure (SourceRootLowering
            (foldr (\((,) binder _) rest -> SLam binder Nothing rest) rhs wanted)
            labels candidates usesManaged)
        }
      }
    };
  -- Fallback retains original signed/SCC contracts without reinserting support
  -- definitions. Unsigned protected singletons keep their issued slot order.
  lowerSourceGroupUnchanged :: ClassInventory -> Map String ((,) String ([] String)) ->
    Map String Bool -> [] ((,,) String (Maybe SAnnotation) SExpr) ->
    Fresh ((,) SExpr ([] ((,,) String ([] String) Bool)));
  lowerSourceGroupUnchanged inventory overloads protected members =
    case inventory of {
      ClassInventory _ ds infos valueScopes candidates methods _ _ _ -> do {
      original <- freshLift (Surface.bindValues members (SConstructor "()"));
      freshLift (traverseEither
        (\((,,) name _ _) -> ensure (M.member compareString name valueScopes)
          "source group member has no authenticated definition scope") members);
      case members of {
        (:) ((,,) name Nothing rhs) [] -> do {
          root <- lowerUnsignedSourceRootProtected inventory overloads protected name rhs;
          case root of {
            SourceRootLowering body labels _ managed ->
              freshPure ((,) (SLet name body (SConstructor "()"))
                ((:) ((,,) name (map (\((,,) _ c _) -> c) labels) managed) []))
          }
        };
        (:) ((,,) name (Just (SAnnotation ((:) variable variables) ty)) rhs) [] -> do {
          root <- lowerUnsignedSourceRootProtected inventory overloads protected name
            (SAnn rhs (SAnnotation ((:) variable variables) ty));
          case root of {
            SourceRootLowering body labels _ managed ->
              freshPure ((,) (SLet name body (SConstructor "()"))
                ((:) ((,,) name (map (\((,,) _ c _) -> c) labels) managed) []))
          }
        };
        _ -> do {
          freshLift (traverseEither
            (\((,,) _ annotation _) -> case annotation of {
              Nothing -> Left "non-singleton fallback requires original signed declarations";
              Just _ -> Right ()
            }) members);
          surface <- freshLift (Surface.lowerExpressionWithData ds original);
          let {
            declaredOverloads = M.fromList compareString
              (map (\((,,) name annotation _) ->
                (,) name ((,) name (case annotation of {
                  Just (SAnnotation _ ty) -> case scheme ty of {
                    (,,) _ ps _ -> map (\(SPredicate c _) -> c) ps
                  };
                  Nothing -> []
                }))) members)
          };
          let { environment = M.union compareString declaredOverloads
            (M.union compareString overloads methods) };
          protection <- freshLift (traverseEither
            (\((,,) _ annotation rhs) -> do {
              normalized <- Surface.lowerExpressionWithData ds rhs;
              Right ((case annotation of {
                Just (SAnnotation _ ty) -> managedType ty;
                Nothing -> False
              }) || protectedSourceBody environment protected normalized)
            }) members);
          let { groupProtected = any (\flag -> flag) protection };
          reserveSourceNames (append (Desugar.allNames surface)
            (append (M.keys environment) (append (map fst (M.elems environment)) (map snd candidates))));
          lowered <- lowerExpr valueScopes ds infos environment candidates surface;
          case lowered of {
            (,) body wants -> do {
              freshLift (ensure (null wants) "signed source group leaked ordinary obligations");
              let {
                contracts = map
                  (\((,,) name annotation rhs) -> case annotation of {
                    Just (SAnnotation _ ty) ->
                      case scheme ty of {
                        (,,) _ ps _ -> (,,) name (map (\(SPredicate c _) -> c) ps)
                          groupProtected
                      };
                    Nothing -> (,,) name [] True
                  }) members
              };
              freshPure ((,) body contracts)
            }
          }
        }
      }
      }
    };
  reserveSourceNames :: [] String -> Fresh ();
  reserveSourceNames names = Fresh (\count used ->
    Right ((,,) () count (foldlStrict (\acc name -> S.insert compareString name acc) used names)));
  protectedSourceBody :: Map String ((,) String ([] String)) -> Map String Bool -> SExpr -> Bool;
  protectedSourceBody environment protected body =
    managedExpression body || any
      (\reference -> M.findWithDefault compareString False reference protected ||
        case M.lookup compareString reference environment of {
          Nothing -> False;
          Just ((,) _ predicates) -> any (\predicate -> eqString predicate callStackPredicate) predicates
        }) (Surface.freeNames body);
  -- Metadata is derived before class expansion, including original instance
  -- methods. It cannot be recovered from a plain result target type.
  inventorySourceProtection :: ClassInventory -> [] ((,) String SInstanceDecl) ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String (Map String Bool);
  inventorySourceProtection inventory@(ClassInventory _ _ _ _ _ _ _ _ externals)
    instances members = do {
      ensure (M.size externals == 0)
        "builtin protection analysis requires a closed inventory";
      inventoryProtection inventory M.empty instances members
    };
  -- Imported protection is explicit metadata, never inferred false from a
  -- plain target result type. Extra flags do not grant additional names.
  inventoryProtection :: ClassInventory -> Map String Bool ->
    [] ((,) String SInstanceDecl) -> [] ((,,) String (Maybe SAnnotation) SExpr) ->
    Either String (Map String Bool);
  inventoryProtection (ClassInventory _ ds infos _ _ methods supports _ externals)
    importedProtection instances members = do {
      ensure (all (\name -> M.member compareString name importedProtection) (M.keys externals))
        "imported source protection inventory is incomplete";
      let { names = map (\((,,) name _ _) -> name) members };
      let { supportNames = map (\((,,) name _ _) -> name) supports };
      ensure (length names == S.size (S.fromList compareString names))
        "duplicate source protection binding";
      ensure (not (any (\name -> elem eqString name supportNames) names))
        "source protection binding overlaps generated support";
      sourceNodes <- traverseEither
        (\((,,) name annotation rhs) -> do {
          body <- Surface.lowerExpressionWithData ds rhs;
          Right ((,,) name (case annotation of {
            Nothing -> False; Just (SAnnotation _ ty) -> managedType ty
          }) ((:) body []))
        }) members;
      instanceNodes <- traverseEither
        (\((,) name instanceDecl) -> do {
          info <- lookupInfo infos (instanceClass instanceDecl);
          bodies <- traverseEither (\method -> Surface.lowerExpressionWithData ds (snd method))
            (instanceMethods instanceDecl);
          let { direct = case info of {
            Info declaration _ _ _ _ -> any (\method -> managedType (snd method))
              (classMethods declaration)
          } };
          Right ((,,) name direct bodies)
        }) (filter (\instancePair -> elem eqString (fst instancePair) supportNames) instances);
      let { selectors = map
        (\((,) target predicates) -> (,,) target
          (any (\predicate -> eqString predicate callStackPredicate) predicates) []) (M.elems methods) };
      let { supers = concatMap (\info -> case info of {
        Info _ _ _ _ namesOfSupers -> map (\name -> (,,) name False []) namesOfSupers
      }) (M.elems infos) };
      let { supportNodes = filter (\((,,) name _ _) -> elem eqString name supportNames)
        (append selectors (append supers instanceNodes)) };
      let { recorded = map (\((,,) name _ _) -> name) supportNodes };
      ensure (length recorded == length supportNames &&
        length recorded == S.size (S.fromList compareString recorded) &&
        all (\name -> elem eqString name recorded) supportNames)
        "generated support protection inventory mismatch";
      let { nodes = append sourceNodes supportNodes };
      let { environment = withExternalOverloads externals methods };
      let { uses current body = protectedSourceBody environment current body ||
        any (\reference -> case M.lookup compareString reference environment of {
          Nothing -> False;
          Just ((,) target _) -> M.findWithDefault compareString False target current
        }) (Surface.freeNames body) };
      let { seeds = M.union compareString
        (M.fromList compareString (map (\((,,) name direct _) -> (,) name direct) nodes))
        (M.mapWithKey (\name ty -> managedType ty ||
          M.findWithDefault compareString False name importedProtection) externals) };
      let {
        advance :: Int -> Map String Bool -> Map String Bool;
        advance remaining current =
          if remaining == 0 then current else
            let { next = foldl
              (\result ((,,) name direct bodies) -> M.insert compareString name
                (direct || any (uses current) bodies) result)
              current nodes }
            in if eqList
                 (\((,) name flag) ((,) other oldFlag) ->
                   eqString name other && (if flag then oldFlag else not oldFlag))
                 (M.toList next) (M.toList current)
               then next else advance (remaining - 1) next
      };
      let { complete = advance (length nodes) seeds };
      Right (M.filterWithKey (\name _ ->
        elem eqString name names || elem eqString name supportNames) complete)
    };
  inventoryOrdinaryRegistry :: ClassInventory -> Map String String;
  inventoryOrdinaryRegistry (ClassInventory _ _ infos _ _ _ _ _ _) =
    M.map (\(Info _ dictionaryIdentity _ _ _) -> dictionaryIdentity) infos;
  -- Rebuild imported calling conventions from finalized predecessor contracts.
  -- The fixed selector environment never retains a predecessor occurrence count.
  withExternalOverloads :: Map String SType ->
                           Map String ((,) String ([] String)) ->
                           Map String ((,) String ([] String));
  withExternalOverloads externals methods =
    M.union compareString
      (M.mapWithKey
        (\n ty -> case scheme ty of {
          (,,) _ ps _ -> (,) n (map (\(SPredicate c _) -> c) ps)
        }) externals)
      methods;
  selectCandidates :: [] String ->
                      [] ((,) EvidenceRole String) -> IntSet -> [] ((,) EvidenceRole String);
  selectCandidates names supers indices =
    append
      (concatMap
         (\((,) i n) -> if I.member i indices then (:) ((,) InstanceEvidence n) [] else [])
         (zip (range 0 (length names - 1)) names))
      supers;
  methodBindings :: Set String ->
                    Bool -> [] ((,) String Info) -> Map String ((,) String ([] String));
  methodBindings imported isImported entries =
    M.fromList compareString
      (concatMap
         (\((,) name (Info declaration _ _ methods _)) ->
            if if isImported
               then S.member compareString name imported
               else not (S.member compareString name imported)
            then map
                   (\((,) method selector) ->
                      let {
                        local =
                          case lookup eqString method (classMethods declaration) of {
                            Nothing -> [];
                            Just ty -> case scheme ty of { (,,) _ ps _ -> map (\(SPredicate c _) -> c) ps }
                          }
                      } in (,) method ((,) selector ((:) name local)))
                   methods
            else [])
         entries);
  instanceDefinition :: Map String ([] ((,) EvidenceRole String)) ->
                        DataEnv ->
                        Map String Info ->
                        Map String ((,) String ([] String)) ->
                        String ->
                        SInstanceDecl ->
                        [] ((,) EvidenceRole String) -> Fresh ((,,) String SAnnotation SExpr);
  instanceDefinition valueScopes ds infos methodEnv name inst available =
    do {
      boundValueShared6 <- freshLift (lookupInfo infos (instanceClass inst));
      case boundValueShared6 of {
        Info declaration _ ctor _ _ ->
          do {
            givenNames <- mapM (\p -> freshName "givenDictionary") (instanceContext inst);
            let {
              candidates = append (map (\n -> (,) GivenEvidence n) givenNames) available
            };
            methodBodies <-
              mapM
                (\((,) method methodType) ->
                   do {
                     original <-
                       freshLift
                         (case lookup eqString method (instanceMethods inst) of {
                            Nothing -> Left ("missing instance method: " ++ method);
                            Just e -> Right e
                          });
                     expected <-
                       instantiateMethod
                         (M.fromList compareString
                            (zip (map fst (classParameters declaration)) (instanceHead inst)))
                         methodType;
                     translatedType <- freshLift (methodEvidenceType expected);
                     lowerSignedBody valueScopes ds infos candidates methodEnv original expected translatedType
                   })
                (classMethods declaration);
            superBodies <-
              mapM
                (\(SPredicate c _) ->
                   do {
                     boundValueShared5 <- freshLift (lookupInfo infos c);
                     case boundValueShared5 of {
                       Info _ dict _ _ _ ->
                         do {
                           freshPure (SWanted dict candidates)
                         }
                     }
                   })
                (superclasses declaration);
            contextTypes <- freshLift (traverseEither (dictionary infos) (instanceContext inst));
            resultType <-
              freshLift (dictionary infos (SPredicate (instanceClass inst) (instanceHead inst)));
            let {
              ty = quantify (instanceVariables inst) (foldr SArrow resultType contextTypes)
            };
            let {
              rhs =
                foldr (\n b -> SLam n Nothing b)
                  (foldl SApp (SConstructor ctor) (append superBodies methodBodies))
                  givenNames
            };
            freshPure ((,,) name (SAnnotation [] ty) rhs)
          }
      }
    };
  validateClasses :: DataEnv -> Map String Info -> Either String ();
  validateClasses ds infos =
    do {
      traverseEither
        (\(Info declaration _ _ _ _) ->
           do {
             ensure (not (eqString (className declaration) callStackPredicate))
               "HasCallStack is a compiler-managed constraint, not a class";
             let {
               scope = M.fromList compareString (classParameters declaration)
             };
             ensure (not (any isCallStackPredicate (superclasses declaration)))
               "HasCallStack is not permitted as a superclass";
             traverseEither (checkPredicate ds infos scope) (superclasses declaration);
             traverseEither
               (\((,) name ty) ->
                  do {
                    let {
                      missing = Surface.without (M.keys scope) (freeType ty)
                    };
                    ensure (null missing)
                      ("ambiguous class method: " ++
                       (name ++
                        (" does not mention class parameters " ++ intercalate ", " missing)));
                    translated <- methodEvidenceType ty;
                    K.annotationType ds scope translated;
                    field translated;
                    Right ()
                  })
               (classMethods declaration);
             Right ()
           })
        (M.elems infos);
      traverseEither (visitSuperclass infos []) (M.keys infos);
      Right ()
    };
  visitSuperclass :: Map String Info -> [] String -> String -> Either String ();
  visitSuperclass infos seen name =
    if elem eqString name seen
    then Left ("cyclic superclass hierarchy: " ++ name)
    else do {
           boundValueShared7 <- lookupInfo infos name;
           case boundValueShared7 of {
             Info declaration _ _ _ _ ->
               do {
                 traverseEither (\(SPredicate c _) -> visitSuperclass infos ((:) name seen) c)
                   (superclasses declaration);
                 Right ()
               }
           }
         };
  dictionaryDecl :: Map String Info -> Info -> Either String DataDecl;
  dictionaryDecl infos (Info declaration name ctor _ _) =
    do {
      supers <- traverseEither (dictionary infos) (superclasses declaration);
      fields <- traverseEither field (append supers (map snd (classMethods declaration)));
      Right (DataDeclK name (classParameters declaration) ((:) (ConstructorDecl ctor fields) []))
    };
  selectorDefinitions :: Map String Info -> Info -> Fresh ([] ((,,) String SAnnotation SExpr));
  selectorDefinitions infos (Info declaration dict ctor methods supers) =
    do {
      superTypes <- freshLift (traverseEither (dictionary infos) (superclasses declaration));
      let {
        signatures =
          append (zip supers superTypes)
            (zip (map snd methods) (map snd (classMethods declaration)))
      };
      let {
        parameters = classParameters declaration
      };
      mapM
        (\((,) selected ((,) name ty)) ->
           do {
             d <- freshName "dictionary";
             value <- freshName "methodValue";
             let {
               fields =
                 map (\i -> if (i == selected) then Just value else Nothing)
                   (range 0 (length signatures - 1))
             };
             let {
               rhs =
                 SLam d Nothing
                   (SCase (SVar d)
                      ((:) (SAlternative (SConstructorPattern ctor fields) (SVar value)) []))
             };
             resultType <- freshLift (methodEvidenceType ty);
             let {
               signature =
                 quantify parameters
                   (SArrow (SCon dict (map (\((,) n _) -> STVar n) parameters)) resultType)
             };
             freshPure ((,,) name (SAnnotation [] signature) rhs)
           })
        (zip (range 0 (length signatures - 1)) signatures)
    };
  methodNames :: [] String -> String;
  methodNames names =
    ("[" ++ (intercalate "," (map Pretty.prettyString (sortBy compareString names)) ++ "]"));
  validateInstance :: DataEnv -> Map String Info -> SInstanceDecl -> Either String SInstanceDecl;
  validateInstance ds infos inst =
    do {
      ensure (not (any isCallStackPredicate (instanceContext inst)))
        "HasCallStack is not permitted in an instance context";
      boundValueShared8 <- lookupInfo infos (instanceClass inst);
      case boundValueShared8 of {
        Info declaration _ _ _ _ ->
          do {
            unique "instance method" (map fst (instanceMethods inst));
            let {
              required = map fst (classMethods declaration)
            };
            let {
              supplied = map fst (instanceMethods inst)
            };
            ensure
              (null (Surface.without required supplied) && null (Surface.without supplied required))
              ("instance methods do not match class " ++
               (instanceClass inst ++
                ("; missing " ++
                 (methodNames (Surface.without required supplied) ++
                  ("; unexpected " ++ methodNames (Surface.without supplied required))))));
            unique "instance type variable" (map fst (instanceVariables inst));
            let {
              arguments = instanceHead inst
            };
            let {
              free = sortBy compareString (nubBy eqString (concatMap freeType arguments))
            };
            let {
              explicit = instanceVariables inst
            };
            let {
              vars =
                append explicit (map (\a -> (,) a Star) (Surface.without free (map fst explicit)))
            };
            let {
              scope = M.fromList compareString vars
            };
            ensure (null (Surface.without (map fst vars) free))
              "instance variables must occur in the instance head";
            checkPredicate ds infos scope (SPredicate (instanceClass inst) arguments);
            case arguments of {
              (:) (SCon _ _) [] -> Right ();
              (:) _ [] -> Left "instance head must start with a named type constructor";
              _ -> Right ()
            };
            traverseEither (headType "") arguments;
            traverseEither
              (\predicate ->
                 case predicate of {
                   SPredicate _ args ->
                     do {
                       ensure (null (Surface.without (concatMap freeType args) free))
                         "instance context has a variable absent from the head";
                       checkPredicate ds infos scope predicate;
                       ensure
                         ((sumCounts (map typeSize args) < sumCounts (map typeSize arguments)) &&
                          all
                            (\a ->
                               (sumCounts (map (occurrences a) args) <=
                                sumCounts (map (occurrences a) arguments)))
                            free)
                         "instance context must be structurally smaller than its head"
                     }
                 })
              (instanceContext inst);
            Right
              (SInstanceDecl vars (instanceContext inst) (instanceClass inst) arguments
                 (instanceMethods inst))
          }
      }
    };
  headType :: String -> SType -> Either String InstanceHead;
  headType prefix ty =
    case ty of {
      STVar a -> Right (HVar (prefix ++ a));
      SCon c ts ->
        foldEither
          (\f a ->
             do {
               value <- headType prefix a;
               Right (HCon "@" ((:) f ((:) value [])))
             })
          (HCon c [])
          ts;
      STypeApp f a ->
        do {
          x <- headType prefix f;
          y <- headType prefix a;
          Right (HCon "@" ((:) x ((:) y [])))
        };
      SArrow a b ->
        do {
          x <- headType prefix a;
          y <- headType prefix b;
          Right (HCon "->" ((:) x ((:) y [])))
        };
      _ -> Left "instance heads must be monotypes"
    };
  checkOverlap :: [] SInstanceDecl -> Either String ();
  checkOverlap instances =
    case instances of {
      [] -> Right ();
      (:) a rest ->
        do {
          traverseEither
            (\b ->
               if not (eqString (instanceClass a) (instanceClass b))
               then Right ()
               else do {
                      xs <- traverseEither (headType "left:") (instanceHead a);
                      ys <- traverseEither (headType "right:") (instanceHead b);
                      ensure (not (overlap M.empty (zip xs ys)))
                        ("overlapping instances for " ++ instanceClass a)
                    })
            rest;
          checkOverlap rest
        }
    };
  eqHead :: InstanceHead -> InstanceHead -> Bool;
  eqHead a b =
    case a of {
      HVar x ->
        case b of {
          HVar y -> eqString x y;
          _ -> False
        };
      HCon x xs ->
        case b of {
          HCon y ys -> (eqString x y && eqList eqHead xs ys);
          _ -> False
        }
    };
  walkHead :: Map String InstanceHead -> InstanceHead -> InstanceHead;
  walkHead substitution ty =
    case ty of {
      HVar a ->
        case M.lookup compareString a substitution of {
          Nothing -> ty;
          Just t -> walkHead substitution t
        };
      HCon c ts -> HCon c (map (walkHead substitution) ts)
    };
  occursHead :: String -> InstanceHead -> Bool;
  occursHead a ty =
    case ty of {
      HVar b -> eqString a b;
      HCon _ ts -> any (occursHead a) ts
    };
  overlap :: Map String InstanceHead -> [] ((,) InstanceHead InstanceHead) -> Bool;
  overlap substitution equations =
    case equations of {
      [] -> True;
      (:) ((,) x y) rest ->
        let {
          a = walkHead substitution x
        } in
        let {
          b = walkHead substitution y
        } in
        if eqHead a b
        then overlap substitution rest
        else case a of {
               HVar name ->
                 if occursHead name b
                 then False
                 else overlap (M.insert compareString name b substitution) rest;
               HCon c xs ->
                 case b of {
                   HVar name ->
                     if occursHead name a
                     then False
                     else overlap (M.insert compareString name a substitution) rest;
                   HCon d ys ->
                     (eqString c d &&
                      ((length xs == length ys) && overlap substitution (append (zip xs ys) rest)))
                 }
             }
    };
  -- Structural size and occurrence counts are total integer accumulations.
  -- Force each update so wide types do not leave a deferred arithmetic chain.
  sumCounts :: [] Int -> Int;
  sumCounts counts = foldlStrict addInt 0 counts;
  typeSize :: SType -> Int;
  typeSize ty =
    case ty of {
      STVar _ -> 1;
      SCon _ xs -> (1 + sumCounts (map typeSize xs));
      STypeApp f a -> (typeSize f + typeSize a);
      SArrow a b -> ((1 + typeSize a) + typeSize b);
      _ -> 1
    };
  occurrences :: String -> SType -> Int;
  occurrences a ty =
    case ty of {
      STVar b -> if eqString a b then 1 else 0;
      SCon _ xs -> sumCounts (map (occurrences a) xs);
      STypeApp f x -> (occurrences a f + occurrences a x);
      SArrow x y -> (occurrences a x + occurrences a y);
      _ -> 0
    };
  lowerExpr :: Map String ([] ((,) EvidenceRole String)) ->
               DataEnv ->
               Map String Info ->
               Map String ((,) String ([] String)) ->
               [] ((,) EvidenceRole String) ->
               SExpr -> Fresh ((,) SExpr ([] ((,) String String)));
  lowerExpr valueScopes ds infos env candidates expression =
    lowerExprAt Nothing valueScopes ds infos env candidates expression;
  lowerExprAt :: Maybe ((,) String SourceSpan) ->
                 Map String ([] ((,) EvidenceRole String)) -> DataEnv -> Map String Info ->
                 Map String ((,) String ([] String)) -> [] ((,) EvidenceRole String) ->
                 SExpr -> Fresh ((,) SExpr ([] ((,) String String)));
  lowerExprAt site valueScopes ds infos env candidates expression =
    case expression of {
      SSourceDefinition body ->
        lowerExprAt site valueScopes ds infos (M.delete compareString callStackScopeKey env) candidates body;
      SCallSite name location value ->
        if eqString name "an expression type signature" && managedAnnotation value
        then lowerFunctionAt (Just ((,) name location)) valueScopes ds infos env candidates value
        else lowerExprAt (Just ((,) name location)) valueScopes ds infos env candidates value;
      SVar x ->
        if eqString x "$MLF.Stack.callStack"
        then do { stack <- currentCallStack env; freshPure ((,) stack []) }
        else case M.lookup compareString x env of {
          Nothing -> freshPure ((,) expression []);
          Just ((,) name classes) -> applyEvidence site x env (SVar name) classes
        };
      SConstructor _ -> freshPure ((,) expression []);
      SIntLit _ -> freshPure ((,) expression []);
      SDoubleLit _ -> freshPure ((,) expression []);
      SBoolLit _ -> freshPure ((,) expression []);
      SStringLit _ -> freshPure ((,) expression []);
      SPrimitive _ -> freshPure ((,) expression []);
      SApp a b ->
        do {
          boundValueShared10 <- lowerFunctionAt site valueScopes ds infos env candidates a;
          case boundValueShared10 of {
            (,) f as ->
              do {
                boundValueShared9 <- lowerExprAt site valueScopes ds infos env candidates b;
                case boundValueShared9 of {
                  (,) x bs ->
                    do {
                      freshPure ((,) (SApp f x) (append as bs))
                    }
                }
              }
          }
        };
      SLam x annotation body ->
        do {
          boundValueShared12 <-
            case annotation of {
              Nothing -> freshPure ((,) Nothing []);
              Just (SAnnotation existential ty) ->
                do {
                  translated <-
                    if null existential
                    then freshLift (translateScheme ds infos ty)
                    else freshPure ty;
                  let {
                    predicates =
                      case scheme ty of {
                        (,,) _ ps _ -> ps
                      }
                  };
                  freshPure
                    ((,) (Just (SAnnotation existential translated))
                       (map (\(SPredicate c _) -> c) predicates))
                }
            };
          case boundValueShared12 of {
            (,) annotation2 classes ->
              do {
                boundValueShared11 <-
                  lowerExprAt site valueScopes ds infos (M.insert compareString x ((,) x classes) env)
                    candidates
                    body;
                case boundValueShared11 of {
                  (,) body2 wants ->
                    do {
                      freshPure ((,) (SLam x annotation2 body2) wants)
                    }
                }
              }
          }
        };
      SLet x (SAnn rhs (SAnnotation [] ty)) body ->
        do {
          rhs2 <-
            signedIn valueScopes ds infos (M.findWithDefault compareString candidates x valueScopes)
              env
              rhs
              ty;
          let {
            predicates =
              case scheme ty of {
                (,,) _ ps _ -> ps
              }
          };
          boundValueShared13 <-
            lowerExprAt site valueScopes ds infos
              (M.insert compareString x ((,) x (map (\(SPredicate c _) -> c) predicates)) env)
              candidates
              body;
          case boundValueShared13 of {
            (,) body2 wants ->
              do {
                freshPure ((,) (SLet x rhs2 body2) wants)
              }
          }
        };
      SLet x rhs body ->
        do {
          boundValueShared15 <-
            lowerExprAt site valueScopes ds infos env
              (M.findWithDefault compareString candidates x valueScopes)
              rhs;
          case boundValueShared15 of {
            (,) rhs2 wanted ->
              do {
                boundValueShared14 <-
                  lowerExprAt site valueScopes ds infos
                    (M.insert compareString x ((,) x (map snd wanted)) env)
                    candidates
                    body;
                case boundValueShared14 of {
                  (,) body2 wants ->
                    do {
                      freshPure
                        ((,) (SLet x (foldr (\((,) n _) b -> SLam n Nothing b) rhs2 wanted) body2)
                           wants)
                    }
                }
              }
          }
        };
      SAnn a (SAnnotation existential ty) ->
        let {
          predicates =
            case scheme ty of {
              (,,) _ ps _ -> ps
            }
        } in
        if not (null predicates)
        then do {
               freshLift
                 (ensure (null existential) "qualified annotations cannot bind existentials");
               result <- signedIn valueScopes ds infos candidates env a ty;
               freshPure ((,) result [])
             }
        else do {
               boundValueShared16 <- lowerExprAt site valueScopes ds infos env candidates a;
               case boundValueShared16 of {
                 (,) a2 wants ->
                   do {
                     translated <-
                       if null existential
                       then freshLift (translateScheme ds infos ty)
                       else freshPure ty;
                     freshPure ((,) (SAnn a2 (SAnnotation existential translated)) wants)
                   }
               }
             };
      SCase a branches ->
        do {
          boundValueShared18 <- lowerExprAt site valueScopes ds infos env candidates a;
          case boundValueShared18 of {
            (,) a2 as ->
              do {
                bs <-
                  mapM
                    (\(SAlternative pattern body) ->
                       do {
                         let {
                           names = Surface.patternVariables pattern
                         };
                         let {
                           scope = foldr (\n -> M.insert compareString n ((,) n [])) env names
                         };
                         boundValueShared17 <- lowerExprAt site valueScopes ds infos scope candidates body;
                         case boundValueShared17 of {
                           (,) body2 wants ->
                             do {
                               freshPure ((,) (SAlternative pattern body2) wants)
                             }
                         }
                       })
                    branches;
                freshPure ((,) (SCase a2 (map fst bs)) (append as (concatMap snd bs)))
              }
          }
        };
      SDo _ _ -> lowerExprAt site valueScopes ds infos env candidates (Desugar.desugarDo expression);
      SLetRec definitions body ->
        do {
          signatures <-
            freshLift
              (traverseEither
                 (\((,,) n annotation rhs) ->
                    case annotation of {
                      SAnnotation [] ty -> Right ((,,) n ty rhs);
                      _ ->
                        Left
                          ("recursive definition " ++
                           (n ++ " requires an explicit closed signature"))
                    })
                 definitions);
          let {
            entries =
              map
                (\((,,) n ty _) ->
                   case scheme ty of {
                     (,,) _ predicates _ ->
                       (,) n ((,) n (map (\(SPredicate c _) -> c) predicates))
                   })
                signatures
          };
          let {
            scope = M.union compareString (M.fromList compareString entries) env
          };
          definitions2 <-
            mapM
              (\((,,) n ty rhs) ->
                 do {
                   translated <- freshLift (translateScheme ds infos ty);
                   rhs2 <-
                     signedIn valueScopes ds infos
                       (M.findWithDefault compareString candidates n valueScopes)
                       scope
                       rhs
                       ty;
                   freshPure ((,,) n (SAnnotation [] translated) rhs2)
                 })
              signatures;
          boundValueShared19 <- lowerExprAt site valueScopes ds infos scope candidates body;
          case boundValueShared19 of {
            (,) body2 wants ->
              do {
                freshPure ((,) (SLetRec definitions2 body2) wants)
              }
          }
        };
      SSharedBind _ _ _ _ _ -> freshFail "shared do bind escaped surface lowering";
      SEquations _ -> freshFail "surface equations escaped lowering";
      SWanted _ _ -> freshFail "dictionary holes are reserved for dictionary translation";
      SChecked _ _ -> freshFail "checked source forms are reserved for dictionary translation"
    };
  managedAnnotation :: SExpr -> Bool;
  managedAnnotation expression = case expression of {
    SAnn _ (SAnnotation _ ty) -> managedType ty;
    _ -> False
  };
  -- Expression signatures are uses, not binding signatures: solve their
  -- managed evidence at this location rather than infer it on an unsigned let.
  lowerFunctionAt :: Maybe ((,) String SourceSpan) ->
                     Map String ([] ((,) EvidenceRole String)) -> DataEnv -> Map String Info ->
                     Map String ((,) String ([] String)) -> [] ((,) EvidenceRole String) ->
                     SExpr -> Fresh ((,) SExpr ([] ((,) String String)));
  lowerFunctionAt site valueScopes ds infos env candidates expression =
    case expression of {
      SSourceDefinition body ->
        lowerFunctionAt site valueScopes ds infos (M.delete compareString callStackScopeKey env) candidates body;
      SCallSite name location value ->
        lowerFunctionAt (Just ((,) name location)) valueScopes ds infos env candidates value;
      SAnn rhs (SAnnotation [] ty) ->
        case scheme ty of {
          (,,) _ predicates _ ->
            if null predicates
            then lowerExprAt site valueScopes ds infos env candidates expression
            else do {
              function <- signedIn valueScopes ds infos candidates env rhs ty;
              applyEvidence site "an expression type signature" env function
                (map (\(SPredicate c _) -> c) predicates)
            }
        };
      _ -> lowerExprAt site valueScopes ds infos env candidates expression
    };
  -- Call-stack evidence is synthesized at each use, never generalized as a wanted.
  currentCallStack :: Map String ((,) String ([] String)) -> Fresh SExpr;
  currentCallStack scope =
    case M.lookup compareString callStackScopeKey scope of {
      Nothing -> freshPure (SPrimitive PEmptyCallStack);
      Just ((,) evidence _) ->
        do {
          stack <- freshName "callStackValue";
          freshPure (SCase (SVar evidence)
            ((:) (SAlternative
              (SConstructorPattern "MLFStackEvidence" ((:) (Just stack) []))
              (SVar stack)) []))
        }
    };
  callSiteEvidence :: Maybe ((,) String SourceSpan) -> String ->
                      Map String ((,) String ([] String)) -> Fresh SExpr;
  callSiteEvidence site fallback scope =
    do {
      stack <- currentCallStack scope;
      let {
        origin = case site of {
          Just value -> value;
          Nothing -> (,) fallback (SourceSpan "" "" "<generated>" 0 0 0 0)
        }
      };
      case origin of {
        (,) display (SourceSpan packageName moduleName file startLine startColumn endLine endColumn) ->
          let {
            args = (:) (SStringLit display) ((:) (SStringLit packageName)
              ((:) (SStringLit moduleName) ((:) (SStringLit file)
              ((:) (SIntLit startLine) ((:) (SIntLit startColumn)
              ((:) (SIntLit endLine) ((:) (SIntLit endColumn) [])))))));
            frame = foldl SApp (SConstructor "MLFStackFrame") args;
            pushed = SApp (SApp (SPrimitive PPushCallStack) frame) stack
          } in freshPure (SApp (SConstructor "MLFStackEvidence") pushed)
      }
    };
  applyEvidence :: Maybe ((,) String SourceSpan) -> String ->
                   Map String ((,) String ([] String)) -> SExpr -> [] String ->
                   Fresh ((,) SExpr ([] ((,) String String)));
  applyEvidence site name scope expression classes =
    case classes of {
      [] -> freshPure ((,) expression []);
      (:) predicate rest ->
        if eqString predicate callStackPredicate
        then do {
               evidence <- callSiteEvidence site name scope;
               applyEvidence site name scope (SApp expression evidence) rest
             }
        else do {
               wanted <- freshName "wantedDictionary";
               result <- applyEvidence site name scope (SApp expression (SVar wanted)) rest;
               case result of {
                 (,) body wants -> freshPure ((,) body ((:) ((,) wanted predicate) wants))
               }
             }
    };
  wantedNames :: [] String -> Fresh ([] ((,) String String));
  wantedNames classes =
    mapM
      (\c ->
         do {
           name <- freshName "wantedDictionary";
           freshPure ((,) name c)
         })
      classes;
  signedIn :: Map String ([] ((,) EvidenceRole String)) ->
              DataEnv ->
              Map String Info ->
              [] ((,) EvidenceRole String) ->
              Map String ((,) String ([] String)) -> SExpr -> SType -> Fresh SExpr;
  signedIn valueScopes ds infos available scope expression ty =
    do {
      translated <- freshLift (translateScheme ds infos ty);
      lowerSignedBody valueScopes ds infos available scope expression ty translated
    };
  lowerSignedBody :: Map String ([] ((,) EvidenceRole String)) ->
                     DataEnv -> Map String Info -> [] ((,) EvidenceRole String) ->
                     Map String ((,) String ([] String)) -> SExpr -> SType -> SType -> Fresh SExpr;
  lowerSignedBody valueScopes ds infos available scope expression ty translated =
    case expression of {
      -- A copied top-level definition keeps its original managed lexical scope.
      -- Peel provenance before installing this definition's own explicit givens.
      SSourceDefinition body -> lowerSignedBody valueScopes ds infos available
        (M.delete compareString callStackScopeKey scope) body ty translated;
      _ -> do {
      let {
        predicates =
          case scheme ty of {
            (,,) _ ps _ -> ps
          }
      };
      names <- mapM (\p -> freshName "givenDictionary") predicates;
      let {
        ordinary = filter (\((,) p _) -> not (isCallStackPredicate p)) (zip predicates names);
        local = append (map (\((,) _ n) -> (,) GivenEvidence n) ordinary) available;
        stackScope = foldl
          (\env ((,) predicate name) ->
             if isCallStackPredicate predicate
             then M.insert compareString callStackScopeKey ((,) name []) env
             else env)
          scope (zip predicates names)
      };
      boundValueShared20 <- lowerExpr valueScopes ds infos stackScope local expression;
      case boundValueShared20 of {
        (,) body wants ->
          do {
            let {
              closed = closeWants infos local wants body
            };
            freshPure (SChecked translated (foldr (\n b -> SLam n Nothing b) closed names))
          }
      }
    }
    };
  closeWants :: Map String Info ->
                [] ((,) EvidenceRole String) -> [] ((,) String String) -> SExpr -> SExpr;
  closeWants infos candidates wants expression =
    let {
      replacements =
        M.fromList compareString
          (concatMap
             (\((,) n c) ->
                case M.lookup compareString c infos of {
                  Nothing -> [];
                  Just (Info _ dict _ _ _) -> (:) ((,) n dict) []
                })
             wants)
    } in
    closeWanted replacements candidates expression;
  closeWanted :: Map String String -> [] ((,) EvidenceRole String) -> SExpr -> SExpr;
  closeWanted replacements candidates expression =
    case expression of {
      SSourceDefinition body -> SSourceDefinition (closeWanted replacements candidates body);
      SCallSite name location body ->
        SCallSite name location (closeWanted replacements candidates body);
      SVar n ->
        case M.lookup compareString n replacements of {
          Nothing -> expression;
          Just d -> SWanted d candidates
        };
      SLam n a b -> SLam n a (closeWanted replacements candidates b);
      SApp a b ->
        SApp (closeWanted replacements candidates a) (closeWanted replacements candidates b);
      SLet n a b ->
        SLet n (closeWanted replacements candidates a) (closeWanted replacements candidates b);
      SAnn a ty -> SAnn (closeWanted replacements candidates a) ty;
      SCase a branches ->
        SCase (closeWanted replacements candidates a)
          (map (\(SAlternative p b) -> SAlternative p (closeWanted replacements candidates b))
             branches);
      SChecked ty a -> SChecked ty (closeWanted replacements candidates a);
      SLetRec definitions body ->
        SLetRec
          (map (\((,,) n t a) -> (,,) n t (closeWanted replacements candidates a)) definitions)
          (closeWanted replacements candidates body);
      _ -> expression
    };
  instantiateMethod :: Map String SType -> SType -> Fresh SType;
  instantiateMethod arguments ty =
    case ty of {
      STVar n -> freshPure (M.findWithDefault compareString ty n arguments);
      SForall flag n bound body ->
        do {
          fresh <-
            freshAvoid "methodType"
              (append (concatMap typeNames (M.elems arguments)) (typeNames ty));
          bound2 <- instantiateMethod arguments bound;
          body2 <- instantiateMethod arguments (substitute n (STVar fresh) body);
          freshPure (SForall flag fresh bound2 body2)
        };
      SArrow a b ->
        do {
          x <- instantiateMethod arguments a;
          y <- instantiateMethod arguments b;
          freshPure (SArrow x y)
        };
      STypeApp f a ->
        do {
          x <- instantiateMethod arguments f;
          y <- instantiateMethod arguments a;
          freshPure (STypeApp x y)
        };
      SCon c types ->
        do {
          ts <- mapM (instantiateMethod arguments) types;
          freshPure (SCon c ts)
        };
      SQualified predicates body ->
        do {
          ps <- mapM (\(SPredicate c ts) -> do {
                    args <- mapM (instantiateMethod arguments) ts;
                    freshPure (SPredicate c args) }) predicates;
          result <- instantiateMethod arguments body;
          freshPure (SQualified ps result)
        };
      _ -> freshPure ty
    };
  freshAvoid :: String -> [] String -> Fresh String;
  freshAvoid prefix forbidden =
    do {
      name <- freshName prefix;
      if elem eqString name forbidden then freshAvoid prefix forbidden else freshPure name
    };
  substitute :: String -> SType -> SType -> SType;
  substitute name replacement ty =
    case ty of {
      STVar a -> if eqString name a then replacement else ty;
      SForall flag a bound body ->
        SForall flag a (substitute name replacement bound)
          (if eqString a name then body else substitute name replacement body);
      SArrow a b -> SArrow (substitute name replacement a) (substitute name replacement b);
      STypeApp f a -> STypeApp (substitute name replacement f) (substitute name replacement a);
      SCon c types -> SCon c (map (substitute name replacement) types);
      SQualified predicates body ->
        SQualified
          (map (\(SPredicate c ts) -> SPredicate c (map (substitute name replacement) ts)) predicates)
          (substitute name replacement body);
      _ -> ty
    };
  prettyQualified :: Map String String -> XType -> String;
  prettyQualified names ty =
    case ty of {
      XForall a bound body ->
        ("forall " ++ (prettyBinder a bound ++ (". " ++ prettyQualified names body)));
      _ ->
        case constraints names ty of {
          (,) [] _ -> Pretty.prettyType ty;
          (,) predicates body ->
            ((if (length predicates == 1)
              then head predicates
              else ("(" ++ (intercalate ", " predicates ++ ")"))) ++
             (" => " ++ prettyQualified names body))
        }
    };
  prettyBinder :: XTyVar -> XType -> String;
  prettyBinder a bound =
    case bound of {
      XBot -> Pretty.prettyType (XVar a);
      XBotKind kind ->
        ("(" ++ (Pretty.prettyType (XVar a) ++ (" : " ++ (prettyKindLocal kind ++ ")"))));
      _ -> ("(" ++ (Pretty.prettyType (XVar a) ++ (" >= " ++ (Pretty.prettyType bound ++ ")"))))
    };
  prettyKindLocal :: Kind -> String;
  prettyKindLocal kind =
    case kind of {
      Star -> "*";
      KArrow a b ->
        ((case a of {
            Star -> "*";
            _ -> ("(" ++ (prettyKindLocal a ++ ")"))
          }) ++
         (" -> " ++ prettyKindLocal b))
    };
  constraints :: Map String String -> XType -> (,) ([] String) XType;
  constraints names ty =
    case ty of {
      XArrow (XCon dictionary args) body ->
        case M.lookup compareString dictionary names of {
          Nothing -> (,) [] ty;
          Just name ->
            case constraints names body of {
              (,) predicates result ->
                (,) ((:) (unwords ((:) name (map prettyArgument args))) predicates) result
            }
        };
      _ -> (,) [] ty
    };
  prettyArgument :: XType -> String;
  prettyArgument ty =
    case ty of {
      XVar _ -> Pretty.prettyType ty;
      XCon _ [] -> Pretty.prettyType ty;
      _ -> ("(" ++ (Pretty.prettyType ty ++ ")"))
    }
}
