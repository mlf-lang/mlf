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
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  data UnitInterface =
    UnitInterface String (List (Pair String String)) (List Modules.Entity) (List DataDecl) (List
                                                                                            SClassDecl) (List
                                                                                                         (Pair
                                                                                                          String
                                                                                                          SInstanceDecl)) (List
                                                                                                                           (Pair
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
  encodedFrom :: String -> Int -> String;
  encodedFrom text i =
    if (i >= stringLength text)
    then ""
    else (showInt (stringCodeAt text i) ++ ("_" ++ encodedFrom text (i + 1)));
  encoded text = encodedFrom text 0;
  canonicalPreludeConstructor entity =
    (eqString (Modules.owner entity) "Prelude" &&
     (case Modules.role entity of { Modules.Constructor _ -> True; _ -> False }) &&
     any (\d -> any (\c -> eqString (Modules.spelling entity) (D.constructorName c))
                       (D.datatypeConstructors d)) D.sourceBuiltinDeclarations);
  stableName entity =
    if (Modules.isRole Modules.BuiltinType entity ||
        (canonicalPreludeConstructor entity ||
         (eqString (Modules.owner entity) "Prelude" && eqString (Modules.spelling entity) "Unit")))
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
  hygieneName env n = M.findWithDefault compareString n n env;
  hygieneBind env names =
    do {
      pairs <-
        mapM
          (\n ->
             do {
               new <- freshName "separateLocal";
               freshPure (Pair n new)
             })
          names;
      freshPure (M.union compareString (M.fromList compareString pairs) env)
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
      _ -> p
    };
  hygieneIn :: Map String String -> SExpr -> Fresh SExpr;
  hygieneIn env expression =
    case expression of {
      SVar n -> freshPure (SVar (hygieneName env n));
      SLam n a b ->
        do {
          scope <- hygieneBind env (Cons n Nil);
          body <- hygieneIn scope b;
          freshPure (SLam (hygieneName scope n) a body)
        };
      SApp f a ->
        do {
          x <- hygieneIn env f;
          y <- hygieneIn env a;
          freshPure (SApp x y)
        };
      SLet n a b ->
        do {
          scope <- hygieneBind env (Cons n Nil);
          x <- hygieneIn env a;
          y <- hygieneIn scope b;
          freshPure (SLet (hygieneName scope n) x y)
        };
      SAnn a t ->
        do {
          x <- hygieneIn env a;
          freshPure (SAnn x t)
        };
      SLetRec ds b ->
        do {
          scope <- hygieneBind env (map (\(Triple n _ _) -> n) ds);
          definitions <-
            mapM
              (\(Triple n t a) ->
                 do {
                   x <- hygieneIn scope a;
                   freshPure (Triple (hygieneName scope n) t x)
                 })
              ds;
          body <- hygieneIn scope b;
          freshPure (SLetRec definitions body)
        };
      SCase a bs ->
        do {
          scrutinee <- hygieneIn env a;
          branches <-
            mapM
              (\(SAlternative p b) ->
                 do {
                   scope <- hygieneBind env (Surface.patternVariables p);
                   body <- hygieneIn scope b;
                   freshPure (SAlternative (hygienePattern scope p) body)
                 })
              bs;
          freshPure (SCase scrutinee branches)
        };
      SEquations rows ->
        do {
          rows2 <-
            mapM
              (\(Pair ps b) ->
                 do {
                   scope <- hygieneBind env (concatMap Surface.patternVariables ps);
                   body <- hygieneIn scope b;
                   freshPure (Pair (map (hygienePattern scope) ps) body)
                 })
              rows;
          freshPure (SEquations rows2)
        };
      SDo _ _ -> hygieneIn env (Desugar.desugarDo expression);
      _ -> freshPure expression
    };
  hygiene expression = runFresh (Desugar.allNames expression) (hygieneIn M.empty expression);
  mapMaybeValue f value =
    case value of {
      Nothing -> Nothing;
      Just a -> Just (f a)
    };
  sourceSchemeIn :: Map String String -> Bool -> XType -> SType;
  sourceSchemeIn dictionaries qualified ty =
    case ty of {
      XVar (XTyVar i) -> STVar ("a" ++ showInt (if (i < 0) then ((0 - (2 * i)) + 1) else (2 * i)));
      XBot -> SBottom;
      XBotKind k -> SBottomKind k;
      XArrow a b ->
        case a of {
          XCon d ts ->
            case if qualified then M.lookup compareString d dictionaries else Nothing of {
              Just c ->
                let {
                  predicate = SPredicate c (map (sourceSchemeIn dictionaries False) ts)
                } in
                case sourceSchemeIn dictionaries True b of {
                  SQualified ps body -> SQualified (Cons predicate ps) body;
                  body -> SQualified (Cons predicate Nil) body
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
  sourceScheme dictionaries ty = sourceSchemeIn dictionaries True ty;
  freshInteger :: Fresh Int;
  freshInteger = Fresh (\count used -> Right (Triple count (count + 1) used));
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
      XForall a bound b ->
        do {
          bound2 <- normalTypeIn env bound;
          i <- freshInteger;
          body <- normalTypeIn (M.insert T.compareTyVar a (XTyVar i) env) b;
          freshPure (XForall (XTyVar i) bound2 body)
        };
      _ -> freshPure ty
    };
  normalType ty =
    case runFresh Nil (normalTypeIn M.empty ty) of {
      Right t -> t;
      Left e -> panic e
    };
  cleanSource (SourceModule path name exports imports ds cs is vs body syntax) =
    do {
      values <- traverseEither (\(Triple n a e) -> mapEither (Triple n a) (hygiene e)) vs;
      instances <-
        traverseEither
          (\(SInstanceDecl vars context klass head methods) ->
             do {
               methods2 <- traverseEither (\(Pair n e) -> mapEither (Pair n) (hygiene e)) methods;
               Right (SInstanceDecl vars context klass head methods2)
             })
          is;
      body2 <-
        case body of {
          Nothing -> Right Nothing;
          Just e -> mapEither Just (hygiene e)
        };
      Right (SourceModule path name exports imports ds cs instances values body2 syntax)
    };
  valueClosure :: Map String (Triple String (Maybe SAnnotation) SExpr) ->
                  Set String -> List String -> Set String;
  valueClosure values seen todo =
    case todo of {
      Nil -> seen;
      Cons n rest ->
        if Set.member compareString n seen
        then valueClosure values seen rest
        else case M.lookup compareString n values of {
               Nothing -> valueClosure values seen rest;
               Just (Triple _ _ e) ->
                 valueClosure values (Set.insert compareString n seen)
                   (append (Surface.freeNames e) rest)
             }
    };
  closeInstance values (SInstanceDecl vars context klass head methods) =
    do {
      let {
        valueMap = M.fromList compareString (map (\v -> Pair (Modules.valueName v) v) values)
      };
      methods2 <-
        traverseEither
          (\(Pair n e) ->
             let {
               needed = valueClosure valueMap Set.empty (Surface.freeNames e)
             } in
             mapEither (Pair n)
               (Surface.bindValues
                  (filter (\v -> Set.member compareString (Modules.valueName v) needed) values)
                  e))
          methods;
      Right (SInstanceDecl vars context klass head methods2)
    };
  stripInstance (SInstanceDecl vars context klass head methods) =
    SInstanceDecl vars context klass head
      (map (\(Pair n _) -> Pair n (SApp (SPrimitive PPanic) (SStringLit "interface method")))
         methods);
  sortBindings bindings = sortBy (\a b -> compareString (fst a) (fst b)) bindings;
  collectBindings :: DataEnv -> XEnv -> XTerm -> Either String (List (Pair XName XType));
  collectBindings ds env term =
    do {
      Check.validateTypeEnv ds (Check.typeEnv env);
      mapM (Check.termType ds (Check.typeEnv env)) (M.elems (Check.termEnv env));
      collectBindingsIn ds env term
    };
  -- The starting environment is checked once. Inferred RHS types and explicitly
  -- checked recursive signatures preserve that invariant as the spine grows.
  collectBindingsIn :: DataEnv -> XEnv -> XTerm -> Either String (List (Pair XName XType));
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
          Right (Cons (Pair n ty) remaining)
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
            entries = map (\(Triple n t _) -> Pair n t) bs
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
        if MLF.Primitive.eqString matchValueShared7 "Unit"
        then case matchValueShared8 of {
               Nil -> Right Nil;
               _ -> Left "invalid inference fragment: expected declarations ending in Unit"
             }
        else Left "invalid inference fragment: expected declarations ending in Unit";
      _ -> Left "invalid inference fragment: expected declarations ending in Unit"
    };
  pack fields = concatMapString (\s -> (showInt (stringLength s) ++ (":" ++ s))) fields;
  digitEnd :: String -> Int -> Int;
  digitEnd text i =
    if (i >= stringLength text)
    then i
    else let {
           c = stringCodeAt text i
         } in
         if ((c >= 48) && (c <= 57)) then digitEnd text (i + 1) else i;
  unpackFrom :: String -> Int -> Either String (List String);
  unpackFrom text start =
    if (start == stringLength text)
    then Right Nil
    else do {
           let {
             end = digitEnd text start
           };
           ensure
             ((end > start) &&
              (((end - start) <= 9) &&
               ((end < stringLength text) && (stringCodeAt text end == 58))))
             "malformed module artifact framing";
           let {
             n = readInt (stringSlice text start (end - start))
           };
           ensure (n <= ((stringLength text - end) - 1)) "truncated module artifact";
           rest <- unpackFrom text ((end + 1) + n);
           Right (Cons (stringSlice text (end + 1) n) rest)
         };
  unpack text = unpackFrom text 0;
  fingerprintFrom :: String -> Int -> Int -> Int -> String;
  fingerprintFrom text i a b =
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
         seq nextA (seq nextB (fingerprintFrom text (i + 1) nextA nextB));
  fingerprint text = fingerprintFrom text 0 0 1;
  -- Exact summaries of the two existing rolling checksums. A summary composes
  -- with any initial state, so shared datatype prefixes need not be rescanned
  -- for every independently checked fragment. The serialized digest is unchanged.
  fingerprintStateFrom :: String -> Int -> Int -> Int -> Pair Int Int;
  fingerprintStateFrom text i a b =
    if (i >= stringLength text)
    then Pair a b
    else let {
           code = stringCodeAt text i
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (fingerprintStateFrom text (i + 1) nextA nextB));
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
  fingerprintPart :: String -> Quad Int Int Int Int;
  fingerprintPart text =
    case fingerprintStateFrom text 0 0 0 of {
      Pair a b ->
        Quad (fingerprintPower 65599 (stringLength text) 2147483647)
          (fingerprintPower 131 (stringLength text) 2147483629)
          a
          b
    };
  fingerprintAppend :: Pair Int Int -> Quad Int Int Int Int -> Pair Int Int;
  fingerprintAppend (Pair a b) (Quad powerA powerB partA partB) =
    let {
      nextA = (((a * powerA) + partA) % 2147483647)
    } in
    let {
      nextB = (((b * powerB) + partB) % 2147483629)
    } in
    seq nextA (seq nextB (Pair nextA nextB));
  fingerprintAfter :: Pair Int Int -> String -> String;
  fingerprintAfter (Pair a b) text = fingerprintFrom text 0 a b;
  entityEncoding (Modules.Entity owner name role) =
    let {
      result =
        case role of {
          Modules.Value -> Pair "value" "";
          Modules.Datatype -> Pair "data" "";
          Modules.Class -> Pair "class" "";
          Modules.Constructor p -> Pair "constructor" p;
          Modules.Method p -> Pair "method" p;
          Modules.BuiltinType -> Pair "builtin" "";
          Modules.Primitive p -> Pair "primitive" (Primitive.primitiveName p);
          Modules.Boolean b -> Pair "bool" (if b then "true" else "false")
        }
    } in
    pack (Cons owner (Cons name (Cons (fst result) (Cons (snd result) Nil))));
  noEntityArg :: forall a. a -> String -> Either String a;
  noEntityArg role arg = if eqString arg "" then Right role else Left "unexpected entity argument";
  decodeEntity text =
    do {
      fields <- unpack text;
      case fields of {
        Cons owner (Cons name (Cons tag (Cons arg Nil))) ->
          do {
            role <-
              let {
                matchValueShared9 = tag
              } in
              if MLF.Primitive.eqString matchValueShared9 "value"
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
      SCon c ts -> ("(" ++ (intercalate " " (Cons c (map prettySourceType ts)) ++ ")"));
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
  prettyPredicate (SPredicate c ts) = intercalate " " (Cons c (map prettySourceType ts));
  prettyContext :: List SPredicate -> String;
  prettyContext ps =
    if null ps then "" else ("(" ++ (intercalate ", " (map prettyPredicate ps) ++ ") => "));
  prettyParameter (Pair n k) = ("(" ++ (n ++ (" : " ++ (K.prettyKind k ++ ")"))));
  prettyMethodName n = if Lexer.sharedIdentifier n then n else "(" ++ (n ++ ")");
  prettyClass c =
    ("class " ++
     (prettyContext (Classes.superclasses c) ++
      (Classes.className c ++
       (" " ++
        (intercalate " " (map prettyParameter (Classes.classParameters c)) ++
         (" where { " ++
          (intercalate "; "
             (map (\(Pair n ty) -> (prettyMethodName n ++ (" : " ++ prettySourceType ty)))
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
              (map (\(Pair n _) -> (prettyMethodName n ++ " = panic \"interface method\""))
                 (Classes.instanceMethods i)) ++
            " };"))))))));
  pairEncoding (Pair a b) = pack (Cons a (Cons b Nil));
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
          (map (\(Pair n t) -> pairEncoding (Pair n (Pretty.prettyType (normalType t))))
             (unitBindings i))
    } in
    Cons "MLFI-2"
      (Cons (unitName i)
         (Cons (pack (map pairEncoding (unitDependencies i)))
            (Cons (pack (map entityEncoding (unitExports i)))
               (Cons metadata (Cons (pack (map fst (unitInstances i))) (Cons bindings Nil))))));
  interfaceFingerprint i = fingerprint (pack (interfaceFields i));
  encodeInterface i = pack (snoc (interfaceFields i) (unitObjectFingerprint i));
  decodePair text =
    do {
      fields <- unpack text;
      case fields of {
        Cons a (Cons b Nil) -> Right (Pair a b);
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
        Cons matchValueShared12 matchValueShared13 ->
          if MLF.Primitive.eqString matchValueShared12 "MLFI-2"
          then case matchValueShared13 of {
                 Cons matchValueShared14 matchValueShared15 ->
                   case matchValueShared15 of {
                     Cons matchValueShared16 matchValueShared17 ->
                       case matchValueShared17 of {
                         Cons matchValueShared18 matchValueShared19 ->
                           case matchValueShared19 of {
                             Cons matchValueShared20 matchValueShared21 ->
                               case matchValueShared21 of {
                                 Cons matchValueShared22 matchValueShared23 ->
                                   case matchValueShared23 of {
                                     Cons matchValueShared24 matchValueShared25 ->
                                       case matchValueShared25 of {
                                         Cons matchValueShared26 matchValueShared27 ->
                                           case matchValueShared27 of {
                                             Nil ->
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
                                                            Pair n ty ->
                                                              do {
                                                                t <- XP.parseType ty;
                                                                Right (Pair n t)
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
                                                   (Cons name
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
                                                 "unsupported or malformed module interface (expected MLFI-2)"
                                           };
                                         _ ->
                                           Left
                                             "unsupported or malformed module interface (expected MLFI-2)"
                                       };
                                     _ ->
                                       Left
                                         "unsupported or malformed module interface (expected MLFI-2)"
                                   };
                                 _ ->
                                   Left
                                     "unsupported or malformed module interface (expected MLFI-2)"
                               };
                             _ -> Left "unsupported or malformed module interface (expected MLFI-2)"
                           };
                         _ -> Left "unsupported or malformed module interface (expected MLFI-2)"
                       };
                     _ -> Left "unsupported or malformed module interface (expected MLFI-2)"
                   };
                 _ -> Left "unsupported or malformed module interface (expected MLFI-2)"
               }
          else Left "unsupported or malformed module interface (expected MLFI-2)";
        _ -> Left "unsupported or malformed module interface (expected MLFI-2)"
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
      (Cons "MLFO-1"
         (Cons (unitName i)
            (Cons (interfaceFingerprint i) (Cons (Pretty.prettyTerm (objectTerm object)) Nil))));
  -- Crate objects and inference queries supply datatype contexts separately.
  -- Keep metadata and payload contexts distinct: a malformed object must not be
  -- repaired by replacing its payload's declarations with its header's layouts.
  objectContext :: UnitObject -> List DataDecl;
  objectContext object =
    case objectTerm object of {
      XWithData ds _ -> ds;
      _ -> Nil
    };
  objectBody :: UnitObject -> XTerm;
  objectBody object =
    case objectTerm object of {
      XWithData _ body -> body;
      body -> body
    };
  withInterfaceData :: UnitInterface -> List DataDecl -> String -> UnitInterface;
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
      header = withInterfaceData (objectInterface object) Nil (fingerprint body)
    } in
    pack (Cons "MLFF-2" (Cons (encodeInterface header) (Cons body Nil)));
  decodeContextualObject :: List DataDecl -> List DataDecl -> String -> Either String UnitObject;
  decodeContextualObject headerData bodyData input =
    decodeContextualObjectAfter
      (fingerprintStateFrom (unlines (map D.prettyDeclaration bodyData)) 0 0 1)
      headerData
      bodyData
      input;
  decodeContextualObjectAfter :: Pair Int Int ->
                                 List DataDecl ->
                                 List DataDecl -> String -> Either String UnitObject;
  decodeContextualObjectAfter prefix headerData bodyData input =
    do {
      fields <- unpack input;
      let {
        matchValueShared28 = fields
      } in
      case matchValueShared28 of {
        Cons matchValueShared29 matchValueShared30 ->
          if MLF.Primitive.eqString matchValueShared29 "MLFF-2"
          then case matchValueShared30 of {
                 Cons matchValueShared31 matchValueShared32 ->
                   case matchValueShared32 of {
                     Cons matchValueShared33 matchValueShared34 ->
                       case matchValueShared34 of {
                         Nil ->
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
                             ensure (eqString input (encodeContextualObject object))
                               "noncanonical contextual inference fragment";
                             Right object
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
        Cons matchValueShared36 matchValueShared37 ->
          if MLF.Primitive.eqString matchValueShared36 "MLFO-1"
          then case matchValueShared37 of {
                 Cons matchValueShared38 matchValueShared39 ->
                   case matchValueShared39 of {
                     Cons matchValueShared40 matchValueShared41 ->
                       case matchValueShared41 of {
                         Cons matchValueShared42 matchValueShared43 ->
                           case matchValueShared43 of {
                             Nil ->
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
  mapTerm name variable term =
    case term of {
      XVarTerm n -> XVarTerm (name n);
      XAbs n ty b -> XAbs (name n) (mapType variable ty) (mapTerm name variable b);
      XApp a b -> XApp (mapTerm name variable a) (mapTerm name variable b);
      XTypeAbs a bound b ->
        XTypeAbs (variable a) (mapType variable bound) (mapTerm name variable b);
      XTypeApp a p -> XTypeApp (mapTerm name variable a) (mapComputation variable p);
      XLet n a b -> XLet (name n) (mapTerm name variable a) (mapTerm name variable b);
      XLetRec bs b ->
        XLetRec
          (map (\(Triple n t a) -> Triple (name n) (mapType variable t) (mapTerm name variable a))
             bs)
          (mapTerm name variable b);
      XPrimitive p ts -> XPrimitive p (map (mapType variable) ts);
      XConstructor c ts -> XConstructor c (map (mapType variable) ts);
      XCase a t bs ->
        XCase (mapTerm name variable a) (mapType variable t)
          (map (\(XAlternative p b) -> XAlternative (mapPattern name p) (mapTerm name variable b))
             bs);
      XWithData ds b -> XWithData ds (mapTerm name variable b);
      _ -> term
    };
  -- Dense renumbering also handles valid object IDs near the parser's Int64
  -- limit. Adding an offset to original IDs would overflow that wire format.
  typeIdentities :: XType -> Set Int -> Set Int;
  typeIdentities ty seen =
    case ty of {
      XVar (XTyVar a) -> Set.insert compareInt a seen;
      XArrow a b -> typeIdentities b (typeIdentities a seen);
      XCon _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XApply a b -> typeIdentities b (typeIdentities a seen);
      XForall (XTyVar a) bound b ->
        typeIdentities b (typeIdentities bound (Set.insert compareInt a seen));
      _ -> seen
    };
  computationIdentities :: XComputation -> Set Int -> Set Int;
  computationIdentities p seen =
    case p of {
      XBottom t -> typeIdentities t seen;
      XHyp (XTyVar a) -> Set.insert compareInt a seen;
      XInner q -> computationIdentities q seen;
      XOuter (XTyVar a) q -> computationIdentities q (Set.insert compareInt a seen);
      XIntro (XTyVar a) -> Set.insert compareInt a seen;
      XIntroKind (XTyVar a) _ -> Set.insert compareInt a seen;
      XThen a b -> computationIdentities b (computationIdentities a seen);
      _ -> seen
    };
  termIdentities :: XTerm -> Set Int -> Set Int;
  termIdentities term seen =
    case term of {
      XVarTerm n -> Set.insert compareInt (X.nameId n) seen;
      XAbs n ty b -> termIdentities b (typeIdentities ty (Set.insert compareInt (X.nameId n) seen));
      XApp a b -> termIdentities b (termIdentities a seen);
      XTypeAbs (XTyVar a) bound b ->
        termIdentities b (typeIdentities bound (Set.insert compareInt a seen));
      XTypeApp a p -> computationIdentities p (termIdentities a seen);
      XLet n a b -> termIdentities b (termIdentities a (Set.insert compareInt (X.nameId n) seen));
      XLetRec bs b ->
        termIdentities b
          (foldl
             (\acc (Triple n t a) ->
                termIdentities a (typeIdentities t (Set.insert compareInt (X.nameId n) acc)))
             seen
             bs);
      XPrimitive _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XConstructor _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XCase a t bs ->
        foldl
          (\acc (XAlternative p b) ->
             termIdentities b
               (foldl (\ids n -> Set.insert compareInt (X.nameId n) ids) acc (X.patternNames p)))
          (typeIdentities t (termIdentities a seen))
          bs;
      XWithData _ b -> termIdentities b seen;
      _ -> seen
    };
  freshObject serial term =
    let {
      ids = Set.toList (termIdentities term Set.empty)
    } in
    let {
      replacements = M.fromList compareInt (zip ids (range serial ((serial + length ids) - 1)))
    } in
    let {
      rename = \n -> M.findWithDefault compareInt (panic "missing object identity") n replacements
    } in
    Pair (serial + length ids)
      (mapTerm (\(XName n hint) -> XName (rename n) hint) (\(XTyVar n) -> XTyVar (rename n)) term);
  splitParameters :: XTerm -> Pair (List (Pair XName XType)) XTerm;
  splitParameters term =
    case term of {
      XAbs n ty b ->
        case splitParameters b of {
          Pair ps rest -> Pair (Cons (Pair n ty) ps) rest
        };
      _ -> Pair Nil term
    };
  mergeDeclaration declarations d =
    case filter (\other -> eqString (D.datatypeName other) (D.datatypeName d)) declarations of {
      Nil -> Right (snoc declarations d);
      Cons other Nil ->
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
        if MLF.Primitive.eqString matchValueShared50 "Unit"
        then case matchValueShared51 of {
               Nil -> Right body;
               _ -> Left "invalid inference fragment declaration spine"
             }
        else Left "invalid inference fragment declaration spine";
      _ -> Left "invalid inference fragment declaration spine"
    };
  sameSignature a b = (eqString (fst a) (fst b) && T.alphaEq (snd a) (snd b));
  removeEntryParameters :: Map String XType ->
                           Map String (Pair XName XType) -> XTerm -> Either String XTerm;
  removeEntryParameters signatures available term =
    case term of {
      XWithData _ b -> removeEntryParameters signatures available b;
      XTypeAbs a bound b ->
        mapEither (XTypeAbs a bound) (removeEntryParameters signatures available b);
      XTypeApp b p -> mapEither (\x -> XTypeApp x p) (removeEntryParameters signatures available b);
      XLetRec bs b ->
        do {
          ensure (eqList eqString (map (\(Triple n _ _) -> X.nameHint n) bs) (M.keys signatures))
            "entry parameter mismatch";
          replacements <-
            traverseEither
              (\(Triple n ty _) ->
                 case M.lookup compareString (X.nameHint n) available of {
                   Nothing -> Left ("missing entry symbol: " ++ X.nameHint n);
                   Just (Pair actual expected) ->
                     do {
                       ensure (T.alphaEq ty expected)
                         ("entry parameter type mismatch: " ++ X.nameHint n);
                       Right (Pair n actual)
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
