# Historical staged editor used during initial three-file preparation; NOT an idempotent rebuild recipe.
# Apply prefix-sharing.patch to the pinned S2 base instead. Later safety refinements are in that patch.
from pathlib import Path
S=Path('/workspace/scratch/3f83e2ebe290/mlf-crates-prefix-source-20261026/libraries/mlf-crates/Bootstrap')
p=S/'Separate.hs';s=p.read_text()
s=s.replace('  import qualified Bootstrap.Data as D;','  import qualified Bootstrap.Data as D;\n  import qualified Bootstrap.SourceEquality as SourceEquality;',1)
pos=s.index('  entityEncoding (Modules.Entity')
s=s[:pos]+'''  -- A per-compilation pool contains only pure encodings, never inferred results.
  -- Entries remain lazy. A name lookup is not an identity proof: lowering may
  -- change a layout, so reuse requires equality of the actual full declaration.
  data DatatypeEncoding =
    DatatypeEncoding DataDecl String Int ((,,,) Int Int Int Int);
  data DatatypeEncodings = DatatypeEncodings (Map String ([] DatatypeEncoding));
  datatypeEncoding :: DataDecl -> DatatypeEncoding;
  datatypeEncoding declaration =
    let { text = D.prettyDeclaration declaration ++ "\\n" } in
    DatatypeEncoding declaration text (stringLength text) (fingerprintPart text);
  prepareDatatypeEncodings :: [] DataDecl -> DatatypeEncodings;
  prepareDatatypeEncodings declarations =
    DatatypeEncodings (M.fromListWith compareString append
      (map (\\d -> (,) (D.datatypeName d) ((:) (datatypeEncoding d) [])) declarations));
  findDatatypeEncoding :: DataDecl -> [] DatatypeEncoding -> DatatypeEncoding;
  findDatatypeEncoding declaration entries = case entries of {
    [] -> datatypeEncoding declaration;
    (:) entry rest -> case entry of {
      DatatypeEncoding original _ _ _ ->
        if SourceEquality.eqDataDecl declaration original then entry
        else findDatatypeEncoding declaration rest
    }
  };
  lookupDatatypeEncoding :: DatatypeEncodings -> DataDecl -> DatatypeEncoding;
  lookupDatatypeEncoding (DatatypeEncodings entries) declaration =
    findDatatypeEncoding declaration
      (M.findWithDefault compareString [] (D.datatypeName declaration) entries);
  datatypeEncodingText :: DatatypeEncoding -> String;
  datatypeEncodingText (DatatypeEncoding _ text _ _) = text;
  datatypeEncodingLength :: DatatypeEncoding -> Int;
  datatypeEncodingLength (DatatypeEncoding _ _ count _) = count;
  appendDatatypeEncoding :: (,) Int Int -> DatatypeEncoding -> (,) Int Int;
  appendDatatypeEncoding state (DatatypeEncoding _ _ _ part) = fingerprintAppend state part;
  prettyTermWithDatatypes :: DatatypeEncodings -> XTerm -> String;
  prettyTermWithDatatypes pool term = case term of {
    XWithData declarations body ->
      concatMapString (\\d -> datatypeEncodingText (lookupDatatypeEncoding pool d)) declarations
        ++ Pretty.prettyTerm body;
    _ -> Pretty.prettyTerm term
  };
  fingerprintTermWithDatatypes :: DatatypeEncodings -> XTerm -> String;
  fingerprintTermWithDatatypes pool term = case term of {
    XWithData declarations body ->
      fingerprintAfter
        (foldlStrict appendDatatypeEncoding ((,) 0 1)
          (map (lookupDatatypeEncoding pool) declarations))
        (Pretty.prettyTerm body);
    _ -> fingerprint (Pretty.prettyTerm term)
  };
  -- The interface checksum is NOT the payload checksum. Compose the exact
  -- scalar-length-framed seven fields, sharing only actual datatype text parts.
  -- Header and payload declarations are looked up separately by encodeUnit.
  encodeInterfaceWithDatatypes :: DatatypeEncodings -> UnitInterface -> (,) String String;
  encodeInterfaceWithDatatypes pool iface =
    let { encodings = map (lookupDatatypeEncoding pool) (unitData iface) } in
    let { suffix = unlines (append (map prettyClass (unitClasses iface))
          (map (\\p -> prettyInstance (snd p)) (unitInstances iface))) } in
    let { metadata = concatMapString datatypeEncodingText encodings ++ suffix } in
    let { metadataLength = foldlStrict (\\n entry -> n + datatypeEncodingLength entry)
          (stringLength suffix) encodings } in
    let { before = (:) "MLFI-4" ((:) (unitName iface)
          ((:) (pack (map pairEncoding (unitDependencies iface)))
            ((:) (pack (map entityEncoding (unitExports iface))) []))) } in
    let { after = (:) (pack (map fst (unitInstances iface)))
          ((:) (pack (map (\\((,) n t) -> pairEncoding ((,) n (Pretty.prettyType (normalType t))))
            (unitBindings iface))) []) } in
    let { fields = append before ((:) metadata after) } in
    let { state = foldlStrict appendDatatypeEncoding
          (fingerprintStateFrom (pack before ++ showInt metadataLength ++ ":") 0 0 1)
          encodings } in
    (,) (pack (snoc fields (unitObjectFingerprint iface)))
      (fingerprintAfter state (suffix ++ pack after));
  encodeUnitWithDatatypes :: DatatypeEncodings -> UnitObject -> (,) String String;
  encodeUnitWithDatatypes pool object =
    let { iface = objectInterface object } in
    let { interfaceEncoding = encodeInterfaceWithDatatypes pool iface } in
    (,) (fst interfaceEncoding)
      (pack ((:) "MLFO-1" ((:) (unitName iface)
        ((:) (snd interfaceEncoding)
          ((:) (prettyTermWithDatatypes pool (objectTerm object)) [])))));
''' + s[pos:]
p.write_text(s)
p=S/'InferenceUnit.hs';s=p.read_text()
old='''  compileLoweredGroup name dependencies datatypes members =
    do {'''
new='''  compileLoweredGroup name dependencies datatypes members =
    compileLoweredGroupUsing (\\term -> Separate.fingerprint (Pretty.prettyTerm term))
      name dependencies datatypes members;
  compileLoweredGroupWithDatatypes :: Separate.DatatypeEncodings -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupWithDatatypes pool name dependencies datatypes members =
    compileLoweredGroupUsing (Separate.fingerprintTermWithDatatypes pool)
      name dependencies datatypes members;
  compileLoweredGroupUsing :: (XTerm -> String) -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupUsing payloadFingerprint name dependencies datatypes members =
    do {'''
assert s.count(old)==1;s=s.replace(old,new,1)
old='(Separate.fingerprint (Pretty.prettyTerm payload))';assert s.count(old)==1;s=s.replace(old,'(payloadFingerprint payload)',1)
p.write_text(s)
p=S/'CrateQuery.hs';s=p.read_text()
s=s.replace('  import qualified Bootstrap.Data as D;','  import qualified Bootstrap.Data as D;\n  import qualified Bootstrap.SourceEquality as SourceEquality;',1)
pos=s.index('  encodeXType ::')
s=s[:pos]+'''  data QueryDatatypeEncoding = QueryDatatypeEncoding DataDecl String;
  data SourceEncodings = SourceEncodings Separate.DatatypeEncodings
    (Map String ([] QueryDatatypeEncoding));
  prepareSourceEncodings :: [] DataDecl -> SourceEncodings;
  prepareSourceEncodings declarations =
    SourceEncodings (Separate.prepareDatatypeEncodings declarations)
      (M.fromListWith compareString append
        (map (\\d -> (,) (D.datatypeName d) ((:) (QueryDatatypeEncoding d (encodeDatatype d)) []))
          (append D.builtinDeclarations declarations)));
  findQueryDatatypeEncoding :: DataDecl -> [] QueryDatatypeEncoding -> String;
  findQueryDatatypeEncoding declaration entries = case entries of {
    [] -> encodeDatatype declaration;
    (:) (QueryDatatypeEncoding original text) rest ->
      if SourceEquality.eqDataDecl declaration original then text
      else findQueryDatatypeEncoding declaration rest
  };
  encodeDatatypeContextWithPool :: SourceEncodings -> [] DataDecl -> String;
  encodeDatatypeContextWithPool (SourceEncodings _ entries) declarations =
    list (\\d -> findQueryDatatypeEncoding d
      (M.findWithDefault compareString [] (D.datatypeName d) entries))
      (append D.builtinDeclarations declarations);
''' + s[pos:]
pos=s.index('  -- Commands receive NUL-separated argv')
s=s[:pos]+'''  encodeCachedWithDatatypes :: Separate.DatatypeEncodings -> String -> Separate.UnitObject -> String;
  encodeCachedWithDatatypes pool key object =
    if contextualCache key object then encodeCached key object
    else let { encoded = Separate.encodeUnitWithDatatypes pool object } in
      Separate.pack ((:) "MLF-QUERY-CACHE-1"
        ((:) key ((:) (fst encoded) ((:) (snd encoded) []))));
''' + s[pos:]
old='''  sourceQueryKey crateId compilerHash prepared contracts datatypes =
    let { observed'''
new='''  sourceQueryKey crateId compilerHash prepared contracts datatypes =
    sourceQueryKeyWithContext crateId compilerHash prepared contracts (encodeDatatypeContext datatypes);
  sourceQueryKeyWithContext :: String -> String -> Source.PreparedGroup ->
    Map String Source.SourceContract -> String -> String;
  sourceQueryKeyWithContext crateId compilerHash prepared contracts datatypeContext =
    let { observed'''
# PreparedSourceGroup name verified below; fix if actual differs.
assert s.count(old)==1;s=s.replace(old,new,1)
# Replace only source-key occurrence after named helper.
pos=s.index('  sourceQueryKeyWithContext crateId compilerHash prepared contracts datatypeContext =')
a=s[:pos];b=s[pos:];assert b.count('(encodeDatatypeContext datatypes)')==1
s=a+b.replace('(encodeDatatypeContext datatypes)','datatypeContext',1)
old='''  runSourceGroups crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results = case groups of {'''
new='''  runSourceGroups crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
    runSourceGroupsWithEncodings Nothing crateId compilerHash cacheDir inventory plan groups contracts
      objects inferred reused results;
  runSourceGroupsWithEncodings :: Maybe SourceEncodings -> String -> String -> String ->
    TypeInventory -> Source.SourcePlan -> [] ([] String) -> Map String Source.SourceContract ->
    [] Separate.UnitObject -> Int -> Int -> [] GroupResult ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  runSourceGroupsWithEncodings encodings crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results = case groups of {'''
assert s.count(old)==1;s=s.replace(old,new,1)
old='''        let { key = sourceQueryKey crateId compilerHash prepared contracts datatypes };'''
new='''        let { key = case encodings of {
          Nothing -> sourceQueryKey crateId compilerHash prepared contracts datatypes;
          Just pool -> sourceQueryKeyWithContext crateId compilerHash prepared contracts
            (encodeDatatypeContextWithPool pool datatypes)
        } };'''
assert s.count(old)==1;s=s.replace(old,new,1)
old='''          Left _ -> mapEither ((,) False)
            (Inference.compileLoweredGroup name
              ((:) (dependencyInterface bindings) []) datatypes members)'''
new='''          Left _ -> mapEither ((,) False) (case encodings of {
            Nothing -> Inference.compileLoweredGroup name
              ((:) (dependencyInterface bindings) []) datatypes members;
            Just (SourceEncodings pool _) -> Inference.compileLoweredGroupWithDatatypes pool name
              ((:) (dependencyInterface bindings) []) datatypes members
          })'''
assert s.count(old)==1;s=s.replace(old,new,1)
# Only the source-group path, not legacy runGroups, changes its encoder.
pos=s.index('  runSourceGroupsWithEncodings encodings');a=s[:pos];b=s[pos:]
old='''                else writeCache destination (encodeCached key object);'''
new='''                else writeCache destination (case encodings of {
                  Nothing -> encodeCached key object;
                  Just (SourceEncodings pool _) -> encodeCachedWithDatatypes pool key object
                });'''
assert b.count(old)==1;b=b.replace(old,new,1)
b=b.replace('''                  runSourceGroups crateId compilerHash cacheDir inventory plan rest''','''                  runSourceGroupsWithEncodings encodings crateId compilerHash cacheDir inventory plan rest''',1)
b=b.replace('''                result <- runSourceGroups crateId compilerHash cacheDir inventory plan
                  (Source.planGroups plan) contracts [] 0 0 [];''','''                let { encodings = prepareSourceEncodings (Source.planData plan) };
                result <- runSourceGroupsWithEncodings (Just encodings)
                  crateId compilerHash cacheDir inventory plan (Source.planGroups plan) contracts [] 0 0 [];''',1)
s=a+b
p.write_text(s)
