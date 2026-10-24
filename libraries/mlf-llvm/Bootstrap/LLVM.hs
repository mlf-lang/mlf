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
  emitLLVMChunks :: XTerm -> Either String (List String);
  emitLLVMChunks term = emitEntryChunks False term;
  emitLLVMIOChunks :: XTerm -> Either String (List String);
  emitLLVMIOChunks term = emitEntryChunks True term;
  ioType :: XType -> Bool;
  ioType ty =
    case ty of {
      XForall variable bound body -> ioType body;
      XCon name (Cons argument Nil) -> eqString name "IO";
      _ -> False
    };
  dataConstructors :: DataDecl -> List ConstructorDecl;
  dataConstructors declaration =
    case declaration of {
      DataDecl name parameters constructors -> constructors;
      DataDeclK name parameters constructors -> constructors
    };
  constructorEntry :: Int -> ConstructorDecl -> Pair String (Pair Int Int);
  constructorEntry index (ConstructorDecl name fields) = Pair name (Pair index (L.length fields));
  emitEntry :: Bool -> XTerm -> Either String String;
  emitEntry requireIO term = L.mapEither L.concatStrings (emitEntryChunks requireIO term);
  -- Keep the module as output chunks for the executable driver. Streaming these
  -- through IO bounds temporary String copies and permits runtime collection.
  emitEntryChunks :: Bool -> XTerm -> Either String (List String);
  emitEntryChunks requireIO term =
    case Checked.check term of {
      Left error -> Left ("LLVM target verification failed: " ++ error);
      Right checked -> emitCheckedChunks requireIO checked
    };
  -- Only an opaque successful check can enter this path. Raw xMLF entry points
  -- above always check, including terms deserialized from outside the compiler.
  emitCheckedChunks :: Bool -> Checked.CheckedTerm -> Either String (List String);
  emitCheckedChunks requireIO checked =
    do {
      prepared <- prepareChecked requireIO checked;
      emitPreparedChunks prepared
    };
  -- The constructor remains private: a cached emission query can only prepare
  -- runtime code from an independently checked term, and cannot replace its
  -- erased program while retaining the successful check.
  data PreparedEntry = PreparedEntry Bool (Map String (Pair Int Int)) XErased;
  entryConstructors declarations =
    let {
      -- Boundary v2 reserves tags 0..8: legacy Unit, (), [], (:), tuples2..4,
      -- MLFStackFrame and MLFStackEvidence. Conversion primitives use these tags.
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
               _ -> Nil
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
  emitPreparedChunks :: PreparedEntry -> Either String (List String);
  emitPreparedChunks (PreparedEntry executeIO constructors lowered) =
    case Codegen.generate constructors lowered of {
      Left error -> Left error;
      Right (Pair entry code) ->
        let {
          header =
            Cons "; Generated from independently checked xMLF."
              (Cons "source_filename = \"emlf\"" (Cons "" Nil))
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
      Just n -> runtimePack (Cons "some" (Cons (runtimeName n) Nil))
    };
  runtimePattern pattern =
    case pattern of {
      XConstructorPattern constructor names ->
        runtimePack
          (Cons "constructor"
             (Cons constructor (Cons (runtimePack (L.map runtimeOptionalName names)) Nil)));
      XDefaultPattern name -> runtimePack (Cons "default" (Cons (runtimeOptionalName name) Nil))
    };
  -- Retain lengths beside a tree of fields. Flattening only once avoids copying
  -- the entire remaining crate at each nested let, while preserving the exact
  -- scalar-length framing used by existing query keys.
  data RuntimeKey = RuntimeText String | RuntimeFields Int (List RuntimeKey);
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
  runtimeKeyChunks :: RuntimeKey -> List String -> List String;
  runtimeKeyChunks key tail =
    case key of {
      RuntimeText text -> Cons text tail;
      RuntimeFields _ fields ->
        L.foldr
          (\field rest ->
             Cons (showInt (runtimeKeyLength field) ++ ":") (runtimeKeyChunks field rest))
          tail
          fields
    };
  runtimeErasedEncoding :: XErased -> RuntimeKey;
  runtimeErasedEncoding term =
    runtimeKeyFields
      (case term of {
         XEVar n -> Cons (RuntimeText "variable") (Cons (RuntimeText (runtimeName n)) Nil);
         XEAbs n body ->
           Cons (RuntimeText "lambda")
             (Cons (RuntimeText (runtimeName n)) (Cons (runtimeErasedEncoding body) Nil));
         XEApp f a ->
           Cons (RuntimeText "application")
             (Cons (runtimeErasedEncoding f) (Cons (runtimeErasedEncoding a) Nil));
         XELet n rhs body ->
           Cons (RuntimeText "let")
             (Cons (RuntimeText (runtimeName n))
                (Cons (runtimeErasedEncoding rhs) (Cons (runtimeErasedEncoding body) Nil)));
         XELetRec definitions body ->
           Cons (RuntimeText "recursive")
             (Cons
                (runtimeKeyFields
                   (L.map
                      (\(Pair n rhs) ->
                         runtimeKeyFields
                           (Cons (RuntimeText (runtimeName n))
                              (Cons (runtimeErasedEncoding rhs) Nil)))
                      definitions))
                (Cons (runtimeErasedEncoding body) Nil));
         XEInt n -> Cons (RuntimeText "integer") (Cons (RuntimeText (showInt n)) Nil);
         XEDouble n ->
           Cons (RuntimeText "double") (Cons (RuntimeText (showInt (doubleToBits n))) Nil);
         XEBool b -> Cons (RuntimeText "boolean") (Cons (RuntimeText (runtimeBool b)) Nil);
         XEString text -> Cons (RuntimeText "string") (Cons (RuntimeText text) Nil);
         XEPrimitive p ->
           Cons (RuntimeText "primitive") (Cons (RuntimeText (P.primitiveName p)) Nil);
         XEConstructor c -> Cons (RuntimeText "constructor") (Cons (RuntimeText c) Nil);
         XEEvidenceHole n -> Cons (RuntimeText "hole") (Cons (RuntimeText (showInt n)) Nil);
         XECase subject branches ->
           Cons (RuntimeText "case")
             (Cons (runtimeErasedEncoding subject)
                (Cons
                   (runtimeKeyFields
                      (L.map
                         (\(XErasedAlternative pattern body) ->
                            runtimeKeyFields
                              (Cons (RuntimeText (runtimePattern pattern))
                                 (Cons (runtimeErasedEncoding body) Nil)))
                         branches))
                   Nil))
       });
  runtimeErased :: XErased -> String;
  runtimeErased term = L.concatStrings (runtimeKeyChunks (runtimeErasedEncoding term) Nil);
  canonicalErasedKey expression =
    case Optimize.runFresh (Optimize.copy M.empty expression) 0 of {
      Pair normalized _ -> runtimeErased normalized
    };
  constructorKey constructors =
    runtimePack
      (L.map
         (\(Pair name (Pair tag arity)) ->
            runtimePack (Cons name (Cons (showInt tag) (Cons (showInt arity) Nil))))
         (M.toList constructors));
  checkedInputKey :: Bool -> Checked.CheckedTerm -> Either String String;
  checkedInputKey requireIO checked =
    if (requireIO && L.not (ioType (Checked.typeOf checked)))
    then Left "program must have type IO a to run"
    else let {
           declarations =
             case Checked.term checked of {
               XWithData ds _ -> ds;
               _ -> Nil
             }
         } in
         Right
           (runtimePack
              (Cons "MLF-CODEGEN-INPUT-COMPACT-2"
                 (Cons "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v2"
                    (Cons (runtimeBool (ioType (Checked.typeOf checked)))
                       (Cons (constructorKey (entryConstructors declarations))
                          (Cons (runtimePack (L.map D.prettyDeclaration declarations))
                             (Cons (canonicalErasedKey (X.erase (Checked.term checked))) Nil)))))));
  preparedKey (PreparedEntry executeIO constructors lowered) =
    runtimePack
      (Cons "MLF-CODEGEN-PREPARED-COMPACT-2"
         (Cons "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v2"
            (Cons (runtimeBool executeIO)
               (Cons (constructorKey constructors) (Cons (canonicalErasedKey lowered) Nil)))));
  -- A crate links all checked fragments, including declarations outside the
  -- entry's dependency closure. Their bodies are not inputs to its execution.
  -- This projection is used ONLY as a whole-program cache key. The checked
  -- term, optimizer, fresh-name allocation and cold LLVM output are unchanged.
  -- Keep the entire declaration spine and constructor ABI. Mask only bodies
  -- which no syntactic path from the entry can demand; branches and captures
  -- conservatively contribute all their free names.
  data EntryGroup = EntryLet XName XErased | EntryRec (List (Pair XName XErased));
  entrySpine :: List EntryGroup -> XErased -> Pair (List EntryGroup) XErased;
  entrySpine groups expression =
    case expression of {
      XELet name rhs body -> entrySpine (Cons (EntryLet name rhs) groups) body;
      XELetRec bindings body -> entrySpine (Cons (EntryRec bindings) groups) body;
      _ -> Pair (L.reverse groups) expression
    };
  entryBindings :: EntryGroup -> List (Pair XName XErased);
  entryBindings group =
    case group of {
      EntryLet name rhs -> Cons (Pair name rhs) Nil;
      EntryRec bindings -> bindings
    };
  entryReach :: Map XName XErased -> Set XName -> List XName -> Set XName;
  entryReach definitions seen pending =
    case pending of {
      Nil -> seen;
      Cons name rest ->
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
  entryMask :: Set XName -> Pair XName XErased -> Pair XName XErased;
  entryMask live (Pair name rhs) =
    Pair name (if Set.member Optimize.compareName name live then rhs else XEInt 0);
  entryGroup :: Set XName -> EntryGroup -> XErased -> XErased;
  entryGroup live group body =
    case group of {
      EntryLet name rhs ->
        case entryMask live (Pair name rhs) of {
          Pair n value -> XELet n value body
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
    case entrySpine Nil unique of {
      Pair groups entry ->
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
               _ -> Nil
             }
         } in
         Right
           (runtimePack
              (Cons "MLF-CODEGEN-CRATE-INPUT-COMPACT-2"
                 (Cons "compact-bdwgc-v1-process-v1-completion-v2-haskell-boundary-v2"
                    (Cons (runtimeBool (ioType (Checked.typeOf checked)))
                       (Cons (constructorKey (entryConstructors declarations))
                          (Cons (runtimePack (L.map D.prettyDeclaration declarations))
                             (Cons (entryRuntimeKey (X.erase (Checked.term checked))) Nil)))))));
  entryCode :: String -> Bool -> List String;
  entryCode entry executeIO =
    let {
      abi = "mlf_require_haskell_boundary_v2_abi"
    } in
    Cons ("declare void @" ++ (abi ++ "()"))
      (Cons "define ptr @mlf_entry() {"
         (Cons ("  call void @" ++ (abi ++ "()"))
            (Cons ("  %root = call ptr " ++ (entry ++ "(ptr null, ptr null)"))
               (Cons "  ret ptr %root"
                  (Cons "}"
                     (Cons "define i32 @main(i32 %argc, ptr %argv) {"
                        (Cons "  call void @mlf_set_args(i32 %argc, ptr %argv)"
                           (Cons "  %root = call ptr @mlf_entry()"
                              (Cons
                                 ("  %status = call i32 @mlf_run(ptr %root, i64 " ++
                                  ((if executeIO then "1" else "0") ++ ")"))
                                 (Cons "  ret i32 %status" (Cons "}" Nil)))))))))))
}
