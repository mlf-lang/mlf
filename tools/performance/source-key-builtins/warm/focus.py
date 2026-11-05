"""Additional call sites for the prespecified second run. No changed producer code."""

def symbol_reader(s,one):
    s=one(s,'  data Read a = Read (Cursor -> IO (Either String ((,) a Cursor)));',
        '''  data Read a = Read (Cursor -> IO (Either String ((,) a Cursor)));
  timedUtf8 (Read action) = Read (\\cursor -> Clock.io "symbol.utf8-reader" (action cursor));''')
    s=one(s,'returnRead (textFromChars (reverse chars))',
             'returnRead (Clock.demand "symbol.materialize" (textFromChars (reverse chars)))')
    return one(s,
        '''      text <- getUtf8 size;
      checkRead (not (M.member compareString text names)) "duplicate binary symbol";
      let { nextTotal = total + size;
            nextNames = M.insert compareString text index names;
            nextSymbols = IM.insert index (Symbol text size) symbols };''',
        '''      text <- timedUtf8 (getUtf8 size);
      checkRead (not (Clock.demand "symbol.lookup" (M.member compareString text names))) "duplicate binary symbol";
      let { nextTotal = total + size;
            nextNames = Clock.demand "symbol.insert-name" (M.insert compareString text index names);
            nextSymbols = Clock.demand "symbol.insert-id" (IM.insert index (Symbol text size) symbols) };''')

def compiler(s,wrap,definitions):
    s=definitions(s,'demand',{'finishCompilation':'builtin.compile'})
    for expr,tag in [('C.generateProgram program','generate'),('C.solvePrepared constraints','solve'),
            ('E.prepareTypes graph','prepare-types'),('E.resolveEvidenceIn types (C.skeleton constraints)','resolve-evidence'),
            ('E.elaboratePreparedIn types solved evidence (C.skeleton constraints)','elaborate'),
            ('Checked.check term','verify-term'),
            ('X.equalErased (X.erase term)\n                       (C.eraseSourceWith evidence (C.skeleton constraints))','verify-erasure')]:
        s=wrap(s,expr,'builtin.'+tag)
    return s

def artifact(s,one,region):
    s=one(s,'  builtinPrelude =','  builtinPrelude = Clock.demand "builtin.construct" HP.$')
    s=one(s,' splitClosedDeclarationObject original =',' splitClosedDeclarationObject original = Clock.demand "builtin.split" HP.$')
    def edit(label,text):
        return text,'(Clock.demand "builtin.'+label+'" ('+text+'))'
    s=region(s,'  builtinPrelude =','  -- The supplied interface',[
        edit('resolve-modules','Modules.resolveCrate NoImplicitPrelude M.empty (definitionName identity)\n          ((:) Modules.preludeSource ((:) Modules.primitiveSource []))'),
        edit('lower','Classes.lowerSeparateClasses M.empty (map fst instances)\n          (SClassProgram sourceData classes (map snd instances) body)'),
        edit('bindings','Separate.collectBindings dataEnv (XEnv M.empty M.empty) implementation'),
        edit('validate-initial-iface','validateInterface (objectInterface object)')])
    return region(s,' splitClosedDeclarationObject original =','  builtinPrelude =',[
        edit('split.link-before','linkCrate (interfaceMap [iface]) originalLayouts (FragmentState 0 M.empty [] [] Set.empty) original'),
        edit('split.check-whole','Checked.check (Separate.objectTerm unit)'),
        edit('split.check-unit','Checked.check term'),
        edit('split.decl-bindings','Checked.declarationBindings old'),
        edit('split.decode-iface','decodeInterface (encodeInterface actual)'),
        edit('split.compare-iface','eqString (encodeInterface decodedInterface) (encodeInterface actual)'),
        edit('split.decode-object','decodeObject decodedInterface (encodeObject object)'),
        edit('split.compare-object','eqString (encodeObject decoded) (encodeObject object)'),
        edit('split.link-after','linkCrate (interfaceMap [decodedInterface]) layouts (FragmentState 0 M.empty [] [] Set.empty) decoded')])

def crate(s,wrap):
    return wrap(s,'eqString (Artifact.encodeInterface (Artifact.objectInterface builtin))\n                           (Artifact.encodeInterface (Artifact.objectInterface prior))','builtin.compare-installed')
