-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ArtifactStructure where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Bitstream as W;

  -- Closed, versioned structural schema over the shared binary symbol/node DAG.
  -- Tags are explicit ABI numbers, never constructor ordinals. All lists retain
  -- order and multiplicity. Names retain both identity and spelling hint; no
  -- binder normalization, pretty-printer, parser or proof deserialization occurs.
  -- Decode is raw syntax only. The integration admission boundary MUST perform
  -- Checked.check and the existing Separate/query/source validation in its scope.
  -- A shared structural node is data, not evidence checked in another binder.
  -- Wire framing, canonical UTF-8, backwards references and resource limits are
  -- enforced by Bitstream.decode/decodeGraph before typed shape decoding.

  malformed :: forall a. String -> Either String a;
  malformed name = Left ("malformed binary artifact " ++ name);
  toInt :: Int -> W.Value;
  toInt value = W.VInt value;
  fromInt :: W.Value -> Either String Int;
  fromInt value = case value of {
    W.VInt number -> Right number;
    _ -> malformed "Int"
  };
  toText :: String -> W.Value;
  toText value = W.VText value;
  fromText :: W.Value -> Either String String;
  fromText value = case value of {
    W.VText text -> Right text;
    _ -> malformed "String"
  };
  -- Float64 is encoded by its exact IEEE-754 bits, including NaN payloads and -0.
  toDouble :: Double -> W.Value;
  toDouble value = W.VBits (doubleToBits value);
  fromDouble :: W.Value -> Either String Double;
  fromDouble value = case value of {
    W.VBits bits -> Right (doubleFromBits bits);
    _ -> malformed "Float64"
  };
  toBool :: Bool -> W.Value;
  toBool value = if value then W.VNode 7 [] else W.VNode 6 [];
  fromBool :: W.Value -> Either String Bool;
  fromBool value = case value of {
    W.VNode tag [] -> if tag == 6 then Right False
      else if tag == 7 then Right True else malformed "Bool tag";
    _ -> malformed "Bool"
  };
  toList :: forall a. (a -> W.Value) -> [] a -> W.Value;
  toList encode values = W.VNode 1 (S.map encode values);
  fromList :: forall a. (W.Value -> Either String a) -> W.Value -> Either String ([] a);
  fromList decode value = case value of {
    W.VNode tag fields -> if tag == 1 then fromListAt decode fields [] (W.maxEdges W.defaultLimits)
      else malformed "list tag";
    _ -> malformed "list"
  };
  fromListAt :: forall a. (W.Value -> Either String a) -> [] W.Value -> [] a ->
    Int -> Either String ([] a);
  fromListAt decode values acc remaining = case values of {
    [] -> Right (S.reverse acc);
    (:) value rest -> if remaining <= 0 then Left "binary typed list count limit exceeded"
      else do {
        result <- decode value;
        fromListAt decode rest ((:) result acc) (remaining - 1)
      }
  };
  toMaybe :: forall a. (a -> W.Value) -> Maybe a -> W.Value;
  toMaybe encode value = case value of {
    Nothing -> W.VNode 4 [];
    Just item -> W.VNode 5 [encode item]
  };
  fromMaybe :: forall a. (W.Value -> Either String a) -> W.Value -> Either String (Maybe a);
  fromMaybe decode value = case value of {
    W.VNode tag fields -> if tag == 4 then case fields of {
      [] -> Right Nothing;
      _ -> malformed "Nothing arity"
    } else if tag == 5 then case fields of {
      [item] -> S.mapEither Just (decode item);
      _ -> malformed "Just arity"
    } else malformed "Maybe tag";
    _ -> malformed "Maybe"
  };
  toPair :: forall a b. (a -> W.Value) -> (b -> W.Value) -> (,) a b -> W.Value;
  toPair encodeA encodeB ((,) a b) = W.VNode 2 [encodeA a, encodeB b];
  fromPair :: forall a b. (W.Value -> Either String a) ->
    (W.Value -> Either String b) -> W.Value -> Either String ((,) a b);
  fromPair decodeA decodeB value = case value of {
    W.VNode tag [a, b] -> if tag == 2 then do {
      resultA <- decodeA a;
      resultB <- decodeB b;
      Right ((,) resultA resultB)
    } else malformed "pair tag";
    _ -> malformed "pair"
  };
  toTriple :: forall a b c. (a -> W.Value) -> (b -> W.Value) ->
    (c -> W.Value) -> (,,) a b c -> W.Value;
  toTriple encodeA encodeB encodeC ((,,) a b c) =
    W.VNode 3 [encodeA a, encodeB b, encodeC c];
  fromTriple :: forall a b c. (W.Value -> Either String a) ->
    (W.Value -> Either String b) -> (W.Value -> Either String c) ->
    W.Value -> Either String ((,,) a b c);
  fromTriple decodeA decodeB decodeC value = case value of {
    W.VNode tag [a, b, c] -> if tag == 3 then do {
      resultA <- decodeA a;
      resultB <- decodeB b;
      resultC <- decodeC c;
      Right ((,,) resultA resultB resultC)
    } else malformed "triple tag";
    _ -> malformed "triple"
  };
  -- Neutral model avoids a dependency cycle with Bootstrap.CrateArtifact.
  data CrateInterfaceFields =
    CrateInterfaceFields String ([] ((,,) String String String)) ([] String) ([] ((,) String ([] Modules.Entity))) ([] ((,) String ([] String))) ([] DataDecl) ([] SClassDecl) ([] ((,) String SInstanceDecl)) ([] DataDecl) ([] ((,) String XType)) String String ([] ((,) String Bool));
  -- Neutral model avoids a dependency cycle with Bootstrap.CrateArtifact.
  -- First field is True for LegacyCrateObject and False for CrateObject.
  data CrateObjectFields =
    CrateObjectFields Bool CrateInterfaceFields ([] Separate.UnitObject);

  toKind :: Kind -> W.Value;
  toKind value = case value of {
    Star -> W.VNode 10 [];
    KArrow x0 x1 -> W.VNode 11 [toKind x0, toKind x1]
  };
  fromKind :: W.Value -> Either String Kind;
  fromKind value = S.bindEither (decodeValue ShapeKind value) expectKind;

  toFlag :: Flag -> W.Value;
  toFlag value = case value of {
    Flexible -> W.VNode 12 [];
    Rigid -> W.VNode 13 []
  };
  fromFlag :: W.Value -> Either String Flag;
  fromFlag value = S.bindEither (decodeValue ShapeFlag value) expectFlag;

  toField :: Field -> W.Value;
  toField value = case value of {
    Parameter x0 -> W.VNode 20 [toText x0];
    Function x0 x1 -> W.VNode 21 [toField x0, toField x1];
    Applied x0 x1 -> W.VNode 22 [toText x0, (toList toField) x1];
    Application x0 x1 -> W.VNode 23 [toField x0, toField x1];
    Quantified x0 x1 x2 -> W.VNode 24 [toText x0, toKind x1, toField x2]
  };
  fromField :: W.Value -> Either String Field;
  fromField value = S.bindEither (decodeValue ShapeField value) expectField;

  toConstructorDecl :: ConstructorDecl -> W.Value;
  toConstructorDecl value = case value of {
    ConstructorDecl x0 x1 -> W.VNode 25 [toText x0, (toList toField) x1]
  };
  fromConstructorDecl :: W.Value -> Either String ConstructorDecl;
  fromConstructorDecl value = S.bindEither (decodeValue ShapeConstructorDecl value) expectConstructorDecl;

  toDataDecl :: DataDecl -> W.Value;
  toDataDecl value = case value of {
    DataDecl x0 x1 x2 -> W.VNode 26 [toText x0, (toList toText) x1, (toList toConstructorDecl) x2];
    DataDeclK x0 x1 x2 -> W.VNode 27 [toText x0, (toList (toPair toText toKind)) x1, (toList toConstructorDecl) x2]
  };
  fromDataDecl :: W.Value -> Either String DataDecl;
  fromDataDecl value = S.bindEither (decodeValue ShapeDataDecl value) expectDataDecl;

  toXTyVar :: XTyVar -> W.Value;
  toXTyVar value = case value of {
    XTyVar x0 -> W.VNode 30 [toInt x0]
  };
  fromXTyVar :: W.Value -> Either String XTyVar;
  fromXTyVar value = S.bindEither (decodeValue ShapeXTyVar value) expectXTyVar;

  toXName :: XName -> W.Value;
  toXName value = case value of {
    XName x0 x1 -> W.VNode 31 [toInt x0, toText x1]
  };
  fromXName :: W.Value -> Either String XName;
  fromXName value = S.bindEither (decodeValue ShapeXName value) expectXName;

  toXType :: XType -> W.Value;
  toXType value = case value of {
    XVar x0 -> W.VNode 40 [toXTyVar x0];
    XBot -> W.VNode 41 [];
    XBotKind x0 -> W.VNode 42 [toKind x0];
    XArrow x0 x1 -> W.VNode 43 [toXType x0, toXType x1];
    XCon x0 x1 -> W.VNode 44 [toText x0, (toList toXType) x1];
    XApply x0 x1 -> W.VNode 45 [toXType x0, toXType x1];
    XForall x0 x1 x2 -> W.VNode 46 [toXTyVar x0, toXType x1, toXType x2]
  };
  fromXType :: W.Value -> Either String XType;
  fromXType value = S.bindEither (decodeValue ShapeXType value) expectXType;

  toXComputation :: XComputation -> W.Value;
  toXComputation value = case value of {
    XRefl -> W.VNode 50 [];
    XBottom x0 -> W.VNode 51 [toXType x0];
    XHyp x0 -> W.VNode 52 [toXTyVar x0];
    XInner x0 -> W.VNode 53 [toXComputation x0];
    XOuter x0 x1 -> W.VNode 54 [toXTyVar x0, toXComputation x1];
    XElim -> W.VNode 55 [];
    XIntro x0 -> W.VNode 56 [toXTyVar x0];
    XIntroKind x0 x1 -> W.VNode 57 [toXTyVar x0, toKind x1];
    XThen x0 x1 -> W.VNode 58 [toXComputation x0, toXComputation x1]
  };
  fromXComputation :: W.Value -> Either String XComputation;
  fromXComputation value = S.bindEither (decodeValue ShapeXComputation value) expectXComputation;

  toXTerm :: XTerm -> W.Value;
  toXTerm value = case value of {
    XVarTerm x0 -> W.VNode 70 [toXName x0];
    XAbs x0 x1 x2 -> W.VNode 71 [toXName x0, toXType x1, toXTerm x2];
    XApp x0 x1 -> W.VNode 72 [toXTerm x0, toXTerm x1];
    XTypeAbs x0 x1 x2 -> W.VNode 73 [toXTyVar x0, toXType x1, toXTerm x2];
    XTypeApp x0 x1 -> W.VNode 74 [toXTerm x0, toXComputation x1];
    XLet x0 x1 x2 -> W.VNode 75 [toXName x0, toXTerm x1, toXTerm x2];
    XLetRec x0 x1 -> W.VNode 76 [(toList (toTriple toXName toXType toXTerm)) x0, toXTerm x1];
    XIntTerm x0 -> W.VNode 77 [toInt x0];
    XDoubleTerm x0 -> W.VNode 78 [toDouble x0];
    XBoolTerm x0 -> W.VNode 79 [toBool x0];
    XStringTerm x0 -> W.VNode 80 [toText x0];
    XPrimitive x0 x1 -> W.VNode 81 [toPrimitive x0, (toList toXType) x1];
    XConstructor x0 x1 -> W.VNode 82 [toText x0, (toList toXType) x1];
    XCase x0 x1 x2 -> W.VNode 83 [toXTerm x0, toXType x1, (toList toXAlternative) x2];
    XWithData x0 x1 -> W.VNode 84 [(toList toDataDecl) x0, toXTerm x1]
  };
  fromXTerm :: W.Value -> Either String XTerm;
  fromXTerm value = S.bindEither (decodeValue ShapeXTerm value) expectXTerm;

  toXPattern :: XPattern -> W.Value;
  toXPattern value = case value of {
    XConstructorPattern x0 x1 -> W.VNode 90 [toText x0, (toList (toMaybe toXName)) x1];
    XDefaultPattern x0 -> W.VNode 91 [(toMaybe toXName) x0]
  };
  fromXPattern :: W.Value -> Either String XPattern;
  fromXPattern value = S.bindEither (decodeValue ShapeXPattern value) expectXPattern;

  toXAlternative :: XAlternative -> W.Value;
  toXAlternative value = case value of {
    XAlternative x0 x1 -> W.VNode 92 [toXPattern x0, toXTerm x1]
  };
  fromXAlternative :: W.Value -> Either String XAlternative;
  fromXAlternative value = S.bindEither (decodeValue ShapeXAlternative value) expectXAlternative;

  toSType :: SType -> W.Value;
  toSType value = case value of {
    STVar x0 -> W.VNode 100 [toText x0];
    SBottom -> W.VNode 101 [];
    SBottomKind x0 -> W.VNode 102 [toKind x0];
    SArrow x0 x1 -> W.VNode 103 [toSType x0, toSType x1];
    SCon x0 x1 -> W.VNode 104 [toText x0, (toList toSType) x1];
    STypeApp x0 x1 -> W.VNode 105 [toSType x0, toSType x1];
    SForall x0 x1 x2 x3 -> W.VNode 106 [toFlag x0, toText x1, toSType x2, toSType x3];
    SQualified x0 x1 -> W.VNode 107 [(toList toSPredicate) x0, toSType x1]
  };
  fromSType :: W.Value -> Either String SType;
  fromSType value = S.bindEither (decodeValue ShapeSType value) expectSType;

  toSAnnotation :: SAnnotation -> W.Value;
  toSAnnotation value = case value of {
    SAnnotation x0 x1 -> W.VNode 110 [(toList toText) x0, toSType x1]
  };
  fromSAnnotation :: W.Value -> Either String SAnnotation;
  fromSAnnotation value = S.bindEither (decodeValue ShapeSAnnotation value) expectSAnnotation;

  toRecursiveMode :: RecursiveMode -> W.Value;
  toRecursiveMode value = case value of {
    InferRecursive -> W.VNode 111 [];
    CheckRecursive x0 -> W.VNode 112 [toSAnnotation x0]
  };
  fromRecursiveMode :: W.Value -> Either String RecursiveMode;
  fromRecursiveMode value = S.bindEither (decodeValue ShapeRecursiveMode value) expectRecursiveMode;

  toSourceSpan :: SourceSpan -> W.Value;
  toSourceSpan value = case value of {
    SourceSpan x0 x1 x2 x3 x4 x5 x6 -> W.VNode 113 [toText x0, toText x1, toText x2, toInt x3, toInt x4, toInt x5, toInt x6]
  };
  fromSourceSpan :: W.Value -> Either String SourceSpan;
  fromSourceSpan value = S.bindEither (decodeValue ShapeSourceSpan value) expectSourceSpan;

  toSourceString :: SourceString -> W.Value;
  toSourceString value = case value of {
    ScalarString x0 -> W.VNode 114 [toText x0];
    CharString x0 -> W.VNode 115 [(toList toInt) x0]
  };
  fromSourceString :: W.Value -> Either String SourceString;
  fromSourceString value = S.bindEither (decodeValue ShapeSourceString value) expectSourceString;

  toEvidenceRole :: EvidenceRole -> W.Value;
  toEvidenceRole value = case value of {
    GivenEvidence -> W.VNode 116 [];
    SuperclassEvidence -> W.VNode 117 [];
    InstanceEvidence -> W.VNode 118 []
  };
  fromEvidenceRole :: W.Value -> Either String EvidenceRole;
  fromEvidenceRole value = S.bindEither (decodeValue ShapeEvidenceRole value) expectEvidenceRole;

  toSExpr :: SExpr -> W.Value;
  toSExpr value = case value of {
    SVar x0 -> W.VNode 120 [toText x0];
    SConstructor x0 -> W.VNode 121 [toText x0];
    SLam x0 x1 x2 -> W.VNode 122 [toText x0, (toMaybe toSAnnotation) x1, toSExpr x2];
    SApp x0 x1 -> W.VNode 123 [toSExpr x0, toSExpr x1];
    SLet x0 x1 x2 -> W.VNode 124 [toText x0, toSExpr x1, toSExpr x2];
    SAnn x0 x1 -> W.VNode 125 [toSExpr x0, toSAnnotation x1];
    SSignature x0 x1 -> W.VNode 126 [toSExpr x0, toSAnnotation x1];
    SIntLit x0 -> W.VNode 127 [toInt x0];
    SDoubleLit x0 -> W.VNode 128 [toDouble x0];
    SBoolLit x0 -> W.VNode 129 [toBool x0];
    SStringLit x0 -> W.VNode 130 [toText x0];
    SPrimitive x0 -> W.VNode 131 [toPrimitive x0];
    SCase x0 x1 -> W.VNode 132 [toSExpr x0, (toList toSAlternative) x1];
    SDo x0 x1 -> W.VNode 133 [(toList toSStatement) x0, toSExpr x1];
    SEquations x0 -> W.VNode 134 [(toList (toPair (toList toSPattern) toSExpr)) x0];
    SLetRec x0 x1 -> W.VNode 135 [(toList (toTriple toText toRecursiveMode toSExpr)) x0, toSExpr x1];
    SWanted x0 x1 -> W.VNode 136 [toText x0, (toList (toPair toEvidenceRole toText)) x1];
    SChecked x0 x1 -> W.VNode 137 [toSType x0, toSExpr x1];
    SSourceDefinition x0 -> W.VNode 138 [toSExpr x0];
    SCallSite x0 x1 x2 -> W.VNode 139 [toText x0, toSourceSpan x1, toSExpr x2];
    SSharedBind x0 x1 x2 x3 x4 -> W.VNode 140 [toSPattern x0, toSExpr x1, toSExpr x2, toSExpr x3, toSExpr x4]
  };
  fromSExpr :: W.Value -> Either String SExpr;
  fromSExpr value = S.bindEither (decodeValue ShapeSExpr value) expectSExpr;

  toSPattern :: SPattern -> W.Value;
  toSPattern value = case value of {
    SConstructorPattern x0 x1 -> W.VNode 150 [toText x0, (toList (toMaybe toText)) x1];
    SDefaultPattern x0 -> W.VNode 151 [(toMaybe toText) x0];
    SNestedPattern x0 x1 -> W.VNode 152 [toText x0, (toList toSPattern) x1];
    SAnnotatedPattern x0 x1 -> W.VNode 153 [toText x0, toSAnnotation x1];
    SIntPattern x0 -> W.VNode 154 [toInt x0];
    SStringPattern x0 -> W.VNode 155 [toText x0];
    SOverloadedStringPattern x0 x1 x2 -> W.VNode 156 [toSourceString x0, toText x1, toText x2];
    SBoolPattern x0 -> W.VNode 157 [toBool x0];
    SAsPattern x0 x1 -> W.VNode 158 [toText x0, toSPattern x1];
    SLazyPattern x0 -> W.VNode 159 [toSPattern x0]
  };
  fromSPattern :: W.Value -> Either String SPattern;
  fromSPattern value = S.bindEither (decodeValue ShapeSPattern value) expectSPattern;

  toSAlternative :: SAlternative -> W.Value;
  toSAlternative value = case value of {
    SAlternative x0 x1 -> W.VNode 160 [toSPattern x0, toSExpr x1]
  };
  fromSAlternative :: W.Value -> Either String SAlternative;
  fromSAlternative value = S.bindEither (decodeValue ShapeSAlternative value) expectSAlternative;

  toSStatement :: SStatement -> W.Value;
  toSStatement value = case value of {
    SDoBind x0 x1 -> W.VNode 161 [toSPattern x0, toSExpr x1];
    SDoThen x0 -> W.VNode 162 [toSExpr x0];
    SDoLet x0 x1 x2 -> W.VNode 163 [toText x0, (toMaybe toSAnnotation) x1, toSExpr x2];
    SDoLetRec x0 -> W.VNode 164 [(toList (toTriple toText toRecursiveMode toSExpr)) x0]
  };
  fromSStatement :: W.Value -> Either String SStatement;
  fromSStatement value = S.bindEither (decodeValue ShapeSStatement value) expectSStatement;

  toSPredicate :: SPredicate -> W.Value;
  toSPredicate value = case value of {
    SPredicate x0 x1 -> W.VNode 170 [toText x0, (toList toSType) x1]
  };
  fromSPredicate :: W.Value -> Either String SPredicate;
  fromSPredicate value = S.bindEither (decodeValue ShapeSPredicate value) expectSPredicate;

  toSClassDecl :: SClassDecl -> W.Value;
  toSClassDecl value = case value of {
    SClassDecl x0 x1 x2 x3 -> W.VNode 171 [toText x0, (toList (toPair toText toKind)) x1, (toList toSPredicate) x2, (toList (toPair toText toSType)) x3]
  };
  fromSClassDecl :: W.Value -> Either String SClassDecl;
  fromSClassDecl value = S.bindEither (decodeValue ShapeSClassDecl value) expectSClassDecl;

  toSInstanceDecl :: SInstanceDecl -> W.Value;
  toSInstanceDecl value = case value of {
    SInstanceDecl x0 x1 x2 x3 x4 -> W.VNode 172 [(toList (toPair toText toKind)) x0, (toList toSPredicate) x1, toText x2, (toList toSType) x3, (toList (toPair toText toSExpr)) x4]
  };
  fromSInstanceDecl :: W.Value -> Either String SInstanceDecl;
  fromSInstanceDecl value = S.bindEither (decodeValue ShapeSInstanceDecl value) expectSInstanceDecl;

  toRole :: Modules.Role -> W.Value;
  toRole value = case value of {
    Modules.Value -> W.VNode 180 [];
    Modules.Datatype -> W.VNode 181 [];
    Modules.Class -> W.VNode 182 [];
    Modules.Constructor x0 -> W.VNode 183 [toText x0];
    Modules.Method x0 -> W.VNode 184 [toText x0];
    Modules.BuiltinType -> W.VNode 185 [];
    Modules.Primitive x0 -> W.VNode 186 [toPrimitive x0];
    Modules.Boolean x0 -> W.VNode 187 [toBool x0];
    Modules.ManagedConstraint -> W.VNode 188 []
  };
  fromRole :: W.Value -> Either String Modules.Role;
  fromRole value = S.bindEither (decodeValue ShapeRole value) expectRole;

  toEntity :: Modules.Entity -> W.Value;
  toEntity value = case value of {
    Modules.Entity x0 x1 x2 -> W.VNode 189 [toText x0, toText x1, toRole x2]
  };
  fromEntity :: W.Value -> Either String Modules.Entity;
  fromEntity value = S.bindEither (decodeValue ShapeEntity value) expectEntity;

  toSourceSyntax :: SourceSyntax -> W.Value;
  toSourceSyntax value = case value of {
    LegacyEmlfV1 -> W.VNode 200 [];
    SharedHaskellV1 -> W.VNode 201 [];
    MetadataSyntax -> W.VNode 202 []
  };
  fromSourceSyntax :: W.Value -> Either String SourceSyntax;
  fromSourceSyntax value = S.bindEither (decodeValue ShapeSourceSyntax value) expectSourceSyntax;

  toSelection :: Selection -> W.Value;
  toSelection value = case value of {
    Everything -> W.VNode 203 [];
    Only x0 -> W.VNode 204 [(toList toExport) x0];
    Hiding x0 -> W.VNode 205 [(toList toExport) x0]
  };
  fromSelection :: W.Value -> Either String Selection;
  fromSelection value = S.bindEither (decodeValue ShapeSelection value) expectSelection;

  toExport :: Export -> W.Value;
  toExport value = case value of {
    ExportValue x0 -> W.VNode 206 [toText x0];
    ExportType x0 x1 -> W.VNode 207 [toText x0, toMembers x1];
    ExportModule x0 -> W.VNode 208 [toText x0]
  };
  fromExport :: W.Value -> Either String Export;
  fromExport value = S.bindEither (decodeValue ShapeExport value) expectExport;

  toMembers :: Members -> W.Value;
  toMembers value = case value of {
    Abstract -> W.VNode 209 [];
    AllMembers -> W.VNode 210 [];
    Members x0 -> W.VNode 211 [(toList toText) x0]
  };
  fromMembers :: W.Value -> Either String Members;
  fromMembers value = S.bindEither (decodeValue ShapeMembers value) expectMembers;

  toImport :: Import -> W.Value;
  toImport value = case value of {
    Import x0 x1 x2 x3 -> W.VNode 212 [toText x0, toBool x1, (toMaybe toText) x2, toSelection x3]
  };
  fromImport :: W.Value -> Either String Import;
  fromImport value = S.bindEither (decodeValue ShapeImport value) expectImport;

  toSourceModule :: SourceModule -> W.Value;
  toSourceModule value = case value of {
    SourceModule x0 x1 x2 x3 x4 x5 x6 x7 x8 x9 -> W.VNode 213 [toText x0, (toMaybe toText) x1, (toMaybe (toList toExport)) x2, (toList toImport) x3, (toList toDataDecl) x4, (toList toSClassDecl) x5, (toList toSInstanceDecl) x6, (toList (toTriple toText (toMaybe toSAnnotation) toSExpr)) x7, (toMaybe toSExpr) x8, toSourceSyntax x9]
  };
  fromSourceModule :: W.Value -> Either String SourceModule;
  fromSourceModule value = S.bindEither (decodeValue ShapeSourceModule value) expectSourceModule;

  toSProgram :: SProgram -> W.Value;
  toSProgram value = case value of {
    SProgram x0 x1 -> W.VNode 214 [(toList toDataDecl) x0, toSExpr x1];
    SClassProgram x0 x1 x2 x3 -> W.VNode 215 [(toList toDataDecl) x0, (toList toSClassDecl) x1, (toList toSInstanceDecl) x2, toSExpr x3]
  };
  fromSProgram :: W.Value -> Either String SProgram;
  fromSProgram value = S.bindEither (decodeValue ShapeSProgram value) expectSProgram;

  toUnitInterface :: Separate.UnitInterface -> W.Value;
  toUnitInterface value = case value of {
    Separate.UnitInterface x0 x1 x2 x3 x4 x5 x6 x7 -> W.VNode 240 [toText x0, (toList (toPair toText toText)) x1, (toList toEntity) x2, (toList toDataDecl) x3, (toList toSClassDecl) x4, (toList (toPair toText toInterfaceInstance)) x5, (toList (toPair toText toXType)) x6, toText x7]
  };
  fromUnitInterface :: W.Value -> Either String Separate.UnitInterface;
  fromUnitInterface value = S.bindEither (decodeValue ShapeUnitInterface value) expectUnitInterface;

  toCrateInterfaceFields :: CrateInterfaceFields -> W.Value;
  toCrateInterfaceFields value = case value of {
    CrateInterfaceFields x0 x1 x2 x3 x4 x5 x6 x7 x8 x9 x10 x11 x12 -> W.VNode 242 [toText x0, (toList (toTriple toText toText toText)) x1, (toList toText) x2, (toList (toPair toText (toList toEntity))) x3, (toList (toPair toText (toList toText))) x4, (toList toDataDecl) x5, (toList toSClassDecl) x6, (toList (toPair toText toInterfaceInstance)) x7, (toList toDataDecl) x8, (toList (toPair toText toXType)) x9, toText x10, toText x11, (toList (toPair toText toBool)) x12]
  };
  fromCrateInterfaceFields :: W.Value -> Either String CrateInterfaceFields;
  fromCrateInterfaceFields value = S.bindEither (decodeValue ShapeCrateInterfaceFields value) expectCrateInterfaceFields;

  toCrateObjectFields :: CrateObjectFields -> W.Value;
  toCrateObjectFields value = case value of {
    CrateObjectFields x0 x1 x2 -> W.VNode 243 [toBool x0, toCrateInterfaceFields x1, (toList toRawUnitObject) x2]
  };
  fromCrateObjectFields :: W.Value -> Either String CrateObjectFields;
  fromCrateObjectFields value = S.bindEither (decodeValue ShapeCrateObjectFields value) expectCrateObjectFields;

  -- Frozen append-only primitive ABI. Unknown/future numbers are rejected;
  -- declaration order and allPrimitives list position are not wire identities.
  primitiveCode :: Primitive -> Int;
  primitiveCode primitive = case primitive of {
    PIOReturn -> 0;
    PIOBind -> 1;
    PPutStr -> 2;
    PPutStrLn -> 3;
    PGetLine -> 4;
    PPrintInt -> 5;
    PConcatString -> 6;
    PShowInt -> 7;
    PAddInt -> 8;
    PSubInt -> 9;
    PEqInt -> 10;
    PLtInt -> 11;
    PEqString -> 12;
    PIfThenElse -> 13;
    PMulInt -> 14;
    PQuotInt -> 15;
    PRemInt -> 16;
    PReadInt -> 17;
    PAddDouble -> 18;
    PSubDouble -> 19;
    PMulDouble -> 20;
    PDivDouble -> 21;
    PSqrtDouble -> 22;
    PEqDouble -> 23;
    PLtDouble -> 24;
    PIntToDouble -> 25;
    PFormatDouble -> 26;
    PNewIntArray -> 27;
    PReadIntArray -> 28;
    PWriteIntArray -> 29;
    PLengthIntArray -> 30;
    PNewDoubleArray -> 31;
    PReadDoubleArray -> 32;
    PWriteDoubleArray -> 33;
    PLengthDoubleArray -> 34;
    PNewByteArray -> 35;
    PReadByteArray -> 36;
    PWriteByteArray -> 37;
    PLengthByteArray -> 38;
    PByteArrayFromString -> 39;
    PPutBytes -> 40;
    PGetByteLine -> 41;
    PNewIntTable -> 42;
    PReadIntTable -> 43;
    PWriteIntTable -> 44;
    PAndInt -> 45;
    PStringLength -> 46;
    PStringCodeAt -> 47;
    PStringSlice -> 48;
    PStringFromCode -> 49;
    PCompareString -> 50;
    PReadDouble -> 51;
    PDoubleToBits -> 52;
    PDoubleFromBits -> 53;
    PSeq -> 54;
    PPanic -> 55;
    PReadFile -> 56;
    PWriteFile -> 57;
    PFileExists -> 58;
    PCanonicalPath -> 59;
    PGetArgCount -> 60;
    PGetArg -> 61;
    PPutErr -> 62;
    PExitWith -> 63;
    PGetExecutablePath -> 64;
    PGetContents -> 65;
    PSTReturn -> 66;
    PSTBind -> 67;
    PRunST -> 68;
    PNewSTArray -> 69;
    PReadSTArray -> 70;
    PWriteSTArray -> 71;
    PLengthSTArray -> 72;
    PGetEnv -> 73;
    PSetEnv -> 74;
    PUnsetEnv -> 75;
    PRunProcess -> 76;
    PListDirectory -> 77;
    PDirectoryExists -> 78;
    PFileDigest -> 79;
    PAcquireFileLock -> 80;
    PReleaseFileLock -> 81;
    PProcessSupervisor -> 82;
    PAsyncScopeNew -> 83;
    PAsyncScopeClose -> 84;
    PAsyncNewCompletion -> 85;
    PAsyncResolveCompletion -> 86;
    PAsyncReadCompletion -> 87;
    PAsyncSubscribeCompletion -> 88;
    PAsyncSubscriptionStatus -> 89;
    PAsyncCancelSubscription -> 90;
    PAsyncStep -> 91;
    PAsyncEnqueue -> 92;
    PAsyncDelay -> 93;
    PAsyncWait -> 94;
    PTextToChars -> 95;
    PTextFromChars -> 96;
    PCharCode -> 97;
    PCharFromCode -> 98;
    PUserError -> 99;
    PIOError -> 100;
    PCatchIOError -> 101;
    PIOErrorString -> 102;
    PEmptyCallStack -> 103;
    PPushCallStack -> 104;
    PPrettyCallStack -> 105;
    PIOErrorWithStack -> 106;
    PConcatStringList -> 107;
    POrInt -> 108;
    PXorInt -> 109;
    PShiftLInt -> 110;
    PShiftRInt -> 111;
    PUnsignedShiftRInt -> 112;
    PCountLeadingZerosInt -> 113;
    PCountTrailingZerosInt -> 114;
    PPopCountInt -> 115;
    PIntToInteger -> 116;
    PIntegerToInt -> 117;
    PAddInteger -> 118;
    PSubInteger -> 119;
    PMulInteger -> 120;
    PQuotInteger -> 121;
    PRemInteger -> 122;
    PEqInteger -> 123;
    PLtInteger -> 124;
    PShowInteger -> 125;
    PReadInteger -> 126;
    PIntegerToDouble -> 127;
    PUnsignedLtInt -> 128;
    PReadByteFileOrError -> 129;
    PWriteByteFileOrError -> 130;
    PByteArrayDigest -> 131
  };
  primitiveFromCode :: Int -> Either String Primitive;
  primitiveFromCode code =
    if code == 0 then Right PIOReturn
    else if code == 1 then Right PIOBind
    else if code == 2 then Right PPutStr
    else if code == 3 then Right PPutStrLn
    else if code == 4 then Right PGetLine
    else if code == 5 then Right PPrintInt
    else if code == 6 then Right PConcatString
    else if code == 7 then Right PShowInt
    else if code == 8 then Right PAddInt
    else if code == 9 then Right PSubInt
    else if code == 10 then Right PEqInt
    else if code == 11 then Right PLtInt
    else if code == 12 then Right PEqString
    else if code == 13 then Right PIfThenElse
    else if code == 14 then Right PMulInt
    else if code == 15 then Right PQuotInt
    else if code == 16 then Right PRemInt
    else if code == 17 then Right PReadInt
    else if code == 18 then Right PAddDouble
    else if code == 19 then Right PSubDouble
    else if code == 20 then Right PMulDouble
    else if code == 21 then Right PDivDouble
    else if code == 22 then Right PSqrtDouble
    else if code == 23 then Right PEqDouble
    else if code == 24 then Right PLtDouble
    else if code == 25 then Right PIntToDouble
    else if code == 26 then Right PFormatDouble
    else if code == 27 then Right PNewIntArray
    else if code == 28 then Right PReadIntArray
    else if code == 29 then Right PWriteIntArray
    else if code == 30 then Right PLengthIntArray
    else if code == 31 then Right PNewDoubleArray
    else if code == 32 then Right PReadDoubleArray
    else if code == 33 then Right PWriteDoubleArray
    else if code == 34 then Right PLengthDoubleArray
    else if code == 35 then Right PNewByteArray
    else if code == 36 then Right PReadByteArray
    else if code == 37 then Right PWriteByteArray
    else if code == 38 then Right PLengthByteArray
    else if code == 39 then Right PByteArrayFromString
    else if code == 40 then Right PPutBytes
    else if code == 41 then Right PGetByteLine
    else if code == 42 then Right PNewIntTable
    else if code == 43 then Right PReadIntTable
    else if code == 44 then Right PWriteIntTable
    else if code == 45 then Right PAndInt
    else if code == 46 then Right PStringLength
    else if code == 47 then Right PStringCodeAt
    else if code == 48 then Right PStringSlice
    else if code == 49 then Right PStringFromCode
    else if code == 50 then Right PCompareString
    else if code == 51 then Right PReadDouble
    else if code == 52 then Right PDoubleToBits
    else if code == 53 then Right PDoubleFromBits
    else if code == 54 then Right PSeq
    else if code == 55 then Right PPanic
    else if code == 56 then Right PReadFile
    else if code == 57 then Right PWriteFile
    else if code == 58 then Right PFileExists
    else if code == 59 then Right PCanonicalPath
    else if code == 60 then Right PGetArgCount
    else if code == 61 then Right PGetArg
    else if code == 62 then Right PPutErr
    else if code == 63 then Right PExitWith
    else if code == 64 then Right PGetExecutablePath
    else if code == 65 then Right PGetContents
    else if code == 66 then Right PSTReturn
    else if code == 67 then Right PSTBind
    else if code == 68 then Right PRunST
    else if code == 69 then Right PNewSTArray
    else if code == 70 then Right PReadSTArray
    else if code == 71 then Right PWriteSTArray
    else if code == 72 then Right PLengthSTArray
    else if code == 73 then Right PGetEnv
    else if code == 74 then Right PSetEnv
    else if code == 75 then Right PUnsetEnv
    else if code == 76 then Right PRunProcess
    else if code == 77 then Right PListDirectory
    else if code == 78 then Right PDirectoryExists
    else if code == 79 then Right PFileDigest
    else if code == 80 then Right PAcquireFileLock
    else if code == 81 then Right PReleaseFileLock
    else if code == 82 then Right PProcessSupervisor
    else if code == 83 then Right PAsyncScopeNew
    else if code == 84 then Right PAsyncScopeClose
    else if code == 85 then Right PAsyncNewCompletion
    else if code == 86 then Right PAsyncResolveCompletion
    else if code == 87 then Right PAsyncReadCompletion
    else if code == 88 then Right PAsyncSubscribeCompletion
    else if code == 89 then Right PAsyncSubscriptionStatus
    else if code == 90 then Right PAsyncCancelSubscription
    else if code == 91 then Right PAsyncStep
    else if code == 92 then Right PAsyncEnqueue
    else if code == 93 then Right PAsyncDelay
    else if code == 94 then Right PAsyncWait
    else if code == 95 then Right PTextToChars
    else if code == 96 then Right PTextFromChars
    else if code == 97 then Right PCharCode
    else if code == 98 then Right PCharFromCode
    else if code == 99 then Right PUserError
    else if code == 100 then Right PIOError
    else if code == 101 then Right PCatchIOError
    else if code == 102 then Right PIOErrorString
    else if code == 103 then Right PEmptyCallStack
    else if code == 104 then Right PPushCallStack
    else if code == 105 then Right PPrettyCallStack
    else if code == 106 then Right PIOErrorWithStack
    else if code == 107 then Right PConcatStringList
    else if code == 108 then Right POrInt
    else if code == 109 then Right PXorInt
    else if code == 110 then Right PShiftLInt
    else if code == 111 then Right PShiftRInt
    else if code == 112 then Right PUnsignedShiftRInt
    else if code == 113 then Right PCountLeadingZerosInt
    else if code == 114 then Right PCountTrailingZerosInt
    else if code == 115 then Right PPopCountInt
    else if code == 116 then Right PIntToInteger
    else if code == 117 then Right PIntegerToInt
    else if code == 118 then Right PAddInteger
    else if code == 119 then Right PSubInteger
    else if code == 120 then Right PMulInteger
    else if code == 121 then Right PQuotInteger
    else if code == 122 then Right PRemInteger
    else if code == 123 then Right PEqInteger
    else if code == 124 then Right PLtInteger
    else if code == 125 then Right PShowInteger
    else if code == 126 then Right PReadInteger
    else if code == 127 then Right PIntegerToDouble
    else if code == 128 then Right PUnsignedLtInt
    else if code == 129 then Right PReadByteFileOrError
    else if code == 130 then Right PWriteByteFileOrError
    else if code == 131 then Right PByteArrayDigest
    else malformed "primitive code";
  toPrimitive :: Primitive -> W.Value;
  toPrimitive value = W.VNode 32 [toInt (primitiveCode value)];
  fromPrimitive :: W.Value -> Either String Primitive;
  fromPrimitive value = case value of {
    W.VNode tag [code] -> if tag == 32 then do {
      number <- fromInt code;
      primitiveFromCode number
    } else malformed "primitive tag";
    _ -> malformed "primitive"
  };

  -- Interface methods are intentionally not source implementations. The legacy
  -- interface contract preserves method names and replaces every body using
  -- Separate.stripInstance. A distinct tag stores exactly those names; no full
  -- source body can be silently accepted as interface metadata. The independent
  -- to/fromSInstanceDecl above is lossless and retains real source method bodies.
  toInterfaceInstance :: SInstanceDecl -> W.Value;
  toInterfaceInstance value = case Separate.stripInstance value of {
    SInstanceDecl variables context klass head methods -> W.VNode 173
      [(toList (toPair toText toKind)) variables,
       (toList toSPredicate) context, toText klass, (toList toSType) head,
       (toList toText) (S.map S.fst methods)]
  };
  fromInterfaceInstance :: W.Value -> Either String SInstanceDecl;
  fromInterfaceInstance value = S.bindEither (decodeValue ShapeInterfaceInstance value) expectInterfaceInstance;

  -- CheckedUnitObject contributes only its raw term. There is no wire tag for
  -- CheckedTerm and decoding cannot manufacture or reuse a checked receipt.
  toRawUnitObject :: Separate.UnitObject -> W.Value;
  toRawUnitObject object = W.VNode 241
    [toUnitInterface (Separate.objectInterface object), toXTerm (Separate.objectTerm object)];
  fromRawUnitObject :: W.Value -> Either String Separate.UnitObject;
  fromRawUnitObject value = S.bindEither (decodeValue ShapeRawUnitObject value) expectRawUnitObject;

  -- A single shared root for datatype contexts, also composable with object and
  -- interface roots so repeated declarations/types/symbols share actual nodes.
  toDataContext :: [] DataDecl -> W.Value;
  toDataContext declarations = W.VNode 244 [(toList toDataDecl) declarations];
  fromDataContext :: W.Value -> Either String ([] DataDecl);
  fromDataContext value = S.bindEither (decodeValue ShapeDataContext value) expectDataContext;


  -- One explicit postorder machine handles Value trees and validated Graph IDs.
  -- Close consumes completed typed children; extractors never call from<Type>.
  -- Graph memo keys include the expected shape and node ID. The memo is local
  -- to this one graph/read, and stores only raw syntax, never CheckedTerm proof.
  -- Visit/width budgets match wire defaults; they are not an RSS guarantee.
  data DecodeShape =
    ShapeInt |
    ShapeText |
    ShapeDouble |
    ShapeBool |
    ShapeKind |
    ShapeFlag |
    ShapeField |
    ShapeConstructorDecl |
    ShapeDataDecl |
    ShapeXTyVar |
    ShapeXName |
    ShapeXType |
    ShapeXComputation |
    ShapeXTerm |
    ShapeXPattern |
    ShapeXAlternative |
    ShapeSType |
    ShapeSAnnotation |
    ShapeRecursiveMode |
    ShapeSourceSpan |
    ShapeSourceString |
    ShapeEvidenceRole |
    ShapeSExpr |
    ShapeSPattern |
    ShapeSAlternative |
    ShapeSStatement |
    ShapeSPredicate |
    ShapeSClassDecl |
    ShapeSInstanceDecl |
    ShapeRole |
    ShapeEntity |
    ShapeSourceSyntax |
    ShapeSelection |
    ShapeExport |
    ShapeMembers |
    ShapeImport |
    ShapeSourceModule |
    ShapeSProgram |
    ShapeUnitInterface |
    ShapeCrateInterfaceFields |
    ShapeCrateObjectFields |
    ShapePrimitive |
    ShapeInterfaceInstance |
    ShapeRawUnitObject |
    ShapeDataContext |
    ShapeList DecodeShape |
    ShapePair DecodeShape DecodeShape |
    ShapeTriple DecodeShape DecodeShape DecodeShape |
    ShapeMaybe DecodeShape;
  data Decoded =
    DecodedInt Int |
    DecodedText String |
    DecodedDouble Double |
    DecodedBool Bool |
    DecodedKind Kind |
    DecodedFlag Flag |
    DecodedField Field |
    DecodedConstructorDecl ConstructorDecl |
    DecodedDataDecl DataDecl |
    DecodedXTyVar XTyVar |
    DecodedXName XName |
    DecodedXType XType |
    DecodedXComputation XComputation |
    DecodedXTerm XTerm |
    DecodedXPattern XPattern |
    DecodedXAlternative XAlternative |
    DecodedSType SType |
    DecodedSAnnotation SAnnotation |
    DecodedRecursiveMode RecursiveMode |
    DecodedSourceSpan SourceSpan |
    DecodedSourceString SourceString |
    DecodedEvidenceRole EvidenceRole |
    DecodedSExpr SExpr |
    DecodedSPattern SPattern |
    DecodedSAlternative SAlternative |
    DecodedSStatement SStatement |
    DecodedSPredicate SPredicate |
    DecodedSClassDecl SClassDecl |
    DecodedSInstanceDecl SInstanceDecl |
    DecodedRole Modules.Role |
    DecodedEntity Modules.Entity |
    DecodedSourceSyntax SourceSyntax |
    DecodedSelection Selection |
    DecodedExport Export |
    DecodedMembers Members |
    DecodedImport Import |
    DecodedSourceModule SourceModule |
    DecodedSProgram SProgram |
    DecodedUnitInterface Separate.UnitInterface |
    DecodedCrateInterfaceFields CrateInterfaceFields |
    DecodedCrateObjectFields CrateObjectFields |
    DecodedPrimitive Primitive |
    DecodedInterfaceInstance SInstanceDecl |
    DecodedRawUnitObject Separate.UnitObject |
    DecodedDataContext ([] DataDecl) |
    DecodedList ([] Decoded) |
    DecodedPair Decoded Decoded |
    DecodedTriple Decoded Decoded Decoded |
    DecodedNothing |
    DecodedJust Decoded;
  data DecodeInput = ValueInput W.Value | GraphInput W.Graph Int;
  data DecodeView = ViewInt Int | ViewBits Int | ViewText String | ViewNode Int ([] DecodeInput);
  data DecodeTask =
    DecodeOne DecodeShape DecodeInput |
    DecodeFields ([] ((,) DecodeShape DecodeInput)) |
    DecodeRepeated DecodeShape ([] DecodeInput) |
    DecodeClose Int Int |
    DecodeRemember DecodeShape Int;
  shapeCode :: DecodeShape -> Int;
  shapeCode shape = case shape of {
    ShapeInt -> 0;
    ShapeText -> 1;
    ShapeDouble -> 2;
    ShapeBool -> 3;
    ShapeKind -> 4;
    ShapeFlag -> 5;
    ShapeField -> 6;
    ShapeConstructorDecl -> 7;
    ShapeDataDecl -> 8;
    ShapeXTyVar -> 9;
    ShapeXName -> 10;
    ShapeXType -> 11;
    ShapeXComputation -> 12;
    ShapeXTerm -> 13;
    ShapeXPattern -> 14;
    ShapeXAlternative -> 15;
    ShapeSType -> 16;
    ShapeSAnnotation -> 17;
    ShapeRecursiveMode -> 18;
    ShapeSourceSpan -> 19;
    ShapeSourceString -> 20;
    ShapeEvidenceRole -> 21;
    ShapeSExpr -> 22;
    ShapeSPattern -> 23;
    ShapeSAlternative -> 24;
    ShapeSStatement -> 25;
    ShapeSPredicate -> 26;
    ShapeSClassDecl -> 27;
    ShapeSInstanceDecl -> 28;
    ShapeRole -> 29;
    ShapeEntity -> 30;
    ShapeSourceSyntax -> 31;
    ShapeSelection -> 32;
    ShapeExport -> 33;
    ShapeMembers -> 34;
    ShapeImport -> 35;
    ShapeSourceModule -> 36;
    ShapeSProgram -> 37;
    ShapeUnitInterface -> 38;
    ShapeCrateInterfaceFields -> 39;
    ShapeCrateObjectFields -> 40;
    ShapePrimitive -> 41;
    ShapeInterfaceInstance -> 42;
    ShapeRawUnitObject -> 43;
    ShapeDataContext -> 44;
    ShapeList _ -> 1001;
    ShapePair _ _ -> 1002;
    ShapeTriple _ _ _ -> 1003;
    ShapeMaybe _ -> 1004
  };
  -- Descriptor nesting is fixed by this schema, not by untrusted AST depth.
  compareShape :: DecodeShape -> DecodeShape -> Int;
  compareShape a b = let { order = S.compareInt (shapeCode a) (shapeCode b) } in
    if order /= 0 then order else case a of {
      ShapeList x -> case b of { ShapeList y -> compareShape x y; _ -> 0 };
      ShapeMaybe x -> case b of { ShapeMaybe y -> compareShape x y; _ -> 0 };
      ShapePair a0 a1 -> case b of {
        ShapePair b0 b1 -> let { first = compareShape a0 b0 } in
          if first /= 0 then first else compareShape a1 b1;
        _ -> 0
      };
      ShapeTriple a0 a1 a2 -> case b of {
        ShapeTriple b0 b1 b2 -> let { first = compareShape a0 b0 } in
          if first /= 0 then first else let { second = compareShape a1 b1 } in
            if second /= 0 then second else compareShape a2 b2;
        _ -> 0
      };
      _ -> 0
    };
  compareDecodeKey :: (,) DecodeShape Int -> (,) DecodeShape Int -> Int;
  compareDecodeKey ((,) a i) ((,) b j) = let { order = compareShape a b } in
    if order == 0 then S.compareInt i j else order;
  valueInputs :: Int -> [] W.Value -> [] DecodeInput -> Either String ([] DecodeInput);
  valueInputs remaining fields acc = case fields of {
    [] -> Right (S.reverse acc);
    (:) value rest -> if remaining <= 0 then Left "binary typed list count limit exceeded"
      else valueInputs (remaining - 1) rest ((:) (ValueInput value) acc)
  };
  graphInputs :: Int -> W.Graph -> [] Int -> [] DecodeInput -> Either String ([] DecodeInput);
  graphInputs remaining graph fields acc = case fields of {
    [] -> Right (S.reverse acc);
    (:) index rest -> if remaining <= 0 then Left "binary typed list count limit exceeded"
      else graphInputs (remaining - 1) graph rest ((:) (GraphInput graph index) acc)
  };
  inspectInput :: DecodeShape -> Int -> DecodeInput -> Either String DecodeView;
  inspectInput shape remaining input = let {
    -- Only a list shape has variable arity. No closed constructor exceeds 13
    -- fields, so malformed wide fixed-arity nodes are rejected before copying.
    arityLimit = case shape of { ShapeList _ -> W.maxEdges W.defaultLimits; _ -> 13 };
    width = S.min remaining arityLimit
  } in case input of {
    ValueInput value -> case value of {
      W.VInt number -> Right (ViewInt number);
      W.VBits bits -> Right (ViewBits bits);
      W.VText text -> Right (ViewText text);
      W.VNode tag fields -> S.mapEither (ViewNode tag) (valueInputs width fields [])
    };
    GraphInput graph index -> do {
      node <- W.lookupGraphNode graph index;
      case node of {
        W.GInt number -> Right (ViewInt number);
        W.GBits bits -> Right (ViewBits bits);
        W.GText text -> Right (ViewText text);
        W.GNode tag fields -> S.mapEither (ViewNode tag) (graphInputs width graph fields [])
      }
    }
  };
  takeDecoded :: Int -> [] Decoded -> [] Decoded ->
    Either String ((,) ([] Decoded) ([] Decoded));
  takeDecoded count values acc = if count == 0 then Right ((,) acc values)
    else case values of {
      [] -> Left "binary typed decoder result stack underflow";
      (:) value rest -> takeDecoded (count - 1) rest ((:) value acc)
    };
  decodeValue :: DecodeShape -> W.Value -> Either String Decoded;
  decodeValue shape value = decodeInput shape (ValueInput value);
  decodeGraphValue :: DecodeShape -> W.Graph -> Int -> Either String Decoded;
  decodeGraphValue shape graph index = decodeInput shape (GraphInput graph index);
  decodeInput :: DecodeShape -> DecodeInput -> Either String Decoded;
  decodeInput shape input = do {
    results <- decodeTasks (W.maxExpandedWork W.defaultLimits)
      [DecodeOne shape input] [] M.empty;
    case results of {
      [result] -> Right result;
      _ -> Left "binary typed decoder result stack mismatch"
    }
  };
  decodeTasks :: Int -> [] DecodeTask -> [] Decoded ->
    Map ((,) DecodeShape Int) Decoded -> Either String ([] Decoded);
  decodeTasks remaining tasks values memo = case tasks of {
    [] -> Right values;
    (:) task rest -> case task of {
      DecodeOne shape input ->
        if remaining <= 0 then Left "binary typed expanded-work limit exceeded"
        else let { next = remaining - 1 } in case input of {
          ValueInput _ -> do {
            view <- inspectInput shape next input;
            decodeOne next shape view rest values memo
          };
          GraphInput _ index -> case M.lookup compareDecodeKey ((,) shape index) memo of {
            Just result -> decodeTasks next rest ((:) result values) memo;
            Nothing -> do {
              view <- inspectInput shape next input;
              decodeOne next shape view ((:) (DecodeRemember shape index) rest) values memo
            }
          }
        };
      DecodeFields fields -> case fields of {
        [] -> decodeTasks remaining rest values memo;
        (:) ((,) shape input) more -> decodeTasks remaining
          ((:) (DecodeOne shape input) ((:) (DecodeFields more) rest)) values memo
      };
      DecodeRepeated shape fields -> case fields of {
        [] -> decodeTasks remaining rest values memo;
        (:) input more -> decodeTasks remaining
          ((:) (DecodeOne shape input) ((:) (DecodeRepeated shape more) rest)) values memo
      };
      DecodeClose tag count -> do {
        split <- takeDecoded count values [];
        case split of { (,) children previous -> do {
          result <- assembleDecoded tag children;
          decodeTasks remaining rest ((:) result previous) memo
        } }
      };
      DecodeRemember shape index -> case values of {
        [] -> Left "binary typed decoder memo stack underflow";
        (:) result _ -> let { nextMemo = M.insert compareDecodeKey ((,) shape index) result memo } in
          seq nextMemo (decodeTasks remaining rest values nextMemo)
      }
    }
  };
  scheduleFields :: Int -> Int -> [] ((,) DecodeShape DecodeInput) ->
    [] DecodeTask -> [] Decoded -> Map ((,) DecodeShape Int) Decoded ->
    Either String ([] Decoded);
  scheduleFields remaining tag fields rest values memo =
    decodeTasks remaining
      ((:) (DecodeFields fields) ((:) (DecodeClose tag (S.length fields)) rest)) values memo;
  expectInt :: Decoded -> Either String Int;
  expectInt value = case value of {
    DecodedInt result -> Right result;
    _ -> malformed "typed Int result"
  };
  fromGraphInt :: W.Graph -> Int -> Either String Int;
  fromGraphInt graph index = S.bindEither (decodeGraphValue ShapeInt graph index) expectInt;
  expectText :: Decoded -> Either String String;
  expectText value = case value of {
    DecodedText result -> Right result;
    _ -> malformed "typed Text result"
  };
  fromGraphText :: W.Graph -> Int -> Either String String;
  fromGraphText graph index = S.bindEither (decodeGraphValue ShapeText graph index) expectText;
  expectDouble :: Decoded -> Either String Double;
  expectDouble value = case value of {
    DecodedDouble result -> Right result;
    _ -> malformed "typed Double result"
  };
  fromGraphDouble :: W.Graph -> Int -> Either String Double;
  fromGraphDouble graph index = S.bindEither (decodeGraphValue ShapeDouble graph index) expectDouble;
  expectBool :: Decoded -> Either String Bool;
  expectBool value = case value of {
    DecodedBool result -> Right result;
    _ -> malformed "typed Bool result"
  };
  fromGraphBool :: W.Graph -> Int -> Either String Bool;
  fromGraphBool graph index = S.bindEither (decodeGraphValue ShapeBool graph index) expectBool;
  expectKind :: Decoded -> Either String Kind;
  expectKind value = case value of {
    DecodedKind result -> Right result;
    _ -> malformed "typed Kind result"
  };
  fromGraphKind :: W.Graph -> Int -> Either String Kind;
  fromGraphKind graph index = S.bindEither (decodeGraphValue ShapeKind graph index) expectKind;
  expectFlag :: Decoded -> Either String Flag;
  expectFlag value = case value of {
    DecodedFlag result -> Right result;
    _ -> malformed "typed Flag result"
  };
  fromGraphFlag :: W.Graph -> Int -> Either String Flag;
  fromGraphFlag graph index = S.bindEither (decodeGraphValue ShapeFlag graph index) expectFlag;
  expectField :: Decoded -> Either String Field;
  expectField value = case value of {
    DecodedField result -> Right result;
    _ -> malformed "typed Field result"
  };
  fromGraphField :: W.Graph -> Int -> Either String Field;
  fromGraphField graph index = S.bindEither (decodeGraphValue ShapeField graph index) expectField;
  expectConstructorDecl :: Decoded -> Either String ConstructorDecl;
  expectConstructorDecl value = case value of {
    DecodedConstructorDecl result -> Right result;
    _ -> malformed "typed ConstructorDecl result"
  };
  fromGraphConstructorDecl :: W.Graph -> Int -> Either String ConstructorDecl;
  fromGraphConstructorDecl graph index = S.bindEither (decodeGraphValue ShapeConstructorDecl graph index) expectConstructorDecl;
  expectDataDecl :: Decoded -> Either String DataDecl;
  expectDataDecl value = case value of {
    DecodedDataDecl result -> Right result;
    _ -> malformed "typed DataDecl result"
  };
  fromGraphDataDecl :: W.Graph -> Int -> Either String DataDecl;
  fromGraphDataDecl graph index = S.bindEither (decodeGraphValue ShapeDataDecl graph index) expectDataDecl;
  expectXTyVar :: Decoded -> Either String XTyVar;
  expectXTyVar value = case value of {
    DecodedXTyVar result -> Right result;
    _ -> malformed "typed XTyVar result"
  };
  fromGraphXTyVar :: W.Graph -> Int -> Either String XTyVar;
  fromGraphXTyVar graph index = S.bindEither (decodeGraphValue ShapeXTyVar graph index) expectXTyVar;
  expectXName :: Decoded -> Either String XName;
  expectXName value = case value of {
    DecodedXName result -> Right result;
    _ -> malformed "typed XName result"
  };
  fromGraphXName :: W.Graph -> Int -> Either String XName;
  fromGraphXName graph index = S.bindEither (decodeGraphValue ShapeXName graph index) expectXName;
  expectXType :: Decoded -> Either String XType;
  expectXType value = case value of {
    DecodedXType result -> Right result;
    _ -> malformed "typed XType result"
  };
  fromGraphXType :: W.Graph -> Int -> Either String XType;
  fromGraphXType graph index = S.bindEither (decodeGraphValue ShapeXType graph index) expectXType;
  expectXComputation :: Decoded -> Either String XComputation;
  expectXComputation value = case value of {
    DecodedXComputation result -> Right result;
    _ -> malformed "typed XComputation result"
  };
  fromGraphXComputation :: W.Graph -> Int -> Either String XComputation;
  fromGraphXComputation graph index = S.bindEither (decodeGraphValue ShapeXComputation graph index) expectXComputation;
  expectXTerm :: Decoded -> Either String XTerm;
  expectXTerm value = case value of {
    DecodedXTerm result -> Right result;
    _ -> malformed "typed XTerm result"
  };
  fromGraphXTerm :: W.Graph -> Int -> Either String XTerm;
  fromGraphXTerm graph index = S.bindEither (decodeGraphValue ShapeXTerm graph index) expectXTerm;
  expectXPattern :: Decoded -> Either String XPattern;
  expectXPattern value = case value of {
    DecodedXPattern result -> Right result;
    _ -> malformed "typed XPattern result"
  };
  fromGraphXPattern :: W.Graph -> Int -> Either String XPattern;
  fromGraphXPattern graph index = S.bindEither (decodeGraphValue ShapeXPattern graph index) expectXPattern;
  expectXAlternative :: Decoded -> Either String XAlternative;
  expectXAlternative value = case value of {
    DecodedXAlternative result -> Right result;
    _ -> malformed "typed XAlternative result"
  };
  fromGraphXAlternative :: W.Graph -> Int -> Either String XAlternative;
  fromGraphXAlternative graph index = S.bindEither (decodeGraphValue ShapeXAlternative graph index) expectXAlternative;
  expectSType :: Decoded -> Either String SType;
  expectSType value = case value of {
    DecodedSType result -> Right result;
    _ -> malformed "typed SType result"
  };
  fromGraphSType :: W.Graph -> Int -> Either String SType;
  fromGraphSType graph index = S.bindEither (decodeGraphValue ShapeSType graph index) expectSType;
  expectSAnnotation :: Decoded -> Either String SAnnotation;
  expectSAnnotation value = case value of {
    DecodedSAnnotation result -> Right result;
    _ -> malformed "typed SAnnotation result"
  };
  fromGraphSAnnotation :: W.Graph -> Int -> Either String SAnnotation;
  fromGraphSAnnotation graph index = S.bindEither (decodeGraphValue ShapeSAnnotation graph index) expectSAnnotation;
  expectRecursiveMode :: Decoded -> Either String RecursiveMode;
  expectRecursiveMode value = case value of {
    DecodedRecursiveMode result -> Right result;
    _ -> malformed "typed RecursiveMode result"
  };
  fromGraphRecursiveMode :: W.Graph -> Int -> Either String RecursiveMode;
  fromGraphRecursiveMode graph index = S.bindEither (decodeGraphValue ShapeRecursiveMode graph index) expectRecursiveMode;
  expectSourceSpan :: Decoded -> Either String SourceSpan;
  expectSourceSpan value = case value of {
    DecodedSourceSpan result -> Right result;
    _ -> malformed "typed SourceSpan result"
  };
  fromGraphSourceSpan :: W.Graph -> Int -> Either String SourceSpan;
  fromGraphSourceSpan graph index = S.bindEither (decodeGraphValue ShapeSourceSpan graph index) expectSourceSpan;
  expectSourceString :: Decoded -> Either String SourceString;
  expectSourceString value = case value of {
    DecodedSourceString result -> Right result;
    _ -> malformed "typed SourceString result"
  };
  fromGraphSourceString :: W.Graph -> Int -> Either String SourceString;
  fromGraphSourceString graph index = S.bindEither (decodeGraphValue ShapeSourceString graph index) expectSourceString;
  expectEvidenceRole :: Decoded -> Either String EvidenceRole;
  expectEvidenceRole value = case value of {
    DecodedEvidenceRole result -> Right result;
    _ -> malformed "typed EvidenceRole result"
  };
  fromGraphEvidenceRole :: W.Graph -> Int -> Either String EvidenceRole;
  fromGraphEvidenceRole graph index = S.bindEither (decodeGraphValue ShapeEvidenceRole graph index) expectEvidenceRole;
  expectSExpr :: Decoded -> Either String SExpr;
  expectSExpr value = case value of {
    DecodedSExpr result -> Right result;
    _ -> malformed "typed SExpr result"
  };
  fromGraphSExpr :: W.Graph -> Int -> Either String SExpr;
  fromGraphSExpr graph index = S.bindEither (decodeGraphValue ShapeSExpr graph index) expectSExpr;
  expectSPattern :: Decoded -> Either String SPattern;
  expectSPattern value = case value of {
    DecodedSPattern result -> Right result;
    _ -> malformed "typed SPattern result"
  };
  fromGraphSPattern :: W.Graph -> Int -> Either String SPattern;
  fromGraphSPattern graph index = S.bindEither (decodeGraphValue ShapeSPattern graph index) expectSPattern;
  expectSAlternative :: Decoded -> Either String SAlternative;
  expectSAlternative value = case value of {
    DecodedSAlternative result -> Right result;
    _ -> malformed "typed SAlternative result"
  };
  fromGraphSAlternative :: W.Graph -> Int -> Either String SAlternative;
  fromGraphSAlternative graph index = S.bindEither (decodeGraphValue ShapeSAlternative graph index) expectSAlternative;
  expectSStatement :: Decoded -> Either String SStatement;
  expectSStatement value = case value of {
    DecodedSStatement result -> Right result;
    _ -> malformed "typed SStatement result"
  };
  fromGraphSStatement :: W.Graph -> Int -> Either String SStatement;
  fromGraphSStatement graph index = S.bindEither (decodeGraphValue ShapeSStatement graph index) expectSStatement;
  expectSPredicate :: Decoded -> Either String SPredicate;
  expectSPredicate value = case value of {
    DecodedSPredicate result -> Right result;
    _ -> malformed "typed SPredicate result"
  };
  fromGraphSPredicate :: W.Graph -> Int -> Either String SPredicate;
  fromGraphSPredicate graph index = S.bindEither (decodeGraphValue ShapeSPredicate graph index) expectSPredicate;
  expectSClassDecl :: Decoded -> Either String SClassDecl;
  expectSClassDecl value = case value of {
    DecodedSClassDecl result -> Right result;
    _ -> malformed "typed SClassDecl result"
  };
  fromGraphSClassDecl :: W.Graph -> Int -> Either String SClassDecl;
  fromGraphSClassDecl graph index = S.bindEither (decodeGraphValue ShapeSClassDecl graph index) expectSClassDecl;
  expectSInstanceDecl :: Decoded -> Either String SInstanceDecl;
  expectSInstanceDecl value = case value of {
    DecodedSInstanceDecl result -> Right result;
    _ -> malformed "typed SInstanceDecl result"
  };
  fromGraphSInstanceDecl :: W.Graph -> Int -> Either String SInstanceDecl;
  fromGraphSInstanceDecl graph index = S.bindEither (decodeGraphValue ShapeSInstanceDecl graph index) expectSInstanceDecl;
  expectRole :: Decoded -> Either String Modules.Role;
  expectRole value = case value of {
    DecodedRole result -> Right result;
    _ -> malformed "typed Role result"
  };
  fromGraphRole :: W.Graph -> Int -> Either String Modules.Role;
  fromGraphRole graph index = S.bindEither (decodeGraphValue ShapeRole graph index) expectRole;
  expectEntity :: Decoded -> Either String Modules.Entity;
  expectEntity value = case value of {
    DecodedEntity result -> Right result;
    _ -> malformed "typed Entity result"
  };
  fromGraphEntity :: W.Graph -> Int -> Either String Modules.Entity;
  fromGraphEntity graph index = S.bindEither (decodeGraphValue ShapeEntity graph index) expectEntity;
  expectSourceSyntax :: Decoded -> Either String SourceSyntax;
  expectSourceSyntax value = case value of {
    DecodedSourceSyntax result -> Right result;
    _ -> malformed "typed SourceSyntax result"
  };
  fromGraphSourceSyntax :: W.Graph -> Int -> Either String SourceSyntax;
  fromGraphSourceSyntax graph index = S.bindEither (decodeGraphValue ShapeSourceSyntax graph index) expectSourceSyntax;
  expectSelection :: Decoded -> Either String Selection;
  expectSelection value = case value of {
    DecodedSelection result -> Right result;
    _ -> malformed "typed Selection result"
  };
  fromGraphSelection :: W.Graph -> Int -> Either String Selection;
  fromGraphSelection graph index = S.bindEither (decodeGraphValue ShapeSelection graph index) expectSelection;
  expectExport :: Decoded -> Either String Export;
  expectExport value = case value of {
    DecodedExport result -> Right result;
    _ -> malformed "typed Export result"
  };
  fromGraphExport :: W.Graph -> Int -> Either String Export;
  fromGraphExport graph index = S.bindEither (decodeGraphValue ShapeExport graph index) expectExport;
  expectMembers :: Decoded -> Either String Members;
  expectMembers value = case value of {
    DecodedMembers result -> Right result;
    _ -> malformed "typed Members result"
  };
  fromGraphMembers :: W.Graph -> Int -> Either String Members;
  fromGraphMembers graph index = S.bindEither (decodeGraphValue ShapeMembers graph index) expectMembers;
  expectImport :: Decoded -> Either String Import;
  expectImport value = case value of {
    DecodedImport result -> Right result;
    _ -> malformed "typed Import result"
  };
  fromGraphImport :: W.Graph -> Int -> Either String Import;
  fromGraphImport graph index = S.bindEither (decodeGraphValue ShapeImport graph index) expectImport;
  expectSourceModule :: Decoded -> Either String SourceModule;
  expectSourceModule value = case value of {
    DecodedSourceModule result -> Right result;
    _ -> malformed "typed SourceModule result"
  };
  fromGraphSourceModule :: W.Graph -> Int -> Either String SourceModule;
  fromGraphSourceModule graph index = S.bindEither (decodeGraphValue ShapeSourceModule graph index) expectSourceModule;
  expectSProgram :: Decoded -> Either String SProgram;
  expectSProgram value = case value of {
    DecodedSProgram result -> Right result;
    _ -> malformed "typed SProgram result"
  };
  fromGraphSProgram :: W.Graph -> Int -> Either String SProgram;
  fromGraphSProgram graph index = S.bindEither (decodeGraphValue ShapeSProgram graph index) expectSProgram;
  expectUnitInterface :: Decoded -> Either String Separate.UnitInterface;
  expectUnitInterface value = case value of {
    DecodedUnitInterface result -> Right result;
    _ -> malformed "typed UnitInterface result"
  };
  fromGraphUnitInterface :: W.Graph -> Int -> Either String Separate.UnitInterface;
  fromGraphUnitInterface graph index = S.bindEither (decodeGraphValue ShapeUnitInterface graph index) expectUnitInterface;
  expectCrateInterfaceFields :: Decoded -> Either String CrateInterfaceFields;
  expectCrateInterfaceFields value = case value of {
    DecodedCrateInterfaceFields result -> Right result;
    _ -> malformed "typed CrateInterfaceFields result"
  };
  fromGraphCrateInterfaceFields :: W.Graph -> Int -> Either String CrateInterfaceFields;
  fromGraphCrateInterfaceFields graph index = S.bindEither (decodeGraphValue ShapeCrateInterfaceFields graph index) expectCrateInterfaceFields;
  expectCrateObjectFields :: Decoded -> Either String CrateObjectFields;
  expectCrateObjectFields value = case value of {
    DecodedCrateObjectFields result -> Right result;
    _ -> malformed "typed CrateObjectFields result"
  };
  fromGraphCrateObjectFields :: W.Graph -> Int -> Either String CrateObjectFields;
  fromGraphCrateObjectFields graph index = S.bindEither (decodeGraphValue ShapeCrateObjectFields graph index) expectCrateObjectFields;
  expectPrimitive :: Decoded -> Either String Primitive;
  expectPrimitive value = case value of {
    DecodedPrimitive result -> Right result;
    _ -> malformed "typed Primitive result"
  };
  fromGraphPrimitive :: W.Graph -> Int -> Either String Primitive;
  fromGraphPrimitive graph index = S.bindEither (decodeGraphValue ShapePrimitive graph index) expectPrimitive;
  expectInterfaceInstance :: Decoded -> Either String SInstanceDecl;
  expectInterfaceInstance value = case value of {
    DecodedInterfaceInstance result -> Right result;
    _ -> malformed "typed InterfaceInstance result"
  };
  fromGraphInterfaceInstance :: W.Graph -> Int -> Either String SInstanceDecl;
  fromGraphInterfaceInstance graph index = S.bindEither (decodeGraphValue ShapeInterfaceInstance graph index) expectInterfaceInstance;
  expectRawUnitObject :: Decoded -> Either String Separate.UnitObject;
  expectRawUnitObject value = case value of {
    DecodedRawUnitObject result -> Right result;
    _ -> malformed "typed RawUnitObject result"
  };
  fromGraphRawUnitObject :: W.Graph -> Int -> Either String Separate.UnitObject;
  fromGraphRawUnitObject graph index = S.bindEither (decodeGraphValue ShapeRawUnitObject graph index) expectRawUnitObject;
  expectDataContext :: Decoded -> Either String ([] DataDecl);
  expectDataContext value = case value of {
    DecodedDataContext result -> Right result;
    _ -> malformed "typed DataContext result"
  };
  fromGraphDataContext :: W.Graph -> Int -> Either String ([] DataDecl);
  fromGraphDataContext graph index = S.bindEither (decodeGraphValue ShapeDataContext graph index) expectDataContext;
  expectList :: forall a. (Decoded -> Either String a) -> Decoded -> Either String ([] a);
  expectList decode value = case value of {
    DecodedList values -> expectListAt decode values [];
    _ -> malformed "typed list result"
  };
  expectListAt :: forall a. (Decoded -> Either String a) -> [] Decoded -> [] a -> Either String ([] a);
  expectListAt decode values acc = case values of {
    [] -> Right (S.reverse acc);
    (:) value rest -> do {
      result <- decode value;
      expectListAt decode rest ((:) result acc)
    }
  };
  expectMaybe :: forall a. (Decoded -> Either String a) -> Decoded -> Either String (Maybe a);
  expectMaybe decode value = case value of {
    DecodedNothing -> Right Nothing;
    DecodedJust item -> S.mapEither Just (decode item);
    _ -> malformed "typed Maybe result"
  };
  expectPair :: forall a b. (Decoded -> Either String a) ->
    (Decoded -> Either String b) -> Decoded -> Either String ((,) a b);
  expectPair decodeA decodeB value = case value of {
    DecodedPair a b -> do {
      resultA <- decodeA a;
      resultB <- decodeB b;
      Right ((,) resultA resultB)
    };
    _ -> malformed "typed pair result"
  };
  expectTriple :: forall a b c. (Decoded -> Either String a) ->
    (Decoded -> Either String b) -> (Decoded -> Either String c) ->
    Decoded -> Either String ((,,) a b c);
  expectTriple decodeA decodeB decodeC value = case value of {
    DecodedTriple a b c -> do {
      resultA <- decodeA a;
      resultB <- decodeB b;
      resultC <- decodeC c;
      Right ((,,) resultA resultB resultC)
    };
    _ -> malformed "typed triple result"
  };
  fromGraphTextList :: W.Graph -> Int -> Either String ([] String);
  fromGraphTextList graph index =
    S.bindEither (decodeGraphValue (ShapeList ShapeText) graph index) (expectList expectText);
  decodeOne :: Int -> DecodeShape -> DecodeView -> [] DecodeTask -> [] Decoded ->
    Map ((,) DecodeShape Int) Decoded -> Either String ([] Decoded);
  decodeOne remaining shape value rest values memo = case shape of {
    ShapeInt -> case value of {
      ViewInt number -> decodeTasks remaining rest ((:) (DecodedInt number) values) memo;
      _ -> malformed "Int"
    };
    ShapeText -> case value of {
      ViewText text -> decodeTasks remaining rest ((:) (DecodedText text) values) memo;
      _ -> malformed "String"
    };
    ShapeDouble -> case value of {
      ViewBits bits -> decodeTasks remaining rest ((:) (DecodedDouble (doubleFromBits bits)) values) memo;
      _ -> malformed "Float64"
    };
    ShapeBool -> case value of {
      ViewNode tag [] -> if tag == 6 then decodeTasks remaining rest ((:) (DecodedBool False) values) memo
        else if tag == 7 then decodeTasks remaining rest ((:) (DecodedBool True) values) memo
        else malformed "Bool tag";
      _ -> malformed "Bool"
    };
    ShapeList item -> case value of {
      ViewNode tag fields -> if tag == 1 then decodeTasks remaining
        ((:) (DecodeRepeated item fields) ((:) (DecodeClose 1 (S.length fields)) rest)) values memo
        else malformed "list tag";
      _ -> malformed "list"
    };
    ShapePair a b -> case value of {
      ViewNode tag [x, y] -> if tag == 2 then
        scheduleFields remaining 2 [(,) a x, (,) b y] rest values memo
        else malformed "pair tag";
      _ -> malformed "pair"
    };
    ShapeTriple a b c -> case value of {
      ViewNode tag [x, y, z] -> if tag == 3 then
        scheduleFields remaining 3 [(,) a x, (,) b y, (,) c z] rest values memo
        else malformed "triple tag";
      _ -> malformed "triple"
    };
    ShapeMaybe item -> case value of {
      ViewNode tag fields -> if tag == 4 then case fields of {
        [] -> decodeTasks remaining rest ((:) DecodedNothing values) memo;
        _ -> malformed "Nothing arity"
      } else if tag == 5 then case fields of {
        [x] -> scheduleFields remaining 5 [(,) item x] rest values memo;
        _ -> malformed "Just arity"
      } else malformed "Maybe tag";
      _ -> malformed "Maybe"
    };
    ShapeKind -> case value of {
      ViewNode tag fields ->
        if tag == 10 then case fields of {
          [] ->
            scheduleFields remaining 10 [] rest values memo;
          _ -> malformed "Star arity"
        }
        else if tag == 11 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 11 [(,) ShapeKind x0, (,) ShapeKind x1] rest values memo;
          _ -> malformed "KArrow arity"
        }
        else malformed "Kind tag";
      _ -> malformed "Kind"
    };
    ShapeFlag -> case value of {
      ViewNode tag fields ->
        if tag == 12 then case fields of {
          [] ->
            scheduleFields remaining 12 [] rest values memo;
          _ -> malformed "Flexible arity"
        }
        else if tag == 13 then case fields of {
          [] ->
            scheduleFields remaining 13 [] rest values memo;
          _ -> malformed "Rigid arity"
        }
        else malformed "Flag tag";
      _ -> malformed "Flag"
    };
    ShapeField -> case value of {
      ViewNode tag fields ->
        if tag == 20 then case fields of {
          [x0] ->
            scheduleFields remaining 20 [(,) ShapeText x0] rest values memo;
          _ -> malformed "Parameter arity"
        }
        else if tag == 21 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 21 [(,) ShapeField x0, (,) ShapeField x1] rest values memo;
          _ -> malformed "Function arity"
        }
        else if tag == 22 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 22 [(,) ShapeText x0, (,) (ShapeList ShapeField) x1] rest values memo;
          _ -> malformed "Applied arity"
        }
        else if tag == 23 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 23 [(,) ShapeField x0, (,) ShapeField x1] rest values memo;
          _ -> malformed "Application arity"
        }
        else if tag == 24 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 24 [(,) ShapeText x0, (,) ShapeKind x1, (,) ShapeField x2] rest values memo;
          _ -> malformed "Quantified arity"
        }
        else malformed "Field tag";
      _ -> malformed "Field"
    };
    ShapeConstructorDecl -> case value of {
      ViewNode tag fields ->
        if tag == 25 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 25 [(,) ShapeText x0, (,) (ShapeList ShapeField) x1] rest values memo;
          _ -> malformed "ConstructorDecl arity"
        }
        else malformed "ConstructorDecl tag";
      _ -> malformed "ConstructorDecl"
    };
    ShapeDataDecl -> case value of {
      ViewNode tag fields ->
        if tag == 26 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 26 [(,) ShapeText x0, (,) (ShapeList ShapeText) x1, (,) (ShapeList ShapeConstructorDecl) x2] rest values memo;
          _ -> malformed "DataDecl arity"
        }
        else if tag == 27 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 27 [(,) ShapeText x0, (,) (ShapeList (ShapePair ShapeText ShapeKind)) x1, (,) (ShapeList ShapeConstructorDecl) x2] rest values memo;
          _ -> malformed "DataDeclK arity"
        }
        else malformed "DataDecl tag";
      _ -> malformed "DataDecl"
    };
    ShapeXTyVar -> case value of {
      ViewNode tag fields ->
        if tag == 30 then case fields of {
          [x0] ->
            scheduleFields remaining 30 [(,) ShapeInt x0] rest values memo;
          _ -> malformed "XTyVar arity"
        }
        else malformed "XTyVar tag";
      _ -> malformed "XTyVar"
    };
    ShapeXName -> case value of {
      ViewNode tag fields ->
        if tag == 31 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 31 [(,) ShapeInt x0, (,) ShapeText x1] rest values memo;
          _ -> malformed "XName arity"
        }
        else malformed "XName tag";
      _ -> malformed "XName"
    };
    ShapeXType -> case value of {
      ViewNode tag fields ->
        if tag == 40 then case fields of {
          [x0] ->
            scheduleFields remaining 40 [(,) ShapeXTyVar x0] rest values memo;
          _ -> malformed "XVar arity"
        }
        else if tag == 41 then case fields of {
          [] ->
            scheduleFields remaining 41 [] rest values memo;
          _ -> malformed "XBot arity"
        }
        else if tag == 42 then case fields of {
          [x0] ->
            scheduleFields remaining 42 [(,) ShapeKind x0] rest values memo;
          _ -> malformed "XBotKind arity"
        }
        else if tag == 43 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 43 [(,) ShapeXType x0, (,) ShapeXType x1] rest values memo;
          _ -> malformed "XArrow arity"
        }
        else if tag == 44 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 44 [(,) ShapeText x0, (,) (ShapeList ShapeXType) x1] rest values memo;
          _ -> malformed "XCon arity"
        }
        else if tag == 45 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 45 [(,) ShapeXType x0, (,) ShapeXType x1] rest values memo;
          _ -> malformed "XApply arity"
        }
        else if tag == 46 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 46 [(,) ShapeXTyVar x0, (,) ShapeXType x1, (,) ShapeXType x2] rest values memo;
          _ -> malformed "XForall arity"
        }
        else malformed "XType tag";
      _ -> malformed "XType"
    };
    ShapeXComputation -> case value of {
      ViewNode tag fields ->
        if tag == 50 then case fields of {
          [] ->
            scheduleFields remaining 50 [] rest values memo;
          _ -> malformed "XRefl arity"
        }
        else if tag == 51 then case fields of {
          [x0] ->
            scheduleFields remaining 51 [(,) ShapeXType x0] rest values memo;
          _ -> malformed "XBottom arity"
        }
        else if tag == 52 then case fields of {
          [x0] ->
            scheduleFields remaining 52 [(,) ShapeXTyVar x0] rest values memo;
          _ -> malformed "XHyp arity"
        }
        else if tag == 53 then case fields of {
          [x0] ->
            scheduleFields remaining 53 [(,) ShapeXComputation x0] rest values memo;
          _ -> malformed "XInner arity"
        }
        else if tag == 54 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 54 [(,) ShapeXTyVar x0, (,) ShapeXComputation x1] rest values memo;
          _ -> malformed "XOuter arity"
        }
        else if tag == 55 then case fields of {
          [] ->
            scheduleFields remaining 55 [] rest values memo;
          _ -> malformed "XElim arity"
        }
        else if tag == 56 then case fields of {
          [x0] ->
            scheduleFields remaining 56 [(,) ShapeXTyVar x0] rest values memo;
          _ -> malformed "XIntro arity"
        }
        else if tag == 57 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 57 [(,) ShapeXTyVar x0, (,) ShapeKind x1] rest values memo;
          _ -> malformed "XIntroKind arity"
        }
        else if tag == 58 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 58 [(,) ShapeXComputation x0, (,) ShapeXComputation x1] rest values memo;
          _ -> malformed "XThen arity"
        }
        else malformed "XComputation tag";
      _ -> malformed "XComputation"
    };
    ShapeXTerm -> case value of {
      ViewNode tag fields ->
        if tag == 70 then case fields of {
          [x0] ->
            scheduleFields remaining 70 [(,) ShapeXName x0] rest values memo;
          _ -> malformed "XVarTerm arity"
        }
        else if tag == 71 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 71 [(,) ShapeXName x0, (,) ShapeXType x1, (,) ShapeXTerm x2] rest values memo;
          _ -> malformed "XAbs arity"
        }
        else if tag == 72 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 72 [(,) ShapeXTerm x0, (,) ShapeXTerm x1] rest values memo;
          _ -> malformed "XApp arity"
        }
        else if tag == 73 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 73 [(,) ShapeXTyVar x0, (,) ShapeXType x1, (,) ShapeXTerm x2] rest values memo;
          _ -> malformed "XTypeAbs arity"
        }
        else if tag == 74 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 74 [(,) ShapeXTerm x0, (,) ShapeXComputation x1] rest values memo;
          _ -> malformed "XTypeApp arity"
        }
        else if tag == 75 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 75 [(,) ShapeXName x0, (,) ShapeXTerm x1, (,) ShapeXTerm x2] rest values memo;
          _ -> malformed "XLet arity"
        }
        else if tag == 76 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 76 [(,) (ShapeList (ShapeTriple ShapeXName ShapeXType ShapeXTerm)) x0, (,) ShapeXTerm x1] rest values memo;
          _ -> malformed "XLetRec arity"
        }
        else if tag == 77 then case fields of {
          [x0] ->
            scheduleFields remaining 77 [(,) ShapeInt x0] rest values memo;
          _ -> malformed "XIntTerm arity"
        }
        else if tag == 78 then case fields of {
          [x0] ->
            scheduleFields remaining 78 [(,) ShapeDouble x0] rest values memo;
          _ -> malformed "XDoubleTerm arity"
        }
        else if tag == 79 then case fields of {
          [x0] ->
            scheduleFields remaining 79 [(,) ShapeBool x0] rest values memo;
          _ -> malformed "XBoolTerm arity"
        }
        else if tag == 80 then case fields of {
          [x0] ->
            scheduleFields remaining 80 [(,) ShapeText x0] rest values memo;
          _ -> malformed "XStringTerm arity"
        }
        else if tag == 81 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 81 [(,) ShapePrimitive x0, (,) (ShapeList ShapeXType) x1] rest values memo;
          _ -> malformed "XPrimitive arity"
        }
        else if tag == 82 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 82 [(,) ShapeText x0, (,) (ShapeList ShapeXType) x1] rest values memo;
          _ -> malformed "XConstructor arity"
        }
        else if tag == 83 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 83 [(,) ShapeXTerm x0, (,) ShapeXType x1, (,) (ShapeList ShapeXAlternative) x2] rest values memo;
          _ -> malformed "XCase arity"
        }
        else if tag == 84 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 84 [(,) (ShapeList ShapeDataDecl) x0, (,) ShapeXTerm x1] rest values memo;
          _ -> malformed "XWithData arity"
        }
        else malformed "XTerm tag";
      _ -> malformed "XTerm"
    };
    ShapeXPattern -> case value of {
      ViewNode tag fields ->
        if tag == 90 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 90 [(,) ShapeText x0, (,) (ShapeList (ShapeMaybe ShapeXName)) x1] rest values memo;
          _ -> malformed "XConstructorPattern arity"
        }
        else if tag == 91 then case fields of {
          [x0] ->
            scheduleFields remaining 91 [(,) (ShapeMaybe ShapeXName) x0] rest values memo;
          _ -> malformed "XDefaultPattern arity"
        }
        else malformed "XPattern tag";
      _ -> malformed "XPattern"
    };
    ShapeXAlternative -> case value of {
      ViewNode tag fields ->
        if tag == 92 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 92 [(,) ShapeXPattern x0, (,) ShapeXTerm x1] rest values memo;
          _ -> malformed "XAlternative arity"
        }
        else malformed "XAlternative tag";
      _ -> malformed "XAlternative"
    };
    ShapeSType -> case value of {
      ViewNode tag fields ->
        if tag == 100 then case fields of {
          [x0] ->
            scheduleFields remaining 100 [(,) ShapeText x0] rest values memo;
          _ -> malformed "STVar arity"
        }
        else if tag == 101 then case fields of {
          [] ->
            scheduleFields remaining 101 [] rest values memo;
          _ -> malformed "SBottom arity"
        }
        else if tag == 102 then case fields of {
          [x0] ->
            scheduleFields remaining 102 [(,) ShapeKind x0] rest values memo;
          _ -> malformed "SBottomKind arity"
        }
        else if tag == 103 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 103 [(,) ShapeSType x0, (,) ShapeSType x1] rest values memo;
          _ -> malformed "SArrow arity"
        }
        else if tag == 104 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 104 [(,) ShapeText x0, (,) (ShapeList ShapeSType) x1] rest values memo;
          _ -> malformed "SCon arity"
        }
        else if tag == 105 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 105 [(,) ShapeSType x0, (,) ShapeSType x1] rest values memo;
          _ -> malformed "STypeApp arity"
        }
        else if tag == 106 then case fields of {
          [x0, x1, x2, x3] ->
            scheduleFields remaining 106 [(,) ShapeFlag x0, (,) ShapeText x1, (,) ShapeSType x2, (,) ShapeSType x3] rest values memo;
          _ -> malformed "SForall arity"
        }
        else if tag == 107 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 107 [(,) (ShapeList ShapeSPredicate) x0, (,) ShapeSType x1] rest values memo;
          _ -> malformed "SQualified arity"
        }
        else malformed "SType tag";
      _ -> malformed "SType"
    };
    ShapeSAnnotation -> case value of {
      ViewNode tag fields ->
        if tag == 110 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 110 [(,) (ShapeList ShapeText) x0, (,) ShapeSType x1] rest values memo;
          _ -> malformed "SAnnotation arity"
        }
        else malformed "SAnnotation tag";
      _ -> malformed "SAnnotation"
    };
    ShapeRecursiveMode -> case value of {
      ViewNode tag fields ->
        if tag == 111 then case fields of {
          [] ->
            scheduleFields remaining 111 [] rest values memo;
          _ -> malformed "InferRecursive arity"
        }
        else if tag == 112 then case fields of {
          [x0] ->
            scheduleFields remaining 112 [(,) ShapeSAnnotation x0] rest values memo;
          _ -> malformed "CheckRecursive arity"
        }
        else malformed "RecursiveMode tag";
      _ -> malformed "RecursiveMode"
    };
    ShapeSourceSpan -> case value of {
      ViewNode tag fields ->
        if tag == 113 then case fields of {
          [x0, x1, x2, x3, x4, x5, x6] ->
            scheduleFields remaining 113 [(,) ShapeText x0, (,) ShapeText x1, (,) ShapeText x2, (,) ShapeInt x3, (,) ShapeInt x4, (,) ShapeInt x5, (,) ShapeInt x6] rest values memo;
          _ -> malformed "SourceSpan arity"
        }
        else malformed "SourceSpan tag";
      _ -> malformed "SourceSpan"
    };
    ShapeSourceString -> case value of {
      ViewNode tag fields ->
        if tag == 114 then case fields of {
          [x0] ->
            scheduleFields remaining 114 [(,) ShapeText x0] rest values memo;
          _ -> malformed "ScalarString arity"
        }
        else if tag == 115 then case fields of {
          [x0] ->
            scheduleFields remaining 115 [(,) (ShapeList ShapeInt) x0] rest values memo;
          _ -> malformed "CharString arity"
        }
        else malformed "SourceString tag";
      _ -> malformed "SourceString"
    };
    ShapeEvidenceRole -> case value of {
      ViewNode tag fields ->
        if tag == 116 then case fields of {
          [] ->
            scheduleFields remaining 116 [] rest values memo;
          _ -> malformed "GivenEvidence arity"
        }
        else if tag == 117 then case fields of {
          [] ->
            scheduleFields remaining 117 [] rest values memo;
          _ -> malformed "SuperclassEvidence arity"
        }
        else if tag == 118 then case fields of {
          [] ->
            scheduleFields remaining 118 [] rest values memo;
          _ -> malformed "InstanceEvidence arity"
        }
        else malformed "EvidenceRole tag";
      _ -> malformed "EvidenceRole"
    };
    ShapeSExpr -> case value of {
      ViewNode tag fields ->
        if tag == 120 then case fields of {
          [x0] ->
            scheduleFields remaining 120 [(,) ShapeText x0] rest values memo;
          _ -> malformed "SVar arity"
        }
        else if tag == 121 then case fields of {
          [x0] ->
            scheduleFields remaining 121 [(,) ShapeText x0] rest values memo;
          _ -> malformed "SConstructor arity"
        }
        else if tag == 122 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 122 [(,) ShapeText x0, (,) (ShapeMaybe ShapeSAnnotation) x1, (,) ShapeSExpr x2] rest values memo;
          _ -> malformed "SLam arity"
        }
        else if tag == 123 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 123 [(,) ShapeSExpr x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SApp arity"
        }
        else if tag == 124 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 124 [(,) ShapeText x0, (,) ShapeSExpr x1, (,) ShapeSExpr x2] rest values memo;
          _ -> malformed "SLet arity"
        }
        else if tag == 125 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 125 [(,) ShapeSExpr x0, (,) ShapeSAnnotation x1] rest values memo;
          _ -> malformed "SAnn arity"
        }
        else if tag == 126 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 126 [(,) ShapeSExpr x0, (,) ShapeSAnnotation x1] rest values memo;
          _ -> malformed "SSignature arity"
        }
        else if tag == 127 then case fields of {
          [x0] ->
            scheduleFields remaining 127 [(,) ShapeInt x0] rest values memo;
          _ -> malformed "SIntLit arity"
        }
        else if tag == 128 then case fields of {
          [x0] ->
            scheduleFields remaining 128 [(,) ShapeDouble x0] rest values memo;
          _ -> malformed "SDoubleLit arity"
        }
        else if tag == 129 then case fields of {
          [x0] ->
            scheduleFields remaining 129 [(,) ShapeBool x0] rest values memo;
          _ -> malformed "SBoolLit arity"
        }
        else if tag == 130 then case fields of {
          [x0] ->
            scheduleFields remaining 130 [(,) ShapeText x0] rest values memo;
          _ -> malformed "SStringLit arity"
        }
        else if tag == 131 then case fields of {
          [x0] ->
            scheduleFields remaining 131 [(,) ShapePrimitive x0] rest values memo;
          _ -> malformed "SPrimitive arity"
        }
        else if tag == 132 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 132 [(,) ShapeSExpr x0, (,) (ShapeList ShapeSAlternative) x1] rest values memo;
          _ -> malformed "SCase arity"
        }
        else if tag == 133 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 133 [(,) (ShapeList ShapeSStatement) x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SDo arity"
        }
        else if tag == 134 then case fields of {
          [x0] ->
            scheduleFields remaining 134 [(,) (ShapeList (ShapePair (ShapeList ShapeSPattern) ShapeSExpr)) x0] rest values memo;
          _ -> malformed "SEquations arity"
        }
        else if tag == 135 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 135 [(,) (ShapeList (ShapeTriple ShapeText ShapeRecursiveMode ShapeSExpr)) x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SLetRec arity"
        }
        else if tag == 136 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 136 [(,) ShapeText x0, (,) (ShapeList (ShapePair ShapeEvidenceRole ShapeText)) x1] rest values memo;
          _ -> malformed "SWanted arity"
        }
        else if tag == 137 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 137 [(,) ShapeSType x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SChecked arity"
        }
        else if tag == 138 then case fields of {
          [x0] ->
            scheduleFields remaining 138 [(,) ShapeSExpr x0] rest values memo;
          _ -> malformed "SSourceDefinition arity"
        }
        else if tag == 139 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 139 [(,) ShapeText x0, (,) ShapeSourceSpan x1, (,) ShapeSExpr x2] rest values memo;
          _ -> malformed "SCallSite arity"
        }
        else if tag == 140 then case fields of {
          [x0, x1, x2, x3, x4] ->
            scheduleFields remaining 140 [(,) ShapeSPattern x0, (,) ShapeSExpr x1, (,) ShapeSExpr x2, (,) ShapeSExpr x3, (,) ShapeSExpr x4] rest values memo;
          _ -> malformed "SSharedBind arity"
        }
        else malformed "SExpr tag";
      _ -> malformed "SExpr"
    };
    ShapeSPattern -> case value of {
      ViewNode tag fields ->
        if tag == 150 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 150 [(,) ShapeText x0, (,) (ShapeList (ShapeMaybe ShapeText)) x1] rest values memo;
          _ -> malformed "SConstructorPattern arity"
        }
        else if tag == 151 then case fields of {
          [x0] ->
            scheduleFields remaining 151 [(,) (ShapeMaybe ShapeText) x0] rest values memo;
          _ -> malformed "SDefaultPattern arity"
        }
        else if tag == 152 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 152 [(,) ShapeText x0, (,) (ShapeList ShapeSPattern) x1] rest values memo;
          _ -> malformed "SNestedPattern arity"
        }
        else if tag == 153 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 153 [(,) ShapeText x0, (,) ShapeSAnnotation x1] rest values memo;
          _ -> malformed "SAnnotatedPattern arity"
        }
        else if tag == 154 then case fields of {
          [x0] ->
            scheduleFields remaining 154 [(,) ShapeInt x0] rest values memo;
          _ -> malformed "SIntPattern arity"
        }
        else if tag == 155 then case fields of {
          [x0] ->
            scheduleFields remaining 155 [(,) ShapeText x0] rest values memo;
          _ -> malformed "SStringPattern arity"
        }
        else if tag == 156 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 156 [(,) ShapeSourceString x0, (,) ShapeText x1, (,) ShapeText x2] rest values memo;
          _ -> malformed "SOverloadedStringPattern arity"
        }
        else if tag == 157 then case fields of {
          [x0] ->
            scheduleFields remaining 157 [(,) ShapeBool x0] rest values memo;
          _ -> malformed "SBoolPattern arity"
        }
        else if tag == 158 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 158 [(,) ShapeText x0, (,) ShapeSPattern x1] rest values memo;
          _ -> malformed "SAsPattern arity"
        }
        else if tag == 159 then case fields of {
          [x0] ->
            scheduleFields remaining 159 [(,) ShapeSPattern x0] rest values memo;
          _ -> malformed "SLazyPattern arity"
        }
        else malformed "SPattern tag";
      _ -> malformed "SPattern"
    };
    ShapeSAlternative -> case value of {
      ViewNode tag fields ->
        if tag == 160 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 160 [(,) ShapeSPattern x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SAlternative arity"
        }
        else malformed "SAlternative tag";
      _ -> malformed "SAlternative"
    };
    ShapeSStatement -> case value of {
      ViewNode tag fields ->
        if tag == 161 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 161 [(,) ShapeSPattern x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SDoBind arity"
        }
        else if tag == 162 then case fields of {
          [x0] ->
            scheduleFields remaining 162 [(,) ShapeSExpr x0] rest values memo;
          _ -> malformed "SDoThen arity"
        }
        else if tag == 163 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 163 [(,) ShapeText x0, (,) (ShapeMaybe ShapeSAnnotation) x1, (,) ShapeSExpr x2] rest values memo;
          _ -> malformed "SDoLet arity"
        }
        else if tag == 164 then case fields of {
          [x0] ->
            scheduleFields remaining 164 [(,) (ShapeList (ShapeTriple ShapeText ShapeRecursiveMode ShapeSExpr)) x0] rest values memo;
          _ -> malformed "SDoLetRec arity"
        }
        else malformed "SStatement tag";
      _ -> malformed "SStatement"
    };
    ShapeSPredicate -> case value of {
      ViewNode tag fields ->
        if tag == 170 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 170 [(,) ShapeText x0, (,) (ShapeList ShapeSType) x1] rest values memo;
          _ -> malformed "SPredicate arity"
        }
        else malformed "SPredicate tag";
      _ -> malformed "SPredicate"
    };
    ShapeSClassDecl -> case value of {
      ViewNode tag fields ->
        if tag == 171 then case fields of {
          [x0, x1, x2, x3] ->
            scheduleFields remaining 171 [(,) ShapeText x0, (,) (ShapeList (ShapePair ShapeText ShapeKind)) x1, (,) (ShapeList ShapeSPredicate) x2, (,) (ShapeList (ShapePair ShapeText ShapeSType)) x3] rest values memo;
          _ -> malformed "SClassDecl arity"
        }
        else malformed "SClassDecl tag";
      _ -> malformed "SClassDecl"
    };
    ShapeSInstanceDecl -> case value of {
      ViewNode tag fields ->
        if tag == 172 then case fields of {
          [x0, x1, x2, x3, x4] ->
            scheduleFields remaining 172 [(,) (ShapeList (ShapePair ShapeText ShapeKind)) x0, (,) (ShapeList ShapeSPredicate) x1, (,) ShapeText x2, (,) (ShapeList ShapeSType) x3, (,) (ShapeList (ShapePair ShapeText ShapeSExpr)) x4] rest values memo;
          _ -> malformed "SInstanceDecl arity"
        }
        else malformed "SInstanceDecl tag";
      _ -> malformed "SInstanceDecl"
    };
    ShapeRole -> case value of {
      ViewNode tag fields ->
        if tag == 180 then case fields of {
          [] ->
            scheduleFields remaining 180 [] rest values memo;
          _ -> malformed "Modules.Value arity"
        }
        else if tag == 181 then case fields of {
          [] ->
            scheduleFields remaining 181 [] rest values memo;
          _ -> malformed "Modules.Datatype arity"
        }
        else if tag == 182 then case fields of {
          [] ->
            scheduleFields remaining 182 [] rest values memo;
          _ -> malformed "Modules.Class arity"
        }
        else if tag == 183 then case fields of {
          [x0] ->
            scheduleFields remaining 183 [(,) ShapeText x0] rest values memo;
          _ -> malformed "Modules.Constructor arity"
        }
        else if tag == 184 then case fields of {
          [x0] ->
            scheduleFields remaining 184 [(,) ShapeText x0] rest values memo;
          _ -> malformed "Modules.Method arity"
        }
        else if tag == 185 then case fields of {
          [] ->
            scheduleFields remaining 185 [] rest values memo;
          _ -> malformed "Modules.BuiltinType arity"
        }
        else if tag == 186 then case fields of {
          [x0] ->
            scheduleFields remaining 186 [(,) ShapePrimitive x0] rest values memo;
          _ -> malformed "Modules.Primitive arity"
        }
        else if tag == 187 then case fields of {
          [x0] ->
            scheduleFields remaining 187 [(,) ShapeBool x0] rest values memo;
          _ -> malformed "Modules.Boolean arity"
        }
        else if tag == 188 then case fields of {
          [] ->
            scheduleFields remaining 188 [] rest values memo;
          _ -> malformed "Modules.ManagedConstraint arity"
        }
        else malformed "Role tag";
      _ -> malformed "Role"
    };
    ShapeEntity -> case value of {
      ViewNode tag fields ->
        if tag == 189 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 189 [(,) ShapeText x0, (,) ShapeText x1, (,) ShapeRole x2] rest values memo;
          _ -> malformed "Modules.Entity arity"
        }
        else malformed "Entity tag";
      _ -> malformed "Entity"
    };
    ShapeSourceSyntax -> case value of {
      ViewNode tag fields ->
        if tag == 200 then case fields of {
          [] ->
            scheduleFields remaining 200 [] rest values memo;
          _ -> malformed "LegacyEmlfV1 arity"
        }
        else if tag == 201 then case fields of {
          [] ->
            scheduleFields remaining 201 [] rest values memo;
          _ -> malformed "SharedHaskellV1 arity"
        }
        else if tag == 202 then case fields of {
          [] ->
            scheduleFields remaining 202 [] rest values memo;
          _ -> malformed "MetadataSyntax arity"
        }
        else malformed "SourceSyntax tag";
      _ -> malformed "SourceSyntax"
    };
    ShapeSelection -> case value of {
      ViewNode tag fields ->
        if tag == 203 then case fields of {
          [] ->
            scheduleFields remaining 203 [] rest values memo;
          _ -> malformed "Everything arity"
        }
        else if tag == 204 then case fields of {
          [x0] ->
            scheduleFields remaining 204 [(,) (ShapeList ShapeExport) x0] rest values memo;
          _ -> malformed "Only arity"
        }
        else if tag == 205 then case fields of {
          [x0] ->
            scheduleFields remaining 205 [(,) (ShapeList ShapeExport) x0] rest values memo;
          _ -> malformed "Hiding arity"
        }
        else malformed "Selection tag";
      _ -> malformed "Selection"
    };
    ShapeExport -> case value of {
      ViewNode tag fields ->
        if tag == 206 then case fields of {
          [x0] ->
            scheduleFields remaining 206 [(,) ShapeText x0] rest values memo;
          _ -> malformed "ExportValue arity"
        }
        else if tag == 207 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 207 [(,) ShapeText x0, (,) ShapeMembers x1] rest values memo;
          _ -> malformed "ExportType arity"
        }
        else if tag == 208 then case fields of {
          [x0] ->
            scheduleFields remaining 208 [(,) ShapeText x0] rest values memo;
          _ -> malformed "ExportModule arity"
        }
        else malformed "Export tag";
      _ -> malformed "Export"
    };
    ShapeMembers -> case value of {
      ViewNode tag fields ->
        if tag == 209 then case fields of {
          [] ->
            scheduleFields remaining 209 [] rest values memo;
          _ -> malformed "Abstract arity"
        }
        else if tag == 210 then case fields of {
          [] ->
            scheduleFields remaining 210 [] rest values memo;
          _ -> malformed "AllMembers arity"
        }
        else if tag == 211 then case fields of {
          [x0] ->
            scheduleFields remaining 211 [(,) (ShapeList ShapeText) x0] rest values memo;
          _ -> malformed "Members arity"
        }
        else malformed "Members tag";
      _ -> malformed "Members"
    };
    ShapeImport -> case value of {
      ViewNode tag fields ->
        if tag == 212 then case fields of {
          [x0, x1, x2, x3] ->
            scheduleFields remaining 212 [(,) ShapeText x0, (,) ShapeBool x1, (,) (ShapeMaybe ShapeText) x2, (,) ShapeSelection x3] rest values memo;
          _ -> malformed "Import arity"
        }
        else malformed "Import tag";
      _ -> malformed "Import"
    };
    ShapeSourceModule -> case value of {
      ViewNode tag fields ->
        if tag == 213 then case fields of {
          [x0, x1, x2, x3, x4, x5, x6, x7, x8, x9] ->
            scheduleFields remaining 213 [(,) ShapeText x0, (,) (ShapeMaybe ShapeText) x1, (,) (ShapeMaybe (ShapeList ShapeExport)) x2, (,) (ShapeList ShapeImport) x3, (,) (ShapeList ShapeDataDecl) x4, (,) (ShapeList ShapeSClassDecl) x5, (,) (ShapeList ShapeSInstanceDecl) x6, (,) (ShapeList (ShapeTriple ShapeText (ShapeMaybe ShapeSAnnotation) ShapeSExpr)) x7, (,) (ShapeMaybe ShapeSExpr) x8, (,) ShapeSourceSyntax x9] rest values memo;
          _ -> malformed "SourceModule arity"
        }
        else malformed "SourceModule tag";
      _ -> malformed "SourceModule"
    };
    ShapeSProgram -> case value of {
      ViewNode tag fields ->
        if tag == 214 then case fields of {
          [x0, x1] ->
            scheduleFields remaining 214 [(,) (ShapeList ShapeDataDecl) x0, (,) ShapeSExpr x1] rest values memo;
          _ -> malformed "SProgram arity"
        }
        else if tag == 215 then case fields of {
          [x0, x1, x2, x3] ->
            scheduleFields remaining 215 [(,) (ShapeList ShapeDataDecl) x0, (,) (ShapeList ShapeSClassDecl) x1, (,) (ShapeList ShapeSInstanceDecl) x2, (,) ShapeSExpr x3] rest values memo;
          _ -> malformed "SClassProgram arity"
        }
        else malformed "SProgram tag";
      _ -> malformed "SProgram"
    };
    ShapeUnitInterface -> case value of {
      ViewNode tag fields ->
        if tag == 240 then case fields of {
          [x0, x1, x2, x3, x4, x5, x6, x7] ->
            scheduleFields remaining 240 [(,) ShapeText x0, (,) (ShapeList (ShapePair ShapeText ShapeText)) x1, (,) (ShapeList ShapeEntity) x2, (,) (ShapeList ShapeDataDecl) x3, (,) (ShapeList ShapeSClassDecl) x4, (,) (ShapeList (ShapePair ShapeText ShapeInterfaceInstance)) x5, (,) (ShapeList (ShapePair ShapeText ShapeXType)) x6, (,) ShapeText x7] rest values memo;
          _ -> malformed "Separate.UnitInterface arity"
        }
        else malformed "UnitInterface tag";
      _ -> malformed "UnitInterface"
    };
    ShapeCrateInterfaceFields -> case value of {
      ViewNode tag fields ->
        if tag == 242 then case fields of {
          [x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12] ->
            scheduleFields remaining 242 [(,) ShapeText x0, (,) (ShapeList (ShapeTriple ShapeText ShapeText ShapeText)) x1, (,) (ShapeList ShapeText) x2, (,) (ShapeList (ShapePair ShapeText (ShapeList ShapeEntity))) x3, (,) (ShapeList (ShapePair ShapeText (ShapeList ShapeText))) x4, (,) (ShapeList ShapeDataDecl) x5, (,) (ShapeList ShapeSClassDecl) x6, (,) (ShapeList (ShapePair ShapeText ShapeInterfaceInstance)) x7, (,) (ShapeList ShapeDataDecl) x8, (,) (ShapeList (ShapePair ShapeText ShapeXType)) x9, (,) ShapeText x10, (,) ShapeText x11, (,) (ShapeList (ShapePair ShapeText ShapeBool)) x12] rest values memo;
          _ -> malformed "CrateInterfaceFields arity"
        }
        else malformed "CrateInterfaceFields tag";
      _ -> malformed "CrateInterfaceFields"
    };
    ShapeCrateObjectFields -> case value of {
      ViewNode tag fields ->
        if tag == 243 then case fields of {
          [x0, x1, x2] ->
            scheduleFields remaining 243 [(,) ShapeBool x0, (,) ShapeCrateInterfaceFields x1, (,) (ShapeList ShapeRawUnitObject) x2] rest values memo;
          _ -> malformed "CrateObjectFields arity"
        }
        else malformed "CrateObjectFields tag";
      _ -> malformed "CrateObjectFields"
    };
    ShapePrimitive -> case value of {
      ViewNode tag [x0] -> if tag == 32 then
        scheduleFields remaining 32 [(,) ShapeInt x0] rest values memo
        else malformed "primitive tag";
      _ -> malformed "primitive"
    };
    ShapeInterfaceInstance -> case value of {
      ViewNode tag [x0, x1, x2, x3, x4] -> if tag == 173 then
        scheduleFields remaining 173 [(,) (ShapeList (ShapePair ShapeText ShapeKind)) x0, (,) (ShapeList ShapeSPredicate) x1, (,) ShapeText x2, (,) (ShapeList ShapeSType) x3, (,) (ShapeList ShapeText) x4] rest values memo
        else malformed "interface instance tag";
      _ -> malformed "interface instance"
    };
    ShapeRawUnitObject -> case value of {
      ViewNode tag [x0, x1] -> if tag == 241 then
        scheduleFields remaining 241 [(,) ShapeUnitInterface x0, (,) ShapeXTerm x1] rest values memo
        else malformed "raw unit object tag";
      _ -> malformed "raw unit object"
    };
    ShapeDataContext -> case value of {
      ViewNode tag [x0] -> if tag == 244 then
        scheduleFields remaining 244 [(,) (ShapeList ShapeDataDecl) x0] rest values memo
        else malformed "datatype context tag";
      _ -> malformed "datatype context"
    }
  };
  assembleDecoded :: Int -> [] Decoded -> Either String Decoded;
  assembleDecoded tag fields =
    if tag == 1 then Right (DecodedList fields)
    else if tag == 2 then case fields of {
      [a, b] -> Right (DecodedPair a b);
      _ -> malformed "typed pair assembly"
    }
    else if tag == 3 then case fields of {
      [a, b, c] -> Right (DecodedTriple a b c);
      _ -> malformed "typed triple assembly"
    }
    else if tag == 5 then case fields of {
      [a] -> Right (DecodedJust a);
      _ -> malformed "typed Just assembly"
    }
    else if tag == 10 then case fields of {
      [] -> Right (DecodedKind Star);
      _ -> malformed "typed Star assembly"
    }
    else if tag == 11 then case fields of {
      [x0, x1] -> do {
        y0 <- expectKind x0;
        y1 <- expectKind x1;
        Right (DecodedKind (KArrow y0 y1))
      };
      _ -> malformed "typed KArrow assembly"
    }
    else if tag == 12 then case fields of {
      [] -> Right (DecodedFlag Flexible);
      _ -> malformed "typed Flexible assembly"
    }
    else if tag == 13 then case fields of {
      [] -> Right (DecodedFlag Rigid);
      _ -> malformed "typed Rigid assembly"
    }
    else if tag == 20 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedField (Parameter y0))
      };
      _ -> malformed "typed Parameter assembly"
    }
    else if tag == 21 then case fields of {
      [x0, x1] -> do {
        y0 <- expectField x0;
        y1 <- expectField x1;
        Right (DecodedField (Function y0 y1))
      };
      _ -> malformed "typed Function assembly"
    }
    else if tag == 22 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectField) x1;
        Right (DecodedField (Applied y0 y1))
      };
      _ -> malformed "typed Applied assembly"
    }
    else if tag == 23 then case fields of {
      [x0, x1] -> do {
        y0 <- expectField x0;
        y1 <- expectField x1;
        Right (DecodedField (Application y0 y1))
      };
      _ -> malformed "typed Application assembly"
    }
    else if tag == 24 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- expectKind x1;
        y2 <- expectField x2;
        Right (DecodedField (Quantified y0 y1 y2))
      };
      _ -> malformed "typed Quantified assembly"
    }
    else if tag == 25 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectField) x1;
        Right (DecodedConstructorDecl (ConstructorDecl y0 y1))
      };
      _ -> malformed "typed ConstructorDecl assembly"
    }
    else if tag == 26 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectText) x1;
        y2 <- (expectList expectConstructorDecl) x2;
        Right (DecodedDataDecl (DataDecl y0 y1 y2))
      };
      _ -> malformed "typed DataDecl assembly"
    }
    else if tag == 27 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectPair expectText expectKind)) x1;
        y2 <- (expectList expectConstructorDecl) x2;
        Right (DecodedDataDecl (DataDeclK y0 y1 y2))
      };
      _ -> malformed "typed DataDeclK assembly"
    }
    else if tag == 30 then case fields of {
      [x0] -> do {
        y0 <- expectInt x0;
        Right (DecodedXTyVar (XTyVar y0))
      };
      _ -> malformed "typed XTyVar assembly"
    }
    else if tag == 31 then case fields of {
      [x0, x1] -> do {
        y0 <- expectInt x0;
        y1 <- expectText x1;
        Right (DecodedXName (XName y0 y1))
      };
      _ -> malformed "typed XName assembly"
    }
    else if tag == 40 then case fields of {
      [x0] -> do {
        y0 <- expectXTyVar x0;
        Right (DecodedXType (XVar y0))
      };
      _ -> malformed "typed XVar assembly"
    }
    else if tag == 41 then case fields of {
      [] -> Right (DecodedXType XBot);
      _ -> malformed "typed XBot assembly"
    }
    else if tag == 42 then case fields of {
      [x0] -> do {
        y0 <- expectKind x0;
        Right (DecodedXType (XBotKind y0))
      };
      _ -> malformed "typed XBotKind assembly"
    }
    else if tag == 43 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXType x0;
        y1 <- expectXType x1;
        Right (DecodedXType (XArrow y0 y1))
      };
      _ -> malformed "typed XArrow assembly"
    }
    else if tag == 44 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectXType) x1;
        Right (DecodedXType (XCon y0 y1))
      };
      _ -> malformed "typed XCon assembly"
    }
    else if tag == 45 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXType x0;
        y1 <- expectXType x1;
        Right (DecodedXType (XApply y0 y1))
      };
      _ -> malformed "typed XApply assembly"
    }
    else if tag == 46 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectXTyVar x0;
        y1 <- expectXType x1;
        y2 <- expectXType x2;
        Right (DecodedXType (XForall y0 y1 y2))
      };
      _ -> malformed "typed XForall assembly"
    }
    else if tag == 50 then case fields of {
      [] -> Right (DecodedXComputation XRefl);
      _ -> malformed "typed XRefl assembly"
    }
    else if tag == 51 then case fields of {
      [x0] -> do {
        y0 <- expectXType x0;
        Right (DecodedXComputation (XBottom y0))
      };
      _ -> malformed "typed XBottom assembly"
    }
    else if tag == 52 then case fields of {
      [x0] -> do {
        y0 <- expectXTyVar x0;
        Right (DecodedXComputation (XHyp y0))
      };
      _ -> malformed "typed XHyp assembly"
    }
    else if tag == 53 then case fields of {
      [x0] -> do {
        y0 <- expectXComputation x0;
        Right (DecodedXComputation (XInner y0))
      };
      _ -> malformed "typed XInner assembly"
    }
    else if tag == 54 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXTyVar x0;
        y1 <- expectXComputation x1;
        Right (DecodedXComputation (XOuter y0 y1))
      };
      _ -> malformed "typed XOuter assembly"
    }
    else if tag == 55 then case fields of {
      [] -> Right (DecodedXComputation XElim);
      _ -> malformed "typed XElim assembly"
    }
    else if tag == 56 then case fields of {
      [x0] -> do {
        y0 <- expectXTyVar x0;
        Right (DecodedXComputation (XIntro y0))
      };
      _ -> malformed "typed XIntro assembly"
    }
    else if tag == 57 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXTyVar x0;
        y1 <- expectKind x1;
        Right (DecodedXComputation (XIntroKind y0 y1))
      };
      _ -> malformed "typed XIntroKind assembly"
    }
    else if tag == 58 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXComputation x0;
        y1 <- expectXComputation x1;
        Right (DecodedXComputation (XThen y0 y1))
      };
      _ -> malformed "typed XThen assembly"
    }
    else if tag == 70 then case fields of {
      [x0] -> do {
        y0 <- expectXName x0;
        Right (DecodedXTerm (XVarTerm y0))
      };
      _ -> malformed "typed XVarTerm assembly"
    }
    else if tag == 71 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectXName x0;
        y1 <- expectXType x1;
        y2 <- expectXTerm x2;
        Right (DecodedXTerm (XAbs y0 y1 y2))
      };
      _ -> malformed "typed XAbs assembly"
    }
    else if tag == 72 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXTerm x0;
        y1 <- expectXTerm x1;
        Right (DecodedXTerm (XApp y0 y1))
      };
      _ -> malformed "typed XApp assembly"
    }
    else if tag == 73 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectXTyVar x0;
        y1 <- expectXType x1;
        y2 <- expectXTerm x2;
        Right (DecodedXTerm (XTypeAbs y0 y1 y2))
      };
      _ -> malformed "typed XTypeAbs assembly"
    }
    else if tag == 74 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXTerm x0;
        y1 <- expectXComputation x1;
        Right (DecodedXTerm (XTypeApp y0 y1))
      };
      _ -> malformed "typed XTypeApp assembly"
    }
    else if tag == 75 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectXName x0;
        y1 <- expectXTerm x1;
        y2 <- expectXTerm x2;
        Right (DecodedXTerm (XLet y0 y1 y2))
      };
      _ -> malformed "typed XLet assembly"
    }
    else if tag == 76 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList (expectTriple expectXName expectXType expectXTerm)) x0;
        y1 <- expectXTerm x1;
        Right (DecodedXTerm (XLetRec y0 y1))
      };
      _ -> malformed "typed XLetRec assembly"
    }
    else if tag == 77 then case fields of {
      [x0] -> do {
        y0 <- expectInt x0;
        Right (DecodedXTerm (XIntTerm y0))
      };
      _ -> malformed "typed XIntTerm assembly"
    }
    else if tag == 78 then case fields of {
      [x0] -> do {
        y0 <- expectDouble x0;
        Right (DecodedXTerm (XDoubleTerm y0))
      };
      _ -> malformed "typed XDoubleTerm assembly"
    }
    else if tag == 79 then case fields of {
      [x0] -> do {
        y0 <- expectBool x0;
        Right (DecodedXTerm (XBoolTerm y0))
      };
      _ -> malformed "typed XBoolTerm assembly"
    }
    else if tag == 80 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedXTerm (XStringTerm y0))
      };
      _ -> malformed "typed XStringTerm assembly"
    }
    else if tag == 81 then case fields of {
      [x0, x1] -> do {
        y0 <- expectPrimitive x0;
        y1 <- (expectList expectXType) x1;
        Right (DecodedXTerm (XPrimitive y0 y1))
      };
      _ -> malformed "typed XPrimitive assembly"
    }
    else if tag == 82 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectXType) x1;
        Right (DecodedXTerm (XConstructor y0 y1))
      };
      _ -> malformed "typed XConstructor assembly"
    }
    else if tag == 83 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectXTerm x0;
        y1 <- expectXType x1;
        y2 <- (expectList expectXAlternative) x2;
        Right (DecodedXTerm (XCase y0 y1 y2))
      };
      _ -> malformed "typed XCase assembly"
    }
    else if tag == 84 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList expectDataDecl) x0;
        y1 <- expectXTerm x1;
        Right (DecodedXTerm (XWithData y0 y1))
      };
      _ -> malformed "typed XWithData assembly"
    }
    else if tag == 90 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectMaybe expectXName)) x1;
        Right (DecodedXPattern (XConstructorPattern y0 y1))
      };
      _ -> malformed "typed XConstructorPattern assembly"
    }
    else if tag == 91 then case fields of {
      [x0] -> do {
        y0 <- (expectMaybe expectXName) x0;
        Right (DecodedXPattern (XDefaultPattern y0))
      };
      _ -> malformed "typed XDefaultPattern assembly"
    }
    else if tag == 92 then case fields of {
      [x0, x1] -> do {
        y0 <- expectXPattern x0;
        y1 <- expectXTerm x1;
        Right (DecodedXAlternative (XAlternative y0 y1))
      };
      _ -> malformed "typed XAlternative assembly"
    }
    else if tag == 100 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSType (STVar y0))
      };
      _ -> malformed "typed STVar assembly"
    }
    else if tag == 101 then case fields of {
      [] -> Right (DecodedSType SBottom);
      _ -> malformed "typed SBottom assembly"
    }
    else if tag == 102 then case fields of {
      [x0] -> do {
        y0 <- expectKind x0;
        Right (DecodedSType (SBottomKind y0))
      };
      _ -> malformed "typed SBottomKind assembly"
    }
    else if tag == 103 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSType x0;
        y1 <- expectSType x1;
        Right (DecodedSType (SArrow y0 y1))
      };
      _ -> malformed "typed SArrow assembly"
    }
    else if tag == 104 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectSType) x1;
        Right (DecodedSType (SCon y0 y1))
      };
      _ -> malformed "typed SCon assembly"
    }
    else if tag == 105 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSType x0;
        y1 <- expectSType x1;
        Right (DecodedSType (STypeApp y0 y1))
      };
      _ -> malformed "typed STypeApp assembly"
    }
    else if tag == 106 then case fields of {
      [x0, x1, x2, x3] -> do {
        y0 <- expectFlag x0;
        y1 <- expectText x1;
        y2 <- expectSType x2;
        y3 <- expectSType x3;
        Right (DecodedSType (SForall y0 y1 y2 y3))
      };
      _ -> malformed "typed SForall assembly"
    }
    else if tag == 107 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList expectSPredicate) x0;
        y1 <- expectSType x1;
        Right (DecodedSType (SQualified y0 y1))
      };
      _ -> malformed "typed SQualified assembly"
    }
    else if tag == 110 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList expectText) x0;
        y1 <- expectSType x1;
        Right (DecodedSAnnotation (SAnnotation y0 y1))
      };
      _ -> malformed "typed SAnnotation assembly"
    }
    else if tag == 111 then case fields of {
      [] -> Right (DecodedRecursiveMode InferRecursive);
      _ -> malformed "typed InferRecursive assembly"
    }
    else if tag == 112 then case fields of {
      [x0] -> do {
        y0 <- expectSAnnotation x0;
        Right (DecodedRecursiveMode (CheckRecursive y0))
      };
      _ -> malformed "typed CheckRecursive assembly"
    }
    else if tag == 113 then case fields of {
      [x0, x1, x2, x3, x4, x5, x6] -> do {
        y0 <- expectText x0;
        y1 <- expectText x1;
        y2 <- expectText x2;
        y3 <- expectInt x3;
        y4 <- expectInt x4;
        y5 <- expectInt x5;
        y6 <- expectInt x6;
        Right (DecodedSourceSpan (SourceSpan y0 y1 y2 y3 y4 y5 y6))
      };
      _ -> malformed "typed SourceSpan assembly"
    }
    else if tag == 114 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSourceString (ScalarString y0))
      };
      _ -> malformed "typed ScalarString assembly"
    }
    else if tag == 115 then case fields of {
      [x0] -> do {
        y0 <- (expectList expectInt) x0;
        Right (DecodedSourceString (CharString y0))
      };
      _ -> malformed "typed CharString assembly"
    }
    else if tag == 116 then case fields of {
      [] -> Right (DecodedEvidenceRole GivenEvidence);
      _ -> malformed "typed GivenEvidence assembly"
    }
    else if tag == 117 then case fields of {
      [] -> Right (DecodedEvidenceRole SuperclassEvidence);
      _ -> malformed "typed SuperclassEvidence assembly"
    }
    else if tag == 118 then case fields of {
      [] -> Right (DecodedEvidenceRole InstanceEvidence);
      _ -> malformed "typed InstanceEvidence assembly"
    }
    else if tag == 120 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSExpr (SVar y0))
      };
      _ -> malformed "typed SVar assembly"
    }
    else if tag == 121 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSExpr (SConstructor y0))
      };
      _ -> malformed "typed SConstructor assembly"
    }
    else if tag == 122 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- (expectMaybe expectSAnnotation) x1;
        y2 <- expectSExpr x2;
        Right (DecodedSExpr (SLam y0 y1 y2))
      };
      _ -> malformed "typed SLam assembly"
    }
    else if tag == 123 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSExpr x0;
        y1 <- expectSExpr x1;
        Right (DecodedSExpr (SApp y0 y1))
      };
      _ -> malformed "typed SApp assembly"
    }
    else if tag == 124 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- expectSExpr x1;
        y2 <- expectSExpr x2;
        Right (DecodedSExpr (SLet y0 y1 y2))
      };
      _ -> malformed "typed SLet assembly"
    }
    else if tag == 125 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSExpr x0;
        y1 <- expectSAnnotation x1;
        Right (DecodedSExpr (SAnn y0 y1))
      };
      _ -> malformed "typed SAnn assembly"
    }
    else if tag == 126 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSExpr x0;
        y1 <- expectSAnnotation x1;
        Right (DecodedSExpr (SSignature y0 y1))
      };
      _ -> malformed "typed SSignature assembly"
    }
    else if tag == 127 then case fields of {
      [x0] -> do {
        y0 <- expectInt x0;
        Right (DecodedSExpr (SIntLit y0))
      };
      _ -> malformed "typed SIntLit assembly"
    }
    else if tag == 128 then case fields of {
      [x0] -> do {
        y0 <- expectDouble x0;
        Right (DecodedSExpr (SDoubleLit y0))
      };
      _ -> malformed "typed SDoubleLit assembly"
    }
    else if tag == 129 then case fields of {
      [x0] -> do {
        y0 <- expectBool x0;
        Right (DecodedSExpr (SBoolLit y0))
      };
      _ -> malformed "typed SBoolLit assembly"
    }
    else if tag == 130 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSExpr (SStringLit y0))
      };
      _ -> malformed "typed SStringLit assembly"
    }
    else if tag == 131 then case fields of {
      [x0] -> do {
        y0 <- expectPrimitive x0;
        Right (DecodedSExpr (SPrimitive y0))
      };
      _ -> malformed "typed SPrimitive assembly"
    }
    else if tag == 132 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSExpr x0;
        y1 <- (expectList expectSAlternative) x1;
        Right (DecodedSExpr (SCase y0 y1))
      };
      _ -> malformed "typed SCase assembly"
    }
    else if tag == 133 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList expectSStatement) x0;
        y1 <- expectSExpr x1;
        Right (DecodedSExpr (SDo y0 y1))
      };
      _ -> malformed "typed SDo assembly"
    }
    else if tag == 134 then case fields of {
      [x0] -> do {
        y0 <- (expectList (expectPair (expectList expectSPattern) expectSExpr)) x0;
        Right (DecodedSExpr (SEquations y0))
      };
      _ -> malformed "typed SEquations assembly"
    }
    else if tag == 135 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList (expectTriple expectText expectRecursiveMode expectSExpr)) x0;
        y1 <- expectSExpr x1;
        Right (DecodedSExpr (SLetRec y0 y1))
      };
      _ -> malformed "typed SLetRec assembly"
    }
    else if tag == 136 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectPair expectEvidenceRole expectText)) x1;
        Right (DecodedSExpr (SWanted y0 y1))
      };
      _ -> malformed "typed SWanted assembly"
    }
    else if tag == 137 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSType x0;
        y1 <- expectSExpr x1;
        Right (DecodedSExpr (SChecked y0 y1))
      };
      _ -> malformed "typed SChecked assembly"
    }
    else if tag == 138 then case fields of {
      [x0] -> do {
        y0 <- expectSExpr x0;
        Right (DecodedSExpr (SSourceDefinition y0))
      };
      _ -> malformed "typed SSourceDefinition assembly"
    }
    else if tag == 139 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- expectSourceSpan x1;
        y2 <- expectSExpr x2;
        Right (DecodedSExpr (SCallSite y0 y1 y2))
      };
      _ -> malformed "typed SCallSite assembly"
    }
    else if tag == 140 then case fields of {
      [x0, x1, x2, x3, x4] -> do {
        y0 <- expectSPattern x0;
        y1 <- expectSExpr x1;
        y2 <- expectSExpr x2;
        y3 <- expectSExpr x3;
        y4 <- expectSExpr x4;
        Right (DecodedSExpr (SSharedBind y0 y1 y2 y3 y4))
      };
      _ -> malformed "typed SSharedBind assembly"
    }
    else if tag == 150 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectMaybe expectText)) x1;
        Right (DecodedSPattern (SConstructorPattern y0 y1))
      };
      _ -> malformed "typed SConstructorPattern assembly"
    }
    else if tag == 151 then case fields of {
      [x0] -> do {
        y0 <- (expectMaybe expectText) x0;
        Right (DecodedSPattern (SDefaultPattern y0))
      };
      _ -> malformed "typed SDefaultPattern assembly"
    }
    else if tag == 152 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectSPattern) x1;
        Right (DecodedSPattern (SNestedPattern y0 y1))
      };
      _ -> malformed "typed SNestedPattern assembly"
    }
    else if tag == 153 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- expectSAnnotation x1;
        Right (DecodedSPattern (SAnnotatedPattern y0 y1))
      };
      _ -> malformed "typed SAnnotatedPattern assembly"
    }
    else if tag == 154 then case fields of {
      [x0] -> do {
        y0 <- expectInt x0;
        Right (DecodedSPattern (SIntPattern y0))
      };
      _ -> malformed "typed SIntPattern assembly"
    }
    else if tag == 155 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedSPattern (SStringPattern y0))
      };
      _ -> malformed "typed SStringPattern assembly"
    }
    else if tag == 156 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectSourceString x0;
        y1 <- expectText x1;
        y2 <- expectText x2;
        Right (DecodedSPattern (SOverloadedStringPattern y0 y1 y2))
      };
      _ -> malformed "typed SOverloadedStringPattern assembly"
    }
    else if tag == 157 then case fields of {
      [x0] -> do {
        y0 <- expectBool x0;
        Right (DecodedSPattern (SBoolPattern y0))
      };
      _ -> malformed "typed SBoolPattern assembly"
    }
    else if tag == 158 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- expectSPattern x1;
        Right (DecodedSPattern (SAsPattern y0 y1))
      };
      _ -> malformed "typed SAsPattern assembly"
    }
    else if tag == 159 then case fields of {
      [x0] -> do {
        y0 <- expectSPattern x0;
        Right (DecodedSPattern (SLazyPattern y0))
      };
      _ -> malformed "typed SLazyPattern assembly"
    }
    else if tag == 160 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSPattern x0;
        y1 <- expectSExpr x1;
        Right (DecodedSAlternative (SAlternative y0 y1))
      };
      _ -> malformed "typed SAlternative assembly"
    }
    else if tag == 161 then case fields of {
      [x0, x1] -> do {
        y0 <- expectSPattern x0;
        y1 <- expectSExpr x1;
        Right (DecodedSStatement (SDoBind y0 y1))
      };
      _ -> malformed "typed SDoBind assembly"
    }
    else if tag == 162 then case fields of {
      [x0] -> do {
        y0 <- expectSExpr x0;
        Right (DecodedSStatement (SDoThen y0))
      };
      _ -> malformed "typed SDoThen assembly"
    }
    else if tag == 163 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- (expectMaybe expectSAnnotation) x1;
        y2 <- expectSExpr x2;
        Right (DecodedSStatement (SDoLet y0 y1 y2))
      };
      _ -> malformed "typed SDoLet assembly"
    }
    else if tag == 164 then case fields of {
      [x0] -> do {
        y0 <- (expectList (expectTriple expectText expectRecursiveMode expectSExpr)) x0;
        Right (DecodedSStatement (SDoLetRec y0))
      };
      _ -> malformed "typed SDoLetRec assembly"
    }
    else if tag == 170 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- (expectList expectSType) x1;
        Right (DecodedSPredicate (SPredicate y0 y1))
      };
      _ -> malformed "typed SPredicate assembly"
    }
    else if tag == 171 then case fields of {
      [x0, x1, x2, x3] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectPair expectText expectKind)) x1;
        y2 <- (expectList expectSPredicate) x2;
        y3 <- (expectList (expectPair expectText expectSType)) x3;
        Right (DecodedSClassDecl (SClassDecl y0 y1 y2 y3))
      };
      _ -> malformed "typed SClassDecl assembly"
    }
    else if tag == 172 then case fields of {
      [x0, x1, x2, x3, x4] -> do {
        y0 <- (expectList (expectPair expectText expectKind)) x0;
        y1 <- (expectList expectSPredicate) x1;
        y2 <- expectText x2;
        y3 <- (expectList expectSType) x3;
        y4 <- (expectList (expectPair expectText expectSExpr)) x4;
        Right (DecodedSInstanceDecl (SInstanceDecl y0 y1 y2 y3 y4))
      };
      _ -> malformed "typed SInstanceDecl assembly"
    }
    else if tag == 180 then case fields of {
      [] -> Right (DecodedRole Modules.Value);
      _ -> malformed "typed Modules.Value assembly"
    }
    else if tag == 181 then case fields of {
      [] -> Right (DecodedRole Modules.Datatype);
      _ -> malformed "typed Modules.Datatype assembly"
    }
    else if tag == 182 then case fields of {
      [] -> Right (DecodedRole Modules.Class);
      _ -> malformed "typed Modules.Class assembly"
    }
    else if tag == 183 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedRole (Modules.Constructor y0))
      };
      _ -> malformed "typed Modules.Constructor assembly"
    }
    else if tag == 184 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedRole (Modules.Method y0))
      };
      _ -> malformed "typed Modules.Method assembly"
    }
    else if tag == 185 then case fields of {
      [] -> Right (DecodedRole Modules.BuiltinType);
      _ -> malformed "typed Modules.BuiltinType assembly"
    }
    else if tag == 186 then case fields of {
      [x0] -> do {
        y0 <- expectPrimitive x0;
        Right (DecodedRole (Modules.Primitive y0))
      };
      _ -> malformed "typed Modules.Primitive assembly"
    }
    else if tag == 187 then case fields of {
      [x0] -> do {
        y0 <- expectBool x0;
        Right (DecodedRole (Modules.Boolean y0))
      };
      _ -> malformed "typed Modules.Boolean assembly"
    }
    else if tag == 188 then case fields of {
      [] -> Right (DecodedRole Modules.ManagedConstraint);
      _ -> malformed "typed Modules.ManagedConstraint assembly"
    }
    else if tag == 189 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectText x0;
        y1 <- expectText x1;
        y2 <- expectRole x2;
        Right (DecodedEntity (Modules.Entity y0 y1 y2))
      };
      _ -> malformed "typed Modules.Entity assembly"
    }
    else if tag == 200 then case fields of {
      [] -> Right (DecodedSourceSyntax LegacyEmlfV1);
      _ -> malformed "typed LegacyEmlfV1 assembly"
    }
    else if tag == 201 then case fields of {
      [] -> Right (DecodedSourceSyntax SharedHaskellV1);
      _ -> malformed "typed SharedHaskellV1 assembly"
    }
    else if tag == 202 then case fields of {
      [] -> Right (DecodedSourceSyntax MetadataSyntax);
      _ -> malformed "typed MetadataSyntax assembly"
    }
    else if tag == 203 then case fields of {
      [] -> Right (DecodedSelection Everything);
      _ -> malformed "typed Everything assembly"
    }
    else if tag == 204 then case fields of {
      [x0] -> do {
        y0 <- (expectList expectExport) x0;
        Right (DecodedSelection (Only y0))
      };
      _ -> malformed "typed Only assembly"
    }
    else if tag == 205 then case fields of {
      [x0] -> do {
        y0 <- (expectList expectExport) x0;
        Right (DecodedSelection (Hiding y0))
      };
      _ -> malformed "typed Hiding assembly"
    }
    else if tag == 206 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedExport (ExportValue y0))
      };
      _ -> malformed "typed ExportValue assembly"
    }
    else if tag == 207 then case fields of {
      [x0, x1] -> do {
        y0 <- expectText x0;
        y1 <- expectMembers x1;
        Right (DecodedExport (ExportType y0 y1))
      };
      _ -> malformed "typed ExportType assembly"
    }
    else if tag == 208 then case fields of {
      [x0] -> do {
        y0 <- expectText x0;
        Right (DecodedExport (ExportModule y0))
      };
      _ -> malformed "typed ExportModule assembly"
    }
    else if tag == 209 then case fields of {
      [] -> Right (DecodedMembers Abstract);
      _ -> malformed "typed Abstract assembly"
    }
    else if tag == 210 then case fields of {
      [] -> Right (DecodedMembers AllMembers);
      _ -> malformed "typed AllMembers assembly"
    }
    else if tag == 211 then case fields of {
      [x0] -> do {
        y0 <- (expectList expectText) x0;
        Right (DecodedMembers (Members y0))
      };
      _ -> malformed "typed Members assembly"
    }
    else if tag == 212 then case fields of {
      [x0, x1, x2, x3] -> do {
        y0 <- expectText x0;
        y1 <- expectBool x1;
        y2 <- (expectMaybe expectText) x2;
        y3 <- expectSelection x3;
        Right (DecodedImport (Import y0 y1 y2 y3))
      };
      _ -> malformed "typed Import assembly"
    }
    else if tag == 213 then case fields of {
      [x0, x1, x2, x3, x4, x5, x6, x7, x8, x9] -> do {
        y0 <- expectText x0;
        y1 <- (expectMaybe expectText) x1;
        y2 <- (expectMaybe (expectList expectExport)) x2;
        y3 <- (expectList expectImport) x3;
        y4 <- (expectList expectDataDecl) x4;
        y5 <- (expectList expectSClassDecl) x5;
        y6 <- (expectList expectSInstanceDecl) x6;
        y7 <- (expectList (expectTriple expectText (expectMaybe expectSAnnotation) expectSExpr)) x7;
        y8 <- (expectMaybe expectSExpr) x8;
        y9 <- expectSourceSyntax x9;
        Right (DecodedSourceModule (SourceModule y0 y1 y2 y3 y4 y5 y6 y7 y8 y9))
      };
      _ -> malformed "typed SourceModule assembly"
    }
    else if tag == 214 then case fields of {
      [x0, x1] -> do {
        y0 <- (expectList expectDataDecl) x0;
        y1 <- expectSExpr x1;
        Right (DecodedSProgram (SProgram y0 y1))
      };
      _ -> malformed "typed SProgram assembly"
    }
    else if tag == 215 then case fields of {
      [x0, x1, x2, x3] -> do {
        y0 <- (expectList expectDataDecl) x0;
        y1 <- (expectList expectSClassDecl) x1;
        y2 <- (expectList expectSInstanceDecl) x2;
        y3 <- expectSExpr x3;
        Right (DecodedSProgram (SClassProgram y0 y1 y2 y3))
      };
      _ -> malformed "typed SClassProgram assembly"
    }
    else if tag == 240 then case fields of {
      [x0, x1, x2, x3, x4, x5, x6, x7] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectPair expectText expectText)) x1;
        y2 <- (expectList expectEntity) x2;
        y3 <- (expectList expectDataDecl) x3;
        y4 <- (expectList expectSClassDecl) x4;
        y5 <- (expectList (expectPair expectText expectInterfaceInstance)) x5;
        y6 <- (expectList (expectPair expectText expectXType)) x6;
        y7 <- expectText x7;
        Right (DecodedUnitInterface (Separate.UnitInterface y0 y1 y2 y3 y4 y5 y6 y7))
      };
      _ -> malformed "typed Separate.UnitInterface assembly"
    }
    else if tag == 242 then case fields of {
      [x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12] -> do {
        y0 <- expectText x0;
        y1 <- (expectList (expectTriple expectText expectText expectText)) x1;
        y2 <- (expectList expectText) x2;
        y3 <- (expectList (expectPair expectText (expectList expectEntity))) x3;
        y4 <- (expectList (expectPair expectText (expectList expectText))) x4;
        y5 <- (expectList expectDataDecl) x5;
        y6 <- (expectList expectSClassDecl) x6;
        y7 <- (expectList (expectPair expectText expectInterfaceInstance)) x7;
        y8 <- (expectList expectDataDecl) x8;
        y9 <- (expectList (expectPair expectText expectXType)) x9;
        y10 <- expectText x10;
        y11 <- expectText x11;
        y12 <- (expectList (expectPair expectText expectBool)) x12;
        Right (DecodedCrateInterfaceFields (CrateInterfaceFields y0 y1 y2 y3 y4 y5 y6 y7 y8 y9 y10 y11 y12))
      };
      _ -> malformed "typed CrateInterfaceFields assembly"
    }
    else if tag == 243 then case fields of {
      [x0, x1, x2] -> do {
        y0 <- expectBool x0;
        y1 <- expectCrateInterfaceFields x1;
        y2 <- (expectList expectRawUnitObject) x2;
        Right (DecodedCrateObjectFields (CrateObjectFields y0 y1 y2))
      };
      _ -> malformed "typed CrateObjectFields assembly"
    }
    else if tag == 32 then case fields of {
      [x0] -> do {
        y0 <- expectInt x0;
        result <- primitiveFromCode y0;
        Right (DecodedPrimitive result)
      };
      _ -> malformed "typed Primitive assembly"
    }
    else if tag == 173 then case fields of {
      [x0, x1, x2, x3, x4] -> do {
        y0 <- (expectList (expectPair expectText expectKind)) x0;
        y1 <- (expectList expectSPredicate) x1;
        y2 <- expectText x2;
        y3 <- (expectList expectSType) x3;
        y4 <- (expectList expectText) x4;
        Right (DecodedInterfaceInstance (SInstanceDecl y0 y1 y2 y3 (interfaceMethods y4 [])))
      };
      _ -> malformed "typed InterfaceInstance assembly"
    }
    else if tag == 241 then case fields of {
      [x0, x1] -> do {
        y0 <- expectUnitInterface x0;
        y1 <- expectXTerm x1;
        Right (DecodedRawUnitObject (Separate.UnitObject y0 y1))
      };
      _ -> malformed "typed Separate.UnitObject assembly"
    }
    else if tag == 244 then case fields of {
      [x0] -> do {
        y0 <- (expectList expectDataDecl) x0;
        Right (DecodedDataContext (y0))
      };
      _ -> malformed "typed DataContext assembly"
    }
    else malformed "typed assembly tag";
  -- Exact body produced by Separate.stripInstance, without a non-tail map.
  interfaceMethods :: [] String -> [] ((,) String SExpr) -> [] ((,) String SExpr);
  interfaceMethods names acc = case names of {
    [] -> S.reverse acc;
    (:) name rest -> interfaceMethods rest
      ((:) ((,) name (SApp (SPrimitive PPanic) (SStringLit "interface method"))) acc)
  };

}
