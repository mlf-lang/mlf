"""Extracted regression fixture only; not a runnable experiment controller."""
def preserved_shape(c):
    r=failure(c);root=R/'main-cpu-attribution-run02'
    expected=load(verify_pin(r['run_scope_files']));dirs=load(verify_pin(r['run_scope_directories']))
    names=[];actualdirs=[]
    for folder,children,files in os.walk(root,followlinks=False):
        for name in children:
            p=Path(folder)/name;require(stat.S_ISDIR(p.lstat().st_mode),'preserved old directory type');actualdirs.append(str(p.relative_to(root)))
        for name in files:
            p=Path(folder)/name;require(stat.S_ISREG(p.lstat().st_mode) and p.lstat().st_nlink==1,'preserved old file type/alias');names.append(str(p))
    require(sorted(names)==[x['path'] for x in expected] and sorted(actualdirs)==dirs,'entire original run02 inventory unchanged')
    b,bc=base(c);b.verify_old_scope(bc)
    return expected
