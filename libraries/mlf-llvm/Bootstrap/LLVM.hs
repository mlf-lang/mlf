-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM (emitLLVM, emitLLVMIO, emitLLVMChunks, emitLLVMIOChunks, ioType, dataConstructors, constructorEntry, emitEntry, emitEntryChunks, emitCheckedChunks, entryCode, PreparedEntry, prepareChecked, emitPreparedChunks, preparedKey, checkedInputKey, crateInputKey, canonicalErasedKey) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.LLVM.Codegen as Codegen;
  import qualified Bootstrap.LLVM.Optimize as Optimize;
  import qualified Bootstrap.LLVM.StrictWrappers as Wrappers;
  emitLLVM :: XTerm -> Either String String;
  emitLLVM term = emitEntry False term;
  emitLLVMIO :: XTerm -> Either String String;
  emitLLVMIO term = emitEntry True term;
  emitLLVMChunks :: XTerm -> Either String ([] String);
  emitLLVMChunks term = emitEntryChunks False term;
  emitLLVMIOChunks :: XTerm -> Either String ([] String);
  emitLLVMIOChunks term = emitEntryChunks True term;
  ioType :: XType -> Bool;
  ioType ty =
    case ty of {
      XForall variable bound body -> ioType body;
      XCon name ((:) argument []) -> eqString name "IO";
      _ -> False
    };
  dataConstructors :: DataDecl -> [] ConstructorDecl;
  dataConstructors declaration =
    case declaration of {
      DataDecl name parameters constructors -> constructors;
      DataDeclK name parameters constructors -> constructors
    };
  constructorEntry :: Int -> ConstructorDecl -> (,) String ((,) Int Int);
  constructorEntry index (ConstructorDecl name fields) = (,) name ((,) index (L.length fields));
  emitEntry :: Bool -> XTerm -> Either String String;
  emitEntry requireIO term = L.mapEither L.concatStrings (emitEntryChunks requireIO term);
  -- Keep the module as output chunks for the executable driver. Streaming these
  -- through IO bounds temporary String copies and permits runtime collection.
  emitEntryChunks :: Bool -> XTerm -> Either String ([] String);
  emitEntryChunks requireIO term =
    case Checked.check term of {
      Left error -> Left ("LLVM target verification failed: " ++ error);
      Right checked -> emitCheckedChunks requireIO checked
    };
  -- Only an opaque successful check can enter this path. Raw xMLF entry points
  -- above always check, including terms deserialized from outside the compiler.
  emitCheckedChunks :: Bool -> Checked.CheckedTerm -> Either String ([] String);
  emitCheckedChunks requireIO checked =
    do {
      prepared <- prepareChecked requireIO checked;
      emitPreparedChunks prepared
    };
  -- The constructor remains private: a cached emission query can only prepare
  -- runtime code from an independently checked term, and cannot replace its
  -- erased program while retaining the successful check.
  data PreparedEntry = PreparedEntry Bool (Map String ((,) Int Int)) XErased;
  entryConstructors declarations =
    let {
      -- Boundary v3 reserves tags0..68: legacy tombstone, (), [], (:), tuples2..4,
      -- stack frame/evidence, then tuples5..64. User constructors start at69.
      builtins = L.concatMap dataConstructors D.builtinDeclarations;
      builtinNames = L.map D.constructorName builtins;
      users = L.filter (\c -> L.not (L.elem eqString (D.constructorName c) builtinNames))
                (L.concatMap dataConstructors declarations);
      all = L.append builtins users
    } in
    M.fromList compareString
      (L.zipWith constructorEntry (L.range 0 (L.length all - 1)) all);
  prepareChecked :: Bool -> Checked.CheckedTerm -> Either String PreparedEntry;
  prepareChecked requireIO checked =
    let {
      term = Checked.term checked
    } in
    let {
      ty = Checked.typeOf checked
    } in
    if (requireIO && L.not (ioType ty))
    then Left "program must have type IO a to run"
    else let {
           declarations =
             case term of {
               XWithData ds body -> ds;
               _ -> []
             }
         } in
         let {
           constructors = entryConstructors declarations
         } in
         let {
           optimized = Optimize.optimize (X.erase term)
         } in
         let {
           lowered = Wrappers.optimize declarations constructors optimized
         } in
         Right (PreparedEntry (ioType ty) constructors lowered);
  emitPreparedChunks :: PreparedEntry -> Either String ([] String);
  emitPreparedChunks (PreparedEntry executeIO constructors lowered) =
    case Codegen.generate constructors lowered of {
      Left error -> Left error;
      Right ((,) entry code) ->
        let {
          header =
            (:) "; Generated from independently checked xMLF."
              ((:) "source_filename = \"emlf\"" ((:) "" []))
        } in
        let {
          output = L.append header (L.append code (entryCode entry executeIO))
        } in
        Right (L.map (\line -> (line ++ "\n")) output)
    };
  runtimePack fields =
    L.concatMapString (\field -> (showInt (stringLength field) ++ (":" ++ field))) fields;
  runtimeBool :: Bool -> String;
  runtimeBool value = if value then "true" else "false";
  runtimeName (XName identity _) = showInt identity;
  runtimeOptionalName name =
    case name of {
      Nothing -> "none";
      Just n -> runtimePack ((:) "some" ((:) (runtimeName n) []))
    };
  runtimePattern pattern =
    case pattern of {
      XConstructorPattern constructor names ->
        runtimePack
          ((:) "constructor"
             ((:) constructor ((:) (runtimePack (L.map runtimeOptionalName names)) [])));
      XDefaultPattern name -> runtimePack ((:) "default" ((:) (runtimeOptionalName name) []))
    };
  -- Retain lengths beside a tree of fields. Flattening only once avoids copying
  -- the entire remaining crate at each nested let, while preserving the exact
  -- scalar-length framing used by existing query keys.
  data RuntimeKey = RuntimeText String | RuntimeFields Int ([] RuntimeKey);
  runtimeKeyLength key =
    case key of {
      RuntimeText text -> stringLength text;
      RuntimeFields size _ -> size
    };
  runtimeKeyFields fields =
    let {
      size =
        L.foldl
          (\total field ->
             let {
               length = runtimeKeyLength field
             } in
             (((total + stringLength (showInt length)) + 1) + length))
          0
          fields
    } in
    seq size (RuntimeFields size fields);
  runtimeKeyChunks :: RuntimeKey -> [] String -> [] String;
  runtimeKeyChunks key tail =
    case key of {
      RuntimeText text -> (:) text tail;
      RuntimeFields _ fields ->
        L.foldr
          (\field rest ->
             (:) (showInt (runtimeKeyLength field) ++ ":") (runtimeKeyChunks field rest))
          tail
          fields
    };
  runtimeErasedEncoding :: XErased -> RuntimeKey;
  runtimeErasedEncoding term =
    runtimeKeyFields
      (case term of {
         XEVar n -> (:) (RuntimeText "variable") ((:) (RuntimeText (runtimeName n)) []);
         XEAbs n body ->
           (:) (RuntimeText "lambda")
             ((:) (RuntimeText (runtimeName n)) ((:) (runtimeErasedEncoding body) []));
         XEApp f a ->
           (:) (RuntimeText "application")
             ((:) (runtimeErasedEncoding f) ((:) (runtimeErasedEncoding a) []));
         XELet n rhs body ->
           (:) (RuntimeText "let")
             ((:) (RuntimeText (runtimeName n))
                ((:) (runtimeErasedEncoding rhs) ((:) (runtimeErasedEncoding body) [])));
         XELetRec definitions body ->
           (:) (RuntimeText "recursive")
             ((:)
                (runtimeKeyFields
                   (L.map
                      (\((,) n rhs) ->
                         runtimeKeyFields
                           ((:) (RuntimeText (runtimeName n))
                              ((:) (runtimeErasedEncoding rhs) [])))
                      definitions))
                ((:) (runtimeErasedEncoding body) []));
         XEInt n -> (:) (RuntimeText "integer") ((:) (RuntimeText (showInt n)) []);
         XEDouble n ->
           (:) (RuntimeText "double") ((:) (RuntimeText (showInt (doubleToBits n))) []);
         XEBool b -> (:) (RuntimeText "boolean") ((:) (RuntimeText (runtimeBool b)) []);
         XEString text -> (:) (RuntimeText "string") ((:) (RuntimeText text) []);
         XEPrimitive p ->
           (:) (RuntimeText "primitive") ((:) (RuntimeText (P.primitiveName p)) []);
         XEConstructor c -> (:) (RuntimeText "constructor") ((:) (RuntimeText c) []);
         XEEvidenceHole n -> (:) (RuntimeText "hole") ((:) (RuntimeText (showInt n)) []);
         XECase subject branches ->
           (:) (RuntimeText "case")
             ((:) (runtimeErasedEncoding subject)
                ((:)
                   (runtimeKeyFields
                      (L.map
                         (\(XErasedAlternative pattern body) ->
                            runtimeKeyFields
                              ((:) (RuntimeText (runtimePattern pattern))
                                 ((:) (runtimeErasedEncoding body) [])))
                         branches))
                   []))
       });
  runtimeErased :: XErased -> String;
  runtimeErased term = L.concatStrings (runtimeKeyChunks (runtimeErasedEncoding term) []);
  canonicalErasedKey expression =
    case Optimize.runFresh (Optimize.copy M.empty expression) 0 of {
      (,) normalized _ -> runtimeErased normalized
    };
  constructorKey constructors =
    runtimePack
      (L.map
         (\((,) name ((,) tag arity)) ->
            runtimePack ((:) name ((:) (showInt tag) ((:) (showInt arity) []))))
         (M.toList constructors));
  checkedInputKey :: Bool -> Checked.CheckedTerm -> Either String String;
  checkedInputKey requireIO checked =
    if (requireIO && L.not (ioType (Checked.typeOf checked)))
    then Left "program must have type IO a to run"
    else let {
           declarations =
             case Checked.term checked of {
               XWithData ds _ -> ds;
               _ -> []
             }
         } in
         Right
           (runtimePack
              ((:) "MLF-CODEGEN-INPUT-COMPACT-4-RESULT-SUM-1-LAZY-PRODUCER-1"
                 ((:) "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v3"
                    ((:) (runtimeBool (ioType (Checked.typeOf checked)))
                       ((:) (constructorKey (entryConstructors declarations))
                          ((:) (runtimePack (L.map D.prettyDeclaration declarations))
                             ((:) (canonicalErasedKey (X.erase (Checked.term checked))) [])))))));
  preparedKey (PreparedEntry executeIO constructors lowered) =
    runtimePack
      ((:) "MLF-CODEGEN-PREPARED-COMPACT-4-RESULT-SUM-1-LAZY-PRODUCER-1"
         ((:) "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v3"
            ((:) (runtimeBool executeIO)
               ((:) (constructorKey constructors) ((:) (canonicalErasedKey lowered) [])))));
  -- A crate links all checked fragments, including declarations outside the
  -- entry's dependency closure. Their bodies are not inputs to its execution.
  -- This projection is used ONLY as a whole-program cache key. The checked
  -- term, optimizer, fresh-name allocation and cold LLVM output are unchanged.
  -- Keep the entire declaration spine and constructor ABI. Mask only bodies
  -- which no syntactic path from the entry can demand; branches and captures
  -- conservatively contribute all their free names.
  data EntryGroup = EntryLet XName XErased | EntryRec ([] ((,) XName XErased));
  entrySpine :: [] EntryGroup -> XErased -> (,) ([] EntryGroup) XErased;
  entrySpine groups expression =
    case expression of {
      XELet name rhs body -> entrySpine ((:) (EntryLet name rhs) groups) body;
      XELetRec bindings body -> entrySpine ((:) (EntryRec bindings) groups) body;
      _ -> (,) (L.reverse groups) expression
    };
  entryBindings :: EntryGroup -> [] ((,) XName XErased);
  entryBindings group =
    case group of {
      EntryLet name rhs -> (:) ((,) name rhs) [];
      EntryRec bindings -> bindings
    };
  entryReach :: Map XName XErased -> Set XName -> [] XName -> Set XName;
  entryReach definitions seen pending =
    case pending of {
      [] -> seen;
      (:) name rest ->
        if Set.member Optimize.compareName name seen
        then entryReach definitions seen rest
        else let {
               next = Set.insert Optimize.compareName name seen
             } in
             case M.lookup Optimize.compareName name definitions of {
               Nothing -> entryReach definitions next rest;
               Just rhs ->
                 entryReach definitions next (L.append (Set.toList (Optimize.free rhs)) rest)
             }
    };
  entryMask :: Set XName -> (,) XName XErased -> (,) XName XErased;
  entryMask live ((,) name rhs) =
    (,) name (if Set.member Optimize.compareName name live then rhs else XEInt 0);
  entryGroup :: Set XName -> EntryGroup -> XErased -> XErased;
  entryGroup live group body =
    case group of {
      EntryLet name rhs ->
        case entryMask live ((,) name rhs) of {
          (,) n value -> XELet n value body
        };
      EntryRec bindings -> XELetRec (L.map (entryMask live) bindings) body
    };
  entryRuntimeKey :: XErased -> String;
  -- Freshen identities before constructing the dependency map, independently
  -- of their original allocation, then normalize again after masking so
  -- binder allocations inside an irrelevant body cannot move live identities.
  entryRuntimeKey expression =
    let {
      unique = L.fst (Optimize.runFresh (Optimize.copy M.empty expression) 0)
    } in
    case entrySpine [] unique of {
      (,) groups entry ->
        let {
          definitions = M.fromList Optimize.compareName (L.concatMap entryBindings groups)
        } in
        let {
          live = entryReach definitions Set.empty (Set.toList (Optimize.free entry))
        } in
        canonicalErasedKey (L.foldr (entryGroup live) entry groups)
    };
  crateInputKey :: Bool -> Checked.CheckedTerm -> Either String String;
  crateInputKey requireIO checked =
    if (requireIO && L.not (ioType (Checked.typeOf checked)))
    then Left "program must have type IO a to run"
    else let {
           declarations =
             case Checked.term checked of {
               XWithData ds _ -> ds;
               _ -> []
             }
         } in
         Right
           (runtimePack
              ((:) "MLF-CODEGEN-CRATE-INPUT-COMPACT-4-RESULT-SUM-1-LAZY-PRODUCER-1"
                 ((:) "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v3"
                    ((:) (runtimeBool (ioType (Checked.typeOf checked)))
                       ((:) (constructorKey (entryConstructors declarations))
                          ((:) (runtimePack (L.map D.prettyDeclaration declarations))
                             ((:) (entryRuntimeKey (X.erase (Checked.term checked))) [])))))));
  entryCode :: String -> Bool -> [] String;
  entryCode entry executeIO =
    let {
      abi = "mlf_require_haskell_boundary_v3_abi"
    } in
    (:) ("declare void @" ++ (abi ++ "()"))
      ((:) "define ptr @mlf_entry() {"
         ((:) ("  call void @" ++ (abi ++ "()"))
            ((:) ("  %root = call ptr " ++ (entry ++ "(ptr null, ptr null)"))
               ((:) "  ret ptr %root"
                  ((:) "}"
                     ((:) "define i32 @main(i32 %argc, ptr %argv) {"
                        ((:) "  call void @mlf_set_args(i32 %argc, ptr %argv)"
                           ((:) "  %root = call ptr @mlf_entry()"
                              ((:)
                                 ("  %status = call i32 @mlf_run(ptr %root, i64 " ++
                                  ((if executeIO then "1" else "0") ++ ")"))
                                 ((:) "  ret i32 %status" ((:) "}" [])))))))))))
}
