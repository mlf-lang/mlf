import hashlib, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
def git(*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('status','--porcelain') == ''
base = git('rev-parse','HEAD')
assert base in ['d8325d909c249fd82d4ad6173d44d8818cc6f8bf','ee495d5783fca3c26a3c0e659ebeac1bab76a37d']
def mark(rel, blob, edits):
    assert git('rev-parse','HEAD:'+rel) == blob
    p=root/rel;s=p.read_text()
    for needle,marker in edits:
        assert s.count(needle)==1,needle
        indent=needle[:len(needle)-len(needle.lstrip())]
        s=s.replace(needle,indent+'putErr "PATRICIA:'+marker+'\\n";\n'+needle)
    p.write_text(s)
mark('bootstrap/MLF/Entry/Emlf.hs','e6c53e6ece214b7612d1e4964b5bd8a8073a11bd',[
('          compiled <-\n            case source of {','entered-source-command'),
('          case compiled of {\n            Left error -> fatal (C.prettyError error);','compile-io-returned'),
('                    putStrLn ((if onlyType then "" else "-- type: ") ++ Prepared.sourceType result);','right-before-type-output')])
mark('bootstrap/MLF/PreparedCompiler.hs','e24accb680946743bd37fdc1bd48ce0dbfb006bf',[
('        loaded <- Modules.loadModuleFilesWithEvidenceUsing LibraryData.parseLibrary paths source input;','before-import-io')])
git('add','--','bootstrap/MLF/Entry/Emlf.hs','bootstrap/MLF/PreparedCompiler.hs')
git('-c','user.name=Patricia diagnostic','-c','user.email=diag@localhost','commit','-m','Temporary stderr-only phase markers')
assert git('rev-parse','HEAD^') == base and git('status','--porcelain') == ''
