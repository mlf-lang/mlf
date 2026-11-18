"""Offline ordered evidence ledger. Never answers a Graph validation query.
Reads already-produced event strings; no compiler execution or payload forcing.
"""
import hashlib,json
from dataclasses import dataclass,field
@dataclass
class Frame:
    rule:str
    identity:str
    start:int
    events:list=field(default_factory=list)
    children:list=field(default_factory=list)
    outcome:str=''
    end:int=0

LABELS = frozenset(['alias:absent', 'alias:present', 'cache:kind-hit', 'dependency:global-euler', 'entry:binder-exists', 'entry:edge-gates', 'entry:global-root-binding-euler', 'entry:kind-fact', 'entry:node-binder', 'entry:require', 'entry:tag-kind', 'failure:binder-exists', 'failure:edge-gates', 'failure:global-root-binding-euler', 'failure:kind-fact', 'failure:node-binder', 'failure:require', 'failure:tag-kind', 'node:absent', 'node:present', 'selector:child-binder', 'selector:child-tag', 'selector:gen-flag', 'selector:kind-payload-not-forced', 'selector:parent-tag', 'selector:root-tag', 'selector:structural-tag-children', 'sparse:unobserved', 'success:binder-exists', 'success:edge-gates', 'success:global-euler', 'success:global-root-binding-euler', 'success:kind-fact', 'success:node-binder', 'success:require', 'success:tag-kind'])

def parse(text):
    if text=='<unavailable-on-Probe>\n':return {'status':'unavailable','frames':[],'reusable':False}
    if text=='sparse:unobserved\t-\n':return {'status':'sparse-unobserved','frames':[],'reusable':False}
    stack=[];roots=[];frames=[]
    for i,line in enumerate(text.splitlines(),1):
        if i>8192:raise ValueError('cap')
        parts=line.split('\t')
        if len(parts)!=2:raise ValueError('event arity')
        label,identity=parts
        if label not in LABELS:raise ValueError('unknown pinned-fixture event')
        if label=='success:global-euler' and (identity!='-' or not stack or stack[-1].rule!='global-root-binding-euler'):raise ValueError('global marker context')
        if identity!='-' and str(int(identity))!=identity:raise ValueError('identity')
        if label.startswith('entry:'):
            f=Frame(label[6:],identity,i)
            if stack:stack[-1].children.append(f)
            else:roots.append(f)
            stack.append(f);frames.append(f)
        elif label.startswith(('success:','failure:')) and label!='success:global-euler':
            status,rule=label.split(':',1)
            if not stack or (stack[-1].rule,stack[-1].identity)!=(rule,identity):raise ValueError('unbalanced completion')
            f=stack.pop();f.outcome=status;f.end=i
        else:
            if not stack:raise ValueError('event outside frame')
            if not label.startswith(('selector:','alias:','node:','dependency:','cache:')) and label!='success:global-euler':raise ValueError('unknown event')
            stack[-1].events.append((i,label,identity))
    if stack or not roots:raise ValueError('incomplete trace')
    def row(f):return dict(rule=f.rule,identity=f.identity,start=f.start,end=f.end,outcome=f.outcome,direct_events=f.events,children=[row(c) for c in f.children])
    return {'status':'complete-observation','frames':[row(f) for f in roots], 'frame_count':len(frames),
            'unkeyed_edge_frames':sum(f.rule=='edge-gates' and f.identity=='-' for f in frames),
            'global_euler_dependencies':sum(e[1]=='dependency:global-euler' for f in frames for e in f.events),
            'reusable':False}

def eligible(dependencies,changed,*,same_owner,prepasses_passed,complete_write_log,dense_mode=True):
    """Conservative metadata-only admission SPECIFICATION, not a production gate.
    Tuple tokens are synthetic selector names, not raw Node payloads.
    """
    if not all((same_owner,prepasses_passed,complete_write_log,dense_mode)):return False
    return set(dependencies).isdisjoint(changed)

def main(path):
    from pathlib import Path
    raw=Path(path).read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!='15c14ef13a72da74fbd52f38e9738715ea7f2a88':raise ValueError('pinned archive mismatch')
    j=json.loads(raw)
    reports={};seen=set()
    for f in j['sidecars']:
        if f['name'] in seen:raise ValueError('duplicate sidecar')
        seen.add(f['name'])
        b=f['utf8'].encode()
        if len(b)!=f['bytes'] or hashlib.sha256(b).hexdigest()!=f['sha256']:raise ValueError('sidecar integrity')
        if f['name'].endswith('.events'):reports[f['name']]=parse(f['utf8'])
    return dict(source_commit='d9c14d396353dffe2b5cebbcfb78aeb91817a9df',all_sidecars_verified=len(j['sidecars']),reports=reports,production_eligible=False)
if __name__=='__main__':
    import sys
    print(json.dumps(main(sys.argv[1]),indent=2))
