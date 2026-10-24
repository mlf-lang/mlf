-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Types where {
  import MLF.Primitive;
  -- Shared data representations. This module is deliberately dependency-free.




  data Maybe a = Nothing | Just a;
  data Either e a = Left e | Right a;
  data Map k v = MapEmpty | MapNode Int k v (Map k v) (Map k v);
  data Set a = Set (Map a ());
  data IntMap a = IntMap (Map Int a);
  data IntSet = IntSet (Map Int ());
  data Kind = Star | KArrow Kind Kind;
  data Flag = Flexible | Rigid;
  data Field =
    Parameter String |
    Function Field Field |
    Applied String ([] Field) |
    Application Field Field |
    Quantified String Kind Field;
  data ConstructorDecl = ConstructorDecl String ([] Field);
  data DataDecl =
    DataDecl String ([] String) ([] ConstructorDecl) |
    DataDeclK String ([] ((,) String Kind)) ([] ConstructorDecl);
  data DataEnv =
    DataEnv (Map String DataDecl) (Map String ((,) DataDecl ConstructorDecl)) (Map String Kind);
  data Primitive =
    PIOReturn |
    PIOBind |
    PPutStr |
    PPutStrLn |
    PGetLine |
    PPrintInt |
    PConcatString |
    PShowInt |
    PAddInt |
    PSubInt |
    PEqInt |
    PLtInt |
    PEqString |
    PIfThenElse |
    PMulInt |
    PQuotInt |
    PRemInt |
    PReadInt |
    PAddDouble |
    PSubDouble |
    PMulDouble |
    PDivDouble |
    PSqrtDouble |
    PEqDouble |
    PLtDouble |
    PIntToDouble |
    PFormatDouble |
    PNewIntArray |
    PReadIntArray |
    PWriteIntArray |
    PLengthIntArray |
    PNewDoubleArray |
    PReadDoubleArray |
    PWriteDoubleArray |
    PLengthDoubleArray |
    PNewByteArray |
    PReadByteArray |
    PWriteByteArray |
    PLengthByteArray |
    PByteArrayFromString |
    PPutBytes |
    PGetByteLine |
    PNewIntTable |
    PReadIntTable |
    PWriteIntTable |
    PAndInt |
    PStringLength |
    PStringCodeAt |
    PStringSlice |
    PStringFromCode |
    PCompareString |
    PReadDouble |
    PDoubleToBits |
    PDoubleFromBits |
    PSeq |
    PPanic |
    PReadFile |
    PWriteFile |
    PFileExists |
    PCanonicalPath |
    PGetArgCount |
    PGetArg |
    PPutErr |
    PExitWith |
    PGetExecutablePath |
    PGetContents |
    PSTReturn |
    PSTBind |
    PRunST |
    PNewSTArray |
    PReadSTArray |
    PWriteSTArray |
    PLengthSTArray |
    PGetEnv |
    PSetEnv |
    PUnsetEnv |
    PRunProcess |
    PListDirectory |
    PDirectoryExists |
    PFileDigest |
    PAcquireFileLock |
    PReleaseFileLock |
    PProcessSupervisor |
    PAsyncScopeNew |
    PAsyncScopeClose |
    PAsyncNewCompletion |
    PAsyncResolveCompletion |
    PAsyncReadCompletion |
    PAsyncSubscribeCompletion |
    PAsyncSubscriptionStatus |
    PAsyncCancelSubscription |
    PAsyncStep |
    PAsyncEnqueue |
    PAsyncDelay |
    PAsyncWait |
    PTextToChars |
    PTextFromChars |
    PCharCode |
    PCharFromCode |
    PUserError |
    PIOError |
    PCatchIOError |
    PIOErrorString |
    PEmptyCallStack |
    PPushCallStack |
    PPrettyCallStack |
    PIOErrorWithStack;
  data SType =
    STVar String |
    SBottom |
    SBottomKind Kind |
    SArrow SType SType |
    SCon String ([] SType) |
    STypeApp SType SType |
    SForall Flag String SType SType |
    SQualified ([] SPredicate) SType;
  data SAnnotation = SAnnotation ([] String) SType;
  data RecursiveMode = InferRecursive | CheckRecursive SAnnotation;
  data SourceSpan = SourceSpan String String String Int Int Int Int;
  data SExpr =
    SVar String |
    SConstructor String |
    SLam String (Maybe SAnnotation) SExpr |
    SApp SExpr SExpr |
    SLet String SExpr SExpr |
    SAnn SExpr SAnnotation |
    -- Declaration provenance is distinct from expression annotation/coercion.
    SSignature SExpr SAnnotation |
    SIntLit Int |
    SDoubleLit Double |
    SBoolLit Bool |
    SStringLit String |
    SPrimitive Primitive |
    SCase SExpr ([] SAlternative) |
    SDo ([] SStatement) SExpr |
    SEquations ([] ((,) ([] SPattern) SExpr)) |
    SLetRec ([] ((,,) String RecursiveMode SExpr)) SExpr |
    SWanted String ([] ((,) EvidenceRole String)) |
    SChecked SType SExpr |
    SSourceDefinition SExpr |
    SCallSite String SourceSpan SExpr |
    SSharedBind SPattern SExpr SExpr SExpr SExpr;
  data SourceString = ScalarString String | CharString ([] Int);
  data SPattern =
    SConstructorPattern String ([] (Maybe String)) |
    SDefaultPattern (Maybe String) |
    SNestedPattern String ([] SPattern) |
    SAnnotatedPattern String SAnnotation |
    SIntPattern Int |
    SStringPattern String |
    SOverloadedStringPattern SourceString String String |
    SBoolPattern Bool |
    SAsPattern String SPattern |
    SLazyPattern SPattern;
  data SAlternative = SAlternative SPattern SExpr;
  data SStatement =
    SDoBind SPattern SExpr |
    SDoThen SExpr |
    SDoLet String (Maybe SAnnotation) SExpr |
    SDoLetRec ([] ((,,) String RecursiveMode SExpr));
  data SPredicate = SPredicate String ([] SType);
  data SClassDecl =
    SClassDecl String ([] ((,) String Kind)) ([] SPredicate) ([] ((,) String SType));
  data SInstanceDecl =
    SInstanceDecl ([] ((,) String Kind)) ([] SPredicate) String ([] SType) ([]
                                                                                   ((,) String
                                                                                    SExpr));
  data EvidenceRole = GivenEvidence | SuperclassEvidence | InstanceEvidence;
  data SProgram =
    SProgram ([] DataDecl) SExpr |
    SClassProgram ([] DataDecl) ([] SClassDecl) ([] SInstanceDecl) SExpr;
  data SourceSyntax = LegacyEmlfV1 | SharedHaskellV1 | MetadataSyntax;
  data SourceModule =
    SourceModule String (Maybe String) (Maybe ([] Export)) ([] Import) ([] DataDecl) ([]
                                                                                            SClassDecl) ([]
                                                                                                         SInstanceDecl) ([]
                                                                                                                         ((,,)
                                                                                                                          String
                                                                                                                          (Maybe
                                                                                                                           SAnnotation)
                                                                                                                          SExpr)) (Maybe
                                                                                                                                   SExpr) SourceSyntax;
  data Import = Import String Bool (Maybe String) Selection;
  data Selection = Everything | Only ([] Export) | Hiding ([] Export);
  data Export = ExportValue String | ExportType String Members | ExportModule String;
  data Members = Abstract | AllMembers | Members ([] String);
  data PreludeMode = ImplicitPrelude | NoImplicitPrelude;
  data LinkedModule = LinkedModule SProgram (Map String String) (Map String IntSet) ([] IntSet);
  data XTyVar = XTyVar Int;
  data XName = XName Int String;
  data XType =
    XVar XTyVar |
    XBot |
    XBotKind Kind |
    XArrow XType XType |
    XCon String ([] XType) |
    XApply XType XType |
    XForall XTyVar XType XType;
  data XComputation =
    XRefl |
    XBottom XType |
    XHyp XTyVar |
    XInner XComputation |
    XOuter XTyVar XComputation |
    XElim |
    XIntro XTyVar |
    XIntroKind XTyVar Kind |
    XThen XComputation XComputation;
  data XTerm =
    XVarTerm XName |
    XAbs XName XType XTerm |
    XApp XTerm XTerm |
    XTypeAbs XTyVar XType XTerm |
    XTypeApp XTerm XComputation |
    XLet XName XTerm XTerm |
    XLetRec ([] ((,,) XName XType XTerm)) XTerm |
    XIntTerm Int |
    XDoubleTerm Double |
    XBoolTerm Bool |
    XStringTerm String |
    XPrimitive Primitive ([] XType) |
    XConstructor String ([] XType) |
    XCase XTerm XType ([] XAlternative) |
    XWithData ([] DataDecl) XTerm;
  data XPattern = XConstructorPattern String ([] (Maybe XName)) | XDefaultPattern (Maybe XName);
  data XAlternative = XAlternative XPattern XTerm;
  data XErased =
    XEVar XName |
    XEAbs XName XErased |
    XEApp XErased XErased |
    XELet XName XErased XErased |
    XEInt Int |
    XEDouble Double |
    XEBool Bool |
    XEString String |
    XEPrimitive Primitive |
    XELetRec ([] ((,) XName XErased)) XErased |
    XEEvidenceHole Int |
    XEConstructor String |
    XECase XErased ([] XErasedAlternative);
  data XErasedAlternative = XErasedAlternative XPattern XErased;
  data XEnv = XEnv (Map XTyVar XType) (Map XName XType);
  data GTag =
    GBot |
    GBotK Kind |
    GArr Int Int |
    GCon String ([] Int) |
    GTyCon String Kind |
    GSkolem Int Kind |
    GTyApp Int Int |
    GGen Int;
  data Node = Node GTag (Maybe Int) Flag;
  data Graph = Graph (IntMap Node) (IntMap Int) Int;
  data Permission = Green | Orange | Red | Inert;
  data ScopeIndex = ScopeIndex (IntMap ((,) Int Int)) ([] (IntMap Int));
  data Solver = Solver Graph (IntMap IntSet) (IntMap IntSet) ScopeIndex;
  data Edge = Edge Int Int;
  data Typed = Typed Int Form;
  data Form =
    FVariable XName (Maybe Edge) |
    FDeclaredVariable XName XType Edge |
    FLambda XName Int Typed Edge |
    FApply Typed Typed Edge Edge |
    FBinding XName Typed Typed Edge |
    FCoercion XName Int Int |
    FIntegerLiteral Int |
    FDoubleLiteral Double |
    FBooleanLiteral Bool |
    FStringLiteral String |
    FPrimitive Primitive ([] Int) |
    FConstructor String ([] Int) |
    FMatch Typed Edge ([] Branch) |
    FRecursive ([] RecursiveDefinition) Typed Edge |
    FEvidence ([] EvidenceBinding) |
    FChecked ([] ((,) XTyVar Kind)) Typed Edge;
  data RecursiveClosure = RecursiveClosure Int (IntMap Int);
  data RecursiveDefinition = RecursiveDefinition XName Int Typed Edge (Maybe RecursiveClosure);
  data Branch = Branch XPattern Typed Edge;
  data EvidenceBinding = EvidenceBinding EvidenceRole XName Int Bool | DeclaredEvidenceBinding EvidenceRole XName XType;
  data Constraints = Constraints Graph Typed ([] ((,) Int Int)) ([] Edge);
  data Core =
    CVar String |
    CLam String Core |
    CApp Core Core |
    CLet String Core Core |
    CCoerce SAnnotation |
    CInt Int |
    CDouble Double |
    CBool Bool |
    CString String |
    CPrimitive Primitive |
    CConstructor String |
    CCase Core ([] ((,) SPattern Core)) |
    CRec ([] ((,,) String RecursiveMode Core)) Core |
    CWanted String ([] ((,) EvidenceRole String)) |
    CChecked SType SExpr;
  data Binding = Mono XName Int | Poly XName Int | DeclaredPoly XName Int XType | RecursiveMono XName Int Int;
  data Phase = Parsing | ModuleResolution | Inference | Resolution | Elaboration | Verification;
  data CompileError = CompileError Phase String
}
