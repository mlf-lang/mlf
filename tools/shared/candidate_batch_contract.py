"""Candidate-selection batch output projections, not fresh-process equivalence."""
import hashlib

BEGIN, END = 812350001, 812350002
FORWARD = tuple(range(24))
REVERSE = tuple(reversed(FORWARD))
SCOPE = '24 logical projections; not 24 fresh interpreter processes or general state/GC equivalence'
def require(ok, message):
    if not ok: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def cases():
    # Independent literal-sized inventory of the original first twelve vectors.
    vectors=[(n,0,ids) for n in (0,1,2,7)
             for ids in ([],[-1,n],[0,0,1,n-1])]
    result={}
    for selector in ('named','ids'):
        for index,(n,period,ids) in enumerate(vectors):
            key=len(result)
            expected=(''.join('i:n%d;'%i for i in range(n) if i in set(ids))+
                      's:super;g:given;i:n0;i:n0;\n').encode('ascii')
            result[key]=dict(selector=selector,index=index,
                arguments=[selector,*map(str,[n,period,len(ids),*ids])],expected=expected)
    require(len(result)==24,'24 interpreter observations')
    return result

def order_for(direction):
    require(direction in ('forward','reverse'),'direction')
    return FORWARD if direction=='forward' else REVERSE

def parse(raw,direction):
    require(type(raw)is bytes and len(raw)<=32768,'bounded actual bytes')
    lines=raw.splitlines(keepends=True)
    require(len(lines)==96,'24 complete framed observations')
    rows=[]; offset=0
    for position,index in enumerate(order_for(direction)):
        chunk=lines[position*4:position*4+4]
        expected=cases()[index]['expected']
        require(chunk==[('%d\n'%BEGIN).encode(),('%d\n'%index).encode(),
                        expected,('%d\n'%END).encode()],'exact marker/order/result bytes')
        start=offset+len(chunk[0])+len(chunk[1]);end=start+len(chunk[2])
        rows.append(dict(index=index,arguments=cases()[index]['arguments'],
            start=start,end=end,actual_ascii=raw[start:end].decode('ascii'),
            actual_sha256=digest(raw[start:end])))
        offset+=sum(map(len,chunk))
    require(offset==len(raw),'unconsumed bytes')
    return rows

def physical_record(command_id,lane,direction,argv,stdout,stderr,exit_code):
    require(type(command_id)is str and bool(command_id),'physical identity')
    require(lane in ('host','interpreter'),'physical lane')
    require(type(argv)is list and bool(argv) and all(type(a)is str for a in argv),'physical argv')
    require(type(exit_code)is int and exit_code==0 and stderr==b'','physical success')
    return dict(id=command_id,lane=lane,direction=direction,argv=argv,
        exit_code=exit_code,stdout_sha256=digest(stdout),stdout_bytes=len(stdout),
        stderr_sha256=digest(stderr),vectors=parse(stdout,direction),scope=SCOPE)

def project(record,stdout,index,original_argv,original_expected):
    require(record['stdout_sha256']==digest(stdout),'capture identity')
    require(parse(stdout,record['direction'])==record['vectors'],'physical vectors changed')
    require(type(index)is int and index in FORWARD,'logical index')
    row=next(r for r in record['vectors'] if r['index']==index)
    args=cases()[index]['arguments']
    require(type(original_argv)is list and original_argv[-len(args):]==args,'exact logical arguments')
    actual=stdout[row['start']:row['end']]
    require(type(original_expected)is bytes and actual==original_expected,'independent expected output')
    return dict(physical_command_id=record['id'],index=index,original_argv=original_argv,
        start=row['start'],end=row['end'],actual_ascii=actual.decode('ascii'),
        actual_sha256=digest(actual),physical_stdout_sha256=digest(stdout),
        fresh_process=False,kind='verified-batch-projection')

def aggregate(physical,projections):
    require(len(physical)==4 and len({p['id'] for p in physical})==4,'four distinct physical batches')
    require({(p['lane'],p['direction']) for p in physical}==
        {(lane,d) for lane in ('host','interpreter') for d in ('forward','reverse')},'four lane/directions')
    require(len(projections)==96,'96 actual projections')
    by_id={p['id']:p for p in physical};seen=set()
    for p in physical:
        # Regenerate expected framing, never a physical execution record.
        expected=b''.join(('%d\n%d\n'%(BEGIN,i)).encode()+cases()[i]['expected']+
            ('%d\n'%END).encode() for i in order_for(p['direction']))
        require(type(p['exit_code'])is int and p['exit_code']==0 and
            p['stderr_sha256']==digest(b'') and p['stdout_sha256']==digest(expected) and
            type(p['stdout_bytes'])is int and p['stdout_bytes']==len(expected) and
            p['vectors']==parse(expected,p['direction']),'physical capture ledger')
    for row in projections:
        require(type(row['index'])is int and row['index'] in FORWARD,'projection index')
        key=(row['physical_command_id'],row['index'])
        require(key not in seen and key[0] in by_id,'duplicate/unknown projection')
        seen.add(key);p=by_id[key[0]];source=next(x for x in p['vectors'] if x['index']==key[1])
        require(type(row['start'])is int and type(row['end'])is int and
            row['kind']=='verified-batch-projection' and row['fresh_process'] is False and
            row['physical_stdout_sha256']==p['stdout_sha256'] and
            all(row[k]==source[k] for k in ('start','end','actual_ascii','actual_sha256')) and
            row['original_argv'][-len(source['arguments']):]==source['arguments'],
            'projection binding/offset/result')
    require(seen=={(p,i) for p in by_id for i in FORWARD},'exact projection coverage')
    return dict(batch_complete=True,physical_batch_count=4,logical_projection_count=96,
        original_interpreter_vectors=24,whole_candidate_complete=False,scope=SCOPE)
