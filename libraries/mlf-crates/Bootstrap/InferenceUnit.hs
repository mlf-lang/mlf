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
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.Kinding as Kinding;
  import qualified Bootstrap.SourceEquality as SourceEquality;
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
  compileOpenGroupIndexed name parameters datatypes members =
    case signedApplicationGroup parameters datatypes members of {
      Right fragment -> Right fragment;
      Left _ -> compileElaboratedGroup parameters datatypes members
    };
  compileElaboratedGroup parameters datatypes members = do {
    (,) externalTypes lowered <- prepareIndexedGroup parameters datatypes members;
    case monomorphicIndexed parameters members lowered of {
      Right fragment -> Right fragment;
      Left _ -> case groundIndexed parameters members lowered of {
        Right fragment -> Right fragment;
        Left _ -> case groundRecursiveIndexed parameters members lowered of {
          Right fragment -> Right fragment;
          Left _ -> case signedDataGroup parameters members lowered of {
            Right fragment -> Right fragment;
            Left _ -> finishOpenGroup externalTypes (map snd members) lowered
          }
        }
      }
    }
  };
  -- A closed, explicitly quantified constructor or case projection has its
  -- type arguments in the declaration. The ordinary xMLF checker verifies
  -- constructor arity, coverage, branch types and the complete exported type.
  signedDataGroup parameters members lowered = case (,,) parameters members lowered of {
    (,,) [] [(,) owner ((,,) exported (Just declared) _)]
      ((,) (SProgram datatypes (SDeclScope [slot] (SLet name (SSignature source written)
        (SConstructor "()")))) _) -> do {
      ensure (V.toInt owner == V.toInt slot && eqString exported name &&
        SourceEquality.eqSAnnotation declared written) "signed data declaration mismatch";
      signature <- case written of {
        SAnnotation [] scheme@(SForall Flexible _ _ _) -> Right scheme;
        _ -> Left "signed data declaration needs an explicit universal type"
      };
      implementation <- case source of {
        SChecked ty value -> do {
          ensure (SourceEquality.eqSType ty signature) "signed data body annotation mismatch";
          Right value
        };
        _ -> Right source
      };
      env <- Open.environment datatypes;
      Kinding.annotationType (Open.dataEnvironment env) M.empty signature;
      field <- Classes.fieldType signature;
      expected <- T.instantiateField M.empty field;
      term <- signedDataValue expected implementation;
      result <- Open.check env [] (XLet (XName 0 name) term (XConstructor "()" []));
      ensure (case Open.bindings result of {
        [(,) actual ty] -> eqString (X.nameHint actual) name && T.alphaEq expected ty;
        _ -> False
      }) "signed data result type mismatch";
      Right result
    };
    _ -> Left "ordinary data elaboration required"
  };
  dataMonotype ty = case ty of {
    XVar _ -> True;
    XArrow a b -> dataMonotype a && dataMonotype b;
    XCon _ arguments -> all dataMonotype arguments;
    XApply f a -> dataMonotype f && dataMonotype a;
    _ -> False
  };
  -- Source inference can remove vacuous quantifiers and reorder a prefix.
  -- With one used star-kinded variable the declared prefix is canonical.
  signedDataValue expected value = case (,) expected value of {
    (,) (XForall variable XBot body@(XArrow input output)) (SLam argument Nothing expression) -> do {
      ensure (dataMonotype input && dataMonotype output &&
        S.member T.compareTyVar variable (T.freeVars body)) "data declaration needs one used type parameter";
      let { binder = XName 1 argument };
      term <- signedDataBody binder output expression;
      Right (XTypeAbs variable XBot (XAbs binder input term))
    };
    _ -> Left "signed data declaration needs a singly quantified function"
  };
  signedDataBody binder expected expression = let {
    local name = eqString name (X.nameHint binder);
    constructor arguments node = case node of {
      SConstructor name -> case expected of {
        XCon _ types -> Right (foldlStrict XApp (XConstructor name types) arguments);
        _ -> Left "constructor result requires a datatype"
      };
      SApp function (SVar name) -> if local name
        then constructor ((:) (XVarTerm binder) arguments) function
        else Left "unknown constructor argument";
      _ -> Left "ordinary constructor elaboration required"
    };
    branch ((,) reversed serial) alternative = case alternative of {
      SAlternative (SConstructorPattern name bindings) (SVar selected) -> let {
        make i item = case item of { Nothing -> Nothing; Just hint -> Just (XName (advanceIdentity serial i) hint) };
        fields = mapIndexed make bindings;
        named = concatMap maybeToList fields
      } in do {
        ensure (S.size (S.fromList compareString (map X.nameHint named)) == length named)
          "duplicate data pattern variable";
        case filter (compose (eqString selected) X.nameHint) named of {
          [found] -> Right ((,) ((:) (XAlternative (XConstructorPattern name fields) (XVarTerm found)) reversed)
            (advanceIdentity serial (length bindings)));
          _ -> Left "data projection needs a bound field"
        }
      };
      _ -> Left "ordinary case elaboration required"
    }
  } in case expression of {
    SCase (SVar name) alternatives -> do {
      ensure (local name && not (null alternatives)) "data case requires its argument";
      (,) reversed _ <- foldM branch ((,) [] 2) alternatives;
      Right (XCase (XVarTerm binder) expected (reverse reversed))
    };
    _ -> constructor [] expression
  };
  -- In a signed first-order body, applications introduce neither a type
  -- annotation nor a binder. Build the resolved term once and let the
  -- independent checker establish every intermediate type in its environment.
  signedApplicationGroup parameters declarations members = case members of {
    [(,) owner ((,,) exported (Just annotation) expression)] -> do {
      expected <- monomorphicAnnotation annotation;
      let { numbered = zip parameters (range 0 (length parameters - 1));
        bindings = map (\((,) ((,,) _ hint ty) number) -> (,) (XName number hint) ty) numbered;
        globals = M.fromList compareInt (zipWith (\((,,) id _ _) binding ->
          (,) (V.toInt id) binding) parameters bindings);
        names = M.fromList compareString (map (\binding -> (,) (X.nameHint (fst binding)) binding) bindings);
        count = length parameters; identity = V.toInt owner; serial = advanceIdentity count 1;
        term binding = XVarTerm (fst binding);
        scoped binding = signedBinding (fst binding) (snd binding) };
      ensure (M.size globals == count && M.size names == count && not (M.member compareInt identity globals)
        && not (M.member compareString exported names)) "signed application needs distinct parameters";
      result <- if all (compose monomorphicTarget snd) bindings
        then signedApplicationSpine identity (M.map term globals) (M.map term names) serial expected expression
        else do {
          ensure (all (\binding -> case scoped binding of { SignedUnsupported -> False; _ -> True }) bindings)
            "signed application needs ground or unary parameters";
          signedApplicationSpineUsing (\n ty -> SignedValue (XVarTerm n) ty) signedInstanceTerm
            identity (M.map scoped globals) (M.map scoped names) serial expected expression
        };
      env <- Open.environment declarations;
      fragment <- Open.check env bindings (XLet (XName count exported) result (XConstructor "()" []));
      ensure (case Open.bindings fragment of {
        [(,) actual ty] -> eqString (X.nameHint actual) exported && T.alphaEq ty expected; _ -> False
      }) "signed application result type mismatch";
      Right fragment
    };
    _ -> Left "signed application needs one signature"
  };
  signedApplicationSpine = signedApplicationSpineUsing (\name _ -> XVarTerm name) signedApplicationBody;
  signedApplicationSpineUsing bind finish owner globals names serial expected expression = let {
    annotated written body = do {
      actual <- monomorphicAnnotation written;
      ensure (T.alphaEq expected actual) "signed application annotation mismatch";
      again body
    };
    again = signedApplicationSpineUsing bind finish owner globals names serial expected;
    lambda slot name written body = case expected of {
      XArrow domain result -> do {
        case written of {
          Just ty -> do { actual <- monomorphicAnnotation ty;
            ensure (T.alphaEq domain actual) "signed application binder annotation mismatch" };
          Nothing -> Right ()
        };
        let { binder = XName serial name; variable = bind binder domain };
        scope <- case slot of {
          Nothing -> Right globals;
          Just i -> do {
            ensure (i /= owner && not (M.member compareInt i globals)) "signed application binder identity collision";
            Right (M.insert compareInt i variable globals)
          }
        };
        value <- signedApplicationSpineUsing bind finish owner scope (M.insert compareString name variable names)
          (advanceIdentity serial 1) result body;
        Right (XAbs binder domain value)
      };
      _ -> Left "signed application binder requires an arrow"
    }
  } in case expression of {
    SDeclScope [i] (SLam name ty body) -> lambda (Just (V.toInt i)) name ty body;
    SLam name ty body -> lambda Nothing name ty body;
    SChecked ty body -> annotated (SAnnotation [] ty) body;
    SSignature body ty -> annotated ty body;
    SAnn body ty -> annotated ty body;
    SCallSite _ _ body -> again body;
    SSourceDefinition body -> again body;
    _ -> finish globals names expression
  };
  signedApplicationBody globals names expression = let {
    sub = signedApplicationBody globals names;
    variable binding = case binding of { Just term -> Right term; Nothing -> Left "unknown signed application variable" }
  } in case expression of {
    SApp f a -> do { x <- sub f; y <- sub a; Right (XApp x y) };
    SGlobal i _ -> variable (M.lookup compareInt (V.toInt i) globals);
    SVar name -> if eqString name "$MLF.Stack.callStack" then Left "managed call stack requires evidence"
      else variable (M.lookup compareString name names);
    -- A constructor with no type arguments is checked in the declaration's
    -- datatype environment along with the rest of the application.
    SConstructor name -> Right (XConstructor name []);
    SPrimitive p -> case Primitive.primitiveSignature p of {
      (,) [] signature -> do {
        ty <- T.instantiateField M.empty signature;
        ensure (monomorphicTarget ty) "nonmonomorphic primitive";
        Right (XPrimitive p [])
      };
      _ -> Left "primitive needs type arguments"
    };
    SIntLit n -> Right (XIntTerm n);
    SBoolLit b -> Right (XBoolTerm b);
    SDoubleLit n -> Right (XDoubleTerm n);
    SStringLit text -> Right (XStringTerm text);
    SCallSite _ _ body -> sub body;
    SSourceDefinition body -> sub body;
    _ -> Left "ordinary elaboration required"
  };
  -- The operand of a unary scheme determines its only type argument. Keep
  -- that evidence on the variable occurrence and check the constructed term
  -- in the complete datatype and parameter environment before accepting it.
  data SignedValue = SignedValue XTerm XType | SignedUnary GroundParameter (XType -> ((,) XTerm XType)) | SignedUnsupported;
  -- A variable's type application and its result can be shared for each
  -- atomic argument in the primitive kind table. Wider arguments use the
  -- same construction with their original type.
  signedInstantiation name shape = let {
    instantiate ty = let {
      proof = XThen (XInner (XBottom ty)) XElim;
      result = case shape of { GroundBare -> ty; GroundWrapped wrapper -> XCon wrapper [ty] }
    } in (,) (XTypeApp (XVarTerm name) proof) result;
    atoms = Check.checkedLookup compareString (\tag _ -> instantiate (XCon tag [])) Data.primitiveKinds
  } in \actual -> case actual of {
    XCon tag [] -> fromMaybe (instantiate actual) (atoms tag);
    _ -> instantiate actual
  };
  signedBinding name ty = case groundImport name ty of {
    GroundUnaryImport _ _ _ input output -> SignedUnary input (signedInstantiation name output);
    _ -> if monomorphicTarget ty then SignedValue (XVarTerm name) ty else SignedUnsupported
  };
  -- A primitive with a closed monomorphic signature has the same typed
  -- occurrence in every scope. Preserve its ordinary admission and error.
  signedPrimitive p = do {
    ty <- Check.closedPrimitiveType p;
    ensure (monomorphicTarget ty) "nonmonomorphic primitive";
    Right (SignedValue (XPrimitive p []) ty)
  };
  signedPrimitives :: IntMap (Either String SignedValue);
  signedPrimitives = IM.fromList (map (\p -> (,) (Primitive.primitiveCode p) (signedPrimitive p)) Primitive.allPrimitives);
  signedInstanceTerm globals names expression = let {
    variable key = case key of { Just value -> Right value; Nothing -> Left "unknown signed application variable" };
    operand shape actual = case shape of {
      GroundBare -> Just actual;
      GroundWrapped wrapper -> case actual of {
        XCon name [ty] -> if eqString name wrapper then Just ty else Nothing;
        _ -> Nothing
      }
    };
    visit term = case term of {
      SApp f a -> do {
        function <- visit f;
        argument <- visit a;
        case argument of {
          SignedValue value ty -> case function of {
            SignedValue operator (XArrow _ out) -> Right (SignedValue (XApp operator value) out);
            SignedUnary input instantiate -> case operand input ty of {
              Just actual -> let { instanceTerm = instantiate actual } in
                Right (SignedValue (XApp (fst instanceTerm) value) (snd instanceTerm));
              Nothing -> Left "signed application operand requires inference"
            };
            _ -> Left "signed application requires a function"
          };
          _ -> Left "signed application operand requires a monotype"
        }
      };
      SGlobal i _ -> variable (M.lookup compareInt (V.toInt i) globals);
      SVar name -> if eqString name "$MLF.Stack.callStack" then Left "managed call stack requires evidence"
        else variable (M.lookup compareString name names);
      SPrimitive p -> IM.findWithDefault (signedPrimitive p) (Primitive.primitiveCode p) signedPrimitives;
      SIntLit n -> Right (SignedValue (XIntTerm n) (XCon "Int" []));
      SBoolLit b -> Right (SignedValue (XBoolTerm b) (XCon "Bool" []));
      SDoubleLit n -> Right (SignedValue (XDoubleTerm n) (XCon "Double" []));
      SStringLit s -> Right (SignedValue (XStringTerm s) (XCon "String" []));
      SCallSite _ _ body -> visit body;
      SSourceDefinition body -> visit body;
      _ -> Left "ordinary elaboration required"
    }
  } in do {
    value <- visit expression;
    case value of { SignedValue term _ -> Right term; _ -> Left "signed application result requires a monotype" }
  };
  -- A signed monotype can specialize imported schemes without building a
  -- generalization graph. Every temporary variable, including every imported
  -- type argument, must become closed. Bounded forall arguments carry checked
  -- instance computations; this never replaces an unsigned export's MLF scheme
  -- with a rank-1 approximation. Ambiguity and unsupported forms fall back.
  data GroundType = GroundVar Int | GroundArrow GroundType GroundType |
    GroundCon String ([] GroundType) | GroundApply GroundType GroundType;
  data GroundState = GroundState Int (IntMap GroundType) (IntMap Int) Int;
  -- A unary scheme can pass its fresh type argument straight from an operand
  -- to the result. The wrapper, if present, must contain exactly that variable.
  data GroundParameter = GroundBare | GroundWrapped String;
  data GroundEvidence = GroundEvidence (GroundState -> [] ((,) XTyVar GroundType) -> Either String XComputation);
  data GroundBinding = GroundLocal XName GroundType | GroundImport XName XType |
    GroundQuantifiedImport XName XType GroundEvidence |
    GroundUnaryImport XName XType XTyVar GroundParameter GroundParameter;
  groundImport name scheme = let {
    general = GroundImport name scheme;
    shape variable ty = case ty of {
      XVar other -> if T.tyVarId variable == T.tyVarId other then Just GroundBare else Nothing;
      XCon wrapper [XVar other] -> if T.tyVarId variable == T.tyVarId other then Just (GroundWrapped wrapper) else Nothing;
      _ -> Nothing
    }
  } in case scheme of {
    XForall variable XBot (XArrow domain result) -> case (,) (shape variable domain) (shape variable result) of {
      (,) (Just input) (Just output) -> GroundUnaryImport name scheme variable input output;
      _ -> general
    };
    XForall _ XBot (XForall _ _ _) -> GroundQuantifiedImport name scheme (prepareGroundEvidence scheme);
    _ -> general
  };
  groundParameter shape value = case shape of {
    GroundBare -> value;
    GroundWrapped wrapper -> GroundCon wrapper [value]
  };
  groundOperand state shape actual = case shape of {
    GroundBare -> Just actual;
    GroundWrapped wrapper -> case groundDeref state actual of {
      GroundCon name [value] -> if eqString wrapper name then Just value else Nothing;
      _ -> Nothing
    }
  };
  data GroundTerm = GroundLiteral XTerm | GroundVariable XName XType ([] ((,) XTyVar GroundType)) |
    GroundQuantifiedUse XName GroundEvidence ([] ((,) XTyVar GroundType)) |
    GroundPrimitive Primitive ([] GroundType) | GroundLambda XName GroundType GroundTerm |
    GroundApplication GroundTerm GroundTerm;
  groundFresh (GroundState next known ranks serial) =
    (,) (GroundVar next) (GroundState (advanceIdentity next 1) known ranks serial);
  groundDeref state ty = case (,) state ty of {
    (,) (GroundState _ known _ _) (GroundVar i) -> case IM.lookup i known of {
      Nothing -> ty; Just value -> groundDeref state value
    };
    _ -> ty
  };
  groundOccurs state identity ty = case groundDeref state ty of {
    GroundVar i -> i == identity;
    GroundArrow a b -> groundOccurs state identity a || groundOccurs state identity b;
    GroundCon _ args -> any (groundOccurs state identity) args;
    GroundApply f a -> groundOccurs state identity f || groundOccurs state identity a
  };
  groundUnify :: GroundState -> GroundType -> GroundType -> Either String GroundState;
  groundUnify state left right = case (,) (groundDeref state left) (groundDeref state right) of {
    (,) (GroundVar i) (GroundVar j) -> Right (if i == j then state else groundUnion state i j);
    (,) (GroundVar i) value -> groundBind state i value;
    (,) value (GroundVar i) -> groundBind state i value;
    (,) (GroundArrow a b) (GroundArrow c d) -> do { next <- groundUnify state a c; groundUnify next b d };
    (,) (GroundCon a xs) (GroundCon b ys) -> do {
      ensure (eqString a b && length xs == length ys) "ground constructor mismatch";
      foldM (\next ((,) x y) -> groundUnify next x y) state (zip xs ys)
    };
    (,) (GroundApply f a) (GroundApply g b) -> do { next <- groundUnify state f g; groundUnify next a b };
    _ -> Left "ground type mismatch"
  };
  -- Both arguments are unbound roots after dereferencing. Rank bounds alias
  -- depth even when a nested polymorphic call spine joins them in reverse order.
  groundUnion (GroundState next known ranks serial) left right = let {
    a = IM.findWithDefault 0 left ranks;
    b = IM.findWithDefault 0 right ranks
  } in if a < b then GroundState next (IM.insert left (GroundVar right) known) ranks serial
    else GroundState next (IM.insert right (GroundVar left) known)
      (if a == b then IM.insert left (a + 1) ranks else ranks) serial;
  groundBind state identity value = case state of { GroundState next known ranks serial -> do {
    ensure (not (groundOccurs state identity value)) "recursive ground type";
    Right (GroundState next (IM.insert identity value known) ranks serial)
  } };
  groundType :: Map XTyVar GroundType -> XType -> Either String GroundType;
  groundType variables ty = case ty of {
    XVar v -> case M.lookup T.compareTyVar v variables of {
      Just value -> Right value; Nothing -> Left "free ground type variable"
    };
    XArrow a b -> do { x <- groundType variables a; y <- groundType variables b; Right (GroundArrow x y) };
    XCon n args -> mapEither (GroundCon n) (traverseEither (groundType variables) args);
    XApply f a -> do { x <- groundType variables f; y <- groundType variables a; Right (GroundApply x y) };
    _ -> Left "ground specialization needs a monotype body"
  };
  groundClosed :: GroundState -> GroundType -> Either String XType;
  groundClosed state ty = case groundDeref state ty of {
    GroundVar _ -> Left "ground specialization is ambiguous";
    GroundArrow a b -> do { x <- groundClosed state a; y <- groundClosed state b; Right (XArrow x y) };
    GroundCon n args -> mapEither (XCon n) (traverseEither (groundClosed state) args);
    GroundApply f a -> do { x <- groundClosed state f; y <- groundClosed state a; Right (XApply x y) }
  };
  groundScheme variables reversed state ty = case ty of {
    XForall v bound body -> let { fresh = groundFresh state; value = fst fresh; next = snd fresh } in do {
      following <- groundBound variables next bound value;
      groundScheme (M.insert T.compareTyVar v value variables) ((:) ((,) v value) reversed) following body
    };
    _ -> mapEither (\body -> (,,) body (reverse reversed) state) (groundType variables ty)
  };
  -- A non-bottom bound can connect earlier quantifiers to a later argument.
  -- Project one possible closed instance with fresh variables now; sealing
  -- reconstructs the bound's actual instance proof after all uses agree.
  groundBound variables state bound expected = case bound of {
    XBot -> Right state;
    XBotKind _ -> Right state;
    _ -> do {
      (,,) actual _ next <- groundScheme variables [] state bound;
      groundUnify next expected actual
    }
  };
  groundEvidence :: GroundState -> XType -> [] ((,) XTyVar GroundType) -> Either String XComputation;
  groundEvidence state source arguments = case (,) source arguments of {
    (,) (XForall v bound body) ((:) ((,) expected variable) rest) -> do {
      ensure (T.tyVarId v == T.tyVarId expected) "ground quantifier identity changed";
      argument <- groundClosed state variable;
      let { general = do {
        first <- groundClosedProof bound argument;
        later <- groundEvidence state (T.substitute v argument body) rest;
        Right (X.compose (X.compose (case first of { XRefl -> XRefl; _ -> XInner first }) XElim) later)
      } };
      -- A closed ground type cannot be bottom. With a single bottom-bounded
      -- quantifier and an arrow body, substitution leaves the outer arrow
      -- intact and the remaining evidence is reflexive.
      case bound of {
        XBot -> case body of {
          XArrow _ _ -> case rest of {
            [] -> Right (XThen (XInner (XBottom argument)) XElim);
            _ -> general
          };
          _ -> general
        };
        _ -> general
      }
    };
    (,) _ [] -> Right XRefl;
    _ -> Left "ground quantifier inventory changed"
  };
  -- The prefix of an imported scheme belongs to the binding. A closed
  -- argument cannot capture or rename any of its later binders. Substitute
  -- a closed non-bottom constructor once per prefix to expose the same
  -- quantifiers and bottom bounds, including the original free-variable
  -- checks. A dependent bound still needs the actual substitutions.
  prepareGroundEvidence :: XType -> GroundEvidence;
  prepareGroundEvidence scheme = let {
    specialize argument source = case source of {
      XForall v _ body -> T.substitute v argument body;
      _ -> source
    };
    prepare shape = case shape of {
      XForall v bound body -> let {
        next = prepare (T.substitute v (XCon "" []) body)
      } in \source state arguments -> case arguments of {
        [] -> Right XRefl;
        (:) ((,) expected variable) rest -> do {
          ensure (T.tyVarId v == T.tyVarId expected) "ground quantifier identity changed";
          argument <- groundClosed state variable;
          let { ordinary = groundEvidence state source arguments;
                first = XThen (XInner (XBottom argument)) XElim };
          case bound of {
            XBot -> case body of {
              XForall _ _ _ -> mapEither (X.compose first) (next (specialize argument source) state rest);
              XArrow _ _ -> case rest of { [] -> Right first; _ -> ordinary };
              _ -> ordinary
            };
            _ -> ordinary
          }
        }
      };
      _ -> \source state arguments -> groundEvidence state source arguments
    }
  } in GroundEvidence (prepare scheme scheme);
  groundClosedProof :: XType -> XType -> Either String XComputation;
  groundClosedProof source target = if T.alphaEq source target then Right XRefl else case source of {
    XBot -> Right (XBottom target);
    XBotKind _ -> Right (XBottom target);
    _ -> do {
      (,,) proposed arguments initial <- groundScheme M.empty [] (GroundState 0 IM.empty IM.empty 0) source;
      wanted <- groundType M.empty target;
      solved <- groundUnify initial proposed wanted;
      groundEvidence solved source arguments
    }
  };
  groundSeal state term = case term of {
    GroundLiteral value -> Right value;
    GroundVariable name scheme arguments -> mapEither (X.instantiate (XVarTerm name))
      (groundEvidence state scheme arguments);
    GroundQuantifiedUse name (GroundEvidence evidence) arguments -> mapEither (X.instantiate (XVarTerm name)) (evidence state arguments);
    GroundPrimitive primitive arguments -> mapEither (XPrimitive primitive) (traverseEither (groundClosed state) arguments);
    GroundLambda name ty body -> do { actual <- groundClosed state ty; value <- groundSeal state body; Right (XAbs name actual value) };
    GroundApplication f a -> do { x <- groundSeal state f; y <- groundSeal state a; Right (XApp x y) }
  };
  groundUse state binding = case binding of {
    Nothing -> Left "unknown ground variable";
    Just (GroundLocal name ty) -> Right ((,,) (GroundLiteral (XVarTerm name)) ty state);
    Just (GroundUnaryImport name ty _ _ _) -> groundUse state (Just (GroundImport name ty));
    Just (GroundQuantifiedImport name ty evidence) -> do {
      (,,) actual arguments next <- groundScheme M.empty [] state ty;
      Right ((,,) (GroundQuantifiedUse name evidence arguments) actual next)
    };
    Just (GroundImport name ty) -> do {
      (,,) actual arguments next <- groundScheme M.empty [] state ty;
      Right ((,,) (GroundVariable name ty arguments) actual next)
    }
  };
  -- A closed primitive does not consume the group's type-variable supply.
  -- Its signature and its sealed term depend only on the primitive ABI.
  closedGroundPrimitive primitive = do {
    ty <- Check.closedPrimitiveType primitive;
    actual <- groundType M.empty ty;
    Right ((,) (GroundLiteral (XPrimitive primitive [])) actual)
  };
  closedGroundPrimitives :: IntMap (Either String ((,) GroundTerm GroundType));
  closedGroundPrimitives = IM.fromList (map (\p -> (,) (Primitive.primitiveCode p)
    (closedGroundPrimitive p)) Primitive.allPrimitives);
  groundPrimitive state primitive = case Primitive.primitiveSignature primitive of {
    (,) [] _ -> mapEither (\((,) term ty) -> (,,) term ty state)
      (IM.findWithDefault (closedGroundPrimitive primitive) (Primitive.primitiveCode primitive) closedGroundPrimitives);
    (,) variables signature -> do {
    ensure (all (\((,) _ kind) -> case kind of { Star -> True; _ -> False }) variables)
      "higher-kinded primitive requires general inference";
    let { entries = zip (map fst variables) (map XTyVar (range 0 (length variables - 1))) };
    ty <- T.instantiateField (M.fromList compareString (map (\((,) n v) -> (,) n (XVar v)) entries)) signature;
    (,,) known reversed next <- foldM (\((,,) known reversed current) ((,) _ v) -> let {
      fresh = groundFresh current; hole = fst fresh; following = snd fresh
    } in Right ((,,) (M.insert T.compareTyVar v hole known) ((:) hole reversed) following))
      ((,,) M.empty [] state) entries;
    actual <- groundType known ty;
    Right ((,,) (GroundPrimitive primitive (reverse reversed)) actual next)
  } };
  groundInfer globals names state expression = case expression of {
    SVar name -> groundUse state (M.lookup compareString name names);
    SGlobal identity _ -> groundUse state (M.lookup compareInt (V.toInt identity) globals);
    SDeclScope [identity] (SLam name annotation body) -> groundLambda globals names state (Just identity) name annotation body;
    SLam name annotation body -> groundLambda globals names state Nothing name annotation body;
    SApp f a -> let {
      ordinary operator = do {
        (,,) function functionType next <- operator;
        (,,) argument argumentType following <- groundInfer globals names next a;
        let {
          allocated = groundFresh following;
          fresh = snd allocated;
          applied = GroundApplication function argument
        };
        case groundDeref following functionType of {
          GroundArrow domain result -> do {
            -- The result already belongs to this type. Preserve the identity
            -- supply but avoid storing an alias for a new result variable.
            solved <- groundUnify fresh domain argumentType;
            Right ((,,) applied result solved)
          };
          unknown -> do {
            let { result = fst allocated };
            solved <- groundUnify fresh unknown (GroundArrow argumentType result);
            Right ((,,) applied result solved)
          }
        }
      };
      bound binding = case binding of {
        Just (GroundUnaryImport name scheme variable input output) -> let {
          allocated = groundFresh state; hole = fst allocated; next = snd allocated
        } in do {
          (,,) argument actual following <- groundInfer globals names next a;
          let {
            fresh = snd (groundFresh following);
            applied value = GroundApplication (GroundVariable name scheme [(,) variable value]) argument
          };
          case groundOperand following input actual of {
            -- Only this use owns the fresh parameter. Forwarding the actual
            -- type also preserves constraints imposed later on that operand.
            Just value -> Right ((,,) (applied value) (groundParameter output value) fresh);
            Nothing -> do {
              solved <- groundUnify fresh (groundParameter input hole) actual;
              Right ((,,) (applied hole) (groundParameter output hole) solved)
            }
          }
        };
        _ -> ordinary (groundUse state binding)
      }
    } in case f of {
      SGlobal i _ -> bound (M.lookup compareInt (V.toInt i) globals);
      SVar name -> bound (M.lookup compareString name names);
      _ -> ordinary (groundInfer globals names state f)
    };
    SPrimitive primitive -> groundPrimitive state primitive;
    SIntLit n -> Right ((,,) (GroundLiteral (XIntTerm n)) (GroundCon "Int" []) state);
    SDoubleLit n -> Right ((,,) (GroundLiteral (XDoubleTerm n)) (GroundCon "Double" []) state);
    SBoolLit b -> Right ((,,) (GroundLiteral (XBoolTerm b)) (GroundCon "Bool" []) state);
    SStringLit s -> Right ((,,) (GroundLiteral (XStringTerm s)) (GroundCon "String" []) state);
    SSignature body annotation -> groundAnnotated globals names state body annotation;
    SAnn body annotation -> groundAnnotated globals names state body annotation;
    SChecked ty body -> groundAnnotated globals names state body (SAnnotation [] ty);
    _ -> Left "expression requires general inference"
  };
  groundAnnotated globals names state body annotation = do {
    expected <- monomorphicAnnotation annotation >>= groundType M.empty;
    (,,) term actual next <- groundInfer globals names state body;
    solved <- groundUnify next actual expected;
    Right ((,,) term expected solved)
  };
  groundLambda globals names state identity name annotation body = do {
    (,) ty next <- case annotation of {
      Nothing -> Right (groundFresh state);
      Just written -> mapEither (\ty -> (,) ty state) (monomorphicAnnotation written >>= groundType M.empty)
    };
    case next of { GroundState count known ranks serial -> do {
      let { binder = XName serial name; binding = GroundLocal binder ty };
      scope <- case identity of {
        Nothing -> Right globals;
        Just i -> do {
          ensure (not (M.member compareInt (V.toInt i) globals)) "ground parameter identity already bound";
          Right (M.insert compareInt (V.toInt i) binding globals)
        }
      };
      (,,) value result final <- groundInfer scope (M.insert compareString name binding names)
        (GroundState count known ranks (advanceIdentity serial 1)) body;
      Right ((,,) (GroundLambda binder ty value) (GroundArrow ty result) final)
    } }
  };
  groundIndexed parameters members lowered = case (,) members lowered of {
    (,) [(,) identity ((,,) name (Just annotation) _)] ((,) (SProgram declarations expression) _) -> do {
      expected <- monomorphicAnnotation annotation;
      let { entries = zip parameters (range 0 (length parameters - 1));
        binding = \((,,) _ hint ty) serial -> groundImport (XName serial hint) ty;
        globals = M.fromList compareInt (map (\((,) row@((,,) i _ _) serial) -> (,) (V.toInt i) (binding row serial)) entries);
        names = M.fromList compareString (map (\((,) row@((,,) _ n _) serial) -> (,) n (binding row serial)) entries);
        ps = map (\((,) ((,,) _ hint ty) serial) -> (,) (XName serial hint) ty) entries;
        core = if null parameters then expression else case expression of {
          SDeclScope _ (SLetRec _ body) -> body; _ -> expression
        } };
      rhs <- case core of {
        SDeclScope [i] (SLet n value (SConstructor "()")) -> do {
          ensure (V.toInt i == V.toInt identity && eqString n name) "ground group identity";
          Right value
        };
        _ -> Left "not a single signed nonrecursive monotype"
      };
      (,,) template actual initial <- groundInfer globals names (GroundState 0 IM.empty IM.empty (length parameters + 1)) rhs;
      wanted <- groundType M.empty expected;
      solved <- groundUnify initial actual wanted;
      implementation <- groundSeal solved template;
      env <- Open.environment declarations;
      fragment <- Open.check env ps (XLet (XName (length parameters) name) implementation (XConstructor "()" []));
      ensure (case Open.bindings fragment of {
        [(,) actual ty] -> eqString (X.nameHint actual) name && T.alphaEq expected ty; _ -> False
      }) "ground fragment export mismatch";
      Right fragment
    };
    _ -> Left "ground specialization requires a signed monotype"
  };
  -- Each member of a fully signed recursive group can be checked against the
  -- common declared environment. Its local unification variables cannot occur
  -- in a peer's closed signature. Only the term identity supply crosses RHSs.
  data GroundMember = GroundMember Int XName XType GroundType SExpr;
  groundRecursiveIndexed parameters members lowered = case lowered of {
    (,) (SProgram declarations expression) _ -> groundRecursiveGroup parameters members declarations expression;
    _ -> Left "ground recursive group requires lowered declarations"
  };
  groundRecursiveGroup parameters members declarations expression = do {
    let { sorted = sortBy (\((,,) _ n _) ((,,) _ m _) -> compareString n m) parameters;
      imported = mapIndexed (\serial ((,,) i name ty) -> (,,) (V.toInt i) (XName serial name) ty) sorted;
      count = length imported;
      declared = M.fromList compareInt (map (\((,) i value) -> (,) (V.toInt i) value) members) };
    core <- case (,) sorted expression of {
      (,) [] _ -> Right expression;
      (,) _ (SDeclScope ids (SLetRec stubs body)) -> do {
        ensure (eqList eqInt (map V.toInt ids) (map (\((,,) id _ _) -> id) imported) &&
          eqList eqString (map (\((,,) n _ _) -> n) stubs) (map (\((,,) _ n _) -> X.nameHint n) imported))
          "ground recursive import scope";
        Right body
      };
      _ -> Left "ground recursive import boundary"
    };
    rows <- case core of {
      SDeclScope ids (SLetRec definitions (SConstructor "()")) -> do {
        ensure (not (null definitions) && length ids == length definitions && length ids == length members &&
          length members == M.size declared) "ground recursive declaration inventory";
        traverseEither (groundMember declared count) (mapIndexed (,) (zip ids definitions))
      };
      _ -> Left "ground specialization requires a recursive group"
    };
    let { bindings = append (map (\((,,) i n ty) -> (,,) i n (groundImport n ty)) imported)
            (map (\(GroundMember i n _ ty _) -> (,,) i n (GroundLocal n ty)) rows);
      globals = M.fromList compareInt (map (\((,,) i _ value) -> (,) i value) bindings);
      names = M.fromList compareString (map (\((,,) _ n value) -> (,) (X.nameHint n) value) bindings);
      ps = map (\((,,) _ n ty) -> (,) n ty) imported;
      memberTypes = map (\(GroundMember _ n ty _ _) -> (,) n ty) rows };
    ensure (M.size globals == length bindings && M.size names == length bindings) "duplicate ground recursive binding";
    (,) reversed _ <- foldM (groundRecursiveBody globals names) ((,) [] (advanceIdentity count (length rows))) rows;
    env <- Open.environment declarations;
    fragment <- Open.check env ps (XLetRec (reverse reversed) (XConstructor "()" []));
    ensure (eqList (\((,) n ty) ((,) m other) -> X.equalName n m && T.alphaEq ty other)
      memberTypes (Open.bindings fragment)) "ground recursive export mismatch";
    Right fragment
  };
  groundMember declared count ((,) ordinal ((,) i ((,,) name mode rhs))) = case (,) mode (M.lookup compareInt (V.toInt i) declared) of {
    (,) (CheckRecursive annotation) (Just ((,,) hint (Just declaredType) _)) -> do {
      expected <- monomorphicAnnotation declaredType;
      actual <- monomorphicAnnotation annotation;
      ensure (eqString name hint && T.alphaEq expected actual) "ground recursive signature mismatch";
      ty <- groundType M.empty expected;
      Right (GroundMember (V.toInt i) (XName (advanceIdentity count ordinal) name) expected ty rhs)
    };
    _ -> Left "ground recursive member requires a closed monotype"
  };
  groundRecursiveBody globals names ((,) reversed serial) (GroundMember _ binder expected wanted rhs) = do {
    (,,) term actual initial <- groundInfer globals names (GroundState 0 IM.empty IM.empty serial) rhs;
    solved <- groundUnify initial actual wanted;
    sealed <- groundSeal solved term;
    case solved of { GroundState _ _ _ next -> Right ((,) ((:) ((,,) binder expected sealed) reversed) next) }
  };
  -- Closed nonrecursive monotypes need no generalization. This deliberately
  -- partial elaborator accepts only exact monomorphic uses and
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
    (,) [(,) identity ((,,) name annotation _)] ((,) (SProgram declarations expression) _) -> do {
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
      expected <- case annotation of {
        Just written -> monomorphicAnnotation written;
        Nothing -> mapEither fst (monoSynthesize
          (M.map (\binding -> MonoType (snd binding)) globals)
          (M.map (\binding -> MonoType (snd binding)) names) (MonoState 0 M.empty) rhs)
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
    _ -> Left "not a single nonrecursive monotype"
  };
  -- A small synthesis pass discovers only fully determined monotypes. Holes
  -- are lambda parameters, filled solely by a known closed argument type.
  -- There is no defaulting, polymorphic instantiation or local generalization;
  -- an unconstrained parameter or unknown callee falls back to the solver.
  -- The resulting type is only a proposal for the ordinary monotype checker
  -- above; no temporary hole can enter an xMLF term or checked fragment.
  data MonoBinding = MonoType XType | MonoParameter Int;
  data MonoState = MonoState Int (Map Int XType);
  monoResolve :: MonoState -> Maybe MonoBinding -> Either String XType;
  monoResolve state binding = case binding of {
    Nothing -> Left "unknown monomorphic variable";
    Just (MonoType ty) -> Right ty;
    Just (MonoParameter i) -> case state of { MonoState _ known ->
      case M.lookup compareInt i known of {
        Nothing -> Left "monomorphic parameter is not determined";
        Just ty -> Right ty
      }
    }
  };
  monoDemand :: MonoState -> XType -> Maybe MonoBinding -> Either String MonoState;
  monoDemand state expected binding = case (,) state binding of {
    (,) (MonoState next known) (Just (MonoParameter i)) -> case M.lookup compareInt i known of {
      Nothing -> do {
        ensure (monomorphicTarget expected) "monomorphic demand is not closed";
        Right (MonoState next (M.insert compareInt i expected known))
      };
      Just ty -> do { ensure (T.alphaEq ty expected) "conflicting monomorphic parameter uses"; Right state }
    };
    _ -> do { ty <- monoResolve state binding; ensure (T.alphaEq ty expected) "monomorphic use mismatch"; Right state }
  };
  monoSynthesize :: Map Int MonoBinding -> Map String MonoBinding -> MonoState -> SExpr ->
    Either String ((,) XType MonoState);
  monoSynthesize globals names state expression = case expression of {
    SDeclScope [identity] (SLam name annotation body) -> monoLambda globals names state (Just identity) name annotation body;
    SLam name annotation body -> monoLambda globals names state Nothing name annotation body;
    SVar name -> mapEither (\ty -> (,) ty state) (monoResolve state (M.lookup compareString name names));
    SGlobal identity _ -> mapEither (\ty -> (,) ty state) (monoResolve state (M.lookup compareInt (V.toInt identity) globals));
    SApp function argument -> do {
      (,) functionType next <- monoSynthesize globals names state function;
      case functionType of {
        XArrow domain result -> mapEither ((,) result) (monoCheck globals names next domain argument);
        _ -> Left "monomorphic application requires known arrow"
      }
    };
    SSignature body annotation -> monoAnnotated globals names state body annotation;
    SAnn body annotation -> monoAnnotated globals names state body annotation;
    SChecked ty body -> monoAnnotated globals names state body (SAnnotation [] ty);
    -- The existing exact inference cases cover literals and monomorphic
    -- primitives. Empty environments cannot synthesize any additional binding.
    _ -> mapEither (\((,,) _ ty _) -> (,) ty state) (monomorphicInfer M.empty M.empty 0 expression)
  };
  monoCheck globals names state expected expression = case expression of {
    SVar name -> monoDemand state expected (M.lookup compareString name names);
    SGlobal identity _ -> monoDemand state expected (M.lookup compareInt (V.toInt identity) globals);
    _ -> do {
      (,) actual next <- monoSynthesize globals names state expression;
      ensure (T.alphaEq actual expected) "monomorphic argument mismatch";
      Right next
    }
  };
  monoAnnotated globals names state body annotation = do {
    expected <- monomorphicAnnotation annotation;
    next <- monoCheck globals names state expected body;
    Right ((,) expected next)
  };
  monoLambda globals names state identity name annotation body = case state of {
    MonoState serial known -> do {
      binding <- case annotation of {
        Just written -> mapEither MonoType (monomorphicAnnotation written);
        Nothing -> Right (MonoParameter serial)
      };
      scope <- case identity of {
        Nothing -> Right globals;
        Just i -> do {
          ensure (not (M.member compareInt (V.toInt i) globals)) "monomorphic parameter identity already bound";
          Right (M.insert compareInt (V.toInt i) binding globals)
        }
      };
      (,) result next <- monoSynthesize scope (M.insert compareString name binding names)
        (MonoState (advanceIdentity serial 1) known) body;
      argument <- monoResolve next (Just binding);
      Right ((,) (XArrow argument result) next)
    }
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
