-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Opt-in capture only. Ordinary full checking precedes all returned evidence.
module MLF.ResourceModules
  (CapturedCompilation, compileCaptured, checkedTerm, moduleCustody, sourceErasure,
   binderOrigins, rawTerm, rawErased, rawType, rawDeclaration, rawDeclarations) where
 { import MLF.Primitive
 ; import Bootstrap.Types
 ; import qualified Bootstrap.Std as L
 ; import qualified Bootstrap.Map as M
 ; import qualified Bootstrap.Set as S
 ; import qualified Bootstrap.IntMap as IM
 ; import qualified Bootstrap.IntSet as IS
 ; import qualified Bootstrap.Module as Modules
 ; import qualified Bootstrap.Parser as Parser
 ; import qualified Bootstrap.CompilerCore as Core
 ; import qualified Bootstrap.Classes as Classes
 ; import qualified Bootstrap.Constraint as Constraint
 ; import qualified Bootstrap.Data as D
 ; import qualified Bootstrap.Surface as Surface
 ; import qualified Bootstrap.Primitive as Primitive
 ; import qualified Bootstrap.X.Checked as K
 ; import qualified Bootstrap.X.Syntax as X
 ; import qualified Bootstrap.X.Type as T
 ; import qualified Package.Json as J

 ; kindNode :: Kind -> J.Json
 ; kindNode kind = case kind of
   { Star -> J.Object [("tag", J.String "star")]
   ; KArrow a b -> J.Object [("tag", J.String "arrow"), ("from", kindNode a), ("to", kindNode b)]

 }  ; fieldNode :: Field -> J.Json
 ; fieldNode field = case field of
   { Parameter n -> J.Object [("tag", J.String "parameter"), ("name", J.String n)]
   ; Function a b -> J.Object [("tag", J.String "function"), ("from", fieldNode a), ("to", fieldNode b)]
   ; Applied n args -> J.Object [("tag", J.String "applied"), ("name", J.String n), ("arguments", J.Array (L.map fieldNode args))]
   ; Application f a -> J.Object [("tag", J.String "application"), ("function", fieldNode f), ("argument", fieldNode a)]
   ; Quantified n k b -> J.Object [("tag", J.String "quantified"), ("name", J.String n), ("kind", kindNode k), ("body", fieldNode b)]

 }  ; constructorNode :: ConstructorDecl -> J.Json
 ; constructorNode (ConstructorDecl n fields) = J.Object
  [("name", J.String n), ("fields", J.Array (L.map fieldNode fields))]

 ; rawDeclaration :: DataDecl -> J.Json
 ; rawDeclaration declaration = case declaration of
   { DataDecl n params constructors -> J.Object
    [("tag", J.String "data"), ("name", J.String n),
     ("parameters", J.Array (L.map J.String params)),
     ("constructors", J.Array (L.map constructorNode constructors))]
   ; DataDeclK n params constructors -> J.Object
    [("tag", J.String "data_kind"), ("name", J.String n),
     ("parameters", J.Array (L.map (\((,) parameter k) -> J.Object
       [("name", J.String parameter), ("kind", kindNode k)]) params)),
     ("constructors", J.Array (L.map constructorNode constructors))]

-- Total serialization of the original checked XMLF datatypes. This vocabulary
-- is independent from the deliberately partial resource-runtime transport.
 }  ; rawNode :: String -> [] ((,) String J.Json) -> J.Json
 ; rawNode tag fields = J.Object ((:) ((,) "tag" (J.String tag)) fields)

 ; nameNode :: XName -> J.Json
 ; nameNode n = J.Object [("id", J.num (X.nameId n)), ("hint", J.String (X.nameHint n))]

 ; rawType :: XType -> J.Json
 ; rawType ty = case ty of
   { XVar (XTyVar n) -> rawNode "var" [("id", J.num n)]
   ; XBot -> rawNode "bottom" []
   ; XBotKind k -> rawNode "bottom_kind" [("kind", kindNode k)]
   ; XArrow a b -> rawNode "arrow" [("from", rawType a), ("to", rawType b)]
   ; XCon n args -> rawNode "constructor" [("name", J.String n), ("arguments", J.Array (L.map rawType args))]
   ; XApply f a -> rawNode "apply" [("function", rawType f), ("argument", rawType a)]
   ; XForall (XTyVar n) bound body -> rawNode "forall"
    [("id", J.num n), ("bound", rawType bound), ("body", rawType body)]

 }  ; computationNode :: XComputation -> J.Json
 ; computationNode proof = case proof of
   { XRefl -> rawNode "refl" []
   ; XBottom ty -> rawNode "bottom" [("type", rawType ty)]
   ; XHyp (XTyVar n) -> rawNode "hyp" [("id", J.num n)]
   ; XInner p -> rawNode "inner" [("witness", computationNode p)]
   ; XOuter (XTyVar n) p -> rawNode "outer" [("id", J.num n), ("witness", computationNode p)]
   ; XElim -> rawNode "elim" []
   ; XIntro (XTyVar n) -> rawNode "intro" [("id", J.num n)]
   ; XIntroKind (XTyVar n) k -> rawNode "intro_kind" [("id", J.num n), ("kind", kindNode k)]
   ; XThen a b -> rawNode "then" [("first", computationNode a), ("second", computationNode b)]

 }  ; optionalNameNode :: Maybe XName -> J.Json
 ; optionalNameNode value = case value of
   { Nothing -> J.Null
   ; Just n -> nameNode n

 }  ; patternNode :: XPattern -> J.Json
 ; patternNode pattern = case pattern of
   { XConstructorPattern constructor fields -> rawNode "constructor"
    [("constructor", J.String constructor), ("fields", J.Array (L.map optionalNameNode fields))]
   ; XDefaultPattern binder -> rawNode "default" [("binder", optionalNameNode binder)]

 }  ; alternativeNode :: XAlternative -> J.Json
 ; alternativeNode (XAlternative pattern body) = J.Object
  [("pattern", patternNode pattern), ("body", rawTerm body)]

 ; recursiveBindingNode :: (,,) XName XType XTerm -> J.Json
 ; recursiveBindingNode ((,,) n ty value) = J.Object
  [("name", nameNode n), ("type", rawType ty), ("value", rawTerm value)]

 ; rawTerm :: XTerm -> J.Json
 ; rawTerm term = case term of
   { XVarTerm n -> rawNode "var" [("name", nameNode n)]
   ; XAbs n ty body -> rawNode "lambda"
    [("parameter", nameNode n), ("parameter_type", rawType ty), ("body", rawTerm body)]
   ; XApp f a -> rawNode "application" [("function", rawTerm f), ("argument", rawTerm a)]
   ; XTypeAbs (XTyVar n) bound body -> rawNode "type_lambda"
    [("id", J.num n), ("bound", rawType bound), ("body", rawTerm body)]
   ; XTypeApp value proof -> rawNode "type_application"
    [("value", rawTerm value), ("witness", computationNode proof)]
   ; XLet n value body -> rawNode "let"
    [("name", nameNode n), ("value", rawTerm value), ("body", rawTerm body)]
   ; XLetRec bindings body -> rawNode "letrec"
    [("bindings", J.Array (L.map recursiveBindingNode bindings)), ("body", rawTerm body)]
   ; XIntTerm value -> rawNode "int64" [("value", J.num value)]
   ; XDoubleTerm value -> rawNode "double" [("bits_i64", J.num (doubleToBits value))]
   ; XBoolTerm value -> rawNode "bool" [("value", J.Boolean value)]
   ; XStringTerm value -> rawNode "string" [("value", J.String value)]
   ; XPrimitive primitive arguments -> rawNode "primitive"
    [("id", J.num (Primitive.primitiveCode primitive)),
     ("name", J.String (Primitive.primitiveName primitive)),
     ("arguments", J.Array (L.map rawType arguments))]
   ; XConstructor constructor arguments -> rawNode "constructor"
    [("name", J.String constructor), ("arguments", J.Array (L.map rawType arguments))]
   ; XCase subject result alternatives -> rawNode "case"
    [("scrutinee", rawTerm subject), ("result_type", rawType result),
     ("alternatives", J.Array (L.map alternativeNode alternatives))]
   ; XWithData declarations body -> rawNode "with_data"
    [("declarations", J.Array (L.map rawDeclaration declarations)), ("body", rawTerm body)]

 }  ; rawDeclarations :: [] DataDecl -> J.Json
 ; rawDeclarations values = J.Array (L.map rawDeclaration values)

 ; rawErased :: XErased -> J.Json
 ; rawErased term = case term of
   { XEVar n -> rawNode "var" [("name", nameNode n)]
   ; XEAbs n body -> rawNode "lambda" [("parameter", nameNode n), ("body", rawErased body)]
   ; XEApp f a -> rawNode "application" [("function", rawErased f), ("argument", rawErased a)]
   ; XELet n value body -> rawNode "let"
    [("name", nameNode n), ("value", rawErased value), ("body", rawErased body)]
   ; XELetRec bindings body -> rawNode "letrec"
    [("bindings", J.Array (L.map (\((,) n value) -> J.Object
      [("name", nameNode n), ("value", rawErased value)]) bindings)), ("body", rawErased body)]
   ; XEInt value -> rawNode "int64" [("value", J.num value)]
   ; XEDouble value -> rawNode "double" [("bits_i64", J.num (doubleToBits value))]
   ; XEBool value -> rawNode "bool" [("value", J.Boolean value)]
   ; XEString value -> rawNode "string" [("value", J.String value)]
   ; XEPrimitive primitive -> rawNode "primitive"
    [("id", J.num (Primitive.primitiveCode primitive)), ("name", J.String (Primitive.primitiveName primitive))]
   ; XEConstructor constructor -> rawNode "constructor" [("name", J.String constructor)]
   ; XECase subject alternatives -> rawNode "case"
    [("scrutinee", rawErased subject), ("alternatives", J.Array (L.map
      (\(XErasedAlternative pattern body) -> J.Object
        [("pattern", patternNode pattern), ("body", rawErased body)]) alternatives))]
   ; XEEvidenceHole n -> rawNode "evidence_hole" [("id", J.num n)]

 }  ; flagNode :: Flag -> J.Json
 ; flagNode value = J.String (case value of { Flexible -> "flexible"; Rigid -> "rigid" })

 ; sourceTypeNode :: SType -> J.Json
 ; sourceTypeNode value = case value of
   { STVar n -> rawNode "var" [("name", J.String n)]
   ; SBottom -> rawNode "bottom" []
   ; SBottomKind k -> rawNode "bottom_kind" [("kind", kindNode k)]
   ; SArrow a b -> rawNode "arrow" [("from", sourceTypeNode a), ("to", sourceTypeNode b)]
   ; SCon n args -> rawNode "constructor" [("name", J.String n), ("arguments", J.Array (L.map sourceTypeNode args))]
   ; STypeApp f a -> rawNode "apply" [("function", sourceTypeNode f), ("argument", sourceTypeNode a)]
   ; SForall f n bound body -> rawNode "forall" [("flag", flagNode f), ("name", J.String n),
    ("bound", sourceTypeNode bound), ("body", sourceTypeNode body)]
   ; SQualified predicates body -> rawNode "qualified"
    [("predicates", J.Array (L.map predicateNode predicates)), ("body", sourceTypeNode body)]

 }  ; predicateNode :: SPredicate -> J.Json
 ; predicateNode (SPredicate n args) = J.Object [("name", J.String n), ("arguments", J.Array (L.map sourceTypeNode args))]

 ; annotationNode :: SAnnotation -> J.Json
 ; annotationNode (SAnnotation variables ty) = J.Object
  [("existentials", J.Array (L.map J.String variables)), ("type", sourceTypeNode ty)]

 ; optional :: forall a. (a -> J.Json) -> Maybe a -> J.Json
 ; optional convert value = case value of { Nothing -> J.Null; Just x -> convert x }

 ; sourceStringNode :: SourceString -> J.Json
 ; sourceStringNode value = case value of
   { ScalarString text -> rawNode "scalar" [("text", J.String text)]
   ; CharString chars -> rawNode "chars" [("codes", J.Array (L.map J.num chars))]

 }  ; sourcePatternNode :: SPattern -> J.Json
 ; sourcePatternNode value = case value of
   { SConstructorPattern n fields -> rawNode "constructor" [("name", J.String n), ("fields", J.Array (L.map (optional J.String) fields))]
   ; SDefaultPattern n -> rawNode "default" [("binder", optional J.String n)]
   ; SNestedPattern n fields -> rawNode "nested" [("name", J.String n), ("fields", J.Array (L.map sourcePatternNode fields))]
   ; SAnnotatedPattern n ty -> rawNode "annotated" [("name", J.String n), ("annotation", annotationNode ty)]
   ; SIntPattern n -> rawNode "int64" [("value", J.num n)]
   ; SStringPattern text -> rawNode "string" [("value", J.String text)]
   ; SOverloadedStringPattern text equality conversion -> rawNode "overloaded_string"
    [("value", sourceStringNode text), ("equality", J.String equality), ("conversion", J.String conversion)]
   ; SBoolPattern b -> rawNode "bool" [("value", J.Boolean b)]
   ; SAsPattern n p -> rawNode "as" [("name", J.String n), ("pattern", sourcePatternNode p)]
   ; SLazyPattern p -> rawNode "lazy" [("pattern", sourcePatternNode p)]

 }  ; recursiveModeNode :: RecursiveMode -> J.Json
 ; recursiveModeNode mode = case mode of
   { InferRecursive -> rawNode "infer" []
   ; CheckRecursive annotation -> rawNode "check" [("annotation", annotationNode annotation)]

 }  ; sourceRecursiveNode :: (,,) String RecursiveMode SExpr -> J.Json
 ; sourceRecursiveNode ((,,) n mode body) = J.Object
  [("name", J.String n), ("mode", recursiveModeNode mode), ("value", sourceExprNode body)]

 ; spanNode :: SourceSpan -> J.Json
 ; spanNode (SourceSpan package moduleName file line column endLine endColumn) = J.Object
  [("package", J.String package), ("module", J.String moduleName), ("file", J.String file),
   ("line", J.num line), ("column", J.num column), ("end_line", J.num endLine), ("end_column", J.num endColumn)]

 ; evidenceRoleNode :: EvidenceRole -> J.Json
 ; evidenceRoleNode role = J.String (case role of
   { GivenEvidence -> "given"
   ; SuperclassEvidence -> "superclass"
   ; InstanceEvidence -> "instance" } )

 ; sourceExprNode :: SExpr -> J.Json
 ; sourceExprNode value = case value of
   { SVar n -> rawNode "var" [("name", J.String n)]
   ; SConstructor n -> rawNode "constructor" [("name", J.String n)]
   ; SLam n annotation body -> rawNode "lambda" [("name", J.String n), ("annotation", optional annotationNode annotation), ("body", sourceExprNode body)]
   ; SApp f a -> rawNode "application" [("function", sourceExprNode f), ("argument", sourceExprNode a)]
   ; SLet n rhs body -> rawNode "let" [("name", J.String n), ("value", sourceExprNode rhs), ("body", sourceExprNode body)]
   ; SAnn body annotation -> rawNode "annotation" [("value", sourceExprNode body), ("annotation", annotationNode annotation)]
   ; SSignature body annotation -> rawNode "signature" [("value", sourceExprNode body), ("annotation", annotationNode annotation)]
   ; SIntLit n -> rawNode "int64" [("value", J.num n)]
   ; SDoubleLit n -> rawNode "double" [("bits_i64", J.num (doubleToBits n))]
   ; SBoolLit b -> rawNode "bool" [("value", J.Boolean b)]
   ; SStringLit text -> rawNode "string" [("value", J.String text)]
   ; SPrimitive p -> rawNode "primitive" [("id", J.num (Primitive.primitiveCode p)), ("name", J.String (Primitive.primitiveName p))]
   ; SCase subject alternatives -> rawNode "case" [("scrutinee", sourceExprNode subject),
    ("alternatives", J.Array (L.map (\(SAlternative pattern body) -> J.Object
      [("pattern", sourcePatternNode pattern), ("body", sourceExprNode body)]) alternatives))]
   ; SDo statements body -> rawNode "do" [("statements", J.Array (L.map statementNode statements)), ("body", sourceExprNode body)]
   ; SEquations rows -> rawNode "equations" [("rows", J.Array (L.map (\((,) patterns body) -> J.Object
    [("patterns", J.Array (L.map sourcePatternNode patterns)), ("body", sourceExprNode body)]) rows))]
   ; SLetRec definitions body -> rawNode "letrec" [("bindings", J.Array (L.map sourceRecursiveNode definitions)), ("body", sourceExprNode body)]
   ; SWanted dictionary candidates -> rawNode "wanted" [("dictionary", J.String dictionary),
    ("candidates", J.Array (L.map (\((,) role n) -> J.Object [("role", evidenceRoleNode role), ("name", J.String n)]) candidates))]
   ; SChecked ty body -> rawNode "checked" [("type", sourceTypeNode ty), ("body", sourceExprNode body)]
   ; SSourceDefinition body -> rawNode "source_definition" [("body", sourceExprNode body)]
   ; SCallSite n location body -> rawNode "call_site" [("name", J.String n), ("location", spanNode location), ("body", sourceExprNode body)]
   ; SSharedBind pattern action body binding failure -> rawNode "shared_bind"
    [("pattern", sourcePatternNode pattern), ("action", sourceExprNode action), ("body", sourceExprNode body),
     ("binding", sourceExprNode binding), ("failure", sourceExprNode failure)]

 }  ; statementNode :: SStatement -> J.Json
 ; statementNode value = case value of
   { SDoBind p a -> rawNode "bind" [("pattern", sourcePatternNode p), ("value", sourceExprNode a)]
   ; SDoThen a -> rawNode "then" [("value", sourceExprNode a)]
   ; SDoLet n annotation a -> rawNode "let" [("name", J.String n), ("annotation", optional annotationNode annotation), ("value", sourceExprNode a)]
   ; SDoLetRec definitions -> rawNode "letrec" [("bindings", J.Array (L.map sourceRecursiveNode definitions))]

 }  ; parameterNode :: (,) String Kind -> J.Json
 ; parameterNode ((,) n k) = J.Object [("name", J.String n), ("kind", kindNode k)]

 ; classNode :: SClassDecl -> J.Json
 ; classNode (SClassDecl n params supers methods) = J.Object
  [("name", J.String n), ("parameters", J.Array (L.map parameterNode params)),
   ("supers", J.Array (L.map predicateNode supers)), ("methods", J.Array (L.map
    (\((,) key ty) -> J.Object [("name", J.String key), ("type", sourceTypeNode ty)]) methods))]

 ; instanceNode :: SInstanceDecl -> J.Json
 ; instanceNode (SInstanceDecl variables context klass args methods) = J.Object
  [("variables", J.Array (L.map parameterNode variables)), ("context", J.Array (L.map predicateNode context)),
   ("class", J.String klass), ("head", J.Array (L.map sourceTypeNode args)),
   ("methods", J.Array (L.map (\((,) n body) -> J.Object [("name", J.String n), ("body", sourceExprNode body)]) methods))]

 ; sourceValueNode :: (,,) String (Maybe SAnnotation) SExpr -> J.Json
 ; sourceValueNode ((,,) n annotation body) = J.Object
  [("name", J.String n), ("annotation", optional annotationNode annotation), ("body", sourceExprNode body)]

 ; membersNode :: Members -> J.Json
 ; membersNode members = case members of
   { Abstract -> rawNode "abstract" []
   ; AllMembers -> rawNode "all" []
   ; Members names -> rawNode "members" [("names", J.Array (L.map J.String names))]

 }  ; exportNode :: Export -> J.Json
 ; exportNode value = case value of
   { ExportValue n -> rawNode "value" [("name", J.String n)]
   ; ExportType n members -> rawNode "type" [("name", J.String n), ("members", membersNode members)]
   ; ExportModule n -> rawNode "module" [("name", J.String n)]

 }  ; selectionNode :: Selection -> J.Json
 ; selectionNode value = case value of
   { Everything -> rawNode "everything" []
   ; Only values -> rawNode "only" [("items", J.Array (L.map exportNode values))]
   ; Hiding values -> rawNode "hiding" [("items", J.Array (L.map exportNode values))]

 }  ; importNode :: Import -> J.Json
 ; importNode (Import n qualified alias selection) = J.Object
  [("module", J.String n), ("qualified", J.Boolean qualified), ("alias", optional J.String alias), ("selection", selectionNode selection)]

 ; syntaxNode :: SourceSyntax -> J.Json
 ; syntaxNode syntax = J.String (case syntax of
   { LegacyEmlfV1 -> "legacy-emlf-v1"
   ; SharedHaskellV1 -> "shared-haskell-v1"
   ; MetadataSyntax -> "metadata" } )

 ; sourceNode :: SourceModule -> J.Json
 ; sourceNode (SourceModule path n exports imports declarations classes instances values body syntax) = J.Object
  [("path", J.String path), ("name", optional J.String n), ("exports", optional (L.compose J.Array (L.map exportNode)) exports),
   ("imports", J.Array (L.map importNode imports)), ("declarations", rawDeclarations declarations),
   ("classes", J.Array (L.map classNode classes)), ("instances", J.Array (L.map instanceNode instances)),
   ("values", J.Array (L.map sourceValueNode values)), ("body", optional sourceExprNode body), ("syntax", syntaxNode syntax)]

 ; roleNode :: Modules.Role -> J.Json
 ; roleNode role = case role of
   { Modules.Value -> rawNode "value" []
   ; Modules.Datatype -> rawNode "datatype" []
   ; Modules.Class -> rawNode "class" []
   ; Modules.Constructor n -> rawNode "constructor" [("datatype", J.String n)]
   ; Modules.Method n -> rawNode "method" [("class", J.String n)]
   ; Modules.BuiltinType -> rawNode "builtin_type" []
   ; Modules.Primitive p -> rawNode "primitive" [("id", J.num (Primitive.primitiveCode p)), ("name", J.String (Primitive.primitiveName p))]
   ; Modules.Boolean b -> rawNode "boolean" [("value", J.Boolean b)]
   ; Modules.ManagedConstraint -> rawNode "managed_constraint" []

 }  ; spaceNode :: Modules.ModuleSpace -> J.Json
 ; spaceNode space = J.String (case space of { Modules.Terms -> "terms"; Modules.Types -> "types" })

 ; entityNode :: Modules.Entity -> J.Json
 ; entityNode entity = J.Object [("owner", J.String (Modules.owner entity)), ("spelling", J.String (Modules.spelling entity)),
  ("role", roleNode (Modules.role entity)), ("namespace", spaceNode (Modules.space entity))]

 ; entityAllocationNode :: (,) Modules.Entity String -> J.Json
 ; entityAllocationNode ((,) entity allocated) = J.Object [("entity", entityNode entity), ("allocated", J.String allocated)]

 ; interfaceNode :: Modules.Interface -> J.Json
 ; interfaceNode (Modules.Interface entries) = J.Array (L.map
  (\((,) ((,) space spelling) entities) -> J.Object [("namespace", spaceNode space), ("spelling", J.String spelling),
    ("entities", J.Array (L.map entityNode (S.toList entities)))]) (M.toList entries))

 ; renamedNode :: Modules.Renamed -> J.Json
 ; renamedNode (Modules.Renamed declarations classes instances values body) = J.Object
  [("declarations", rawDeclarations declarations), ("classes", J.Array (L.map classNode classes)),
   ("instances", J.Array (L.map instanceNode instances)), ("values", J.Array (L.map sourceValueNode values)),
   ("body", optional sourceExprNode body)]

 ; resolutionNode :: Modules.ResolvedCrate -> J.Json
 ; resolutionNode resolution = let  { names = case Modules.resolvedCrateNames resolution of { Modules.Names resolvedNamesValue -> resolvedNamesValue }  } in J.Object
  [("entities", J.Array (L.map entityAllocationNode (M.toList names))),
   ("modules", J.Array (L.map (\r -> J.Object [("source", sourceNode (Modules.resolvedSource r)),
     ("compiler_owned", J.Boolean (Modules.isBuiltinModule (Modules.moduleIdentity (Modules.resolvedSource r)))),
     ("renamed", renamedNode (Modules.resolvedContents r)), ("scope", interfaceNode (Modules.resolvedScope r))])
       (Modules.resolvedCrateModules resolution))),
   ("display_names", J.Array (L.map (\((,) n text) -> J.Object [("allocated", J.String n), ("display", J.String text)])
       (M.toList (Modules.resolvedCrateDisplayNames resolution)))),
   ("instances", J.Array (L.map (\((,) owner inst) -> J.Object [("owner", J.String owner), ("instance", instanceNode inst)])
       (Modules.resolvedCrateInstances resolution))),
   ("value_scopes", J.Array (L.map (\((,) n values) -> J.Object [("name", J.String n), ("scope", J.Array (L.map J.num (IS.toList values)))])
       (M.toList (Modules.resolvedCrateValueScopes resolution)))),
   ("instance_scopes", J.Array (L.map (\values -> J.Array (L.map J.num (IS.toList values))) (Modules.resolvedCrateInstanceScopes resolution))),
   ("reach", J.Array (L.map (\((,) owner values) -> J.Object [("owner", J.String owner), ("modules", J.Array (L.map J.String (S.toList values)))])
       (M.toList (Modules.resolvedCrateReach resolution))))]
 ; coreNode :: Core -> J.Json
 ; coreNode core = case core of
   { CVar n -> rawNode "var" [("name", J.String n)]
   ; CLam n body -> rawNode "lambda" [("name", J.String n), ("body", coreNode body)]
   ; CApp f a -> rawNode "application" [("function", coreNode f), ("argument", coreNode a)]
   ; CLet n rhs body -> rawNode "let" [("name", J.String n), ("value", coreNode rhs), ("body", coreNode body)]
   ; CCoerce annotation -> rawNode "coerce" [("annotation", annotationNode annotation)]
   ; CInt n -> rawNode "int64" [("value", J.num n)]
   ; CDouble n -> rawNode "double" [("bits_i64", J.num (doubleToBits n))]
   ; CBool b -> rawNode "bool" [("value", J.Boolean b)]
   ; CString text -> rawNode "string" [("value", J.String text)]
   ; CPrimitive p -> rawNode "primitive" [("id", J.num (Primitive.primitiveCode p)), ("name", J.String (Primitive.primitiveName p))]
   ; CConstructor n -> rawNode "constructor" [("name", J.String n)]
   ; CCase subject alternatives -> rawNode "case" [("scrutinee", coreNode subject),
    ("alternatives", J.Array (L.map (\((,) pattern body) -> J.Object
      [("pattern", sourcePatternNode pattern), ("body", coreNode body)]) alternatives))]
   ; CRec definitions body -> rawNode "letrec" [("bindings", J.Array (L.map (\((,,) n mode rhs) -> J.Object
    [("name", J.String n), ("mode", recursiveModeNode mode), ("value", coreNode rhs)]) definitions)), ("body", coreNode body)]
   ; CWanted dictionary candidates -> rawNode "wanted" [("dictionary", J.String dictionary),
    ("candidates", J.Array (L.map (\((,) role n) -> J.Object [("role", evidenceRoleNode role), ("name", J.String n)]) candidates))]
   ; CChecked ty expression -> rawNode "checked" [("type", sourceTypeNode ty), ("expression", sourceExprNode expression)]

 }  ; edgeNode :: Edge -> J.Json
 ; edgeNode (Edge from to) = J.Object [("from", J.num from), ("to", J.num to)]

 ; intMapNode :: IntMap Int -> J.Json
 ; intMapNode values = J.Array (L.map (\((,) k v) -> J.Object [("key", J.num k), ("value", J.num v)]) (IM.toList values))

 ; closureNode :: RecursiveClosure -> J.Json
 ; closureNode (RecursiveClosure group copies) = J.Object [("group", J.num group), ("copies", intMapNode copies)]

 ; typedRecursiveNode :: RecursiveDefinition -> J.Json
 ; typedRecursiveNode (RecursiveDefinition n declaration rhs edge closure) = J.Object
  [("name", nameNode n), ("declaration", J.num declaration), ("value", typedNode rhs),
   ("edge", edgeNode edge), ("closure", optional closureNode closure)]

 ; evidenceBindingNode :: EvidenceBinding -> J.Json
 ; evidenceBindingNode value = case value of
   { EvidenceBinding role n identity polymorphic -> rawNode "inferred"
    [("role", evidenceRoleNode role), ("name", nameNode n), ("identity", J.num identity), ("polymorphic", J.Boolean polymorphic)]
   ; DeclaredEvidenceBinding role n ty -> rawNode "declared"
    [("role", evidenceRoleNode role), ("name", nameNode n), ("type", rawType ty)]

 }  ; typedNode :: Typed -> J.Json
 ; typedNode (Typed gen form) = J.Object [("generation", J.num gen), ("form", case form of
   { FVariable n edge -> rawNode "var" [("name", nameNode n), ("edge", optional edgeNode edge)]
   ; FDeclaredVariable n ty edge -> rawNode "declared_var" [("name", nameNode n), ("type", rawType ty), ("edge", edgeNode edge)]
   ; FLambda n domain body edge -> rawNode "lambda" [("name", nameNode n), ("domain", J.num domain), ("body", typedNode body), ("edge", edgeNode edge)]
   ; FApply f a ef ea -> rawNode "application" [("function", typedNode f), ("argument", typedNode a), ("function_edge", edgeNode ef), ("argument_edge", edgeNode ea)]
   ; FBinding n rhs body edge -> rawNode "let" [("name", nameNode n), ("value", typedNode rhs), ("body", typedNode body), ("edge", edgeNode edge)]
   ; FCoercion n domain codomain -> rawNode "coerce" [("name", nameNode n), ("domain", J.num domain), ("codomain", J.num codomain)]
   ; FIntegerLiteral n -> rawNode "int64" [("value", J.num n)]
   ; FDoubleLiteral n -> rawNode "double" [("bits_i64", J.num (doubleToBits n))]
   ; FBooleanLiteral b -> rawNode "bool" [("value", J.Boolean b)]
   ; FStringLiteral text -> rawNode "string" [("value", J.String text)]
   ; FPrimitive p args -> rawNode "primitive" [("id", J.num (Primitive.primitiveCode p)), ("name", J.String (Primitive.primitiveName p)), ("arguments", J.Array (L.map J.num args))]
   ; FConstructor n args -> rawNode "constructor" [("name", J.String n), ("arguments", J.Array (L.map J.num args))]
   ; FMatch subject edge branches -> rawNode "case" [("scrutinee", typedNode subject), ("edge", edgeNode edge),
    ("alternatives", J.Array (L.map (\(Branch pattern body branchEdge) -> J.Object
      [("pattern", patternNode pattern), ("body", typedNode body), ("edge", edgeNode branchEdge)]) branches))]
   ; FRecursive definitions body edge -> rawNode "letrec" [("bindings", J.Array (L.map typedRecursiveNode definitions)), ("body", typedNode body), ("edge", edgeNode edge)]
   ; FEvidence candidates -> rawNode "evidence" [("candidates", J.Array (L.map evidenceBindingNode candidates))]
   ; FChecked variables body edge -> rawNode "checked" [("variables", J.Array (L.map (\((,) (XTyVar n) k) -> J.Object
    [("id", J.num n), ("kind", kindNode k)]) variables)), ("body", typedNode body), ("edge", edgeNode edge)] } )]

 ; pathChild :: [] String -> String -> [] String
 ; pathChild path edge = L.snoc path edge

 ; pathIndexed :: [] String -> String -> Int -> String -> [] String
 ; pathIndexed path edge index final = L.append path [edge, showInt index, final]

 ; sameName :: XName -> XName -> Bool
 ; sameName a b = X.equalName a b && eqString (X.nameHint a) (X.nameHint b)

 ; checkFreshHint :: String -> XName -> Either String ()
 ; checkFreshHint source actual = L.ensure (eqString (Constraint.targetNameHint source) (X.nameHint actual))
  "constraint binder does not match the original freshName encoding"

 ; ownedBinding :: Modules.ResolvedCrate -> Bool -> String -> Either String J.Json
 ; ownedBinding resolution outer source =
  if L.not outer then Right J.Null else let
     { declared = L.concatMap (\r -> L.map (\((,,) n _ _) -> (,) (Modules.moduleIdentity (Modules.resolvedSource r)) n)
      (Modules.renamedValues (Modules.resolvedContents r))) (Modules.resolvedCrateModules resolution)
     ; names = case Modules.resolvedCrateNames resolution of { Modules.Names resolvedOwnedNamesValue -> resolvedOwnedNamesValue }
     ; owners = L.filter (\((,) _ n) -> eqString source n) declared
     ; allocations = L.filter (\((,) entity n) -> eqString source n && case Modules.role entity of
       { Modules.Value -> True
       ; _ -> False } ) (M.toList names)
   } in case owners of
     { [] -> Right J.Null
     ; [(,) owner _] -> case allocations of
       { [entry] -> do
         { L.ensure (eqString owner (Modules.owner (L.fst entry))) "source declaration owner differs from actual resolver allocation"
         ; Right (entityAllocationNode entry)
       }  ; _ -> Left "outer source declaration lacks a unique actual value allocation"
     }  ; _ -> Left "outer source declaration has duplicate resolver ownership"

 }  ; originBinding :: Modules.ResolvedCrate -> Bool -> String -> XName -> Either String J.Json
 ; originBinding resolution outer source actual = do
   { checkFreshHint source actual
   ; allocated <- ownedBinding resolution outer source
   ; let  { resolved = case allocated of { J.Null -> False; _ -> True }
   }  ; Right (J.Object [("name", nameNode actual), ("source_internal_name", J.String source),
    ("association", J.String (if resolved then "resolved_outer_declaration" else "compiler_local_or_generated")),
    ("resolver_allocation", allocated)])

 }  ; originRow :: [] String -> Int -> String -> [] J.Json -> J.Json
 ; originRow path generation kind bindings = J.Object
  [("path", J.Array (L.map J.String path)), ("generation", J.num generation), ("kind", J.String kind), ("bindings", J.Array bindings)]

 ; lookupSource :: Map String XName -> String -> XName -> Either String ()
 ; lookupSource env source actual = case M.lookup compareString source env of
   { Nothing -> Left "constraint variable has no structurally paired source binder"
   ; Just expected -> L.ensure (sameName actual expected) "constraint variable identity differs from lexical source binding"

 }  ; pairPattern :: Map String XName -> SPattern -> XPattern -> Either String (Map String XName)
 ; pairPattern env source actual = case (,) source actual of
   { (,) (SConstructorPattern a names) (XConstructorPattern b binders) -> do
     { L.ensure (eqString a b && L.length names == L.length binders) "source/typed constructor pattern mismatch"
     ; pairs <- pairPatternNames names binders
     ; Right (M.union compareString (M.fromList compareString pairs) env)
   }  ; (,) (SDefaultPattern a) (XDefaultPattern b) -> do
     { pairs <- pairPatternNames [a] [b]
     ; Right (M.union compareString (M.fromList compareString pairs) env)
   }  ; _ -> Left "source/typed pattern constructor mismatch"

 }  ; pairPatternNames :: [] (Maybe String) -> [] (Maybe XName) -> Either String ([] ((,) String XName))
 ; pairPatternNames sources actuals = case (,) sources actuals of
   { (,) [] [] -> Right []
   ; (,) ((:) Nothing ss) ((:) Nothing ns) -> pairPatternNames ss ns
   ; (,) ((:) (Just s) ss) ((:) (Just n) ns) -> do
     { checkFreshHint s n
     ; rest <- pairPatternNames ss ns
     ; Right ((:) ((,) s n) rest)
   }  ; _ -> Left "source/typed pattern binder arity or wildcard mismatch"

 }  ; pairEvidence :: Map String XName -> [] ((,) EvidenceRole String) -> [] EvidenceBinding -> Either String ()
 ; pairEvidence env sources actuals = case (,) sources actuals of
   { (,) [] [] -> Right ()
   ; (,) ((:) ((,) role source) rest) ((:) value values) -> do
     { let  { evidenceRoleNameParts = case value of
           { EvidenceBinding r n _ _ -> (,) r n
           ; DeclaredEvidenceBinding r n _ -> (,) r n
         }  ; actualRole = L.fst evidenceRoleNameParts
         ; name = L.snd evidenceRoleNameParts
     }  ; L.ensure (J.equal (evidenceRoleNode role) (evidenceRoleNode actualRole)) "dictionary evidence role differs from source candidate"
     ; lookupSource env source name
     ; pairEvidence env rest values
   }  ; _ -> Left "dictionary evidence source/typed candidate count mismatch"

 }  ; pairCore :: DataEnv -> Modules.ResolvedCrate -> Map String XName -> Bool -> [] String -> Core -> Typed -> Either String ([] J.Json)
 ; pairCore ds resolution env outer path source (Typed generation actual) = case (,) source actual of
   { (,) (CVar n) (FVariable name _) -> do { lookupSource env n name; Right [] }
   ; (,) (CVar n) (FDeclaredVariable name _ _) -> do { lookupSource env n name; Right [] }
   ; (,) (CVar n) (FPrimitive p args) -> do
     { L.ensure (L.not (M.member compareString n env)) "lexical variable incorrectly resolved as primitive"
     ; case Primitive.lookupPrimitive n of
       { Nothing -> Left "source variable does not resolve to the recorded actual primitive"
       ; Just expected -> pairCore ds resolution env outer path (CPrimitive expected) (Typed generation (FPrimitive p args))
   }  }  ; (,) (CLam sourceName body) (FLambda name _ typedBody _) -> do
     { checkFreshHint sourceName name
     ; pairCore ds resolution (M.insert compareString sourceName name env) False (pathChild path "body") body typedBody
   }  ; (,) (CApp f a) (FApply tf ta _ _) -> do
     { left <- pairCore ds resolution env False (pathChild path "function") f tf
     ; right <- pairCore ds resolution env False (pathChild path "argument") a ta
     ; Right (L.append left right)
   }  ; (,) (CLet sourceName rhs body) (FBinding name typedRhs typedBody _) -> do
     { binding <- originBinding resolution outer sourceName name
     ; left <- pairCore ds resolution env False (pathChild path "value") rhs typedRhs
     ; right <- pairCore ds resolution (M.insert compareString sourceName name env) outer (pathChild path "body") body typedBody
     ; Right ((:) (originRow path generation "let" [binding]) (L.append left right))
   }  ; (,) (CRec definitions body) (FRecursive actualDefinitions typedBody _) -> do
     { L.ensure (L.length definitions == L.length actualDefinitions) "recursive source/typed group count mismatch"
     ; bindings <- pairRecursiveNames resolution outer definitions actualDefinitions
     ; let  { names = L.map (\((,) ((,,) sourceName _ _) (RecursiveDefinition name _ _ _ _)) -> (,) sourceName name)
          (L.zip definitions actualDefinitions)
     }  ; let  { scope = M.union compareString (M.fromList compareString names) env
     }  ; rows <- pairRecursiveValues ds resolution scope path 0 definitions actualDefinitions
     ; tail <- pairCore ds resolution scope outer (pathChild path "body") body typedBody
     ; Right ((:) (originRow path generation "letrec" bindings) (L.append rows tail))
   }  ; (,) (CCoerce _) (FCoercion name _ _) -> do { checkFreshHint "coerce" name; Right [] }
   ; (,) (CInt a) (FIntegerLiteral b) -> do { L.ensure (a == b) "integer source/typed mismatch"; Right [] }
   ; (,) (CDouble a) (FDoubleLiteral b) -> do { L.ensure (doubleToBits a == doubleToBits b) "Double source/typed bit mismatch"; Right [] }
   ; (,) (CBool a) (FBooleanLiteral b) -> do { L.ensure (a == b) "Boolean source/typed mismatch"; Right [] }
   ; (,) (CString a) (FStringLiteral b) -> do { L.ensure (eqString a b) "String source/typed mismatch"; Right [] }
   ; (,) (CPrimitive a) (FPrimitive b args) -> do
     { L.ensure (Primitive.eqPrimitive a b && L.length args == L.length (L.fst (Primitive.primitiveSignature a))) "primitive source/typed identity or type arity mismatch"
     ; Right []
   }  ; (,) (CConstructor a) (FConstructor b args) -> do
     { declaration <- D.lookupConstructor ds a
     ; L.ensure (eqString a b && L.length args == L.length (D.datatypeBinders (L.fst declaration))) "constructor source/typed identity or arity mismatch"
     ; Right []
   }  ; (,) (CCase subject alternatives) (FMatch typedSubject _ branches) -> do
     { L.ensure (L.length alternatives == L.length branches) "case source/typed alternative count mismatch"
     ; first <- pairCore ds resolution env False (pathChild path "scrutinee") subject typedSubject
     ; rest <- pairBranches ds resolution env path 0 alternatives branches
     ; Right (L.append first rest)
   }  ; (,) (CWanted _ candidates) (FEvidence actualCandidates) -> do
     { pairEvidence env candidates actualCandidates
     ; Right []
   }  ; (,) (CChecked signature expression) (FChecked variables body _) -> do
     { let  { leading = Constraint.leadingVariables signature
     }  ; L.ensure (L.length (L.fst leading) == L.length variables && L.and (L.map
      (\((,) ((,) _ a) ((,) _ b)) -> L.eqKind a b) (L.zip (L.fst leading) variables)))
      "checked source/typed scoped variable mismatch"
     ; let  { expected = L.snd leading
     }  ; pairCore ds resolution env False path
      (Constraint.desugar (SAnn (Constraint.directed expected expression) (SAnnotation [] expected))) body
   }  ; _ -> Left "source Core/actual Typed skeleton constructor mismatch"

 }  ; pairRecursiveNames :: Modules.ResolvedCrate -> Bool -> [] ((,,) String RecursiveMode Core) -> [] RecursiveDefinition -> Either String ([] J.Json)
 ; pairRecursiveNames resolution outer sources actuals = case (,) sources actuals of
   { (,) [] [] -> Right []
   ; (,) ((:) ((,,) source mode _) ss) ((:) (RecursiveDefinition name _ _ _ closure) ns) -> do
     { case (,) mode closure of
       { (,) InferRecursive (Just _) -> Right ()
       ; (,) (CheckRecursive (SAnnotation [] _)) Nothing -> Right ()
       ; _ -> Left "recursive source/typed inference mode mismatch"
     }  ; first <- originBinding resolution outer source name
     ; rest <- pairRecursiveNames resolution outer ss ns
     ; Right ((:) first rest)
   }  ; _ -> Left "recursive source/typed binder order/count mismatch"

 }  ; pairRecursiveValues :: DataEnv -> Modules.ResolvedCrate -> Map String XName -> [] String -> Int -> [] ((,,) String RecursiveMode Core) -> [] RecursiveDefinition -> Either String ([] J.Json)
 ; pairRecursiveValues ds resolution env path index sources actuals = case (,) sources actuals of
   { (,) [] [] -> Right []
   ; (,) ((:) ((,,) _ _ source) ss) ((:) (RecursiveDefinition _ _ actual _ _) ns) -> do
     { first <- pairCore ds resolution env False (pathIndexed path "bindings" index "value") source actual
     ; rest <- pairRecursiveValues ds resolution env path (index + 1) ss ns
     ; Right (L.append first rest)
   }  ; _ -> Left "recursive source/typed RHS count mismatch"

 }  ; pairBranches :: DataEnv -> Modules.ResolvedCrate -> Map String XName -> [] String -> Int -> [] ((,) SPattern Core) -> [] Branch -> Either String ([] J.Json)
 ; pairBranches ds resolution env path index sources actuals = case (,) sources actuals of
   { (,) [] [] -> Right []
   ; (,) ((:) ((,) sourcePattern sourceBody) ss) ((:) (Branch actualPattern actualBody _) ns) -> do
     { scope <- pairPattern env sourcePattern actualPattern
     ; first <- pairCore ds resolution scope False (pathIndexed path "alternatives" index "body") sourceBody actualBody
     ; rest <- pairBranches ds resolution env path (index + 1) ss ns
     ; Right (L.append first rest)
   }  ; _ -> Left "source/typed branch count mismatch"
-- An explicit work list bounds recursive JSON encoding and association replay.
 }  ; data BudgetItem = BudgetTerm XTerm | BudgetType XType | BudgetProof XComputation |
  BudgetField Field | BudgetDeclaration DataDecl | BudgetKind Kind

 ; budgetChildren :: BudgetItem -> [] BudgetItem
 ; budgetChildren item = case item of
   { BudgetTerm term -> case term of
     { XVarTerm _ -> []
     ; XAbs _ ty body -> [BudgetType ty, BudgetTerm body]
     ; XApp f a -> [BudgetTerm f, BudgetTerm a]
     ; XTypeAbs _ bound body -> [BudgetType bound, BudgetTerm body]
     ; XTypeApp body proof -> [BudgetTerm body, BudgetProof proof]
     ; XLet _ rhs body -> [BudgetTerm rhs, BudgetTerm body]
     ; XLetRec bindings body -> L.append (L.concatMap (\((,,) _ ty rhs) -> [BudgetType ty, BudgetTerm rhs]) bindings) [BudgetTerm body]
     ; XIntTerm _ -> []
     ; XDoubleTerm _ -> []
     ; XBoolTerm _ -> []
     ; XStringTerm _ -> []
     ; XPrimitive _ args -> L.map BudgetType args
     ; XConstructor _ args -> L.map BudgetType args
     ; XCase subject ty alternatives -> L.append [BudgetTerm subject, BudgetType ty]
      (L.map (\(XAlternative _ body) -> BudgetTerm body) alternatives)
     ; XWithData declarations body -> L.append (L.map BudgetDeclaration declarations) [BudgetTerm body]
   }  ; BudgetType ty -> case ty of
     { XVar _ -> []
     ; XBot -> []
     ; XBotKind k -> [BudgetKind k]
     ; XArrow a b -> [BudgetType a, BudgetType b]
     ; XCon _ args -> L.map BudgetType args
     ; XApply f a -> [BudgetType f, BudgetType a]
     ; XForall _ bound body -> [BudgetType bound, BudgetType body]
   }  ; BudgetProof proof -> case proof of
     { XRefl -> []
     ; XBottom ty -> [BudgetType ty]
     ; XHyp _ -> []
     ; XInner p -> [BudgetProof p]
     ; XOuter _ p -> [BudgetProof p]
     ; XElim -> []
     ; XIntro _ -> []
     ; XIntroKind _ k -> [BudgetKind k]
     ; XThen a b -> [BudgetProof a, BudgetProof b]
   }  ; BudgetField field -> case field of
     { Parameter _ -> []
     ; Function a b -> [BudgetField a, BudgetField b]
     ; Applied _ args -> L.map BudgetField args
     ; Application f a -> [BudgetField f, BudgetField a]
     ; Quantified _ k body -> [BudgetKind k, BudgetField body]
   }  ; BudgetDeclaration declaration -> L.append (L.map (L.compose BudgetKind L.snd) (D.datatypeBinders declaration))
    (L.concatMap (\(ConstructorDecl _ fields) -> L.map BudgetField fields) (D.datatypeConstructors declaration))
   ; BudgetKind kind -> case kind of { Star -> []; KArrow a b -> [BudgetKind a, BudgetKind b] }

 }  ; checkBudget :: Int -> [] ((,) Int BudgetItem) -> Either String ()
 ; checkBudget count pending = case pending of
   { [] -> Right ()
   ; (:) ((,) depth node) rest -> do
     { L.ensure (count < 100000 && depth <= 1024) "module evidence exceeds node/depth admission budget"
     ; let  { next = count + 1
     }  ; seq next (checkBudget next (L.append (L.map (\child -> (,) (depth + 1) child) (budgetChildren node)) rest))

 }  }  ; boundedUTF8 :: String -> Either String Int
 ; boundedUTF8 text = utf8Loop text 0 0

 ; utf8Loop :: String -> Int -> Int -> Either String Int
 ; utf8Loop text index count =
  if index >= stringLength text then Right count else do
     { let  { code = stringCodeAt text index
     }  ; let  { width = if code < 128 then 1 else if code < 2048 then 2 else if code < 65536 then 3 else 4
     }  ; let  { next = count + width
     }  ; L.ensure (next <= 1048576) "captured module exceeds 1MiB UTF-8 budget"
     ; seq next (utf8Loop text (index + 1) next)

 }  ; slashParts :: String -> Int -> Int -> [] String
 ; slashParts text start index =
  if index >= stringLength text then [stringSlice text start (index - start)]
  else if stringCodeAt text index == 47 then (:) (stringSlice text start (index - start)) (slashParts text (index + 1) (index + 1))
  else slashParts text start (index + 1)

 ; safeGuestPath :: String -> Bool
 ; safeGuestPath recorded = let
   { path = if stringLength recorded >= 2 && eqString (stringSlice recorded 0 2) "./"
    then stringSlice recorded 2 (stringLength recorded - 2) else recorded
   ; n = stringLength path
   ; parts = slashParts path 0 0
   ; safePart part = L.not (eqString part "" || eqString part "." || eqString part "..") && safeChars part 0
   ; safeChars text index = if index >= stringLength text then True else
    let  { code = stringCodeAt text index  } in code /= 92 && code /= 0 && safeChars text (index + 1)
   } in n >= 5 && eqString (stringSlice path (n - 5) 5) ".emlf" && L.all safePart parts

 ; validateLoaded :: SourceModule -> Modules.LoadedModules -> Either String ()
 ; validateLoaded root loaded = do
   { let  { entries = Modules.loadedEntries loaded
   }  ; L.ensure (L.not (L.null entries) && L.length entries <= 33) "module capture requires root plus at most 32 guests"
   ; L.ensure (L.eqList eqString (Modules.moduleSearchPaths [] root) ["."]) "module capture search roots differ from private snapshot cwd"
   ; sizes <- L.traverseEither (\entry -> do
     { let  { source = Modules.loadedSource entry
     }  ; L.ensure (case Modules.sourceSyntax source of { LegacyEmlfV1 -> True; _ -> False }) "module capture admits legacy EMLF guests only"
     ; L.ensure (eqString (Modules.sourcePath source) "<stdin>" || safeGuestPath (Modules.sourcePath source))
      "actual guest path is not a bounded snapshot-relative .emlf source"
     ; boundedUTF8 (Modules.loadedText entry) } ) entries
   ; L.ensure (L.foldl (+) 0 sizes <= 8388608) "captured source closure exceeds 8MiB UTF-8 budget"
   ; L.ensure (eqString (Modules.sourcePath (Modules.loadedSource (L.last entries))) "<stdin>" &&
    L.length (L.filter (\entry -> eqString (Modules.sourcePath (Modules.loadedSource entry)) "<stdin>") entries) == 1)
    "loaded root marker does not identify exactly the original stdin payload"

-- Canonical metadata checks do not reopen or replace captured parser bytes.
-- The public runner additionally authenticates the entire immutable snapshot.
 }  ; validateLoadedPaths :: Modules.LoadedModules -> IO (Either String ())
 ; validateLoadedPaths loaded = do
   { root <- canonicalPath "."
   ; checkLoadedPaths root (Modules.loadedEntries loaded)

 }  ; checkLoadedPaths :: String -> [] Modules.LoadedModule -> IO (Either String ())
 ; checkLoadedPaths root entries = case entries of
   { [] -> ioReturn (Right ())
   ; (:) entry rest -> let  { recorded = Modules.sourcePath (Modules.loadedSource entry)  } in
    if eqString recorded "<stdin>" then checkLoadedPaths root rest
    else if L.not (safeGuestPath recorded) then ioReturn (Left "unsafe actual guest source path")
    else do
       { actual <- canonicalPath recorded
       ; let  { relative = if stringLength recorded >= 2 && eqString (stringSlice recorded 0 2) "./"
            then stringSlice recorded 2 (stringLength recorded - 2) else recorded
       }  ; if L.not (eqString actual (Modules.joinPath root relative))
        then ioReturn (Left "actual guest path escapes the snapshot or crosses a symlink")
        else checkLoadedPaths root rest

 }  }  ; validateBinderIdentities :: IntSet -> [] XTerm -> Either String ()
 ; validateBinderIdentities seen pending = case pending of
   { [] -> Right ()
   ; (:) term rest -> do
     { let  { binderIdentityParts = case term of
           { XAbs n _ body -> (,) [n] [body]
           ; XLet n rhs body -> (,) [n] [rhs, body]
           ; XLetRec bindings body -> (,) (L.map (\((,,) n _ _) -> n) bindings)
            (L.append (L.map (\((,,) _ _ rhs) -> rhs) bindings) [body])
           ; XApp f a -> (,) [] [f, a]
           ; XTypeAbs _ _ body -> (,) [] [body]
           ; XTypeApp body _ -> (,) [] [body]
           ; XCase subject _ alternatives -> (,) (L.concatMap (\(XAlternative pattern _) -> X.patternNames pattern) alternatives)
            ((:) subject (L.map (\(XAlternative _ body) -> body) alternatives))
           ; XWithData _ body -> (,) [] [body]
           ; _ -> (,) [] []
         }  ; names = L.fst binderIdentityParts
         ; children = L.snd binderIdentityParts
     }  ; let  { ids = L.map X.nameId names
     }  ; L.ensure (L.all (\n -> n >= 0 && L.not (IS.member n seen)) ids && IS.size (IS.fromList ids) == L.length ids)
      "module checked binding graph repeats or rebinds a term identity"
     ; validateBinderIdentities (L.foldl (\state n -> IS.insert n state) seen ids) (L.append children rest)

 }  }  ; capturedCustody :: SourceModule -> Modules.LoadedModules -> Modules.ResolvedCrate -> J.Json
 ; capturedCustody root loaded resolution = J.Object
  [("policy", J.String "legacy-single-root/1"), ("root_file", J.String "<stdin>"),
   ("prelude", J.String "NoImplicitPrelude"), ("include_paths", J.Array []),
   ("search_paths", J.Array (L.map J.String (Modules.moduleSearchPaths [] root))),
   ("loaded", J.Array (L.map (\entry -> let  { source = Modules.loadedSource entry  } in J.Object
     [("source", sourceNode source), ("text", J.String (Modules.loadedText entry)),
      ("is_root", J.Boolean (eqString (Modules.sourcePath source) "<stdin>"))]) (Modules.loadedEntries loaded))),
   ("resolution", resolutionNode resolution)]

-- Compare the replay's binding rows to a separately traversed actual erasure.
-- Unknown evidence-generated let shapes are conservatively outside this route.
 ; erasedBindingRows :: [] String -> XErased -> [] J.Json
 ; erasedBindingRows path term = case term of
   { XELet name rhs body -> (:) (J.Object [("path", J.Array (L.map J.String path)), ("kind", J.String "let"),
      ("names", J.Array [nameNode name])])
    (L.append (erasedBindingRows (pathChild path "value") rhs) (erasedBindingRows (pathChild path "body") body))
   ; XELetRec bindings body -> (:) (J.Object [("path", J.Array (L.map J.String path)), ("kind", J.String "letrec"),
      ("names", J.Array (L.map (L.compose nameNode L.fst) bindings))])
    (L.append (L.concat (L.mapIndexed (\index ((,) _ rhs) -> erasedBindingRows (pathIndexed path "bindings" index "value") rhs) bindings))
      (erasedBindingRows (pathChild path "body") body))
   ; XEAbs _ body -> erasedBindingRows (pathChild path "body") body
   ; XEApp f a -> L.append (erasedBindingRows (pathChild path "function") f) (erasedBindingRows (pathChild path "argument") a)
   ; XECase subject alternatives -> L.append (erasedBindingRows (pathChild path "scrutinee") subject)
    (L.concat (L.mapIndexed (\index (XErasedAlternative _ body) -> erasedBindingRows (pathIndexed path "alternatives" index "body") body) alternatives))
   ; _ -> []

 }  ; originRowView :: J.Json -> J.Json
 ; originRowView row = J.Object [("path", J.get "path" row), ("kind", J.get "kind" row),
  ("names", J.Array (L.map (J.get "name") (J.values (J.get "bindings" row))))]

 ; captureOrigins :: Modules.ResolvedCrate -> Core.CompilationEvidence -> Either String J.Json
 ; captureOrigins resolution evidence = case Core.evidenceProgram evidence of
   { SClassProgram _ _ _ _ -> Left "module association expected the actual class-lowered core program"
   ; SProgram declarations expression -> do
     { ds <- D.validateDeclarations declarations
     ; lowered <- Surface.lowerExpression expression
     ; Constraint.validateAnnotations ds lowered
     ; let  { source = Constraint.desugar lowered
     }  ; rows <- pairCore ds resolution M.empty True [] source (Core.evidenceSkeleton evidence)
     ; let  { erasedRows = erasedBindingRows [] (Core.evidenceErasure evidence)
     }  ; L.ensure (J.equal (J.Array (L.map originRowView rows)) (J.Array erasedRows))
      "paired source/Typed bindings do not equal the original checked source-erasure binding graph"
     ; Right (J.Object [("policy", J.String "constraint-core-association/1"),
      ("source_program", J.Object [("declarations", rawDeclarations declarations), ("body", sourceExprNode expression)]),
      ("lowered_expression", sourceExprNode lowered), ("source_core", coreNode source),
      ("typed_skeleton", typedNode (Core.evidenceSkeleton evidence)),
      ("resolved_evidence", J.Array (L.map (\((,) gen term) -> J.Object [("generation", J.num gen), ("term", rawTerm term)])
        (IM.toList (Core.evidenceTerms evidence)))),
      ("bindings", J.Array rows), ("erased_bindings", J.Array erasedRows)])

 }  }  ; data CapturedCompilation = CapturedCompilation K.CheckedTerm J.Json XErased J.Json

 ; checkedTerm :: CapturedCompilation -> K.CheckedTerm
 ; checkedTerm (CapturedCompilation checked _ _ _) = checked
 ; moduleCustody :: CapturedCompilation -> J.Json
 ; moduleCustody (CapturedCompilation _ custody _ _) = custody
 ; sourceErasure :: CapturedCompilation -> XErased
 ; sourceErasure (CapturedCompilation _ _ erased _) = erased
 ; binderOrigins :: CapturedCompilation -> J.Json
 ; binderOrigins (CapturedCompilation _ _ _ origins) = origins

 ; compileCaptured :: String -> String -> IO (Either CompileError CapturedCompilation)
 ; compileCaptured file input = case Core.atPhase Parsing (Parser.parseModule file input) of
   { Left error -> ioReturn (Left error)
   ; Right root -> case Core.atPhase ModuleResolution (do
       { L.ensure (eqString file "<stdin>") "module capture requires the exact stdin root path"
       ; L.ensure (case Modules.sourceModuleName root of { Nothing -> True; Just _ -> False }) "module capture requires a headerless root"
       ; L.ensure (L.not (L.null (Modules.sourceImports root))) "module capture requires actual imports"
       ; L.ensure (case Modules.sourceSyntax root of { LegacyEmlfV1 -> True; _ -> False }) "module capture requires legacy EMLF root syntax"
       ; Right () } ) of
     { Left error -> ioReturn (Left error)
     ; Right () -> do
       { loaded <- Modules.loadModuleFilesWithEvidenceUsing Parser.parseModule [] root input
       ; paths <- case loaded of
         { Left _ -> ioReturn (Right ())
         ; Right graph -> validateLoadedPaths graph
       }  ; ioReturn (do
         { graph <- Core.atPhase ModuleResolution loaded
         ; Core.atPhase ModuleResolution paths
         ; Core.atPhase ModuleResolution (validateLoaded root graph)
         ; pair <- Core.atPhase ModuleResolution (Modules.linkModulesWithResolution NoImplicitPrelude (Modules.loadedSources graph))
         ; case pair of
           { (,) (LinkedModule program names valueScopes instanceScopes) resolution -> do
             { let  { display = Modules.displayNames names
             }  ; canonical <- Core.atPhase Inference (L.mapLeft display (Classes.canonicalSourceProgram S.empty program))
             ; lowered <- Core.atPhase Inference (L.mapLeft display (Classes.lowerClassesWithScopes valueScopes instanceScopes canonical))
             ; let  { diagnosticNames = M.union compareString (M.map display (L.snd lowered)) names
             }  ; evidence <- L.mapLeft (\(CompileError phase message) -> CompileError phase (Modules.displayNames diagnosticNames message))
              (Core.finishCompilationWithEvidence lowered)
             ; let  { checked = Core.checkedTerm (Core.evidenceCompilation evidence)
             }  ; Core.atPhase Verification (checkBudget 0 [(,) 1 (BudgetTerm (K.term checked))])
             ; Core.atPhase Verification (validateBinderIdentities IS.empty [K.term checked])
             ; origins <- Core.atPhase Verification (captureOrigins resolution evidence)
             ; Right (CapturedCompilation checked (capturedCustody root graph resolution) (Core.evidenceErasure evidence) origins) }  }  } )
 }  }  }  }
