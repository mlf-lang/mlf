-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Separate where {
  import MLF.Primitive;
  import qualified Bootstrap.Lexer as Lexer;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.NameEncoding as NameEncoding;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.SourceEquality as SourceEquality;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  data UnitInterface =
    UnitInterface String ([] ((,) String String)) ([] Modules.Entity) ([] DataDecl) ([]
                                                                                            SClassDecl) ([]
                                                                                                         ((,)
                                                                                                          String
                                                                                                          SInstanceDecl)) ([]
                                                                                                                           ((,)
                                                                                                                            String
                                                                                                                            XType)) String;
  data UnitObject =
    UnitObject UnitInterface XTerm | CheckedUnitObject UnitInterface Checked.CheckedTerm;
  unitName (UnitInterface n _ _ _ _ _ _ _) = n;
  unitDependencies (UnitInterface _ ds _ _ _ _ _ _) = ds;
  unitExports (UnitInterface _ _ es _ _ _ _ _) = es;
  unitData (UnitInterface _ _ _ ds _ _ _ _) = ds;
  unitClasses (UnitInterface _ _ _ _ cs _ _ _) = cs;
  unitInstances (UnitInterface _ _ _ _ _ is _ _) = is;
  unitBindings (UnitInterface _ _ _ _ _ _ bs _) = bs;
  unitObjectFingerprint (UnitInterface _ _ _ _ _ _ _ h) = h;
  objectInterface object =
    case object of {
      UnitObject i _ -> i;
      CheckedUnitObject i _ -> i
    };
  objectTerm object =
    case object of {
      UnitObject _ t -> t;
      CheckedUnitObject _ checked -> Checked.term checked
    };
  objectChecked :: UnitObject -> Either String Checked.CheckedTerm;
  objectChecked object =
    case object of {
      UnitObject _ term -> Checked.check term;
      CheckedUnitObject _ checked -> Right checked
    };
  -- Each scalar ends in an underscore. Reuse that complete field for
  -- ASCII identifiers while retaining decimal scalar spellings for Unicode.
  encodedAscii :: V.IndexVec Int String;
  encodedAscii = V.fromList (map (\code -> showInt code ++ "_") (range 0 127));
  encodedFrom :: String -> Int -> String;
  encodedFrom text start = let {
    end = stringLength text;
    fields i = if i >= end then [] else let {
      code = stringCodeAt text i; rest = fields (i + 1)
    } in if code < 128 then (:) (V.at encodedAscii (V.fromInt code)) rest
      else (:) (showInt code) ((:) "_" rest)
  } in concatStringList (fields start);
  encodedChunks text i = if i >= stringLength text then []
    else (:) (showInt (stringCodeAt text i)) ((:) "_" (encodedChunks text (i + 1)));
  compactName text = NameEncoding.compactName text;
  queryGroupName crateId members = "Query_" ++ encoded crateId ++ "z_" ++ encoded (head members);
  -- Open-fragment owners are wire text, not generated source identifiers.
  -- Frame the full canonical ownership set once instead of escaping its
  -- already escaped declaration names. The legacy unit format stays separate.
  openGroupName crateId members = pack ["MLF-OPEN-GROUP-1",crateId,pack (sortBy compareString members)];
  -- The previous owner spelling remains available for explicit admission.
  compactOpenGroupNameV2 crateId = let {
    suffix = encoded crateId ++ "z_";
    valuePrefix = "module_" ++ suffix; typePrefix = "Module_" ++ suffix;
    begins prefix text = stringLength text >= stringLength prefix &&
      eqString prefix (stringSlice text 0 (stringLength prefix));
    after prefix text = stringSlice text (stringLength prefix) (stringLength text - stringLength prefix);
    member text = if begins valuePrefix text then pack ["value",after valuePrefix text]
      else if begins typePrefix text then pack ["type",after typePrefix text]
      else pack ["raw",text]
  } in \members -> pack ["MLF-OPEN-GROUP-2",crateId,pack (map member (sortBy compareString members))];
  -- Version 3 factors the compact declaration-name prefix. The complete crate
  -- and entity suffix remain; other names are framed verbatim. Sort before
  -- factoring so the owner preserves the complete canonical member inventory.
  compactOpenGroupName crateId = let {
    suffix = compactName crateId ++ "_";
    valuePrefix = "module_c1_" ++ suffix; typePrefix = "Module_c1_" ++ suffix;
    begins prefix text = stringLength text >= stringLength prefix &&
      eqString prefix (stringSlice text 0 (stringLength prefix));
    after prefix text = stringSlice text (stringLength prefix) (stringLength text - stringLength prefix);
    member text = if begins valuePrefix text then pack ["value",after valuePrefix text]
      else if begins typePrefix text then pack ["type",after typePrefix text]
      else pack ["raw",text]
  } in \members -> pack ["MLF-OPEN-GROUP-3",crateId,pack (map member (sortBy compareString members))];
  encoded text = encodedFrom text 0;
  canonicalPreludeConstructor entity =
    (eqString (Modules.owner entity) "Prelude" &&
     (case Modules.role entity of {
       Modules.Constructor parent ->
         any (\d -> eqString parent (D.datatypeName d) &&
                    any (\c -> eqString (Modules.spelling entity) (D.constructorName c))
                        (D.datatypeConstructors d)) D.sourceBuiltinDeclarations;
       _ -> False
     }));
  managedBuiltinName :: Modules.Entity -> Maybe String;
  managedBuiltinName entity =
    if eqString (Modules.owner entity) "MLF.Primitive"
    then case Modules.role entity of {
      Modules.ManagedConstraint ->
        if eqString (Modules.spelling entity) "HasCallStack" then Just "MLFHasCallStack" else Nothing;
      Modules.BuiltinType ->
        if eqString (Modules.spelling entity) "CallStack" then Just "MLFCallStack" else Nothing;
      Modules.Value ->
        if eqString (Modules.spelling entity) "callStack" then Just "mlfCallStack" else Nothing;
      _ -> Nothing
    }
    else Nothing;
  stableName entity =
    case managedBuiltinName entity of {
      Just name -> name;
      Nothing -> ordinaryStableName entity
    };
  ordinaryStableName entity =
    if (Modules.isRole Modules.BuiltinType entity || canonicalPreludeConstructor entity)
    then Modules.spelling entity
    else ((if ((Modules.compareSpace (Modules.space entity) Modules.Types == 0) ||
               (case Modules.role entity of {
                  Modules.Constructor _ -> True;
                  _ -> False
                }))
           then "Module_"
           else "module_") ++
          (encoded (Modules.owner entity) ++ ("z_" ++ encoded (Modules.spelling entity))));
  mainName n = stableName (Modules.Entity n "main" Modules.Value);
  managedIntrinsicName n = eqString n "$MLF.Stack.callStack";
  hygieneName env n =
    if managedIntrinsicName n then n else M.findWithDefault compareString n n env;
  hygieneBinderPrefix :: String;
  hygieneBinderPrefix = "separateLocal";
  hygieneBind env names =
    do {
      pairs <-
        mapM
          (\n ->
             do {
               new <- freshName hygieneBinderPrefix;
               freshPure ((,) n new)
             })
          names;
      -- Infix markers and prefix uses must name the same lexical binder
      -- after freshening, so resolution can enforce the canonical operator.
      let { markers = map (\((,) n fresh) -> (,) ("$MLF.Infix." ++ n) ("$MLF.Infix." ++ fresh))
              (filter (\pair -> Set.member compareString (fst pair) Lexer.sharedValueOperatorSet) pairs) };
      freshPure (M.union compareString (M.fromList compareString (append pairs markers)) env)
    };
  hygieneRef env ref = case ref of {
    LexicalRef n -> LexicalRef (hygieneName env n);
    DeclRef _ _ -> ref
  };
  hygienePattern :: Map String String -> SPattern -> SPattern;
  hygienePattern env p =
    case p of {
      SDefaultPattern n -> SDefaultPattern (mapMaybeValue (hygieneName env) n);
      SConstructorPattern c ns -> SConstructorPattern c (map (mapMaybeValue (hygieneName env)) ns);
      SNestedPattern c ps -> SNestedPattern c (map (hygienePattern env) ps);
      SAnnotatedPattern n a -> SAnnotatedPattern (hygieneName env n) a;
      SOverloadedStringPattern s equal fromString ->
        SOverloadedStringPattern s (hygieneName env equal) (hygieneName env fromString);
      SIndexedStringPattern t eq from -> SIndexedStringPattern t (hygieneRef env eq) (hygieneRef env from);
      SAsPattern n pattern -> SAsPattern (hygieneName env n) (hygienePattern env pattern);
      SLazyPattern pattern -> SLazyPattern (hygienePattern env pattern);
      _ -> p
    };
  -- A binder-free application keeps the local name supply unchanged. Resolve
  -- just its lexical occurrences, retaining locations and declared IDs.
  plainHygiene term = case term of {
    SApp f a -> plainHygiene f && plainHygiene a;
    SCallSite _ _ e -> plainHygiene e;
    SVar _ -> True; SGlobal _ _ -> True; SPrimitive _ -> True; SConstructor _ -> True;
    SIntLit _ -> True; SBoolLit _ -> True; SDoubleLit _ -> True; SStringLit _ -> True;
    _ -> False
  };
  renamePlain env term = case term of {
    SApp f a -> SApp (renamePlain env f) (renamePlain env a);
    SCallSite n span e -> SCallSite n span (renamePlain env e);
    SVar n -> SVar (hygieneName env n);
    _ -> term
  };
  -- A parsed application needs a new node only on a path to a renamed
  -- lexical occurrence. Keep its original source spans and untouched
  -- operands. General callers retain the original lazy tree mapping.
  renameParsedPlain env expression = let {
    -- A lexical name has one replacement in this scope. Keep its variable
    -- leaf with the lookup result so every occurrence can share both.
    replacement = M.lookupProjected compareString (\_ name -> SVar name) env;
    changed term = case term of {
      SVar name -> if managedIntrinsicName name then Nothing else replacement name;
      SCallSite label span body -> mapOptional (SCallSite label span) (changed body);
      SApp f a -> case changed f of {
        Nothing -> mapOptional (SApp f) (changed a);
        Just function -> Just (SApp function (fromMaybe a (changed a)))
      };
      _ -> Nothing
    }
  } in fromMaybe expression (changed expression);
  hygieneApplication env term = hygieneApplicationWith hygieneIn env term;
  hygieneApplicationWith walk env term = let {
    child expression = case expression of {
      SApp f a -> do { x <- child f; y <- child a; freshPure (SApp x y) };
      SCallSite n span e -> do { b <- child e; freshPure (SCallSite n span b) };
      _ -> walk env expression
    }
  } in child term;
  hygieneIn :: Map String String -> SExpr -> Fresh SExpr;
  hygieneIn env expression = hygieneWith renamePlain env expression;
  hygieneWith rename env expression = let { walk = hygieneWith rename } in case expression of {
      SVar n -> freshPure (SVar (hygieneName env n));
      SGlobal _ _ -> freshPure expression;
      SGivenScope names body -> do {
        inner <- walk env body;
        freshPure (SGivenScope (map (hygieneName env) names) inner)
      };
      SWantedScope _ _ -> freshPure expression;
      SWantedRefs n cs -> freshPure (SWantedRefs n (map (\((,) role r) -> (,) role (hygieneRef env r)) cs));
      SDeclScope ids enclosed -> do {
        b <- case enclosed of {
          SLam n a body -> do { x <- walk env body; freshPure (SLam n a x) };
          SLet n a body -> do { x <- walk env a; y <- walk env body; freshPure (SLet n x y) };
          SLetRec ds body -> do {
            defs <- mapM (\((,,) n mode rhs) -> do { x <- walk env rhs; freshPure ((,,) n mode x) }) ds;
            x <- walk env body; freshPure (SLetRec defs x)
          };
          _ -> freshFail "invalid declaration binder in separate compilation"
        };
        freshPure (SDeclScope ids b)
      };
      SLam n a b ->
        do {
          scope <- hygieneBind env ((:) n []);
          body <- walk scope b;
          freshPure (SLam (hygieneName scope n) a body)
        };
      SBindDictionaries names body -> do {
        scope <- hygieneBind env names;
        inner <- walk scope body;
        freshPure (SBindDictionaries (map (hygieneName scope) names) inner)
      };
      SApp _ _ -> if plainHygiene expression
        then freshPure (if M.null env then expression else rename env expression)
        else hygieneApplicationWith walk env expression;
      SApplyDictionaries f names -> freshPure
        (SApplyDictionaries (hygieneRef env f) (map (hygieneName env) names));
      SLet n a b ->
        do {
          scope <- hygieneBind env ((:) n []);
          x <- walk env a;
          y <- walk scope b;
          freshPure (SLet (hygieneName scope n) x y)
        };
      SAnn a t ->
        do {
          x <- walk env a;
          freshPure (SAnn x t)
        };
      SSignature a t ->
        do {
          x <- walk env a;
          freshPure (SSignature x t)
        };
      SLetRec ds b ->
        do {
          scope <- hygieneBind env (map (\((,,) n _ _) -> n) ds);
          definitions <-
            mapM
              (\((,,) n mode a) ->
                 do {
                   x <- walk scope a;
                   freshPure ((,,) (hygieneName scope n) mode x)
                 })
              ds;
          body <- walk scope b;
          freshPure (SLetRec definitions body)
        };
      SCase a bs ->
        do {
          scrutinee <- walk env a;
          branches <-
            mapM
              (\(SAlternative p b) ->
                 do {
                   scope <- hygieneBind env (Surface.patternVariables p);
                   body <- walk scope b;
                   freshPure (SAlternative (hygienePattern scope p) body)
                 })
              bs;
          freshPure (SCase scrutinee branches)
        };
      SEquations rows ->
        do {
          rows2 <-
            mapM
              (\((,) ps b) ->
                 do {
                   scope <- hygieneBind env (concatMap Surface.patternVariables ps);
                   body <- walk scope b;
                   freshPure ((,) (map (hygienePattern scope) ps) body)
                 })
              rows;
          freshPure (SEquations rows2)
        };
      SSourceDefinition body ->
        do { result <- walk env body; freshPure (SSourceDefinition result) };
      SCallSite label span body ->
        do { result <- walk env body; freshPure (SCallSite label span result) };
      SSharedBind pattern action continuation bindMethod failure ->
        do {
          scope <- hygieneBind env (Surface.patternVariables pattern);
          action2 <- walk env action;
          continuation2 <- walk scope continuation;
          bindMethod2 <- walk env bindMethod;
          failure2 <- walk env failure;
          freshPure (SSharedBind (hygienePattern scope pattern) action2 continuation2 bindMethod2 failure2)
        };
      SChecked ty body -> do { inner <- walk env body; freshPure (SChecked ty inner) };
      SWanted dict candidates -> freshPure (SWanted dict
        (map (\((,) role name) -> (,) role (hygieneName env name)) candidates));
      SDo _ _ -> walk env (Desugar.desugarDo expression);
      _ -> freshPure expression
    };
  hygiene expression = runFresh (Desugar.allNames expression) (hygieneIn M.empty expression);
  mapMaybeValue f value =
    case value of {
      Nothing -> Nothing;
      Just a -> Just (f a)
    };
  -- Managed call-stack qualification is represented by a private evidence
  -- wrapper, never by the raw first-class CallStack value type. No class or
  -- instance dictionary for HasCallStack is fabricated during reconstruction.
  dictionaryClass :: forall a. Map String String -> String -> [] a -> Maybe String;
  dictionaryClass dictionaries name args =
    if eqString name "MLFStackEvidence" && null args then Just Classes.callStackPredicate else
    if eqString name "MLFCallStack" then Nothing else M.lookup compareString name dictionaries;
  sourceSchemeIn :: Map String String -> Bool -> XType -> SType;
  sourceSchemeIn dictionaries qualified ty =
    case ty of {
      XVar (XTyVar i) -> STVar ("a" ++ showInt (if (i < 0) then ((0 - (2 * i)) + 1) else (2 * i)));
      XBot -> SBottom;
      XBotKind k -> SBottomKind k;
      XArrow a b ->
        case a of {
          XCon d ts ->
            case if qualified
                 then dictionaryClass dictionaries d ts
                 else Nothing of {
              Just c ->
                let {
                  predicate = SPredicate c (map (sourceSchemeIn dictionaries False) ts)
                } in
                case sourceSchemeIn dictionaries True b of {
                  SQualified ps body -> SQualified ((:) predicate ps) body;
                  body -> SQualified ((:) predicate []) body
                };
              Nothing ->
                SArrow (sourceSchemeIn dictionaries False a) (sourceSchemeIn dictionaries False b)
            };
          _ -> SArrow (sourceSchemeIn dictionaries False a) (sourceSchemeIn dictionaries False b)
        };
      XCon c ts -> SCon c (map (sourceSchemeIn dictionaries False) ts);
      XApply a b ->
        STypeApp (sourceSchemeIn dictionaries False a) (sourceSchemeIn dictionaries False b);
      XForall (XTyVar i) bound body ->
        SForall Flexible ("a" ++ showInt (if (i < 0) then ((0 - (2 * i)) + 1) else (2 * i)))
          (sourceSchemeIn dictionaries False bound)
          (sourceSchemeIn dictionaries qualified body)
    };
  -- Only call metadata follows a bounded result variable. Keep the exact
  -- imported XType for the checked wrapper. Capture the environment at the
  -- forall's definition so repeated variable names retain lexical scope.
  data PrefixBound = PrefixBound XType (Map XTyVar PrefixBound);
  importClasses :: Map String String -> XType -> [] String;
  importClasses dictionaries ty = importClassesIn dictionaries M.empty ty;
  importClassesIn :: Map String String -> Map XTyVar PrefixBound -> XType -> [] String;
  importClassesIn dictionaries bounds ty = case ty of {
    XForall variable bound body -> importClassesIn dictionaries
      (M.insert T.compareTyVar variable (PrefixBound bound bounds) bounds) body;
    XVar variable -> case M.lookup T.compareTyVar variable bounds of {
      Nothing -> [];
      Just (PrefixBound definition outer) -> importClassesIn dictionaries outer definition
    };
    XArrow (XCon name args) result -> case dictionaryClass dictionaries name args of {
      Nothing -> []; Just cls -> (:) cls (importClassesIn dictionaries bounds result)
    };
    _ -> []
  };
  sourceScheme dictionaries ty = sourceSchemeIn dictionaries True ty;
  freshInteger :: Fresh Int;
  freshInteger = Fresh (\count used -> Right ((,,) count (count + 1) used));
  normalTypeIn :: Map XTyVar XTyVar -> XType -> Fresh XType;
  normalTypeIn env ty =
    case ty of {
      XVar a -> freshPure (XVar (M.findWithDefault T.compareTyVar a a env));
      XArrow a b ->
        do {
          x <- normalTypeIn env a;
          y <- normalTypeIn env b;
          freshPure (XArrow x y)
        };
      XCon c ts ->
        do {
          args <- mapM (normalTypeIn env) ts;
          freshPure (XCon c args)
        };
      XApply a b ->
        do {
          x <- normalTypeIn env a;
          y <- normalTypeIn env b;
          freshPure (XApply x y)
        };
      XForall a XBot body@(XForall r tail (XArrow (XVar input) (XVar output))) ->
        if T.equalTyVar a input && T.equalTyVar r output && not (T.equalTyVar a r) then do {
          i <- freshInteger;
          let { variable = XTyVar i };
          bound <- normalTypeIn (M.insert T.compareTyVar a variable env) tail;
          j <- freshInteger;
          let { result = XTyVar j };
          freshPure (XForall variable XBot (XForall result bound (XArrow (XVar variable) (XVar result))))
        } else normalForall env a XBot body;
      XForall a bound b -> normalForall env a bound b;
      _ -> freshPure ty
    };
  normalForall env a bound body = do {
    bound2 <- normalTypeIn env bound;
    i <- freshInteger;
    let { v = XTyVar i };
    result <- normalTypeIn (M.insert T.compareTyVar a v env) body;
    freshPure (XForall v bound2 result)
  };
  normalType ty = case T.projectionTypeLayout ty of {
    Just ((,) width selected) -> let {
      -- Match normalTypeIn's allocation order. The argument binder comes
      -- before its suffix and the result binder comes after that suffix.
      argument index = let { a = XTyVar index; next = index + 1 } in
        if next == width then XForall a XBot (XArrow (XVar a) (XVar (XTyVar selected)))
        else let { r = XTyVar (2 * (width - 1) - index) } in
          XForall a XBot (XForall r (argument next) (XArrow (XVar a) (XVar r)))
    } in argument 0;
    Nothing -> case runFresh [] (normalTypeIn M.empty ty) of {
      Right t -> t;
      Left e -> panic e
    };
  };
  cleanSource source = cleanSourceWith hygiene source;
  cleanParsedSource = cleanParsedReserving True;
  cleanParsedReserving possible = cleanSourceWith (\e ->
    runFresh (if possible then Desugar.allNames e else []) (hygieneWith renameParsedPlain M.empty e));
  -- Shared identifiers have literal token spellings. Qualification joins
  -- components with dots. The parser's generated names use other prefixes.
  -- A hit anywhere, including a comment or string, keeps full reservations.
  sourceHasHygienePrefix text = let {
    size = stringLength text; last = stringLength hygieneBinderPrefix - 1;
    first = stringCodeAt hygieneBinderPrefix 0; final = stringCodeAt hygieneBinderPrefix last;
    scan end = end < size &&
      ((stringCodeAt text end == final && stringCodeAt text (end - last) == first &&
        Lexer.textStartsAt text (end - last) hygieneBinderPrefix) ||
       scan (end + 1))
  } in scan last;
  cleanSourceWith clean (SourceModule path name exports imports ds cs is vs body syntax) =
    do {
      values <- traverseEither (\((,,) n a e) -> mapEither ((,,) n a) (clean e)) vs;
      instances <-
        traverseEither
          (\(SInstanceDecl vars context klass head methods) ->
             do {
               methods2 <- traverseEither (\((,) n e) -> mapEither ((,) n) (clean e)) methods;
               Right (SInstanceDecl vars context klass head methods2)
             })
          is;
      body2 <-
        case body of {
          Nothing -> Right Nothing;
          Just e -> mapEither Just (clean e)
        };
      Right (SourceModule path name exports imports ds cs instances values body2 syntax)
    };
  valueClosure :: Map String ((,,) String (Maybe SAnnotation) SExpr) ->
                  Set String -> [] String -> Set String;
  valueClosure values seen todo =
    case todo of {
      [] -> seen;
      (:) n rest ->
        if Set.member compareString n seen
        then valueClosure values seen rest
        else case M.lookup compareString n values of {
               Nothing -> valueClosure values seen rest;
               Just ((,,) _ _ e) ->
                 valueClosure values (Set.insert compareString n seen)
                   (append (Surface.freeNames e) rest)
             }
    };
  closeInstance values inst =
    Surface.closeSourceInstance values
      (M.fromList compareString (map (\v -> (,) (Modules.valueName v) v) values)) inst;
  stripInstance (SInstanceDecl vars context klass head methods) =
    SInstanceDecl vars context klass head
      (map (\((,) n _) -> (,) n (SApp (SPrimitive PPanic) (SStringLit "interface method")))
         methods);
  sortBindings bindings = sortBy (\a b -> compareString (fst a) (fst b)) bindings;
  collectBindings :: DataEnv -> XEnv -> XTerm -> Either String ([] ((,) XName XType));
  collectBindings ds env term =
    do {
      Check.validateTypeEnv ds (Check.typeEnv env);
      mapM (Check.termType ds (Check.typeEnv env)) (M.elems (Check.termEnv env));
      collectBindingsIn ds env term
    };
  -- The starting environment is checked once. Inferred RHS types and explicitly
  -- checked recursive signatures preserve that invariant as the spine grows.
  collectBindingsIn :: DataEnv -> XEnv -> XTerm -> Either String ([] ((,) XName XType));
  collectBindingsIn ds env term =
    let {
      matchValueShared1 = term
    } in
    case matchValueShared1 of {
      XLet matchValueShared2 matchValueShared3 matchValueShared4 ->
        let {
          n = matchValueShared2
        } in
        let {
          rhs = matchValueShared3
        } in
        let {
          rest = matchValueShared4
        } in
        do {
          ty <- Check.inferIn ds env rhs;
          ensure (Set.null (T.freeVars ty)) "inference binding has an open type";
          remaining <-
            collectBindingsIn ds
              (XEnv (Check.typeEnv env) (M.insert X.compareName n ty (Check.termEnv env)))
              rest;
          Right ((:) ((,) n ty) remaining)
        };
      XLetRec matchValueShared5 matchValueShared6 ->
        let {
          bs = matchValueShared5
        } in
        let {
          rest = matchValueShared6
        } in
        do {
          let {
            entries = map (\((,,) n t _) -> (,) n t) bs
          };
          ensure (all (\p -> Set.null (T.freeVars (snd p))) entries)
            "inference binding has an open type";
          mapM (Check.termType ds (Check.typeEnv env)) (map snd entries);
          remaining <-
            collectBindingsIn ds
              (XEnv (Check.typeEnv env)
                 (M.union X.compareName (M.fromList X.compareName entries) (Check.termEnv env)))
              rest;
          Right (append entries remaining)
        };
      XConstructor matchValueShared7 matchValueShared8 ->
        if MLF.Primitive.eqString matchValueShared7 "()"
        then case matchValueShared8 of {
               [] -> Right [];
               _ -> Left "invalid inference fragment: expected declarations ending in ()"
             }
        else Left "invalid inference fragment: expected declarations ending in ()";
      _ -> Left "invalid inference fragment: expected declarations ending in ()"
    };
  pack fields = packStringFields fields;
  digitEnd :: String -> Int -> Int;
  digitEnd text i =
    if (i >= stringLength text)
    then i
    else let {
           c = stringCodeAt text i
         } in
         if ((c >= 48) && (c <= 57)) then digitEnd text (i + 1) else i;
  -- Read each decimal length in one pass. A padded length still has a
  -- valid frame boundary, so validate the rest before reporting its spelling.
  unpackFields :: Maybe String -> String -> Int -> Either String ([] String);
  unpackFields canonicalError text initial = let {
    limit = stringLength text;
    malformed = Left "malformed module artifact framing";
    fields start = if start == limit then Right [] else digits start start 0;
    digits start position n =
      if position >= limit then malformed else let { c = stringCodeAt text position } in
      if c == 58 && position > start then
        if n > limit - position - 1 then Left "truncated module artifact" else do {
          rest <- fields (position + 1 + n);
          case canonicalError of {
            Nothing -> Right ();
            Just message -> ensure (position - start == 1 || stringCodeAt text start /= 48) message
          };
          Right ((:) (stringSlice text (position + 1) n) rest)
        }
      else if c < 48 || c > 57 || position - start >= 9 then malformed
      else digits start (position + 1) (10 * n + (c - 48))
  } in fields initial;
  unpackFrom :: String -> Int -> Either String ([] String);
  unpackFrom text start = unpackFields Nothing text start;
  unpack text = unpackFrom text 0;
  fingerprintFrom :: String -> Int -> Int -> Int -> String;
  fingerprintFrom text i a b =
    if (i >= stringLength text)
    then (showInt a ++ ("-" ++ showInt b))
    else if (i == 0)
         then fingerprintChars (textToChars text) a b
         else fingerprintIndexedFrom text i a b;
  -- Complete traversals use the existing scalar-character stream. Keep the
  -- indexed path for every nonzero start: negative indices retain their exact
  -- error/demand behavior and positive offsets do not require a prefix scan.
  fingerprintIndexedFrom :: String -> Int -> Int -> Int -> String;
  fingerprintIndexedFrom text i a b =
    if (i >= stringLength text)
    then (showInt a ++ ("-" ++ showInt b))
    else let {
           code = stringCodeAt text i
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (fingerprintIndexedFrom text (i + 1) nextA nextB));
  fingerprintChars :: [] Char -> Int -> Int -> String;
  fingerprintChars chars a b =
    case chars of {
      [] -> (showInt a ++ ("-" ++ showInt b));
      (:) c rest ->
        let { code = charCode c } in
        let { nextA = (((a * 65599) + code) % 2147483647) } in
        let { nextB = (((b * 131) + code) % 2147483629) } in
        seq nextA (seq nextB (fingerprintChars rest nextA nextB))
    };
  -- Group four scalar steps for the canonical seeds. Each coefficient is
  -- reduced modulo its original prime. Even the largest possible state
  -- times coefficient plus three Unicode scalars times coefficients fits Int64.
  -- The exported signed-seed and indexed recurrences retain their old domain.
  canonicalFingerprintState chars a b = case chars of {
    (:) c0 ((:) c1 ((:) c2 ((:) c3 rest))) -> let {
      x0 = charCode c0; x1 = charCode c1; x2 = charCode c2; x3 = charCode c3;
      nextA = (a * 1172642095 + x0 * 780718649 + x1 * 8261507 + x2 * 65599 + x3) % 2147483647;
      nextB = (b * 294499921 + x0 * 2248091 + x1 * 17161 + x2 * 131 + x3) % 2147483629
    } in seq nextA (seq nextB (canonicalFingerprintState rest nextA nextB));
    _ -> fingerprintStateChars chars a b
  };
  canonicalFingerprintText text index size a b =
    if index == 0 && size > 1024 && size == stringLength text && size /= stringUtf8Length text
    then fingerprintBlocks text 0 size a b else canonicalFingerprintBlock text index size a b;
  -- A few Unicode scalars in an otherwise ASCII artifact should only require
  -- streaming their own block. Each block continues both polynomial states.
  fingerprintBlocks text index size a b =
    if index == size then (,) a b else let {
      count = if size - index < 1024 then size - index else 1024;
      block = stringSlice text index count;
      states = if stringUtf8Length block == count
        then canonicalFingerprintBlock block 0 count a b
        else canonicalFingerprintState (textToChars block) a b
    } in case states of {
      (,) nextA nextB -> seq nextA (seq nextB (fingerprintBlocks text (index + count) size nextA nextB))
    };
  -- ASCII fields are common in artifacts. Read four scalars directly without
  -- allocating a character-list cell for each byte. On the first non-ASCII
  -- block, stream just the remaining suffix so Unicode stays a linear scan.
  canonicalFingerprintBlock text index size a b =
    if size - index < 4 then canonicalFingerprintState
      (textToChars (stringSlice text index (size - index))) a b
    else let {
      x0 = stringCodeAt text index; x1 = stringCodeAt text (index + 1);
      x2 = stringCodeAt text (index + 2); x3 = stringCodeAt text (index + 3)
    } in if x0 < 128 && x1 < 128 && x2 < 128 && x3 < 128 then let {
      nextA = (a * 1172642095 + x0 * 780718649 + x1 * 8261507 + x2 * 65599 + x3) % 2147483647;
      nextB = (b * 294499921 + x0 * 2248091 + x1 * 17161 + x2 * 131 + x3) % 2147483629
    } in seq nextA (seq nextB (canonicalFingerprintBlock text (index + 4) size nextA nextB))
    else canonicalFingerprintState (textToChars (stringSlice text index (size - index))) a b;
  fingerprint text = case canonicalFingerprintText text 0 (stringLength text) 0 1 of {
    (,) a b -> showInt a ++ "-" ++ showInt b
  };
  -- Exact summaries of the two existing rolling checksums. A summary composes
  -- with a canonical nonnegative rolling state, so datatype prefixes need not be rescanned
  -- for every independently checked fragment. The serialized digest is unchanged.
  fingerprintStateFrom :: String -> Int -> Int -> Int -> (,) Int Int;
  fingerprintStateFrom text i a b =
    if (i >= stringLength text)
    then (,) a b
    else if (i == 0)
         then fingerprintStateChars (textToChars text) a b
         else fingerprintIndexedStateFrom text i a b;
  fingerprintIndexedStateFrom :: String -> Int -> Int -> Int -> (,) Int Int;
  fingerprintIndexedStateFrom text i a b =
    if (i >= stringLength text)
    then (,) a b
    else let {
           code = stringCodeAt text i
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (fingerprintIndexedStateFrom text (i + 1) nextA nextB));
  fingerprintStateChars :: [] Char -> Int -> Int -> (,) Int Int;
  fingerprintStateChars chars a b =
    case chars of {
      [] -> (,) a b;
      (:) c rest ->
        let { code = charCode c } in
        let { nextA = (((a * 65599) + code) % 2147483647) } in
        let { nextB = (((b * 131) + code) % 2147483629) } in
        seq nextA (seq nextB (fingerprintStateChars rest nextA nextB))
    };
  fingerprintPower :: Int -> Int -> Int -> Int;
  fingerprintPower base count modulus =
    if (count == 0)
    then 1
    else let {
           half = fingerprintPower base (quotInt count 2) modulus
         } in
         let {
           squared = ((half * half) % modulus)
         } in
         if ((count % 2) == 0) then squared else ((squared * base) % modulus);
  fingerprintPart :: String -> (,,,) Int Int Int Int;
  fingerprintPart text =
    case canonicalFingerprintText text 0 (stringLength text) 0 0 of {
      (,) a b ->
        (,,,) (fingerprintPower 65599 (stringLength text) 2147483647)
          (fingerprintPower 131 (stringLength text) 2147483629)
          a
          b
    };
  fingerprintAppend :: (,) Int Int -> (,,,) Int Int Int Int -> (,) Int Int;
  fingerprintAppend ((,) a b) ((,,,) powerA powerB partA partB) =
    let {
      nextA = (((a * powerA) + partA) % 2147483647)
    } in
    let {
      nextB = (((b * powerB) + partB) % 2147483629)
    } in
    seq nextA (seq nextB ((,) nextA nextB));
  fingerprintAfter :: (,) Int Int -> String -> String;
  fingerprintAfter ((,) a b) text = fingerprintFrom text 0 a b;
  -- Exact compositional summaries of actual serialized scalar text.
  data FingerprintEncoding = FingerprintEncoding Int Int Int Int Int;
  encodingLength (FingerprintEncoding count _ _ _ _) = count;
  encodingText text = case fingerprintPart text of {
    (,,,) pa pb a b -> FingerprintEncoding (stringLength text) pa pb a b
  };
  encodingEmpty = FingerprintEncoding 0 1 1 0 0;
  encodingAppend (FingerprintEncoding n pa pb a b) (FingerprintEncoding m qa qb c d) =
    case fingerprintAppend ((,) a b) ((,,,) qa qb c d) of {
      (,) x y -> FingerprintEncoding (n + m) ((pa * qa) % 2147483647)
        ((pb * qb) % 2147483629) x y
    };
  encodingConcat values = foldlStrict encodingAppend encodingEmpty values;
  encodingPack values = encodingConcat (concatMap (\value ->
    [encodingText (showInt (encodingLength value) ++ ":"), value]) values);
  -- Composition requires canonical nonnegative residues, as produced above.
  encodingState state (FingerprintEncoding _ pa pb a b) =
    fingerprintAppend state ((,,,) pa pb a b);
  encodingAfter state value = case encodingState state value of {
    (,) a b -> showInt a ++ "-" ++ showInt b
  };
  encodingFingerprint value = encodingAfter ((,) 0 1) value;
  -- The pool lasts for one admitted object and keys exact scalar text, never
  -- names, inferred types or caller-provided digests. Punctuation is reusable too.
  -- Advance the two residues per chunk. Aggregate powers depend only on the
  -- total scalar length, so compute them once rather than once per token.
  encodingChunks pool chunks (FingerprintEncoding count pa pb a b) =
    case encodingChunkState pool chunks 0 ((,) a b) of {
      (,,) next added ((,) x y) -> let {
        powerA = (pa * fingerprintPower 65599 added 2147483647) % 2147483647;
        powerB = (pb * fingerprintPower 131 added 2147483629) % 2147483629;
        total = count + added
      } in seq total (seq powerA (seq powerB
        ((,) next (FingerprintEncoding total powerA powerB x y))))
    };
  encodingChunkState pool chunks count state = case chunks of {
    [] -> (,,) pool count state;
    (:) text rest -> let {
      selected = case M.lookup compareString text pool of {
        Just encoded -> (,) pool encoded;
        Nothing -> let { encoded = encodingText text }
          in (,) (M.insert compareString text encoded pool) encoded
      };
      next = count + encodingLength (snd selected)
    } in case encodingState state (snd selected) of {
      (,) x y -> seq next (seq x (seq y (encodingChunkState (fst selected) rest next ((,) x y))))
    }
  };
  -- A per-compilation pool contains only pure encodings, never inferred results.
  -- Entries remain lazy. A name lookup is not an identity proof: lowering may
  -- change a layout, so reuse requires equality of the actual full declaration.
  data DatatypeEncoding =
    DatatypeEncoding DataDecl String ((,,,) Int Int Int Int);
  data DatatypeEncodings = DatatypeEncodings (Map String ([] DatatypeEncoding));
  datatypeEncoding :: DataDecl -> DatatypeEncoding;
  datatypeEncoding declaration =
    let { text = D.prettyDeclaration declaration ++ "\n" } in
    DatatypeEncoding declaration text (fingerprintPart text);
  prepareDatatypeEncodings :: [] DataDecl -> DatatypeEncodings;
  prepareDatatypeEncodings declarations =
    DatatypeEncodings (M.fromListWith compareString append
      (map (\d -> (,) (D.datatypeName d) ((:) (datatypeEncoding d) [])) declarations));
  findDatatypeEncoding :: DataDecl -> [] DatatypeEncoding -> DatatypeEncoding;
  findDatatypeEncoding declaration entries = case entries of {
    [] -> datatypeEncoding declaration;
    (:) entry rest -> case entry of {
      DatatypeEncoding original _ _ ->
        if SourceEquality.eqDataDecl declaration original then entry
        else findDatatypeEncoding declaration rest
    }
  };
  lookupDatatypeEncoding :: DatatypeEncodings -> DataDecl -> DatatypeEncoding;
  lookupDatatypeEncoding (DatatypeEncodings entries) declaration =
    findDatatypeEncoding declaration
      (M.findWithDefault compareString [] (D.datatypeName declaration) entries);
  appendDatatypeEncoding :: (,) Int Int -> DatatypeEncoding -> (,) Int Int;
  -- Internal callers reach canonical residues. Other signed Int64 seeds need
  -- the original recurrence: a negative seed can cross zero, and a large
  -- positive seed can wrap before the first remainder. Composing the summary
  -- is exact only when both seeds are already within their residue ranges.
  appendDatatypeEncoding state (DatatypeEncoding _ text part) = case state of {
    (,) a b -> if (a < 0 || a >= 2147483647 || b < 0 || b >= 2147483629)
      then fingerprintStateFrom text 0 a b
      else fingerprintAppend state part
  };
  fingerprintTermWithDatatypes :: DatatypeEncodings -> XTerm -> String;
  fingerprintTermWithDatatypes pool term = case term of {
    XWithData declarations body ->
      fingerprintAfter
        (foldlStrict appendDatatypeEncoding ((,) 0 1)
          (map (lookupDatatypeEncoding pool) declarations))
        (Pretty.prettyTerm body);
    _ -> fingerprint (Pretty.prettyTerm term)
  };
  entityEncoding (Modules.Entity owner name role) =
    let {
      result :: (String, String);
      result =
        case role of {
          Modules.Value -> (,) "value" "";
          Modules.Datatype -> (,) "data" "";
          Modules.Class -> (,) "class" "";
          Modules.ManagedConstraint -> (,) "managed-constraint" "";
          Modules.Constructor p -> (,) "constructor" p;
          Modules.Method p -> (,) "method" p;
          Modules.BuiltinType -> (,) "builtin" "";
          Modules.Primitive p -> (,) "primitive" (Primitive.primitiveName p);
          Modules.Boolean b -> (,) "bool" (if b then "true" else "false")
        }
    } in
    pack ((:) owner ((:) name ((:) (fst result) ((:) (snd result) []))));
  noEntityArg :: forall a. a -> String -> Either String a;
  noEntityArg role arg = if eqString arg "" then Right role else Left "unexpected entity argument";
  decodeEntity text =
    do {
      fields <- unpack text;
      case fields of {
        (:) owner ((:) name ((:) tag ((:) arg []))) ->
          do {
            role <-
              let {
                matchValueShared9 = tag
              } in
              if MLF.Primitive.eqString matchValueShared9 "managed-constraint"
              then noEntityArg Modules.ManagedConstraint arg
              else if MLF.Primitive.eqString matchValueShared9 "value"
              then noEntityArg Modules.Value arg
              else if MLF.Primitive.eqString matchValueShared9 "data"
                   then noEntityArg Modules.Datatype arg
                   else if MLF.Primitive.eqString matchValueShared9 "class"
                        then noEntityArg Modules.Class arg
                        else if MLF.Primitive.eqString matchValueShared9 "constructor"
                             then Right (Modules.Constructor arg)
                             else if MLF.Primitive.eqString matchValueShared9 "method"
                                  then Right (Modules.Method arg)
                                  else if MLF.Primitive.eqString matchValueShared9 "builtin"
                                       then noEntityArg Modules.BuiltinType arg
                                       else if MLF.Primitive.eqString matchValueShared9 "primitive"
                                            then case Primitive.lookupPrimitive arg of {
                                                   Nothing -> Left "unknown interface primitive";
                                                   Just p -> Right (Modules.Primitive p)
                                                 }
                                            else if MLF.Primitive.eqString matchValueShared9 "bool"
                                                 then if eqString arg "true"
                                                      then Right (Modules.Boolean True)
                                                      else if eqString arg "false"
                                                           then Right (Modules.Boolean False)
                                                           else Left "unknown interface entity role"
                                                 else Left "unknown interface entity role";
            case role of {
              Modules.ManagedConstraint ->
                ensure (eqString owner "MLF.Primitive" && eqString name "HasCallStack")
                  "invalid managed constraint identity";
              _ -> Right ()
            };
            Right (Modules.Entity owner name role)
          };
        _ -> Left "malformed interface entity"
      }
    };
  prettySourceType :: SType -> String;
  prettySourceType ty =
    case ty of {
      STVar n -> n;
      SBottom -> "bot";
      SBottomKind k -> ("bot[" ++ (K.prettyKind k ++ "]"));
      SArrow a b -> ("(" ++ (prettySourceType a ++ (" -> " ++ (prettySourceType b ++ ")"))));
      STypeApp a b -> ("(" ++ (prettySourceType a ++ (" " ++ (prettySourceType b ++ ")"))));
      SCon c ts -> ("(" ++ (intercalate " " ((:) c (map prettySourceType ts)) ++ ")"));
      SForall flag n bound body ->
        ("(forall (" ++
         (n ++
          ((case flag of {
              Flexible -> " >= ";
              Rigid -> " > "
            }) ++
           (prettySourceType bound ++ ("). " ++ (prettySourceType body ++ ")"))))));
      SQualified ps b -> ("(" ++ (prettyContext ps ++ (prettySourceType b ++ ")")))
    };
  prettyPredicate :: SPredicate -> String;
  prettyPredicate (SPredicate c ts) = intercalate " " ((:) c (map prettySourceType ts));
  prettyContext :: [] SPredicate -> String;
  prettyContext ps =
    if null ps then "" else ("(" ++ (intercalate ", " (map prettyPredicate ps) ++ ") => "));
  prettyParameter ((,) n k) = ("(" ++ (n ++ (" : " ++ (K.prettyKind k ++ ")"))));
  prettyMethodName n = if Lexer.sharedIdentifier n then n else "(" ++ (n ++ ")");
  prettyClass c =
    ("class " ++
     (prettyContext (Classes.superclasses c) ++
      (Classes.className c ++
       (" " ++
        (intercalate " " (map prettyParameter (Classes.classParameters c)) ++
         (" where { " ++
          (intercalate "; "
             (map (\((,) n ty) -> (prettyMethodName n ++ (" : " ++ prettySourceType ty)))
                (Classes.classMethods c)) ++
           " };")))))));
  prettyInstance i =
    ("instance " ++
     ((if null (Classes.instanceVariables i)
       then ""
       else ("forall " ++
             (intercalate " " (map prettyParameter (Classes.instanceVariables i)) ++ ". "))) ++
      (prettyContext (Classes.instanceContext i) ++
       (Classes.instanceClass i ++
        (" " ++
         (intercalate " " (map prettySourceType (Classes.instanceHead i)) ++
          (" where { " ++
           (intercalate "; "
              (map (\((,) n _) -> (prettyMethodName n ++ " = panic \"interface method\""))
                 (Classes.instanceMethods i)) ++
            " };"))))))));
  pairEncoding ((,) a b) = pack ((:) a ((:) b []));
  interfaceFields i =
    let {
      metadata =
        unlines
          (append (map D.prettyDeclaration (unitData i))
             (append (map prettyClass (unitClasses i))
                (map (\p -> prettyInstance (snd p)) (unitInstances i))))
    } in
    let {
      bindings =
        pack
          (map (\((,) n t) -> pairEncoding ((,) n (Pretty.prettyType (normalType t))))
             (unitBindings i))
    } in
    (:) "MLFI-4"
      ((:) (unitName i)
         ((:) (pack (map pairEncoding (unitDependencies i)))
            ((:) (pack (map entityEncoding (unitExports i)))
               ((:) metadata ((:) (pack (map fst (unitInstances i))) ((:) bindings []))))));
  interfaceFingerprint i = fingerprint (pack (interfaceFields i));
  encodeInterface i = pack (snoc (interfaceFields i) (unitObjectFingerprint i));
  -- Preserve encodeInterface's exact eight framed fields, reusing only the
  -- rendered name/type text summaries from this object's local pool.
  encodingBindings pool bindings = case bindings of {
    [] -> (,) pool [];
    (:) ((,) name ty) rest -> let {
      named = encodingChunks pool [name] encodingEmpty;
      typed = encodingChunks (fst named) (Pretty.typeChunks 0 (normalType ty) []) encodingEmpty;
      remaining = encodingBindings (fst typed) rest
    } in (,) (fst remaining) ((:) (encodingPack [snd named, snd typed]) (snd remaining))
  };
  encodingInterface pool iface = let {
    bindings = encodingBindings pool (unitBindings iface);
    prefix = map encodingText (take 6 (interfaceFields iface));
    fields = append prefix [encodingPack (snd bindings), encodingText (unitObjectFingerprint iface)]
  } in (,) (fst bindings) (encodingPack fields);
  decodePair text =
    do {
      fields <- unpack text;
      case fields of {
        (:) a ((:) b []) -> Right ((,) a b);
        _ -> Left "malformed interface pair"
      }
    };
  decodeInterface input =
    do {
      fields <- unpack input;
      let {
        matchValueShared11 = fields
      } in
      case matchValueShared11 of {
        (:) matchValueShared12 matchValueShared13 ->
          if MLF.Primitive.eqString matchValueShared12 "MLFI-4"
          then case matchValueShared13 of {
                 (:) matchValueShared14 matchValueShared15 ->
                   case matchValueShared15 of {
                     (:) matchValueShared16 matchValueShared17 ->
                       case matchValueShared17 of {
                         (:) matchValueShared18 matchValueShared19 ->
                           case matchValueShared19 of {
                             (:) matchValueShared20 matchValueShared21 ->
                               case matchValueShared21 of {
                                 (:) matchValueShared22 matchValueShared23 ->
                                   case matchValueShared23 of {
                                     (:) matchValueShared24 matchValueShared25 ->
                                       case matchValueShared25 of {
                                         (:) matchValueShared26 matchValueShared27 ->
                                           case matchValueShared27 of {
                                             [] ->
                                               let {
                                                 name = matchValueShared14
                                               } in
                                               let {
                                                 deps = matchValueShared16
                                               } in
                                               let {
                                                 exports = matchValueShared18
                                               } in
                                               let {
                                                 metadata = matchValueShared20
                                               } in
                                               let {
                                                 instanceNames = matchValueShared22
                                               } in
                                               let {
                                                 bindings = matchValueShared24
                                               } in
                                               let {
                                                 objectHash = matchValueShared26
                                               } in
                                               do {
                                                 rawDeps <- unpack deps;
                                                 ds <- traverseEither decodePair rawDeps;
                                                 rawExports <- unpack exports;
                                                 es <- traverseEither decodeEntity rawExports;
                                                 source <-
                                                   Parser.parseMetadataModule "<module interface>"
                                                     ("module InterfaceMetadata where {\n" ++
                                                      (metadata ++ "\n}"));
                                                 ns <- unpack instanceNames;
                                                 rawBindings <- unpack bindings;
                                                 bs <-
                                                   traverseEither
                                                     (\field ->
                                                        do {
                                                          boundValueShared10 <- decodePair field;
                                                          case boundValueShared10 of {
                                                            (,) n ty ->
                                                              do {
                                                                t <- XP.parseType ty;
                                                                Right ((,) n t)
                                                              }
                                                          }
                                                        })
                                                     rawBindings;
                                                 ensure
                                                   (length ns ==
                                                    length (Modules.sourceInstances source))
                                                   "interface instance count mismatch";
                                                 ensure
                                                   (null (Modules.sourceValues source) &&
                                                    null (Modules.sourceImports source))
                                                   "interface contains executable declarations";
                                                 ensure
                                                   ((length ds ==
                                                     length (nubBy eqString (map fst ds))) &&
                                                    ((length ns == length (nubBy eqString ns)) &&
                                                     (length bs ==
                                                      length (nubBy eqString (map fst bs)))))
                                                   "duplicate interface entry";
                                                 ensure
                                                   (all (\p -> Set.null (T.freeVars (snd p))) bs)
                                                   "interface has open types";
                                                 ensure
                                                   ((stringLength name > 0) &&
                                                    (stringLength objectHash > 0))
                                                   "incomplete module interface";
                                                 traverseEither validModuleName
                                                   ((:) name
                                                      (append (map fst ds) (map Modules.owner es)));
                                                 let {
                                                   i =
                                                     UnitInterface name ds es
                                                       (Modules.sourceDatatypes source)
                                                       (Modules.sourceClasses source)
                                                       (zip ns
                                                          (map stripInstance
                                                             (Modules.sourceInstances source)))
                                                       bs
                                                       objectHash
                                                 };
                                                 ensure (eqString (encodeInterface i) input)
                                                   "noncanonical module interface";
                                                 Right i
                                               };
                                             _ ->
                                               Left
                                                 "unsupported or malformed module interface (expected MLFI-4)"
                                           };
                                         _ ->
                                           Left
                                             "unsupported or malformed module interface (expected MLFI-4)"
                                       };
                                     _ ->
                                       Left
                                         "unsupported or malformed module interface (expected MLFI-4)"
                                   };
                                 _ ->
                                   Left
                                     "unsupported or malformed module interface (expected MLFI-4)"
                               };
                             _ -> Left "unsupported or malformed module interface (expected MLFI-4)"
                           };
                         _ -> Left "unsupported or malformed module interface (expected MLFI-4)"
                       };
                     _ -> Left "unsupported or malformed module interface (expected MLFI-4)"
                   };
                 _ -> Left "unsupported or malformed module interface (expected MLFI-4)"
               }
          else Left "unsupported or malformed module interface (expected MLFI-4)";
        _ -> Left "unsupported or malformed module interface (expected MLFI-4)"
      }
    };
  validModuleName name =
    do {
      -- Metadata identities include native builtins; source ownership is checked
      -- by parseModule when loading source, not by this grammar validator.
      parsed <- Parser.parseLayout False Parser.moduleName "<module identity>" name;
      ensure (eqString parsed name)
        "invalid compiled module identity"
    };
  encodeObject object =
    let {
      i = objectInterface object
    } in
    pack
      ((:) "MLFO-1"
         ((:) (unitName i)
            ((:) (interfaceFingerprint i) ((:) (Pretty.prettyTerm (objectTerm object)) []))));
  -- Crate objects and inference queries supply datatype contexts separately.
  -- Keep metadata and payload contexts distinct: a malformed object must not be
  -- repaired by replacing its payload's declarations with its header's layouts.
  objectContext :: UnitObject -> [] DataDecl;
  objectContext object =
    case objectTerm object of {
      XWithData ds _ -> ds;
      _ -> []
    };
  objectBody :: UnitObject -> XTerm;
  objectBody object =
    case objectTerm object of {
      XWithData _ body -> body;
      body -> body
    };
  withInterfaceData :: UnitInterface -> [] DataDecl -> String -> UnitInterface;
  withInterfaceData i datatypes checksum =
    UnitInterface (unitName i) (unitDependencies i) (unitExports i) datatypes (unitClasses i)
      (unitInstances i)
      (unitBindings i)
      checksum;
  encodeContextualObject :: UnitObject -> String;
  encodeContextualObject object =
    let {
      body = Pretty.prettyTerm (objectBody object)
    } in
    let {
      header = withInterfaceData (objectInterface object) [] (fingerprint body)
    } in
    pack ((:) "MLFF-2" ((:) (encodeInterface header) ((:) body [])));
  decodeContextualObjectAfter :: (,) Int Int ->
                                 [] DataDecl ->
                                 [] DataDecl -> String -> Either String UnitObject;
  decodeContextualObjectAfter prefix headerData bodyData input =
    decodeContextualObjectAfterWithCanonical prefix headerData bodyData input
      (\object canonical -> Right object);
  decodeContextualObjectAfterWithCanonical :: forall a. (,) Int Int ->
                                              [] DataDecl ->
                                              [] DataDecl ->
                                              String ->
                                              (UnitObject -> String -> Either String a) ->
                                              Either String a;
  decodeContextualObjectAfterWithCanonical prefix headerData bodyData input success =
    do {
      fields <- unpack input;
      let {
        matchValueShared28 = fields
      } in
      case matchValueShared28 of {
        (:) matchValueShared29 matchValueShared30 ->
          if MLF.Primitive.eqString matchValueShared29 "MLFF-2"
          then case matchValueShared30 of {
                 (:) matchValueShared31 matchValueShared32 ->
                   case matchValueShared32 of {
                     (:) matchValueShared33 matchValueShared34 ->
                       case matchValueShared34 of {
                         [] ->
                           let {
                             metadata = matchValueShared31
                           } in
                           let {
                             body = matchValueShared33
                           } in
                           do {
                             header <- decodeInterface metadata;
                             ensure (null (unitData header))
                               "contextual fragment contains an inline datatype header";
                             ensure (eqString (fingerprint body) (unitObjectFingerprint header))
                               "contextual fragment body checksum mismatch";
                             parsed <- XP.parseTerm "<contextual inference fragment>" body;
                             let {
                               term = XWithData bodyData parsed
                             };
                             checked <- Checked.check term;
                             let {
                               restored =
                                 withInterfaceData header headerData
                                   (fingerprintAfter prefix (Pretty.prettyTerm parsed))
                             };
                             let {
                               object = CheckedUnitObject restored checked
                             };
                             let {
                               canonical = encodeContextualObject object
                             };
                             ensure (eqString input canonical)
                               "noncanonical contextual inference fragment";
                             success object canonical
                           };
                         _ ->
                           Left
                             "unsupported or malformed contextual inference fragment (expected MLFF-2)"
                       };
                     _ ->
                       Left
                         "unsupported or malformed contextual inference fragment (expected MLFF-2)"
                   };
                 _ ->
                   Left "unsupported or malformed contextual inference fragment (expected MLFF-2)"
               }
          else Left "unsupported or malformed contextual inference fragment (expected MLFF-2)";
        _ -> Left "unsupported or malformed contextual inference fragment (expected MLFF-2)"
      }
    };
  decodeObject i input =
    do {
      fields <- unpack input;
      let {
        matchValueShared35 = fields
      } in
      case matchValueShared35 of {
        (:) matchValueShared36 matchValueShared37 ->
          if MLF.Primitive.eqString matchValueShared36 "MLFO-1"
          then case matchValueShared37 of {
                 (:) matchValueShared38 matchValueShared39 ->
                   case matchValueShared39 of {
                     (:) matchValueShared40 matchValueShared41 ->
                       case matchValueShared41 of {
                         (:) matchValueShared42 matchValueShared43 ->
                           case matchValueShared43 of {
                             [] ->
                               let {
                                 name = matchValueShared38
                               } in
                               let {
                                 abi = matchValueShared40
                               } in
                               let {
                                 body = matchValueShared42
                               } in
                               do {
                                 ensure (eqString name (unitName i)) "module object name mismatch";
                                 ensure (eqString abi (interfaceFingerprint i))
                                   "module object interface mismatch";
                                 ensure (eqString (fingerprint body) (unitObjectFingerprint i))
                                   "module object checksum mismatch";
                                 term <- XP.parseTerm "<module object>" body;
                                 Check.checkClosed term;
                                 Right (UnitObject i term)
                               };
                             _ -> Left "unsupported or malformed module object (expected MLFO-1)"
                           };
                         _ -> Left "unsupported or malformed module object (expected MLFO-1)"
                       };
                     _ -> Left "unsupported or malformed module object (expected MLFO-1)"
                   };
                 _ -> Left "unsupported or malformed module object (expected MLFO-1)"
               }
          else Left "unsupported or malformed module object (expected MLFO-1)";
        _ -> Left "unsupported or malformed module object (expected MLFO-1)"
      }
    };
  mapType :: (XTyVar -> XTyVar) -> XType -> XType;
  mapType variable ty =
    case ty of {
      XVar a -> XVar (variable a);
      XArrow a b -> XArrow (mapType variable a) (mapType variable b);
      XCon c ts -> XCon c (map (mapType variable) ts);
      XApply a b -> XApply (mapType variable a) (mapType variable b);
      XForall a bound b -> XForall (variable a) (mapType variable bound) (mapType variable b);
      _ -> ty
    };
  mapComputation :: (XTyVar -> XTyVar) -> XComputation -> XComputation;
  mapComputation variable computation =
    case computation of {
      XBottom t -> XBottom (mapType variable t);
      XHyp a -> XHyp (variable a);
      XInner p -> XInner (mapComputation variable p);
      XOuter a p -> XOuter (variable a) (mapComputation variable p);
      XIntro a -> XIntro (variable a);
      XIntroKind a k -> XIntroKind (variable a) k;
      XThen a b -> XThen (mapComputation variable a) (mapComputation variable b);
      _ -> computation
    };
  mapPattern name pattern =
    case pattern of {
      XConstructorPattern c ns -> XConstructorPattern c (map (mapMaybeValue name) ns);
      XDefaultPattern n -> XDefaultPattern (mapMaybeValue name n)
    };
  mapTerm :: (XName -> XName) -> (XTyVar -> XTyVar) -> XTerm -> XTerm;
  mapTerm name variable = mapTermProof name variable (mapComputation variable);
  -- Each proof operation remains lazy in its original XTypeApp field.
  mapTermProof :: (XName -> XName) -> (XTyVar -> XTyVar) ->
    (XComputation -> XComputation) -> XTerm -> XTerm;
  mapTermProof name variable proof term = let {
    walk = mapTermProof name variable proof
  } in
    case term of {
      XVarTerm n -> XVarTerm (name n);
      XAbs n ty b -> XAbs (name n) (mapType variable ty) (walk b);
      XApp a b -> XApp (walk a) (walk b);
      XTypeAbs a bound b ->
        XTypeAbs (variable a) (mapType variable bound) (walk b);
      XTypeApp a p -> XTypeApp (walk a) (proof p);
      XProjection rows selected -> X.mapProjection name variable rows selected;
      XInstantiationSpine head rows -> XInstantiationSpine (name head)
        (map (\((,,) spelling eliminate operand) -> (,,) spelling eliminate (walk operand)) rows);
      XLet n a b -> XLet (name n) (walk a) (walk b);
      XLetRec bs b ->
        XLetRec
          (map (\((,,) n t a) -> (,,) (name n) (mapType variable t) (walk a))
             bs)
          (walk b);
      XPrimitive p ts -> XPrimitive p (map (mapType variable) ts);
      XConstructor c ts -> XConstructor c (map (mapType variable) ts);
      XCase a t bs ->
        XCase (walk a) (mapType variable t)
          (map (\(XAlternative p b) -> XAlternative (mapPattern name p) (walk b))
             bs);
      XWithData ds b -> XWithData ds (walk b);
      _ -> term
    };
  -- Dense renumbering also handles valid object IDs near the parser's Int64
  -- limit. Adding an offset to original IDs would overflow that wire format.
  typeIdentities :: XType -> IntSet -> IntSet;
  typeIdentities = foldTypeIdentities IS.insert;
  foldTypeIdentities :: forall a. (Int -> a -> a) -> XType -> a -> a;
  foldTypeIdentities add ty seen =
    case ty of {
      XVar (XTyVar a) -> add a seen;
      XArrow a b -> foldTypeIdentities add b (foldTypeIdentities add a seen);
      XCon _ ts -> foldl (\acc t -> foldTypeIdentities add t acc) seen ts;
      XApply a b -> foldTypeIdentities add b (foldTypeIdentities add a seen);
      XForall (XTyVar a) bound b ->
        foldTypeIdentities add b (foldTypeIdentities add bound (add a seen));
      _ -> seen
    };
  computationIdentities :: XComputation -> IntSet -> IntSet;
  computationIdentities = foldComputationIdentities IS.insert;
  foldComputationIdentities :: forall a. (Int -> a -> a) -> XComputation -> a -> a;
  foldComputationIdentities add p seen =
    case p of {
      XBottom t -> foldTypeIdentities add t seen;
      XHyp (XTyVar a) -> add a seen;
      XInner q -> foldComputationIdentities add q seen;
      XOuter (XTyVar a) q -> foldComputationIdentities add q (add a seen);
      XIntro (XTyVar a) -> add a seen;
      XIntroKind (XTyVar a) _ -> add a seen;
      XThen a b -> foldComputationIdentities add b (foldComputationIdentities add a seen);
      _ -> seen
    };
  termIdentities :: XTerm -> IntSet -> IntSet;
  termIdentities = foldTermIdentities IS.insert;
  foldTermIdentities :: forall a. (Int -> a -> a) -> XTerm -> a -> a;
  foldTermIdentities add term seen =
    case term of {
      XVarTerm n -> add (X.nameId n) seen;
      XAbs n ty b -> foldTermIdentities add b (foldTypeIdentities add ty (add (X.nameId n) seen));
      XApp a b -> foldTermIdentities add b (foldTermIdentities add a seen);
      XTypeAbs (XTyVar a) bound b ->
        foldTermIdentities add b (foldTypeIdentities add bound (add a seen));
      XTypeApp a p -> foldComputationIdentities add p (foldTermIdentities add a seen);
      XProjection rows selected -> X.foldProjectionIdentities add rows selected seen;
      XInstantiationSpine n rows -> foldl (\ids ((,,) _ _ operand) -> foldTermIdentities add operand ids)
        (add (X.nameId n) seen) rows;
      XLet n a b -> foldTermIdentities add b (foldTermIdentities add a (add (X.nameId n) seen));
      XLetRec bs b ->
        foldTermIdentities add b
          (foldl
             (\acc ((,,) n t a) ->
                foldTermIdentities add a (foldTypeIdentities add t (add (X.nameId n) acc)))
             seen
             bs);
      XPrimitive _ ts -> foldl (\acc t -> foldTypeIdentities add t acc) seen ts;
      XConstructor _ ts -> foldl (\acc t -> foldTypeIdentities add t acc) seen ts;
      XCase a t bs ->
        foldl
          (\acc (XAlternative p b) ->
             foldTermIdentities add b
               (foldl (\ids n -> add (X.nameId n) ids) acc (X.patternNames p)))
          (foldTypeIdentities add t (foldTermIdentities add a seen))
          bs;
      XWithData _ b -> foldTermIdentities add b seen;
      _ -> seen
    };
  -- Checking an identity bound needs only a maximum. Use the same visit
  -- order and binder, pattern, type and computation coverage as relocation.
  maximumTermIdentity lower term = foldTermIdentities (\identity previous -> max previous identity) term lower;
  freshObject serial term =
    let {
      ids = IS.toList (termIdentities term IS.empty)
    } in
    let {
      replacements = IM.fromList (zip ids (range serial ((advanceIdentity serial (length ids)) - 1)))
    } in
    let {
      rename = \n -> IM.findWithDefault (panic "missing object identity") n replacements
    } in
    (,) (advanceIdentity serial (length ids))
      (mapTerm (\(XName n hint) -> XName (rename n) hint) (\(XTyVar n) -> XTyVar (rename n)) term);
  -- The same injective renaming applies to the term and its exported names.
  -- Inferred types may contain fresh quantified identities from datatype
  -- fields that are absent from the term. Closed export types can instead be
  -- alpha-normalized without capture. No caller-provided signature enters.
  -- Keep the inventory's fragment-specific error deferred until linking asks
  -- for it, after the existing metadata, layout and import-boundary checks.
  freshCheckedObject :: Int -> Checked.CheckedTerm ->
    (,,) Int XTerm (Either String ([] ((,) XName XType)));
  freshCheckedObject serial checked =
    let {
      term = Checked.term checked;
      ids = IS.toList (termIdentities term IS.empty);
      replacements = IM.fromList (zip ids (range serial ((advanceIdentity serial (length ids)) - 1)));
      rename = \n -> IM.findWithDefault (panic "missing object identity") n replacements;
      name = \(XName n hint) -> XName (rename n) hint;
      variable = \(XTyVar n) -> XTyVar (rename n)
    } in
    (,,) (advanceIdentity serial (length ids)) (mapTerm name variable term)
      (mapEither (map (\((,) n ty) -> (,) (name n) (normalType ty)))
        (Checked.declarationBindings checked));
  splitParameters :: XTerm -> (,) ([] ((,) XName XType)) XTerm;
  splitParameters term =
    case term of {
      XAbs n ty b ->
        case splitParameters b of {
          (,) ps rest -> (,) ((:) ((,) n ty) ps) rest
        };
      _ -> (,) [] term
    };
  mergeDeclaration declarations d =
    case filter (\other -> eqString (D.datatypeName other) (D.datatypeName d)) declarations of {
      [] -> Right (snoc declarations d);
      (:) other [] ->
        if eqString (D.prettyDeclaration other) (D.prettyDeclaration d)
        then Right declarations
        else Left ("conflicting module datatype: " ++ D.datatypeName d);
      _ -> Left ("conflicting module datatype: " ++ D.datatypeName d)
    };
  graft :: XTerm -> XTerm -> Either String XTerm;
  graft declarations body =
    let {
      matchValueShared44 = declarations
    } in
    case matchValueShared44 of {
      XLet matchValueShared45 matchValueShared46 matchValueShared47 ->
        let {
          n = matchValueShared45
        } in
        let {
          a = matchValueShared46
        } in
        let {
          b = matchValueShared47
        } in
        mapEither (XLet n a) (graft b body);
      XLetRec matchValueShared48 matchValueShared49 ->
        let {
          ds = matchValueShared48
        } in
        let {
          b = matchValueShared49
        } in
        mapEither (XLetRec ds) (graft b body);
      XConstructor matchValueShared50 matchValueShared51 ->
        if MLF.Primitive.eqString matchValueShared50 "()"
        then case matchValueShared51 of {
               [] -> Right body;
               _ -> Left "invalid inference fragment declaration spine"
             }
        else Left "invalid inference fragment declaration spine";
      _ -> Left "invalid inference fragment declaration spine"
    };
  sameSignature a b = (eqString (fst a) (fst b) && T.alphaEq (snd a) (snd b));
  removeEntryParameters :: Map String XType ->
                           Map String ((,) XName XType) -> XTerm -> Either String XTerm;
  removeEntryParameters signatures available term =
    case term of {
      XWithData _ b -> removeEntryParameters signatures available b;
      XTypeAbs a bound b ->
        mapEither (XTypeAbs a bound) (removeEntryParameters signatures available b);
      XTypeApp b p -> mapEither (\x -> XTypeApp x p) (removeEntryParameters signatures available b);
      XLetRec bs b ->
        do {
          ensure (eqList eqString (map (\((,,) n _ _) -> X.nameHint n) bs) (M.keys signatures))
            "entry parameter mismatch";
          replacements <-
            traverseEither
              (\((,,) n ty _) ->
                 case M.lookup compareString (X.nameHint n) available of {
                   Nothing -> Left ("missing entry symbol: " ++ X.nameHint n);
                   Just ((,) actual expected) ->
                     do {
                       ensure (T.alphaEq ty expected)
                         ("entry parameter type mismatch: " ++ X.nameHint n);
                       Right ((,) n actual)
                     }
                 })
              bs;
          let {
            substitution = M.fromList X.compareName replacements
          };
          Right (mapTerm (\n -> M.findWithDefault X.compareName n n substitution) (\a -> a) b)
        };
      _ -> Left "entry elaboration did not retain its import parameters"
    };
  readStrict path =
    do {
      present <- fileExists path;
      if present
      then do {
             text <- readFile path;
             ioReturn (Right text)
           }
      else ioReturn (Left ("file does not exist: " ++ path))
    }
}
