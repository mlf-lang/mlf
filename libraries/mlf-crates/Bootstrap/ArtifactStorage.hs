-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ArtifactStorage where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Unicode as U;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Primitive as P;
  -- Byte arrays remain private immutable snapshots after the raw read. A new
  -- binary magic commits to the binary decoder; corruption cannot downgrade.
  data Input = LegacyText String | BinaryInput W.Graph;
  hasNul :: String -> Int -> Bool;
  hasNul text index = if index >= stringLength text then False
    else stringCodeAt text index == 0 || hasNul text (index + 1);
  maxBytes :: Int;
  maxBytes = 268435456;
  readRaw :: String -> IO (Either String ByteArray);
  readRaw path = do {
    result <- readByteFileOrError path maxBytes;
    ioReturn (case result of { (,) error bytes ->
      if eqString error "" then Right bytes else Left error })
  };
  decode :: Int -> ByteArray -> IO (Either String Input);
  decode = decodeWithText [];
  decodeWithText hints schema bytes = do {
    binary <- W.hasMagic bytes;
    if binary then do {
      decoded <- W.decodeGraphWithText hints W.defaultLimits schema bytes;
      ioReturn (mapEither BinaryInput decoded)
    } else do {
      decoded <- W.strictUtf8 maxBytes bytes;
      ioReturn (mapEither LegacyText decoded)
    }
  };
  read :: Int -> String -> IO (Either String Input);
  read = readWithText [];
  readWithText hints schema path = do {
    raw <- readRaw path;
    case raw of { Left error -> ioReturn (Left error); Right bytes -> decodeWithText hints schema bytes }
  };
  encode :: Int -> [] W.Value -> IO (Either String ByteArray);
  encode schema roots = W.encode W.defaultLimits schema roots;
  writeRaw :: String -> ByteArray -> IO (Either String ());
  writeRaw path bytes = do {
    error <- writeByteFileOrError path bytes;
    ioReturn (if eqString error "" then Right () else Left error)
  };
  write :: Int -> String -> [] W.Value -> IO (Either String ());
  write schema path roots = do {
    encoded <- encode schema roots;
    case encoded of { Left error -> ioReturn (Left error); Right bytes -> writeRaw path bytes }
  };
  -- Same cooperating publisher protocol as the existing text writer. This is
  -- atomic replacement of each file, not a two-file transaction or fsync claim.
  writeAtomic :: Int -> String -> [] W.Value -> IO (Either String ());
  writeAtomic schema path roots =
    if hasNul path 0 then ioReturn (Left "file path contains NUL") else do {
      let { destination = if Host.absolutePath path then path else "./" ++ path };
      isDirectory <- directoryExists destination;
      if isDirectory then ioReturn (Left "artifact destination is a directory") else do {
        written <- write schema (destination ++ ".new") roots;
        case written of {
          Left error -> ioReturn (Left error);
          Right _ -> do {
            arguments <- Host.hostArguments ["/bin/mv", "-f", destination ++ ".new", destination];
            code <- runProcess "" (concatMapString (\field -> field ++ stringFromCode 0)
              (append ["1800", "", "", ""] arguments));
            ioReturn (if code == 0 then Right () else Left "cannot publish binary artifact")
          }
        }
      }
    };
  sameBytesFrom :: ByteArray -> ByteArray -> Int -> Int -> IO Bool;
  sameBytesFrom a b count index =
    if index == count then ioReturn True else do {
      x <- readByteArray a index;
      y <- readByteArray b index;
      if x == y then sameBytesFrom a b count (index + 1) else ioReturn False
    };
  sameBytes :: ByteArray -> ByteArray -> IO Bool;
  sameBytes a b = do {
    na <- lengthByteArray a; nb <- lengthByteArray b;
    if na == nb then sameBytesFrom a b na 0 else ioReturn False
  };
  -- Typed wire decoding preserves all IDs and hints. Production admission is a
  -- separate syntax-domain check; no text roundtrip or alpha normalization.
  -- Every recursive syntax/list edge is an explicit work item.
  data AdmitTask =
    AdmitTerm XTerm | AdmitType XType | AdmitTypes ([] XType) |
    AdmitComputation XComputation | AdmitName XName | AdmitVariable XTyVar |
    AdmitRec ([] ((,,) XName XType XTerm)) | AdmitAlternatives ([] XAlternative) |
    AdmitPattern XPattern | AdmitNames ([] (Maybe XName)) |
    AdmitData Bool ([] DataDecl) | AdmitConstructors Bool ([] ConstructorDecl) |
    AdmitFields Bool ([] Field) | AdmitField Bool Field | AdmitParameters Bool ([] ((,) String Kind)) |
    AdmitClasses ([] SClassDecl) | AdmitInstances ([] ((,) String SInstanceDecl)) |
    AdmitMethods ([] ((,) String SType)) | AdmitMethodNames ([] ((,) String SExpr)) |
    AdmitSurface SType | AdmitSurfaces ([] SType) | AdmitPredicates ([] SPredicate) |
    AdmitBindings ([] ((,) String XType));
  syntaxFailure :: String -> Either String ();
  syntaxFailure what = Left ("binary artifact syntax admission: " ++ what);
  syntaxName :: (Int -> Bool) -> [] String -> String -> Bool;
  syntaxName first reserved name = D.identifier first name && not (elem eqString name reserved);
  lowerSyntax :: String -> Bool;
  lowerSyntax = syntaxName U.isLower Parser.reservedWords;
  binderSyntax :: Bool -> String -> Bool;
  binderSyntax metadata = syntaxName U.isLower (if metadata then Parser.reservedWords else XP.dataReserved);
  dataConstructorSyntax :: Bool -> String -> Bool;
  dataConstructorSyntax metadata name = if metadata
    then upperSyntax name || eqString name "True" || eqString name "False"
    else builtinSyntax name || syntaxName U.isUpper XP.dataReserved name;
  upperSyntax :: String -> Bool;
  upperSyntax = syntaxName U.isUpper Parser.reservedWords;
  -- Builtin tuple/list names are tokens in both metadata and xMLF grammars.
  builtinSyntax :: String -> Bool;
  builtinSyntax name = eqString name "[]" || eqString name ":" || eqString name "()"
    || (let { count = stringLength name } in count >= 3 && count <= 65
      && stringCodeAt name 0 == 40 && stringCodeAt name (count - 1) == 41
      && commasOnly name 1 (count - 1));
  metadataBuiltinSyntax :: String -> Bool;
  metadataBuiltinSyntax name = not (eqString name ":") && builtinSyntax name;
  commasOnly :: String -> Int -> Int -> Bool;
  commasOnly name index end = if index == end then True
    else stringCodeAt name index == 44 && commasOnly name (index + 1) end;
  upperReferenceSyntax :: String -> Bool;
  upperReferenceSyntax name = referenceSyntax name 0 0;
  referenceSyntax :: String -> Int -> Int -> Bool;
  referenceSyntax name begin index =
    if index == stringLength name || stringCodeAt name index == 46
    then let { part = stringSlice name begin (index - begin);
      valid = upperSyntax part || (index == stringLength name
        && (eqString part "True" || eqString part "False")) } in
      valid && (if index == stringLength name then True else referenceSyntax name (index + 1) (index + 1))
    else referenceSyntax name begin (index + 1);
  methodSyntax :: String -> Bool;
  methodSyntax name = lowerSyntax name || elem eqString name Lexer.sharedValueOperators;
  admit :: [] AdmitTask -> Either String ();
  admit tasks = case tasks of {
    [] -> Right ();
    (:) task rest -> case task of {
      AdmitName (XName identity hint) ->
        if identity >= 0 && D.identifier U.isAlpha hint
        then admit rest else syntaxFailure "invalid term identity or hint";
      AdmitVariable (XTyVar identity) ->
        if identity /= (-9223372036854775808) then admit rest
        else syntaxFailure "type identity outside legacy decimal domain";
      AdmitType ty -> case ty of {
        XVar variable -> admit ((:) (AdmitVariable variable) rest);
        XBot -> admit rest; XBotKind _ -> admit rest;
        XArrow a b -> admit ((:) (AdmitType a) ((:) (AdmitType b) rest));
        XApply a b -> admit ((:) (AdmitType a) ((:) (AdmitType b) rest));
        XCon name arguments -> if builtinSyntax name || syntaxName U.isUpper XP.reservedWords name
          then admit ((:) (AdmitTypes arguments) rest) else syntaxFailure "invalid xMLF type constructor";
        XForall variable bound body -> admit ((:) (AdmitVariable variable)
          ((:) (AdmitType bound) ((:) (AdmitType body) rest)))
      };
      AdmitTypes values -> case values of { [] -> admit rest; (:) x xs ->
        admit ((:) (AdmitType x) ((:) (AdmitTypes xs) rest)) };
      AdmitBindings values -> case values of { [] -> admit rest; (:) ((,) _ ty) xs ->
        admit ((:) (AdmitType ty) ((:) (AdmitBindings xs) rest)) };
      AdmitComputation computation -> case computation of {
        XRefl -> admit rest; XElim -> admit rest;
        XBottom ty -> admit ((:) (AdmitType ty) rest);
        XHyp variable -> admit ((:) (AdmitVariable variable) rest);
        XIntro variable -> admit ((:) (AdmitVariable variable) rest);
        XIntroKind variable _ -> admit ((:) (AdmitVariable variable) rest);
        XInner body -> admit ((:) (AdmitComputation body) rest);
        XOuter variable body -> admit ((:) (AdmitVariable variable) ((:) (AdmitComputation body) rest));
        XThen a b -> admit ((:) (AdmitComputation a) ((:) (AdmitComputation b) rest))
      };
      AdmitTerm term -> case term of {
        XVarTerm name -> admit ((:) (AdmitName name) rest);
        XAbs name ty body -> admit ((:) (AdmitName name) ((:) (AdmitType ty) ((:) (AdmitTerm body) rest)));
        XApp a b -> admit ((:) (AdmitTerm a) ((:) (AdmitTerm b) rest));
        XTypeAbs variable ty body -> admit ((:) (AdmitVariable variable) ((:) (AdmitType ty) ((:) (AdmitTerm body) rest)));
        XTypeApp body computation -> admit ((:) (AdmitTerm body) ((:) (AdmitComputation computation) rest));
        XLet name rhs body -> admit ((:) (AdmitName name) ((:) (AdmitTerm rhs) ((:) (AdmitTerm body) rest)));
        XLetRec bindings body -> admit ((:) (AdmitRec bindings) ((:) (AdmitTerm body) rest));
        XIntTerm _ -> admit rest; XDoubleTerm _ -> admit rest;
        XBoolTerm _ -> admit rest; XStringTerm _ -> admit rest;
        XPrimitive _ arguments -> admit ((:) (AdmitTypes arguments) rest);
        XConstructor name arguments -> if builtinSyntax name || syntaxName U.isUpper XP.reservedWords name
          then admit ((:) (AdmitTypes arguments) rest) else syntaxFailure "invalid xMLF constructor";
        XCase body ty alternatives -> admit ((:) (AdmitTerm body) ((:) (AdmitType ty) ((:) (AdmitAlternatives alternatives) rest)));
        XWithData declarations body -> admit ((:) (AdmitData False declarations) ((:) (AdmitTerm body) rest))
      };
      AdmitRec values -> case values of { [] -> admit rest; (:) ((,,) name ty body) xs ->
        admit ((:) (AdmitName name) ((:) (AdmitType ty) ((:) (AdmitTerm body) ((:) (AdmitRec xs) rest)))) };
      AdmitAlternatives values -> case values of { [] -> admit rest; (:) (XAlternative pattern body) xs ->
        admit ((:) (AdmitPattern pattern) ((:) (AdmitTerm body) ((:) (AdmitAlternatives xs) rest))) };
      AdmitPattern pattern -> case pattern of {
        XDefaultPattern name -> admit ((:) (AdmitNames [name]) rest);
        XConstructorPattern name fields -> if builtinSyntax name || syntaxName U.isUpper XP.reservedWords name
          then admit ((:) (AdmitNames fields) rest) else syntaxFailure "invalid pattern constructor"
      };
      AdmitNames values -> case values of { [] -> admit rest;
        (:) Nothing xs -> admit ((:) (AdmitNames xs) rest);
        (:) (Just name) xs -> admit ((:) (AdmitName name) ((:) (AdmitNames xs) rest)) };
      AdmitData metadata values -> case values of { [] -> admit rest; (:) declaration xs ->
        if dataConstructorSyntax metadata (D.datatypeName declaration)
          && not (null (D.datatypeConstructors declaration))
        then admit ((:) (AdmitParameters metadata (D.datatypeBinders declaration))
          ((:) (AdmitConstructors metadata (D.datatypeConstructors declaration)) ((:) (AdmitData metadata xs) rest)))
        else syntaxFailure "invalid datatype name or empty constructors" };
      AdmitConstructors metadata values -> case values of { [] -> admit rest; (:) (ConstructorDecl name fields) xs ->
        if dataConstructorSyntax metadata name
        then admit ((:) (AdmitFields metadata fields) ((:) (AdmitConstructors metadata xs) rest))
        else syntaxFailure "invalid datatype constructor name" };
      AdmitParameters metadata values -> case values of { [] -> admit rest; (:) ((,) name _) xs ->
        if binderSyntax metadata name then admit ((:) (AdmitParameters metadata xs) rest)
        else syntaxFailure "invalid type parameter" };
      AdmitFields metadata values -> case values of { [] -> admit rest; (:) x xs ->
        admit ((:) (AdmitField metadata x) ((:) (AdmitFields metadata xs) rest)) };
      AdmitField metadata field -> case field of {
        Parameter name -> if binderSyntax metadata name then admit rest else syntaxFailure "invalid field parameter";
        Function a b -> admit ((:) (AdmitField metadata a) ((:) (AdmitField metadata b) rest));
        Application a b -> admit ((:) (AdmitField metadata a) ((:) (AdmitField metadata b) rest));
        Applied name arguments -> if (if metadata
          then metadataBuiltinSyntax name || upperReferenceSyntax name
          else builtinSyntax name || syntaxName U.isUpper XP.dataReserved name)
          then admit ((:) (AdmitFields metadata arguments) rest) else syntaxFailure "invalid field constructor";
        Quantified name _ body -> if binderSyntax metadata name then admit ((:) (AdmitField metadata body) rest)
          else syntaxFailure "invalid quantified field binder"
      };
      AdmitClasses values -> case values of { [] -> admit rest;
        (:) (SClassDecl name parameters supers methods) xs ->
          if upperSyntax name && not (null parameters)
          then admit ((:) (AdmitParameters True parameters) ((:) (AdmitPredicates supers)
            ((:) (AdmitMethods methods) ((:) (AdmitClasses xs) rest))))
          else syntaxFailure "invalid class name or empty parameters" };
      AdmitInstances values -> case values of { [] -> admit rest;
        (:) ((,) _ (SInstanceDecl parameters predicates name arguments methods)) xs ->
          if upperReferenceSyntax name && not (null arguments)
          then admit ((:) (AdmitParameters True parameters) ((:) (AdmitPredicates predicates)
            ((:) (AdmitSurfaces arguments) ((:) (AdmitMethodNames methods) ((:) (AdmitInstances xs) rest)))))
          else syntaxFailure "invalid instance class or empty head" };
      AdmitMethods values -> case values of { [] -> admit rest; (:) ((,) name ty) xs ->
        if methodSyntax name then admit ((:) (AdmitSurface ty) ((:) (AdmitMethods xs) rest))
        else syntaxFailure "invalid class method name" };
      -- Interface instance bodies are stripped by the metadata codec, exactly
      -- as in Separate.stripInstance. Only the retained method names are syntax.
      AdmitMethodNames values -> case values of { [] -> admit rest; (:) ((,) name _) xs ->
        if methodSyntax name then admit ((:) (AdmitMethodNames xs) rest)
        else syntaxFailure "invalid instance method name" };
      AdmitSurfaces values -> case values of { [] -> admit rest; (:) x xs ->
        admit ((:) (AdmitSurface x) ((:) (AdmitSurfaces xs) rest)) };
      AdmitSurface ty -> case ty of {
        STVar name -> if lowerSyntax name then admit rest else syntaxFailure "invalid surface type variable";
        SBottom -> admit rest; SBottomKind _ -> admit rest;
        SArrow a b -> admit ((:) (AdmitSurface a) ((:) (AdmitSurface b) rest));
        STypeApp a b -> admit ((:) (AdmitSurface a) ((:) (AdmitSurface b) rest));
        SCon name arguments -> if metadataBuiltinSyntax name || upperReferenceSyntax name
          then admit ((:) (AdmitSurfaces arguments) rest) else syntaxFailure "invalid surface type constructor";
        SForall _ name bound body -> if lowerSyntax name
          then admit ((:) (AdmitSurface bound) ((:) (AdmitSurface body) rest))
          else syntaxFailure "invalid surface type binder";
        SQualified predicates body -> admit ((:) (AdmitPredicates predicates) ((:) (AdmitSurface body) rest))
      };
      AdmitPredicates values -> case values of { [] -> admit rest; (:) (SPredicate name arguments) xs ->
        if upperReferenceSyntax name && (not (null arguments)
          || eqString (Parser.referenceLeaf name) "HasCallStack" || eqString name "MLFHasCallStack")
        then admit ((:) (AdmitSurfaces arguments) ((:) (AdmitPredicates xs) rest))
        else syntaxFailure "invalid predicate class or empty arguments" }
    }
  };
  -- The old decoder's interface admission, now over typed structural fields.
  -- No CheckedTerm/evidence is deserialized or accepted from the wire.
  validateUnitInterface :: Separate.UnitInterface -> Either String ();
  validateUnitInterface iface = do {
    let { dependencies = Separate.unitDependencies iface;
          instances = Separate.unitInstances iface;
          bindings = Separate.unitBindings iface };
    ensure (length dependencies == length (nubBy eqString (map fst dependencies))
      && length instances == length (nubBy eqString (map fst instances))
      && length bindings == length (nubBy eqString (map fst bindings)))
      "duplicate interface entry";
    ensure (all (\entry -> Set.null (T.freeVars (snd entry))) bindings)
      "interface has open types";
    ensure (stringLength (Separate.unitName iface) > 0
      && stringLength (Separate.unitObjectFingerprint iface) > 0)
      "incomplete module interface";
    _ <- traverseEither Separate.validModuleName
      ((:) (Separate.unitName iface) (append (map fst dependencies)
        (map Modules.owner (Separate.unitExports iface))));
    admit [AdmitData True (Separate.unitData iface), AdmitClasses (Separate.unitClasses iface),
      AdmitInstances instances, AdmitBindings bindings];
    _ <- D.validateDeclarations (Separate.unitData iface);
    Right ()
  };
  checkUnit :: Separate.UnitObject -> Either String Separate.UnitObject;
  checkUnit object = do {
    let { iface = Separate.objectInterface object; term = Separate.objectTerm object };
    validateUnitInterface iface;
    admit [AdmitTerm term];
    ensure (eqString (Separate.fingerprint (Pretty.prettyTerm term))
      (Separate.unitObjectFingerprint iface)) "module object checksum mismatch";
    checked <- Checked.check term;
    Right (Separate.CheckedUnitObject iface checked)
  }
  ;
  -- V2-only bounded exact legacy rendering. Bounds reserve scalar characters
  -- and UTF-8 bytes separately: pack/fingerprint use scalars, not UTF-8.
  -- None of these helpers changes an old codec, checker or default limit.
  data RenderBounds = RenderBounds Int Int;
  data RenderSummary = RenderSummary Int Int Separate.FingerprintEncoding;
  renderBoundScalars :: RenderBounds -> Int;
  renderBoundScalars (RenderBounds n _) = n;
  renderBoundUtf8 :: RenderBounds -> Int;
  renderBoundUtf8 (RenderBounds _ n) = n;
  renderSummaryScalars :: RenderSummary -> Int;
  renderSummaryScalars (RenderSummary n _ _) = n;
  renderSummaryUtf8 :: RenderSummary -> Int;
  renderSummaryUtf8 (RenderSummary _ n _) = n;
  renderSummaryEncoding :: RenderSummary -> Separate.FingerprintEncoding;
  renderSummaryEncoding (RenderSummary _ _ encoding) = encoding;
  v2ValidBounds :: RenderBounds -> Bool;
  v2ValidBounds (RenderBounds scalars bytes) = scalars >= 0 && scalars <= 2147483647
    && bytes >= 0 && bytes <= 2147483647;
  v2Room :: RenderBounds -> Int -> Int -> Int -> Int -> Either String ();
  v2Room bounds usedScalars usedBytes scalars bytes = do {
    ensure (v2ValidBounds bounds && usedScalars >= 0 && usedBytes >= 0
      && usedScalars <= renderBoundScalars bounds && usedBytes <= renderBoundUtf8 bounds)
      "invalid v2 render bounds";
    ensure (scalars >= 0 && scalars <= renderBoundScalars bounds - usedScalars)
      "v2 rendered scalar limit exceeded";
    ensure (bytes >= 0 && bytes <= renderBoundUtf8 bounds - usedBytes)
      "v2 rendered UTF-8 limit exceeded"
  };
  v2ValidSummary :: RenderSummary -> Bool;
  v2ValidSummary (RenderSummary scalars bytes encoding) = case encoding of {
    Separate.FingerprintEncoding count pa pb a b ->
      scalars >= 0 && scalars <= 2147483647 && bytes >= scalars
      && bytes <= 2147483647 && count == scalars
      && pa >= 0 && pa < 2147483647 && pb >= 0 && pb < 2147483629
      && a >= 0 && a < 2147483647 && b >= 0 && b < 2147483629
  };
  v2ForceEncoding :: Separate.FingerprintEncoding -> Separate.FingerprintEncoding;
  v2ForceEncoding encoded = case encoded of {
    Separate.FingerprintEncoding count pa pb a b ->
      seq count (seq pa (seq pb (seq a (seq b encoded))))
  };
  v2SummaryText :: RenderBounds -> String -> Either String RenderSummary;
  v2SummaryText bounds text = do {
    v2Room bounds 0 0 (stringLength text) 0;
    bytes <- W.utf8Size (renderBoundUtf8 bounds) text;
    v2Room bounds 0 0 (stringLength text) bytes;
    let { encoded = v2ForceEncoding (Separate.encodingText text) };
    seq encoded (Right (RenderSummary (stringLength text) bytes encoded))
  };
  v2SummaryAppend :: RenderBounds -> RenderSummary -> RenderSummary -> Either String RenderSummary;
  v2SummaryAppend bounds left right = case left of {
    RenderSummary n bytes encoded -> case right of {
      RenderSummary m more other -> do {
        ensure (v2ValidSummary left && v2ValidSummary right) "invalid v2 render summary";
        v2Room bounds n bytes m more;
        let { total = n + m; totalBytes = bytes + more;
              joined = v2ForceEncoding (Separate.encodingAppend encoded other) };
        seq total (seq totalBytes (seq joined (Right (RenderSummary total totalBytes joined))))
      }
    }
  };
  v2DecimalLength :: Int -> Int;
  v2DecimalLength value = if value < 10 then 1 else 1 + v2DecimalLength (quotInt value 10);
  v2IntLength :: Int -> Int;
  v2IntLength value = if value >= 0 then v2DecimalLength value
    else if value == (-9223372036854775808) then 20
    else 1 + v2DecimalLength (0 - value);
  v2SummaryPack :: RenderBounds -> [] RenderSummary -> Either String RenderSummary;
  v2SummaryPack bounds values = v2SummaryPackAt bounds values (RenderSummary 0 0 Separate.encodingEmpty);
  v2SummaryPackAt :: RenderBounds -> [] RenderSummary -> RenderSummary -> Either String RenderSummary;
  v2SummaryPackAt bounds values current = case values of {
    [] -> do { ensure (v2ValidBounds bounds) "invalid v2 render bounds"; Right current };
    (:) value rest -> do {
      ensure (v2ValidSummary value) "invalid v2 render summary";
      let { digits = v2DecimalLength (renderSummaryScalars value); prefixSize = digits + 1 };
      v2Room bounds (renderSummaryScalars current) (renderSummaryUtf8 current) prefixSize prefixSize;
      prefix <- v2SummaryText bounds (showInt (renderSummaryScalars value) ++ ":");
      before <- v2SummaryAppend bounds current prefix;
      next <- v2SummaryAppend bounds before value;
      v2SummaryPackAt bounds rest next
    }
  };

  -- Measurement and emission share one explicit task grammar. Measurement
  -- never calls numeric/string/declaration pretty printers. A numeric token
  -- reserves its size BEFORE emission: exact Int64 digits, Double <= 1077.
  -- Internal values during measurement carry lengths only, not hash evidence.
  data V2RenderValue = V2RenderValue Int Int Separate.FingerprintEncoding;
  data V2TextBuffer = V2TextBuffer Int ([] String) ([] String);
  data V2RenderState = V2RenderState Int Int Int V2RenderValue V2TextBuffer;
  data V2RenderTask =
    V2Text String | V2Int Int | V2Double Double | V2Escape String Int |
    V2Many ([] V2RenderTask) | V2Separated String Bool ([] V2RenderTask) |
    V2Pack ([] V2RenderTask) | V2FieldEnd V2RenderValue ([] V2RenderTask) |
    V2AppendValue V2RenderValue |
    V2Term Int XTerm | V2Type Int XType | V2Computation XComputation |
    V2Name XName | V2Variable XTyVar | V2MaybeName (Maybe XName) |
    V2Binding ((,,) XName XType XTerm) | V2Alternative XAlternative | V2Pattern XPattern |
    V2Kind Bool Kind | V2Declaration DataDecl | V2DataParameter ((,) String Kind) |
    V2Constructor ConstructorDecl | V2Field Int Field |
    V2Surface SType | V2Predicate SPredicate | V2Context ([] SPredicate) |
    V2Parameter ((,) String Kind) | V2MethodName String | V2Class SClassDecl |
    V2Instance SInstanceDecl | V2ClassMethod ((,) String SType) |
    V2InstanceMethod ((,) String SExpr) | V2Entity Modules.Entity |
    V2Interface Bool Separate.UnitInterface | V2InterfaceBinding ((,) String XType) |
    V2NormalStart XType | V2NormalType Int (Map XTyVar XTyVar) XType |
    V2NormalBoundEnd V2RenderValue Int (Map XTyVar XTyVar) XTyVar XType;
  v2EmptyValue :: V2RenderValue;
  v2EmptyValue = V2RenderValue 0 0 Separate.encodingEmpty;
  v2ValueAppend :: Bool -> RenderBounds -> V2RenderValue -> V2RenderValue -> Either String V2RenderValue;
  v2ValueAppend measuring bounds (V2RenderValue n bytes encoded) (V2RenderValue m more other) = do {
    v2Room bounds n bytes m more;
    let { total = n + m; totalBytes = bytes + more;
          joined = if measuring then Separate.encodingEmpty else v2ForceEncoding (Separate.encodingAppend encoded other) };
    seq total (seq totalBytes (seq joined (Right (V2RenderValue total totalBytes joined))))
  };
  -- At most 256 nonempty token pieces are retained before a block is joined.
  -- Text limits bound logical text; runtime allocation/copies need separate
  -- guard qualification and are not claimed to equal the UTF-8 byte count.
  v2BufferText :: String -> V2TextBuffer -> V2TextBuffer;
  v2BufferText text (V2TextBuffer count pieces blocks) =
    if stringLength text == 0 then V2TextBuffer count pieces blocks
    else if count == 255 then
      let { block = concatStrings (reverse ((:) text pieces)); blockLength = stringLength block } in
      seq blockLength (V2TextBuffer 0 [] ((:) block blocks))
    else V2TextBuffer (count + 1) ((:) text pieces) blocks;
  v2FinishBuffer :: V2TextBuffer -> String;
  v2FinishBuffer (V2TextBuffer _ pieces blocks) =
    concatStrings (reverse ((:) (concatStrings (reverse pieces)) blocks));
  v2EmitKnown :: Bool -> Bool -> RenderBounds -> Int -> Int -> String -> V2RenderState -> Either String V2RenderState;
  v2EmitKnown measuring retain bounds scalars bytes text (V2RenderState usedScalars usedBytes fresh current buffer) = do {
    v2Room bounds usedScalars usedBytes scalars bytes;
    let { nextScalars = usedScalars + scalars; nextBytes = usedBytes + bytes;
          encoded = if measuring then Separate.encodingEmpty else v2ForceEncoding (Separate.encodingText text) };
    next <- v2ValueAppend measuring bounds current (V2RenderValue scalars bytes encoded);
    let { nextBuffer = if retain then v2BufferText text buffer else buffer };
    seq nextScalars (seq nextBytes (seq nextBuffer
      (Right (V2RenderState nextScalars nextBytes fresh next nextBuffer))))
  };
  v2EmitText :: Bool -> Bool -> RenderBounds -> String -> V2RenderState -> Either String V2RenderState;
  v2EmitText measuring retain bounds text state = case state of {
    V2RenderState usedScalars usedBytes _ _ _ -> do {
      v2Room bounds usedScalars usedBytes (stringLength text) 0;
      bytes <- W.utf8Size (renderBoundUtf8 bounds - usedBytes) text;
      v2EmitKnown measuring retain bounds (stringLength text) bytes text state
    }
  };
  v2ReserveToken :: RenderBounds -> Int -> V2RenderState -> Either String ();
  v2ReserveToken bounds maximum (V2RenderState scalars bytes _ _ _) =
    v2Room bounds scalars bytes maximum maximum;
  v2EscapeSizes :: Int -> Either String ((,) Int Int);
  v2EscapeSizes code = do {
    ensure (W.scalar code) "binary symbol contains a non-scalar code point";
    if code == 34 || code == 92 || code == 10 || code == 13 || code == 9
    then Right ((,) 2 2)
    else if code < 32 || code == 127 then
      let { count = v2DecimalLength code + 3 } in Right ((,) count count)
    else Right ((,) 1 (W.scalarBytes code))
  };
  v2Par :: Bool -> [] V2RenderTask -> [] V2RenderTask;
  v2Par condition tasks = if condition
    then [V2Text "(", V2Many tasks, V2Text ")"] else tasks;
  v2Line :: V2RenderTask -> V2RenderTask;
  v2Line task = V2Many [task, V2Text "\n"];

  v2Run :: Bool -> Bool -> RenderBounds -> [] V2RenderTask -> V2RenderState -> Either String V2RenderState;
  v2Run measuring retain bounds tasks state = case tasks of {
    [] -> Right state;
    (:) task rest -> case task of {
      V2Text text -> do { next <- v2EmitText measuring retain bounds text state; v2Run measuring retain bounds rest next };
      V2Int integer -> do {
        let { size = v2IntLength integer };
        v2ReserveToken bounds size state;
        next <- if measuring then v2EmitKnown True False bounds size size "" state
          else v2EmitText False retain bounds (showInt integer) state;
        v2Run measuring retain bounds rest next
      };
      V2Double number -> do {
        v2ReserveToken bounds 1077 state;
        next <- if measuring then v2EmitKnown True False bounds 1077 1077 "" state
          else v2EmitText False retain bounds (Pretty.prettyDouble number) state;
        v2Run measuring retain bounds rest next
      };
      V2Escape text index -> if index == stringLength text
        then v2Run measuring retain bounds rest state else do {
          sizes <- v2EscapeSizes (stringCodeAt text index);
          case sizes of { (,) scalars bytes -> case state of {
            V2RenderState usedScalars usedBytes _ _ _ -> do {
              v2Room bounds usedScalars usedBytes scalars bytes;
              next <- v2EmitKnown measuring retain bounds scalars bytes
                (if measuring then "" else Pretty.escapeScalar (stringCodeAt text index)) state;
              v2Run measuring retain bounds ((:) (V2Escape text (index + 1)) rest) next
            }
          }}
        };
      V2Many values -> case values of {
        [] -> v2Run measuring retain bounds rest state;
        (:) first more -> v2Run measuring retain bounds ((:) first ((:) (V2Many more) rest)) state
      };
      V2Separated separator first values -> case values of {
        [] -> v2Run measuring retain bounds rest state;
        (:) value more -> v2Run measuring retain bounds
          ((:) (V2Many (if first then [value] else [V2Text separator, value]))
            ((:) (V2Separated separator False more) rest)) state
      };
      V2Pack values -> do {
        ensure (not retain) "v2 framed text cannot use declaration scratch";
        case values of {
          [] -> v2Run measuring retain bounds rest state;
          (:) first more -> case state of {
            V2RenderState scalars bytes fresh current buffer ->
              v2Run measuring retain bounds ((:) first ((:) (V2FieldEnd current more) rest))
                (V2RenderState scalars bytes fresh v2EmptyValue buffer)
          }
        }
      };
      V2FieldEnd previous more -> case state of {
        V2RenderState scalars bytes fresh field buffer -> case field of {
          V2RenderValue count _ _ -> do {
            let { size = v2DecimalLength count + 1;
                  reset = V2RenderState scalars bytes fresh previous buffer };
            v2Room bounds scalars bytes size size;
            prefixed <- v2EmitKnown measuring False bounds size size
              (if measuring then "" else showInt count ++ ":") reset;
            v2Run measuring retain bounds ((:) (V2AppendValue field) ((:) (V2Pack more) rest)) prefixed
          }
        }
      };
      V2AppendValue value -> case state of {
        V2RenderState scalars bytes fresh previous buffer -> do {
          joined <- v2ValueAppend measuring bounds previous value;
          v2Run measuring retain bounds rest (V2RenderState scalars bytes fresh joined buffer)
        }
      };
      V2NormalStart ty -> case state of {
        V2RenderState scalars bytes _ current buffer ->
          v2Run measuring retain bounds ((:) (V2NormalType 0 M.empty ty) rest)
            (V2RenderState scalars bytes 0 current buffer)
      };
      V2NormalType precedence environment ty -> case ty of {
        XForall variable XBot body -> case state of {
          V2RenderState scalars bytes fresh current buffer -> do {
            ensure (fresh >= 0 && fresh < 2147483647) "v2 normalized type identity limit exceeded";
            let { selected = XTyVar fresh; nextEnvironment = M.insert T.compareTyVar variable selected environment };
            seq nextEnvironment (Right ());
            v2Run measuring retain bounds
              ((:) (V2Many (v2Par (precedence > 0) [V2Text "forall ", V2Variable selected,
                V2Text ". ", V2NormalType 0 nextEnvironment body])) rest)
              (V2RenderState scalars bytes (fresh + 1) current buffer)
          }
        };
        XForall variable bound body -> do {
          ensure (not retain) "v2 normalized type cannot use declaration scratch";
          case state of {
            V2RenderState scalars bytes fresh current buffer ->
              v2Run measuring retain bounds ((:) (V2NormalType 0 environment bound)
                ((:) (V2NormalBoundEnd current precedence environment variable body) rest))
                (V2RenderState scalars bytes fresh v2EmptyValue buffer)
          }
        };
        _ -> do {
          parts <- v2NormalParts precedence environment ty;
          v2Run measuring retain bounds ((:) (V2Many parts) rest) state
        }
      };
      V2NormalBoundEnd previous precedence environment variable body -> case state of {
        V2RenderState scalars bytes fresh bound buffer -> do {
          ensure (fresh >= 0 && fresh < 2147483647) "v2 normalized type identity limit exceeded";
          let { selected = XTyVar fresh; nextEnvironment = M.insert T.compareTyVar variable selected environment };
          seq nextEnvironment (Right ());
          v2Run measuring retain bounds
            ((:) (V2Many (v2Par (precedence > 0) [V2Text "forall (", V2Variable selected,
              V2Text " >= ", V2AppendValue bound, V2Text "). ", V2NormalType 0 nextEnvironment body])) rest)
            (V2RenderState scalars bytes (fresh + 1) previous buffer)
        }
      };
      _ -> do {
        parts <- v2Parts task;
        v2Run measuring retain bounds ((:) (V2Many parts) rest) state
      }
    }
  };
  v2TypeParts :: Int -> XType -> [] V2RenderTask;
  v2TypeParts p ty = case ty of {
    XVar variable -> [V2Variable variable];
    XBot -> [V2Text "bot"];
    XBotKind kind -> [V2Text "bot[", V2Kind False kind, V2Text "]"];
    XArrow a b -> v2Par (p > 1) [V2Type 2 a, V2Text " -> ", V2Type 1 b];
    XCon name arguments -> if null arguments then [V2Text name]
      else v2Par (p > 2) [V2Text name, V2Separated " " False (map (V2Type 3) arguments)];
    XApply a b -> v2Par (p > 2) [V2Type 2 a, V2Text " ", V2Type 3 b];
    XForall variable XBot body -> v2Par (p > 0)
      [V2Text "forall ", V2Variable variable, V2Text ". ", V2Type 0 body];
    XForall variable bound body -> v2Par (p > 0)
      [V2Text "forall (", V2Variable variable, V2Text " >= ", V2Type 0 bound, V2Text "). ", V2Type 0 body]
  };
  v2NormalParts :: Int -> Map XTyVar XTyVar -> XType -> Either String ([] V2RenderTask);
  v2NormalParts p environment ty = case ty of {
    XVar variable -> Right [V2Variable (M.findWithDefault T.compareTyVar variable variable environment)];
    XBot -> Right [V2Text "bot"];
    XBotKind kind -> Right [V2Text "bot[", V2Kind False kind, V2Text "]"];
    XArrow a b -> Right (v2Par (p > 1) [V2NormalType 2 environment a, V2Text " -> ", V2NormalType 1 environment b]);
    XCon name arguments -> Right (if null arguments then [V2Text name]
      else v2Par (p > 2) [V2Text name, V2Separated " " False (map (V2NormalType 3 environment) arguments)]);
    XApply a b -> Right (v2Par (p > 2) [V2NormalType 2 environment a, V2Text " ", V2NormalType 3 environment b]);
    XForall _ _ _ -> Left "v2 normalized forall task invariant failure"
  };
  v2TermParts :: Int -> XTerm -> [] V2RenderTask;
  v2TermParts p term = case term of {
    XVarTerm name -> [V2Name name];
    XAbs name ty body -> v2Par (p > 0)
      [V2Text "\\(", V2Name name, V2Text " : ", V2Type 0 ty, V2Text ") -> ", V2Term 0 body];
    XApp a b -> v2Par (p > 1) [V2Term 1 a, V2Text " ", V2Term 2 b];
    XTypeAbs variable bound body -> v2Par (p > 0)
      [V2Text "/\\(", V2Variable variable, V2Text " >= ", V2Type 0 bound, V2Text ") -> ", V2Term 0 body];
    XTypeApp body computation -> [V2Term 2 body, V2Text "[", V2Computation computation, V2Text "]"];
    XLet name rhs body -> v2Par (p > 0)
      [V2Text "let ", V2Name name, V2Text " = ", V2Term 0 rhs, V2Text " in ", V2Term 0 body];
    XLetRec bindings body -> v2Par (p > 0)
      [V2Text "letrec { ", V2Separated "; " True (map V2Binding bindings), V2Text " } in ", V2Term 0 body];
    XIntTerm integer -> [V2Int integer];
    XDoubleTerm number -> [V2Double number];
    XBoolTerm boolean -> [V2Text (if boolean then "true" else "false")];
    XStringTerm text -> [V2Text "\"", V2Escape text 0, V2Text "\""];
    XPrimitive primitive arguments -> [V2Text "primitive ", V2Text (P.primitiveName primitive),
      V2Text "(", V2Separated ", " True (map (V2Type 0) arguments), V2Text ")"];
    XConstructor name arguments -> [V2Text "construct ", V2Text name, V2Text "(",
      V2Separated ", " True (map (V2Type 0) arguments), V2Text ")"];
    XCase body ty alternatives -> v2Par (p > 0)
      [V2Text "case ", V2Term 0 body, V2Text " return ", V2Type 0 ty, V2Text " of { ",
        V2Separated "; " True (map V2Alternative alternatives), V2Text " }"];
    XWithData declarations body ->
      [V2Many (map (\declaration -> v2Line (V2Declaration declaration)) declarations), V2Term 0 body]
  };
  v2ComputationParts :: XComputation -> [] V2RenderTask;
  v2ComputationParts computation = case computation of {
    XRefl -> [V2Text "id"];
    XBottom ty -> [V2Text "bot(", V2Type 0 ty, V2Text ")"];
    XHyp variable -> [V2Text "hyp(", V2Variable variable, V2Text ")"];
    XInner body -> [V2Text "inner(", V2Computation body, V2Text ")"];
    XOuter variable body -> [V2Text "outer(", V2Variable variable, V2Text ", ", V2Computation body, V2Text ")"];
    XElim -> [V2Text "elim"];
    XIntro variable -> [V2Text "intro(", V2Variable variable, V2Text ")"];
    XIntroKind variable kind -> [V2Text "intro(", V2Variable variable, V2Text " : ", V2Kind False kind, V2Text ")"];
    XThen a b -> [V2Computation a, V2Text "; ", V2Computation b]
  };
  v2FieldParts :: Int -> Field -> [] V2RenderTask;
  v2FieldParts p field = case field of {
    Parameter name -> [V2Text name];
    Applied name arguments -> if null arguments then [V2Text name]
      else v2Par (p > 1) [V2Text name, V2Separated " " False (map (V2Field 2) arguments)];
    Function a b -> v2Par (p > 0) [V2Field 1 a, V2Text " -> ", V2Field 0 b];
    Application a b -> v2Par (p > 1) [V2Field 1 a, V2Text " ", V2Field 2 b];
    Quantified name kind body -> v2Par (p > 0)
      [V2Text "forall ", V2DataParameter ((,) name kind), V2Text ". ", V2Field 0 body]
  };
  v2SurfaceParts :: SType -> [] V2RenderTask;
  v2SurfaceParts ty = case ty of {
    STVar name -> [V2Text name];
    SBottom -> [V2Text "bot"];
    SBottomKind kind -> [V2Text "bot[", V2Kind False kind, V2Text "]"];
    SArrow a b -> [V2Text "(", V2Surface a, V2Text " -> ", V2Surface b, V2Text ")"];
    STypeApp a b -> [V2Text "(", V2Surface a, V2Text " ", V2Surface b, V2Text ")"];
    SCon name arguments -> [V2Text "(", V2Text name,
      V2Separated " " False (map V2Surface arguments), V2Text ")"];
    SForall flag name bound body -> [V2Text "(forall (", V2Text name,
      V2Text (case flag of { Flexible -> " >= "; Rigid -> " > " }),
      V2Surface bound, V2Text "). ", V2Surface body, V2Text ")"];
    SQualified predicates body -> [V2Text "(", V2Context predicates, V2Surface body, V2Text ")"]
  };
  v2EntityParts :: Modules.Entity -> [] V2RenderTask;
  v2EntityParts (Modules.Entity owner name role) =
    let { fields = case role of {
      Modules.Value -> [V2Text "value", V2Text ""];
      Modules.Datatype -> [V2Text "data", V2Text ""];
      Modules.Class -> [V2Text "class", V2Text ""];
      Modules.ManagedConstraint -> [V2Text "managed-constraint", V2Text ""];
      Modules.Constructor parent -> [V2Text "constructor", V2Text parent];
      Modules.Method parent -> [V2Text "method", V2Text parent];
      Modules.BuiltinType -> [V2Text "builtin", V2Text ""];
      Modules.Primitive primitive -> [V2Text "primitive", V2Text (P.primitiveName primitive)];
      Modules.Boolean boolean -> [V2Text "bool", V2Text (if boolean then "true" else "false")]
    }} in [V2Pack ((:) (V2Text owner) ((:) (V2Text name) fields))];
  v2InterfaceParts :: Bool -> Separate.UnitInterface -> [] V2RenderTask;
  v2InterfaceParts includeFingerprint iface = let { fields = [
    V2Text "MLFI-4", V2Text (Separate.unitName iface),
    V2Pack (map (\((,) name value) -> V2Pack [V2Text name, V2Text value]) (Separate.unitDependencies iface)),
    V2Pack (map V2Entity (Separate.unitExports iface)),
    V2Many [V2Many (map (\value -> v2Line (V2Declaration value)) (Separate.unitData iface)),
      V2Many (map (\value -> v2Line (V2Class value)) (Separate.unitClasses iface)),
      V2Many (map (\((,) _ value) -> v2Line (V2Instance value)) (Separate.unitInstances iface))],
    V2Pack (map (\((,) name _) -> V2Text name) (Separate.unitInstances iface)),
    V2Pack (map V2InterfaceBinding (Separate.unitBindings iface)),
    V2Text (Separate.unitObjectFingerprint iface)] } in
    [V2Pack (if includeFingerprint then fields else take 7 fields)];
  v2Parts :: V2RenderTask -> Either String ([] V2RenderTask);
  v2Parts task = case task of {
    V2Term precedence term -> Right (v2TermParts precedence term);
    V2Type precedence ty -> Right (v2TypeParts precedence ty);
    V2Computation computation -> Right (v2ComputationParts computation);
    V2Name (XName identity hint) -> Right [V2Text hint, V2Text "_", V2Int identity];
    V2Variable (XTyVar identity) -> Right (if identity < 0
      then [V2Text "z", if identity == (-9223372036854775808)
        then V2Text "9223372036854775808" else V2Int (0 - identity)]
      else [V2Text "a", V2Int identity]);
    V2MaybeName name -> Right (case name of { Nothing -> [V2Text "_"]; Just value -> [V2Name value] });
    V2Binding ((,,) name ty body) -> Right [V2Name name, V2Text " : ", V2Type 0 ty, V2Text " = ", V2Term 0 body];
    V2Alternative (XAlternative pattern body) -> Right [V2Pattern pattern, V2Text " -> ", V2Term 0 body];
    V2Pattern pattern -> Right (case pattern of {
      XDefaultPattern name -> [V2MaybeName name];
      XConstructorPattern name fields -> [V2Text name, V2Separated " " False (map V2MaybeName fields)]
    });
    V2Kind left kind -> Right (case kind of {
      Star -> [V2Text "*"];
      KArrow a b -> v2Par left [V2Kind True a, V2Text " -> ", V2Kind False b]
    });
    V2Declaration declaration -> Right [V2Text "data ", V2Text (D.datatypeName declaration),
      V2Separated " " False (map V2DataParameter (D.datatypeBinders declaration)), V2Text " = ",
      V2Separated " | " True (map V2Constructor (D.datatypeConstructors declaration)), V2Text ";"];
    V2DataParameter ((,) name kind) -> Right (case kind of {
      Star -> [V2Text name];
      KArrow _ _ -> [V2Text "(", V2Text name, V2Text " : ", V2Kind False kind, V2Text ")"]
    });
    V2Constructor (ConstructorDecl name fields) -> Right [V2Text name, V2Separated " " False (map (V2Field 2) fields)];
    V2Field precedence field -> Right (v2FieldParts precedence field);
    V2Surface ty -> Right (v2SurfaceParts ty);
    V2Predicate (SPredicate name arguments) -> Right [V2Text name, V2Separated " " False (map V2Surface arguments)];
    V2Context predicates -> Right (if null predicates then []
      else [V2Text "(", V2Separated ", " True (map V2Predicate predicates), V2Text ") => "]);
    V2Parameter ((,) name kind) -> Right [V2Text "(", V2Text name, V2Text " : ", V2Kind False kind, V2Text ")"];
    V2MethodName name -> Right (if Lexer.sharedIdentifier name then [V2Text name]
      else [V2Text "(", V2Text name, V2Text ")"]);
    V2Class (SClassDecl name parameters supers methods) -> Right [V2Text "class ", V2Context supers,
      V2Text name, V2Text " ", V2Separated " " True (map V2Parameter parameters), V2Text " where { ",
      V2Separated "; " True (map V2ClassMethod methods), V2Text " };"];
    V2Instance (SInstanceDecl parameters predicates name arguments methods) -> Right [V2Text "instance ",
      V2Many (if null parameters then [] else [V2Text "forall ",
        V2Separated " " True (map V2Parameter parameters), V2Text ". "]),
      V2Context predicates, V2Text name, V2Text " ", V2Separated " " True (map V2Surface arguments),
      V2Text " where { ", V2Separated "; " True (map V2InstanceMethod methods), V2Text " };"];
    V2ClassMethod ((,) name ty) -> Right [V2MethodName name, V2Text " : ", V2Surface ty];
    V2InstanceMethod ((,) name _) -> Right [V2MethodName name, V2Text " = panic \"interface method\""];
    V2Entity entity -> Right (v2EntityParts entity);
    V2Interface includeFingerprint iface -> Right (v2InterfaceParts includeFingerprint iface);
    V2InterfaceBinding ((,) name ty) -> Right [V2Pack [V2Text name, V2NormalStart ty]];
    _ -> Left "v2 render task invariant failure"
  };

  v2Evaluate :: Bool -> Bool -> RenderBounds -> V2RenderTask -> Either String ((,) V2RenderValue V2TextBuffer);
  v2Evaluate measuring retain bounds task = do {
    ensure (v2ValidBounds bounds && not (measuring && retain)) "invalid v2 render bounds";
    result <- v2Run measuring retain bounds [task]
      (V2RenderState 0 0 0 v2EmptyValue (V2TextBuffer 0 [] []));
    case result of {
      V2RenderState scalars bytes _ value buffer -> case value of {
        V2RenderValue count size _ -> do {
          ensure (scalars == count && bytes == size) "v2 render accounting invariant failure";
          Right ((,) value buffer)
        }
      }
    }
  };
  v2Measure :: Int -> Int -> V2RenderTask -> Either String RenderBounds;
  v2Measure scalars bytes task = do {
    result <- v2Evaluate True False (RenderBounds scalars bytes) task;
    case result of { (,) (V2RenderValue count size _) _ -> Right (RenderBounds count size) }
  };
  v2Render :: RenderBounds -> V2RenderTask -> Either String RenderSummary;
  v2Render bounds task = do {
    result <- v2Evaluate False False bounds task;
    case result of {
      (,) (V2RenderValue scalars bytes encoded) _ -> do {
        let { summary = RenderSummary scalars bytes encoded };
        ensure (v2ValidSummary summary) "v2 render summary invariant failure";
        Right summary
      }
    }
  };
  v2MeasureTerm :: Int -> Int -> XTerm -> Either String RenderBounds;
  v2MeasureTerm scalars bytes term = v2Measure scalars bytes (V2Term 0 term);
  v2MeasureUnitInterface :: Int -> Int -> Separate.UnitInterface -> Either String RenderBounds;
  v2MeasureUnitInterface scalars bytes iface = v2Measure scalars bytes (V2Interface True iface);
  v2MeasureUnitInterfacePrefix :: Int -> Int -> Separate.UnitInterface -> Either String RenderBounds;
  v2MeasureUnitInterfacePrefix scalars bytes iface = v2Measure scalars bytes (V2Interface False iface);
  v2MeasureDeclaration :: Int -> Int -> DataDecl -> Either String RenderBounds;
  v2MeasureDeclaration scalars bytes declaration = v2Measure scalars bytes (V2Declaration declaration);
  v2RenderTerm :: RenderBounds -> XTerm -> Either String RenderSummary;
  v2RenderTerm bounds term = v2Render bounds (V2Term 0 term);
  v2RenderUnitInterface :: RenderBounds -> Separate.UnitInterface -> Either String RenderSummary;
  v2RenderUnitInterface bounds iface = v2Render bounds (V2Interface True iface);
  v2RenderUnitInterfacePrefix :: RenderBounds -> Separate.UnitInterface -> Either String RenderSummary;
  v2RenderUnitInterfacePrefix bounds iface = v2Render bounds (V2Interface False iface);
  v2RenderDeclarationText :: RenderBounds -> DataDecl -> Either String ((,) String RenderSummary);
  v2RenderDeclarationText bounds declaration = do {
    ensure (renderBoundScalars bounds <= 16777216 && renderBoundUtf8 bounds <= 16777216)
      "v2 declaration render scratch limit exceeded";
    result <- v2Evaluate False True bounds (V2Declaration declaration);
    case result of {
      (,) (V2RenderValue scalars bytes encoded) buffer -> do {
        let { summary = RenderSummary scalars bytes encoded };
        ensure (v2ValidSummary summary) "v2 render summary invariant failure";
        let { text = v2FinishBuffer buffer };
        ensure (stringLength text == scalars) "v2 declaration text length invariant failure";
        Right ((,) text summary)
      }
    }
  };
  v2CheckUnit :: RenderBounds -> Separate.UnitObject -> Either String ((,) Separate.UnitObject RenderSummary);
  v2CheckUnit bounds object = do {
    let { iface = Separate.objectInterface object; term = Separate.objectTerm object };
    -- Complete bounded rendering before semantic checks that may themselves
    -- report formatted syntax. This summary belongs to THIS actual term.
    summary <- v2RenderTerm bounds term;
    validateUnitInterface iface;
    admit [AdmitTerm term];
    ensure (eqString (Separate.encodingFingerprint (renderSummaryEncoding summary))
      (Separate.unitObjectFingerprint iface)) "module object checksum mismatch";
    checked <- Checked.check term;
    Right ((,) (Separate.CheckedUnitObject iface checked) summary)
  };
  writeRawAtomic :: String -> ByteArray -> IO (Either String ());
  writeRawAtomic path bytes =
    if hasNul path 0 then ioReturn (Left "file path contains NUL") else do {
      let { destination = if Host.absolutePath path then path else "./" ++ path };
      isDirectory <- directoryExists destination;
      if isDirectory then ioReturn (Left "artifact destination is a directory") else do {
        size <- lengthByteArray bytes;
        if size > maxBytes then ioReturn (Left "binary file byte limit exceeded") else do {
          written <- writeRaw (destination ++ ".new") bytes;
          case written of {
            Left error -> ioReturn (Left error);
            Right _ -> do {
              arguments <- Host.hostArguments ["/bin/mv", "-f", destination ++ ".new", destination];
              code <- runProcess "" (concatMapString (\field -> field ++ stringFromCode 0)
                (append ["1800", "", "", ""] arguments));
              ioReturn (if code == 0 then Right () else Left "cannot publish binary artifact")
            }
          }
        }
      }
    };

  -- Base64 is only the checked JSON release transport. Formal artifacts stay
  -- binary. Build bounded blocks, never a whole-file boxed list of bytes.
  base64Alphabet :: String;
  base64Alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  base64Char :: Int -> String;
  base64Char index = stringSlice base64Alphabet index 1;
  base64Block :: ByteArray -> Int -> Int -> Int -> [] String -> IO ((,) Int String);
  base64Block bytes size offset remaining pieces =
    if offset >= size || remaining == 0 then ioReturn ((,) offset (concatStrings (reverse pieces)))
    else do {
      a <- readByteArray bytes offset;
      b <- if offset + 1 < size then readByteArray bytes (offset + 1) else ioReturn 0;
      c <- if offset + 2 < size then readByteArray bytes (offset + 2) else ioReturn 0;
      let { text = base64Char (quotInt a 4)
        ++ base64Char (remInt a 4 * 16 + quotInt b 16)
        ++ (if offset + 1 < size then base64Char (remInt b 16 * 4 + quotInt c 64) else "=")
        ++ (if offset + 2 < size then base64Char (remInt c 64) else "=") };
      base64Block bytes size (offset + 3) (remaining - 1) ((:) text pieces)
    };
  base64Blocks :: ByteArray -> Int -> Int -> [] String -> IO String;
  base64Blocks bytes size offset blocks =
    if offset >= size then ioReturn (concatStrings (reverse blocks)) else do {
      next <- base64Block bytes size offset 1024 [];
      base64Blocks bytes size (fst next) ((:) (snd next) blocks)
    };
  encodeBase64 :: ByteArray -> IO (Either String String);
  encodeBase64 bytes = do {
    size <- lengthByteArray bytes;
    if size > maxBytes then ioReturn (Left "release byte payload exceeds limit") else do {
      text <- base64Blocks bytes size 0 [];
      ioReturn (Right text)
    }
  };
  base64Digit :: Int -> Int;
  base64Digit code =
    if code >= 65 && code <= 90 then code - 65
    else if code >= 97 && code <= 122 then code - 97 + 26
    else if code >= 48 && code <= 57 then code - 48 + 52
    else if code == 43 then 62 else if code == 47 then 63 else (-1);
  decodeBase64Groups :: String -> Int -> Int -> ByteArray -> Int -> IO (Either String ByteArray);
  decodeBase64Groups text total offset bytes output =
    if offset == total then ioReturn (Right bytes) else do {
      let { a = base64Digit (stringCodeAt text offset);
            b = base64Digit (stringCodeAt text (offset + 1));
            cc = stringCodeAt text (offset + 2);
            dc = stringCodeAt text (offset + 3);
            pad2 = cc == 61;
            pad1 = dc == 61;
            c = if pad2 then 0 else base64Digit cc;
            d = if pad1 then 0 else base64Digit dc;
            last = offset + 4 == total;
            valid = a >= 0 && b >= 0 && c >= 0 && d >= 0
              && (not pad2 || (pad1 && last && remInt b 16 == 0))
              && (not pad1 || (last && (pad2 || remInt c 4 == 0))) };
      if not valid then ioReturn (Left "noncanonical release base64") else do {
        writeByteArray bytes output (a * 4 + quotInt b 16);
        if pad2 then ioReturn () else writeByteArray bytes (output + 1) (remInt b 16 * 16 + quotInt c 4);
        if pad1 then ioReturn () else writeByteArray bytes (output + 2) (remInt c 4 * 64 + d);
        decodeBase64Groups text total (offset + 4) bytes
          (output + (if pad2 then 1 else if pad1 then 2 else 3))
      }
    };
  decodeBase64 :: String -> IO (Either String ByteArray);
  decodeBase64 text = let { total = stringLength text;
      maximum = (quotInt maxBytes 3 + 1) * 4 } in
    if total > maximum || remInt total 4 /= 0
    then ioReturn (Left "invalid release base64 length")
    else let { padding = if total == 0 then 0
          else if stringCodeAt text (total - 2) == 61 then 2
          else if stringCodeAt text (total - 1) == 61 then 1 else 0;
        count = quotInt total 4 * 3 - padding } in
      if count < 0 || count > maxBytes then ioReturn (Left "release byte payload exceeds limit")
      else do {
        bytes <- newByteArray count 0;
        decodeBase64Groups text total 0 bytes 0
      };
  readBase64 :: String -> IO (Either String String);
  readBase64 path = do {
    raw <- readRaw path;
    case raw of { Left error -> ioReturn (Left error); Right bytes -> encodeBase64 bytes }
  };
  writeBase64 :: String -> String -> IO (Either String ());
  writeBase64 path text = do {
    decoded <- decodeBase64 text;
    case decoded of { Left error -> ioReturn (Left error); Right bytes -> writeRaw path bytes }
  }
}
