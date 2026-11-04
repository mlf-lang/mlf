-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Module where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Unicode as U;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Resolved as R;
  import qualified Bootstrap.IndexVec as V;
  sourcePath (SourceModule path _ _ _ _ _ _ _ _ _) = path;
  sourceModuleName (SourceModule _ name _ _ _ _ _ _ _ _) = name;
  sourceExports (SourceModule _ _ exports _ _ _ _ _ _ _) = exports;
  sourceImports (SourceModule _ _ _ imports _ _ _ _ _ _) = imports;
  sourceDatatypes (SourceModule _ _ _ _ ds _ _ _ _ _) = ds;
  sourceClasses (SourceModule _ _ _ _ _ cs _ _ _ _) = cs;
  sourceInstances (SourceModule _ _ _ _ _ _ instances _ _ _) = instances;
  sourceValues (SourceModule _ _ _ _ _ _ _ values _ _) = values;
  sourceBody (SourceModule _ _ _ _ _ _ _ _ body _) = body;
  sourceSyntax (SourceModule _ _ _ _ _ _ _ _ _ syntax) = syntax;
  isBuiltinModule name = (eqString name "Prelude" || eqString name "MLF.Primitive");
  moduleIdentity m = fromMaybe "Main" (sourceModuleName m);
  standaloneProgram m = Parser.standaloneProgram m;
  importedModule (Import name _ _ _) = name;
  importQualified (Import _ qualified _ _) = qualified;
  importAlias (Import _ _ alias _) = alias;
  importSelection (Import _ _ _ selection) = selection;
  className (SClassDecl name _ _ _) = name;
  classParameters (SClassDecl _ parameters _ _) = parameters;
  superclasses (SClassDecl _ _ supers _) = supers;
  classMethods (SClassDecl _ _ _ methods) = methods;
  instanceVariables (SInstanceDecl variables _ _ _ _) = variables;
  instanceContext (SInstanceDecl _ context _ _ _) = context;
  instanceClass (SInstanceDecl _ _ name _ _) = name;
  instanceHead (SInstanceDecl _ _ _ head _) = head;
  instanceMethods (SInstanceDecl _ _ _ _ methods) = methods;
  valueName ((,,) name _ _) = name;
  linkedProgram (LinkedModule program _ _ _) = program;
  linkedNames (LinkedModule _ names _ _) = names;
  linkedValueScopes (LinkedModule _ _ scopes _) = scopes;
  linkedInstanceScopes (LinkedModule _ _ _ scopes) = scopes;
  -- Loading threads explicit visited/order state through the caller's monad.
  -- The same traversal serves in-memory tests and file-backed compilation.
  loadGraph :: forall (m :: (* -> *)). (Monad m) => (String -> m (Either String SourceModule)) ->
                                                    SourceModule ->
                                                    m (Either String ([] SourceModule));
  loadGraph fetch root =
    loadGraphBy (\source -> source) fetch root;
  -- Payloads travel with the exact parser read. Consumers that authenticate
  -- fixed implementations must not reopen a path and mistake a later read for
  -- the bytes whose syntax and namespace were checked here.
  data LoadedModule = LoadedModule SourceModule String;
  data LoadedModules = LoadedModules ([] LoadedModule);
  loadedSource (LoadedModule source _) = source;
  loadedText (LoadedModule _ text) = text;
  loadedEntries (LoadedModules entries) = entries;
  loadedSources (LoadedModules entries) = map loadedSource entries;
  loadGraphBy :: forall (m :: (* -> *)) a. (Monad m) =>
    (a -> SourceModule) -> (String -> m (Either String a)) -> a -> m (Either String ([] a));
  loadGraphBy sourceOf fetch root =
    do {
      result <- visitBy sourceOf fetch root Set.empty [];
      return (mapEither (\state -> reverse (snd state)) result)
    };
  visit :: forall (m :: (* -> *)). (Monad m) => (String -> m (Either String SourceModule)) ->
                                                SourceModule ->
                                                Set String ->
                                                [] SourceModule ->
                                                m
                                                (Either String
                                                 ((,) (Set String) ([] SourceModule)));
  -- Discovery and namespace dependencies are not a compilation order. Mark
  -- before descending so a reference back into this crate needs no boot file.
  visit fetch source done order =
    visitBy (\value -> value) fetch source done order;
  visitBy :: forall (m :: (* -> *)) a. (Monad m) =>
    (a -> SourceModule) -> (String -> m (Either String a)) -> a ->
    Set String -> [] a -> m (Either String ((,) (Set String) ([] a)));
  visitBy sourceOf fetch payload done order =
    let {
      source = sourceOf payload;
      name = moduleIdentity source
    } in
    if Set.member compareString name done
    then return (Right ((,) done order))
    else do {
           let {
             dependencies = nubBy eqString (map importedModule (sourceImports source))
           };
           result <-
             visitDependenciesBy sourceOf fetch dependencies (Set.insert compareString name done) order;
           return (mapEither (\state -> (,) (fst state) ((:) payload (snd state))) result)
         };
  visitDependencies :: forall (m :: (* -> *)). (Monad m) => (String ->
                                                             m (Either String SourceModule)) ->
                                                            [] String ->
                                                            Set String ->
                                                            [] SourceModule ->
                                                            m
                                                            (Either String
                                                             ((,) (Set String)
                                                              ([] SourceModule)));
  visitDependencies fetch dependencies done order =
    visitDependenciesBy (\source -> source) fetch dependencies done order;
  visitDependenciesBy :: forall (m :: (* -> *)) a. (Monad m) =>
    (a -> SourceModule) -> (String -> m (Either String a)) -> [] String ->
    Set String -> [] a -> m (Either String ((,) (Set String) ([] a)));
  visitDependenciesBy sourceOf fetch dependencies done order =
    case dependencies of {
      [] -> return (Right ((,) done order));
      (:) dependency rest ->
        if isBuiltinModule dependency
        then visitDependenciesBy sourceOf fetch rest done order
        else if Set.member compareString dependency done
             then visitDependenciesBy sourceOf fetch rest done order
             else do {
                    loaded <- fetch dependency;
                    case loaded of {
                      Left message -> return (Left message);
                      Right payload -> let { child = sourceOf payload } in
                        if not (eqMaybe eqString (sourceModuleName child) (Just dependency))
                        then return
                               (Left
                                  (sourcePath child ++
                                   (": expected module " ++
                                    (dependency ++
                                     (", found " ++
                                      fromMaybe "an unnamed script" (sourceModuleName child))))))
                        else if isJust (sourceBody child)
                             then return
                                    (Left
                                       (sourcePath child ++
                                        ": imported modules must contain declarations only"))
                             else do {
                                    result <- visitBy sourceOf fetch payload done order;
                                    case result of {
                                      Left message -> return (Left message);
                                      Right state ->
                                        visitDependenciesBy sourceOf fetch rest (fst state) (snd state)
                                    }
                                  }
                    }
                  }
    };
  data ModuleIdentity a = ModuleIdentity a;
  runIdentity (ModuleIdentity a) = a;
  identityBind (ModuleIdentity a) f = f a;
  instance Functor ModuleIdentity where {
    fmap function action = identityBind action (\value -> ModuleIdentity (function value))
  };
  instance Applicative ModuleIdentity where {
    pure = ModuleIdentity;
    (<*>) action argument =
      identityBind action
        (\function -> identityBind argument (\value -> ModuleIdentity (function value)))
  };
  instance Monad ModuleIdentity where {
    (>>=) = identityBind
  };
  loadModuleMap :: Map String ((,) String String) ->
                   SourceModule -> Either String ([] SourceModule);
  loadModuleMap sources root =
    runIdentity
      (loadGraph
         (\name ->
            ModuleIdentity
              (case M.lookup compareString name sources of {
                 Nothing -> Left ("cannot find module " ++ name);
                 Just ((,) file source) -> Parser.parseModule file source
               }))
         root);
  splitComponents :: String -> Int -> Int -> [] String;
  splitComponents text start position =
    if (position >= stringLength text)
    then (:) (stringSlice text start (position - start)) []
    else if (stringCodeAt text position == 46)
         then (:) (stringSlice text start (position - start))
                (splitComponents text (position + 1) (position + 1))
         else splitComponents text start (position + 1);
  components name = splitComponents name 0 0;
  lastSlash :: String -> Int -> Int;
  lastSlash text position =
    if (position < 0)
    then (-1)
    else if ((stringCodeAt text position == 47) || (stringCodeAt text position == 92))
         then position
         else lastSlash text (position - 1);
  trimSlash :: String -> Int -> Int;
  trimSlash path n =
    if ((n > 1) && ((stringCodeAt path (n - 1) == 47) || (stringCodeAt path (n - 1) == 92)))
    then trimSlash path (n - 1)
    else n;
  takeDirectory path =
    let {
      end = trimSlash path (stringLength path)
    } in
    let {
      position = lastSlash path (end - 1)
    } in
    if (position < 0) then "." else if (position == 0) then "/" else stringSlice path 0 position;
  parentDirectory :: Int -> String -> String;
  parentDirectory count path =
    if (count <= 0) then path else parentDirectory (count - 1) (takeDirectory path);
  joinPath a b =
    if (stringLength a == 0)
    then b
    else if (stringCodeAt a (stringLength a - 1) == 47) then (a ++ b) else (a ++ ("/" ++ b));
  findFiles :: [] String -> IO ([] String);
  findFiles [] = ioReturn [];
  findFiles ((:) file rest) =
    do {
      present <- fileExists file;
      remaining <- findFiles rest;
      ioReturn (if present then (:) file remaining else remaining)
    };
  fetchFile paths name =
    do {
      result <- fetchFileWithEvidence paths name;
      ioReturn (mapEither loadedSource result)
    };
  fetchFileWithEvidence paths name = fetchFileWithEvidenceUsing Parser.parseModule paths name;
  -- The callback returns raw syntax, not authenticated evidence. Graph and
  -- compiler checks remain mandatory, including for caller-supplied parsers.
  fetchFileWithEvidenceUsing parseSource paths name =
    do {
      let {
        stem = intercalate "/" (components name)
      };
      let {
        files =
          concatMap
            (\path ->
               (:) (joinPath path (stem ++ ".emlf")) ((:) (joinPath path (stem ++ ".hs")) []))
            paths
      };
      found <- findFiles files;
      let {
        legacy = any (\file -> Lexer.sourceHasSuffix file ".emlf") found
      };
      let {
        shared = any (\file -> Lexer.sourceHasSuffix file ".hs") found
      };
      if (legacy && shared)
      then ioReturn
             (Left
                ("ambiguous source module " ++
                 (name ++
                  (": both .emlf and .hs candidates exist: " ++
                   (intercalate ", " found ++ "; use an explicit manifest mapping")))))
      else case found of {
             [] ->
               ioReturn
                 (Left
                    ("cannot find module " ++ (name ++ ("; searched " ++ intercalate ", " files))));
             (:) file _ ->
               do {
                 source <- readFile file;
                 ioReturn (mapEither (\parsed -> LoadedModule parsed source) (parseSource file source))
               }
           }
    };
  loadModuleFiles :: [] String -> SourceModule -> IO (Either String ([] SourceModule));
  -- Search roots need not exist: an unused -i path must not abort loading.
  -- fileExists/readFile resolve relative paths, dot segments and symlinks
  -- through the filesystem; no canonicalPath precondition is needed here.
  loadModuleFiles includes root =
    loadGraph (fetchFile (moduleSearchPaths includes root)) root;
  moduleSearchPaths includes root = let {
    directory = takeDirectory (sourcePath root);
    hierarchy = parentDirectory (length (components (moduleIdentity root)) - 1) directory
  } in nubBy eqString ((:) directory (append includes ((:) hierarchy ((:) "." []))));
  loadModuleFilesWithEvidence :: [] String -> SourceModule -> String ->
    IO (Either String LoadedModules);
  loadModuleFilesWithEvidence includes root input =
    loadModuleFilesWithEvidenceUsing Parser.parseModule includes root input;
  loadModuleFilesWithEvidenceUsing parseSource includes root input = do {
    result <- loadGraphBy loadedSource (fetchFileWithEvidenceUsing parseSource (moduleSearchPaths includes root))
      (LoadedModule root input);
    ioReturn (mapEither LoadedModules result)
  };
  -- Installed defaults have lower precedence than actual user search roots.
  -- Presence is decided before parsing, so an explicit malformed or ambiguous
  -- source never silently falls through to a different installed definition.
  fetchFileWithEvidenceUsingFallback parseSource paths defaults name = do {
    let { stem = intercalate "/" (components name);
          files = concatMap (\path ->
            [joinPath path (stem ++ ".emlf"), joinPath path (stem ++ ".hs")]) paths };
    found <- findFiles files;
    if null found then fetchFileWithEvidenceUsing parseSource defaults name
      else fetchFileWithEvidenceUsing parseSource paths name
  };
  loadModuleFilesWithEvidenceUsingFallback parseSource includes defaults root input = do {
    result <- loadGraphBy loadedSource
      (fetchFileWithEvidenceUsingFallback parseSource (moduleSearchPaths includes root) defaults)
      (LoadedModule root input);
    ioReturn (mapEither LoadedModules result)
  };
  -- Interfaces retain original entity identity across diamonds and re-exports.
  data ModuleSpace = Terms | Types;
  data Role =
    Value |
    Datatype |
    Class |
    Constructor String |
    Method String |
    BuiltinType |
    Primitive Primitive |
    Boolean Bool |
    ManagedConstraint;
  data Entity = Entity String String Role;
  data Interface = Interface (Map ((,) ModuleSpace String) (Set Entity));
  data Names = Names (Map Entity String);
  data Renamed = Renamed Dependency.Symbols ([] DataDecl) ([] (R.Class Dependency.Declaration))
    ([] (R.Instance Dependency.Declaration)) ([] Dependency.Bound) (Maybe (R.Expr Dependency.Declaration));
  data Resolved = Resolved SourceModule Interface Renamed;
  data ResolvedCrate = ResolvedCrate Bindings ([] Resolved) (Map String IntSet) (Map String (Set String));
  resolvedCrateBindings (ResolvedCrate bindings _ _ _) = bindings;
  resolvedCrateNames crate = bindingNames (resolvedCrateBindings crate);
  resolvedCrateDisplayNames crate = M.fromList compareString (map (\((,) entity name) ->
    (,) name (if eqString (owner entity) "Prelude" then spelling entity else label entity))
    (M.toList (canonicalEntries (resolvedCrateBindings crate))));
  resolvedCrateModules (ResolvedCrate _ modules _ _) = modules;
  resolvedInstanceRows crate = concatMap (\entry ->
    map (\inst -> (,) (moduleIdentity (resolvedSource entry)) inst) (resolvedInstances (resolvedContents entry)))
    (resolvedCrateModules crate);
  instanceValue crate = R.namedInstance (Dependency.symbolName (bindingSymbols (resolvedCrateBindings crate)));
  resolvedCrateInstances crate = map (\((,) owner inst) -> (,) owner (instanceValue crate inst)) (resolvedInstanceRows crate);
  resolvedCrateValueScopes (ResolvedCrate _ modules masks _) = M.fromList compareString
    (concatMap (\entry -> let { r = resolvedContents entry; scope = M.get compareString (moduleIdentity (resolvedSource entry)) masks } in
      map (\binding -> (,) (Dependency.symbolName (renamedSymbols r) (Dependency.boundId binding)) scope) (renamedBindings r)) modules);
  resolvedCrateInstanceScopes (ResolvedCrate _ modules masks _) = concatMap (\entry ->
    map (\_ -> M.get compareString (moduleIdentity (resolvedSource entry)) masks)
      (resolvedInstances (resolvedContents entry))) modules;
  resolvedCrateReach (ResolvedCrate _ _ _ reach) = reach;
  boundIn crate modules = Dependency.BoundValues (bindingSymbols (resolvedCrateBindings crate))
    (concatMap (compose renamedBindings resolvedContents) modules);
  owner (Entity name _ _) = name;
  spelling (Entity _ name _) = name;
  role (Entity _ _ category) = category;
  space entity =
    case role entity of {
      Datatype -> Types;
      Class -> Types;
      BuiltinType -> Types;
      ManagedConstraint -> Types;
      _ -> Terms
    };
  spaceCode :: ModuleSpace -> Int;
  spaceCode Terms = 0;
  spaceCode Types = 1;
  compareSpace a b = compareInt (spaceCode a) (spaceCode b);
  compareKey a b = comparePair compareSpace compareString a b;
  roleCode :: Role -> Int;
  roleCode Value = 0;
  roleCode Datatype = 1;
  roleCode Class = 2;
  roleCode (Constructor _) = 3;
  roleCode (Method _) = 4;
  roleCode BuiltinType = 5;
  roleCode (Primitive _) = 6;
  roleCode (Boolean _) = 7;
  roleCode ManagedConstraint = 8;
  compareRole a b =
    let {
      first = compareInt (roleCode a) (roleCode b)
    } in
    if (first /= 0)
    then first
    else case a of {
           Constructor name ->
             case b of {
               Constructor other -> compareString name other;
               _ -> 0
             };
           Method name ->
             case b of {
               Method other -> compareString name other;
               _ -> 0
             };
           Primitive p ->
             case b of {
               Primitive q -> P.comparePrimitive p q;
               _ -> 0
             };
           Boolean x ->
             case b of {
               Boolean y -> compareInt (if x then 1 else 0) (if y then 1 else 0);
               _ -> 0
             };
           _ -> 0
         };
  compareEntity a b =
    let {
      ownerOrder = compareString (owner a) (owner b)
    } in
    let {
      name = compareString (spelling a) (spelling b)
    } in
    if (ownerOrder /= 0)
    then ownerOrder
    else if (name /= 0) then name else compareRole (role a) (role b);
  isRole category entity = (compareRole category (role entity) == 0);
  parent entity =
    case role entity of {
      Constructor name -> Just ((,) (owner entity) name);
      Method name -> Just ((,) (owner entity) name);
      Boolean _ -> Just ((,) "Prelude" "Bool");
      _ -> Nothing
    };
  emptyInterface = Interface M.empty;
  interface entities =
    Interface
      (M.fromListWith compareKey (Set.union compareEntity)
         (map (\entity -> (,) ((,) (space entity) (spelling entity)) (Set.singleton entity))
            entities));
  interfaceMap (Interface entries) = entries;
  interfaceEntries (Interface entries) = M.toList entries;
  union (Interface a) (Interface b) =
    Interface (M.unionWith compareKey (Set.union compareEntity) a b);
  lookupEntities namespace name (Interface entries) =
    M.findWithDefault compareKey Set.empty ((,) namespace name) entries;
  visible (Interface entries) = Set.unions compareEntity (M.elems entries);
  -- Selector predicates depend only on entity identity. Filtering each alias
  -- set first preserves the ordered, deduplicated result without rebuilding a
  -- global set containing every unrelated visible entity for each parent.
  visibleMatching :: (Entity -> Bool) -> Interface -> Set Entity;
  visibleMatching predicate (Interface entries) =
    Set.unions compareEntity (map (Set.filter predicate) (M.elems entries));
  -- Compiler-only intrinsic reach supplies generated evidence, not source method visibility.
  -- Ordinary qualified imports remain visible for instance method declarations.
  sourceMethodVisible (Interface entries) =
    visible
      (Interface
         (M.filterWithKey
            (\key _ -> not (Lexer.textStartsAt (snd key) 0 "$MLF.Intrinsics."))
            entries));
  uniqueInterface context env =
    do {
      mapM_
        (\entry ->
           unless (Set.size (snd entry) == 1)
             (Left (context ++ (": conflicting declarations or exports for " ++ snd (fst entry)))))
        (interfaceEntries env);
      Right env
    };
  primitiveTypeNames :: [] String;
  primitiveTypeNames = append ((:) "Char" ((:) "IOError" legacyPrimitiveTypeNames)) ["IOWorld"];
  legacyPrimitiveTypeNames :: [] String;
  legacyPrimitiveTypeNames =
    ["AsyncScope", "Completion", "AsyncSubscription", "ST", "STArray",
     "Int", "Integer", "Double", "Bool", "String", "IO", "IntArray", "DoubleArray",
     "ByteArray", "IntTable"];
  primitiveEntities =
    append (map (\p -> Entity "Prelude" (P.primitiveName p) (Primitive p)) P.allPrimitives)
      (append (map (\name -> Entity "Prelude" name BuiltinType) primitiveTypeNames)
        [Entity "Prelude" "True" (Boolean True), Entity "Prelude" "False" (Boolean False)]);
  primitiveScope = interface primitiveEntities;
  -- Prelude is a re-export of the one standard facade, never a second Monad.
  preludeSource =
    SourceModule "<Prelude>" (Just "Prelude")
      (Just ((:) (ExportModule "MLF.Primitive") []))
      ((:) (Import "MLF.Primitive" False Nothing Everything) [])
      [] [] [] [] Nothing LegacyEmlfV1;
  -- These are ordinary bindings with the same fixities and class identities as
  -- the GHC facade. Primitive nominal types retain their stable runtime identity.
  sharedPrimitiveEntities =
    append ((:) (Entity "MLF.Primitive" "HasCallStack" ManagedConstraint)
      ((:) (Entity "MLF.Primitive" "CallStack" BuiltinType)
        ((:) (Entity "MLF.Primitive" "callStack" Value) [])))
      (filter (\entity -> not (eqString (spelling entity) "pure" || eqString (spelling entity) "ioError")) primitiveEntities);
  builtinEntities source = if eqString (moduleIdentity source) "MLF.Primitive" then sharedPrimitiveEntities else [];
  primitiveSource =
    SourceModule "<MLF.Primitive>" (Just "MLF.Primitive") Nothing [] []
      Prelude.sharedClasses Prelude.sharedInstances
      (append Prelude.stackFacadeValues (filter (\((,,) name _ _) -> not (eqString name "==" || eqString name "/="))
((:) ((,,) "otherwise" Nothing (SBoolLit True)) ((:) ((,,) "implementationHost" Nothing (SStringLit "native-MLF")) ((:) ((,,) "bind" Nothing (SVar "$MLF.Primitive.>>=")) ((:) ((,,) "negate" Nothing (SLam "$x" Nothing (SApp (SApp (SPrimitive PSubInt) (SIntLit 0)) (SVar "$x")))) ((:) ((,,) "+" Nothing (SPrimitive PAddInt)) ((:) ((,,) "-" Nothing (SPrimitive PSubInt)) ((:) ((,,) "*" Nothing (SPrimitive PMulInt)) ((:) ((,,) "/" Nothing (SPrimitive PQuotInt)) ((:) ((,,) "%" Nothing (SPrimitive PRemInt)) ((:) ((,,) "==" Nothing (SPrimitive PEqInt)) ((:) ((,,) "<" Nothing (SPrimitive PLtInt)) ((:) ((,,) "++" Nothing (SPrimitive PConcatString)) ((:) ((,,) "/=" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (Parser.notValue (SApp (SApp (SPrimitive PEqInt) (SVar "$a")) (SVar "$b")))))) ((:) ((,,) "<=" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (Parser.notValue (SApp (SApp (SPrimitive PLtInt) (SVar "$b")) (SVar "$a")))))) ((:) ((,,) ">" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (SApp (SApp (SPrimitive PLtInt) (SVar "$b")) (SVar "$a"))))) ((:) ((,,) ">=" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (Parser.notValue (SApp (SApp (SPrimitive PLtInt) (SVar "$a")) (SVar "$b")))))) ((:) ((,,) "&&" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (Parser.conditional (SVar "$a") (SVar "$b") (SBoolLit False))))) ((:) ((,,) "||" Nothing (SLam "$a" Nothing (SLam "$b" Nothing (Parser.conditional (SVar "$a") (SBoolLit True) (SVar "$b"))))) ([]))))))))))))))))))))) Nothing LegacyEmlfV1;
  locals :: SourceModule -> Either String Interface;
  locals source =
    do {
      mapM_
        (\declaration ->
           do {
             when (elem eqString (D.datatypeName declaration) primitiveTypeNames)
               (Left
                  (moduleIdentity source ++
                   (": cannot redefine a primitive type: " ++ D.datatypeName declaration)));
             when (elem eqString (D.datatypeName declaration) ((:) "True" ((:) "False" [])))
               (Left (moduleIdentity source ++ ": reserved data type name"));
             mapM_
               (\constructor ->
                  when
                    (elem eqString (D.constructorName constructor)
                       ((:) "True" ((:) "False" [])))
                    (Left
                       (moduleIdentity source ++
                        (": cannot redefine a primitive constructor: " ++
                         D.constructorName constructor))))
               (D.datatypeConstructors declaration)
           })
        (sourceDatatypes source);
      let {
        entity = Entity (moduleIdentity source)
      };
      let {
        values = map (\value -> entity (valueName value) Value) (sourceValues source)
      };
      let {
        datatypes =
          concatMap
            (\declaration ->
               (:) (entity (D.datatypeName declaration) Datatype)
                 (map
                    (\constructor ->
                       entity (D.constructorName constructor)
                         (Constructor (D.datatypeName declaration)))
                    (D.datatypeConstructors declaration)))
            (sourceDatatypes source)
      };
      let {
        classes =
          concatMap
            (\klass ->
               (:) (entity (className klass) Class)
                 (map (\method -> entity (fst method) (Method (className klass)))
                    (classMethods klass)))
            (sourceClasses source)
      };
      let {
        entries = append values (append datatypes classes)
      };
      let {
        keys = map (\entry -> (,) (space entry) (spelling entry)) entries
      };
      unless (length keys == length (nubBy (\a b -> (compareKey a b == 0)) keys))
        (Left (moduleIdentity source ++ ": duplicate declaration"));
      uniqueInterface (moduleIdentity source) (interface entries)
    };
  implicitMode :: PreludeMode -> Bool;
  implicitMode ImplicitPrelude = True;
  implicitMode NoImplicitPrelude = False;
  importsFor mode source =
    if isBuiltinModule (moduleIdentity source)
    then sourceImports source
    else let {
           imports = sourceImports source;
           -- Only compiler-generated references can use this unlexable alias.
           -- Its dependency edge supplies genuine builtin instances even with
           -- NoImplicitPrelude, without exposing ordinary facade names.
           intrinsic = Import "MLF.Primitive" True (Just "$MLF.Intrinsics") Everything;
           withIntrinsic = (:) intrinsic imports
         } in
         if (implicitMode mode &&
             (not (Lexer.isSharedSyntax (sourceSyntax source)) &&
              not (any (\entry -> eqString (importedModule entry) "Prelude") imports)))
         then (:) (Import "Prelude" False Nothing Everything) withIntrinsic
         else withIntrinsic;
  qualify name (Interface entries) =
    Interface
      (M.fromList compareKey
         (map
            (\entry ->
               case entry of {
                 (,) ((,) namespace spelling) entities ->
                   (,) ((,) namespace (name ++ ("." ++ spelling))) entities
               })
            (M.toList entries)));
  scope :: PreludeMode ->
           Map String Interface -> SourceModule -> Interface -> Either String Interface;
  scope mode exports source local =
    do {
      imported <-
        mapM
          (\entry ->
             do {
               available <-
                 case M.lookup compareString (importedModule entry) exports of {
                   Nothing -> Left ("unknown imported module " ++ importedModule entry);
                   Just env -> Right env
                 };
               selected <- selectImport available (importSelection entry);
               let {
                 alias = fromMaybe (importedModule entry) (importAlias entry)
               };
               let {
                 qualified = qualify alias selected
               };
               Right (if importQualified entry then qualified else union selected qualified)
             })
          (importsFor mode source);
      let {
        builtins =
          if (not (Lexer.isSharedSyntax (sourceSyntax source)) &&
              (not (implicitMode mode) &&
               not
                 (any (\entry -> eqString (importedModule entry) "Prelude")
                    (sourceImports source))))
          then primitiveScope
          else emptyInterface
      };
      let {
        declared = foldr union (union local (qualify (moduleIdentity source) local)) imported
      };
      Right (Interface (M.union compareKey (interfaceMap declared) (interfaceMap builtins)))
    };
  sourceReference name = if Lexer.textStartsAt name 0 "$MLF.Source." then stringSlice name 12 (stringLength name - 12) else name;
  label entity = (owner entity ++ ("." ++ spelling entity));
  lookupEntity namespace name env =
    case Set.toList (lookupEntities namespace (sourceReference name) env) of {
      [] -> Left ("name is not in scope: " ++ name);
      (:) entity [] -> Right entity;
      entities ->
        Left ("ambiguous name " ++ (name ++ (": " ++ intercalate ", " (map label entities))))
    };
  isConstructor entity =
    case role entity of {
      Constructor _ -> True;
      Boolean _ -> True;
      _ -> False
    };
  selectItem :: Bool -> Interface -> Export -> Either String Interface;
  selectItem hiding env item =
    case item of {
      ExportValue name ->
        do {
          entity <- lookupEntity Terms name env;
          Right (interface ((:) entity []))
        };
      ExportType name Abstract ->
        if hiding
        then do {
               let {
                 matches =
                   Set.union compareEntity (lookupEntities Types name env)
                     (Set.filter isConstructor (lookupEntities Terms name env))
               };
               when (Set.null matches) (Left ("name is not exported: " ++ name));
               Right (interface (Set.toList matches))
             }
        else selectType env name Abstract;
      ExportType name members -> selectType env name members;
      ExportModule _ -> Left "module re-exports are only allowed in export lists"
    };
  selectType env name members =
    do {
      ty <- lookupEntity Types name env;
      let {
        children =
          Set.toList
            (visibleMatching
               (\entity ->
                  eqMaybe (eqPair eqString eqString) (parent entity)
                    (Just ((,) (owner ty) (spelling ty))))
               env)
      };
      chosen <-
        case members of {
          Abstract -> Right [];
          AllMembers -> Right children;
          Members names ->
            mapM
              (\child ->
                 case filter (\entity -> eqString child (spelling entity)) children of {
                   (:) entity [] -> Right entity;
                   _ -> Left (child ++ (" is not a visible member of " ++ name))
                 })
              names
        };
      Right (interface ((:) ty chosen))
    };
  selectImport :: Interface -> Selection -> Either String Interface;
  selectImport env selection =
    case selection of {
      Everything -> Right env;
      Only items ->
        foldM
          (\acc item ->
             do {
               selected <- selectItem False env item;
               Right (union acc selected)
             })
          emptyInterface
          items;
      Hiding items ->
        do {
          hidden <-
            foldM
              (\acc item ->
                 do {
                   selected <- selectItem True env item;
                   Right (union acc selected)
                 })
              emptyInterface
              items;
          let {
            omitted = visible hidden
          };
          Right
            (Interface
               (M.mapMaybe
                  (\entities ->
                     let {
                       remaining = Set.difference compareEntity entities omitted
                     } in
                     if Set.null remaining then Nothing else Just remaining)
                  (interfaceMap env)))
        }
    };
  hasDot :: String -> Int -> Bool;
  hasDot name index =
    ((index < stringLength name) && ((stringCodeAt name index == 46) || hasDot name (index + 1)));
  exportsFor mode source local env =
    case sourceExports source of {
      Nothing -> Right local;
      Just items ->
        do {
          let {
            aliases =
              (:) (moduleIdentity source)
                (map (\entry -> fromMaybe (importedModule entry) (importAlias entry))
                   (importsFor mode source))
          };
          exported <- foldM (exportItem aliases env) emptyInterface items;
          uniqueInterface (moduleIdentity source) exported
        }
    };
  exportItem aliases env acc item =
    case item of {
      ExportModule name ->
        do {
          unless (elem eqString name aliases)
            (Left ("cannot re-export unimported module " ++ name));
          let {
            entries =
              concatMap
                (\entry ->
                   case entry of {
                     (,) ((,) namespace spelling) entities ->
                       if hasDot spelling 0
                       then []
                       else filter
                              (\entity ->
                                 Set.member compareEntity entity
                                   (lookupEntities namespace (name ++ ("." ++ spelling)) env))
                              (Set.toList entities)
                   })
                (interfaceEntries env)
          };
          Right (union acc (interface entries))
        };
      _ ->
        do {
          selected <- selectItem False env item;
          Right (union acc selected)
        }
    };
  namespacePart namespace (Interface entries) =
    Interface (M.filterWithKey (\key _ -> (compareSpace (fst key) namespace == 0)) entries);
  eqInterface a b =
    M.eqMap (\x y -> (compareKey x y == 0)) (Set.eqSet (\x y -> (compareEntity x y == 0)))
      (interfaceMap a)
      (interfaceMap b);
  -- During namespace discovery a selector denotes all currently known candidate
  -- identities. Missing names and ambiguity are diagnosed only after convergence.
  -- Types are solved first: member hiding then has fixed parent identities and
  -- the term equations are monotone even through cyclic re-exports.
  partialSelectItem hiding env item =
    case item of {
      ExportModule _ -> emptyInterface;
      ExportValue name -> interface (Set.toList (lookupEntities Terms name env));
      ExportType name Abstract ->
        if hiding
        then interface
               (Set.toList
                  (Set.union compareEntity (lookupEntities Types name env)
                     (Set.filter isConstructor (lookupEntities Terms name env))))
        else interface (Set.toList (lookupEntities Types name env));
      ExportType name members ->
        let {
          types = lookupEntities Types name env
        } in
        let {
          parents = map (\entity -> (,) (owner entity) (spelling entity)) (Set.toList types)
        } in
        let {
          children =
            Set.toList
              (visibleMatching
                 (\entity ->
                    case parent entity of {
                      Nothing -> False;
                      Just identity -> elem (eqPair eqString eqString) identity parents
                    })
                 env)
        } in
        let {
          chosen =
            case members of {
              Abstract -> [];
              AllMembers -> children;
              Members names -> filter (\entity -> elem eqString (spelling entity) names) children
            }
        } in
        interface (append (Set.toList types) chosen)
    };
  partialImport env selection =
    case selection of {
      Everything -> env;
      Only items ->
        foldl (\acc item -> union acc (partialSelectItem False env item)) emptyInterface items;
      Hiding items ->
        let {
          omitted =
            visible
              (foldl (\acc item -> union acc (partialSelectItem True env item)) emptyInterface
                 items)
        } in
        Interface
          (M.mapMaybe
             (\entities ->
                let {
                  remaining = Set.difference compareEntity entities omitted
                } in
                if Set.null remaining then Nothing else Just remaining)
             (interfaceMap env))
    };
  partialScope mode exports source local =
    let {
      imported =
        map
          (\entry ->
             let {
               available =
                 M.findWithDefault compareString emptyInterface (importedModule entry) exports
             } in
             let {
               selected = partialImport available (importSelection entry)
             } in
             let {
               qualified = qualify (fromMaybe (importedModule entry) (importAlias entry)) selected
             } in
             if importQualified entry then qualified else union selected qualified)
          (importsFor mode source)
    } in
    let {
      builtins =
        if (not (Lexer.isSharedSyntax (sourceSyntax source)) &&
            (not (implicitMode mode) &&
             not
               (any (\entry -> eqString (importedModule entry) "Prelude") (sourceImports source))))
        then primitiveScope
        else emptyInterface
    } in
    let {
      declared = foldr union (union local (qualify (moduleIdentity source) local)) imported
    } in
    Interface (M.union compareKey (interfaceMap declared) (interfaceMap builtins));
  partialExports mode source local env =
    case sourceExports source of {
      Nothing -> local;
      Just items ->
        foldl
          (\acc item ->
             case item of {
               ExportModule name ->
                 let {
                   aliases =
                     (:) (moduleIdentity source)
                       (map (\entry -> fromMaybe (importedModule entry) (importAlias entry))
                          (importsFor mode source))
                 } in
                 if elem eqString name aliases
                 then case exportItem aliases env acc item of {
                        Left _ -> acc;
                        Right selected -> selected
                      }
                 else acc;
               _ -> union acc (partialSelectItem False env item)
             })
          emptyInterface
          items
    };
  settleExports :: PreludeMode ->
                   Bool ->
                   Map String Interface ->
                   Map String Interface ->
                   Map String Interface ->
                   [] SourceModule -> Map String Interface -> Map String Interface;
  settleExports mode typePhase external typeExports localMap modules current =
    let {
      entries =
        map
          (\source ->
             let {
               name = moduleIdentity source
             } in
             let {
               local = M.findWithDefault compareString emptyInterface name localMap
             } in
             let {
               env =
                 partialScope mode current source local
             } in
             let {
               exported = partialExports mode source local env
             } in
             (,) name
               (if typePhase
                then namespacePart Types exported
                else union (M.findWithDefault compareString emptyInterface name typeExports)
                       (namespacePart Terms exported)))
          modules
    } in
    let {
      next = M.union compareString (M.fromList compareString entries) external
    } in
    if M.eqMap eqString eqInterface current next
    then next
    else settleExports mode typePhase external typeExports localMap modules next;
  crateExports mode external localMap modules =
    let {
      types = settleExports mode True external M.empty localMap modules external
    } in
    settleExports mode False external types localMap modules types;
  sourceUsed source =
    let {
      datatypes =
        concatMap
          (\declaration ->
             (:) (D.datatypeName declaration)
               (map D.constructorName (D.datatypeConstructors declaration)))
          (sourceDatatypes source)
    } in
    let {
      classes =
        concatMap (\klass -> (:) (className klass) (map fst (classMethods klass)))
          (sourceClasses source)
    } in
    let {
      values =
        concatMap
          (\value ->
             case value of {
               (,,) name _ body -> (:) name (Desugar.allNames body)
             })
          (sourceValues source)
    } in
    let {
      methods =
        concatMap
          (\inst ->
             concatMap (\method -> (:) (fst method) (Desugar.allNames (snd method)))
               (instanceMethods inst))
          (sourceInstances source)
    } in
    append datatypes
      (append classes
         (append values (append methods (maybe [] Desugar.allNames (sourceBody source)))));
  chooseName :: Set String -> String -> Int -> (,) String Int;
  chooseName used prefix index =
    let {
      name = (prefix ++ showInt index)
    } in
    if Set.member compareString name used
    then chooseName used prefix (index + 1)
    else (,) name (index + 1);
  allocateName used state entity =
    case state of {
      (,) entries index ->
        if (eqString (owner entity) "MLF.Primitive" &&
            ((eqString (spelling entity) "HasCallStack" && isRole ManagedConstraint entity) ||
             (eqString (spelling entity) "CallStack" && isRole BuiltinType entity) ||
             (eqString (spelling entity) "callStack" && isRole Value entity)))
        then (,) (M.insert compareEntity entity
                    (if eqString (spelling entity) "HasCallStack" then "MLFHasCallStack"
                     else if eqString (spelling entity) "CallStack" then "MLFCallStack" else "mlfCallStack") entries) index
        else if isRole BuiltinType entity
        then (,) (M.insert compareEntity entity (spelling entity) entries) index
        else let {
               constructor =
                 case role entity of {
                   Constructor _ -> True;
                   _ -> False
                 }
             } in
             let {
               prefix =
                 if ((spaceCode (space entity) == spaceCode Types) || constructor)
                 then "ModuleEntity"
                 else "moduleEntity"
             } in
             let {
               chosen = chooseName used prefix index
             } in
             (,) (M.insert compareEntity entity (fst chosen) entries) (snd chosen)
    };
  -- Preserve the standalone names assigned with the original 132-entry ABI.
  -- Appended primitives still receive collision-checked names, after every
  -- entity that was present in an older compilation of the same source.
  allocateEntities :: Set String -> Set Entity -> Names;
  allocateEntities used entities =
    let {
      appended entity = case role entity of {
        Primitive p -> P.primitiveCode p >= 132;
        BuiltinType -> eqString (spelling entity) "IOWorld";
        _ -> False
      }
    } in case partition appended (Set.toList entities) of {
      (,) extra established -> Names (fst (foldl (allocateName used) ((,) M.empty 0)
                                         (append established extra)))
    };
  freshNames modules entities =
    allocateEntities (Set.fromList compareString (concatMap sourceUsed modules)) entities;
  -- Resolve the genuine facade alone, without subjecting standalone abstract
  -- nominal annotations to module lookup. The caller supplies every user name.
  standaloneBuiltinScope :: [] String -> Either String ((,,) Bindings Interface Renamed);
  standaloneBuiltinScope userNames = do {
    declared <- locals primitiveSource;
    let { env = union declared (interface sharedPrimitiveEntities) };
    let { used = Set.fromList compareString (append userNames (sourceUsed primitiveSource)) };
    let { names = resolveNames (allocateEntities used (visible env)) };
    renamed <- renameModule names env env primitiveSource;
    Right ((,,) names env renamed)
  };
  resolvedName (Names names) entity =
    case M.lookup compareEntity entity names of {
      Nothing -> Left ("missing module identity: " ++ label entity);
      Just name -> Right name
    };
  resolveType :: Bindings -> Interface -> SType -> Either String SType;
  resolveType names env ty =
    case ty of {
      SArrow a b ->
        do {
          a' <- resolveType names env a;
          b' <- resolveType names env b;
          Right (SArrow a' b')
        };
      SCon constructor arguments ->
        do {
          name <-
            if D.sourceBuiltinType constructor
            then Right constructor
            else do {
                   entity <- lookupEntity Types constructor env;
                   if (isRole Class entity || isRole ManagedConstraint entity)
                   then Left ("class used as a type constructor: " ++ constructor)
                   else bindingSpelling names entity
                 };
          arguments' <- mapM (resolveType names env) arguments;
          Right (SCon name arguments')
        };
      STypeApp f a ->
        do {
          f' <- resolveType names env f;
          a' <- resolveType names env a;
          Right (STypeApp f' a')
        };
      SForall flag variable bound body ->
        do {
          bound' <- resolveType names env bound;
          body' <- resolveType names env body;
          Right (SForall flag variable bound' body')
        };
      SQualified predicates body ->
        do {
          predicates' <- mapM (resolvePredicate names env) predicates;
          body' <- resolveType names env body;
          Right (SQualified predicates' body')
        };
      _ -> Right ty
    };
  resolvePredicate :: Bindings -> Interface -> SPredicate -> Either String SPredicate;
  resolvePredicate names env predicate =
    case predicate of {
      SPredicate name arguments ->
        do {
          entity <- lookupEntity Types name env;
          unless (isRole Class entity || isRole ManagedConstraint entity) (Left ("not a class: " ++ name));
          when (isRole ManagedConstraint entity && not (null arguments))
            (Left "HasCallStack does not take type arguments");
          name' <- bindingSpelling names entity;
          arguments' <- mapM (resolveType names env) arguments;
          Right (SPredicate name' arguments')
        }
    };
  resolveAnnotation names env annotation =
    case annotation of {
      SAnnotation variables ty ->
        do {
          ty' <- resolveType names env ty;
          Right (SAnnotation variables ty')
        }
    };
  resolveOptionalAnnotation names env annotation =
    case annotation of {
      Nothing -> Right Nothing;
      Just value ->
        do {
          value' <- resolveAnnotation names env value;
          Right (Just value')
        }
    };
  resolveRecursiveMode :: Bindings -> Interface -> RecursiveMode -> Either String RecursiveMode;
  resolveRecursiveMode names env mode =
    case mode of {
      InferRecursive -> Right InferRecursive;
      CheckRecursive annotation ->
        mapEither CheckRecursive (resolveAnnotation names env annotation)
    };
  -- Names is the name-based allocator/ABI interface. Only Bindings is retained
  -- by resolution. A term entity owns a slot; its spelling lives in Symbols.
  data BindingName = TermSlot (V.Index Dependency.Declaration) | OtherName String;
  data Bindings = Bindings Dependency.Symbols (Map Entity BindingName);
  resolveNames (Names allocated) = let {
    isTerm entry = case role (fst entry) of { Value -> True; Method _ -> True; _ -> False };
    parts = partition isTerm (M.toList allocated); terms = fst parts;
    symbols = Dependency.symbols (map (\((,) e n) -> (,) n (case role e of { Method _ -> True; _ -> False })) terms);
    slots = M.fromDistinctAscList (zipWith (\entry i -> (,) (fst entry) (TermSlot i)) terms
      (V.indices (Dependency.symbolNodes symbols)));
    others = M.fromDistinctAscList (map (\((,) e n) -> (,) e (OtherName n)) (snd parts))
  } in Bindings symbols (M.union compareEntity slots others);
  bindingSymbols (Bindings symbols _) = symbols;
  bindingText symbols binding = case binding of {
    TermSlot i -> Dependency.symbolName symbols i; OtherName name -> name
  };
  canonicalEntries (Bindings symbols table) = M.map (bindingText symbols) table;
  bindingNames bindings = Names (canonicalEntries bindings);
  lookupBinding (Bindings _ table) entity = case M.lookup compareEntity entity table of {
    Nothing -> Left ("missing module identity: " ++ label entity); Just binding -> Right binding
  };
  bindingSpelling bindings entity = mapEither (bindingText (bindingSymbols bindings)) (lookupBinding bindings entity);
  termId bindings entity = do {
    binding <- lookupBinding bindings entity;
    case binding of { TermSlot i -> Right i; OtherName _ -> Left ("not a declaration: " ++ label entity) }
  };
  variable bindings entity = case role entity of {
    Primitive p -> Right (R.Prim p);
    Value -> if eqString (owner entity) "MLF.Primitive" && eqString (spelling entity) "callStack"
             then Right R.CallStack else mapEither R.Global (termId bindings entity);
    Method _ -> mapEither R.Global (termId bindings entity);
    _ -> Left ("not a function or value: " ++ label entity)
  };
  constructor bindings entity = case role entity of {
    Constructor _ -> mapEither R.Constructor (bindingSpelling bindings entity);
    Boolean b -> Right (R.BoolLit b);
    _ -> Left ("not a data constructor: " ++ label entity)
  };
  namedTerm bindings = R.namedExpr (Dependency.symbolName (bindingSymbols bindings));
  resolveVariable names entity = mapEither (namedTerm names) (variable names entity);
  resolveConstructor names entity = mapEither (namedTerm names) (constructor names entity);
  resolvePattern bindings env pattern = let { child = resolvePattern bindings env } in case pattern of {
    SAsPattern name inner -> mapEither (R.AsPattern name) (child inner);
    SLazyPattern inner -> mapEither R.LazyPattern (child inner);
    SOverloadedStringPattern text _ _ -> do {
      eq <- termId bindings (Entity "MLF.Primitive" "==" (Method "Eq"));
      from <- termId bindings (Entity "MLF.Primitive" "fromString" (Method "IsString"));
      Right (R.OverloadedStringPattern text eq from)
    };
    SConstructorPattern name fields ->
      if D.sourceBuiltinConstructor name then Right (R.ConstructorPattern name fields) else do {
        entity <- lookupEntity Terms name env;
        case role entity of {
          Constructor _ -> mapEither (\n -> R.ConstructorPattern n fields) (bindingSpelling bindings entity);
          Boolean b -> if null fields then Right (R.BoolPattern b) else Left ("not a constructor pattern: " ++ name);
          _ -> Left ("not a constructor pattern: " ++ name)
        }
      };
    SNestedPattern name patterns -> do {
      n <- if D.sourceBuiltinConstructor name then Right name else do {
        entity <- lookupEntity Terms name env;
        case role entity of { Constructor _ -> bindingSpelling bindings entity; _ -> Left ("not a constructor pattern: " ++ name) }
      };
      mapEither (R.NestedPattern n) (mapM child patterns)
    };
    SAnnotatedPattern n ty -> mapEither (R.AnnotatedPattern n) (resolveAnnotation bindings env ty);
    SDefaultPattern n -> Right (R.DefaultPattern n);
    SIntPattern n -> Right (R.IntPattern n); SStringPattern s -> Right (R.StringPattern s);
    SBoolPattern b -> Right (R.BoolPattern b)
  };
  resolveExpr bindings env expression = resolveBound bindings env Set.empty (Desugar.desugarDo expression);
  entryExpr crate entry = let {
    source = resolvedSource entry; bindings = resolvedCrateBindings crate
  } in case resolvedBody (resolvedContents entry) of {
    Just body -> Right body;
    Nothing -> if any (\value -> eqString (valueName value) "main") (sourceValues source)
      then mapEither R.Global (termId bindings (Entity (moduleIdentity source) "main" Value))
      else resolveExpr bindings (resolvedScope entry) (SVar "main")
  };
  managedAnnotation :: SExpr -> Bool;
  managedAnnotation expression = case expression of {
    SAnn _ (SAnnotation _ ty) -> managedAnnotationType ty;
    _ -> False
  };
  managedResolved :: R.Expr Dependency.Declaration -> Bool;
  managedResolved expression = case expression of {
    R.Ann _ (SAnnotation _ ty) -> managedAnnotationType ty;
    _ -> False
  };
  managedAnnotationType ty = case ty of {
    SForall _ _ _ body -> managedAnnotationType body;
    SQualified predicates body -> any (\(SPredicate name _) -> eqString name "MLFHasCallStack") predicates || managedAnnotationType body;
    _ -> False
  };
  resolveBound :: Bindings -> Interface -> Set String -> SExpr -> Either String (R.Expr Dependency.Declaration);
  resolveBound bindings env bound expression = let {
    walk = resolveBound bindings env; child = walk bound; pat = resolvePattern bindings env;
    under ps = Set.union compareString bound (Set.fromList compareString (concatMap Surface.patternVariables ps))
  } in case expression of {
    SVar name ->
      if eqString name "$MLF.Stack.callStack" then Right R.CallStack
      else if Lexer.textStartsAt name 0 "$MLF.Primitive."
      then let { method = stringSlice name 15 (stringLength name - 15) } in
        variable bindings (Entity "MLF.Primitive" method (Method (Prelude.standardMethodClass method)))
      else if Lexer.textStartsAt name 0 "$MLF.Infix." then do {
        let { op = stringSlice name 11 (stringLength name - 11);
              invalid = "shared infix use requires a canonical MLF.Primitive binding; use the symbolic binding in prefix form" };
        when (Set.member compareString op bound) (Left invalid);
        entity <- lookupEntity Terms op env;
        unless (eqString (owner entity) "MLF.Primitive") (Left invalid);
        variable bindings entity
      } else if Set.member compareString name bound then Right (R.Local name)
      else bindEither (lookupEntity Terms name env) (variable bindings);
    SConstructor name -> if D.sourceBuiltinConstructor name then Right (R.Constructor name)
      else bindEither (lookupEntity Terms name env) (constructor bindings);
    SIntLit n -> Right (R.IntLit n); SDoubleLit n -> Right (R.DoubleLit n);
    SStringLit s -> Right (R.StringLit s); SBoolLit b -> Right (R.BoolLit b); SPrimitive p -> Right (R.Prim p);
    SLam n a b -> do {
      ty <- resolveOptionalAnnotation bindings env a;
      mapEither (R.Lam n ty) (walk (Set.insert compareString n bound) b)
    };
    SApp a b -> do { f <- child a; mapEither (R.App f) (child b) };
    SLet n a b -> do { v <- child a; mapEither (R.Let n v) (walk (Set.insert compareString n bound) b) };
    SAnn a t -> do { v <- child a; mapEither (R.Ann v) (resolveAnnotation bindings env t) };
    SSignature a t -> do { v <- child a; mapEither (R.Signature v) (resolveAnnotation bindings env t) };
    SLetRec defs b -> let {
      local = Set.union compareString bound (Set.fromList compareString (map (\((,,) n _ _) -> n) defs))
    } in do {
      ds <- mapM (\((,,) n mode value) -> do {
        m <- resolveRecursiveMode bindings env mode;
        mapEither ((,,) n m) (walk local value)
      }) defs;
      mapEither (R.LetRec ds) (walk local b)
    };
    SCase a arms -> do {
      scrut <- child a;
      mapEither (R.Case scrut) (mapM (\(SAlternative p b) -> do {
        q <- pat p; mapEither ((,) q) (walk (under [p]) b)
      }) arms)
    };
    SEquations rows -> mapEither R.Equations (mapM (\((,) ps b) -> do {
      qs <- mapM pat ps; mapEither ((,) qs) (walk (under ps) b)
    }) rows);
    SSharedBind p a b bind fail -> do {
      q <- pat p; x <- child a; y <- walk (under [p]) b; z <- child bind; f <- child fail;
      Right (R.SharedBind q x y z f)
    };
    SSourceDefinition b -> mapEither R.SourceDefinition (child b);
    SCallSite display loc b -> do {
      v <- child b; Right (if eqString display "an expression type signature" && not (managedResolved v)
        then v else R.CallSite display loc v)
    };
    SDo _ _ -> child (Desugar.desugarDo expression);
    SChecked _ _ -> Left "checked source forms are reserved for dictionary translation";
    SWanted _ _ -> Left "dictionary holes are reserved for dictionary translation"
  };
  ownName names local namespace name =
    do {
      entity <- lookupEntity namespace name local;
      bindingSpelling names entity
    };
  resolveField :: Bindings -> Interface -> Field -> Either String Field;
  resolveField names env field =
    case field of {
      Parameter _ -> Right field;
      Applied constructor fields ->
        do {
          ty <- resolveType names env (SCon constructor []);
          case ty of {
            SCon renamed _ ->
              do {
                fields' <- mapM (resolveField names env) fields;
                Right (Applied renamed fields')
              };
            _ -> Left "invalid field type"
          }
        };
      Function a b ->
        do {
          a' <- resolveField names env a;
          b' <- resolveField names env b;
          Right (Function a' b')
        };
      Application f a ->
        do {
          f' <- resolveField names env f;
          a' <- resolveField names env a;
          Right (Application f' a')
        };
      Quantified variable kind body ->
        do {
          body' <- resolveField names env body;
          Right (Quantified variable kind body')
        }
    };
  renameDatatype names local env declaration =
    do {
      name <- ownName names local Types (D.datatypeName declaration);
      constructors <-
        mapM
          (\constructor ->
             do {
               name' <- ownName names local Terms (D.constructorName constructor);
               fields <- mapM (resolveField names env) (D.constructorFields constructor);
               Right (ConstructorDecl name' fields)
             })
          (D.datatypeConstructors declaration);
      Right (DataDeclK name (D.datatypeBinders declaration) constructors)
    };
  renameClass names local env klass =
    do {
      name <- ownName names local Types (className klass);
      supers <- mapM (resolvePredicate names env) (superclasses klass);
      methods <-
        mapM
          (\method ->
             do {
               entity <- lookupEntity Terms (fst method) local;
               name' <- termId names entity;
               ty <- resolveType names env (snd method);
               Right ((,) name' ty)
             })
          (classMethods klass);
      Right (R.Class name (classParameters klass) supers methods)
    };
  renameInstance shared names env inst =
    do {
      klass <- lookupEntity Types (instanceClass inst) env;
      unless (isRole Class klass) (Left ("not a class: " ++ instanceClass inst));
      when shared (mapM_ (\method -> unless (Set.member compareEntity (Entity (owner klass) (fst method) (Method (spelling klass))) (sourceMethodVisible env)) (Left ("instance method is not visible: " ++ fst method))) (instanceMethods inst));
      originals <- if eqString (owner klass) "MLF.Primitive" then Prelude.standardDefaults (spelling klass) (instanceMethods inst) else Right (instanceMethods inst);
      methods <-
        mapM
          (\method ->
             do {
               name <-
                 termId names (Entity (owner klass) (fst method) (Method (spelling klass)));
               body <- resolveExpr names env (snd method);
               Right ((,) name body)
             })
          originals;
      context <- mapM (resolvePredicate names env) (instanceContext inst);
      name <- bindingSpelling names klass;
      head <- mapM (resolveType names env) (instanceHead inst);
      Right (R.Instance (instanceVariables inst) context name head methods)
    };
  renameModule names local env source = do {
    ds <- mapM (renameDatatype names local env) (sourceDatatypes source);
    cs <- mapM (renameClass names local env) (sourceClasses source);
    instances <- mapM (renameInstance (Lexer.isSharedSyntax (sourceSyntax source)) names env) (sourceInstances source);
    values <- mapM (\((,,) original annotation expression) -> do {
      entity <- lookupEntity Terms original local;
      i <- termId names entity;
      a <- resolveOptionalAnnotation names env annotation;
      mapEither (Dependency.Bound i a) (resolveExpr names env expression)
    }) (sourceValues source);
    body <- case sourceBody source of {
      Nothing -> Right Nothing; Just expression -> mapEither Just (resolveExpr names env expression)
    };
    Right (Renamed (bindingSymbols names) ds cs instances values body)
  };
  renamedSymbols (Renamed symbols _ _ _ _ _) = symbols;
  renamedDatatypes (Renamed _ ds _ _ _ _) = ds;
  resolvedClasses (Renamed _ _ cs _ _ _) = cs;
  resolvedInstances (Renamed _ _ _ instances _ _) = instances;
  renamedBindings (Renamed _ _ _ _ bindings _) = bindings;
  resolvedBody (Renamed _ _ _ _ _ body) = body;
  renamedClasses r = map (R.namedClass (Dependency.symbolName (renamedSymbols r))) (resolvedClasses r);
  renamedInstances r = map (R.namedInstance (Dependency.symbolName (renamedSymbols r))) (resolvedInstances r);
  renamedValueNames r = map (compose (Dependency.symbolName (renamedSymbols r)) Dependency.boundId) (renamedBindings r);
  renamedValues r = map (Dependency.boundValue (renamedSymbols r)) (renamedBindings r);
  renamedBody r = mapOptional (R.namedExpr (Dependency.symbolName (renamedSymbols r))) (resolvedBody r);
  resolvedSource (Resolved source _ _) = source;
  resolvedScope (Resolved _ env _) = env;
  resolvedContents (Resolved _ _ content) = content;
  resolvedExports mode entry =
    do {
      let {
        source = resolvedSource entry
      };
      declared <- locals source;
      let {
        local =
          if isBuiltinModule (moduleIdentity source)
          then union declared (interface (builtinEntities source))
          else declared
      };
      exportsFor mode source local (resolvedScope entry)
    };
  -- Run the original strict selectors after the namespace fixed point. This
  -- preserves private-name, missing-member and conflicting-export diagnostics.
  resolveOneWith mode names localMap exports source =
    do {
      local <-
        case M.lookup compareString (moduleIdentity source) localMap of {
          Nothing -> Left "missing module declarations";
          Just env -> Right env
        };
      env <-
        if eqString (moduleIdentity source) "MLF.Primitive"
        then Right local
        else scope mode exports source local;
      exported <- exportsFor mode source local env;
      validateSharedIdentities source env exported;
      renamed <-
        mapLeft (\message -> (sourcePath source ++ (": " ++ message)))
          (renameModule names local env source);
      Right (Resolved source env renamed)
    };
  -- External-only modules are leaf vertices. Publish only owners from the
  -- input table, using the existing name sets required by crate interfaces.
  moduleReach :: Map String (Set String) -> Map String (Set String);
  moduleReach direct =
    let {
      entries = M.toList (M.map Set.toList direct);
      leaves = concatMap (\entry -> map (\name -> (,) name []) (snd entry)) entries;
      graph = Dependency.moduleGraph (append leaves entries);
      nodes = Dependency.graphNodes graph;
      closed = Dependency.reachTable (Dependency.graphRows graph);
      reach name = case Dependency.graphId graph name of {
        Nothing -> panic "missing module reach owner";
        Just i -> Set.fromDistinctAscList
          (map (\j -> fst (V.at nodes (V.fromInt j))) (IS.toAscList (V.at closed i)))
      }
    } in M.mapWithKey (\name _ -> reach name) direct;
  crateReach mode modules =
    let {
      direct =
        M.fromList compareString
          (map
             (\source ->
                (,) (moduleIdentity source)
                  (Set.fromList compareString (append (if Lexer.isSharedSyntax (sourceSyntax source) then (:) "MLF.Primitive" [] else []) (map importedModule (importsFor mode source)))))
             modules)
    } in
    moduleReach direct;
  candidateScope reach instances ownerName =
    let {
      reachable = M.findWithDefault compareString Set.empty ownerName reach
    } in
    IS.fromList
      (catMaybes
         (mapIndexed
            (\index inst ->
               if Set.member compareString (fst inst) reachable then Just index else Nothing)
            instances));
  bindValues publicNames values expression =
    mapLeft (displayNames publicNames) (Surface.bindValues values expression);
  closeInstance publicNames values valueMap inst =
    mapLeft (displayNames publicNames) (Surface.closeSourceInstance values valueMap inst);
  resolveCrate :: PreludeMode ->
                  Map String Interface ->
                  (Entity -> String) -> [] SourceModule -> Either String ResolvedCrate;
  resolveCrate mode external mangle supplied =
    resolveCrateWithAllocator mode external
      (\_ entities ->
         Names
           (M.fromList compareEntity
              (map (\entity -> (,) entity (mangle entity)) (Set.toList entities))))
      supplied;
  data CrateResolution = CrateResolution PreludeMode ([] SourceModule)
    (Map String Interface) (Map String Interface) (Set Entity);
  resolveCrateWithAllocator :: PreludeMode ->
                               Map String Interface ->
                               ([] SourceModule -> Set Entity -> Names) ->
                               [] SourceModule -> Either String ResolvedCrate;
  -- An instance implements its class's methods even when those method names
  -- are intentionally omitted from the class's imported source namespace.
  resolveCrateWithAllocator mode external allocate supplied = do {
    plan <- prepareCrateResolution mode external supplied;
    resolveCratePlan allocate plan
  };
  prepareCrateResolution mode external supplied =
    if null supplied
    then Left "no entry module"
    else do {
           when
             (any
                (\source ->
                   (isBuiltinModule (moduleIdentity source) &&
                    not (eqString (sourcePath source) ("<" ++ (moduleIdentity source ++ ">")))))
                supplied)
             (Left "Prelude and MLF.Primitive are built-in modules and cannot be redefined");
           validateSharedModuleCycles supplied;
           let {
             identities = map moduleIdentity supplied
           };
           unless (length identities == length (nubBy eqString identities))
             (Left "duplicate source module");
           mapM_
             (\name ->
                when (M.member compareString name external)
                  (Left ("source module conflicts with external module: " ++ name)))
             identities;
           let {
             useFacade =
               any
                 (\source ->
                    (Lexer.isSharedSyntax (sourceSyntax source) || any (\entry -> eqString (importedModule entry) "MLF.Primitive")
                      (importsFor mode source)))
                 supplied
           };
           let {
             usePrelude =
               (useFacade ||
                any
                  (\source ->
                     any (\entry -> eqString (importedModule entry) "Prelude")
                       (importsFor mode source))
                  supplied)
           };
           let {
             withFacade =
               if (useFacade &&
                   (not (M.member compareString "MLF.Primitive" external) &&
                    not (elem eqString "MLF.Primitive" identities)))
               then (:) primitiveSource supplied
               else supplied
           };
           let {
             modules =
               if (usePrelude &&
                   (not (M.member compareString "Prelude" external) &&
                    not (elem eqString "Prelude" identities)))
               then (:) preludeSource withFacade
               else withFacade
           };
           localEntries <-
             mapM
               (\source ->
                  do {
                    local <- locals source;
                    Right
                      ((,) (moduleIdentity source)
                         (if isBuiltinModule (moduleIdentity source)
                          then union local (interface (builtinEntities source))
                          else local))
                  })
               modules;
           let {
             localMap = M.fromList compareString localEntries
           };
           let {
             exports = crateExports mode external localMap modules
           };
           methodEntities <-
             mapM
               (\source ->
                  do {
                    let {
                      local =
                        M.findWithDefault compareString emptyInterface (moduleIdentity source)
                          localMap
                    };
                    env <-
                      if isBuiltinModule (moduleIdentity source)
                      then Right local
                      else scope mode exports source local;
                    methods <-
                      mapM
                        (\inst ->
                           do {
                             klass <- lookupEntity Types (instanceClass inst) env;
                             Right
                               (map
                                  (\method ->
                                     Entity (owner klass) (fst method) (Method (spelling klass)))
                                  (instanceMethods inst))
                           })
                        (sourceInstances source);
                    Right (concat methods)
                  })
               modules;
           let {
             allEntities =
               Set.unions compareEntity
                 ((:) (visible primitiveScope)
                    (append (map (\entry -> visible (snd entry)) localEntries)
                       (append (map visible (M.elems external))
                          ((:) (Set.fromList compareEntity (concat methodEntities)) []))))
           };
           Right (CrateResolution mode modules localMap exports allEntities)
         };
  resolveCratePlan allocate (CrateResolution mode modules localMap exports allEntities) = do {
           let { bindings = resolveNames (allocate modules allEntities) };
           resolved <- mapM (resolveOneWith mode bindings localMap exports) modules;
           let { instances = concatMap (\entry -> map (\inst -> (,) (moduleIdentity (resolvedSource entry)) inst)
                    (resolvedInstances (resolvedContents entry))) resolved;
                 reach = crateReach mode modules;
                 scopes = M.fromList compareString (map (\source -> let { name = moduleIdentity source } in
                   (,) name (candidateScope reach instances name)) modules) };
           Right (ResolvedCrate bindings resolved scopes reach)
         };
  linkModules :: PreludeMode -> [] SourceModule -> Either String LinkedModule;
  linkModules mode supplied =
    do {
      crate <- resolveCrateWithAllocator mode M.empty freshNames supplied;
      let {
        publicNames = resolvedCrateDisplayNames crate
      };
      let {
        resolved = resolvedCrateModules crate
      };
      let {
        instances = resolvedInstanceRows crate
      };
      let {
        scopes = resolvedCrateValueScopes crate
      };
      let {
        ds = concatMap (\entry -> renamedDatatypes (resolvedContents entry)) resolved
      };
      let {
        cs = concatMap (\entry -> renamedClasses (resolvedContents entry)) resolved
      };
      let { bindings = boundIn crate resolved };
      let {
        entryModule = last resolved
      };
      entry <- entryExpr crate entryModule;
      body <- mapLeft (displayNames publicNames) (Surface.bindResolvedExpr bindings entry);
      instances' <- mapLeft (displayNames publicNames) (mapM
        (compose (Surface.closeResolvedInstance (Surface.helperScope bindings)) snd) instances);
      let {
        program =
          if (null cs && null instances')
          then SProgram ds body
          else SClassProgram ds cs instances' body
      };
      Right (LinkedModule program publicNames scopes (resolvedCrateInstanceScopes crate))
    };
  wordChar c = (U.isAlphaNum c || ((c == 95) || (c == 39)));
  wordEnd :: String -> Int -> Int;
  wordEnd text index =
    if ((index < stringLength text) && wordChar (stringCodeAt text index))
    then wordEnd text (index + 1)
    else index;
  displayFrom :: Map String String -> String -> Int -> String;
  displayFrom names text index =
    if (index >= stringLength text)
    then ""
    else let {
           code = stringCodeAt text index
         } in
         if wordChar code
         then let {
                end = wordEnd text index
              } in
              let {
                word = stringSlice text index (end - index)
              } in
              (M.findWithDefault compareString word word names ++ displayFrom names text end)
         else (stringFromCode code ++ displayFrom names text (index + 1));
  displayNames names text = displayFrom names text 0;
  -- Ordinary Haskell imports and lexical shadowing do not rebind syntax.
  validateSharedIdentities :: SourceModule -> Interface -> Interface -> Either String ();
  validateSharedIdentities _ _ _ = Right ();
  validateSharedModuleCycles :: [] SourceModule -> Either String ();
  validateSharedModuleCycles sources =
    let {
      groups =
        Dependency.groupNames (Dependency.moduleGraph
          (map (\source -> (,) (moduleIdentity source) (map importedModule (sourceImports source)))
             sources))
    } in
    mapM_
      (\group ->
         do {
           let {
             members = filter (\source -> elem eqString (moduleIdentity source) group) sources
           };
           let {
             cyclic =
               ((length group > 1) ||
                any
                  (\source ->
                     elem eqString (moduleIdentity source)
                       (map importedModule (sourceImports source)))
                  members)
           };
           when (cyclic && any (\source -> Lexer.isSharedSyntax (sourceSyntax source)) members)
             (Left ("shared implementation module cycle: " ++ intercalate ", " group))
         })
      groups
}
