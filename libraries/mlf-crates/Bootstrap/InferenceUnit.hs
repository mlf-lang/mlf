-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.InferenceUnit where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.X.Pretty as Pretty;
  -- Class translation is a crate query, before the value dependency graph is
  -- built. Its generated selectors/dictionaries become ordinary signed graph
  -- vertices. Inference queries consume this lowered representation directly.
  data LoweredDeclarations =
    LoweredDeclarations ([] DataDecl) ([] ((,,) String (Maybe SAnnotation) SExpr)) (Map String String) |
    IndexedDeclarations ([] DataDecl) Dependency.GeneratedTable
      ([] ((,) (V.Index Declaration) ((,,) String (Maybe SAnnotation) SExpr))) (Map String String);
  loweredData lowered = case lowered of {
    LoweredDeclarations ds _ _ -> ds; IndexedDeclarations ds _ _ _ -> ds
  };
  loweredValues lowered = case lowered of {
    LoweredDeclarations _ values _ -> values; IndexedDeclarations _ _ values _ -> map snd values
  };
  loweredNames lowered = case lowered of {
    LoweredDeclarations _ _ names -> names; IndexedDeclarations _ _ _ names -> names
  };
  loweredDeclarationTable lowered = case lowered of {
    LoweredDeclarations _ _ _ -> Nothing; IndexedDeclarations _ table _ _ -> Just table
  };
  loweredIdValues lowered = case lowered of {
    LoweredDeclarations _ _ _ -> []; IndexedDeclarations _ _ rows _ -> rows
  };
  recursiveAnnotation :: RecursiveMode -> Maybe SAnnotation;
  recursiveAnnotation mode =
    case mode of {
      InferRecursive -> Nothing;
      CheckRecursive annotation -> Just annotation
    };
  extractLoweredDeclarations :: SExpr ->
                                Either String ([] ((,,) String (Maybe SAnnotation) SExpr));
  extractLoweredDeclarations expression = extractDeclarations expression [];
  extractDeclarations :: SExpr ->
                         [] ((,,) String (Maybe SAnnotation) SExpr) ->
                         Either String ([] ((,,) String (Maybe SAnnotation) SExpr));
  extractDeclarations expression reversed =
    let {
      matchValueShared1 = expression
    } in
    case matchValueShared1 of {
      SDeclScope _ group -> extractDeclarations group reversed;
      SLet matchValueShared2 matchValueShared3 matchValueShared4 ->
        let {
          n = matchValueShared2
        } in
        let {
          rhs = matchValueShared3
        } in
        let {
          body = matchValueShared4
        } in
        let {
          -- A checked expression can come from a qualified SAnn too. Only
          -- declaration provenance may restore a declaration signature here.
          declaration =
            case rhs of {
              SSignature value annotation -> (,,) n (Just annotation) value;
              _ -> (,,) n Nothing rhs
            }
        } in
        extractDeclarations body ((:) declaration reversed);
      SLetRec matchValueShared5 matchValueShared6 ->
        let {
          definitions = matchValueShared5
        } in
        let {
          body = matchValueShared6
        } in
        extractDeclarations body
          (foldlStrict (\acc ((,,) n mode rhs) -> (:) ((,,) n (recursiveAnnotation mode) rhs) acc) reversed
             definitions);
      SConstructor matchValueShared7 ->
        if MLF.Primitive.eqString matchValueShared7 "()"
        then Right (reverse reversed)
        else Left "lowered crate declarations must end in ()";
      _ -> Left "lowered crate declarations must end in ()"
    };
  lowerDeclarations :: [] DataDecl ->
                       [] SClassDecl ->
                       [] ((,) String SInstanceDecl) ->
                       Map String IntSet ->
                       [] IntSet ->
                       [] ((,,) String (Maybe SAnnotation) SExpr) ->
                       Either String LoweredDeclarations;
  lowerDeclarations datatypes classes instances valueScopes instanceScopes members =
    lowerDeclarationsWithImports M.empty datatypes classes instances valueScopes instanceScopes
      members;
  lowerDeclarationsWithImports :: Map String SType ->
                                  [] DataDecl ->
                                  [] SClassDecl ->
                                  [] ((,) String SInstanceDecl) ->
                                  Map String IntSet ->
                                  [] IntSet ->
                                  [] ((,,) String (Maybe SAnnotation) SExpr) ->
                                  Either String LoweredDeclarations;
  -- Helper closures retain the existing dictionary translation of unsigned
  -- and qualified helpers used inside instance methods. Their local lets keep
  -- the helper's defining-module instance scope through valueScopes.
  lowerDeclarationsWithImports externals datatypes classes instances valueScopes instanceScopes members =
    do {
      closedInstances <-
        traverseEither (\((,) n inst) -> mapEither ((,) n) (Separate.closeInstance members inst))
          instances;
      body <- Surface.bindValues members (SConstructor "()");
      lowerBoundDeclarations externals datatypes classes closedInstances valueScopes instanceScopes body
    };
  lowerBoundDeclarations externals datatypes classes closedInstances valueScopes =
    lowerBoundInScopes externals datatypes classes closedInstances (Dependency.NamedScopes valueScopes);
  lowerBoundInScopes = lowerBoundWithImports M.empty;
  lowerBoundWithImports conventions externals datatypes classes closedInstances valueScopes instanceScopes body = do {
    (,) lowered generation <- Classes.lowerSeparateClassesAndSlotsWithImports conventions externals (map fst closedInstances) valueScopes
      instanceScopes (SClassProgram datatypes classes (map snd closedInstances) body);
    case lowered of {
      (,) (SProgram ds expression) names -> case generation of {
        Nothing -> do {
          declarations <- extractLoweredDeclarations expression;
          Right (LoweredDeclarations ds (filter (\((,,) n _ _) -> not (M.member compareString n externals)) declarations) names)
        };
        Just table -> do {
          imported <- traverseEither (\key -> case Dependency.generatedImportId table key of {
            Nothing -> Left ("lowered import lacks a declaration slot: " ++ key);
            Just i -> Right (V.toInt i)
          }) (M.keys externals);
          let { external = IS.fromList imported };
          rows <- extractIndexedDeclarations (Dependency.generatedSymbols table) expression [];
          ensure (IS.size (IS.fromList (map (compose V.toInt fst) rows)) == length rows)
            "duplicate lowered declaration owner";
          Right (IndexedDeclarations ds table (filter (\entry -> not (IS.member (V.toInt (fst entry)) external)) rows) names)
        }
      };
      _ -> Left "class lowering did not produce core crate declarations"
    }
  };
  extractIndexedDeclarations symbols expression result = case expression of {
    SConstructor n -> if eqString n "()" then Right (reverse result) else Left "invalid lowered declaration terminator";
    SDeclScope ids group -> let {
      owned i row = do {
        Dependency.checkedDeclId symbols (V.toInt i);
        let { name = Surface.valueName row };
        ensure (eqString name (Dependency.symbolName symbols i) || eqString name (Dependency.symbolKey symbols i))
          "lowered declaration owner does not match its binding";
        Right ((,) i row)
      }
    } in case group of {
      SLet n rhs rest -> case ids of {
        [i] -> do {
          row <- owned i (case rhs of {
            SSignature value annotation -> (,,) n (Just annotation) value; _ -> (,,) n Nothing rhs
          });
          extractIndexedDeclarations symbols rest ((:) row result)
        };
        _ -> Left "lowered declaration scope arity mismatch"
      };
      SLetRec defs rest -> do {
        ensure (length ids == length defs) "lowered declaration scope arity mismatch";
        rows <- sequenceEither (zipWith (\i ((,,) n mode rhs) -> owned i ((,,) n (recursiveAnnotation mode) rhs)) ids defs);
        extractIndexedDeclarations symbols rest (foldl (\acc row -> (:) row acc) result rows)
      };
      _ -> Left "invalid lowered declaration group"
    };
    _ -> Left "lowered declaration is missing its owner"
  };
  -- Dependency closure for crate queries is indexed and works equally for
  -- source values and generated dictionary declarations. Unknown names are
  -- external semantic inputs, not vertices owned by this crate.
  declarationClosure :: [] ((,,) String (Maybe SAnnotation) SExpr) ->
                        [] String -> [] ((,,) String (Maybe SAnnotation) SExpr);
  declarationClosure declarations roots =
    let {
      values =
        M.fromList compareString
          (map
             (\v ->
                case v of {
                  (,,) n _ _ -> (,) n v
                })
             declarations)
    } in
    let {
      edges = M.fromList compareString (Dependency.declarationEdges declarations)
    } in
    let {
      wanted = closeDependencies edges S.empty roots
    } in
    map snd (filter (\entry -> S.member compareString (fst entry) wanted) (M.toList values));
  closeDependencies :: Map String ([] String) -> Set String -> [] String -> Set String;
  closeDependencies edges seen pending =
    case pending of {
      [] -> seen;
      (:) n rest ->
        if S.member compareString n seen
        then closeDependencies edges seen rest
        else closeDependencies edges (S.insert compareString n seen)
               (append (M.findWithDefault compareString [] n edges) rest)
    };
  mergeExternal :: Map String XType -> (,) String XType -> Either String (Map String XType);
  mergeExternal types entry =
    case entry of {
      (,) n ty ->
        do {
          ensure (S.null (T.freeVars ty)) ("inference dependency has an open type: " ++ n);
          case M.lookup compareString n types of {
            Nothing -> Right (M.insert compareString n ty types);
            Just other ->
              if T.alphaEq other ty
              then Right types
              else Left ("conflicting inference dependency scheme: " ++ n)
          }
        }
    };
  -- Only dependency bindings actually observed by this SCC belong in the
  -- argument interfaces. The caller owns datatype/class/instance closure and
  -- persistent query keys; this function always performs the complete checked
  -- inference, elaboration, type-agreement and erasure-agreement pipeline.
  compileLoweredGroup :: String ->
                         [] Separate.UnitInterface ->
                         [] DataDecl ->
                         [] ((,,) String (Maybe SAnnotation) SExpr) ->
                         Either String Separate.UnitObject;
  -- SCC fragments are parameters, not independently imported modules. The
  -- crate artifact validates the selected schemes and owns the crate DAG;
  -- module interface dependency hashes would cause transitive invalidation.
  compileLoweredGroup name dependencies datatypes members =
    compileLoweredGroupUsing (\term -> Separate.fingerprint (Pretty.prettyTerm term))
      name dependencies datatypes members;
  compileLoweredGroupWithDatatypes :: Separate.DatatypeEncodings -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupWithDatatypes pool name dependencies datatypes members =
    compileLoweredGroupUsing (Separate.fingerprintTermWithDatatypes pool)
      name dependencies datatypes members;
  compileLoweredGroupUsing :: (XTerm -> String) -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupUsing payloadFingerprint name dependencies datatypes members =
    do {
      (,) externalTypes lowered <- prepareNamedGroup dependencies datatypes members;
      finishLoweredGroup payloadFingerprint name externalTypes members lowered
    };
  compileLoweredGroupIndexed payloadFingerprint name parameters datatypes members = do {
    (,) externalTypes lowered <- prepareIndexedGroup parameters datatypes members;
    finishLoweredGroup payloadFingerprint name externalTypes (map snd members) lowered
  };
  finishLoweredGroup payloadFingerprint name externalTypes members lowered = do {
    (,,) declarations parameters implementation <- compileGroupBody externalTypes lowered;
    -- Only the named external parameters may precede the declaration
    -- spine. The checker peels leading lambdas when collecting its
    -- inventory, so an extra lambda here must still be rejected.
    case implementation of {
      XAbs _ _ _ -> Left "invalid inference fragment: expected declarations ending in ()";
      _ -> Right ()
    };
    let {
      payload =
        XWithData declarations
          (foldr (\((,) n ty) term -> XAbs n ty term) implementation parameters)
    };
    checked <- Checked.check payload;
    bindings <- Checked.declarationBindings checked;
    ensure
      (eqList eqString (sortBy compareString (map (\((,) n _) -> X.nameHint n) bindings))
         (sortBy compareString (map (\((,,) n _ _) -> n) members)))
      "inference fragment changed declaration ownership";
    let {
      iface =
        Separate.UnitInterface name [] [] declarations [] []
          (Separate.sortBindings
             (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) bindings))
          (payloadFingerprint payload)
    };
    Right (Separate.CheckedUnitObject iface checked)
  };
  compileOpenGroup = compileOpenGroupUsing (\_ -> "");
  compileOpenGroupUsing :: (XTerm -> String) -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Open.Fragment;
  compileOpenGroupUsing payloadFingerprint name dependencies datatypes members =
    do {
      (,) externalTypes lowered <- prepareNamedGroup dependencies datatypes members;
      finishOpenGroup externalTypes members lowered
    };
  prepareNamedGroup dependencies datatypes members = do {
      ensure (not (null members)) "cannot infer an empty declaration group";
      externalTypes <- foldM mergeExternal M.empty (concatMap Separate.unitBindings dependencies);
      traverseEither
        (\((,,) n _ _) ->
           ensure (not (M.member compareString n externalTypes))
             ("inference group also imports its own binding: " ++ n))
        members;
      body <- Surface.bindValues members (SConstructor "()");
      let {
        -- Members already contain explicit evidence applications. Recovering
        -- source qualifications here would insert the managed argument twice.
        externals = M.map (Separate.sourceSchemeIn M.empty False) externalTypes
      };
      lowered <- Classes.lowerSeparateClasses externals [] (SProgram datatypes body);
      Right ((,) externalTypes lowered)
  };
  compileOpenGroupIndexed name parameters datatypes members = do {
    (,) externalTypes lowered <- prepareIndexedGroup parameters datatypes members;
    case monomorphicIndexed parameters members lowered of {
      Right fragment -> Right fragment;
      Left _ -> finishOpenGroup externalTypes (map snd members) lowered
    }
  };
  -- Signed nonrecursive monotypes need checking, not generalization. This
  -- deliberately partial elaborator accepts only exact monomorphic uses and
  -- still obtains the opaque fragment proof from the independent xMLF checker.
  -- Unsupported syntax/types and all failed checks take the ordinary path.
  monomorphicType :: SType -> Either String XType;
  monomorphicType ty = case ty of {
    SArrow a b -> do { x <- monomorphicType a; y <- monomorphicType b; Right (XArrow x y) };
    SCon n args -> mapEither (XCon n) (traverseEither monomorphicType args);
    STypeApp f a -> do { x <- monomorphicType f; y <- monomorphicType a; Right (T.apply x y) };
    _ -> Left "not a closed monotype"
  };
  monomorphicAnnotation (SAnnotation variables ty) = do {
    ensure (null variables) "existential monomorphic annotation";
    monomorphicType ty
  };
  monomorphicTarget ty = case ty of {
    XArrow a b -> monomorphicTarget a && monomorphicTarget b;
    XCon _ args -> all monomorphicTarget args;
    XApply f a -> monomorphicTarget f && monomorphicTarget a;
    _ -> False
  };
  monomorphicIndexed parameters members lowered = case (,) members lowered of {
    (,) [(,) identity ((,,) name (Just annotation) _)] ((,) (SProgram declarations expression) _) -> do {
      expected <- monomorphicAnnotation annotation;
      ensure (all (\((,,) _ _ ty) -> monomorphicTarget ty) parameters)
        "polymorphic import requires ordinary adaptation";
      let { entries = zip parameters (range 0 (length parameters - 1));
        pair = \((,,) _ hint ty) serial -> (,) (XName serial hint) ty;
        globals = M.fromList compareInt (map (\((,) row@((,,) i _ _) serial) ->
          (,) (V.toInt i) (pair row serial)) entries);
        names = M.fromList compareString (map (\((,) row@((,,) _ n _) serial) ->
          (,) n (pair row serial)) entries);
        ps = map (\((,) row serial) -> pair row serial) entries;
        core = if null parameters then expression else case expression of {
          SDeclScope _ (SLetRec _ body) -> body;
          _ -> expression
        } };
      rhs <- case core of {
        SDeclScope [i] (SLet n value (SConstructor "()")) -> do {
          ensure (V.toInt i == V.toInt identity && eqString n name) "monomorphic group identity";
          Right value
        };
        _ -> Left "not a single nonrecursive binding"
      };
      result <- monomorphicCheck globals names (length parameters + 1) expected rhs;
      env <- Open.environment declarations;
      fragment <- Open.check env ps
        (XLet (XName (length parameters) name) (fst result) (XConstructor "()" []));
      ensure (case Open.bindings fragment of {
        [(,) actual ty] -> eqString (X.nameHint actual) name && T.alphaEq expected ty;
        _ -> False
      }) "monomorphic fragment export mismatch";
      Right fragment
    };
    _ -> Left "not a signed nonrecursive monotype"
  };
  monomorphicCheck globals names serial expected expression = case expression of {
    SDeclScope [identity] (SLam name annotation body) ->
      monomorphicLambda globals names serial expected (Just identity) name annotation body;
    SLam name annotation body ->
      monomorphicLambda globals names serial expected Nothing name annotation body;
    SSignature body annotation -> monomorphicAnnotated globals names serial expected body annotation;
    SAnn body annotation -> monomorphicAnnotated globals names serial expected body annotation;
    SChecked ty body -> monomorphicAnnotated globals names serial expected body (SAnnotation [] ty);
    SLet name rhs body -> do {
      (,,) value ty next <- monomorphicInfer globals names serial rhs;
      let { binder = XName next name };
      result <- monomorphicCheck globals (M.insert compareString name ((,) binder ty) names)
        (advanceIdentity next 1) expected body;
      Right ((,) (XLet binder value (fst result)) (snd result))
    };
    _ -> do {
      (,,) term actual next <- monomorphicInfer globals names serial expression;
      ensure (T.alphaEq actual expected) "monomorphic type mismatch";
      Right ((,) term next)
    }
  };
  monomorphicAnnotated globals names serial expected body annotation = do {
    actual <- monomorphicAnnotation annotation;
    ensure (T.alphaEq actual expected) "monomorphic annotation mismatch";
    monomorphicCheck globals names serial expected body
  };
  monomorphicLambda globals names serial expected identity name annotation body = case expected of {
    XArrow argument result -> do {
      _ <- case identity of { Nothing -> Right (); Just i ->
        ensure (not (M.member compareInt (V.toInt i) globals)) "monomorphic declaration identity already bound" };
      _ <- case annotation of { Nothing -> Right (); Just written -> do {
        actual <- monomorphicAnnotation written;
        ensure (T.alphaEq actual argument) "monomorphic lambda annotation mismatch"
      } };
      let { binder = XName serial name; binding = (,) binder argument;
        scope = case identity of { Nothing -> globals; Just i -> M.insert compareInt (V.toInt i) binding globals } };
      compiled <- monomorphicCheck scope (M.insert compareString name binding names)
        (advanceIdentity serial 1) result body;
      Right ((,) (XAbs binder argument (fst compiled)) (snd compiled))
    };
    _ -> Left "monomorphic lambda requires an arrow"
  };
  monomorphicUse serial binding = case binding of {
    Nothing -> Left "unknown monomorphic variable";
    Just ((,) name ty) -> do {
      ensure (monomorphicTarget ty) "polymorphic variable requires instantiation";
      Right ((,,) (XVarTerm name) ty serial)
    }
  };
  monomorphicInfer globals names serial expression = case expression of {
    SVar name -> monomorphicUse serial (M.lookup compareString name names);
    SGlobal identity _ -> monomorphicUse serial (M.lookup compareInt (V.toInt identity) globals);
    SIntLit value -> Right ((,,) (XIntTerm value) (XCon "Int" []) serial);
    SDoubleLit value -> Right ((,,) (XDoubleTerm value) (XCon "Double" []) serial);
    SBoolLit value -> Right ((,,) (XBoolTerm value) (XCon "Bool" []) serial);
    SStringLit value -> Right ((,,) (XStringTerm value) (XCon "String" []) serial);
    SPrimitive primitive -> case Primitive.primitiveSignature primitive of {
      (,) [] signature -> do {
        ty <- T.instantiateField M.empty signature;
        ensure (monomorphicTarget ty) "polymorphic primitive";
        Right ((,,) (XPrimitive primitive []) ty serial)
      };
      _ -> Left "polymorphic primitive requires instantiation"
    };
    SApp function argument -> do {
      (,,) compiled ty next <- monomorphicInfer globals names serial function;
      case ty of {
        XArrow domain result -> do {
          value <- monomorphicCheck globals names next domain argument;
          Right ((,,) (XApp compiled (fst value)) result (snd value))
        };
        _ -> Left "monomorphic application requires an arrow"
      }
    };
    SSignature body annotation -> monomorphicInferAnnotated globals names serial body annotation;
    SAnn body annotation -> monomorphicInferAnnotated globals names serial body annotation;
    SChecked ty body -> monomorphicInferAnnotated globals names serial body (SAnnotation [] ty);
    _ -> Left "expression requires ordinary inference"
  };
  monomorphicInferAnnotated globals names serial body annotation = do {
    ty <- monomorphicAnnotation annotation;
    result <- monomorphicCheck globals names serial ty body;
    Right ((,,) (fst result) ty (snd result))
  };
  prepareIndexedGroup parameters datatypes members = do {
    ensure (not (null members)) "cannot infer an empty declaration group";
    let { parameterIds = M.fromList compareString (map (\((,,) i n _) -> (,) n i) parameters) };
    externalTypes <- foldM mergeExternal M.empty (map (\((,,) _ n ty) -> (,) n ty) parameters);
    ensure (length parameters == M.size parameterIds) "duplicate inference parameter";
    let { externalIds = map (\((,,) i _ _) -> V.toInt i) parameters };
    ensure (length externalIds == IS.size (IS.fromList externalIds)) "duplicate inference parameter slot";
    ensure (not (any (\((,) i _) -> elem eqInt (V.toInt i) externalIds) members))
      "inference group also imports its own binding";
    body <- Surface.bindIndexedMembers members (SConstructor "()");
    let { externals = M.map (Separate.sourceSchemeIn M.empty False) externalTypes };
    lowered <- Classes.lowerSeparateClasses externals [] (SProgram datatypes body);
    let { attached = case lowered of {
      (,) (SProgram ds (SLetRec defs rest)) registry -> if M.null externalTypes then lowered else
        (,) (SProgram ds (SDeclScope (map (\((,,) n _ _) -> M.get compareString n parameterIds) defs) (SLetRec defs rest))) registry;
      _ -> lowered
    } };
    Right ((,) externalTypes attached)
  };
  compileGroupBody externalTypes lowered = do {
      compiled <- mapLeft Compiler.prettyError (Compiler.finishCompilation lowered);
      let {
        coreAndData =
          case Compiler.compiledTerm compiled of {
            XWithData ds term -> (,) ds term;
            term -> (,) [] term
          }
      };
      let {
        declarations = fst coreAndData
      };
      let {
        core = snd coreAndData
      };
      boundValueShared9 <-
        if M.null externalTypes
        then Right ((,) [] core)
        else case core of {
               XLetRec bindings rest ->
                 do {
                   ensure
                     (eqList eqString (map (\((,,) n _ _) -> X.nameHint n) bindings)
                        (M.keys externalTypes))
                     "inference parameter order mismatch";
                   traverseEither
                     (\((,,) n ty _) ->
                        ensure
                          (case M.lookup compareString (X.nameHint n) externalTypes of {
                             Nothing -> False;
                             Just expected -> T.alphaEq ty expected
                           })
                          ("dependency scheme changed during inference: " ++ X.nameHint n))
                     bindings;
                   Right ((,) (map (\((,,) n ty _) -> (,) n ty) bindings) rest)
                 };
               _ -> Left "inference did not retain external parameters"
             };
      Right ((,,) declarations (fst boundValueShared9) (snd boundValueShared9))
  };
  finishOpenGroup externalTypes members lowered = do {
    (,,) declarations parameters implementation <- compileGroupBody externalTypes lowered;
    env <- Open.environment declarations;
    checked <- Open.check env parameters implementation;
    ensure
      (eqList eqString (sortBy compareString (map (\((,) n _) -> X.nameHint n) (Open.bindings checked)))
        (sortBy compareString (map (\((,,) n _ _) -> n) members)))
      "inference fragment changed declaration ownership";
    Right checked
  }
}
