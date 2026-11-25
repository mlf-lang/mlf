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
  import qualified Bootstrap.IndexVec as V;
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
  -- The writer keeps solver work in reverse dependency order. A case barrier
  -- carries a sealed descriptor list before any alternative body is generated.
  data Generation = Generation Graph ([] ((,) Int Int)) ([] SolveStep);
  -- The file compiler owns one resolver snapshot. Its module handles remain
  -- meaningful only inside the current declaration binding environment.
  -- Public/manual inputs may combine snapshots and resolve their exact rows.
  data CandidateMemo = SeparateEnvironments | SharedEnvironments (IntMap ResolvedCandidateEnvironment) |
    BatchedEnvironments (IntMap ResolvedCandidateEnvironment);
  candidateTable memo = case memo of {
    SharedEnvironments table -> table; BatchedEnvironments table -> table; SeparateEnvironments -> IM.empty
  };
  replaceCandidateTable memo table = case memo of {
    SharedEnvironments _ -> SharedEnvironments table; BatchedEnvironments _ -> BatchedEnvironments table;
    SeparateEnvironments -> SeparateEnvironments
  };
  data Generate a = Generate (Generation -> Either String ((,) a Generation)) |
    WithCandidates (CandidateMemo -> Generation -> Either String ((,,) a Generation CandidateMemo));
  runWithCandidates memo action state = case action of {
    Generate f -> case f state of {
      Left message -> Left message;
      Right ((,) value after) -> Right ((,,) value after memo)
    };
    WithCandidates f -> f memo state
  };
  runGeneration memo action state = case runWithCandidates memo action state of {
    Left message -> Left message;
    Right ((,,) value after _) -> Right ((,) value after)
  };
  runGenerate action state = runGeneration SeparateEnvironments action state;
  generatePure :: forall a. a -> Generate a;
  generatePure value = Generate (\state -> Right ((,) value state));
  generateBind :: forall a b. Generate a -> (a -> Generate b) -> Generate b;
  generateBind action next = WithCandidates (\memo state ->
    case runWithCandidates memo action state of {
      Left message -> Left message;
      Right ((,,) value after memo2) -> seq after (runWithCandidates memo2 (next value) after)
    });
  -- Lexical binders cannot change a declaration slot. A declaration binder
  -- installs a different slot table, whose memo lives only inside its body.
  withDeclarationScope action = WithCandidates (\memo state -> case memo of {
    SeparateEnvironments -> runWithCandidates SeparateEnvironments action state;
    _ -> case runWithCandidates (replaceCandidateTable memo IM.empty) action state of {
      Left message -> Left message;
      Right ((,,) value after _) -> Right ((,,) value after memo)
    }
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
           Generation g _ _ -> Right ((,) g state)
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
             seq strict (Right ((,) () (Generation strict eqs es)))
         });
  newNode tag parent flag =
    do {
      graph <- getGraph;
      case G.newNode tag parent flag graph of {
        (,) identity next ->
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
        (,) identity next ->
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
        (,) identity next -> do { setGraph next; return identity }
      }
    };
  -- All pending instance sources are completed children, closed declarations,
  -- or frozen exports. Recursive assumptions contribute equalities only.
  -- Keep the surrounding unfinished graph unnormalized across this boundary.
  flushGeneration :: Generate ();
  flushGeneration =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es ->
             do {
               solved <- Solver.solveGenerated graph (reverse eqs) (reverse es);
               finished <- Solver.finish solved;
               Right ((,) () (Generation finished [] []))
             }
         });
  equality a b =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es -> Right ((,) () (Generation graph ((:) ((,) a b) eqs) es))
         });
  edge gen target =
    Generate
      (\state ->
         case state of {
           Generation graph eqs es ->
             let {
               e = Edge gen target
             } in
             Right ((,) e (Generation graph eqs ((:) (Instantiate e) es)))
         });
  projectCase fields =
    Generate
      (\state ->
         case state of {
           Generation graph eqs steps ->
             Right ((,) () (Generation graph eqs ((:) (ProjectCase fields) steps)))
         });
  evaluateStep :: Solver -> SolveStep -> Either String Solver;
  evaluateStep solver step =
    case step of {
      Instantiate e -> Solver.instantiateClosed (fromGen e) (toNode e) solver;
      ProjectCase fields -> Solver.projectCaseFields fields solver
    };
  evaluateSteps :: Solver -> [] SolveStep -> Either String Solver;
  evaluateSteps initial steps = foldM evaluateStep initial steps;
  -- These entry points accept an externally supplied prepared solver.
  evaluatePreparedStep :: Solver -> SolveStep -> Either String Solver;
  evaluatePreparedStep solver step =
    case step of {
      Instantiate e -> Solver.instantiateClosedPrepared (fromGen e) (toNode e) solver;
      ProjectCase fields -> Solver.projectCaseFields fields solver
    };
  evaluatePreparedSteps :: Solver -> [] SolveStep -> Either String Solver;
  evaluatePreparedSteps initial steps = let {
    advance ((,) solver cache) step = case step of {
      Instantiate e -> Solver.instantiateClosedWith cache (fromGen e) (toNode e) solver;
      ProjectCase fields -> mapEither (\result -> (,) result cache) (Solver.projectCaseFields fields solver)
    }
  } in mapEither fst (foldM advance ((,) initial Solver.emptyUnificationCache) steps);
  generalization (Typed gen _) = gen;
  rawForm (Typed _ f) = f;
  form typed = stripGivenScope (rawForm typed);
  stripGivenScope f = case f of { FWithGivens _ body -> stripGivenScope body; _ -> f };
  fromGen (Edge gen _) = gen;
  toNode (Edge _ target) = target;
  initialGraph (Constraints graph _ _ _) = graph;
  skeleton (Constraints _ typed _ _) = typed;
  equalities (Constraints _ _ eqs _) = eqs;
  solveSteps (Constraints _ _ _ steps) = steps;
  -- Edge-only inspection/evidence view. Solver drivers must use solveSteps.
  instances constraints = concatMap (\step -> case step of {
    Instantiate e -> (:) e [];
    ProjectCase _ -> []
  }) (solveSteps constraints);
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
  sameTypes :: [] SType -> [] SType -> Bool;
  sameTypes [] [] = True;
  sameTypes ((:) a rest) ((:) b remaining) = (sameType a b && sameTypes rest remaining);
  sameTypes _ _ = False;
  samePredicates :: [] SPredicate -> [] SPredicate -> Bool;
  samePredicates [] [] = True;
  samePredicates ((:) (SPredicate n xs) ps) ((:) (SPredicate m ys) qs) =
    (eqString n m && (sameTypes xs ys && samePredicates ps qs));
  samePredicates _ _ = False;
  recursiveRHS :: RecursiveMode -> SExpr -> Core;
  recursiveRHS mode expression =
    case mode of {
      CheckRecursive (SAnnotation [] ty) ->
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
      SGlobal i hint -> CGlobal i hint;
      SDeclScope [i] (SLam n (Just annotation) body) ->
        CDeclScope [i] (CLam n (CDeclScope [i] (CLet n (CApp (CCoerce annotation) (CGlobal i n)) (desugar body))));
      SDeclScope ids body -> CDeclScope ids (desugar body);
      SWantedRefs dictionary candidates -> CWantedRefs dictionary candidates;
      SWantedScope dictionary environment -> CWantedScope dictionary environment;
      SGivenScope names body -> CGivenScope names (desugar body);
      SConstructor n -> CConstructor n;
      SLam x Nothing body -> CLam x (desugar body);
      SLam x (Just annotation) body ->
        CLam x (CLet x (CApp (CCoerce annotation) (CVar x)) (desugar body));
      SApp a (SWantedScope dictionary candidates) -> scopedDictionaryApplications a [(,) dictionary candidates];
      SApp a b -> CApp (desugar a) (desugar b);
      SApplyDictionaries function arguments -> CApplyDictionaries function arguments;
      SBindDictionaries names body -> CBindDictionaries names (desugar body);
      SLet x a b -> CLet x (desugar a) (desugar b);
      SAnn a annotation -> CApp (CCoerce annotation) (desugar a);
      SSignature a annotation ->
        case annotation of {
          SAnnotation [] _ -> recursiveRHS (CheckRecursive annotation) a;
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
                  SAlternative pattern body -> (,) pattern (desugar body)
                })
             alternatives);
      SDo _ _ -> desugar (Desugar.desugarDo expression);
      SLetRec definitions body ->
        CRec
          (map
             (\definition ->
                case definition of {
                  (,,) n annotation rhs -> (,,) n annotation (recursiveRHS annotation rhs)
                })
             definitions)
          (desugar body);
      SEquations _ -> panic "surface equations escaped lowering";
      SSourceDefinition _ -> panic "source definition provenance escaped class lowering";
      SCallSite _ _ _ -> panic "source call site escaped class lowering";
      SSharedBind _ _ _ _ _ -> panic "shared pattern bind escaped surface lowering";
      SWanted dictionary candidates -> CWanted dictionary candidates;
      SChecked ty body -> CChecked ty body
    };
  generate expression = generateProgram (SProgram [] expression);
  generateProgram :: SProgram -> Either String Constraints;
  generateProgram = generateProgramWith SeparateEnvironments;
  generateFileProgram = generateProgramWith (SharedEnvironments IM.empty);
  generateProgramWith memo program = do {
    constraints <- generateUncheckedProgramWith memo program;
    G.validateGraph (initialGraph constraints);
    Right constraints
  };
  -- This entry point immediately solves the generated constraints. The
  -- solver prepares and validates the same initial graph before using it.
  generateAndSolveFileProgram :: SProgram -> Either String ((,) Constraints Solver);
  generateAndSolveFileProgram program = do {
    constraints <- generateUncheckedProgramWith (SharedEnvironments IM.empty) program;
    solved <- solvePrepared constraints;
    Right ((,) constraints solved)
  };
  generateUncheckedProgramWith memo program =
    case program of {
      SClassProgram _ _ _ _ ->
        Left "class declarations must be translated before constraint generation";
      SProgram declarations expression ->
        do {
          datatypes <- D.validateDeclarations declarations;
          lowered <- Surface.lowerExpression expression;
          validateAnnotations datatypes lowered;
          result <-
            runGeneration memo (build datatypes M.empty Nothing M.empty (desugar lowered))
              (Generation G.emptyGraph [] []);
          case result of {
            (,) typed (Generation graph eqs es) ->
              Right (Constraints graph typed (reverse eqs) (reverse es))
          }
        }
    };
  data BindingEnv = BindingEnv (Map String Binding) (Map (V.Index Declaration) Binding) |
    ClosedPrimitiveScope BindingEnv;
  compareRefSlot a b = compareInt (V.toInt a) (V.toInt b);
  compareTermRef a b = case (,) a b of {
    (,) (LexicalRef x) (LexicalRef y) -> compareString x y;
    (,) (DeclRef i _) (DeclRef j _) -> compareRefSlot i j;
    (,) (LexicalRef _) _ -> 0 - 1;
    _ -> 1
  };
  lookupTerm (ClosedPrimitiveScope env) ref = lookupTerm env ref;
  lookupTerm (BindingEnv locals globals) ref = case ref of {
    LexicalRef n -> M.lookup compareString n locals;
    DeclRef i _ -> M.lookup compareRefSlot i globals
  };
  bindTerm (ClosedPrimitiveScope env) ref value = ClosedPrimitiveScope (bindTerm env ref value);
  bindTerm (BindingEnv locals globals) ref value = case ref of {
    LexicalRef n -> BindingEnv (M.insert compareString n value locals) globals;
    DeclRef i _ -> BindingEnv locals (M.insert compareRefSlot i value globals)
  };
  bindTerms env entries = foldlStrict (\scope ((,) ref value) -> bindTerm scope ref value) env entries;
  isDeclarationRef ref = case ref of { DeclRef _ _ -> True; _ -> False };
  withBoundRef ref action = if isDeclarationRef ref then withDeclarationScope action else action;
  evidenceBinding = evidenceBindingIn M.empty;
  evidenceBindingIn imported env ((,) role ref) = case lookupTerm env ref of {
    Just (Mono name identity) -> Right (EvidenceBinding role name identity False);
    Just (Poly name source) -> Right (EvidenceBinding role name source True);
    Just (DeclaredPoly name _ declared) -> Right (DeclaredEvidenceBinding role name declared);
    Just (RecursiveMono _ _ _) -> Left "recursive dictionary interfaces require an explicit signature";
    Just (RecursiveDictionaryMono _ _ _ _) -> Left "recursive dictionary interfaces require an explicit signature";
    Nothing -> let { missing = Left ("dictionary candidate is out of scope: " ++ termRefName ref) } in
      case ref of {
        DeclRef i _ -> case M.lookup compareRefSlot i imported of {
          Just ((,) name declared) -> Right (DeclaredEvidenceBinding role name declared);
          Nothing -> missing
        };
        LexicalRef _ -> missing
      }
  };
  resolveCandidateEnvironment = resolveCandidateEnvironmentIn M.empty;
  resolveCandidateEnvironmentIn imported env gen (CandidateEnvironment owner refs) =
    WithCandidates (\memo state -> let {
      resolve = traverseEither (evidenceBindingIn imported env) refs;
      fresh rows = ResolvedCandidateEnvironment gen rows
    } in case memo of {
      SeparateEnvironments -> mapEither (\rows -> (,,) (fresh rows) state memo) resolve;
      _ -> let { table = candidateTable memo } in case IM.lookup owner table of {
        Just shared -> Right ((,,) shared state memo);
        Nothing -> do {
          -- Only declaration references belong to a module's immutable base.
          ensure (all (compose isDeclarationRef snd) refs) "lexical binding in module evidence environment";
          rows <- resolve;
          let { shared = fresh rows; next = IM.insert owner shared table };
          seq next (Right ((,,) shared state (replaceCandidateTable memo next)))
        }
      }
    });
  build :: DataEnv -> Map String Int -> Maybe Int -> Map String Binding -> Core -> Generate Typed;
  build datatypes typeScope parent locals = buildIn datatypes typeScope parent (BindingEnv locals M.empty);
  buildIn :: DataEnv -> Map String Int -> Maybe Int -> BindingEnv -> Core -> Generate Typed;
  buildIn = buildInWithEvidence M.empty;
  -- Checked file imports that occur only in wanted inventories belong to the
  -- evidence namespace. All public builders begin with an empty inventory.
  buildInWithEvidence imported datatypes typeScope parent env core =
    generalize parent (\gen root -> withBindingRoot gen (\scopeRoot ->
      buildCoreUnderIn ((,) scopeRoot imported) datatypes typeScope env gen root core));
  generalize :: Maybe Int -> (Int -> Int -> Generate Form) -> Generate Typed;
  generalize parent makeForm = do {
    gen <- newNode (GGen (-1)) parent Flexible;
    root <- newNode GBot (Just gen) Flexible;
    setNode gen (Node (GGen root) parent Flexible);
    f <- makeForm gen root;
    return (Typed gen f)
  };
  -- Descendants are generated under the same binding root. An entry may
  -- start inside an existing graph, including the crate import wrappers.
  -- Derive its root from that graph once, only if a wanted type needs it.
  withBindingRoot :: forall a. Int -> (Int -> Generate a) -> Generate a;
  withBindingRoot gen action = do {
    graph <- getGraph;
    action (outermost graph gen)
  };
  buildUnder :: Int -> DataEnv -> Map String Int -> Int -> BindingEnv -> Core -> Generate Typed;
  buildUnder root = buildUnderIn ((,) root M.empty);
  buildUnderIn scopeRoot datatypes typeScope parent env core =
    generalize (Just parent) (\gen root -> buildCoreUnderIn scopeRoot datatypes typeScope env gen root core);
  buildCore :: DataEnv ->
               Map String Int -> BindingEnv -> Int -> Int -> Core -> Generate Form;
  buildCore datatypes typeScope env gen root core = withBindingRoot gen
    (\scopeRoot -> buildCoreUnder scopeRoot datatypes typeScope env gen root core);
  -- The authenticated imported scheme has the precise rank-one shape
  -- forall a. D a -> [Char] -> a. Every constructor in its checked
  -- embedding is rigid, and the unique flexible hole belongs to the
  -- outer arrow. Other converters keep ordinary application inference.
  caseConverter :: BindingEnv -> Graph -> TermRef -> Bool;
  caseConverter env graph ref =
    let { node = G.nodeAt graph;
          nominal parent name ty = case node ty of {
            Node (GCon actual []) (Just owner) Rigid -> owner == parent && eqString actual name;
            _ -> False
          };
          list parent ty = case node ty of {
            Node (GTyApp head element) (Just owner) Rigid -> owner == parent &&
              (case node head of {
                Node (GTyCon name (KArrow Star Star)) (Just holder) Rigid ->
                  holder == ty && eqString name "[]" && nominal ty "Char" element;
                _ -> False
              });
            _ -> False
          };
          dictionary parent parameter ty = case node ty of {
            Node (GTyApp head argument) (Just owner) Rigid -> owner == parent && argument == parameter &&
              (case node head of { Node (GTyCon _ (KArrow Star Star)) (Just holder) Rigid -> holder == ty; _ -> False });
            _ -> False
          };
          scheme source = let { root = G.genRoot graph source } in case node root of {
            Node (GArr domain range) (Just owner) Flexible -> owner == source && (case node range of {
              Node (GArr chars parameter) (Just holder) Rigid -> holder == root && dictionary root parameter domain &&
                list range chars && (case node parameter of {
                  Node GBot (Just binding) Flexible -> binding == root; _ -> False
                });
              _ -> False
            });
            _ -> False
          }
    } in case ref of {
      DeclRef _ _ -> case lookupTerm env ref of { Just (Poly _ source) -> scheme source; _ -> False };
      _ -> False
    };
  checkedStringConverterName env graph ref =
    if not (caseConverter env graph ref) then Nothing else case lookupTerm env ref of {
      Just (Poly name source) -> case G.tag (G.nodeAt graph (G.genRoot graph source)) of {
        GArr domain _ -> case G.tag (G.nodeAt graph domain) of {
          GTyApp head _ -> case G.tag (G.nodeAt graph head) of {
            GTyCon dictionary _ -> Just ((,) name dictionary); _ -> Nothing
          }; _ -> Nothing
        }; _ -> Nothing
      }; _ -> Nothing
    };
  caseCoreRef :: Core -> Maybe TermRef;
  caseCoreRef expr = case expr of {
    CVar name -> Just (LexicalRef name); CGlobal i name -> Just (DeclRef i name); _ -> Nothing
  };
  caseRefTerm :: TermRef -> Core;
  caseRefTerm ref = case ref of {
    LexicalRef name -> CVar name; DeclRef i name -> CGlobal i name
  };
  stringArm :: Core -> Maybe ((,,,) TermRef TermRef String String);
  stringArm expr = case expr of {
    CApp function (CApp (CApp conversion (CVar dictionary)) (CApp (CPrimitive PTextToChars) (CString text))) -> do {
      f <- caseCoreRef function; c <- caseCoreRef conversion;
      Just ((,,,) f c dictionary text)
    };
    _ -> Nothing
  };
  integerTest :: Core -> Maybe ((,) TermRef Int);
  integerTest condition = case condition of {
    CApp (CApp (CPrimitive PEqInt) subject) (CInt key) -> mapOptional (\name -> (,) name key) (caseCoreRef subject);
    _ -> Nothing
  };
  -- Arms stay in source order, including repeated keys. No later literal
  -- forces its function, evidence, payload or the otherwise branch.
  stringCallRun :: BindingEnv -> ((,) TermRef Int) -> ((,,,) TermRef TermRef String String) -> Core ->
    Maybe ((,) ([] ((,,) Int String String)) Core);
  stringCallRun env ((,) subject key) ((,,,) f convert evidence first) no = let {
      collect rows expr = case expr of {
        CApp (CApp (CApp (CPrimitive PIfThenElse) test) arm) rest ->
          let { next = do {
            (,) s k <- integerTest test;
            (,,,) g c d text <- stringArm arm;
            if compareTermRef s subject /= 0 || compareTermRef g f /= 0 || compareTermRef c convert /= 0 then Nothing
            else case lookupTerm env (LexicalRef d) of {
              Just (Mono _ _) -> Just ((,,) k d text); _ -> Nothing
            }
          } } in case next of {
            Just row -> collect ((:) row rows) rest; Nothing -> (,) rows expr
          };
        _ -> (,) rows expr
      }
    } in case lookupTerm env (LexicalRef evidence) of {
      Just (Mono _ _) -> case collect [(,,) key evidence first] no of {
        (,) rows rest -> if null (drop 7 rows) then Nothing else Just ((,) (reverse rows) rest)
      };
      _ -> Nothing
    };
  -- This surface form can only be issued by the class planner. Collect a
  -- contiguous prefix once, including when a callee fails admission.
  scopedDictionaryApplications expression arguments = case expression of {
    SApp inner (SWantedScope dictionary candidates) ->
      scopedDictionaryApplications inner ((:) ((,) dictionary candidates) arguments);
    SGlobal slot hint -> if null (drop 7 arguments) then ordinaryScopedDictionaries (CGlobal slot hint) arguments
      else CApplyScopedDictionaries (DeclRef slot hint) arguments;
    _ -> ordinaryScopedDictionaries (desugar expression) arguments
  };
  ordinaryScopedDictionaries callee arguments = foldl (\f ((,) dictionary candidates) ->
    CApp f (CWantedScope dictionary candidates)) callee arguments;
  -- Only the scheme root may be flexible. Every structural child of the
  -- saved arrow is rigid, closed and owned by this scheme. No intermediate
  -- function can generalize a free type or introduce another type argument.
  groundDictionaryDomains graph source operands = let {
    root = G.resolve graph (G.genRoot graph source);
    reached = G.reachable graph root;
    owns n owner = if n == root then owner == source
      else owner == source || IS.member (G.resolve graph owner) reached;
    fixed n = case G.nodeAt graph n of {
      Node tag (Just owner) flag -> owns n owner && (n == root || G.equalFlag flag Rigid) && (case tag of {
        GArr _ _ -> True; GCon _ _ -> True; GTyCon _ _ -> True; GTyApp _ _ -> True; _ -> False
      });
      _ -> False
    };
    named label n = case G.tag (G.nodeAt graph n) of {
      GCon name _ -> eqString label name;
      GTyCon name _ -> eqString label name;
      GTyApp f _ -> named label f;
      _ -> False
    };
    walk n pending = case pending of {
      [] -> True;
      (:) ((,) label _) rest -> case G.tag (G.nodeAt graph n) of {
        GArr domain tail -> named label domain && walk tail rest;
        _ -> False
      }
    }
  } in walk root operands && all fixed (IS.toList reached);
  -- Read a complete, monomorphic checked arrow prefix. A first-order tail
  -- is embedded under the caller; no node of the saved scheme is mutated.
  repeatedDictionaryCall graph source operands alreadyGround = let {
    root = G.genRoot graph source;
    atom n = case G.tag (G.nodeAt graph n) of {
      GTyApp f a -> case (,) (G.tag (G.nodeAt graph f)) (G.tag (G.nodeAt graph a)) of {
        (,) (GTyCon c (KArrow Star Star)) (GCon t []) -> Just ((,) c t); _ -> Nothing
      }; _ -> Nothing
    };
    nominal n = case G.tag (G.nodeAt graph n) of { GCon c [] -> Just (SCon c []); _ -> Nothing };
    tail n = case G.tag (G.nodeAt graph n) of {
      GArr a b -> do { x <- nominal a; y <- nominal b; Just (SArrow x y) };
      _ -> nominal n
    };
    walk c t first n remaining = case remaining of {
      [] -> tail n;
      (:) _ more -> case G.tag (G.nodeAt graph n) of {
        GArr domain result -> if domain == first then walk c t first result more else do {
          (,) other actual <- atom domain;
          if eqString c other && eqString t actual then walk c t first result more else Nothing
        };
        _ -> Nothing
      }
    }
  } in case (,) operands (G.tag (G.nodeAt graph root)) of {
    (,) ((:) _ ((:) _ _)) (GArr first _) -> do {
      (,) c t <- atom first;
      result <- walk c t first root operands;
      if alreadyGround || groundDictionaryDomains graph source (map (\_ -> (,) c ()) operands)
      then Just ((,,) c t result) else Nothing
    };
    _ -> Nothing
  };
  fileApplication specialized ordinary = WithCandidates (\memo state ->
    runWithCandidates memo (case memo of {
      SeparateEnvironments -> ordinary;
      _ -> specialized
    }) state);
  -- A complete first-order producer can prove that all of these distinct
  -- binders have one closed nominal predicate. Only their type is shared.
  buildDictionaryPrefix common root = buildDictionaryPrefixIn common ((,) root M.empty);
  buildDictionaryPrefixIn common scopeRoot datatypes typeScope env gen root names body = let {
    bottom = newNode GBot (Just gen) Flexible;
    setTag tag = setNode root (Node tag (Just gen) Flexible);
    child = buildUnderIn scopeRoot datatypes typeScope gen
  } in do {
        shared <- case common of {
          Nothing -> return Nothing;
          Just ((,) constructor argument) -> do {
            known <- embed datatypes M.empty (SCon constructor [SCon argument []]);
            attach gen Rigid known;
            return (Just known)
          }
        };
        parameters <- mapM (\n -> do {
          name <- freshName n;
          domain <- case shared of { Nothing -> bottom; Just known -> return known };
          return ((,,) (LexicalRef n) name domain)
        }) names;
        result <- bottom;
        case parameters of {
          (:) ((,,) _ _ first) rest -> do {
            tail <- foldM (\to ((,,) _ _ from) -> newNode (GArr from to) (Just gen) Flexible)
              result (reverse rest);
            setTag (GArr first tail)
          };
          _ -> failGenerate "missing inferred dictionary binders"
        };
        let {
          bindings = map (\((,,) ref name domain) -> (,) ref (Mono name domain)) parameters
        };
        let { scope = bindTerms env bindings };
        value <- child (case common of { Just _ -> ClosedPrimitiveScope scope; _ -> scope }) body;
        proof <- edge (generalization value) result;
        return (FBindDictionaries (map (\((,,) _ name domain) -> (,) name domain) parameters) value proof)
      };
  buildCoreUnder :: Int -> DataEnv -> Map String Int -> BindingEnv -> Int -> Int -> Core -> Generate Form;
  buildCoreUnder root = buildCoreUnderIn ((,) root M.empty);
  buildCoreUnderIn scopeRoot datatypes typeScope env gen root core =
    let {
      child = buildUnderIn scopeRoot datatypes typeScope gen
    } in
    let {
      bottom = newNode GBot (Just gen) Flexible
    } in
    let {
      setTag = \tag -> setNode root (Node tag (Just gen) Flexible)
    } in
    let {
      recursiveVariable name shared export = do {
        equality root shared;
        -- The export does not exist until this group has finished solving.
        return (FVariable name (Just (Edge export root)))
      };
      variable ref = case lookupTerm env ref of {
          Nothing -> case ref of {
            LexicalRef x -> case P.lookupPrimitive x of {
              Just primitive -> buildCoreUnderIn scopeRoot datatypes typeScope env gen root (CPrimitive primitive);
              Nothing -> failGenerate ("unbound variable: " ++ x)
            };
            DeclRef _ hint -> failGenerate ("unbound variable: " ++ hint)
          };
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
          Just (RecursiveMono name shared export) -> recursiveVariable name shared export;
          Just (RecursiveDictionaryMono name shared export _) -> recursiveVariable name shared export
        };
      lambda ref body =
        do {
          name <- freshName (termRefName ref);
          domain <- bottom;
          result <- bottom;
          setTag (GArr domain result);
          body' <- withBoundRef ref (child (bindTerm env ref (Mono name domain)) body);
          e <- edge (generalization body') result;
          return (FLambda name domain body' e)
        };
      binding ref a b =
        do {
          name <- freshName (termRefName ref);
          a' <- child env a;
          b' <- withBoundRef ref (child (bindTerm env ref (Poly name (generalization a'))) b);
          e <- edge (generalization b') root;
          return (FBinding name a' b' e)
        };
      application a b = do {
        a' <- child env a;
        b' <- child env b;
        domain <- bottom;
        arrow <- newNode (GArr domain root) (Just gen) Flexible;
        ea <- edge (generalization a') arrow;
        eb <- edge (generalization b') domain;
        return (FApply a' b' ea eb)
      };
      -- These operands cannot flush the graph or issue a pattern projection.
      -- Bound the lookahead so nested calls take linear time to classify.
      simpleOperand depth operand = case operand of {
        CVar _ -> True; CGlobal _ _ -> True; CPrimitive _ -> True; CConstructor _ -> True;
        CInt _ -> True; CString _ -> True; CBool _ -> True; CDouble _ -> True;
        CApplyDictionaries _ _ -> True;
        CApp f x -> depth > 0 && simpleOperand (depth - 1) f && simpleOperand (depth - 1) x;
        _ -> False
      };
      -- An ordinary Poly binding already has its generalization. At a known
      -- arrow head, instantiate it once at this use's own fresh unary arrow.
      -- A later argument still instantiates the resulting expression normally.
      variableApplication ref operand ordinary = fileApplication (case lookupTerm env ref of {
        Just (Poly name source) -> if not (simpleOperand 3 operand) then ordinary else do {
          graph <- getGraph;
          case G.tag (G.nodeAt graph (G.genRoot graph source)) of {
            GArr _ _ -> do {
              domain <- bottom;
              arrow <- newNode (GArr domain root) (Just gen) Flexible;
              use <- edge source arrow;
              argument <- child env operand;
              proof <- edge (generalization argument) domain;
              return (FApplyVariable name use argument proof)
            };
            _ -> ordinary
          }
        };
        _ -> ordinary
      }) ordinary;
      verifiedCall source ref count alreadyGround = WithCandidates (\memo state -> runWithCandidates memo (case (,) memo ref of {
        (,) (BatchedEnvironments _) (DeclRef _ _) -> do {
          graph <- getGraph;
          case repeatedDictionaryCall graph source count alreadyGround of {
            Just ((,,) dictionary argument tail) -> do {
              wanted <- embed datatypes M.empty (SCon dictionary [SCon argument []]);
              attach gen Rigid wanted;
              result <- embed datatypes M.empty tail;
              attach gen Flexible result;
              equality root result;
              return (Just ((,) wanted (Edge source (G.genRoot graph source))))
            };
            _ -> return Nothing
          }
        };
        _ -> return Nothing
      }) state);
      primitiveApplication primitive types operands = let {
        ordinary expression target = do {
          argument <- child env expression;
          proof <- edge (generalization argument) target;
          return (PrimitiveUse argument proof)
        };
        result arity p = let {
          fixed n ty = case (,) n ty of {
            (,) 0 (Applied name []) -> Just name;
            (,) count (Function (Applied _ []) tail) -> if count > 0 then fixed (count - 1) tail else Nothing;
            _ -> Nothing
          }
        } in case P.primitiveSignature p of { (,) [] ty -> fixed arity ty; _ -> Nothing };
        targetResult expression = case expression of {
          CApp (CPrimitive p) _ -> result 1 p;
          CApp (CApp (CPrimitive p) _) _ -> result 2 p;
          CApp (CApp (CApp (CPrimitive p) _) _) _ -> result 3 p;
          _ -> Nothing
        };
        operand ((,) expression target) = case env of {
          ClosedPrimitiveScope _ -> case targetResult expression of {
            Just output -> do {
              graph <- getGraph;
              case G.nodeAt graph target of {
                Node (GCon required []) (Just owner) Flexible ->
                  if owner == gen && G.resolve graph target == target && eqString output required then
                    fmap ClosedPrimitiveForm (buildCoreUnderIn scopeRoot datatypes typeScope env gen target expression)
                  else ordinary expression target;
                _ -> ordinary expression target
              }
            };
            _ -> ordinary expression target
          };
          _ -> ordinary expression target
        }
      } in do {
        arguments <- mapM operand operands;
        return (FApplyPrimitive primitive types arguments)
      };
      -- A complete primitive call with closed nominal operands and result
      -- has no intermediate scheme to instantiate. Keep one proof for each
      -- operand, with types taken from the primitive's declared signature.
      convertedPrimitive primitive operand ordinary = case operand of {
        CApp (CApp converter (CVar dictionary)) (CApp (CPrimitive PTextToChars) (CString text)) ->
          case (,,) (P.primitiveSignature primitive) (caseCoreRef converter) (lookupTerm env (LexicalRef dictionary)) of {
            (,,) ((,) [] (Function (Applied input []) (Applied output []))) (Just ref) (Just (Mono _ supplied)) ->
              fileApplication (do {
                graph <- getGraph;
                case checkedStringConverterName env graph ref of {
                  Just ((,) name constructor) -> do {
                    -- The selector has precisely forall a. D a -> [Char] -> a.
                    -- This saturated primitive fixes a. The actual dictionary
                    -- retains its own ordinary instantiation at D a.
                    setTag (GCon output []);
                    let { closed = case G.nodeAt graph supplied of {
                            Node (GTyApp h a) _ Rigid -> case (,) (G.nodeAt graph h) (G.nodeAt graph a) of {
                              (,) (Node (GTyCon c (KArrow Star Star)) (Just p) Rigid)
                                  (Node (GCon t []) (Just q) Rigid) ->
                                p == supplied && q == supplied && eqString c constructor && eqString t input;
                              _ -> False
                            };
                            _ -> False
                          } };
                    expected <- if closed then return supplied else do {
                      known <- embed datatypes M.empty (SCon constructor [SCon input []]);
                      attach gen Flexible known;
                      return known
                    };
                    value <- child env (CVar dictionary);
                    use <- edge (generalization value) expected;
                    return (FPrimitiveStringConversion primitive name (XCon input []) value use text)
                  };
                  Nothing -> ordinary
                }
              }) ordinary;
            _ -> ordinary
          };
        _ -> ordinary
      };
      closedPrimitive primitive operands ordinary = fileApplication (let {
        nominal field = case field of {
          Applied _ fields -> all nominal fields;
          _ -> False
        };
        signature remaining field = case (,) remaining field of {
          (,) ((:) expression rest) (Function domain range) ->
            if nominal domain then mapOptional (\((,) arguments result) ->
              (,) ((:) ((,) expression domain) arguments) result) (signature rest range)
            else Nothing;
          (,) [] result -> if nominal result then Just ((,) [] result) else Nothing;
          _ -> Nothing
        };
        owned field = do {
          source <- liftResult (sourceField field);
          identity <- embed datatypes M.empty source;
          attach gen Flexible identity;
          return identity
        }
      } in case P.primitiveSignature primitive of {
        (,) [] fields -> case signature operands fields of {
          Just ((,) arguments result) -> let {
            normal = do {
              targets <- mapM (\((,) term field) -> do {
                identity <- owned field;
                return ((,) term identity)
              }) arguments;
              resultType <- owned result;
              equality root resultType;
              primitiveApplication primitive [] targets
            }
          } in case (,) env result of {
            (,) (ClosedPrimitiveScope _) (Applied output []) -> do {
              -- These primitives have a concrete result. Repeated operands of
              -- that same nominal type keep separate use proofs against it.
              setTag (GCon output []);
              targets <- mapM (\((,) term field) -> do {
                identity <- case field of {
                  Applied input [] -> if eqString input output then return root else owned field;
                  _ -> owned field
                };
                return ((,) term identity)
              }) arguments;
              primitiveApplication primitive [] targets
            };
            _ -> normal
          };
          Nothing -> ordinary
        };
        _ -> ordinary
      }) ordinary;
      -- Each site instantiates a shared lexical function at its own argument
      -- type. A standard argument edge retains the original dictionary's
      -- independent subsumption proof, including inside a polymorphic scope.
      stringCalls subject function convert rows fallback = do {
        operator <- freshName "stringLiteralBranch";
        let { dict = "$mlf.case.dictionary"; str = "$mlf.case.text";
              body = CApp (caseRefTerm function)
                (CApp (CApp (caseRefTerm convert) (CVar dict)) (CApp (CPrimitive PTextToChars) (CVar str)));
              worker = CLam dict (CLam str body) };
        worker' <- child env worker;
        value <- child env (caseRefTerm subject);
        integer <- newNode (GCon "Int" []) (Just gen) Flexible;
        valueProof <- edge (generalization value) integer;
        string <- newNode (GCon "String" []) (Just gen) Flexible;
        target <- newNode (GArr string root) (Just gen) Flexible;
        arms <- mapM (\((,,) key dictionary text) -> do {
          domain <- bottom;
          arrow <- newNode (GArr domain target) (Just gen) Flexible;
          proof <- edge (generalization worker') arrow;
          argument <- child env (CVar dictionary);
          operand <- edge (generalization argument) domain;
          return (StringCallArm key text argument operand proof)
        }) rows;
        remaining <- child env fallback;
        rest <- edge (generalization remaining) root;
        return (FIntStringCalls operator worker' value valueProof root arms remaining rest)
      };
      explicit refs = liftResult (mapEither FEvidence (traverseEither (evidenceBindingIn (snd scopeRoot) env) refs));
      wanted dictionary evidence =
        do {
          declaration <- liftResult (D.lookupDatatype datatypes dictionary);
          parameters <-
            mapM (\parameter -> newNode (G.bottomTag (snd parameter)) (Just (fst scopeRoot)) Flexible)
              (D.datatypeBinders declaration);
          let {
            ps = M.fromList compareString (zip (D.datatypeParameters declaration) parameters)
          };
          embedded <-
            embed datatypes ps (SCon dictionary (map STVar (D.datatypeParameters declaration)));
          attach gen Flexible embedded;
          equality root embedded;
          evidence
        }
    } in
    case core of {
      CVar x -> variable (LexicalRef x);
      CGivenScope names body -> do {
        givens <- liftResult (traverseEither (\name -> evidenceBinding env ((,) GivenEvidence (LexicalRef name))) names);
        enclosed <- buildCoreUnderIn scopeRoot datatypes typeScope env gen root body;
        return (FWithGivens givens enclosed)
      };
      CGlobal i hint -> variable (DeclRef i hint);
      CLam x body -> lambda (LexicalRef x) body;
      CBindDictionaries names body -> buildDictionaryPrefixIn Nothing scopeRoot datatypes typeScope env gen root names body;
      CDeclScope ids enclosed -> case (,) ids enclosed of {
        (,) [i] (CLam x body) -> lambda (DeclRef i x) body;
        (,) [i] (CLet x a b) -> binding (DeclRef i x) a b;
        (,) slots (CRec defs body) -> if length slots == length defs
          then withDeclarationScope (buildRecursiveUnderIn scopeRoot datatypes typeScope env gen root
            (zipWith (\i ((,,) n mode rhs) -> (,,) (DeclRef i n) mode rhs) slots defs) body)
          else failGenerate "recursive declaration slot inventory mismatch";
        _ -> failGenerate "declaration scope requires a matching top-level binder"
      };
      CApp a b -> let { ordinary = application a b } in case a of {
        -- A saturated conditional constrains both branches to its result.
        -- The operands still get individual instantiation proofs.
        CApp (CApp (CPrimitive PIfThenElse) condition) yes -> let {
          simple = do {
            boolean <- newNode (GCon "Bool" []) (Just gen) Flexible;
            primitiveApplication PIfThenElse [root] [(,) condition boolean,(,) yes root,(,) b root]
          };
          safeName ref = case ref of {
            LexicalRef n -> not (eqString n "$mlf.case.dictionary" || eqString n "$mlf.case.text");
            _ -> True
          };
          candidate = case (,) (integerTest condition) (stringArm yes) of {
            (,) (Just header@((,) subject _)) (Just shape@((,,,) function convert _ _)) ->
              if not (safeName function && safeName convert) then simple else do {
                graph <- getGraph;
                -- Reject an unsupported converter before inspecting the suffix.
                if not (caseConverter env graph convert) then simple
                else case stringCallRun env header shape b of {
                  Just ((,) arms fallback) -> stringCalls subject function convert arms fallback;
                  Nothing -> simple
                }
              };
            _ -> simple
          }
        } in fileApplication candidate ordinary;
        -- Integer patterns lower to this primitive. Constrain the operands
        -- directly to Int and record the primitive's known Bool result.
        CApp (CPrimitive PEqInt) left -> fileApplication (do {
          setTag (GCon "Bool" []);
          integer <- newNode (GCon "Int" []) (Just gen) Flexible;
          primitiveApplication PEqInt [] [(,) left integer,(,) b integer]
        }) ordinary;
        CPrimitive primitive -> convertedPrimitive primitive b (closedPrimitive primitive [b] ordinary);
        CApp (CPrimitive primitive) x -> closedPrimitive primitive [x,b] ordinary;
        CApp (CApp (CPrimitive primitive) x) y -> closedPrimitive primitive [x,y,b] ordinary;
        CVar name -> variableApplication (LexicalRef name) b ordinary;
        CGlobal i hint -> variableApplication (DeclRef i hint) b ordinary;
        _ -> ordinary
      };
      CApplyScopedDictionaries function arguments -> let {
        ordinary = buildCoreUnderIn scopeRoot datatypes typeScope env gen root
          (ordinaryScopedDictionaries (caseRefTerm function) arguments);
        -- The whole source scheme was checked by groundDictionaryDomains.
        -- Adjacent wants for the same fully ground nominal argument in the
        -- same lexical frame and immutable module scope have the same proof.
        -- Distinct application positions keep separate instantiation edges.
        atom graph n = case G.tag (G.nodeAt graph n) of {
          GTyApp h a -> case (,) (G.tag (G.nodeAt graph h)) (G.tag (G.nodeAt graph a)) of {
            (,) (GTyCon c (KArrow Star Star)) (GCon t []) -> Just ((,) c t); _ -> Nothing
          }; _ -> Nothing
        };
        values graph n remaining previous = case remaining of {
          [] -> return [];
          (:) ((,) ((,) dictionary candidates@(CandidateEnvironment owner _)) domain) tail ->
            case G.tag (G.nodeAt graph n) of {
              GArr arg rest -> do {
                let { key = atom graph arg;
                      fresh = child env (CWantedScope dictionary candidates) };
                value <- case (,) key previous of {
                  (,) (Just ((,) c t)) (Just ((,,,) pc pt po old)) ->
                    if owner /= po || not (eqString c pc && eqString t pt) then fresh else do {
                      resolved <- resolveCandidateEnvironmentIn (snd scopeRoot) env gen candidates;
                      case (,) old resolved of {
                        (,) (Typed _ (FScopedEvidence (ResolvedCandidateEnvironment previous _)))
                            (ResolvedCandidateEnvironment actual _) ->
                          if previous == actual then return old else fresh;
                        _ -> fresh
                      }
                    };
                  _ -> fresh
                };
                use <- edge (generalization value) domain;
                let { next = mapOptional (\((,) c t) -> (,,,) c t owner value) key };
                more <- values graph rest tail next;
                return ((:) ((,) value use) more)
              };
              _ -> failGenerate "checked dictionary arrow inventory mismatch"
            }
        }
      } in fileApplication (case lookupTerm env function of {
        Just (Poly name source) -> do {
          graph <- getGraph;
          if not (groundDictionaryDomains graph source arguments) then ordinary else do {
            -- Each wanted keeps its lexical environment, source order and
            -- independent instantiation edge, as in the ordinary application.
            known <- verifiedCall source function arguments True;
            (,) proof domains <- case known of {
              Just ((,) target use) -> return ((,) use (map (\_ -> target) arguments));
              Nothing -> do {
                pending <- mapM (\_ -> bottom) arguments;
                arrow <- foldM (\result domain -> newNode (GArr domain result) (Just gen) Flexible)
                  root (reverse pending);
                use <- edge source arrow;
                return ((,) use pending)
              }
            };
            operands <- WithCandidates (\memo state -> runWithCandidates memo (case memo of {
              BatchedEnvironments _ -> values graph (G.genRoot graph source) (zip arguments domains) Nothing;
              _ -> mapM (\((,) ((,) dictionary candidates) domain) -> do {
              value <- child env (CWantedScope dictionary candidates);
              use <- edge (generalization value) domain;
              return ((,) value use)
            }) (zip arguments domains)
            }) state);
            return (FApplyGroundDictionaries name proof operands)
          }
        };
        _ -> ordinary
      }) ordinary;
      CApplyDictionaries function arguments -> let {
        callee = case function of { LexicalRef name -> CVar name; DeclRef i hint -> CGlobal i hint };
        dictionary name = case lookupTerm env (LexicalRef name) of {
          Just (Mono resolved domain) -> Right ((,) resolved domain);
          _ -> Left ()
        };
        prefixType parameters = foldM (\result ((,) _ domain) -> newNode (GArr domain result) (Just gen) Flexible)
          root (reverse parameters);
        ordinary = buildCoreUnderIn scopeRoot datatypes typeScope env gen root
          (foldl CApp callee (map CVar arguments))
      } in case (,) (lookupTerm env function) (traverseEither dictionary arguments) of {
        (,) (Just (Poly name source)) (Right parameters) -> do {
          -- The callee's binding already owns its scheme. Instantiate it
          -- at the complete arrow using the caller's monomorphic domains.
          known <- verifiedCall source function parameters False;
          proof <- case known of {
            Just ((,) target use) -> do {
              mapM (\((,) _ actual) -> equality target actual) parameters;
              return use
            };
            Nothing -> do { arrow <- prefixType parameters; use <- edge source arrow;
              return use }
          };
          return (FApplyDictionaries name proof (map fst parameters))
        };
        (,) (Just (RecursiveDictionaryMono name shared export arity)) (Right parameters) ->
          if arity /= length parameters then ordinary else fileApplication (do {
            -- The compiler's complete dictionary prefix is monomorphic
            -- inside this group. Equate it once and retain the export edge
            -- only for elaborating the eventually checked recursive call.
            arrow <- prefixType parameters;
            equality shared arrow;
            return (FApplyDictionaries name (Edge export arrow) (map fst parameters))
          }) ordinary;
        _ -> ordinary
      };
      CLet x a b -> binding (LexicalRef x) a b;
      CRec defs body -> buildRecursiveUnderIn scopeRoot datatypes typeScope env gen root
        (map (\((,,) n mode rhs) -> (,,) (LexicalRef n) mode rhs) defs) body;
      CWanted dictionary candidates -> wanted dictionary
        (explicit (map (\((,) role n) -> (,) role (LexicalRef n)) candidates));
      CWantedRefs dictionary candidates -> wanted dictionary (explicit candidates);
      CWantedScope dictionary environment -> wanted dictionary
        (fmap FScopedEvidence (resolveCandidateEnvironmentIn (snd scopeRoot) env gen environment));
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
                   (,) a k ->
                     do {
                       identity <- newNode (G.bottomTag k) (Just gen) Rigid;
                       setNode identity (Node (GSkolem identity k) (Just gen) Rigid);
                       return ((,,) a identity k)
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
                           (,,) a identity _ -> (,) a identity
                         })
                      skolems))
                typeScope
          };
          target <- embed datatypes local expected;
          attach gen Rigid target;
          checked <-
            buildUnderIn scopeRoot datatypes local gen env
              (desugar (SAnn (directed expected expression) (SAnnotation [] expected)));
          e <- edge (generalization checked) target;
          return
            (FChecked
               (map
                  (\skolem ->
                     case skolem of {
                       (,,) _ identity k -> (,) (XTyVar identity) k
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
                   return ((,) x identity)
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
          setTag (GCon "Int" []);
          return (FIntegerLiteral n)
        };
      CDouble n ->
        do {
          setTag (GCon "Double" []);
          return (FDoubleLiteral n)
        };
      CBool b ->
        do {
          setTag (GCon "Bool" []);
          return (FBooleanLiteral b)
        };
      CString text ->
        do {
          setTag (GCon "String" []);
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
          -- An unsigned recursive group can flush while generating the first
          -- branch. Allocate and seal EVERY alternative before any body work.
          prepared <- mapM (prepareBranch datatypes gen domain parameters) alternatives;
          let { projections = concatMap preparedProjections prepared };
          unless (null projections) (projectCase projections);
          branches <- mapM (buildPreparedBranchUnderIn scopeRoot datatypes typeScope env gen root) prepared;
          return (FMatch a ea branches)
        }
    };
  checkedRecursive ((,,) _ mode _) = case mode of { CheckRecursive _ -> True; InferRecursive -> False };
  recursiveRefs core = let {
    hide bound = filter (\ref -> not (any (\b -> compareTermRef ref b == 0) bound));
    recursive refs defs body = hide refs (append (recursiveRefs body)
      (concatMap (\((,,) _ _ rhs) -> recursiveRefs rhs) defs))
  } in case core of {
    CVar n -> [LexicalRef n]; CGlobal i n -> [DeclRef i n];
    CLam n body -> hide [LexicalRef n] (recursiveRefs body);
    CBindDictionaries ns body -> hide (map LexicalRef ns) (recursiveRefs body);
    CApp a b -> append (recursiveRefs a) (recursiveRefs b);
    CApplyDictionaries function arguments -> (:) function (map LexicalRef arguments);
    CApplyScopedDictionaries function arguments -> (:) function
      (concatMap (\((,) _ (CandidateEnvironment _ refs)) -> map snd refs) arguments);
    CLet n a b -> append (recursiveRefs a) (hide [LexicalRef n] (recursiveRefs b));
    CCase a branches -> append (recursiveRefs a) (concatMap (\((,) pat b) ->
      hide (map LexicalRef (Desugar.patternVariables pat)) (recursiveRefs b)) branches);
    CRec defs b -> recursive (map (\((,,) n _ _) -> LexicalRef n) defs) defs b;
    CDeclScope ids enclosed -> case (,) ids enclosed of {
      (,) [i] (CLam n b) -> hide [DeclRef i n] (recursiveRefs b);
      (,) [i] (CLet n a b) -> append (recursiveRefs a) (hide [DeclRef i n] (recursiveRefs b));
      (,) slots (CRec defs b) -> recursive (zipWith (\i ((,,) n _ _) -> DeclRef i n) slots defs) defs b;
      _ -> []
    };
    CWanted _ candidates -> map (compose LexicalRef snd) candidates;
    CWantedRefs _ candidates -> map snd candidates;
    CWantedScope _ (CandidateEnvironment _ refs) -> map snd refs;
    CGivenScope names body -> append (map LexicalRef names) (recursiveRefs body);
    CChecked _ expression -> recursiveRefs (desugar expression);
    _ -> []
  };
  -- Dense lexical ranks preserve the legacy DFS order; edges compare local
  -- binders by spelling and global binders by declaration slot.
  recursiveGroups [] = [];
  recursiveGroups [member] = [[member]];
  recursiveGroups definitions = let {
    ref ((,,) name _ _) = name;
    ordered = sortBy (\a b -> compareString (termRefName (ref a)) (termRefName (ref b))) definitions;
    nodes = V.fromList ordered;
    ranks = M.fromList compareTermRef (zip (map ref ordered) (V.indices nodes));
    row ((,,) _ _ rhs) = V.fromList (map V.fromInt (IS.toAscList (IS.fromList
      (map V.toInt (mapMaybe (\r -> M.lookup compareTermRef r ranks) (recursiveRefs rhs))))));
    groups = Dependency.componentsById (Dependency.Rows (V.fromList (map row ordered))) (V.indices nodes)
  } in map (\group -> map (V.at nodes) (sortBy (\i j -> compareInt (V.toInt i) (V.toInt j)) group)) groups;
  -- The spine is only a multi-root reachability anchor. It has no fresh leaf,
  -- and none of these arrows is used by an instance/equality constraint.
  recursiveAnchor :: Int -> [] Int -> Generate Int;
  recursiveAnchor group roots =
    case roots of {
      [] -> failGenerate "empty recursive inference component";
      (:) root [] -> newNode (GArr root root) (Just group) Flexible;
      (:) first ((:) second []) -> newNode (GArr first second) (Just group) Flexible;
      (:) first rest ->
        do {
          tail <- recursiveAnchor group rest;
          newNode (GArr first tail) (Just group) Flexible
        }
    };
  buildRecursive :: DataEnv -> Map String Int -> BindingEnv -> Int -> Int ->
                    [] ((,,) TermRef RecursiveMode Core) -> Core -> Generate Form;
  buildRecursive datatypes typeScope env gen root definitions body = withBindingRoot gen
    (\scopeRoot -> buildRecursiveUnder scopeRoot datatypes typeScope env gen root definitions body);
  buildRecursiveUnder root = buildRecursiveUnderIn ((,) root M.empty);
  buildRecursiveUnderIn scopeRoot datatypes typeScope env gen root definitions body =
    do {
      let { signed = filter checkedRecursive definitions };
      declarations <- mapM (\((,,) ref mode rhs) -> do {
        (,,,) _ name source target <- declareRecursive datatypes gen ((,,) (termRefName ref) mode rhs);
        return ((,,,) ref name source target)
      }) signed;
      let {
        signedScope =
          bindTerms env (map (\((,,,) ref name source _) -> (,) ref (Poly name source)) declarations)
      };
      let {
        unsigned = filter (\definition -> not (checkedRecursive definition)) definitions
      };
      let { groups = recursiveGroups unsigned };
      inferred <- inferRecursiveGroupsIn scopeRoot datatypes typeScope gen signedScope groups;
      case inferred of {
        (,) scope inferredDefinitions ->
          do {
            checkedDefinitions <-
              mapM
                (\((,) ((,,,) n name source target) ((,,) _ _ rhs)) ->
                   do {
                     value <- buildUnderIn scopeRoot datatypes typeScope gen scope rhs;
                     proof <- edge (generalization value) target;
                     return ((,) n (RecursiveDefinition name source value proof Nothing))
                   })
                (zip declarations signed);
            let { values = M.fromList compareTermRef (append inferredDefinitions checkedDefinitions) };
            ordered <- mapM
              (\((,,) n _ _) -> case M.lookup compareTermRef n values of {
                 Nothing -> failGenerate "recursive component lost a declaration";
                 Just value -> return value
               }) definitions;
            continuation <- buildUnderIn scopeRoot datatypes typeScope gen scope body;
            proof <- edge (generalization continuation) root;
            return (FRecursive ordered continuation proof)
          }
      }
    };
  -- A batch contains only declaration SCCs with no dependency between
  -- members of distinct SCCs. Their pre-existing references must be closed
  -- declarations. Scope and type errors use the established per-SCC order.
  inferRecursiveGroups root = inferRecursiveGroupsIn ((,) root M.empty);
  inferRecursiveGroupsIn scopeRoot datatypes typeScope parent signedScope groups = let {
    build scope group = buildRecursiveGroupUnderIn scopeRoot datatypes typeScope scope parent group;
    plan scope group = planRecursiveGroupIn scopeRoot datatypes typeScope scope parent group;
    scoped group action = if any (\((,,) ref _ _) -> isDeclarationRef ref) group
      then withDeclarationScope action else action;
    single scope group = scoped group (build scope group);
    step run ((,) scope done) members = do {
      (,) next additions <- run scope members;
      return ((,) next (append done additions))
    };
    ordinary = foldM (step single) ((,) signedScope []) groups;
    -- The memo owns the parsed declaration environment. An artificial
    -- standalone Core environment keeps the original staging.
    candidate = foldM (step runBatch) ((,) signedScope []) (independentRecursiveBatches groups);
    runBatch scope batch = let {
      sequential = foldM (step single) ((,) scope []) batch;
      together = do {
        pending <- mapM (\group -> scoped group (plan scope group)) batch;
        flushGeneration;
        finishRecursiveGroupsUsing G.materializeSolvedExportBatch scope parent pending
      }
    } in case batch of {
      (:) _ ((:) _ _) -> WithCandidates (\memo state -> case state of {
        Generation graph [] [] -> if not (closedRecursiveBatchIn (snd scopeRoot) graph scope batch)
          then runWithCandidates memo sequential state
          else runWithCandidates memo together state;
        _ -> runWithCandidates memo sequential state
      });
      _ -> sequential
    }
  } in WithCandidates (\memo state -> case memo of {
    BatchedEnvironments _ -> runWithCandidates memo candidate state;
    _ -> runWithCandidates memo ordinary state
  });
  recursiveDeclarations group = IS.fromList (mapMaybe (\((,,) ref _ _) -> case ref of {
    DeclRef i _ -> Just (V.toInt i); LexicalRef _ -> Nothing
  }) group);
  recursiveMentioned group = concatMap (\((,,) _ _ rhs) -> recursiveRefs rhs) group;
  recursiveDeclarationReads group = IS.fromList (mapMaybe (\ref -> case ref of {
    DeclRef i _ -> Just (V.toInt i); LexicalRef _ -> Nothing
  }) (recursiveMentioned group));
  independentRecursiveBatches groups = let {
    batch owners reads ordered remaining = case remaining of {
      [] -> [reverse ordered];
      (:) group rest -> let {
        next = recursiveDeclarations group;
        needed = recursiveDeclarationReads group;
        separate = IS.null (IS.intersection owners needed) && IS.null (IS.intersection next reads)
      } in if separate then batch (IS.union owners next) (IS.union reads needed) ((:) group ordered) rest
        else (:) (reverse ordered) (batch next needed [group] rest)
    }
  } in case groups of {
    [] -> [];
    (:) first rest -> batch (recursiveDeclarations first) (recursiveDeclarationReads first) [first] rest
  };
  closedRecursiveBatch = closedRecursiveBatchIn M.empty;
  closedRecursiveBatchIn imported graph scope groups = let {
    declarations = foldlStrict IS.union IS.empty (map recursiveDeclarations groups);
    refs = concatMap recursiveMentioned groups;
    declared group = IS.size (recursiveDeclarations group) == length group;
    external ref = case ref of {
      DeclRef i _ -> IS.notMember (V.toInt i) declarations;
      LexicalRef _ -> True
    };
    admit sources ref = case ref of {
      LexicalRef name -> case (,) (lookupTerm scope ref) (P.lookupPrimitive name) of {
        (,) Nothing (Just _) -> Right sources;
        _ -> Left "batch requires closed declarations"
      };
      DeclRef i _ -> case lookupTerm scope ref of {
        Just (Poly _ gen) -> Right (IS.insert gen sources);
        Nothing -> if M.member compareRefSlot i imported then Right sources
          else Left "batch requires closed declarations";
        _ -> Left "batch requires closed declarations"
      }
    };
    closed gen = case G.expansionVisitCached graph gen IM.empty ((,) IS.empty IM.empty) [G.genRoot graph gen] of {
      (,) visited scopes -> all (\n -> IM.findWithDefault False n scopes) (IS.toList visited)
    }
  } in all declared groups && IS.size declarations == sum (map length groups) && (case G.foldE admit IS.empty (filter external refs) of {
    Left _ -> False;
    Right sources -> all closed (IS.toList sources)
  });
  hasLambdaPrefix :: Int -> Core -> Bool;
  hasLambdaPrefix count term = if count == 0 then True else case term of {
    CLam _ body -> hasLambdaPrefix (count - 1) body; _ -> False
  };
  -- Each admitted parameter has a use at a closed nominal type. Every call
  -- in the body is saturated, and its result is closed. Only the contiguous
  -- leading parameters used exclusively as an authenticated selector's
  -- dictionary operand can share a binder group. Their actual values and
  -- operand order remain distinct, and ordinary user lambdas keep their
  -- own generation scopes.
  closedDictionaryLambdas :: Graph -> BindingEnv -> Core -> Maybe Core;
  closedDictionaryLambdas graph env original =
    mapOptional (\((,,) names body _) -> CBindDictionaries names body)
      (closedDictionaryLambdasWithDomain graph env original);
  closedDictionaryLambdasWithDomain graph env original = let {
    nominal ty = case ty of { XCon _ xs -> all nominal xs; XApply f x -> nominal f && nominal x; _ -> False };
    field f = case f of {
      Applied c xs -> mapOptional (XCon c) (mapM field xs);
      Function a b -> do { x <- field a; y <- field b; Just (XArrow x y) };
      _ -> Nothing
    };
    checked ref = case (,) ref (lookupTerm env ref) of {
      (,) (DeclRef _ _) (Just (Poly _ source)) -> let {
        domain parent id = case G.nodeAt graph id of {
          Node (GCon c []) (Just owner) Rigid -> if owner == parent then Just (XCon c []) else Nothing;
          _ -> Nothing
        };
        read parent root id = case G.nodeAt graph id of {
          Node tag (Just owner) flag -> if owner /= parent || not (root || G.equalFlag flag Rigid) then Nothing else
            case tag of {
              GArr a b -> do { x <- domain id a; y <- read id False b; Just (XArrow x y) };
              GCon c [] -> Just (XCon c []);
              _ -> Nothing
            };
          _ -> Nothing
        }
      } in read source True (G.genRoot graph source);
      _ -> Nothing
    };
    headType expr = case expr of {
      CPrimitive primitive -> case P.primitiveSignature primitive of {
        (,) [] signature -> field signature; _ -> Nothing
      };
      _ -> case caseCoreRef expr of { Just ref -> checked ref; _ -> Nothing }
    };
    spine expression args = case expression of {
      CApp f a -> spine f ((:) a args); _ -> (,) expression args
    };
    result ty args = case (,) ty args of {
      (,) (XArrow domain tail) ((:) _ more) -> if nominal domain then result tail more else Nothing;
      (,) end [] -> if nominal end then Just end else Nothing;
      _ -> Nothing
    };
    known expr = case expr of {
      CInt _ -> Just (XCon "Int" []); CBool _ -> Just (XCon "Bool" []); CString _ -> Just (XCon "String" []);
      CApp (CApp (CApp (CPrimitive PIfThenElse) _) y) n -> case known y of { Just t -> Just t; _ -> known n };
      _ -> case spine expr [] of { (,) f args -> do { t <- headType f; result t args } }
    };
    converter ref = if not (caseConverter env graph ref) then Nothing else case lookupTerm env ref of {
      Just (Poly _ source) -> case G.tag (G.nodeAt graph (G.genRoot graph source)) of {
        GArr domain _ -> case G.tag (G.nodeAt graph domain) of {
          GTyApp constructor _ -> case G.tag (G.nodeAt graph constructor) of { GTyCon name _ -> Just name; _ -> Nothing };
          _ -> Nothing
        }; _ -> Nothing
      }; _ -> Nothing
    };
    check binders expect expr used = let {
      bind evidence n ty = if not (M.member compareString n binders) then Nothing else case M.lookup compareString n used of {
        Nothing -> Just (M.insert compareString n ((,) ty evidence) used);
        Just ((,) previous onlyEvidence) -> if not (T.alphaEq previous ty) then Nothing
          else if onlyEvidence && not evidence then Just (M.insert compareString n ((,) ty False) used)
          else Just used
      };
      args signature values previous = case (,) signature values of {
        (,) (XArrow domain tail) ((:) v rest) -> if not (nominal domain) then Nothing else do {
          now <- check binders domain v previous; args tail rest now
        };
        (,) end [] -> if nominal end && T.alphaEq expect end then Just previous else Nothing;
        _ -> Nothing
      };
      application = case spine expr [] of { (,) f values -> do { ty <- headType f; args ty values used } };
      literal typ = if T.alphaEq expect (XCon typ []) then Just used else Nothing
    } in case expr of {
      CVar n -> bind False n expect;
      CInt _ -> literal "Int"; CBool _ -> literal "Bool"; CString _ -> literal "String";
      CApp (CApp (CApp (CPrimitive PIfThenElse) condition) yes) no -> do {
        a <- check binders (XCon "Bool" []) condition used;
        b <- check binders expect yes a; check binders expect no b
      };
      CApp (CApp callee (CVar d)) (CApp (CPrimitive PTextToChars) (CString _)) -> case caseCoreRef callee of {
        Just ref -> case converter ref of { Just c -> bind True d (XCon c [expect]); Nothing -> application };
        _ -> application
      };
      CApp _ _ -> application;
      _ -> Nothing
    };
    lambdas expression names = case expression of {
      CLam name body -> lambdas body ((:) name names);
      _ -> (,) (reverse names) expression
    }
  } in case original of {
    CLam _ (CLam _ _) -> case lambdas original [] of { (,) names body -> do {
      let { binders = M.fromList compareString (map (\n -> (,) n ()) names) };
      if M.size binders /= length names then Nothing else do {
        end <- known body;
        used <- check binders end body M.empty;
        let { isEvidence n = case M.lookup compareString n used of {
                Just ((,) _ True) -> True; _ -> False
              } };
        if M.size used /= length names then Nothing else case span isEvidence names of {
          (,) leading@((:) first ((:) _ _)) trailing -> let {
            common = case M.lookup compareString first used of {
              Just ((,) (XCon constructor [XCon argument []]) True) ->
                if all (\n -> case M.lookup compareString n used of {
                  Just ((,) (XCon other [XCon actual []]) True) ->
                    eqString constructor other && eqString argument actual;
                  _ -> False
                }) leading then Just ((,) constructor argument) else Nothing;
              _ -> Nothing
            }
          } in Just ((,,) leading (foldr CLam body trailing) common);
          _ -> Nothing
        }
      }
    } };
    _ -> Nothing
  };
  buildRecursiveGroup :: DataEnv -> Map String Int -> BindingEnv -> Int ->
                         [] ((,,) TermRef RecursiveMode Core) ->
                         Generate ((,) BindingEnv ([] ((,) TermRef RecursiveDefinition)));
  buildRecursiveGroup datatypes typeScope env parent definitions = withBindingRoot parent
    (\scopeRoot -> buildRecursiveGroupUnder scopeRoot datatypes typeScope env parent definitions);
  buildRecursiveGroupUnder root = buildRecursiveGroupUnderIn ((,) root M.empty);
  buildRecursiveGroupUnderIn scopeRoot datatypes typeScope env parent definitions = do {
    pending <- planRecursiveGroupIn scopeRoot datatypes typeScope env parent definitions;
    flushGeneration;
    finishRecursiveGroupsUsing G.materializeSolvedExportBatch env parent [pending]
  };
  data PendingRecursive = PendingRecursive Int ([] ((,,,) TermRef XName Int Int)) ([] ((,) Typed Edge));
  planRecursiveGroup root = planRecursiveGroupIn ((,) root M.empty);
  planRecursiveGroupIn scopeRoot datatypes typeScope env parent definitions =
    do {
      group <- newNode (GGen (-1)) (Just parent) Flexible;
      declarations <- mapM
        (\((,,) n _ _) -> do {
           name <- freshName (termRefName n);
           shared <- newNode GBot (Just group) Flexible;
           export <- reserveIdentity;
           return ((,,,) n name shared export)
         }) definitions;
      anchor <- recursiveAnchor group (map (\((,,,) _ _ shared _) -> shared) declarations);
      setNode group (Node (GGen anchor) (Just parent) Flexible);
      let {
        assumption ((,,,) n name shared export) ((,,) _ _ rhs) =
          (,) n (case rhs of {
            CBindDictionaries slots _ -> if null slots then RecursiveMono name shared export
              else RecursiveDictionaryMono name shared export (length slots);
            _ -> RecursiveMono name shared export
          });
        scope = bindTerms env (zipWith assumption declarations definitions)
      };
      bodies <- mapM
        (\((,) ((,,,) declaration _ shared _) ((,,) _ _ rhs)) -> do {
           let { buildBody = buildUnderIn scopeRoot datatypes typeScope group scope; ordinary = buildBody rhs };
           value <- case declaration of {
             DeclRef _ _ -> if not (hasLambdaPrefix 8 rhs) then ordinary else fileApplication (do {
               graph <- getGraph;
               case closedDictionaryLambdasWithDomain graph scope rhs of {
                 Nothing -> ordinary;
                 Just ((,,) names body common) -> let { compact = CBindDictionaries names body } in case common of {
                   Nothing -> buildBody compact;
                   Just _ -> WithCandidates (\memo state -> runWithCandidates memo (case memo of {
                     BatchedEnvironments _ -> generalize (Just group) (\gen root ->
                       buildDictionaryPrefixIn common scopeRoot datatypes typeScope scope gen root names body);
                     _ -> buildBody compact
                   }) state)
                 }
               }
             }) ordinary;
             _ -> ordinary
           };
           proof <- edge (generalization value) shared;
           return ((,) value proof)
         }) (zip declarations definitions);
      return (PendingRecursive group declarations bodies)
    };
  finishRecursiveGroups = finishRecursiveGroupsUsing G.materializeCheckedExportBatch;
  finishRecursiveGroupsUsing materialize env parent pending = do {
    graph <- getGraph;
    let {
      items (PendingRecursive group declarations bodies) = map (\((,) declaration body) -> (,,) group declaration body)
        (zip declarations bodies);
      members = concatMap items pending;
      request ((,,) group ((,,,) _ _ shared export) _) = (,,) group shared export;
      freeze ((,,) group ((,,,) n name _ export) ((,) value proof)) ((,) _ copies) =
        (,) n (RecursiveDefinition name export value proof (Just (RecursiveClosure group copies)));
      exportedScope = bindTerms env (map (\((,,) _ ((,,,) n name _ export) _) -> (,) n (Poly name export)) members)
    };
    (,) completed next <- liftResult (materialize parent (map request members) graph);
    setGraph next;
    return ((,) exportedScope (zipWith freeze members completed))
  };
  declareRecursive :: DataEnv ->
                      Int -> (,,) String RecursiveMode Core -> Generate ((,,,) String XName Int Int);
  declareRecursive datatypes gen definition =
    case definition of {
      (,,) x (CheckRecursive (SAnnotation [] ty)) _ ->
        do {
          name <- freshName x;
          declarationGen <- newNode (GGen (-1)) (Just gen) Flexible;
          root <- embed datatypes M.empty ty;
          attach declarationGen Flexible root;
          setNode declarationGen (Node (GGen root) (Just gen) Flexible);
          return ((,,,) x name declarationGen root)
        };
      (,,) _ InferRecursive _ -> failGenerate "unsigned recursive inference is not implemented";
      _ -> failGenerate "recursive definitions require a closed signature"
    };
  outermost :: Graph -> Int -> Int;
  outermost graph identity =
    case G.binder (G.nodeAt graph identity) of {
      Nothing -> identity;
      Just parent -> outermost graph parent
    };
  leadingVariables :: SType -> (,) ([] ((,) String Kind)) SType;
  leadingVariables signature =
    case signature of {
      SForall Flexible name SBottom body ->
        let {
          result = leadingVariables body
        } in
        (,) ((:) ((,) name Star) (fst result)) (snd result);
      SForall Flexible name (SBottomKind kind) body ->
        let {
          result = leadingVariables body
        } in
        (,) ((:) ((,) name kind) (fst result)) (snd result);
      _ -> (,) [] signature
    };
  directed :: SType -> SExpr -> SExpr;
  directed (SArrow domain result) (SLam x annotation body) =
    SLam x (Just (fromMaybe (SAnnotation [] domain) annotation)) (directed result body);
  -- Ordinary let infers/generalizes its RHS as before. Only its continuation
  -- is checked under the same expected type, including scoped skolems.
  directed expected (SLet name rhs body) = SLet name rhs (directed expected body);
  directed expected (SGivenScope names expression) = SGivenScope names (directed expected expression);
  directed expected (SDeclScope ids expression) = SDeclScope ids (directed expected expression);
  directed _ expression = expression;
  freshOptional :: Maybe String -> Generate (Maybe XName);
  freshOptional Nothing = return Nothing;
  freshOptional (Just hint) =
    do {
      name <- freshName hint;
      return (Just name)
    };
  patternBindings :: [] (Maybe String) ->
                     [] (Maybe XName) -> [] ((,) Int (Maybe XType)) -> [] ((,) String Binding);
  patternBindings ((:) (Just original) originals) ((:) (Just resolved) names) ((:) ((,) identity declared) identities) =
    (:) ((,) original (case declared of {
      Nothing -> Mono resolved identity;
      Just ty -> DeclaredPoly resolved identity ty
    })) (patternBindings originals names identities);
  patternBindings ((:) _ originals) ((:) _ names) ((:) _ identities) =
    patternBindings originals names identities;
  patternBindings _ _ _ = [];
  data PreparedBranch = PreparedBranch XPattern ([] ((,) String Binding)) Core ([] ((,) Int Int));
  preparedProjections (PreparedBranch _ _ _ fields) = fields;
  prepareBranch :: DataEnv -> Int -> Int -> Map String Int ->
                   (,) SPattern Core -> Generate PreparedBranch;
  prepareBranch datatypes gen domain parameters alternative =
    case alternative of {
      (,) pattern body ->
        case pattern of {
          SConstructorPattern constructor names -> do {
            declaration <- liftResult (D.lookupConstructor datatypes constructor);
            let { declared = D.constructorFields (snd declaration) };
            fields <- mapM (patternField datatypes parameters gen) declared;
            let { used = catMaybes names };
            unless (length used == length (nubBy eqString used))
              (failGenerate "duplicate pattern variable");
            names' <- mapM freshOptional names;
            projections <- liftResult (mapM patternProjection (zip declared fields));
            return (PreparedBranch (XConstructorPattern constructor names')
              (patternBindings names names' fields) body (catMaybes projections))
          };
          SDefaultPattern name -> do {
            resolvedName <- freshOptional name;
            let {
              bindings = case name of {
                Nothing -> [];
                Just original -> case resolvedName of {
                  Nothing -> [];
                  Just resolved -> (:) ((,) original (Mono resolved domain)) []
                }
              }
            };
            return (PreparedBranch (XDefaultPattern resolvedName) bindings body [])
          };
          _ -> failGenerate "surface pattern escaped lowering"
        }
    };
  patternProjection :: (,) Field ((,) Int (Maybe XType)) ->
                       Either String (Maybe ((,) Int Int));
  patternProjection ((,) field prepared) =
    case field of {
      Parameter _ -> case snd prepared of {
        Just (XVar (XTyVar original)) -> Right (Just ((,) original (fst prepared)));
        _ -> Left "pattern parameter lost its exact projection identity"
      };
      _ -> Right Nothing
    };
  buildPreparedBranch :: DataEnv -> Map String Int -> BindingEnv ->
                         Int -> Int -> PreparedBranch -> Generate Branch;
  buildPreparedBranch datatypes typeScope env gen root prepared = withBindingRoot gen
    (\scopeRoot -> buildPreparedBranchUnder scopeRoot datatypes typeScope env gen root prepared);
  buildPreparedBranchUnder root = buildPreparedBranchUnderIn ((,) root M.empty);
  buildPreparedBranchUnderIn scopeRoot datatypes typeScope env gen root prepared =
    case prepared of {
      PreparedBranch pattern bindings body _ -> do {
        body' <- buildUnderIn scopeRoot datatypes typeScope gen
          (bindTerms env (map (\((,) n binding) -> (,) (LexicalRef n) binding) bindings)) body;
        e <- edge (generalization body') root;
        return (Branch pattern body' e)
      }
    };
  -- Declared foralls keep their existing evidence path. Bare parameters use
  -- external-root proxies until the case's one-shot barrier either copies a
  -- known polymorphic interface or permanently leaves the field shared.
  patternField :: DataEnv -> Map String Int -> Int -> Field -> Generate ((,) Int (Maybe XType));
  patternField datatypes parameters parent field =
    case field of {
      Parameter name -> do {
        embedded <- embedDeclaredField datatypes parameters field;
        gen <- newNode (GGen (fst embedded)) (Just parent) Flexible;
        return ((,) gen (Just (snd embedded)))
      };
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
        return ((,) gen (Just (snd embedded)))
      };
      _ -> do {
        ty <- liftResult (sourceField field);
        identity <- embed datatypes parameters ty;
        attach parent Rigid identity;
        return ((,) identity Nothing)
      }
    };
  -- Keep the exact declaration alongside its graph view. Its bound IDs are
  -- distinct from free datatype-parameter IDs, including under shadowing;
  -- unused binders survive in the evidence type even when graph pruning drops
  -- them. This metadata never introduces an inferred/generalized field type.
  embedDeclaredField :: DataEnv -> Map String Int -> Field -> Generate ((,) Int XType);
  embedDeclaredField datatypes scope field =
    case field of {
      Parameter name ->
        case M.lookup compareString name scope of {
          Nothing -> failGenerate ("unbound data type parameter: " ++ name);
          Just identity -> return ((,) identity (XVar (XTyVar identity)))
        };
      Function a b -> do {
        root <- newNode GBot Nothing Rigid;
        x <- embedDeclaredField datatypes scope a;
        y <- embedDeclaredField datatypes scope b;
        attachUnscoped root scope (fst x);
        attachUnscoped root scope (fst y);
        setNode root (Node (GArr (fst x) (fst y)) Nothing Rigid);
        return ((,) root (XArrow (snd x) (snd y)))
      };
      Applied constructor arguments -> do {
        let { kind = D.constructorKind datatypes constructor (length arguments) };
        head <- newNode
          (if Kind.eqKind kind Star then GCon constructor [] else GTyCon constructor kind)
          Nothing Rigid;
        foldM (\f argument -> do {
          a <- embedDeclaredField datatypes scope argument;
          root <- embedApplication scope (fst f) (fst a);
          return ((,) root (T.apply (snd f) (snd a)))
        }) ((,) head (XCon constructor [])) arguments
      };
      Application f a -> do {
        x <- embedDeclaredField datatypes scope f;
        y <- embedDeclaredField datatypes scope a;
        root <- embedApplication scope (fst x) (fst y);
        return ((,) root (T.apply (snd x) (snd y)))
      };
      Quantified name kind body -> do {
        bound <- newNode (G.bottomTag kind) Nothing Flexible;
        result <- embedDeclaredField datatypes (M.insert compareString name bound scope) body;
        graph <- getGraph;
        when ((bound /= fst result) && IS.member bound (G.reachable graph (fst result)))
          (setNode bound (Node (G.tag (G.nodeAt graph bound)) (Just (fst result)) Flexible));
        return ((,) (fst result) (XForall (XTyVar bound) (T.bottomKind kind) (snd result)))
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
  patternShape :: SPattern -> (,) (Maybe String) Int;
  patternShape (SConstructorPattern constructor names) = (,) (Just constructor) (length names);
  patternShape (SDefaultPattern _) = (,) Nothing 0;
  patternShape _ = panic "surface pattern escaped lowering";
  validateAnnotations datatypes expression = validateIn datatypes M.empty expression;
  validateAnnotation datatypes scope annotation =
    case annotation of {
      SAnnotation variables ty ->
        K.annotationType datatypes
          (M.union compareString
             (M.fromList compareString (map (\name -> (,) name Star) variables))
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
  validateIn :: DataEnv -> Map String Kind -> SExpr -> Either String ();
  validateIn datatypes scope expression =
    case expression of {
      SVar _ -> Right ();
      SGlobal _ _ -> Right ();
      SApplyDictionaries _ _ -> Right ();
      SBindDictionaries names body -> do {
        ensure (not (null names)) "missing inferred dictionary binders";
        validateIn datatypes scope body
      };
      SDeclScope ids b -> do {
        let { slots = map V.toInt ids };
        ensure (all (\i -> i >= 0) slots && IS.size (IS.fromList slots) == length slots)
          "invalid declaration binder slots";
        validateIn datatypes scope b
      };
      SWantedScope _ _ -> Right ();
      SGivenScope _ body -> validateIn datatypes scope body;
      SWantedRefs dictionary candidates ->
        validateIn datatypes scope (SWanted dictionary (map (\((,) role ref) -> (,) role (termRefName ref)) candidates));
      SConstructor _ -> Right ();
      SLam _ annotation body ->
        do {
          case annotation of {
            Nothing -> Right ();
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
          SAnnotation [] ty -> validateIn datatypes scope (SChecked ty a);
          _ -> validateIn datatypes scope (SAnn a annotation)
        };
      SIntLit _ -> Right ();
      SDoubleLit n ->
        unless (andInt (doubleToBits n) 9218868437227405312 /= 9218868437227405312)
          (Left "non-finite Double literal");
      SBoolLit _ -> Right ();
      SStringLit _ -> Right ();
      SPrimitive _ -> Right ();
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
      SSourceDefinition _ -> Left "source definition provenance escaped class lowering";
      SCallSite _ _ _ -> Left "source call site escaped class lowering";
      SSharedBind _ _ _ _ _ -> Left "shared pattern bind escaped surface lowering";
      SLetRec definitions body ->
        do {
          mapM_
            (\definition ->
               case definition of {
                 (,,) _ annotation value ->
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
      SWanted _ _ -> Right ();
      SChecked ty body ->
        do {
          K.annotationType datatypes scope ty;
          local <- validateBinders datatypes scope ty;
          validateIn datatypes local body
        }
    };
  validateRecursiveMode :: DataEnv -> Map String Kind -> RecursiveMode -> Either String ();
  validateRecursiveMode datatypes scope mode =
    case mode of {
      InferRecursive -> Right ();
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
        Just _ -> return ()
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
              (if Kind.eqKind kind Star then GCon constructor [] else GTyCon constructor kind)
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
      solved <- Solver.solveGenerated (initialGraph constraints) (equalities constraints) (solveSteps constraints);
      Solver.finishNormalized solved
    };
  eraseEvidence evidence typed = case IM.lookup (generalization typed) evidence of {
    Nothing -> XEEvidenceHole (generalization typed); Just proof -> X.erase proof
  };
  eraseSource typed = eraseSourceWith IM.empty typed;
  eraseSourceWith :: IntMap XTerm -> Typed -> XErased;
  eraseSourceWith evidence typed = let {
    erase current = case current of {
      FWithGivens _ body -> erase body;
      FVariable name _ -> XEVar name;
      FDeclaredVariable name _ _ -> XEVar name;
      FLambda name _ body _ -> XEAbs name (eraseSourceWith evidence body);
      FBindDictionaries args body _ -> foldr (\((,) n _) b -> XEAbs n b) (eraseSourceWith evidence body) args;
      FApply a b _ _ -> XEApp (eraseSourceWith evidence a) (eraseSourceWith evidence b);
      FApplyVariable f _ argument _ -> XEApp (XEVar f) (eraseSourceWith evidence argument);
      FApplyDictionaries f _ arguments -> foldl (\value name -> XEApp value (XEVar name))
        (XEVar f) arguments;
      FApplyGroundDictionaries f _ arguments -> foldl (\function ((,) argument _) ->
        XEApp function (eraseSourceWith evidence argument)) (XEVar f) arguments;
      FApplyPrimitive primitive _ arguments -> foldl (\function operand -> XEApp function (case operand of {
        PrimitiveUse argument _ -> eraseSourceWith evidence argument;
        ClosedPrimitiveForm current -> erase current
      })) (XEPrimitive primitive) arguments;
      FPrimitiveStringConversion primitive selector _ dictionary _ text ->
        XEApp (XEPrimitive primitive) (XEApp (XEApp (XEVar selector) (eraseSourceWith evidence dictionary))
          (XEApp (XEPrimitive PTextToChars) (XEString text)));
      FIntStringCalls operator worker value _ _ arms fallback _ -> let {
        use = eraseSourceWith evidence value;
        arm (StringCallArm key text argument _ _) rest = XEApp (XEApp (XEApp (XEPrimitive PIfThenElse)
          (XEApp (XEApp (XEPrimitive PEqInt) use) (XEInt key)))
          (XEApp (XEApp (XEVar operator) (eraseSourceWith evidence argument)) (XEString text))) rest
      } in XELet operator (eraseSourceWith evidence worker) (foldr arm (eraseSourceWith evidence fallback) arms);
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
                  RecursiveDefinition name _ rhs _ _ -> (,) name (eraseSourceWith evidence rhs)
                })
             definitions)
          (eraseSourceWith evidence body);
      FEvidence _ -> eraseEvidence evidence typed;
      FScopedEvidence _ -> eraseEvidence evidence typed;
      FChecked _ body _ -> eraseSourceWith evidence body
    }
  } in erase (rawForm typed)
}
