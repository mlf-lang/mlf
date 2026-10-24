-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Constraint where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Kinding as K;
  import qualified Bootstrap.Kind as Kind;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Unicode as Unicode;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  -- The writer keeps edges in reverse creation order. They are reversed once at
  -- the boundary; this preserves dependency-first instantiation exactly.
  data Generation = Generation Graph (List (Pair Int Int)) (List Edge);
  data Generate a = Generate (Generation -> Either String (Pair a Generation));
  runGenerate (Generate f) state = f state;
  generatePure :: forall a. a -> Generate a;
  generatePure value = Generate (\state -> Right (Pair value state));
  generateBind :: forall a b. Generate a -> (a -> Generate b) -> Generate b;
  generateBind action next =
    Generate
      (\state ->
         case runGenerate action state of {
           Left message -> Left message;
           Right (Pair value after) -> seq after (runGenerate (next value) after)
         });
  instance Functor Generate where {
    fmap function action = generateBind action (\value -> generatePure (function value))
  };
  instance Applicative Generate where {
    pure = generatePure;
    (<*>) action argument =
      generateBind action
        (\function -> generateBind argument (\value -> generatePure (function value)))
  };
  instance Monad Generate where {
    (>>=) = generateBind
  };
  failGenerate :: forall a. String -> Generate a;
  failGenerate message = Generate (\_ -> Left message);
  liftResult :: forall a. Either String a -> Generate a;
  liftResult result =
    case result of {
      Left message -> failGenerate message;
      Right value -> return value
    };
  getGraph =
    Generate
      (\state ->
         case state of {
           Generation g _ _ -> Right (Pair g state)
         });
  strictGraph :: Graph -> Graph;
  strictGraph graph = G.strictGraph graph;
  setGraph graph =
    Generate
      (\state ->
         case state of {
           Generation _ eqs es ->
             let {
               strict = strictGraph graph
             } in
             seq strict (Right (Pair Unit (Generation strict eqs es)))
         });
  newNode tag parent flag =
    do {
      graph <- getGraph;
      case G.newNode tag parent flag graph of {
        Pair identity next ->
          do {
            setGraph next;
            seq identity (return identity)
          }
      }
    };
  setNode identity node =
    do {
      graph <- getGraph;
      setGraph (G.setNode identity node graph)
    };
  -- Source names remain hygienic environment keys. Only the target display
  -- hint is encoded; fresh numeric identities still determine binding.
  targetHintTail :: String -> Int -> Bool;
  targetHintTail hint i =
    if i >= stringLength hint then True
    else Lexer.isIdentChar (stringCodeAt hint i) && targetHintTail hint (i + 1);
  encodedHintTail :: String -> Int -> String;
  encodedHintTail hint i =
    if i >= stringLength hint then ""
    else "_" ++ (showInt (stringCodeAt hint i) ++ encodedHintTail hint (i + 1));
  targetNameHint :: String -> String;
  targetNameHint hint =
    if stringLength hint > 0 && Unicode.isAlpha (stringCodeAt hint 0) && targetHintTail hint 1
    then hint
    else "mlfInternal" ++ encodedHintTail hint 0;
  freshName hint =
    do {
      graph <- getGraph;
      case G.freshId graph of {
        Pair identity next ->
          do {
            setGraph next;
            seq identity (return (XName identity (targetNameHint hint)))
          }
      }
    };
  reserveIdentity =
    do {
      graph <- getGraph;
      case G.freshId graph of {
        Pair identity next -> do { setGraph next; return identity }
      }
    };
  -- All pending instance sources are completed children, closed declarations,
  -- or frozen exports. Recursive assumptions contribute equalities only.
  -- Keep the surrounding unfinished graph unnormalized across this boundary.
  flushGeneration :: Generate Unit;
  flushGeneration =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es ->
             do {
               prepared <- Solver.prepare graph;
               initial <- Solver.solverUnify (reverse eqs) prepared;
               solved <-
                 foldM (\solver e -> Solver.instantiateClosed (fromGen e) (toNode e) solver)
                   initial (reverse es);
               finished <- Solver.finish solved;
               Right (Pair Unit (Generation finished Nil Nil))
             }
         });
  equality a b =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es -> Right (Pair Unit (Generation graph (Cons (Pair a b) eqs) es))
         });
  edge gen target =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es ->
             let {
               e = Edge gen target
             } in
             Right (Pair e (Generation graph eqs (Cons e es)))
         });
  generalization (Typed gen _) = gen;
  form (Typed _ f) = f;
  fromGen (Edge gen _) = gen;
  toNode (Edge _ target) = target;
  initialGraph (Constraints graph _ _ _) = graph;
  skeleton (Constraints _ typed _ _) = typed;
  equalities (Constraints _ _ eqs _) = eqs;
  instances (Constraints _ _ _ es) = es;
  sameFlag :: Flag -> Flag -> Bool;
  sameFlag Flexible Flexible = True;
  sameFlag Rigid Rigid = True;
  sameFlag _ _ = False;
  sameType :: SType -> SType -> Bool;
  sameType (STVar a) (STVar b) = eqString a b;
  sameType SBottom SBottom = True;
  sameType (SBottomKind a) (SBottomKind b) = Kind.eqKind a b;
  sameType (SArrow a b) (SArrow c d) = (sameType a c && sameType b d);
  sameType (SCon a xs) (SCon b ys) = (eqString a b && sameTypes xs ys);
  sameType (STypeApp f a) (STypeApp g b) = (sameType f g && sameType a b);
  sameType (SForall f a b t) (SForall g x y u) =
    (sameFlag f g && (eqString a x && (sameType b y && sameType t u)));
  sameType (SQualified ps a) (SQualified qs b) = (samePredicates ps qs && sameType a b);
  sameType _ _ = False;
  sameTypes :: List SType -> List SType -> Bool;
  sameTypes Nil Nil = True;
  sameTypes (Cons a rest) (Cons b remaining) = (sameType a b && sameTypes rest remaining);
  sameTypes _ _ = False;
  samePredicates :: List SPredicate -> List SPredicate -> Bool;
  samePredicates Nil Nil = True;
  samePredicates (Cons (SPredicate n xs) ps) (Cons (SPredicate m ys) qs) =
    (eqString n m && (sameTypes xs ys && samePredicates ps qs));
  samePredicates _ _ = False;
  recursiveRHS :: RecursiveMode -> SExpr -> Core;
  recursiveRHS mode expression =
    case mode of {
      CheckRecursive (SAnnotation Nil ty) ->
        case expression of {
          SChecked other _ ->
            if sameType ty other then desugar expression else CChecked ty expression;
          _ -> CChecked ty expression
        };
      _ -> desugar expression
    };
  desugar :: SExpr -> Core;
  desugar expression =
    case expression of {
      SVar n -> CVar n;
      SConstructor n -> CConstructor n;
      SLam x Nothing body -> CLam x (desugar body);
      SLam x (Just annotation) body ->
        CLam x (CLet x (CApp (CCoerce annotation) (CVar x)) (desugar body));
      SApp a b -> CApp (desugar a) (desugar b);
      SLet x a b -> CLet x (desugar a) (desugar b);
      SAnn a annotation -> CApp (CCoerce annotation) (desugar a);
      SSignature a annotation ->
        case annotation of {
          SAnnotation Nil _ -> recursiveRHS (CheckRecursive annotation) a;
          _ -> CApp (CCoerce annotation) (desugar a)
        };
      SIntLit n -> CInt n;
      SDoubleLit n -> CDouble n;
      SBoolLit b -> CBool b;
      SStringLit text -> CString text;
      SPrimitive p -> CPrimitive p;
      SCase a alternatives ->
        CCase (desugar a)
          (map
             (\branch ->
                case branch of {
                  SAlternative pattern body -> Pair pattern (desugar body)
                })
             alternatives);
      SDo _ _ -> desugar (Desugar.desugarDo expression);
      SLetRec definitions body ->
        CRec
          (map
             (\definition ->
                case definition of {
                  Triple n annotation rhs -> Triple n annotation (recursiveRHS annotation rhs)
                })
             definitions)
          (desugar body);
      SEquations _ -> panic "surface equations escaped lowering";
      SWanted dictionary candidates -> CWanted dictionary candidates;
      SChecked ty body -> CChecked ty body
    };
  generate expression = generateProgram (SProgram Nil expression);
  generateProgram :: SProgram -> Either String Constraints;
  generateProgram program =
    case program of {
      SClassProgram _ _ _ _ ->
        Left "class declarations must be translated before constraint generation";
      SProgram declarations expression ->
        do {
          datatypes <- D.validateDeclarations declarations;
          lowered <- Surface.lowerExpression expression;
          validateAnnotations datatypes lowered;
          result <-
            runGenerate (build datatypes M.empty Nothing M.empty (desugar lowered))
              (Generation G.emptyGraph Nil Nil);
          case result of {
            Pair typed (Generation graph eqs es) ->
              do {
                G.validateGraph graph;
                Right (Constraints graph typed (reverse eqs) (reverse es))
              }
          }
        }
    };
  build :: DataEnv -> Map String Int -> Maybe Int -> Map String Binding -> Core -> Generate Typed;
  build datatypes typeScope parent env core =
    do {
      gen <- newNode (GGen (-1)) parent Flexible;
      root <- newNode GBot (Just gen) Flexible;
      setNode gen (Node (GGen root) parent Flexible);
      let {
        resolved =
          case core of {
            CVar x ->
              if M.member compareString x env
              then core
              else case P.lookupPrimitive x of {
                     Nothing -> core;
                     Just p -> CPrimitive p
                   };
            _ -> core
          }
      };
      f <- buildCore datatypes typeScope env gen root resolved;
      return (Typed gen f)
    };
  buildCore :: DataEnv ->
               Map String Int -> Map String Binding -> Int -> Int -> Core -> Generate Form;
  buildCore datatypes typeScope env gen root core =
    let {
      child = build datatypes typeScope (Just gen)
    } in
    let {
      bottom = newNode GBot (Just gen) Flexible
    } in
    let {
      setTag = \tag -> setNode root (Node tag (Just gen) Flexible)
    } in
    case core of {
      CVar x ->
        case M.lookup compareString x env of {
          Nothing -> failGenerate ("unbound variable: " ++ x);
          Just (Mono name identity) ->
            do {
              equality root identity;
              return (FVariable name Nothing)
            };
          Just (Poly name source) ->
            do {
              e <- edge source root;
              return (FVariable name (Just e))
            };
          Just (DeclaredPoly name source declared) ->
            do {
              e <- edge source root;
              return (FDeclaredVariable name declared e)
            };
          Just (RecursiveMono name shared export) ->
            do {
              equality root shared;
              -- This edge is evidence metadata, never solver work.
              return (FVariable name (Just (Edge export root)))
            }
        };
      CLam x body ->
        do {
          name <- freshName x;
          domain <- bottom;
          result <- bottom;
          setTag (GArr domain result);
          body' <- child (M.insert compareString x (Mono name domain) env) body;
          e <- edge (generalization body') result;
          return (FLambda name domain body' e)
        };
      CApp a b ->
        do {
          a' <- child env a;
          b' <- child env b;
          domain <- bottom;
          arrow <- newNode (GArr domain root) (Just gen) Flexible;
          ea <- edge (generalization a') arrow;
          eb <- edge (generalization b') domain;
          return (FApply a' b' ea eb)
        };
      CLet x a b ->
        do {
          name <- freshName x;
          a' <- child env a;
          b' <- child (M.insert compareString x (Poly name (generalization a')) env) b;
          e <- edge (generalization b') root;
          return (FBinding name a' b' e)
        };
      CRec definitions body ->
        buildRecursive datatypes typeScope env gen root definitions body;
      CWanted dictionary candidates ->
        do {
          declaration <- liftResult (D.lookupDatatype datatypes dictionary);
          graph <- getGraph;
          let {
            scopeRoot = outermost graph gen
          };
          parameters <-
            mapM (\parameter -> newNode (G.bottomTag (snd parameter)) (Just scopeRoot) Flexible)
              (D.datatypeBinders declaration);
          let {
            ps = M.fromList compareString (zip (D.datatypeParameters declaration) parameters)
          };
          embedded <-
            embed datatypes ps (SCon dictionary (map STVar (D.datatypeParameters declaration)));
          attach gen Flexible embedded;
          equality root embedded;
          candidates' <-
            mapM
              (\candidate ->
                 case candidate of {
                   Pair role x ->
                     case M.lookup compareString x env of {
                       Just (Mono name identity) ->
                         return (EvidenceBinding role name identity False);
                       Just (Poly name source) -> return (EvidenceBinding role name source True);
                       Just (DeclaredPoly name _ declared) ->
                         return (DeclaredEvidenceBinding role name declared);
                       Just (RecursiveMono _ _ _) ->
                         failGenerate "recursive dictionary interfaces require an explicit signature";
                       Nothing -> failGenerate ("dictionary candidate is out of scope: " ++ x)
                     }
                 })
              candidates;
          return (FEvidence candidates')
        };
      CChecked signature expression ->
        do {
          embedded <- embed datatypes typeScope signature;
          attach gen Flexible embedded;
          equality root embedded;
          let {
            leading = leadingVariables signature
          };
          let {
            variables = fst leading
          };
          let {
            expected = snd leading
          };
          skolems <-
            mapM
              (\variable ->
                 case variable of {
                   Pair a k ->
                     do {
                       identity <- newNode (G.bottomTag k) (Just gen) Rigid;
                       setNode identity (Node (GSkolem identity k) (Just gen) Rigid);
                       return (Triple a identity k)
                     }
                 })
              variables;
          let {
            local =
              M.union compareString
                (M.fromList compareString
                   (map
                      (\skolem ->
                         case skolem of {
                           Triple a identity _ -> Pair a identity
                         })
                      skolems))
                typeScope
          };
          target <- embed datatypes local expected;
          attach gen Rigid target;
          checked <-
            build datatypes local (Just gen) env
              (desugar (SAnn (directed expected expression) (SAnnotation Nil expected)));
          e <- edge (generalization checked) target;
          return
            (FChecked
               (map
                  (\skolem ->
                     case skolem of {
                       Triple _ identity k -> Pair (XTyVar identity) k
                     })
                  skolems)
               checked
               e)
        };
      CCoerce (SAnnotation existentials ty) ->
        do {
          existentialBindings <-
            mapM
              (\x ->
                 do {
                   identity <- newNode GBot (Just gen) Flexible;
                   return (Pair x identity)
                 })
              existentials;
          let {
            scope = M.union compareString (M.fromList compareString existentialBindings) typeScope
          };
          domain <- embed datatypes scope ty;
          result <- embed datatypes scope ty;
          attach root Rigid domain;
          attach root Flexible result;
          setTag (GArr domain result);
          name <- freshName "coerce";
          return (FCoercion name domain result)
        };
      CInt n ->
        do {
          setTag (GCon "Int" Nil);
          return (FIntegerLiteral n)
        };
      CDouble n ->
        do {
          setTag (GCon "Double" Nil);
          return (FDoubleLiteral n)
        };
      CBool b ->
        do {
          setTag (GCon "Bool" Nil);
          return (FBooleanLiteral b)
        };
      CString text ->
        do {
          setTag (GCon "String" Nil);
          return (FStringLiteral text)
        };
      CPrimitive primitive ->
        do {
          let {
            signature = P.primitiveSignature primitive
          };
          let {
            parameters = fst signature
          };
          identities <-
            mapM (\parameter -> newNode (G.bottomTag (snd parameter)) (Just gen) Flexible)
              parameters;
          ty <- liftResult (sourceField (snd signature));
          embedded <-
            embed datatypes (M.fromList compareString (zip (map fst parameters) identities)) ty;
          attach gen Flexible embedded;
          equality root embedded;
          return (FPrimitive primitive identities)
        };
      CConstructor constructor ->
        do {
          declaration <- liftResult (D.lookupConstructor datatypes constructor);
          let {
            d = fst declaration
          };
          let {
            ctor = snd declaration
          };
          identities <-
            mapM (\parameter -> newNode (G.bottomTag (snd parameter)) (Just gen) Flexible)
              (D.datatypeBinders d);
          let {
            variables = M.fromList compareString (zip (D.datatypeParameters d) identities)
          };
          let {
            result = SCon (D.datatypeName d) (map STVar (D.datatypeParameters d))
          };
          fields <- liftResult (mapM sourceField (D.constructorFields ctor));
          embedded <- embed datatypes variables (foldr SArrow result fields);
          attach gen Flexible embedded;
          equality root embedded;
          return (FConstructor constructor identities)
        };
      CCase scrutinee alternatives ->
        do {
          owner <-
            liftResult
              (D.checkAlternatives datatypes
                 (map (\alternative -> patternShape (fst alternative)) alternatives));
          domain <- bottom;
          parameters <-
            case owner of {
              Nothing -> return M.empty;
              Just d ->
                do {
                  identities <-
                    mapM (\parameter -> newNode (G.bottomTag (snd parameter)) (Just gen) Flexible)
                      (D.datatypeBinders d);
                  let {
                    ps = M.fromList compareString (zip (D.datatypeParameters d) identities)
                  };
                  embedded <-
                    embed datatypes ps
                      (SCon (D.datatypeName d) (map STVar (D.datatypeParameters d)));
                  attach gen Flexible embedded;
                  equality domain embedded;
                  return ps
                }
            };
          a <- child env scrutinee;
          ea <- edge (generalization a) domain;
          branches <-
            mapM (buildBranch datatypes typeScope env gen root domain parameters) alternatives;
          return (FMatch a ea branches)
        }
    };
  checkedRecursive :: Triple String RecursiveMode Core -> Bool;
  checkedRecursive (Triple _ mode _) =
    case mode of { CheckRecursive _ -> True; InferRecursive -> False };
  recursiveCoreNames :: Core -> List String;
  recursiveCoreNames core =
    case core of {
      CVar n -> Cons n Nil;
      CLam n body -> filter (\x -> not (eqString n x)) (recursiveCoreNames body);
      CApp a b -> append (recursiveCoreNames a) (recursiveCoreNames b);
      CLet n a b ->
        append (recursiveCoreNames a)
          (filter (\x -> not (eqString n x)) (recursiveCoreNames b));
      CCase a branches ->
        append (recursiveCoreNames a)
          (concatMap
             (\(Pair pattern body) ->
                filter (\x -> not (elem eqString x (Desugar.patternVariables pattern)))
                  (recursiveCoreNames body)) branches);
      CRec definitions body ->
        let { names = map (\(Triple n _ _) -> n) definitions } in
        filter (\x -> not (elem eqString x names))
          (append (recursiveCoreNames body)
             (concatMap (\(Triple _ _ rhs) -> recursiveCoreNames rhs) definitions));
      CWanted _ candidates -> map snd candidates;
      CChecked _ expression -> Dependency.valueNames (Dependency.observeExpression expression);
      _ -> Nil
    };
  -- The spine is only a multi-root reachability anchor. It has no fresh leaf,
  -- and none of these arrows is used by an instance/equality constraint.
  recursiveAnchor :: Int -> List Int -> Generate Int;
  recursiveAnchor group roots =
    case roots of {
      Nil -> failGenerate "empty recursive inference component";
      Cons root Nil -> newNode (GArr root root) (Just group) Flexible;
      Cons first (Cons second Nil) -> newNode (GArr first second) (Just group) Flexible;
      Cons first rest ->
        do {
          tail <- recursiveAnchor group rest;
          newNode (GArr first tail) (Just group) Flexible
        }
    };
  buildRecursive :: DataEnv -> Map String Int -> Map String Binding -> Int -> Int ->
                    List (Triple String RecursiveMode Core) -> Core -> Generate Form;
  buildRecursive datatypes typeScope env gen root definitions body =
    do {
      let { signed = filter checkedRecursive definitions };
      declarations <- mapM (declareRecursive datatypes gen) signed;
      let {
        signedScope =
          M.union compareString
            (M.fromList compareString
               (map (\(Quad n name source _) -> Pair n (Poly name source)) declarations)) env
      };
      let {
        unsigned = filter (\definition -> not (checkedRecursive definition)) definitions
      };
      let {
        members = M.fromList compareString (map (\d -> case d of { Triple n _ _ -> Pair n d }) unsigned)
      };
      let {
        groups = Dependency.components
          (map (\(Triple n _ rhs) -> Pair n (recursiveCoreNames rhs)) unsigned)
      };
      inferred <-
        foldM
          (\state names ->
             case state of {
               Pair scope done ->
                 do {
                   result <- buildRecursiveGroup datatypes typeScope scope gen
                     (map (\n -> M.findWithDefault compareString
                         (Triple n InferRecursive (CVar n)) n members) names);
                   case result of {
                     Pair scope2 values -> return (Pair scope2 (append done values))
                   }
                 }
             })
          (Pair signedScope Nil) groups;
      case inferred of {
        Pair scope inferredDefinitions ->
          do {
            checkedDefinitions <-
              mapM
                (\(Pair (Quad n name source target) (Triple _ _ rhs)) ->
                   do {
                     value <- build datatypes typeScope (Just gen) scope rhs;
                     proof <- edge (generalization value) target;
                     return (Pair n (RecursiveDefinition name source value proof Nothing))
                   })
                (zip declarations signed);
            let { values = M.fromList compareString (append inferredDefinitions checkedDefinitions) };
            ordered <- mapM
              (\(Triple n _ _) -> case M.lookup compareString n values of {
                 Nothing -> failGenerate "recursive component lost a declaration";
                 Just value -> return value
               }) definitions;
            continuation <- build datatypes typeScope (Just gen) scope body;
            proof <- edge (generalization continuation) root;
            return (FRecursive ordered continuation proof)
          }
      }
    };
  buildRecursiveGroup :: DataEnv -> Map String Int -> Map String Binding -> Int ->
                         List (Triple String RecursiveMode Core) ->
                         Generate (Pair (Map String Binding) (List (Pair String RecursiveDefinition)));
  buildRecursiveGroup datatypes typeScope env parent definitions =
    do {
      group <- newNode (GGen (-1)) (Just parent) Flexible;
      declarations <- mapM
        (\(Triple n _ _) -> do {
           name <- freshName n;
           shared <- newNode GBot (Just group) Flexible;
           export <- reserveIdentity;
           return (Quad n name shared export)
         }) definitions;
      anchor <- recursiveAnchor group (map (\(Quad _ _ shared _) -> shared) declarations);
      setNode group (Node (GGen anchor) (Just parent) Flexible);
      let {
        scope = M.union compareString
          (M.fromList compareString
             (map (\(Quad n name shared export) -> Pair n (RecursiveMono name shared export)) declarations)) env
      };
      bodies <- mapM
        (\(Pair (Quad _ _ shared _) (Triple _ _ rhs)) -> do {
           value <- build datatypes typeScope (Just group) scope rhs;
           proof <- edge (generalization value) shared;
           return (Pair value proof)
         }) (zip declarations definitions);
      flushGeneration;
      exports <- mapM
        (\(Pair (Quad n name shared export) (Pair value proof)) -> do {
           graph <- getGraph;
           materialized <- liftResult (G.materializeExport group shared export parent graph);
           case materialized of {
             Pair (Pair _ copies) next -> do {
               setGraph next;
               return (Pair n (RecursiveDefinition name export value proof
                 (Just (RecursiveClosure group copies))))
             }
           }
         }) (zip declarations bodies);
      let {
        exportedScope = M.union compareString
          (M.fromList compareString
             (map (\(Quad n name _ export) -> Pair n (Poly name export)) declarations)) env
      };
      return (Pair exportedScope exports)
    };
  declareRecursive :: DataEnv ->
                      Int -> Triple String RecursiveMode Core -> Generate (Quad String XName Int Int);
  declareRecursive datatypes gen definition =
    case definition of {
      Triple x (CheckRecursive (SAnnotation Nil ty)) _ ->
        do {
          name <- freshName x;
          declarationGen <- newNode (GGen (-1)) (Just gen) Flexible;
          root <- embed datatypes M.empty ty;
          attach declarationGen Flexible root;
          setNode declarationGen (Node (GGen root) (Just gen) Flexible);
          return (Quad x name declarationGen root)
        };
      Triple _ InferRecursive _ -> failGenerate "unsigned recursive inference is not implemented";
      _ -> failGenerate "recursive definitions require a closed signature"
    };
  outermost :: Graph -> Int -> Int;
  outermost graph identity =
    case G.binder (G.nodeAt graph identity) of {
      Nothing -> identity;
      Just parent -> outermost graph parent
    };
  leadingVariables :: SType -> Pair (List (Pair String Kind)) SType;
  leadingVariables signature =
    case signature of {
      SForall Flexible name SBottom body ->
        let {
          result = leadingVariables body
        } in
        Pair (Cons (Pair name Star) (fst result)) (snd result);
      SForall Flexible name (SBottomKind kind) body ->
        let {
          result = leadingVariables body
        } in
        Pair (Cons (Pair name kind) (fst result)) (snd result);
      _ -> Pair Nil signature
    };
  directed :: SType -> SExpr -> SExpr;
  directed (SArrow domain result) (SLam x annotation body) =
    SLam x (Just (fromMaybe (SAnnotation Nil domain) annotation)) (directed result body);
  directed _ expression = expression;
  freshOptional :: Maybe String -> Generate (Maybe XName);
  freshOptional Nothing = return Nothing;
  freshOptional (Just hint) =
    do {
      name <- freshName hint;
      return (Just name)
    };
  patternBindings :: List (Maybe String) ->
                     List (Maybe XName) -> List (Pair Int (Maybe XType)) -> List (Pair String Binding);
  patternBindings (Cons (Just original) originals) (Cons (Just resolved) names) (Cons (Pair identity declared) identities) =
    Cons (Pair original (case declared of {
      Nothing -> Mono resolved identity;
      Just ty -> DeclaredPoly resolved identity ty
    })) (patternBindings originals names identities);
  patternBindings (Cons _ originals) (Cons _ names) (Cons _ identities) =
    patternBindings originals names identities;
  patternBindings _ _ _ = Nil;
  buildBranch :: DataEnv ->
                 Map String Int ->
                 Map String Binding ->
                 Int -> Int -> Int -> Map String Int -> Pair SPattern Core -> Generate Branch;
  buildBranch datatypes typeScope env gen root domain parameters alternative =
    case alternative of {
      Pair pattern body ->
        do {
          resolved <-
            case pattern of {
              SConstructorPattern constructor names ->
                do {
                  declaration <- liftResult (D.lookupConstructor datatypes constructor);
                  fields <-
                    mapM (patternField datatypes parameters gen)
                      (D.constructorFields (snd declaration));
                  let {
                    used = catMaybes names
                  };
                  unless (length used == length (nubBy eqString used))
                    (failGenerate "duplicate pattern variable");
                  names' <- mapM freshOptional names;
                  return
                    (Pair (XConstructorPattern constructor names')
                       (patternBindings names names' fields))
                };
              SDefaultPattern name ->
                do {
                  resolvedName <- freshOptional name;
                  let {
                    bindings =
                      case name of {
                        Nothing -> Nil;
                        Just original ->
                          case resolvedName of {
                            Nothing -> Nil;
                            Just resolved -> Cons (Pair original (Mono resolved domain)) Nil
                          }
                      }
                  };
                  return (Pair (XDefaultPattern resolvedName) bindings)
                };
              _ -> failGenerate "surface pattern escaped lowering"
            };
          body' <-
            build datatypes typeScope (Just gen)
              (M.union compareString (M.fromList compareString (snd resolved)) env)
              body;
          e <- edge (generalization body') root;
          return (Branch (fst resolved) body' e)
        }
    };
  -- Only a declaration-leading forall grants independent instantiation. A
  -- datatype parameter (even one later unified with a polymorphic type) and
  -- every ordinary field retain their original monomorphic binding.
  patternField :: DataEnv -> Map String Int -> Int -> Field -> Generate (Pair Int (Maybe XType));
  patternField datatypes parameters parent field =
    case field of {
      Quantified _ _ _ -> do {
        gen <- newNode (GGen (-1)) (Just parent) Flexible;
        before <- getGraph;
        embedded <- embedDeclaredField datatypes parameters field;
        after <- getGraph;
        setGraph (pruneEmbedding (G.nextId before) (fst embedded) after);
        -- An external parameter can itself be the entire field root. attach
        -- deliberately leaves its original owner unchanged in that case.
        attach gen Flexible (fst embedded);
        setNode gen (Node (GGen (fst embedded)) (Just parent) Flexible);
        return (Pair gen (Just (snd embedded)))
      };
      _ -> do {
        ty <- liftResult (sourceField field);
        identity <- embed datatypes parameters ty;
        attach parent Rigid identity;
        return (Pair identity Nothing)
      }
    };
  -- Keep the exact declaration alongside its graph view. Its bound IDs are
  -- distinct from free datatype-parameter IDs, including under shadowing;
  -- unused binders survive in the evidence type even when graph pruning drops
  -- them. This metadata never introduces an inferred/generalized field type.
  embedDeclaredField :: DataEnv -> Map String Int -> Field -> Generate (Pair Int XType);
  embedDeclaredField datatypes scope field =
    case field of {
      Parameter name ->
        case M.lookup compareString name scope of {
          Nothing -> failGenerate ("unbound data type parameter: " ++ name);
          Just identity -> return (Pair identity (XVar (XTyVar identity)))
        };
      Function a b -> do {
        root <- newNode GBot Nothing Rigid;
        x <- embedDeclaredField datatypes scope a;
        y <- embedDeclaredField datatypes scope b;
        attachUnscoped root scope (fst x);
        attachUnscoped root scope (fst y);
        setNode root (Node (GArr (fst x) (fst y)) Nothing Rigid);
        return (Pair root (XArrow (snd x) (snd y)))
      };
      Applied constructor arguments -> do {
        let { kind = D.constructorKind datatypes constructor (length arguments) };
        head <- newNode
          (if Kind.eqKind kind Star then GCon constructor Nil else GTyCon constructor kind)
          Nothing Rigid;
        foldM (\f argument -> do {
          a <- embedDeclaredField datatypes scope argument;
          root <- embedApplication scope (fst f) (fst a);
          return (Pair root (T.apply (snd f) (snd a)))
        }) (Pair head (XCon constructor Nil)) arguments
      };
      Application f a -> do {
        x <- embedDeclaredField datatypes scope f;
        y <- embedDeclaredField datatypes scope a;
        root <- embedApplication scope (fst x) (fst y);
        return (Pair root (T.apply (snd x) (snd y)))
      };
      Quantified name kind body -> do {
        bound <- newNode (G.bottomTag kind) Nothing Flexible;
        result <- embedDeclaredField datatypes (M.insert compareString name bound scope) body;
        graph <- getGraph;
        when ((bound /= fst result) && IS.member bound (G.reachable graph (fst result)))
          (setNode bound (Node (G.tag (G.nodeAt graph bound)) (Just (fst result)) Flexible));
        return (Pair (fst result) (XForall (XTyVar bound) (T.bottomKind kind) (snd result)))
      }
    };
  sourceField :: Field -> Either String SType;
  sourceField field =
    case field of {
      Parameter parameter -> Right (STVar parameter);
      Function a b ->
        do {
          x <- sourceField a;
          y <- sourceField b;
          Right (SArrow x y)
        };
      Applied constructor types ->
        do {
          fields <- mapM sourceField types;
          Right (SCon constructor fields)
        };
      Application f a ->
        do {
          x <- sourceField f;
          y <- sourceField a;
          Right (STypeApp x y)
        };
      Quantified name kind body ->
        do {
          ty <- sourceField body;
          Right
            (SForall Flexible name (if Kind.eqKind kind Star then SBottom else SBottomKind kind) ty)
        }
    };
  patternShape :: SPattern -> Pair (Maybe String) Int;
  patternShape (SConstructorPattern constructor names) = Pair (Just constructor) (length names);
  patternShape (SDefaultPattern _) = Pair Nothing 0;
  patternShape _ = panic "surface pattern escaped lowering";
  validateAnnotations datatypes expression = validateIn datatypes M.empty expression;
  validateAnnotation datatypes scope annotation =
    case annotation of {
      SAnnotation variables ty ->
        K.annotationType datatypes
          (M.union compareString
             (M.fromList compareString (map (\name -> Pair name Star) variables))
             scope)
          ty
    };
  validateBinders :: DataEnv -> Map String Kind -> SType -> Either String (Map String Kind);
  validateBinders datatypes scope ty =
    case ty of {
      SForall _ name bound body ->
        do {
          kind <- K.kindOf datatypes scope bound;
          validateBinders datatypes (M.insert compareString name kind scope) body
        };
      _ -> Right scope
    };
  validateIn :: DataEnv -> Map String Kind -> SExpr -> Either String Unit;
  validateIn datatypes scope expression =
    case expression of {
      SVar _ -> Right Unit;
      SConstructor _ -> Right Unit;
      SLam _ annotation body ->
        do {
          case annotation of {
            Nothing -> Right Unit;
            Just value -> validateAnnotation datatypes scope value
          };
          validateIn datatypes scope body
        };
      SApp a b ->
        do {
          validateIn datatypes scope a;
          validateIn datatypes scope b
        };
      SLet _ a b ->
        do {
          validateIn datatypes scope a;
          validateIn datatypes scope b
        };
      SAnn a annotation ->
        do {
          validateIn datatypes scope a;
          validateAnnotation datatypes scope annotation
        };
      SSignature a annotation ->
        case annotation of {
          SAnnotation Nil ty -> validateIn datatypes scope (SChecked ty a);
          _ -> validateIn datatypes scope (SAnn a annotation)
        };
      SIntLit _ -> Right Unit;
      SDoubleLit n ->
        unless (andInt (doubleToBits n) 9218868437227405312 /= 9218868437227405312)
          (Left "non-finite Double literal");
      SBoolLit _ -> Right Unit;
      SStringLit _ -> Right Unit;
      SPrimitive _ -> Right Unit;
      SCase a branches ->
        do {
          validateIn datatypes scope a;
          mapM_
            (\branch ->
               case branch of {
                 SAlternative _ b -> validateIn datatypes scope b
               })
            branches
        };
      SDo _ _ -> validateIn datatypes scope (Desugar.desugarDo expression);
      SEquations _ -> Left "surface equations escaped lowering";
      SLetRec definitions body ->
        do {
          mapM_
            (\definition ->
               case definition of {
                 Triple _ annotation value ->
                   do {
                     validateRecursiveMode datatypes scope annotation;
                     case annotation of {
                       InferRecursive -> validateIn datatypes scope value;
                       CheckRecursive signature ->
                         validateIn datatypes scope (SSignature value signature)
                     }
                   }
               })
            definitions;
          validateIn datatypes scope body
        };
      SWanted _ _ -> Right Unit;
      SChecked ty body ->
        do {
          K.annotationType datatypes scope ty;
          local <- validateBinders datatypes scope ty;
          validateIn datatypes local body
        }
    };
  validateRecursiveMode :: DataEnv -> Map String Kind -> RecursiveMode -> Either String Unit;
  validateRecursiveMode datatypes scope mode =
    case mode of {
      InferRecursive -> Right Unit;
      CheckRecursive annotation -> validateAnnotation datatypes scope annotation
    };
  attach parent flag identity =
    do {
      graph <- getGraph;
      let {
        node = G.nodeAt graph identity
      };
      case G.binder node of {
        Nothing -> setNode identity (Node (G.tag node) (Just parent) flag);
        Just _ -> return Unit
      }
    };
  -- Source aliases share identities. Only reachable nodes survive embedding;
  -- unused, alias and forall-a.a bounds never become target quantifiers.
  embed :: DataEnv -> Map String Int -> SType -> Generate Int;
  embed datatypes scope ty =
    do {
      before <- getGraph;
      let {
        start = G.nextId before
      };
      root <- embedType datatypes scope ty;
      after <- getGraph;
      setGraph (pruneEmbedding start root after);
      return root
    };
  -- Every allocated identity is below nextId. Preserve the final values of old
  -- nodes and visit only this embedding's fresh interval, including any gaps.
  -- Rebuilding the whole persistent map here makes generation quadratic.
  pruneEmbedding :: Int -> Int -> Graph -> Graph;
  pruneEmbedding start root graph =
    let {
      retained = pruneFreshNodes start (G.nextId graph) (G.reachable graph root) (G.nodes graph)
    } in
    G.mkGraph retained (G.links graph) (G.nextId graph);
  pruneFreshNodes :: Int -> Int -> IntSet -> IntMap Node -> IntMap Node;
  pruneFreshNodes identity stop keep retained =
    if (identity >= stop)
    then retained
    else if IS.member identity keep
         then pruneFreshNodes (identity + 1) stop keep retained
         else let {
                remaining = IM.delete identity retained
              } in
              seq remaining (pruneFreshNodes (identity + 1) stop keep remaining);
  isScoped scope identity = any (\entry -> (entry == identity)) (M.elems scope);
  attachUnscoped parent scope identity =
    unless (isScoped scope identity) (attach parent Rigid identity);
  embedType :: DataEnv -> Map String Int -> SType -> Generate Int;
  embedType datatypes scope ty =
    case ty of {
      STVar name ->
        case M.lookup compareString name scope of {
          Nothing -> failGenerate ("unbound annotation type variable: " ++ name);
          Just identity -> return identity
        };
      SBottom -> newNode GBot Nothing Flexible;
      SBottomKind kind -> newNode (G.bottomTag kind) Nothing Flexible;
      SArrow a b ->
        do {
          root <- newNode GBot Nothing Rigid;
          x <- embedType datatypes scope a;
          y <- embedType datatypes scope b;
          attachUnscoped root scope x;
          attachUnscoped root scope y;
          setNode root (Node (GArr x y) Nothing Rigid);
          return root
        };
      SCon constructor arguments ->
        do {
          let {
            kind = D.constructorKind datatypes constructor (length arguments)
          };
          head <-
            newNode
              (if Kind.eqKind kind Star then GCon constructor Nil else GTyCon constructor kind)
              Nothing
              Rigid;
          foldM
            (\f argument ->
               do {
                 a <- embedType datatypes scope argument;
                 embedApplication scope f a
               })
            head
            arguments
        };
      STypeApp f a ->
        do {
          x <- embedType datatypes scope f;
          y <- embedType datatypes scope a;
          embedApplication scope x y
        };
      SForall flag name bound body ->
        do {
          b <- embedType datatypes scope bound;
          result <- embedType datatypes (M.insert compareString name b scope) body;
          graph <- getGraph;
          when ((b /= result) && (IS.member b (G.reachable graph result) && not (isScoped scope b)))
            (setNode b (Node (G.tag (G.nodeAt graph b)) (Just result) flag));
          return result
        };
      SQualified _ _ -> failGenerate "untranslated class constraint"
    };
  embedApplication scope f a =
    do {
      root <- newNode (GTyApp f a) Nothing Rigid;
      attachUnscoped root scope f;
      attachUnscoped root scope a;
      return root
    };
  solve :: Constraints -> Either String Graph;
  solve constraints =
    do {
      solved <- solvePrepared constraints;
      Right (Solver.solverGraph solved)
    };
  -- Normalization only changes flags: structural indexes depend on tags,
  -- binding indexes on binders, and scope indexes on Gen tags/binders.
  -- finishNormalized checks the whole graph and indexes before this
  -- validity-preserving transformation, then shares the finished indexes.
  solvePrepared :: Constraints -> Either String Solver;
  solvePrepared constraints =
    do {
      prepared <- Solver.prepare (initialGraph constraints);
      initial <- Solver.solverUnify (equalities constraints) prepared;
      solved <-
        foldM (\solver e -> Solver.instantiateClosed (fromGen e) (toNode e) solver) initial
          (instances constraints);
      Solver.finishNormalized solved
    };
  eraseSource typed = eraseSourceWith IM.empty typed;
  eraseSourceWith :: IntMap XTerm -> Typed -> XErased;
  eraseSourceWith evidence typed =
    case form typed of {
      FVariable name _ -> XEVar name;
      FDeclaredVariable name _ _ -> XEVar name;
      FLambda name _ body _ -> XEAbs name (eraseSourceWith evidence body);
      FApply a b _ _ -> XEApp (eraseSourceWith evidence a) (eraseSourceWith evidence b);
      FBinding name a b _ -> XELet name (eraseSourceWith evidence a) (eraseSourceWith evidence b);
      FCoercion name _ _ -> XEAbs name (XEVar name);
      FIntegerLiteral n -> XEInt n;
      FDoubleLiteral n -> XEDouble n;
      FBooleanLiteral b -> XEBool b;
      FStringLiteral text -> XEString text;
      FPrimitive p _ -> XEPrimitive p;
      FConstructor constructor _ -> XEConstructor constructor;
      FMatch scrutinee _ branches ->
        XECase (eraseSourceWith evidence scrutinee)
          (map
             (\branch ->
                case branch of {
                  Branch pattern body _ ->
                    XErasedAlternative pattern (eraseSourceWith evidence body)
                })
             branches);
      FRecursive definitions body _ ->
        XELetRec
          (map
             (\definition ->
                case definition of {
                  RecursiveDefinition name _ rhs _ _ -> Pair name (eraseSourceWith evidence rhs)
                })
             definitions)
          (eraseSourceWith evidence body);
      FEvidence _ ->
        case IM.lookup (generalization typed) evidence of {
          Nothing -> XEEvidenceHole (generalization typed);
          Just proof -> X.erase proof
        };
      FChecked _ body _ -> eraseSourceWith evidence body
    }
}
