"""Pure byte-level cross-compiler Fixture publication qualification.
No filesystem, imports of repository code, execution, cache edits or normalization.
The caller supplies complete raw maps and independently authenticated executable SHAs.
"""
import hashlib, re, struct, zlib
MAX_BYTES = 268435456
MAX_NODES = 4194304
MAX_EDGES = 16777216
MAX_SYMBOLS = 1048576
MAX_SYMBOL_BYTES = 16777216
MAX_TOTAL_SYMBOL_BYTES = 134217728
MAX_DEPTH = 16384
MAX_WORK = 67108864
PREFIX = 'builtin-work/queries/query-graph-v2/'
STATIC = {'builtin.mlfci','builtin.mlfco','builtin.lock','builtin-work/Fixture.emlf',
          'builtin-work/fixture.spec','builtin-work/fixture.mlfci','builtin-work/fixture.mlfco',
          'builtin-work/fixture.queries','builtin-work/queries/.lock'}


def need(ok, message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None,'canonical SHA256 required')
    return value


class Bits:
    def __init__(self, raw, start, end):
        self.raw=raw; self.i=start*8; self.end=end*8
        need(0<=self.i<=self.end<=len(raw)*8,'bounded section')
    def get(self,width):
        need(type(width) is int and 0<=width<=64 and self.i+width<=self.end,'truncated/invalid bit field')
        value=0
        for j in range(width):
            value|=((self.raw[self.i//8]>>(self.i%8))&1)<<j;self.i+=1
        return value
    def var(self):
        value=0
        for n in range(10):
            x=self.get(8); value|=(x&127)<<(7*n)
            if x<128:
                need((n==0 or x>0) and value<2**64,'noncanonical/overflow varint')
                return value
        raise ValueError('overlong varint')
    def finish(self):
        need(0<=self.end-self.i<8,'unconsumed section bytes')
        need(self.get(self.end-self.i)==0,'nonzero padding')


def symbol_budget(size,total):
    need(0<=size<=MAX_SYMBOL_BYTES and size<=MAX_TOTAL_SYMBOL_BYTES-total,'symbol byte limits')
    return total+size


def node_resources(row,symbols,depths,works):
    depth=1;work=1
    if row[0]=='text':work+=symbols[row[1]]['bytes']
    elif row[0]=='node':
        need(0<=row[1]<=2147483647,'constructor tag range')
        for ref in row[2]:
            depth=max(depth,depths[ref]+1);work+=works[ref]
            need(depth<=MAX_DEPTH and work<=MAX_WORK,'expanded node depth/work limits')
    need(depth<=MAX_DEPTH and work<=MAX_WORK,'expanded node depth/work limits')
    return depth,work


def packed_size(lengths):
    size=sum(n+len(str(n))+1 for n in lengths)
    need(size<=MAX_WORK,'snapshot packed identity budget')
    return size


def identity_lengths(lengths):
    need(all(n>0 for n in lengths) and sum(lengths)<=MAX_WORK,'snapshot table/row identity budget')
    return lengths


def decode(raw,schema):
    need(type(raw) is bytes and 80<=len(raw)<=MAX_BYTES and raw[:8]==b'MLFBIN\r\n','container magic/size')
    names=['version','flags','schema','header_bytes','total_bytes','symbols','symbol_offset','symbol_bytes','nodes','node_offset','node_bytes','edges','roots','root_offset','root_bytes','node_width','symbol_width','crc32']
    h=dict(zip(names,struct.unpack('<18I',raw[8:80])))
    need(h['version']==1 and h['flags']==0 and h['schema']==schema and h['header_bytes']==h['symbol_offset']==80 and h['total_bytes']==len(raw),'exact header')
    need(h['node_offset']==80+h['symbol_bytes'] and h['root_offset']==h['node_offset']+h['node_bytes'] and len(raw)==h['root_offset']+h['root_bytes'],'sections/trailing bytes')
    need(h['symbols']<=min(MAX_SYMBOLS,h['symbol_bytes']) and h['nodes']<=MAX_NODES and h['nodes']*2<=h['node_bytes']*8 and h['edges']<=MAX_EDGES and h['roots']<=h['nodes'],'bounded counts')
    need(h['root_bytes']==(h['roots']*h['node_width']+7)//8 and h['node_width']==max(1,(h['nodes']-1).bit_length()) and h['symbol_width']==max(1,(h['symbols']-1).bit_length()),'canonical widths/root bytes')
    need(zlib.crc32(raw[:76]+bytes(4)+raw[80:])==h['crc32'],'container CRC')
    symbols=[];symbol_bytes=0;r=Bits(raw,80,h['node_offset'])
    for _ in range(h['symbols']):
        prefix=r.i//8;n=r.var();start=r.i//8
        symbol_bytes=symbol_budget(n,symbol_bytes)
        need(n<=(r.end-r.i)//8,'symbol length beyond section')
        data=bytes(r.get(8) for _ in range(n));text=data.decode('utf8')
        need(text.encode('utf8')==data,'strict UTF8 roundtrip')
        symbols.append({'text':text,'prefix':prefix,'start':start,'bytes':n})
    r.finish();need(len({s['text'] for s in symbols})==len(symbols),'duplicate symbol')
    nodes=[];depths=[];works=[];r=Bits(raw,h['node_offset'],h['root_offset']);edge_count=0;keys=set()
    for i in range(h['nodes']):
        kind=r.get(2)
        if kind==0:
            n=r.var();row=('int',(n>>1)^-(n&1))
        elif kind==1:row=('bits',r.get(64))
        elif kind==2:
            n=r.get(h['symbol_width']);need(n<len(symbols),'symbol index');row=('text',n)
        else:
            tag=r.var();n=r.var()
            need(n<=h['edges']-edge_count and n*h['node_width']<=r.end-r.i,'edge count/section')
            refs=tuple(r.get(h['node_width']) for _ in range(n));need(all(x<i for x in refs),'acyclic backward reference')
            edge_count+=n;row=('node',tag,refs)
        need(row not in keys,'duplicate canonical node');keys.add(row)
        depth,work=node_resources(row,symbols,depths,works);depths.append(depth);works.append(work);nodes.append(row)
    r.finish();need(edge_count==h['edges'],'complete edge count')
    r=Bits(raw,h['root_offset'],len(raw));roots=tuple(r.get(h['node_width']) for _ in range(h['roots']))
    need(all(i<len(nodes) for i in roots),'root bounds');r.finish()
    need(sum(works[i] for i in roots)<=MAX_WORK,'aggregate expanded root work')
    # Iterative traversal avoids Python recursion limits; every wire node must be canonical/reachable.
    seen=set();post=[]
    for root in roots:
        stack=[(root,False)]
        while stack:
            i,done=stack.pop()
            if done:post.append(i);continue
            if i in seen:continue
            seen.add(i);stack.append((i,True))
            if nodes[i][0]=='node':stack.extend((j,False) for j in reversed(nodes[i][2]))
    need(post==list(range(len(nodes))),'canonical reachable postorder')
    first=[];used=set()
    for n in nodes:
        if n[0]=='text' and n[1] not in used:used.add(n[1]);first.append(n[1])
    need(first==list(range(len(symbols))),'canonical complete symbol order')
    return {'header':h,'symbols':symbols,'nodes':nodes,'roots':roots}


def scalar(g,i,kind):
    need(type(i) is int and 0<=i<len(g['nodes']),'scalar index')
    n=g['nodes'][i];need(n[0]==kind,'scalar kind')
    return g['symbols'][n[1]]['text'] if kind=='text' else n[1]


def node(g,i,tag):
    need(type(i) is int and 0<=i<len(g['nodes']),'node index')
    n=g['nodes'][i];need(n[0]=='node' and n[1]==tag,'node tag');return n[2]


def packed(text):
    fields=[];spans=[];i=0
    while i<len(text):
        end=text.find(':',i);need(end>=i,'packed delimiter')
        length=text[i:end];need(re.fullmatch('0|[1-9][0-9]*',length) is not None,'packed canonical length')
        n=int(length);i=end+1;need(n<=len(text)-i,'packed truncated field')
        fields.append(text[i:i+n]);spans.append((i,i+n));i+=n
    return fields,spans


def snapshot(g,compiler):
    digest(compiler);need(len(g['roots'])==1,'one snapshot root')
    root=g['roots'][0];ids=node(g,root,412);need(len(ids)==7,'exact snapshot fields')
    fmt,config,declarations,groups,evidence,types,entries=ids
    need(scalar(g,fmt,'text')=='MLF-CRATE-QUERY-GRAPH-2','snapshot format')
    text=scalar(g,config,'text');fields,spans=packed(text)
    need(fields==['compiler-shapes/builtin',compiler,'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1','source'],'exact configuration including actual compiler SHA')
    incoming=[(i,j) for i,n in enumerate(g['nodes']) if n[0]=='node' for j,v in enumerate(n[2]) if v==config]
    need(incoming==[(root,1)] and config not in g['roots'],'configuration confined to its one field')
    ds=[scalar(g,i,'text') for i in node(g,declarations,1)];ts=[scalar(g,i,'text') for i in node(g,types,1)]
    need(ds==sorted(set(ds)) and ts==sorted(set(ts)) and all(ds) and all(ts),'canonical declaration/type dictionary')
    gs=[]
    for i in node(g,groups,1):
        row=tuple(scalar(g,j,'int') for j in node(g,i,1))
        need(row and len(row)==len(set(row)) and all(0<=x<len(ds) for x in row),'group indices')
        gs.append(row)
    need(len(set(gs))==len(gs),'unique groups')
    es=[]
    for i in node(g,evidence,1):
        v=node(g,i,414);need(len(v)==3,'evidence arity');a,b,c=v
        row=(scalar(g,a,'int'),scalar(g,b,'int'),scalar(g,c,'text'))
        need(0<=row[0]<len(gs) and row[1]>=0 and row[2]!='','evidence indices/site/nonempty goal');es.append(row)
    need(len(set(es))==len(es),'unique evidence')
    ds_size=identity_lengths([len(x) for x in ds]);ts_size=identity_lengths([len(x) for x in ts])
    gs_size=identity_lengths([packed_size([ds_size[j] for j in row]) for row in gs])
    es_size=identity_lengths([packed_size([gs_size[row[0]],len(str(row[1])),len(row[2])]) for row in es])
    def descriptor_size(desc):
        tag,x=desc
        names={0:'Binding',415:'Binding',416:'Prepared',417:'ScopeInventory',418:'Scope',419:'InferScc',431:'FinishScc',432:'Evidence',433:'Datatype',434:'Datatype'}
        sizes=ds_size if tag in (0,415) else gs_size if tag in (416,417,418,419,431) else es_size if tag==432 else ts_size
        size=packed_size([len(names[tag]),sizes[x]])
        return packed_size([len('Input'),size]) if tag in (415,416,417,434) else size
    def descriptor(i):
        n=g['nodes'][i]
        if n[0]=='int':tag=0;x=n[1];limit=len(ds)
        else:
            need(n[0]=='node' and n[1] in (415,416,417,418,419,431,432,433,434) and len(n[2])==1,'descriptor tag/arity')
            tag=n[1];x=scalar(g,n[2][0],'int');limit=len(ds) if tag==415 else len(gs) if tag in (416,417,418,419,431) else len(es) if tag==432 else len(ts)
        need(0<=x<limit,'descriptor dictionary index');return (tag,x)
    rows=[];bydesc={};byvalue=set()
    for i in node(g,entries,1):
        v=node(g,i,413);need(len(v)==4,'entry arity');key,hashnode,reads,location=v
        desc=descriptor(key);need(key not in bydesc and desc not in byvalue,'duplicate descriptor');byvalue.add(desc)
        value=digest(scalar(g,hashnode,'text'));refs=node(g,reads,1)
        for r in refs:descriptor(r)
        # Production keeps repeated reads and their order; never deduplicate.
        loc=g['nodes'][location];need(loc[0]=='node' and loc[1] in (4,5) and len(loc[2])==(0 if loc[1]==4 else 1),'payload location')
        payload=None if loc[1]==4 else digest(scalar(g,loc[2][0],'text'))
        need(payload is None or payload==value,'payload content address')
        row={'key':key,'descriptor':desc,'digest':value,'reads':refs,'payload':payload};rows.append(row);bydesc[key]=row
    need(all(j in bydesc for row in rows for j in row['reads']),'complete dependency closure')
    identity_lengths([descriptor_size(row['descriptor']) for row in rows])
    done=set();visiting=set();heights={}
    for key in bydesc:
        stack=[(key,False)]
        while stack:
            i,exit=stack.pop()
            if exit:
                heights[i]=1+max((heights[j] for j in bydesc[i]['reads']),default=0)
                need(heights[i]<=4096,'query longest path limit')
                visiting.remove(i);done.add(i);continue
            if i in done:continue
            need(i not in visiting,'query dependency cycle');visiting.add(i);stack.append((i,True))
            stack.extend((j,False) for j in reversed(bydesc[i]['reads']))
    sym=g['symbols'][g['nodes'][config][1]];lo,hi=spans[1]
    start=sym['start']+len(text[:lo].encode('utf8'));end=start+len(text[lo:hi].encode('utf8'))
    need(end-start==64,'fixed actual SHA extent')
    return {'config_symbol':g['nodes'][config][1],'compiler_span':(start,end),'configuration':fields,'declarations':ds,'groups':gs,'evidence':es,'types':ts,'rows':rows}


def publication(files,compiler):
    need(type(files) is dict and files and len(files)<=4096 and all(type(k) is str and type(v) is bytes for k,v in files.items()),'raw map')
    need(sum(map(len,files.values()))<=MAX_BYTES,'aggregate fixture byte bound')
    need(STATIC<=files.keys(),'missing fixed fixture files')
    need(files['builtin.lock']==files['builtin-work/queries/.lock']==b'','empty lock artifacts')
    current=PREFIX+'CURRENT';need(current in files,'missing CURRENT')
    cg=decode(files[current],6)
    need(cg['header']['symbols']==cg['header']['nodes']==cg['header']['roots']==1 and cg['header']['edges']==0,'single text CURRENT container')
    address=digest(scalar(cg,cg['roots'][0],'text'));generation=PREFIX+'generations/'+address+'.mlfqg'
    need(generation in files and sha(files[generation])==address,'generation filename/content SHA')
    g=decode(files[generation],6);s=snapshot(g,compiler)
    results={PREFIX+'results/'+r['payload']+'.mlfqr' for r in s['rows'] if r['payload'] is not None}
    need(set(files)==STATIC|{current,generation}|results,'exact complete fixture inventory, no missing/extra results or files')
    for rel in sorted(results):
        need(sha(files[rel])==rel.rsplit('/',1)[1][:-6],'result content address')
        decode(files[rel],6)
    # Checked/interface container bytes are identical across sides, and independently structurally decoded.
    for rel,schema in [('builtin.mlfci',3),('builtin.mlfco',4),('builtin-work/fixture.mlfci',3),('builtin-work/fixture.mlfco',8)]:decode(files[rel],schema)
    return {'generation':generation,'current':current,'graph':g,'snapshot':s,'current_graph':cg,'result_count':len(results),'files':len(files)}


def exact_except(left,right,spans):
    need(len(left)==len(right),'same byte length required')
    cursor=0
    for lo,hi in sorted(spans):
        need(cursor<=lo<=hi<=len(left),'nonoverlapping explicit byte spans')
        need(left[cursor:lo]==right[cursor:lo],'unallowed raw byte difference')
        cursor=hi
    need(left[cursor:]==right[cursor:],'unallowed raw byte tail difference')


def compare_fixture(ordinary,stats,ordinary_sha,stats_sha):
    a=publication(ordinary,ordinary_sha);b=publication(stats,stats_sha)
    ag,bg=a['generation'],b['generation'];current=a['current']
    need(set(ordinary)-{ag}==set(stats)-{bg},'relative inventory equality except authenticated generation names')
    for rel in ordinary:
        if rel not in (ag,current):need(ordinary[rel]==stats[rel],'semantic artifact bytes changed: '+rel)
    ga,gb=a['graph'],b['graph'];sa,sb=a['snapshot'],b['snapshot']
    need(ga['nodes']==gb['nodes'] and ga['roots']==gb['roots'],'exact node/root tables')
    need(sa['compiler_span']==sb['compiler_span'] and sa['config_symbol']==sb['config_symbol'],'same configuration field position')
    need(len(ga['symbols'])==len(gb['symbols']),'symbol count')
    for i,(x,y) in enumerate(zip(ga['symbols'],gb['symbols'])):
        if i!=sa['config_symbol']:need(x==y,'nonconfiguration symbol changed')
        else:need({k:v for k,v in x.items() if k!='text'}=={k:v for k,v in y.items() if k!='text'},'configuration framing changed')
    exact_except(ordinary[ag],stats[bg],[(76,80),sa['compiler_span']])
    ca,cb=a['current_graph'],b['current_graph']
    need(ca['nodes']==cb['nodes'] and ca['roots']==cb['roots'],'CURRENT shape')
    x,y=ca['symbols'][0],cb['symbols'][0]
    need({k:v for k,v in x.items() if k!='text'}=={k:v for k,v in y.items() if k!='text'} and x['bytes']==64,'CURRENT framing')
    exact_except(ordinary[current],stats[current],[(76,80),(x['start'],x['start']+64)])
    if ordinary_sha==stats_sha:need(ordinary==stats,'same compiler requires complete raw identity')
    return {'schema':'main-gap-cross-compiler-fixture-equivalence-v1','complete':True,
        'ordinary_compiler_sha256':ordinary_sha,'stats_compiler_sha256':stats_sha,
        'ordinary_generation':ag,'stats_generation':bg,'files_each':a['files'],'result_files':a['result_count'],
        'rows':len(sa['rows']),'compiler_sha_span':list(sa['compiler_span']),
        'allowed_differences':['configuration field1 actual executable SHA','derived container CRC32','derived generation filename SHA256','CURRENT exact derived digest and CRC32'],
        'all_other_raw_bytes_equal':True,'containers_fully_decoded':True,'result_closure_exact':True,
        'full_cross_compiler_raw_equality_claimed':ordinary==stats,'same_binary_future_raw_identity_required':True,
        'artifact_normalization_or_rewrite':False}
