"""Authenticate the reviewed A1 and Patricia maintenance child of the published PR55 tree."""
PARENT = '8402e29040d5786d79dbcc3ccc9e8e047208c399'
TREE = '0b73c8e68e014f282f9e991d6d62262ba2785a0d'
SOURCE = '010508904b6882e9070ffa0cc9be9846dc22e290'
SELF = 'tools/performance/artifact-binary/phase2_a1_overlay.py'
SUCCESSOR = 'tools/performance/artifact-binary/phase2_source_successor.py'
LOADER = 'tools/release/check_benchmark_phase2_successor.py'
MANIFEST = 'tools/release/test-suites.json'
ADAPTER = 'tools/performance/a1-private-index/test_phase2_current.py'
TEST = 'tools/release/test_a1_phase2_overlay.py'
PATRICIA = 'tools/release/test_phase2_patricia_adapters.py'
EXTERNAL = 'tests/external-suites.json'
INSERT = b"    if git.commit(metadata) == ['8402e29040d5786d79dbcc3ccc9e8e047208c399']:\n        overlay = pinned_module(HERE, 'phase2_a1_overlay.py', 'SELF')\n        metadata = overlay.predecessor(git, source_root, metadata, read, sha, oid, require)\n"
REVIEWED = {ADAPTER:'19fbde9e50909f001ebd76e3f06e7fe8a5574cf84c60581a5bb38d02bbf2ef90', TEST:'50bbe3cb423a0d685f46001b8b5bf78c703cc3c83e89cf2565f408b05601612d', PATRICIA:'bafb68265d914c9768f930b0a091de871941b056a875fdc90bfbae323c9ad3ba'}


def predecessor(git, root, child, read, sha, oid, require):
    git.commit(PARENT, TREE, [SOURCE])
    git.commit(child, parents=[PARENT])
    statuses = {SELF:'A', SUCCESSOR:'M', LOADER:'M', MANIFEST:'M', ADAPTER:'A', TEST:'A', PATRICIA:'A', EXTERNAL:'M'}
    parts = git.run('diff', '--no-renames', '--name-status','-z',PARENT,child).split(b'\0')
    require(parts[-1]==b'' and len(parts)==1+2*len(statuses) and
            {p.decode():s.decode() for s,p in zip(parts[::2],parts[1::2])}==statuses,
            'exact A1 maintenance overlay')
    physical = {p:read(root,p,131072) for p in statuses}
    entries = git.run('ls-tree','-rz',child,'--',*statuses).split(b'\0')
    require(set(entries)=={b'',*(('100644 blob '+oid(raw)+'\t'+p).encode()
                                   for p,raw in physical.items())},'A1 physical and tracked blob/mode')
    require(all(sha(physical[p])==h for p,h in REVIEWED.items()),'reviewed A1 adapter and regression')
    def parent(path):
        return git.run('cat-file','blob',PARENT+':'+path)
    def edit(path,before,after,message):
        old = parent(path)
        require(old.count(before)==1 and old.replace(before,after)==physical[path],message)
    edit(MANIFEST, b'"tools/performance/a1-private-index/test_current.py"',
         b'"tools/performance/a1-private-index/test_phase2_current.py"','only the exact A1 suite route')
    edit(EXTERNAL, b'"tools/performance/patricia/test_adapters.py"',
         b'"tools/release/test_phase2_patricia_adapters.py"', 'only the exact Patricia suite route')
    line=b'    parents = git.commit(metadata)\n'
    edit(SUCCESSOR,line,INSERT.replace(b'SELF',sha(physical[SELF]).encode())+line,
         'exact successor loader extension; all prior checks preserved')
    edit(LOADER,sha(parent(SUCCESSOR)).encode(),sha(physical[SUCCESSOR]).encode(),
         'exact unchanged benchmark loader and successor pin')
    return PARENT
