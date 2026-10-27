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
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;
  -- Class translation is a crate query, before the value dependency graph is
  -- built. Its generated selectors/dictionaries become ordinary signed graph
  -- vertices. Inference queries consume this lowered representation directly.
  data LoweredDeclarations =
    LoweredDeclarations ([] DataDecl) ([] ((,,) String (Maybe SAnnotation) SExpr)) (Map String
                                                                                          String);
  loweredData (LoweredDeclarations ds _ _) = ds;
  loweredValues (LoweredDeclarations _ values _) = values;
  loweredNames (LoweredDeclarations _ _ names) = names;
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
          annotation =
            case rhs of {
              SChecked ty _ -> Just (SAnnotation [] ty);
              SAnn _ a -> Just a;
              _ -> Nothing
            }
        } in
        extractDeclarations body ((:) ((,,) n annotation rhs) reversed);
      SLetRec matchValueShared5 matchValueShared6 ->
        let {
          definitions = matchValueShared5
        } in
        let {
          body = matchValueShared6
        } in
        extractDeclarations body
          (foldlStrict (\acc ((,,) n a rhs) -> (:) ((,,) n (Just a) rhs) acc) reversed
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
      boundValueShared8 <-
        Classes.lowerSeparateClassesWithScopes externals (map fst closedInstances) valueScopes
          instanceScopes
          (SClassProgram datatypes classes (map snd closedInstances) body);
      case boundValueShared8 of {
        (,) program names ->
          do {
            case program of {
              SProgram ds expression ->
                do {
                  declarations <- extractLoweredDeclarations expression;
                  Right
                    (LoweredDeclarations ds
                       (filter (\((,,) n _ _) -> not (M.member compareString n externals))
                          declarations)
                       names)
                };
              _ -> Left "class lowering did not produce core crate declarations"
            }
          }
      }
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
    do {
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
      case boundValueShared9 of {
        (,) parameters implementation ->
          do {
            dataEnv <- D.validateDeclarations declarations;
            bindings <-
              Separate.collectBindings dataEnv (XEnv M.empty (M.fromList X.compareName parameters))
                implementation;
            ensure
              (eqList eqString (sortBy compareString (map (\((,) n _) -> X.nameHint n) bindings))
                 (sortBy compareString (map (\((,,) n _ _) -> n) members)))
              "inference fragment changed declaration ownership";
            let {
              payload =
                XWithData declarations
                  (foldr (\((,) n ty) term -> XAbs n ty term) implementation parameters)
            };
            checked <- Checked.check payload;
            let {
              iface =
                Separate.UnitInterface name [] [] declarations [] []
                  (Separate.sortBindings
                     (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) bindings))
                  (Separate.fingerprint (Pretty.prettyTerm payload))
            };
            Right (Separate.CheckedUnitObject iface checked)
          }
      }
    }
}
