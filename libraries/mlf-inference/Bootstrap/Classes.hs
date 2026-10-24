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
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.ClassDemand as Q;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Kinding as K;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.X.Pretty as Pretty;
  data Info = Info SClassDecl String String (List (Pair String String)) (List String);
  data InstanceHead = HVar String | HCon String (List InstanceHead);
  className :: SClassDecl -> String;
  className (SClassDecl n _ _ _) = n;
  classParameters :: SClassDecl -> List (Pair String Kind);
  classParameters (SClassDecl _ ps _ _) = ps;
  superclasses :: SClassDecl -> List SPredicate;
  superclasses (SClassDecl _ _ ps _) = ps;
  classMethods :: SClassDecl -> List (Pair String SType);
  classMethods (SClassDecl _ _ _ ms) = ms;
  instanceVariables :: SInstanceDecl -> List (Pair String Kind);
  instanceVariables (SInstanceDecl vs _ _ _ _) = vs;
  instanceContext :: SInstanceDecl -> List SPredicate;
  instanceContext (SInstanceDecl _ ps _ _ _) = ps;
  instanceClass :: SInstanceDecl -> String;
  instanceClass (SInstanceDecl _ _ c _ _) = c;
  instanceHead :: SInstanceDecl -> List SType;
  instanceHead (SInstanceDecl _ _ _ ts _) = ts;
  instanceMethods :: SInstanceDecl -> List (Pair String SExpr);
  instanceMethods (SInstanceDecl _ _ _ _ ms) = ms;
  lookupInfo :: Map String Info -> String -> Either String Info;
  lookupInfo infos name =
    case M.lookup compareString name infos of {
      Nothing -> Left ("unknown class: " ++ name);
      Just info -> Right info
    };
  dictionary :: Map String Info -> SPredicate -> Either String SType;
  dictionary infos (SPredicate name arguments) =
    do {
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
  quantify :: List (Pair String Kind) -> SType -> SType;
  quantify variables ty = foldr (\(Pair n k) b -> SForall Flexible n (bottom k) b) ty variables;
  freeType :: SType -> List String;
  freeType ty = sortBy compareString (nubBy eqString (freeTypeRaw ty));
  freeTypeRaw :: SType -> List String;
  freeTypeRaw ty =
    case ty of {
      STVar a -> Cons a Nil;
      SArrow a b -> append (freeTypeRaw a) (freeTypeRaw b);
      STypeApp a b -> append (freeTypeRaw a) (freeTypeRaw b);
      SCon _ ts -> concatMap freeTypeRaw ts;
      SForall _ a bound body ->
        append (freeTypeRaw bound) (filter (\n -> not (eqString a n)) (freeTypeRaw body));
      SQualified predicates body ->
        append (freeTypeRaw body)
          (concatMap (\(SPredicate _ args) -> concatMap freeTypeRaw args) predicates);
      _ -> Nil
    };
  unique :: String -> List String -> Either String Unit;
  unique label names =
    ensure (length names == length (nubBy eqString names)) ("duplicate " ++ label);
  scheme :: SType -> Triple (List (Triple Flag String SType)) (List SPredicate) SType;
  scheme ty =
    case ty of {
      SForall flag name bound body ->
        case scheme body of {
          Triple variables predicates result ->
            Triple (Cons (Triple flag name bound) variables) predicates result
        };
      SQualified predicates body -> Triple Nil predicates body;
      _ -> Triple Nil Nil ty
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
      Triple variables predicates body ->
        do {
          ensure (not (qualified body || any (\(Triple _ _ bound) -> qualified bound) variables))
            "class constraints must occur at the outside of a type scheme";
          scope <-
            foldEither
              (\env (Triple _ a bound) ->
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
              foldr (\(Triple flag a bound) rest -> SForall flag a bound rest)
                (foldr SArrow body args)
                variables
          };
          K.annotationType ds M.empty result;
          Right result
        }
    };
  checkPredicate :: DataEnv ->
                    Map String Info -> Map String Kind -> SPredicate -> Either String Unit;
  checkPredicate ds infos scope (SPredicate name arguments) =
    do {
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
  field ty =
    case ty of {
      STVar a -> Right (Parameter a);
      SArrow a b ->
        do {
          x <- field a;
          y <- field b;
          Right (Function x y)
        };
      STypeApp f a ->
        do {
          x <- field f;
          y <- field a;
          Right (Application x y)
        };
      SCon c args -> mapEither (Applied c) (traverseEither field args);
      SForall Flexible a SBottom body -> mapEither (Quantified a Star) (field body);
      SForall Flexible a (SBottomKind k) body -> mapEither (Quantified a k) (field body);
      _ ->
        Left
          "class methods require ordinary forall signatures without bounded or nested class constraints"
    };
  lowerClasses :: SProgram -> Either String (Pair SProgram (Map String String));
  lowerClasses original = lowerClassesWithImports S.empty original;
  lowerClassesWithImports :: Set String ->
                             SProgram -> Either String (Pair SProgram (Map String String));
  lowerClassesWithImports imported original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses imported M.empty Nothing program
    };
  lowerClassesWithScopes :: Map String IntSet ->
                            List IntSet ->
                            SProgram -> Either String (Pair SProgram (Map String String));
  lowerClassesWithScopes values instances original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses S.empty values (Just instances) program
    };
  lowerCoreClasses :: Set String ->
                      Map String IntSet ->
                      Maybe (List IntSet) ->
                      SProgram -> Either String (Pair SProgram (Map String String));
  lowerCoreClasses imported valueIndices instanceIndices program =
    lowerCoreClassesWith Nothing imported valueIndices instanceIndices program;
  lowerSeparateClasses externals instanceNames original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds Nil Nil b;
             _ -> original
           });
      case program of {
        SClassProgram ds Nil Nil body ->
          let {
            parameters =
              map
                (\(Pair n ty) ->
                   Triple n (CheckRecursive (SAnnotation Nil ty))
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                (M.toList externals)
          } in
          Right
            (Pair (SProgram ds (if null parameters then body else SLetRec parameters body))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just (Pair externals instanceNames)) S.empty M.empty Nothing program
      }
    };
  -- Crate lowering has a complete declaration/instance inventory, but candidate
  -- visibility remains that of each declaration's defining module. Stable
  -- dictionary names make the lowered declarations reusable inference queries.
  lowerSeparateClassesWithScopes :: Map String SType ->
                                    List String ->
                                    Map String IntSet ->
                                    List IntSet ->
                                    SProgram -> Either String (Pair SProgram (Map String String));
  lowerSeparateClassesWithScopes externals instanceNames valueScopes instanceScopes original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds Nil Nil b;
             _ -> original
           });
      case program of {
        SClassProgram ds Nil Nil body ->
          let {
            parameters =
              map
                (\(Pair n ty) ->
                   Triple n (CheckRecursive (SAnnotation Nil ty))
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked crate parameter"))))
                (M.toList externals)
          } in
          Right
            (Pair (SProgram ds (if null parameters then body else SLetRec parameters body))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just (Pair externals instanceNames)) S.empty valueScopes
            (Just instanceScopes)
            program
      }
    };
  lowerCoreClassesWith :: Maybe (Pair (Map String SType) (List String)) ->
                          Set String ->
                          Map String IntSet ->
                          Maybe (List IntSet) ->
                          SProgram -> Either String (Pair SProgram (Map String String));
  lowerCoreClassesWith config imported valueIndices instanceIndices program =
    case program of {
      SProgram ds body ->
        case config of {
          Nothing -> Right (Pair program M.empty);
          Just _ ->
            lowerCoreClassesWith config imported valueIndices instanceIndices
              (SClassProgram ds Nil Nil body)
        };
      SClassProgram datatypes declarations instances body ->
        do {
          case instanceIndices of {
            Nothing -> Right Unit;
            Just scopes ->
              ensure (length scopes == length instances) "module instance scope count mismatch"
          };
          base <- D.validateDeclarations datatypes;
          unique "class" (map className declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then Nil
                  else map fst (classMethods d))
               declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then map fst (classMethods d)
                  else Nil)
               declarations);
          traverseEither
            (\d ->
               do {
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
                      (\i -> concatMap (\(Pair _ e) -> Desugar.allNames e) (instanceMethods i))
                      instances)
                   (append
                      (concatMap
                         (\d ->
                            Cons (D.datatypeName d)
                              (map D.constructorName (D.datatypeConstructors d)))
                         datatypes)
                      (concatMap
                         (\d ->
                            Cons (className d)
                              (append (map fst (classParameters d))
                                 (concatMap (\(Pair n ty) -> Cons n (typeNames ty))
                                    (classMethods d))))
                         declarations)))
          };
          runFresh used
            (lowerClassesBody config imported valueIndices instanceIndices datatypes instances body
               base
               classes)
        }
    };
  implicitParameters :: SClassDecl -> SClassDecl;
  implicitParameters (SClassDecl name parameters supers methods) =
    SClassDecl name parameters supers
      (map
         (\(Pair n ty) ->
            Pair n
              (quantify
                 (map (\a -> Pair a Star) (Surface.without (freeType ty) (map fst parameters)))
                 ty))
         methods);
  typeNames :: SType -> List String;
  typeNames ty =
    case ty of {
      STVar n -> Cons n Nil;
      SCon n ts -> Cons n (concatMap typeNames ts);
      SForall _ n a b -> Cons n (append (typeNames a) (typeNames b));
      SArrow a b -> append (typeNames a) (typeNames b);
      STypeApp a b -> append (typeNames a) (typeNames b);
      SQualified ps t ->
        append (concatMap (\(SPredicate n ts) -> Cons n (concatMap typeNames ts)) ps) (typeNames t);
      _ -> Nil
    };
  separateName config stable prefix =
    case config of {
      Nothing -> freshName prefix;
      Just _ -> freshPure stable
    };
  lowerClassesBody :: Maybe (Pair (Map String SType) (List String)) ->
                      Set String ->
                      Map String IntSet ->
                      Maybe (List IntSet) ->
                      List DataDecl ->
                      List SInstanceDecl ->
                      SExpr ->
                      DataEnv -> List SClassDecl -> Fresh (Pair SProgram (Map String String));
  lowerClassesBody config imported valueIndices instanceIndices datatypes instances body base classes =
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
                   (\(Pair n _) ->
                      do {
                        selector <-
                          separateName config ("select_" ++ n) ("select" ++ className declaration);
                        freshPure (Pair n selector)
                      })
                   (classMethods declaration);
               supers <-
                 mapM
                   (\i ->
                      separateName config
                        ("super_" ++ (className declaration ++ ("_" ++ showInt i)))
                        "superclass")
                   (range 0 (length (superclasses declaration) - 1));
               freshPure (Pair (className declaration) (Info declaration dict ctor methods supers))
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
          Just (Pair _ ns) ->
            do {
              freshLift
                (ensure (length ns == length checkedInstances)
                   "separate instance identity count mismatch");
              freshPure ns
            }
        };
      let {
        supers =
          concatMap (\(Pair _ (Info _ _ _ _ ns)) -> map (\n -> Pair SuperclassEvidence n) ns)
            entries
      };
      let {
        globalCandidates = append (map (\n -> Pair InstanceEvidence n) names) supers
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
            Just (Pair es _) -> es
          }
      };
      let {
        externalOverloads =
          M.mapWithKey
            (\n ty ->
               case scheme ty of {
                 Triple _ ps _ -> Pair n (map (\(SPredicate c _) -> c) ps)
               })
            externalSchemes
      };
      let {
        methodEnv =
          M.union compareString externalOverloads
            (M.union compareString (methodBindings imported False entries)
               (methodBindings imported True entries))
      };
      selectorGroups <- mapM (\entry -> selectorDefinitions infos (snd entry)) entries;
      definitions <-
        mapM
          (\(Pair (Pair name inst) available) ->
             instanceDefinition valueScopes ds infos methodEnv name inst available)
          (zip (zip names checkedInstances) instanceScopes);
      boundValueShared3 <- lowerExpr valueScopes ds infos methodEnv globalCandidates body;
      case boundValueShared3 of {
        Pair expression wants ->
          do {
            let {
              result = closeWants infos globalCandidates wants expression
            };
            let {
              bindings =
                map
                  (\(Triple n annotation rhs) ->
                     case annotation of {
                       SAnnotation _ ty -> Triple n (CheckRecursive annotation) (SChecked ty rhs)
                     })
                  (append (concat selectorGroups) definitions)
            };
            let {
              localBindings =
                filter (\(Triple n _ _) -> not (M.member compareString n externalSchemes)) bindings
            };
            let {
              inner = if null localBindings then result else SLetRec localBindings result
            };
            externalBindings <-
              mapM
                (\(Pair n ty) ->
                   do {
                     translated <- freshLift (translateScheme ds infos ty);
                     freshPure
                       (Triple n (CheckRecursive (SAnnotation Nil translated))
                          (SChecked translated
                             (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                   })
                (M.toList externalSchemes);
            let {
              output = if null externalBindings then inner else SLetRec externalBindings inner
            };
            freshPure
              (Pair (SProgram (append datatypes dictionaries) output)
                 (M.fromList compareString
                    (map (\(Pair name (Info _ dict _ _ _)) -> Pair dict name) entries)))
          }
      }
    };
  selectCandidates :: List String ->
                      List (Pair EvidenceRole String) -> IntSet -> List (Pair EvidenceRole String);
  selectCandidates names supers indices =
    append
      (concatMap
         (\(Pair i n) -> if I.member i indices then Cons (Pair InstanceEvidence n) Nil else Nil)
         (zip (range 0 (length names - 1)) names))
      supers;
  methodBindings :: Set String ->
                    Bool -> List (Pair String Info) -> Map String (Pair String (List String));
  methodBindings imported isImported entries =
    M.fromList compareString
      (concatMap
         (\(Pair name (Info _ _ _ methods _)) ->
            if if isImported
               then S.member compareString name imported
               else not (S.member compareString name imported)
            then map (\(Pair method selector) -> Pair method (Pair selector (Cons name Nil)))
                   methods
            else Nil)
         entries);
  instanceDefinition :: Map String (List (Pair EvidenceRole String)) ->
                        DataEnv ->
                        Map String Info ->
                        Map String (Pair String (List String)) ->
                        String ->
                        SInstanceDecl ->
                        List (Pair EvidenceRole String) -> Fresh (Triple String SAnnotation SExpr);
  instanceDefinition valueScopes ds infos methodEnv name inst available =
    do {
      boundValueShared6 <- freshLift (lookupInfo infos (instanceClass inst));
      case boundValueShared6 of {
        Info declaration _ ctor _ _ ->
          do {
            givenNames <- mapM (\p -> freshName "givenDictionary") (instanceContext inst);
            let {
              candidates = append (map (\n -> Pair GivenEvidence n) givenNames) available
            };
            methodBodies <-
              mapM
                (\(Pair method methodType) ->
                   do {
                     original <-
                       freshLift
                         (case lookup eqString method (instanceMethods inst) of {
                            Nothing -> Left ("missing instance method: " ++ method);
                            Just e -> Right e
                          });
                     boundValueShared4 <-
                       lowerExpr valueScopes ds infos methodEnv candidates original;
                     case boundValueShared4 of {
                       Pair translated wants ->
                         do {
                           expected <-
                             instantiateMethod
                               (M.fromList compareString
                                  (zip (map fst (classParameters declaration)) (instanceHead inst)))
                               methodType;
                           freshPure
                             (SChecked expected (closeWants infos candidates wants translated))
                         }
                     }
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
            freshPure (Triple name (SAnnotation Nil ty) rhs)
          }
      }
    };
  validateClasses :: DataEnv -> Map String Info -> Either String Unit;
  validateClasses ds infos =
    do {
      traverseEither
        (\(Info declaration _ _ _ _) ->
           do {
             let {
               scope = M.fromList compareString (classParameters declaration)
             };
             traverseEither (checkPredicate ds infos scope) (superclasses declaration);
             traverseEither
               (\(Pair name ty) ->
                  do {
                    let {
                      missing = Surface.without (M.keys scope) (freeType ty)
                    };
                    ensure (null missing)
                      ("ambiguous class method: " ++
                       (name ++
                        (" does not mention class parameters " ++ intercalate ", " missing)));
                    K.annotationType ds scope ty;
                    field ty;
                    Right Unit
                  })
               (classMethods declaration);
             Right Unit
           })
        (M.elems infos);
      traverseEither (visitSuperclass infos Nil) (M.keys infos);
      Right Unit
    };
  visitSuperclass :: Map String Info -> List String -> String -> Either String Unit;
  visitSuperclass infos seen name =
    if elem eqString name seen
    then Left ("cyclic superclass hierarchy: " ++ name)
    else do {
           boundValueShared7 <- lookupInfo infos name;
           case boundValueShared7 of {
             Info declaration _ _ _ _ ->
               do {
                 traverseEither (\(SPredicate c _) -> visitSuperclass infos (Cons name seen) c)
                   (superclasses declaration);
                 Right Unit
               }
           }
         };
  dictionaryDecl :: Map String Info -> Info -> Either String DataDecl;
  dictionaryDecl infos (Info declaration name ctor _ _) =
    do {
      supers <- traverseEither (dictionary infos) (superclasses declaration);
      fields <- traverseEither field (append supers (map snd (classMethods declaration)));
      Right (DataDeclK name (classParameters declaration) (Cons (ConstructorDecl ctor fields) Nil))
    };
  selectorDefinitions :: Map String Info -> Info -> Fresh (List (Triple String SAnnotation SExpr));
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
        (\(Pair selected (Pair name ty)) ->
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
                      (Cons (SAlternative (SConstructorPattern ctor fields) (SVar value)) Nil))
             };
             let {
               signature =
                 quantify parameters
                   (SArrow (SCon dict (map (\(Pair n _) -> STVar n) parameters)) ty)
             };
             freshPure (Triple name (SAnnotation Nil signature) rhs)
           })
        (zip (range 0 (length signatures - 1)) signatures)
    };
  methodNames :: List String -> String;
  methodNames names =
    ("[" ++ (intercalate "," (map Pretty.prettyString (sortBy compareString names)) ++ "]"));
  validateInstance :: DataEnv -> Map String Info -> SInstanceDecl -> Either String SInstanceDecl;
  validateInstance ds infos inst =
    do {
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
                append explicit (map (\a -> Pair a Star) (Surface.without free (map fst explicit)))
            };
            let {
              scope = M.fromList compareString vars
            };
            ensure (null (Surface.without (map fst vars) free))
              "instance variables must occur in the instance head";
            checkPredicate ds infos scope (SPredicate (instanceClass inst) arguments);
            case arguments of {
              Cons (SCon _ _) Nil -> Right Unit;
              Cons _ Nil -> Left "instance head must start with a named type constructor";
              _ -> Right Unit
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
               Right (HCon "@" (Cons f (Cons value Nil)))
             })
          (HCon c Nil)
          ts;
      STypeApp f a ->
        do {
          x <- headType prefix f;
          y <- headType prefix a;
          Right (HCon "@" (Cons x (Cons y Nil)))
        };
      SArrow a b ->
        do {
          x <- headType prefix a;
          y <- headType prefix b;
          Right (HCon "->" (Cons x (Cons y Nil)))
        };
      _ -> Left "instance heads must be monotypes"
    };
  checkOverlap :: List SInstanceDecl -> Either String Unit;
  checkOverlap instances =
    case instances of {
      Nil -> Right Unit;
      Cons a rest ->
        do {
          traverseEither
            (\b ->
               if not (eqString (instanceClass a) (instanceClass b))
               then Right Unit
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
  overlap :: Map String InstanceHead -> List (Pair InstanceHead InstanceHead) -> Bool;
  overlap substitution equations =
    case equations of {
      Nil -> True;
      Cons (Pair x y) rest ->
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
  sumCounts :: List Int -> Int;
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
  -- Planning fixes dictionary arity/provenance, never predicate argument types.
  -- Those remain ordinary dictionary-arrow constraints in the existing solver.
  data QualifiedBinding = QualifiedKnown String (List String)
                        | QualifiedTemplate String Int Int
                        | QualifiedRecursive String Int;
  data QualifiedExpr = QualifiedExpr Int QualifiedForm;
  data QualifiedForm = QualifiedPlain SExpr
                     | QualifiedVariable String (Maybe (Pair Int Int))
                     | QualifiedApply QualifiedExpr QualifiedExpr
                     | QualifiedContext QualifiedExpr
                     | QualifiedLambda String (Maybe SAnnotation) QualifiedExpr
                     | QualifiedLet String QualifiedExpr QualifiedExpr
                     | QualifiedAnnotation QualifiedExpr SAnnotation
                     | QualifiedCase QualifiedExpr (List (Pair SPattern QualifiedExpr))
                     | QualifiedChecked SType (List String) (List (Pair EvidenceRole String)) QualifiedExpr
                     | QualifiedRec (List (Triple String RecursiveMode QualifiedExpr)) QualifiedExpr;
  data QualifiedBuild = QualifiedBuild (List Q.Frame) (List Q.Seed) (List Q.Use)
                                      (List (Pair Int Q.Demand));
  data QualifiedResult = QualifiedResult QualifiedExpr QualifiedBuild;
  qualifiedEmpty :: QualifiedBuild;
  qualifiedEmpty = QualifiedBuild Nil Nil Nil Nil;
  qualifiedMerge :: QualifiedBuild -> QualifiedBuild -> QualifiedBuild;
  qualifiedMerge (QualifiedBuild a b c d) (QualifiedBuild w x y z) =
    QualifiedBuild (append a w) (append b x) (append c y) (append d z);
  qualifiedBuilds :: List QualifiedBuild -> QualifiedBuild;
  qualifiedBuilds = foldlStrict qualifiedMerge qualifiedEmpty;
  qualifiedNode :: QualifiedExpr -> Int;
  qualifiedNode (QualifiedExpr n _) = n;
  qualifiedExpression :: QualifiedResult -> QualifiedExpr;
  qualifiedExpression (QualifiedResult expression _) = expression;
  qualifiedBuild :: QualifiedResult -> QualifiedBuild;
  qualifiedBuild (QualifiedResult _ build) = build;
  qualifiedId :: Fresh Int;
  qualifiedId = Fresh (\count used -> Right (Triple count (count + 1) used));
  qualifiedFinish :: Int -> Maybe Int -> QualifiedBuild -> Fresh QualifiedBuild;
  qualifiedFinish owner parent (QualifiedBuild frames seeds uses nodes) =
    do {
      rank <- qualifiedId;
      freshPure (QualifiedBuild (Cons (Q.Frame owner parent rank) frames) seeds uses nodes)
    };
  qualifiedMake :: QualifiedForm -> Q.Demand -> QualifiedBuild -> Fresh QualifiedResult;
  qualifiedMake form demand build =
    do {
      node <- qualifiedId;
      case build of {
        QualifiedBuild frames seeds uses nodes ->
          freshPure (QualifiedResult (QualifiedExpr node form)
            (QualifiedBuild frames seeds uses (Cons (Pair node demand) nodes)))
      }
    };
  qualifiedJoin :: QualifiedForm -> List QualifiedResult -> Fresh QualifiedResult;
  qualifiedJoin form results =
    qualifiedMake form (Q.UnionNodes (map (\result -> qualifiedNode (qualifiedExpression result)) results))
      (qualifiedBuilds (map qualifiedBuild results));
  qualifiedClasses :: SType -> List String;
  qualifiedClasses ty =
    case scheme ty of { Triple _ ps _ -> map (\(SPredicate c _) -> c) ps };
  qualifiedSeeds :: Int -> List String -> Fresh QualifiedBuild;
  qualifiedSeeds owner classes =
    do {
      seeds <- mapM (\c -> do { n <- qualifiedId; freshPure (Q.Seed n c owner) }) classes;
      nodes <- mapM (\seed -> case seed of {
        Q.Seed n _ _ -> do { node <- qualifiedId; freshPure (Pair node (Q.SeedNode n)) }
      }) seeds;
      freshPure (QualifiedBuild Nil seeds Nil nodes)
    };
  qualifiedKnown :: Int -> String -> List String -> Fresh QualifiedResult;
  qualifiedKnown owner name classes =
    do {
      build <- qualifiedSeeds owner classes;
      case build of {
        QualifiedBuild _ _ _ nodes ->
          qualifiedMake (QualifiedVariable name Nothing) (Q.UnionNodes (map fst nodes)) build
      }
    };
  planQualified :: Map String (List (Pair EvidenceRole String)) -> DataEnv -> Map String Info -> Int ->
                   Map String QualifiedBinding -> List (Pair EvidenceRole String) ->
                   SExpr -> Fresh QualifiedResult;
  planQualified valueScopes ds infos owner env candidates expression =
    case expression of {
      SVar x ->
        case M.lookup compareString x env of {
          Nothing -> qualifiedMake (QualifiedPlain expression) Q.Empty qualifiedEmpty;
          Just (QualifiedKnown name classes) -> qualifiedKnown owner name classes;
          Just (QualifiedRecursive name source) ->
            qualifiedMake (QualifiedVariable name Nothing) (Q.RefNode source) qualifiedEmpty;
          Just (QualifiedTemplate name frame source) ->
            do {
              use <- qualifiedId;
              qualifiedMake (QualifiedVariable name (Just (Pair use source))) (Q.InstantiateNode use source)
                (QualifiedBuild Nil Nil (Cons (Q.Use use frame owner) Nil) Nil)
            }
        };
      SApp a b ->
        do {
          left <- case a of {
            SAnn rhs (SAnnotation Nil ty) ->
              if null (qualifiedClasses ty)
              then planQualified valueScopes ds infos owner env candidates a
              else do {
                checked <- planQualifiedSigned valueScopes ds infos owner env candidates rhs ty;
                build <- qualifiedSeeds owner (qualifiedClasses ty);
                case build of {
                  QualifiedBuild _ _ _ nodes ->
                    qualifiedMake (QualifiedContext (qualifiedExpression checked))
                      (Q.UnionNodes (map fst nodes))
                      (qualifiedMerge (qualifiedBuild checked) build)
                }
              };
            _ -> planQualified valueScopes ds infos owner env candidates a
          };
          right <- planQualified valueScopes ds infos owner env candidates b;
          qualifiedJoin (QualifiedApply (qualifiedExpression left) (qualifiedExpression right))
            (Cons left (Cons right Nil))
        };
      SLam x annotation body ->
        do {
          translated <- case annotation of {
            Nothing -> freshPure Nothing;
            Just (SAnnotation existential ty) ->
              do {
                ty2 <- if null existential then freshLift (translateScheme ds infos ty)
                       else freshPure ty;
                freshPure (Just (SAnnotation existential ty2))
              }
          };
          let { classes = case annotation of {
            Nothing -> Nil; Just (SAnnotation _ ty) -> qualifiedClasses ty
          } };
          result <- planQualified valueScopes ds infos owner
            (M.insert compareString x (QualifiedKnown x classes) env) candidates body;
          qualifiedJoin (QualifiedLambda x translated (qualifiedExpression result)) (Cons result Nil)
        };
      SLet x (SAnn rhs (SAnnotation Nil ty)) body ->
        do {
          left <- planQualifiedSigned valueScopes ds infos owner env
            (M.findWithDefault compareString candidates x valueScopes) rhs ty;
          right <- planQualified valueScopes ds infos owner
            (M.insert compareString x (QualifiedKnown x (qualifiedClasses ty)) env) candidates body;
          qualifiedMake (QualifiedLet x (qualifiedExpression left) (qualifiedExpression right))
            (Q.RefNode (qualifiedNode (qualifiedExpression right)))
            (qualifiedMerge (qualifiedBuild left) (qualifiedBuild right))
        };
      SLet x rhs body ->
        do {
          frame <- qualifiedId;
          left <- planQualified valueScopes ds infos frame env
            (M.findWithDefault compareString candidates x valueScopes) rhs;
          build <- qualifiedFinish frame (Just owner) (qualifiedBuild left);
          right <- planQualified valueScopes ds infos owner
            (M.insert compareString x
              (QualifiedTemplate x frame (qualifiedNode (qualifiedExpression left))) env)
            candidates body;
          qualifiedMake (QualifiedLet x (qualifiedExpression left) (qualifiedExpression right))
            (Q.RefNode (qualifiedNode (qualifiedExpression right)))
            (qualifiedMerge build (qualifiedBuild right))
        };
      SAnn rhs (SAnnotation existential ty) ->
        if not (null (qualifiedClasses ty))
        then do {
          freshLift (ensure (null existential) "qualified annotations cannot bind existentials");
          planQualifiedSigned valueScopes ds infos owner env candidates rhs ty
        }
        else do {
          result <- planQualified valueScopes ds infos owner env candidates rhs;
          ty2 <- if null existential then freshLift (translateScheme ds infos ty) else freshPure ty;
          qualifiedJoin (QualifiedAnnotation (qualifiedExpression result) (SAnnotation existential ty2))
            (Cons result Nil)
        };
      SCase rhs branches ->
        do {
          result <- planQualified valueScopes ds infos owner env candidates rhs;
          planned <- mapM (\(SAlternative pattern body) -> do {
            let { scope = foldr (\n -> M.insert compareString n (QualifiedKnown n Nil))
                          env (Surface.patternVariables pattern) };
            branch <- planQualified valueScopes ds infos owner scope candidates body;
            freshPure (Pair pattern branch)
          }) branches;
          qualifiedJoin (QualifiedCase (qualifiedExpression result)
            (map (\(Pair p r) -> Pair p (qualifiedExpression r)) planned))
            (Cons result (map snd planned))
        };
      SDo _ _ -> planQualified valueScopes ds infos owner env candidates (Desugar.desugarDo expression);
      SLetRec definitions body ->
        planQualifiedRecursive valueScopes ds infos owner env candidates definitions body;
      SEquations _ -> freshFail "surface equations escaped lowering";
      SWanted _ _ -> freshFail "dictionary holes are reserved for dictionary translation";
      SChecked _ _ -> freshFail "checked source forms are reserved for dictionary translation";
      _ -> qualifiedMake (QualifiedPlain expression) Q.Empty qualifiedEmpty
    };
  planQualifiedSigned :: Map String (List (Pair EvidenceRole String)) -> DataEnv -> Map String Info -> Int ->
                         Map String QualifiedBinding -> List (Pair EvidenceRole String) ->
                         SExpr -> SType -> Fresh QualifiedResult;
  planQualifiedSigned valueScopes ds infos owner env available expression ty =
    do {
      translated <- freshLift (translateScheme ds infos ty);
      names <- mapM (\_ -> freshName "givenDictionary") (qualifiedClasses ty);
      let { local = append (map (\n -> Pair GivenEvidence n) names) available };
      frame <- qualifiedId;
      result <- planQualified valueScopes ds infos frame env local expression;
      build <- qualifiedFinish frame (Just owner) (qualifiedBuild result);
      qualifiedMake (QualifiedChecked translated names local (qualifiedExpression result)) Q.Empty build
    };
  planQualifiedRecursive :: Map String (List (Pair EvidenceRole String)) -> DataEnv -> Map String Info -> Int ->
                            Map String QualifiedBinding -> List (Pair EvidenceRole String) ->
                            List (Triple String RecursiveMode SExpr) -> SExpr -> Fresh QualifiedResult;
  planQualifiedRecursive valueScopes ds infos owner env candidates definitions body =
    do {
      freshLift (traverseEither (\(Triple n mode _) -> case mode of {
        InferRecursive -> Right Unit;
        CheckRecursive (SAnnotation Nil _) -> Right Unit;
        _ -> Left ("recursive definition " ++ n ++ " requires an explicit closed signature")
      }) definitions);
      let {
        unsigned = filter (\(Triple _ mode _) -> case mode of {
          InferRecursive -> True; _ -> False
        }) definitions;
        signed = filter (\(Triple _ mode _) -> case mode of {
          InferRecursive -> False; _ -> True
        }) definitions;
        fixed = foldr (\(Triple n mode _) scope -> case mode of {
          CheckRecursive (SAnnotation Nil ty) ->
            M.insert compareString n (QualifiedKnown n (qualifiedClasses ty)) scope;
          _ -> scope
        }) env signed;
        groups = Dependency.components (map (\(Triple n _ rhs) ->
          Pair n (Dependency.valueNames (Dependency.observeExpression rhs))) unsigned)
      };
      accumulated <- foldM (\(Triple scope previous build) group -> do {
        frame <- qualifiedId;
        entries <- mapM (\n -> do { node <- qualifiedId; freshPure (Pair n node) }) group;
        let {
          shared = foldr (\(Pair n node) -> M.insert compareString n (QualifiedRecursive n node))
                    scope entries
        };
        planned <- mapM (\(Pair n node) -> do {
          rhs <- freshLift (case find (\(Triple name _ _) -> eqString name n) unsigned of {
            Nothing -> Left "qualified recursive declaration disappeared";
            Just (Triple _ _ rhs) -> Right rhs
          });
          result <- planQualified valueScopes ds infos frame shared
            (M.findWithDefault compareString candidates n valueScopes) rhs;
          let {
            link = QualifiedBuild Nil Nil Nil
              (Cons (Pair node (Q.RefNode (qualifiedNode (qualifiedExpression result)))) Nil)
          };
          freshPure (Pair (Triple n InferRecursive (qualifiedExpression result))
            (qualifiedMerge (qualifiedBuild result) link))
        }) entries;
        completed <- qualifiedFinish frame (Just owner) (qualifiedBuilds (map snd planned));
        let {
          exported = foldr (\(Pair n node) -> M.insert compareString n (QualifiedTemplate n frame node))
                       scope entries
        };
        freshPure (Triple exported (append previous (map fst planned)) (qualifiedMerge build completed))
      }) (Triple fixed Nil qualifiedEmpty) groups;
      case accumulated of {
        Triple scope inferred build -> do {
          checked <- mapM (\(Triple n mode rhs) -> case mode of {
            CheckRecursive (SAnnotation Nil ty) -> do {
              translated <- freshLift (translateScheme ds infos ty);
              result <- planQualifiedSigned valueScopes ds infos owner scope
                (M.findWithDefault compareString candidates n valueScopes) rhs ty;
              freshPure (Pair (Triple n (CheckRecursive (SAnnotation Nil translated))
                (qualifiedExpression result)) (qualifiedBuild result))
            };
            _ -> freshFail "invalid signed recursive plan"
          }) signed;
          let { allDefinitions = append inferred (map fst checked) };
          ordered <- freshLift (traverseEither (\(Triple n _ _) ->
            case find (\(Triple name _ _) -> eqString name n) allDefinitions of {
              Nothing -> Left "qualified recursive plan lost a declaration";
              Just definition -> Right definition
            }) definitions);
          continuation <- planQualified valueScopes ds infos owner scope candidates body;
          qualifiedMake (QualifiedRec ordered (qualifiedExpression continuation))
            (Q.RefNode (qualifiedNode (qualifiedExpression continuation)))
            (qualifiedBuilds (Cons build (Cons (qualifiedBuild continuation) (map snd checked))))
        }
      }
    };
  qualifiedParameters :: Q.Plan -> QualifiedExpr -> Fresh (List (Triple Int String String));
  qualifiedParameters plan expression =
    do {
      slots <- freshLift (Q.slotsAt plan (qualifiedNode expression));
      mapM (\slot -> do {
        name <- freshName "wantedDictionary";
        classId <- freshLift (Q.slotClass plan slot);
        freshPure (Triple slot name classId)
      }) slots
    };
  qualifiedParameterMap :: List (Triple Int String String) -> IntMap String;
  qualifiedParameterMap parameters = IM.fromList (map (\(Triple slot name _) -> Pair slot name) parameters);
  qualifiedWants :: List (Triple Int String String) -> List (Pair String String);
  qualifiedWants parameters = map (\(Triple _ name classId) -> Pair name classId) parameters;
  renderQualified :: Q.Plan -> Map String Info -> IntMap String -> QualifiedExpr -> Fresh SExpr;
  renderQualified plan infos bindings expression =
    case expression of {
      QualifiedExpr node form ->
        case form of {
          QualifiedPlain source -> freshPure source;
          QualifiedVariable name mapping -> renderQualifiedArguments plan bindings node mapping (SVar name);
          QualifiedApply a b -> do {
            left <- renderQualified plan infos bindings a;
            right <- renderQualified plan infos bindings b;
            freshPure (SApp left right)
          };
          QualifiedContext source -> do {
            result <- renderQualified plan infos bindings source;
            renderQualifiedArguments plan bindings node Nothing result
          };
          QualifiedLambda name annotation body -> do {
            result <- renderQualified plan infos bindings body;
            freshPure (SLam name annotation result)
          };
          QualifiedLet name rhs body -> do {
            parameters <- qualifiedParameters plan rhs;
            left <- renderQualified plan infos (qualifiedParameterMap parameters) rhs;
            right <- renderQualified plan infos bindings body;
            freshPure (SLet name (foldr (\(Triple _ n _) b -> SLam n Nothing b) left parameters) right)
          };
          QualifiedAnnotation source annotation -> do {
            result <- renderQualified plan infos bindings source;
            freshPure (SAnn result annotation)
          };
          QualifiedCase source branches -> do {
            result <- renderQualified plan infos bindings source;
            alternatives <- mapM (\(Pair pattern body) -> do {
              branch <- renderQualified plan infos bindings body;
              freshPure (SAlternative pattern branch)
            }) branches;
            freshPure (SCase result alternatives)
          };
          QualifiedChecked ty names candidates source -> do {
            parameters <- qualifiedParameters plan source;
            result <- renderQualified plan infos (qualifiedParameterMap parameters) source;
            freshPure (SChecked ty (foldr (\n b -> SLam n Nothing b)
              (closeWants infos candidates (qualifiedWants parameters) result) names))
          };
          QualifiedRec definitions body -> do {
            lowered <- mapM (\(Triple name mode rhs) -> do {
              parameters <- qualifiedParameters plan rhs;
              result <- renderQualified plan infos (qualifiedParameterMap parameters) rhs;
              freshPure (Triple name mode
                (foldr (\(Triple _ n _) b -> SLam n Nothing b) result parameters))
            }) definitions;
            result <- renderQualified plan infos bindings body;
            freshPure (SLetRec lowered result)
          }
        }
    };
  renderQualifiedArguments :: Q.Plan -> IntMap String -> Int -> Maybe (Pair Int Int) -> SExpr -> Fresh SExpr;
  renderQualifiedArguments plan bindings node mapping source =
    do {
      -- Preserve formal order and multiplicity. Two callee slots can map to
      -- one inherited caller slot; the call still passes both arguments.
      slots <- freshLift (case mapping of {
        Nothing -> Q.slotsAt plan node;
        Just (Pair use input) -> do {
          original <- Q.slotsAt plan input;
          traverseEither (Q.instantiateSlot plan use) original
        }
      });
      names <- freshLift (traverseEither (\slot -> case IM.lookup slot bindings of {
        Nothing -> Left "qualified dictionary slot escaped its lexical abstraction";
        Just name -> Right name
      }) slots);
      freshPure (foldl SApp source (map SVar names))
    };
  lowerExpr :: Map String (List (Pair EvidenceRole String)) -> DataEnv -> Map String Info ->
               Map String (Pair String (List String)) -> List (Pair EvidenceRole String) ->
               SExpr -> Fresh (Pair SExpr (List (Pair String String)));
  lowerExpr valueScopes ds infos env candidates expression =
    do {
      owner <- qualifiedId;
      result <- planQualified valueScopes ds infos owner
        (M.map (\(Pair name classes) -> QualifiedKnown name classes) env) candidates expression;
      build <- qualifiedFinish owner Nothing (qualifiedBuild result);
      plan <- freshLift (case build of {
        QualifiedBuild frames seeds uses nodes -> Q.solve frames seeds uses (IM.fromList nodes)
      });
      let { planned = qualifiedExpression result };
      parameters <- qualifiedParameters plan planned;
      lowered <- renderQualified plan infos (qualifiedParameterMap parameters) planned;
      freshPure (Pair lowered (qualifiedWants parameters))
    };
  wantedNames :: List String -> Fresh (List (Pair String String));
  wantedNames classes =
    mapM
      (\c ->
         do {
           name <- freshName "wantedDictionary";
           freshPure (Pair name c)
         })
      classes;
  signedIn :: Map String (List (Pair EvidenceRole String)) ->
              DataEnv ->
              Map String Info ->
              List (Pair EvidenceRole String) ->
              Map String (Pair String (List String)) -> SExpr -> SType -> Fresh SExpr;
  signedIn valueScopes ds infos available scope expression ty =
    do {
      translated <- freshLift (translateScheme ds infos ty);
      let {
        predicates =
          case scheme ty of {
            Triple _ ps _ -> ps
          }
      };
      names <- mapM (\p -> freshName "givenDictionary") predicates;
      let {
        local = append (map (\n -> Pair GivenEvidence n) names) available
      };
      boundValueShared20 <- lowerExpr valueScopes ds infos scope local expression;
      case boundValueShared20 of {
        Pair body wants ->
          do {
            let {
              closed = closeWants infos local wants body
            };
            freshPure (SChecked translated (foldr (\n b -> SLam n Nothing b) closed names))
          }
      }
    };
  closeWants :: Map String Info ->
                List (Pair EvidenceRole String) -> List (Pair String String) -> SExpr -> SExpr;
  closeWants infos candidates wants expression =
    let {
      replacements =
        M.fromList compareString
          (concatMap
             (\(Pair n c) ->
                case M.lookup compareString c infos of {
                  Nothing -> Nil;
                  Just (Info _ dict _ _ _) -> Cons (Pair n dict) Nil
                })
             wants)
    } in
    closeWanted replacements candidates expression;
  closeWanted :: Map String String -> List (Pair EvidenceRole String) -> SExpr -> SExpr;
  closeWanted replacements candidates expression =
    case expression of {
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
          (map (\(Triple n t a) -> Triple n t (closeWanted replacements candidates a)) definitions)
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
      _ -> freshPure ty
    };
  freshAvoid :: String -> List String -> Fresh String;
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
      _ -> ty
    };
  prettyQualified :: Map String String -> XType -> String;
  prettyQualified names ty =
    case ty of {
      XForall a bound body ->
        ("forall " ++ (prettyBinder a bound ++ (". " ++ prettyQualified names body)));
      _ ->
        case constraints names ty of {
          Pair Nil _ -> Pretty.prettyType ty;
          Pair predicates body ->
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
  constraints :: Map String String -> XType -> Pair (List String) XType;
  constraints names ty =
    case ty of {
      XArrow (XCon dictionary args) body ->
        case M.lookup compareString dictionary names of {
          Nothing -> Pair Nil ty;
          Just name ->
            case constraints names body of {
              Pair predicates result ->
                Pair (Cons (unwords (Cons name (map prettyArgument args))) predicates) result
            }
        };
      _ -> Pair Nil ty
    };
  prettyArgument :: XType -> String;
  prettyArgument ty =
    case ty of {
      XVar _ -> Pretty.prettyType ty;
      XCon _ Nil -> Pretty.prettyType ty;
      _ -> ("(" ++ (Pretty.prettyType ty ++ ")"))
    }
}
