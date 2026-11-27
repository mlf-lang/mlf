-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.NativeCrate
  (Contract, nativeABI, contractIdentity, contractCrate, contractImports, contractExports,
   contractTags, emitLibrary, emitProgramFromInterfaces) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.CrateArtifact as A;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Traversal as Traversal;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.LLVM.Library as ABI;

  nativeABI :: String;
  nativeABI = "mlf-crate-boxed/1";
  -- The public product slots and factory arguments both use stable symbol order.
  -- A library has one physical getter slot containing this pure factory.
  data Contract = Contract String ABI.ExportLayout ABI.ExportLayout ([] ((,) String XType))
    ([] ((,) String ((,) Int Int)));
  contractIdentity (Contract _ layout _ _ _) = ABI.identity layout;
  contractCrate (Contract crate _ _ _ _) = crate;
  contractImports (Contract _ _ _ imports _) = imports;
  contractExports (Contract _ logical _ _ _) = map (\((,,) key _ ty) -> (,) key ty) (ABI.exports logical);
  contractTags (Contract _ _ _ _ tags) = tags;
  products (Contract _ logical _ _ _) = logical;
  physical (Contract _ _ factory _ _) = factory;
  factoryKey c = "mlf_crate_factory_" ++ contractIdentity c;
  factoryType c = foldr (\row rest -> XArrow (snd row) rest) (ABI.exportProductType (products c)) (contractImports c);
  requireKey key table = maybe (Left ("missing checked crate binding: " ++ key)) Right (M.lookup compareString key table);
  declarations closure = concatMap A.crateLoweredData closure;
  describe byName object identity = do {
    let { crate = A.crateId (A.objectInterface object) };
    fragments <- case object of {
      A.OpenCrateObject _ package -> Right (map snd (Open.packageFragments package));
      _ -> Left "native producer requires checked declaration groups"
    };
    let { own = M.fromList compareString (A.crateBindings (A.objectInterface object));
          foreignKeys = S.fromList compareString (concatMap (\f -> map (compose X.nameHint fst)
            (Open.parameters f)) fragments) };
    describeInterface byName crate identity (filter (\key -> not (M.member compareString key own)) (S.toList foreignKeys))
  };
  -- The body's required keys are certified by its producer. Reconstruct every
  -- slot and type from the actual checked interface closure before using them.
  describeInterface byName crate identity required = do {
    iface <- requireKey crate byName;
    ensure (eqString (A.crateEntry iface) "") "native producer requires a library crate";
    closure <- A.dependencyClosure byName [] [] [crate];
    let { own = M.fromList compareString (A.crateBindings iface);
          external = filter (\i -> not (eqString crate (A.crateId i))) closure;
          bindings = M.fromList compareString (concatMap A.crateBindings external);
          ds = declarations closure;
          rows = map (\((,) key ty) -> (,,) key (C.targetNameHint key) ty) (M.toList own) };
    ensure (eqList eqString required (S.toList (S.fromList compareString required)))
      "native factory imports are not unique and ordered";
    ensure (not (M.null own)) "native crate has no value exports";
    imports <- traverseEither (\key -> mapEither ((,) key) (requireKey key bindings)) required;
    logical <- ABI.prepareLayout identity rows ds;
    let { key = "mlf_crate_factory_" ++ identity;
          ty = foldr (\row rest -> XArrow (snd row) rest) (ABI.exportProductType logical) imports };
    factory <- ABI.prepareLayout identity [(,,) key key ty] ds;
    tags <- ABI.crateConstructorTags ds;
    Right (Contract crate logical factory imports (M.toList tags))
  };
  emptyState serial bindings ds = A.FragmentState serial bindings [] ds S.empty;
  numberImports signatures = zipWith (\i ((,) key ty) -> (,) key ((,) (XName i (C.targetNameHint key)) ty))
    (range 0 (length signatures - 1)) signatures;
  closeBodies state entry = foldEither (\rest spine -> Separate.graft spine rest) entry (A.fragmentBodies state);
  bindParameters rows body = foldr (\((,) _ ((,) name ty)) rest -> XAbs name ty rest) body rows;
  -- Native providers depend on checked headers. Only the owner's declaration
  -- groups are executable inputs to its factory.
  emitLibrary :: String -> [] A.CrateInterface -> A.CrateObject -> Either String (Either String ((,) ([] String) Contract));
  emitLibrary identity headers object = do {
    let { target = A.objectInterface object; crate = A.crateId target };
    context <- prepareContext headers [object] crate;
    case context of { A.EnvelopeKnownObjects ordered byName _ _ layouts -> do {
      index <- A.openIndex ordered [object];
      case describe byName object identity of {
        Left reason -> Right (Left reason);
        Right c -> do {
          let { imports = numberImports (contractImports c);
                ds = ABI.declarations (products c);
                start = emptyState (length imports) (M.fromDistinctAscList imports) ds };
          state <- A.linkIndexedCrate index Nothing layouts start target;
          product <- ABI.exportProduct (products c) (A.fragmentBindings state);
          body <- closeBodies state product;
          let { worker = bindParameters imports body;
                name = XName (A.fragmentSerial state) (factoryKey c) };
          outer <- ABI.exportProduct (physical c) (M.singleton (factoryKey c) ((,) name (factoryType c)));
          checked <- Checked.check (XWithData ds (XLet name worker outer));
          case ABI.closedCrateTypes (physical c) checked of {
            Left reason -> Right (Left reason);
            Right () -> do {
              chunks <- ABI.emitCrateLibrary (physical c) checked;
              Right (Right ((,) chunks c))
            }
          }
        }
      }
    } }
  };

  -- Visit the actual declaration graph. Reaching any native export requires
  -- its factory's exact external arguments. IR groups keep their own edges.
  nativeReach (A.OpenIndex ids rows producer _) contracts roots = do {
    let { slot = A.openDecl ids };
    native <- traverseEither (\c -> do {
      ins <- traverseEither (compose slot fst) (contractImports c);
      outs <- traverseEither (compose slot fst) (contractExports c);
      Right (map (\d -> (,) (V.toInt d) ((,) (contractCrate c) ins)) outs)
    }) contracts;
    seeds <- traverseEither slot roots;
    let { factories = IM.fromList (concat native);
          visit seen groups active pending = case pending of {
            [] -> (,,) seen groups active;
            (:) d rest -> let { i = V.toInt d; next = IS.insert i seen } in
              if IS.member i seen then visit seen groups active rest else case IM.lookup i factories of {
                Just ((,) crate inputs) -> if S.member compareString crate active
                  then visit next groups active rest
                  else visit next groups (S.insert compareString crate active) (append inputs rest);
                Nothing -> case IM.lookup i producer of {
                  Nothing -> visit next groups active rest;
                  Just group -> if IS.member (V.toInt group) groups then visit next groups active rest
                    else case V.at rows group of { A.IndexedFragment _ _ inputs _ ->
                      visit next (IS.insert (V.toInt group) groups) active (append inputs rest) }
                }
              }
          } };
    Right (visit IS.empty IS.empty S.empty seeds)
  };

  -- The applied factory is one shared lazy binding. Projections preserve
  -- field laziness and have the exact source declaration's checked type.
  bindFactory ids needed c binder (A.FragmentState serial bindings bodies ds groups) = do {
    args <- traverseEither (\((,) key expected) -> do {
      (,) name ty <- requireKey key bindings;
      ensure (T.alphaEq ty expected) ("native factory argument type changed: " ++ key);
      Right (XVarTerm name)
    }) (contractImports c);
    let { product = XName serial "nativeCrateProduct";
          selected = filter (\row -> case M.lookup compareString (fst row) ids of {
            Nothing -> False; Just d -> IS.member (V.toInt d) needed }) (contractExports c);
          project ((,,) next table definitions) ((,) key ty) = do {
            (,) end rhs <- ABI.projectExport (products c) key next (XVarTerm product);
            let { name = XName end (C.targetNameHint key) };
            Right ((,,) (end + 1) (M.insert compareString key ((,) name ty) table) ((:) ((,) name rhs) definitions))
          } };
    (,,) end table defs <- foldEither project ((,,) (serial + 1) bindings []) selected;
    let { tail = foldl (\rest ((,) name rhs) -> XLet name rhs rest) (XConstructor "()" []) defs;
          spine = XLet product (foldl XApp (XVarTerm binder) args) tail };
    Right (A.FragmentState end table ((:) spine bodies) ds groups)
  };
  data ProgramAttempt = MissingBodies ([] String) | ProgramAttempt (Set String) (Set String) (Either String ([] String));
  decision :: Set String -> Set String -> Map String String -> String -> (,,) String String String;
  decision native checked reasons crate =
    if S.member compareString crate native then (,,) crate "native" "reachable export with a matching checked crate ABI"
    else if S.member compareString crate checked then (,,) crate "ir"
      (M.findWithDefault compareString "using checked implementation" crate reasons)
    else (,,) crate "unused" "no implementation required by the checked root";
  rejectionReasons choices = M.fromList compareString (mapMaybe (\row -> case snd row of {
    Left why -> Just ((,) (fst row) why); Right _ -> Nothing }) choices);
  admittedContracts choices = mapMaybe (\row -> case snd row of { Right c -> Just c; Left _ -> Nothing }) choices;
  multiplicities keys = M.fromListWith compareString (\x y -> x + y) (map (\key -> (,) key 1) keys);
  reportOwners requested root ordered = let { named = S.fromList compareString requested } in
    append requested (filter (\owner -> not (eqString owner root || S.member compareString owner named))
      (map A.crateId ordered));
  uniqueRequest :: String -> String -> Map String Int -> Map String Int -> Either String ();
  uniqueRequest crate identity owners identities = ensure
    (M.findWithDefault compareString 0 crate owners == 1 && M.findWithDefault compareString 0 identity identities == 1)
    "duplicate native crate or ABI identity";
  emitMixed (A.EnvelopeKnownObjects ordered byName objectMap admitted layouts) index@(A.OpenIndex ids _ _ _) root contracts = do {
    iface <- requireKey root byName;
    ensure (not (eqString (A.crateEntry iface) "")) "native program requires a crate entry";
    let { actual = mapMaybe (\i -> M.lookup compareString (A.crateId i) objectMap) ordered;
          opaque = filter (compose not A.openMarked) actual };
    opaqueDeps <- traverseEither (\o -> A.dependencyClosure byName [] []
      (map A.dependencyId (A.crateDependencies (A.objectInterface o)))) opaque;
    let { -- Elaborate the checked entry once against fresh names. The class
          -- resolver may consider selectors or dictionaries it never actually
          -- reads. Only the final witnesses are roots of the group graph.
          signatures = A.entrySignatures (A.crateEntry iface) (concatMap A.crateBindings ordered);
          aliases = numberImports signatures };
    charged <- A.envelopePrechargeEntry root admitted ordered;
    entry <- seq charged (A.linkEntry (length aliases) ordered iface (M.fromList compareString aliases) (A.crateEntry iface));
    let { reads = S.fromList X.compareName (Traversal.freeNames entry);
          usedAliases = filter (\row -> S.member X.compareName (fst (snd row)) reads) aliases;
          roots = append (map fst usedAliases) (concatMap (compose (map fst) A.crateBindings) (concat opaqueDeps));
          firstFactory = Separate.maximumTermIdentity (length aliases - 1) entry + 1 };
    (,,) needed groups active <- nativeReach index contracts roots;
    let { offered = S.fromList compareString (map contractCrate contracts);
          absent i = not (M.member compareString (A.crateId i) objectMap || S.member compareString (A.crateId i) offered);
          referenced i = any (\binding -> case M.lookup compareString (fst binding) ids of {
            Just d -> IS.member (V.toInt d) needed; Nothing -> False }) (A.crateBindings i);
          missing = map A.crateId (filter (\i -> absent i && referenced i) ordered);
          fromIR = S.fromList compareString (append (map (compose A.crateId A.objectInterface) opaque)
            (map A.crateId (filter (\i -> not (S.member compareString (A.crateId i) offered) && referenced i) ordered))) };
    if not (null missing) then Right (MissingBodies missing) else Right (ProgramAttempt active fromIR (do {
      let { selected = filter (\c -> S.member compareString (contractCrate c) active) contracts;
          numbered = zipWith (\i c -> (,) c (XName i (factoryKey c))) (range firstFactory (firstFactory + length selected - 1)) selected;
          factories = M.fromList compareString (map (\pair -> (,) (contractCrate (fst pair)) pair) numbered);
          program = Just ((,) index (Just groups));
          initial = emptyState (firstFactory + length selected) M.empty (declarations ordered);
          link ((,) state admission) i = let { crate = A.crateId i } in case M.lookup compareString crate factories of {
            Just ((,) c name) -> mapEither (\result -> (,) result admission) (bindFactory ids needed c name state);
            Nothing -> if S.member compareString crate offered || absent i then Right ((,) state admission) else do {
              object <- requireKey crate objectMap;
              case M.lookup compareString crate admission of {
                Nothing -> mapEither (\s -> (,) s admission) (A.linkProgramCrate program byName layouts state object);
                Just (A.EnvelopeLinkArtifact evidence digest) -> do {
                  result <- A.envelopeLinkCrateWithSpinePrepared byName layouts
                    ((,) state (Left "native root checks the final composition")) evidence;
                  case result of { A.EnvelopeLinkState next _ pool budget ->
                    Right ((,) next (M.insert compareString crate
                      (A.EnvelopeLinkArtifact (A.envelopeReplaceAdmission pool budget evidence) digest) admission)) }
                }
              }
            }
          } };
    (,) linked _ <- foldEither link ((,) initial charged) ordered;
    substitutions <- traverseEither (\((,) key ((,) alias expected)) -> do {
      (,) actualName ty <- requireKey key (A.fragmentBindings linked);
      ensure (T.alphaEq ty expected) ("entry argument type mismatch: " ++ key);
      Right ((,) alias actualName)
    }) usedAliases;
    let { replacements = M.fromList X.compareName substitutions;
          renamed = Separate.mapTerm (\n -> M.findWithDefault X.compareName n n replacements) id entry };
    body <- closeBodies linked renamed;
    let { wrapped = foldr (\((,) c name) rest -> XAbs name (factoryType c) rest) body numbered };
    checked <- Checked.check (XWithData (A.fragmentData linked) wrapped);
    if null selected then do {
      T.checkExecutableType (Checked.typeOf checked);
      LLVM.emitCheckedChunks False checked
    } else ABI.emitCrateExecutable (map (\c -> (,) (physical c) (factoryKey c)) selected) checked
    }))
  };

  prepareContext headers objects root = do {
    A.uniqueNames "crate interface" (map A.crateId headers);
    let { metadata = A.interfaceMap headers;
          supplied = S.fromList compareString (map (compose A.crateId A.objectInterface) objects);
          external = filter (\iface -> not (S.member compareString (A.crateId iface) supplied)) headers };
    traverseEither (\o -> let { iface = A.objectInterface o } in do {
      header <- requireKey (A.crateId iface) metadata;
      ensure (A.sameAdmittedInterface header iface) "checked implementation differs from the supplied interface"
    }) objects;
    ensure (S.member compareString root supplied) "native compilation requires its checked root object";
    A.envelopePrepareObjectInputs external objects [root] True
  };

  -- A joint attachment can fail only after combining individually admitted
  -- factories. Probe checked alternatives already in memory before asking for
  -- another body. A probed provider is still eligible to join the final link.
  selectProgram :: ([] Contract -> Either String ProgramAttempt) -> Map String A.CrateObject ->
    [] Contract -> Map String String -> [] String ->
    Either String (Either ([] ((,) String String)) ((,) ([] String) ([] ((,,) String String String))));
  selectProgram probe available eligible rejections owners = let {
    report reasons used checked chunks = Right (Right ((,) chunks (map (decision used checked reasons) owners)));
    need missing = Right (Left (map (\crate -> (,) crate (M.findWithDefault compareString
      "reachable checked implementation required" crate rejections)) missing));
    withReason why candidate = M.insert compareString (contractCrate candidate) why;
    recover used why = let {
      canSwap c = S.member compareString (contractCrate c) used && M.member compareString (contractCrate c) available;
      optional = filter canSwap eligible;
      required = filter (compose not canSwap) eligible;
      requestNative active reason = let {
        missing = filter (\crate -> not (M.member compareString crate available)) (S.toList active)
      } in if null missing then Left reason else Right (Left (map (\crate -> (,) crate reason) missing));
      -- With a compatible baseline, reattach each available provider. A
      -- rejected candidate cannot discard one already admitted in this link.
      add ((,,) kept reasons lastGood) c = do {
        let { candidates = snoc kept c };
        check <- probe candidates;
        case check of {
          ProgramAttempt native ir (Right chunks) -> Right ((,,) candidates reasons ((,,) native ir chunks));
          ProgramAttempt _ _ (Left reason) -> Right ((,,) kept (withReason reason c reasons) lastGood);
          MissingBodies _ -> Right ((,,) kept (withReason why c reasons) lastGood)
        }
      };
      baseline = do {
        checkedOnly <- probe required;
        case checkedOnly of {
          MissingBodies missing -> need missing;
          ProgramAttempt active _ (Left reason) -> requestNative active reason;
          ProgramAttempt native ir (Right chunks) -> do {
            (,,) _ reasons ((,,) kept usedIR output) <- foldEither add
              ((,,) required rejections ((,,) native ir chunks)) optional;
            report reasons kept usedIR output
          }
        }
      };
      -- Try a single demotion first. This preserves the other native-only
      -- providers even when their checked fallback is unavailable.
      removeOne pending = case pending of {
        [] -> baseline;
        (:) c rest -> do {
          alternative <- probe (filter (\other -> not (eqString (contractCrate other) (contractCrate c))) eligible);
          case alternative of {
            ProgramAttempt native ir (Right chunks) -> report (withReason why c rejections) native ir chunks;
            _ -> removeOne rest
          }
        }
      }
    } in case optional of {
      [] -> requestNative used why;
      [_] -> baseline;
      _ -> removeOne optional
    }
  } in do {
    result <- probe eligible;
    case result of {
      MissingBodies missing -> need missing;
      ProgramAttempt used checked (Right chunks) -> report rejections used checked chunks;
      ProgramAttempt used _ (Left why) -> if S.null used then Left why else recover used why
    }
  };

  -- Package tooling authenticates the producer contract and machine object
  -- before this call. Only the checked interface is required for an accepted
  -- native provider. MissingBodies explicitly requests a lazy checked fallback.
  emitProgramFromInterfaces :: (Contract -> Either String ()) -> [] ((,,) String String ([] String)) ->
    [] A.CrateInterface -> [] A.CrateObject -> String ->
    Either String (Either ([] ((,) String String)) ((,) ([] String) ([] ((,,) String String String))));
  emitProgramFromInterfaces verify requests headers objects root = do {
    context <- prepareContext headers objects root;
    case context of { A.EnvelopeKnownObjects ordered byName objectMap _ _ -> do {
      let { closure = S.fromList compareString (map A.crateId ordered);
            actual = mapMaybe (\i -> M.lookup compareString (A.crateId i) objectMap) ordered;
            owners = map (\((,,) crate _ _) -> crate) requests;
            ownerCounts = multiplicities owners;
            identities = multiplicities (map (\((,,) _ identity _) -> identity) requests);
            admit ((,,) crate identity keys) = do {
              ensure (not (eqString crate root) && S.member compareString crate closure)
                "candidate is outside the root's dependencies";
              uniqueRequest crate identity ownerCounts identities;
              c <- describeInterface byName crate identity keys;
              verify c;
              Right c
            };
            choices = zip owners (map admit requests);
            eligible = admittedContracts choices;
            rejections = rejectionReasons choices };
      index <- A.openIndex ordered actual;
      selectProgram (emitMixed context index root) objectMap eligible rejections (reportOwners owners root ordered)
    } }
  }
}
