"""Pure synthetic checker tests. No compiler, subprocess, network or real artifacts."""
import hashlib,json,struct,sys,zlib
from pathlib import Path
import artifact_checks as c
import sampling_policy as sampling
def pack(xs):return ''.join(str(len(x))+':'+x for x in xs)
def frame(schema,group,stage='raw'):
    symbols=[stage,group,'fragment'];syms=bytearray()
    def var(n):
        out=[]
        while n>=128:out.append((n&127)|128);n>>=7
        return out+[n]
    for s in symbols:
        b=s.encode();syms.extend(var(len(b)));syms.extend(b)
    bits=[]
    def put(n,w):bits.extend((n>>i)&1 for i in range(w))
    def pv(n):
        for b in var(n):put(b,8)
    for i in range(3):put(2,2);put(i,2)
    put(3,2);pv(1);pv(0)
    put(3,2);pv(400);pv(7)
    for i in [0,1,2,3,3,3,3]:put(i,3)
    put(3,2);pv(425);pv(2)
    for i in [3,4]:put(i,3)
    nodes=bytes(sum(bits[j+i]<<i for i in range(min(8,len(bits)-j)))for j in range(0,len(bits),8))
    roots=bytes([5]);no=80+len(syms);ro=no+len(nodes);total=ro+1
    h=b'MLFBIN\r\n'+struct.pack('<18I',1,0,schema,80,total,3,80,len(syms),6,no,len(nodes),9,1,ro,1,3,2,0)
    b=h+syms+nodes+roots
    return b[:76]+struct.pack('<I',zlib.crc32(b))+b[80:]
def main():
    out=Path(sys.argv[1]);out.mkdir();cache=out/'cache';results=cache/'query-graph-v2/results';results.mkdir(parents=True)
    crate='checker/1/library';member='module_'+c.encoded(crate)+'z_'+c.encoded(pack(['Owner','f','value','']))
    group='Query_'+c.encoded(crate)+'z_'+c.encoded(member)
    contract=dict(crate_id=crate,expected_groups=None,expected_value_modules=['Owner'],required_members=[member])
    raw=frame(6,group);key=hashlib.sha256(raw).hexdigest()
    report=dict(format=1,crate=crate,inferred_groups=1,reused_groups=0,groups=[dict(id=group,members=[member],cached=False,semantic_fingerprint='contracts-not-raw',query_key=key)])
    prefix=out/'unit';ci=Path(str(prefix)+'.mlfci');co=Path(str(prefix)+'.mlfco');q=Path(str(prefix)+'.queries')
    ci.write_bytes(frame(3,group));co.write_bytes(frame(8,group))
    def setup(data=raw,k=None):
        for p in results.iterdir():p.unlink()
        digest=hashlib.sha256(data).hexdigest()if k is None else k
        (results/(digest+'.mlfqr')).write_bytes(data);report['groups'][0]['query_key']=digest
        q.write_text(json.dumps(report))
    def check():return c.full_artifact(prefix,cache,contract,lambda:None)
    passed=[]
    def reject(name,fn):
        try:fn()
        except ValueError:passed.append(name);return
        raise AssertionError(name+' did not reject')
    setup();r=check();assert r['coverage']['inferred_groups']==1;passed.append('valid-schema6-group')
    broken=raw[:-1]+bytes([raw[-1]^1]);setup(broken);reject('bad-crc',check)
    setup(raw,'0'*64);reject('wrong-content-key',check)
    setup(frame(6,group+'wrong'));reject('wrong-group',check)
    setup(frame(6,group,'not-raw'));reject('wrong-stage',check)
    setup();report['groups'][0]['cached']=True;q.write_text(json.dumps(report));reject('cached',check);report['groups'][0]['cached']=False
    setup();contract['expected_value_modules']=['Owner','Missing'];reject('missing-owner',check);contract['expected_value_modules']=['Owner']
    x=out/'left';y=out/'right';x.write_bytes(b'abc');y.write_bytes(b'abd');reject('unequal-raw',lambda:c.same_raw(x,y,lambda:None))
    setup();check()
    temporary='work/query-cache/query-graph-v2/staging/'+'a'*64+'.mlfqr'
    probe=out/'sampling';probe.mkdir()
    def vanished(relative,active):
        path=probe/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'x')
        enumerated=list(path.parent.iterdir());assert path in enumerated
        path.unlink()
        return sampling.sample_lstat(next(p for p in enumerated if p==path),probe,'A',active)
    def rejects_os(name,fn,kind):
        try:fn()
        except kind:passed.append(name);return
        raise AssertionError(name+' did not reject')
    assert vanished(temporary,True)==(None,'staged-result');passed.append('active-enumerated-transient-vanish')
    rejects_os('active-fixed-vanish-rejected',lambda:vanished('work/unit.mlfci',True),FileNotFoundError)
    rejects_os('terminal-transient-vanish-rejected',lambda:vanished(temporary,False),FileNotFoundError)
    rejects_os('inactive-evidence-vanish-rejected',lambda:vanished(temporary.replace('work/','evidence-A/'),True),FileNotFoundError)
    def denied():raise PermissionError(13,'controlled permission failure',str(probe/temporary))
    rejects_os('non-ENOENT-propagates',lambda:sampling.sample_lstat(probe/temporary,probe,'A',True,denied),PermissionError)
    assert not sampling.terminal_quiescent(None,True);passed.append('missing-cleanup-receipt-rejected')
    good=dict(phase='terminal',cleanup_complete=True,survivors=[])
    assert sampling.terminal_quiescent(good,True)
    assert not sampling.terminal_quiescent(good,False)
    assert not sampling.terminal_quiescent(dict(phase='terminal',survivors=[]),True)
    passed.append('terminal-cleanup-required')
    print(json.dumps(dict(complete=True,cases=passed,compiler_executed=False)))
if __name__=='__main__':main()
