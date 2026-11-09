#!/usr/bin/env python3
"""Closed typed validation and cache closure inspection over the independent DAG.
This validates syntax/identity, not the compiler's checked-term proof judgment.
"""
from pathlib import Path
import hashlib
import json
import re
from artifact_binary_reference import Invalid, MAGIC, read_document, physical_inventory, require, tree_document

CONTRACT_PATH = Path(__file__).with_name('artifact_structure_contract.json')
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))
ALIASES = {'Modules.Role':'Role', 'Modules.Entity':'Entity'}
SCHEMAS = {}
for family, tag, constructor, fields in CONTRACT['schema_fields']:
    SCHEMAS.setdefault(ALIASES.get(family,family), {})[tag] = tuple(fields)
SCHEMAS['InterfaceInstance'] = {173: (['list',['pair','String','Kind']], ['list','SPredicate'],
                                     'String',['list','SType'],['list','String'])}
SCHEMAS['RawUnitObject'] = {241: ('UnitInterface','XTerm')}
SCHEMAS['DataContext'] = {244: (['list','DataDecl'],)}
SCHEMAS['Primitive'] = {32: ('PrimitiveCode',)}
SCHEMAS['Bool'] = {6: (), 7: ()}
# Existing public open-object ABI, independently described by its 430/401
# records (also consumed by crate-query-graph/finish_receipts.py).
SCHEMAS['OpenFinal'] = {401: ('String', 'String', ['list','String'],
    ['list','XName'], 'XTerm', ['list','XName'], ['list','XName'])}
SCHEMAS['OpenPackage'] = {430: ('String', 'String', 'String',
    ['list',['pair','String','String']], ['list',['pair','String','String']], ['list','OpenFinal'])}
OPEN_FORMAT = 'MLF-OPEN-CRATE-1/checker-1'


def frozen(value):
    return tuple(frozen(x) for x in value) if isinstance(value,(list,tuple)) else value

def validate_type(document, root, family):
    pending, seen = [(root,frozen(family))], set()
    while pending:
        index, typ = pending.pop()
        if (index,typ) in seen: continue
        seen.add((index,typ)); node = document.nodes[index]
        if typ in ('Int','PrimitiveCode'):
            require(node.kind == 0, 'typed integer leaf')
            if typ=='PrimitiveCode': require(0 <= node.data <= 133, 'closed primitive ABI')
        elif typ=='String': require(node.kind == 2, 'typed text leaf')
        elif typ=='Double': require(node.kind == 1, 'typed IEEE bits leaf')
        else:
            require(node.kind == 3, 'typed constructor node')
            tag, children = node.data
            if isinstance(typ,tuple):
                form,*args=typ
                if form=='list':
                    require(tag==1,'typed list tag'); fields = [args[0]]*len(children)
                elif form=='maybe':
                    require(tag in (4,5),'typed Maybe tag'); fields = [] if tag==4 else args
                elif form in ('pair','triple'):
                    require(tag==(2 if form=='pair' else 3),'typed product tag'); fields=args
                else: raise Invalid('unknown frozen schema combinator')
            else:
                require(typ in SCHEMAS and tag in SCHEMAS[typ], 'closed typed constructor tag: '+str(typ))
                fields=SCHEMAS[typ][tag]
            require(len(children)==len(fields), 'typed constructor arity')
            pending.extend((i,frozen(t)) for i,t in zip(children,fields))
    return len(seen)


def value_node(value, tag=None, arity=None):
    require(value[0]=='node', 'expected typed node')
    require(tag is None or value[1]==tag,'expected typed tag')
    require(arity is None or len(value[2])==arity,'expected typed arity')
    return value[2]
def text(value):
    require(value[0]=='text','expected text'); return value[1]
def list_values(value): return value_node(value,1)
def pack(values): return ''.join(str(len(x))+':'+x for x in values)
def unpack(source):
    values=[]
    while source:
        count,sep,rest=source.partition(':')
        require(sep and count.isascii() and count.isdecimal() and str(int(count))==count,'legacy scalar framing')
        size=int(count); require(size<=len(rest),'legacy scalar length')
        values.append(rest[:size]); source=rest[size:]
    return values

def n(tag,*children): return ('node',tag,tuple(children))
def s(value): return ('text',value)
def l(*values): return n(1,*values)
def builtin_datatypes():
    def param(name): return n(20,s(name))
    def applied(name,*args): return n(22,s(name),l(*args))
    def constructor(name,*fields): return n(25,s(name),l(*fields))
    def data(name,parameters,*constructors): return n(26,s(name),l(*(s(p) for p in parameters)),l(*constructors))
    source=[data('()',[],constructor('()')),data('[]',['a'],constructor('[]'),constructor(':',param('a'),applied('[]',param('a'))))]
    for arity in range(2,65):
        name='('+','*(arity-1)+')'; parameters=['a'+str(x) for x in range(1,arity+1)]
        source.append(data(name,parameters,constructor(name,*(param(x) for x in parameters))))
    stack=data('MLFStackFrame',[],constructor('MLFStackFrame',*[applied('String')]*4,*[applied('Int')]*4))
    evidence=data('MLFStackEvidence',[],constructor('MLFStackEvidence',applied('MLFCallStack')))
    return [data('MLFLegacyUnit',[],constructor('MLFLegacyUnit')),*source[:5],stack,evidence,*source[5:]]

def logical_context(declarations, key_format):
    """Independent datatype projection of the complete v6 or v7 source query key.
    This is a logical key oracle; it is never stored as a binary payload.
    """
    def tagged(tag,*fields): return pack([tag,*fields])
    def kind(value):
        fs=value_node(value)
        return tagged('star') if value[1]==10 else tagged('kind-arrow',kind(fs[0]),kind(fs[1]))
    def canonical_field(value,scope,depth):
        fs=value_node(value); tag=value[1]
        if tag==20:
            name=text(fs[0]); name=name if name=='$MLF.Stack.callStack' else scope.get(name,'global:'+name)
            return n(20,s(name))
        if tag in (21,23):
            a,b=(canonical_field(x,scope,depth) for x in fs)
            if tag==23 and a[1]==22:
                name,args=value_node(a,22,2); return n(22,name,l(*list_values(args),b))
            return n(tag,a,b)
        if tag==22: return n(22,fs[0],l(*(canonical_field(x,scope,depth) for x in list_values(fs[1]))))
        require(tag==24,'closed field tag')
        name='type:'+str(depth); extended=dict(scope); extended[text(fs[0])]=name
        return n(24,s(name),fs[1],canonical_field(fs[2],extended,depth+1))
    def field(value):
        fs=value_node(value); tag=value[1]
        if tag==20:return tagged('parameter',text(fs[0]))
        if tag==21:return tagged('function-field',field(fs[0]),field(fs[1]))
        if tag==22:return tagged('applied-field',text(fs[0]),pack([field(x) for x in list_values(fs[1])]))
        if tag==23:return tagged('application-field',field(fs[0]),field(fs[1]))
        require(tag==24,'closed field tag');return tagged('quantified-field',text(fs[0]),kind(fs[1]),field(fs[2]))
    def data(value):
        name,parameters,constructors=value_node(value,arity=3)
        if value[1]==26: binders=[(text(x),n(10)) for x in list_values(parameters)]
        else:
            require(value[1]==27,'closed datatype tag');binders=[(text(a),b) for a,b in (value_node(x,2,2) for x in list_values(parameters))]
        scope={name:'type:'+str(i) for i,(name,_) in enumerate(binders)}
        ps=pack([tagged('parameter',scope[name] if name!='$MLF.Stack.callStack' else name,kind(k)) for name,k in binders])
        cs=[]
        for constructor in list_values(constructors):
            cname,fields=value_node(constructor,25,2)
            cs.append(tagged('constructor',text(cname),pack([field(canonical_field(x,scope,len(binders))) for x in list_values(fields)])))
        return tagged('data',text(name),ps,pack(cs))
    require(key_format in ('MLF-SOURCE-CRATE-QUERY-6','MLF-SOURCE-CRATE-QUERY-7'), 'known source key format')
    builtins = builtin_datatypes() if key_format == 'MLF-SOURCE-CRATE-QUERY-6' else []
    return pack([data(x) for x in [*builtins,*declarations]])


def query_payload_root(doc):
    if len(doc.roots) == 1:
        return doc.roots[0]
    require(len(doc.roots) == 2, 'source query root count')
    address, root = doc.roots
    require(address == 0 and doc.nodes[address].kind == 2 and doc.nodes[address].data == 0,
            'source query address must own the first symbol')
    require(re.fullmatch('[0-9a-f]{64}',doc.symbols[0]), 'invalid source query address')
    payload = doc.nodes[root]
    require(payload.kind == 3, 'addressed query payload node')
    tag, children = payload.data
    require((tag == 302 and len(children) == 3 and children[0] == address) or
            (tag == 303 and len(children) == 5 and children[1] == address) or
            (tag in (305,306) and len(children) == (3 if tag == 305 else 5) and children[0] == address),
            'source query address disagrees with payload')
    return root


def inspect_artifact(raw, schema):
    doc=read_document(raw,schema)
    if schema == 2:
        root = query_payload_root(doc)
    else:
        require(len(doc.roots)==1,'one artifact root')
        root = doc.roots[0]
    if schema in (1,3,4,7):
        validate_type(doc,root,{1:'DataContext',3:'CrateInterfaceFields',4:'CrateObjectFields',7:'OpenPackage'}[schema])
        if schema == 7: inspect_open_package(doc)
    else:
        require(schema == 2, 'closed artifact schema inventory')
        node=doc.nodes[root];require(node.kind==3,'query node root');tag,children=node.data
        if tag==300:
            require(len(children)==2,'inline query arity')
            validate_type(doc,children[0],'String');validate_type(doc,children[1],'RawUnitObject')
        elif tag==301:
            require(len(children)==4,'shared query arity')
            for i,t in zip(children,('String',('list','String'),'UnitInterface','XTerm')):validate_type(doc,i,t)
            value=doc.values()[-1];ref,compact,iface,body=value[2]
            require(re.fullmatch('[0-9a-f]{64}',text(ref)) is not None,'safe context digest')
            fields=[text(x) for x in list_values(compact)]
            require(len(fields)==8 and fields[0] in ('MLF-SOURCE-CRATE-QUERY-6','MLF-SOURCE-CRATE-QUERY-7'),'complete compact source key')
            require(not list_values(value_node(iface,240,8)[3]),'shared query header has no duplicated datatype list')
        elif tag in (302,303,305,306):
            if tag in (305,306):
                require(len(doc.roots) == 2, 'source result slot requires an addressed record')
            shape = ('String','String','RawUnitObject') if tag in (302,305) else (
                'String','String','String','UnitInterface','XTerm')
            require(len(children) == len(shape), 'fingerprinted source query arity')
            for child, family in zip(children, shape):
                validate_type(doc, child, family)
            fields = doc.values()[-1][2]
            require(all(re.fullmatch('[0-9a-f]{64}',text(value)) for value in fields[:2 if tag in (302,305) else 3]),
                    'source query SHA-256 spelling')
            if tag in (303,306):
                require(not list_values(value_node(fields[3],240,8)[3]), 'inline data in contextual header')
        else: raise Invalid('closed query envelope tag')
    return doc



def inspect_open_package(doc):
    """Validate open syntax and explicit reference identities, not a type proof."""
    fmt, checker, association, bindings, datatypes, finals = value_node(doc.values()[0],430,6)
    require(text(fmt) == OPEN_FORMAT, 'open package format')
    expected = hashlib.sha256(tree_document([n(431,s('MLF/shared-haskell-v1'),s(OPEN_FORMAT),
        l(*builtin_datatypes()))],schema=6)).hexdigest()
    require(text(checker) == expected, 'open checker identity')
    commitments = unpack(text(association))
    require(commitments and all(re.fullmatch('[0-9a-f]{64}',x) for x in commitments),
            'open interface association hashes')
    def references(value):
        rows = [(text(k),text(h)) for k,h in (value_node(x,2,2) for x in list_values(value))]
        names = [name for name,_ in rows]
        require(names == sorted(set(names)), 'open references strictly ordered')
        require(all(re.fullmatch('[0-9a-f]{64}',h) for _,h in rows), 'open reference SHA256')
        return set(names)
    binding_keys, datatype_keys = references(bindings), references(datatypes)
    def binder(value):
        number,hint = value_node(value,31,2)
        require(number[0] == 'int' and number[1] >= 0 and text(hint) and '\0' not in text(hint),
                'open binder identity')
        return number[1],text(hint)
    groups, actual_keys = [], set()
    for final in list_values(finals):
        group,stamp,ds,ps,body,owned,used = value_node(final,401,7)
        groups.append(text(group))
        require(re.fullmatch('[0-9]+-[0-9]+',text(stamp)), 'open fragment stamp spelling')
        names = [text(x) for x in list_values(ds)]
        require(len(names) == len(set(names)) and set(names) <= datatype_keys, 'open datatype references')
        params = [binder(x) for x in list_values(ps)]
        exports = [binder(x) for x in list_values(owned)]
        reads = [binder(x) for x in list_values(used)]
        require(exports, 'open fragment owns declarations')
        for values in (params,exports):
            require(len(values) == len({hint for _,hint in values}), 'open duplicate binding reference')
        both = params + exports
        require(len(both) == len({i for i,_ in both}), 'open duplicate binder identity')
        require(len(reads) == len({i for i,_ in reads}) and set(reads) <= set(params),
                'open used parameter identity')
        actual_keys.update(hint for _,hint in both)
    require(len(groups) == len(set(groups)), 'open duplicate fragment')
    require(actual_keys == binding_keys, 'open binding reference inventory')


def binary_object_schema(raw):
    # Dispatch is committed by the physical schema; never try another parser
    # when an identified schema fails CRC, version, shape or semantic checks.
    require(raw.startswith(MAGIC) and len(raw) >= 80, 'binary object header')
    schema = int.from_bytes(raw[16:20],'little')
    require(schema in (4,7), 'closed object schema inventory')
    return schema


def inspect_crate_pair(metadata, body, schema, dependency_metadata=()):
    interface = inspect_artifact(metadata,3)
    fields = value_node(interface.values()[0],242,13)
    require(schema in (4,7), 'closed object schema inventory')
    object_doc = inspect_artifact(body,schema)
    if schema == 4:
        require(value_node(object_doc.values()[0],243,3)[1] == interface.values()[0],
                'binary full object/interface exact metadata')
        return interface,object_doc
    require(text(fields[11]) == hashlib.sha256(body).hexdigest(), 'open crate SHA256')
    package = value_node(object_doc.values()[0],430,6)
    def normalized(meta):
        result = list(meta)
        result[1] = l(*(n(3,key,s(''),semantic) for key,path,semantic in
                        (value_node(x,3,3) for x in list_values(meta[1]))))
        result[11] = s('open-object')
        return hashlib.sha256(tree_document([n(242,*result)],schema=6)).hexdigest()
    dependencies = [value_node(inspect_artifact(raw,3).values()[0],242,13) for raw in dependency_metadata]
    by_name = {text(meta[0]):meta for meta in dependencies}
    require(len(by_name) == len(dependencies) and text(fields[0]) not in by_name,
            'open dependency interface inventory')
    pending = [text(value_node(x,3,3)[0]) for x in list_values(fields[1])]
    reached = set()
    while pending:
        key = pending.pop()
        require(key in by_name, 'open missing dependency interface')
        if key in reached: continue
        reached.add(key)
        pending.extend(text(value_node(x,3,3)[0]) for x in list_values(by_name[key][1]))
    require(reached == set(by_name), 'open unrelated dependency interface')
    require(unpack(text(package[2])) == [normalized(fields),*(normalized(by_name[key]) for key in sorted(by_name))],
            'open complete interface association')
    actual = []
    for final in list_values(package[-1]):
        group,stamp,ds,ps,term,owned,used = value_node(final,401,7)
        names = [text(value_node(x,31,2)[1]) for x in list_values(owned)]
        encode = lambda name: ''.join(str(ord(char))+'_' for char in name)
        require(text(group) == 'Query_'+encode(text(fields[0]))+'z_'+encode(min(names)),
                'open fragment owner')
        actual.extend(names)
    expected = [text(value_node(x,2,2)[0]) for x in list_values(fields[9])]
    require(len(actual) == len(set(actual)) and actual == expected, 'open ordered ownership inventory')
    return interface,object_doc



def open_pair_controls(pair, dependencies):
    """Mutate the actual Session pair, repairing transport CRC and paired SHA.

    Ordinary checksum failures alone cannot satisfy these typed/association
    controls. Production formal-check separately establishes checked terms.
    """
    metadata,body = pair
    interface,document = inspect_crate_pair(metadata,body,7,dependencies)
    root = document.values()[0]
    fields = list(value_node(interface.values()[0],242,13))
    package = list(value_node(root,430,6))
    finals = list(list_values(package[-1]))
    require(finals, 'open controls require actual final fragment')
    rejected = []
    def refuse(name, action, reason):
        try: action()
        except Invalid as error:
            require(str(error) == reason, 'open negative diagnostic: '+name+': '+str(error))
            rejected.append(name)
        else: raise Invalid('accepted open negative: '+name)
    def changed(value, schema=7):
        data = tree_document([value],schema=schema)
        updated = list(fields); updated[11] = s(hashlib.sha256(data).hexdigest())
        return tree_document([n(242,*updated)],schema=3),data
    def mutation(name, value, reason):
        candidate = changed(value)
        refuse(name,lambda: inspect_crate_pair(*candidate,7,dependencies),reason)
    def header(name,index,value,reason):
        altered = list(package); altered[index] = value
        mutation(name,n(430,*altered),reason)
    def fragment(name,index,value,reason):
        altered = list(value_node(finals[0],401,7)); altered[index] = value
        header(name,5,l(n(401,*altered),*finals[1:]),reason)
    refuse('open-as-closed',lambda: inspect_crate_pair(metadata,body,4,dependencies),'schema mismatch')
    unknown = changed(root,8)
    refuse('unknown-object-schema',lambda: binary_object_schema(unknown[1]),'closed object schema inventory')
    mutation('wrong-root-tag',n(431,*package),'closed typed constructor tag: OpenPackage')
    mutation('wrong-root-arity',n(430,*package[:-1]),'typed constructor arity')
    header('wrong-format',0,s(OPEN_FORMAT+'-other'),'open package format')
    header('wrong-checker',1,s('0'*64),'open checker identity')
    header('malformed-association',2,s('64:short'),'legacy scalar length')
    association = unpack(text(package[2])); association[0] = '0'*64
    header('wrong-associated-interface',2,s(pack(association)),'open complete interface association')
    refs = list(list_values(package[3])); require(refs, 'open controls require actual binding reference')
    header('duplicate-reference',3,l(*refs,refs[0]),'open references strictly ordered')
    header('missing-reference',3,l(*refs[1:]),'open binding reference inventory')
    key,digest = value_node(refs[0],2,2)
    header('malformed-reference-sha',3,l(n(2,key,s('g'*64)),*refs[1:]),'open reference SHA256')
    fragment('datatype-out-of-scope',2,l(s('missing-datatype')),'open datatype references')
    fragment('wrong-body-type',4,s('not a term'),'typed constructor node')
    owned = list(list_values(value_node(finals[0],401,7)[5])); number,hint = value_node(owned[0],31,2)
    fragment('negative-binder',5,l(n(31,('int',-1),hint),*owned[1:]),'open binder identity')
    fragment('duplicate-owned-binder',5,l(*owned,owned[0]),'open duplicate binding reference')
    fragment('used-owned-as-parameter',6,l(owned[0]),'open used parameter identity')
    fragment('wrong-owner',0,s('different-owner'),'open fragment owner')
    header('duplicate-fragment',5,l(*finals,finals[0]),'open duplicate fragment')
    bad_fields = list(fields); bad_fields[11] = s('0'*64)
    refuse('wrong-paired-sha',lambda: inspect_crate_pair(tree_document([n(242,*bad_fields)],schema=3),
        body,7,dependencies),'open crate SHA256')
    if dependencies:
        refuse('missing-dependency-interface',lambda: inspect_crate_pair(metadata,body,7),
               'open missing dependency interface')
    return {'accepted':'actual Session open7 pair with independently reconstructed association',
            'rejected':rejected,'mutations_repair_crc_and_paired_sha':True}


def verify_source_result(doc):
    """Hash the bounded canonical result independently of the production writer."""
    query_payload_root(doc)
    _, tag, fields = doc.values()[-1]
    if tag in (305,306):
        key, result, *body = fields
        template = ('node', tag, (key, ('text', '~'*64), *body))
        raw = tree_document([key, template], schema=2)
        require(hashlib.sha256(raw).hexdigest() == text(result), 'source result slot fingerprint')
        return text(key)
    if tag == 303:
        ref, key, result, header, body = fields
        material = (key, ref, header, body)
    elif tag == 302:
        key, result, unit = fields
        material = (key, unit)
    else:
        raise Invalid('missing source result fingerprint')
    raw = tree_document([('node',304,material)],schema=2)
    require(hashlib.sha256(raw).hexdigest() == text(result),'source result fingerprint')
    return text(key)


def cache_snapshot(root, active_hashes):
    inventory=physical_inventory(root);files=inventory['files'];records={};contexts=set();legacy=[];details={}
    for key in active_hashes:
        require(re.fullmatch('[0-9a-f]{64}',key) is not None,'query filename digest')
        name=key+'.mlfq'; require(name in files,'reachable record exists');raw=(root/name).read_bytes()
        full=None
        if raw.startswith(MAGIC):
            doc=inspect_artifact(raw,2);value=doc.values()[-1];details[name]=doc.accounting()
            if value[1] in (302,303,305,306):
                require(verify_source_result(doc)==key, 'stored fingerprint matches source query filename')
                version = 4 if value[1] in (305,306) else 3 if len(doc.roots)==2 else 2
                representation=f'MLFBIN-QUERY-INLINE-{version}'
                if value[1] in (303,306):
                    digest=text(value[2][2 if value[1]==306 else 0]); context='context-'+digest+'.mlfqc'
                    require(context in files and files[context]['sha256']==digest,'context exact physical SHA256')
                    cdoc=inspect_artifact((root/context).read_bytes(),1)
                    contexts.add(context); details[context]=cdoc.accounting()
                    representation=f'MLFBIN-QUERY-SHARED-{version}'
            elif value[1]==300:
                full=text(value[2][0]); representation='MLFBIN-QUERY-INLINE-1'
            else:
                ref,compact,_,_=value[2];digest=text(ref);context='context-'+digest+'.mlfqc'
                require(context in files and files[context]['sha256']==digest,'context exact physical SHA256')
                cdoc=inspect_artifact((root/context).read_bytes(),1)
                declarations=list_values(value_node(cdoc.values()[0],244,1)[0])
                fields=[text(x) for x in list_values(compact)]
                full=pack(fields[:5]+[logical_context(declarations,fields[0])]+fields[5:])
                contexts.add(context);details[context]=cdoc.accounting();representation='MLFBIN-QUERY-SHARED-1'
        else:
            try:fields=unpack(raw.decode('utf-8','strict'))
            except UnicodeError as error:raise Invalid('legacy UTF8') from error
            require(fields and fields[0] in ('MLF-QUERY-CACHE-1','MLF-QUERY-CACHE-2','MLF-QUERY-CACHE-3') and
                    len(fields)==(3 if fields[0]=='MLF-QUERY-CACHE-2' else 4),'known legacy query')
            representation=fields[0];legacy.append(name)
            if representation=='MLF-QUERY-CACHE-3':
                digest=fields[1]; require(re.fullmatch('[0-9a-f]{64}',digest) is not None,'legacy safe context ref')
                context='context-'+digest+'.mlfqc';require(context in files and files[context]['sha256']==digest,'legacy exact context SHA')
                carrier=unpack((root/context).read_bytes().decode('utf-8','strict'));compact=unpack(fields[2])
                require(len(carrier)==2 and carrier[0]=='MLF-SOURCE-QUERY-CONTEXT-1' and len(compact)==8,'legacy context/key shape')
                full=pack(compact[:5]+[carrier[1]]+compact[5:]);contexts.add(context)
            else:full=fields[1]
        if full is not None:
            require(hashlib.sha256(full.encode('utf-8')).hexdigest()==key,'unchanged full logical source/query SHA filename')
        records[name]=representation
    reachable=set(records)|contexts;others=set(files)-reachable
    return dict(inventory, all_cache_logical_bytes=inventory['all_logical_bytes'],
                all_cache_pathname_conservative_allocated_bytes=inventory['all_pathname_conservative_allocated_bytes'],
                active_records=records,reachable_contexts=sorted(contexts),legacy_records=legacy,
                reachable_files=sorted(reachable),reachable_logical_bytes=sum(files[x]['bytes'] for x in reachable),
                reachable_file_allocated_bytes=sum(files[x]['allocated'] for x in reachable),
                other_physical_files=sorted(others),other_physical_bytes=sum(files[x]['bytes'] for x in others),
                unreachable_context_files=sorted(x for x in others if x.endswith('.mlfqc')),
                retained_old_query_files=sorted(x for x in others if x.endswith('.mlfq')),
                scratch_and_lock_files=sorted(x for x in others if not x.endswith(('.mlfq','.mlfqc'))),
                binary_details=details)


def fixture_roots():
    first={}
    for row in CONTRACT['schema_fields']:first.setdefault(ALIASES.get(row[0],row[0]),row)
    def sample(typ,seed):
        if isinstance(typ,list):
            form,*args=typ
            if form=='list':return l(*(sample(args[0],3*seed+i) for i in (1,2,1)))
            if form=='maybe':return n(4) if seed%2==0 else n(5,sample(args[0],seed))
            return n(2 if form=='pair' else 3,*(sample(t,seed*5+i+1) for i,t in enumerate(args)))
        typ=ALIASES.get(typ,typ)
        if typ=='String':return s('field-'+str(seed)+'-α😀\0')
        if typ=='Int':return ('int',-(3*seed+7))
        if typ=='Double':return ('bits',seed)
        if typ=='Bool':return n(7 if seed%2 else 6)
        if typ=='Primitive':return n(32,('int',131))
        if typ=='RawUnitObject':return n(241,sample('UnitInterface',seed),sample('XTerm',seed+1))
        if typ=='InterfaceInstance':
            return n(173,l(n(2,sample('String',seed),n(10))),l(),sample('String',seed+1),
                     l(n(100,sample('String',seed+2))),l(sample('String',seed+3)))
        return ctor(first[typ],seed)
    def ctor(row,seed):return n(row[1],*(sample(t,seed*7+i+1) for i,t in enumerate(row[3])))
    return tuple([ctor(row,i+1) for i,row in enumerate(CONTRACT['schema_fields'])]+
                 [n(32,('int',code)) for _,code in CONTRACT['primitive_codes']])
