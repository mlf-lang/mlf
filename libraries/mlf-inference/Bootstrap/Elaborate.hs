-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Elaborate where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Evidence as Evidence;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Pretty as Pretty;
  isFlexible :: Flag -> Bool;
  isFlexible Flexible = True;
  isFlexible Rigid = False;
  sameParent parent maybe =
    case maybe of {
      Nothing -> False;
      Just identity -> (parent == identity)
    };
  -- A finished graph is immutable. Share its translated types and ordered
  -- bounds across resolution, elaboration and final checking. Map values are
  -- lazy, so preparing the table does not demand unused types or bounds.
  data TypeContext = TypeContext Graph (IntMap XType) (IntMap (List (Pair XTyVar XType))) IntSet;
  contextGraph :: TypeContext -> Graph;
  contextGraph (TypeContext graph types bounds parents) = graph;
  prepareTypes :: Graph -> TypeContext;
  prepareTypes graph =
    let {
      context :: TypeContext;
      context =
        TypeContext graph (IM.mapWithKey (\n ignored -> typeAtRaw context n) (G.nodes graph))
          (IM.mapWithKey (\n ignored -> boundsAtRaw context n) (G.nodes graph))
          (IS.fromList
             (concatMap (\v -> if isFlexible (G.flag v) then maybeToList (G.binder v) else Nil)
                (IM.elems (G.nodes graph))))
    } in
    context;
  typeAtIn :: TypeContext -> Int -> XType;
  typeAtIn (TypeContext graph types bounds parents) identity =
    IM.get (G.resolve graph identity) types;
  boundsAtIn :: TypeContext -> Int -> List (Pair XTyVar XType);
  boundsAtIn (TypeContext graph types bounds parents) identity =
    IM.get (G.resolve graph identity) bounds;
  -- Flexible graph nodes become target binders; rigid bounds remain structure.
  typeAtRaw :: TypeContext -> Int -> XType;
  typeAtRaw context identity =
    let {
      graph = contextGraph context
    } in
    let {
      resolved = G.resolve graph identity
    } in
    let {
      structure =
        case G.tag (G.nodeAt graph resolved) of {
          GBot -> XBot;
          GBotK kind -> T.bottomKind kind;
          GArr a b -> XArrow (childTypeIn context a) (childTypeIn context b);
          GCon constructor parameters -> XCon constructor (map (childTypeIn context) parameters);
          GTyCon constructor _ -> XCon constructor Nil;
          GSkolem skolem _ -> XVar (XTyVar skolem);
          GTyApp f a -> T.apply (childTypeIn context f) (childTypeIn context a);
          GGen _ -> panic "typeAt: a gen node is not a type"
        }
    } in
    foldr (\bound body -> XForall (fst bound) (snd bound) body) structure
      (boundsAtIn context resolved);
  childTypeIn :: TypeContext -> Int -> XType;
  childTypeIn context identity =
    let {
      graph = contextGraph context
    } in
    if isFlexible (G.flag (G.nodeAt graph identity))
    then XVar (XTyVar (G.resolve graph identity))
    else typeAtIn context identity;
  referenceIn :: TypeContext -> Int -> XType;
  referenceIn context identity =
    let {
      graph = contextGraph context
    } in
    let {
      node = G.nodeAt graph identity
    } in
    let {
      generalized =
        case G.binder node of {
          Nothing -> False;
          Just parent ->
            case G.tag (G.nodeAt graph parent) of {
              GGen _ -> True;
              _ -> False
            }
        }
    } in
    if (isFlexible (G.flag node) && generalized)
    then XVar (XTyVar (G.resolve graph identity))
    else typeAtIn context identity;
  boundsAtRaw :: TypeContext -> Int -> List (Pair XTyVar XType);
  boundsAtRaw context parent =
    case context of {
      TypeContext graph types bounds parents ->
        if IS.notMember parent parents
        then Nil
        else let {
               root =
                 case G.tag (G.nodeAt graph parent) of {
                   GGen identity -> identity;
                   _ -> parent
                 }
             } in
             map (\identity -> Pair (XTyVar identity) (typeAtIn context identity))
               (filter
                  (\identity ->
                     (sameParent (G.resolve graph parent) (G.binder (G.nodeAt graph identity)) &&
                      isFlexible (G.flag (G.nodeAt graph identity))))
                  (G.orderedBelow graph root))
    };
  schemeTypeIn context gen =
    let {
      graph = contextGraph context
    } in
    foldr (\bound body -> XForall (fst bound) (snd bound) body)
      (referenceIn context (G.genRoot graph gen))
      (boundsAtIn context gen);
  nodeConstructorKind node =
    case G.tag node of {
      GTyCon name kind -> Just (Pair name kind);
      _ -> Nothing
    };
  graphDatatypes graph =
    D.withKinds (catMaybes (map nodeConstructorKind (IM.elems (G.nodes graph))));
  extendEnvironment outer bounds =
    foldl (\env bound -> M.insert T.compareTyVar (fst bound) (snd bound) env) outer bounds;
  isRefl :: XComputation -> Bool;
  isRefl XRefl = True;
  isRefl _ = False;
  proveInstance targetGraph image env source target =
    proveInstanceWithIn (graphDatatypes targetGraph) (prepareTypes targetGraph) image env source
      target;
  proveInstanceWithIn :: DataEnv ->
                         TypeContext ->
                         (Int -> Int) ->
                         Map XTyVar XType -> XType -> XType -> Either String XComputation;
  proveInstanceWithIn datatypes context image env source target =
    proveInstanceUsing datatypes (graphReplacementIn context image) env source target;
  graphReplacementIn context image gamma variable =
    do {
      let {
        targetGraph = contextGraph context
      };
      let {
        identity = image (T.tyVarId variable)
      };
      unless (IM.member identity (G.nodes targetGraph))
        (Left ("instance lost node provenance: " ++ showInt (T.tyVarId variable)));
      Right
        (if M.member T.compareTyVar (XTyVar identity) gamma
         then XVar (XTyVar identity)
         else typeAtIn context identity)
    };
  -- The declaration retains its own forall identities, including unused
  -- binders. Only free references denote shared datatype-parameter graph
  -- nodes; substituting by source spelling would lose shadowing and kinds.
  declaredTypeIn :: TypeContext -> IntSet -> XType -> XType;
  declaredTypeIn context local ty =
    case ty of {
      XVar variable ->
        if IS.member (T.tyVarId variable) local then ty
        else referenceIn context (T.tyVarId variable);
      XArrow a b -> XArrow (declaredTypeIn context local a) (declaredTypeIn context local b);
      XCon name arguments -> XCon name (map (declaredTypeIn context local) arguments);
      XApply f a -> T.apply (declaredTypeIn context local f) (declaredTypeIn context local a);
      XForall variable bound body ->
        XForall variable (declaredTypeIn context local bound)
          (declaredTypeIn context (IS.insert (T.tyVarId variable) local) body);
      _ -> ty
    };
  declaredReplacementIn context kinds gamma variable =
    let { graph = contextGraph context } in
    let { identity = G.resolve graph (T.tyVarId variable) } in
    if IM.member identity (G.nodes graph)
    then graphReplacementIn context (\n -> n) gamma variable
    else case M.lookup T.compareTyVar variable kinds of {
      Just kind -> Right (T.bottomKind kind);
      Nothing -> Left ("declared field lost type provenance: " ++ showInt (T.tyVarId variable))
    };
  -- Vacuous leading binders are removed explicitly, before the generic proof
  -- considers target abstractions. In particular forall b.a -> a must retain
  -- the shared external a, not attempt to instantiate it to its bound.
  dropUnusedLeading :: XType -> XComputation;
  dropUnusedLeading ty =
    case ty of {
      XForall variable _ body ->
        let { inner = dropUnusedLeading body } in
        if Set.member T.compareTyVar variable (T.freeVars body)
        then if isRefl inner then XRefl else XOuter variable inner
        else X.compose XElim inner;
      _ -> XRefl
    };
  declaredFieldComputationIn :: TypeContext -> DataEnv -> Map XTyVar XType ->
                                XType -> Int -> Either String XComputation;
  declaredFieldComputationIn context datatypes env declaration source = do {
    let { actual = declaredTypeIn context IS.empty declaration };
    let { prefix = dropUnusedLeading actual };
    normalized <- Check.checkComputationIn datatypes env prefix actual;
    let { kinds = M.fromList T.compareTyVar (fst (Evidence.quantifiers actual)) };
    proof <- proveInstanceUsing datatypes (declaredReplacementIn context kinds) env
      normalized (schemeTypeIn context source);
    let { combined = X.compose prefix proof };
    checked <- Check.checkComputationIn datatypes env combined actual;
    unless (T.alphaEq checked (schemeTypeIn context source))
      (Left "declared field evidence has the wrong target");
    Right combined
  };
  -- Explicit signatures can retain unused binders or a different forall order.
  -- All adaptations use the same independently checked atomic computations.
  proveInstanceUsing :: DataEnv ->
                        (Map XTyVar XType -> XTyVar -> Either String XType) ->
                        Map XTyVar XType -> XType -> XType -> Either String XComputation;
  proveInstanceUsing datatypes replacement env source target =
    do {
      computation <- prove datatypes replacement env source target;
      actual <- Check.checkComputationIn datatypes env computation source;
      unless (T.alphaEq actual target) (Left "instance evidence has the wrong target");
      Right computation
    };
  prove :: DataEnv ->
           (Map XTyVar XType -> XTyVar -> Either String XType) ->
           Map XTyVar XType -> XType -> XType -> Either String XComputation;
  prove datatypes replacement gamma source target =
    if T.alphaEq source target
    then Right XRefl
    else case source of {
           XBot -> Right (XBottom target);
           XBotKind _ -> Right (XBottom target);
           _ ->
             case target of {
               XVar variable ->
                 case M.lookup T.compareTyVar variable gamma of {
                   Nothing -> Left ("missing target abstraction: " ++ showInt (T.tyVarId variable));
                   Just bound ->
                     do {
                       computation <- prove datatypes replacement gamma source bound;
                       Right (X.compose computation (XHyp variable))
                     }
                 };
               XForall variable bound body ->
                 do {
                   computation <-
                     prove datatypes replacement (M.insert T.compareTyVar variable bound gamma)
                       source
                       body;
                   kind <- T.kindOf datatypes gamma bound;
                   let {
                     intro =
                       if K.eqKind kind Star then XIntro variable else XIntroKind variable kind
                   };
                   let {
                     strengthening =
                       if T.alphaEq bound (T.bottomKind kind) then XRefl else XInner (XBottom bound)
                   };
                   Right (X.compose (X.compose intro strengthening) (XOuter variable computation))
                 };
               _ -> eliminate datatypes replacement gamma source target
             }
         };
  eliminate :: DataEnv ->
               (Map XTyVar XType -> XTyVar -> Either String XType) ->
               Map XTyVar XType -> XType -> XType -> Either String XComputation;
  eliminate datatypes replacement gamma source target =
    case source of {
      XForall variable bound body ->
        do {
          argument <- replacement gamma variable;
          first <- prove datatypes replacement gamma bound argument;
          rest <- prove datatypes replacement gamma (T.substitute variable argument body) target;
          Right (X.compose (X.compose (if isRefl first then XRefl else XInner first) XElim) rest)
        };
      _ ->
        Left
          ("no permitted instance from " ++
           (Pretty.prettyType source ++ (" to " ++ Pretty.prettyType target)))
    };
  structuralPairs :: GTag -> GTag -> List (Pair Int Int);
  structuralPairs (GArr a b) (GArr c d) = Cons (Pair a c) (Cons (Pair b d) Nil);
  structuralPairs (GTyApp a b) (GTyApp c d) = Cons (Pair a c) (Cons (Pair b d) Nil);
  structuralPairs (GCon c xs) (GCon d ys) =
    if (eqString c d && (length xs == length ys)) then zip xs ys else Nil;
  structuralPairs _ _ = Nil;
  correspondence :: Graph -> IntSet -> IntMap Int -> List (Pair Int Int) -> IntMap Int;
  correspondence _ _ images Nil = images;
  correspondence graph seen images (Cons (Pair original target) rest) =
    let {
      a = G.resolve graph original
    } in
    let {
      b = G.resolve graph target
    } in
    if IS.member a seen
    then correspondence graph seen images rest
    else let {
           pairs = structuralPairs (G.tag (G.nodeAt graph a)) (G.tag (G.nodeAt graph b))
         } in
         correspondence graph (IS.insert a seen) (IM.insert a b images) (append pairs rest);
  -- Every fast correspondence is checked. Failed candidates use the final
  -- presolution's frontier-first expansion to retain graph provenance.
  edgeComputationIn :: TypeContext ->
                       DataEnv -> Solver -> Map XTyVar XType -> Edge -> Either String XComputation;
  edgeComputationIn context datatypes solver env edge =
    let {
      graph = Solver.solverGraph solver
    } in
    let {
      target = G.resolve graph (C.toNode edge)
    } in
    let {
      source = schemeTypeIn context (C.fromGen edge)
    } in
    let {
      targetType = referenceIn context target
    } in
    if T.alphaEq source targetType
    then Right XRefl
    else let {
           positions =
             correspondence graph IS.empty IM.empty
               (Cons (Pair (G.genRoot graph (C.fromGen edge)) target) Nil)
         } in
         let {
           directImage =
             \identity -> IM.findWithDefault identity (G.resolve graph identity) positions
         } in
         case proveInstanceWithIn datatypes context directImage env source targetType of {
           Right proof -> Right proof;
           Left _ ->
             do {
               witness <- Solver.witness (C.fromGen edge) target solver;
               let {
                 copies = fst witness
               };
               let {
                 solved = Solver.solverGraph (snd witness)
               };
               let {
                 image = \identity -> G.resolve solved (IM.findWithDefault identity identity copies)
               };
               proveInstanceWithIn datatypes context image env source targetType
             }
         };
  candidateTypeIn context candidate =
    let {
      graph = contextGraph context
    } in
    case candidate of {
      EvidenceBinding role name identity polymorphic ->
        Triple role name
          (if polymorphic then schemeTypeIn context identity else referenceIn context identity);
      DeclaredEvidenceBinding role name declaration ->
        Triple role name (declaredTypeIn context IS.empty declaration)
    };
  mergeEvidence results = foldl IM.union IM.empty results;
  resolveEvidence graph typed = resolveEvidenceIn (prepareTypes graph) typed;
  resolveEvidenceIn context typed =
    resolveWithinIn context (graphDatatypes (contextGraph context)) M.empty typed;
  resolveWithinIn :: TypeContext ->
                     DataEnv -> Map XTyVar XType -> Typed -> Either String (IntMap XTerm);
  resolveWithinIn context datatypes outer typed =
    let {
      graph = contextGraph context
    } in
    let {
      gen = C.generalization typed
    } in
    let {
      env = extendEnvironment outer (boundsAtIn context gen)
    } in
    let {
      child = resolveWithinIn context datatypes env
    } in
    case C.form typed of {
      FEvidence candidates ->
        do {
          term <-
            Evidence.resolveDictionary datatypes env (map (candidateTypeIn context) candidates)
              (referenceIn context (G.genRoot graph gen));
          Right (IM.singleton gen term)
        };
      FLambda _ _ body _ -> child body;
      FApply a b _ _ ->
        do {
          left <- child a;
          right <- child b;
          Right (IM.union left right)
        };
      FBinding _ a b _ ->
        do {
          left <- child a;
          right <- child b;
          Right (IM.union left right)
        };
      FMatch scrutinee _ branches ->
        do {
          results <-
            mapM child
              (Cons scrutinee
                 (map
                    (\branch ->
                       case branch of {
                         Branch _ body _ -> body
                       })
                    branches));
          Right (mergeEvidence results)
        };
      FRecursive definitions body _ ->
        do {
          continuation <- child body;
          results <- mapM
            (\definition ->
               case definition of {
                 RecursiveDefinition _ _ rhs _ closure ->
                   case closure of {
                     Nothing -> child rhs;
                     Just (RecursiveClosure group _) ->
                       resolveWithinIn context datatypes
                         (extendEnvironment env (boundsAtIn context group)) rhs
                   }
               }) definitions;
          Right (mergeEvidence (Cons continuation results))
        };
      FChecked variables body _ ->
        resolveWithinIn context datatypes
          (extendEnvironment env
             (map (\variable -> Pair (fst variable) (T.bottomKind (snd variable))) variables))
          body;
      _ -> Right IM.empty
    };
  elaborate graph typed =
    do {
      evidence <- resolveEvidence graph typed;
      elaborateResolved graph evidence typed
    };
  elaborateResolved :: Graph -> IntMap XTerm -> Typed -> Either String XTerm;
  elaborateResolved graph evidence typed =
    do {
      solver <- Solver.prepare graph;
      elaborateWithinIn (prepareTypes graph) (graphDatatypes graph) evidence solver M.empty typed
    };
  -- The checked compiler can retain its finished solver through normalization.
  -- Legacy graph entry points above still prepare and validate their own input.
  elaboratePrepared :: Solver -> IntMap XTerm -> Typed -> Either String XTerm;
  elaboratePrepared solver evidence typed =
    elaboratePreparedIn (prepareTypes (Solver.solverGraph solver)) solver evidence typed;
  elaboratePreparedIn :: TypeContext -> Solver -> IntMap XTerm -> Typed -> Either String XTerm;
  elaboratePreparedIn context solver evidence typed =
    elaborateWithinIn context (graphDatatypes (contextGraph context)) evidence solver M.empty typed;
  instantiateEdgeIn context datatypes solver env term edge =
    do {
      proof <- edgeComputationIn context datatypes solver env edge;
      Right (X.instantiate term proof)
    };
  elaborateEdgeIn :: TypeContext ->
                     DataEnv ->
                     IntMap XTerm ->
                     Solver -> Map XTyVar XType -> Typed -> Edge -> Either String XTerm;
  elaborateEdgeIn context datatypes evidence solver env typed edge =
    do {
      let {
        graph = contextGraph context
      };
      term <- elaborateWithinIn context datatypes evidence solver env typed;
      instantiateEdgeIn context datatypes solver env term edge
    };
  elaborateWithinIn :: TypeContext ->
                       DataEnv ->
                       IntMap XTerm -> Solver -> Map XTyVar XType -> Typed -> Either String XTerm;
  elaborateWithinIn context datatypes evidence solver outer typed =
    do {
      let {
        graph = contextGraph context
      };
      let {
        gen = C.generalization typed
      };
      let {
        bounds = boundsAtIn context gen
      };
      let {
        env = extendEnvironment outer bounds
      };
      let {
        child = elaborateWithinIn context datatypes evidence solver env
      };
      let {
        childEdge = elaborateEdgeIn context datatypes evidence solver env
      };
      body <-
        case C.form typed of {
          FVariable name Nothing -> Right (XVarTerm name);
          FVariable name (Just edge) ->
            instantiateEdgeIn context datatypes solver env (XVarTerm name) edge;
          FDeclaredVariable name declaration edge -> do {
            proof <- declaredFieldComputationIn context datatypes env declaration (C.fromGen edge);
            instantiateEdgeIn context datatypes solver env (X.instantiate (XVarTerm name) proof) edge
          };
          FLambda name domain body edge ->
            do {
              body' <- childEdge body edge;
              Right (XAbs name (referenceIn context domain) body')
            };
          FApply a b ea eb ->
            do {
              a' <- childEdge a ea;
              b' <- childEdge b eb;
              Right (XApp a' b')
            };
          FBinding name a b edge ->
            do {
              a' <- child a;
              b' <- childEdge b edge;
              Right (XLet name a' b')
            };
          FCoercion name domain codomain ->
            do {
              let {
                local = boundsAtIn context (G.genRoot graph gen)
              };
              let {
                gamma = extendEnvironment env local
              };
              let {
                domainType = referenceIn context domain
              };
              let {
                result =
                  if M.member T.compareTyVar (XTyVar (G.resolve graph codomain)) gamma
                  then XVar (XTyVar (G.resolve graph codomain))
                  else typeAtIn context codomain
              };
              proof <-
                proveInstanceWithIn datatypes context (\identity -> identity) gamma domainType
                  result;
              Right
                (foldr (\bound inner -> XTypeAbs (fst bound) (snd bound) inner)
                   (XAbs name domainType (X.instantiate (XVarTerm name) proof))
                   local)
            };
          FIntegerLiteral n -> Right (XIntTerm n);
          FDoubleLiteral n -> Right (XDoubleTerm n);
          FBooleanLiteral b -> Right (XBoolTerm b);
          FStringLiteral text -> Right (XStringTerm text);
          FPrimitive p identities -> Right (XPrimitive p (map (referenceIn context) identities));
          FConstructor constructor identities ->
            Right (XConstructor constructor (map (referenceIn context) identities));
          FMatch scrutinee edge branches ->
            do {
              a <- childEdge scrutinee edge;
              branches' <-
                mapM
                  (\branch ->
                     case branch of {
                       Branch pattern body branchEdge ->
                         do {
                           body' <- childEdge body branchEdge;
                           Right (XAlternative pattern body')
                         }
                     })
                  branches;
              Right (XCase a (referenceIn context (G.genRoot graph gen)) branches')
            };
          FRecursive definitions body edge ->
            do {
              definitions' <-
                mapM
                  (\definition ->
                     case definition of {
                       RecursiveDefinition name declaration rhs rhsEdge closure ->
                         do {
                           rhs' <- case closure of {
                             Nothing -> childEdge rhs rhsEdge;
                             Just (RecursiveClosure group copies) ->
                               elaborateRecursiveIn context datatypes evidence solver env
                                 group copies declaration rhs rhsEdge
                           };
                           Right (Triple name (schemeTypeIn context declaration) rhs')
                         }
                     })
                  definitions;
              body' <- childEdge body edge;
              Right (XLetRec definitions' body')
            };
          FEvidence _ ->
            case IM.lookup gen evidence of {
              Nothing -> Left "unresolved dictionary evidence";
              Just term -> Right term
            };
          FChecked variables body edge ->
            do {
              let {
                local =
                  extendEnvironment env
                    (map (\variable -> Pair (fst variable) (T.bottomKind (snd variable))) variables)
              };
              body' <- elaborateWithinIn context datatypes evidence solver local body;
              proof <- edgeComputationIn context datatypes solver local edge;
              let {
                abstracted =
                  foldr
                    (\variable inner -> XTypeAbs (fst variable) (T.bottomKind (snd variable)) inner)
                    (X.instantiate body' proof)
                    variables
              };
              let {
                actual =
                  foldr
                    (\variable inner -> XForall (fst variable) (T.bottomKind (snd variable)) inner)
                    (referenceIn context (C.toNode edge))
                    variables
              };
              let {
                expected = referenceIn context (G.genRoot graph gen)
              };
              let {
                positions = checkedCorrespondence graph (C.toNode edge) (G.genRoot graph gen)
              };
              let {
                kinds = M.fromList T.compareTyVar variables
              };
              adaptation <-
                proveInstanceUsing datatypes (checkedReplacementIn context positions kinds) env
                  actual
                  expected;
              Right (X.instantiate abstracted adaptation)
            }
        };
      Right (foldr (\bound inner -> XTypeAbs (fst bound) (snd bound) inner) body bounds)
    };
  -- Projection replacements are planned in telescope order. In particular,
  -- dropping a peer-only bounded variable uses its CURRENT substituted bound,
  -- not a graph readback containing already-eliminated variables.
  recursiveReplacementIn context copies bounds gamma variable =
    do {
      replacements <- foldM
        (\known bound -> do {
           let { name = fst bound };
           value <- case IM.lookup (T.tyVarId name) copies of {
             Just target -> graphReplacementIn context (\_ -> target) gamma name;
             Nothing -> Right (foldl
               (\ty entry -> T.substitute (fst entry) (snd entry) ty) (snd bound) known)
           };
           Right (append known (Cons (Pair name value) Nil))
         }) Nil bounds;
      case M.lookup T.compareTyVar variable (M.fromList T.compareTyVar replacements) of {
        Just value -> Right value;
        Nothing -> graphReplacementIn context
          (\identity -> IM.findWithDefault identity identity copies) gamma variable
      }
    };
  elaborateRecursiveIn context datatypes evidence solver env group copies declaration rhs edge =
    do {
      let { bounds = boundsAtIn context group };
      let { local = extendEnvironment env bounds };
      value <- elaborateEdgeIn context datatypes evidence solver local rhs edge;
      let {
        source = foldr (\bound body -> XForall (fst bound) (snd bound) body)
          (referenceIn context (C.toNode edge)) bounds
      };
      let {
        abstracted = foldr (\bound body -> XTypeAbs (fst bound) (snd bound) body) value bounds
      };
      proof <- proveInstanceUsing datatypes (recursiveReplacementIn context copies bounds) env
        source (schemeTypeIn context declaration);
      Right (X.instantiate abstracted proof)
    };
  checkedReplacementIn context positions kinds gamma variable =
    let {
      graph = contextGraph context
    } in
    case IM.lookup (T.tyVarId variable) positions of {
      Just identity ->
        Right
          (if M.member T.compareTyVar (XTyVar identity) gamma
           then XVar (XTyVar identity)
           else typeAtIn context identity);
      Nothing ->
        case M.lookup T.compareTyVar variable kinds of {
          Just kind -> Right (T.bottomKind kind);
          Nothing ->
            let {
              identity = G.resolve graph (T.tyVarId variable)
            } in
            if IM.member identity (G.nodes graph)
            then Right
                   (if M.member T.compareTyVar (XTyVar identity) gamma
                    then XVar (XTyVar identity)
                    else typeAtIn context identity)
            else Left ("checked declaration lost type provenance: " ++ showInt (T.tyVarId variable))
        }
    };
  checkedCorrespondence graph source target =
    checkedPositions graph IS.empty IM.empty (Cons (Pair source target) Nil);
  checkedPositions :: Graph -> IntSet -> IntMap Int -> List (Pair Int Int) -> IntMap Int;
  checkedPositions _ _ images Nil = images;
  checkedPositions graph seen images (Cons (Pair source target) rest) =
    let {
      a = G.resolve graph source
    } in
    let {
      b = G.resolve graph target
    } in
    if IS.member a seen
    then checkedPositions graph seen images rest
    else let {
           inserted = IM.insert a b images
         } in
         let {
           withSkolem =
             case G.tag (G.nodeAt graph a) of {
               GSkolem identity _ -> IM.insert identity b inserted;
               _ -> inserted
             }
         } in
         let {
           pairs = structuralPairs (G.tag (G.nodeAt graph a)) (G.tag (G.nodeAt graph b))
         } in
         checkedPositions graph (IS.insert a seen) withSkolem (append pairs rest);
  -- Public compatibility entry points used by graph-level callers.
  typeAt :: Graph -> Int -> XType;
  typeAt graph identity = typeAtIn (prepareTypes graph) identity;
  reference :: Graph -> Int -> XType;
  reference graph identity = referenceIn (prepareTypes graph) identity;
  boundsAt :: Graph -> Int -> List (Pair XTyVar XType);
  boundsAt graph identity = boundsAtIn (prepareTypes graph) identity;
  schemeType :: Graph -> Int -> XType;
  schemeType graph identity = schemeTypeIn (prepareTypes graph) identity
}
