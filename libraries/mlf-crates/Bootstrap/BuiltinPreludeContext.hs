-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.BuiltinPreludeContext
  (RawPrelude(..), PreparedPrelude, prepareFresh, checkCompilerPrelude,
   inputIdentity, rawTerm, interface, linked, names, environment, sourceValues,
   protectedNames, contracts, sourceExternals) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.SourceEquality as SourceEquality;

  -- RawPrelude is compiler-owned generated source data, not a serialized object
  -- format. Ordinary .mlfco loading still uses the complete Artifact admission.
  -- Its source identity is verified against fresh preparation by the build;
  -- the running compiler additionally checks its entire closed target term.
  data RawPrelude = RawPrelude String Int Artifact.CrateInterface XTerm
    (Map String ((,) XName XType)) Int Modules.Names Modules.Interface
    (Set String) (Set String) (Map String Source.SourceContract) ([] SourceModule);
  data PreparedPrelude = PreparedPrelude RawPrelude Checked.CheckedTerm Artifact.FragmentState;
  inputIdentity (RawPrelude identity _ _ _ _ _ _ _ _ _ _ _) = identity;
  rawTerm (RawPrelude _ _ _ term _ _ _ _ _ _ _ _) = term;
  interface (PreparedPrelude (RawPrelude _ _ iface _ _ _ _ _ _ _ _ _) _ _) = iface;
  linked (PreparedPrelude _ _ state) = state;
  names (PreparedPrelude (RawPrelude _ _ _ _ _ _ value _ _ _ _ _) _ _) = value;
  environment (PreparedPrelude (RawPrelude _ _ _ _ _ _ _ value _ _ _ _) _ _) = value;
  sourceValues (PreparedPrelude (RawPrelude _ _ _ _ _ _ _ _ value _ _ _) _ _) = value;
  protectedNames (PreparedPrelude (RawPrelude _ _ _ _ _ _ _ _ _ value _ _) _ _) = value;
  contracts (PreparedPrelude (RawPrelude _ _ _ _ _ _ _ _ _ _ value _) _ _) = value;

  -- This entry is for the fixed compiler literal only. It creates no unchecked
  -- CheckedTerm and does not replace the untrusted artifact loading APIs.
  checkCompilerPrelude raw = case raw of {
    RawPrelude identity primitiveCount iface term available serial storedNames storedEnv storedValues storedProtected storedContracts witnesses -> do {
      ensure (stringLength identity > 0) "prepared Prelude lacks a source identity";
      ensure (primitiveCount == length P.allPrimitives) "prepared Prelude primitive ABI is stale";
      ensure (eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity)
        "prepared Prelude builtin interface is stale";
      ensure (eqList SourceEquality.eqSourceModule witnesses canonicalSources)
        "prepared Prelude canonical source witness is stale";
      metadata <- prepareMetadata iface;
      case metadata of { Metadata expectedNames expectedEnv expectedValues expectedProtected expectedContracts -> do {
        ensure (sameNames storedNames expectedNames) "prepared Prelude source names are inconsistent";
        ensure (sameEnvironment storedEnv expectedEnv) "prepared Prelude source environment is inconsistent";
        ensure (sameSet eqString storedValues expectedValues) "prepared Prelude source value inventory is inconsistent";
        ensure (sameSet eqString storedProtected expectedProtected) "prepared Prelude protected inventory is inconsistent";
        ensure (sameMap eqString sameContract storedContracts expectedContracts)
          "prepared Prelude source contracts are inconsistent"
      } };
      checked <- Checked.check term;
      ensure (T.alphaEq (Checked.typeOf checked) (XCon "()" []))
        "prepared Prelude is not a closed declaration spine";
      inventory <- Checked.declarationBindings checked;
      let { inferred = M.fromList X.compareName inventory;
            signatures = M.fromList compareString (Artifact.crateBindings iface) };
      ensure (eqList eqString (M.keys available) (M.keys signatures))
        "prepared Prelude exported inventory mismatch";
      traverseEither (\((,) key ((,) name expected)) -> do {
        declared <- case M.lookup X.compareName name inferred of {
          Nothing -> Left ("prepared Prelude export is not a checked binder: " ++ key);
          Just ty -> Right ty
        };
        target <- case M.lookup compareString key signatures of {
          Nothing -> Left "prepared Prelude lost an exported contract";
          Just ty -> Right ty
        };
        ensure (T.alphaEq declared expected && T.alphaEq declared target)
          ("prepared Prelude export contract mismatch: " ++ key)
      }) (M.toList available);
      let { identities = IS.toList (Separate.termIdentities term IS.empty) };
      ensure (serial >= 0 && all (\identity -> identity < serial) identities)
        "prepared Prelude fresh serial overlaps its checked term";
      case term of {
        XWithData declarations body -> Right (PreparedPrelude raw checked
          (Artifact.FragmentState serial available ((:) body []) declarations S.empty));
        _ -> Left "prepared Prelude is missing its datatype context"
      }
    }
  };
  sameEntity a b = Modules.compareEntity a b == 0;
  intrinsic entity = elem sameEntity entity Modules.sharedPrimitiveEntities;
  callStackEntity = Modules.Entity "MLF.Primitive" "callStack" Modules.Value;
  -- Generation always takes the ordinary fresh builtin route. This module
  -- imports no generated constants, so regeneration cannot bootstrap from them.
  prepareFresh identity = do {
    object <- Artifact.builtinPrelude;
    prepareObject identity object
  };
  prepareObject :: String -> Artifact.CrateObject -> Either String RawPrelude;
  prepareObject identity object = do {
    let { iface = Artifact.objectInterface object };
    Artifact.validateInterface iface;
    ensure (eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity)
      "prepared Prelude is not the builtin crate";
    ensure (null (Artifact.crateDependencies iface) && eqString (Artifact.crateEntry iface) "")
      "prepared Prelude must have no dependencies or executable entry";
    let { byName = Artifact.interfaceMap ((:) iface []) };
    Artifact.validateDependencies byName iface;
    Artifact.validateExportBoundary byName iface;
    Artifact.validateLayouts ((:) iface []);
    let { layouts = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (Artifact.datatypePart d))
          (Artifact.crateLoweredData iface)) };
    linked <- Artifact.linkCrate byName layouts (Artifact.FragmentState 0 M.empty [] [] S.empty) object;
    metadata <- prepareMetadata iface;
    case metadata of { Metadata names env sourceValues protectedNames contracts -> do {
    body <- foldEither (\continuation declarations -> Separate.graft declarations continuation)
      (XConstructor "()" []) (Artifact.fragmentBodies linked);
    let { raw = RawPrelude identity (length P.allPrimitives) iface
      (XWithData (Artifact.fragmentData linked) body) (Artifact.fragmentBindings linked)
      (Artifact.fragmentSerial linked) names env sourceValues protectedNames contracts canonicalSources };
    checkCompilerPrelude raw;
    Right raw
    } }
  };
  canonicalSources = (:) Modules.preludeSource ((:) Modules.primitiveSource []);
  data Metadata = Metadata Modules.Names Modules.Interface (Set String) (Set String)
    (Map String Source.SourceContract);
  prepareMetadata iface = do {
    -- EXACT original standalone visible environment, not full crate exports.
    declared <- Modules.locals Modules.primitiveSource;
    let {
      env = Modules.union declared (Modules.interface Modules.sharedPrimitiveEntities);
      entities = S.toList (Modules.visible env);
      exports = concatMap snd (Artifact.crateExports iface);
      nameOf = Artifact.definitionName Artifact.builtinCrateIdentity;
      names = Modules.Names (M.fromList Modules.compareEntity (map (\e -> (,) e (nameOf e)) entities));
      sourceValues = S.fromList compareString
        (map nameOf (filter (\e -> Modules.isRole Modules.Value e && not (sameEntity e callStackEntity)) entities));
      sourceData = Artifact.crateData iface;
      loweredData = Artifact.crateLoweredData iface;
      classes = Artifact.crateClasses iface;
      protectedNames = S.fromList compareString (append (map fst (Artifact.crateBindings iface))
        (append (map fst (Artifact.crateInstances iface))
          (append (concatMap (\d -> (:) (D.datatypeName d) (map D.constructorName (D.datatypeConstructors d)))
                    (append sourceData loweredData))
            (append (map Modules.className classes) (concatMap (\c -> map fst (Modules.classMethods c)) classes)))))
    };
    -- Names follow the existing separate-lowering rule, never a displayed
    -- class spelling. Exact root-generated layout equality is checked again
    -- by mergeDeclaration after lowering, before the final independent check.
    traverseEither (\klass -> ensure
      (elem eqString ("Dict_" ++ Modules.className klass) (map D.datatypeName loweredData))
      ("installed Prelude missing authenticated dictionary layout: " ++ Modules.className klass)) classes;
    traverseEither (\entity -> do {
      ensure (intrinsic entity || elem sameEntity entity exports)
        ("installed Prelude lacks exact visible Entity: " ++ Modules.label entity);
      case Modules.role entity of {
        Modules.Value -> ensure (sameEntity entity callStackEntity ||
          elem eqString (nameOf entity) (map fst (Artifact.crateBindings iface)))
          ("installed Prelude missing value signature: " ++ Modules.label entity);
        Modules.Class -> ensure (elem eqString (nameOf entity) (map Modules.className classes))
          ("installed Prelude missing class identity: " ++ Modules.label entity);
        Modules.Method _ -> ensure (elem eqString (nameOf entity) (concatMap (\c -> map fst (Modules.classMethods c)) classes))
          ("installed Prelude missing method identity: " ++ Modules.label entity);
        Modules.Datatype -> ensure (elem eqString (nameOf entity) (map D.datatypeName sourceData))
          ("installed Prelude missing datatype identity: " ++ Modules.label entity);
        Modules.Constructor _ -> ensure (elem eqString (nameOf entity) (concatMap (\d -> map D.constructorName (D.datatypeConstructors d)) sourceData))
          ("installed Prelude missing constructor identity: " ++ Modules.label entity);
        _ -> ensure (intrinsic entity) "unsupported installed Prelude intrinsic Entity"
      }
    }) entities;
    contracts <- sourceContracts iface sourceValues;
    Right (Metadata names env sourceValues protectedNames contracts)
  };
  -- Preserve the canonical persistent-map shape as well as its entries. A
  -- stale size field must not affect later union/balance operations.
  sameMap eqKey eqValue first second = case (,) first second of {
    (,) MapEmpty MapEmpty -> True;
    (,) (MapNode a k v l r) (MapNode b k2 v2 l2 r2) ->
      a == b && eqKey k k2 && eqValue v v2 &&
        sameMap eqKey eqValue l l2 && sameMap eqKey eqValue r r2;
    _ -> False
  };
  sameSet equal (Set first) (Set second) = sameMap equal (\_ _ -> True) first second;
  sameNames (Modules.Names first) (Modules.Names second) = sameMap sameEntity eqString first second;
  sameEnvironment (Modules.Interface first) (Modules.Interface second) =
    sameMap (\a b -> Modules.compareKey a b == 0) (sameSet sameEntity) first second;
  sameContract (Source.SourceContract ty classes protected) (Source.SourceContract other others flag) =
    T.alphaEq ty other && eqList eqString classes others && protected == flag;
  sourceExternals iface sourceValues = let {
    dictionaries = M.fromList compareString
      (map (\c -> (,) ("Dict_" ++ Classes.className c) (Classes.className c)) (Artifact.crateClasses iface))
  } in M.mapWithKey (\name ty ->
    if S.member compareString name sourceValues then Separate.sourceScheme dictionaries ty
    else Separate.sourceSchemeIn M.empty False ty) (M.fromList compareString (Artifact.crateBindings iface));
  -- These flags govern managed evidence contraction, not graph quantifier
  -- rigidity. Carry complete source authority without invoking module-root
  -- compaction or replacing ordinary whole-root wanted closure.
  sourceContracts :: Artifact.CrateInterface -> Set String -> Either String (Map String Source.SourceContract);
  sourceContracts iface sourceValues = let {
    externals = sourceExternals iface sourceValues;
    protection = M.fromList compareString (Artifact.crateProtection iface)
  } in mapEither (M.fromList compareString) (traverseEither
    (\((,) name ty) -> do {
      source <- case M.lookup compareString name externals of {
        Nothing -> Left "prepared source dependency lacks an import contract";
        Just value -> Right value
      };
      flag <- case M.lookup compareString name protection of {
        Nothing -> Left "prepared source dependency lacks protection authority";
        Just value -> Right value
      };
      let { classes = case Classes.scheme source of {
        (,,) _ predicates _ -> map (\(SPredicate cls _) -> cls) predicates
      } };
      Right ((,) name (Source.SourceContract ty classes (flag || Classes.managedType source)))
    }) (Artifact.crateBindings iface));
}
