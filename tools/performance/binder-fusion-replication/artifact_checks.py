"""Bounded checked-crate wire integrity and query-coverage checks, not typed decoding."""
import json,re,struct,zlib
from pathlib import Path

def need(ok,message):
    if not ok:raise ValueError(message)

def encoded(text):return ''.join(str(ord(c))+'_' for c in text)

def decoded(text):
    need(bool(re.fullmatch(r'(?:[0-9]+_)+',text)),'noncanonical encoded scalar sequence')
    codes=[int(x) for x in text[:-1].split('_')]
    need(all(x<=0x10ffff and not 0xd800<=x<=0xdfff for x in codes),'invalid Unicode scalar')
    result=''.join(chr(x)for x in codes);need(encoded(result)==text,'noncanonical decimal scalar');return result

def unpack(text):
    values=[];index=0
    while index<len(text):
        end=text.find(':',index);need(end>index,'malformed framed field');number=text[index:end]
        need(number.isascii() and number.isdigit() and str(int(number))==number,'noncanonical framed length')
        count=int(number);index=end+1;need(count<=len(text)-index,'truncated framed field');values.append(text[index:index+count]);index+=count
    return values

def member_owner(member,crate):
    ordinary='module_'+encoded(crate)+'z_';instance='instance_'+encoded(crate)+'z_'
    if member.startswith(ordinary):
        fields=unpack(decoded(member[len(ordinary):]));need(len(fields)==4 and fields[1] and fields[2] in ['value','method'],'invalid query entity')
        need((fields[2]=='value' and fields[3]=='')or(fields[2]=='method' and bool(fields[3])),'query entity role argument');return fields[0]
    if member.startswith(instance):
        parts=member[len(instance):].split('z_');need(len(parts)==2 and decoded(parts[1]),'invalid instance identity');return decoded(parts[0])
    raise ValueError('foreign or unknown query member identity')

def inspect_queries(path,step,deadline):
    deadline();report=json.loads(path.read_text());deadline();groups=report['groups']
    need(report['format']==1 and report['crate']==step['crate_id'],'query report identity')
    need(type(report['inferred_groups'])is int and report['inferred_groups']==len(groups)>0 and report['reused_groups']==0,'fresh group counts')
    if step['expected_groups'] is not None:need(len(groups)==step['expected_groups'],'authored fixture group count')
    ids=set();members=set();owners=set();ordered=[]
    for group in groups:
        deadline();names=group['members'];need(isinstance(names,list) and names and all(isinstance(n,str)and n for n in names),'query members')
        need(group['cached'] is False and group['id'] not in ids and group['id']=='Query_'+encoded(step['crate_id'])+'z_'+encoded(names[0]),'query id/freshness')
        need(isinstance(group['semantic_fingerprint'],str)and group['semantic_fingerprint'] and isinstance(group['query_key'],str)and group['query_key'],'missing query fingerprints')
        for member in names:
            need(member not in members,'duplicate declaration across groups');members.add(member);owners.add(member_owner(member,step['crate_id']))
        ids.add(group['id']);ordered.append({'id':group['id'],'members':names})
    need(owners==set(step['expected_value_modules']),'value-bearing module coverage/foreign owner')
    need(set(step['required_members']).issubset(members),'missing authored per-module value witnesses')
    return {'crate':report['crate'],'inferred_groups':len(groups),'reused_groups':0,'all_uncached':True,'ordered_groups':ordered,'covered_modules':sorted(owners),'declaration_members':len(members),'scope':'Actual ordered query identities and module/value witnesses; not an independent full semantic proof'}

def wire_integrity(path,schemas,deadline,allow_envelope=False):
    size=path.stat().st_size;need(80<=size<=512*1024**2,'artifact size')
    def region(stream,start,length,allowed,envelope=False):
        deadline();stream.seek(start);head=stream.read(min(80,length));need(len(head)>=64,'short artifact header')
        if head[:8]==b'MLFBIN\r\n':
            need(length>=80,'short binary header')
            version,flags,schema,header,total,ns,so,sl,nn,no,nl,edges,nr,ro,rl,nw,sw,crc=struct.unpack_from('<18I',head,8)
            need(version==1 and flags==0 and schema in allowed and header==80,'wire version/schema/header')
            need(total==length and so==80 and no==so+sl and ro==no+nl and ro+rl==total,'wire sections/trailing bytes')
            need(nn>0 and nr>0 and nw==max(1,(nn-1).bit_length()) and sw==(max(1,(ns-1).bit_length())if ns else 1),'wire reference widths/counts')
            need(rl==(nr*nw+7)//8,'wire root-section length');zero=76;summary={'format':'MLFBIN-v1','schema':schema,'bytes':length,'nodes':nn,'roots':nr}
        else:
            need(envelope and head[:8]==b'MLFCR2\r\n','unknown artifact magic')
            v,flags,schema,header,total,chunks,fragments,directory,entry,db,payload,legacy,reserved,crc=struct.unpack_from('<14I',head,8)
            need(v==2 and flags==0 and schema==4 and header==directory==64 and total==length and entry==32 and reserved==0 and legacy in [0,1],'envelope header')
            need(1<=chunks<=(length-64)//112 and db==chunks*32 and payload==64+db and payload<=length,'envelope directory bounds')
            need((fragments==0 and chunks==1)or(fragments>0 and 2<=chunks<=fragments+1),'envelope fragment count')
            offset=payload;first=0
            for index in range(chunks):
                deadline();stream.seek(start+64+index*32);row=stream.read(32);need(len(row)==32,'short envelope directory')
                role,ordinal,begin,count,beginning,number,kind,res=struct.unpack('<8I',row)
                need(ordinal==index and res==0 and begin==offset and 80<=count<=length-offset,'envelope region bounds')
                need((index==0 and(role,kind,beginning,number)==(0,3,0,0))or(index>0 and role==1 and kind==4 and beginning==first and 0<number<=fragments-first),'envelope region role')
                region(stream,start+begin,count,[kind]);offset+=count;first+=number
            need(offset==length and first==fragments,'envelope complete coverage');zero=60;summary={'format':'MLFCR2-v2','schema':4,'bytes':length,'chunks':chunks}
        stream.seek(start);position=0;computed=0
        while position<length:
            deadline();block=stream.read(min(1048576,length-position));need(bool(block),'truncated artifact while checksumming')
            if position<=zero<position+len(block):
                at=zero-position;block=block[:at]+b'\0'*4+block[at+4:]
            computed=zlib.crc32(block,computed);position+=len(block)
        need(computed==crc,'artifact CRC mismatch');summary['crc32_verified']=True;return summary
    with path.open('rb')as stream:return region(stream,0,size,schemas,allow_envelope)

# Added independent bounded DAG framing; no typed evaluator or shared MLF decoder.
import hashlib
class Bits:
    def __init__(self,data):self.data=data;self.pos=0
    def bits(self,n):
        need(0<=n<=64 and self.pos+n<=len(self.data)*8,'bitstream truncated')
        value=0;used=0
        while n:
            k=min(n,8-self.pos%8);value|=((self.data[self.pos//8]>>(self.pos%8))&((1<<k)-1))<<used
            self.pos+=k;used+=k;n-=k
        return value
    def var(self):
        value=0
        for i in range(10):
            x=self.bits(8);part=x&127
            need(i<9 or (x<128 and part<=1),'varint overflow')
            need(x>=128 or i==0 or part!=0,'noncanonical varint')
            value|=part<<(7*i)
            if x<128:return value
        raise ValueError('varint too long')
    def end(self):
        remain=len(self.data)*8-self.pos
        need(remain<8 and self.bits(remain)==0,'section padding/length')

def dag(path,schema,deadline):
    wire_integrity(path,[schema],deadline)
    data=path.read_bytes();v=struct.unpack_from('<18I',data,8)
    ns,so,sl,nn,no,nl,edges,nr,ro,rl,nw,sw=v[5:17]
    need(nn<=2000000 and edges<=8000000 and ns<=1000000,'independent decoder resource cap')
    sb=Bits(data[so:so+sl]);symbols=[]
    for _ in range(ns):
        deadline();size=sb.var();need(size<=sl and size*8<=len(sb.data)*8-sb.pos,'symbol bound')
        raw=bytes(sb.bits(8)for _ in range(size));symbols.append(raw.decode('utf-8',errors='strict'))
    sb.end();need(len(set(symbols))==len(symbols),'duplicate symbol')
    nb=Bits(data[no:no+nl]);nodes=[];seen=set();used_edges=0
    for i in range(nn):
        if i%256==0:deadline()
        kind=nb.bits(2)
        if kind==0:entry=(kind,nb.var())
        elif kind==1:entry=(kind,nb.bits(64))
        elif kind==2:
            symbol=nb.bits(sw);need(symbol<ns,'symbol reference');entry=(kind,symbol)
        else:
            tag=nb.var();arity=nb.var();need(tag<=2147483647 and arity<=edges-used_edges and arity*nw<=len(nb.data)*8-nb.pos,'tag/edge bounds')
            children=tuple(nb.bits(nw)for _ in range(arity));need(all(x<i for x in children),'forward reference');used_edges+=arity;entry=(kind,tag,children)
        need(entry not in seen,'noncanonical duplicate node');seen.add(entry);nodes.append(entry)
    nb.end();need(used_edges==edges,'edge count')
    rb=Bits(data[ro:ro+rl]);roots=[rb.bits(nw)for _ in range(nr)];rb.end();need(all(x<nn for x in roots),'root bounds')
    return symbols,nodes,roots

def node(nodes,index,tag,count=None):
    row=nodes[index];need(row[0]==3 and row[1]==tag and (count is None or len(row[2])==count),'node tag/arity')
    return row[2]
def text_value(symbols,nodes,index):
    row=nodes[index];need(row[0]==2,'text node required');return symbols[row[1]]

def builtin_pair(prefix,deadline):
    ci=Path(str(prefix)+'.mlfci');co=Path(str(prefix)+'.mlfco')
    s,n,r=dag(ci,3,deadline);need(len(r)==1,'builtin roots')
    fields=node(n,r[0],242,13);modules=[text_value(s,n,x)for x in node(n,fields[2],1)]
    need('Prelude'in modules and 'MLF.Primitive'in modules,'builtin modules absent')
    return dict(interface=wire_integrity(ci,[3],deadline),object=wire_integrity(co,[4],deadline,allow_envelope=True),modules=modules)

def full_artifact(prefix,cache,contract,deadline):
    ci=Path(str(prefix)+'.mlfci');co=Path(str(prefix)+'.mlfco');report_path=Path(str(prefix)+'.queries')
    wire=[wire_integrity(ci,[3],deadline),wire_integrity(co,[8],deadline)]
    coverage=inspect_queries(report_path,contract,deadline);report=json.loads(report_path.read_text())
    results=cache/'query-graph-v2/results';need(results.is_dir()and not results.is_symlink(),'results directory')
    all_results={}
    # Authenticate ALL result filenames, not merely the report-selected subset.
    for p in sorted(results.iterdir()):
        deadline();need(p.is_file()and not p.is_symlink()and re.fullmatch('[0-9a-f]{64}\\.mlfqr',p.name),'unexpected result')
        digest=hashlib.sha256(p.read_bytes()).hexdigest();need(digest==p.stem,'result content SHA mismatch')
        wire_integrity(p,[6],deadline);all_results[p.stem]=p
    mappings=[]
    for group in report['groups']:
        key=group['query_key'];need(re.fullmatch('[0-9a-f]{64}',key)and key in all_results,'missing raw node')
        s,n,roots=dag(all_results[key],6,deadline);need(len(roots)==1,'raw node roots')
        children=node(n,roots[0],425,2);fields=node(n,children[1],400,7)
        need(text_value(s,n,fields[0])=='raw'and text_value(s,n,fields[1])==group['id'],'raw/group mapping')
        mappings.append(dict(id=group['id'],query_key=key,raw_fragment_fingerprint=text_value(s,n,fields[2]),reported_semantic_fingerprint=group['semantic_fingerprint']))
    return dict(wire=wire,coverage=coverage,result_files=len(all_results),raw_group_mappings=mappings,
                query_key_basis='SHA256 entire schema6 value bytes, not producer/session hash',typed_decode=False)

def same_raw(left,right,deadline):
    need(left.stat().st_size==right.stat().st_size,'raw size mismatch')
    with left.open('rb')as a,right.open('rb')as b:
        while True:
            deadline();x=a.read(1048576);y=b.read(1048576);need(x==y,'raw byte mismatch')
            if not x:break

