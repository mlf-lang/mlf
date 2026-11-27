-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Library
  (ExportLayout, prepareLayout, prepareLayoutWithTypeNames, prepareLayoutIds, withTypeNames, identity, exports, declarations,
   reservedTypeNames, libraryTypeNames, libraryTerm,
   exportProduct, exportProductType, projectExport, closedCrateTypes, emitCrateLibrary, emitCrateProgram, crateConstructorTags) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
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
  -- CheckedTerm, and no alleged result type is accepted by emitCrateProgram.
  -- A root and its library share an ABI order but may allocate different
  -- declaration slots. The numeric ABI slot is used only at the LLVM boundary.
  data AbiSlot = AbiSlot;
  data ExportRows = ExportRows (V.IndexVec AbiSlot ((,) (V.Index Declaration) ((,,) String String XType)))
    (Map String (V.Index Declaration)) (IntMap (V.Index AbiSlot));
  data ExportLayout = ExportLayout String ExportRows ([] DataDecl) (Maybe (Set String));
  exportRows (ExportLayout _ rows _ _) = rows;
  identity :: ExportLayout -> String;
  identity (ExportLayout value _ _ _) = value;
  exports :: ExportLayout -> [] ((,,) String String XType);
  exports (ExportLayout _ (ExportRows rows _ _) _ _) = map snd (V.toList rows);
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
  prepareLayout input entries ds = prepareLayoutIds input
    (zip (map V.fromInt (range 0 (length entries - 1))) entries) ds;
  prepareLayoutIds :: String -> [] ((,) (V.Index Declaration) ((,,) String String XType)) ->
    [] DataDecl -> Either String ExportLayout;
  prepareLayoutIds input indexed ds = do {
    let { entries = map snd indexed; rows = V.fromList indexed;
          byKey = M.fromList compareString (map (\((,) d entry) -> (,) (exportKey entry) d) indexed);
          byDecl = IM.fromList (map (\slot -> (,) (V.toInt (fst (V.at rows slot))) slot) (V.indices rows)) };
    ensure (digest input) "native library requires a SHA256 installation identity";
    ensure (length entries == M.size byKey) "native library duplicate export key";
    ensure (length entries == S.size (S.fromList compareString (map exportHint entries))) "native library ambiguous export hint";
    ensure (all (\entry -> not (eqString (exportKey entry) "") && not (eqString (exportHint entry) "")) entries)
      "native library empty export identity";
    ensure (all (\r -> V.toInt (fst r) >= 0) indexed && IM.size byDecl == length entries)
      "native library duplicate or invalid declaration slot";
    context <- D.validateDeclarations ds;
    traverseEither (\((,,) _ _ ty) -> do {
      ensure (S.null (T.freeVars ty)) "native library export contract is not closed";
      kind <- T.kindOf context M.empty ty;
      ensure (eqKind kind Star) "native library export contract does not have kind *"
    }) entries;
    Right (ExportLayout input (ExportRows rows byKey byDecl) ds Nothing)
  };
  -- This is sealed schema data, not a proof manufactured by the caller.
  -- emitCrateLibrary checks its exact census against the actual checked code; the
  -- consumer authenticates the corresponding compiled installation registry.
  prepareLayoutWithTypeNames :: String -> [] ((,,) String String XType) -> [] DataDecl -> [] String -> Either String ExportLayout;
  prepareLayoutWithTypeNames input entries ds names = do {
    base <- prepareLayout input entries ds;
    withTypeNames base names
  };
  withTypeNames :: ExportLayout -> [] String -> Either String ExportLayout;
  withTypeNames (ExportLayout input rows ds _) names = do {
    let { known = S.fromList compareString names };
    ensure (eqList eqString names (S.toList known) && all (\name -> not (eqString name "")) names)
      "native library type-name census is not canonical";
    Right (ExportLayout input rows ds (Just known))
  };
  reservedTypeNames :: ExportLayout -> [] String;
  reservedTypeNames (ExportLayout _ _ _ known) = case known of { Nothing -> []; Just names -> S.toList names };
  builtinConstructorTags :: Map String ((,) Int Int);
  builtinConstructorTags = let {
    builtins = concatMap LLVM.dataConstructors D.builtinDeclarations
  } in M.fromList compareString
    (zipWith LLVM.constructorEntry (range 0 (length builtins - 1)) builtins);

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
  exportEntries layout = case exportRows layout of {
    ExportRows rows _ _ -> map (\slot -> case snd (V.at rows slot) of {
      (,,) _ hint ty -> (,,) (V.toInt slot) (XName (V.toInt slot) hint) ty
    }) (V.indices rows)
  };
  envelope :: ExportLayout -> Product;
  envelope layout = wrapProduct (exportEntries layout);
  wrapProduct entries = case buildProduct entries of {
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
    XInstantiationSpine _ rows -> join (concatMap (\((,,) constructor _ value) ->
      [S.singleton constructor,termNames value]) rows);
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
  generateWithTags :: Map String ((,) Int Int) -> Checked.CheckedTerm -> Either String ((,) String ([] String));
  generateWithTags cs checked = let {
    -- Whole-program strict-wrapper erasure changes constructor representation.
    -- Independently compiled libraries and roots preserve one boxed ABI.
    optimized = Optimize.optimizeChecked (X.erase (Checked.term checked))
  } in Codegen.generatePreparedProgram False S.empty cs M.empty optimized;
  chunks :: [] String -> [] String;
  chunks = map (\line -> line ++ "\n");
  -- The generic object ABI assigns user constructor tags by their resolved,
  -- crate-qualified name. Adding another crate cannot renumber a producer.
  -- The modulus keeps both the accumulator and tagged immediates within the
  -- signed native Int range. Check collisions across the whole linked closure.
  crateConstructorTags :: [] DataDecl -> Either String (Map String ((,) Int Int));
  crateConstructorTags ds = do {
    D.validateDeclarations ds;
    let { builtin = builtinConstructorTags;
          user = filter (\c -> not (M.member compareString (D.constructorName c) builtin))
            (concatMap LLVM.dataConstructors ds);
          hash text i state = if i == stringLength text then state else
            let { next = remInt (state * 257 + stringCodeAt text i + 1) 140737488355213 }
            in seq next (hash text (i + 1) next);
          row c = LLVM.constructorEntry (M.size builtin + hash (D.constructorName c) 0 1) c;
          rows = map row user;
          distinct = IS.fromList (map (\entry -> fst (snd entry)) rows) };
    ensure (IS.size distinct == length rows) "native crate constructor tag collision";
    Right (M.union compareString builtin (M.fromList compareString rows))
  };
  crateSymbol layout = "mlf_crate_" ++ identity layout;
  exportProduct :: ExportLayout -> Map String ((,) XName XType) -> Either String XTerm;
  exportProduct layout bindings = do {
    actual <- traverseEither (\((,) slot ((,,) key _ expected)) ->
      case M.lookup compareString key bindings of {
        Nothing -> Left ("missing native crate export " ++ key);
        Just ((,) name ty) -> do {
          ensure (T.alphaEq ty expected) ("native crate export type mismatch: " ++ key);
          Right ((,,) slot name ty)
        }
      }) (zip (range 0 (length (exports layout) - 1)) (exports layout));
    case wrapProduct actual of { Product body _ _ -> Right body }
  };
  exportProductType :: ExportLayout -> XType;
  exportProductType layout = case envelope layout of { Product _ ty _ -> ty };
  -- The factory returns the same balanced pair product built by exportProduct.
  -- Follow only this slot's path; unused sibling fields remain lazy.
  projectExport :: ExportLayout -> String -> Int -> XTerm -> Either String ((,) Int XTerm);
  projectExport layout key serial source = case exportRows layout of {
    ExportRows rows byKey byDecl -> do {
      d <- maybe (Left ("missing native crate projection " ++ key)) Right (M.lookup compareString key byKey);
      slot <- maybe (Left "native crate export slot missing") Right (IM.lookup (V.toInt d) byDecl);
      let { ty = case snd (V.at rows slot) of { (,,) _ _ t -> t };
            path size i = if size <= 1 then [] else let { middle = size / 2 } in
              if i < middle then (:) 0 (path middle i) else (:) 1 (path (size - middle) (i - middle));
            project next term branches = case branches of {
              [] -> (,) next term;
              (:) side rest -> let {
                name = XName next "nativeExportField";
                fields = if side == 0 then [Just name,Nothing] else [Nothing,Just name];
                deeper = project (next + 1) (XVarTerm name) rest
              } in (,) (fst deeper) (XCase term ty [XAlternative (XConstructorPattern "(,)" fields) (snd deeper)])
            }
          };
      Right (project serial source ((:) 1 (path (V.count rows) (V.toInt slot))))
    }
  };
  checkedParts checked = case Checked.term checked of {
    XWithData ds body -> (,) ds body;
    body -> (,) [] body
  };
  crateHeader :: [] String;
  crateHeader = ["; Generated from checked xMLF using the boxed crate object ABI.",
    "source_filename = \"emlf-native-crate\"", ""];
  -- Independently compiled bodies must not reinterpret an open nominal type
  -- when another crate adds a datatype with that name.
  closedCrateTypes :: ExportLayout -> Checked.CheckedTerm -> Either String ();
  closedCrateTypes layout checked = let {
    declared = S.fromList compareString (append (M.keys D.primitiveKinds)
      (map D.datatypeName (append D.builtinDeclarations (declarations layout))))
  } in case find (\name -> not (S.member compareString name declared)) (checkedTypeNames layout checked) of {
    Nothing -> Right ();
    Just name -> Left ("native crate uses an undeclared nominal type: " ++ name)
  };
  emitCrateLibrary :: ExportLayout -> Checked.CheckedTerm -> Either String ([] String);
  emitCrateLibrary layout checked = do {
    closedCrateTypes layout checked;
    case layout of {
      ExportLayout _ _ _ Nothing -> Right ();
      ExportLayout _ _ _ (Just known) -> ensure
        (eqList eqString (S.toList known) (checkedTypeNames layout checked))
        "native crate type-name census differs from actual checked code"
    };
    let { ds = fst (checkedParts checked) };
    -- Check the declared producer layout against the actual checked wrapper.
    ensure (eqList eqString (map D.prettyDeclaration (declarations layout)) (map D.prettyDeclaration ds))
      "native crate producer declaration layout mismatch";
    tags <- crateConstructorTags ds;
    case envelope layout of { Product _ ty paths -> do {
      ensure (T.alphaEq ty (Checked.typeOf checked)) "native crate export product type mismatch";
      generated <- generateWithTags tags checked;
      Right (chunks (concat [crateHeader, snd generated, [LLVM.abiDeclaration],
        libraryAdapter (crateSymbol layout) (length paths) (fst generated) paths]))
    } }
  };
  crateParameters selected term ty = case selected of {
    [] -> Right ((,) [] ty);
    (:) ((,) layout key) rest -> case exportRows layout of {
      ExportRows rows byKey byDecl -> case M.lookup compareString key byKey of {
        Nothing -> Left ("native crate does not export " ++ key);
        Just d -> case IM.lookup (V.toInt d) byDecl of {
          Nothing -> Left "native crate export slot missing";
          Just slot -> case (,,) (snd (V.at rows slot)) term ty of {
            (,,) ((,,) _ hint expected) (XAbs binder annotation body) (XArrow parameter result) -> do {
              ensure (eqString (X.nameHint binder) hint && T.alphaEq expected annotation && T.alphaEq expected parameter)
                ("native crate import wrapper type or name mismatch: " ++ key);
              (,) later answer <- crateParameters rest body result;
              Right ((,) ((:) ((,) (crateSymbol layout) (V.toInt slot)) later) answer)
            };
            _ -> Left "native crate root lost its checked import arrow"
          }
        }
      }
    }
  };
  emitCrateProgram :: [] ((,) ExportLayout String) -> Checked.CheckedTerm -> Either String ([] String);
  emitCrateProgram selected checked = do {
    let { parts = checkedParts checked; ds = fst parts; body = snd parts;
          layouts = M.fromList compareString (map (\entry -> (,) (identity (fst entry)) (fst entry)) selected);
          declarationsByName = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (D.prettyDeclaration d)) ds);
          agrees d = case M.lookup compareString (D.datatypeName d) declarationsByName of {
            Nothing -> False; Just actual -> eqString actual (D.prettyDeclaration d)
          } };
    ensure (length selected == S.size (S.fromList compareString (map snd selected)))
      "duplicate native crate import";
    ensure (all (\layout -> all agrees (declarations layout)) (M.elems layouts))
      "native crate dependency datatype layout mismatch";
    tags <- crateConstructorTags ds;
    (,) imports result <- crateParameters selected body (Checked.typeOf checked);
    generated <- generateWithTags tags checked;
    Right (chunks (concat [crateHeader, snd generated,
      rootAdapter (map crateSymbol (M.elems layouts)) (fst generated) imports (LLVM.ioType result)]))
  };
  libraryAdapter :: String -> Int -> String -> [] ((,) Int ([] Int)) -> [] String;
  libraryAdapter prefix count entry paths =
    append ["@" ++ prefix ++ "_root = private global ptr null, align 8",
      "@" ++ prefix ++ "_slots = private global [" ++ showInt count ++ " x ptr] zeroinitializer, align 8",
      "@" ++ prefix ++ "_state = private global i32 0, align 4",
      "declare void @llvm.trap()",
      "define private void @" ++ prefix ++ "_init() {", "entry:",
      "  %state = load i32, ptr @" ++ prefix ++ "_state",
      "  switch i32 %state, label %cycle [ i32 0, label %start i32 2, label %done ]",
      "cycle:", "  call void @llvm.trap()", "  unreachable", "start:",
      "  store i32 1, ptr @" ++ prefix ++ "_state",
      LLVM.abiCall,
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
  rootAdapter :: [] String -> String -> [] ((,) String Int) -> Bool -> [] String;
  rootAdapter symbols entry imports executeIO =
    concat [[LLVM.abiDeclaration], map (\prefix -> "declare ptr @" ++ prefix ++ "_get(i64)") symbols,
      ["define ptr @mlf_entry() {", "entry:",
       LLVM.abiCall,
       "  %wrapper = call ptr " ++ entry ++ "(ptr null, ptr null)"],
      concat (zipWith (\index ((,) prefix slot) ->
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
