-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Data where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.Unicode as U;
  datatypeName :: DataDecl -> String;
  datatypeName (DataDecl n _ _) = n;
  datatypeName (DataDeclK n _ _) = n;
  datatypeBinders :: DataDecl -> [] ((,) String Kind);
  datatypeBinders (DataDecl _ ps _) = map (\p -> (,) p Star) ps;
  datatypeBinders (DataDeclK _ ps _) = ps;
  datatypeParameters d = map fst (datatypeBinders d);
  datatypeConstructors :: DataDecl -> [] ConstructorDecl;
  datatypeConstructors (DataDecl _ _ cs) = cs;
  datatypeConstructors (DataDeclK _ _ cs) = cs;
  constructorName (ConstructorDecl n _) = n;
  constructorFields (ConstructorDecl _ fs) = fs;
  -- Source graphs cannot represent unused quantifiers. Normalize only freshly
  -- declared source layouts, before they become checked nominal contracts.
  -- In particular, imported target layouts must never pass through this map.
  fieldUsesParameter :: String -> Field -> Bool;
  fieldUsesParameter name field =
    case field of {
      Parameter variable -> eqString name variable;
      Function a b -> fieldUsesParameter name a || fieldUsesParameter name b;
      Applied _ arguments -> any (fieldUsesParameter name) arguments;
      Application f a -> fieldUsesParameter name f || fieldUsesParameter name a;
      Quantified variable _ body ->
        not (eqString name variable) && fieldUsesParameter name body
    };
  canonicalSourceField :: Field -> Field;
  canonicalSourceField field =
    case field of {
      Parameter _ -> field;
      Function a b -> Function (canonicalSourceField a) (canonicalSourceField b);
      Applied name arguments -> Applied name (map canonicalSourceField arguments);
      Application f a -> Application (canonicalSourceField f) (canonicalSourceField a);
      Quantified variable kind body ->
        let { normalized = canonicalSourceField body } in
        if fieldUsesParameter variable normalized
        then Quantified variable kind normalized
        else normalized
    };
  canonicalSourceDeclaration :: DataDecl -> DataDecl;
  canonicalSourceDeclaration declaration =
    let {
      constructors = map (\(ConstructorDecl name fields) ->
        ConstructorDecl name (map canonicalSourceField fields)) (datatypeConstructors declaration)
    } in
    case declaration of {
      DataDecl name parameters _ -> DataDecl name parameters constructors;
      DataDeclK name parameters _ -> DataDeclK name parameters constructors
    };
  canonicalSourceDeclarations :: [] DataDecl -> [] DataDecl -> Either String ([] DataDecl);
  canonicalSourceDeclarations checkedContext declarations = do {
    -- Validate the original syntax: deleting an unused binder must not conceal
    -- an ill-kinded or ill-scoped field. The context participates in validation
    -- but is returned nowhere and remains byte-for-byte owned by its importer.
    validateDeclarations (append checkedContext declarations);
    Right (map canonicalSourceDeclaration declarations)
  };
  canonicalSourceProgram :: SProgram -> Either String SProgram;
  canonicalSourceProgram program =
    case program of {
      SProgram declarations body -> do {
        normalized <- canonicalSourceDeclarations [] declarations;
        Right (SProgram normalized body)
      };
      SClassProgram declarations classes instances body -> do {
        normalized <- canonicalSourceDeclarations [] declarations;
        Right (SClassProgram normalized classes instances body)
      }
    };
  scalarPrimitiveKinds :: Map String Kind;
  scalarPrimitiveKinds = M.insert compareString "Integer" Star (
    M.fromList compareString
      ((:) ((,) "AsyncScope" Star)
         ((:) ((,) "Completion" (KArrow Star Star))
            ((:) ((,) "AsyncSubscription" Star)
               ((:) ((,) "ST" (KArrow Star (KArrow Star Star)))
                  ((:) ((,) "STArray" (KArrow Star (KArrow Star Star)))
                     ((:) ((,) "Int" Star)
                        ((:) ((,) "Double" Star)
                           ((:) ((,) "Bool" Star)
                              ((:) ((,) "String" Star)
                                 ((:) ((,) "MLFLegacyUnit" Star)
                                    ((:) ((,) "IntArray" Star)
                                       ((:) ((,) "DoubleArray" Star)
                                          ((:) ((,) "ByteArray" Star)
                                             ((:) ((,) "IntTable" Star)
                                                ((:) ((,) "IO" (KArrow Star Star))
                                                   []))))))))))))))));
  -- Wired source identities are independent of Bootstrap.Types' temporary
  -- List/Pair/Unit implementation ADTs. Never normalize a user ADT to these.
  sourceUnitDeclaration :: DataDecl;
  sourceUnitDeclaration = DataDecl "()" [] ((:) (ConstructorDecl "()" []) []);
  sourceListDeclaration :: DataDecl;
  sourceListDeclaration =
    DataDecl "[]" ((:) "a" [])
      ((:) (ConstructorDecl "[]" [])
         ((:) (ConstructorDecl ":"
                  ((:) (Parameter "a")
                     ((:) (Applied "[]" ((:) (Parameter "a") [])) []))) []));
  sourceTupleDeclaration :: String -> [] String -> DataDecl;
  sourceTupleDeclaration name parameters =
    DataDecl name parameters
      ((:) (ConstructorDecl name (map Parameter parameters)) []);
  sourceTupleName :: Int -> String;
  sourceTupleName arity = "(" ++ (foldr (++) "" (replicate (arity - 1) ",") ++ ")");
  sourceTupleParameters :: Int -> [] String;
  sourceTupleParameters arity = map (\i -> "a" ++ showInt i) (range 1 arity);
  sourceBuiltinDeclarations :: [] DataDecl;
  sourceBuiltinDeclarations = (:) sourceUnitDeclaration ((:) sourceListDeclaration
    (map (\arity -> sourceTupleDeclaration (sourceTupleName arity) (sourceTupleParameters arity)) (range 2 64)));
  sourceBuiltinType :: String -> Bool;
  sourceBuiltinType name = any (\d -> eqString (datatypeName d) name) sourceBuiltinDeclarations;
  sourceBuiltinConstructor :: String -> Bool;
  sourceBuiltinConstructor name =
    any (\d -> any (\c -> eqString (constructorName c) name) (datatypeConstructors d))
      sourceBuiltinDeclarations;
  primitiveKinds :: Map String Kind;
  primitiveKinds =
    M.union compareString (M.fromList compareString
      ((:) ((,) "MLFCallStack" Star) ((:) ((,) "MLFStackFrame" Star)
        ((:) ((,) "MLFStackEvidence" Star) []))))
    (M.union compareString scalarPrimitiveKinds
      (M.fromList compareString
         ((:) ((,) "IOError" Star) ((:) ((,) "Char" Star)
            (map (\d -> (,) (datatypeName d)
                           (foldr (\_ k -> KArrow Star k) Star (datatypeParameters d)))
               sourceBuiltinDeclarations)))));
  unitDeclaration = DataDecl "MLFLegacyUnit" [] ((:) (ConstructorDecl "MLFLegacyUnit" []) []);
  stackFrameDeclaration :: DataDecl;
  stackFrameDeclaration = DataDecl "MLFStackFrame" []
    ((:) (ConstructorDecl "MLFStackFrame"
      (append (replicate 4 (Applied "String" [])) (replicate 4 (Applied "Int" [])))) []);
  stackEvidenceDeclaration :: DataDecl;
  stackEvidenceDeclaration = DataDecl "MLFStackEvidence" []
    ((:) (ConstructorDecl "MLFStackEvidence" ((:) (Applied "MLFCallStack" []) [])) []);
  builtinDeclarations :: [] DataDecl;
  builtinDeclarations = (:) unitDeclaration
    (append (take 5 sourceBuiltinDeclarations)
      ((:) stackFrameDeclaration ((:) stackEvidenceDeclaration (drop 5 sourceBuiltinDeclarations))));
  builtinDatatypes :: Map String DataDecl;
  builtinDatatypes =
    M.fromList compareString (map (\d -> (,) (datatypeName d) d) builtinDeclarations);
  builtinConstructors :: Map String ((,) DataDecl ConstructorDecl);
  builtinConstructors =
    M.fromList compareString
      (concatMap (\d -> map (\c -> (,) (constructorName c) ((,) d c))
                           (datatypeConstructors d)) builtinDeclarations);
  withKinds ks =
    DataEnv builtinDatatypes builtinConstructors
      (M.union compareString primitiveKinds (M.fromList compareString ks));
  emptyDataEnv = withKinds [];
  lookupDatatype :: DataEnv -> String -> Either String DataDecl;
  lookupDatatype (DataEnv ds _ _) n =
    case M.lookup compareString n ds of {
      Nothing -> Left ("unknown data type: " ++ n);
      Just d -> Right d
    };
  lookupConstructor :: DataEnv -> String -> Either String ((,) DataDecl ConstructorDecl);
  lookupConstructor (DataEnv _ cs _) n =
    case M.lookup compareString n cs of {
      Nothing -> Left ("unknown data constructor: " ++ n);
      Just c -> Right c
    };
  constructorKind :: DataEnv -> String -> Int -> Kind;
  constructorKind (DataEnv _ _ ks) n fallback =
    case M.lookup compareString n primitiveKinds of {
      Just k -> k;
      Nothing -> M.findWithDefault compareString (foldr KArrow Star (replicate fallback Star)) n ks
    };
  checkArity :: DataEnv -> String -> Int -> Either String ();
  checkArity (DataEnv ds _ _) n actual =
    let {
      expected =
        case M.lookup compareString n primitiveKinds of {
          Just k -> Just (K.kindArity k);
          Nothing -> mapOptional (\d -> length (datatypeParameters d)) (M.lookup compareString n ds)
        }
    } in
    case expected of {
      Nothing -> Right ();
      Just arity ->
        if (actual == arity)
        then Right ()
        else Left
               ("invalid type constructor arity: " ++
                (n ++ (" expects " ++ (showInt arity ++ (", got " ++ showInt actual)))))
    };
  identifierTail :: String -> Int -> Bool;
  identifierTail name i =
    if (i >= stringLength name)
    then True
    else let {
           c = stringCodeAt name i
         } in
         ((U.isAlphaNum c || ((c == 95) || (c == 39))) && identifierTail name (i + 1));
  identifier first name =
    ((stringLength name > 0) && (first (stringCodeAt name 0) && identifierTail name 1));
  upper what name =
    if identifier U.isUpper name
    then Right ()
    else Left ("invalid " ++ (what ++ (" name: " ++ name)));
  keywords :: [] String;
  keywords =
    (:) "data"
      ((:) "class"
         ((:) "instance"
            ((:) "where"
               ((:) "case"
                  ((:) "of"
                     ((:) "do"
                        ((:) "let"
                           ((:) "in"
                              ((:) "forall"
                                 ((:) "exists"
                                    ((:) "true" ((:) "false" ((:) "bot" [])))))))))))));
  memberString :: String -> [] String -> Bool;
  memberString name names = any (eqString name) names;
  distinct :: String -> [] String -> Either String ();
  distinct what xs =
    -- Complete the spine before demanding names. Int64 worker arguments can
    -- otherwise evaluate the Set side before the ordered comparison is entered.
    let { count = length xs } in
    seq count (if (count == Set.size (Set.fromList compareString xs)) then Right () else Left ("duplicate " ++ what));
  fieldKind :: [] DataDecl -> DataEnv -> Map String Kind -> Field -> Either String Kind;
  fieldKind declarations env ps field =
    case field of {
      Parameter p ->
        case M.lookup compareString p ps of {
          Nothing -> Left ("unbound data type parameter: " ++ p);
          Just k -> Right k
        };
      Function a b ->
        do {
          ka <- fieldKind declarations env ps a;
          kb <- fieldKind declarations env ps b;
          if (K.eqKind ka Star && K.eqKind kb Star)
          then Right Star
          else Left "function fields require kind * arguments"
        };
      Applied c args ->
        do {
          unless
            (M.member compareString c primitiveKinds ||
             memberString c (map datatypeName declarations))
            (Left ("unknown field type: " ++ c));
          when (length args > K.kindArity (constructorKind env c 0))
            (checkArity env c (length args));
          ks <- mapM (fieldKind declarations env ps) args;
          foldM K.applyKind (constructorKind env c (length args)) ks
        };
      Application a b ->
        do {
          ka <- fieldKind declarations env ps a;
          kb <- fieldKind declarations env ps b;
          K.applyKind ka kb
        };
      Quantified a k b -> fieldKind declarations env (M.insert compareString a k ps) b
    };
  validateConstructor :: [] DataDecl ->
                         DataEnv -> DataDecl -> ConstructorDecl -> Either String ();
  validateConstructor declarations env d c =
    do {
      upper "data constructor" (constructorName c);
      when (memberString (constructorName c) ((:) "True" ((:) "False" [])))
        (Left "cannot redefine a primitive constructor");
      mapM_
        (\field ->
           do {
             k <- fieldKind declarations env (M.fromList compareString (datatypeBinders d)) field;
             unless (K.eqKind k Star) (Left "constructor field must have kind *")
           })
        (constructorFields c)
    };
  validateDeclaration :: [] DataDecl -> DataEnv -> DataDecl -> Either String ();
  validateDeclaration declarations env d =
    do {
      upper "data type" (datatypeName d);
      when (M.member compareString (datatypeName d) primitiveKinds)
        (Left "cannot redefine a primitive type");
      when (memberString (datatypeName d) ((:) "True" ((:) "False" [])))
        (Left "reserved data type name");
      distinct "type parameter" (datatypeParameters d);
      mapM_
        (\p ->
           unless (identifier U.isLower p && not (memberString p keywords))
             (Left ("invalid type parameter: " ++ p)))
        (datatypeParameters d);
      when (null (datatypeConstructors d))
        (Left ("data type has no constructors: " ++ datatypeName d));
      mapM_ (validateConstructor declarations env d) (datatypeConstructors d)
    };
  validateDeclarations :: [] DataDecl -> Either String DataEnv;
  validateDeclarations ds =
    do {
      distinct "data type" (map datatypeName ds);
      distinct "data constructor"
        (concatMap (\d -> map constructorName (datatypeConstructors d)) ds);
      let {
        declarations = append builtinDeclarations ds
      };
      let {
        env =
          DataEnv (M.fromList compareString (map (\d -> (,) (datatypeName d) d) declarations))
            (M.fromList compareString
               (concatMap
                  (\d -> map (\c -> (,) (constructorName c) ((,) d c)) (datatypeConstructors d))
                  declarations))
            (M.union compareString primitiveKinds
               (M.fromList compareString
                  (map
                     (\d ->
                        (,) (datatypeName d)
                          (foldr (\p k -> KArrow (snd p) k) Star (datatypeBinders d)))
                     ds)))
      };
      mapM_ (validateDeclaration ds env) ds;
      Right env
    };
  alternativeNames :: [] ((,) (Maybe String) Int) -> [] String;
  alternativeNames [] = [];
  alternativeNames ((:) ((,) Nothing _) rest) = alternativeNames rest;
  alternativeNames ((:) ((,) (Just c) _) rest) = (:) c (alternativeNames rest);
  defaultPositions :: Int -> [] ((,) (Maybe String) Int) -> [] Int;
  defaultPositions _ [] = [];
  defaultPositions i ((:) ((,) name _) rest) =
    case name of {
      Nothing -> (:) i (defaultPositions (i + 1) rest);
      Just _ -> defaultPositions (i + 1) rest
    };
  validDefaults defaults total =
    case defaults of {
      [] -> True;
      (:) n [] -> (n == (total - 1));
      _ -> False
    };
  alternativeOwners :: DataEnv -> [] ((,) (Maybe String) Int) -> Either String ([] DataDecl);
  alternativeOwners _ [] = Right [];
  alternativeOwners env ((:) ((,) name arity) rest) =
    case name of {
      Nothing -> alternativeOwners env rest;
      Just c ->
        do {
          dc <- lookupConstructor env c;
          let {
            d = fst dc
          };
          let {
            ctor = snd dc
          };
          unless (arity == length (constructorFields ctor))
            (Left ("constructor pattern arity mismatch: " ++ c));
          ds <- alternativeOwners env rest;
          Right ((:) d ds)
        }
    };
  checkAlternatives :: DataEnv -> [] ((,) (Maybe String) Int) -> Either String (Maybe DataDecl);
  checkAlternatives env alternatives =
    do {
      when (null alternatives) (Left "case has no alternatives");
      let {
        names = alternativeNames alternatives
      };
      let {
        defaults = defaultPositions 0 alternatives
      };
      distinct "constructor alternative" names;
      unless (validDefaults defaults (length alternatives))
        (Left "a default alternative must be last and unique");
      owners <- alternativeOwners env alternatives;
      case owners of {
        [] -> Right Nothing;
        (:) d rest ->
          do {
            unless (all (\other -> eqString (datatypeName d) (datatypeName other)) rest)
              (Left "case patterns belong to different data types");
            let {
              missing =
                filter (\c -> not (memberString c names))
                  (map constructorName (datatypeConstructors d))
            };
            when (null defaults && not (null missing))
              (Left ("non-exhaustive case; missing: " ++ intercalate ", " missing));
            Right (Just d)
          }
      }
    };
  par yes text = if yes then ("(" ++ (text ++ ")")) else text;
  prettyParameter :: (,) String Kind -> String;
  prettyParameter ((,) name Star) = name;
  prettyParameter ((,) name kind) = ("(" ++ (name ++ (" : " ++ (K.prettyKind kind ++ ")"))));
  prettyField :: Int -> Field -> String;
  prettyField p field =
    case field of {
      Parameter a -> a;
      Applied c [] -> c;
      Applied c args -> par (p > 1) (intercalate " " ((:) c (map (prettyField 2) args)));
      Function a b -> par (p > 0) (prettyField 1 a ++ (" -> " ++ prettyField 0 b));
      Application a b -> par (p > 1) (prettyField 1 a ++ (" " ++ prettyField 2 b));
      Quantified n k b ->
        par (p > 0) ("forall " ++ (prettyParameter ((,) n k) ++ (". " ++ prettyField 0 b)))
    };
  prettyConstructor c =
    intercalate " " ((:) (constructorName c) (map (prettyField 2) (constructorFields c)));
  prettyDeclaration d =
    ("data " ++
     (intercalate " " ((:) (datatypeName d) (map prettyParameter (datatypeBinders d))) ++
      (" = " ++ (intercalate " | " (map prettyConstructor (datatypeConstructors d)) ++ ";"))))
}
