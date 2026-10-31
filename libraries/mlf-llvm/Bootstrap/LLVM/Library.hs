-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Library
  (ExportLayout, prepareLayout, prepareLayoutWithTypeNames, identity, exports, declarations, constructorTags,
   reservedTypeNames, libraryTypeNames, rootConstructorTags, libraryTerm, emitLibrary, emitRoot) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.LLVM.Codegen as Codegen;
  import qualified Bootstrap.LLVM.Optimize as Optimize;

  -- Layout validity is not native-object authentication. The consumer must
  -- bind these compiler-owned fields to its independently verified installed
  -- object/runtime identities before linking. No raw native object is a
  -- CheckedTerm, and no alleged result type is accepted by emitRoot.
  data ExportLayout = ExportLayout String ([] ((,,) String String XType)) ([] DataDecl) (Maybe (Set String));
  identity :: ExportLayout -> String;
  identity (ExportLayout value _ _ _) = value;
  exports :: ExportLayout -> [] ((,,) String String XType);
  exports (ExportLayout _ value _ _) = value;
  declarations :: ExportLayout -> [] DataDecl;
  declarations (ExportLayout _ _ value _) = value;
  digest :: String -> Bool;
  digest value = stringLength value == 64 && all (\index -> let {
    code = stringCodeAt value index
  } in (code >= 48 && code <= 57) || (code >= 97 && code <= 102)) (range 0 63);
  exportKey :: (,,) String String XType -> String;
  exportKey ((,,) key _ _) = key;
  exportHint :: (,,) String String XType -> String;
  exportHint ((,,) _ hint _) = hint;
  prepareLayout :: String -> [] ((,,) String String XType) -> [] DataDecl -> Either String ExportLayout;
  prepareLayout input entries ds = do {
    ensure (digest input) "native library requires a SHA256 installation identity";
    ensure (length entries == length (nubBy eqString (map exportKey entries))) "native library duplicate export key";
    ensure (length entries == length (nubBy eqString (map exportHint entries))) "native library ambiguous export hint";
    ensure (all (\entry -> not (eqString (exportKey entry) "") && not (eqString (exportHint entry) "")) entries)
      "native library empty export identity";
    context <- D.validateDeclarations ds;
    traverseEither (\((,,) _ _ ty) -> do {
      ensure (S.null (T.freeVars ty)) "native library export contract is not closed";
      kind <- T.kindOf context M.empty ty;
      ensure (eqKind kind Star) "native library export contract does not have kind *"
    }) entries;
    Right (ExportLayout input entries ds Nothing)
  };
  -- This is sealed schema data, not a proof manufactured by the caller.
  -- emitLibrary checks its exact census against the actual checked code; the
  -- consumer authenticates the corresponding compiled installation registry.
  prepareLayoutWithTypeNames :: String -> [] ((,,) String String XType) -> [] DataDecl -> [] String -> Either String ExportLayout;
  prepareLayoutWithTypeNames input entries ds names = do {
    prepareLayout input entries ds;
    let { known = S.fromList compareString names };
    ensure (eqList eqString names (S.toList known) && all (\name -> not (eqString name "")) names)
      "native library type-name census is not canonical";
    Right (ExportLayout input entries ds (Just known))
  };
  reservedTypeNames :: ExportLayout -> [] String;
  reservedTypeNames (ExportLayout _ _ _ known) = case known of { Nothing -> []; Just names -> S.toList names };
  constructorTags :: ExportLayout -> Map String ((,) Int Int);
  constructorTags layout = contextTags (declarations layout);
  contextTags :: [] DataDecl -> Map String ((,) Int Int);
  contextTags ds = let {
    builtins = concatMap LLVM.dataConstructors D.builtinDeclarations;
    builtinNames = map D.constructorName builtins;
    users = filter (\c -> not (elem eqString (D.constructorName c) builtinNames))
      (concatMap LLVM.dataConstructors ds)
  } in M.fromList compareString
    (zipWith LLVM.constructorEntry (range 0 (length builtins + length users - 1)) (append builtins users));
  symbol :: ExportLayout -> String;
  symbol layout = "mlf_fixed_" ++ identity layout;

  -- Every leaf has its own closed type, including impredicative forall types.
  -- Existing checked pairs provide the heterogeneous product; no casts, holes
  -- or additional erased term constructors are involved.
  data Product = Product XTerm XType ([] ((,) Int ([] Int)));
  buildProduct :: [] ((,,) Int XName XType) -> Product;
  buildProduct entries = case entries of {
    [] -> Product (XConstructor "()" []) (XCon "()" []) [];
    [((,,) slot name ty)] -> Product (XVarTerm name) ty [(,) slot []];
    _ -> let {
      middle = length entries / 2;
      left = buildProduct (take middle entries);
      right = buildProduct (drop middle entries)
    } in case (,) left right of {
      (,) (Product a ta pathsA) (Product b tb pathsB) ->
        Product (XApp (XApp (XConstructor "(,)" [ta,tb]) a) b) (XCon "(,)" [ta,tb])
          (append (map (\((,) slot path) -> (,) slot ((:) 0 path)) pathsA)
            (map (\((,) slot path) -> (,) slot ((:) 1 path)) pathsB))
    }
  };
  exportEntries :: ExportLayout -> [] ((,,) Int XName XType);
  exportEntries layout = zipWith (\slot ((,,) _ hint ty) -> (,,) slot (XName slot hint) ty)
    (range 0 (length (exports layout) - 1)) (exports layout);
  envelope :: ExportLayout -> Product;
  envelope layout = case buildProduct (exportEntries layout) of {
    Product body ty paths ->
      -- Even one export must remain a lazy field, never the evaluated root.
      Product (XApp (XApp (XConstructor "(,)" [XCon "()" [],ty]) (XConstructor "()" [])) body)
        (XCon "(,)" [XCon "()" [],ty])
        (map (\((,) slot path) -> (,) slot ((:) 1 path)) paths)
  };
  libraryTerm :: ExportLayout -> Checked.LinkedSpine -> Either String Checked.CheckedTerm;
  libraryTerm layout linked = do {
    let { body = case envelope layout of { Product value _ _ -> value };
          wrapped = foldr (\((,,) _ name ty) rest -> XAbs name ty rest) (XLetRec [] body)
            (exportEntries layout) };
    checked <- Checked.check (XWithData (declarations layout) wrapped);
    combined <- Checked.finishSpine linked
      (map (\((,,) key hint _) -> (,) key hint) (exports layout)) checked;
    -- Installation is outside user compilation. Keep an independent complete
    -- check here in addition to composition evidence, once per installed build.
    independent <- Checked.check (Checked.term combined);
    ensure (T.alphaEq (Checked.typeOf independent) (Checked.typeOf combined))
      "native library independent product check changed type";
    Right combined
  };
  typeNames :: XType -> Set String;
  typeNames ty = case ty of {
    XCon name arguments -> S.insert compareString name (S.unions compareString (map typeNames arguments));
    XArrow a b -> S.union compareString (typeNames a) (typeNames b);
    XApply a b -> S.union compareString (typeNames a) (typeNames b);
    XForall _ bound body -> S.union compareString (typeNames bound) (typeNames body);
    _ -> S.empty
  };
  fieldNames :: Field -> Set String;
  fieldNames field = case field of {
    Parameter _ -> S.empty;
    Function a b -> S.union compareString (fieldNames a) (fieldNames b);
    Applied name arguments -> S.insert compareString name (S.unions compareString (map fieldNames arguments));
    Application a b -> S.union compareString (fieldNames a) (fieldNames b);
    Quantified _ _ body -> fieldNames body
  };
  declarationNames :: DataDecl -> Set String;
  declarationNames declaration = S.insert compareString (D.datatypeName declaration)
    (S.unions compareString (concatMap (\constructor -> map fieldNames (D.constructorFields constructor))
      (D.datatypeConstructors declaration)));
  proofNames :: XComputation -> Set String;
  proofNames proof = case proof of {
    XBottom ty -> typeNames ty;
    XInner body -> proofNames body;
    XOuter _ body -> proofNames body;
    XThen a b -> S.union compareString (proofNames a) (proofNames b);
    _ -> S.empty
  };
  termNames :: XTerm -> Set String;
  termNames source = let { join = S.unions compareString } in case source of {
    XAbs _ annotation body -> join [typeNames annotation, termNames body];
    XApp a b -> join [termNames a, termNames b];
    XTypeAbs _ bound body -> join [typeNames bound, termNames body];
    XTypeApp body proof -> join [termNames body, proofNames proof];
    XLet _ rhs body -> join [termNames rhs, termNames body];
    XLetRec definitions body -> join ((:) (termNames body)
      (concatMap (\((,,) _ annotation rhs) -> [typeNames annotation, termNames rhs]) definitions));
    XPrimitive _ arguments -> join (map typeNames arguments);
    XConstructor _ arguments -> join (map typeNames arguments);
    XCase subject result alternatives -> join ((:) (termNames subject) ((:) (typeNames result)
      (map (\(XAlternative _ body) -> termNames body) alternatives)));
    XWithData ds body -> join ((:) (termNames body) (map declarationNames ds));
    _ -> S.empty
  };
  checkedTypeNames :: ExportLayout -> Checked.CheckedTerm -> [] String;
  checkedTypeNames layout checked = S.toList (S.unions compareString
    [termNames (Checked.term checked), typeNames (Checked.typeOf checked),
     S.unions compareString (map (\((,,) _ _ ty) -> typeNames ty) (exports layout)),
     S.unions compareString (map declarationNames (append D.builtinDeclarations (declarations layout))),
     S.fromList compareString (M.keys D.primitiveKinds)]);
  libraryTypeNames :: ExportLayout -> Checked.LinkedSpine -> Either String ([] String);
  libraryTypeNames layout linked = mapEither (checkedTypeNames layout) (libraryTerm layout linked);
  generate :: [] DataDecl -> [] DataDecl -> Checked.CheckedTerm -> Either String ((,) String ([] String));
  generate private ds checked = let {
    cs = contextTags ds;
    -- Whole-program strict-wrapper erasure changes constructor representation.
    -- Independently compiled library and root cannot infer the same candidate
    -- set, so this boundary always preserves the ordinary boxed datatype ABI.
    optimized = Optimize.optimize (X.erase (Checked.term checked));
    -- The installed nominal census rules out independent library construction
    -- of these fresh root types. Their local sites still undergo the ordinary
    -- all-site/escaping-constructor proof; shared constructors remain open.
    names = S.fromList compareString (concatMap (\d -> map D.constructorName (D.datatypeConstructors d)) private)
  } in Codegen.generateWithPrivate names cs optimized;
  header :: [] String;
  header = ["; Generated from checked xMLF and an authenticated fixed native library boundary.",
    "source_filename = \"emlf-fixed-native\"", ""];
  abi :: [] String;
  abi = ["declare void @mlf_require_haskell_boundary_v4_abi()"];
  chunks :: [] String -> [] String;
  chunks = map (\line -> line ++ "\n");
  emitLibrary :: ExportLayout -> Checked.LinkedSpine -> Either String ([] String);
  emitLibrary layout linked = do {
    checked <- libraryTerm layout linked;
    case layout of {
      ExportLayout _ _ _ Nothing -> Right ();
      ExportLayout _ _ _ (Just known) -> ensure
        (eqList eqString (S.toList known) (checkedTypeNames layout checked))
        "native library type-name census differs from actual checked code"
    };
    generated <- generate [] (declarations layout) checked;
    let { paths = case envelope layout of { Product _ _ value -> value } };
    Right (chunks (concat [header, snd generated, abi, libraryAdapter layout (fst generated) paths]))
  };
  -- The installed constructor prefix is independent of root declaration order.
  -- Fresh declarations may not change a nominal constant used by installed code.
  rootContext :: ExportLayout -> [] DataDecl -> Either String ([] DataDecl);
  rootContext layout ds = do {
    let { installed = declarations layout;
          oldNames = map D.datatypeName installed;
          fresh = filter (\d -> not (elem eqString (D.datatypeName d) oldNames)) ds };
    ensure (all (\d -> any (\actual -> eqString (D.prettyDeclaration d) (D.prettyDeclaration actual)) ds) installed)
      "native root changed or omitted an installed datatype";
    case layout of {
      ExportLayout _ _ _ Nothing -> ensure (null fresh)
        "native root datatype extension requires an installed type-name census";
      ExportLayout _ _ _ (Just known) -> ensure
        (all (\d -> not (S.member compareString (D.datatypeName d) known)) fresh)
        "native root datatype extension changes an installed nominal type"
    };
    D.validateDeclarations ds;
    let { combined = append installed fresh };
    D.validateDeclarations combined;
    Right combined
  };
  rootConstructorTags :: ExportLayout -> [] DataDecl -> Either String (Map String ((,) Int Int));
  rootConstructorTags layout ds = mapEither contextTags (rootContext layout ds);
  rootParameters :: Map String ((,) Int ((,) String XType)) -> [] String -> XTerm -> XType ->
                    Either String ((,) ([] Int) XType);
  rootParameters available keys term ty = case keys of {
    [] -> Right ((,) [] ty);
    (:) key rest -> case M.lookup compareString key available of {
      Nothing -> Left "native root requested an uninstalled export";
      Just ((,) slot ((,) hint expected)) -> case (,) term ty of {
        (,) (XAbs name actual body) (XArrow parameter result) -> do {
          ensure (eqString (X.nameHint name) hint && T.alphaEq expected actual && T.alphaEq expected parameter)
            "native root import wrapper does not match installed contract";
          next <- rootParameters available rest body result;
          Right ((,) ((:) slot (fst next)) (snd next))
        };
        _ -> Left "native root lost its checked import arrow"
      }
    }
  };
  emitRoot :: ExportLayout -> [] String -> Checked.CheckedTerm -> Either String ([] String);
  emitRoot layout selected checked = do {
    ensure (length selected == length (nubBy eqString selected)) "native root duplicate import key";
    let { parts = case Checked.term checked of { XWithData ds body -> (,) ds body; body -> (,) [] body } };
    ds <- rootContext layout (fst parts);
    let { available = M.fromList compareString
      (zipWith (\slot ((,,) key hint ty) -> (,) key ((,) slot ((,) hint ty)))
        (range 0 (length (exports layout) - 1)) (exports layout)) };
    imports <- rootParameters available selected (snd parts) (Checked.typeOf checked);
    generated <- generate (drop (length (declarations layout)) ds) ds checked;
    Right (chunks (concat [header, snd generated, rootAdapter layout (fst generated) (fst imports) (LLVM.ioType (snd imports))]))
  };
  libraryAdapter :: ExportLayout -> String -> [] ((,) Int ([] Int)) -> [] String;
  libraryAdapter layout entry paths = let { prefix = symbol layout; count = length (exports layout) } in
    append ["@" ++ prefix ++ "_root = private global ptr null, align 8",
      "@" ++ prefix ++ "_slots = private global [" ++ showInt count ++ " x ptr] zeroinitializer, align 8",
      "@" ++ prefix ++ "_state = private global i32 0, align 4",
      "declare void @llvm.trap()",
      "define private void @" ++ prefix ++ "_init() {", "entry:",
      "  %state = load i32, ptr @" ++ prefix ++ "_state",
      "  switch i32 %state, label %cycle [ i32 0, label %start i32 2, label %done ]",
      "cycle:", "  call void @llvm.trap()", "  unreachable", "start:",
      "  store i32 1, ptr @" ++ prefix ++ "_state",
      "  call void @mlf_require_haskell_boundary_v4_abi()",
      "  %root = call ptr " ++ entry ++ "(ptr null, ptr null)",
      "  store ptr %root, ptr @" ++ prefix ++ "_root, align 8"]
      (append (concatMap (slotCode prefix count) paths)
        ["  store i32 2, ptr @" ++ prefix ++ "_state", "  br label %done", "done:", "  ret void", "}",
         "define ptr @" ++ prefix ++ "_get(i64 %index) {", "entry:",
         "  call void @" ++ prefix ++ "_init()",
         "  %valid = icmp ult i64 %index, " ++ showInt count,
         "  br i1 %valid, label %read, label %invalid", "invalid:", "  call void @llvm.trap()", "  unreachable", "read:",
         "  %slot = getelementptr [" ++ showInt count ++ " x ptr], ptr @" ++ prefix ++ "_slots, i64 0, i64 %index",
         "  %value = load ptr, ptr %slot, align 8", "  ret ptr %value", "}"]);
  slotCode :: String -> Int -> (,) Int ([] Int) -> [] String;
  slotCode prefix count ((,) slot path) = let {
    local = "%export" ++ showInt slot;
    steps = zipWith (\depth branch ->
      "  " ++ local ++ "_" ++ showInt depth ++ " = call ptr @mlf_field(ptr " ++
      (if depth == 0 then "%root" else local ++ "_" ++ showInt (depth - 1)) ++ ", i64 " ++ showInt branch ++ ")")
      (range 0 (length path - 1)) path;
    value = if null path then "%root" else local ++ "_" ++ showInt (length path - 1)
  } in append steps ["  " ++ local ++ "_slot = getelementptr [" ++ showInt count ++ " x ptr], ptr @" ++ prefix ++
      "_slots, i64 0, i64 " ++ showInt slot,
      "  store ptr " ++ value ++ ", ptr " ++ local ++ "_slot, align 8"];
  rootAdapter :: ExportLayout -> String -> [] Int -> Bool -> [] String;
  rootAdapter layout entry imports executeIO = let { prefix = symbol layout } in
    concat [abi,
      ["declare ptr @" ++ prefix ++ "_get(i64)", "define ptr @mlf_entry() {", "entry:",
       "  call void @mlf_require_haskell_boundary_v4_abi()",
       "  %wrapper = call ptr " ++ entry ++ "(ptr null, ptr null)"],
      concat (zipWith (\index slot ->
        ["  %import" ++ showInt index ++ " = call ptr @" ++ prefix ++ "_get(i64 " ++ showInt slot ++ ")",
         "  %apply" ++ showInt index ++ " = call ptr @mlf_application(ptr " ++
         (if index == 0 then "%wrapper" else "%apply" ++ showInt (index - 1)) ++
         ", ptr %import" ++ showInt index ++ ")"]) (range 0 (length imports - 1)) imports),
      ["  %result = call ptr @mlf_force(ptr " ++
         (if null imports then "%wrapper" else "%apply" ++ showInt (length imports - 1)) ++ ")",
       "  ret ptr %result", "}", "define i32 @main(i32 %argc, ptr %argv) {", "entry:",
       "  call void @mlf_set_args(i32 %argc, ptr %argv)", "  %root = call ptr @mlf_entry()",
       "  %status = call i32 @mlf_run(ptr %root, i64 " ++ (if executeIO then "1" else "0") ++ ")",
       "  ret i32 %status", "}"]];
}
