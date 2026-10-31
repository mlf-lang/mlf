-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.BuiltinPreludeLiteral where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Unicode as Unicode;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.X.Pretty as Pretty;

  -- This is a structural source-literal printer, not a source translator or
  -- checker. It preserves constructor tags, identities, list order and map
  -- shape. The generated consumer uses the ordinary shared source syntax.
  application :: String -> [] String -> String;
  application constructor arguments = case arguments of {
    [] -> constructor;
    _ -> "(" ++ L.intercalate " " ((:) constructor arguments) ++ ")"
  };
  list :: forall a. (a -> String) -> [] a -> String;
  list render values = "[" ++ L.intercalate "," (L.map render values) ++ "]";
  pair :: forall a b. (a -> String) -> (b -> String) -> (,) a b -> String;
  pair first second ((,) a b) = "(" ++ first a ++ "," ++ second b ++ ")";
  triple :: forall a b c. (a -> String) -> (b -> String) -> (c -> String) -> (,,) a b c -> String;
  triple first second third ((,,) a b c) =
    "(" ++ first a ++ "," ++ second b ++ "," ++ third c ++ ")";
  maybe :: forall a. (a -> String) -> Maybe a -> String;
  maybe render value = case value of {
    Nothing -> "Nothing";
    Just body -> application "Just" [render body]
  };
  integer :: Int -> String;
  integer value = if value < 0 then "(" ++ showInt value ++ ")" else showInt value;
  boolean :: Bool -> String;
  boolean value = if value then "True" else "False";
  unit :: () -> String;
  unit value = case value of { () -> "()" };
  -- Decimal rendering is unnecessary here: the primitive reconstructs the
  -- exact IEEE bits, including negative zero and non-finite payloads.
  double :: Double -> String;
  double value = application "doubleFromBits" [integer (doubleToBits value)];
  string :: String -> String;
  string value = "\"" ++ concatStringList (stringParts value 0 (stringLength value)) ++ "\"";
  stringParts :: String -> Int -> Int -> [] String;
  stringParts value offset size =
    if offset >= size then [] else let {
      scalar = stringCodeAt value offset;
      quoted = if scalar < 128 || Unicode.isPrint scalar then Pretty.escapeScalar scalar
        else "\\" ++ showInt scalar ++ "\\&"
    } in (:) quoted (stringParts value (offset + 1) size);
  map :: forall a b. (a -> String) -> (b -> String) -> Map a b -> String;
  map key value entries = case entries of {
    MapEmpty -> "MapEmpty";
    MapNode size k v left right -> application "MapNode"
      [integer size, key k, value v, map key value left, map key value right]
  };
  mapString :: forall a. (a -> String) -> Map String a -> String;
  mapString = map string;
  set :: forall a. (a -> String) -> Set a -> String;
  set value entries = case entries of {
    Set tree -> application "Set" [map value unit tree]
  };
  kind :: Kind -> String;
  kind value = case value of {
    Star -> "Star";
    KArrow domain result -> application "KArrow" [kind domain, kind result]
  };
  flag :: Flag -> String;
  flag value = case value of { Flexible -> "Flexible"; Rigid -> "Rigid" };
  field :: Field -> String;
  field value = case value of {
    Parameter n -> application "Parameter" [string n];
    Function a b -> application "Function" [field a, field b];
    Applied n arguments -> application "Applied" [string n, list field arguments];
    Application a b -> application "Application" [field a, field b];
    Quantified n k body -> application "Quantified" [string n, kind k, field body]
  };
  constructor :: ConstructorDecl -> String;
  constructor value = case value of {
    ConstructorDecl n fields -> application "ConstructorDecl" [string n, list field fields]
  };
  declaration :: DataDecl -> String;
  declaration value = case value of {
    DataDecl n parameters constructors -> application "DataDecl"
      [string n, list string parameters, list constructor constructors];
    DataDeclK n parameters constructors -> application "DataDeclK"
      [string n, list (pair string kind) parameters, list constructor constructors]
  };
  primitive :: Primitive -> String;
  primitive value = case value of {
    PIOReturn -> "PIOReturn";
    PIOBind -> "PIOBind";
    PPutStr -> "PPutStr";
    PPutStrLn -> "PPutStrLn";
    PGetLine -> "PGetLine";
    PPrintInt -> "PPrintInt";
    PConcatString -> "PConcatString";
    PShowInt -> "PShowInt";
    PAddInt -> "PAddInt";
    PSubInt -> "PSubInt";
    PEqInt -> "PEqInt";
    PLtInt -> "PLtInt";
    PEqString -> "PEqString";
    PIfThenElse -> "PIfThenElse";
    PMulInt -> "PMulInt";
    PQuotInt -> "PQuotInt";
    PRemInt -> "PRemInt";
    PReadInt -> "PReadInt";
    PAddDouble -> "PAddDouble";
    PSubDouble -> "PSubDouble";
    PMulDouble -> "PMulDouble";
    PDivDouble -> "PDivDouble";
    PSqrtDouble -> "PSqrtDouble";
    PEqDouble -> "PEqDouble";
    PLtDouble -> "PLtDouble";
    PIntToDouble -> "PIntToDouble";
    PFormatDouble -> "PFormatDouble";
    PNewIntArray -> "PNewIntArray";
    PReadIntArray -> "PReadIntArray";
    PWriteIntArray -> "PWriteIntArray";
    PLengthIntArray -> "PLengthIntArray";
    PNewDoubleArray -> "PNewDoubleArray";
    PReadDoubleArray -> "PReadDoubleArray";
    PWriteDoubleArray -> "PWriteDoubleArray";
    PLengthDoubleArray -> "PLengthDoubleArray";
    PNewByteArray -> "PNewByteArray";
    PReadByteArray -> "PReadByteArray";
    PWriteByteArray -> "PWriteByteArray";
    PLengthByteArray -> "PLengthByteArray";
    PByteArrayFromString -> "PByteArrayFromString";
    PPutBytes -> "PPutBytes";
    PGetByteLine -> "PGetByteLine";
    PNewIntTable -> "PNewIntTable";
    PReadIntTable -> "PReadIntTable";
    PWriteIntTable -> "PWriteIntTable";
    PAndInt -> "PAndInt";
    PStringLength -> "PStringLength";
    PStringCodeAt -> "PStringCodeAt";
    PStringSlice -> "PStringSlice";
    PStringFromCode -> "PStringFromCode";
    PCompareString -> "PCompareString";
    PReadDouble -> "PReadDouble";
    PDoubleToBits -> "PDoubleToBits";
    PDoubleFromBits -> "PDoubleFromBits";
    PSeq -> "PSeq";
    PPanic -> "PPanic";
    PReadFile -> "PReadFile";
    PWriteFile -> "PWriteFile";
    PFileExists -> "PFileExists";
    PCanonicalPath -> "PCanonicalPath";
    PGetArgCount -> "PGetArgCount";
    PGetArg -> "PGetArg";
    PPutErr -> "PPutErr";
    PExitWith -> "PExitWith";
    PGetExecutablePath -> "PGetExecutablePath";
    PGetContents -> "PGetContents";
    PSTReturn -> "PSTReturn";
    PSTBind -> "PSTBind";
    PRunST -> "PRunST";
    PNewSTArray -> "PNewSTArray";
    PReadSTArray -> "PReadSTArray";
    PWriteSTArray -> "PWriteSTArray";
    PLengthSTArray -> "PLengthSTArray";
    PGetEnv -> "PGetEnv";
    PSetEnv -> "PSetEnv";
    PUnsetEnv -> "PUnsetEnv";
    PRunProcess -> "PRunProcess";
    PListDirectory -> "PListDirectory";
    PDirectoryExists -> "PDirectoryExists";
    PFileDigest -> "PFileDigest";
    PAcquireFileLock -> "PAcquireFileLock";
    PReleaseFileLock -> "PReleaseFileLock";
    PProcessSupervisor -> "PProcessSupervisor";
    PAsyncScopeNew -> "PAsyncScopeNew";
    PAsyncScopeClose -> "PAsyncScopeClose";
    PAsyncNewCompletion -> "PAsyncNewCompletion";
    PAsyncResolveCompletion -> "PAsyncResolveCompletion";
    PAsyncReadCompletion -> "PAsyncReadCompletion";
    PAsyncSubscribeCompletion -> "PAsyncSubscribeCompletion";
    PAsyncSubscriptionStatus -> "PAsyncSubscriptionStatus";
    PAsyncCancelSubscription -> "PAsyncCancelSubscription";
    PAsyncStep -> "PAsyncStep";
    PAsyncEnqueue -> "PAsyncEnqueue";
    PAsyncDelay -> "PAsyncDelay";
    PAsyncWait -> "PAsyncWait";
    PTextToChars -> "PTextToChars";
    PTextFromChars -> "PTextFromChars";
    PCharCode -> "PCharCode";
    PCharFromCode -> "PCharFromCode";
    PUserError -> "PUserError";
    PIOError -> "PIOError";
    PCatchIOError -> "PCatchIOError";
    PIOErrorString -> "PIOErrorString";
    PEmptyCallStack -> "PEmptyCallStack";
    PPushCallStack -> "PPushCallStack";
    PPrettyCallStack -> "PPrettyCallStack";
    PIOErrorWithStack -> "PIOErrorWithStack";
    PConcatStringList -> "PConcatStringList";
    POrInt -> "POrInt";
    PXorInt -> "PXorInt";
    PShiftLInt -> "PShiftLInt";
    PShiftRInt -> "PShiftRInt";
    PUnsignedShiftRInt -> "PUnsignedShiftRInt";
    PCountLeadingZerosInt -> "PCountLeadingZerosInt";
    PCountTrailingZerosInt -> "PCountTrailingZerosInt";
    PPopCountInt -> "PPopCountInt";
    PIntToInteger -> "PIntToInteger";
    PIntegerToInt -> "PIntegerToInt";
    PAddInteger -> "PAddInteger";
    PSubInteger -> "PSubInteger";
    PMulInteger -> "PMulInteger";
    PQuotInteger -> "PQuotInteger";
    PRemInteger -> "PRemInteger";
    PEqInteger -> "PEqInteger";
    PLtInteger -> "PLtInteger";
    PShowInteger -> "PShowInteger";
    PReadInteger -> "PReadInteger";
    PIntegerToDouble -> "PIntegerToDouble";
    PUnsignedLtInt -> "PUnsignedLtInt"
  };
  sourceType :: SType -> String;
  sourceType value = case value of {
    STVar n -> application "STVar" [string n];
    SBottom -> "SBottom";
    SBottomKind k -> application "SBottomKind" [kind k];
    SArrow a b -> application "SArrow" [sourceType a, sourceType b];
    SCon n arguments -> application "SCon" [string n, list sourceType arguments];
    STypeApp a b -> application "STypeApp" [sourceType a, sourceType b];
    SForall permission n bound body -> application "SForall"
      [flag permission, string n, sourceType bound, sourceType body];
    SQualified predicates body -> application "SQualified" [list predicate predicates, sourceType body]
  };
  annotation :: SAnnotation -> String;
  annotation value = case value of {
    SAnnotation variables ty -> application "SAnnotation" [list string variables, sourceType ty]
  };
  recursiveMode :: RecursiveMode -> String;
  recursiveMode value = case value of {
    InferRecursive -> "InferRecursive";
    CheckRecursive signature -> application "CheckRecursive" [annotation signature]
  };
  sourceSpan :: SourceSpan -> String;
  sourceSpan value = case value of {
    SourceSpan package file owner startLine startColumn endLine endColumn -> application "SourceSpan"
      [string package, string file, string owner, integer startLine, integer startColumn, integer endLine, integer endColumn]
  };
  sourceExpression :: SExpr -> String;
  sourceExpression value = case value of {
    SVar n -> application "SVar" [string n];
    SConstructor n -> application "SConstructor" [string n];
    SLam n signature body -> application "SLam" [string n, maybe annotation signature, sourceExpression body];
    SApp a b -> application "SApp" [sourceExpression a, sourceExpression b];
    SLet n a b -> application "SLet" [string n, sourceExpression a, sourceExpression b];
    SAnn body signature -> application "SAnn" [sourceExpression body, annotation signature];
    SSignature body signature -> application "SSignature" [sourceExpression body, annotation signature];
    SIntLit n -> application "SIntLit" [integer n];
    SDoubleLit n -> application "SDoubleLit" [double n];
    SBoolLit b -> application "SBoolLit" [boolean b];
    SStringLit text -> application "SStringLit" [string text];
    SPrimitive p -> application "SPrimitive" [primitive p];
    SCase body alternatives -> application "SCase" [sourceExpression body, list sourceAlternative alternatives];
    SDo statements body -> application "SDo" [list statement statements, sourceExpression body];
    SEquations equations -> application "SEquations" [list (pair (list sourcePattern) sourceExpression) equations];
    SLetRec definitions body -> application "SLetRec"
      [list (triple string recursiveMode sourceExpression) definitions, sourceExpression body];
    SWanted n candidates -> application "SWanted" [string n, list (pair evidenceRole string) candidates];
    SChecked ty body -> application "SChecked" [sourceType ty, sourceExpression body];
    SSourceDefinition body -> application "SSourceDefinition" [sourceExpression body];
    SCallSite n location body -> application "SCallSite" [string n, sourceSpan location, sourceExpression body];
    SSharedBind pattern action binding failure continuation -> application "SSharedBind"
      [sourcePattern pattern, sourceExpression action, sourceExpression binding, sourceExpression failure, sourceExpression continuation]
  };
  sourceString :: SourceString -> String;
  sourceString value = case value of {
    ScalarString text -> application "ScalarString" [string text];
    CharString codes -> application "CharString" [list integer codes]
  };
  sourcePattern :: SPattern -> String;
  sourcePattern value = case value of {
    SConstructorPattern n fields -> application "SConstructorPattern" [string n, list (maybe string) fields];
    SDefaultPattern n -> application "SDefaultPattern" [maybe string n];
    SNestedPattern n fields -> application "SNestedPattern" [string n, list sourcePattern fields];
    SAnnotatedPattern n signature -> application "SAnnotatedPattern" [string n, annotation signature];
    SIntPattern n -> application "SIntPattern" [integer n];
    SStringPattern text -> application "SStringPattern" [string text];
    SOverloadedStringPattern literal conversion equality -> application "SOverloadedStringPattern"
      [sourceString literal, string conversion, string equality];
    SBoolPattern b -> application "SBoolPattern" [boolean b];
    SAsPattern n body -> application "SAsPattern" [string n, sourcePattern body];
    SLazyPattern body -> application "SLazyPattern" [sourcePattern body]
  };
  sourceAlternative :: SAlternative -> String;
  sourceAlternative value = case value of {
    SAlternative pattern body -> application "SAlternative" [sourcePattern pattern, sourceExpression body]
  };
  statement :: SStatement -> String;
  statement value = case value of {
    SDoBind pattern body -> application "SDoBind" [sourcePattern pattern, sourceExpression body];
    SDoThen body -> application "SDoThen" [sourceExpression body];
    SDoLet n signature body -> application "SDoLet" [string n, maybe annotation signature, sourceExpression body];
    SDoLetRec definitions -> application "SDoLetRec" [list (triple string recursiveMode sourceExpression) definitions]
  };
  predicate :: SPredicate -> String;
  predicate value = case value of {
    SPredicate n arguments -> application "SPredicate" [string n, list sourceType arguments]
  };
  sourceClass :: SClassDecl -> String;
  sourceClass value = case value of {
    SClassDecl n parameters parents methods -> application "SClassDecl"
      [string n, list (pair string kind) parameters, list predicate parents, list (pair string sourceType) methods]
  };
  sourceInstance :: SInstanceDecl -> String;
  sourceInstance value = case value of {
    SInstanceDecl variables predicates n arguments methods -> application "SInstanceDecl"
      [list (pair string kind) variables, list predicate predicates, string n,
       list sourceType arguments, list (pair string sourceExpression) methods]
  };
  evidenceRole :: EvidenceRole -> String;
  evidenceRole value = case value of {
    GivenEvidence -> "GivenEvidence";
    SuperclassEvidence -> "SuperclassEvidence";
    InstanceEvidence -> "InstanceEvidence"
  };
  sourceSyntax :: SourceSyntax -> String;
  sourceSyntax value = case value of {
    LegacyEmlfV1 -> "LegacyEmlfV1";
    SharedHaskellV1 -> "SharedHaskellV1";
    MetadataSyntax -> "MetadataSyntax"
  };
  members :: Members -> String;
  members value = case value of {
    Abstract -> "Abstract";
    AllMembers -> "AllMembers";
    Members entries -> application "Members" [list string entries]
  };
  sourceExport :: Export -> String;
  sourceExport value = case value of {
    ExportValue n -> application "ExportValue" [string n];
    ExportType n exported -> application "ExportType" [string n, members exported];
    ExportModule n -> application "ExportModule" [string n]
  };
  selection :: Selection -> String;
  selection value = case value of {
    Everything -> "Everything";
    Only entries -> application "Only" [list sourceExport entries];
    Hiding entries -> application "Hiding" [list sourceExport entries]
  };
  sourceImport :: Import -> String;
  sourceImport value = case value of {
    Import n qualified alias selected -> application "Import"
      [string n, boolean qualified, maybe string alias, selection selected]
  };
  sourceModule :: SourceModule -> String;
  sourceModule value = case value of {
    SourceModule file n exports imports declarations classes instances values body syntax ->
      application "SourceModule"
        [string file, maybe string n, maybe (list sourceExport) exports, list sourceImport imports,
         list declaration declarations, list sourceClass classes, list sourceInstance instances,
         list (triple string (maybe annotation) sourceExpression) values,
         maybe sourceExpression body, sourceSyntax syntax]
  };
  variable :: XTyVar -> String;
  variable value = case value of { XTyVar identity -> application "XTyVar" [integer identity] };
  name :: XName -> String;
  name value = case value of { XName identity hint -> application "XName" [integer identity, string hint] };
  typeLiteral :: XType -> String;
  typeLiteral value = case value of {
    XVar a -> application "XVar" [variable a];
    XBot -> "XBot";
    XBotKind k -> application "XBotKind" [kind k];
    XArrow a b -> application "XArrow" [typeLiteral a, typeLiteral b];
    XCon n arguments -> application "XCon" [string n, list typeLiteral arguments];
    XApply a b -> application "XApply" [typeLiteral a, typeLiteral b];
    XForall a bound body -> application "XForall" [variable a, typeLiteral bound, typeLiteral body]
  };
  computation :: XComputation -> String;
  computation value = case value of {
    XRefl -> "XRefl";
    XBottom ty -> application "XBottom" [typeLiteral ty];
    XHyp a -> application "XHyp" [variable a];
    XInner body -> application "XInner" [computation body];
    XOuter a body -> application "XOuter" [variable a, computation body];
    XElim -> "XElim";
    XIntro a -> application "XIntro" [variable a];
    XIntroKind a k -> application "XIntroKind" [variable a, kind k];
    XThen first second -> application "XThen" [computation first, computation second]
  };
  term :: XTerm -> String;
  term value = case value of {
    XVarTerm n -> application "XVarTerm" [name n];
    XAbs n ty body -> application "XAbs" [name n, typeLiteral ty, term body];
    XApp a b -> application "XApp" [term a, term b];
    XTypeAbs a bound body -> application "XTypeAbs" [variable a, typeLiteral bound, term body];
    XTypeApp body proof -> application "XTypeApp" [term body, computation proof];
    XLet n a b -> application "XLet" [name n, term a, term b];
    XLetRec definitions body -> application "XLetRec" [list (triple name typeLiteral term) definitions, term body];
    XIntTerm n -> application "XIntTerm" [integer n];
    XDoubleTerm n -> application "XDoubleTerm" [double n];
    XBoolTerm b -> application "XBoolTerm" [boolean b];
    XStringTerm text -> application "XStringTerm" [string text];
    XPrimitive p arguments -> application "XPrimitive" [primitive p, list typeLiteral arguments];
    XConstructor n arguments -> application "XConstructor" [string n, list typeLiteral arguments];
    XCase body ty alternatives -> application "XCase" [term body, typeLiteral ty, list alternative alternatives];
    XWithData declarations body -> application "XWithData" [list declaration declarations, term body]
  };
  patternLiteral :: XPattern -> String;
  patternLiteral value = case value of {
    XConstructorPattern n fields -> application "XConstructorPattern" [string n, list (maybe name) fields];
    XDefaultPattern n -> application "XDefaultPattern" [maybe name n]
  };
  alternative :: XAlternative -> String;
  alternative value = case value of {
    XAlternative pattern body -> application "XAlternative" [patternLiteral pattern, term body]
  };
  role :: Modules.Role -> String;
  role value = case value of {
    Modules.Value -> "Value";
    Modules.Datatype -> "Datatype";
    Modules.Class -> "Class";
    Modules.Constructor parent -> application "Constructor" [string parent];
    Modules.Method parent -> application "Method" [string parent];
    Modules.BuiltinType -> "BuiltinType";
    Modules.Primitive p -> application "Primitive" [primitive p];
    Modules.Boolean b -> application "Boolean" [boolean b];
    Modules.ManagedConstraint -> "ManagedConstraint"
  };
  entity :: Modules.Entity -> String;
  entity value = case value of {
    Modules.Entity owner spelling entityRole -> application "Entity" [string owner, string spelling, role entityRole]
  };
  moduleSpace :: Modules.ModuleSpace -> String;
  moduleSpace value = case value of { Modules.Terms -> "Terms"; Modules.Types -> "Types" };
  moduleInterface :: Modules.Interface -> String;
  moduleInterface value = case value of {
    Modules.Interface entries -> application "Interface" [map (pair moduleSpace string) (set entity) entries]
  };
  names :: Modules.Names -> String;
  names value = case value of { Modules.Names entries -> application "Names" [map entity string entries] };
  sourceContract :: Source.SourceContract -> String;
  sourceContract value = case value of {
    Source.SourceContract ty classes protected -> application "SourceContract"
      [typeLiteral ty, list string classes, boolean protected]
  };
  interface :: Artifact.CrateInterface -> String;
  interface value = case value of {
    Artifact.CrateInterface identity dependencies modules exports imports declarations classes instances
      lowered bindings entry fingerprint protection -> application "CrateInterface"
      [string identity, list (triple string string string) dependencies, list string modules,
       list (pair string (list entity)) exports, list (pair string (list string)) imports,
       list declaration declarations, list sourceClass classes, list (pair string sourceInstance) instances,
       list declaration lowered, list (pair string typeLiteral) bindings, string entry,
       string fingerprint, list (pair string boolean) protection]
  };
  rawPrelude :: Context.RawPrelude -> String;
  rawPrelude value = case value of {
    Context.RawPrelude identity primitiveCount iface body available serial sourceNames visible values protected sourceContracts witnesses ->
      application "RawPrelude"
        [string identity, integer primitiveCount, interface iface, term body,
         mapString (pair name typeLiteral) available, integer serial, names sourceNames,
         moduleInterface visible, set string values, set string protected, mapString sourceContract sourceContracts,
         list sourceModule witnesses]
  };

  -- Bound the inference problem for generated target data. Every chunk is an
  -- ordinary signed source definition and retains the normal checker path.
  data TermPieces = TermPieces Int ([] String) String;
  pieceText (TermPieces _ _ text) = text;
  pieceNext (TermPieces next _ _) = next;
  pieceDefinitions (TermPieces _ definitions _) = definitions;
  constantPiece text serial = TermPieces serial [] text;
  collectPieces :: [] (Int -> TermPieces) -> Int -> (,,) Int ([] String) ([] String);
  collectPieces renderers serial = case renderers of {
    [] -> (,,) serial [] [];
    (:) render rest -> let {
      first = render serial;
      remaining = collectPieces rest (pieceNext first)
    } in case remaining of { (,,) next definitions texts ->
      (,,) next (L.append (pieceDefinitions first) definitions) ((:) (pieceText first) texts) }
  };
  assemblePieces constructor renderers serial = case collectPieces renderers serial of {
    (,,) next definitions texts -> TermPieces next definitions (application constructor texts)
  };
  listPieces renderers serial = case collectPieces renderers serial of {
    (,,) next definitions texts -> TermPieces next definitions ("[" ++ L.intercalate "," texts ++ "]")
  };
  termPieces :: XTerm -> Int -> TermPieces;
  termPieces value serial = let {
    c = constantPiece;
    child = termPieces;
    node = case value of {
      XVarTerm n -> assemblePieces "XVarTerm" [c (name n)];
      XAbs n ty body -> assemblePieces "XAbs" [c (name n), c (typeLiteral ty), child body];
      XApp a b -> assemblePieces "XApp" [child a, child b];
      XTypeAbs a bound body -> assemblePieces "XTypeAbs" [c (variable a), c (typeLiteral bound), child body];
      XTypeApp body proof -> assemblePieces "XTypeApp" [child body, c (computation proof)];
      XLet n a b -> assemblePieces "XLet" [c (name n), child a, child b];
      XLetRec definitions body -> assemblePieces "XLetRec"
        [listPieces (L.map (\((,,) n ty rhs) -> assemblePieces "(,,)" [c (name n), c (typeLiteral ty), child rhs]) definitions), child body];
      XCase body ty alternatives -> assemblePieces "XCase"
        [child body, c (typeLiteral ty), listPieces (L.map (\(XAlternative pat rhs) ->
          assemblePieces "XAlternative" [c (patternLiteral pat), child rhs]) alternatives)];
      XWithData declarations body -> assemblePieces "XWithData" [c (list declaration declarations), child body];
      _ -> c (term value)
    };
    result = node serial
  } in if stringLength (pieceText result) < 8192 then result else let {
    label = "mlfLiteralTerm" ++ showInt (pieceNext result);
    definition = label ++ " :: () -> XTerm;\n" ++ label ++ " _ = " ++ pieceText result ++ ";\n"
  } in TermPieces (pieceNext result + 1)
    (L.snoc (pieceDefinitions result) definition) ("(" ++ label ++ " ())");
  rawPreludePieces :: Context.RawPrelude -> (,) String String;
  rawPreludePieces value = case value of {
    Context.RawPrelude identity primitiveCount iface body available serial sourceNames visible values protected sourceContracts witnesses -> let {
      pieces = termPieces body 0
    } in (,) (concatStringList (pieceDefinitions pieces))
      (application "RawPrelude"
        [string identity, integer primitiveCount, interface iface, pieceText pieces,
         mapString (pair name typeLiteral) available, integer serial, names sourceNames,
         moduleInterface visible, set string values, set string protected, mapString sourceContract sourceContracts,
         list sourceModule witnesses])
  };

}
