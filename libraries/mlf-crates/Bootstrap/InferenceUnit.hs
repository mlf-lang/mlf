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
    LoweredDeclarations (List DataDecl) (List (Triple String (Maybe SAnnotation) SExpr)) (Map String
                                                                                          String);
  loweredData (LoweredDeclarations ds _ _) = ds;
  loweredValues (LoweredDeclarations _ values _) = values;
  loweredNames (LoweredDeclarations _ _ names) = names;
  recursiveAnnotation :: RecursiveMode -> Maybe SAnnotation;
  recursiveAnnotation mode =
    case mode of {
      InferRecursive -> Nothing;
      CheckRecursive annotation -> Just annotation
    };
  extractLoweredDeclarations :: SExpr ->
                                Either String (List (Triple String (Maybe SAnnotation) SExpr));
  extractLoweredDeclarations expression = extractDeclarations expression Nil;
  extractDeclarations :: SExpr ->
                         List (Triple String (Maybe SAnnotation) SExpr) ->
                         Either String (List (Triple String (Maybe SAnnotation) SExpr));
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
              SChecked ty _ -> Just (SAnnotation Nil ty);
              SAnn _ a -> Just a;
              _ -> Nothing
            }
        } in
        extractDeclarations body (Cons (Triple n annotation rhs) reversed);
      SLetRec matchValueShared5 matchValueShared6 ->
        let {
          definitions = matchValueShared5
        } in
        let {
          body = matchValueShared6
        } in
        extractDeclarations body
          (foldlStrict (\acc (Triple n mode rhs) -> Cons (Triple n (recursiveAnnotation mode) rhs) acc) reversed
             definitions);
      SConstructor matchValueShared7 ->
        if MLF.Primitive.eqString matchValueShared7 "Unit"
        then Right (reverse reversed)
        else Left "lowered crate declarations must end in Unit";
      _ -> Left "lowered crate declarations must end in Unit"
    };
  lowerDeclarations :: List DataDecl ->
                       List SClassDecl ->
                       List (Pair String SInstanceDecl) ->
                       Map String IntSet ->
                       List IntSet ->
                       List (Triple String (Maybe SAnnotation) SExpr) ->
                       Either String LoweredDeclarations;
  lowerDeclarations datatypes classes instances valueScopes instanceScopes members =
    lowerDeclarationsWithImports M.empty datatypes classes instances valueScopes instanceScopes
      members;
  lowerDeclarationsWithImports :: Map String SType ->
                                  List DataDecl ->
                                  List SClassDecl ->
                                  List (Pair String SInstanceDecl) ->
                                  Map String IntSet ->
                                  List IntSet ->
                                  List (Triple String (Maybe SAnnotation) SExpr) ->
                                  Either String LoweredDeclarations;
  -- Helper closures retain the existing dictionary translation of unsigned
  -- and qualified helpers used inside instance methods. Their local lets keep
  -- the helper's defining-module instance scope through valueScopes.
  lowerDeclarationsWithImports externals datatypes classes instances valueScopes instanceScopes members =
    do {
      closedInstances <-
        traverseEither (\(Pair n inst) -> mapEither (Pair n) (Separate.closeInstance members inst))
          instances;
      body <- Surface.bindValues members (SConstructor "Unit");
      boundValueShared8 <-
        Classes.lowerSeparateClassesWithScopes externals (map fst closedInstances) valueScopes
          instanceScopes
          (SClassProgram datatypes classes (map snd closedInstances) body);
      case boundValueShared8 of {
        Pair program names ->
          do {
            case program of {
              SProgram ds expression ->
                do {
                  declarations <- extractLoweredDeclarations expression;
                  Right
                    (LoweredDeclarations ds
                       (filter (\(Triple n _ _) -> not (M.member compareString n externals))
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
  declarationClosure :: List (Triple String (Maybe SAnnotation) SExpr) ->
                        List String -> List (Triple String (Maybe SAnnotation) SExpr);
  declarationClosure declarations roots =
    let {
      values =
        M.fromList compareString
          (map
             (\v ->
                case v of {
                  Triple n _ _ -> Pair n v
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
  closeDependencies :: Map String (List String) -> Set String -> List String -> Set String;
  closeDependencies edges seen pending =
    case pending of {
      Nil -> seen;
      Cons n rest ->
        if S.member compareString n seen
        then closeDependencies edges seen rest
        else closeDependencies edges (S.insert compareString n seen)
               (append (M.findWithDefault compareString Nil n edges) rest)
    };
  mergeExternal :: Map String XType -> Pair String XType -> Either String (Map String XType);
  mergeExternal types entry =
    case entry of {
      Pair n ty ->
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
                         List Separate.UnitInterface ->
                         List DataDecl ->
                         List (Triple String (Maybe SAnnotation) SExpr) ->
                         Either String Separate.UnitObject;
  -- SCC fragments are parameters, not independently imported modules. The
  -- crate artifact validates the selected schemes and owns the crate DAG;
  -- module interface dependency hashes would cause transitive invalidation.
  compileLoweredGroup name dependencies datatypes members =
    do {
      ensure (not (null members)) "cannot infer an empty declaration group";
      externalTypes <- foldM mergeExternal M.empty (concatMap Separate.unitBindings dependencies);
      traverseEither
        (\(Triple n _ _) ->
           ensure (not (M.member compareString n externalTypes))
             ("inference group also imports its own binding: " ++ n))
        members;
      body <- Surface.bindValues members (SConstructor "Unit");
      let {
        externals = M.map (Separate.sourceScheme M.empty) externalTypes
      };
      lowered <- Classes.lowerSeparateClasses externals Nil (SProgram datatypes body);
      compiled <- mapLeft Compiler.prettyError (Compiler.finishCompilation lowered);
      let {
        coreAndData =
          case Compiler.compiledTerm compiled of {
            XWithData ds term -> Pair ds term;
            term -> Pair Nil term
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
        then Right (Pair Nil core)
        else case core of {
               XLetRec bindings rest ->
                 do {
                   ensure
                     (eqList eqString (map (\(Triple n _ _) -> X.nameHint n) bindings)
                        (M.keys externalTypes))
                     "inference parameter order mismatch";
                   traverseEither
                     (\(Triple n ty _) ->
                        ensure
                          (case M.lookup compareString (X.nameHint n) externalTypes of {
                             Nothing -> False;
                             Just expected -> T.alphaEq ty expected
                           })
                          ("dependency scheme changed during inference: " ++ X.nameHint n))
                     bindings;
                   Right (Pair (map (\(Triple n ty _) -> Pair n ty) bindings) rest)
                 };
               _ -> Left "inference did not retain external parameters"
             };
      case boundValueShared9 of {
        Pair parameters implementation ->
          do {
            dataEnv <- D.validateDeclarations declarations;
            bindings <-
              Separate.collectBindings dataEnv (XEnv M.empty (M.fromList X.compareName parameters))
                implementation;
            ensure
              (eqList eqString (sortBy compareString (map (\(Pair n _) -> X.nameHint n) bindings))
                 (sortBy compareString (map (\(Triple n _ _) -> n) members)))
              "inference fragment changed declaration ownership";
            let {
              payload =
                XWithData declarations
                  (foldr (\(Pair n ty) term -> XAbs n ty term) implementation parameters)
            };
            checked <- Checked.check payload;
            let {
              iface =
                Separate.UnitInterface name Nil Nil declarations Nil Nil
                  (Separate.sortBindings
                     (map (\(Pair n ty) -> Pair (X.nameHint n) (Separate.normalType ty)) bindings))
                  (Separate.fingerprint (Pretty.prettyTerm payload))
            };
            Right (Separate.CheckedUnitObject iface checked)
          }
      }
    }
}
